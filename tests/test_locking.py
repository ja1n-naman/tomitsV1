"""Periods lock at local midnight after they end; the review one day later.
Enforced in the logic layer (tracking.py), tested here without any UI."""

from datetime import date, timedelta

import pytest

from tomits import periods as P
from tomits import tracking as tr
from tomits.errors import TaskError
from helpers import (DAY, FRI_2_OCT, MONTH, MON_28_SEP, MON_5_OCT, OCT, SAT_3_OCT, SEP, SUN_27_SEP, SUN_4_OCT,
                     THU_1_OCT, TUE_29_SEP, WED_30_SEP, WEEK, reading_chain)


# ---------- pure period math ----------

@pytest.mark.parametrize("d,start", [
    (SUN_27_SEP, SUN_27_SEP), (WED_30_SEP, SUN_27_SEP), (SAT_3_OCT, SUN_27_SEP), (SUN_4_OCT, SUN_4_OCT),
])
def test_weeks_start_on_sunday(d, start):
    assert P.period_start(WEEK, d) == start
    assert P.period_end(WEEK, d) == start + timedelta(days=6)


def test_month_bounds():
    assert (P.period_start(MONTH, WED_30_SEP), P.period_end(MONTH, SEP)) == (SEP, WED_30_SEP)
    assert P.period_end(MONTH, date(2028, 2, 10)) == date(2028, 2, 29)


@pytest.mark.parametrize("kind,start,last_open,review_last", [
    (DAY, TUE_29_SEP, TUE_29_SEP, WED_30_SEP),
    (WEEK, SUN_27_SEP, SAT_3_OCT, SUN_4_OCT),
    (MONTH, SEP, WED_30_SEP, THU_1_OCT),
])
def test_lock_and_review_cutoff_dates(kind, start, last_open, review_last):
    assert not P.is_locked(kind, start, last_open)
    assert P.is_locked(kind, start, last_open + timedelta(days=1))
    assert not P.is_review_locked(kind, start, review_last)
    assert P.is_review_locked(kind, start, review_last + timedelta(days=1))


# ---------- every write is refused once the period has ended ----------

@pytest.mark.parametrize("kind,start,ended_on", [
    (DAY, TUE_29_SEP, WED_30_SEP),
    (WEEK, SUN_27_SEP, SUN_4_OCT),
    (MONTH, SEP, THU_1_OCT),
])
def test_all_edits_refused_after_period_ends(session, kind, start, ended_on):
    last_day = P.period_end(kind, start)
    g = tr.create_goal(session, kind, start, "numeric", 10, "pages", today=last_day)
    plain = tr.create_goal(session, kind, start, "plain", today=last_day)
    log = tr.log_progress(session, g.id, 1, on=last_day, today=last_day)
    tr.set_process(session, kind, start, "old process", today=last_day)
    sac = tr.add_sacrifice(session, kind, start, "no phone", today=last_day)

    refused = [
        lambda: tr.create_goal(session, kind, start, "late goal", today=ended_on),
        lambda: tr.update_goal(session, g.id, title="renamed", today=ended_on),
        lambda: tr.delete_goal(session, plain.id, today=ended_on),
        lambda: tr.log_progress(session, g.id, 1, on=last_day, today=ended_on),
        lambda: tr.delete_log(session, log.id, today=ended_on),
        lambda: tr.set_goal_done(session, plain.id, True, today=ended_on),
        lambda: tr.set_process(session, kind, start, "new process", today=ended_on),
        lambda: tr.add_sacrifice(session, kind, start, "late", today=ended_on),
        lambda: tr.mark_sacrifice_made(session, sac.id, today=ended_on),
        lambda: tr.remove_sacrifice(session, sac.id, today=ended_on),
    ]
    for action in refused:
        with pytest.raises(TaskError, match="read-only"):
            action()

    session.expire_all()
    entry = tr.get_entry(session, kind, start)
    assert entry.process == "old process"
    assert [x.title for x in entry.goals] == ["numeric", "plain"]
    assert [(x.text, x.status) for x in entry.sacrifices] == [("no phone", "planned")]
    assert tr.progress(g).text == "1/10 pages" and not tr.progress(plain).done


@pytest.mark.parametrize("kind,start", [(DAY, TUE_29_SEP), (WEEK, SUN_27_SEP), (MONTH, SEP)])
def test_edits_allowed_on_last_day(session, kind, start):
    last_day = P.period_end(kind, start)
    g = tr.create_goal(session, kind, start, "g", 10, "pages", today=last_day)
    tr.log_progress(session, g.id, 2, on=last_day, today=last_day)
    tr.set_process(session, kind, start, "p", today=last_day)
    tr.set_process(session, kind, start, "p2", today=last_day)
    sac = tr.add_sacrifice(session, kind, start, "s", today=last_day)
    tr.mark_sacrifice_made(session, sac.id, today=last_day)
    tr.update_goal(session, g.id, target=12, today=last_day)


# ---------- review cutoff ----------

@pytest.mark.parametrize("kind,start,cutoff", [
    (DAY, TUE_29_SEP, WED_30_SEP),
    (WEEK, SUN_27_SEP, SUN_4_OCT),
    (MONTH, SEP, THU_1_OCT),
])
def test_review_open_during_and_until_cutoff_then_locked(session, kind, start, cutoff):
    tr.set_review(session, kind, start, "during", today=P.period_start(kind, start))
    tr.set_review(session, kind, start, "on cutoff day", today=cutoff)
    with pytest.raises(TaskError, match="closed"):
        tr.set_review(session, kind, start, "too late", today=cutoff + timedelta(days=1))
    session.expire_all()
    assert tr.get_entry(session, kind, start).review == "on cutoff day"


def test_review_cannot_be_written_before_period_starts(session):
    with pytest.raises(TaskError, match="hasn't started"):
        tr.set_review(session, DAY, WED_30_SEP, "early", today=TUE_29_SEP)


def test_review_blank_clears(session):
    tr.set_review(session, DAY, TUE_29_SEP, "x", today=TUE_29_SEP)
    tr.set_review(session, DAY, TUE_29_SEP, "  ", today=TUE_29_SEP)
    assert tr.get_entry(session, DAY, TUE_29_SEP).review is None


# ---------- week spanning two months ----------

def test_spanning_week_stays_open_after_its_first_month_locks(session):
    m, w, _ = reading_chain(session, today=SUN_27_SEP)
    today = THU_1_OCT  # September has ended, the week hasn't
    with pytest.raises(TaskError, match="read-only"):
        tr.create_goal(session, MONTH, SEP, "late", today=today)
    with pytest.raises(TaskError, match="read-only"):
        tr.log_progress(session, m.id, 5, on=WED_30_SEP, today=today)
    with pytest.raises(TaskError, match="read-only"):
        tr.set_process(session, MONTH, SEP, "late", today=today)
    # the week is still editable
    tr.set_process(session, WEEK, SUN_27_SEP, "read at night", today=today)
    tr.add_sacrifice(session, WEEK, SUN_27_SEP, "no games", today=today)
    tr.log_progress(session, w.id, 20, on=THU_1_OCT, today=today)
    d = tr.create_goal(session, DAY, THU_1_OCT, "read 15", 15, "pages", parent_id=w.id, today=today)
    tr.log_progress(session, d.id, 15, today=today)
    assert tr.progress(w).text == "35/110 pages"
    # September's review is still open on 1 Oct, closed on 2 Oct
    tr.set_review(session, MONTH, SEP, "good month", today=THU_1_OCT)
    with pytest.raises(TaskError, match="closed"):
        tr.set_review(session, MONTH, SEP, "edit", today=FRI_2_OCT)


def test_spanning_week_locks_after_saturday_and_review_after_sunday(session):
    _, w, _ = reading_chain(session, today=SUN_27_SEP)
    tr.log_progress(session, w.id, 5, on=SAT_3_OCT, today=SAT_3_OCT)
    with pytest.raises(TaskError, match="read-only"):
        tr.log_progress(session, w.id, 5, on=SAT_3_OCT, today=SUN_4_OCT)
    with pytest.raises(TaskError, match="read-only"):
        tr.set_process(session, WEEK, SUN_27_SEP, "p", today=SUN_4_OCT)
    tr.set_review(session, WEEK, SUN_27_SEP, "ok week", today=SUN_4_OCT)
    with pytest.raises(TaskError, match="closed"):
        tr.set_review(session, WEEK, SUN_27_SEP, "later", today=MON_5_OCT)


def test_week_can_link_to_ended_month_while_week_is_open(session):
    """Decision (TASKS.md): progress flows up links whatever the date, so the
    picked month keeps receiving this week's progress; the month's own data
    stays read-only."""
    sep = tr.create_goal(session, MONTH, SEP, "sep", 500, "pages", today=WED_30_SEP)
    w = tr.create_goal(session, WEEK, SUN_27_SEP, "w", 110, "pages", parent_id=sep.id, today=THU_1_OCT)
    tr.log_progress(session, w.id, 10, on=THU_1_OCT, today=THU_1_OCT)
    assert tr.progress(sep).text == "10/500 pages"


# ---------- dates of logs ----------

def test_log_date_must_be_inside_period_and_not_future(session):
    _, w, _ = reading_chain(session)
    monday = tr.create_goal(session, DAY, MON_28_SEP, "monday", 5, "pages", today=SUN_27_SEP)
    with pytest.raises(TaskError, match="outside"):
        tr.log_progress(session, monday.id, 1, on=SUN_27_SEP, today=MON_28_SEP)
    with pytest.raises(TaskError, match="future"):
        tr.log_progress(session, w.id, 1, on=TUE_29_SEP, today=MON_28_SEP)
    with pytest.raises(TaskError):
        tr.log_progress(session, w.id, 0, today=MON_28_SEP)


def test_future_periods_can_be_planned(session):
    g = tr.create_goal(session, DAY, WED_30_SEP, "tomorrow's goal", today=TUE_29_SEP)
    tr.set_process(session, WEEK, SUN_4_OCT, "next week's process", today=TUE_29_SEP)
    tr.add_sacrifice(session, MONTH, OCT, "no sugar", today=TUE_29_SEP)
    assert g.id
