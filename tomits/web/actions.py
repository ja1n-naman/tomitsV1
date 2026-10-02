"""The browser's handlers, attached to the registry commands.

Each handler only reads its arguments and calls the logic layer - the same
functions the voice handler and the typed menu call. Rules (overlaps, locked
periods, mandatory reasons, fixed / pinned tasks, ...) live there; a refusal
comes back as TaskError and is shown next to the control that was used.

Handler signature: fn(app, session, args) -> dict (message, extra data).
Destructive commands are registered with confirm=True and get a `preview`
that reads back exactly what will happen; the browser must send
confirmed=true to go ahead.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

from .. import exporting as EX
from .. import notes as N
from .. import planner as pl
from .. import reminders as REM
from .. import rescheduler as rs
from .. import services as svc
from .. import tracking as tr
from ..errors import TaskError
from ..models import PRIORITY_NAMES, Sacrifice, Task, TaskStatus
from ..periods import PeriodKind
from ..settings import (save_settings, validate_layout, validate_snooze, validate_task_minutes, validate_theme,
                        validate_window, LAYOUTS)
from ..voice import commands as _commands  # noqa: F401  (fills the registry)
from ..voice.registry import web_action

# ---------------- argument helpers ----------------


def _req(a: dict, key: str, what: Optional[str] = None):
    v = a.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        raise TaskError(f"{what or key.replace('_', ' ').capitalize()} is needed.")
    return v


def _int(a: dict, key: str, what: Optional[str] = None) -> int:
    v = _req(a, key, what)
    try:
        return int(v)
    except (TypeError, ValueError):
        raise TaskError(f"{what or key} must be a number.") from None


def _opt_int(a: dict, key: str) -> Optional[int]:
    v = a.get(key)
    if v in (None, "", "none"):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        raise TaskError(f"{key} must be a number.") from None


def _day(app, a: dict, key: str = "date") -> date:
    v = a.get(key)
    if not v:
        return app.today()
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise TaskError(f"Can't read the date {v!r}.") from None


def _time(a: dict, key: str) -> Optional[time]:
    v = a.get(key)
    if v in (None, ""):
        return None
    return svc.parse_time(str(v))


def _opt_minutes(a: dict, key: str = "duration") -> Optional[int]:
    """A duration, or None when left blank (a time in the title can supply it)."""
    v = a.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    return _minutes(a, key)


def _rules(app, a: dict) -> dict:
    """What the logic layer needs to read a time written in a title."""
    ampm = a.get("ampm") if a.get("ampm") in ("am", "pm") else None
    return dict(now=app.clock(), window=app.settings.window, default_minutes=app.settings.default_task_minutes,
                ampm=ampm)


def _understood(task) -> dict:
    line = getattr(task, "understood", None)
    return {"understood": line, "task_id": task.id} if line else {"task_id": task.id}


def _minutes(a: dict, key: str = "duration") -> int:
    v = _req(a, key, "Duration")
    if isinstance(v, (int, float)):
        if v <= 0:
            raise TaskError("Duration must be more than 0 minutes.")
        return int(v)
    return svc.parse_duration(str(v))


def _amount(a: dict, key: str, what: str) -> Optional[float]:
    v = a.get(key)
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        raise TaskError(f"{what} must be a number.") from None


def _kind(a: dict) -> PeriodKind:
    try:
        return PeriodKind(str(a.get("kind")))
    except ValueError:
        raise TaskError("Pick day, week or month.") from None


def _bool(a: dict, key: str) -> bool:
    v = a.get(key)
    return v is True or str(v).lower() in ("1", "true", "yes", "on")


def _task_line(t: Task) -> str:
    when = f" at {t.start_time:%H:%M}" if t.start_time else ""
    return f"'{t.title}'{when}"


def _progress_line(goal) -> str:
    return "; ".join(f"{g.title} {tr.progress(g).text}" for g in [goal, *tr.ancestors(goal)])


# ---------------- timetable ----------------

@web_action("add_task")
def add_task(app, s, a):
    task = svc.add_task(s, _req(a, "title", "A title"), _opt_minutes(a), _opt_int(a, "goal_id"), a.get("purpose"),
                        planned_for=_day(app, a), start_time=_time(a, "start"), today=app.today(),
                        priority=a.get("priority") or 3, **_rules(app, a))
    day = "" if task.planned_for == app.today() else f" on {task.planned_for:%a %d %b}"
    return {"message": f"Added {_task_line(task)}{day}, {svc.format_duration(task.duration_min)}.",
            "label": f"add '{task.title}'", **_understood(task)}


@web_action("add_several")
def add_several(app, s, a):
    drafts, rows = [], []
    for i, line in enumerate(a.get("lines") or []):
        if not str(line.get("title") or "").strip():
            continue
        ampm = line.get("ampm") if line.get("ampm") in ("am", "pm") else None
        drafts.append(svc.TaskDraft(line["title"], _opt_minutes(line), _opt_int(line, "goal_id"), line.get("purpose"),
                                    priority=line.get("priority") or 3, ampm=ampm))
        rows.append(i)
    rules = _rules(app, a)
    rules.pop("ampm")
    try:
        tasks = svc.plan_day(s, _day(app, a), drafts, start=_time(a, "start"), today=app.today(), **rules)
    except svc.AmbiguousTime as e:   # the question names the row the browser sent
        raise svc.AmbiguousTime(e.question, e.choices, rows[e.line] if e.line is not None else None) from None
    lines = [t.understood for t in tasks if getattr(t, "understood", None)]
    return {"message": f"Added {len(tasks)} tasks.", "label": f"add {len(tasks)} tasks",
            "understood": " ".join(lines) or None}


@web_action("plan_day")
def plan_day(app, s, a):
    day = _day(app, a)
    if day < app.today():
        raise TaskError(f"{day:%a %d %b} is in the past; past days are never changed.")
    result = pl.plan_day(s, day, app.settings.window, now=app.clock())
    msg = f"Placed {len(result.placed)} task{'s' if len(result.placed) != 1 else ''}."
    if result.overflow:
        msg += f" {len(result.overflow)} didn't fit: " + ", ".join(t.title for t in result.overflow) + "."
    if result.kept:
        msg += f" {len(result.kept)} kept where they are (fixed, pinned or started)."
    return {"message": msg, "label": f"plan {day:%a %d %b}"}


@web_action("move_task")
def move_task(app, s, a):
    tid = _int(a, "id", "Task")
    mode = a.get("mode") or "time"
    if mode in ("before", "after"):
        task = svc.move_next_to(s, tid, _int(a, "other_id", "The other task"), mode, now=app.clock())
    elif mode == "day":
        task = svc.move_to_day(s, tid, _day(app, a), _time(a, "start"), today=app.today(), now=app.clock())
    elif mode == "time":
        task = svc.set_start_time(s, tid, _time(a, "start"), now=app.clock())
    else:
        raise TaskError("Move to a time, a day, or before / after another task.")
    where = f"{task.planned_for:%a %d %b}" + (f" at {task.start_time:%H:%M}" if task.start_time else ", no time")
    return {"message": f"Moved '{task.title}' to {where}." + (" Pinned: re-planning won't move it."
                                                             if task.placement == "pinned" else ""),
            "label": f"move '{task.title}'"}


@web_action("pin_task")
def pin_task(app, s, a):
    task = svc.get_task(s, _int(a, "id", "Task"))
    if task.start_time is None:
        raise TaskError(f"'{task.title}' has no time yet. Give it a time (move it) to pin it.")
    task = svc.set_start_time(s, task.id, task.start_time, now=app.clock())
    return {"message": f"Pinned '{task.title}' at {task.start_time:%H:%M}.", "label": f"pin '{task.title}'"}


@web_action("unpin_task")
def unpin_task(app, s, a):
    task = svc.unpin_task(s, _int(a, "id", "Task"))
    return {"message": f"Unpinned '{task.title}'. The next re-plan may move it.", "label": f"unpin '{task.title}'"}


@web_action("edit_task")
def edit_task(app, s, a):
    changes = {}
    if "title" in a:
        changes["title"] = a["title"]
    if a.get("duration") not in (None, ""):
        changes["duration_min"] = _minutes(a)
    if a.get("priority") not in (None, ""):
        changes["priority"] = a["priority"]
    if "purpose" in a:
        changes["purpose"] = a["purpose"] or ""
    task = svc.update_task(s, _int(a, "id", "Task"), today=app.today(), **_rules(app, a), **changes)
    return {"message": f"Updated '{task.title}'.", "label": f"edit '{task.title}'", **_understood(task)}


@web_action("keep_typed_title")
def keep_typed_title(app, s, a):
    task = svc.restore_typed_title(s, _int(a, "id", "Task"))
    return {"message": f"'{task.title}' is back as typed, with no time. Plan my day places it.",
            "label": f"keep '{task.title}' as typed"}


def _preview_delete_task(app, s, a):
    t = svc.get_task(s, _int(a, "id", "Task"))
    return f"Delete the task {_task_line(t)} on {t.planned_for:%a %d %b}? This can't be undone from the terminal."


@web_action("delete_task", confirm=True)
def delete_task(app, s, a):
    t = svc.get_task(s, _int(a, "id", "Task"))
    title = t.title
    svc.delete_task(s, t.id)
    return {"message": f"Deleted '{title}'.", "label": f"delete '{title}'"}


delete_task.preview = _preview_delete_task


@web_action("mark_done")
def mark_done(app, s, a):
    task = svc.complete_task(s, _int(a, "id", "Task"), contribution=_amount(a, "contribution", "The amount") or 0,
                             mark_goal_done=_bool(a, "mark_goal_done"), today=app.today())
    app.after_close(task.id)
    msg = f"'{task.title}' done."
    if task.goal is not None:
        s.refresh(task.goal)
        msg += " " + _progress_line(task.goal)
    return {"message": msg, "label": f"done '{task.title}'"}


def _close(app, s, a, status: TaskStatus):
    tid = _int(a, "id", "Task")
    fn = svc.fail_task if status is TaskStatus.FAILED else svc.skip_task
    task = fn(s, tid, a.get("reason") or "")          # the logic layer refuses a blank reason
    app.after_close(task.id)
    pid = app.proposals.add(s, ("closed", task.id, None))
    return {"message": f"'{task.title}' marked {status.value}. Reason saved permanently. A reschedule proposal is ready.",
            "label": f"{status.value} '{task.title}'", "proposal_id": pid}


@web_action("mark_failed")
def mark_failed(app, s, a):
    return _close(app, s, a, TaskStatus.FAILED)


@web_action("mark_skipped")
def mark_skipped(app, s, a):
    return _close(app, s, a, TaskStatus.SKIPPED)


@web_action("extend_task")
def extend_task(app, s, a):
    task = svc.get_task(s, _int(a, "id", "Task"))
    if task.status != TaskStatus.PENDING.value:
        raise TaskError(f"'{task.title}' is already {task.status}.")
    if task.start_at is None:
        raise TaskError(f"'{task.title}' has no time, so it can't run over.")
    if a.get("until"):
        new_end = datetime.combine(task.planned_for, svc.parse_time(str(a["until"])))
    else:
        new_end = task.end_at + timedelta(minutes=_int(a, "minutes", "Minutes to add"))
    if new_end <= task.end_at:
        raise TaskError(f"'{task.title}' already ends at {task.end_at:%H:%M}; pick a later time.")
    app.checkins.pop(task.id, None)
    pid = app.proposals.add(s, ("overrun", task.id, new_end))
    return {"message": f"Proposal ready: '{task.title}' until {new_end:%H:%M}. Nothing changes until you accept.",
            "proposal_id": pid}


@web_action("reschedule_missed")
def reschedule_missed(app, s, a):
    task = svc.get_task(s, _int(a, "id", "Task"))
    pid = app.proposals.add(s, ("closed", task.id, None))
    return {"message": f"Proposal ready for '{task.title}'.", "proposal_id": pid}


@web_action("proposal_answer")
def proposal_answer(app, s, a):
    pid = _int(a, "id", "Proposal")
    if a.get("answer") == "accept":
        prop = app.proposals.accept(s, pid)
        return {"message": "Plan updated. Use Undo, or 'undo the reschedule', to go back.",
                "label": f"reschedule ({prop.summary})"}
    if a.get("answer") == "reject":
        app.proposals.remove(pid)
        return {"message": "Nothing was changed. Failed or skipped tasks keep their reason; reschedule them any time."}
    raise TaskError("Accept or reject.")


@web_action("collision_answer")
def collision_answer(app, s, a):
    choice = {"shorten": "shorten", "continue": "continue", "move": "continue", "leave": "leave"}.get(a.get("choice"))
    if choice is None:
        raise TaskError("Shorten, move the rest, or leave it.")
    return {"message": app.proposals.choose(s, _int(a, "id", "Proposal"), choice)}


@web_action("cap_answer")
def cap_answer(app, s, a):
    choice = a.get("choice")
    if choice not in ("keep", "split", "drop"):
        raise TaskError("Keep, split or drop.")
    return {"message": app.proposals.choose(s, _int(a, "id", "Proposal"), choice)}


def _preview_undo_reschedule(app, s, a):
    log = rs.last_log(s)
    if log is None or log.undone:
        raise TaskError("There's no reschedule to undo.")
    return f"Undo the reschedule from {log.created_at:%H:%M} ({log.trigger})? Failure reasons are kept."


@web_action("undo_reschedule", confirm=True)
def undo_reschedule(app, s, a):
    rs.undo_last(s)
    return {"message": "Undone. The previous plan is back; failure reasons are kept.", "label": "undo the reschedule"}


undo_reschedule.preview = _preview_undo_reschedule


@web_action("link_task")
def link_task(app, s, a):
    task = svc.link_task(s, _int(a, "id", "Task"), _opt_int(a, "goal_id"), today=app.today())
    return {"message": f"Linked '{task.title}' to '{task.goal.title}'." if task.goal else f"Unlinked '{task.title}'.",
            "label": f"link '{task.title}'"}


@web_action("checkin_answer")
def checkin_answer(app, s, a):
    tid = _int(a, "id", "Task")
    if a.get("answer") != "later":
        raise TaskError("Use Done, Still going, Failed or Skipped on the task itself.")
    app.checkins.pop(tid, None)
    return {"message": "OK, it stays open."}


# ---------------- goals and tracking pages ----------------

@web_action("new_goal")
def new_goal(app, s, a):
    goal = tr.create_goal(s, _kind(a), _day(app, a, "start"), _req(a, "title", "A goal title"),
                          _amount(a, "target", "The target"), (a.get("unit") or None) if a.get("target") not in
                          (None, "") else None, _opt_int(a, "parent_id"), today=app.today())
    return {"message": f"Added the goal '{goal.title}' ({tr.progress(goal).text}).", "label": f"new goal '{goal.title}'",
            "goal_id": goal.id}


@web_action("edit_goal")
def edit_goal(app, s, a):
    changes = {}
    if "title" in a:
        changes["title"] = a["title"]
    if "target" in a:
        changes["target"] = _amount(a, "target", "The target")
    if "unit" in a:
        changes["unit"] = a["unit"] or None
    if "parent_id" in a:
        changes["parent_id"] = _opt_int(a, "parent_id")
    goal = tr.update_goal(s, _int(a, "id", "Goal"), today=app.today(), **changes)
    return {"message": f"Updated the goal '{goal.title}' ({tr.progress(goal).text}).", "label": f"edit goal '{goal.title}'"}


def _preview_delete_goal(app, s, a):
    g = tr.get_goal(s, _int(a, "id", "Goal"))
    return f"Delete the {g.kind.value} goal '{g.title}'? Only allowed for an unused goal (no logs, links or tasks)."


@web_action("delete_goal", confirm=True)
def delete_goal(app, s, a):
    g = tr.get_goal(s, _int(a, "id", "Goal"))
    title = g.title
    tr.delete_goal(s, g.id, today=app.today())
    return {"message": f"Deleted the goal '{title}'.", "label": f"delete goal '{title}'"}


delete_goal.preview = _preview_delete_goal


@web_action("log_progress")
def log_progress(app, s, a):
    amount = _amount(a, "amount", "The amount")
    if amount is None:
        raise TaskError("Enter an amount to log.")
    gid = _int(a, "goal_id", "Goal")
    tr.log_progress(s, gid, amount, on=_day(app, a), today=app.today())
    goal = tr.get_goal(s, gid)
    return {"message": f"Logged {tr.fmt_amount(amount)} {goal.unit or ''}. {_progress_line(goal)}",
            "label": f"log {tr.fmt_amount(amount)} to '{goal.title}'"}


def _preview_remove_log(app, s, a):
    from ..models import ProgressLog
    log = s.get(ProgressLog, _int(a, "log_id", "Log"))
    if log is None:
        raise TaskError("That log no longer exists.")
    return f"Remove {tr.fmt_amount(log.amount)} {log.goal.unit or ''} logged on {log.logged_for:%a %d %b} for '{log.goal.title}'?"


@web_action("remove_log", confirm=True)
def remove_log(app, s, a):
    tr.delete_log(s, _int(a, "log_id", "Log"), today=app.today())
    return {"message": "Log removed.", "label": "remove a progress log"}


remove_log.preview = _preview_remove_log


@web_action("goal_done")
def goal_done(app, s, a):
    goal = tr.set_goal_done(s, _int(a, "id", "Goal"), _bool(a, "done"), today=app.today())
    return {"message": f"'{goal.title}': {tr.progress(goal).text}.", "label": f"goal '{goal.title}' done / not done"}


@web_action("set_process")
def set_process(app, s, a):
    tr.set_process(s, _kind(a), _day(app, a, "start"), a.get("text") or "", today=app.today())
    return {"message": "Process saved.", "label": "process"}


@web_action("write_review")
def write_review(app, s, a):
    tr.set_review(s, _kind(a), _day(app, a, "start"), a.get("text"), today=app.today())
    return {"message": "Review saved.", "label": "review"}


@web_action("add_sacrifice")
def add_sacrifice(app, s, a):
    tr.add_sacrifice(s, _kind(a), _day(app, a, "start"), _req(a, "text", "The sacrifice"), a.get("status") or "planned",
                     today=app.today())
    return {"message": "Sacrifice added.", "label": "add a sacrifice"}


@web_action("made_sacrifice")
def made_sacrifice(app, s, a):
    item = tr.mark_sacrifice_made(s, _int(a, "id", "Sacrifice"), today=app.today())
    return {"message": f"'{item.text}' marked as made.", "label": f"mark '{item.text}' as made"}


@web_action("remove_sacrifice")
def remove_sacrifice(app, s, a):
    # no confirmation (by request): the Undo toast brings it back
    sid = _int(a, "id", "Sacrifice")
    item = s.get(Sacrifice, sid)
    text = item.text if item is not None else ""
    tr.remove_sacrifice(s, sid, today=app.today())
    return {"message": f"Deleted the sacrifice '{text}'.", "label": f"delete the sacrifice '{text}'"}


# ---------------- reminders ----------------

@web_action("dismiss_reminder")
def dismiss_reminder(app, s, a):
    REM.dismiss_reminder(s, _kind(a), _day(app, a, "start"), str(a.get("part")), now=app.clock())
    return {"message": "Reminder hidden. It won't come back for this item.", "label": "hide a reminder"}


# ---------------- alarms ----------------

@web_action("alarm_dismiss")
def alarm_dismiss(app, s, a):
    return {"message": app.dismiss_alarm(str(a.get("kind")), _int(a, "task_id", "Task"))}


@web_action("alarm_snooze")
def alarm_snooze(app, s, a):
    return {"message": app.snooze_alarm(str(a.get("kind")), _int(a, "task_id", "Task"), _opt_int(a, "minutes"))}


# ---------------- bulk delete ----------------

def _preview_delete_all(app, s, a):
    return svc.bulk_delete_plan(s, a.get("scope") or "tasks and goals", today=app.today()).describe()


@web_action("delete_all", confirm=True)
def delete_all(app, s, a):
    plan = svc.bulk_delete_plan(s, a.get("scope") or "tasks and goals", today=app.today())
    if plan.empty:
        raise TaskError(plan.describe())
    n_t, n_g = svc.bulk_delete(s, plan, today=app.today())
    return {"message": f"Deleted {n_t} tasks and {n_g} goals.", "label": "delete all"}


delete_all.preview = _preview_delete_all


def _preview_clear_day(app, s, a):
    return svc.bulk_delete_plan(s, "day", day=_day(app, a), today=app.today()).describe()


@web_action("clear_day", confirm=True)
def clear_day(app, s, a):
    plan = svc.bulk_delete_plan(s, "day", day=_day(app, a), today=app.today())
    if plan.empty:
        raise TaskError(plan.describe())
    n, _ = svc.bulk_delete(s, plan, today=app.today())
    return {"message": f"Cleared {n} pending tasks.", "label": f"clear {plan.day:%a %d %b}"}


clear_day.preview = _preview_clear_day


# ---------------- settings ----------------

def _save(app):
    save_settings(app.settings_file, app.settings)


@web_action("settings")
def settings(app, s, a):
    st = app.settings
    if a.get("day_start") or a.get("day_end"):
        st.day_start, st.day_end = validate_window(a.get("day_start") or st.day_start, a.get("day_end") or st.day_end)
    if a.get("snooze_minutes") not in (None, ""):
        st.snooze_minutes = validate_snooze(a["snooze_minutes"])
    if a.get("default_task_minutes") not in (None, ""):
        st.default_task_minutes = validate_task_minutes(a["default_task_minutes"])
    _save(app)
    return {"message": f"Day window {st.day_start}-{st.day_end}, snooze {st.snooze_minutes} min, "
                       f"default task length {st.default_task_minutes} min.", "label": "settings"}


@web_action("voice_settings")
def voice_settings(app, s, a):
    st = app.settings
    for name in ("spoken_replies", "hands_free", "llm_enabled"):
        if name in a:
            setattr(st, name, _bool(a, name))
    if a.get("wake_phrase"):
        st.wake_phrase = str(a["wake_phrase"]).strip().lower()
    if a.get("stt_model"):
        from ..voice.stt import MODEL_SIZES_MB
        if a["stt_model"] not in MODEL_SIZES_MB:
            raise TaskError("Pick a speech model from the list.")
        st.stt_model = a["stt_model"]
    if "lowconf" in a:
        pass  # fixed by design (LOW_CONFIDENCE), shown read-only
    _save(app)
    app._understanding = None  # rebuilt with the new model settings
    return {"message": "Voice settings saved.", "label": "voice settings"}


@web_action("mute")
def mute(app, s, a):
    app.settings.muted = _bool(a, "muted")
    _save(app)
    return {"message": "Microphone muted." if app.settings.muted else "Microphone on.", "label": "mute"}


@web_action("input_device")
def input_device(app, s, a):
    app.settings.browser_mic = str(a.get("device") or "")[:200]
    _save(app)
    return {"message": "Microphone chosen.", "label": "microphone"}


@web_action("switch_layout")
def switch_layout(app, s, a):
    app.settings.ui_layout = validate_layout(a.get("layout"))
    _save(app)
    return {"message": f"Switched to the {LAYOUTS[app.settings.ui_layout][0]} layout.", "label": "layout"}


@web_action("set_theme")
def set_theme(app, s, a):
    app.settings.ui_theme = validate_theme(a.get("theme"))
    _save(app)
    return {"message": f"Theme: {app.settings.ui_theme}.", "label": "theme"}


@web_action("finish_setup")
def finish_setup(app, s, a):
    app.settings.setup_done = True
    _save(app)
    return {"message": "Setup finished.", "label": "finish setup"}


@web_action("undo_action")
def undo_action(app, s, a):
    label = app.undo_last_action(_opt_int(a, "id"))
    return {"message": f"Undone: {label}. Failure reasons are always kept."}


# ---------------- Remember (notes, v1.8) ----------------

@web_action("add_note")
def add_note(app, s, a):
    due = None
    if a.get("due"):
        try:
            due = datetime.fromisoformat(str(a["due"])[:16])
        except ValueError:
            raise TaskError(f"Can't read the date and time {a['due']!r}.") from None
    ampm = a.get("ampm") if a.get("ampm") in ("am", "pm") else None
    note = N.add_note(s, a.get("text") or "", due, a.get("color"), now=app.clock(), window=app.settings.window,
                      ampm=ampm)
    return {"message": f"Note added: {N.describe(note, app.today())}.", "label": "add a note",
            "understood": note.understood}


@web_action("delete_note")
def delete_note(app, s, a):
    # no confirmation (by request): the Undo toast restores the exact note
    text = N.delete_note(s, _int(a, "id", "Note"))
    return {"message": f"Deleted the note: {text}.", "label": f"delete the note '{text[:40]}'"}


@web_action("dismiss_note_banner")
def dismiss_note_banner(app, s, a):
    if str(a.get("id")) == "away":
        app.notes_away = 0
        return {"message": "Hidden. Those notes stay under Overdue until you delete them."}
    N.dismiss_banner(s, _int(a, "id", "Note"))
    return {"message": "Hidden. The note stays until you delete it.", "label": "hide a note reminder"}


@web_action("notes_panel")
def notes_panel(app, s, a):
    app.settings.notes_open = _bool(a, "open")
    _save(app)
    return {"message": "Notes shown." if app.settings.notes_open else "Notes hidden.", "label": "notes panel"}


# ---------------- export and import (v1.8) ----------------

@web_action("export_data")
def export_data(app, s, a):
    path = EX.write_export(app.engine, app.db_path, app.clock())
    import json
    return {"message": f"Exported everything to {path.name} (also saved in the exports folder next to your data).",
            "export": json.loads(path.read_text(encoding="utf-8")), "filename": path.name}


def _import_payload(a):
    data = a.get("data")
    if not data:
        raise TaskError("Choose an export file first.")
    return EX.check(data)


def _preview_import(app, s, a):
    return (f"Replace ALL your data with this export: {EX.summary(_import_payload(a))}? Your current data is backed up "
            "first, and Undo can take the import back.")


@web_action("import_data", confirm=True)
def import_data(app, s, a):
    data = _import_payload(a)
    s.close()
    return {"message": EX.import_data(app.engine, app.db_path, data, app.clock()), "label": "import"}


import_data.preview = _preview_import
