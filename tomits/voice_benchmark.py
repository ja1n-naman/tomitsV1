"""Benchmark Whisper model sizes on your own recorded clips.

    python -m tomits.voice_benchmark                     sizes: base, small, medium
    python -m tomits.voice_benchmark tiny small large-v3-turbo
    options: --llm   also check understanding with the local language model

Reads tests/audio/clips.csv (file, expected text, expected command). For each
size it measures: word error rate (WER) against the expected text, how often
the command is understood correctly, and seconds per clip. Recommends the most
accurate size whose median time is within MAX_SECONDS_PER_COMMAND, writes
tests/audio/benchmark_results.csv, and can save the choice in settings.
"""

from __future__ import annotations

import csv
import statistics
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

MAX_SECONDS_PER_COMMAND = 3.0      # "a result in a reasonable time"
DEFAULT_SIZES = ["base", "small", "medium"]


def wer(expected: str, got: str) -> float:
    from .voice.parse import normalize
    a, b = normalize(expected).split(), normalize(got).split()
    if not a:
        return 0.0 if not b else 1.0
    d = list(range(len(b) + 1))
    for i, wa in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, wb in enumerate(b, 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (wa != wb))
            prev, d[j] = d[j], cur
    return d[len(b)] / len(a)


def load_clips(folder: Path):
    rows = []
    with open(folder / "clips.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            path = folder / r["file"].strip()
            if path.exists():
                rows.append((path, r["expected_text"].strip(), r.get("expected_command", "").strip()))
    return rows


def main(argv=None) -> int:
    from .db import PROJECT_ROOT, default_db_path
    from .settings import load_settings, save_settings, settings_path
    from .voice import audio as A
    from .voice import commands  # noqa: F401
    from .voice.nlu import OllamaBackend, Understanding
    from .voice.stt import SttUnavailable, WhisperEngine, model_label
    from .voice_setup import setup_whisper
    argv = list(sys.argv[1:] if argv is None else argv)
    console = Console()
    folder = PROJECT_ROOT / "tests" / "audio"
    clips = load_clips(folder)
    if not clips:
        console.print("[red]No recorded clips yet.[/] Record them first (see tests/audio/README.md), for example:\n"
                      "  voice_mictest.bat --record delete_all_everywhere")
        return 1
    sizes = [a for a in argv if not a.startswith("--")] or DEFAULT_SIZES
    sp = settings_path(default_db_path())
    settings = load_settings(sp)
    understanding = Understanding(OllamaBackend(settings.llm_model) if "--llm" in argv else None)
    audio = [(p, A.prepare(*A.load_wav(p)), exp, cmd) for p, exp, cmd in clips]
    console.print(f"{len(audio)} clips, sizes: {', '.join(sizes)}")
    results, detail = [], []
    for size in sizes:
        try:
            engine = WhisperEngine(size)
        except SttUnavailable:
            if not setup_whisper(size):
                console.print(f"[yellow]Skipping {size}.[/]")
                continue
            engine = WhisperEngine(size)
        engine.transcribe(audio[0][1])  # warm-up
        errs, secs, ok_cmd = [], [], 0
        for path, x, expected, cmd in audio:
            t0 = time.perf_counter()
            heard = engine.transcribe(x)
            secs.append(time.perf_counter() - t0)
            e = wer(expected, heard.text)
            errs.append(e)
            interp = understanding.interpret(heard.text) if heard.text else None
            got_cmd = interp.command if interp else "none"
            ok_cmd += (got_cmd == cmd) if cmd else 0
            detail.append((size, path.name, expected, heard.text, f"{heard.confidence:.2f}", f"{e:.2f}", got_cmd, cmd,
                           f"{secs[-1]:.2f}"))
        with_cmd = sum(1 for *_, c in audio if c)
        results.append({"size": size, "wer": statistics.mean(errs), "cmd_acc": ok_cmd / with_cmd if with_cmd else None,
                        "median_s": statistics.median(secs), "max_s": max(secs)})
    if not results:
        return 1
    table = Table(title="Whisper benchmark on your clips")
    for col in ("Model", "Word error rate", "Commands understood", "Median s", "Slowest s"):
        table.add_column(col)
    for r in results:
        table.add_row(model_label(r["size"]), f"{r['wer']:.1%}", "-" if r["cmd_acc"] is None else f"{r['cmd_acc']:.0%}",
                      f"{r['median_s']:.2f}", f"{r['max_s']:.2f}")
    console.print(table)
    with open(folder / "benchmark_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["model", "file", "expected", "heard", "confidence", "wer", "command", "expected_command", "seconds"])
        w.writerows(detail)
    fast = [r for r in results if r["median_s"] <= MAX_SECONDS_PER_COMMAND] or results
    best = min(fast, key=lambda r: (r["wer"], -(r["cmd_acc"] or 0), r["median_s"]))
    console.print(f"Recommended: [bold]{best['size']}[/] (lowest error within {MAX_SECONDS_PER_COMMAND:g} s per command). "
                  f"Details: tests/audio/benchmark_results.csv")
    if best["size"] != settings.stt_model and input(f"Use {best['size']} from now on? [y/N] ").strip().lower() == "y":
        settings.stt_model = best["size"]
        save_settings(sp, settings)
        console.print("Saved in settings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
