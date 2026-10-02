"""v1.3 day planner: priority order, fixed tasks stay, overflow, history,
pinning, manual moves, window edges. Fake history is inserted directly."""

import io
import sqlite3
from datetime import date, datetime, time, timedelta

import pytest
from rich.console import Console

from tomits import planner as pl
from tomits import services as svc
from tomits import tracking as tr
from tomits import ui
from tomits.db import make_session_factory
from tomits.errors import TaskError
from tomits.models import Placement, Task, TaskStatus
from tomits.periods import PeriodKind
from tomits.settings import Settings, load_settings, save_settings, validate_window

DAY = date(2026, 10, 5)                     # a Monday in the future of the fake history
WINDOW = (time(9, 0), time(21, 0))
BEFORE = datetime(2026, 10, 4, 22, 0)       # "now" the evening before: whole DAY is plannable


def add(s, title, minutes, priority=3, start=None, goal_id=None, day=DAY):
    return svc.add_task(s, title, minutes, goal_id=goal_id, planned_for=day, start_time=start,
                        priority=priority, today=day)


def past(s, title, day, start, status="done", minutes=30, goal_id=None):
    """A finished task on a past day (bypasses the rules on purpose)."""
    t = Task(title=title, duration_min=minutes, planned_for=day, start_time=start, position=0,
             status=status, goal_id=goal_id, priority=3, placement=Placement.FIXED.value,
             heads_up_sent=True, end_alert_sent=True)
    s.add(t)
    s.commit()
    return t


def plan(s, day=DAY, window=WINDOW, now=BEFORE):
    return pl.plan_day(s, day, window, now=now)


def times(tasks):
    return [(t.title, t.start_time.strftime("%H:%M") if t.start_time else None) for t in tasks]


def assert_no_overlaps(s, day=DAY):
    busy = [t for t in svc.tasks_for_day(s, day) if t.start_time and t.status in svc.BLOCKING_STATUSES]
    for i, a in enumerate(busy):
        for b in busy[i + 1:]:
            assert not (a.start_at < b.end_at and b.start_at < a.end_at), (a.title, b.title)


# ---------- priority ordering (no history) ----------

def test_priority_first_then_shorter_first(session):
    add(session, "low", 60, priority=4)
    add(session, "urgent", 60, priority=1)
    add(session, "high long", 60, priority=2)
    add(session, "high short", 30, priority=2)
    add(session, "normal", 30, priority=3)
    r = plan(session)
    assert times(r.placed) == [("urgent", "09:00"), ("high short", "10:00"), ("high long", "10:30"),
                               ("normal", "11:30"), ("low", "12:00")]
    assert all(t.placement == "auto" and t.plan_reason == "no history: placed by priority" for t in r.placed)
    assert_no_overlaps(session)


def test_priority_parsing():
    assert [svc.parse_priority(x) for x in ("1", "u", "High", "n", "4", "low")] == [1, 1, 2, 3, 4, 4]
    with pytest.raises(TaskError):
        svc.parse_priority("5")


# ---------- fixed tasks stay put ----------

def test_fixed_tasks_never_move_and_gaps_are_filled(session):
    fixed = add(session, "meeting", 60, start=time(10, 0))
    a = add(session, "a", 60, priority=1)
    b = add(session, "b", 45, priority=2)
    r = plan(session)
    assert fixed.start_time == time(10, 0) and fixed.placement == "fixed"
    assert times([a, b]) == [("a", "09:00"), ("b", "11:00")]  # 45 min doesn't fit 10:00-10:00; next gap
    assert r.kept == [fixed]
    assert_no_overlaps(session)


def test_fixed_task_alarm_state_untouched(session):
    fixed = add(session, "meeting", 60, start=time(10, 0))
    fixed.heads_up_sent = True
    session.commit()
    add(session, "a", 60)
    plan(session)
    assert fixed.heads_up_sent is True


def test_done_task_blocks_but_failed_task_frees_time(session):
    done = add(session, "done", 60, start=time(9, 0))
    svc.complete_task(session, done.id, today=DAY)
    failed = add(session, "failed", 60, start=time(10, 0))
    svc.fail_task(session, failed.id, "sick")
    a = add(session, "a", 60)
    plan(session)
    assert a.start_time == time(10, 0)


# ---------- overflow ----------

def test_overflow_when_hours_run_out(session):
    window = (time(9, 0), time(12, 0))
    big1 = add(session, "big 1", 120, priority=1)
    big2 = add(session, "big 2", 120, priority=2)
    small = add(session, "small", 30, priority=3)
    tiny_low = add(session, "tiny low", 90, priority=4)
    r = plan(session, window=window)
    assert times(r.placed) == [("big 1", "09:00"), ("small", "11:00")]
    assert [t.title for t in r.overflow] == ["big 2", "tiny low"]  # priority order
    for t in r.overflow:
        assert t.start_time is None and t.status == "pending" and t.placement == "overflow"
    assert big2.plan_reason == "didn't fit: needs 2h, largest free gap 1h"  # 11:00-12:00 when big 2 was tried
    assert [t.id for t in pl.overflow_tasks(session, DAY)] == [big2.id, tiny_low.id]
    assert len(svc.tasks_for_day(session, DAY)) == 4  # nothing deleted


def test_overflow_task_gets_placed_when_room_appears(session):
    window = (time(9, 0), time(10, 0))
    a = add(session, "a", 60, priority=1)
    b = add(session, "b", 60, priority=2)
    plan(session, window=window)
    assert b.placement == "overflow"
    svc.fail_task(session, a.id, "cancelled")
    plan(session, window=window)
    assert b.start_time == time(9, 0) and b.placement == "auto"


# ---------- history ----------

def _gym_history(s, hour=19, n=5, status="done", title="Gym"):
    for i in range(n):
        past(s, title, DAY - timedelta(days=i + 1), time(hour, 0), status)


def test_no_history_fallback_reason(session):
    t = add(session, "brand new thing", 30)
    plan(session)
    assert t.plan_reason == "no history: placed by priority" and t.start_time == time(9, 0)


def test_too_little_history_falls_back(session):
    _gym_history(session, n=pl.HISTORY_MIN_ENTRIES - 1)
    t = add(session, "gym", 60)
    plan(session)
    assert t.start_time == time(9, 0)
    assert t.plan_reason.startswith(f"too little history ({pl.HISTORY_MIN_ENTRIES - 1} similar")


def test_history_places_near_usual_completion_time(session):
    _gym_history(session, hour=19)
    t = add(session, "gym", 60)
    add(session, "other", 30, priority=1)
    plan(session)
    assert t.start_time == time(19, 0)
    assert t.plan_reason == "usually completed around 7 pm (5 done, 0 failed in similar past tasks)"
    assert_no_overlaps(session)


def test_failures_push_away_from_an_hour(session):
    for i in range(3):
        past(session, "run", DAY - timedelta(days=i + 1), time(7, 0), "done")
        past(session, "run", DAY - timedelta(days=i + 10), time(7, 0), "failed")
        past(session, "run", DAY - timedelta(days=i + 20), time(18, 30), "done")
    t = add(session, "Run", 45)
    plan(session, window=(time(6, 0), time(21, 0)))
    assert t.start_time == time(18, 30)
    assert "3 done" not in t.plan_reason  # counts all similar: 6 done, 3 failed
    assert "(6 done, 3 failed" in t.plan_reason


def test_similar_by_goal_even_with_other_titles(session):
    g = tr.create_goal(session, PeriodKind.MONTH, date(2026, 10, 1), "fitness", today=date(2026, 10, 1))
    for i, title in enumerate(["morning jog", "stretching", "yoga"]):
        past(session, title, DAY - timedelta(days=i + 1), time(8, 0), goal_id=g.id)
    t = add(session, "pushups", 20, goal_id=g.id)
    plan(session, window=(time(6, 0), time(21, 0)))
    assert t.start_time == time(8, 0) and "around 8 am" in t.plan_reason


@pytest.mark.parametrize("a,b,similar", [
    ("Read book", "read the book", True),     # 2 of 3 words shared
    ("Gym #2", "gym", True),                  # digits and punctuation ignored
    ("write report", "read report", False),   # 1 of 3 words
    ("Email", "Emails", False),               # different words
])
def test_title_similarity(a, b, similar):
    ta, tb = Task(title=a, goal_id=None), Task(title=b, goal_id=None)
    assert pl.is_similar(ta, tb) is similar


def test_history_target_taken_uses_nearest_free_slot(session):
    _gym_history(session, hour=19)
    add(session, "dinner", 90, start=time(18, 30))  # 18:30-20:00 fixed
    t = add(session, "gym", 60)
    plan(session)
    assert t.start_time == time(20, 0)  # 20:00 is 60 min from 19:00; 17:30 would be 90 min
    assert "nearest free slot 20:00" in t.plan_reason
    assert_no_overlaps(session)


def test_only_past_done_or_failed_timed_tasks_count(session):
    past(session, "gym", DAY - timedelta(days=1), time(19, 0), "skipped")
    past(session, "gym", DAY - timedelta(days=2), time(19, 0), "pending")
    past(session, "gym", DAY + timedelta(days=1), time(19, 0), "done")   # future
    past(session, "gym", DAY - timedelta(days=200), time(19, 0), "done")  # too old
    t = add(session, "gym", 60)
    plan(session)
    assert t.plan_reason == "no history: placed by priority"


def test_usual_order_from_past_days_is_kept(session):
    # 2 past days: email before report. Too few for time preference, enough for order.
    for i in (1, 2):
        past(session, "check email", DAY - timedelta(days=i), time(9, 0))
        past(session, "write report", DAY - timedelta(days=i), time(9, 30))
    report = add(session, "write report", 60, priority=1)   # priority alone would put it first
    email = add(session, "check email", 30, priority=2)
    plan(session)
    assert times([email, report]) == [("check email", "09:00"), ("write report", "09:30")]
    assert "kept before 'write report' as on past days" in email.plan_reason
    assert_no_overlaps(session)


def test_order_needs_enough_days(session):
    past(session, "check email", DAY - timedelta(days=1), time(9, 0))
    past(session, "write report", DAY - timedelta(days=1), time(9, 30))
    report = add(session, "write report", 60, priority=1)
    email = add(session, "check email", 30, priority=2)
    plan(session)
    assert times([report, email]) == [("write report", "09:00"), ("check email", "10:00")]


# ---------- pinning ----------

def test_manual_move_pins_and_survives_replan(session):
    a = add(session, "a", 60, priority=1)
    b = add(session, "b", 60, priority=2)
    plan(session)
    assert b.start_time == time(10, 0)
    svc.set_start_time(session, b.id, time(15, 0))
    assert b.placement == "pinned" and b.plan_reason == "pinned: moved by you"
    add(session, "c", 60, priority=1)  # added on the fly
    plan(session)
    assert b.start_time == time(15, 0) and b.placement == "pinned"
    assert_no_overlaps(session)


def test_move_before_or_after_another_task_pins(session):
    a = add(session, "a", 60, priority=1)
    b = add(session, "b", 30, priority=2)
    c = add(session, "c", 30, priority=3)
    plan(session)  # a 9:00, b 10:00, c 10:30
    svc.move_next_to(session, c.id, a.id, "before")   # 08:30, outside window but a manual choice
    assert (c.start_time, c.placement) == (time(8, 30), "pinned")
    svc.move_next_to(session, a.id, b.id, "after")    # a -> 10:30 (c freed that slot)
    assert a.start_time == time(10, 30)
    plan(session)
    assert (a.start_time, c.start_time) == (time(10, 30), time(8, 30))
    assert_no_overlaps(session)


def test_unpin_hands_task_back_to_planner(session):
    a = add(session, "a", 60)
    plan(session)
    svc.set_start_time(session, a.id, time(15, 0))
    svc.unpin_task(session, a.id)
    assert a.placement == "auto"
    plan(session)
    assert a.start_time == time(9, 0)


def test_unpin_a_fixed_task_too(session):
    f = add(session, "fixed", 60, start=time(14, 0))
    svc.unpin_task(session, f.id)
    plan(session)
    assert (f.start_time, f.placement) == (time(9, 0), "auto")


def test_unpin_refused_for_planner_owned_task(session):
    a = add(session, "a", 60)
    plan(session)
    with pytest.raises(TaskError, match="isn't pinned"):
        svc.unpin_task(session, a.id)


def test_clearing_time_hands_to_planner(session):
    f = add(session, "fixed", 60, start=time(14, 0))
    svc.set_start_time(session, f.id, None)
    assert f.placement is None
    plan(session)
    assert f.placement == "auto"


# ---------- overlapping manual moves: nothing moves silently ----------
# v1.7: a task given its own time owns it. Onto a planner-placed task the
# change waits for a reschedule proposal (SlotTaken); onto a fixed / pinned
# one it is refused. Either way nothing is saved here.

def test_overlapping_manual_move_waits_for_a_proposal(session):
    a = add(session, "a", 60, priority=1)
    b = add(session, "b", 60, priority=2)
    plan(session)
    with pytest.raises(svc.SlotTaken, match="overlaps 'a' \\(09:00-10:00\\)"):
        svc.set_start_time(session, b.id, time(9, 30), now=BEFORE)
    assert (b.start_time, b.placement) == (time(10, 0), "auto")


def test_overlapping_manual_move_onto_a_pinned_task_is_refused(session):
    a = add(session, "a", 60, priority=1)
    b = add(session, "b", 60, priority=2)
    plan(session)
    svc.set_start_time(session, a.id, time(9, 0), now=BEFORE)          # pins a where it is
    with pytest.raises(TaskError, match="overlaps task .* 'a' \\(09:00-10:00\\).*Neither task is moved"):
        svc.set_start_time(session, b.id, time(9, 30), now=BEFORE)
    assert (b.start_time, b.placement) == (time(10, 0), "auto")


def test_overlapping_before_after_move_waits_for_a_proposal(session):
    a = add(session, "a", 60, priority=1)
    b = add(session, "b", 60, priority=2)
    c = add(session, "c", 60, priority=3)
    plan(session)  # a 9, b 10, c 11
    with pytest.raises(svc.SlotTaken, match="overlaps 'b'"):
        svc.move_next_to(session, c.id, a.id, "after", now=BEFORE)  # 10:00 is b's
    assert c.start_time == time(11, 0)


def test_new_timed_task_over_an_auto_placed_task_waits_for_a_proposal(session):
    add(session, "a", 60)
    plan(session)
    with pytest.raises(svc.SlotTaken, match="'a' \\(09:00-10:00\\)"):
        svc.add_task(session, "clash", 30, planned_for=DAY, start_time=time(9, 30), today=DAY, now=BEFORE)
    assert [t.title for t in svc.tasks_for_day(session, DAY)] == ["a"]


# ---------- window edges ----------

def test_task_exactly_filling_the_end_of_window(session):
    window = (time(9, 0), time(10, 0))
    t = add(session, "exact", 60)
    plan(session, window=window)
    assert t.start_time == time(9, 0) and t.end_at.time() == time(10, 0)


def test_one_minute_too_long_does_not_fit(session):
    t = add(session, "long", 61)
    r = plan(session, window=(time(9, 0), time(10, 0)))
    assert r.overflow == [t]


def test_never_placed_outside_window_even_with_history(session):
    _gym_history(session, hour=6)
    t = add(session, "gym", 60)
    plan(session)
    assert t.start_time == time(9, 0)  # nearest in-window slot to 6:00


def test_fixed_tasks_outside_window_stay_and_block(session):
    early = add(session, "early", 90, start=time(8, 0))    # 08:00-09:30 straddles the start
    late = add(session, "late", 60, start=time(22, 0))     # fully outside
    t = add(session, "a", 30)
    plan(session)
    assert (early.start_time, late.start_time) == (time(8, 0), time(22, 0))
    assert t.start_time == time(9, 30)


def test_today_only_places_after_now(session):
    now = datetime.combine(DAY, time(13, 2))
    t = add(session, "a", 30)
    plan(session, now=now)
    assert t.start_time == time(13, 5)


def test_started_auto_task_is_not_moved(session):
    a = add(session, "a", 60)
    plan(session)                                   # a 09:00
    add(session, "urgent", 30, priority=1)
    plan(session, now=datetime.combine(DAY, time(9, 20)))
    assert a.start_time == time(9, 0)               # in progress: kept


def test_past_days_are_refused_and_untouched(session):
    t = add(session, "a", 30, day=date(2026, 10, 1))
    with pytest.raises(TaskError, match="past"):
        plan(session, day=date(2026, 10, 1), now=BEFORE)
    assert t.start_time is None and t.placement is None


def test_future_days_can_be_planned(session):
    t = add(session, "a", 30, day=DAY + timedelta(days=3))
    plan(session, day=DAY + timedelta(days=3))
    assert t.start_time == time(9, 0)


# ---------- alarms, determinism, no overlaps ----------

def test_alarm_flags_reset_only_when_time_changes(session):
    a = add(session, "a", 60)
    plan(session)
    a.heads_up_sent = True
    session.commit()
    plan(session)                          # same result -> unchanged
    assert a.heads_up_sent is True
    add(session, "urgent", 30, priority=1)
    plan(session)                          # a moves to 09:30
    assert a.start_time == time(9, 30) and a.heads_up_sent is False


def test_planned_task_rings_like_any_other(session):
    from tomits.alarms import HEADS_UP, collect_due
    a = add(session, "a", 60)
    plan(session)
    assert [x.kind for x in collect_due(session, datetime.combine(DAY, time(8, 55)))] == [HEADS_UP]


def test_replan_is_deterministic_and_never_overlaps(session):
    _gym_history(session, hour=12)
    add(session, "lunch", 60, start=time(12, 30))
    add(session, "standup", 15, start=time(9, 45))
    for i, (title, mins, pri) in enumerate([("gym", 60, 2), ("deep work", 120, 1), ("email", 30, 3),
                                            ("call", 20, 2), ("read", 45, 4), ("admin", 90, 3)]):
        add(session, title, mins, priority=pri)
    first = times(plan(session).placed)
    second = times(plan(session).placed)
    assert first == second
    assert_no_overlaps(session)
    gym = [t for t in svc.tasks_for_day(session, DAY) if t.title == "gym"][0]
    # deep work takes 10:00-12:00, 12:00-12:30 is too short, so 13:30 is the nearest free slot to 12:00
    assert gym.start_time == time(13, 30) and "nearest free slot 13:30" in gym.plan_reason


# ---------- settings and migration ----------

def test_window_setting_default_round_trip_and_validation(tmp_path):
    path = tmp_path / "settings.json"
    s = load_settings(path)
    assert (s.day_start, s.day_end) == ("09:00", "21:00") and s.window == WINDOW
    s.day_start, s.day_end = validate_window("07:30", "22:00")
    save_settings(path, s)
    assert load_settings(path).window == (time(7, 30), time(22, 0))
    with pytest.raises(TaskError):
        validate_window("21:00", "09:00")
    path.write_text('{"snooze_minutes": 7, "day_start": "bad"}')
    loaded = load_settings(path)
    assert (loaded.snooze_minutes, loaded.day_start) == (7, "09:00")


def test_v3_database_gets_priority_and_fixed_placement(tmp_path):
    from test_times_and_migration import _make_v2
    db = tmp_path / "tomits.db"
    _make_v2(db)          # has one timed task (Gym 18:00) and one untimed
    Session = make_session_factory(db)
    with Session() as s:
        gym, old = svc.get_task(s, 2), svc.get_task(s, 1)
        assert (gym.priority, gym.placement) == (3, "fixed")
        assert (old.priority, old.placement) == (3, None)
    with sqlite3.connect(db) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] >= 4  # later versions migrate further


# ---------- UI ----------

class Quiet:
    def notify(self, *a, **k):
        pass


@pytest.fixture
def app(db_file, monkeypatch):
    out = io.StringIO()
    monkeypatch.setattr(ui, "console", Console(file=out, width=160))
    monkeypatch.setattr("tomits.ui_common.console", Console(file=io.StringIO()))
    a = ui.App(db_file, notifier=Quiet(), clock=lambda: BEFORE)
    a.out = out
    return a


def _answer(monkeypatch, *answers):
    it = iter(answers)
    monkeypatch.setattr(ui.Prompt, "ask", classmethod(lambda cls, *a, **k: next(it)))


def test_ui_plan_my_day_shows_plan_and_didnt_fit(app, monkeypatch):
    app.settings.day_start, app.settings.day_end = "09:00", "10:00"
    with app.Session() as s:
        add(s, "fits", 60, priority=1)
        add(s, "too much", 30, priority=2)
    _answer(monkeypatch, DAY.isoformat())
    app.plan_my_day()
    text = app.out.getvalue()
    assert "09:00-10:00" in text and "no history: placed by priority" in text
    assert "Didn't fit" in text and "too much" in text and "1 placed" in text


def test_ui_move_onto_a_fixed_task_is_refused_then_retry(app, monkeypatch):
    with app.Session() as s:
        a, b, c = add(s, "a", 60, 1), add(s, "b", 60, 2), add(s, "c", 60, 3)
        plan(s)
        svc.set_start_time(s, b.id, time(10, 0), now=BEFORE)          # b pinned at 10:00
    _answer(monkeypatch, str(c.id), f"after {a.id}", f"after {b.id}")  # first clashes with b
    app.set_time()
    assert "overlaps task" in app.out.getvalue() and "Neither task is moved" in app.out.getvalue()
    with app.Session() as s:
        c2 = svc.get_task(s, c.id)
        assert (c2.start_time, c2.placement) == (time(11, 0), "pinned")


@pytest.mark.parametrize("accept", [False, True])
def test_ui_move_onto_a_planned_task_shows_a_proposal(app, monkeypatch, accept):
    with app.Session() as s:
        a, b, c = add(s, "a", 60, 1), add(s, "b", 60, 2), add(s, "c", 60, 3)
        plan(s)                                                         # a 9, b 10, c 11
    _answer(monkeypatch, str(c.id), f"after {a.id}")
    monkeypatch.setattr(ui.Confirm, "ask", classmethod(lambda cls, *a, **k: accept))
    app.set_time()
    out = app.out.getvalue()
    assert "placed by the planner" in out and "Proposed changes" in out and "takes its own time 10:00-11:00" in out
    with app.Session() as s:
        b2, c2 = svc.get_task(s, b.id), svc.get_task(s, c.id)
        if accept:
            assert (c2.start_time, c2.placement) == (time(10, 0), "pinned")
            assert b2.start_time == time(11, 0) and "'c' has its own time 10:00-11:00" in b2.move_reason
        else:
            assert (b2.start_time, c2.start_time) == (time(10, 0), time(11, 0)) and c2.placement == "auto"


def test_confirming_current_slot_pins_without_overlap_check(session):
    a = add(session, "a", 60)
    plan(session)
    svc.set_start_time(session, a.id, time(9, 0))
    assert a.placement == "pinned"
