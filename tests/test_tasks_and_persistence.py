from datetime import date

import pytest

from tomits import services as svc
from tomits.db import make_session_factory


@pytest.mark.parametrize("text,minutes", [("25", 25), ("90m", 90), ("1h", 60), ("1h30", 90), ("1h 30m", 90), ("2H", 120)])
def test_parse_duration(text, minutes):
    assert svc.parse_duration(text) == minutes


@pytest.mark.parametrize("text", ["", "abc", "0", "-5", "1x"])
def test_parse_duration_rejects_bad_input(text):
    with pytest.raises(svc.TaskError):
        svc.parse_duration(text)


def test_task_requires_positive_duration(session):
    with pytest.raises(svc.TaskError):
        svc.add_task(session, "x", 0)


def test_plan_day_is_all_or_nothing(session):
    day = date(2026, 10, 2)
    with pytest.raises(svc.TaskError):
        svc.plan_day(session, day, [svc.TaskDraft("ok", 30), svc.TaskDraft("", 30)])
    assert svc.tasks_for_day(session, day) == []


def test_plan_then_on_the_fly_keeps_order(session):
    day = date.today()
    svc.plan_day(session, day, [svc.TaskDraft("first", 30), svc.TaskDraft("second", 30)])
    svc.add_task(session, "third", 15)
    assert [t.title for t in svc.tasks_for_day(session, day)] == ["first", "second", "third"]


def test_data_survives_restart(db_file):
    from tomits import tracking as tr
    from tomits.periods import PeriodKind

    today = date.today()
    Session = make_session_factory(db_file)
    with Session() as s:
        goal = tr.create_goal(s, PeriodKind.MONTH, today, "Persist me", 50, "pages")
        tr.set_process(s, PeriodKind.MONTH, today, "read daily")
        tr.add_sacrifice(s, PeriodKind.MONTH, today, "no TV")
        done = svc.add_task(s, "done one", 30, goal_id=goal.id)
        failed = svc.add_task(s, "failed one", 30, goal_id=goal.id)
        svc.complete_task(s, done.id, contribution=12)
        svc.fail_task(s, failed.id, "power cut")

    # Fresh engine, as if the app was closed and reopened.
    Session2 = make_session_factory(db_file)
    with Session2() as s:
        entry = tr.get_entry(s, PeriodKind.MONTH, today)
        goal = entry.goals[0]
        assert goal.title == "Persist me"
        assert tr.progress(goal).text == "12/50 pages"
        assert entry.process == "read daily" and entry.sacrifices[0].text == "no TV"
        failed = [t for t in goal.tasks if t.title == "failed one"][0]
        assert failed.latest_reason == "power cut"


def test_overdue_lists_only_open_past_tasks(session):
    past = date(2026, 1, 1)
    open_t = svc.add_task(session, "open", 10, planned_for=past)
    closed = svc.add_task(session, "closed", 10, planned_for=past)
    svc.complete_task(session, closed.id)
    svc.add_task(session, "today", 10)
    assert [t.id for t in svc.overdue_tasks(session)] == [open_t.id]
