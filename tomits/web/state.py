"""Read-only JSON snapshot of everything the browser shows. Built fresh from
the database on each request, so every view always shows saved data only."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import func, select

from .. import __version__
from .. import periods as P
from .. import notes as N
from .. import planner as pl
from .. import reminders as REM
from .. import rescheduler as rs
from .. import services as svc
from .. import tracking as tr
from ..models import PRIORITY_NAMES, Goal, PeriodEntry, Task, TaskReason, TaskStatus
from ..settings import LAYOUTS
from ..voice import registry as R
from ..voice.dialog import LOW_CONFIDENCE


def _iso(d) -> Optional[str]:
    return d.isoformat() if d is not None else None


def _hm(t) -> Optional[str]:
    return t.strftime("%H:%M") if t is not None else None


def goal_brief(g: Goal) -> dict:
    p = tr.progress(g)
    return {"id": g.id, "title": g.title, "kind": g.kind.value, "start": _iso(g.period_start),
            "period": P.short_label(g.kind, g.period_start), "unit": g.unit, "target": g.target,
            "logged": p.logged, "text": p.text, "fraction": round(p.fraction, 4), "done": p.done}


def task_json(t: Task, now: datetime, today: date) -> dict:
    closed = t.status in (TaskStatus.FAILED.value, TaskStatus.SKIPPED.value)
    start, end = t.start_at, t.end_at
    out = {
        "id": t.id, "title": t.title, "title_typed": t.title_typed, "purpose": t.purpose, "duration": t.duration_min,
        "duration_text": svc.format_duration(t.duration_min), "date": _iso(t.planned_for),
        "start": _hm(t.start_time), "end": end.strftime("%H:%M") if end else None,
        "status": t.status, "priority": t.priority, "priority_name": PRIORITY_NAMES.get(t.priority, ""),
        "placement": t.placement or ("timed" if t.start_time else "untimed"),
        "reason": t.plan_reason or t.move_reason, "move_reason": t.move_reason,
        "fail_reason": t.latest_reason if closed else None, "has_history": bool(t.reasons or t.rescheduled_copies),
        "running": bool(start and t.status == TaskStatus.PENDING.value and start <= now < end),
        "past_end": bool(end and t.status == TaskStatus.PENDING.value and now >= end),
        "rescheduled_from": t.rescheduled_from_id, "reschedule_count": t.reschedule_count,
        "goal": goal_brief(t.goal) if t.goal else None,
        "copies": [{"id": c.id, "date": _iso(c.planned_for), "start": _hm(c.start_time), "status": c.status}
                   for c in t.rescheduled_copies],
    }
    if t.status == TaskStatus.PENDING.value:
        c = tr.contribution_for(t, today)
        out["contribution"] = {"mode": c.mode, "note": c.note}
    if out["running"]:
        total = (end - start).total_seconds()
        out["elapsed"] = round((now - start).total_seconds() / total, 4) if total else 0
        out["minutes_left"] = int((end - now).total_seconds() // 60)
    return out


def day_json(s, day: date, now: datetime, today: date, window) -> dict:
    tasks = svc.tasks_for_day(s, day)
    timed = [t for t in tasks if t.start_time is not None]
    untimed = [t for t in tasks if t.start_time is None]
    w0, w1 = (datetime.combine(day, window[0]), datetime.combine(day, window[1]))
    busy = [(t.start_at, t.end_at) for t in timed if t.status in svc.BLOCKING_STATUSES]
    gaps = [{"start": a.strftime("%H:%M"), "end": b.strftime("%H:%M"), "minutes": int((b - a).total_seconds() // 60)}
            for a, b in pl.free_gaps(max(w0, now) if day == today else w0, w1, busy)] if w1 > w0 else []
    return {"date": _iso(day), "label": f"{day:%A %d %B %Y}", "short": f"{day:%a %d %b}",
            "is_today": day == today, "is_past": day < today, "is_tomorrow": day == today + timedelta(days=1),
            "tasks": [task_json(t, now, today) for t in timed], "untimed": [task_json(t, now, today) for t in untimed],
            "gaps": gaps, "free_minutes": sum(g["minutes"] for g in gaps),
            "counts": {k: sum(1 for t in tasks if t.status == k) for k in ("pending", "done", "failed", "skipped")}}


def goal_json(s, g: Goal, today: date) -> dict:
    out = goal_brief(g)
    locked = P.is_locked(g.kind, g.period_start, today)
    out.update({
        "locked": locked,
        "parent": goal_brief(g.parent) if g.parent else None,
        "ancestors": [goal_brief(a) for a in tr.ancestors(g)],
        "children": [goal_brief(c) for c in g.children],
        "logs": [{"id": l.id, "amount": l.amount, "date": _iso(l.logged_for), "task_id": l.task_id} for l in g.logs],
        "own_logged": sum(l.amount for l in g.logs),
        "task_count": s.scalar(select(func.count()).select_from(Task).where(Task.goal_id == g.id)) or 0,
        "link_options": [goal_brief(x) for x in tr.link_candidates(s, g.kind, g.period_start, g.unit)],
    })
    return out


def period_json(s, kind: str, day: date, today: date) -> dict:
    kind = P.PeriodKind(kind)
    start = P.period_start(kind, day)
    end = P.period_end(kind, start)
    entry = tr.get_entry(s, kind, start)
    goals = list(entry.goals) if entry else []
    parent_kind = P.PARENT_KIND[kind]
    parent_options = []
    if parent_kind is not None:
        for ps in P.parent_starts(kind, start):
            parent_options += [goal_brief(g) for g in tr.goals_for_period(s, parent_kind, ps)]
    out = {
        "kind": kind.value, "start": _iso(start), "end": _iso(end), "label": P.label(kind, start),
        "short": P.short_label(kind, start), "current": P.contains(kind, start, today),
        "future": start > today, "locked": P.is_locked(kind, start, today),
        "review_locked": P.is_review_locked(kind, start, today), "review_cutoff": _iso(P.review_cutoff(kind, start)),
        "prev": _iso(P.shift(kind, start, -1)), "next": _iso(P.shift(kind, start, 1)),
        "goals": [goal_json(s, g, today) for g in goals],
        "process": entry.process if entry else None, "review": entry.review if entry else None,
        "sacrifices": [{"id": x.id, "text": x.text, "status": x.status} for x in (entry.sacrifices if entry else [])],
        "parent_options": parent_options,
    }
    if kind is P.PeriodKind.WEEK:
        out["days"] = [_iso(start + timedelta(days=i)) for i in range(7)]
    if kind is P.PeriodKind.MONTH:
        weeks, w = [], P.period_start(P.PeriodKind.WEEK, start)
        while w <= end:
            weeks.append(_iso(w))
            w += timedelta(days=7)
        out["weeks"] = weeks
    return out


def history_json(s, f: dict, today: date) -> dict:
    goal_id = int(f["goal"]) if str(f.get("goal") or "").isdigit() else None
    start = date.fromisoformat(f["from"]) if f.get("from") else None
    end = date.fromisoformat(f["to"]) if f.get("to") else None
    rows = rs.reason_history(s, goal_id, start, end)
    status = f.get("status")
    if status in ("failed", "skipped"):
        rows = [r for r in rows if r.status == status]
    if f.get("goal") == "none":
        rows = [r for r in rows if r.goal_id is None]
    goals = {}
    for r in s.scalars(select(TaskReason).where(TaskReason.goal_id.is_not(None))):
        goals[r.goal_id] = r.goal_title
    out_rows = []
    for r in rows:
        copies = r.task.rescheduled_copies if r.task else []
        out_rows.append({
            "id": r.id, "task_id": r.task_id, "date": _iso(r.task_date), "title": r.task_title, "status": r.status,
            "priority": r.priority, "goal_id": r.goal_id, "goal_title": r.goal_title, "reason": r.reason,
            "at": r.created_at.isoformat(timespec="minutes") if r.created_at else None,
            "task_status": r.task.status if r.task else None,
            "copies": [{"id": c.id, "date": _iso(c.planned_for), "start": _hm(c.start_time), "status": c.status}
                       for c in copies]})
    return {"rows": out_rows, "goals": [{"id": k, "title": v} for k, v in sorted(goals.items(), key=lambda x: x[1] or "")],
            "filters": f, "total": s.scalar(select(func.count()).select_from(TaskReason)) or 0}


def alarms_json(app) -> dict:
    now = app.clock()
    return {
        "ringing": [{"kind": r.alarm.kind, "task_id": r.alarm.task_id, "title": r.alarm.title,
                     "message": r.alarm.message, "title_line": r.alarm.title_line,
                     "seconds_left": r.seconds_left(now), "snoozes": r.snoozes} for r in app.ringer.ringing()],
        "snoozed": [{"kind": r.alarm.kind, "task_id": r.alarm.task_id, "title": r.alarm.title,
                     "due": due.strftime("%H:%M")} for r, due in app.ringer.snoozed()],
        "recent": [{"at": when.strftime("%H:%M"), "kind": a.kind, "task_id": a.task_id, "message": a.message}
                   for when, a in list(app.recent)],
        "missed": [{"kind": a.kind, "task_id": a.task_id, "message": a.message} for a in app.missed],
        "checkins": [{"task_id": a.task_id, "title": a.title, "message": a.message} for a in app.checkins.values()],
        "snooze_minutes": app.settings.snooze_minutes,
        "errors": [e for e in (app.alarms.last_error, app.reminders.last_error, app.watcher.last_error) if e],
    }


def voice_json(app) -> dict:
    rows = app.voice_log.recent(30)
    return {
        "log": [{"id": r.id, "at": r.ts, "text": r.transcript, "confidence": r.confidence, "command": r.command,
                 "interpreted": r.interpreted, "acted": bool(r.acted), "result": r.result, "source": r.source}
                for r in rows],
        "stt": app.stt_status(), "low_confidence": LOW_CONFIDENCE,
        "phrases": [{"name": c.name, "summary": c.summary, "examples": c.examples, "risky": c.risky}
                    for c in R.REGISTRY if R.MAIN in c.contexts and c.examples],
    }


def build_state(app, q: dict) -> dict:
    now = app.clock()
    today = now.date()
    st = app.settings
    with app.Session() as s:
        day = date.fromisoformat(q["day"]) if q.get("day") else today
        week_start = P.period_start(P.PeriodKind.WEEK, day)
        has_data = bool(s.scalar(select(func.count()).select_from(Task)) or s.scalar(select(func.count()).select_from(Goal)))
        overflow = pl.overflow_tasks(s, today) + pl.overflow_tasks(s, today + timedelta(days=1))
        state = {
            "version": __version__, "hub_version": app.hub.version,
            # every command the browser may send: the registry's names, defined once there
            "commands": sorted(c.name for c in R.REGISTRY if c.web is not None),
            "notes": _notes(s, app, now),
            "update_waiting": bool(getattr(app, "code_check", None) and app.code_check.changed()),
            "now": now.isoformat(timespec="seconds"), "today": _iso(today), "tomorrow": _iso(today + timedelta(days=1)),
            "settings": {k: getattr(st, k) for k in ("day_start", "day_end", "snooze_minutes", "default_task_minutes",
                                                     "spoken_replies",
                                                     "hands_free", "wake_phrase", "muted", "stt_model", "llm_enabled",
                                                     "llm_model", "push_to_talk_key", "browser_mic")},
            "ui": {"layout": st.ui_layout, "theme": st.ui_theme, "setup_done": st.setup_done,
                   "layouts": [{"id": k, "name": v[0], "description": v[1]} for k, v in LAYOUTS.items()]},
            "setup": {"needed": not st.setup_done and not has_data},
            "day": day_json(s, day, now, today, st.window),
            "today_view": day_json(s, today, now, today, st.window) if day != today else None,
            "week": {"start": _iso(week_start),
                     "days": [day_json(s, week_start + timedelta(days=i), now, today, st.window) for i in range(7)]},
            "overflow": [task_json(t, now, today) for t in overflow],
            "overdue": [task_json(t, now, today) for t in svc.overdue_tasks(s, today)],
            "open_goals": [goal_brief(g) for g in tr.open_goals(s, today)],
            "periods": {k: period_json(s, k, date.fromisoformat(q[k]) if q.get(k) else today, today)
                        for k in ("day", "week", "month")},
            "history": history_json(s, {k: q.get("h_" + k) for k in ("goal", "from", "to", "status")}, today),
            "reminders": [{"key": i.key, "kind": i.kind.value, "start": _iso(i.start), "part": i.part,
                           "message": i.message} for i in REM.active_reminders(s, today)],
            "proposals": app.proposals.to_json(s),
            "last_reschedule": None,
        }
        log = rs.last_log(s)
        if log is not None and not log.undone:
            state["last_reschedule"] = {"at": log.created_at.strftime("%H:%M"), "trigger": log.trigger}
    state["alarms"] = alarms_json(app)
    state["voice"] = voice_json(app)
    latest = app.undo.latest()
    state["undo"] = {"id": latest[0], "label": latest[1]} if latest else None
    return state


def _notes(s, app, now) -> dict:
    sec = N.sections(s, now)
    return {"upcoming": [N.to_json(n, now) for n in sec.upcoming],
            "no_time": [N.to_json(n, now) for n in sec.no_time],
            "overdue": [N.to_json(n, now) for n in sec.overdue],
            "count": sec.total, "overdue_count": len(sec.overdue), "max": N.MAX_NOTES, "max_text": N.MAX_TEXT,
            "colors": list(N.COLORS), "open": app.settings.notes_open,
            "banners": [N.to_json(n, now) for n in sec.overdue if n.banner_open],
            "away": getattr(app, "notes_away", 0)}
