"""v1.6 web app: the API enforces every earlier rule through the logic layer,
writes are committed at once, live updates reach other clients, the terminal
and the web app can write together, undo never deletes a reason, and only the
local app may talk to the server."""

import json
import sqlite3
import threading
import time as _time
from datetime import date, datetime, time

import pytest

from tomits import services as svc
from tomits import tracking as tr
from tomits.db import make_session_factory
from tomits.models import Task, TaskReason
from tomits.voice import registry as R
from tomits.web.context import WebApp
from tomits.web.server import create_app
from helpers import DAY, MONTH, MON_28_SEP, SUN_27_SEP, TUE_29_SEP, WEEK

NOW = datetime.combine(TUE_29_SEP, time(10, 0))
BASE = "http://127.0.0.1:3000"
H = {"X-Tomits": "1"}


@pytest.fixture
def ctx(db_file):
    c = WebApp(db_file, clock=lambda: NOW, start_threads=False)
    c.settings.llm_enabled = False
    yield c
    c.stop()


@pytest.fixture
def client(ctx):
    return create_app(ctx, 3000).test_client()


def cmd(client, name, **args):
    r = client.post("/api/command", base_url=BASE, headers=H, json={"cmd": name, "args": args})
    return r.status_code, r.get_json()


def state(client, **q):
    return client.get("/api/state", base_url=BASE, query_string=q).get_json()


def add(client, title="t", duration=30, start=None, **kw):
    code, out = cmd(client, "add_task", title=title, duration=duration, start=start, date=kw.pop("date", TUE_29_SEP.isoformat()), **kw)
    assert code == 200, out
    return out["task_id"]


def fresh_session(db_file):
    """A separate engine, like another process (the terminal version)."""
    return make_session_factory(db_file)()


# ======================= rules through the API =======================

def test_overlap_is_refused_and_back_to_back_is_fine(client):
    add(client, "a", 60, "10:00")
    code, out = cmd(client, "add_task", title="b", duration=30, start="10:30", date=TUE_29_SEP.isoformat())
    assert code == 422 and "overlaps" in out["error"]
    add(client, "c", 30, "11:00")
    code, out = cmd(client, "move_task", id=1, mode="time", start="11:15")
    assert code == 422 and "overlaps" in out["error"]


def test_failing_or_skipping_needs_a_reason(client, db_file):
    tid = add(client, "a", 30, "12:00")
    for name in ("mark_failed", "mark_skipped"):
        code, out = cmd(client, name, id=tid, reason="   ")
        assert code == 422 and "reason is required" in out["error"]
    with fresh_session(db_file) as s:
        assert s.get(Task, tid).status == "pending"
    code, out = cmd(client, "mark_failed", id=tid, reason="power cut")
    assert code == 200 and out["proposal_id"]


def test_locked_periods_are_refused(client):
    code, out = cmd(client, "new_goal", kind="day", start=MON_28_SEP.isoformat(), title="late")
    assert code == 422 and "ended" in out["error"]
    code, out = cmd(client, "set_process", kind="week", start="2026-09-20", text="p")
    assert code == 422
    code, out = cmd(client, "write_review", kind="day", start=SUN_27_SEP.isoformat(), text="r")
    assert code == 422 and "closed" in out["error"]
    code, out = cmd(client, "write_review", kind="day", start=MON_28_SEP.isoformat(), text="r")  # within the cutoff
    assert code == 200


def test_plan_day_never_moves_fixed_or_pinned_tasks(client, db_file):
    fixed = add(client, "fixed", 60, "10:00")
    pinned = add(client, "pin me", 30)
    assert cmd(client, "plan_day", date=TUE_29_SEP.isoformat())[0] == 200       # placed by the planner
    assert cmd(client, "move_task", id=pinned, mode="time", start="13:00")[0] == 200  # moved by you: pinned
    for i in range(3):
        add(client, f"free {i}", 45)
    assert cmd(client, "plan_day", date=TUE_29_SEP.isoformat())[0] == 200
    with fresh_session(db_file) as s:
        assert s.get(Task, fixed).start_time == time(10, 0) and s.get(Task, fixed).placement == "fixed"
        assert s.get(Task, pinned).start_time == time(13, 0) and s.get(Task, pinned).placement == "pinned"
        assert all(t.start_time is not None for t in s.query(Task).all())


def test_plan_day_refuses_past_days(client):
    code, out = cmd(client, "plan_day", date=MON_28_SEP.isoformat())
    assert code == 422 and "past" in out["error"]


def test_reschedule_proposal_changes_nothing_until_accepted_and_keeps_pinned(client, db_file):
    pinned = add(client, "pinned", 30)
    cmd(client, "plan_day", date=TUE_29_SEP.isoformat())
    cmd(client, "move_task", id=pinned, mode="time", start="12:00")
    tid = add(client, "work", 60, "10:30")
    code, out = cmd(client, "mark_failed", id=tid, reason="tired")
    pid = out["proposal_id"]
    with fresh_session(db_file) as s:
        assert s.query(Task).count() == 2  # nothing created yet
    props = state(client)["proposals"]
    assert props and props[0]["moves"][0]["kind"] == "copy"
    code, out = cmd(client, "proposal_answer", id=pid, answer="accept")
    assert code == 200 and out["undo_id"]
    with fresh_session(db_file) as s:
        assert s.query(Task).count() == 3
        assert s.get(Task, pinned).start_time == time(12, 0)
    assert cmd(client, "undo_reschedule", confirmed=True)[0] == 200
    with fresh_session(db_file) as s:
        assert s.query(Task).count() == 2


def test_rejected_proposal_changes_nothing(client, db_file):
    tid = add(client, "work", 60, "10:30")
    pid = cmd(client, "mark_skipped", id=tid, reason="ill")[1]["proposal_id"]
    assert cmd(client, "proposal_answer", id=pid, answer="reject")[0] == 200
    assert state(client)["proposals"] == []
    with fresh_session(db_file) as s:
        assert s.query(Task).count() == 1


def test_extend_shows_a_proposal_first(client, db_file):
    tid = add(client, "running", 60, "09:30")
    code, out = cmd(client, "extend_task", id=tid, minutes=30)
    assert code == 200 and out["proposal_id"]
    with fresh_session(db_file) as s:
        assert s.get(Task, tid).duration_min == 60
    cmd(client, "proposal_answer", id=out["proposal_id"], answer="accept")
    with fresh_session(db_file) as s:
        assert s.get(Task, tid).duration_min == 90


def test_destructive_commands_need_confirmation(client, db_file):
    tid = add(client, "keep me", 30)
    code, out = cmd(client, "delete_task", id=tid)
    assert code == 200 and out["needs_confirm"] and "keep me" in out["message"]
    with fresh_session(db_file) as s:
        assert s.get(Task, tid) is not None
    code, out = cmd(client, "delete_all", scope="tasks and goals")
    assert out["needs_confirm"] and "permanently delete 1 pending task" in out["message"]
    with fresh_session(db_file) as s:
        assert s.get(Task, tid) is not None
    assert cmd(client, "delete_task", id=tid, confirmed=True)[0] == 200
    with fresh_session(db_file) as s:
        assert s.get(Task, tid) is None


def test_every_destructive_command_is_marked_for_confirmation():
    import tomits.web.actions  # noqa: F401
    for name in ("delete_task", "delete_goal", "remove_log", "delete_all", "clear_day", "undo_reschedule"):
        assert R.get(name).web_confirm, name


def test_goal_progress_rolls_up_through_the_api(client):
    code, m = cmd(client, "new_goal", kind="month", start="2026-09-01", title="read", target=500, unit="pages")
    code, w = cmd(client, "new_goal", kind="week", start=SUN_27_SEP.isoformat(), title="read wk", target=110, unit="pages", parent_id=m["goal_id"])
    code, d = cmd(client, "new_goal", kind="day", start=TUE_29_SEP.isoformat(), title="read day", target=10, unit="pages", parent_id=w["goal_id"])
    assert cmd(client, "log_progress", goal_id=d["goal_id"], amount=10)[0] == 200
    texts = {g["title"]: g["text"] for k in ("day", "week", "month") for g in state(client)["periods"][k]["goals"]}
    assert texts == {"read day": "10/10 pages", "read wk": "10/110 pages", "read": "10/500 pages"}
    code, out = cmd(client, "new_goal", kind="day", start=TUE_29_SEP.isoformat(), title="x", target=3, unit="km", parent_id=w["goal_id"])
    assert code == 422 and "unit" in out["error"]


def test_every_web_command_is_also_spoken():
    import tomits.web.actions  # noqa: F401
    web = [c for c in R.REGISTRY if c.web is not None]
    assert len(web) >= 40
    for c in web:
        assert c.patterns and c.handler and c.examples, c.name


# ======================= saved at once, live everywhere =======================

def test_writes_are_in_the_database_immediately(client, db_file):
    tid = add(client, "saved?", 25, "15:00")
    with fresh_session(db_file) as s:  # another process would see it now
        t = s.get(Task, tid)
        assert (t.title, t.duration_min, t.start_time) == ("saved?", 25, time(15, 0))
    cmd(client, "set_process", kind="day", start=TUE_29_SEP.isoformat(), text="one step at a time")
    with sqlite3.connect(db_file) as c:
        assert c.execute("SELECT process FROM period_entries WHERE kind='day'").fetchone()[0] == "one step at a time"


def _events(client):
    resp = client.get("/api/events", base_url=BASE, buffered=False)
    return resp, iter(resp.response)


def test_live_updates_reach_every_open_client(client, ctx):
    r1, e1 = _events(client)
    r2, e2 = _events(client)
    assert b"hello" in next(e1) and b"hello" in next(e2)
    add(client, "pushed", 20)
    for e in (e1, e2):
        msg = next(e)
        assert b"event: changed" in msg and b'"command": "add_task"' in msg
    r1.close(); r2.close()
    assert ctx.hub.client_count == 0


def test_terminal_changes_reach_the_browser(db_file):
    ctx = WebApp(db_file, clock=lambda: NOW, start_threads=False, watch_interval=0.1)
    q = ctx.hub.subscribe()
    ctx.watcher.start()
    try:
        _time.sleep(0.3)
        with fresh_session(db_file) as s:   # what the terminal version does
            svc.add_task(s, "from the terminal", 30, planned_for=TUE_29_SEP, today=TUE_29_SEP)
        msg = q.get(timeout=3)
        assert "changed" in msg and "database" in msg
        client = create_app(ctx, 3000).test_client()
        titles = [t["title"] for t in state(client)["day"]["untimed"]]
        assert "from the terminal" in titles
    finally:
        ctx.stop()


def test_concurrent_writes_from_the_terminal_and_the_web_app(client, db_file):
    errors = []

    def terminal():
        try:
            S = make_session_factory(db_file)
            for i in range(15):
                with S() as s:
                    svc.add_task(s, f"terminal {i}", 10, planned_for=TUE_29_SEP, today=TUE_29_SEP)
        except Exception as e:  # pragma: no cover - the failure we look for
            errors.append(e)

    def web():
        for i in range(15):
            code, out = cmd(client, "add_task", title=f"web {i}", duration=10, date=TUE_29_SEP.isoformat())
            if code != 200:
                errors.append(out)

    threads = [threading.Thread(target=terminal), threading.Thread(target=web)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    with fresh_session(db_file) as s:
        assert s.query(Task).count() == 30


# ======================= undo =======================

def test_undo_restores_the_exact_previous_state(client, db_file):
    tid = add(client, "move me", 30, "10:00")
    out = cmd(client, "move_task", id=tid, mode="time", start="14:00")[1]
    assert cmd(client, "undo_action", id=out["undo_id"])[0] == 200
    with fresh_session(db_file) as s:
        t = s.get(Task, tid)
        assert t.start_time == time(10, 0) and t.placement == "fixed"
    out = cmd(client, "add_task", title="gone", duration=10, date=TUE_29_SEP.isoformat())[1]
    cmd(client, "undo_action", id=out["undo_id"])
    with fresh_session(db_file) as s:
        assert s.query(Task).filter_by(title="gone").count() == 0


def test_undo_never_deletes_a_failure_reason(client, db_file):
    tid = add(client, "will fail", 30, "11:00")
    out = cmd(client, "mark_failed", id=tid, reason="the car broke down")[1]
    assert cmd(client, "undo_action", id=out["undo_id"])[0] == 200
    with fresh_session(db_file) as s:
        t = s.get(Task, tid)
        assert t.status == "pending"
        assert [r.reason for r in s.query(TaskReason).all()] == ["the car broke down"]
    assert [r["reason"] for r in state(client)["history"]["rows"]] == ["the car broke down"]
    code, out = cmd(client, "delete_task", id=tid, confirmed=True)   # it has history now: kept
    assert code == 422


def test_undo_is_refused_when_the_row_changed_again(client):
    tid = add(client, "a", 30, "10:00")
    first = cmd(client, "move_task", id=tid, mode="time", start="12:00")[1]
    cmd(client, "move_task", id=tid, mode="time", start="13:00")
    code, out = cmd(client, "undo_action", id=first["undo_id"])
    assert code == 422 and "changed again" in out["error"]


# ======================= reminders, first run =======================

def test_first_run_on_an_empty_database(client):
    st = state(client)
    assert st["setup"]["needed"] is True
    assert st["day"]["tasks"] == [] and st["day"]["untimed"] == [] and st["history"]["rows"] == []
    assert len(st["reminders"]) == 6       # day / week / month x goal / process, as a banner
    assert cmd(client, "finish_setup")[0] == 200
    assert state(client)["setup"]["needed"] is False


def test_reminder_banner_items_are_dismissed_one_by_one(client, ctx):
    assert len(ctx.reminders.check()) == 3             # one notification per period, once
    assert ctx.reminders.check() == []
    st = state(client)
    item = st["reminders"][0]
    assert cmd(client, "dismiss_reminder", kind=item["kind"], start=item["start"], part=item["part"])[0] == 200
    keys = [r["key"] for r in state(client)["reminders"]]
    assert item["key"] not in keys and len(keys) == 5
    assert ctx.reminders.check() == []                # dismissing doesn't re-fire anything


def test_settings_layout_and_theme_are_saved(client, ctx):
    assert cmd(client, "switch_layout", layout=3)[0] == 200
    assert cmd(client, "set_theme", theme="dark")[0] == 200
    assert cmd(client, "settings", day_start="08:00", day_end="20:00", snooze_minutes=10)[0] == 200
    saved = json.loads(ctx.settings_file.read_text(encoding="utf-8"))
    assert (saved["ui_layout"], saved["ui_theme"], saved["day_start"], saved["snooze_minutes"]) == (3, "dark", "08:00", 10)
    code, out = cmd(client, "settings", day_start="20:00", day_end="08:00")
    assert code == 422
    code, out = cmd(client, "switch_layout", layout=9)
    assert code == 422


def test_alarm_dismiss_and_snooze_through_the_api(client, ctx):
    from tomits.alarms import HEADS_UP, Alarm
    a = Alarm(HEADS_UP, 1, "x", NOW, NOW)
    ctx._on_alarm(a)
    assert state(client)["alarms"]["ringing"][0]["task_id"] == 1
    code, out = cmd(client, "alarm_snooze", kind=HEADS_UP, task_id=1)
    assert code == 200 and "10:05" in out["message"]
    assert state(client)["alarms"]["snoozed"]
    assert cmd(client, "alarm_dismiss", kind=HEADS_UP, task_id=1)[0] == 200   # also cancels the snooze
    st = state(client)["alarms"]
    assert st["ringing"] == [] and st["snoozed"] == []
    code, out = cmd(client, "alarm_dismiss", kind=HEADS_UP, task_id=1)
    assert code == 422 and "isn't ringing" in out["error"]


def test_typed_command_box_runs_the_voice_dialog(client, db_file):
    r = client.post("/api/say", base_url=BASE, headers=H, json={"text": "add a task read for 30 minutes, high priority"}).get_json()
    assert r["done"] and "Added read" in r["messages"][-1]["text"] and r["undo_id"]
    r = client.post("/api/say", base_url=BASE, headers=H, json={"text": "delete all tasks and goals"}).get_json()
    assert r["asking"] and "Say yes or no" in r["question"]
    r = client.post("/api/say", base_url=BASE, headers=H, json={"text": "no", "conv": r["conv"]}).get_json()
    assert r["done"]
    with fresh_session(db_file) as s:
        assert s.query(Task).count() == 1           # nothing deleted without a yes
    r = client.post("/api/say", base_url=BASE, headers=H, json={"text": "add a task call mom", "confidence": 0.3}).get_json()
    assert "did nothing" in r["messages"][-1]["text"]   # low confidence never acts


# ======================= local only =======================

@pytest.mark.parametrize("base", ["http://evil.example", "http://192.168.1.20:3000", "http://127.0.0.1:4000"])
def test_requests_for_other_hosts_are_refused(client, base):
    assert client.get("/api/state", base_url=base).status_code == 403


def test_foreign_origins_and_missing_header_are_refused(client):
    assert client.post("/api/command", base_url=BASE, headers={**H, "Origin": "http://evil.example"},
                       json={"cmd": "add_task", "args": {}}).status_code == 403
    assert client.post("/api/command", base_url=BASE, json={"cmd": "add_task", "args": {}}).status_code == 403
    assert client.post("/api/command", base_url=BASE, headers={**H, "Sec-Fetch-Site": "cross-site"},
                       json={"cmd": "add_task", "args": {}}).status_code == 403
    assert client.get("/api/events", base_url=BASE, headers={"Origin": "http://evil.example"}).status_code == 403
    ok = client.get("/api/state", base_url=BASE, headers={"Origin": BASE})
    assert ok.status_code == 200 and "Access-Control-Allow-Origin" not in ok.headers
    assert "default-src 'self'" in ok.headers["Content-Security-Policy"]


def test_server_listens_on_localhost_only(ctx):
    from tomits.web.__main__ import HOST, build_server, find_port
    port = find_port(3900)
    server = build_server(ctx, port)
    try:
        assert HOST == "127.0.0.1" and server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_busy_port_moves_to_the_next_free_one():
    import socket
    from tomits.web.__main__ import find_port
    port = find_port(3950)
    with socket.socket() as s:
        s.bind(("127.0.0.1", port))
        s.listen()
        assert find_port(port) > port


def test_each_alarm_rings_once_for_its_task(client, ctx):
    from datetime import timedelta
    tid = add(client, "soon", 30, "10:04")
    rung = []
    ctx.alarms._on_alarm = rung.append
    ctx.alarms.check()
    ctx.alarms.check()
    assert [a.kind for a in rung] == ["heads_up"]          # once; again only via Snooze
