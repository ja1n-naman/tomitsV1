"""v1.7: a time written in a task's title, a fixed time owning its slot, and
sacrifices that can't be edited. Logic layer first, then the same behaviour
through the web API, the quick-add box, voice and the terminal."""

import io
import sqlite3
from datetime import date, datetime, time

import pytest
from rich.console import Console

from tomits import planner as pl
from tomits import rescheduler as rs
from tomits import services as svc
from tomits import titletime as TT
from tomits import tracking as tr
from tomits import ui, ui_tracking
from tomits.db import SCHEMA_VERSION, make_session_factory
from tomits.errors import TaskError
from tomits.models import Sacrifice, Task
from tomits.periods import PeriodKind
from tomits.settings import Settings, load_settings, save_settings, validate_task_minutes
from tomits.voice import registry as R
from tomits.web.context import WebApp
from tomits.web.server import create_app

MON = date(2026, 10, 5)                     # a Monday; weeks start on Sunday
NOW = datetime(2026, 10, 5, 8, 0)           # before the 09:00-21:00 day window opens
WINDOW = (time(9, 0), time(21, 0))
DAY = PeriodKind.DAY


def read(title, today=MON, window=WINDOW, ampm=None):
    return TT.read(title, today, window, ampm=ampm)


def add(s, title, minutes=None, day=MON, now=NOW, **kw):
    return svc.add_task(s, title, minutes, planned_for=day, today=MON, now=now, window=WINDOW, **kw)


def auto(s, title, start, minutes=60, day=MON, priority=3):
    """A task the planner placed (unpinned, may be shifted)."""
    t = svc.add_task(s, title, minutes, planned_for=day, today=MON, now=NOW, priority=priority)
    t.start_time, t.placement, t.plan_reason = start, "auto", "first free slot, by priority"
    s.commit()
    return t


# ======================= reading the time =======================

@pytest.mark.parametrize("title,start,clean", [
    ("gym 11pm", time(23, 0), "gym"),
    ("gym 11 pm", time(23, 0), "gym"),
    ("gym 11:30 pm", time(23, 30), "gym"),
    ("gym 11:30pm", time(23, 30), "gym"),
    ("gym 7.15 a.m.", time(7, 15), "gym"),
    ("standup 23:00", time(23, 0), "standup"),
    ("standup 07:30", time(7, 30), "standup"),
    ("call at 17", time(17, 0), "call"),
    ("call at 0", time(0, 0), "call"),
    ("lunch at noon", time(12, 0), "lunch"),
    ("lunch noon", time(12, 0), "lunch"),
    ("call mom @ 4pm", time(16, 0), "call mom"),
    ("Gym - 7pm", time(19, 0), "Gym"),
    ("team call (2pm)", time(14, 0), "team call"),
    ("Review, 6pm, notes", time(18, 0), "Review, notes"),
])
def test_each_clear_time_format(title, start, clean):
    r = read(title)
    assert (r.start, r.title, r.range_minutes) == (start, clean, None)


@pytest.mark.parametrize("title,start,minutes,clean", [
    ("yoga 7 to 8 pm", time(19, 0), 60, "yoga"),
    ("yoga 7-8pm", time(19, 0), 60, "yoga"),
    ("yoga 7pm to 8:30pm", time(19, 0), 90, "yoga"),
    ("run from 6:30 to 7:15", time(18, 30), 45, "run"),      # unclear am/pm: the day window picks pm
    ("run from 06:30 to 07:15", time(6, 30), 45, "run"),
    ("call between 2 and 3 pm", time(14, 0), 60, "call"),
    ("study 11 to 1 pm", time(11, 0), 120, "study"),        # 11 am, so it ends after it starts
    ("study 10 am to 2", time(10, 0), 240, "study"),
    ("read 10pm to midnight", time(22, 0), 120, "read"),
])
def test_ranges_set_start_and_length(title, start, minutes, clean):
    r = read(title)
    assert (r.start, r.range_minutes, r.title) == (start, minutes, clean)


@pytest.mark.parametrize("title", [
    "read 10 pages", "chapter 5", "pages 10 to 20", "chapters 5-7", "verse 3:16", "look at 3 options",
    "5 km run", "version 1.5", "plan 2026-10-05", "work until 5pm", "finish before 6pm", "midnight snack",
    "top 10 at work", "buy 2 apples", "call 3 people", "",
])
def test_ordinary_numbers_are_not_times(title):
    assert read(title) is None


def test_bare_number_after_at_counts_only_when_it_looks_like_a_time():
    assert read("meet at 5 tomorrow").start == time(17, 0)
    assert read("meet at 5, then lunch").start == time(17, 0)
    assert read("look at 5 options") is None


# ---------- am / pm ----------

def test_unclear_am_pm_uses_the_day_window():
    assert read("call at 5").start == time(17, 0)          # 05:00 is outside 09:00-21:00
    assert read("call at 9").start == time(9, 0)           # 21:00 is the window's end
    assert read("call at 8").start == time(20, 0)
    assert read("call at 5").ampm_how == "day window"


def test_both_readings_fit_asks_and_answer_settles_it():
    wide = (time(6, 0), time(23, 0))
    with pytest.raises(TT.AmbiguousTime) as err:
        read("call at 7", window=wide)
    assert [v for _, v in err.value.choices] == ["am", "pm"]
    assert "7:00 am" in err.value.question and "7:00 pm" in err.value.question
    assert read("call at 7", window=wide, ampm="am").start == time(7, 0)
    assert read("call at 7", window=wide, ampm="pm").start == time(19, 0)


def test_neither_reading_fits_asks_too():
    with pytest.raises(TT.AmbiguousTime):
        read("call at 6", window=(time(9, 0), time(17, 0)))


def test_unclear_range_asks_when_both_fit():
    with pytest.raises(TT.AmbiguousTime) as err:
        read("run 6:30-7:15", window=(time(5, 0), time(23, 0)))
    assert "6:30 am to 7:15 am" in err.value.question


def test_tonight_means_pm():
    r = read("gym at 7 tonight", window=(time(6, 0), time(23, 0)))
    assert (r.start, r.day) == (time(19, 0), MON)


# ---------- day words ----------

@pytest.mark.parametrize("title,expected", [
    ("gym today 6pm", MON),
    ("gym tomorrow at 6pm", date(2026, 10, 6)),
    ("gym on friday at 6pm", date(2026, 10, 9)),
    ("gym this friday 6pm", date(2026, 10, 9)),
    ("gym monday 6pm", MON),                              # the coming Monday: today
    ("gym next monday 6pm", date(2026, 10, 12)),
    ("gym sunday 6pm", date(2026, 10, 11)),
    ("gym next sunday 6pm", date(2026, 10, 11)),          # weeks start Sunday: the first Sunday after today
])
def test_day_words(title, expected):
    r = read(title)
    assert (r.day, r.title) == (expected, "gym")


def test_next_sunday_on_a_sunday_is_a_week_later():
    assert read("gym next sunday 6pm", today=date(2026, 10, 4)).day == date(2026, 10, 11)
    assert read("gym sunday 6pm", today=date(2026, 10, 4)).day == date(2026, 10, 4)


def test_a_day_word_without_a_time_changes_nothing(session):
    assert read("call tomorrow") is None
    t = add(session, "call tomorrow", 30)
    assert (t.title, t.start_time, t.planned_for, t.understood) == ("call tomorrow", None, MON, None)


def test_possessive_day_word_stays_in_the_title():
    assert read("Today's standup at 9am").title == "Today's standup"


def test_only_a_time_is_refused():
    with pytest.raises(TaskError, match="only a time"):
        read("7pm")


# ======================= adding a task =======================

def test_time_in_title_becomes_a_fixed_start_and_is_taken_out(session):
    t = add(session, "gym at 7pm")
    assert (t.title, t.title_typed, t.start_time, t.duration_min, t.placement) == (
        "gym", "gym at 7pm", time(19, 0), 30, "fixed")
    assert t.understood.startswith("Read from the title: 19:00-19:30 today, 30m (default length)")
    assert "'at 7pm' moved out of the title" in t.understood


def test_no_time_in_title_changes_nothing_and_the_planner_places_it(session):
    t = add(session, "read 10 pages", 45)
    assert (t.title, t.title_typed, t.start_time, t.placement, t.understood) == ("read 10 pages", None, None, None, None)
    result = pl.plan_day(session, MON, WINDOW, now=NOW)
    assert t in result.placed and t.start_time == time(9, 0)


def test_no_time_and_no_duration_still_needs_a_duration(session):
    with pytest.raises(TaskError, match="duration"):
        add(session, "read 10 pages")


def test_default_length_is_a_setting(session):
    t = add(session, "gym at 7pm", default_minutes=45)
    assert t.duration_min == 45
    with pytest.raises(TaskError):
        validate_task_minutes(0)
    assert load_settings(_settings_file(session)).default_task_minutes == 30


def _settings_file(session):
    from pathlib import Path
    return Path(str(session.bind.url.database)).with_name("settings.json")


def test_range_sets_the_length_and_a_given_duration_wins(session):
    a = add(session, "yoga 7 to 8 pm")
    b = add(session, "swim 9 to 10 pm", 20)
    assert (a.duration_min, b.duration_min) == (60, 20)
    assert "20m (the length you gave)" in b.understood


def test_date_in_title_puts_the_task_on_that_day(session):
    t = add(session, "dentist tomorrow at 11am")
    assert (t.title, t.planned_for, t.start_time) == ("dentist", date(2026, 10, 6), time(11, 0))
    assert "tomorrow" in t.understood


def test_without_a_date_the_task_goes_on_the_day_being_added_to(session):
    t = add(session, "gym at 7pm", day=date(2026, 10, 8))
    assert t.planned_for == date(2026, 10, 8)


def test_start_field_wins_and_the_title_is_left_alone(session):
    t = svc.add_task(session, "gym at 7pm", 30, planned_for=MON, start_time=time(18, 0), today=MON, now=NOW)
    assert (t.title, t.start_time, t.title_typed) == ("gym at 7pm", time(18, 0), None)


def test_past_time_is_added_with_a_notice(session):
    t = add(session, "gym at 7am", now=datetime(2026, 10, 5, 12, 0))
    assert t.start_time == time(7, 0) and t.id
    assert "07:00 today has already passed; the task was added anyway" in t.understood


def test_range_past_midnight_ends_at_midnight_and_never_overlaps_tomorrow(session):
    early = svc.add_task(session, "early", 60, planned_for=date(2026, 10, 6), start_time=time(0, 0), today=MON, now=NOW)
    t = add(session, "party 11pm to 1am")
    assert (t.start_time, t.duration_min, t.end_at) == (time(23, 0), 60, datetime(2026, 10, 6, 0, 0))
    assert "ends at midnight" in t.understood
    assert early.start_at >= t.end_at                     # back to back with tomorrow's first task


def test_single_time_near_midnight_is_cut_at_midnight(session):
    t = add(session, "read at 23:45")
    assert t.duration_min == 15 and "ends at midnight" in t.understood


def test_ambiguous_time_asks_before_saving(session):
    with pytest.raises(svc.AmbiguousTime):
        svc.add_task(session, "call at 7", None, planned_for=MON, today=MON, now=NOW, window=(time(6, 0), time(23, 0)))
    assert svc.tasks_for_day(session, MON) == []
    t = svc.add_task(session, "call at 7", None, planned_for=MON, today=MON, now=NOW,
                     window=(time(6, 0), time(23, 0)), ampm="pm")
    assert t.start_time == time(19, 0) and t.title_typed == "call at 7"


def test_keep_title_as_typed_restores_the_original_text(session):
    t = add(session, "gym tomorrow at 7pm")
    t = svc.restore_typed_title(session, t.id)
    assert (t.title, t.title_typed, t.start_time, t.placement) == ("gym tomorrow at 7pm", None, None, None)
    with pytest.raises(TaskError, match="no time read"):
        svc.restore_typed_title(session, t.id)


def test_several_tasks_read_each_title(session):
    tasks = svc.plan_day(session, MON, [svc.TaskDraft("gym 7-8pm", None), svc.TaskDraft("read 10 pages", 30),
                                        svc.TaskDraft("call tomorrow at 10am", None)], today=MON, now=NOW, window=WINDOW)
    by = {t.title: t for t in tasks}
    assert (by["gym"].start_time, by["gym"].duration_min) == (time(19, 0), 60)
    assert by["read 10 pages"].start_time is None
    assert (by["call"].planned_for, by["call"].start_time) == (date(2026, 10, 6), time(10, 0))


def test_several_tasks_ask_am_pm_for_the_right_line(session):
    with pytest.raises(svc.AmbiguousTime) as err:
        svc.plan_day(session, MON, [svc.TaskDraft("a", 30), svc.TaskDraft("call at 7", None)], today=MON, now=NOW,
                     window=(time(6, 0), time(23, 0)))
    assert err.value.line == 1


# ======================= a fixed time owns its slot =======================

def test_fixed_slot_is_never_moved_by_the_planner(session):
    t = add(session, "gym at 10am")
    other = svc.add_task(session, "read", 60, planned_for=MON, today=MON)
    result = pl.plan_day(session, MON, WINDOW, now=NOW)
    assert t.start_time == time(10, 0) and t in result.kept and other.start_time == time(9, 0)
    assert t.priority == 3                               # priority untouched


def test_fixed_slot_is_never_moved_by_rescheduling(session):
    t = add(session, "gym at 10am")
    failed = svc.add_task(session, "report", 60, planned_for=MON, start_time=time(9, 0), today=MON, now=NOW)
    svc.fail_task(session, failed.id, "too tired")
    prop = rs.build_for_closed(session, failed.id, WINDOW, now=datetime(2026, 10, 5, 9, 30))
    rs.accept(session, prop, now=datetime(2026, 10, 5, 9, 30))
    assert t.start_time == time(10, 0) and all(m.task_id != t.id for m in prop.moves)


def test_overlapping_a_planned_task_gives_a_proposal_not_a_silent_move(session):
    flex = auto(session, "read", time(10, 0))
    with pytest.raises(svc.SlotTaken) as err:
        add(session, "gym at 10am")
    assert "overlaps 'read' (10:00-11:00)" in str(err.value)
    assert [t.title for t in svc.tasks_for_day(session, MON)] == ["read"] and flex.start_time == time(10, 0)
    prop = rs.build(session, ("claim", err.value.claim, None), WINDOW, now=NOW)
    shift = [m for m in prop.moves if m.kind == "shift"][0]
    assert shift.task_id == flex.id and shift.to_start == time(9, 0)      # first free slot, by priority
    assert shift.reason.startswith("moved from 10 am: 'gym' has its own time 10:00-10:30")
    log = rs.accept(session, prop, now=NOW)
    gym = [t for t in svc.tasks_for_day(session, MON) if t.title == "gym"][0]
    assert (gym.start_time, gym.placement, gym.title_typed) == (time(10, 0), "fixed", "gym at 10am")
    assert flex.start_time == time(9, 0)
    rs.undo_last(session)                               # undo: the new task goes, the planned one comes back
    assert [(t.title, t.start_time) for t in svc.tasks_for_day(session, MON)] == [("read", time(10, 0))]
    assert log.id


def test_rejecting_the_proposal_changes_nothing(session):
    auto(session, "read", time(10, 0))
    with pytest.raises(svc.SlotTaken):
        add(session, "gym at 10am")
    assert [(t.title, t.start_time) for t in svc.tasks_for_day(session, MON)] == [("read", time(10, 0))]


def test_two_fixed_tasks_overlapping_is_refused_naming_both(session):
    add(session, "call at 10am")
    with pytest.raises(TaskError) as err:
        add(session, "gym 10:15am")
    msg = str(err.value)
    assert not isinstance(err.value, svc.SlotTaken)
    assert "'gym' (10:15-10:45) overlaps task 1 'call' (10:00-10:30)" in msg and "Neither task is moved" in msg
    pinned = auto(session, "read", time(12, 0))
    svc.set_start_time(session, pinned.id, time(12, 0), now=NOW)       # pinned
    with pytest.raises(TaskError, match="'read' is pinned"):
        add(session, "lunch at noon")


def test_back_to_back_with_a_fixed_task_is_fine(session):
    add(session, "call 10-11am")
    t = add(session, "gym at 11am")
    assert t.start_time == time(11, 0)


def test_a_started_planned_task_is_not_moved(session):
    auto(session, "read", time(10, 0))
    with pytest.raises(TaskError, match="has already started"):
        add(session, "gym at 10:30am", now=datetime(2026, 10, 5, 10, 15))


# ---------- edits ----------

def test_editing_a_title_reads_its_time(session):
    t = svc.add_task(session, "gym", 30, planned_for=MON, today=MON, now=NOW)
    t = svc.update_task(session, t.id, title="gym at 6pm", today=MON, now=NOW, window=WINDOW)
    assert (t.title, t.start_time, t.placement, t.title_typed) == ("gym", time(18, 0), "fixed", "gym at 6pm")
    assert t.understood


def test_editing_with_an_unchanged_duration_lets_the_range_set_it(session):
    t = svc.add_task(session, "yoga", 30, planned_for=MON, today=MON, now=NOW)
    t = svc.update_task(session, t.id, title="yoga 6 to 7:30 pm", duration_min=30, today=MON, now=NOW, window=WINDOW)
    assert t.duration_min == 90
    u = svc.add_task(session, "swim", 30, planned_for=MON, today=MON, now=NOW)
    u = svc.update_task(session, u.id, title="swim 8 to 9 pm", duration_min=40, today=MON, now=NOW, window=WINDOW)
    assert u.duration_min == 40                                   # a changed duration was given: it wins


def test_editing_into_a_planned_task_gives_a_proposal(session):
    auto(session, "read", time(10, 0))
    t = svc.add_task(session, "gym", 30, planned_for=MON, today=MON, now=NOW)
    with pytest.raises(svc.SlotTaken) as err:
        svc.update_task(session, t.id, title="gym at 10am", today=MON, now=NOW, window=WINDOW)
    session.expire_all()
    assert svc.get_task(session, t.id).title == "gym"            # nothing saved yet
    prop = rs.build(session, ("claim", err.value.claim, None), WINDOW, now=NOW)
    rs.accept(session, prop, now=NOW)
    t = svc.get_task(session, t.id)
    assert (t.title, t.start_time, t.title_typed) == ("gym", time(10, 0), "gym at 10am")
    rs.undo_last(session)
    t = svc.get_task(session, t.id)
    assert (t.title, t.start_time, t.title_typed) == ("gym", None, None)


def test_editing_into_a_fixed_task_is_refused(session):
    add(session, "call at 10am")
    t = svc.add_task(session, "gym", 30, planned_for=MON, today=MON, now=NOW)
    with pytest.raises(TaskError, match="Neither task is moved"):
        svc.update_task(session, t.id, title="gym at 10am", today=MON, now=NOW, window=WINDOW)


def test_moving_a_time_uses_the_same_rules(session):
    auto(session, "read", time(10, 0))
    t = svc.add_task(session, "gym", 30, planned_for=MON, today=MON, now=NOW)
    with pytest.raises(svc.SlotTaken):
        svc.set_start_time(session, t.id, time(10, 0), now=NOW)
    with pytest.raises(svc.SlotTaken):
        svc.move_to_day(session, t.id, MON, time(10, 0), today=MON, now=NOW)


# ======================= sacrifices =======================

def test_sacrifice_add_mark_made_and_delete(session):
    item = tr.add_sacrifice(session, DAY, MON, "no phone", today=MON)
    made = tr.mark_sacrifice_made(session, item.id, today=MON)
    assert (made.text, made.status) == ("no phone", "made")
    with pytest.raises(TaskError, match="already marked as made"):
        tr.mark_sacrifice_made(session, item.id, today=MON)
    tr.remove_sacrifice(session, item.id, today=MON)
    assert session.query(Sacrifice).count() == 0


def test_sacrifices_lock_when_the_period_ends(session):
    item = tr.add_sacrifice(session, DAY, MON, "no phone", today=MON)
    for action in (lambda: tr.mark_sacrifice_made(session, item.id, today=date(2026, 10, 6)),
                   lambda: tr.remove_sacrifice(session, item.id, today=date(2026, 10, 6))):
        with pytest.raises(TaskError, match="has ended; its sacrifices are read-only"):
            action()
    session.expire_all()
    assert (session.get(Sacrifice, item.id).text, session.get(Sacrifice, item.id).status) == ("no phone", "planned")


def test_sacrifice_editing_is_gone_everywhere():
    assert not hasattr(tr, "update_sacrifice")
    names = {c.name for c in R.REGISTRY}
    assert "change_sacrifice" not in names and {"made_sacrifice", "remove_sacrifice"} <= names
    assert not R.get("remove_sacrifice").risky and not R.get("remove_sacrifice").web_confirm
    assert not hasattr(ui_tracking.TrackingScreen, "change_sacrifice")
    for cmd in R.REGISTRY:
        for pat in cmd.patterns:
            assert "rename (?:the )?sacrifice" not in pat


# ======================= migration =======================

def test_v6_database_gets_title_typed_with_a_backup(tmp_path):
    path = tmp_path / "old.db"
    make_session_factory(path)                          # current schema
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE tasks_old AS SELECT * FROM tasks;
        DROP TABLE tasks;
        CREATE TABLE tasks AS SELECT id, title, purpose, duration_min, planned_for, position, status, goal_id,
          created_at, closed_at, start_time, heads_up_sent, end_alert_sent, priority, placement, plan_reason,
          rescheduled_from_id, reschedule_count, move_reason FROM tasks_old WHERE 0;
        DROP TABLE tasks_old;
        INSERT INTO tasks (id, title, duration_min, planned_for, position, status, heads_up_sent, end_alert_sent,
          priority, reschedule_count) VALUES (1, 'kept', 30, '2026-10-05', 1, 'pending', 0, 0, 3, 0);
        INSERT INTO period_entries (id, kind, start, created_at) VALUES (1, 'day', '2026-10-05', '2026-10-05 08:00');
        INSERT INTO sacrifices (id, entry_id, text, status, created_at) VALUES (1, 1, 'kept too', 'planned', '2026-10-05 08:00');
        PRAGMA user_version = 6;
    """)
    c.commit()
    c.close()
    Session = make_session_factory(path)
    assert list(tmp_path.glob("old.db.bak-v6-*"))
    with Session() as s:
        t = s.get(Task, 1)
        assert (t.title, t.title_typed) == ("kept", None)
        assert [(x.text, x.status) for x in s.query(Sacrifice)] == [("kept too", "planned")]
    c = sqlite3.connect(path)
    assert c.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION >= 7   # later versions migrate further
    c.close()


# ======================= the same through every surface =======================

BASE = "http://127.0.0.1:3000"
H = {"X-Tomits": "1"}


@pytest.fixture
def web(db_file):
    ctx = WebApp(db_file, clock=lambda: NOW, start_threads=False)
    ctx.settings.llm_enabled = False
    client = create_app(ctx, 3000).test_client()
    yield ctx, client
    ctx.stop()


def cmd(client, name, **args):
    r = client.post("/api/command", base_url=BASE, headers=H, json={"cmd": name, "args": args})
    return r.status_code, r.get_json()


def say(client, text):
    return client.post("/api/say", base_url=BASE, headers=H, json={"text": text}).get_json()


def web_tasks(ctx, day=MON):
    with ctx.Session() as s:
        return [(t.title, t.start_time, t.duration_min, t.placement) for t in svc.tasks_for_day(s, day)]


def test_web_form_reads_the_title_and_offers_keep_as_typed(web):
    ctx, client = web
    code, out = cmd(client, "add_task", title="gym 7 to 8 pm", duration="", date=MON.isoformat())
    assert code == 200 and out["understood"].startswith("Read from the title: 19:00-20:00 today, 1h (from the range)")
    assert web_tasks(ctx) == [("gym", time(19, 0), 60, "fixed")]
    code, out = cmd(client, "keep_typed_title", id=out["task_id"])
    assert code == 200 and web_tasks(ctx) == [("gym 7 to 8 pm", None, 60, None)]


def test_web_undo_restores_the_typed_title(web):
    ctx, client = web
    t = svc.add_task(ctx.Session(), "gym", 30, planned_for=MON, today=MON, now=NOW)
    code, out = cmd(client, "edit_task", id=t.id, title="gym at 6pm", duration="30")
    assert code == 200 and web_tasks(ctx) == [("gym", time(18, 0), 30, "fixed")]
    code, _ = cmd(client, "undo_action", id=out["undo_id"])
    assert code == 200 and web_tasks(ctx) == [("gym", None, 30, None)]


def test_web_asks_am_or_pm_and_saves_nothing_until_answered(web):
    ctx, client = web
    ctx.settings.day_start, ctx.settings.day_end = "06:00", "23:00"
    code, out = cmd(client, "add_task", title="call at 7", date=MON.isoformat())
    assert code == 200 and out["needs_choice"] and out["field"] == "ampm" and not out["saved"]
    assert [c["value"] for c in out["choices"]] == ["am", "pm"] and web_tasks(ctx) == []
    code, out = cmd(client, "add_task", title="call at 7", date=MON.isoformat(), ampm="pm")
    assert code == 200 and web_tasks(ctx) == [("call", time(19, 0), 30, "fixed")]
    code, out = cmd(client, "add_several", date=MON.isoformat(), lines=[{"title": ""}, {"title": "swim at 8"}])
    assert out["needs_choice"] and out["line"] == 1


def test_web_overlap_with_a_planned_task_opens_a_proposal(web):
    ctx, client = web
    with ctx.Session() as s:
        auto(s, "read", time(10, 0))
    code, out = cmd(client, "add_task", title="gym at 10am", date=MON.isoformat())
    assert code == 200 and out["proposal_id"] and not out["saved"] and "placed by the planner" in out["message"]
    st = client.get("/api/state", base_url=BASE).get_json()
    prop = [p for p in st["proposals"] if p["id"] == out["proposal_id"]][0]
    assert prop["trigger"] == "claim" and [m["kind"] for m in prop["moves"]] == ["claim", "shift"]
    code, acc = cmd(client, "proposal_answer", id=out["proposal_id"], answer="accept")
    assert code == 200 and web_tasks(ctx) == [("read", time(9, 0), 60, "auto"), ("gym", time(10, 0), 30, "fixed")]
    cmd(client, "undo_action", id=acc["undo_id"])
    assert web_tasks(ctx) == [("read", time(10, 0), 60, "auto")]


def test_web_two_fixed_tasks_overlapping_is_refused(web):
    ctx, client = web
    cmd(client, "add_task", title="call at 10am", date=MON.isoformat())
    code, out = cmd(client, "add_task", title="gym 10:15am", date=MON.isoformat())
    assert code == 422 and "'call' (10:00-10:30)" in out["error"] and "Neither task is moved" in out["error"]


def test_web_move_onto_a_planned_task_opens_a_proposal(web):
    ctx, client = web
    with ctx.Session() as s:
        auto(s, "read", time(10, 0))
        t = svc.add_task(s, "gym", 30, planned_for=MON, today=MON, now=NOW)
    code, out = cmd(client, "move_task", id=t.id, mode="time", start="10:00")
    assert code == 200 and out["proposal_id"]


def test_quick_add_box_reads_the_time_like_the_form(web):
    ctx, client = web
    out = say(client, "add a task gym at 7 pm normal priority")
    assert out["done"] and web_tasks(ctx) == [("gym", time(19, 0), 30, "fixed")]
    assert any(m["text"].startswith("Read from the title") for m in out["messages"])


def test_web_sacrifices_made_and_deleted_without_confirmation(web):
    ctx, client = web
    cmd(client, "add_sacrifice", kind="day", start=MON.isoformat(), text="no phone")
    with ctx.Session() as s:
        sid = s.query(Sacrifice).one().id
    code, out = cmd(client, "made_sacrifice", id=sid)
    assert code == 200
    with ctx.Session() as s:
        assert (s.get(Sacrifice, sid).text, s.get(Sacrifice, sid).status) == ("no phone", "made")
    code, out = cmd(client, "remove_sacrifice", id=sid)
    assert code == 200 and not out.get("needs_confirm") and out["undo_id"]
    cmd(client, "undo_action", id=out["undo_id"])
    with ctx.Session() as s:
        assert s.get(Sacrifice, sid).text == "no phone"


def test_web_sacrifices_lock_after_the_period(web):
    ctx, client = web
    with ctx.Session() as s:
        item = tr.add_sacrifice(s, DAY, date(2026, 10, 4), "old", today=date(2026, 10, 4))
    for name in ("made_sacrifice", "remove_sacrifice"):
        code, out = cmd(client, name, id=item.id)
        assert code == 422 and "read-only" in out["error"]


def test_removed_sacrifice_edit_routes_are_gone(web):
    ctx, client = web
    code, out = cmd(client, "change_sacrifice", id=1, text="x")
    assert code == 422 and "Unknown action" in out["error"]


def test_default_length_setting_through_the_web(web):
    ctx, client = web
    code, _ = cmd(client, "settings", default_task_minutes="45")
    assert code == 200 and load_settings(ctx.settings_file).default_task_minutes == 45
    cmd(client, "add_task", title="gym at 7pm", date=MON.isoformat())
    assert web_tasks(ctx)[0][2] == 45
    code, out = cmd(client, "settings", default_task_minutes="0")
    assert code == 422


# ---------- voice ----------

class ScriptedIO:
    def __init__(self, utterances):
        self.queue = list(utterances)
        self.said = []

    def say(self, text):
        self.said.append(text)

    def listen(self, prompt=None, grammar=None):
        from tomits.voice.dialog import Heard
        if prompt:
            self.said.append(prompt)
        return Heard(self.queue.pop(0) if self.queue else "", 1.0)

    def show(self, text):
        self.said.append(text)


class Quiet:
    def notify(self, *a, **k):
        pass

    def play_burst(self):
        pass


@pytest.fixture
def term(db_file, monkeypatch):
    out = io.StringIO()
    monkeypatch.setattr(ui, "console", Console(file=out, width=200))
    monkeypatch.setattr(ui_tracking, "console", Console(file=out, width=200))
    monkeypatch.setattr("tomits.ui_common.console", Console(file=io.StringIO()))
    a = ui.App(db_file, notifier=Quiet(), clock=lambda: NOW, player=Quiet())
    a.out = out
    return a


def talk(app, *utterances):
    io_ = ScriptedIO(utterances)
    app.voice_turn(io_)
    return io_


def term_tasks(app, day=MON):
    with app.Session() as s:
        return [(t.title, t.start_time, t.duration_min, t.placement) for t in svc.tasks_for_day(s, day)]


def test_voice_reads_the_time_and_does_not_ask_for_a_length(term):
    io_ = talk(term, "add a task gym tomorrow at 7 pm normal priority")
    assert term_tasks(term, date(2026, 10, 6)) == [("gym", time(19, 0), 30, "fixed")]
    assert not any("How long" in x for x in io_.said)


def test_voice_asks_am_or_pm_when_both_fit(term):
    term.settings.day_start, term.settings.day_end = "06:00", "23:00"
    talk(term, "add a task call at 7 normal priority", "pm")
    assert term_tasks(term) == [("call", time(19, 0), 30, "fixed")]


def test_voice_overlap_reads_the_proposal_and_accepts(term):
    with term.Session() as s:
        auto(s, "read", time(10, 0))
    io_ = talk(term, "add a task gym at 10 am normal priority", "yes")
    assert any("Here's the new plan" in x and "gym takes today at 10" in x for x in io_.said)
    assert term_tasks(term) == [("read", time(9, 0), 60, "auto"), ("gym", time(10, 0), 30, "fixed")]


def test_voice_sacrifice_made_and_delete_without_a_yes(term):
    with term.Session() as s:
        tr.add_sacrifice(s, DAY, MON, "no phone", today=MON)
    talk(term, "mark sacrifice no phone as made")
    io_ = talk(term, "delete the sacrifice no phone")
    assert io_.said[-1] == "Deleted the sacrifice no phone."
    with term.Session() as s:
        assert s.query(Sacrifice).count() == 0


def test_voice_keep_title_as_typed(term):
    talk(term, "add a task gym at 7 pm normal priority")
    talk(term, "keep the gym title as typed")
    assert term_tasks(term) == [("gym at 7 pm", None, 30, None)]


def test_voice_default_length(term):
    talk(term, "set the default task length to 45 minutes")
    assert term.settings.default_task_minutes == 45


# ---------- terminal ----------

def _answers(monkeypatch, *answers):
    it = iter(answers)
    monkeypatch.setattr(ui.Prompt, "ask", classmethod(lambda cls, *a, **k: next(it)))


def test_terminal_add_reads_the_title(term, monkeypatch):
    # title, duration (blank = from the title), priority, purpose, goal
    _answers(monkeypatch, "gym 7 to 8 pm", "", "3", "", "")
    term.add_now()
    assert term_tasks(term) == [("gym", time(19, 0), 60, "fixed")]
    assert "Read from the title" in term.out.getvalue()


def test_terminal_change_title_reads_the_time(term, monkeypatch):
    with term.Session() as s:
        t = svc.add_task(s, "gym", 30, planned_for=MON, today=MON, now=NOW)
    _answers(monkeypatch, str(t.id), "", "")
    monkeypatch.setattr(ui, "ask_text", lambda *a, **k: "gym at 6pm")
    term.change_task()
    assert term_tasks(term) == [("gym", time(18, 0), 30, "fixed")]


def test_terminal_sacrifice_made_and_delete(term, monkeypatch):
    with term.Session() as s:
        item = tr.add_sacrifice(s, DAY, MON, "no phone", today=MON)
    screen = ui_tracking.TrackingScreen(term)
    _answers(monkeypatch, str(item.id))
    screen.sacrifice_made()
    with term.Session() as s:
        assert s.get(Sacrifice, item.id).status == "made"
    _answers(monkeypatch, str(item.id))
    screen.remove_sacrifice()
    with term.Session() as s:
        assert s.query(Sacrifice).count() == 0
