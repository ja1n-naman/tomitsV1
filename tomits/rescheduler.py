"""v1.4 automatic rescheduling. Local, deterministic, no UI imports.

Triggers: a task fails, is skipped, or runs over; or (v1.7) a task with its
own time takes a slot where planner-placed tasks are ("claim"). Each trigger builds a
*proposal* (nothing is written); only accept() changes the database, and
undo_last() restores the exact previous plan.

Rules:
- A failed / skipped task needs a stored reason before anything happens
  (services enforces it when closing; build_for_closed re-checks).
- The failed / skipped task stays on its day as a record. A new linked
  copy is placed; its goal contribution is logged only when it's done.
- Places are searched in today's window (from now) and then tomorrow's.
  Nothing goes beyond tomorrow; what doesn't fit is "unplaced".
- Placement reuses the v1.3 logic: priority order, history-based time of
  day when there's enough history, earliest free slot otherwise.
- Fixed, pinned, done and already-started tasks never move. Unpinned
  auto-placed tasks may be shifted, and a higher-priority item may
  displace a lower-priority one (which is then placed by the same rules).
- An overrun that would hit a fixed / pinned task is not applied; the
  proposal carries a collision and the caller picks shorten / continue /
  leave.

Tuning is at the top; TASKS.md describes how a proposal is built.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import planner as pl
from .errors import TaskError
from .models import USER_PLACED, Placement, RescheduleLog, Task, TaskReason, TaskStatus
from . import services as svc
from .services import (BLOCKING_STATUSES, Claim, find_overlap, format_duration, get_task, is_movable,
                       overlap_message)

# ---------- tuning ----------
MAX_RESCHEDULES = 3   # at this many reschedules of one chain, ask: keep / split / drop
DAYS_AHEAD = 1        # today + this many days (1 = tomorrow). Never more.

CLOSED = (TaskStatus.FAILED.value, TaskStatus.SKIPPED.value)
SNAPSHOT_FIELDS = ("planned_for", "start_time", "duration_min", "placement", "plan_reason", "move_reason",
                   "heads_up_sent", "end_alert_sent", "title", "title_typed", "priority", "purpose", "position")


# ---------- proposal data ----------

@dataclass
class Move:
    kind: str                         # "copy" (new linked task), "shift" (existing task), "extend" (overrun),
                                      # "claim" (the task taking its own time: added or changed)
    title: str
    priority: int
    duration: int
    reason: str
    task_id: Optional[int] = None     # existing task (shift / extend)
    source_id: Optional[int] = None   # original task (copy)
    from_day: Optional[date] = None
    from_start: Optional[time] = None
    to_day: Optional[date] = None     # None with to_start None = unplaced
    to_start: Optional[time] = None
    new_duration: Optional[int] = None
    count: int = 0                    # reschedule count the copy will carry

    @property
    def unplaced(self) -> bool:
        return self.kind != "extend" and self.to_start is None


@dataclass
class Collision:
    task_id: int
    title: str
    start: datetime
    end: datetime
    placement: str

    @property
    def message(self) -> str:
        return f"task {self.task_id} '{self.title}' ({self.start:%H:%M}-{self.end:%H:%M}, {self.placement})"


@dataclass
class Proposal:
    trigger: str                      # "failed", "skipped", "overrun", "claim"
    task_id: int
    title: str
    today: date
    moves: List[Move] = field(default_factory=list)
    collisions: List[Collision] = field(default_factory=list)
    cap_reached: bool = False         # MAX_RESCHEDULES hit: needs keep / split / drop
    chain_count: int = 0
    choice: Optional[str] = None      # the cap or collision choice used to build it
    requested_end: Optional[datetime] = None
    claim: Optional[Claim] = None     # trigger "claim": the change waiting on this proposal

    @property
    def placed(self) -> List[Move]:
        return [m for m in self.moves if not m.unplaced]

    @property
    def unplaced(self) -> List[Move]:
        return sorted((m for m in self.moves if m.unplaced), key=lambda m: (m.priority, m.title))

    @property
    def needs_choice(self) -> bool:
        return bool(self.collisions) or (self.cap_reached and self.choice is None)

    @property
    def summary(self) -> str:
        if self.trigger == "claim":
            c = self.claim
            end = datetime.combine(c.day, c.start) + timedelta(minutes=c.minutes)
            return f"'{c.title}' takes its own time {c.start:%H:%M}-{end:%H:%M}"
        what = {"failed": "failed", "skipped": "skipped", "overrun": "ran over"}[self.trigger]
        return f"task {self.task_id} '{self.title}' {what}"


# ---------- board: free time on today and tomorrow ----------

def _describe_fixed(t: Task, now: datetime) -> str:
    if t.status == TaskStatus.DONE.value:
        return "done"
    if t.placement in USER_PLACED:
        return t.placement
    if t.placement == Placement.AUTO.value and t.start_at <= now:
        return "already started"
    return "fixed"


class _Board:
    def __init__(self, s: Session, days: Sequence[date], window: Tuple[time, time], now: datetime,
                 skip_ids=()):
        self.days = list(days)
        self.bounds: Dict[date, Tuple[datetime, datetime]] = {}
        self.fixed: Dict[date, List[Tuple[datetime, datetime]]] = {d: [] for d in self.days}
        self.movable: Dict[date, Dict[int, Task]] = {d: {} for d in self.days}
        self.placed: Dict[date, List[Tuple[datetime, datetime]]] = {d: [] for d in self.days}
        for d in self.days:
            start, end = datetime.combine(d, window[0]), datetime.combine(d, window[1])
            self.bounds[d] = (max(start, pl._ceil_step(now)) if d == now.date() else start, end)
            for t in s.scalars(select(Task).where(Task.planned_for == d)):
                if t.id in skip_ids or t.start_time is None or t.status not in BLOCKING_STATUSES:
                    continue
                if is_movable(t, now):
                    self.movable[d][t.id] = t
                else:
                    self.fixed[d].append((t.start_at, t.end_at))

    def gaps(self, d: date, without: Optional[int] = None) -> List[Tuple[datetime, datetime]]:
        busy = list(self.fixed[d]) + list(self.placed[d])
        busy += [(t.start_at, t.end_at) for i, t in self.movable[d].items() if i != without]
        return pl.free_gaps(*self.bounds[d], busy)


@dataclass
class _Item:
    key: str
    title: str
    duration: int
    priority: int
    goal_id: Optional[int]
    cause: str
    task: Optional[Task] = None       # existing task being shifted
    source: Optional[Task] = None     # original of a copy
    from_day: Optional[date] = None
    from_start: Optional[time] = None
    count: int = 0

    @property
    def sort_key(self):
        return (self.priority, self.duration, self.key)

    @property
    def proxy(self) -> Task:
        return Task(title=self.title, goal_id=self.goal_id)


def _item_for_task(t: Task, cause: str) -> _Item:
    return _Item(f"task:{t.id}", t.title, t.duration_min, t.priority, t.goal_id, cause, task=t,
                 from_day=t.planned_for, from_start=t.start_time)


def _best_slot(gaps, need: timedelta, day: date, pref) -> Tuple[Optional[datetime], str]:
    fits = [(g0, g1) for g0, g1 in gaps if g1 - g0 >= need]
    if not fits:
        return None, ""
    if pref is None:
        return fits[0][0], "first free slot, by priority"
    target = datetime.combine(day, time(0)) + timedelta(minutes=pref.minute)
    best = min(((abs(min(max(target, g0), g1 - need) - target), min(max(target, g0), g1 - need))
                for g0, g1 in fits))
    return best[1], pref.reason


def _from_label(item: _Item, today: date) -> str:
    if item.from_start is None:
        return "no time"
    when = pl._clock(item.from_start.hour * 60 + item.from_start.minute)
    return when if item.from_day == today else f"{when} {item.from_day:%a %d %b}"


def _place_all(board: _Board, items: List[_Item], pool, today: date) -> List[Move]:
    queue = sorted(items, key=lambda i: i.sort_key)
    moves: List[Move] = []
    while queue:
        item = queue.pop(0)
        need = timedelta(minutes=item.duration)
        pref, why = pl.time_preference(item.proxy, pool)
        slot, day, detail, victim = None, None, "", None
        for d in board.days:
            slot, detail = _best_slot(board.gaps(d), need, d, pref)
            if slot:
                day = d
                break
        if slot is None:
            # displace the least important, latest lower-priority unpinned task that makes room
            cands = sorted(((d, t) for d in board.days for t in board.movable[d].values() if t.priority > item.priority),
                           key=lambda x: (-x[1].priority, board.days.index(x[0]), -x[1].start_at.timestamp()))
            for d, t in cands:
                slot, detail = _best_slot(board.gaps(d, without=t.id), need, d, pref)
                if slot:
                    day, victim = d, t
                    del board.movable[d][t.id]
                    queue.append(_item_for_task(t, f"made room for '{item.title}' (higher priority)"))
                    queue.sort(key=lambda i: i.sort_key)
                    break
        if slot is not None:
            board.placed[day].append((slot, slot + need))
        head = f"moved from {_from_label(item, today)}: {item.cause}"
        if victim is not None:
            head += f", higher priority than '{victim.title}'"
        if slot is None:
            reason = f"{head}; unplaced: no room today or tomorrow (needs {format_duration(item.duration)})"
        else:
            where = "tomorrow, " if day != today else ""
            reason = f"{head}; {where}{detail if pref else 'first free slot, by priority'}"
        kind = "shift" if item.task is not None else "copy"
        moves.append(Move(
            kind=kind, title=item.title, priority=item.priority, duration=item.duration, reason=reason,
            task_id=item.task.id if item.task else None, source_id=item.source.id if item.source else None,
            from_day=item.from_day, from_start=item.from_start,
            to_day=day, to_start=slot.time() if slot else None, count=item.count,
        ))
    return moves


def _days(now: datetime) -> List[date]:
    return [now.date() + timedelta(days=i) for i in range(DAYS_AHEAD + 1)]


# ---------- trigger: failed or skipped ----------

def build_for_closed(s: Session, task_id: int, window: Tuple[time, time], now: Optional[datetime] = None,
                     choice: Optional[str] = None) -> Proposal:
    """Proposal for a failed / skipped task. `choice` answers the cap
    question: "keep", "split" or "drop"."""
    now = now or datetime.now()
    task = get_task(s, task_id)
    if task.status not in CLOSED:
        raise TaskError(f"Task {task_id} is {task.status}; only failed or skipped tasks are rescheduled "
                        "(a running-over task is extended instead).")
    latest = task.reasons[-1] if task.reasons else None
    if latest is None or latest.status != task.status or not (latest.reason or "").strip():
        raise TaskError(f"A reason is required before task {task_id} can be rescheduled.")
    if task.rescheduled_copies:
        c = task.rescheduled_copies[0]
        raise TaskError(f"Task {task_id} was already rescheduled as task {c.id}.")
    today = now.date()
    prop = Proposal(task.status, task.id, task.title, today, chain_count=task.reschedule_count + 1, choice=choice)
    if prop.chain_count >= MAX_RESCHEDULES:
        prop.cap_reached = True
        if choice is None:
            return prop
    if choice == "drop":
        return prop
    cause = f"task {task.status}"
    base = dict(title=task.title, priority=task.priority, goal_id=task.goal_id, cause=cause, source=task,
                from_day=task.planned_for, from_start=task.start_time, count=prop.chain_count)
    if choice == "split" and task.duration_min >= 2:
        first = (task.duration_min + 1) // 2
        items = [_Item(f"copy:{task.id}:1", duration=first, **{**base, "title": f"{task.title} (part 1)"}),
                 _Item(f"copy:{task.id}:2", duration=task.duration_min - first,
                       **{**base, "title": f"{task.title} (part 2)"})]
    else:
        items = [_Item(f"copy:{task.id}", duration=task.duration_min, **base)]
    board = _Board(s, _days(now), window, now)
    prop.moves = _place_all(board, items, pl.history_pool(s, today), today)
    return prop


# ---------- trigger: running over ----------

def build_for_overrun(s: Session, task_id: int, new_end: datetime, window: Tuple[time, time],
                      now: Optional[datetime] = None, choice: Optional[str] = None) -> Proposal:
    """Proposal for a task still going until `new_end`. If that would hit a
    fixed / pinned / done task, the proposal only carries collisions unless
    `choice` is "shorten" (end where the blocker starts), "continue" (end
    there and put the rest in the next free slot) or "leave" (change nothing)."""
    now = now or datetime.now()
    today = now.date()
    task = get_task(s, task_id)
    if task.status != TaskStatus.PENDING.value:
        raise TaskError(f"Task {task_id} is already {task.status}.")
    if task.start_at is None:
        raise TaskError(f"Task {task_id} has no time, so it can't run over.")
    if task.planned_for != today:
        raise TaskError("Only today's tasks can run over.")
    midnight = datetime.combine(today + timedelta(days=1), time(0))
    if new_end <= task.end_at:
        raise TaskError(f"The new end must be after {task.end_at:%H:%M}, when '{task.title}' ends now.")
    if new_end > midnight:
        raise TaskError("A task can't run past midnight.")
    prop = Proposal("overrun", task.id, task.title, today, choice=choice, requested_end=new_end)

    def pushable(t: Task) -> bool:
        # A planned task due to start when (or after) this one was meant to end
        # hasn't really begun while this one is still going, even if its start
        # time has passed.
        return (t.status == TaskStatus.PENDING.value and t.start_time is not None
                and t.placement == Placement.AUTO.value and (t.start_at > now or t.start_at >= task.end_at))

    blockers = sorted(
        (t for t in s.scalars(select(Task).where(Task.planned_for == today, Task.id != task.id))
         if t.start_time is not None and t.status in BLOCKING_STATUSES and not pushable(t)
         and t.start_at < new_end and t.end_at > task.end_at),
        key=lambda t: t.start_at)
    rest = 0
    if blockers:
        if choice not in ("shorten", "continue", "leave"):
            prop.collisions = [Collision(t.id, t.title, t.start_at, t.end_at, _describe_fixed(t, now)) for t in blockers]
            return prop
        if choice == "leave":
            return prop
        first = blockers[0]
        cut = max(first.start_at, task.end_at)
        if choice == "shorten" and cut <= task.end_at:
            raise TaskError(f"'{first.title}' starts right when '{task.title}' ends; there's no room to extend it.")
        if choice == "continue":
            rest = int((new_end - cut).total_seconds() // 60)
        new_end = cut
    if new_end > task.end_at:
        prop.moves.append(Move(
            kind="extend", title=task.title, priority=task.priority, duration=task.duration_min,
            reason=f"ran over: extended to {new_end:%H:%M}", task_id=task.id, from_day=today,
            from_start=task.start_time, to_day=today, to_start=task.start_time,
            new_duration=int((new_end - task.start_at).total_seconds() // 60)))
    # affected = the chain of unpinned planned tasks the overrun pushes: each
    # one that starts before the pushed end of the previous one
    affected, cursor = [], new_end
    followers = sorted((t for t in s.scalars(select(Task).where(Task.planned_for == today, Task.id != task.id))
                        if pushable(t) and t.end_at > task.start_at), key=lambda t: (t.start_at, t.id))
    for t in followers:
        if t.start_at >= cursor:
            break
        affected.append(t)
        cursor = max(cursor, t.start_at) + timedelta(minutes=t.duration_min)
    board = _Board(s, _days(now), window, now, skip_ids={task.id, *(t.id for t in affected)})
    board.fixed[today].append((task.start_at, new_end))
    items = [_item_for_task(t, f"'{task.title}' ran over to {new_end:%H:%M}") for t in affected]
    if rest > 0:
        items.append(_Item(f"copy:{task.id}:rest", f"{task.title} (rest)", rest, task.priority, task.goal_id,
                           f"rest of '{task.title}' after '{blockers[0].title}' ({blockers[0].start_at:%H:%M})",
                           source=task, from_day=today, from_start=new_end.time(), count=task.reschedule_count))
    prop.moves += _place_all(board, items, pl.history_pool(s, today), today)
    return prop


# ---------- trigger: a task takes its own time (v1.7) ----------

def build_for_claim(s: Session, claim: Claim, window: Tuple[time, time], now: Optional[datetime] = None) -> Proposal:
    """Proposal for a task given its own time (added, edited, or moved) where
    planner-placed tasks are. The task keeps that time; the tasks in the way
    are placed by the usual rules: on that day (and tomorrow, if it's today),
    never beyond tomorrow; what doesn't fit is unplaced. Refused if a fixed,
    pinned, done or started task is in the way (neither moves)."""
    now = now or datetime.now()
    today = now.date()
    if claim.day < today:
        raise TaskError(f"{claim.day:%a %d %b} is in the past; past days are never changed.")
    begin = datetime.combine(claim.day, claim.start)
    end = begin + timedelta(minutes=claim.minutes)
    in_way = []
    for t in s.scalars(select(Task).where(Task.planned_for == claim.day, Task.start_time.is_not(None),
                                          Task.status.in_(BLOCKING_STATUSES)).order_by(Task.start_time, Task.id)):
        if t.id == claim.task_id or not (begin < t.end_at and t.start_at < end):
            continue
        if not is_movable(t, now):
            svc.check_slot(s, claim.title, claim.day, claim.start, claim.minutes, claim.task_id, now)  # raises, naming both
        in_way.append(t)
    prop = Proposal("claim", claim.task_id or 0, claim.title, today, claim=claim)
    prop.moves.append(Move(
        kind="claim", title=claim.title, priority=claim.priority, duration=claim.minutes,
        reason="its own time: " + ("added" if claim.op == "add" else "changed by you") + "; it never moves",
        task_id=claim.task_id, from_day=claim.was_day, from_start=claim.was_start,
        to_day=claim.day, to_start=claim.start))
    if not in_way:
        return prop
    days = [d for d in _days(now) if d >= claim.day] or [claim.day]
    if claim.day not in days:
        days = [claim.day]
    board = _Board(s, days, window, now, skip_ids={claim.task_id, *(t.id for t in in_way)})
    board.fixed[claim.day].append((begin, end))
    cause = f"'{claim.title}' has its own time {begin:%H:%M}-{end:%H:%M}"
    items = [_item_for_task(t, cause) for t in in_way]
    prop.moves += _place_all(board, items, pl.history_pool(s, today), today)
    return prop


def build(s: Session, trigger, window: Tuple[time, time], now: Optional[datetime] = None,
          choice: Optional[str] = None) -> Proposal:
    """Any trigger tuple: ("closed", task_id, None), ("overrun", task_id,
    new_end) or ("claim", Claim, None). Used by the terminal, voice and web."""
    kind, subject, new_end = trigger
    if kind == "closed":
        return build_for_closed(s, subject, window, now=now, choice=choice)
    if kind == "claim":
        return build_for_claim(s, subject, window, now=now)
    return build_for_overrun(s, subject, new_end, window, now=now, choice=choice)


# ---------- accept and undo ----------

def _serialize(v):
    if isinstance(v, (date, time)):
        return v.isoformat()
    return v


def _deserialize(field_name: str, v):
    if v is None:
        return None
    if field_name == "planned_for":
        return date.fromisoformat(v)
    if field_name == "start_time":
        return time.fromisoformat(v)
    return v


def _check_overlaps(s: Session, checks) -> None:
    """checks: (task, day, start, minutes). Raise if any range overlaps."""
    s.flush()
    for t, day, start, minutes in checks:
        other = find_overlap(s, day, start, minutes, exclude_task_id=t.id)
        if other is not None:
            raise TaskError(overlap_message(t.title, day, start, minutes, other))


def accept(s: Session, prop: Proposal, now: Optional[datetime] = None) -> Optional[RescheduleLog]:
    """Apply a proposal. Refused if a choice is still open or the plan changed
    since it was built. Returns the undo log entry (None if nothing moved)."""
    if prop.needs_choice:
        raise TaskError("Choose what to do first (see the warning).")
    if not prop.moves:
        return None
    snapshot, created, checks = {}, [], []
    try:
        for m in prop.moves:
            if m.kind == "claim":
                c = prop.claim
                if c.op == "add":
                    t = svc.claim_task(s, c)
                    s.add(t)
                    created.append(t)
                else:
                    t = get_task(s, c.task_id)
                    snapshot[str(t.id)] = {f: _serialize(getattr(t, f)) for f in SNAPSHOT_FIELDS}
                    svc.apply_claim(s, c)
                checks.append((t, c.day, c.start, c.minutes))
                continue
            if m.kind == "copy":
                src = get_task(s, m.source_id)
                day = m.to_day or prop.today
                copy = Task(
                    title=m.title, purpose=src.purpose, duration_min=m.duration, planned_for=day,
                    start_time=m.to_start, position=0, status=TaskStatus.PENDING.value, goal_id=src.goal_id,
                    priority=src.priority, placement=Placement.AUTO.value if m.to_start else Placement.OVERFLOW.value,
                    plan_reason=m.reason, move_reason=m.reason, rescheduled_from=src,
                    reschedule_count=m.count, heads_up_sent=False, end_alert_sent=False,
                )
                s.add(copy)
                created.append(copy)
                if m.to_start:
                    checks.append((copy, day, m.to_start, m.duration))
                continue
            t = get_task(s, m.task_id)
            if t.status != TaskStatus.PENDING.value or t.start_time != m.from_start or t.planned_for != m.from_day:
                raise TaskError("The plan changed since this proposal was made. Nothing was changed; try again.")
            snapshot[str(t.id)] = {f: _serialize(getattr(t, f)) for f in SNAPSHOT_FIELDS}
            if m.kind == "extend":
                old_end = t.end_at
                t.duration_min = m.new_duration
                t.end_alert_sent = False
                t.move_reason = m.reason
                checks.append((t, t.planned_for, old_end.time(), int((t.end_at - old_end).total_seconds() // 60)))
            elif m.to_start is None:
                t.start_time, t.placement = None, Placement.OVERFLOW.value
                t.plan_reason = t.move_reason = m.reason
            else:
                t.planned_for, t.start_time, t.placement = m.to_day, m.to_start, Placement.AUTO.value
                t.plan_reason = t.move_reason = m.reason
                t.heads_up_sent = t.end_alert_sent = False
                checks.append((t, m.to_day, m.to_start, t.duration_min))
        _check_overlaps(s, checks)
    except TaskError:
        s.rollback()
        raise
    log = RescheduleLog(trigger=prop.summary, snapshot=json.dumps(snapshot),
                        created_ids=json.dumps([c.id for c in created]))
    s.add(log)
    s.commit()
    return log


def last_log(s: Session) -> Optional[RescheduleLog]:
    return s.scalar(select(RescheduleLog).order_by(RescheduleLog.id.desc()).limit(1))


def undo_last(s: Session) -> RescheduleLog:
    """Undo the most recent accepted reschedule (one step). Removes the copies
    it created and restores every changed task exactly. Failure records and
    their reasons are never touched."""
    log = last_log(s)
    if log is None or log.undone:
        raise TaskError("There's no reschedule to undo.")
    created = [t for t in (s.get(Task, i) for i in json.loads(log.created_ids)) if t is not None]
    snapshot = json.loads(log.snapshot)
    changed = [t for t in (s.get(Task, int(i)) for i in snapshot) if t is not None]
    for t in created + changed:
        if t.status != TaskStatus.PENDING.value:
            raise TaskError(f"Can't undo: task {t.id} '{t.title}' is already {t.status}.")
    try:
        for c in created:
            s.delete(c)
        checks = []
        for t in changed:
            for f, v in snapshot[str(t.id)].items():
                setattr(t, f, _deserialize(f, v))
            if t.start_time is not None:
                checks.append((t, t.planned_for, t.start_time, t.duration_min))
        _check_overlaps(s, checks)
    except TaskError as e:
        s.rollback()
        raise TaskError(f"Can't undo: {e}") from None
    log.undone = True
    s.commit()
    return log


# ---------- reason history ----------

def reason_history(s: Session, goal_id: Optional[int] = None, start: Optional[date] = None,
                   end: Optional[date] = None) -> List[TaskReason]:
    """Failed / skipped records with their reasons, newest first."""
    q = select(TaskReason).where(TaskReason.status.in_(CLOSED))
    if goal_id is not None:
        q = q.where(TaskReason.goal_id == goal_id)
    if start is not None:
        q = q.where(TaskReason.task_date >= start)
    if end is not None:
        q = q.where(TaskReason.task_date <= end)
    return list(s.scalars(q.order_by(TaskReason.task_date.desc(), TaskReason.id.desc())))
