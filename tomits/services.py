"""Business logic. No Rich/UI imports here, so this can later run as a
background service or be driven by voice."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import titletime as TT
from . import tracking
from .errors import TaskError
from .models import (DEFAULT_PRIORITY, PRIORITY_NAMES, REASON_REQUIRED, USER_PLACED, Placement, Task, TaskReason,
                     TaskStatus)
from .settings import DEFAULT_DAY_END, DEFAULT_DAY_START, DEFAULT_TASK_MINUTES
from .titletime import AmbiguousTime

__all__ = ["TaskError", "AmbiguousTime"]  # re-exported: callers use services.TaskError

DEFAULT_WINDOW = (time.fromisoformat(DEFAULT_DAY_START), time.fromisoformat(DEFAULT_DAY_END))


# ---------- durations ----------

_DURATION_RE = re.compile(r"^\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m?)?\s*$", re.IGNORECASE)


def parse_duration(text: str) -> int:
    """'25' -> 25, '90m' -> 90, '1h' -> 60, '1h30' / '1h 30m' -> 90."""
    m = _DURATION_RE.match(text or "")
    if not m or (m.group(1) is None and m.group(2) is None):
        raise TaskError(f"Can't read duration {text!r}. Try 25, 90m, 1h or 1h30m.")
    minutes = int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
    if minutes <= 0:
        raise TaskError("Duration must be more than 0 minutes.")
    return minutes


def format_duration(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m}m"
    return f"{h}h" if h else f"{m}m"


# ---------- clock times ----------

_TIME_RE = re.compile(r"^\s*(\d{1,2})(?::?(\d{2}))?\s*(am|pm)?\s*$", re.IGNORECASE)


def parse_time(text: str) -> time:
    """'14:30', '9:05', '930', '9', '2pm', '2:30 pm' -> time."""
    m = _TIME_RE.match(text or "")
    if not m:
        raise TaskError(f"Can't read time {text!r}. Try 14:30, 9:05 or 2:30pm.")
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ampm:
        if not 1 <= hour <= 12:
            raise TaskError(f"{text!r}: with am/pm the hour must be 1-12.")
        hour = hour % 12 + (12 if ampm.lower() == "pm" else 0)
    if hour > 23 or minute > 59:
        raise TaskError(f"{text!r} is not a valid time of day.")
    return time(hour, minute)


def format_time(t: time) -> str:
    return t.strftime("%H:%M")


# ---------- tasks ----------

@dataclass
class TaskDraft:
    """One line of a day plan, before it is saved."""

    title: str
    duration_min: Optional[int]
    goal_id: Optional[int] = None
    purpose: Optional[str] = None
    start_time: Optional[time] = None
    priority: int = DEFAULT_PRIORITY
    ampm: Optional[str] = None         # answer to "am or pm?" for a time in the title
    title_typed: Optional[str] = None  # set when a time was read out of the title
    day: Optional[date] = None         # set when the title named another day


def parse_priority(value) -> int:
    """1-4, or urgent/high/normal/low (first letter is enough)."""
    raw = str(value).strip().lower()
    if raw.isdigit() and int(raw) in PRIORITY_NAMES:
        return int(raw)
    for num, name in PRIORITY_NAMES.items():
        if raw and name.startswith(raw):
            return num
    raise TaskError("Priority is 1 urgent, 2 high, 3 normal or 4 low.")


def _next_position(s: Session, day: date) -> int:
    current = s.scalar(select(func.max(Task.position)).where(Task.planned_for == day))
    return (current or 0) + 1


def _build_task(s: Session, draft: TaskDraft, day: date, position: int, today: Optional[date] = None) -> Task:
    title = (draft.title or "").strip()
    if not title:
        raise TaskError("A task needs a title.")
    if draft.duration_min is None or draft.duration_min <= 0:
        raise TaskError("A task needs a duration above 0 minutes.")
    # Goals are created only on the tracking pages; tasks may only pick an
    # existing goal whose period hasn't ended.
    tracking.check_task_goal(s, draft.goal_id, today)
    return Task(
        title=title,
        duration_min=draft.duration_min,
        goal_id=draft.goal_id,
        purpose=(draft.purpose or "").strip() or None,
        planned_for=day,
        position=position,
        status=TaskStatus.PENDING.value,
        start_time=draft.start_time,
        priority=parse_priority(draft.priority),
        placement=Placement.FIXED.value if draft.start_time else None,
        heads_up_sent=False,
        end_alert_sent=False,
        title_typed=draft.title_typed,
    )


# ---------- overlaps ----------

# Tasks whose time slot is taken. Failed and skipped tasks free their slot.
BLOCKING_STATUSES = (TaskStatus.PENDING.value, TaskStatus.DONE.value)


def _range(day: date, start: time, duration_min: int):
    begin = datetime.combine(day, start)
    return begin, begin + timedelta(minutes=duration_min)


def _fmt_range(begin: datetime, end: datetime) -> str:
    return f"{begin:%H:%M}-{end:%H:%M}"


def find_overlap(
    s: Session, day: date, start: Optional[time], duration_min: int, exclude_task_id: Optional[int] = None
) -> Optional[Task]:
    """First pending or done task on `day` whose time range overlaps
    [start, start + duration). Back-to-back (end == start) is not an overlap.
    Untimed tasks never overlap anything."""
    if start is None:
        return None
    begin, end = _range(day, start, duration_min)
    others = s.scalars(
        select(Task)
        .where(Task.planned_for == day, Task.start_time.is_not(None), Task.status.in_(BLOCKING_STATUSES))
        .order_by(Task.start_time, Task.id)
    )
    for other in others:
        if other.id == exclude_task_id:
            continue
        if begin < other.end_at and other.start_at < end:
            return other
    return None


def overlap_message(title: str, day: date, start: time, duration_min: int, other: Task) -> str:
    begin, end = _range(day, start, duration_min)
    return (
        f"'{title}' ({_fmt_range(begin, end)}) overlaps task {other.id} '{other.title}' "
        f"({_fmt_range(other.start_at, other.end_at)}) on {day:%a %d %b}. "
        f"Start at {other.end_at:%H:%M} or later, or finish by {other.start_at:%H:%M}."
    )


def check_no_overlap(
    s: Session, title: str, day: date, start: Optional[time], duration_min: int,
    exclude_task_id: Optional[int] = None,
) -> None:
    """Raise TaskError naming the conflicting task. Every code path that
    adds a task or changes its time goes through here (1.4 rescheduling too)."""
    other = find_overlap(s, day, start, duration_min, exclude_task_id)
    if other is not None:
        raise TaskError(overlap_message(title, day, start, duration_min, other))


# ---------- a time written in the title (v1.7) ----------

@dataclass
class TitleTime:
    """What was read from a title: the cleaned title, the time, length and day."""
    title: str
    typed: str
    start: time
    minutes: int
    day: date
    line: str          # one short line for the screen / voice ("Read from the title: ...")


def _now_for(today: Optional[date], now: Optional[datetime]) -> datetime:
    if now is not None:
        return now
    real = datetime.now()
    return real if today is None or today == real.date() else datetime.combine(today, time(0))


def read_title_time(title: str, duration_min: Optional[int], day: date, today: date,
                    window=None, default_minutes: Optional[int] = None, ampm: Optional[str] = None,
                    now: Optional[datetime] = None, line: Optional[int] = None) -> Optional[TitleTime]:
    """The time written in a title, or None (then nothing changes and the
    planner places the task as before). A range sets the length, a single
    time gets `default_minutes`; a length given separately wins. A day word
    in the title moves the task to that day. The task always stays inside its
    day: a length past midnight is cut at midnight. Raises AmbiguousTime when
    am / pm can't be settled from the day window."""
    r = TT.read(title, today, window or DEFAULT_WINDOW, ampm=ampm, line=line)
    if r is None:
        return None
    if duration_min is not None:
        minutes, source = int(duration_min), "given"
    elif r.range_minutes is not None:
        minutes, source = r.range_minutes, "range"
    else:
        minutes, source = int(default_minutes or DEFAULT_TASK_MINUTES), "default"
    if minutes <= 0:
        raise TaskError("A task needs a duration above 0 minutes.")
    minutes, cut = TT.cap_at_midnight(r.start, minutes)
    if cut and not r.capped:
        r.notes.append("it would run past midnight, so it ends at midnight")
    the_day = r.day or day
    if the_day < today:
        raise TaskError(f"{the_day:%a %d %b} is in the past; tasks go on today or later.")
    return TitleTime(r.title, r.typed, r.start, minutes, the_day,
                     TT.describe(r, minutes, source, the_day, today, _now_for(today, now)))


def is_movable(t: Task, now: datetime) -> bool:
    """A planner-placed task that may be shifted: pending, unpinned, timed,
    not started yet."""
    return (t.status == TaskStatus.PENDING.value and t.start_time is not None
            and t.placement == Placement.AUTO.value and t.start_at > now)


@dataclass(frozen=True)
class Claim:
    """A task that takes its own time slot, waiting for a reschedule proposal
    because planner-placed tasks are in the way. Nothing is saved until the
    proposal is accepted (rescheduler.build_for_claim / accept)."""
    op: str                            # "add" or "edit"
    title: str
    day: date
    start: time
    minutes: int
    placement: str                     # fixed / pinned
    task_id: Optional[int] = None      # edit
    title_typed: Optional[str] = None
    priority: int = DEFAULT_PRIORITY
    goal_id: Optional[int] = None
    purpose: Optional[str] = None
    understood: Optional[str] = None   # the "Read from the title" line
    # edit: the task as it was when this was proposed (accept refuses if it changed)
    was_day: Optional[date] = None
    was_start: Optional[time] = None
    was_minutes: Optional[int] = None


class SlotTaken(TaskError):
    """The slot is free except for planner-placed tasks. Callers turn this into
    a v1.4 reschedule proposal (trigger ("claim", claim, None))."""

    def __init__(self, message: str, claim: Claim, task_ids: List[int]):
        super().__init__(message)
        self.claim = claim
        self.task_ids = task_ids


def _kind_of(t: Task, now: datetime) -> str:
    if t.status == TaskStatus.DONE.value:
        return "is done"
    if t.placement == Placement.PINNED.value:
        return "is pinned"
    if t.placement == Placement.AUTO.value:
        return "has already started"
    return "has a fixed time"


def check_slot(s: Session, title: str, day: date, start: Optional[time], minutes: int,
               exclude_task_id: Optional[int] = None, now: Optional[datetime] = None,
               claim: Optional[Claim] = None) -> None:
    """A task with its own time owns that time. If the slot overlaps a fixed,
    pinned, done or started task: refused, naming both (neither moves). If it
    overlaps only planner-placed tasks: SlotTaken, so the caller can show a
    reschedule proposal for them. Back-to-back is fine."""
    if start is None:
        return
    now = now or datetime.now()
    begin, end = _range(day, start, minutes)
    others = [o for o in s.scalars(
        select(Task).where(Task.planned_for == day, Task.start_time.is_not(None), Task.status.in_(BLOCKING_STATUSES))
        .order_by(Task.start_time, Task.id))
        if o.id != exclude_task_id and begin < o.end_at and o.start_at < end]
    if not others:
        return
    fixed = [o for o in others if not is_movable(o, now)]
    if fixed or claim is None:
        o = (fixed or others)[0]
        msg = overlap_message(title, day, start, minutes, o)
        if fixed:
            msg += f" Neither task is moved: '{o.title}' {_kind_of(o, now)}."
        raise TaskError(msg)
    names = ", ".join(f"'{o.title}' ({_fmt_range(o.start_at, o.end_at)})" for o in others)
    raise SlotTaken(f"'{title}' ({_fmt_range(begin, end)}) has its own time and overlaps {names}, placed by the "
                    f"planner. Nothing is saved yet: see the proposal to move "
                    f"{'it' if len(others) == 1 else 'them'}.", claim, [o.id for o in others])


def add_task(
    s: Session,
    title: str,
    duration_min: Optional[int],
    goal_id: Optional[int] = None,
    purpose: Optional[str] = None,
    planned_for: Optional[date] = None,
    start_time: Optional[time] = None,
    today: Optional[date] = None,
    priority: int = DEFAULT_PRIORITY,
    *,
    now: Optional[datetime] = None,
    window=None,
    default_minutes: Optional[int] = None,
    ampm: Optional[str] = None,
    read_title: bool = True,
) -> Task:
    """Add one task on the fly (defaults to today). A start time is optional;
    only tasks with one get alarms. Without a start time, a clear time written
    in the title is read (read_title_time): the task gets that time as a fixed
    task and the time is taken out of the title; `task.understood` is then the
    line describing what was read (else None). A time that overlaps only
    planner-placed tasks raises SlotTaken (a proposal moves them)."""
    base_today = today or date.today()
    day = planned_for or base_today
    now = _now_for(today, now)
    typed, understood = None, None
    if start_time is None and read_title:
        tt = read_title_time(title or "", duration_min, day, base_today, window, default_minutes, ampm, now)
        if tt is not None:
            title, typed, start_time, duration_min, day, understood = (tt.title, tt.typed, tt.start, tt.minutes,
                                                                       tt.day, tt.line)
    draft = TaskDraft(title, duration_min, goal_id, purpose, start_time, priority, title_typed=typed)
    task = _build_task(s, draft, day, _next_position(s, day), today)
    claim = Claim("add", task.title, day, start_time, task.duration_min, Placement.FIXED.value, title_typed=typed,
                  priority=task.priority, goal_id=task.goal_id, purpose=task.purpose,
                  understood=understood) if start_time is not None else None
    check_slot(s, task.title, day, start_time, task.duration_min, now=now, claim=claim)
    s.add(task)
    s.commit()
    task.understood = understood
    return task


def claim_task(s: Session, c: Claim) -> Task:
    """The task an "add" claim describes, not saved yet (rescheduler.accept adds it)."""
    draft = TaskDraft(c.title, c.minutes, c.goal_id, c.purpose, c.start, c.priority, title_typed=c.title_typed)
    task = _build_task(s, draft, c.day, _next_position(s, c.day))
    task.placement = c.placement
    return task


def apply_claim(s: Session, c: Claim) -> Task:
    """Apply an "edit" claim to its task (rescheduler.accept checks overlaps)."""
    task = get_task(s, c.task_id)
    if (task.status != TaskStatus.PENDING.value or task.planned_for != c.was_day or task.start_time != c.was_start
            or task.duration_min != c.was_minutes):
        raise TaskError("The plan changed since this proposal was made. Nothing was changed; try again.")
    if task.planned_for != c.day:
        task.position = _next_position(s, c.day)
    task.title, task.planned_for, task.start_time, task.duration_min = c.title, c.day, c.start, c.minutes
    if c.title_typed is not None:
        task.title_typed = c.title_typed
    task.priority, task.purpose = c.priority, c.purpose
    task.placement = c.placement
    task.plan_reason = "pinned: moved by you" if c.placement == Placement.PINNED.value else None
    task.heads_up_sent = task.end_alert_sent = False
    return task


def _edit_claim(task: Task, **kw) -> Claim:
    base = dict(op="edit", title=task.title, day=task.planned_for, start=task.start_time, minutes=task.duration_min,
                placement=task.placement or Placement.FIXED.value, task_id=task.id, priority=task.priority,
                goal_id=task.goal_id, purpose=task.purpose, was_day=task.planned_for, was_start=task.start_time,
                was_minutes=task.duration_min)
    base.update(kw)
    return Claim(**base)


def schedule_back_to_back(day: date, drafts: List[TaskDraft], start: time) -> List[TaskDraft]:
    """Give each draft a start time, one after another from `start`.
    A draft that already has a start time keeps it and the chain continues
    from its end. Raises if the plan would run past midnight."""
    cursor = datetime.combine(day, start)
    out = []
    for d in drafts:
        begin = datetime.combine(day, d.start_time) if d.start_time else cursor
        cursor = begin + timedelta(minutes=d.duration_min)
        if cursor.date() != day and cursor != datetime.combine(day + timedelta(days=1), time(0)):
            raise TaskError(f"The plan runs past midnight at '{d.title}'. Start earlier or plan fewer tasks.")
        out.append(TaskDraft(d.title, d.duration_min, d.goal_id, d.purpose, begin.time(), d.priority))
    return out


def check_plan_overlaps(s: Session, day: date, drafts: List[TaskDraft]) -> None:
    """Each timed draft must not overlap a saved task or another draft."""
    timed = [d for d in drafts if d.start_time is not None]
    for d in timed:
        check_no_overlap(s, d.title, day, d.start_time, d.duration_min)
    for i, a in enumerate(timed):
        a_begin, a_end = _range(day, a.start_time, a.duration_min)
        for b in timed[i + 1:]:
            b_begin, b_end = _range(day, b.start_time, b.duration_min)
            if a_begin < b_end and b_begin < a_end:
                raise TaskError(
                    f"'{b.title}' ({_fmt_range(b_begin, b_end)}) overlaps '{a.title}' "
                    f"({_fmt_range(a_begin, a_end)}) in this plan."
                )


def plan_day(
    s: Session, day: date, drafts: Iterable[TaskDraft], start: Optional[time] = None,
    today: Optional[date] = None, *, now: Optional[datetime] = None, window=None,
    default_minutes: Optional[int] = None,
) -> List[Task]:
    """Save a whole day's plan at once. All-or-nothing: if one line is
    invalid, nothing is saved. With `start`, tasks are timed back to back.
    A time written in a line's title is read like add_task does (a day word
    puts that line on its day); in this list an overlap is always refused."""
    base_today = today or date.today()
    now = _now_for(today, now)
    read, understood = [], {}
    for i, d in enumerate(drafts):
        if d.start_time is None:
            tt = read_title_time(d.title or "", d.duration_min, day, base_today, window, default_minutes, d.ampm,
                                 now, line=i)
            if tt is not None:
                d = TaskDraft(tt.title, tt.minutes, d.goal_id, d.purpose, tt.start, d.priority, d.ampm, tt.typed,
                              tt.day if tt.day != day else None)
                understood[len(read)] = tt.line
        read.append(d)
    drafts = read
    if start is not None:
        timed = iter(schedule_back_to_back(day, [d for d in drafts if d.day is None], start))
        drafts = [d if d.day is not None else _keep_extra(next(timed), d) for d in drafts]
    tasks, positions = [], {}
    for draft in drafts:
        d_day = draft.day or day
        if d_day not in positions:
            positions[d_day] = _next_position(s, d_day)
        tasks.append(_build_task(s, draft, d_day, positions[d_day], today))
        positions[d_day] += 1
    if not tasks:
        raise TaskError("The plan is empty.")
    for d_day in positions:
        check_plan_overlaps(s, d_day, [d for d in drafts if (d.day or day) == d_day])
    s.add_all(tasks)
    s.commit()
    for i, t in enumerate(tasks):
        t.understood = understood.get(i)
    return tasks


def _keep_extra(timed: TaskDraft, original: TaskDraft) -> TaskDraft:
    timed.title_typed, timed.ampm = original.title_typed, original.ampm
    return timed


def get_task(s: Session, task_id: int) -> Task:
    task = s.get(Task, task_id)
    if task is None:
        raise TaskError(f"No task with id {task_id}.")
    return task


def tasks_for_day(s: Session, day: date) -> List[Task]:
    """Timed tasks first, by start time; then untimed ones in the order added."""
    return list(
        s.scalars(
            select(Task)
            .where(Task.planned_for == day)
            .order_by(Task.start_time.is_(None), Task.start_time, Task.position, Task.id)
        )
    )


def set_start_time(s: Session, task_id: int, start_time: Optional[time], now: Optional[datetime] = None) -> Task:
    """You set, change or clear (None) a pending task's start time. Its alarms
    are re-armed for the new time. A time you set is never moved by the
    planner: a planned task becomes "pinned", any other becomes "fixed".
    Clearing the time hands the task to the planner."""
    task = get_task(s, task_id)
    if task.status != TaskStatus.PENDING.value:
        raise TaskError(f"Task {task_id} is already {task.status}; its time can't change.")
    if start_time == task.start_time:
        # unchanged: no overlap check, alarms keep their state. Confirming a
        # planned task's current slot still pins it.
        if start_time is not None and task.placement == Placement.AUTO.value:
            task.placement, task.plan_reason = Placement.PINNED.value, "pinned: kept here by you"
            s.commit()
        return task
    pin = task.placement in (Placement.AUTO.value, Placement.OVERFLOW.value, Placement.PINNED.value)
    placement = Placement.PINNED.value if pin else Placement.FIXED.value
    check_slot(s, task.title, task.planned_for, start_time, task.duration_min, exclude_task_id=task.id, now=now,
               claim=_edit_claim(task, start=start_time, placement=placement) if start_time else None)
    if start_time is None:
        task.placement, task.plan_reason = None, None
    elif pin:
        task.placement, task.plan_reason = Placement.PINNED.value, "pinned: moved by you"
    else:
        task.placement, task.plan_reason = Placement.FIXED.value, None
    task.start_time = start_time
    task.heads_up_sent = False
    task.end_alert_sent = False
    s.commit()
    return task


def update_task(s: Session, task_id: int, *, title: Optional[str] = None, duration_min: Optional[int] = None,
                priority=None, purpose: Optional[str] = None, now: Optional[datetime] = None,
                today: Optional[date] = None, window=None, default_minutes: Optional[int] = None,
                ampm: Optional[str] = None) -> Task:
    """Change a pending task's title, duration, priority or purpose. A longer
    duration is checked like any time change. A new title is read for a time
    exactly like add_task: if it has one, the task gets that time (and day) as
    a fixed task, and `task.understood` describes what was read. An unchanged
    duration doesn't count as given, so a range in the new title sets it."""
    task = get_task(s, task_id)
    if task.status != TaskStatus.PENDING.value:
        raise TaskError(f"Task {task_id} is already {task.status}; it can't be changed.")
    now = _now_for(today, now)
    today = today or now.date()
    if title is not None:
        title = title.strip()
        if not title:
            raise TaskError("A task needs a title.")
    if duration_min is not None and duration_min <= 0:
        raise TaskError("A task needs a duration above 0 minutes.")
    tt = None
    if title is not None and title != task.title:
        given = duration_min if duration_min is not None and duration_min != task.duration_min else None
        tt = read_title_time(title, given, task.planned_for, today, window, default_minutes, ampm, now)
    new_priority = parse_priority(priority) if priority is not None else task.priority
    new_purpose = (purpose.strip() or None) if purpose is not None else task.purpose
    if tt is not None:
        check_slot(s, tt.title, tt.day, tt.start, tt.minutes, exclude_task_id=task.id, now=now, claim=_edit_claim(
            task, title=tt.title, title_typed=tt.typed, day=tt.day, start=tt.start, minutes=tt.minutes,
            placement=Placement.FIXED.value, priority=new_priority, purpose=new_purpose, understood=tt.line))
        if tt.day != task.planned_for:
            task.position = _next_position(s, tt.day)
        task.title, task.title_typed, task.planned_for = tt.title, tt.typed, tt.day
        task.start_time, task.duration_min = tt.start, tt.minutes
        task.placement, task.plan_reason = Placement.FIXED.value, None
        task.heads_up_sent = task.end_alert_sent = False
    else:
        if duration_min is not None and duration_min != task.duration_min:
            check_slot(s, title or task.title, task.planned_for, task.start_time, duration_min,
                       exclude_task_id=task.id, now=now,
                       claim=_edit_claim(task, title=title or task.title, minutes=duration_min,
                                         priority=new_priority, purpose=new_purpose) if task.start_time else None)
        if title is not None:
            task.title = title
        if duration_min is not None and duration_min != task.duration_min:
            task.duration_min = duration_min
            task.end_alert_sent = False
    task.priority, task.purpose = new_priority, new_purpose
    s.commit()
    task.understood = tt.line if tt else None
    return task


def restore_typed_title(s: Session, task_id: int) -> Task:
    """Undo a time read from a title: the title goes back to exactly what was
    typed and the task loses that time (the planner places it again). Its day
    and length stay. The title isn't read again."""
    task = get_task(s, task_id)
    if task.status != TaskStatus.PENDING.value:
        raise TaskError(f"Task {task_id} is already {task.status}; it can't be changed.")
    if not task.title_typed:
        raise TaskError(f"'{task.title}' has no time read from its title.")
    task.title, task.title_typed = task.title_typed, None
    task.start_time, task.placement, task.plan_reason = None, None, None
    task.heads_up_sent = task.end_alert_sent = False
    s.commit()
    return task


def delete_task(s: Session, task_id: int) -> None:
    """Delete a pending task that has no stored reasons and no copies.
    Failed / skipped records are never deleted: their reasons are permanent."""
    task = get_task(s, task_id)
    if task.status != TaskStatus.PENDING.value:
        raise TaskError(f"Task {task_id} is {task.status}; only pending tasks can be deleted "
                        "(failed and skipped records keep their reasons).")
    if task.reasons or task.rescheduled_copies:
        raise TaskError(f"Task {task_id} has history attached, so it can't be deleted.")
    s.delete(task)
    s.commit()


def move_to_day(s: Session, task_id: int, day: date, start_time: Optional[time] = None,
                today: Optional[date] = None, now: Optional[datetime] = None) -> Task:
    """You move a pending task to another day (today or later), optionally at
    a time. With a time it's fixed there (overlap-checked); without one the
    planner places it on that day."""
    today = today or date.today()
    task = get_task(s, task_id)
    if task.status != TaskStatus.PENDING.value:
        raise TaskError(f"Task {task_id} is already {task.status}.")
    if day < today:
        raise TaskError(f"{day:%a %d %b} is in the past; tasks can only move to today or later.")
    check_slot(s, task.title, day, start_time, task.duration_min, exclude_task_id=task.id, now=_now_for(today, now),
               claim=_edit_claim(task, day=day, start=start_time, placement=Placement.FIXED.value)
               if start_time else None)
    task.planned_for = day
    task.start_time = start_time
    task.position = _next_position(s, day)
    task.placement = Placement.FIXED.value if start_time else None
    task.plan_reason = None
    task.heads_up_sent = task.end_alert_sent = False
    s.commit()
    return task


# ---------- bulk delete (v1.5.1) ----------

@dataclass
class BulkPlan:
    """What a bulk delete would remove, and what the rules keep (and why)."""
    scope: str                        # "tasks", "goals", "tasks and goals", "day"
    day: Optional[date] = None
    task_ids: List[int] = field(default_factory=list)
    goal_ids: List[int] = field(default_factory=list)
    kept: dict = field(default_factory=dict)   # reason -> count

    @property
    def empty(self) -> bool:
        return not self.task_ids and not self.goal_ids

    def describe(self) -> str:
        what = []
        if self.task_ids:
            what.append(f"{len(self.task_ids)} pending task{'s' if len(self.task_ids) != 1 else ''}")
        if self.goal_ids:
            what.append(f"{len(self.goal_ids)} goal{'s' if len(self.goal_ids) != 1 else ''}")
        where = f" on {self.day:%A %d %B}" if self.day else ""
        msg = (f"This will permanently delete {' and '.join(what)}{where}." if what
               else f"There's nothing that can be deleted{where}.")
        if self.kept:
            msg += " Kept, because the rules protect them: " + "; ".join(f"{n} {r}" for r, n in self.kept.items()) + "."
        if what:
            msg += " This can't be undone."
        return msg


def bulk_delete_plan(s: Session, scope: str, day: Optional[date] = None, today: Optional[date] = None) -> BulkPlan:
    from . import periods as PER
    from .models import Goal
    today = today or date.today()
    if scope not in ("tasks", "goals", "tasks and goals", "day"):
        raise TaskError(f"Unknown bulk delete scope '{scope}'.")
    if scope == "day":
        if day is None:
            raise TaskError("Which day should be cleared?")
        if day < today:
            raise TaskError(f"{day:%a %d %b} is in the past; past days are never changed.")
    plan = BulkPlan(scope, day if scope == "day" else None)
    kept: dict = {}

    def keep(reason, n=1):
        kept[reason] = kept.get(reason, 0) + n

    q = s.query(Task)
    if scope == "day":
        q = q.filter(Task.planned_for == day)
    all_tasks = q.all()
    if scope in ("tasks", "tasks and goals", "day"):
        for t in all_tasks:
            if t.status in (TaskStatus.FAILED.value, TaskStatus.SKIPPED.value):
                keep("failed or skipped records (their reasons are permanent)")
            elif t.status == TaskStatus.DONE.value:
                keep("done tasks (completed history)")
            elif t.reasons or t.rescheduled_copies:
                keep("tasks with history attached")
            else:
                plan.task_ids.append(t.id)
    if scope in ("goals", "tasks and goals"):
        deleting_tasks = set(plan.task_ids)
        cands = {}
        for g in s.query(Goal).all():
            if g.entry is None or PER.is_locked(g.kind, g.period_start, today):
                keep("goals in ended periods (read-only)")
            elif g.logs:
                keep("goals with logged progress")
            elif any(t.id not in deleting_tasks for t in g.tasks):
                keep("goals linked to tasks that are kept")
            else:
                cands[g.id] = g
        changed = True
        while changed:  # a goal can go only if every goal linked below it goes too
            changed = False
            for gid, g in list(cands.items()):
                if any(c.id not in cands for c in g.children):
                    del cands[gid]
                    keep("goals that kept goals link to")
                    changed = True
        order = {PER.PeriodKind.DAY: 0, PER.PeriodKind.WEEK: 1, PER.PeriodKind.MONTH: 2}
        plan.goal_ids = [g.id for g in sorted(cands.values(), key=lambda g: (order[g.kind], g.id))]
    plan.kept = kept
    return plan


def bulk_delete(s: Session, plan: BulkPlan, today: Optional[date] = None) -> Tuple[int, int]:
    """Carry out a plan from bulk_delete_plan, through the normal delete rules
    (tasks first, then goals from day up to month)."""
    from . import tracking
    for tid in plan.task_ids:
        delete_task(s, tid)
    for gid in plan.goal_ids:
        tracking.delete_goal(s, gid, today=today)
    return len(plan.task_ids), len(plan.goal_ids)


def move_next_to(s: Session, task_id: int, other_id: int, where: str, now: Optional[datetime] = None) -> Task:
    """Manual reorder: put a task right 'before' or 'after' another task
    (back-to-back). Pins it. Refused if that time overlaps something."""
    task, other = get_task(s, task_id), get_task(s, other_id)
    if task.id == other.id:
        raise TaskError("Pick a different task to move next to.")
    if other.planned_for != task.planned_for:
        raise TaskError(f"Task {other.id} is on another day.")
    if other.start_at is None:
        raise TaskError(f"Task {other.id} has no time yet, so there's nothing to line up with.")
    if where == "after":
        begin = other.end_at
    elif where == "before":
        begin = other.start_at - timedelta(minutes=task.duration_min)
    else:
        raise TaskError("Move 'before' or 'after' a task.")
    if begin.date() != task.planned_for:
        raise TaskError("That would move the task onto another day.")
    return set_start_time(s, task_id, begin.time(), now=now)


def unpin_task(s: Session, task_id: int) -> Task:
    """Hand a fixed or pinned task back to the planner. It keeps its time
    until the next re-plan, which may move it."""
    task = get_task(s, task_id)
    if task.status != TaskStatus.PENDING.value:
        raise TaskError(f"Task {task_id} is already {task.status}.")
    if task.placement not in USER_PLACED:
        raise TaskError(f"Task {task_id} isn't pinned; the planner already handles it.")
    if task.start_time is None:
        task.placement, task.plan_reason = None, None
    else:
        task.placement, task.plan_reason = Placement.AUTO.value, "unpinned: the next re-plan may move it"
    s.commit()
    return task


def overdue_tasks(s: Session, today: Optional[date] = None) -> List[Task]:
    today = today or date.today()
    return list(
        s.scalars(
            select(Task)
            .where(Task.planned_for < today, Task.status == TaskStatus.PENDING.value)
            .order_by(Task.planned_for, Task.position)
        )
    )


def _close(s: Session, task_id: int, status: TaskStatus, reason: Optional[str]) -> Task:
    task = get_task(s, task_id)
    if task.status != TaskStatus.PENDING.value:
        raise TaskError(f"Task {task_id} is already {task.status}.")
    reason = (reason or "").strip()
    if status in REASON_REQUIRED and not reason:
        raise TaskError(f"A reason is required to mark a task {status.value}.")
    task.status = status.value
    task.closed_at = datetime.now()
    if reason:
        task.reasons.append(TaskReason(
            status=status.value, reason=reason,
            # permanent snapshot of the task at the moment it was closed
            task_title=task.title, task_date=task.planned_for, priority=task.priority,
            goal_id=task.goal_id, goal_title=task.goal.title if task.goal else None,
        ))
        # no alarms for a closed record
        task.heads_up_sent = True
        task.end_alert_sent = True
    s.commit()
    return task


def link_task(s: Session, task_id: int, goal_id: Optional[int], today: Optional[date] = None) -> Task:
    """Link a pending task to an existing open goal, or unlink it (None)."""
    task = get_task(s, task_id)
    if task.status != TaskStatus.PENDING.value:
        raise TaskError(f"Task {task_id} is already {task.status}.")
    tracking.check_task_goal(s, goal_id, today)
    task.goal_id = goal_id
    s.commit()
    return task


def complete_task(
    s: Session,
    task_id: int,
    contribution: float = 0,
    mark_goal_done: bool = False,
    today: Optional[date] = None,
) -> Task:
    """Mark a task done. If it is linked to a goal:
    - numeric goal: `contribution` (default 0) is logged to it, dated today
    - no-target goal: `mark_goal_done=True` marks the goal done
    Everything is checked before anything is saved."""
    today = today or date.today()
    task = get_task(s, task_id)
    if task.status != TaskStatus.PENDING.value:
        raise TaskError(f"Task {task_id} is already {task.status}.")
    contribution = float(contribution or 0)
    if contribution < 0:
        raise TaskError("A contribution can't be negative.")
    if contribution > 0 or mark_goal_done:
        c = tracking.contribution_for(task, today)
        if c.mode == "none":
            raise TaskError("This task isn't linked to a goal.")
        if c.mode == "closed":
            raise TaskError(c.note)
        if contribution > 0 and c.mode != "amount":
            raise TaskError(f"'{task.goal.title}' has no target; mark it done instead of logging an amount.")
        if mark_goal_done and c.mode != "mark_done":
            raise TaskError(f"'{task.goal.title}' has a target; log an amount instead.")
    task = _close(s, task_id, TaskStatus.DONE, None)
    if contribution > 0:
        tracking.log_progress(s, task.goal_id, contribution, on=today, task_id=task.id, today=today)
    if mark_goal_done:
        tracking.set_goal_done(s, task.goal_id, True, today=today)
    return task


def fail_task(s: Session, task_id: int, reason: str) -> Task:
    return _close(s, task_id, TaskStatus.FAILED, reason)


def skip_task(s: Session, task_id: int, reason: str) -> Task:
    return _close(s, task_id, TaskStatus.SKIPPED, reason)
