"""Mandatory fill-in: each missing goal / process item is reminded once
(v1.6 single-reminder rule; replaces the v1.1 repeat every 5 minutes)."""

import time as _time
from datetime import datetime, time

from tomits import tracking as tr
from tomits.db import make_session_factory
from tomits import reminders as R
from tomits.reminders import REMINDER_INTERVAL_SECONDS, ReminderService
from helpers import DAY, MONTH, MON_28_SEP, SEP, SUN_27_SEP, TUE_29_SEP, WEEK

T = TUE_29_SEP


def parts(missing):
    return {(m.kind.value, m.parts) for m in missing}


def test_empty_database_misses_everything(session):
    assert parts(tr.missing_fill_ins(session, T)) == {
        ("day", ("goal", "process")), ("week", ("goal", "process")), ("month", ("goal", "process")),
    }


def test_goal_and_process_are_both_needed(session):
    tr.create_goal(session, DAY, T, "g", today=T)
    tr.set_process(session, WEEK, T, "p", today=T)
    assert parts(tr.missing_fill_ins(session, T)) == {
        ("day", ("process",)), ("week", ("goal",)), ("month", ("goal", "process")),
    }


def test_nothing_missing_when_all_filled(session):
    for kind in (DAY, WEEK, MONTH):
        tr.create_goal(session, kind, T, "g", today=T)
        tr.set_process(session, kind, T, "p", today=T)
    assert tr.missing_fill_ins(session, T) == []


def test_other_periods_and_other_fields_do_not_count(session):
    tr.create_goal(session, DAY, MON_28_SEP, "yesterday", today=MON_28_SEP)
    tr.set_process(session, DAY, MON_28_SEP, "p", today=MON_28_SEP)
    tr.add_sacrifice(session, DAY, T, "s", today=T)
    tr.set_review(session, DAY, T, "r", today=T)
    assert ("day", ("goal", "process")) in parts(tr.missing_fill_ins(session, T))


def test_message_names_period_and_what_is_missing(session):
    tr.create_goal(session, DAY, T, "g", today=T)
    msgs = {m.message for m in tr.missing_fill_ins(session, T)}
    assert "Tue 29 Sep 2026: missing process" in msgs
    assert "Week Sun 27 Sep - Sat 03 Oct 2026: missing goal and process" in msgs
    assert "September 2026: missing goal and process" in msgs


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def notify(self, title, message, urgent=False):
        self.sent.append(message)


def test_interval_is_a_check_not_a_repeat():
    assert REMINDER_INTERVAL_SECONDS <= 300


def _service(db_file, notifier, batches=None, when=T, hour=10):
    return ReminderService(make_session_factory(db_file), notifier,
                           on_reminder=(batches.append if batches is not None else None),
                           clock=lambda: datetime.combine(when, time(hour, 0)))


def test_each_missing_item_is_reminded_once_only(db_file):
    notifier, batches = FakeNotifier(), []
    service = _service(db_file, notifier, batches)
    first = service.check()
    assert len(notifier.sent) == 3 and len(batches) == 1          # one per period, both parts listed
    assert {(m.kind.value, m.parts) for m in first} == {
        ("day", ("goal", "process")), ("week", ("goal", "process")), ("month", ("goal", "process"))}
    notifier.sent.clear()
    for _ in range(3):                                              # never fires again
        assert service.check() == []
    assert notifier.sent == [] and len(batches) == 1


def test_reminder_does_not_return_after_a_restart(db_file):
    notifier = FakeNotifier()
    _service(db_file, notifier).check()
    notifier.sent.clear()
    assert _service(db_file, notifier).check() == [] and notifier.sent == []


def test_banner_stays_until_filled_and_dismissed_items_stay_hidden(db_file):
    Session = make_session_factory(db_file)
    _service(db_file, FakeNotifier()).check()
    with Session() as s:
        keys = {i.key for i in R.active_reminders(s, T)}
        assert len(keys) == 6                                       # still shown: nothing filled in
        R.dismiss_reminder(s, DAY, T, "goal")
        keys = {i.key for i in R.active_reminders(s, T)}
        assert "day:2026-09-29:goal" not in keys and len(keys) == 5
        tr.set_process(s, DAY, T, "p", today=T)                     # filling in removes the banner item
        keys = {i.key for i in R.active_reminders(s, T)}
        assert "day:2026-09-29:process" not in keys and len(keys) == 4


def test_new_period_gives_its_own_single_reminder(db_file):
    notifier = FakeNotifier()
    _service(db_file, notifier, when=MON_28_SEP).check()
    notifier.sent.clear()
    new = _service(db_file, notifier, when=T).check()                # next day: only the new day is new
    assert [(m.kind.value, m.parts) for m in new] == [("day", ("goal", "process"))]
    assert notifier.sent == ["Tue 29 Sep 2026: missing goal and process"]


def test_item_that_becomes_missing_later_gets_one_reminder(db_file):
    Session = make_session_factory(db_file)
    with Session() as s:
        for kind in (DAY, WEEK, MONTH):
            tr.create_goal(s, kind, T, "g", today=T)
            tr.set_process(s, kind, T, "p", today=T)
    notifier = FakeNotifier()
    assert _service(db_file, notifier).check() == []
    with Session() as s:                                            # month goal deleted (a mistake)
        tr.delete_goal(s, tr.goals_for_period(s, MONTH, T)[0].id, today=T)
    assert [m.parts for m in _service(db_file, notifier).check()] == [("goal",)]
    assert _service(db_file, notifier).check() == []


def test_service_thread_checks_immediately_without_blocking_and_does_not_repeat(db_file):
    notifier = FakeNotifier()
    service = ReminderService(make_session_factory(db_file), notifier, interval_seconds=1,
                              clock=lambda: datetime.combine(T, time(10, 0)))
    started = _time.monotonic()
    service.start()
    assert _time.monotonic() - started < 0.5  # start() returns at once
    _time.sleep(2.5)
    service.stop()
    assert len(notifier.sent) == 3            # immediate check, then no repeats
    assert service.last_error is None
