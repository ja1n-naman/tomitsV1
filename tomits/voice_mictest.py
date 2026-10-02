"""Mic test: live level, playback, what Whisper heard.

    python -m tomits.voice_mictest                 test with the chosen mic
    python -m tomits.voice_mictest --list          list microphones
    python -m tomits.voice_mictest --device 3      use device 3 (saved in settings)
    python -m tomits.voice_mictest --record NAME   record a test clip into tests/audio/NAME.wav
"""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console


def main(argv=None) -> int:
    from .db import PROJECT_ROOT, default_db_path
    from .settings import load_settings, save_settings, settings_path
    from .voice import audio as A
    argv = list(sys.argv[1:] if argv is None else argv)
    console = Console()
    sp = settings_path(default_db_path())
    settings = load_settings(sp)
    if "--list" in argv or "--device" in argv:
        try:
            devices = A.list_input_devices()
        except Exception as e:
            console.print(f"[red]Can't list microphones: {e}[/]")
            return 1
        for d in devices:
            mark = "  <- in use" if str(d.index) == settings.input_device else ""
            console.print(f"{d.index:>3}  {d.describe()}{mark}" + (f"\n     [yellow]{d.warning}[/]" if d.warning else ""))
        if "--device" in argv:
            n = argv[argv.index("--device") + 1]
            if not any(str(d.index) == n for d in devices):
                console.print(f"[red]No input device {n}.[/]")
                return 1
            settings.input_device = n
            save_settings(sp, settings)
            console.print(f"[green]Now using device {n}.[/]")
        if "--list" in argv:
            return 0
    save_as = None
    if "--record" in argv:
        name = argv[argv.index("--record") + 1]
        save_as = PROJECT_ROOT / "tests" / "audio" / (name if name.endswith(".wav") else name + ".wav")
    from .voice import commands  # noqa: F401
    from .voice.mictest import run_mic_test
    from .voice.nlu import OllamaBackend, Understanding
    understanding = Understanding(OllamaBackend(settings.llm_model) if settings.llm_enabled else None)
    report = run_mic_test(settings, console, save_as=save_as, understanding=understanding,
                          seconds=8.0 if save_as else 5.0)
    return 0 if report.get("diagnosis") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
