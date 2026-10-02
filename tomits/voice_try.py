"""Run a .wav file (or a typed sentence) through the whole voice pipeline and
print what would happen, WITHOUT executing anything.

    python -m tomits.voice_try tests/audio/delete_all_everywhere.wav
    python -m tomits.voice_try --text "push my workout to tomorrow"
    options: --model small   Whisper size      --no-llm   rules only
"""

from __future__ import annotations

import sys
import time
from datetime import date

from rich.console import Console


def explain(text: str, confidence: float, understanding, console: Console, session_factory, today: date) -> dict:
    from .voice import parse as P
    from .voice import registry as R
    from .voice.dialog import LOW_CONFIDENCE
    from .voice.specs import SPECS
    out = {"transcript": text, "confidence": round(confidence, 3)}
    console.print(f"Transcript:  [bold]\"{text}\"[/]   confidence {confidence:.0%}")
    if confidence < LOW_CONFIDENCE:
        console.print(f"Would do:    nothing (confidence below {LOW_CONFIDENCE:.0%}); asks you to repeat.")
        out["would"] = "nothing: low confidence"
        return out
    with session_factory() as s:
        from . import tracking as tr
        from .models import Task, TaskStatus
        tasks = sorted({t.title for t in s.query(Task).filter(Task.status == TaskStatus.PENDING.value)})
        goals = sorted({g.title for g in tr.open_goals(s, today)})
        t0 = time.perf_counter()
        interp = understanding.interpret(text, tasks, goals)
        out["understand_seconds"] = round(time.perf_counter() - t0, 2)
        if interp is None:
            console.print(f"Understood:  nothing ({understanding.last_note or 'no rule matched'})")
            console.print("Would do:    nothing; says it didn't understand and gives an example.")
            out["would"] = "nothing: not understood"
            return out
        out.update(command=interp.command, source=interp.source, interpreted=interp.plain)
        console.print(f"Understood:  [bold]{interp.plain}[/]   command {interp.command}, by {interp.source}"
                      f" ({out['understand_seconds']} s)")
        fields = {k: v for k, v in interp.groups.items() if v}
        if fields:
            console.print(f"Fields:      {fields}")
        for key in ("name", "goal", "other", "parent"):
            said = interp.groups.get(key)
            if not said or said in ("it", "this"):
                continue
            pool = tasks if key in ("name", "other") else goals
            matches = P.fuzzy_matches(said, pool, key=lambda x: x)
            if interp.command in ("goal_done", "edit_goal", "delete_goal"):
                matches = P.fuzzy_matches(said, goals, key=lambda x: x)
            pick = P.pick_unique(matches)
            desc = (f"'{pick}'" if pick else ("ask you to pick: " + ", ".join(m for _, m in matches)) if matches
                    else "no match: would say it can't find it")
            console.print(f"Name '{said}': {desc}")
        cmd = R.get(interp.command)
        spec = SPECS.get(interp.command)
        if interp.command in ("delete_all", "clear_day"):
            from . import services as svc
            scope = {"tasks": "tasks", "goals": "goals"}.get(interp.groups.get("what") or "", "tasks and goals")
            day = P.extract_date(interp.groups.get("when") or "", today)[0] if interp.command == "clear_day" else None
            try:
                plan = svc.bulk_delete_plan(s, "day" if interp.command == "clear_day" else scope, day=day, today=today)
                console.print(f"Read-back:   {plan.describe()}")
            except Exception as e:
                console.print(f"Read-back:   refused: {e}")
            s.rollback()
        needs_yes = cmd.risky or (spec and spec.destructive)
        out["needs_yes"] = bool(needs_yes)
        console.print("Would do:    " + ("read back and wait for a spoken yes" if needs_yes else "run it and say what it did")
                      + ", through the normal rules (nothing was executed now).")
        out["would"] = "confirm" if needs_yes else "run"
    return out


def main(argv=None) -> int:
    from .db import default_db_path, make_session_factory
    from .settings import load_settings, settings_path
    from .voice import commands  # noqa: F401
    from .voice.nlu import OllamaBackend, Understanding
    argv = list(sys.argv[1:] if argv is None else argv)
    console = Console()
    settings = load_settings(settings_path(default_db_path()))
    model = argv[argv.index("--model") + 1] if "--model" in argv else settings.stt_model
    understanding = Understanding(None if "--no-llm" in argv or not settings.llm_enabled
                                  else OllamaBackend(settings.llm_model))
    Session = make_session_factory(default_db_path())
    if "--text" in argv:
        text, conf = argv[argv.index("--text") + 1], 1.0
    else:
        paths = [a for a in argv if a.lower().endswith(".wav")]
        if not paths:
            console.print(__doc__)
            return 2
        from .voice import audio as A
        from .voice.stt import SttUnavailable, WhisperEngine
        try:
            engine = WhisperEngine(model)
        except SttUnavailable as e:
            console.print(f"[red]{e}[/]")
            return 1
        raw, sr = A.load_wav(paths[0])
        t0 = time.perf_counter()
        heard = engine.transcribe(A.prepare(raw, sr))
        console.print(f"Whisper {model}: {time.perf_counter() - t0:.2f} s")
        text, conf = heard.text, heard.confidence
    explain(text, conf, understanding, console, Session, date.today())
    return 0


if __name__ == "__main__":
    sys.exit(main())
