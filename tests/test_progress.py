"""v1.1 goal progress: logged / target, rolling up the links.
(Replaces the v1.0 task-count progress tests; that model was removed.)"""

import pytest

from tomits import tracking as tr
from helpers import (DAY, MONTH, MON_28_SEP, OCT, SEP, SUN_27_SEP, TUE_29_SEP, WEEK, reading_chain)


def text(goal):
    return tr.progress(goal).text


def test_spec_example_10_pages_rolls_up(session):
    m, w, d = reading_chain(session)
    tr.log_progress(session, d.id, 10, on=SUN_27_SEP, today=SUN_27_SEP)
    assert (text(d), text(w), text(m)) == ("10/10 pages", "10/110 pages", "10/500 pages")
    assert tr.progress(d).done and not tr.progress(w).done


def test_several_days_add_up_on_week_and_month(session):
    m, w, d = reading_chain(session, today=SUN_27_SEP)
    d2 = tr.create_goal(session, DAY, MON_28_SEP, "read 20", 20, "pages", parent_id=w.id, today=SUN_27_SEP)
    tr.log_progress(session, d.id, 10, today=SUN_27_SEP)
    tr.log_progress(session, d2.id, 25, on=MON_28_SEP, today=MON_28_SEP)
    assert (text(d2), text(w), text(m)) == ("25/20 pages", "35/110 pages", "35/500 pages")


def test_logging_on_week_goal_reaches_month_not_days(session):
    m, w, d = reading_chain(session)
    tr.log_progress(session, w.id, 30, today=TUE_29_SEP)
    assert (text(d), text(w), text(m)) == ("0/10 pages", "30/110 pages", "30/500 pages")


def test_unlinked_goal_does_not_roll_up(session):
    m, w, _ = reading_chain(session)
    solo = tr.create_goal(session, DAY, SUN_27_SEP, "read solo", 5, "pages", today=SUN_27_SEP)
    tr.log_progress(session, solo.id, 5, today=SUN_27_SEP)
    assert (text(solo), text(w), text(m)) == ("5/5 pages", "0/110 pages", "0/500 pages")


def test_over_target_is_shown_and_bar_is_capped(session):
    _, _, d = reading_chain(session)
    tr.log_progress(session, d.id, 15, today=SUN_27_SEP)
    p = tr.progress(d)
    assert p.text == "15/10 pages" and p.fraction == 1.0 and p.done


def test_decimal_amounts(session):
    g = tr.create_goal(session, DAY, SUN_27_SEP, "run", 5, "km", today=SUN_27_SEP)
    tr.log_progress(session, g.id, 2.5, today=SUN_27_SEP)
    assert text(g) == "2.5/5 km"


def test_no_target_goals_are_done_or_not_and_do_not_roll_up(session):
    m = tr.create_goal(session, MONTH, SEP, "finish book", today=SUN_27_SEP)
    w = tr.create_goal(session, WEEK, SUN_27_SEP, "finish ch. 3", parent_id=m.id, today=SUN_27_SEP)
    assert (text(w), text(m)) == ("not done", "not done")
    tr.set_goal_done(session, w.id, True, today=SUN_27_SEP)
    assert (text(w), text(m)) == ("done", "not done")
    tr.set_goal_done(session, w.id, False, today=SUN_27_SEP)
    assert text(w) == "not done"


def test_no_target_goal_cannot_take_amounts_and_numeric_cannot_be_marked(session):
    plain = tr.create_goal(session, DAY, SUN_27_SEP, "call mom", today=SUN_27_SEP)
    _, _, d = reading_chain(session)
    with pytest.raises(tr.TaskError):
        tr.log_progress(session, plain.id, 1, today=SUN_27_SEP)
    with pytest.raises(tr.TaskError):
        tr.set_goal_done(session, d.id, True, today=SUN_27_SEP)


def test_week_spanning_two_months_rolls_into_the_month_picked(session):
    sep = tr.create_goal(session, MONTH, SEP, "sep reading", 500, "pages", today=SUN_27_SEP)
    oct_ = tr.create_goal(session, MONTH, OCT, "oct reading", 400, "pages", today=SUN_27_SEP)
    w = tr.create_goal(session, WEEK, SUN_27_SEP, "week reading", 110, "pages", parent_id=oct_.id, today=SUN_27_SEP)
    tr.log_progress(session, w.id, 10, on=SUN_27_SEP, today=SUN_27_SEP)  # a September day
    assert (text(w), text(oct_), text(sep)) == ("10/110 pages", "10/400 pages", "0/500 pages")


def test_removing_a_log_updates_the_roll_up(session):
    m, w, d = reading_chain(session)
    log = tr.log_progress(session, d.id, 10, today=SUN_27_SEP)
    tr.delete_log(session, log.id, today=SUN_27_SEP)
    assert (text(d), text(w), text(m)) == ("0/10 pages", "0/110 pages", "0/500 pages")


@pytest.mark.parametrize("raw,value", [("10", 10), ("10 pages", 10), ("2.5", 2.5), ("0", 0)])
def test_parse_amount(raw, value):
    assert tr.parse_amount(raw) == value


@pytest.mark.parametrize("raw", ["", "pages", "-3"])
def test_parse_amount_rejects(raw):
    with pytest.raises(tr.TaskError):
        tr.parse_amount(raw)
