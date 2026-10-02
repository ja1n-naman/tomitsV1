"""Log of every voice attempt (v1.5.1).

A separate SQLite file (data/voice_log.db, table `voice_log`) so it can be
queried with any SQLite tool without touching the main database:

    id, ts, transcript, confidence, source (rules/model/none), command,
    interpreted (plain words), acted (0/1), result, audio_file, device, note

The audio of the last AUDIO_KEEP attempts is kept as WAV in data/voice_audio/
(named <id>.wav); older audio files are deleted automatically, the text rows
are kept.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..db import PROJECT_ROOT

AUDIO_KEEP = 50   # how many attempts keep their audio

SCHEMA = """
CREATE TABLE IF NOT EXISTS voice_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    transcript TEXT NOT NULL,
    confidence REAL,
    source TEXT,
    command TEXT,
    interpreted TEXT,
    acted INTEGER NOT NULL DEFAULT 0,
    result TEXT,
    audio_file TEXT,
    device TEXT,
    note TEXT
);
CREATE INDEX IF NOT EXISTS voice_log_ts ON voice_log(ts);
"""


@dataclass
class LogRow:
    id: int
    ts: str
    transcript: str
    confidence: Optional[float]
    source: Optional[str]
    command: Optional[str]
    interpreted: Optional[str]
    acted: bool
    result: Optional[str]
    audio_file: Optional[str]
    device: Optional[str]
    note: Optional[str]


class VoiceLog:
    def __init__(self, db_file: Optional[Path] = None, audio_dir: Optional[Path] = None, keep: int = AUDIO_KEEP):
        self.db_file = Path(db_file) if db_file else PROJECT_ROOT / "data" / "voice_log.db"
        self.audio_dir = Path(audio_dir) if audio_dir else self.db_file.parent / "voice_audio"
        self.keep = keep
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self):
        return sqlite3.connect(self.db_file)

    def add(self, transcript: str, confidence: Optional[float], audio=None, device: Optional[str] = None,
            ts: Optional[datetime] = None) -> int:
        with self._conn() as c:
            cur = c.execute("INSERT INTO voice_log (ts, transcript, confidence, device) VALUES (?, ?, ?, ?)",
                            ((ts or datetime.now()).isoformat(timespec="seconds"), transcript or "", confidence, device))
            row_id = cur.lastrowid
        if audio is not None and len(audio):
            from .audio import save_wav
            path = save_wav(self.audio_dir / f"{row_id}.wav", audio)
            with self._conn() as c:
                c.execute("UPDATE voice_log SET audio_file = ? WHERE id = ?", (str(path), row_id))
            self._prune_audio()
        return row_id

    def update(self, row_id: int, **fields) -> None:
        allowed = {"source", "command", "interpreted", "acted", "result", "note"}
        sets = {k: (int(v) if k == "acted" else v) for k, v in fields.items() if k in allowed}
        if not sets:
            return
        with self._conn() as c:
            c.execute(f"UPDATE voice_log SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", (*sets.values(), row_id))

    def recent(self, n: int = 10) -> List[LogRow]:
        with self._conn() as c:
            rows = c.execute("SELECT id, ts, transcript, confidence, source, command, interpreted, acted, result, "
                             "audio_file, device, note FROM voice_log ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return [LogRow(*r[:7], bool(r[7]), *r[8:]) for r in rows]

    def _prune_audio(self) -> None:
        with self._conn() as c:
            rows = c.execute("SELECT id, audio_file FROM voice_log WHERE audio_file IS NOT NULL ORDER BY id DESC").fetchall()
            for row_id, path in rows[self.keep:]:
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    pass
                c.execute("UPDATE voice_log SET audio_file = NULL, note = COALESCE(note || '; ', '') || 'audio removed' "
                          "WHERE id = ?", (row_id,))
