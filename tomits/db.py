"""Engine and session setup. SQLite file, Windows-safe paths."""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Union

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .models import Base

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def default_db_path() -> Path:
    """TOMITS_DB env var wins; otherwise <project>/data/tomits.db."""
    env = os.environ.get("TOMITS_DB")
    if env:
        return Path(env).expanduser()
    return PROJECT_ROOT / "data" / "tomits.db"


class MigrationError(RuntimeError):
    """The database needs a migration but the backup before it failed."""


def _stored_version(db_path: Path) -> Optional[int]:
    """user_version of an existing database with tables, or None if the file
    is missing or empty (a fresh install: nothing to back up)."""
    if not db_path.exists() or db_path.stat().st_size == 0:
        return None
    conn = sqlite3.connect(str(db_path))
    try:
        tables = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
        if not tables:
            return None
        return conn.execute("PRAGMA user_version").fetchone()[0] or 0
    finally:
        conn.close()


def backup_database(db_path: Path, version: int, now: Optional[datetime] = None) -> Path:
    """Consistent copy (SQLite backup API) to <name>.bak-v<version>-<date>-<time>.
    Checked with an integrity check; raises MigrationError if anything fails."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    target = db_path.with_name(f"{db_path.name}.bak-v{version or 1}-{stamp}")
    n = 1
    while target.exists():
        n += 1
        target = db_path.with_name(f"{db_path.name}.bak-v{version or 1}-{stamp}-{n}")
    try:
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
            ok = dst.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            dst.close()
            src.close()
        if not ok:
            raise MigrationError("the backup copy failed its integrity check")
    except Exception as e:
        try:
            target.unlink()
        except OSError:
            pass
        raise MigrationError(f"Couldn't back up {db_path.name} before updating it ({e}). "
                             "Nothing was changed. Check the disk has free space and the folder isn't read-only.") from e
    return target


def make_engine(path: Optional[Union[str, Path]] = None) -> Engine:
    if path == ":memory:":
        url = "sqlite:///:memory:"
    else:
        db_path = Path(path) if path else default_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path.as_posix()}"
        # Before any schema change: a timestamped backup, or stop.
        version = _stored_version(db_path)
        if version is not None and version < SCHEMA_VERSION:
            backup_database(db_path, version)
    # check_same_thread=False: the alarm thread and the UI thread each use
    # their own sessions on the same file. timeout waits out brief locks.
    engine = create_engine(url, future=True, connect_args={"check_same_thread": False, "timeout": 15})

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _record):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    migrate(engine, None if path == ":memory:" else Path(url[len("sqlite:///"):]))
    return engine


# ---------- schema migrations ----------
# 1: v1.0 tables.  2: v1.2 alarm columns on tasks.
# 3: v1.1 tracking: period entries, goal targets/units/links, progress logs,
#    sacrifices. Old goals move into the current month as no-target goals.
# 4: v1.3 planner: task priority, placement (fixed/auto/pinned/overflow), plan reason.
# 5: v1.4 rescheduling: task copy links, reschedule count, move reason; reason
#    snapshots (title, date, priority, goal); reschedule_log for undo.
# 6: v1.6 web app: reminder_marks (each missing goal / process is reminded once).
# 7: v1.7 times in titles: tasks.title_typed (the title as typed, when a time was read out of it).
# 8: v1.8 Remember: the notes table (a new table only; nothing else changes).
SCHEMA_VERSION = 8

_V2_TASK_COLUMNS = {
    "start_time": "TIME",
    "heads_up_sent": "BOOLEAN NOT NULL DEFAULT 0",
    "end_alert_sent": "BOOLEAN NOT NULL DEFAULT 0",
}
_V4_TASK_COLUMNS = {
    "priority": "INTEGER NOT NULL DEFAULT 3",
    "placement": "VARCHAR(8)",
    "plan_reason": "TEXT",
}
_V5_TASK_COLUMNS = {
    "rescheduled_from_id": "INTEGER REFERENCES tasks(id)",
    "reschedule_count": "INTEGER NOT NULL DEFAULT 0",
    "move_reason": "TEXT",
}
_V7_TASK_COLUMNS = {
    "title_typed": "VARCHAR(200)",
}
_V5_REASON_COLUMNS = {
    "task_title": "VARCHAR(200)",
    "task_date": "DATE",
    "priority": "INTEGER",
    "goal_id": "INTEGER",
    "goal_title": "VARCHAR(200)",
}
_V3_GOAL_COLUMNS = {
    "entry_id": "INTEGER REFERENCES period_entries(id)",
    "target": "FLOAT",
    "unit": "VARCHAR(40)",
    "parent_id": "INTEGER REFERENCES goals(id)",
    "done_at": "DATETIME",
}


def _columns(conn, table: str) -> set:
    return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}


def migrate(engine: Engine, db_path: Optional[Path] = None, today: Optional[date] = None) -> None:
    """Bring an older database up to SCHEMA_VERSION without losing data. Only
    adds columns and fills them; never drops or rewrites a table. make_engine()
    backs the file up first. New tables were already created by create_all()."""
    today = today or date.today()
    with engine.connect() as conn:
        version = conn.exec_driver_sql("PRAGMA user_version").scalar() or 0
        task_cols = _columns(conn, "tasks")
        missing_task = {k: v for k, v in {**_V2_TASK_COLUMNS, **_V4_TASK_COLUMNS, **_V5_TASK_COLUMNS,
                                                 **_V7_TASK_COLUMNS}.items()
                        if k not in task_cols}
        missing_reason = {k: v for k, v in _V5_REASON_COLUMNS.items() if k not in _columns(conn, "task_reasons")}
        needs_placement = "placement" not in task_cols
        missing_goal = {k: v for k, v in _V3_GOAL_COLUMNS.items() if k not in _columns(conn, "goals")}
        orphan_goals = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM goals" + (" WHERE entry_id IS NULL" if not missing_goal else "")
        ).scalar()
    # The timestamped backup is taken by make_engine() before anything changes.
    with engine.begin() as conn:
        for name, ddl in missing_task.items():
            conn.exec_driver_sql(f"ALTER TABLE tasks ADD COLUMN {name} {ddl}")
        for name, ddl in missing_goal.items():
            conn.exec_driver_sql(f"ALTER TABLE goals ADD COLUMN {name} {ddl}")
        for name, ddl in missing_reason.items():
            conn.exec_driver_sql(f"ALTER TABLE task_reasons ADD COLUMN {name} {ddl}")
        if missing_reason:
            # snapshot for reasons written before v1.4, from their task (and goal)
            conn.exec_driver_sql("""
                UPDATE task_reasons SET
                  task_title = (SELECT title FROM tasks WHERE tasks.id = task_reasons.task_id),
                  task_date  = (SELECT planned_for FROM tasks WHERE tasks.id = task_reasons.task_id),
                  priority   = (SELECT priority FROM tasks WHERE tasks.id = task_reasons.task_id),
                  goal_id    = (SELECT goal_id FROM tasks WHERE tasks.id = task_reasons.task_id),
                  goal_title = (SELECT goals.title FROM tasks JOIN goals ON goals.id = tasks.goal_id
                                WHERE tasks.id = task_reasons.task_id)
            """)
        if needs_placement:
            # Tasks that already have a start time were timed by you: fixed.
            conn.exec_driver_sql("UPDATE tasks SET placement = 'fixed' WHERE start_time IS NOT NULL")
        if orphan_goals:
            # v1.0 goals -> current month's goals, no target. Task links
            # (tasks.goal_id) are untouched, so they keep working.
            month = today.replace(day=1)
            conn.exec_driver_sql(
                "INSERT OR IGNORE INTO period_entries (kind, start, created_at) VALUES ('month', ?, ?)",
                (month.isoformat(), datetime.now().isoformat(sep=" ")),
            )
            entry_id = conn.exec_driver_sql(
                "SELECT id FROM period_entries WHERE kind = 'month' AND start = ?", (month.isoformat(),)
            ).scalar()
            conn.exec_driver_sql("UPDATE goals SET entry_id = ? WHERE entry_id IS NULL", (entry_id,))
        if version < SCHEMA_VERSION:
            conn.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")


def make_session_factory(path: Optional[Union[str, Path]] = None) -> sessionmaker:
    return sessionmaker(bind=make_engine(path), expire_on_commit=False)
