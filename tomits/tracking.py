"""v1.1 tracking layer: day / week / month pages with goals, sacrifices,
process and review. All locking rules are enforced here, not in the UI.

Every function that changes data takes an optional `today` (defaults to
date.today()) so the rules can be tested at any date.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import periods as P
from .errors import TaskError
from .models import Goal, PeriodEntry, ProgressLog, Sacrifice, SacrificeStatus, Task

UNSET = object()  # "leave this field unchanged" in update functions


def _today(today: Optional[date]) -> date:
    return today or date.today()


def fmt_amount(x: Optional[float]) -> str:
    if x is None:
        return ""
    return str(int(x)) if float(x).is_integer() else f"{x:.2f}".rstrip("0").rstrip(".")


_AMOUNT_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)")


def parse_amount(text: str) -> float:
    """Leading number of the text as a float. Zero is allowed here."""
    m = _AMOUNT_RE.match(text or "")
    if not m:
        raise TaskError(f"Can't read amount {text!r}. Use a number like 10 or 2.5.")
    return float(m.group(1))


# ---------- period entries ----------

def get_entry(s: Session, kind, day: date) -> Optional[PeriodEntry]:
    kind = P.PeriodKind(kind)
    start = P.period_start(kind, day)
    return s.scalar(select(PeriodEntry).where(PeriodEntry.kind == kind.value, PeriodEntry.start == start))


def get_or_create_entry(s: Session, kind, day: date) -> PeriodEntry:
    entry = get_entry(s, kind, day)
    if entry is None:
        kind = P.PeriodKind(kind)
        entry = PeriodEntry(kind=kind.value, start=P.period_start(kind, day))
        s.add(entry)
        s.flush()
    return entry


def _require_open(kind, start: date, today: date, what: str) -> None:
    if P.is_locked(kind, start, today):
        raise TaskError(f"{P.label(kind, start)} has ended; its {what} are read-only.")


# ---------- goals ----------

def _norm_unit(unit: Optional[str]) -> Optional[str]:
    return (unit or "").strip() or None


def _same_unit(a: Optional[str], b: Optional[str]) -> bool:
    """Case-insensitive. A goal with no target has no unit (None)."""
    return (a or "").casefold() == (b or "").casefold()


def _unit_name(unit: Optional[str]) -> str:
    return f"'{unit}'" if unit else "no target (done / not done)"


def _validate_shape(target: Optional[float], unit: Optional[str]) -> None:
    if target is None:
        if unit:
            raise TaskError("A goal without a target can't have a unit.")
        return
    if target <= 0:
        raise TaskError("A target must be more than 0.")
    if not unit:
        raise TaskError("A goal with a target needs a unit, e.g. pages or hours.")


def _check_parent(s: Session, kind, start: date, unit: Optional[str], parent_id: Optional[int]) -> Optional[Goal]:
    if parent_id is None:
        return None
    kind = P.PeriodKind(kind)
    parent = get_goal(s, parent_id)
    parent_kind = P.PARENT_KIND[kind]
    if parent_kind is None:
        raise TaskError("Monthly goals don't link to anything.")
    if parent.kind is not parent_kind:
        raise TaskError(f"A {kind.value} goal can only link to a {parent_kind.value} goal.")
    if parent.period_start not in P.parent_starts(kind, start):
        raise TaskError(
            f"'{parent.title}' belongs to {P.label(parent.kind, parent.period_start)}, "
            f"which doesn't contain {P.label(kind, start)}."
        )
    if not _same_unit(unit, parent.unit):
        raise TaskError(
            f"Linked goals must use the same unit: this goal is {_unit_name(unit)}, "
            f"'{parent.title}' is {_unit_name(parent.unit)}."
        )
    return parent


def get_goal(s: Session, goal_id: int) -> Goal:
    goal = s.get(Goal, goal_id)
    if goal is None:
        raise TaskError(f"No goal with id {goal_id}.")
    return goal


def create_goal(
    s: Session,
    kind,
    day: date,
    title: str,
    target: Optional[float] = None,
    unit: Optional[str] = None,
    parent_id: Optional[int] = None,
    today: Optional[date] = None,
) -> Goal:
    """The only way to create a goal."""
    today = _today(today)
    kind = P.PeriodKind(kind)
    start = P.period_start(kind, day)
    _require_open(kind, start, today, "goals")
    title = (title or "").strip()
    if not title:
        raise TaskError("A goal needs a title.")
    unit = _norm_unit(unit)
    target = None if target is None else float(target)
    _validate_shape(target, unit)
    parent = _check_parent(s, kind, start, unit, parent_id)
    goal = Goal(title=title, target=target, unit=unit, parent=parent, entry=get_or_create_entry(s, kind, start))
    s.add(goal)
    s.commit()
    return goal


def update_goal(
    s: Session, goal_id: int, *, title=UNSET, target=UNSET, unit=UNSET, parent_id=UNSET, today: Optional[date] = None
) -> Goal:
    today = _today(today)
    goal = get_goal(s, goal_id)
    _require_open(goal.kind, goal.period_start, today, "goals")
    new_title = goal.title if title is UNSET else (title or "").strip()
    if not new_title:
        raise TaskError("A goal needs a title.")
    new_target = goal.target if target is UNSET else (None if target is None else float(target))
    new_unit = goal.unit if unit is UNSET else _norm_unit(unit)
    if target is not UNSET and target is None and unit is UNSET:
        new_unit = None  # switching to done / not done drops the unit
    new_parent = goal.parent_id if parent_id is UNSET else parent_id
    _validate_shape(new_target, new_unit)
    if goal.has_target != (new_target is not None) and goal.logs:
        raise TaskError("This goal has logged progress, so it can't switch between a target and done / not done.")
    parent = _check_parent(s, goal.kind, goal.period_start, new_unit, new_parent)
    for child in goal.children:
        if not _same_unit(child.unit, new_unit):
            raise TaskError(
                f"'{child.title}' links to this goal and is {_unit_name(child.unit)}. Linked goals must use the same unit."
            )
    goal.title, goal.target, goal.unit = new_title, new_target, new_unit
    goal.parent = parent  # via the relationship so both sides stay in sync
    if new_target is not None:
        goal.done_at = None
    s.commit()
    return goal


def delete_goal(s: Session, goal_id: int, today: Optional[date] = None) -> None:
    """Only for a mistake: an open goal with no logs, links or tasks."""
    today = _today(today)
    goal = get_goal(s, goal_id)
    _require_open(goal.kind, goal.period_start, today, "goals")
    if goal.logs:
        raise TaskError("This goal has logged progress; it can't be deleted.")
    if goal.children:
        raise TaskError("Other goals link to this goal; it can't be deleted.")
    if s.scalar(select(func.count()).select_from(Task).where(Task.goal_id == goal.id)):
        raise TaskError("Timetable tasks are linked to this goal; unlink them first (l in the timetable).")
    s.delete(goal)
    s.commit()


def goals_for_period(s: Session, kind, day: date) -> List[Goal]:
    entry = get_entry(s, kind, day)
    return list(entry.goals) if entry else []


def link_candidates(s: Session, kind, day: date, unit: Optional[str]) -> List[Goal]:
    """Goals one level up that a goal of this period (with this unit) may link to."""
    kind = P.PeriodKind(kind)
    parent_kind = P.PARENT_KIND[kind]
    if parent_kind is None:
        return []
    out: List[Goal] = []
    for start in P.parent_starts(kind, day):
        out += [g for g in goals_for_period(s, parent_kind, start) if _same_unit(g.unit, unit)]
    return out


def open_goals(s: Session, today: Optional[date] = None) -> List[Goal]:
    """Goals whose period hasn't ended: the ones timetable tasks may link to."""
    today = _today(today)
    goals = s.scalars(select(Goal).join(PeriodEntry)).all()
    goals = [g for g in goals if not P.is_locked(g.kind, g.period_start, today)]
    return sorted(goals, key=lambda g: (P.ORDER[g.kind], g.period_start, g.id))


# ---------- progress ----------

@dataclass(frozen=True)
class GoalProgress:
    logged: float
    target: Optional[float]
    unit: Optional[str]
    done: bool

    @property
    def has_target(self) -> bool:
        return self.target is not None

    @property
    def fraction(self) -> float:
        if self.has_target:
            return min(self.logged / self.target, 1.0)
        return 1.0 if self.done else 0.0

    @property
    def text(self) -> str:
        if self.has_target:
            return f"{fmt_amount(self.logged)}/{fmt_amount(self.target)} {self.unit}"
        return "done" if self.done else "not done"


def logged_amount(goal: Goal) -> float:
    """Own logs plus everything logged on goals that link to it, all the way
    down. No-target goals don't roll up numerically."""
    if not goal.has_target:
        return 0.0
    return sum(l.amount for l in goal.logs) + sum(logged_amount(c) for c in goal.children if c.has_target)


def progress(goal: Goal) -> GoalProgress:
    if goal.has_target:
        logged = logged_amount(goal)
        return GoalProgress(logged, goal.target, goal.unit, logged >= goal.target)
    return GoalProgress(0.0, None, None, goal.done_at is not None)


def log_progress(
    s: Session,
    goal_id: int,
    amount: float,
    on: Optional[date] = None,
    task_id: Optional[int] = None,
    today: Optional[date] = None,
) -> ProgressLog:
    today = _today(today)
    goal = get_goal(s, goal_id)
    on = on or today
    if not goal.has_target:
        raise TaskError(f"'{goal.title}' has no target; mark it done instead.")
    _require_open(goal.kind, goal.period_start, today, "progress logs")
    if not P.contains(goal.kind, goal.period_start, on):
        raise TaskError(f"{on:%a %d %b} is outside {P.label(goal.kind, goal.period_start)}.")
    if on > today:
        raise TaskError("Progress can't be logged for a future date.")
    amount = float(amount)
    if amount <= 0:
        raise TaskError("Logged amount must be more than 0.")
    log = ProgressLog(goal=goal, amount=amount, logged_for=on, task_id=task_id)
    s.add(log)
    s.commit()
    return log


def delete_log(s: Session, log_id: int, today: Optional[date] = None) -> None:
    """Undo a wrong entry while its goal's period is still open."""
    today = _today(today)
    log = s.get(ProgressLog, log_id)
    if log is None:
        raise TaskError(f"No progress log with id {log_id}.")
    _require_open(log.goal.kind, log.goal.period_start, today, "progress logs")
    s.delete(log)
    s.commit()


def set_goal_done(s: Session, goal_id: int, done: bool, today: Optional[date] = None) -> Goal:
    today = _today(today)
    goal = get_goal(s, goal_id)
    if goal.has_target:
        raise TaskError(f"'{goal.title}' has a target; log progress instead.")
    _require_open(goal.kind, goal.period_start, today, "goals")
    goal.done_at = datetime.now() if done else None
    s.commit()
    return goal


def ancestors(goal: Goal) -> List[Goal]:
    out, g = [], goal.parent
    while g is not None:
        out.append(g)
        g = g.parent
    return out


# ---------- process, sacrifices, review ----------

def set_process(s: Session, kind, day: date, text: str, today: Optional[date] = None) -> PeriodEntry:
    today = _today(today)
    kind = P.PeriodKind(kind)
    start = P.period_start(kind, day)
    _require_open(kind, start, today, "process")
    text = (text or "").strip()
    if not text:
        raise TaskError("Process can't be empty.")
    entry = get_or_create_entry(s, kind, start)
    entry.process = text
    s.commit()
    return entry


def _status(value) -> str:
    try:
        return SacrificeStatus(value).value
    except ValueError:
        raise TaskError("A sacrifice is either 'planned' or 'made'.") from None


def add_sacrifice(
    s: Session, kind, day: date, text: str, status: str = "planned", today: Optional[date] = None
) -> Sacrifice:
    today = _today(today)
    kind = P.PeriodKind(kind)
    start = P.period_start(kind, day)
    _require_open(kind, start, today, "sacrifices")
    text = (text or "").strip()
    if not text:
        raise TaskError("A sacrifice needs some text.")
    item = Sacrifice(entry=get_or_create_entry(s, kind, start), text=text, status=_status(status))
    s.add(item)
    s.commit()
    return item


def _get_sacrifice_open(s: Session, sacrifice_id: int, today: date) -> Sacrifice:
    item = s.get(Sacrifice, sacrifice_id)
    if item is None:
        raise TaskError(f"No sacrifice with id {sacrifice_id}.")
    _require_open(item.entry.kind, item.entry.start, today, "sacrifices")
    return item


# v1.7: a sacrifice's text can't be edited. It is added, marked as made (once,
# from planned), or deleted, and only while its period is open.

def mark_sacrifice_made(s: Session, sacrifice_id: int, today: Optional[date] = None) -> Sacrifice:
    """Planned -> made. Only the status changes; nothing else about it."""
    item = _get_sacrifice_open(s, sacrifice_id, _today(today))
    if item.status == SacrificeStatus.MADE.value:
        raise TaskError(f"'{item.text}' is already marked as made.")
    item.status = SacrificeStatus.MADE.value
    s.commit()
    return item


def remove_sacrifice(s: Session, sacrifice_id: int, today: Optional[date] = None) -> None:
    item = _get_sacrifice_open(s, sacrifice_id, _today(today))
    s.delete(item)
    s.commit()


def set_review(s: Session, kind, day: date, text: Optional[str], today: Optional[date] = None) -> PeriodEntry:
    """Writable from the period's first day until the end of the day after
    it ends. Empty text clears it."""
    today = _today(today)
    kind = P.PeriodKind(kind)
    start = P.period_start(kind, day)
    if not P.has_started(kind, start, today):
        raise TaskError(f"{P.label(kind, start)} hasn't started; write its review during or after it.")
    if P.is_review_locked(kind, start, today):
        raise TaskError(
            f"The review for {P.label(kind, start)} closed at the end of {P.review_cutoff(kind, start):%a %d %b}."
        )
    entry = get_or_create_entry(s, kind, start)
    entry.review = (text or "").strip() or None
    s.commit()
    return entry


# ---------- mandatory fill-in ----------

@dataclass(frozen=True)
class Missing:
    kind: P.PeriodKind
    start: date
    parts: Tuple[str, ...]  # subset of ("goal", "process")

    @property
    def message(self) -> str:
        return f"{P.label(self.kind, self.start)}: missing {' and '.join(self.parts)}"


def missing_fill_ins(s: Session, today: Optional[date] = None) -> List[Missing]:
    """Current day, week and month pages that lack a goal or a process."""
    today = _today(today)
    out = []
    for kind in (P.PeriodKind.DAY, P.PeriodKind.WEEK, P.PeriodKind.MONTH):
        entry = get_entry(s, kind, today)
        parts = []
        if entry is None or not entry.goals:
            parts.append("goal")
        if entry is None or not entry.process:
            parts.append("process")
        if parts:
            out.append(Missing(kind, P.period_start(kind, today), tuple(parts)))
    return out


# ---------- timetable tasks ----------

def check_task_goal(s: Session, goal_id: Optional[int], today: Optional[date] = None) -> Optional[Goal]:
    """A task may link only to an existing goal whose period hasn't ended."""
    if goal_id is None:
        return None
    today = _today(today)
    goal = get_goal(s, goal_id)
    if P.is_locked(goal.kind, goal.period_start, today):
        raise TaskError(f"'{goal.title}' belongs to {P.label(goal.kind, goal.period_start)}, which has ended.")
    return goal


@dataclass(frozen=True)
class Contribution:
    """What completing a linked task can do to its goal today."""

    mode: str  # "none" (no goal), "amount", "mark_done", "closed"
    note: str = ""


def contribution_for(task: Task, today: Optional[date] = None) -> Contribution:
    """The contribution is logged on the day the task is completed, to the
    goal the task is linked to, and only if that day falls inside the goal's
    period. So a task moved to another period keeps its link, but its
    contribution can only be logged while the goal's period covers the
    completion day."""
    today = _today(today)
    goal = task.goal
    if goal is None:
        return Contribution("none")
    where = P.label(goal.kind, goal.period_start)
    if P.is_locked(goal.kind, goal.period_start, today):
        return Contribution("closed", f"'{goal.title}' ({where}) has ended, so nothing can be logged to it.")
    if not goal.has_target:
        return Contribution("mark_done")
    if not P.contains(goal.kind, goal.period_start, today):
        return Contribution("closed", f"'{goal.title}' is for {where}; today isn't in it, so nothing can be logged.")
    return Contribution("amount")
