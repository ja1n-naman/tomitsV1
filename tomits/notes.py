"""v1.8 Remember: short notes of things not to forget. Logic only (no UI):
the web app, voice and the terminal all call these functions.

Rules:
- text required, at most MAX_TEXT characters; at most MAX_NOTES notes;
- an optional date and time; a clear time written in the text is read the
  same way as in a task title (titletime) and taken out of the text;
- a muted colour from COLORS, chosen when the note is added;
- notes are only added and deleted, never edited, never locked, and stay
  until deleted;
- a note whose time arrives gets ONE reminder (claimed atomically, so two
  running copies of tomits never both remind). Notes whose time passed while
  tomits wasn't running are only counted in one "while you were away" summary.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Callable, Dict, List, Optional, Tuple

import schedule
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from . import titletime as TT
from .errors import TaskError
from .models import Note

MAX_TEXT = 200
MAX_NOTES = 50
COLORS = ("sand", "sage", "sky", "lilac", "rose", "slate")    # muted; drawn by the UI
DEFAULT_COLOR = COLORS[0]
CHECK_SECONDS = 15
DEFAULT_WINDOW = (time(9, 0), time(21, 0))


def validate_color(color: Optional[str]) -> str:
    c = (color or DEFAULT_COLOR).strip().lower()
    if c not in COLORS:
        raise TaskError("Pick a colour: " + ", ".join(COLORS) + ".")
    return c


def count(s: Session) -> int:
    return s.scalar(select(func.count()).select_from(Note)) or 0


def add_note(s: Session, text: str, due_at: Optional[datetime] = None, color: Optional[str] = None, *,
             now: Optional[datetime] = None, window=None, ampm: Optional[str] = None,
             read_text: bool = True) -> Note:
    """Add a note. Without `due_at`, a clear time in the text (with a day word
    or not) becomes its time and is taken out of the text; unclear am / pm
    raises AmbiguousTime. A time already passed: added straight to Overdue,
    with no reminder. `note.understood` describes what was read (or None)."""
    now = now or datetime.now()
    text = (text or "").strip()
    if not text:
        raise TaskError("A note needs some text.")
    understood = None
    if due_at is None and read_text:
        r = TT.read(text, now.date(), window or DEFAULT_WINDOW, ampm=ampm)
        if r is not None:
            day = r.day or now.date()
            due_at = datetime.combine(day, r.start)
            when = "today" if day == now.date() else f"{day:%a %d %b}"
            understood = (f"Read from the note: {when} at {r.start:%H:%M}; '{r.time_text}'"
                          + (f" and '{r.day_text}'" if r.day_text else "") + " moved out of the text.")
            text = r.title
    if len(text) > MAX_TEXT:
        raise TaskError(f"A note can be at most {MAX_TEXT} characters; this one has {len(text)}.")
    color = validate_color(color)
    if count(s) >= MAX_NOTES:
        raise TaskError(f"You already have {MAX_NOTES} notes, the most there can be. Delete one to add another.")
    note = Note(text=text, due_at=due_at, color=color, created_at=now)
    if due_at is not None and due_at <= now:   # already past: it goes to Overdue, no reminder
        note.reminded_at, note.reminded_how = now, "past"
        understood = (understood or "") + (" " if understood else "") + \
            f"{due_at:%a %d %b %H:%M} has already passed, so the note is under Overdue."
    s.add(note)
    s.commit()
    note.understood = understood
    return note


def get_note(s: Session, note_id: int) -> Note:
    note = s.get(Note, note_id)
    if note is None:
        raise TaskError(f"There's no note {note_id} (it may have been deleted).")
    return note


def delete_note(s: Session, note_id: int) -> str:
    """Delete a note (no confirmation: Undo restores it exactly). Returns its text."""
    note = get_note(s, note_id)
    text = note.text
    s.delete(note)
    s.commit()
    return text


def dismiss_banner(s: Session, note_id: int) -> Note:
    """Hide a note's reminder banner. The note stays; it is never reminded again."""
    note = get_note(s, note_id)
    note.banner_open = False
    s.commit()
    return note


@dataclass
class Sections:
    upcoming: List[Note] = field(default_factory=list)   # time not passed, soonest first
    no_time: List[Note] = field(default_factory=list)    # newest first
    overdue: List[Note] = field(default_factory=list)    # time passed, earliest first; stay until deleted

    @property
    def total(self) -> int:
        return len(self.upcoming) + len(self.no_time) + len(self.overdue)


def sections(s: Session, now: datetime) -> Sections:
    out = Sections()
    for n in s.scalars(select(Note)):
        if n.due_at is None:
            out.no_time.append(n)
        elif n.due_at > now:
            out.upcoming.append(n)
        else:
            out.overdue.append(n)
    out.upcoming.sort(key=lambda n: (n.due_at, n.id))
    out.no_time.sort(key=lambda n: (n.created_at, n.id), reverse=True)
    out.overdue.sort(key=lambda n: (n.due_at, n.id))
    return out


def matching(s: Session, said: str) -> List[Note]:
    """Notes whose text contains the words said (for voice / typed delete), best first."""
    from .voice import parse as P
    notes = list(s.scalars(select(Note).order_by(Note.id)))
    words = P.normalize(said).split()
    exact = [n for n in notes if words and all(w in P.normalize(n.text).split() or w in P.normalize(n.text)
                                               for w in words)]
    if exact:
        return exact
    return [n for _, n in P.fuzzy_matches(said, notes, key=lambda n: n.text)]


def describe(n: Note, today: Optional[date] = None) -> str:
    if n.due_at is None:
        return n.text
    today = today or date.today()
    day = "today" if n.due_at.date() == today else f"{n.due_at:%a %d %b}"
    return f"{n.text}, {day} at {n.due_at:%H:%M}"


# ---------- the one reminder per note ----------

def _claim(s: Session, now: datetime, how: str) -> List[Note]:
    """Mark every note whose time has come and that hasn't been reminded.
    Each row is claimed with a conditional UPDATE, so if the terminal and the
    web app both run, only one of them reminds."""
    due = list(s.scalars(select(Note).where(Note.due_at.is_not(None), Note.due_at <= now,
                                            Note.reminded_at.is_(None)).order_by(Note.due_at, Note.id)))
    got = []
    for n in due:
        res = s.execute(update(Note).where(Note.id == n.id, Note.reminded_at.is_(None))
                        .values(reminded_at=now, reminded_how=how, banner_open=(how == "live")))
        if res.rowcount == 1:
            got.append(n)
    s.commit()
    for n in got:
        s.refresh(n)
    return got


def claim_due(s: Session, now: datetime) -> List[Note]:
    """Notes whose time just arrived while tomits runs: one banner + one notification each."""
    return _claim(s, now, "live")


def claim_away(s: Session, now: datetime) -> int:
    """At start: notes that passed while tomits wasn't running. Counted for one
    summary banner; no notification each."""
    return len(_claim(s, now, "away"))


class NoteService:
    """Background check every CHECK_SECONDS. `on_due(notes)` gets the notes
    claimed this time (the caller shows the banner and the notification)."""

    def __init__(self, session_factory: sessionmaker, on_due: Callable[[List[Note]], None],
                 clock: Callable[[], datetime] = datetime.now, interval_seconds: int = CHECK_SECONDS) -> None:
        self._sf, self._on_due, self._clock, self._interval = session_factory, on_due, clock, interval_seconds
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._scheduler = schedule.Scheduler()
        self.last_error: Optional[str] = None

    def startup(self) -> int:
        with self._lock, self._sf() as s:
            return claim_away(s, self._clock())

    def check(self) -> List[Note]:
        with self._lock, self._sf() as s:
            got = claim_due(s, self._clock())
        if got:
            self._on_due(got)
        return got

    def _safe(self) -> None:
        try:
            self.check()
        except Exception as e:  # never stop checking
            self.last_error = str(e)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._scheduler.every(self._interval).seconds.do(self._safe)
        self._thread = threading.Thread(target=self._loop, name="tomits-notes", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(1):
            self._scheduler.run_pending()

    def stop(self) -> None:
        self._stop.set()


def to_json(n: Note, now: datetime) -> Dict:
    return {"id": n.id, "text": n.text, "color": n.color,
            "due": n.due_at.isoformat(timespec="minutes") if n.due_at else None,
            "due_label": (("today " if n.due_at.date() == now.date() else f"{n.due_at:%a %d %b} ") +
                          f"{n.due_at:%H:%M}") if n.due_at else None,
            "created": n.created_at.isoformat(timespec="minutes"),
            "overdue": bool(n.due_at and n.due_at <= now), "banner": bool(n.banner_open)}
