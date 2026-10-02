"""The voice dialog: turns one utterance into a finished action, asking short
follow-up questions when something is missing. Engine-independent: it talks
to an `io` object with listen() and say(), so tests use text transcripts.

Every rule stays in the logic layer (services / tracking / planner /
rescheduler). A refusal there (TaskError) is spoken back unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Callable, List, Optional, Sequence, TypeVar

from ..errors import TaskError
from . import parse as P
from . import registry as R

T = TypeVar("T")

# ---------- tuning ----------
LOW_CONFIDENCE = 0.6   # below this, nothing is done: the app says what it heard and asks you to repeat (v1.5.1)
MAX_RETRIES = 2        # "I didn't catch that" this many times, then the question is cancelled


class Cancelled(Exception):
    """The user said cancel (or never answered)."""


@dataclass
class Heard:
    text: str
    confidence: float = 1.0
    audio: Optional[object] = None     # the prepared 16 kHz audio, kept for the voice log
    device: Optional[str] = None


@dataclass
class VoiceState:
    """Remembered between turns."""
    last_task_id: Optional[int] = None
    view_kind: Optional[str] = None      # set while a tracking page is open
    view_start: Optional[date] = None
    history: List[str] = field(default_factory=list)


class Dialog:
    def __init__(self, app, io, state: Optional[VoiceState] = None):
        self.app = app
        self.io = io
        self.state = state or VoiceState()
        self.last_said: Optional[str] = None
        self.declined = False   # a confirmation got "no" during this command

    # ----- time -----

    def now(self) -> datetime:
        return self.app.clock()

    def today(self) -> date:
        return self.app.today()

    # ----- speaking and listening -----

    def say(self, text: str) -> None:
        self.last_said = text
        self.io.say(text)

    def show(self, text: str) -> None:
        """On screen only (not spoken)."""
        show = getattr(self.io, "show", None)
        if show is not None:
            show(text)

    def ask(self, question: str, grammar: Optional[Sequence[str]] = None, raw: bool = False) -> str:
        """Ask and return the answer (normalized unless raw). 'cancel' raises
        Cancelled; silence is retried MAX_RETRIES times."""
        prompt = question
        for _ in range(MAX_RETRIES + 1):
            heard = self.io.listen(prompt, grammar)
            text = (heard.text or "").strip()
            if text and P.is_cancel(text):
                raise Cancelled()
            if text:
                self.state.history.append(text)
                return text if raw else P.normalize(text)
            prompt = "I didn't catch that. " + question
        raise Cancelled()

    def confirm(self, statement: str) -> bool:
        """Read back and require a spoken yes. Anything else is a no."""
        for _ in range(MAX_RETRIES + 1):
            answer = self.ask(f"{statement} Say yes or no.")
            if P.is_yes(answer):
                return True
            if P.is_no(answer):
                self.declined = True
                return False
            statement = "Please say yes or no."
        self.declined = True
        return False

    def dictate(self, what: str, initial: Optional[str] = None, question: Optional[str] = None) -> str:
        """Free text: read it back, then 'save', 'redo', or 'change X to Y'."""
        text = initial.strip() if initial else None
        while True:
            if not text:
                text = self.ask(question or f"Say the {what}.", raw=True).strip()
            raw = self.ask(f"I heard: {text}. Say save, redo, or change something to something.", raw=True)
            answer = P.normalize(raw)
            if P.is_yes(answer):
                return text
            if answer in ("redo", "again", "say it again", "start over", "no"):
                text = None
                question = f"Say the {what} again."
                continue
            if answer in ("edit", "change it"):
                raw = self.ask("Say change, then the words to replace, then to, then the new words.", raw=True)
                answer = P.normalize(raw)
            if answer.startswith("change ") and " to " in answer:
                # use the words as spoken (not digit-converted) so "three" matches "three"
                spoken = " ".join(raw.lower().replace(",", " ").split())
                body = spoken[len("change "):] if spoken.startswith("change ") else answer[len("change "):]
                old, new = body.split(" to ", 1) if " to " in body else answer[len("change "):].split(" to ", 1)
                old, new = old.strip(), new.strip()
                if old and old in text.lower():
                    idx = text.lower().index(old)
                    text = text[:idx] + new + text[idx + len(old):]
                else:
                    self.say(f"I couldn't find '{old}' in the text.")
                continue
            self.say("Say save to keep it, redo to say it again, or change something to something.")

    def choose(self, items: Sequence[T], describe: Callable[[T], str], what: str = "one") -> T:
        """Several matches: list them by number and pick by voice."""
        if len(items) == 1:
            return items[0]
        listing = "; ".join(f"{i}: {describe(x)}" for i, x in enumerate(items, 1))
        for _ in range(MAX_RETRIES + 1):
            n = P.parse_number(self.ask(f"I found {len(items)}. {listing}. Which {what}? Say the number."))
            if n and 1 <= n <= len(items):
                return items[n - 1]
            listing = f"a number from 1 to {len(items)}"
        raise Cancelled()

    # ----- typed-value follow-ups -----

    def ask_duration(self, question: str = "How long will it take?") -> int:
        for _ in range(MAX_RETRIES + 1):
            text = self.ask(question)
            minutes, _ = P.extract_duration(text)
            if minutes is None and text.isdigit():
                minutes = int(text)
            if minutes:
                return minutes
            question = "Say a duration, like 30 minutes or an hour."
        raise Cancelled()

    def ask_priority(self) -> int:
        for _ in range(MAX_RETRIES + 1):
            text = self.ask("What priority: urgent, high, normal or low?")
            p, _ = P.extract_priority(text)
            if p is None and text.strip() in ("1", "2", "3", "4"):
                p = int(text)
            if p:
                return p
        raise Cancelled()

    def ask_time(self, question: str) -> time:
        for _ in range(MAX_RETRIES + 1):
            text = self.ask(question)
            t, _ = P.extract_time(text if text.startswith("at ") else "at " + text)
            if t:
                return t
            question = "Say a time, like 3 pm or 9 30."
        raise Cancelled()

    def ask_choice(self, question: str, options: dict) -> str:
        """options: spoken word -> value."""
        for _ in range(MAX_RETRIES + 1):
            text = self.ask(question, grammar=list(options))
            for word, value in options.items():
                if word in text.split() or text == word:
                    return value
            question = "Please say " + ", ".join(options) + "."
        raise Cancelled()

    # ----- one turn -----

    def handle(self, heard: Heard, context: str = R.MAIN) -> Optional[str]:
        """Run one spoken command. Returns the command name, or None.

        Shows what was heard, then what it's understood as, before acting.
        Low confidence or no clear meaning -> nothing is done. Every attempt
        goes to the voice log."""
        log = getattr(self.app, "voice_log", None)
        text = (heard.text or "").strip()
        log_id = log.add(text, heard.confidence, heard.audio, heard.device) if log else None

        def record(**fields):
            if log and log_id:
                log.update(log_id, **fields)

        self.show(f'Heard: "{text or "(nothing)"}"  ({heard.confidence:.0%} sure)')
        norm = P.normalize(text)
        if not norm:
            self.say("I didn't hear anything.")
            record(result="nothing heard")
            return None
        if P.is_cancel(norm):
            self.say("Cancelled.")
            record(result="cancelled")
            return None
        if heard.confidence < LOW_CONFIDENCE:
            self.say(f"I heard: {text}. I'm not sure I heard that right, so I did nothing. Please repeat or rephrase.")
            record(result="low confidence: no action", source="none")
            return None
        interp = None
        understanding = getattr(self.app, "understanding", None)
        if context == R.MAIN and understanding is not None:
            tasks, goals = self.app.voice_names() if hasattr(self.app, "voice_names") else ([], [])
            interp = understanding.interpret(text, tasks, goals)
            note = understanding.last_note
        else:
            found = R.match(norm, context)
            note = None
            if found:
                from .nlu import Interpretation
                interp = Interpretation(found[0].name, found[1], norm, "rules")
        if interp is None:
            self.say(f"Sorry, I didn't understand '{norm}'. You could say: {R.example_for(context)}.")
            record(result="not understood: no action", source="none", note=note)
            return None
        cmd = R.get(interp.command)
        self.show(f"→ {interp.plain}  [{'understood by the local model' if interp.source == 'model' else 'matched'}]")
        record(source=interp.source, command=cmd.name, interpreted=interp.plain, note=note)
        self.declined = False
        try:
            result = cmd.handler(self, interp.groups)
            record(acted=not self.declined, result=("declined: " if self.declined else "") + (self.last_said or ""))
            return result if isinstance(result, str) else cmd.name
        except Cancelled:
            self.say("Cancelled. Nothing was changed.")
            record(result="cancelled")
        except TaskError as e:
            self.say(f"I can't do that. {e}")
            record(result=f"refused: {e}")
        return None
