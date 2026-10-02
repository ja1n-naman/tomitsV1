"""Ringing alarms (v1.2 fixes). No UI imports.

When an alarm goes off it starts *ringing*: a built-in tone repeats until
you dismiss or snooze it, and stops by itself after RING_LIMIT (2 minutes).
Snooze stops the tone and rings again after the snooze length (a setting).

The state logic (ring / dismiss / snooze / tick) is plain Python with an
injectable clock, so it is fully testable. A background thread plays the
tone while anything rings and calls tick() so snoozes re-ring and the
2-minute stop happen even if you're not at the keyboard.

If the tone can't play, alarms still ring visibly and `sound_error` says why.
"""

from __future__ import annotations

import sys
import threading
import time as _time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

from .alarms import Alarm

RING_LIMIT = timedelta(minutes=2)

Key = Tuple[str, int]  # (alarm kind, task id)

# Events reported by tick() and to on_event
RERUNG = "rerung"      # a snoozed alarm is ringing again
TIMED_OUT = "timed_out"  # stopped by itself after RING_LIMIT


def key_of(alarm: Alarm) -> Key:
    return (alarm.kind, alarm.task_id)


@dataclass
class Ringing:
    alarm: Alarm
    started: datetime  # when this ring began (restarts after a snooze)
    snoozes: int = 0

    def seconds_left(self, now: datetime, limit: timedelta = RING_LIMIT) -> int:
        return max(0, int((self.started + limit - now).total_seconds()))


class WindowsTonePlayer:
    """Built-in tone via winsound.Beep: ships with Python on Windows, needs
    no files, setup or online service. One call plays one short burst."""

    PATTERN = ((880, 180), (0, 90), (880, 180), (0, 90), (1320, 320))

    def play_burst(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("the built-in tone (winsound) only exists on Windows")
        import winsound

        for freq, ms in self.PATTERN:
            if freq:
                winsound.Beep(freq, ms)  # raises RuntimeError if no audio device
            else:
                _time.sleep(ms / 1000)


class Ringer:
    def __init__(
        self,
        player=None,
        snooze_minutes: Callable[[], int] = lambda: 5,
        clock: Callable[[], datetime] = datetime.now,
        limit: timedelta = RING_LIMIT,
        on_event: Optional[Callable[[str, Alarm], None]] = None,
        pause_seconds: float = 0.8,
    ) -> None:
        self._player = player if player is not None else WindowsTonePlayer()
        self._snooze_minutes = snooze_minutes
        self._clock = clock
        self._limit = limit
        self._on_event = on_event
        self._pause = pause_seconds
        self._lock = threading.RLock()
        self._ringing: Dict[Key, Ringing] = {}
        self._snoozed: Dict[Key, Tuple[Ringing, datetime]] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._quiet = threading.Event()  # set while the mic listens (v1.5)
        self.sound_error: Optional[str] = None

    # ----- state (thread-safe, clock-driven) -----

    def ring(self, alarm: Alarm) -> None:
        with self._lock:
            self._snoozed.pop(key_of(alarm), None)
            self._ringing[key_of(alarm)] = Ringing(alarm, self._clock())

    def dismiss(self, key: Key) -> Optional[Alarm]:
        """Stop ringing for good (also cancels a pending snooze)."""
        with self._lock:
            r = self._ringing.pop(key, None)
            if r is None:
                snoozed = self._snoozed.pop(key, None)
                r = snoozed[0] if snoozed else None
            return r.alarm if r else None

    def snooze(self, key: Key, minutes: Optional[int] = None) -> datetime:
        """Stop ringing now; ring again after the snooze length (or `minutes`)."""
        with self._lock:
            r = self._ringing.pop(key, None)
            if r is None:
                raise KeyError(key)
            due = self._clock() + timedelta(minutes=minutes or self._snooze_minutes())
            r.snoozes += 1
            self._snoozed[key] = (r, due)
            return due

    def tick(self) -> List[Tuple[str, Alarm]]:
        """Stop alarms that rang for RING_LIMIT; re-ring snoozes that are due."""
        now = self._clock()
        events: List[Tuple[str, Alarm]] = []
        with self._lock:
            for key, r in list(self._ringing.items()):
                if now - r.started >= self._limit:
                    del self._ringing[key]
                    events.append((TIMED_OUT, r.alarm))
            for key, (r, due) in list(self._snoozed.items()):
                if now >= due:
                    del self._snoozed[key]
                    r.started = now
                    self._ringing[key] = r
                    events.append((RERUNG, r.alarm))
        if self._on_event is not None:
            for event, alarm in events:
                self._on_event(event, alarm)
        return events

    def ringing(self) -> List[Ringing]:
        with self._lock:
            return sorted(self._ringing.values(), key=lambda r: r.started)

    def snoozed(self) -> List[Tuple[Ringing, datetime]]:
        with self._lock:
            return sorted(self._snoozed.values(), key=lambda x: x[1])

    @property
    def is_ringing(self) -> bool:
        with self._lock:
            return bool(self._ringing)

    # ----- sound thread -----

    def play_once(self) -> bool:
        """Play one burst if anything is ringing. Returns True if sound played.
        On failure, remember the error and stop trying (alarms stay visible)."""
        if not self.is_ringing or self.sound_error or self._quiet.is_set():
            return False
        try:
            self._player.play_burst()
            return True
        except Exception as e:
            self.sound_error = f"Alarm sound failed: {e}"
            return False

    def quiet(self, on: bool) -> None:
        """Pause the tone (alarms keep ringing visibly) while the mic listens."""
        (self._quiet.set if on else self._quiet.clear)()

    @property
    def is_quiet(self) -> bool:
        return self._quiet.is_set()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="tomits-ringer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.tick()
            if self.play_once():
                self._stop.wait(self._pause)
            else:
                self._stop.wait(0.25)
