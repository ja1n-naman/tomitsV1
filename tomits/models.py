"""Database models. Pure data: no UI, no business rules."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from . import periods as P


class Base(DeclarativeBase):
    pass


class TaskStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class Priority(int, Enum):
    URGENT = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


PRIORITY_NAMES = {1: "urgent", 2: "high", 3: "normal", 4: "low"}
DEFAULT_PRIORITY = Priority.NORMAL.value


class Placement(str, Enum):
    """How a task got its start time (v1.3 day planner)."""

    FIXED = "fixed"        # you gave it a time: the planner never moves it
    AUTO = "auto"          # the planner placed it: a re-plan may move it
    PINNED = "pinned"      # you moved a planned task: treated like fixed
    OVERFLOW = "overflow"  # the planner found no room: listed as "didn't fit"


USER_PLACED = {Placement.FIXED.value, Placement.PINNED.value}


# Statuses that close a task and therefore need a written reason.
REASON_REQUIRED = {TaskStatus.FAILED, TaskStatus.SKIPPED}


class SacrificeStatus(str, Enum):
    PLANNED = "planned"
    MADE = "made"


class PeriodEntry(Base):
    """One tracking page per day / week / month: goals, sacrifices,
    process and review. Created on first use."""

    __tablename__ = "period_entries"
    __table_args__ = (UniqueConstraint("kind", "start"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(5))
    start: Mapped[date] = mapped_column(Date, index=True)
    process: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    goals: Mapped[List["Goal"]] = relationship(back_populates="entry", order_by="Goal.id")
    sacrifices: Mapped[List["Sacrifice"]] = relationship(
        back_populates="entry", order_by="Sacrifice.id", cascade="all, delete-orphan"
    )

    @property
    def period_kind(self) -> P.PeriodKind:
        return P.PeriodKind(self.kind)

    @property
    def label(self) -> str:
        return P.label(self.kind, self.start)


class Goal(Base):
    """A goal belongs to one period. It has either a numeric target with a
    unit (progress = logged / target) or no target (done / not done).
    It may link up one level: day -> week -> month."""

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # v1.1 tracking (schema v3). entry_id is filled for every goal after migration.
    entry_id: Mapped[Optional[int]] = mapped_column(ForeignKey("period_entries.id"), nullable=True, index=True)
    target: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("goals.id"), nullable=True, index=True)
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    entry: Mapped[Optional[PeriodEntry]] = relationship(back_populates="goals")
    parent: Mapped[Optional["Goal"]] = relationship(back_populates="children", remote_side="Goal.id")
    children: Mapped[List["Goal"]] = relationship(back_populates="parent", order_by="Goal.id")
    logs: Mapped[List["ProgressLog"]] = relationship(
        back_populates="goal", order_by="(ProgressLog.logged_for, ProgressLog.id)"
    )
    tasks: Mapped[List["Task"]] = relationship(back_populates="goal")

    @property
    def kind(self) -> P.PeriodKind:
        return self.entry.period_kind

    @property
    def period_start(self) -> date:
        return self.entry.start

    @property
    def has_target(self) -> bool:
        return self.target is not None


class ProgressLog(Base):
    """An amount logged against a numeric goal on a given date."""

    __tablename__ = "progress_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    logged_for: Mapped[date] = mapped_column(Date)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    goal: Mapped[Goal] = relationship(back_populates="logs")


class Sacrifice(Base):
    __tablename__ = "sacrifices"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("period_entries.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(8), default=SacrificeStatus.PLANNED.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    entry: Mapped[PeriodEntry] = relationship(back_populates="sacrifices")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    # The task's own goal: what "done" looks like for this task.
    purpose: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_min: Mapped[int] = mapped_column(Integer)
    planned_for: Mapped[date] = mapped_column(Date, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default=TaskStatus.PENDING.value)
    goal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("goals.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # v1.2 alarms. A task without a start time gets no alarms.
    start_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    heads_up_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    end_alert_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # v1.3 day planner (schema v4)
    priority: Mapped[int] = mapped_column(Integer, default=DEFAULT_PRIORITY, server_default=str(DEFAULT_PRIORITY))
    placement: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    plan_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # v1.4 rescheduling (schema v5)
    rescheduled_from_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    reschedule_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    move_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # v1.7 (schema v7): the title as typed, when a time was read out of it
    # ("gym at 7pm" -> title "gym"); None when nothing was read
    title_typed: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    goal: Mapped[Optional[Goal]] = relationship(back_populates="tasks")
    reasons: Mapped[List["TaskReason"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskReason.id"
    )
    rescheduled_from: Mapped[Optional["Task"]] = relationship(
        remote_side="Task.id", back_populates="rescheduled_copies", foreign_keys="Task.rescheduled_from_id"
    )
    rescheduled_copies: Mapped[List["Task"]] = relationship(
        back_populates="rescheduled_from", foreign_keys="Task.rescheduled_from_id", order_by="Task.id"
    )

    @property
    def start_at(self) -> Optional[datetime]:
        if self.start_time is None:
            return None
        return datetime.combine(self.planned_for, self.start_time)

    @property
    def end_at(self) -> Optional[datetime]:
        start = self.start_at
        return start + timedelta(minutes=self.duration_min) if start else None

    @property
    def status_enum(self) -> TaskStatus:
        return TaskStatus(self.status)

    @property
    def latest_reason(self) -> Optional[str]:
        return self.reasons[-1].reason if self.reasons else None


class TaskReason(Base):
    """Why a task failed or was skipped. Permanent: written once when the
    task is closed, never updated or deleted by rescheduling or undo.
    v1.4 keeps a snapshot of the task (title, date, priority, goal) so the
    record stays meaningful even if the task or goal changes later."""

    __tablename__ = "task_reasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    status: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # snapshot (schema v5)
    task_title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    task_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    goal_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    goal_title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    task: Mapped[Task] = relationship(back_populates="reasons")


class RescheduleLog(Base):
    """One accepted reschedule: what it was, the exact previous values of
    every task it changed (JSON), and the copies it created. Used for undo."""

    __tablename__ = "reschedule_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    trigger: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[str] = mapped_column(Text)       # {"<task id>": {field: value, ...}}
    created_ids: Mapped[str] = mapped_column(Text)    # [task id, ...]
    undone: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class ReminderMark(Base):
    """v1.6: one row per missing goal / process item that has been reminded
    about. Each item (such as today's goal or this week's process) is reminded once;
    dismissing it hides the banner for that item. A new period has new items."""

    __tablename__ = "reminder_marks"
    __table_args__ = (UniqueConstraint("kind", "start", "part"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(5))
    start: Mapped[date] = mapped_column(Date)
    part: Mapped[str] = mapped_column(String(8))          # "goal" or "process"
    shown_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Note(Base):
    """v1.8 Remember: a short note that isn't tied to any day, week or month.
    Added and deleted only, never edited, never locked. A note with a time
    gets one reminder when that time arrives (or is counted in the "while you
    were away" summary if tomits wasn't running)."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(200))
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    color: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    reminded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)   # the one reminder was given
    reminded_how: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)      # live / away / past
    banner_open: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
