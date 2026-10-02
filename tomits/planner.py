"""v1.3 day planner. Local, deterministic, no external services.

Given a day's tasks, place every *movable* task (pending, no time you set)
into the free gaps of the daily window, highest priority first:

- Fixed and pinned tasks (times you set) never move; they, done tasks, and
  planned tasks that have already started only block time.
- WHEN a task goes: if there is enough history of similar past tasks, the
  slot nearest the time of day where they were completed most / failed
  least; otherwise the earliest free slot (so higher priority comes first,
  ties by shorter duration).
- Then, adjacent planned tasks are swapped to match the order they usually
  had on past days.
- Tasks that don't fit anywhere are left on the day without a time and
  listed as "didn't fit".

Tuning constants are at the top; TASKS.md explains the score.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import TaskError
from .models import USER_PLACED, Placement, Task, TaskStatus
from .services import BLOCKING_STATUSES, format_duration

# ---------- tuning ----------
HISTORY_MIN_ENTRIES = 3      # similar past done/failed tasks needed before history is used
HISTORY_LOOKBACK_DAYS = 90   # only look this far back
FAIL_WEIGHT = 1.0            # a failure at an hour cancels this many completions
NEIGHBOR_WEIGHT = 0.5        # share of each entry's weight given to the hour before and after
TITLE_SIMILARITY = 0.5       # word-overlap (Jaccard) needed for "similar title"
ORDER_MIN_DAYS = 2           # "B usually before A" needs this many more days than the reverse
SLOT_STEP_MIN = 5            # placements snap to this grid (minutes)

MIN = timedelta(minutes=1)


# ---------- similarity ----------

_WORD_RE = re.compile(r"[a-z]+")


def title_words(title: str) -> frozenset:
    """Lower-case words, digits and punctuation dropped: 'Gym #2!' -> {'gym'}."""
    return frozenset(_WORD_RE.findall((title or "").lower()))


def is_similar(task: Task, past: Task) -> bool:
    """Same goal, same title words, or enough shared title words."""
    if task.goal_id is not None and task.goal_id == past.goal_id:
        return True
    a, b = title_words(task.title), title_words(past.title)
    if not a or not b:
        return False
    if a == b:
        return True
    return len(a & b) / len(a | b) >= TITLE_SIMILARITY


def history_pool(s: Session, day: date) -> List[Task]:
    """Past completed or failed tasks that had a time, within the lookback."""
    return list(
        s.scalars(
            select(Task).where(
                Task.planned_for < day,
                Task.planned_for >= day - timedelta(days=HISTORY_LOOKBACK_DAYS),
                Task.start_time.is_not(None),
                Task.status.in_((TaskStatus.DONE.value, TaskStatus.FAILED.value)),
            ).order_by(Task.planned_for, Task.start_time, Task.id)
        )
    )


# ---------- history score ----------

@dataclass(frozen=True)
class TimePreference:
    minute: int          # preferred start, minutes after midnight
    done: int            # similar completions counted
    failed: int          # similar failures counted
    hour: int

    @property
    def reason(self) -> str:
        return (f"usually completed around {_clock(self.minute)} "
                f"({self.done} done, {self.failed} failed in similar past tasks)")


def _clock(minute: int) -> str:
    h, m = divmod(minute, 60)
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}" if m else f"{h12} {suffix}"


def time_preference(task: Task, pool: Sequence[Task]) -> Tuple[Optional[TimePreference], str]:
    """(preference, reason-if-none). See TASKS.md for the score."""
    similar = [p for p in pool if is_similar(task, p)]
    if len(similar) < HISTORY_MIN_ENTRIES:
        n = len(similar)
        return None, ("no history: placed by priority" if n == 0
                      else f"too little history ({n} similar, need {HISTORY_MIN_ENTRIES}): placed by priority")
    score = [0.0] * 24
    for p in similar:
        w = 1.0 if p.status == TaskStatus.DONE.value else -FAIL_WEIGHT
        h = p.start_time.hour
        score[h] += w
        for nh in (h - 1, h + 1):
            if 0 <= nh < 24:
                score[nh] += w * NEIGHBOR_WEIGHT
    best = max(score)
    if best <= 0:
        return None, "history shows mostly misses: placed by priority"
    done_by_hour = Counter(p.start_time.hour for p in similar if p.status == TaskStatus.DONE.value)
    hour = min((h for h in range(24) if score[h] == best), key=lambda h: (-done_by_hour[h], h))
    starts = [p.start_time.hour * 60 + p.start_time.minute for p in similar
              if p.status == TaskStatus.DONE.value and p.start_time.hour == hour]
    minute = round(sum(starts) / len(starts)) if starts else hour * 60
    minute = round(minute / SLOT_STEP_MIN) * SLOT_STEP_MIN
    done = sum(1 for p in similar if p.status == TaskStatus.DONE.value)
    return TimePreference(minute, done, len(similar) - done, hour), ""


def usual_order(a: Task, b: Task, pool: Sequence[Task]) -> int:
    """Days where something like `a` started before something like `b`,
    minus days where it was the other way round."""
    first: Dict[date, Dict[str, time]] = {}
    for p in pool:
        for tag, t in (("a", a), ("b", b)):
            if is_similar(t, p):
                slot = first.setdefault(p.planned_for, {})
                if tag not in slot or p.start_time < slot[tag]:
                    slot[tag] = p.start_time
    score = 0
    for slot in first.values():
        if "a" in slot and "b" in slot and slot["a"] != slot["b"]:
            score += 1 if slot["a"] < slot["b"] else -1
    return score


# ---------- gaps ----------

Gap = Tuple[datetime, datetime]


def free_gaps(start: datetime, end: datetime, busy: Sequence[Gap]) -> List[Gap]:
    gaps, cursor = [], start
    for b0, b1 in sorted(busy):
        if b1 <= cursor or b0 >= end:
            continue
        if b0 > cursor:
            gaps.append((cursor, min(b0, end)))
        cursor = max(cursor, b1)
    if cursor < end:
        gaps.append((cursor, end))
    return gaps


def _take(gaps: List[Gap], begin: datetime, end: datetime) -> List[Gap]:
    out = []
    for g0, g1 in gaps:
        if end <= g0 or begin >= g1:
            out.append((g0, g1))
            continue
        if g0 < begin:
            out.append((g0, begin))
        if end < g1:
            out.append((end, g1))
    return out


def _ceil_step(dt: datetime) -> datetime:
    dt = dt.replace(second=0, microsecond=0) + (MIN if dt.second or dt.microsecond else timedelta(0))
    extra = (-dt.minute) % SLOT_STEP_MIN
    return dt + timedelta(minutes=extra)


# ---------- plan ----------

@dataclass
class PlanResult:
    day: date
    placed: List[Task] = field(default_factory=list)     # auto-placed this run, by start time
    overflow: List[Task] = field(default_factory=list)   # didn't fit, priority order
    kept: List[Task] = field(default_factory=list)       # fixed / pinned / started, untouched


def _is_movable(t: Task, now: datetime) -> bool:
    if t.status != TaskStatus.PENDING.value or t.placement in USER_PLACED:
        return False
    if t.placement == Placement.AUTO.value and t.start_at is not None and t.start_at <= now:
        return False  # already started: leave it where it is
    if t.placement is None and t.start_time is not None:
        return False  # a time from before v1.3 without a placement: treat as yours
    return True


def plan_day(s: Session, day: date, window: Tuple[time, time], now: Optional[datetime] = None) -> PlanResult:
    """Place the day's movable tasks. Today and future days only."""
    now = now or datetime.now()
    if day < now.date():
        raise TaskError(f"{day:%a %d %b} is in the past; past days are never changed.")
    w_start, w_end = datetime.combine(day, window[0]), datetime.combine(day, window[1])
    earliest = max(w_start, _ceil_step(now)) if day == now.date() else w_start

    tasks = list(s.scalars(select(Task).where(Task.planned_for == day).order_by(Task.id)))
    movable = [t for t in tasks if _is_movable(t, now)]
    moving = {t.id for t in movable}
    blockers = [t for t in tasks if t.id not in moving and t.start_time is not None and t.status in BLOCKING_STATUSES]
    gaps = free_gaps(earliest, w_end, [(t.start_at, t.end_at) for t in blockers])
    pool = history_pool(s, day)

    result = PlanResult(day, kept=sorted((t for t in blockers if t.status == TaskStatus.PENDING.value),
                                         key=lambda t: t.start_at))
    slots: Dict[int, Tuple[datetime, str]] = {}
    for t in sorted(movable, key=lambda t: (t.priority, t.duration_min, t.id)):
        need = timedelta(minutes=t.duration_min)
        fits = [(g0, g1) for g0, g1 in gaps if g1 - g0 >= need]
        if not fits:
            largest = max((g1 - g0 for g0, g1 in gaps), default=timedelta(0))
            slots[t.id] = (None, f"didn't fit: needs {format_duration(t.duration_min)}, largest free gap "
                                 f"{format_duration(int(largest.total_seconds() // 60)) if largest else 'none'}")
            continue
        pref, why = time_preference(t, pool)
        if pref is None:
            begin = fits[0][0]
            reason = why
        else:
            target = datetime.combine(day, time(0)) + timedelta(minutes=pref.minute)
            best = None
            for g0, g1 in fits:
                cand = min(max(target, g0), g1 - need)
                key = (abs(cand - target), cand)
                if best is None or key < best[0]:
                    best = (key, cand)
            begin = best[1]
            reason = pref.reason
            if abs(begin - target) >= timedelta(minutes=30):
                reason += f"; nearest free slot {begin:%H:%M}"
        slots[t.id] = (begin, reason)
        gaps = _take(gaps, begin, begin + need)

    # keep the order of past days: swap back-to-back planned pairs
    by_id = {t.id: t for t in movable}
    for _ in range(len(slots)):
        placed = sorted(((b, i) for i, (b, _) in slots.items() if b is not None))
        swapped = False
        for (b1, i1), (b2, i2) in zip(placed, placed[1:]):
            a, b = by_id[i1], by_id[i2]
            if b1 + timedelta(minutes=a.duration_min) != b2:
                continue
            if usual_order(b, a, pool) >= ORDER_MIN_DAYS:  # b usually comes before a
                slots[i2] = (b1, slots[i2][1] + f"; kept before '{a.title}' as on past days")
                slots[i1] = (b1 + timedelta(minutes=b.duration_min), slots[i1][1])
                swapped = True
                break
        if not swapped:
            break

    for t in movable:
        begin, reason = slots[t.id]
        new_time = begin.time() if begin else None
        if new_time != t.start_time:
            t.heads_up_sent = False
            t.end_alert_sent = False
        t.start_time = new_time
        t.placement = Placement.AUTO.value if begin else Placement.OVERFLOW.value
        t.plan_reason = reason
    s.commit()
    result.placed = sorted((t for t in movable if t.start_time is not None), key=lambda t: t.start_at)
    result.overflow = sorted((t for t in movable if t.start_time is None), key=lambda t: (t.priority, t.id))
    return result


def overflow_tasks(s: Session, day: date) -> List[Task]:
    """The day's "didn't fit" list (from the last plan), priority order."""
    return list(s.scalars(
        select(Task).where(Task.planned_for == day, Task.placement == Placement.OVERFLOW.value,
                           Task.status == TaskStatus.PENDING.value)
        .order_by(Task.priority, Task.id)
    ))
