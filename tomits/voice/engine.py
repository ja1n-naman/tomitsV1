"""Offline speech adapters.

- Speech-to-text (v1.5.1): faster-whisper (see stt.py) on audio recorded and
  prepared by audio.py (mono 16 kHz, normalized, trimmed, end padding).
  No account, audio never leaves the computer. (v1.5 used Vosk; removed.)
- Text-to-speech: pyttsx3, which uses the Windows built-in voices (SAPI5).

If anything is missing (library, model, microphone) a VoiceUnavailable with a
plain reason is raised; the app shows it and keeps working with typed input.
"""

from __future__ import annotations

import difflib
import sys
from typing import Callable, Optional, Sequence

from .dialog import Heard


class VoiceUnavailable(Exception):
    """Voice can't be used right now; the message says why."""


GRAMMAR_SNAP = 0.6   # with a word list (alarm), snap to the closest phrase if at least this similar


class WhisperRecognizer:
    """Record from the mic, prepare the audio, transcribe with Whisper."""

    def __init__(self, size: str, device: str = "", hint: Optional[Callable[[], str]] = None):
        from . import audio as A
        from .stt import SttUnavailable, WhisperEngine
        try:
            import sounddevice  # noqa: F401
        except ImportError:
            raise VoiceUnavailable("sounddevice isn't installed. Run run.bat to install it.") from None
        except OSError as e:
            raise VoiceUnavailable(f"the audio library couldn't load ({e}).") from None
        self.device = int(device) if str(device).strip().isdigit() else None
        try:
            self.info = A.input_device(self.device)
            if self.info.channels < 1:
                raise ValueError
        except Exception:
            raise VoiceUnavailable("no microphone was found.") from None
        try:
            self.engine = WhisperEngine(size)
        except SttUnavailable as e:
            raise VoiceUnavailable(str(e)) from None
        self.hint = hint or (lambda: "")
        self._A = A

    def listen(self, grammar: Optional[Sequence[str]] = None, max_seconds: Optional[float] = None,
               start_timeout: Optional[float] = None) -> Heard:
        A = self._A
        raw, sr, info = A.record(self.device, max_seconds or A.MAX_RECORD_S)
        self.info = info
        x = A.prepare(raw, sr)
        if not len(x):
            return Heard("", 0.0, None, info.describe())
        hint = ". ".join(grammar) + "." if grammar else self.hint()
        heard = self.engine.transcribe(x, hint)
        heard.audio, heard.device = x, info.describe()
        if grammar and heard.text:
            from . import parse as P
            said = P.normalize(heard.text)
            best = max(grammar, key=lambda g: difflib.SequenceMatcher(None, said, g).ratio())
            if difflib.SequenceMatcher(None, said, best).ratio() >= GRAMMAR_SNAP:
                heard.text = best
        return heard


class WindowsSpeaker:
    """pyttsx3 -> SAPI5 on Windows. Any failure turns speech off (text still shows)."""

    def __init__(self):
        self.error: Optional[str] = None
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
        except Exception as e:
            self._engine = None
            self.error = f"spoken replies unavailable ({e}); showing text only."

    def say(self, text: str) -> None:
        if self._engine is None:
            return
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception as e:
            self.error = f"spoken replies stopped ({e}); showing text only."
            self._engine = None


class VoiceIO:
    """What the dialog talks to: prints everything, speaks if enabled, shows a
    listening indicator, pauses the alarm tone while listening, and falls back
    to typed answers if the mic is muted or fails."""

    def __init__(self, app, recognizer, speaker, console, typed_fallback):
        self.app, self.rec, self.speaker, self.console = app, recognizer, speaker, console
        self.typed_fallback = typed_fallback

    def say(self, text: str) -> None:
        self.console.print(f"[bold cyan]tomits:[/] {text}")
        if self.app.settings.spoken_replies and self.speaker is not None:
            self.speaker.say(text)
            if self.speaker.error:
                self.console.print(f"[dim red]{self.speaker.error}[/]")

    def listen(self, prompt: Optional[str] = None, grammar: Optional[Sequence[str]] = None) -> Heard:
        if prompt:
            self.say(prompt)
        if self.app.settings.muted:
            self.console.print("[yellow]Microphone is muted. Type your answer (or unmute with m).[/]")
            return self.typed_fallback(prompt)
        ringer = getattr(self.app, "ringer", None)
        if ringer is not None and ringer.is_ringing:
            ringer.quiet(True)   # the tone would drown out the mic
        info = getattr(self.rec, "info", None)
        if info is not None and not getattr(self, "_device_shown", False):
            self._device_shown = True
            self.console.print(f"[dim]Microphone: {info.describe()}[/]")
            if info.warning:
                self.console.print(f"[bold yellow]Warning:[/] {info.warning}")
        self.console.print("[bold white on red] ● LISTENING [/] [dim]speak now; it stops when you pause[/]")
        try:
            heard = self.rec.listen(grammar)
        except Exception as e:
            self.console.print(f"[red]The microphone failed ({e}). Type your answer instead.[/]")
            return self.typed_fallback(prompt)
        finally:
            if ringer is not None:
                ringer.quiet(False)
        shown = heard.text or "(nothing)"
        self.console.print(f"[dim]heard: {shown}  ({heard.confidence:.0%})[/]")
        return heard


    def show(self, text: str) -> None:
        self.console.print(f"[dim]{text}[/]" if text.startswith("Heard") else f"[bold]{text}[/]")


class TypedIO:
    """Same dialog, typed: used as the fallback when voice is unavailable."""

    def __init__(self, console, ask):
        self.console, self._ask = console, ask

    def say(self, text: str) -> None:
        self.console.print(f"[bold cyan]tomits:[/] {text}")

    def show(self, text: str) -> None:
        self.console.print(f"[dim]{text}[/]")

    def listen(self, prompt: Optional[str] = None, grammar=None) -> Heard:
        if prompt:
            self.say(prompt)
        return Heard(self._ask("you"), 1.0)


def keyboard_pressed() -> bool:
    """Non-blocking 'was a key pressed?' (Windows: msvcrt; elsewhere: select)."""
    try:
        if sys.platform == "win32":
            import msvcrt
            return msvcrt.kbhit()
        import select
        return bool(select.select([sys.stdin], [], [], 0)[0])
    except Exception:
        return False
