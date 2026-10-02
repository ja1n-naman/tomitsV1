"""Alarms (v1.2). No Rich/UI imports, so this can later run as a
background service.

For each pending task with a start time:
- heads-up: 5 minutes before it starts
- end check: when start + duration has passed, ask whether it was finished

Each alarm fires once; flags on the task record that it was sent.
Alarms that came due while the app was closed are collected once at
startup and reported as "missed" instead of being replayed.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, List, Optional

import schedule
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from .models import Task, TaskStatus
from .services import format_duration

HEADS_UP_BEFORE = timedelta(minutes=5)
HEADS_UP = "heads_up"
END_CHECK = "end_check"


@dataclass(frozen=True)
class Alarm:
    kind: str
    task_id: int
    title: str
    start: datetime
    end: datetime
    missed: bool = False  # came due while the app was closed

    @property
    def title_line(self) -> str:
        return "tomits: starting soon" if self.kind == HEADS_UP else "tomits: time's up"

    @property
    def message(self) -> str:
        if self.kind == HEADS_UP:
            if self.missed:
                return f"'{self.title}' started at {self.start:%a %d %b %H:%M} (planned until {self.end:%H:%M})."
            return f"'{self.title}' starts at {self.start:%H:%M} ({format_duration(int((self.end - self.start).total_seconds() // 60))} planned)."
        if self.missed:
            return f"'{self.title}' was planned to end at {self.end:%a %d %b %H:%M} and is still open."
        return f"'{self.title}' was planned to end at {self.end:%H:%M}. Did you finish it?"


def collect_due(s: Session, now: datetime, startup: bool = False) -> List[Alarm]:
    """Return alarms due at `now` and mark them sent.

    Live (startup=False): a heads-up whose task has already started is
    dropped silently. At startup, that task is reported as missed if it is
    still inside its planned time; end checks that passed are reported as
    missed."""
    tasks = s.scalars(
        select(Task).where(
            Task.status == TaskStatus.PENDING.value,
            Task.start_time.is_not(None),
            Task.planned_for <= now.date(),
            or_(Task.heads_up_sent.is_(False), Task.end_alert_sent.is_(False)),
        )
    ).all()
    alarms: List[Alarm] = []
    for t in tasks:
        start, end = t.start_at, t.end_at
        if not t.heads_up_sent and now >= start - HEADS_UP_BEFORE:
            t.heads_up_sent = True
            if now < start:
                alarms.append(Alarm(HEADS_UP, t.id, t.title, start, end))
            elif startup and now < end:
                alarms.append(Alarm(HEADS_UP, t.id, t.title, start, end, missed=True))
        if not t.end_alert_sent and now >= end:
            t.end_alert_sent = True
            alarms.append(Alarm(END_CHECK, t.id, t.title, start, end, missed=startup))
    s.commit()
    alarms.sort(key=lambda a: a.start if a.kind == HEADS_UP else a.end)
    return alarms


class AlarmService:
    """Checks for due alarms every `interval_seconds` on a background thread
    (using `schedule`). Live alarms go to the notifier and to `on_alarm`."""

    def __init__(
        self,
        session_factory: sessionmaker,
        notifier,
        on_alarm: Optional[Callable[[Alarm], None]] = None,
        interval_seconds: int = 15,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._session_factory = session_factory
        self._notifier = notifier
        self._on_alarm = on_alarm
        self._interval = interval_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._scheduler = schedule.Scheduler()
        self.last_error: Optional[str] = None

    def check(self, startup: bool = False) -> List[Alarm]:
        """Run one check now. Returns every alarm found, missed ones included;
        only live ones are sent to the notifier and on_alarm."""
        with self._lock:
            with self._session_factory() as s:
                alarms = collect_due(s, self._clock(), startup=startup)
        for alarm in alarms:
            if alarm.missed:
                continue
            if self._notifier is not None:
                self._notifier.notify(alarm.title_line, alarm.message, urgent=alarm.kind == END_CHECK)
            if self._on_alarm is not None:
                self._on_alarm(alarm)
        return alarms

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._scheduler.every(self._interval).seconds.do(self._safe_check)
        self._thread = threading.Thread(target=self._loop, name="tomits-alarms", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._thread = None
        self._scheduler.clear()

    def _loop(self) -> None:
        while not self._stop.wait(1):
            self._scheduler.run_pending()

    def _safe_check(self) -> None:
        try:
            self.check()
            self.last_error = None
        except Exception as e:  # keep the thread alive; the UI shows the error
            self.last_error = f"Alarm check failed: {e}"
