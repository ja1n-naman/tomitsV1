"""Server push (Server-Sent Events) and the database change watcher.

Every open browser tab subscribes to /api/events. When anything changes the
database - this server, another tab, voice, or the terminal version in another
process - the watcher notices (SQLite's data_version counter) and tells every
tab to refresh. Settings changes (settings.json) are noticed the same way.
"""

from __future__ import annotations

import json
import queue
import sqlite3
import threading
from pathlib import Path
from typing import Callable, List, Optional


class Hub:
    def __init__(self) -> None:
        self._clients: List[queue.Queue] = []
        self._lock = threading.Lock()
        self.version = 0  # bumps on every publish; the UI shows it in the "saved" check

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=200)
        with self._lock:
            self._clients.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._clients:
                self._clients.remove(q)

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def publish(self, event: str, data: Optional[dict] = None) -> None:
        with self._lock:
            self.version += 1
            payload = dict(data or {}, version=self.version)
            msg = f"event: {event}\ndata: {json.dumps(payload)}\n\n"
            for q in list(self._clients):
                try:
                    q.put_nowait(msg)
                except queue.Full:  # a stuck tab: drop it, it reconnects and refetches
                    self._clients.remove(q)


class Watcher:
    """Polls the database's data_version and the settings file's mtime."""

    def __init__(self, db_path: Path, settings_file: Path, hub: Hub, on_settings: Callable[[], None],
                 interval: float = 0.5) -> None:
        self._db_path = Path(db_path)
        self._settings_file = Path(settings_file)
        self._hub = hub
        self._on_settings = on_settings
        self._interval = interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_error: Optional[str] = None

    def _mtime(self) -> float:
        try:
            return self._settings_file.stat().st_mtime
        except OSError:
            return 0.0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="tomits-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=15)
        try:
            last = conn.execute("PRAGMA data_version").fetchone()[0]
            mtime = self._mtime()
            while not self._stop.wait(self._interval):
                try:
                    v = conn.execute("PRAGMA data_version").fetchone()[0]
                    if v != last:
                        last = v
                        self._hub.publish("changed", {"source": "database"})
                    m = self._mtime()
                    if m != mtime:
                        mtime = m
                        self._on_settings()
                        self._hub.publish("changed", {"source": "settings"})
                    self.last_error = None
                except sqlite3.Error as e:  # locked for a moment: try again next round
                    self.last_error = str(e)
        finally:
            conn.close()
