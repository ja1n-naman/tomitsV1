"""v1.8 Remember (notes): rules in the logic layer, the single reminder and
the away summary, undo, migration, live updates, export / import, and the
same actions from the web API, the quick-add box, voice and the terminal."""

import io
import json
import sqlite3
import time as _time
from datetime import date, datetime, time, timedelta

import pytest
from rich.console import Console

from tomits import exporting as EX
from tomits import notes as N
from tomits import services as svc
from tomits import ui
from tomits.db import SCHEMA_VERSION, make_session_factory
from tomits.errors import TaskError
from tomits.models import Note, Task
from tomits.web.context import WebApp
from tomits.web.server import create_app

NOW = datetime(2026, 10, 5, 10, 0)
TODAY = NOW.date()
BASE = "http://127.0.0.1:3000"
H = {"X-Tomits": "1"}


def add(s, text="note", due=None, color=None, now=NOW, **kw):
    return N.add_note(s, text, due, color, now=now, **kw)


# ======================= rules =======================

def test_text_is_required_and_at_most_200_characters(session):
    with pytest.raises(TaskError, match="needs some text"):
        add(session, "   ")
    add(session, "x" * 200)
    with pytest.raises(TaskError, match="at most 200 characters; this one has 201"):
        add(session, "x" * 201)


def test_at_most_50_notes(session):
    for i in range(50):
        add(session, f"note {i}")
    with pytest.raises(TaskError, match="already have 50 notes, the most there can be"):
        add(session, "one more")
    assert N.count(session) == 50


def test_colour_is_from_the_fixed_set_and_stored(session):
    assert add(session, "a").color == "sand"
    assert add(session, "b", color="sage").color == "sage"
    with pytest.raises(TaskError, match="Pick a colour"):
        add(session, "c", color="neon")


def test_notes_cannot_be_edited():
    assert not any(hasattr(N, f) for f in ("update_note", "edit_note", "set_color", "rename_note"))
    from tomits.voice import registry as R
    assert {c.name for c in R.REGISTRY if "note" in c.name} == {"add_note", "delete_note", "notes_panel",
                                                               "dismiss_note_banner"}


def test_a_time_in_the_text_is_read_like_a_task_title(session):
    n = add(session, "call the bank tomorrow at 5pm")
    assert (n.text, n.due_at) == ("call the bank", datetime(2026, 10, 6, 17, 0))
    assert n.understood.startswith("Read from the note: Tue 06 Oct at 17:00")
    plain = add(session, "read 10 pages")
    assert (plain.text, plain.due_at) == ("read 10 pages", None)


def test_unclear_am_pm_asks(session):
    with pytest.raises(svc.AmbiguousTime):
        add(session, "call at 7", window=(time(6, 0), time(23, 0)))
    assert add(session, "call at 7", window=(time(6, 0), time(23, 0)), ampm="pm").due_at == datetime(2026, 10, 5, 19)


def test_a_time_already_past_goes_straight_to_overdue_without_a_reminder(session):
    n = add(session, "late", datetime(2026, 10, 5, 9, 0))
    assert n.reminded_how == "past" and "already passed" in n.understood
    assert N.claim_due(session, NOW) == []


# ======================= sections =======================

def test_three_sections_and_their_order(session):
    a = add(session, "no time old", now=datetime(2026, 10, 5, 8, 0))
    b = add(session, "no time new", now=datetime(2026, 10, 5, 9, 0))
    later = add(session, "later", datetime(2026, 10, 6, 9, 0))
    soon = add(session, "soon", datetime(2026, 10, 5, 11, 0))
    sec = N.sections(session, NOW)
    assert [n.text for n in sec.upcoming] == ["soon", "later"]           # soonest first
    assert [n.text for n in sec.no_time] == ["no time new", "no time old"]  # newest first
    assert sec.overdue == [] and sec.total == 4
    assert a.id and b.id and later.id and soon.id


def test_a_note_moves_to_overdue_when_its_time_passes_and_stays(session):
    n = add(session, "soon", datetime(2026, 10, 5, 10, 30))
    assert [x.id for x in N.sections(session, NOW).upcoming] == [n.id]
    after = datetime(2026, 10, 5, 10, 30)
    sec = N.sections(session, after)
    assert [x.id for x in sec.overdue] == [n.id] and sec.upcoming == []
    assert [x.id for x in N.sections(session, after + timedelta(days=30)).overdue] == [n.id]   # never disappears


# ======================= one reminder, and the away summary =======================

def test_each_note_is_reminded_once(session):
    n = add(session, "call", datetime(2026, 10, 5, 10, 5))
    assert N.claim_due(session, datetime(2026, 10, 5, 10, 4)) == []
    got = N.claim_due(session, datetime(2026, 10, 5, 10, 5))
    assert [x.id for x in got] == [n.id] and got[0].banner_open
    N.dismiss_banner(session, n.id)
    assert N.claim_due(session, datetime(2026, 10, 5, 11, 0)) == []        # never again, even after dismissing
    assert session.get(Note, n.id) is not None                              # dismissing doesn't delete it


def test_two_running_copies_never_both_remind(db_file):
    S1, S2 = make_session_factory(db_file), make_session_factory(db_file)
    with S1() as s:
        add(s, "once", datetime(2026, 10, 5, 10, 5))
    with S1() as a, S2() as b:
        first = N.claim_due(a, datetime(2026, 10, 5, 10, 6))
        second = N.claim_due(b, datetime(2026, 10, 5, 10, 6))
    assert len(first) + len(second) == 1


def test_notes_that_passed_while_closed_give_one_summary_and_no_live_reminders(db_file):
    with make_session_factory(db_file)() as s:
        add(s, "a", datetime(2026, 10, 5, 7, 0), now=datetime(2026, 10, 5, 6, 0))
        add(s, "b", datetime(2026, 10, 5, 8, 0), now=datetime(2026, 10, 5, 6, 0))
        add(s, "c", datetime(2026, 10, 5, 12, 0), now=datetime(2026, 10, 5, 6, 0))
    fired = []
    ctx = WebApp(db_file, clock=lambda: NOW, start_threads=False)
    ctx.notes._on_due = fired.append
    assert ctx.notes.startup() == 2 and ctx.notes.check() == [] and fired == []
    client = create_app(ctx, 3000).test_client()
    ctx.notes_away = 2
    st = client.get("/api/state", base_url=BASE).get_json()["notes"]
    assert st["away"] == 2 and st["banners"] == [] and st["overdue_count"] == 2
    code = client.post("/api/command", base_url=BASE, headers=H, json={"cmd": "dismiss_note_banner",
                                                                        "args": {"id": "away"}}).status_code
    assert code == 200 and client.get("/api/state", base_url=BASE).get_json()["notes"]["away"] == 0
    ctx.stop()


def test_web_app_reminds_once_with_a_banner_and_one_event(db_file):
    clock = {"now": NOW}
    ctx = WebApp(db_file, clock=lambda: clock["now"], start_threads=False)
    client = create_app(ctx, 3000).test_client()
    with ctx.Session() as s:
        n = add(s, "stretch", datetime(2026, 10, 5, 10, 1))
    q = ctx.hub.subscribe()                     # an open tab
    clock["now"] = datetime(2026, 10, 5, 10, 1)
    assert len(ctx.notes.check()) == 1 and ctx.notes.check() == []
    events = [q.get(timeout=1) for _ in range(2)]
    assert sum("event: note" in e for e in events) == 1 and '"text": "stretch"' in events[0]
    st = client.get("/api/state", base_url=BASE).get_json()["notes"]
    assert [b["id"] for b in st["banners"]] == [n.id]
    client.post("/api/command", base_url=BASE, headers=H, json={"cmd": "dismiss_note_banner", "args": {"id": n.id}})
    st = client.get("/api/state", base_url=BASE).get_json()["notes"]
    assert st["banners"] == [] and st["overdue"][0]["id"] == n.id
    ctx.stop()


def test_with_no_tab_open_the_server_notifies_once(db_file):
    clock = {"now": NOW}
    ctx = WebApp(db_file, clock=lambda: clock["now"], start_threads=False)
    sent = []

    class Toast:
        def notify(self, title, message, urgent=False):
            sent.append(message)

    ctx.notifier = Toast()
    with ctx.Session() as s:
        add(s, "alone", datetime(2026, 10, 5, 10, 1))
    clock["now"] = datetime(2026, 10, 5, 10, 2)
    ctx.notes.check()
    ctx.notes.check()
    assert sent == ["alone"]
    ctx.stop()


# ======================= web API, undo, live =======================

@pytest.fixture
def web(db_file):
    ctx = WebApp(db_file, clock=lambda: NOW, start_threads=False)
    ctx.settings.llm_enabled = False
    yield ctx, create_app(ctx, 3000).test_client()
    ctx.stop()


def cmd(client, name, **args):
    r = client.post("/api/command", base_url=BASE, headers=H, json={"cmd": name, "args": args})
    return r.status_code, r.get_json()


def test_add_with_and_without_time_and_delete_with_undo_restoring_the_exact_note(web, db_file):
    ctx, client = web
    code, out = cmd(client, "add_note", text="with time", due="2026-10-05T15:30", color="lilac")
    assert code == 200
    cmd(client, "add_note", text="without time")
    st = client.get("/api/state", base_url=BASE).get_json()["notes"]
    assert [n["text"] for n in st["upcoming"]] == ["with time"] and [n["text"] for n in st["no_time"]] == ["without time"]
    note = st["upcoming"][0]
    with sqlite3.connect(db_file) as c:
        before = c.execute("SELECT * FROM notes WHERE id = ?", (note["id"],)).fetchone()
    code, out = cmd(client, "delete_note", id=note["id"])
    assert code == 200 and not out.get("needs_confirm") and out["undo_id"]
    code, _ = cmd(client, "undo_action", id=out["undo_id"])
    with sqlite3.connect(db_file) as c:
        after = c.execute("SELECT * FROM notes WHERE id = ?", (note["id"],)).fetchone()
    assert code == 200 and after == before                    # same id, text, time, colour, created time


def test_limits_through_the_api(web):
    ctx, client = web
    code, out = cmd(client, "add_note", text="x" * 201)
    assert code == 422 and "at most 200" in out["error"]
    for i in range(50):
        cmd(client, "add_note", text=f"n{i}")
    code, out = cmd(client, "add_note", text="51st")
    assert code == 422 and "50 notes" in out["error"]


def test_panel_state_is_remembered_and_not_an_undo_step(web):
    ctx, client = web
    code, out = cmd(client, "notes_panel", open=True)
    assert code == 200 and out["undo_id"] is None
    from tomits.settings import load_settings
    assert load_settings(ctx.settings_file).notes_open is True


def test_note_changes_reach_every_open_tab(web):
    ctx, client = web
    q1, q2 = ctx.hub.subscribe(), ctx.hub.subscribe()
    cmd(client, "add_note", text="live")
    assert "changed" in q1.get(timeout=1) and "changed" in q2.get(timeout=1)


def test_a_note_added_in_the_terminal_reaches_the_browser(db_file):
    ctx = WebApp(db_file, clock=lambda: NOW, start_threads=False, watch_interval=0.1)
    q = ctx.hub.subscribe()
    ctx.watcher.start()
    try:
        _time.sleep(0.3)
        with make_session_factory(db_file)() as s:      # another process, like the terminal version
            add(s, "from the terminal")
        assert "changed" in q.get(timeout=3)
        st = create_app(ctx, 3000).test_client().get("/api/state", base_url=BASE).get_json()
        assert [n["text"] for n in st["notes"]["no_time"]] == ["from the terminal"]
    finally:
        ctx.stop()


def test_quick_add_box_adds_and_deletes_notes(web):
    ctx, client = web
    say = lambda t: client.post("/api/say", base_url=BASE, headers=H, json={"text": t}).get_json()
    out = say("remember to buy stamps at 6 pm")
    assert any("Added the note: buy stamps, today at 18:00" in m["text"] for m in out["messages"])
    out = say("delete the note stamps")
    assert any("Deleted the note: buy stamps" in m["text"] for m in out["messages"])
    with ctx.Session() as s:
        assert N.count(s) == 0


# ======================= export / import / backups / migration =======================

def test_notes_are_in_the_export_and_come_back_on_import(web, db_file):
    ctx, client = web
    cmd(client, "add_note", text="keep me", due="2026-10-07T08:00", color="rose")
    code, out = cmd(client, "export_data")
    assert code == 200 and out["filename"].startswith("tomits-export-")
    notes = out["export"]["tables"]["notes"]
    assert [(n["text"], n["color"], n["due_at"][:16]) for n in notes] == [("keep me", "rose", "2026-10-07 08:00")]
    assert (db_file.parent / "exports" / out["filename"]).exists()
    cmd(client, "add_note", text="added after the export")
    with ctx.Session() as s:
        svc.add_task(s, "task after export", 30, planned_for=TODAY, today=TODAY)
    code, prev = cmd(client, "import_data", data=json.dumps(out["export"]))
    assert prev["needs_confirm"] and "1 notes" in prev["message"]
    code, done = cmd(client, "import_data", data=json.dumps(out["export"]), confirmed=True)
    assert code == 200 and "backed up" in done["message"]
    with ctx.Session() as s:
        assert [(n.text, n.color) for n in s.query(Note)] == [("keep me", "rose")]
        assert s.query(Task).count() == 0
    assert list(db_file.parent.glob("test.db.bak-v*"))                 # the data before the import


def test_a_bad_import_changes_nothing(web):
    ctx, client = web
    cmd(client, "add_note", text="stays")
    for bad in ("not json", json.dumps({"app": "other"}), json.dumps({"app": "tomits", "format": 1, "schema": 1, "tables": {}})):
        code, out = cmd(client, "import_data", data=bad, confirmed=True)
        assert code == 422
    with ctx.Session() as s:
        assert [n.text for n in s.query(Note)] == ["stays"]


def test_notes_are_in_database_backups(db_file):
    from tomits.db import backup_database
    with make_session_factory(db_file)() as s:
        add(s, "backed up")
    copy = backup_database(db_file, SCHEMA_VERSION)
    with sqlite3.connect(copy) as c:
        assert c.execute("SELECT text FROM notes").fetchall() == [("backed up",)]


def _v7_database(path):
    make_session_factory(path)
    with sqlite3.connect(path) as c:
        c.executescript("""DROP TABLE notes; PRAGMA user_version = 7;
            INSERT INTO tasks (id, title, duration_min, planned_for, position, status, heads_up_sent, end_alert_sent,
              priority, reschedule_count, created_at) VALUES (1, 'kept', 30, '2026-10-05', 1, 'pending', 0, 0, 3, 0,
              '2026-10-05 08:00');""")


def test_migration_adds_notes_after_a_timestamped_backup(tmp_path):
    db = tmp_path / "tomits.db"
    _v7_database(db)
    Session = make_session_factory(db)
    assert len(list(tmp_path.glob("tomits.db.bak-v7-*"))) == 1
    with Session() as s:
        assert s.get(Task, 1).title == "kept" and N.count(s) == 0
        add(s, "first")
    with sqlite3.connect(db) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 8


def test_migration_stops_if_the_backup_fails(tmp_path, monkeypatch):
    from tomits import db as DB
    db = tmp_path / "tomits.db"
    _v7_database(db)
    real = sqlite3.connect

    def broken(path, *a, **k):
        if ".bak-" in str(path):
            raise sqlite3.OperationalError("disk is full")
        return real(path, *a, **k)

    monkeypatch.setattr(DB.sqlite3, "connect", broken)
    with pytest.raises(DB.MigrationError, match="Nothing was changed"):
        make_session_factory(db)
    monkeypatch.undo()
    with sqlite3.connect(db) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 7
        assert "notes" not in {r[0] for r in c.execute("SELECT name FROM sqlite_master")}


# ======================= voice and terminal =======================

class ScriptedIO:
    def __init__(self, utterances):
        self.queue, self.said = list(utterances), []

    def say(self, text):
        self.said.append(text)

    def listen(self, prompt=None, grammar=None):
        from tomits.voice.dialog import Heard
        if prompt:
            self.said.append(prompt)
        return Heard(self.queue.pop(0) if self.queue else "", 1.0)


class Quiet:
    def notify(self, *a, **k):
        pass

    def play_burst(self):
        pass


@pytest.fixture
def term(db_file, monkeypatch):
    out = io.StringIO()
    monkeypatch.setattr(ui, "console", Console(file=out, width=200))
    monkeypatch.setattr("tomits.ui_common.console", Console(file=io.StringIO()))
    a = ui.App(db_file, notifier=Quiet(), clock=lambda: NOW, player=Quiet())
    a.out = out
    return a


def talk(app, *utterances):
    io_ = ScriptedIO(utterances)
    app.voice_turn(io_)
    return io_


def texts(app):
    with app.Session() as s:
        return sorted(n.text for n in s.query(Note))


def test_voice_adds_a_note_with_a_time_and_confirms_out_loud(term):
    io_ = talk(term, "remember to call the bank tomorrow at 5 pm")
    assert "Added the note: call the bank, Tue 06 Oct at 17:00." in io_.said
    io_ = talk(term, "add a note buy stamps in sage")
    with term.Session() as s:
        assert s.query(Note).filter_by(text="buy stamps").one().color == "sage"


def test_voice_deletes_by_part_of_the_text_and_picks_by_number(term):
    with term.Session() as s:
        add(s, "pay the gas bill")
        add(s, "pay the water bill")
        add(s, "buy stamps")
    io_ = talk(term, "delete the note stamps")
    assert io_.said[-1] == "Deleted the note: buy stamps."
    io_ = talk(term, "delete the note pay the bill", "the second one")
    assert any("1" in x and "gas" in x and "water" in x for x in io_.said)
    assert io_.said[-1] == "Deleted the note: pay the water bill."
    assert texts(term) == ["pay the gas bill"]


def test_voice_reads_the_notes(term):
    with term.Session() as s:
        add(s, "soon", datetime(2026, 10, 5, 11, 0))
    io_ = talk(term, "what do i need to remember")
    assert io_.said[-1].startswith("You have 1 note. coming up: soon, today at 11:00")


def _answers(monkeypatch, *answers):
    it = iter(answers)
    monkeypatch.setattr(ui.Prompt, "ask", classmethod(lambda cls, *a, **k: next(it)))


def test_terminal_adds_and_deletes_notes(term, monkeypatch):
    _answers(monkeypatch, "water the plants", "", "sky")
    term.add_note()
    _answers(monkeypatch, "pay rent", "2026-10-06 09:00", "sand")
    term.add_note()
    assert texts(term) == ["pay rent", "water the plants"]
    with term.Session() as s:
        assert s.query(Note).filter_by(text="pay rent").one().due_at == datetime(2026, 10, 6, 9, 0)
    _answers(monkeypatch, "1")                               # the list: upcoming first (no overdue), then no time
    term.delete_note()
    assert texts(term) == ["water the plants"]


def test_terminal_shows_the_panel_and_the_away_summary(term):
    with term.Session() as s:
        add(s, "missed", datetime(2026, 10, 5, 7, 0), now=datetime(2026, 10, 5, 6, 0))
        add(s, "later", datetime(2026, 10, 5, 18, 0))
    term.notes_away = term.notes.startup()
    term.dashboard()
    out = term.out.getvalue()
    assert "Remember (2, 1 overdue)" in out and "1 note became overdue while you were away" in out


def test_terminal_export_and_import(term, monkeypatch):
    with term.Session() as s:
        add(s, "exported")
    term.export_typed()
    with term.Session() as s:
        add(s, "after")
    _answers(monkeypatch, "", "IMPORT")
    term.import_typed()
    assert texts(term) == ["exported"]
