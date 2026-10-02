import shutil
import sqlite3
from datetime import date, datetime, time
from pathlib import Path

import pytest

from tomits import services as svc
from tomits import tracking as tr
from tomits.periods import PeriodKind
from tomits.db import SCHEMA_VERSION, make_session_factory

DAY = date(2026, 10, 1)


@pytest.mark.parametrize("text,expected", [
    ("14:30", time(14, 30)), ("9:05", time(9, 5)), ("930", time(9, 30)), ("1430", time(14, 30)),
    ("9", time(9, 0)), ("2pm", time(14, 0)), ("2:30 PM", time(14, 30)), ("12am", time(0, 0)), ("12pm", time(12, 0)),
])
def test_parse_time(text, expected):
    assert svc.parse_time(text) == expected


@pytest.mark.parametrize("text", ["", "25:00", "9:60", "13pm", "noon", "0am"])
def test_parse_time_rejects(text):
    with pytest.raises(svc.TaskError):
        svc.parse_time(text)


def test_plan_day_back_to_back(session):
    drafts = [svc.TaskDraft("a", 60), svc.TaskDraft("b", 30), svc.TaskDraft("c", 45)]
    svc.plan_day(session, DAY, drafts, start=time(9, 0))
    got = [(t.title, t.start_time) for t in svc.tasks_for_day(session, DAY)]
    assert got == [("a", time(9, 0)), ("b", time(10, 0)), ("c", time(10, 30))]


def test_plan_day_past_midnight_is_rejected_and_nothing_saved(session):
    with pytest.raises(svc.TaskError):
        svc.plan_day(session, DAY, [svc.TaskDraft("a", 60), svc.TaskDraft("b", 90)], start=time(22, 30))
    assert svc.tasks_for_day(session, DAY) == []


def test_plan_day_ending_exactly_at_midnight_is_ok(session):
    svc.plan_day(session, DAY, [svc.TaskDraft("late", 60)], start=time(23, 0))
    assert svc.tasks_for_day(session, DAY)[0].end_at.time() == time(0, 0)


def test_plan_day_without_start_has_no_times(session):
    svc.plan_day(session, DAY, [svc.TaskDraft("a", 60)])
    assert svc.tasks_for_day(session, DAY)[0].start_time is None


def test_day_lists_timed_tasks_by_start_then_untimed(session):
    svc.add_task(session, "untimed", 10, planned_for=DAY)
    svc.add_task(session, "late", 10, planned_for=DAY, start_time=time(15, 0))
    svc.add_task(session, "early", 10, planned_for=DAY, start_time=time(8, 0))
    assert [t.title for t in svc.tasks_for_day(session, DAY)] == ["early", "late", "untimed"]


def test_time_of_closed_task_cannot_change(session):
    t = svc.add_task(session, "x", 10)
    svc.complete_task(session, t.id)
    with pytest.raises(svc.TaskError):
        svc.set_start_time(session, t.id, time(9, 0))


# ---------- migration from a v1.0 database ----------

V1_SCHEMA = """
CREATE TABLE goals (id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, description TEXT, created_at DATETIME NOT NULL);
CREATE TABLE tasks (id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, purpose TEXT, duration_min INTEGER NOT NULL,
  planned_for DATE NOT NULL, position INTEGER NOT NULL, status VARCHAR(10) NOT NULL, goal_id INTEGER REFERENCES goals(id),
  created_at DATETIME NOT NULL, closed_at DATETIME);
CREATE TABLE task_reasons (id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id), status VARCHAR(10) NOT NULL,
  reason TEXT NOT NULL, created_at DATETIME NOT NULL);
INSERT INTO goals VALUES (1, 'Ship tomits', NULL, '2026-09-29 10:00:00.000000');
INSERT INTO tasks VALUES (1, 'Old task', NULL, 30, '2026-09-29', 1, 'failed', 1, '2026-09-29 10:00:00.000000', '2026-09-29 11:00:00.000000');
INSERT INTO task_reasons VALUES (1, 1, 'failed', 'power cut', '2026-09-29 11:00:00.000000');
"""


def _columns(path):
    with sqlite3.connect(path) as c:
        return {r[1] for r in c.execute("PRAGMA table_info(tasks)")}


def test_v1_database_is_upgraded_keeping_data_and_backed_up(tmp_path):
    db = tmp_path / "tomits.db"
    with sqlite3.connect(db) as c:
        c.executescript(V1_SCHEMA)

    Session = make_session_factory(db)

    assert {"start_time", "heads_up_sent", "end_alert_sent"} <= _columns(db)
    backups = list(tmp_path.glob("tomits.db.bak-v1-*"))  # v1.6: timestamped
    assert len(backups) == 1 and "start_time" not in _columns(backups[0])
    with sqlite3.connect(db) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    with Session() as s:
        task = svc.get_task(s, 1)
        assert task.latest_reason == "power cut"
        assert task.start_time is None and task.heads_up_sent is False
        # v1.0 goal -> current month, no target; task link kept
        goal = tr.get_goal(s, 1)
        assert goal.kind is PeriodKind.MONTH and goal.period_start == date.today().replace(day=1)
        assert not goal.has_target and tr.progress(goal).text == "not done"
        assert task.goal.title == "Ship tomits"
        new = svc.add_task(s, "new", 20, start_time=time(9, 0))
        assert new.start_time == time(9, 0)


def test_opening_upgraded_database_again_changes_nothing(tmp_path):
    db = tmp_path / "tomits.db"
    with sqlite3.connect(db) as c:
        c.executescript(V1_SCHEMA)
    make_session_factory(db)
    backups = list(tmp_path.glob("tomits.db.bak-*"))
    make_session_factory(db)
    assert list(tmp_path.glob("tomits.db.bak-*")) == backups and len(backups) == 1


def test_fresh_database_needs_no_backup(tmp_path):
    make_session_factory(tmp_path / "new.db")
    assert not list(tmp_path.glob("*.bak-*"))


def _make_v2(db):
    """A v1.2 database (schema v2): v1 tables + alarm columns, 2 goals."""
    with sqlite3.connect(db) as c:
        c.executescript(V1_SCHEMA)
        c.executescript("""
            ALTER TABLE tasks ADD COLUMN start_time TIME;
            ALTER TABLE tasks ADD COLUMN heads_up_sent BOOLEAN NOT NULL DEFAULT 0;
            ALTER TABLE tasks ADD COLUMN end_alert_sent BOOLEAN NOT NULL DEFAULT 0;
            INSERT INTO goals VALUES (2, 'Get fit', 'gym', '2026-09-29 10:00:00.000000');
            INSERT INTO tasks VALUES (2, 'Gym', NULL, 60, '2026-09-29', 2, 'pending', 2,
                                      '2026-09-29 10:00:00.000000', NULL, '18:00:00.000000', 0, 0);
            PRAGMA user_version = 2;
        """)


def test_v2_goals_move_to_current_month_as_no_target_with_task_links(tmp_path):
    db = tmp_path / "tomits.db"
    _make_v2(db)
    Session = make_session_factory(db)
    assert len(list(tmp_path.glob("tomits.db.bak-v2-*"))) == 1
    month = date.today().replace(day=1)
    with Session() as s:
        goals = tr.goals_for_period(s, PeriodKind.MONTH, month)
        assert [(g.id, g.title, g.target, g.unit, g.parent_id) for g in goals] == [
            (1, "Ship tomits", None, None, None), (2, "Get fit", None, None, None)]
        gym = svc.get_task(s, 2)
        assert gym.goal.title == "Get fit" and gym.start_time == time(18, 0)
        # the linked task can mark its migrated goal done
        c = tr.contribution_for(gym)
        assert c.mode == "mark_done"
        svc.complete_task(s, 2, mark_goal_done=True)
        assert tr.progress(tr.get_goal(s, 2)).done
        # migrated goals count for this month's "has a goal" check
        assert all(m.kind is not PeriodKind.MONTH or "goal" not in m.parts for m in tr.missing_fill_ins(s))


def test_v2_migration_runs_once(tmp_path):
    db = tmp_path / "tomits.db"
    _make_v2(db)
    make_session_factory(db)
    make_session_factory(db)
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM period_entries").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM goals WHERE entry_id IS NULL").fetchone()[0] == 0
    names = sorted(p.name for p in tmp_path.iterdir())
    assert len(names) == 2 and names[0] == "tomits.db" and names[1].startswith("tomits.db.bak-v2-")


def test_migration_stops_with_nothing_changed_if_the_backup_fails(tmp_path, monkeypatch):
    import sqlite3 as _sqlite3
    from tomits import db as DB
    db = tmp_path / "tomits.db"
    _make_v2(db)
    real_connect = _sqlite3.connect

    def broken(path, *a, **k):  # the backup target can't be written
        if ".bak-" in str(path):
            raise _sqlite3.OperationalError("disk is full")
        return real_connect(path, *a, **k)

    monkeypatch.setattr(DB.sqlite3, "connect", broken)
    with pytest.raises(DB.MigrationError, match="Nothing was changed"):
        make_session_factory(db)
    monkeypatch.undo()
    with sqlite3.connect(db) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 2
        assert "priority" not in {r[1] for r in c.execute("PRAGMA table_info(tasks)")}
    assert not list(tmp_path.glob("*.bak-*"))


def test_backup_is_a_complete_timestamped_copy(tmp_path):
    from tomits.db import backup_database
    db = tmp_path / "tomits.db"
    _make_v2(db)
    path = backup_database(db, 2, now=datetime(2026, 10, 1, 9, 30, 5))
    assert path.name == "tomits.db.bak-v2-20261001-093005"
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 2
