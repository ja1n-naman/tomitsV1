"""v1.5.1: local-model understanding (validated against the registry), fallback,
no action on low confidence / garbled input, destructive confirmations, name
matching, voice log, audio handling. All from text; no microphone or model."""

import io
import json
import sqlite3
import time as _time
from datetime import date, datetime, time, timedelta

import numpy as np
import pytest
from rich.console import Console

from tomits import services as svc
from tomits import tracking as tr
from tomits import ui, ui_tracking
from tomits.errors import TaskError
from tomits.models import Placement, Task, TaskStatus
from tomits.periods import PeriodKind
from tomits.voice import audio as A
from tomits.voice import nlu as N
from tomits.voice import parse as P
from tomits.voice import registry as R
from tomits.voice.dialog import LOW_CONFIDENCE, Heard
from tomits.voice.specs import SPECS, free_commands
from tomits.voice.voicelog import VoiceLog

TODAY = date(2026, 10, 5)
NOW = datetime(2026, 10, 5, 8, 30)
GARBLED = "they need all the tasks and bought from him that he did"


# ---------- fakes ----------

class FakeBackend:
    name = "fake"

    def __init__(self, answer=None, delay=0.0, error=None, unavailable=None):
        self.answer, self.delay, self.error, self.unavailable = answer, delay, error, unavailable
        self.calls = []

    def available(self):
        return self.unavailable

    def complete(self, prompt, schema, timeout):
        self.calls.append(prompt)
        if self.delay:
            _time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.answer if isinstance(self.answer, str) else json.dumps(self.answer)


def answer(command, confidence=0.9, **fields):
    return {"command": command, "fields": fields, "confidence": confidence}


class ScriptedIO:
    def __init__(self, utterances):
        self.queue = [u if isinstance(u, tuple) else (u, 1.0) for u in utterances]
        self.said, self.prompts, self.shown, self.events = [], [], [], []

    def say(self, text):
        self.said.append(text)
        self.events.append(("say", text))

    def show(self, text):
        self.shown.append(text)
        self.events.append(("show", text))

    def listen(self, prompt=None, grammar=None):
        if prompt:
            self.said.append(prompt)
            self.prompts.append(prompt)
            self.events.append(("say", prompt))
        text, conf = self.queue.pop(0)
        return Heard(text, conf)


class Quiet:
    def notify(self, *a, **k):
        pass


@pytest.fixture
def app(db_file, monkeypatch):
    for mod in (ui, ui_tracking):
        monkeypatch.setattr(mod, "console", Console(file=io.StringIO(), width=160))
    monkeypatch.setattr("tomits.ui_common.console", Console(file=io.StringIO()))
    a = ui.App(db_file, notifier=Quiet(), clock=lambda: NOW)
    a.understanding = N.Understanding(None)  # model off unless a test sets one
    return a


def talk(app, *utterances):
    io_ = ScriptedIO(utterances)
    app.voice_turn(io_)
    assert io_.queue == [], io_.queue
    return io_


def add(app, title, minutes=60, start=None, day=TODAY, placement=None, goal_id=None):
    with app.Session() as s:
        t = svc.add_task(s, title, minutes, goal_id=goal_id, planned_for=day, start_time=start, today=TODAY)
        if placement:
            t.placement = placement
            s.commit()
        return t.id


def titles(app, day=TODAY):
    with app.Session() as s:
        return [(t.title, t.status) for t in svc.tasks_for_day(s, day)]


# ======================= validation against the registry =======================

def test_every_free_command_has_a_spec_and_every_template_maps_back():
    samples = {"duration": "45 minutes", "time": "3 pm", "date": "tomorrow", "priority": "high", "title": "read",
               "name": "report", "where": "after", "other": "email", "new_title": "x", "goal": "fitness",
               "period": "this week", "direction": "next", "parent": "run 40 km", "target": "50", "amount": "10",
               "unit": "pages", "when": "today", "text": "no phone", "status": "made", "new_text": "y", "what": "tasks",
               "start": "8 am", "end": "10 pm", "minutes": "10", "phrase": "hey there", "number": "2", "what2": "x",
               "layout": "board", "theme": "dark"}
    assert {c.name for c in free_commands()} <= set(SPECS)
    for name, spec in SPECS.items():
        for t in spec.templates:
            vals = {f: samples.get(f, "x") for f in spec.fields}
            vals.update({"kind": "week" if name == "go_period" else "weekly",
                         "state": "done" if name == "goal_done" else "on"})
            one = spec.render({k: v for k, v in vals.items() if "{" + k + "}" in t}) if "{" in t else t
            found = R.match(P.normalize(one))
            assert found and found[0].name == name, (name, one, found and found[0].name)


def test_valid_model_output_is_accepted():
    i = N.validate(json.dumps(answer("mark_done", name="reading")), "i wrapped up the reading bit")
    assert (i.command, i.groups["name"], i.source, i.canonical) == ("mark_done", "reading", "model", "mark reading done")


@pytest.mark.parametrize("raw,why", [
    ("not json", "not JSON"),
    (json.dumps([1, 2]), "not an object"),
    (json.dumps(answer("none")), "no command"),
    (json.dumps(answer("format_disk")), "unknown command"),
    (json.dumps(answer("mark_done", name="x", shell="rm -rf")), "unexpected field"),
    (json.dumps(answer("move_task")), "missing required field"),
    (json.dumps(answer("add_task", title="x", priority="super")), "must be one of"),
    (json.dumps(answer("mark_done", confidence=0.3, name="x")), "confidence too low"),
    (json.dumps(answer("mark_done", name="x" * 200)), "too long"),
    (json.dumps({"command": "mark_done", "fields": "name=x", "confidence": 0.9}), "fields must be an object"),
    (json.dumps(answer("alarm_dismiss")), "unknown command"),     # prompt answers aren't free commands
])
def test_invalid_model_output_is_rejected(raw, why):
    with pytest.raises(N.Invalid, match=why):
        N.validate(raw, "whatever was said")


def test_destructive_command_needs_a_delete_word_in_what_was_said():
    raw = json.dumps(answer("delete_all", what="tasks and goals"))
    with pytest.raises(N.Invalid, match="delete-type word"):
        N.validate(raw, GARBLED)
    assert N.validate(raw, "please wipe all my tasks and goals").command == "delete_all"


def test_prompt_lists_only_registry_commands_and_current_names():
    prompt = N.build_prompt("x", ["morning workout"], ["run 40 km"])
    assert "morning workout" in prompt and "run 40 km" in prompt
    assert "alarm_dismiss" not in prompt and "- delete_all:" in prompt
    assert set(N.build_schema()["properties"]["command"]["enum"]) == set(SPECS) | {"none"}


# ======================= rules first, model fallback, model fallback to rules =======================

def test_rules_answer_first_without_calling_the_model():
    b = FakeBackend(answer("quit"))
    i = N.Understanding(b).interpret("plan my day")
    assert i.command == "plan_day" and i.source == "rules" and b.calls == []


@pytest.mark.parametrize("backend,note", [
    (None, "local model off"),
    (FakeBackend(unavailable="Ollama isn't running"), "Ollama isn't running"),
    (FakeBackend(error=RuntimeError("boom")), "local model error: boom"),
    (FakeBackend("{broken"), "model answer rejected: not JSON"),
    (FakeBackend(answer("none", 0.9)), "model answer rejected: no command"),
])
def test_model_missing_or_broken_falls_back(backend, note):
    u = N.Understanding(backend)
    assert u.interpret("i wrapped up the reading bit") is None
    assert u.last_note.startswith(note)


def test_model_timeout_falls_back_quickly():
    u = N.Understanding(FakeBackend(answer("mark_done", name="x"), delay=2.0), timeout=0.2)
    t0 = _time.monotonic()
    assert u.interpret("i wrapped up the reading bit") is None
    assert _time.monotonic() - t0 < 1.0 and "longer than 0.2 s" in u.last_note


def test_timeout_constant_exists():
    assert N.LLM_TIMEOUT_SECONDS > 0 and N.LLM_MIN_CONFIDENCE == 0.6


@pytest.mark.parametrize("said,command", [
    ("I'm done with reading", "mark_done"), ("push my workout to tomorrow", "move_task"),
    ("what have I got left today", "my_day"), ("what's left to do", "my_day"),
    ("delete all the tasks and goals from everywhere", "delete_all"), ("clear tomorrow", "clear_day"),
    ("postpone the report till 5 pm", "move_task"), ("show the voice log", "show_voice_log"),
    ("test my mic", "mic_test"), ("list my microphones", "input_device"),
])
def test_rephrasings_work_with_the_model_off(said, command):
    i = N.Understanding(None).interpret(said)
    assert i is not None and i.command == command


# ======================= in the app: show, confirm, no action =======================

def test_heard_text_and_interpretation_shown_before_acting(app):
    add(app, "reading", start=time(8, 0))
    app.understanding = N.Understanding(FakeBackend(answer("mark_done", name="reading")))
    io_ = talk(app, "i wrapped up the reading bit")
    kinds = [k for k, _ in io_.events]
    assert io_.shown[0] == 'Heard: "i wrapped up the reading bit"  (100% sure)'
    assert io_.shown[1].startswith("→ Mark reading done  [understood by the local model]")
    assert kinds.index("show") < kinds.index("say")
    assert titles(app) == [("reading", "done")]


def test_garbled_transcript_does_nothing_even_if_model_guesses_delete(app):
    add(app, "report")
    app.understanding = N.Understanding(FakeBackend(answer("delete_all", 0.95, what="tasks and goals")))
    io_ = talk(app, GARBLED)
    assert io_.said[-1].startswith(f"Sorry, I didn't understand '{GARBLED}'.")
    assert titles(app) == [("report", "pending")]
    row = app.voice_log.recent(1)[0]
    assert (row.acted, row.command, row.result) == (False, None, "not understood: no action")
    assert "delete-type word" in row.note


def test_garbled_transcript_with_model_off_does_nothing(app):
    add(app, "report")
    io_ = talk(app, GARBLED)
    assert "didn't understand" in io_.said[-1] and titles(app) == [("report", "pending")]


def test_low_confidence_never_acts_even_for_clear_commands(app):
    add(app, "report", start=time(8, 0))
    io_ = talk(app, ("mark report done", LOW_CONFIDENCE - 0.05))
    assert "so I did nothing. Please repeat or rephrase." in io_.said[-1]
    assert titles(app) == [("report", "pending")]
    assert app.voice_log.recent(1)[0].result == "low confidence: no action"


def _mixed_data(app):
    """2 pending tasks, 1 failed record, 1 done task, goals incl. locked / with logs."""
    add(app, "report")
    add(app, "email", day=TODAY + timedelta(days=1))
    f = add(app, "gym")
    d = add(app, "read")
    with app.Session() as s:
        svc.fail_task(s, f, "sick")
        svc.complete_task(s, d, today=TODAY)
        tr.create_goal(s, PeriodKind.MONTH, TODAY, "ship tomits", today=TODAY)
        g = tr.create_goal(s, PeriodKind.WEEK, TODAY, "read", 50, "pages", today=TODAY)
        tr.log_progress(s, g.id, 5, today=TODAY)
        tr.create_goal(s, PeriodKind.DAY, TODAY - timedelta(days=1), "old", today=TODAY - timedelta(days=1))


def test_delete_all_reads_back_counts_and_needs_yes(app):
    _mixed_data(app)
    io_ = talk(app, "delete all the tasks and goals from everywhere", "no")
    readback = io_.prompts[0]
    assert readback.startswith("This will permanently delete 2 pending tasks and 1 goal.")
    assert "1 failed or skipped records (their reasons are permanent)" in readback
    assert "1 goals in ended periods (read-only)" in readback and "1 goals with logged progress" in readback
    assert "This can't be undone." in readback and readback.endswith("Say yes or no.")
    assert io_.said[-1] == "Nothing was deleted." and len(titles(app)) == 3
    talk(app, "delete all the tasks and goals from everywhere", "yes")
    with app.Session() as s:
        left = {t.title: t.status for t in s.query(Task).all()}
        goals = {g.title for g in s.query(tr.Goal).all()}
    assert left == {"gym": "failed", "read": "done"}           # failed record + reason kept
    assert goals == {"read", "old"}                              # logged / locked goals kept
    assert app.voice_log.recent(1)[0].acted is True


def test_delete_all_anything_but_yes_is_a_no(app):
    add(app, "report")
    talk(app, "delete all the tasks", "maybe", "hmm", "later")
    assert titles(app) == [("report", "pending")]


def test_clear_day_confirmation_and_past_day_refused(app):
    add(app, "a", day=TODAY + timedelta(days=1))
    add(app, "b", day=TODAY + timedelta(days=1))
    io_ = talk(app, "clear tomorrow", "yes")
    assert io_.prompts[0].startswith("This will permanently delete 2 pending tasks on Tuesday 06 October.")
    assert titles(app, TODAY + timedelta(days=1)) == []
    io_ = talk(app, "clear yesterday")
    assert "past days are never changed" in io_.said[-1]


def test_typed_bulk_delete_needs_the_word_delete(app, monkeypatch):
    add(app, "report")
    answers = iter(["t", "yes"])
    monkeypatch.setattr(ui.Prompt, "ask", classmethod(lambda cls, *a, **k: next(answers)))
    app.bulk_delete_typed()
    assert titles(app) == [("report", "pending")]
    answers = iter(["t", "DELETE"])
    monkeypatch.setattr(ui.Prompt, "ask", classmethod(lambda cls, *a, **k: next(answers)))
    app.bulk_delete_typed()
    assert titles(app) == []


# ======================= names from existing data =======================

def test_model_names_are_matched_against_existing_tasks(app):
    add(app, "morning workout", start=time(18, 0), placement=Placement.AUTO.value)
    app.understanding = N.Understanding(FakeBackend(answer("move_task", name="workout", date="tomorrow")))
    b = app.understanding.backend
    io_ = talk(app, "shove the workout thing to tomorrow")
    assert "morning workout" in b.calls[0]                     # current names were given to the model
    assert titles(app, TODAY + timedelta(days=1)) == [("morning workout", "pending")]
    assert io_.said[-1].startswith("Moved morning workout to tomorrow, no time yet.")


def test_push_to_tomorrow_by_rules(app):
    add(app, "workout", start=time(18, 0))
    talk(app, "push my workout to tomorrow at 7 am")
    with app.Session() as s:
        t = svc.tasks_for_day(s, TODAY + timedelta(days=1))[0]
        assert (t.title, t.start_time, t.placement) == ("workout", time(7, 0), "fixed")


def test_ambiguous_model_name_asks_to_pick(app):
    add(app, "read chapter one", start=time(9, 0))
    add(app, "read chapter two", start=time(10, 0))
    app.understanding = N.Understanding(FakeBackend(answer("mark_done", name="read chapter")))
    io_ = talk(app, "wrapped up the chapter reading", "2")
    assert any(p.startswith("I found 2.") for p in io_.prompts)
    assert ("read chapter two", "done") in titles(app)


def test_unknown_name_is_refused_not_guessed(app):
    add(app, "report")
    io_ = talk(app, "push my workout to tomorrow")
    assert io_.said[-1] == "I can't do that. I couldn't find a task called 'my workout'."


def test_model_goal_names_match_existing_goals(app):
    with app.Session() as s:
        tr.create_goal(s, PeriodKind.DAY, TODAY, "run 5 km", 5, "km", today=TODAY)
    app.understanding = N.Understanding(FakeBackend(answer("log_progress", amount="3", unit="km", goal="running")))
    io_ = talk(app, "put down three kilometres for my running")
    assert io_.said[-1].startswith("Logged 3 km. run 5 km 3/5 km")


def test_model_cannot_bypass_rules_overlap(app):
    add(app, "meeting", start=time(15, 0))
    app.understanding = N.Understanding(FakeBackend(answer("add_task", title="call", duration="30 minutes",
                                                           time="3 30 pm", priority="normal")))
    io_ = talk(app, "slot in a call around half three")
    assert "overlaps task" in io_.said[-1] and [t for t, _ in titles(app)] == ["meeting"]


def test_model_cannot_bypass_locked_period(app):
    app.understanding = N.Understanding(FakeBackend(answer("add_sacrifice", text="no phone", period="today")))
    # 'today' is allowed; a locked period isn't in the allowed values at all:
    with pytest.raises(N.Invalid):
        N.validate(json.dumps(answer("add_sacrifice", text="x", period="last week")), "x")
    io_ = talk(app, "add a sacrifice no phone for yesterday")
    assert io_.said[-1].endswith("its sacrifices are read-only.")


# ======================= voice log =======================

def test_log_format_and_audio_retention(tmp_path):
    log = VoiceLog(tmp_path / "voice_log.db", keep=3)
    ids = [log.add(f"cmd {i}", 0.9, audio=np.zeros(1600, dtype=np.float32), device="Mic (16000 Hz)") for i in range(5)]
    log.update(ids[-1], source="rules", command="plan_day", interpreted="Plan my day", acted=True, result="Planned.")
    with sqlite3.connect(tmp_path / "voice_log.db") as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(voice_log)")]
        assert cols == ["id", "ts", "transcript", "confidence", "source", "command", "interpreted", "acted", "result",
                        "audio_file", "device", "note"]
        assert c.execute("SELECT COUNT(*) FROM voice_log").fetchone()[0] == 5      # text kept
    rows = log.recent(5)
    assert (rows[0].transcript, rows[0].command, rows[0].acted, rows[0].result) == ("cmd 4", "plan_day", True, "Planned.")
    with_audio = [r for r in rows if r.audio_file]
    assert len(with_audio) == 3 and len(list((tmp_path / "voice_audio").glob("*.wav"))) == 3
    assert all("audio removed" in (r.note or "") for r in rows if not r.audio_file)


def test_audio_keep_default():
    from tomits.voice import voicelog
    assert voicelog.AUDIO_KEEP == 50


def test_every_attempt_is_logged(app):
    add(app, "report", start=time(8, 0))
    talk(app, "mark report done")
    talk(app, "make me a sandwich")
    talk(app, ("plan my day", 0.2))
    rows = app.voice_log.recent(3)
    assert [(r.transcript, r.acted) for r in rows] == [("plan my day", False), ("make me a sandwich", False),
                                                      ("mark report done", True)]
    assert rows[2].interpreted == "Mark report done" and rows[2].source == "rules"


def test_show_voice_log_by_voice(app):
    talk(app, "what's next")
    io_ = talk(app, "show the voice log")
    assert io_.said[-1].startswith("Last commands: 'show the voice log'") or "'what's next'" in io_.said[-1]


# ======================= dry-run test script =======================

def test_voice_try_never_executes(app, db_file):
    from tomits.voice_try import explain
    _mixed_data(app)
    before = titles(app) + titles(app, TODAY + timedelta(days=1))
    out = explain("delete all the tasks and goals from everywhere", 0.9, N.Understanding(None),
                  Console(file=io.StringIO()), app.Session, TODAY)
    assert out["command"] == "delete_all" and out["would"] == "confirm" and out["needs_yes"]
    assert titles(app) + titles(app, TODAY + timedelta(days=1)) == before
    out = explain(GARBLED, 0.9, N.Understanding(None), Console(file=io.StringIO()), app.Session, TODAY)
    assert out["would"] == "nothing: not understood"
    out = explain("plan my day", 0.3, N.Understanding(None), Console(file=io.StringIO()), app.Session, TODAY)
    assert out["would"] == "nothing: low confidence"


def test_benchmark_word_error_rate():
    from tomits.voice_benchmark import wer
    assert wer("delete all the tasks", "delete all the tasks") == 0
    assert wer("delete all the tasks and goals", "they need all the tasks and bought") == pytest.approx(3 / 6)


# ======================= audio handling =======================

def test_prepare_mono_16k_normalized_trimmed_padded():
    sr = 44100
    t = np.linspace(0, 1, sr, endpoint=False)
    tone = 0.05 * np.sin(2 * np.pi * 300 * t)
    x = np.stack([np.concatenate([np.zeros(sr), tone, np.zeros(sr)])] * 2, axis=1)   # stereo, silence around
    y = A.prepare(x, sr)
    assert y.ndim == 1 and abs(np.max(np.abs(y)) - A.TARGET_PEAK) < 0.01
    assert abs(len(y) / A.SAMPLE_RATE - (1 + 2 * A.KEEP_MARGIN_S + A.END_PADDING_S)) < 0.05
    assert np.all(y[-int(A.SAMPLE_RATE * A.END_PADDING_S):] == 0)                   # padding at the end


def test_prepare_silence_gives_nothing():
    assert len(A.prepare(np.zeros(16000), 16000)) == 0


def test_wav_round_trip(tmp_path):
    x = (0.5 * np.sin(np.linspace(0, 100, 16000))).astype(np.float32)
    A.save_wav(tmp_path / "a.wav", x)
    y, sr = A.load_wav(tmp_path / "a.wav")
    assert sr == 16000 and np.max(np.abs(x - y)) < 1e-3


def test_low_sample_rate_device_warning():
    bt = A.DeviceInfo(3, "Headset (Boat Airdopes Hands-Free)", 8000, 1)
    assert "8000 Hz" in bt.warning and "call mode" in bt.warning
    assert A.DeviceInfo(1, "Microphone Array (Realtek)", 48000, 2).warning is None
    assert "hands-free" in A.DeviceInfo(2, "Earbuds Hands-Free AG Audio", 16000, 1).warning


def test_mic_test_report_with_fake_audio(monkeypatch, tmp_path):
    from tomits.voice import mictest, stt
    from tomits.settings import Settings
    sr = 16000
    t = np.linspace(0, 1, sr, endpoint=False)
    clip = np.concatenate([np.zeros(sr // 2), 0.3 * np.sin(2 * np.pi * 200 * t), np.zeros(sr // 2)]).astype(np.float32)
    monkeypatch.setattr(A, "input_device", lambda dev=None: A.DeviceInfo(0, "Test mic", 16000, 1))
    monkeypatch.setattr(A, "record", lambda dev, fixed_seconds=None, on_level=None, **k: (on_level(-10.0), (clip, sr,
                        A.DeviceInfo(0, "Test mic", 16000, 1)))[1])
    monkeypatch.setattr(A, "play", lambda x, sr: None)

    class Eng:
        def __init__(self, size):
            pass

        def transcribe(self, x, hint=""):
            return Heard("plan my day", 0.93)

    monkeypatch.setattr(stt, "WhisperEngine", Eng)
    rep = mictest.run_mic_test(Settings(), Console(file=io.StringIO()), save_as=tmp_path / "clip.wav",
                               understanding=N.Understanding(None))
    assert (rep["transcript"], rep["understood"], rep["diagnosis"]) == ("plan my day", "Plan my day", "ok")
    assert (tmp_path / "clip.wav").exists() and rep["peak_db"] == -10.0


def test_move_to_day_rules(app):
    a = add(app, "workout", start=time(18, 0))
    add(app, "dinner", start=time(18, 0), day=TODAY + timedelta(days=1))
    with app.Session() as s:
        with pytest.raises(TaskError, match="past"):
            svc.move_to_day(s, a, TODAY - timedelta(days=1), today=TODAY)
        with pytest.raises(TaskError, match="overlaps"):
            svc.move_to_day(s, a, TODAY + timedelta(days=1), time(18, 30), today=TODAY)
        t = svc.move_to_day(s, a, TODAY + timedelta(days=1), today=TODAY)
        assert (t.planned_for, t.start_time, t.placement) == (TODAY + timedelta(days=1), None, None)


@pytest.mark.parametrize("word,st", [("running", "run"), ("ran", "run"), ("pages", "page"), ("studied", "study"),
                                     ("workouts", "workout"), ("emails", "email")])
def test_stemming_for_name_matching(word, st):
    assert P.stem(word) == st


def test_weak_name_match_is_read_back_not_guessed(app):
    add(app, "read chapter one")
    io_ = talk(app, "finished off the chapter reading", "no")
    assert io_.prompts[0].startswith("Did you mean read chapter one, today")
    assert titles(app) == [("read chapter one", "pending")]
    talk(app, "finished off the chapter reading", "yes")
    assert titles(app) == [("read chapter one", "done")]


def test_declined_confirmation_is_logged_as_not_acted(app):
    add(app, "report")
    talk(app, "delete all the tasks", "no")
    row = app.voice_log.recent(1)[0]
    assert row.acted is False and row.result == "declined: Nothing was deleted."
