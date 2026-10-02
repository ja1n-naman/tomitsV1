"""Mandatory fill-in reminder (v1.1, single-reminder rule since v1.6). No UI imports.

Each missing item - one period's goal or process, such as "today's goal" or
"this week's process" - produces ONE reminder. Once it has been shown it does
not fire again (no repeat, sound or notification), and once dismissed its
banner stays hidden. The banner stays visible (undismissed) until the item is
filled in. A new period with a new missing item gets its own single reminder.

Shown / dismissed marks live in the database (table reminder_marks), so the
rule holds across restarts and between the terminal version and the web app.
A background thread checks periodically for items that newly became missing
(for example at midnight, when a new day starts).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, List, Optional

import schedule
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import periods as P
from . import tracking
from .errors import TaskError
from .models import ReminderMark
from .tracking import Missing

# How often the thread looks for newly missing items. This is a check, not a
# repeat: an item already reminded about is never sent again.
REMINDER_INTERVAL_SECONDS = 60

PART_NAMES = {"goal": "goal", "process": "process"}


@dataclass(frozen=True)
class Item:
    """One missing thing: a period's goal or its process."""
    kind: P.PeriodKind
    start: date
    part: str
    dismissed: bool = False

    @property
    def key(self) -> str:
        return f"{self.kind.value}:{self.start.isoformat()}:{self.part}"

    @property
    def message(self) -> str:
        return f"{P.label(self.kind, self.start)}: missing {self.part}"


def missing_items(s: Session, today: date) -> List[Item]:
    """Every current goal / process that is missing, one Item each."""
    return [Item(m.kind, m.start, part) for m in tracking.missing_fill_ins(s, today) for part in m.parts]


def _mark(s: Session, item: Item) -> Optional[ReminderMark]:
    return s.scalar(select(ReminderMark).where(ReminderMark.kind == item.kind.value, ReminderMark.start == item.start,
                                               ReminderMark.part == item.part))


def due_reminders(s: Session, today: date, now: Optional[datetime] = None) -> List[Missing]:
    """Items missing now that were never reminded about. They are marked as
    shown (so they never fire again) and returned grouped by period."""
    new: List[Item] = []
    for item in missing_items(s, today):
        if _mark(s, item) is None:
            s.add(ReminderMark(kind=item.kind.value, start=item.start, part=item.part, shown_at=now or datetime.now()))
            new.append(item)
    if new:
        s.commit()
    grouped: dict = {}
    for item in new:
        grouped.setdefault((item.kind, item.start), []).append(item.part)
    return [Missing(k, st, tuple(parts)) for (k, st), parts in grouped.items()]


def active_reminders(s: Session, today: date) -> List[Item]:
    """Missing items for the banner, minus the ones you dismissed."""
    out = []
    for item in missing_items(s, today):
        mark = _mark(s, item)
        if mark is None or mark.dismissed_at is None:
            out.append(item)
    return out


def dismiss_reminder(s: Session, kind, start: date, part: str, now: Optional[datetime] = None) -> Item:
    """Hide the banner for one item. It does not come back for that item."""
    kind = P.PeriodKind(kind)
    if part not in PART_NAMES:
        raise TaskError("A reminder is about a goal or a process.")
    item = Item(kind, P.period_start(kind, start), part)
    mark = _mark(s, item)
    if mark is None:
        mark = ReminderMark(kind=item.kind.value, start=item.start, part=part, shown_at=now or datetime.now())
        s.add(mark)
    if mark.dismissed_at is None:
        mark.dismissed_at = now or datetime.now()
    s.commit()
    return item


class ReminderService:
    def __init__(
        self,
        session_factory: sessionmaker,
        notifier,
        on_reminder: Optional[Callable[[List[Missing]], None]] = None,
        interval_seconds: int = REMINDER_INTERVAL_SECONDS,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._session_factory = session_factory
        self._notifier = notifier
        self._on_reminder = on_reminder
        self._interval = interval_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._scheduler = schedule.Scheduler()
        self.last_error: Optional[str] = None

    def check(self) -> List[Missing]:
        """Send one reminder for each item that newly became missing."""
        with self._lock:
            now = self._clock()
            with self._session_factory() as s:
                new = due_reminders(s, now.date(), now)
        for m in new:
            if self._notifier is not None:
                self._notifier.notify("tomits: fill in your plan", m.message)
        if new and self._on_reminder is not None:
            self._on_reminder(new)
        return new

    def start(self) -> None:
        """First check right away, then every interval (only new items fire)."""
        if self._thread is not None:
            return
        self._stop.clear()
        self._scheduler.every(self._interval).seconds.do(self._safe_check)
        self._thread = threading.Thread(target=self._loop, name="tomits-reminders", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._thread = None
        self._scheduler.clear()

    def _loop(self) -> None:
        self._safe_check()
        while not self._stop.wait(1):
            self._scheduler.run_pending()

    def _safe_check(self) -> None:
        try:
            self.check()
            self.last_error = None
        except Exception as e:  # keep the thread alive; the UI shows the error
            self.last_error = f"Reminder check failed: {e}"
