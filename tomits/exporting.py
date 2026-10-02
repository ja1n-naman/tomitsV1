"""v1.8 export and import of all tomits data (tasks, reasons, goals, pages,
sacrifices, reschedule history, reminders, notes). Logic only.

- export_data(): every table, row by row exactly as stored, into one JSON
  document ({"app": "tomits", "format": 1, "schema": N, "tables": {...}}).
  write_export() also saves it as data/exports/tomits-export-<date>-<time>.json.
- import_data(): replaces everything with an export's contents. A timestamped
  backup of the database is taken first (if it fails, nothing changes); the
  export must come from the same schema version; it all happens in one
  transaction, so a bad file changes nothing.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.engine import Engine

from .db import SCHEMA_VERSION, MigrationError, backup_database
from .errors import TaskError
from .models import Base

FORMAT = 1


def table_names() -> List[str]:
    return [t.name for t in Base.metadata.sorted_tables]          # parents before children


def export_data(engine: Engine, now: Optional[datetime] = None) -> dict:
    tables: Dict[str, list] = {}
    with engine.connect() as conn:
        for name in table_names():
            res = conn.exec_driver_sql(f"SELECT * FROM {name} ORDER BY 1")
            cols = list(res.keys())
            tables[name] = [dict(zip(cols, row)) for row in res]
    return {"app": "tomits", "format": FORMAT, "schema": SCHEMA_VERSION,
            "exported_at": (now or datetime.now()).isoformat(timespec="seconds"), "tables": tables}


def exports_dir(db_path: Path) -> Path:
    return Path(db_path).parent / "exports"


def write_export(engine: Engine, db_path: Path, now: Optional[datetime] = None) -> Path:
    now = now or datetime.now()
    folder = exports_dir(db_path)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"tomits-export-{now:%Y%m%d-%H%M%S}.json"
    n = 1
    while path.exists():
        n += 1
        path = folder / f"tomits-export-{now:%Y%m%d-%H%M%S}-{n}.json"
    path.write_text(json.dumps(export_data(engine, now), ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def latest_export(db_path: Path) -> Optional[Path]:
    files = sorted(exports_dir(db_path).glob("tomits-export-*.json"))
    return files[-1] if files else None


def summary(data: dict) -> str:
    t = data.get("tables") or {}
    parts = [f"{len(t.get('tasks', []))} tasks", f"{len(t.get('goals', []))} goals",
             f"{len(t.get('notes', []))} notes"]
    return ", ".join(parts) + f" (exported {data.get('exported_at', 'at an unknown time')})"


def check(data) -> dict:
    """Refuse anything that isn't a tomits export of this schema version."""
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except ValueError:
            raise TaskError("That file isn't a tomits export (it isn't valid JSON).") from None
    if not isinstance(data, dict) or data.get("app") != "tomits" or not isinstance(data.get("tables"), dict):
        raise TaskError("That file isn't a tomits export.")
    if data.get("format") != FORMAT:
        raise TaskError(f"That export uses format {data.get('format')}; this tomits reads format {FORMAT}.")
    if data.get("schema") != SCHEMA_VERSION:
        raise TaskError(f"That export is from database version {data.get('schema')}; this tomits uses version "
                        f"{SCHEMA_VERSION}. Import it with the tomits version that made it.")
    known = set(table_names())
    for name, rows in data["tables"].items():
        if name not in known or not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise TaskError(f"That export has an unexpected part ('{name}').")
    return data


def import_data(engine: Engine, db_path: Path, data, now: Optional[datetime] = None) -> str:
    """Replace all data with the export. Returns a one-line summary."""
    data = check(data)
    try:
        backup = backup_database(Path(db_path), SCHEMA_VERSION, now)
    except MigrationError as e:
        raise TaskError(str(e).replace("before updating it", "before importing")) from None
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA defer_foreign_keys = ON")
        cols = {name: {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({name})")} for name in table_names()}
        for name in reversed(table_names()):
            conn.exec_driver_sql(f"DELETE FROM {name}")
        for name in table_names():
            for row in data["tables"].get(name, []):
                if not set(row) <= cols[name]:
                    raise TaskError(f"That export has columns this tomits doesn't know in '{name}'. Nothing changed.")
                keys = list(row)
                conn.exec_driver_sql(f"INSERT INTO {name} ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
                                     tuple(row[k] for k in keys))
    return f"Imported {summary(data)}. The data from before is backed up as {backup.name}."
