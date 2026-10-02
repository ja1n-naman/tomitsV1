"""Local, deterministic understanding of spoken text. No network, no AI.

- normalize(): lower-case, number words -> digits, "p.m." -> "pm", ...
- extract_*(): pull a duration, time, date, priority, target out of a
  phrase and return what's left (usually a task or goal name)
- fuzzy_matches(): rank names against what was said
"""

from __future__ import annotations

import difflib
import re
from datetime import date, time, timedelta
from typing import List, Optional, Sequence, Tuple, TypeVar

T = TypeVar("T")

# ---------- tuning ----------
MATCH_THRESHOLD = 0.6     # fuzzy score needed to count as a match
UNIQUE_MARGIN = 0.15      # top match must beat the next by this much to be picked without asking
NAME_CONFIRM_SCORE = 0.8  # a single match weaker than this is read back ("Did you mean ...?") before acting

_UNITS = {"zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
          "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
            "ninth": 9, "tenth": 10}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]

CANCEL_WORDS = {"cancel", "stop that", "never mind", "nevermind", "forget it", "abort", "cancel that"}
YES_WORDS = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "correct", "right", "do it", "save",
             "yes please", "that's right", "thats right", "accept"}
NO_WORDS = {"no", "nope", "nah", "don't", "dont", "reject", "no thanks", "wrong"}


def _words_to_numbers(words: List[str]) -> List[str]:
    out, i = [], 0
    while i < len(words):
        w = words[i]
        if w in _TENS or w in _UNITS or (w == "hundred" and out and out[-1].isdigit()):
            if w == "hundred":
                out[-1] = str(int(out[-1]) * 100)
                i += 1
                if i < len(words) and words[i] == "and":
                    i += 1
                continue
            value = _TENS.get(w, _UNITS.get(w))
            i += 1
            if w in _TENS and i < len(words) and words[i] in _UNITS and _UNITS[words[i]] < 10:
                value += _UNITS[words[i]]
                i += 1
            if out and out[-1].isdigit() and int(out[-1]) % 100 == 0 and int(out[-1]) >= 100:
                out[-1] = str(int(out[-1]) + value)  # "one hundred twenty"
            else:
                out.append(str(value))
            continue
        out.append(w)
        i += 1
    return out


def normalize(text: str) -> str:
    """'Add a task: read for forty-five minutes at 3 P.M.' ->
    'add a task read for 45 minutes at 3 pm'"""
    t = (text or "").lower()
    t = re.sub(r"\b([ap])\.\s?m\.?", r"\1m", t)
    t = t.replace("o'clock", "oclock").replace("’", "'")
    t = re.sub(r"(\d)\s*(am|pm)\b", r"\1 \2", t)
    t = re.sub(r"[^a-z0-9:'\s]", " ", t)
    t = re.sub(r"(?<!\d):|:(?!\d)", " ", t)  # keep ':' only inside times like 10:30
    t = t.replace("'s ", "s ").replace("'", "")
    return " ".join(_words_to_numbers(t.split()))


def is_cancel(text: str) -> bool:
    return normalize(text) in CANCEL_WORDS


def is_yes(text: str) -> bool:
    return normalize(text) in YES_WORDS


def is_no(text: str) -> bool:
    return normalize(text) in NO_WORDS


def _cut(text: str, m: re.Match) -> str:
    return " ".join((text[:m.start()] + " " + text[m.end():]).split())


# ---------- durations ----------

_DUR_RE = re.compile(
    r"(?:\bfor\s+)?(?:(?P<half>half an hour|half hour)|"
    r"(?:(?P<h>\d+|an|a)\s*(?:and a half\s+)?(?P<hu>hours?|hrs?|h)\b(?P<hhalf>\s+and a half)?)?"
    r"\s*(?:and\s+)?(?:(?P<m>\d+)\s*(?P<mu>minutes?|mins?|m)\b)?)"
    r"(?:\s+more)?"
)


def extract_duration(text: str) -> Tuple[Optional[int], str]:
    """'read for 45 minutes' -> (45, 'read'); 'for an hour and a half' -> 90."""
    for m in _DUR_RE.finditer(text):
        if not m.group(0).strip():
            continue
        if m.group("half"):
            minutes = 30
        else:
            if not (m.group("hu") or m.group("mu")):
                continue
            h = m.group("h")
            hours = 1 if h in ("an", "a") else int(h or 0)
            minutes = hours * 60 + int(m.group("m") or 0)
            if m.group("hhalf") or (m.group(0).find("and a half") != -1 and m.group("hu")):
                minutes += 30
        if minutes > 0:
            return minutes, _cut(text, m)
    return None, text


# ---------- times ----------

_TIME_RE = re.compile(
    r"\b(?:at\s+|from\s+|until\s+|till\s+|to\s+)?(?:"
    r"(?P<noon>noon|midday|midnight)|"
    r"(?P<qp>half|quarter)\s+(?P<rel>past|to)\s+(?P<qh>\d{1,2})|"
    r"(?P<h>\d{1,2})(?::(?P<m1>\d{2})|\s+(?P<m2>\d{2})(?!\s*(?:minutes?|mins?|hours?)))?\s*(?P<ap>am|pm|oclock)?"
    r")\b"
)


def _hour_guess(h: int) -> int:
    """No am / pm said: 1-6 means afternoon, 7-11 morning, 12 noon."""
    return h + 12 if 1 <= h <= 6 else h


def extract_time(text: str, require_marker: bool = False) -> Tuple[Optional[time], str]:
    """'at 3 pm' / 'at 10 30' / 'half past 9' / 'tomorrow at 9' -> time.
    A bare number counts only after 'at' / 'until' / 'from' / 'to' or with am / pm."""
    for m in _TIME_RE.finditer(text):
        g = m.groupdict()
        lead = m.group(0).split()[0] in ("at", "from", "until", "till", "to")
        if g["noon"]:
            return (time(0, 0) if g["noon"] == "midnight" else time(12, 0)), _cut(text, m)
        if g["qp"]:
            h = _hour_guess(int(g["qh"]))
            if h > 23:
                continue
            minute = 30 if g["qp"] == "half" else 15
            if g["rel"] == "to":
                h, minute = (h - 1) % 24, 60 - minute
            return time(h, minute), _cut(text, m)
        if g["h"] is None:
            continue
        if not (lead or g["ap"]) or (require_marker and not lead and not g["ap"]):
            continue
        h, minute = int(g["h"]), int(g["m1"] or g["m2"] or 0)
        if minute > 59 or h > 23:
            continue
        ap = g["ap"]
        if ap == "pm" and h < 12:
            h += 12
        elif ap == "am" and h == 12:
            h = 0
        elif ap in (None, "oclock") and h <= 12:
            h = _hour_guess(h)
        if h > 23:
            continue
        return time(h, minute), _cut(text, m)
    return None, text


# ---------- dates ----------

def _next_weekday(today: date, wd: int, strictly_after: bool) -> date:
    delta = (wd - today.weekday()) % 7
    if delta == 0 and strictly_after:
        delta = 7
    return today + timedelta(days=delta)


_DATE_RE = re.compile(
    r"\b(?:(?:for|on)\s+)?(?:"
    r"(?P<rel>today|tonight|tomorrow|yesterday|day after tomorrow)|"
    r"(?:(?P<np>next|this|coming|last)\s+)?(?P<wd>" + "|".join(WEEKDAYS) + r")|"
    r"in\s+(?P<n>\d+)\s+days?|"
    r"(?:the\s+)?(?P<d1>\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<mo1>" + "|".join(MONTHS) + r")|"
    r"(?P<mo2>" + "|".join(MONTHS) + r")\s+(?:the\s+)?(?P<d2>\d{1,2})(?:st|nd|rd|th)?"
    r")\b"
)


def extract_date(text: str, today: date) -> Tuple[Optional[date], str]:
    """today / tomorrow / next sunday / on friday / in 3 days / 5 october."""
    m = _DATE_RE.search(text)
    if not m:
        return None, text
    g = m.groupdict()
    if g["rel"]:
        d = {"today": today, "tonight": today, "tomorrow": today + timedelta(days=1),
             "yesterday": today - timedelta(days=1), "day after tomorrow": today + timedelta(days=2)}[g["rel"]]
    elif g["wd"]:
        wd = WEEKDAYS.index(g["wd"])
        if g["np"] == "last":
            d = today - timedelta(days=((today.weekday() - wd) % 7) or 7)
        else:
            d = _next_weekday(today, wd, strictly_after=g["np"] == "next")
    elif g["n"]:
        d = today + timedelta(days=int(g["n"]))
    else:
        day = int(g["d1"] or g["d2"])
        month = MONTHS.index(g["mo1"] or g["mo2"]) + 1
        try:
            d = date(today.year, month, day)
        except ValueError:
            return None, text
        if d < today - timedelta(days=180):
            d = date(today.year + 1, month, day)
    return d, _cut(text, m)


_PERIOD_RE = re.compile(
    r"\b(?P<which>this|last|previous|next|current)?\s*(?P<kind>day|week|month)(?:s|ly)?\b|"
    r"\b(?P<rel>today|yesterday|tomorrow)(?:s)?\b"
)


def extract_period(text: str, today: date):
    """'this week' / 'last month' / 'tomorrow' / 'weekly' -> (kind, a date inside
    that period, rest). kind is 'day' | 'week' | 'month' or None."""
    m = _PERIOD_RE.search(text)
    if not m:
        return None, None, text
    if m.group("rel"):
        d = {"today": today, "yesterday": today - timedelta(days=1), "tomorrow": today + timedelta(days=1)}[m.group("rel")]
        return "day", d, _cut(text, m)
    kind, which = m.group("kind"), m.group("which")
    step = {"last": -1, "previous": -1, "next": 1}.get(which, 0)
    if kind == "day":
        d = today + timedelta(days=step)
    elif kind == "week":
        d = today + timedelta(weeks=step)
    else:
        months = today.year * 12 + today.month - 1 + step
        d = date(months // 12, months % 12 + 1, 1)
    return kind, d, _cut(text, m)


# ---------- priority, numbers, targets ----------

_PRIORITY_RE = re.compile(
    r"\b(?:(?:with|at|as|set to|make it|priority)\s+)?(?:(?:a|an)\s+)?"
    r"(?:priority\s+(?P<n>[1-4])|(?P<w>urgent|high|important|normal|medium|low)(?:\s+priority)?)\b"
)
PRIORITY_WORDS = {"urgent": 1, "high": 2, "important": 2, "normal": 3, "medium": 3, "low": 4}


def extract_priority(text: str) -> Tuple[Optional[int], str]:
    m = _PRIORITY_RE.search(text)
    if not m:
        return None, text
    return (int(m.group("n")) if m.group("n") else PRIORITY_WORDS[m.group("w")]), _cut(text, m)


def parse_number(text: str) -> Optional[int]:
    """'2' / 'two' / 'number 2' / 'the second one' -> 2."""
    t = normalize(text)
    for word, n in ORDINALS.items():
        if re.search(rf"\b{word}\b", t):
            return n
    m = re.search(r"\b(\d+)\b", t)
    return int(m.group(1)) if m else None


_TARGET_RE = re.compile(r"\b(?:(?:with\s+)?(?:a\s+)?target(?:\s+of)?\s+)?(?P<n>\d+(?:\.\d+)?)\s+(?P<unit>[a-z]+)\b")
_NOT_UNITS = {"am", "pm", "oclock", "days", "day", "times", "percent"}


def extract_target(text: str) -> Tuple[Optional[float], Optional[str], str, bool]:
    """'run 40 km' -> (40, 'km', text, explicit=False). With the
    word 'target' the phrase is removed from the title (explicit=True)."""
    for m in _TARGET_RE.finditer(text):
        if m.group("unit") in _NOT_UNITS:
            continue
        explicit = "target" in m.group(0)
        rest = _cut(text, m) if explicit else text
        return float(m.group("n")), m.group("unit"), rest, explicit
    return None, None, text, False


def same_unit(a: Optional[str], b: Optional[str]) -> bool:
    """'page' ~ 'pages', 'km' ~ 'kms', case-insensitive."""
    a, b = (a or "").lower().strip(), (b or "").lower().strip()
    return a == b or a.rstrip("s") == b.rstrip("s")


# ---------- fuzzy names ----------

_FILLER = {"the", "my", "a", "an", "task", "goal", "please", "called", "named", "with"}


def _clean(name: str) -> str:
    return " ".join(w for w in normalize(name).split() if w not in _FILLER)


_IRREGULAR = {"ran": "run", "wrote": "write", "read": "read", "did": "do", "went": "go", "swam": "swim"}


def stem(word: str) -> str:
    """Very small English stemmer: running -> run, pages -> page, studied -> study."""
    w = _IRREGULAR.get(word, word)
    if w.endswith(("sses", "xes", "zes", "ches", "shes")) and len(w) >= 5:
        w = w[:-2]
    else:
        for suffix, repl in (("ies", "y"), ("ied", "y"), ("ing", ""), ("ed", ""), ("s", "")):
            if w.endswith(suffix) and len(w) - len(suffix) >= 3 and not w.endswith("ss"):
                w = w[: len(w) - len(suffix)] + repl
                break
    if len(w) >= 4 and w[-1] == w[-2] and w[-1] not in "aeiouls":
        w = w[:-1]   # runn -> run
    return w


def name_score(said: str, name: str) -> float:
    a, b = _clean(said), _clean(name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    aw, bw = {stem(w) for w in a.split()}, {stem(w) for w in b.split()}
    overlap = len(aw & bw) / len(aw) if aw else 0.0      # how much of what was said is in the name (word stems)
    contained = 0.95 if (f" {a} " in f" {b} ") else 0.0  # "report" in "write report"
    return max(ratio, overlap * 0.9, contained)


def fuzzy_matches(said: str, items: Sequence[T], key) -> List[Tuple[float, T]]:
    """Items scoring at least MATCH_THRESHOLD, best first."""
    scored = sorted(((name_score(said, key(i)), i) for i in items), key=lambda x: -x[0])
    return [(sc, i) for sc, i in scored if sc >= MATCH_THRESHOLD]


def pick_unique(matches: List[Tuple[float, T]]) -> Optional[T]:
    """The single clear winner, or None if it's ambiguous (or empty)."""
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0][1]
    if matches[0][0] >= 0.99 and matches[1][0] < 0.99:
        return matches[0][1]
    if matches[0][0] - matches[1][0] >= UNIQUE_MARGIN:
        return matches[0][1]
    return None
