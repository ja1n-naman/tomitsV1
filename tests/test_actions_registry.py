"""No dead buttons (v1.8, replaces the weaker v1.6 check).

1. Static scan of every layout and every shared front-end file for each
   action name a control can send to the server (data-act, data-form, btn(),
   T.trigger, T.run, T.api.command, data-autosave). Each must be a command in
   the registry that has a web handler, or a declared screen-only action
   (`ui:`), which never reaches the server. Command names are defined once,
   in the registry: the front end has no second copy (no `cmd:` fields).
2. End to end: every web command runs through the real API (/api/command)
   with valid sample input on a seeded database, and every name the scan
   found is sent too. "Unknown action" or an unhandled error fails.
3. The page served is the one the server started with, so a server that is
   older than the files on disk can't hand out buttons it doesn't know.
"""

import json
import re
import shutil
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

import tomits.web.actions  # noqa: F401  (attaches web handlers)
from tomits import notes as N
from tomits import services as svc
from tomits import tracking as tr
from tomits.alarms import HEADS_UP, Alarm
from tomits.models import Task
from tomits.periods import PeriodKind
from tomits.voice import registry as R
from tomits.web.codecheck import FrontEnd, Fingerprint
from tomits.web.context import WebApp
from tomits.web.server import create_app

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "tomits" / "web" / "static"
DAY, WEEK = PeriodKind.DAY, PeriodKind.WEEK


def front_end_code() -> dict:
    """Every file of the six layouts and the shared code: name -> text."""
    files = sorted(p for p in STATIC.rglob("*") if p.suffix in (".js", ".html"))
    assert {f"l{n}.js" for n in range(1, 7)} <= {p.name for p in files}
    return {p.relative_to(STATIC).as_posix(): p.read_text(encoding="utf-8") for p in files}


# patterns that put an action name on a control, or send one to the server
CONTROL = [r'data-act="(\w+)"', r'data-act=\\"(\w+)', r'data-form="(\w+)"', r"data-form=\\\"(\w+)",
           r'\bbtn\("(\w+)"', r'\.btn\("(\w+)"', r'T\.trigger\("(\w+)"',
           r'data-form="\' \+ \(\w+ \? "(\w+)" : "\w+"\)', r'data-form="\' \+ \(\w+ \? "\w+" : "(\w+)"\)']
SENT = [r'T\.run\("(\w+)"', r'T\.api\.command\("(\w+)"', r'\bapi\.command\("(\w+)"', r'data-autosave="(\w+)"',
        r"data-autosave=\\\"(\w+)"]


def scan(code: dict):
    """(control names -> files, names sent straight to the server -> files,
    screen-only action names, names that carry a second copy of a command name)."""
    controls, sent, ui_only, copies = {}, {}, set(), []
    for path, text in code.items():
        for pat in CONTROL:
            for m in re.finditer(pat, text):
                controls.setdefault(m.group(1), set()).add(path)
        for pat in SENT:
            for m in re.finditer(pat, text):
                sent.setdefault(m.group(1), set()).add(path)
        for m in re.finditer(r"^ {4}(\w+): \{ ui: \"", text, re.M):
            ui_only.add(m.group(1))
        for m in re.finditer(r"T\.ACTIONS\.(\w+) = \{ ui: \"", text):
            ui_only.add(m.group(1))
        for m in re.finditer(r"(\w+): \{ cmd: \"(\w+)\"", text):
            copies.append((path, m.group(1), m.group(2)))
    return controls, sent, ui_only, copies


def web_commands() -> set:
    return {c.name for c in R.REGISTRY if c.web is not None}


def problems(code: dict) -> list:
    controls, sent, ui_only, copies = scan(code)
    cmds = web_commands()
    out = []
    for name, files in sorted(controls.items()):
        if name not in cmds and name not in ui_only:
            out.append(f"control '{name}' ({', '.join(sorted(files))}) is not a registry command or a screen-only action")
    for name, files in sorted(sent.items()):
        if name not in cmds:
            out.append(f"'{name}' is sent to the server ({', '.join(sorted(files))}) but isn't a registry command")
    for name in sorted(ui_only & set(R.names()) if hasattr(R, "names") else ui_only & {c.name for c in R.REGISTRY}):
        out.append(f"screen-only action '{name}' has the same name as a registry command")
    for path, key, cmd in copies:
        out.append(f"{path}: '{key}' repeats a command name (cmd: \"{cmd}\"); the registry name is the only name")
    return out


# ======================= 1. static scan =======================

def test_every_name_a_control_can_send_is_in_the_registry():
    assert problems(front_end_code()) == []


def test_every_web_command_is_reachable_from_some_control():
    controls, sent, _, _ = scan(front_end_code())
    missing = web_commands() - set(controls) - set(sent)
    assert missing == set(), f"web commands with no control: {missing}"


@pytest.mark.parametrize("old,new", [
    ('btn("made_sacrifice"', 'btn("made_sacrifices"'),        # the bug that started this
    ('btn("remove_sacrifice"', 'btn("delete_sacrifice"'),
    ('data-form="add_note"', 'data-form="new_note"'),
    ('T.run("move_task"', 'T.run("move_tasks"'),
])
def test_a_deliberately_renamed_button_is_caught(old, new):
    code = front_end_code()
    hits = [p for p, t in code.items() if old in t]
    assert hits, f"{old} not found in the front end"
    code[hits[0]] = code[hits[0]].replace(old, new, 1)
    found = problems(code)
    assert any(new.split('"')[1] in p for p in found), found


# ======================= 2. end to end through the API =======================

NOW = datetime(2026, 9, 29, 10, 0)
TODAY = NOW.date()
BASE = "http://127.0.0.1:3000"
H = {"X-Tomits": "1"}


@pytest.fixture
def world(db_file):
    """A seeded app: tasks in every state the commands need, goals, a log,
    a sacrifice, notes, proposals, a ringing alarm and an undo entry."""
    ctx = WebApp(db_file, clock=lambda: NOW, start_threads=False)
    ctx.settings.llm_enabled = False
    client = create_app(ctx, 3000).test_client()
    ids = {}
    with ctx.Session() as s:
        add = lambda title, start, minutes=30, **kw: svc.add_task(s, title, minutes, planned_for=TODAY, start_time=start,
                                                                   today=TODAY, now=NOW, read_title=False, **kw)
        ids["task"] = add("later", time(12, 0)).id
        ids["running"] = add("running", time(9, 30), 60).id
        ids["blocker"] = add("blocker", time(10, 30), 30).id
        ids["typed"] = svc.add_task(s, "typed at 15:00", None, planned_for=TODAY, today=TODAY, now=NOW).id
        ids["failed"] = add("failed", time(8, 0)).id
        svc.fail_task(s, ids["failed"], "reason")
        capped = add("capped", time(7, 0))
        capped.reschedule_count = 2
        s.commit()
        svc.fail_task(s, capped.id, "reason")
        ids["capped"] = capped.id
        week = tr.create_goal(s, WEEK, TODAY, "week pages", 50, "pages", today=TODAY)
        ids["goal"] = tr.create_goal(s, DAY, TODAY, "day pages", 10, "pages", parent_id=week.id, today=TODAY).id
        ids["plain"] = tr.create_goal(s, DAY, TODAY, "plain", today=TODAY).id
        ids["spare"] = tr.create_goal(s, DAY, TODAY, "spare", today=TODAY).id
        ids["log"] = tr.log_progress(s, ids["goal"], 1, on=TODAY, today=TODAY).id
        ids["sacrifice"] = tr.add_sacrifice(s, DAY, TODAY, "item", today=TODAY).id
        ids["note"] = N.add_note(s, "note one", now=NOW).id
        banner = N.add_note(s, "note two", datetime(2026, 9, 29, 9, 59, 30), now=datetime(2026, 9, 29, 9, 0))
        N.claim_due(s, NOW)
        ids["banner"] = banner.id
        ids["closed_prop"] = ctx.proposals.add(s, ("closed", ids["failed"], None))
        ids["cap_prop"] = ctx.proposals.add(s, ("closed", ids["capped"], None))
        ids["overrun_prop"] = ctx.proposals.add(s, ("overrun", ids["running"], datetime(2026, 9, 29, 11, 0)))
    ctx.ringer.ring(Alarm(HEADS_UP, ids["task"], "later", datetime(2026, 9, 29, 12, 0), datetime(2026, 9, 29, 12, 30)))
    ctx.checkins[ids["running"]] = Alarm("end", ids["running"], "running", NOW, NOW)
    yield ctx, client, ids
    ctx.stop()


def post(client, name, args):
    r = client.post("/api/command", base_url=BASE, headers=H, json={"cmd": name, "args": args})
    return r.status_code, r.get_json()


def _undo_id(client, ids):
    code, out = post(client, "add_task", {"title": "to undo", "duration": 15, "date": TODAY.isoformat()})
    return {"id": out["undo_id"]}


def _accepted(client, ids):
    post(client, "proposal_answer", {"id": ids["closed_prop"], "answer": "accept"})
    return {"confirmed": True}


def _export(client, ids):
    code, out = post(client, "export_data", {})
    return {"data": json.dumps(out["export"]), "confirmed": True}


# valid sample input for every web command; a callable gets (client, ids)
SAMPLES = {
    "add_task": {"title": "new", "duration": 30, "date": TODAY.isoformat()},
    "add_several": {"date": TODAY.isoformat(), "lines": [{"title": "a", "duration": 15}, {"title": "b", "duration": 15}]},
    "plan_day": {"date": TODAY.isoformat()},
    "move_task": lambda c, i: {"id": i["task"], "mode": "time", "start": "13:00"},
    "pin_task": lambda c, i: {"id": i["task"]},
    "unpin_task": lambda c, i: {"id": i["task"]},
    "edit_task": lambda c, i: {"id": i["task"], "title": "renamed", "duration": "30"},
    "keep_typed_title": lambda c, i: {"id": i["typed"]},
    "delete_task": lambda c, i: {"id": i["task"], "confirmed": True},
    "mark_done": lambda c, i: {"id": i["task"]},
    "mark_failed": lambda c, i: {"id": i["task"], "reason": "no time"},
    "mark_skipped": lambda c, i: {"id": i["task"], "reason": "not needed"},
    "extend_task": lambda c, i: {"id": i["running"], "minutes": 10},
    "reschedule_missed": lambda c, i: {"id": i["failed"]},
    "proposal_answer": lambda c, i: {"id": i["closed_prop"], "answer": "accept"},
    "collision_answer": lambda c, i: {"id": i["overrun_prop"], "choice": "leave"},
    "cap_answer": lambda c, i: {"id": i["cap_prop"], "choice": "keep"},
    "undo_reschedule": _accepted,
    "link_task": lambda c, i: {"id": i["task"], "goal_id": i["goal"]},
    "checkin_answer": lambda c, i: {"id": i["running"], "answer": "later"},
    "new_goal": {"kind": "day", "start": TODAY.isoformat(), "title": "another"},
    "edit_goal": lambda c, i: {"id": i["goal"], "title": "day pages renamed"},
    "delete_goal": lambda c, i: {"id": i["spare"], "confirmed": True},
    "log_progress": lambda c, i: {"goal_id": i["goal"], "amount": 2},
    "remove_log": lambda c, i: {"log_id": i["log"], "confirmed": True},
    "goal_done": lambda c, i: {"id": i["plain"], "done": True},
    "set_process": {"kind": "day", "start": TODAY.isoformat(), "text": "steps"},
    "write_review": {"kind": "day", "start": TODAY.isoformat(), "text": "went fine"},
    "add_sacrifice": {"kind": "day", "start": TODAY.isoformat(), "text": "another"},
    "made_sacrifice": lambda c, i: {"id": i["sacrifice"]},
    "remove_sacrifice": lambda c, i: {"id": i["sacrifice"]},
    "dismiss_reminder": {"kind": "week", "start": TODAY.isoformat(), "part": "process"},
    "alarm_dismiss": lambda c, i: {"kind": HEADS_UP, "task_id": i["task"]},
    "alarm_snooze": lambda c, i: {"kind": HEADS_UP, "task_id": i["task"]},
    "delete_all": {"scope": "tasks", "confirmed": True},
    "clear_day": {"date": TODAY.isoformat(), "confirmed": True},
    "settings": {"snooze_minutes": 10},
    "voice_settings": {"spoken_replies": False},
    "mute": {"muted": True},
    "input_device": {"device": ""},
    "switch_layout": {"layout": 2},
    "set_theme": {"theme": "dark"},
    "finish_setup": {},
    "undo_action": _undo_id,
    "add_note": {"text": "remember this", "color": "sage"},
    "delete_note": lambda c, i: {"id": i["note"]},
    "dismiss_note_banner": lambda c, i: {"id": i["banner"]},
    "notes_panel": {"open": True},
    "export_data": {},
    "import_data": _export,
}


def test_every_web_command_has_a_sample():
    assert web_commands() - set(SAMPLES) == set(), "add a sample for each new web command"
    assert set(SAMPLES) - web_commands() == set(), "samples for commands that no longer exist"


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_each_web_command_runs_end_to_end(world, name):
    ctx, client, ids = world
    args = SAMPLES[name]
    args = args(client, ids) if callable(args) else dict(args)
    code, out = post(client, name, args)
    assert "Unknown action" not in str(out), out
    assert code == 200 and out["ok"], (name, code, out)
    assert not out.get("needs_confirm"), (name, out)


def test_every_name_the_front_end_sends_reaches_a_handler(world):
    """Whatever the scan found, sent as is (empty arguments): never Unknown
    action, never a crash; a rule refusal (422) is fine."""
    ctx, client, ids = world
    controls, sent, ui_only, _ = scan(front_end_code())
    for name in sorted((set(controls) | set(sent)) - ui_only):
        code, out = post(client, name, {})
        assert code != 500 and "Unknown action" not in str(out), (name, code, out)
        assert code in (200, 422), (name, code, out)


def test_a_renamed_name_would_be_refused_by_the_server(world):
    ctx, client, ids = world
    code, out = post(client, "made_sacrifices", {"id": ids["sacrifice"]})
    assert code == 422 and "Unknown action" in out["error"]


def test_the_state_lists_the_registry_commands(world):
    ctx, client, ids = world
    st = client.get("/api/state", base_url=BASE).get_json()
    assert set(st["commands"]) == web_commands()


# ======================= 3. the page always matches the running server =======================

def test_the_page_served_is_the_one_the_server_started_with(tmp_path):
    root = tmp_path / "static"
    shutil.copytree(STATIC, root)
    front = FrontEnd(root)
    before = front.get("js/actions.js")[0]
    (root / "js" / "actions.js").write_text("// changed on disk while running", encoding="utf-8")
    assert front.get("js/actions.js")[0] == before


def test_a_code_change_on_disk_is_noticed(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1", encoding="utf-8")
    fp = Fingerprint(pkg, every=0)
    assert not fp.changed()
    (pkg / "a.py").write_text("x = 22", encoding="utf-8")
    assert fp.changed()


def test_the_server_serves_its_snapshot(world):
    ctx, client, ids = world
    r = client.get("/static/js/actions.js", base_url=BASE)
    assert r.status_code == 200 and "T.isCommand" in r.get_data(as_text=True)
    assert client.get("/static/js/nope.js", base_url=BASE).status_code == 404
    assert client.get("/", base_url=BASE).status_code == 200
    st = client.get("/api/state", base_url=BASE).get_json()
    assert st["update_waiting"] is False
