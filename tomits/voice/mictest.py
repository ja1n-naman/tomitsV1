"""Mic test (v1.5.1): record a short clip with a live input level, play it
back, show what Whisper heard and how it would be understood, so you can tell
whether a problem is the mic, the audio, or the recognition."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.text import Text

TEST_SECONDS = 5.0
QUIET_DB = -35.0     # loudest moment below this: the mic is too quiet / muted / wrong device


def _bar(db: float, width: int = 40) -> Text:
    filled = int(max(0.0, min(1.0, (db + 60) / 60)) * width)
    style = "green" if db < -12 else "yellow" if db < -3 else "red"
    t = Text("level ")
    t.append("█" * filled, style=style)
    t.append("·" * (width - filled), style="dim")
    t.append(f" {db:5.1f} dB")
    return t


def run_mic_test(settings, console: Console, save_as: Optional[Path] = None, understanding=None,
                 names=None, seconds: float = TEST_SECONDS) -> dict:
    """Returns a small report dict (also printed)."""
    from . import audio as A
    report = {}
    dev = int(settings.input_device) if str(settings.input_device).strip().isdigit() else None
    try:
        info = A.input_device(dev)
    except Exception as e:
        console.print(f"[red]No microphone available: {e}[/]")
        return {"error": str(e)}
    console.print(f"Input device: [bold]{info.describe()}[/]" + ("" if dev is not None else "  (Windows default)"))
    if info.warning:
        console.print(f"[bold yellow]Warning:[/] {info.warning}")
    console.print(f"Recording {seconds:g} seconds. [bold]Speak now.[/]")
    peak = [-120.0]
    with Live(_bar(-60), console=console, refresh_per_second=12, transient=True) as live:
        def on_level(db):
            peak[0] = max(peak[0], db)
            live.update(_bar(db))
        raw, sr, info = A.record(dev, fixed_seconds=seconds, on_level=on_level)
    report.update(device=info.describe(), samplerate=sr, peak_db=round(peak[0], 1), seconds=round(len(raw) / sr, 2))
    console.print(f"Loudest moment: {peak[0]:.1f} dB  (recorded at {sr} Hz)")
    if save_as:
        A.save_wav(save_as, A.resample(A.to_mono(raw), sr), A.SAMPLE_RATE)
        console.print(f"Saved the clip to {save_as}")
    console.print("Playing it back ...")
    try:
        A.play(raw, sr)
    except Exception as e:
        console.print(f"[red]Playback failed: {e}[/]")
    x = A.prepare(raw, sr)
    report["speech_seconds"] = round(len(x) / A.SAMPLE_RATE, 2)
    if peak[0] < QUIET_DB or not len(x):
        console.print("[bold red]Almost nothing was recorded.[/] The mic is muted, too far away, or the wrong "
                      "device is selected (see the device list with 'o' then 'i'). This is a mic / audio problem.")
        report["diagnosis"] = "mic or audio: too quiet"
        return report
    try:
        from .stt import SttUnavailable, WhisperEngine
        engine = WhisperEngine(settings.stt_model)
    except SttUnavailable as e:
        console.print(f"[yellow]Can't transcribe: {e}[/] The recording itself worked; listen to the playback.")
        report["diagnosis"] = "recognizer not set up"
        return report
    heard = engine.transcribe(x)
    report.update(transcript=heard.text, confidence=round(heard.confidence, 2))
    console.print(f"Whisper ({settings.stt_model}) heard: [bold]\"{heard.text}\"[/]  ({heard.confidence:.0%} sure)")
    if understanding is not None and heard.text:
        tasks, goals = names or ([], [])
        interp = understanding.interpret(heard.text, tasks, goals)
        report["understood"] = interp.plain if interp else None
        console.print(f"Would be understood as: [bold]{interp.plain}[/]" if interp
                      else f"Not understood as a command ({understanding.last_note or 'no match'}).")
    if heard.confidence < 0.6:
        report["diagnosis"] = "recognition: low confidence"
        console.print("[yellow]The playback sounded clear but confidence is low? Then it's the recognition: try a "
                      "larger Whisper model (voice_benchmark.bat compares them). Sounded muffled or choppy? Then "
                      "it's the mic / audio (see the warning above about Bluetooth call mode).[/]")
    else:
        report["diagnosis"] = "ok"
    return report
