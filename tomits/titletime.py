"""Reading a clock time (and a day) out of a task title. Pure: no database,
no UI, so typed forms, the quick-add box, voice and the terminal all read a
title the same way (services.add_task / update_task call this).

Only clear time expressions count:
- a time with am / pm ("11pm", "11:30 pm", "7.15 a.m.")
- a 24-hour time ("23:00", "07:30"); a time like "6:30" counts only after
  "at" or inside a range, so "verse 3:16" stays text
- "at" followed by a time ("at 5", "at 17", "at 5:30")
- ranges ("7 to 8 pm", "from 6:30 to 7:15", "7-8pm", "between 2 and 3 pm")
- "noon" / "midnight" after at / by / from or at the end of the title
Bare numbers never count ("10 pages", "chapter 5", "pages 10 to 20").
A time after "until", "till" or "before" is an end, not a start: not read.

Day words are read only together with a time: today, tonight, tomorrow, a
weekday ("on friday", "this friday": the coming one, today included) and
"next <weekday>" (strictly after today; weeks start on Sunday, so "next
sunday" is the first Sunday after today).

Unclear am / pm ("at 5", "6:30-7:15"): the reading whose start falls inside
the day window wins; if both or neither do, AmbiguousTime asks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Tuple

from .errors import TaskError

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MIDNIGHT_MIN = 24 * 60

# one time point; parsed again by _point()
_AP = r"(?:[ap]\.?m\.?)(?![a-z])"
_POINT = (r"(?:noon|midday|midnight|\d{1,2}(?:[:.]\d{2})?\s*" + _AP + r"|\d{1,2}:\d{2}|\d{1,2}\s*o'?clock|\d{1,2})")
_LEFT = r"(?<![\w:.\-/])"
_RIGHT = r"(?![\w:/]|\.\d)"
_SEP = r"\s*(?:-|–|—|\bto\b|\btill\b|\buntil\b)\s*"

_RANGE_RE = re.compile(
    r"(?:\b(?:from|at)\s+|@\s*)?" + _LEFT + r"(?P<a>" + _POINT + r")" + _RIGHT + _SEP +
    r"(?P<b>" + _POINT + r")" + _RIGHT, re.I)
_BETWEEN_RE = re.compile(
    r"\bbetween\s+(?P<a>" + _POINT + r")" + _RIGHT + r"\s+and\s+(?P<b>" + _POINT + r")" + _RIGHT, re.I)
_SINGLE_RE = re.compile(r"(?:\b(?P<lead>at|by|from|after|around|about)\s+|@\s*)?" + _LEFT +
                        r"(?P<a>" + _POINT + r")" + _RIGHT, re.I)
_ENDERS = re.compile(r"\b(?:until|till|til|before)\s*$", re.I)
# after "at 5" (a bare hour) only these may follow, so "look at 3 options" stays text
_BARE_FOLLOW = {"today", "tonight", "tomorrow", "on", "this", "next", "coming", "for", "and", "with", "in",
                "sharp", "then", "to", *WEEKDAYS}
_DAY_RE = re.compile(r"\b(?:(?P<pre>on|this|coming|next)\s+)?(?P<word>today|tonight|tomorrow|" +
                     "|".join(WEEKDAYS) + r")\b(?!['’]s)", re.I)


class AmbiguousTime(TaskError):
    """am or pm can't be told from the day window: ask, then call again with
    ampm="am" / "pm". `line` is the row of a several-task form (else None)."""

    def __init__(self, question: str, choices: List[Tuple[str, str]], line: Optional[int] = None):
        super().__init__(question)
        self.question = question
        self.choices = choices
        self.line = line


@dataclass
class Reading:
    typed: str                  # the title as typed
    title: str                  # what's left once the time (and day) are taken out
    time_text: str              # the words that were read as the time
    start: time
    range_minutes: Optional[int] = None    # from a range; None for a single time
    day: Optional[date] = None             # from a day word
    day_text: Optional[str] = None
    ampm: Optional[str] = None             # how an unclear am / pm was settled
    ampm_how: Optional[str] = None         # "day window" / "your answer" / "tonight"
    capped: bool = False                   # the range ran past midnight: it ends at midnight
    notes: List[str] = field(default_factory=list)


# ---------- time points ----------

@dataclass
class _Pt:
    minutes: int                # 0..1440 (1440 = midnight at the end of the day)
    clear: bool                 # am / pm known
    alt: Optional[int] = None   # the other reading when unclear (+12 h)
    marked: bool = False        # am/pm, colon, o'clock, noon or midnight (not a bare number)
    bare: bool = False


def _point(text: str, as_end: bool = False) -> Optional[_Pt]:
    t = text.lower().replace(" ", "")
    if t in ("noon", "midday"):
        return _Pt(12 * 60, True, marked=True)
    if t == "midnight":
        return _Pt(MIDNIGHT_MIN if as_end else 0, True, marked=True)
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?([ap])\.?m\.?", t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if not 1 <= h <= 12 or mi > 59:
            return None
        h = h % 12 + (12 if m.group(3) == "p" else 0)
        return _Pt(h * 60 + mi, True, marked=True)
    m = re.fullmatch(r"(\d{1,2})o'?clock", t)
    if m:
        h = int(m.group(1))
        if not 1 <= h <= 12:
            return None
        return _Pt((h % 12) * 60, False, alt=(h % 12 + 12) * 60, marked=True)
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", t)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h > 23 or mi > 59:
        return None
    colon = m.group(2) is not None
    if h == 0 or h >= 13 or (colon and m.group(1).startswith("0")):
        return _Pt(h * 60 + mi, True, marked=colon, bare=not colon)
    return _Pt((h % 12) * 60 + mi, False, alt=(h % 12 + 12) * 60 + mi, marked=colon, bare=not colon)


def _after(start: int, cands) -> int:
    """The candidate end that comes soonest after start (it may wrap past midnight)."""
    return min(cands, key=lambda c: (c - start) % MIDNIGHT_MIN or MIDNIGHT_MIN)


def _hm(minutes: int) -> str:
    return "24:00" if minutes == MIDNIGHT_MIN else f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def _clock_label(minutes: int) -> str:
    h, m = divmod(minutes % MIDNIGHT_MIN, 60)
    return f"{h % 12 or 12}:{m:02d} {'am' if h < 12 else 'pm'}"


# ---------- finding the time ----------

@dataclass
class _Found:
    span: Tuple[int, int]
    readings: List[Tuple[int, Optional[int]]]   # (start, end or None); 1 reading = clear, 2 = am / pm
    text: str


def _range_readings(a: _Pt, b: _Pt) -> List[Tuple[int, int]]:
    if a.clear:
        starts = [a.minutes]
    elif b.clear:
        starts = [_before(b.minutes, [a.minutes, a.alt])]
    else:
        starts = [a.minutes, a.alt]
    out = []
    for s in starts:
        if b.clear:
            e = b.minutes
        else:
            e = _after(s, [b.minutes, b.alt])
        out.append((s, e))
    return out


def _before(end: int, cands) -> int:
    """The candidate start that comes latest before end (it may wrap)."""
    return min(cands, key=lambda c: (end - c) % MIDNIGHT_MIN or MIDNIGHT_MIN)


def _find(title: str) -> Optional[_Found]:
    best: Optional[_Found] = None
    for rx in (_RANGE_RE, _BETWEEN_RE):
        for m in rx.finditer(title):
            a, b = _point(m.group("a")), _point(m.group("b"), as_end=True)
            if a is None or b is None or not (a.marked or b.marked):
                continue
            if _ENDERS.search(title[:m.start()]):
                continue
            found = _Found((m.start(), m.end()), _range_readings(a, b), m.group(0).strip())
            if best is None or found.span[0] < best.span[0]:
                best = found
            break
    for m in _SINGLE_RE.finditer(title):
        if best is not None and m.start() >= best.span[0]:
            break
        raw = m.group("a")
        p = _point(raw)
        if p is None:
            continue
        lead = (m.group("lead") or ("@" if m.group(0).lstrip().startswith("@") else "")).lower()
        if _ENDERS.search(title[:m.start()]):
            continue
        low = raw.lower()
        if low in ("noon", "midday", "midnight"):
            rest = title[m.end():].strip(" .,;:!)")
            if not lead and rest:
                continue
        elif p.bare:
            if lead not in ("at", "@"):
                continue
            nxt = re.match(r"\s*([A-Za-z]+)", title[m.end():])
            tail = title[m.end():].strip()
            if tail and not re.match(r"[.,;:!)(\-–—]", tail) and (not nxt or nxt.group(1).lower() not in _BARE_FOLLOW):
                continue
        elif ":" in low and not re.search(r"[ap]\.?m", low) and not p.clear and lead not in ("at", "@"):
            continue  # "6:30" alone could be anything (a verse, a score); "at 6:30" is a time
        readings = [(p.minutes, None)] if p.clear else [(p.minutes, None), (p.alt, None)]
        best = _Found((m.start(), m.end()), readings, m.group(0).strip())
        break
    return best


# ---------- day words ----------

def _day_of(word: str, pre: Optional[str], today: date) -> date:
    word = word.lower()
    if word in ("today", "tonight"):
        return today
    if word == "tomorrow":
        return today + timedelta(days=1)
    delta = (WEEKDAYS.index(word) - today.weekday()) % 7
    if delta == 0 and (pre or "").lower() == "next":
        delta = 7
    return today + timedelta(days=delta)


# ---------- cleaning the title ----------

def _tidy(text: str) -> str:
    t = re.sub(r"\(\s*\)|\[\s*\]", " ", text)
    t = re.sub(r"\s+([,;:.!?])", r"\1", t)
    t = re.sub(r"([,;:])(\s*[,;:])+", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    for _ in range(3):
        t = re.sub(r"^(?:[-–—,;:@]\s*)+|(?:\s*[-–—,;:@])+$", "", t).strip()
        t = re.sub(r"(?:^|\s)(?:at|on|from|by|for|this|next|and)$", "", t, flags=re.I).strip()
        t = re.sub(r"^(?:at|on|from|by)\s", "", t, flags=re.I).strip()
    return t


def _cut(text: str, span: Tuple[int, int]) -> str:
    return text[:span[0]] + " " + text[span[1]:]


# ---------- the reader ----------

def read(title: str, today: date, window: Tuple[time, time], ampm: Optional[str] = None,
         line: Optional[int] = None) -> Optional[Reading]:
    """The time (and day) written in `title`, or None if it has no clear time.
    Raises AmbiguousTime when am / pm can't be settled, and TaskError when
    nothing but the time is left of the title."""
    typed = title or ""
    found = _find(typed)
    if found is None:
        return None
    rest = _cut(typed, found.span)
    day, day_text = None, None
    dm = _DAY_RE.search(rest)
    if dm:
        day, day_text = _day_of(dm.group("word"), dm.group("pre"), today), dm.group(0)
        rest = _cut(rest, dm.span())
    clean = _tidy(rest)
    if not clean:
        raise TaskError(f"'{typed.strip()}' is only a time; add what the task is.")

    readings, how, chosen = found.readings, None, None
    if len(readings) == 2:
        am, pm = sorted(readings, key=lambda r: r[0])
        w0, w1 = window[0].hour * 60 + window[0].minute, window[1].hour * 60 + window[1].minute
        fits = [r for r in (am, pm) if w0 <= r[0] < w1]
        if ampm in ("am", "pm"):
            chosen, how = (am if ampm == "am" else pm), "your answer"
        elif day_text and day_text.lower().endswith("tonight"):
            chosen, how = pm, "tonight"
        elif len(fits) == 1:
            chosen, how = fits[0], "day window"
        else:
            def label(r):
                return _clock_label(r[0]) + (f" to {_clock_label(r[1])}" if r[1] is not None else "")
            where = "both fit" if fits else "neither is"
            raise AmbiguousTime(
                f"'{found.text}' in '{typed.strip()}': {label(am)} or {label(pm)}? ({where} in your day window "
                f"{window[0]:%H:%M}-{window[1]:%H:%M}.)", [(label(am), "am"), (label(pm), "pm")], line)
        start, end = chosen
        ampm_used = "am" if chosen is am else "pm"
    else:
        (start, end), ampm_used = readings[0], None

    r = Reading(typed=typed, title=clean, time_text=found.text, start=time(start // 60 % 24, start % 60),
                day=day, day_text=day_text, ampm=ampm_used, ampm_how=how)
    if end is not None:
        if end <= start:   # runs past midnight: it ends at midnight (see TASKS.md)
            r.capped = True
            r.notes.append(f"'{found.text}' runs past midnight, so it ends at midnight; "
                           "add the rest for the next day as its own task")
            end = MIDNIGHT_MIN
        r.range_minutes = end - start
    return r


def cap_at_midnight(start: time, minutes: int) -> Tuple[int, bool]:
    """A detected time keeps its task inside its own day (so the per-day
    overlap check sees everything): the duration is cut at midnight."""
    room = MIDNIGHT_MIN - (start.hour * 60 + start.minute)
    return (room, True) if minutes > room else (minutes, False)


def describe(r: Reading, minutes: int, minutes_from: str, day: date, today: date, now: Optional[datetime]) -> str:
    """One short line: what was read from the title."""
    end = datetime.combine(day, r.start) + timedelta(minutes=minutes)
    when = "today" if day == today else "tomorrow" if day == today + timedelta(days=1) else f"{day:%a %d %b}"
    dur = {"range": "from the range", "default": "default length", "given": "the length you gave"}[minutes_from]
    from .services import format_duration
    parts = [f"Read from the title: {r.start:%H:%M}-{end:%H:%M} {when}", f"{format_duration(minutes)} ({dur})"]
    if r.ampm_how == "day window":
        parts.append(f"{r.ampm} because it falls in your day window")
    parts.append(f"'{r.time_text}'" + (f" and '{r.day_text}'" if r.day_text else "") + " moved out of the title")
    line = ", ".join(parts) + "."
    if now is not None and datetime.combine(day, r.start) < now:
        line += f" Note: {r.start:%H:%M} {'today ' if day == today else ''}has already passed; the task was added anyway."
    for n in r.notes:
        line += f" Note: {n}."
    return line
