"""Goal shape and link rules: same unit, one level up, containing period."""

import pytest

from tomits import tracking as tr
from tomits.errors import TaskError
from helpers import DAY, MONTH, MON_5_OCT, OCT, SEP, SUN_27_SEP, SUN_4_OCT, WEEK, reading_chain

T = SUN_27_SEP


def test_unit_mismatch_on_link_is_refused(session):
    w = tr.create_goal(session, WEEK, T, "read", 110, "pages", today=T)
    with pytest.raises(TaskError, match="same unit"):
        tr.create_goal(session, DAY, T, "read hours", 2, "hours", parent_id=w.id, today=T)


def test_units_match_ignoring_case_and_spaces(session):
    w = tr.create_goal(session, WEEK, T, "read", 110, "pages", today=T)
    tr.create_goal(session, DAY, T, "read", 10, "  Pages ", parent_id=w.id, today=T)


def test_numeric_and_no_target_goals_cannot_link(session):
    numeric_w = tr.create_goal(session, WEEK, T, "read", 110, "pages", today=T)
    plain_w = tr.create_goal(session, WEEK, T, "finish", today=T)
    with pytest.raises(TaskError, match="same unit"):
        tr.create_goal(session, DAY, T, "plain day", parent_id=numeric_w.id, today=T)
    with pytest.raises(TaskError, match="same unit"):
        tr.create_goal(session, DAY, T, "numeric day", 10, "pages", parent_id=plain_w.id, today=T)


def test_day_links_to_week_only_not_month(session):
    m = tr.create_goal(session, MONTH, SEP, "read", 500, "pages", today=T)
    with pytest.raises(TaskError, match="only link to a week"):
        tr.create_goal(session, DAY, T, "read", 10, "pages", parent_id=m.id, today=T)


def test_day_cannot_link_to_another_weeks_goal(session):
    next_week = tr.create_goal(session, WEEK, SUN_4_OCT, "read", 110, "pages", today=T)
    with pytest.raises(TaskError, match="doesn't contain"):
        tr.create_goal(session, DAY, T, "read", 10, "pages", parent_id=next_week.id, today=T)


def test_spanning_week_may_link_to_either_month_but_not_a_third(session):
    sep = tr.create_goal(session, MONTH, SEP, "sep", 500, "pages", today=T)
    oct_ = tr.create_goal(session, MONTH, OCT, "oct", 500, "pages", today=T)
    tr.create_goal(session, WEEK, T, "a", 1, "pages", parent_id=sep.id, today=T)
    tr.create_goal(session, WEEK, T, "b", 1, "pages", parent_id=oct_.id, today=T)
    # the week of 4 Oct lies wholly in October
    with pytest.raises(TaskError, match="doesn't contain"):
        tr.create_goal(session, WEEK, SUN_4_OCT, "c", 1, "pages", parent_id=sep.id, today=T)
    cands = tr.link_candidates(session, WEEK, T, "pages")
    assert {g.title for g in cands} == {"sep", "oct"}


def test_monthly_goals_do_not_link(session):
    sep = tr.create_goal(session, MONTH, SEP, "sep", 500, "pages", today=T)
    with pytest.raises(TaskError):
        tr.create_goal(session, MONTH, OCT, "oct", 500, "pages", parent_id=sep.id, today=T)


@pytest.mark.parametrize("target,unit", [(10, None), (10, "  "), (None, "pages"), (0, "pages"), (-5, "pages")])
def test_goal_shape_rules(session, target, unit):
    with pytest.raises(TaskError):
        tr.create_goal(session, DAY, T, "x", target, unit, today=T)


def test_goal_needs_title(session):
    with pytest.raises(TaskError):
        tr.create_goal(session, DAY, T, "   ", today=T)


def test_changing_unit_that_breaks_a_link_is_refused(session):
    m, w, d = reading_chain(session)
    with pytest.raises(TaskError, match="same unit"):
        tr.update_goal(session, w.id, unit="hours", today=T)  # parent m and child d are pages
    with pytest.raises(TaskError, match="same unit"):
        tr.update_goal(session, d.id, unit="hours", today=T)


def test_edit_title_and_target(session):
    _, w, _ = reading_chain(session)
    tr.update_goal(session, w.id, title="read 150", target=150, today=T)
    assert (w.title, tr.progress(w).text) == ("read 150", "0/150 pages")


def test_cannot_switch_to_no_target_after_logging(session):
    _, _, d = reading_chain(session)
    tr.log_progress(session, d.id, 3, today=T)
    with pytest.raises(TaskError, match="logged progress"):
        tr.update_goal(session, d.id, target=None, today=T)


def test_relink_and_unlink(session):
    m, w, d = reading_chain(session)
    tr.update_goal(session, d.id, parent_id=None, today=T)
    tr.log_progress(session, d.id, 10, today=T)
    assert tr.progress(w).text == "0/110 pages"
    tr.update_goal(session, d.id, parent_id=w.id, today=T)
    assert tr.progress(w).text == "10/110 pages"


def test_delete_goal_rules(session):
    m, w, d = reading_chain(session)
    with pytest.raises(TaskError, match="link"):
        tr.delete_goal(session, w.id, today=T)  # d links to it
    tr.log_progress(session, d.id, 1, today=T)
    with pytest.raises(TaskError, match="logged"):
        tr.delete_goal(session, d.id, today=T)
    spare = tr.create_goal(session, DAY, T, "spare", today=T)
    tr.delete_goal(session, spare.id, today=T)
    assert [g.title for g in tr.goals_for_period(session, DAY, T)] == ["read 10 pages"]
