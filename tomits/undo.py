"""One-step undo for any change (v1.6). Logic layer, no UI.

Before an action, `capture()` snapshots the rows of the tables a user action
can change (plus the settings file). After it, `diff()` gives the exact rows
inserted, deleted and updated. `undo()` puts every one of those rows back to
its previous values in one transaction.

Rules:
- Failure reasons (table task_reasons) are never touched: they are not
  snapshotted, so undo can't delete or change them. Undoing a "failed" marks
  the task open again; its stored reason stays (the task then counts as
  having history, so it can't be deleted).
- Undo is refused, with nothing changed, if any affected row was changed
  again since (by you, another tab, voice or the terminal version), if it
  would bring back an overlap, or if it touches a period that has since
  locked.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import periods as P
from .errors import TaskError

# Parents before children (insert order); deletes go in reverse.
TABLES = ("period_entries", "goals", "tasks", "progress_logs", "sacrifices", "reschedule_log", "reminder_marks",
          "notes")

Rows = Dict[str, Dict[int, dict]]


@dataclass
class Capture:
    rows: Rows
    settings: Optional[str]


@dataclass
class Change:
    label: str
    inserted: Rows = field(default_factory=dict)
    deleted: Rows = field(default_factory=dict)
    updated: Dict[str, Dict[int, Tuple[dict, dict]]] = field(default_factory=dict)
    settings_before: Optional[str] = None
    settings_after: Optional[str] = None

    @property
    def empty(self) -> bool:
        return (not any(self.inserted.values()) and not any(self.deleted.values())
                and not any(self.updated.values()) and self.settings_before == self.settings_after)


def _read_settings(path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def capture(engine: Engine, settings_file: Optional[Path] = None) -> Capture:
    rows: Rows = {}
    with engine.connect() as conn:
        for t in TABLES:
            res = conn.exec_driver_sql(f"SELECT * FROM {t}")
            cols = list(res.keys())
            rows[t] = {r[0]: dict(zip(cols, r)) for r in res}
    return Capture(rows, _read_settings(settings_file))


def diff(before: Capture, after: Capture, label: str = "change") -> Change:
    ch = Change(label, settings_before=before.settings, settings_after=after.settings)
    for t in TABLES:
        b, a = before.rows.get(t, {}), after.rows.get(t, {})
        ch.inserted[t] = {i: a[i] for i in a.keys() - b.keys()}
        ch.deleted[t] = {i: b[i] for i in b.keys() - a.keys()}
        ch.updated[t] = {i: (b[i], a[i]) for i in a.keys() & b.keys() if a[i] != b[i]}
    return ch


def describe(change: Change) -> str:
    n = sum(len(v) for v in change.inserted.values()) + sum(len(v) for v in change.deleted.values()) + \
        sum(len(v) for v in change.updated.values())
    return f"{change.label} ({n} row{'s' if n != 1 else ''})"


def _period_locked(kind: str, start, today: date, review_only: bool) -> bool:
    start = date.fromisoformat(str(start)[:10])
    return P.is_review_locked(kind, start, today) if review_only else P.is_locked(kind, start, today)


def _entry_of(conn, entry_id) -> Optional[Tuple[str, str]]:
    row = conn.exec_driver_sql("SELECT kind, start FROM period_entries WHERE id = ?", (entry_id,)).fetchone()
    return (row[0], row[1]) if row else None


def _check_locks(conn, change: Change, today: date) -> None:
    def refuse():
        raise TaskError("Can't undo: that change belongs to a period that has ended (it's read-only now).")

    for i, row in list(change.inserted["period_entries"].items()) + list(change.deleted["period_entries"].items()):
        if _period_locked(row["kind"], row["start"], today, False):
            refuse()
    for i, (old, new) in change.updated["period_entries"].items():
        review_only = {k for k in old if old[k] != new[k]} <= {"review"}
        if _period_locked(old["kind"], old["start"], today, review_only):
            refuse()
    for t in ("goals", "sacrifices"):
        rows = list(change.inserted[t].values()) + list(change.deleted[t].values()) + \
            [r for pair in change.updated[t].values() for r in pair]
        for row in rows:
            e = _entry_of(conn, row["entry_id"]) if row.get("entry_id") else None
            if e is None:
                e = next(((r["kind"], r["start"]) for r in list(change.deleted["period_entries"].values()) +
                          list(change.inserted["period_entries"].values()) if r["id"] == row.get("entry_id")), None)
            if e and _period_locked(e[0], e[1], today, False):
                refuse()
    logs = list(change.inserted["progress_logs"].values()) + list(change.deleted["progress_logs"].values())
    for row in logs:
        g = conn.exec_driver_sql("SELECT entry_id FROM goals WHERE id = ?", (row["goal_id"],)).fetchone()
        e = _entry_of(conn, g[0]) if g and g[0] else None
        if e and _period_locked(e[0], e[1], today, False):
            refuse()


def undo(engine: Engine, change: Change, today: date, settings_file: Optional[Path] = None) -> None:
    """Restore every row the change touched. All or nothing."""
    if change.empty:
        raise TaskError("There's nothing to undo.")
    now_settings = _read_settings(settings_file)
    if change.settings_before != change.settings_after and now_settings != change.settings_after:
        raise TaskError("Can't undo: the settings were changed again since.")
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            def current(t, i):
                res = conn.exec_driver_sql(f"SELECT * FROM {t} WHERE id = ?", (i,))
                cols = list(res.keys())
                r = res.fetchone()
                return dict(zip(cols, r)) if r else None

            for t in TABLES:
                for i, row in change.inserted[t].items():
                    if current(t, i) != row:
                        raise TaskError("Can't undo: something it changed was changed again since.")
                for i, (_old, new) in change.updated[t].items():
                    if current(t, i) != new:
                        raise TaskError("Can't undo: something it changed was changed again since.")
                for i in change.deleted[t]:
                    if current(t, i) is not None:
                        raise TaskError("Can't undo: something it changed was changed again since.")
            for i in change.inserted["tasks"]:
                if conn.exec_driver_sql("SELECT COUNT(*) FROM task_reasons WHERE task_id = ?", (i,)).scalar():
                    raise TaskError("Can't undo: a failure reason is attached to that task, and reasons are permanent.")
            _check_locks(conn, change, today)

            for t in reversed(TABLES):
                for i in change.inserted[t]:
                    conn.exec_driver_sql(f"DELETE FROM {t} WHERE id = ?", (i,))
            for t in TABLES:
                for i, row in change.deleted[t].items():
                    cols = list(row)
                    conn.exec_driver_sql(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                                         tuple(row[c] for c in cols))
                for i, (old, new) in change.updated[t].items():
                    cols = [c for c in old if old[c] != new[c]]
                    conn.exec_driver_sql(f"UPDATE {t} SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?",
                                         tuple(old[c] for c in cols) + (i,))
            _check_overlaps(conn, change)
            trans.commit()
        except IntegrityError:
            trans.rollback()
            raise TaskError("Can't undo: other records now depend on what it would remove.") from None
        except Exception:
            trans.rollback()
            raise
    if change.settings_before != change.settings_after and settings_file is not None:
        path = Path(settings_file)
        if change.settings_before is None:
            try:
                path.unlink()
            except OSError:
                pass
        else:
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(change.settings_before, encoding="utf-8")
            tmp.replace(path)


def _check_overlaps(conn, change: Change) -> None:
    """Restored timed tasks must not overlap anything (back-to-back is fine)."""
    from . import services as svc
    ids = set(change.deleted["tasks"]) | set(change.updated["tasks"])
    if not ids:
        return
    s = Session(bind=conn)
    try:
        from .models import Task
        for tid in ids:
            t = s.get(Task, tid)
            if t is None or t.start_time is None or t.status not in svc.BLOCKING_STATUSES:
                continue
            other = svc.find_overlap(s, t.planned_for, t.start_time, t.duration_min, exclude_task_id=t.id)
            if other is not None:
                raise TaskError("Can't undo: " + svc.overlap_message(t.title, t.planned_for, t.start_time,
                                                                       t.duration_min, other))
    finally:
        s.close()


class UndoStack:
    """Recent changes made through the app, newest last (kept in memory)."""

    def __init__(self, limit: int = 30):
        self._items: List[Tuple[int, Change]] = []
        self._next = 1
        self._limit = limit
        self._lock = threading.Lock()

    def push(self, change: Change) -> Optional[int]:
        if change.empty:
            return None
        with self._lock:
            uid = self._next
            self._next += 1
            self._items.append((uid, change))
            del self._items[:-self._limit]
            return uid

    def get(self, uid: Optional[int] = None) -> Tuple[int, Change]:
        with self._lock:
            if not self._items:
                raise TaskError("There's nothing to undo.")
            if uid is None:
                return self._items[-1]
            for i, c in self._items:
                if i == uid:
                    return i, c
        raise TaskError("That change can no longer be undone.")

    def remove(self, uid: int) -> None:
        with self._lock:
            self._items = [(i, c) for i, c in self._items if i != uid]

    def latest(self) -> Optional[Tuple[int, str]]:
        with self._lock:
            return (self._items[-1][0], self._items[-1][1].label) if self._items else None


def to_json(change: Change) -> str:  # for debugging / tests
    return json.dumps({"label": change.label, "inserted": {t: list(v) for t, v in change.inserted.items()}})
