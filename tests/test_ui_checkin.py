"""End-of-duration check-in: failing or skipping still needs a reason.
Since the v1.2 fixes the end alarm rings first; the check-in follows Dismiss."""

import io
from datetime import date, datetime, time

import pytest
from rich.console import Console

from tomits import services as svc
from tomits import ui


class Silent:
    def play_burst(self):
        pass


class Quiet:
    def notify(self, *a, **k):
        pass


@pytest.fixture
def app(db_file, monkeypatch):
    monkeypatch.setattr(ui, "console", Console(file=io.StringIO()))
    today = date.today()
    return ui.App(db_file, notifier=Quiet(), clock=lambda: datetime.combine(today, time(23, 59)), player=Silent())


def _answer(monkeypatch, *answers):
    it = iter(answers)
    monkeypatch.setattr(ui.Prompt, "ask", classmethod(lambda cls, *a, **k: next(it)))


def _due_task(app):
    with app.Session() as s:
        return svc.add_task(s, "Write UI", 45, start_time=time(9, 0)).id


def test_checkin_fail_requires_reason(app, monkeypatch):
    task_id = _due_task(app)
    app.alarms.check()  # end is due; the alarm rings
    _answer(monkeypatch, "d", "f", "", "  ", "took longer")  # dismiss, then check-in
    app.attend()
    with app.Session() as s:
        t = svc.get_task(s, task_id)
        assert (t.status, t.latest_reason) == ("failed", "took longer")


def test_checkin_done(app, monkeypatch):
    task_id = _due_task(app)
    app.alarms.check()
    _answer(monkeypatch, "d", "d")  # dismiss, then "done"
    app.attend()
    with app.Session() as s:
        assert svc.get_task(s, task_id).status == "done"


def test_checkin_later_leaves_task_open_and_does_not_ask_again(app, monkeypatch):
    task_id = _due_task(app)
    app.alarms.check()
    _answer(monkeypatch, "d", "l")  # dismiss, then "later"
    app.attend()
    app.alarms.check()
    assert app.checkins.empty()
    with app.Session() as s:
        assert svc.get_task(s, task_id).status == "pending"


def test_checkin_skipped_if_task_already_closed(app, monkeypatch):
    task_id = _due_task(app)
    app.alarms.check()
    with app.Session() as s:
        svc.complete_task(s, task_id)
    _answer(monkeypatch, "d")  # dismiss; any further prompt would raise StopIteration
    app.attend()
