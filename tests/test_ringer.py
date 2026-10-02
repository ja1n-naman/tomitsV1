"""Ringing alarms: repeat until dismissed or snoozed, stop after 2 minutes,
snooze length from settings. Uses a fake clock and a fake tone player."""

import io
import threading
import time as _time
from datetime import datetime, timedelta

import pytest
from rich.console import Console

from tomits import ui
from tomits.alarms import END_CHECK, HEADS_UP, Alarm
from tomits.errors import TaskError
from tomits.ringer import RERUNG, RING_LIMIT, TIMED_OUT, Ringer, key_of
from tomits.settings import Settings, load_settings, save_settings, settings_path, validate_snooze

T0 = datetime(2026, 10, 1, 14, 0, 0)


class Clock:
    def __init__(self, now=T0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


class CountingPlayer:
    def __init__(self):
        self.bursts = 0

    def play_burst(self):
        self.bursts += 1


class BrokenPlayer:
    def play_burst(self):
        raise RuntimeError("Failed to beep")


def alarm(kind=HEADS_UP, task_id=1):
    return Alarm(kind, task_id, "Write UI", T0, T0 + timedelta(minutes=45))


@pytest.fixture
def clock():
    return Clock()


def make(clock, minutes=5, player=None, events=None):
    return Ringer(player=player or CountingPlayer(), snooze_minutes=lambda: minutes, clock=clock,
                  on_event=(lambda e, a: events.append(e)) if events is not None else None)


# ---------- 2-minute stop ----------

def test_ring_limit_is_two_minutes():
    assert RING_LIMIT == timedelta(minutes=2)


def test_rings_until_two_minutes_then_stops_by_itself(clock):
    events = []
    r = make(clock, events=events)
    r.ring(alarm())
    clock.advance(seconds=119)
    assert r.tick() == [] and r.is_ringing
    clock.advance(seconds=1)
    assert r.tick() == [(TIMED_OUT, alarm())]
    assert not r.is_ringing and events == [TIMED_OUT]


def test_seconds_left(clock):
    r = make(clock)
    r.ring(alarm())
    clock.advance(seconds=30)
    assert r.ringing()[0].seconds_left(clock()) == 90


# ---------- dismiss ----------

def test_dismiss_stops_ringing(clock):
    r = make(clock)
    r.ring(alarm())
    assert r.dismiss(key_of(alarm())) == alarm()
    assert not r.is_ringing
    clock.advance(minutes=10)
    assert r.tick() == []


# ---------- snooze ----------

def test_snooze_rerings_after_default_five_minutes(clock):
    events = []
    r = make(clock, events=events)
    r.ring(alarm())
    clock.advance(seconds=20)
    due = r.snooze(key_of(alarm()))
    assert due == T0 + timedelta(seconds=20, minutes=5)
    assert not r.is_ringing
    clock.advance(minutes=4, seconds=59)
    assert r.tick() == [] and not r.is_ringing
    clock.advance(seconds=1)
    assert r.tick() == [(RERUNG, alarm())] and r.is_ringing
    assert events == [RERUNG]


def test_snooze_length_follows_the_setting(clock):
    settings = Settings(snooze_minutes=5)
    r = Ringer(player=CountingPlayer(), snooze_minutes=lambda: settings.snooze_minutes, clock=clock)
    r.ring(alarm())
    settings.snooze_minutes = 12
    assert r.snooze(key_of(alarm())) == T0 + timedelta(minutes=12)


def test_two_minute_limit_restarts_after_snooze(clock):
    r = make(clock)
    r.ring(alarm())
    clock.advance(seconds=100)
    r.snooze(key_of(alarm()))
    clock.advance(minutes=5)
    r.tick()  # re-rings now
    clock.advance(seconds=119)
    assert r.tick() == [] and r.is_ringing
    clock.advance(seconds=1)
    assert r.tick() == [(TIMED_OUT, alarm())]


def test_snooze_can_repeat(clock):
    r = make(clock, minutes=3)
    r.ring(alarm())
    for _ in range(3):
        r.snooze(key_of(alarm()))
        clock.advance(minutes=3)
        r.tick()
        assert r.is_ringing
    assert r.ringing()[0].snoozes == 3


def test_dismissing_a_snoozed_alarm_cancels_the_rering(clock):
    r = make(clock)
    r.ring(alarm())
    r.snooze(key_of(alarm()))
    assert r.dismiss(key_of(alarm())) == alarm()
    clock.advance(minutes=10)
    assert r.tick() == [] and not r.is_ringing


def test_snoozing_a_stopped_alarm_raises(clock):
    r = make(clock)
    with pytest.raises(KeyError):
        r.snooze(key_of(alarm()))


def test_several_alarms_ring_independently(clock):
    r = make(clock)
    r.ring(alarm(HEADS_UP, 1))
    clock.advance(seconds=60)
    r.ring(alarm(END_CHECK, 2))
    clock.advance(seconds=60)
    assert r.tick() == [(TIMED_OUT, alarm(HEADS_UP, 1))]
    assert [x.alarm.task_id for x in r.ringing()] == [2]


# ---------- sound ----------

def test_tone_plays_only_while_ringing(clock):
    player = CountingPlayer()
    r = make(clock, player=player)
    assert r.play_once() is False and player.bursts == 0
    r.ring(alarm())
    assert r.play_once() is True and player.bursts == 1
    r.dismiss(key_of(alarm()))
    assert r.play_once() is False and player.bursts == 1


def test_sound_failure_is_reported_and_alarm_stays_visible(clock):
    r = make(clock, player=BrokenPlayer())
    r.ring(alarm())
    assert r.play_once() is False
    assert r.sound_error == "Alarm sound failed: Failed to beep"
    assert r.is_ringing  # still shown, still needs dismiss / snooze


def test_real_thread_repeats_tone_and_stops_on_dismiss():
    player = CountingPlayer()
    r = Ringer(player=player, pause_seconds=0.05)
    r.start()
    r.ring(alarm())
    _time.sleep(0.5)
    r.dismiss(key_of(alarm()))
    played = player.bursts
    _time.sleep(0.4)
    r.stop()
    assert played >= 3  # it repeated
    assert player.bursts - played <= 1  # and stopped (at most one burst in flight)


def test_real_thread_stops_after_limit_without_any_input():
    player = CountingPlayer()
    r = Ringer(player=player, limit=timedelta(seconds=0.3), pause_seconds=0.02)
    r.start()
    r.ring(alarm())
    _time.sleep(0.8)
    assert not r.is_ringing
    count = player.bursts
    _time.sleep(0.3)
    r.stop()
    assert player.bursts == count


# ---------- settings ----------

def test_settings_default_and_round_trip(tmp_path):
    path = settings_path(tmp_path / "tomits.db")
    assert path.name == "settings.json"
    assert load_settings(path).snooze_minutes == 5
    save_settings(path, Settings(snooze_minutes=10))
    assert load_settings(path).snooze_minutes == 10


def test_bad_settings_file_falls_back_to_default(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    assert load_settings(path).snooze_minutes == 5
    path.write_text('{"snooze_minutes": 999}')
    assert load_settings(path).snooze_minutes == 5


@pytest.mark.parametrize("value", ["0", "121", "abc", "", "2.5"])
def test_snooze_validation(value):
    with pytest.raises(TaskError):
        validate_snooze(value)


# ---------- UI: Dismiss and Snooze ----------

class Quiet:
    def notify(self, *a, **k):
        pass


@pytest.fixture
def app(db_file, monkeypatch, clock):
    monkeypatch.setattr(ui, "console", Console(file=io.StringIO()))
    return ui.App(db_file, notifier=Quiet(), clock=clock, player=CountingPlayer())


def _answer(monkeypatch, *answers):
    it = iter(answers)
    monkeypatch.setattr(ui.Prompt, "ask", classmethod(lambda cls, *a, **k: next(it)))


def test_ui_snooze_then_dismiss(app, monkeypatch, clock):
    app._on_alarm(alarm())
    _answer(monkeypatch, "z")
    app.attend()
    assert not app.ringer.is_ringing and len(app.ringer.snoozed()) == 1
    clock.advance(minutes=5)
    app.ringer.tick()
    assert app.ringer.is_ringing
    _answer(monkeypatch, "d")
    app.attend()
    assert not app.ringer.is_ringing and app.ringer.snoozed() == []


def test_ui_snooze_uses_saved_setting(app, monkeypatch, clock, db_file):
    _answer(monkeypatch, "7")
    app.change_settings()
    assert load_settings(settings_path(db_file)).snooze_minutes == 7
    app._on_alarm(alarm())
    _answer(monkeypatch, "z")
    app.attend()
    assert app.ringer.snoozed()[0][1] == T0 + timedelta(minutes=7)


def test_end_alarm_check_in_comes_after_timeout(app, monkeypatch, clock):
    app._on_alarm(alarm(END_CHECK))
    clock.advance(minutes=2)
    app.ringer.tick()  # stops by itself -> check-in queued
    assert not app.ringer.is_ringing and app.checkins.qsize() == 1


def test_end_alarm_snooze_does_not_ask_check_in_yet(app, monkeypatch):
    app._on_alarm(alarm(END_CHECK))
    _answer(monkeypatch, "z")
    app.process_ringing()
    assert app.checkins.empty()
