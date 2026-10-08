"""User settings stored as JSON next to the database (data/settings.json)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import time
from pathlib import Path

from .errors import TaskError

DEFAULT_SNOOZE_MINUTES = 5
SNOOZE_RANGE = (1, 120)
DEFAULT_DAY_START = "09:00"
DEFAULT_DAY_END = "21:00"
DEFAULT_TASK_MINUTES = 30          # length of a task whose title gives a single time
TASK_MINUTES_RANGE = (5, 600)


@dataclass
class Settings:
    snooze_minutes: int = DEFAULT_SNOOZE_MINUTES
    # v1.3: the planner only places tasks inside this daily window
    day_start: str = DEFAULT_DAY_START
    day_end: str = DEFAULT_DAY_END
    # v1.5 voice
    push_to_talk_key: str = "v"
    hands_free: bool = False
    wake_phrase: str = "hey tomits"
    spoken_replies: bool = True
    muted: bool = False
    voice_model: str = ""          # (v1.5, Vosk; no longer used)
    # v1.5.1
    stt_model: str = "small"       # faster-whisper model size: tiny / base / small / medium / large-v3-turbo ...
    llm_enabled: bool = True       # use the local language model (Ollama) to understand rephrased commands
    llm_model: str = "qwen2.5:1.5b"
    input_device: str = ""         # sounddevice input index; blank = Windows default
    # v1.6 web app
    ui_layout: int = 1             # 1-6, see LAYOUTS
    ui_theme: str = "system"       # system / light / dark
    setup_done: bool = False       # first-run setup finished or skipped
    browser_mic: str = ""          # microphone chosen in the browser (its device id); blank = default
    # v1.7: a title with a single time ("gym at 7pm") and no length gets this many minutes
    default_task_minutes: int = DEFAULT_TASK_MINUTES
    # v1.8: the Remember panel is open (True) or collapsed to its count
    notes_open: bool = False

    @property
    def window(self):
        return _parse_hhmm(self.day_start), _parse_hhmm(self.day_end)


# v1.6: the six web layouts (names shown in the layout chooser)
LAYOUTS = {
    1: ("Timeline", "A left sidebar and a vertical timeline of the day; each block shows why it is there."),
    2: ("Calendar grid", "A week grid with today widened, a 'no time' row and a goals ladder panel."),
    3: ("Board", "Cards in Didn't fit, Planned, Now, Done and Missed columns; pages open as drawers."),
    4: ("Focus on now", "One calm screen with the current task large; everything else in a dock."),
    5: ("Split dashboard", "Dense panes: plan, goals, reschedule, voice and history at once."),
    6: ("Voice first", "A conversation with a big mic; answers come back as cards you can act on."),
}
THEMES = ("system", "light", "dark")


def validate_layout(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 0
    if n not in LAYOUTS:
        raise TaskError("Pick a layout from 1 to 6.")
    return n


def validate_theme(value) -> str:
    theme = str(value or "").strip().lower()
    if theme not in THEMES:
        raise TaskError("The theme is system, light or dark.")
    return theme


def validate_snooze(minutes) -> int:
    try:
        value = int(minutes)
    except (TypeError, ValueError):
        raise TaskError("Snooze length must be a whole number of minutes.") from None
    lo, hi = SNOOZE_RANGE
    if not lo <= value <= hi:
        raise TaskError(f"Snooze length must be between {lo} and {hi} minutes.")
    return value


def validate_task_minutes(minutes) -> int:
    try:
        value = int(minutes)
    except (TypeError, ValueError):
        raise TaskError("The default task length must be a whole number of minutes.") from None
    lo, hi = TASK_MINUTES_RANGE
    if not lo <= value <= hi:
        raise TaskError(f"The default task length must be between {lo} and {hi} minutes.")
    return value


def _parse_hhmm(text: str) -> time:
    try:
        h, m = str(text).split(":")
        return time(int(h), int(m))
    except (ValueError, TypeError):
        raise TaskError(f"Can't read time {text!r}. Use HH:MM.") from None


def validate_window(start, end):
    """Accepts time objects or 'HH:MM'. Returns ('HH:MM', 'HH:MM')."""
    start = start if isinstance(start, time) else _parse_hhmm(start)
    end = end if isinstance(end, time) else _parse_hhmm(end)
    if start >= end:
        raise TaskError("The day window must end after it starts (same day).")
    return start.strftime("%H:%M"), end.strftime("%H:%M")


def settings_path(db_path) -> Path:
    return Path(db_path).with_name("settings.json")


def load_settings(path: Path) -> Settings:
    """Missing or unreadable file -> defaults for the bad parts (never crashes)."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError
    except (OSError, ValueError):
        return Settings()
    out = Settings()
    try:
        out.snooze_minutes = validate_snooze(raw.get("snooze_minutes", DEFAULT_SNOOZE_MINUTES))
    except TaskError:
        pass
    try:
        out.day_start, out.day_end = validate_window(raw.get("day_start", DEFAULT_DAY_START),
                                                     raw.get("day_end", DEFAULT_DAY_END))
    except TaskError:
        pass
    try:
        out.push_to_talk_key = validate_key(raw.get("push_to_talk_key", out.push_to_talk_key))
    except TaskError:
        pass
    for name in ("hands_free", "spoken_replies", "muted"):
        if isinstance(raw.get(name), bool):
            setattr(out, name, raw[name])
    if isinstance(raw.get("wake_phrase"), str) and raw["wake_phrase"].strip():
        out.wake_phrase = raw["wake_phrase"].strip().lower()
    if isinstance(raw.get("voice_model"), str):
        out.voice_model = raw["voice_model"]
    for name in ("stt_model", "llm_model", "input_device"):
        if isinstance(raw.get(name), str):
            setattr(out, name, raw[name].strip())
    if isinstance(raw.get("llm_enabled"), bool):
        out.llm_enabled = raw["llm_enabled"]
    try:
        out.ui_layout = validate_layout(raw.get("ui_layout", out.ui_layout))
    except TaskError:
        pass
    try:
        out.ui_theme = validate_theme(raw.get("ui_theme", out.ui_theme))
    except TaskError:
        pass
    try:
        out.default_task_minutes = validate_task_minutes(raw.get("default_task_minutes", DEFAULT_TASK_MINUTES))
    except TaskError:
        pass
    if isinstance(raw.get("notes_open"), bool):
        out.notes_open = raw["notes_open"]
    if isinstance(raw.get("setup_done"), bool):
        out.setup_done = raw["setup_done"]
    if isinstance(raw.get("browser_mic"), str):
        out.browser_mic = raw["browser_mic"][:200]
    return out


# keys the typed menus already use can't be the push-to-talk key
RESERVED_KEYS = set("anpeudfsxrzhlgtocmq")


def validate_key(key) -> str:
    key = str(key or "").strip().lower()
    if len(key) != 1 or not key.isalnum():
        raise TaskError("The push-to-talk key must be a single letter or digit.")
    if key in RESERVED_KEYS:
        raise TaskError(f"'{key}' is already a menu key; pick another (v, b, i, j, k, w or y are free).")
    return key


def save_settings(path: Path, settings: Settings) -> None:
    validate_snooze(settings.snooze_minutes)
    validate_window(settings.day_start, settings.day_end)
    validate_key(settings.push_to_talk_key)
    validate_layout(settings.ui_layout)
    validate_theme(settings.ui_theme)
    validate_task_minutes(settings.default_task_minutes)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # write to a temp file then replace, so a reader never sees half a file
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    tmp.replace(path)
