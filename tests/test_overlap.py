"""No overlapping tasks on the same day (back-to-back is fine).
Checked in the logic layer: add_task, plan_day, set_start_time."""

from datetime import date, time

import pytest

from tomits import services as svc
from tomits.errors import TaskError
from tomits.models import Task, TaskStatus

DAY = date(2026, 10, 1)


def add(s, title, start, minutes, day=DAY):
    return svc.add_task(s, title, minutes, planned_for=day, start_time=start, today=DAY)


def existing(s, title, start, minutes, day=DAY):
    """Insert directly, bypassing the rule: simulates data saved before it existed."""
    t = Task(title=title, duration_min=minutes, planned_for=day, start_time=start, position=0,
             status=TaskStatus.PENDING.value, heads_up_sent=False, end_alert_sent=False)
    s.add(t)
    s.commit()
    return t


@pytest.fixture
def base(session):
    """'Deep work' 09:00-10:00."""
    return add(session, "Deep work", time(9, 0), 60)


@pytest.mark.parametrize("start,minutes,case", [
    (time(8, 30), 60, "partial: ends inside"),
    (time(9, 30), 60, "partial: starts inside"),
    (time(9, 15), 30, "containment: new inside existing"),
    (time(8, 0), 180, "containment: new around existing"),
    (time(9, 0), 60, "exact match"),
    (time(9, 0), 1, "same start"),
    (time(9, 59), 5, "one minute overlap"),
])
def test_overlaps_are_refused(session, base, start, minutes, case):
    with pytest.raises(TaskError, match="overlaps task") as err:
        add(session, "New", start, minutes)
    msg = str(err.value)
    assert f"task {base.id} 'Deep work' (09:00-10:00)" in msg, case
    assert "Start at 10:00 or later, or finish by 09:00" in msg
    assert len(svc.tasks_for_day(session, DAY)) == 1


@pytest.mark.parametrize("start,minutes", [(time(10, 0), 30), (time(8, 0), 60)])
def test_back_to_back_is_allowed(session, base, start, minutes):
    add(session, "Neighbour", start, minutes)
    assert len(svc.tasks_for_day(session, DAY)) == 2


def test_message_names_new_range_too(session, base):
    with pytest.raises(TaskError) as err:
        add(session, "Email", time(9, 45), 30)
    assert str(err.value).startswith("'Email' (09:45-10:15) overlaps task")


def test_untimed_tasks_never_overlap(session, base):
    svc.add_task(session, "Anytime", 600, planned_for=DAY, today=DAY)


def test_other_days_do_not_matter(session, base):
    add(session, "Tomorrow", time(9, 0), 60, day=date(2026, 10, 2))


def test_done_blocks_but_failed_and_skipped_free_the_slot(session):
    done = add(session, "done", time(9, 0), 60)
    svc.complete_task(session, done.id, today=DAY)
    with pytest.raises(TaskError):
        add(session, "x", time(9, 30), 10)
    failed = add(session, "failed", time(11, 0), 60)
    svc.fail_task(session, failed.id, "sick")
    skipped = add(session, "skipped", time(13, 0), 60)
    svc.skip_task(session, skipped.id, "not needed")
    add(session, "replaces failed", time(11, 0), 60)
    add(session, "replaces skipped", time(13, 30), 30)


# ---------- editing a task's time ----------

def test_moving_a_task_into_an_overlap_is_refused_and_nothing_changes(session, base):
    other = add(session, "Lunch", time(12, 0), 60)
    with pytest.raises(TaskError, match="'Deep work' \\(09:00-10:00\\)"):
        svc.set_start_time(session, other.id, time(9, 30))
    session.refresh(other)
    assert other.start_time == time(12, 0)


def test_moving_a_task_within_its_own_slot_is_fine(session, base):
    svc.set_start_time(session, base.id, time(9, 30))  # overlaps only its old self
    assert base.start_time == time(9, 30)


def test_moving_back_to_back_is_fine(session, base):
    other = add(session, "Lunch", time(12, 0), 60)
    svc.set_start_time(session, other.id, time(10, 0))


# ---------- tasks that already overlapped before the rule ----------

def test_pre_existing_overlaps_are_left_alone(session):
    a = existing(session, "old A", time(9, 0), 60)
    b = existing(session, "old B", time(9, 30), 60)
    # editing without changing the time is not blocked
    svc.set_start_time(session, b.id, time(9, 30))
    svc.link_task(session, b.id, None, today=DAY)
    svc.complete_task(session, a.id, today=DAY)
    session.refresh(b)
    assert (b.start_time, b.status) == (time(9, 30), "pending")


def test_pre_existing_overlap_moved_to_another_clash_is_refused(session):
    a = existing(session, "old A", time(9, 0), 60)
    b = existing(session, "old B", time(9, 30), 60)
    with pytest.raises(TaskError, match="old A"):
        svc.set_start_time(session, b.id, time(9, 45))
    svc.set_start_time(session, b.id, time(10, 0))  # moved clear of A: accepted


def test_clearing_the_time_is_always_allowed(session):
    existing(session, "old A", time(9, 0), 60)
    b = existing(session, "old B", time(9, 30), 60)
    svc.set_start_time(session, b.id, None)
    assert b.start_time is None


def test_new_task_next_to_pre_existing_overlap_still_checked(session):
    existing(session, "old A", time(9, 0), 60)
    existing(session, "old B", time(9, 30), 60)
    with pytest.raises(TaskError):
        add(session, "new", time(10, 15), 30)  # clashes with old B (09:30-10:30)
    add(session, "new", time(10, 30), 30)


# ---------- planning a day ----------

def test_plan_that_clashes_with_saved_task_is_refused_whole(session, base):
    drafts = [svc.TaskDraft("a", 30), svc.TaskDraft("b", 30)]
    with pytest.raises(TaskError, match="Deep work"):
        svc.plan_day(session, DAY, drafts, start=time(8, 30), today=DAY)  # a 08:30-09:00, b 09:00-09:30
    assert [t.title for t in svc.tasks_for_day(session, DAY)] == ["Deep work"]


def test_plan_back_to_back_after_saved_task(session, base):
    svc.plan_day(session, DAY, [svc.TaskDraft("a", 30), svc.TaskDraft("b", 30)], start=time(10, 0), today=DAY)
    assert len(svc.tasks_for_day(session, DAY)) == 3


def test_plan_drafts_that_clash_with_each_other_are_refused(session):
    drafts = [svc.TaskDraft("a", 60, start_time=time(9, 0)), svc.TaskDraft("b", 30, start_time=time(9, 30))]
    with pytest.raises(TaskError, match="in this plan"):
        svc.plan_day(session, DAY, drafts, today=DAY)
    assert svc.tasks_for_day(session, DAY) == []
