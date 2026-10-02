"""v1.4 automatic rescheduling."""

import io
import json
import sqlite3
from datetime import date, datetime, time, timedelta

import pytest
from rich.console import Console

from tomits import planner as pl
from tomits import rescheduler as rs
from tomits import services as svc
from tomits import tracking as tr
from tomits import ui
from tomits.alarms import END_CHECK, HEADS_UP, collect_due
from tomits.db import SCHEMA_VERSION, make_session_factory
from tomits.errors import TaskError
from tomits.models import Placement, Task, TaskReason, TaskStatus
from tomits.periods import PeriodKind

TODAY = date(2026, 10, 5)
TOMORROW = TODAY + timedelta(days=1)
WINDOW = (time(9, 0), time(21, 0))


def at(h, m=0, day=TODAY):
    return datetime.combine(day, time(h, m))


def auto(s, title, start, minutes, priority=3, day=TODAY, goal_id=None):
    """A planner-placed (unpinned) task."""
    t = Task(title=title, duration_min=minutes, planned_for=day, start_time=start, position=0,
             status=TaskStatus.PENDING.value, priority=priority, placement=Placement.AUTO.value,
             goal_id=goal_id, heads_up_sent=False, end_alert_sent=False)
    s.add(t)
    s.commit()
    return t


def fixed(s, title, start, minutes, day=TODAY, priority=3):
    return svc.add_task(s, title, minutes, planned_for=day, start_time=start, priority=priority, today=day)


def fail(s, task, now, reason="got pulled into a call", window=WINDOW, choice=None):
    svc.fail_task(s, task.id, reason)
    return rs.build_for_closed(s, task.id, window, now=now, choice=choice)


def by_title(prop, title):
    return [m for m in prop.moves if m.title == title][0]


def assert_no_overlaps(s, *days):
    for day in days or (TODAY, TOMORROW):
        busy = [t for t in svc.tasks_for_day(s, day) if t.start_time and t.status in svc.BLOCKING_STATUSES]
        for i, a in enumerate(busy):
            for b in busy[i + 1:]:
                assert not (a.start_at < b.end_at and b.start_at < a.end_at), (day, a.title, b.title)


# ---------- reason is required ----------

def test_fail_or_skip_without_reason_is_refused_and_nothing_happens(session):
    t = auto(session, "report", time(10, 0), 60)
    for bad in ("", "   ", None):
        with pytest.raises(TaskError, match="reason is required"):
            svc.fail_task(session, t.id, bad)
        with pytest.raises(TaskError, match="reason is required"):
            svc.skip_task(session, t.id, bad)
    session.refresh(t)
    assert t.status == "pending" and t.reasons == []
    with pytest.raises(TaskError, match="only failed or skipped"):
        rs.build_for_closed(session, t.id, WINDOW, now=at(9, 0))


def test_rescheduler_refuses_a_closed_task_without_a_stored_reason(session):
    t = auto(session, "report", time(10, 0), 60)
    t.status = TaskStatus.FAILED.value  # forced past the rules
    session.commit()
    with pytest.raises(TaskError, match="reason is required"):
        rs.build_for_closed(session, t.id, WINDOW, now=at(9, 0))


def test_reason_stored_with_snapshot_of_task(session):
    g = tr.create_goal(session, PeriodKind.MONTH, TODAY, "ship", today=TODAY)
    t = auto(session, "report", time(10, 0), 60, priority=2, goal_id=g.id)
    svc.fail_task(session, t.id, "sick")
    r = t.reasons[0]
    assert (r.reason, r.status, r.task_title, r.task_date, r.priority, r.goal_id, r.goal_title) == \
        ("sick", "failed", "report", TODAY, 2, g.id, "ship")


# ---------- failing early / late / last ----------

def test_fail_early_places_copy_in_todays_free_time(session):
    a = auto(session, "report", time(10, 0), 60, priority=2)
    b = auto(session, "email", time(11, 0), 30, priority=3)
    prop = fail(session, a, now=at(9, 30))
    copy = by_title(prop, "report")
    assert (copy.kind, copy.to_day, copy.to_start) == ("copy", TODAY, time(9, 30))
    assert copy.reason == "moved from 10 am: task failed; first free slot, by priority"
    assert [m.title for m in prop.moves] == ["report"]  # b untouched
    rs.accept(session, prop, now=at(9, 30))
    new = session.get(Task, a.id).rescheduled_copies[0]
    assert (new.start_time, new.placement, new.rescheduled_from_id, new.reschedule_count) == \
        (time(9, 30), "auto", a.id, 1)
    assert (a.status, a.planned_for, a.start_time, a.latest_reason) == \
        ("failed", TODAY, time(10, 0), "got pulled into a call")  # the record stays on its day
    assert b.start_time == time(11, 0)
    assert_no_overlaps(session)


def test_fail_midday_skips_fixed_and_pinned_tasks(session):
    a = auto(session, "report", time(9, 0), 60)
    fixed(session, "lunch", time(12, 0), 60)
    pinned = auto(session, "call", time(10, 30), 90)
    svc.set_start_time(session, pinned.id, time(10, 30))   # confirm -> pinned
    prop = fail(session, a, now=at(10, 0))
    rs.accept(session, prop, now=at(10, 0))
    copy = a.rescheduled_copies[0]
    assert copy.start_time == time(13, 0)  # 10:00-10:30 too short, 10:30-13:00 taken
    assert pinned.start_time == time(10, 30)
    assert_no_overlaps(session)


def test_fail_late_spills_to_tomorrow(session):
    a = auto(session, "report", time(19, 0), 60)
    auto(session, "tomorrow first", time(9, 0), 30, day=TOMORROW)
    prop = fail(session, a, now=at(20, 10))  # 50 min left today
    copy = by_title(prop, "report")
    assert (copy.to_day, copy.to_start) == (TOMORROW, time(9, 30))
    assert "tomorrow" in copy.reason
    rs.accept(session, prop, now=at(20, 10))
    assert_no_overlaps(session)


def test_fail_last_task_of_the_day_after_window_ends(session):
    a = auto(session, "wrap up", time(20, 0), 60)
    fixed(session, "gym", time(9, 0), 60, day=TOMORROW)
    prop = fail(session, a, now=at(21, 30))
    copy = by_title(prop, "wrap up")
    assert (copy.to_day, copy.to_start) == (TOMORROW, time(10, 0))
    rs.accept(session, prop, now=at(21, 30))
    assert_no_overlaps(session)


def test_skipped_task_is_rescheduled_the_same_way(session):
    a = auto(session, "read", time(10, 0), 30)
    svc.skip_task(session, a.id, "not in the mood")
    prop = rs.build_for_closed(session, a.id, WINDOW, now=at(9, 0))
    assert prop.trigger == "skipped" and "task skipped" in prop.moves[0].reason


def test_untimed_failed_task_gets_a_copy_too(session):
    t = svc.add_task(session, "someday", 30, planned_for=TODAY, today=TODAY)
    prop = fail(session, t, now=at(9, 0))
    assert prop.moves[0].reason.startswith("moved from no time: task failed")


# ---------- nothing left / nothing beyond tomorrow ----------

def test_no_room_today_or_tomorrow_gives_unplaced(session):
    window = (time(9, 0), time(12, 0))
    a = auto(session, "report", time(9, 0), 60)
    fixed(session, "busy today", time(10, 0), 120)
    fixed(session, "busy tomorrow", time(9, 0), 180, day=TOMORROW)
    prop = fail(session, a, now=at(9, 45), window=window)   # only 09:45-10:00 free today
    assert [m.title for m in prop.unplaced] == ["report"]
    assert "unplaced: no room today or tomorrow (needs 1h)" in prop.unplaced[0].reason
    rs.accept(session, prop, now=at(9, 45))
    copy = a.rescheduled_copies[0]
    assert (copy.planned_for, copy.start_time, copy.placement, copy.status) == (TODAY, None, "overflow", "pending")
    assert [t.id for t in pl.overflow_tasks(session, TODAY)] == [copy.id]


def test_never_beyond_tomorrow(session):
    window = (time(9, 0), time(10, 0))
    a = auto(session, "report", time(9, 0), 60)
    fixed(session, "tomorrow full", time(9, 0), 60, day=TOMORROW)
    prop = fail(session, a, now=at(9, 30), window=window)
    assert prop.unplaced and prop.placed == []  # the day after tomorrow is free but not used


def test_unplaced_list_is_in_priority_order(session):
    window = (time(9, 0), time(10, 0))
    fixed(session, "today full", time(9, 0), 60, priority=1)
    fixed(session, "tomorrow full", time(9, 0), 60, day=TOMORROW, priority=1)
    t = auto(session, "t", time(9, 0), 60, day=TOMORROW + timedelta(days=5))
    svc.fail_task(session, t.id, "x")
    prop = rs.build_for_closed(session, t.id, window, now=at(8, 0), choice=None)
    assert [m.title for m in prop.unplaced] == ["t"]


# ---------- priority displacement ----------

def _displacement_day(s, low_priority=4):
    window = (time(9, 0), time(11, 0))
    a = fixed(s, "urgent thing", time(8, 0), 60, priority=1)     # outside the window
    low = auto(s, "low thing", time(9, 0), 120, priority=low_priority)
    fixed(s, "tomorrow full", time(9, 0), 120, day=TOMORROW)
    return window, a, low


def test_higher_priority_displaces_lower_priority_unpinned_task(session):
    window, a, low = _displacement_day(session)
    prop = fail(session, a, now=at(8, 30), window=window)
    copy, moved = by_title(prop, "urgent thing"), by_title(prop, "low thing")
    assert (copy.to_day, copy.to_start) == (TODAY, time(9, 0))
    assert "higher priority than 'low thing'" in copy.reason
    assert moved.kind == "shift" and moved.unplaced  # 2h no longer fits anywhere
    assert "made room for 'urgent thing' (higher priority)" in moved.reason
    rs.accept(session, prop, now=at(8, 30))
    assert (low.start_time, low.placement, low.status) == (None, "overflow", "pending")
    assert_no_overlaps(session)


def test_equal_priority_is_not_displaced(session):
    window, a, low = _displacement_day(session, low_priority=1)
    prop = fail(session, a, now=at(8, 30), window=window)
    assert [m.title for m in prop.unplaced] == ["urgent thing"]
    assert low.start_time == time(9, 0)


def test_pinned_lower_priority_task_is_never_displaced(session):
    window, a, low = _displacement_day(session)
    svc.set_start_time(session, low.id, time(9, 0))  # pin it
    prop = fail(session, a, now=at(8, 30), window=window)
    assert [m.title for m in prop.unplaced] == ["urgent thing"]


def test_displaced_task_moves_to_next_free_slot(session):
    window = (time(9, 0), time(12, 0))
    a = fixed(session, "urgent", time(8, 0), 60, priority=1)
    low = auto(session, "low", time(9, 0), 60, priority=4)
    fixed(session, "block", time(10, 0), 60)
    auto(session, "normal", time(11, 0), 60, priority=3)
    fixed(session, "tomorrow full", time(9, 0), 180, day=TOMORROW)
    prop = fail(session, a, now=at(8, 30), window=window)
    # 'low' (p4) is displaced first (least important); it finds no room -> 'normal' isn't touched
    assert by_title(prop, "urgent").to_start == time(9, 0)
    assert by_title(prop, "low").unplaced
    rs.accept(session, prop, now=at(8, 30))
    assert_no_overlaps(session)


# ---------- overrun ----------

def test_overrun_extend_shifts_following_unpinned_tasks(session):
    t = auto(session, "deep work", time(10, 0), 60, priority=2)
    b = auto(session, "email", time(11, 0), 30, priority=3)
    c = auto(session, "calls", time(11, 30), 30, priority=3)
    fixed(session, "lunch", time(13, 0), 60)
    prop = rs.build_for_overrun(session, t.id, at(11, 30), WINDOW, now=at(10, 50))
    ext = by_title(prop, "deep work")
    assert (ext.kind, ext.new_duration) == ("extend", 90)
    assert by_title(prop, "email").to_start == time(11, 30)
    assert by_title(prop, "calls").to_start == time(12, 0)
    assert by_title(prop, "email").reason.startswith("moved from 11 am: 'deep work' ran over to 11:30")
    rs.accept(session, prop, now=at(10, 50))
    assert (t.duration_min, t.end_at.time(), t.status) == (90, time(11, 30), "pending")  # not failed
    assert (b.start_time, c.start_time) == (time(11, 30), time(12, 0))
    assert_no_overlaps(session)


def test_overrun_pushes_back_to_back_chain_but_stops_at_a_gap(session):
    t = auto(session, "deep work", time(10, 0), 60)
    a = auto(session, "a", time(11, 0), 30)
    b = auto(session, "b", time(11, 30), 30)       # back-to-back with a: pushed too
    c = auto(session, "c", time(13, 0), 30)        # after a gap that absorbs the push
    prop = rs.build_for_overrun(session, t.id, at(11, 20), WINDOW, now=at(10, 50))
    assert {m.title for m in prop.moves} == {"deep work", "a", "b"}
    assert (by_title(prop, "a").to_start, by_title(prop, "b").to_start) == (time(11, 20), time(11, 50))


def test_overrun_noticed_late_still_pushes_the_next_planned_task(session):
    """At 11:05 'email' (11:00) looks started, but deep work was still going."""
    t = auto(session, "deep work", time(10, 0), 60)
    b = auto(session, "email", time(11, 0), 30)
    prop = rs.build_for_overrun(session, t.id, at(11, 30), WINDOW, now=at(11, 5))
    assert prop.collisions == [] and by_title(prop, "email").to_start == time(11, 30)


def test_overrun_only_moves_tasks_it_hits(session):
    t = auto(session, "deep work", time(10, 0), 60)
    later = auto(session, "later", time(15, 0), 30)
    prop = rs.build_for_overrun(session, t.id, at(11, 15), WINDOW, now=at(10, 50))
    assert [m.kind for m in prop.moves] == ["extend"]
    assert later.start_time == time(15, 0)


def test_overrun_into_fixed_task_warns_and_does_not_move_it(session):
    t = auto(session, "deep work", time(10, 0), 60)
    f = fixed(session, "meeting", time(11, 30), 60)
    prop = rs.build_for_overrun(session, t.id, at(12, 0), WINDOW, now=at(10, 50))
    assert prop.needs_choice and prop.moves == []
    assert prop.collisions[0].message == f"task {f.id} 'meeting' (11:30-12:30, fixed)"
    with pytest.raises(TaskError, match="Choose"):
        rs.accept(session, prop)
    assert f.start_time == time(11, 30)


def test_overrun_collision_choice_shorten(session):
    t = auto(session, "deep work", time(10, 0), 60)
    f = fixed(session, "meeting", time(11, 30), 60)
    prop = rs.build_for_overrun(session, t.id, at(12, 0), WINDOW, now=at(10, 50), choice="shorten")
    rs.accept(session, prop, now=at(10, 50))
    assert (t.end_at.time(), f.start_time) == (time(11, 30), time(11, 30))


def test_overrun_collision_choice_move_rest_after(session):
    t = auto(session, "deep work", time(10, 0), 60)
    fixed(session, "meeting", time(11, 30), 60)
    prop = rs.build_for_overrun(session, t.id, at(12, 0), WINDOW, now=at(10, 50), choice="continue")
    rest = by_title(prop, "deep work (rest)")
    assert (rest.duration, rest.to_start) == (30, time(12, 30))
    rs.accept(session, prop, now=at(10, 50))
    assert t.end_at.time() == time(11, 30)
    assert t.rescheduled_copies[0].rescheduled_from_id == t.id
    assert_no_overlaps(session)


def test_overrun_collision_choice_leave_changes_nothing(session):
    t = auto(session, "deep work", time(10, 0), 60)
    fixed(session, "meeting", time(11, 30), 60)
    prop = rs.build_for_overrun(session, t.id, at(12, 0), WINDOW, now=at(10, 50), choice="leave")
    assert prop.moves == [] and rs.accept(session, prop) is None
    assert t.duration_min == 60


def test_overrun_into_pinned_task_warns(session):
    t = auto(session, "deep work", time(10, 0), 60)
    p = auto(session, "pinned", time(11, 0), 30)
    svc.set_start_time(session, p.id, time(11, 0))
    prop = rs.build_for_overrun(session, t.id, at(11, 20), WINDOW, now=at(10, 50))
    assert prop.collisions and prop.collisions[0].placement == "pinned"


@pytest.mark.parametrize("end,msg", [(at(10, 30), "must be after"), (at(23, 59) + timedelta(minutes=2), "midnight")])
def test_overrun_validation(session, end, msg):
    t = auto(session, "deep work", time(10, 0), 60)
    with pytest.raises(TaskError, match=msg):
        rs.build_for_overrun(session, t.id, end, WINDOW, now=at(10, 50))


def test_overrun_only_for_todays_timed_pending_tasks(session):
    t = auto(session, "tomorrow", time(10, 0), 60, day=TOMORROW)
    with pytest.raises(TaskError, match="today"):
        rs.build_for_overrun(session, t.id, at(12, 0, TOMORROW), WINDOW, now=at(10, 50))


# ---------- confirm / undo ----------

def test_nothing_changes_until_accepted(session):
    a = auto(session, "report", time(10, 0), 60)
    b = auto(session, "email", time(11, 0), 30)
    prop = rs.build_for_overrun(session, a.id, at(11, 30), WINDOW, now=at(10, 50))
    session.expire_all()
    assert (a.duration_min, b.start_time) == (60, time(11, 0))
    assert session.query(Task).count() == 2


def test_undo_restores_exact_plan_and_keeps_reason(session):
    window, a, low = _displacement_day(session)
    low.heads_up_sent = True
    session.commit()
    prop = fail(session, a, now=at(8, 30), window=window, reason="flat tyre")  # the fail itself is kept
    before = {t.id: (t.planned_for, t.start_time, t.placement, t.heads_up_sent) for t in session.query(Task)}
    rs.accept(session, prop, now=at(8, 30))
    assert low.start_time is None and len(a.rescheduled_copies) == 1
    rs.undo_last(session)
    session.expire_all()
    after = {t.id: (t.planned_for, t.start_time, t.placement, t.heads_up_sent) for t in session.query(Task)}
    assert after == before
    assert (a.status, a.latest_reason) == ("failed", "flat tyre")
    assert session.query(TaskReason).count() == 1
    assert rs.reason_history(session)[0].reason == "flat tyre"


def test_undo_is_one_step(session):
    a = auto(session, "report", time(10, 0), 60)
    rs.accept(session, fail(session, a, now=at(9, 0)), now=at(9, 0))
    rs.undo_last(session)
    with pytest.raises(TaskError, match="no reschedule to undo"):
        rs.undo_last(session)


def test_undo_refused_once_copy_is_done(session):
    a = auto(session, "report", time(10, 0), 60)
    rs.accept(session, fail(session, a, now=at(9, 0)), now=at(9, 0))
    svc.complete_task(session, a.rescheduled_copies[0].id, today=TODAY)
    with pytest.raises(TaskError, match="already done"):
        rs.undo_last(session)


def test_undo_refused_if_restoring_would_overlap(session):
    a = auto(session, "report", time(9, 0), 60)
    b = auto(session, "email", time(10, 0), 30)
    rs.accept(session, rs.build_for_overrun(session, a.id, at(10, 30), WINDOW, now=at(9, 50)), now=at(9, 50))
    svc.skip_task(session, a.id, "done enough")   # ...then b's old slot gets taken by a new fixed task
    fixed(session, "new", time(10, 0), 30)
    with pytest.raises(TaskError, match="Can't undo"):
        rs.undo_last(session)


def test_stale_proposal_is_refused(session):
    a = auto(session, "report", time(10, 0), 60)
    b = auto(session, "email", time(11, 0), 30)
    prop = rs.build_for_overrun(session, a.id, at(11, 30), WINDOW, now=at(10, 50))
    svc.set_start_time(session, b.id, time(15, 0))
    with pytest.raises(TaskError, match="plan changed"):
        rs.accept(session, prop, now=at(10, 50))
    session.expire_all()
    assert a.duration_min == 60


def test_already_rescheduled_task_is_refused(session):
    a = auto(session, "report", time(10, 0), 60)
    rs.accept(session, fail(session, a, now=at(9, 0)), now=at(9, 0))
    with pytest.raises(TaskError, match="already rescheduled"):
        rs.build_for_closed(session, a.id, WINDOW, now=at(9, 0))


# ---------- reschedule cap ----------

def _fail_chain(s, times_):
    t = auto(s, "essay", time(10, 0), 60)
    for i in range(times_):
        prop = fail(s, t, now=at(9, 0), reason=f"miss {i + 1}")
        rs.accept(s, prop, now=at(9, 0))
        t = t.rescheduled_copies[0]
    return t


def test_cap_constant():
    assert rs.MAX_RESCHEDULES == 3


def test_third_reschedule_is_flagged_and_needs_a_choice(session):
    t = _fail_chain(session, 2)
    assert t.reschedule_count == 2
    prop = fail(session, t, now=at(9, 0))
    assert prop.cap_reached and prop.chain_count == 3 and prop.moves == [] and prop.needs_choice
    with pytest.raises(TaskError):
        rs.accept(session, prop)


def test_cap_choice_keep(session):
    t = _fail_chain(session, 2)
    svc.fail_task(session, t.id, "again")
    prop = rs.build_for_closed(session, t.id, WINDOW, now=at(9, 0), choice="keep")
    rs.accept(session, prop, now=at(9, 0))
    assert t.rescheduled_copies[0].reschedule_count == 3


def test_cap_choice_split(session):
    t = _fail_chain(session, 2)
    svc.fail_task(session, t.id, "too big")
    prop = rs.build_for_closed(session, t.id, WINDOW, now=at(9, 0), choice="split")
    assert [(m.title, m.duration) for m in prop.moves] == [("essay (part 1)", 30), ("essay (part 2)", 30)]
    rs.accept(session, prop, now=at(9, 0))
    assert len(t.rescheduled_copies) == 2
    assert_no_overlaps(session)


def test_cap_choice_drop(session):
    t = _fail_chain(session, 2)
    svc.fail_task(session, t.id, "not worth it")
    prop = rs.build_for_closed(session, t.id, WINDOW, now=at(9, 0), choice="drop")
    assert prop.moves == [] and rs.accept(session, prop) is None
    assert t.status == "failed" and t.rescheduled_copies == []


# ---------- alarms ----------

def test_alarms_follow_moves(session):
    a = auto(session, "report", time(10, 0), 60)
    b = auto(session, "email", time(11, 0), 30)
    b.heads_up_sent = True
    session.commit()
    rs.accept(session, rs.build_for_overrun(session, a.id, at(11, 30), WINDOW, now=at(10, 50)), now=at(10, 50))
    assert b.heads_up_sent is False  # re-armed for 11:30
    assert [(x.kind, x.task_id) for x in collect_due(session, at(11, 25))] == [(HEADS_UP, b.id)]


def test_failed_record_alarms_cleared_and_copy_rings_at_new_time(session):
    a = auto(session, "report", time(14, 0), 60)
    prop = fail(session, a, now=at(9, 0))
    rs.accept(session, prop, now=at(9, 0))
    copy = a.rescheduled_copies[0]
    assert (a.heads_up_sent, a.end_alert_sent) == (True, True)
    assert (copy.start_time, copy.heads_up_sent, copy.end_alert_sent) == (time(9, 0), False, False)
    due = collect_due(session, at(13, 55))
    assert all(x.task_id != a.id for x in due)            # nothing for the failed record
    assert [(x.kind, x.task_id) for x in due] == [(END_CHECK, copy.id)]  # the copy rings at its new time


# ---------- goals ----------

def test_goal_logs_only_when_copy_is_completed(session):
    g = tr.create_goal(session, PeriodKind.DAY, TODAY, "read", 50, "pages", today=TODAY)
    a = auto(session, "read ch 1", time(10, 0), 60, goal_id=g.id)
    prop = fail(session, a, now=at(9, 0))
    assert g.logs == []
    rs.accept(session, prop, now=at(9, 0))
    copy = a.rescheduled_copies[0]
    assert copy.goal_id == g.id and g.logs == []
    svc.complete_task(session, copy.id, contribution=10, today=TODAY)
    session.refresh(g)
    assert [(l.amount, l.task_id) for l in g.logs] == [(10, copy.id)]
    assert tr.progress(g).text == "10/50 pages"


# ---------- history ----------

def test_history_view_filters_and_links_copies(session):
    g1 = tr.create_goal(session, PeriodKind.MONTH, TODAY, "fitness", today=TODAY)
    g2 = tr.create_goal(session, PeriodKind.MONTH, TODAY, "study", today=TODAY)
    old = auto(session, "run", time(10, 0), 30, goal_id=g1.id, day=TODAY - timedelta(days=20))
    svc.fail_task(session, old.id, "rain")
    a = auto(session, "study ch 2", time(10, 0), 60, goal_id=g2.id)
    rs.accept(session, fail(session, a, now=at(9, 0), reason="tired"), now=at(9, 0))
    b = auto(session, "stretch", time(15, 0), 15, goal_id=g1.id)
    svc.skip_task(session, b.id, "no time")
    assert [r.reason for r in rs.reason_history(session)] == ["tired", "no time", "rain"] or \
        [r.reason for r in rs.reason_history(session)] == ["no time", "tired", "rain"]
    assert [r.reason for r in rs.reason_history(session, goal_id=g1.id)] == ["no time", "rain"]
    assert [r.reason for r in rs.reason_history(session, start=TODAY - timedelta(days=7))] == ["no time", "tired"]
    rec = rs.reason_history(session, goal_id=g2.id)[0]
    assert rec.task.rescheduled_copies[0].start_time == time(9, 0)


def test_reason_snapshot_survives_renames(session):
    g = tr.create_goal(session, PeriodKind.MONTH, TODAY, "old goal name", today=TODAY)
    a = auto(session, "old title", time(10, 0), 60, goal_id=g.id)
    svc.fail_task(session, a.id, "x")
    a.title = "new title"
    tr.update_goal(session, g.id, title="new goal name", today=TODAY)
    r = rs.reason_history(session)[0]
    assert (r.task_title, r.goal_title) == ("old title", "old goal name")


def test_migration_backfills_reason_snapshots(tmp_path):
    from test_times_and_migration import _make_v2
    db = tmp_path / "tomits.db"
    _make_v2(db)  # task 1 'Old task' failed with 'power cut', goal 1 'Ship tomits'
    Session = make_session_factory(db)
    with Session() as s:
        r = rs.reason_history(s)[0]
        assert (r.reason, r.task_title, r.task_date, r.priority, r.goal_title) == \
            ("power cut", "Old task", date(2026, 9, 29), 3, "Ship tomits")
    with sqlite3.connect(db) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


# ---------- no overlaps under a busy day ----------

def test_busy_day_fail_and_overrun_never_overlap(session):
    fixed(session, "standup", time(9, 30), 15)
    fixed(session, "lunch", time(12, 30), 60)
    slots = [time(10, 0), time(10, 45), time(11, 30), time(13, 30), time(14, 15), time(15, 0), time(16, 0),
             time(17, 0), time(18, 0), time(19, 0)]
    tasks = [auto(session, f"t{i}", st, 45, priority=1 + i % 4) for i, st in enumerate(slots)]
    assert_no_overlaps(session)
    fixed(session, "tomorrow a", time(10, 0), 90, day=TOMORROW)
    rs.accept(session, rs.build_for_overrun(session, tasks[0].id, at(11, 0), WINDOW, now=at(10, 10)), now=at(10, 10))
    assert_no_overlaps(session)
    rs.accept(session, fail(session, tasks[3], now=at(11, 5)), now=at(11, 5))
    assert_no_overlaps(session)
    rs.accept(session, fail(session, tasks[-1], now=at(19, 30)), now=at(19, 30))
    assert_no_overlaps(session)


# ---------- UI ----------

class Quiet:
    def notify(self, *a, **k):
        pass


class Silent:
    def play_burst(self):
        pass


@pytest.fixture
def app(db_file, monkeypatch):
    out = io.StringIO()
    monkeypatch.setattr(ui, "console", Console(file=out, width=180))
    monkeypatch.setattr("tomits.ui_common.console", Console(file=io.StringIO()))
    now = {"t": at(9, 0)}
    a = ui.App(db_file, notifier=Quiet(), clock=lambda: now["t"], player=Silent())
    a.out, a.now = out, now
    return a


def _answer(monkeypatch, *answers, confirm=True):
    it = iter(answers)
    monkeypatch.setattr(ui.Prompt, "ask", classmethod(lambda cls, *a, **k: next(it)))
    monkeypatch.setattr(ui.Confirm, "ask", classmethod(lambda cls, *a, **k: confirm))


def test_ui_fail_then_accept_then_undo(app, monkeypatch):
    with app.Session() as s:
        t = auto(s, "report", time(10, 0), 60)
    _answer(monkeypatch, str(t.id), "", "sick")      # task, empty reason refused, then reason
    app.close_with_reason(TaskStatus.FAILED)
    assert app.triggers == [("closed", t.id, None)]
    _answer(monkeypatch)                               # accept (Confirm -> True)
    app.attend()
    assert "Proposed changes: task" in app.out.getvalue() and "moved from 10 am: task failed" in app.out.getvalue()
    with app.Session() as s:
        orig = svc.get_task(s, t.id)
        assert orig.status == "failed" and len(orig.rescheduled_copies) == 1
    app.undo_reschedule()
    with app.Session() as s:
        orig = svc.get_task(s, t.id)
        assert orig.rescheduled_copies == [] and orig.latest_reason == "sick"


def test_ui_rejecting_changes_nothing(app, monkeypatch):
    with app.Session() as s:
        t = auto(s, "report", time(10, 0), 60)
        svc.fail_task(s, t.id, "sick")
    app.triggers.append(("closed", t.id, None))
    _answer(monkeypatch, confirm=False)
    app.attend()
    with app.Session() as s:
        assert svc.get_task(s, t.id).rescheduled_copies == []
    assert "press r to reschedule it later" in app.out.getvalue()


def test_ui_overrun_detected_by_end_alarm(app, monkeypatch):
    """Detection way 2: end time passes -> alarm -> check-in 'still going'."""
    with app.Session() as s:
        t = auto(s, "deep work", time(10, 0), 60)
        b = auto(s, "email", time(11, 0), 30)
    app.now["t"] = at(11, 0)
    app.alarms.check()                                 # end-of-task alarm rings
    _answer(monkeypatch, "d", "g", "30")               # dismiss, still going, +30 min
    app.attend()
    assert app.triggers == [("overrun", t.id, at(11, 30))]
    _answer(monkeypatch)                               # accept
    app.attend()
    with app.Session() as s:
        assert svc.get_task(s, t.id).end_at.time() == time(11, 30)
        assert svc.get_task(s, b.id).start_time == time(11, 30)


def test_ui_overrun_told_explicitly_with_end_time(app, monkeypatch):
    """Detection way 1: I say it's still going and give a new end time."""
    with app.Session() as s:
        t = auto(s, "deep work", time(10, 0), 60)
    app.now["t"] = at(10, 50)
    _answer(monkeypatch, str(t.id), "11:20")
    app.still_going()
    _answer(monkeypatch)
    app.attend()
    with app.Session() as s:
        assert svc.get_task(s, t.id).end_at.time() == time(11, 20)


def test_ui_collision_warning_names_fixed_task(app, monkeypatch):
    with app.Session() as s:
        t = auto(s, "deep work", time(10, 0), 60)
        fixed(s, "meeting", time(11, 30), 60)
    app.now["t"] = at(10, 50)
    app.triggers.append(("overrun", t.id, at(12, 0)))
    _answer(monkeypatch, "s")                          # shorten
    app.attend()
    out = app.out.getvalue()
    assert "would run into" in out and "'meeting' (11:30-12:30, fixed)" in out
    with app.Session() as s:
        assert svc.get_task(s, t.id).end_at.time() == time(11, 30)


def test_ui_history_view(app, monkeypatch):
    with app.Session() as s:
        t = auto(s, "report", time(10, 0), 60)
        svc.fail_task(s, t.id, "power cut")
    _answer(monkeypatch, "", "", "")
    app.history()
    out = app.out.getvalue()
    assert "power cut" in out and "report" in out
