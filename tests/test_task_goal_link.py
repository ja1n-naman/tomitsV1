"""Timetable tasks and goals: optional link, contribution on completion,
and no goal creation from the timetable."""

import io
from datetime import date, datetime, time

import pytest
from rich.console import Console

from tomits import services as svc
from tomits import tracking as tr
from tomits import ui
from tomits.errors import TaskError
from helpers import DAY, MONTH, MON_28_SEP, SEP, SUN_27_SEP, THU_1_OCT, TUE_29_SEP, WEEK, reading_chain


def test_task_without_goal_completes_normally(session):
    t = svc.add_task(session, "attend clg", 300, planned_for=SUN_27_SEP, today=SUN_27_SEP)
    svc.complete_task(session, t.id, today=SUN_27_SEP)
    assert t.status == "done" and t.goal is None


def test_linked_task_logs_its_contribution_and_it_rolls_up(session):
    m, w, d = reading_chain(session)
    t = svc.add_task(session, "read ch. 1", 30, goal_id=d.id, planned_for=SUN_27_SEP, today=SUN_27_SEP)
    svc.complete_task(session, t.id, contribution=10, today=SUN_27_SEP)
    assert [(l.amount, l.task_id, l.logged_for) for l in d.logs] == [(10, t.id, SUN_27_SEP)]
    assert (tr.progress(d).text, tr.progress(w).text, tr.progress(m).text) == \
        ("10/10 pages", "10/110 pages", "10/500 pages")


def test_contribution_defaults_to_zero_and_logs_nothing(session):
    _, _, d = reading_chain(session)
    t = svc.add_task(session, "read", 30, goal_id=d.id, planned_for=SUN_27_SEP, today=SUN_27_SEP)
    svc.complete_task(session, t.id, today=SUN_27_SEP)
    assert t.status == "done" and d.logs == []


def test_linked_no_target_goal_can_be_marked_done(session):
    g = tr.create_goal(session, WEEK, SUN_27_SEP, "finish chapter", today=SUN_27_SEP)
    t = svc.add_task(session, "write", 60, goal_id=g.id, planned_for=SUN_27_SEP, today=SUN_27_SEP)
    assert tr.contribution_for(t, SUN_27_SEP).mode == "mark_done"
    svc.complete_task(session, t.id, mark_goal_done=True, today=SUN_27_SEP)
    assert tr.progress(g).done


def test_wrong_kind_of_contribution_is_refused_and_task_stays_open(session):
    plain = tr.create_goal(session, DAY, SUN_27_SEP, "plain", today=SUN_27_SEP)
    t = svc.add_task(session, "x", 10, goal_id=plain.id, planned_for=SUN_27_SEP, today=SUN_27_SEP)
    with pytest.raises(TaskError):
        svc.complete_task(session, t.id, contribution=5, today=SUN_27_SEP)
    assert t.status == "pending"
    free = svc.add_task(session, "free", 10, planned_for=SUN_27_SEP, today=SUN_27_SEP)
    with pytest.raises(TaskError, match="isn't linked"):
        svc.complete_task(session, free.id, contribution=5, today=SUN_27_SEP)


def test_negative_contribution_refused(session):
    _, _, d = reading_chain(session)
    t = svc.add_task(session, "read", 30, goal_id=d.id, planned_for=SUN_27_SEP, today=SUN_27_SEP)
    with pytest.raises(TaskError):
        svc.complete_task(session, t.id, contribution=-1, today=SUN_27_SEP)


# ---------- rescheduled into another period (decision in TASKS.md) ----------

def test_contribution_is_logged_on_completion_day_whatever_the_planned_day(session):
    """Task linked to Sunday's goal but planned for Monday: completing it on
    Sunday logs to Sunday's goal."""
    _, _, d = reading_chain(session)
    t = svc.add_task(session, "read", 30, goal_id=d.id, planned_for=MON_28_SEP, today=SUN_27_SEP)
    svc.complete_task(session, t.id, contribution=4, today=SUN_27_SEP)
    assert d.logs[0].logged_for == SUN_27_SEP


def test_task_completed_after_its_goals_period_cannot_log(session):
    _, _, d = reading_chain(session)  # Sunday's goal
    t = svc.add_task(session, "read", 30, goal_id=d.id, planned_for=SUN_27_SEP, today=SUN_27_SEP)
    c = tr.contribution_for(t, MON_28_SEP)
    assert c.mode == "closed" and "has ended" in c.note
    with pytest.raises(TaskError):
        svc.complete_task(session, t.id, contribution=10, today=MON_28_SEP)
    svc.complete_task(session, t.id, today=MON_28_SEP)  # still completes with 0
    assert t.status == "done" and d.logs == []


def test_task_linked_to_future_period_goal_cannot_log_yet(session):
    oct_goal = tr.create_goal(session, MONTH, THU_1_OCT, "oct", 100, "pages", today=TUE_29_SEP)
    t = svc.add_task(session, "early", 10, goal_id=oct_goal.id, planned_for=TUE_29_SEP, today=TUE_29_SEP)
    assert tr.contribution_for(t, TUE_29_SEP).mode == "closed"


def test_week_goal_accepts_contribution_from_any_day_in_the_week(session):
    _, w, _ = reading_chain(session)
    t = svc.add_task(session, "read", 30, goal_id=w.id, planned_for=SUN_27_SEP, today=SUN_27_SEP)
    svc.complete_task(session, t.id, contribution=7, today=THU_1_OCT)
    assert tr.progress(w).text == "7/110 pages"


# ---------- timetable can only pick existing, open goals ----------

def test_services_can_no_longer_create_goals():
    assert not hasattr(svc, "create_goal")


def test_task_cannot_link_to_missing_or_ended_goal(session):
    with pytest.raises(TaskError, match="No goal"):
        svc.add_task(session, "x", 10, goal_id=999)
    old = tr.create_goal(session, DAY, SUN_27_SEP, "old", today=SUN_27_SEP)
    with pytest.raises(TaskError, match="has ended"):
        svc.add_task(session, "x", 10, goal_id=old.id)  # real today is after 27 Sep 2026
    with pytest.raises(TaskError, match="has ended"):
        svc.plan_day(session, date.today(), [svc.TaskDraft("x", 10, old.id)])


def test_link_and_unlink_existing_task(session):
    g = tr.create_goal(session, DAY, date.today(), "today", today=date.today())
    t = svc.add_task(session, "x", 10)
    svc.link_task(session, t.id, g.id)
    assert t.goal_id == g.id
    svc.link_task(session, t.id, None)
    assert t.goal_id is None


class Quiet:
    def notify(self, *a, **k):
        pass


@pytest.fixture
def app(db_file, monkeypatch):
    monkeypatch.setattr(ui, "console", Console(file=io.StringIO()))
    monkeypatch.setattr("tomits.ui_common.console", Console(file=io.StringIO()))
    return ui.App(db_file, notifier=Quiet(), clock=lambda: datetime.combine(SUN_27_SEP, time(12, 0)))


def _answer(monkeypatch, *answers):
    it = iter(answers)
    monkeypatch.setattr(ui.Prompt, "ask", classmethod(lambda cls, *a, **k: next(it)))
    monkeypatch.setattr(ui.Confirm, "ask", classmethod(lambda cls, *a, **k: next(it)))


def test_timetable_goal_picker_cannot_create_a_goal(app, monkeypatch):
    with app.Session() as s:
        tr.create_goal(s, DAY, SUN_27_SEP, "existing", today=SUN_27_SEP)
        _answer(monkeypatch, "n")  # 'n' used to mean "new goal"
        with pytest.raises(TaskError):
            app._pick_goal(s)
        assert len(tr.open_goals(s, SUN_27_SEP)) == 1


def test_ui_done_asks_contribution_for_linked_task(app, monkeypatch):
    with app.Session() as s:
        _, _, d = reading_chain(s)
        t = svc.add_task(s, "read", 30, goal_id=d.id, planned_for=SUN_27_SEP, today=SUN_27_SEP)
    _answer(monkeypatch, str(t.id), "10")
    app.done()
    with app.Session() as s:
        assert tr.progress(tr.get_goal(s, d.id)).text == "10/10 pages"


def test_ui_done_on_unlinked_task_asks_nothing_extra(app, monkeypatch):
    with app.Session() as s:
        t = svc.add_task(s, "attend clg", 300, planned_for=SUN_27_SEP, today=SUN_27_SEP)
    _answer(monkeypatch, str(t.id))
    app.done()
    with app.Session() as s:
        assert svc.get_task(s, t.id).status == "done"


def test_tracking_view_switch_keeps_today(app):
    from tomits.ui_tracking import TrackingScreen

    screen = TrackingScreen(app, MONTH)  # September, contains today (27 Sep)
    screen.switch_kind(WEEK)
    assert screen.start == SUN_27_SEP
    screen.switch_kind(DAY)
    assert screen.start == SUN_27_SEP
    screen.start = date(2026, 8, 12)  # browsing an old day
    screen.switch_kind(MONTH)
    assert screen.start == date(2026, 8, 1)
