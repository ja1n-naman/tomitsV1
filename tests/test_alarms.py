from datetime import date, datetime, time, timedelta

import pytest

from tomits import services as svc
from tomits.alarms import END_CHECK, HEADS_UP, AlarmService, collect_due

DAY = date(2026, 10, 1)


def at(h, m=0, day=DAY):
    return datetime.combine(day, time(h, m))


def timed(session, title="Write UI", start=time(14, 0), minutes=45, day=DAY):
    return svc.add_task(session, title, minutes, planned_for=day, start_time=start)


def kinds(alarms):
    return [(a.kind, a.missed) for a in alarms]


# ---------- collect_due ----------

def test_untimed_tasks_never_alarm(session):
    svc.add_task(session, "no time", 30, planned_for=DAY)
    assert collect_due(session, at(23, 59)) == []


def test_nothing_before_heads_up_window(session):
    timed(session)
    assert collect_due(session, at(13, 54)) == []


def test_heads_up_fires_5_min_before_and_only_once(session):
    timed(session)
    assert kinds(collect_due(session, at(13, 55))) == [(HEADS_UP, False)]
    assert collect_due(session, at(13, 58)) == []


def test_end_check_fires_when_duration_is_over_and_only_once(session):
    timed(session)
    collect_due(session, at(13, 55))
    assert collect_due(session, at(14, 44)) == []
    assert kinds(collect_due(session, at(14, 45))) == [(END_CHECK, False)]
    assert collect_due(session, at(15, 0)) == []


def test_live_heads_up_is_dropped_if_task_already_started(session):
    # e.g. task added at 14:10 with start 14:00: no "starting soon" alarm
    timed(session)
    assert collect_due(session, at(14, 10)) == []
    assert kinds(collect_due(session, at(14, 45))) == [(END_CHECK, False)]


def test_closed_tasks_do_not_alarm(session):
    t = timed(session)
    svc.complete_task(session, t.id)
    assert collect_due(session, at(15, 0)) == []
    t2 = timed(session, "other", start=time(16, 0))  # 14:00 is taken by t (no overlaps since v1.2 fixes)
    svc.fail_task(session, t2.id, "sick")
    assert collect_due(session, at(17, 0)) == []


def test_future_days_do_not_alarm(session):
    timed(session, day=DAY + timedelta(days=1))
    assert collect_due(session, at(23, 59)) == []


def test_startup_reports_passed_end_as_missed(session):
    timed(session)
    assert kinds(collect_due(session, at(16, 0), startup=True)) == [(END_CHECK, True)]
    assert collect_due(session, at(16, 1)) == []  # not replayed later


def test_startup_reports_running_task_as_missed_then_end_fires_live(session):
    timed(session)  # 14:00-14:45
    assert kinds(collect_due(session, at(14, 20), startup=True)) == [(HEADS_UP, True)]
    assert kinds(collect_due(session, at(14, 45))) == [(END_CHECK, False)]


def test_startup_inside_heads_up_window_is_live_not_missed(session):
    timed(session)
    assert kinds(collect_due(session, at(13, 57), startup=True)) == [(HEADS_UP, False)]


def test_previous_day_open_task_is_missed_at_startup(session):
    timed(session, day=DAY - timedelta(days=1))
    alarms = collect_due(session, at(9, 0), startup=True)
    assert kinds(alarms) == [(END_CHECK, True)]


def test_changing_time_rearms_alarms(session):
    t = timed(session)
    collect_due(session, at(13, 55))
    svc.set_start_time(session, t.id, time(16, 0))
    assert kinds(collect_due(session, at(15, 55))) == [(HEADS_UP, False)]


def test_clearing_time_stops_alarms(session):
    t = timed(session)
    svc.set_start_time(session, t.id, None)
    assert collect_due(session, at(23, 0)) == []


# ---------- AlarmService ----------

class FakeNotifier:
    def __init__(self):
        self.sent = []

    def notify(self, title, message, urgent=False):
        self.sent.append((title, message, urgent))


def test_service_notifies_live_alarms_only(db_file):
    from tomits.db import make_session_factory

    Session = make_session_factory(db_file)
    with Session() as s:
        timed(s, "missed one", start=time(9, 0))
        timed(s, "soon", start=time(14, 0))
    now = [at(13, 56)]
    notifier, seen = FakeNotifier(), []
    service = AlarmService(Session, notifier, on_alarm=seen.append, clock=lambda: now[0])

    found = service.check(startup=True)
    assert sorted((a.title, a.missed) for a in found) == [("missed one", True), ("soon", False)]
    assert [m for _, m, _ in notifier.sent] == ["'soon' starts at 14:00 (45m planned)."]
    assert [a.title for a in seen] == ["soon"]

    now[0] = at(14, 45)
    service.check()
    assert notifier.sent[-1][2] is True  # end check is urgent
    assert seen[-1].kind == END_CHECK


def test_service_thread_starts_and_stops(db_file):
    from tomits.db import make_session_factory

    service = AlarmService(make_session_factory(db_file), FakeNotifier(), interval_seconds=1)
    service.start()
    service.stop()
    assert service.last_error is None
