"""Every tomits action as a registry command. Handlers only gather what the
logic layer needs (asking follow-ups) and call the same functions the typed
UI calls; the rules live there. Importing this module fills the registry."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import List, Optional

from sqlalchemy import select

from .. import periods as PER
from .. import planner as pl
from .. import notes as N
from .. import rescheduler as rs
from .. import services as svc
from .. import tracking as tr
from ..errors import TaskError
from ..models import PRIORITY_NAMES, Placement, Sacrifice, Task, TaskStatus
from ..settings import save_settings, validate_key, validate_snooze, validate_task_minutes, validate_window
from . import parse as P
from .dialog import Cancelled, Dialog
from .registry import (ALARM, CAP, CHECKIN, COLLISION, MAIN, PROPOSAL, SETTINGS, TIMETABLE, TRACKING, command)

NAME = r"(?P<name>.+?)"
IT_WORDS = {"", "it", "this", "that", "current", "the current task", "this task", "that task", "current task",
            "the task", "task"}


# ======================= helpers =======================

def clock(t: Optional[time]) -> str:
    if t is None:
        return "no time"
    return pl._clock(t.hour * 60 + t.minute)


def when_text(task: Task, today: date) -> str:
    day = "today" if task.planned_for == today else ("tomorrow" if task.planned_for == today + timedelta(days=1)
                                                     else f"{task.planned_for:%A %d %B}")
    return f"{day} at {clock(task.start_time)}" if task.start_time else f"{day}, no time yet"


def describe_task(task: Task, today: date) -> str:
    return f"{task.title}, {when_text(task, today)}"


def _current_task(d: Dialog, s) -> Optional[Task]:
    now, today = d.now(), d.today()
    tasks = [t for t in svc.tasks_for_day(s, today) if t.status == TaskStatus.PENDING.value]
    running = [t for t in tasks if t.start_at and t.start_at <= now < t.end_at]
    if running:
        return running[0]
    if d.state.last_task_id:
        t = s.get(Task, d.state.last_task_id)
        if t is not None and t.status == TaskStatus.PENDING.value:
            return t
    upcoming = sorted((t for t in tasks if t.start_at and t.start_at > now), key=lambda t: t.start_at)
    return upcoming[0] if upcoming else None


def resolve_task(d: Dialog, s, name: Optional[str], statuses=(TaskStatus.PENDING.value,), what="task") -> Task:
    today = d.today()
    name = (name or "").strip()
    if name in IT_WORDS and TaskStatus.PENDING.value in statuses:
        t = _current_task(d, s)
        if t is not None:
            d.state.last_task_id = t.id
            return t
        name = d.ask(f"Which {what}?")
    elif name in IT_WORDS:
        name = d.ask(f"Which {what}?")
    cands = [t for t in s.query(Task).filter(Task.status.in_(statuses)).all()
             if t.planned_for >= today - timedelta(days=7) and t.planned_for <= today + timedelta(days=1)]
    matches = P.fuzzy_matches(name, cands, key=lambda t: t.title)
    if not matches:
        raise TaskError(f"I couldn't find a {what} called '{name}'.")
    task = P.pick_unique(matches)
    if task is None:
        task = d.choose([t for _, t in matches], lambda t: describe_task(t, today), what)
    elif matches[0][0] < P.NAME_CONFIRM_SCORE and not d.confirm(f"Did you mean {describe_task(task, today)}?"):
        raise Cancelled()
    d.state.last_task_id = task.id
    return task


def resolve_goal(d: Dialog, s, name: str, goals=None, what="goal"):
    goals = goals if goals is not None else tr.open_goals(s, d.today())
    matches = P.fuzzy_matches(name, goals, key=lambda g: g.title)
    if not matches:
        raise TaskError(f"I couldn't find an open goal called '{name}'.")
    goal = P.pick_unique(matches)
    if goal is None:
        return d.choose([g for _, g in matches], goal_desc, what)
    if matches[0][0] < P.NAME_CONFIRM_SCORE and not d.confirm(f"Did you mean the {goal_desc(goal)}?"):
        raise Cancelled()
    return goal


def goal_desc(g) -> str:
    return f"{g.kind.value} goal {g.title}, {tr.progress(g).text}"


def period_of(d: Dialog, text: str, ask: bool = True, default_kind: Optional[str] = None):
    """('day'|'week'|'month', a date in it, rest-of-text)."""
    kind, day, rest = P.extract_period(text or "", d.today())
    if kind is None:
        dd, rest2 = P.extract_date(text or "", d.today())
        if dd is not None:
            return "day", dd, rest2
    if kind is None and d.state.view_kind:
        return d.state.view_kind, d.state.view_start, rest
    if kind is None and default_kind:
        return default_kind, d.today(), rest
    if kind is None and ask:
        kind = d.ask_choice("For today, this week or this month?",
                            {"today": "day", "day": "day", "week": "week", "month": "month"})
        day = d.today()
    return kind, day, rest


def period_name(kind: str, day: date, today: date) -> str:
    start = PER.period_start(kind, day)
    if start == PER.period_start(kind, today):
        return {"day": "today", "week": "this week", "month": "this month"}[kind]
    return PER.label(kind, start)


AMPM_WORDS = {"am": "am", "morning": "am", "pm": "pm", "evening": "pm", "afternoon": "pm", "night": "pm",
              "tonight": "pm"}


def title_rules(d: Dialog) -> dict:
    """What the logic layer needs to read a time from a title (same as typing)."""
    return dict(now=d.now(), window=d.app.settings.window, default_minutes=d.app.settings.default_task_minutes)


def claiming(d: Dialog, fn):
    """Run a change that gives a task its own time, as typing does: am or pm
    is asked when the day window can't settle it; if planner-placed tasks are
    in the way, the reschedule proposal is read out (nothing changes unless
    you accept). Returns the task, or None when it went to a proposal."""
    ampm = None
    for _ in range(3):
        try:
            return fn(ampm)
        except svc.AmbiguousTime as e:
            ampm = d.ask_choice(e.question + " Say am or pm.", AMPM_WORDS)
        except svc.SlotTaken as e:
            d.say(str(e))
            run_proposal(d, ("claim", e.claim, None))
            if e.claim.understood:
                d.show(e.claim.understood)
            return None
    raise Cancelled()


def speak_proposal(d: Dialog, prop) -> str:
    parts = []
    for m in prop.placed:
        if m.kind == "extend":
            end = datetime.combine(m.to_day, m.to_start) + timedelta(minutes=m.new_duration)
            parts.append(f"{m.title} runs until {end:%H:%M}")
        else:
            day = ("today" if m.to_day == d.today() else "tomorrow" if m.to_day == d.today() + timedelta(days=1)
                   else f"{m.to_day:%A}")
            if m.kind == "claim":
                parts.append(f"{m.title} takes {day} at {clock(m.to_start)}, its own time")
                continue
            verb = "a new copy of" if m.kind == "copy" else "move"
            parts.append(f"{verb} {m.title} to {day} at {clock(m.to_start)}, because {m.reason.split(': ', 1)[-1]}")
    for m in prop.unplaced:
        parts.append(f"{m.title} is unplaced, {svc.format_duration(m.duration)}")
    return "Here's the new plan: " + ". ".join(parts) + "." if parts else "Nothing needs to move."


def run_proposal(d: Dialog, trigger) -> None:
    """Build, read aloud and (on yes) accept a reschedule proposal by voice.
    Same logic calls as the typed flow."""
    app = d.app
    with app.Session() as s:
        prop = app._build(s, trigger)
        if prop.cap_reached and prop.choice is None:
            choice = d.ask_choice(f"{prop.title} has now been rescheduled {prop.chain_count} times. "
                                  "Keep rescheduling, split it in two, or drop it?",
                                  {"keep": "keep", "split": "split", "drop": "drop"})
            prop = app._build(s, trigger, choice)
            if choice == "drop":
                d.say(f"Dropped. {prop.title} stays {prop.trigger} with its reason; no new copy.")
                return
        if prop.collisions:
            c = prop.collisions[0]
            choice = d.ask_choice(
                f"Warning: {prop.title} running until {prop.requested_end:%H:%M} would run into {c.title} at "
                f"{c.start:%H:%M}, which is {c.placement} and won't move. Say shorten, move the rest, or leave it.",
                {"shorten": "shorten", "move": "continue", "leave": "leave"})
            if choice == "leave":
                d.say("Left as it is. Nothing was changed.")
                return
            prop = app._build(s, trigger, choice)
        app._show_proposal(prop)
        if not prop.moves:
            d.say("Nothing needs to move.")
            return
        summary = speak_proposal(d, prop)
        for _ in range(3):
            answer = d.ask(f"{summary} Say yes to accept, no to reject, or repeat.")
            if P.is_yes(answer):
                rs.accept(s, prop, now=app.clock())
                app.after_accept(prop)
                d.say("Plan updated. Say undo the reschedule to go back.")
                return
            if P.is_no(answer):
                extra = " It stays failed with its reason; say reschedule it later." if prop.trigger in ("failed", "skipped") else ""
                d.say("Nothing was changed." + extra)
                return
            if "undo" in answer:
                d.say("There's nothing accepted yet to undo; say no to reject.")
        d.say("Nothing was changed.")


def parse_new_end(d: Dialog, task: Task, text: str) -> datetime:
    t, _ = P.extract_time(text, require_marker=False)
    if t is None:
        t, _ = P.extract_time("at " + text) if re.fullmatch(r"\d{1,2}(:\d{2}| \d{2})?( am| pm)?", text) else (None, text)
    if t is not None:
        return datetime.combine(task.planned_for, t)
    minutes, _ = P.extract_duration(text)
    if minutes is None and text.isdigit():
        minutes = int(text)
    if minutes:
        return task.end_at + timedelta(minutes=minutes)
    raise TaskError("I need a new end time or a number of minutes.")


# ======================= timetable =======================

LINK_RE = re.compile(r"\b(?:link(?:ed)? (?:it )?to|for|towards|under)\s+(?:the\s+)?goal\s+(?P<goal>.+)$")


@command("add_task", "Add a task", ["add a task read for 45 minutes at 3 pm, high priority",
                                     "add call mom tomorrow at 9 for half an hour"],
         [r"(?:add|create|new|schedule|put in)(?: a)?(?: new)? task (?P<rest>.+)",
          r"(?:add|schedule|remind me to|i need to|i have to) (?P<rest>(?!.*\b(?:goal|sacrifice|review|process|note)\b).+)"],
         typed=[(TIMETABLE, "a", "add_now")], rank=40)
def add_task(d: Dialog, g):
    today = d.today()
    text = g["rest"]
    goal_name = None
    m = LINK_RE.search(text)
    if m:
        goal_name, text = m.group("goal"), text[:m.start()].strip()
    minutes, text = P.extract_duration(text)
    priority, text = P.extract_priority(text)
    text = re.sub(r"^(?:to|called|named)\s+", "", text).strip(" ,")
    # A clear time in the words is read by the logic layer, exactly as from a typed title.
    has_time = _has_title_time(d, text, minutes)
    day, start = None, None
    if not has_time:   # spoken-only forms ("half past 9") and a day without a time, as before
        day, text = P.extract_date(text, today)
        start, text = P.extract_time(text)
    title = text.strip(" ,") or None
    title = re.sub(r"\s+(?:and|at|for|on)$", "", title) if title else None
    if not title:
        title = d.ask("What's the task called?", raw=True)
    if not minutes and not has_time:
        minutes = d.ask_duration(f"How long will {title} take?")
    if not priority:
        priority = d.ask_priority()
    with d.app.Session() as s:
        goal_id = resolve_goal(d, s, goal_name).id if goal_name else None
        task = claiming(d, lambda ampm: svc.add_task(
            s, title, minutes, goal_id, None, planned_for=day or today, start_time=start, today=today,
            priority=priority, ampm=ampm, **title_rules(d)))
        if task is None:
            return
        d.state.last_task_id = task.id
        d.say(f"Added {task.title}, {svc.format_duration(task.duration_min)}, {PRIORITY_NAMES[priority]} priority, "
              f"{when_text(task, today)}.")
        if task.understood:
            d.show(task.understood)


def _has_title_time(d: Dialog, text: str, minutes) -> bool:
    """Does the logic layer read a clear time from these words? (am / pm is
    settled later, when the task is added.)"""
    if not text:
        return False
    rules = title_rules(d)
    try:
        return svc.read_title_time(text, minutes, d.today(), d.today(), rules["window"], rules["default_minutes"],
                                   "am", rules["now"]) is not None
    except svc.TaskError:
        return False


@command("add_several", "Add several tasks for a day", ["add several tasks for tomorrow"],
         [r"(?:add|enter|plan) (?:several|some|a few|multiple) tasks(?: for (?P<when>.+))?",
          r"lets (?:add|enter) tasks(?: for (?P<when>.+))?"],
         typed=[(TIMETABLE, "n", "plan")], rank=30)
def add_several(d: Dialog, g):
    day, _ = P.extract_date(g.get("when") or "", d.today())
    day = day or d.today()
    added = 0
    while True:
        text = d.ask("What's the next task? Say that's all when you're done.")
        if text in ("thats all", "that is all", "done", "finished", "no more", "nothing", "stop"):
            break
        dname = "today" if day == d.today() else "tomorrow" if day == d.today() + timedelta(days=1) else f"{day:%A %d %B}"
        try:
            add_task(d, {"rest": f"{text} {dname}" if P.extract_date(text, d.today())[0] is None else text})
            added += 1
        except TaskError as e:
            d.say(f"I can't add that. {e}")
    d.say(f"Added {added} task{'s' if added != 1 else ''}.")


@command("plan_day", "Plan my day / re-plan", ["plan my day", "re-plan", "plan tomorrow"],
         [r"(?:plan|replan|re plan|schedule)(?: out)? my day", r"(?:re ?plan|replan)(?: my day)?(?: (?P<when>.+))?",
          r"plan (?P<when>today|tomorrow|.+day|next .+|on .+)"],
         typed=[(TIMETABLE, "p", "plan_my_day")], rank=35)
def plan_day(d: Dialog, g):
    day, _ = P.extract_date(g.get("when") or "", d.today())
    day = day or d.today()
    with d.app.Session() as s:
        result = pl.plan_day(s, day, d.app.settings.window, now=d.now())
        d.app.render_plan(result)
        placed = sorted(result.placed + result.kept, key=lambda t: t.start_at)
        if not placed and not result.overflow:
            d.say("There's nothing to plan.")
            return
        lines = [f"{clock(t.start_time)} {t.title}" for t in placed[:6]]
        more = f", and {len(placed) - 6} more" if len(placed) > 6 else ""
        msg = f"Planned {'today' if day == d.today() else f'{day:%A}'}: " + ", ".join(lines) + more + "."
        if result.overflow:
            msg += " Didn't fit: " + ", ".join(t.title for t in result.overflow) + "."
        d.say(msg)


@command("move_task", "Move a task / set its time (pins it)", ["move report to 4 pm", "put email after report"],
         [r"(?:move|shift|put|set) " + NAME + r" (?P<where>before|after) (?P<other>.+)",
          r"(?:move|shift|reschedule|push|postpone|bump|delay|put off) " + NAME + r" (?:to|till|until) (?P<when>.+)",
          r"(?:set|change) (?:the )?(?:start )?time (?:of|for) " + NAME + r" to (?P<when>.+)",
          r"start " + NAME + r" at (?P<when>.+)"],
         typed=[(TIMETABLE, "e", "set_time")], rank=45)
def move_task(d: Dialog, g):
    with d.app.Session() as s:
        task = resolve_task(d, s, g["name"])
        if g.get("where"):
            other = resolve_task(d, s, g["other"], what="task to line up with")
            task = claiming(d, lambda _: svc.move_next_to(s, task.id, other.id, g["where"], now=d.now()))
            if task is None:
                return
        else:
            when = g["when"]
            day, rest = P.extract_date(when, d.today())
            t, _ = P.extract_time(rest if rest.startswith(("at ", "until ")) else "at " + rest) if rest.strip() else (None, rest)
            if day is not None and day != task.planned_for:
                task = claiming(d, lambda _: svc.move_to_day(s, task.id, day, t, today=d.today(), now=d.now()))
                if task is None:
                    return
                d.say(f"Moved {task.title} to {when_text(task, d.today())}." +
                      ("" if t else " Say plan " + ("tomorrow" if day == d.today() + timedelta(days=1) else f"{day:%A}")
                       + " to give it a time."))
                return
            if t is None:
                raise TaskError(f"I didn't get a time from '{when}'.")
            task = claiming(d, lambda _: svc.set_start_time(s, task.id, t, now=d.now()))
            if task is None:
                return
        d.say(f"Moved {task.title} to {clock(task.start_time)}. It's pinned now.")


@command("pin_task", "Pin a task where it is", ["pin the report"], [r"pin " + NAME + r"(?: where it is)?"],
         rank=44)
def pin_task(d: Dialog, g):
    with d.app.Session() as s:
        task = resolve_task(d, s, g["name"])
        t = task.start_time or d.ask_time(f"{task.title} has no time. At what time?")
        task = claiming(d, lambda _: svc.set_start_time(s, task.id, t, now=d.now()))
        if task is None:
            return
        d.say(f"{task.title} is pinned at {clock(task.start_time)}.")


@command("unpin_task", "Unpin a task", ["unpin the report"], [r"unpin " + NAME, r"let the planner move " + NAME],
         typed=[(TIMETABLE, "u", "unpin")], rank=43)
def unpin_task(d: Dialog, g):
    with d.app.Session() as s:
        task = resolve_task(d, s, g["name"])
        svc.unpin_task(s, task.id)
        d.say(f"{task.title} is unpinned. Say re-plan to let the planner place it.")


@command("edit_task", "Change a task's title, duration or priority",
         ["rename report to quarterly report", "change the duration of report to 90 minutes", "make email urgent"],
         [r"rename (?:task )?" + NAME + r" to (?P<new>.+)",
          r"(?:change|set) (?:the )?(?:duration|length) of " + NAME + r" to (?P<dur>.+)",
          r"(?:change|set) (?:the )?priority of " + NAME + r" to (?P<prio>.+)",
          r"make " + NAME + r" (?P<prio>urgent|high priority|normal priority|low priority|high|normal|low)",
          r"change " + NAME + r" to (?P<dur>\d+ (?:minutes?|mins?|hours?).*|an hour.*|half an hour)"],
         typed=[(TIMETABLE, "c", "change_task")], rank=42)
def edit_task(d: Dialog, g):
    with d.app.Session() as s:
        task = resolve_task(d, s, g["name"])
        changes = {}
        if g.get("new"):
            changes["title"] = g["new"]
        if g.get("dur"):
            minutes, _ = P.extract_duration(g["dur"])
            if not minutes:
                raise TaskError(f"I didn't get a duration from '{g['dur']}'.")
            changes["duration_min"] = minutes
        if g.get("prio"):
            p, _ = P.extract_priority(g["prio"])
            if not p:
                raise TaskError(f"I didn't get a priority from '{g['prio']}'.")
            changes["priority"] = p
        old = task.title
        task = claiming(d, lambda ampm: svc.update_task(s, task.id, today=d.today(), ampm=ampm, **title_rules(d),
                                                        **changes))
        if task is None:
            return
        d.say(f"Updated {old}: " + ", ".join(
            {"title": f"now called {task.title}", "duration_min": f"{svc.format_duration(task.duration_min)}",
             "priority": f"{PRIORITY_NAMES[task.priority]} priority"}[k] for k in changes) + ".")
        if task.understood:
            d.show(task.understood)


@command("keep_typed_title", "Keep a task's title as typed (drop the time read from it)",
         ["keep the title as typed", "keep the report title as i typed it"],
         [r"keep (?:the )?title as (?:i )?typed(?: it)?",
          r"keep (?:the )?(?P<name>.+?) title as (?:i )?typed(?: it)?",
          r"(?:undo|ignore|drop) the time (?:read )?from the title(?: of (?P<name2>.+))?"],
         typed=[(TIMETABLE, "typed", "keep_typed_title")], rank=41)
def keep_typed_title(d: Dialog, g):
    with d.app.Session() as s:
        task = resolve_task(d, s, g.get("name") or g.get("name2") or "it")
        task = svc.restore_typed_title(s, task.id)
        d.say(f"The title is {task.title} again, with no time. Say plan my day to place it.")


@command("delete_task", "Delete a pending task", ["delete the email task"],
         [r"(?:delete|remove|cancel) (?:the )?task " + NAME, r"(?:delete|remove) " + NAME + r" from (?:my|the) (?:day|list|plan)",
          r"delete " + r"(?P<name>(?!.*\b(?:goal|sacrifice|log|review|process|notes?)\b).+)"],
         typed=[(TIMETABLE, "del", "delete_task_typed")], risky=True, rank=41)
def delete_task(d: Dialog, g):
    with d.app.Session() as s:
        task = resolve_task(d, s, g["name"])
        if not d.confirm(f"Delete {describe_task(task, d.today())}? This can't be undone."):
            d.say("Kept it.")
            return
        title = task.title
        svc.delete_task(s, task.id)
        d.state.last_task_id = None
        d.say(f"Deleted {title}.")


@command("mark_done", "Mark a task done", ["mark it done", "i finished reading", "done with the report"],
         [r"(?:mark|set) (?P<name>.+?) (?:as )?(?:done|finished|complete|completed)",
          r"(?:i am |im |i )?(?:finished|completed|am done with|done with|did|through with) (?P<name>(?!.*\bgoal\b).+?)(?:,? (?P<amount>\d+(?:\.\d+)? [a-z]+))?",
          r"(?:i am |im )?(?:done|finished)", r"(?P<name>.+?) is (?:done|finished|complete)"],
         typed=[(TIMETABLE, "d", "done")], rank=48)
def mark_done(d: Dialog, g):
    with d.app.Session() as s:
        task = resolve_task(d, s, g.get("name"))
        c = tr.contribution_for(task, d.today())
        amount, mark = 0.0, False
        if c.mode == "amount":
            if g.get("amount"):
                n, unit, _, _ = P.extract_target(g["amount"])
                amount = n or 0.0
            else:
                text = d.ask(f"How many {task.goal.unit} did {task.title} add to {task.goal.title}? Say a number or zero.")
                n = P.parse_number(text)
                amount = float(n) if n is not None else 0.0
        elif c.mode == "mark_done":
            mark = d.confirm(f"Does it complete the goal {task.goal.title}?")
        elif c.mode == "closed":
            d.say(c.note)
        task = svc.complete_task(s, task.id, contribution=amount, mark_goal_done=mark, today=d.today())
        msg = f"Marked {task.title} done."
        if task.goal and (amount or mark):
            s.refresh(task.goal)
            msg += " " + "; ".join(f"{g_.title} {tr.progress(g_).text}" for g_ in [task.goal, *tr.ancestors(task.goal)])
        d.say(msg)


def _close_by_voice(d: Dialog, name, status: TaskStatus):
    verb = "failed" if status is TaskStatus.FAILED else "skipped"
    with d.app.Session() as s:
        task = resolve_task(d, s, name)
        if task.status != TaskStatus.PENDING.value:
            raise TaskError(f"{task.title} is already {task.status}.")
        reason = d.dictate("reason", question=f"What's the reason {task.title} {'failed' if verb == 'failed' else 'was skipped'}?")
        (svc.fail_task if status is TaskStatus.FAILED else svc.skip_task)(s, task.id, reason)
        d.app.after_close(task.id)
        d.say(f"Marked {task.title} {verb}. Reason saved.")
        task_id = task.id
    run_proposal(d, ("closed", task_id, None))


@command("mark_failed", "Mark a task failed (reason required)", ["i failed the report", "mark gym as failed"],
         [r"(?:mark|set) " + NAME + r" (?:as )?failed", r"fail " + NAME,
          r"i (?:failed|couldnt do|could not do|didnt do|did not do|missed|didnt finish|did not finish) " + NAME,
          r"(?P<name>.+?) failed"],
         typed=[(TIMETABLE, "f", "fail")], rank=47)
def mark_failed(d: Dialog, g):
    _close_by_voice(d, g.get("name"), TaskStatus.FAILED)


@command("mark_skipped", "Skip a task (reason required)", ["skip the gym", "i'm skipping email"],
         [r"skip " + NAME, r"(?:mark|set) " + NAME + r" (?:as )?skipped",
          r"(?:i am |im |i )?(?:skipping|skipped|will skip) " + NAME],
         typed=[(TIMETABLE, "s", "skip")], rank=47)
def mark_skipped(d: Dialog, g):
    _close_by_voice(d, g.get("name"), TaskStatus.SKIPPED)


@command("extend_task", "A task is still going (extend it)",
         ["i'm still working on the report until 4 pm", "extend it by 15 minutes", "still going"],
         [r"(?:i am |im )?still (?:working on|doing|on) " + NAME + r"(?: (?:until|till|for) (?P<until>.+))?",
          r"extend " + NAME + r" (?:by|for|until|till|to) (?P<until>.+)",
          r"(?P<name>.+?) is (?:running over|still going|taking longer)(?: (?:until|till|by|for) (?P<until>.+))?",
          r"(?:it is |its )?still going(?: (?:until|till|for) (?P<until>.+))?"],
         typed=[(TIMETABLE, "x", "still_going")], rank=39)
def extend_task(d: Dialog, g):
    with d.app.Session() as s:
        task = resolve_task(d, s, g.get("name"))
        if task.start_at is None:
            raise TaskError(f"{task.title} has no time, so it can't run over.")
        until = g.get("until") or d.ask(f"{task.title} ends at {task.end_at:%H:%M}. Until when, or for how many more minutes?")
        new_end = parse_new_end(d, task, until)
        task_id = task.id
    run_proposal(d, ("overrun", task_id, new_end))


@command("reschedule_missed", "Reschedule a failed or skipped task", ["reschedule the report"],
         [r"reschedule " + NAME + r"(?: again)?", r"find (?:a )?new (?:time|slot) for " + NAME],
         typed=[(TIMETABLE, "r", "reschedule_again")], rank=46)
def reschedule_missed(d: Dialog, g):
    with d.app.Session() as s:
        task = resolve_task(d, s, g["name"], statuses=(TaskStatus.FAILED.value, TaskStatus.SKIPPED.value),
                            what="failed or skipped task")
        task_id = task.id
    run_proposal(d, ("closed", task_id, None))


@command("undo_reschedule", "Undo the last accepted reschedule", ["undo the reschedule"],
         [r"undo(?: the)?(?: last)?(?: reschedule| rescheduling| that| it)?", r"go back to the (?:old|previous) plan"],
         typed=[(TIMETABLE, "z", "undo_reschedule")], risky=True, rank=20)
def undo_reschedule(d: Dialog, g):
    with d.app.Session() as s:
        log = rs.last_log(s)
        if log is None or log.undone:
            raise TaskError("There's no reschedule to undo.")
        if not d.confirm(f"Undo the reschedule from {log.created_at:%H:%M}, when {log.trigger}?"):
            d.say("Kept the current plan.")
            return
        rs.undo_last(s)
        d.say("Undone. The previous plan is back, and the failure reasons are kept.")


@command("history", "Failed and skipped history", ["show my failures for fitness last month"],
         [r"(?:show|open|read)(?: me)?(?: my| the)? (?:history|failures|failed tasks|skipped tasks|misses|missed tasks|failed and skipped(?: tasks)?)(?P<rest>.*)",
          r"what did i (?:miss|fail|skip)(?P<rest>.*)"],
         typed=[(TIMETABLE, "h", "history")], rank=30)
def history(d: Dialog, g):
    today = d.today()
    rest = g.get("rest") or ""
    goal_id, goal_label = None, "all goals"
    start, end = today - timedelta(days=30), today
    m = re.search(r"\b(?:for|on)\s+(?:the\s+)?(?:goal\s+)?(?P<goal>.+?)(?=\s+(?:from|since|last|this|in)\b|$)", rest)
    kind, dd, rest2 = P.extract_period(rest, today)
    if kind is not None:
        start, end = PER.period_start(kind, dd), min(PER.period_end(kind, dd), today)
    mm = re.search(r"\bfrom (?P<a>.+?) (?:to|until) (?P<b>.+)$", rest) or re.search(r"\bsince (?P<a>.+)$", rest)
    if mm:
        a, _ = P.extract_date(mm.group("a"), today)
        b, _ = P.extract_date(mm.group("b"), today) if "b" in mm.groupdict() and mm.groupdict().get("b") else (today, "")
        if a:
            start, end = a, b or today
    with d.app.Session() as s:
        if m and m.group("goal") and not re.fullmatch(r"(?:this|last|next) (?:week|month)|today|yesterday", m.group("goal")):
            goals = s.query(tr.Goal).all()
            goal = resolve_goal(d, s, m.group("goal"), goals=goals)
            goal_id, goal_label = goal.id, goal.title
        rows = rs.reason_history(s, goal_id, start, end)
        d.app.render_history(rows, start, end)
        if not rows:
            d.say(f"No failed or skipped tasks for {goal_label} from {start:%d %B} to {end:%d %B}.")
            return
        lines = [f"{r.task_date:%A %d %B}, {r.task_title}, {r.status}, because {r.reason}" for r in rows[:5]]
        d.say(f"{len(rows)} missed for {goal_label}. " + ". ".join(lines) + ("." if len(rows) <= 5 else ", and more on screen."))


@command("link_task", "Link or unlink a task and a goal", ["link report to goal ship tomits", "unlink report"],
         [r"link (?:task )?" + NAME + r" to (?:the )?(?:goal )?(?P<goal>.+)", r"unlink (?:task )?" + NAME + r"(?: from (?:its |the )?goal)?"],
         typed=[(TIMETABLE, "l", "link_task")], rank=38)
def link_task(d: Dialog, g):
    with d.app.Session() as s:
        task = resolve_task(d, s, g["name"])
        goal = resolve_goal(d, s, g["goal"]) if g.get("goal") else None
        svc.link_task(s, task.id, goal.id if goal else None, today=d.today())
        d.say(f"Linked {task.title} to {goal.title}." if goal else f"Unlinked {task.title}.")


@command("show_day", "View another day", ["what do i have tomorrow", "show friday"],
         [r"(?:show|open|read)(?: me)?(?: my)?(?: tasks| plan)?(?: for)? (?P<when>tomorrow|yesterday|today|on .+|.+day|next .+|the .+|in \d+ days)(?:s)?(?: tasks| plan)?",
          r"what (?:do i have|is on|s on|am i doing)(?: for)? (?P<when>.+)"],
         typed=[(TIMETABLE, "t", "view_day")], rank=36)
def show_day(d: Dialog, g):
    day, _ = P.extract_date(g["when"], d.today())
    if day is None:
        raise TaskError(f"I didn't get a day from '{g['when']}'.")
    _speak_day(d, day)


def _speak_day(d: Dialog, day: date) -> None:
    with d.app.Session() as s:
        tasks = svc.tasks_for_day(s, day)
        d.app.render_day(day)
        name = "today" if day == d.today() else "tomorrow" if day == d.today() + timedelta(days=1) else f"{day:%A %d %B}"
        if not tasks:
            d.say(f"Nothing on {name}.")
            return
        pending = [t for t in tasks if t.status == TaskStatus.PENDING.value]
        timed = [f"{clock(t.start_time)} {t.title}" for t in pending if t.start_time]
        untimed = [t.title for t in pending if not t.start_time]
        done = sum(1 for t in tasks if t.status == TaskStatus.DONE.value)
        missed = sum(1 for t in tasks if t.status in (TaskStatus.FAILED.value, TaskStatus.SKIPPED.value))
        if not pending:
            extra = ", ".join(x for x in (f"{done} done" if done else "", f"{missed} missed" if missed else "") if x)
            d.say(f"Nothing left to do {name}" + (f": {extra}." if extra else "."))
            return
        msg = f"{name.capitalize()}: {len(pending)} to do"
        msg += f", {done} done" if done else ""
        msg += (". " + ", ".join(timed[:6]) + ".") if timed else "."
        if untimed:
            msg += " Not planned yet: " + ", ".join(untimed[:4]) + "."
        d.say(msg)


@command("my_day", "What's my day like", ["what's my day like"],
         [r"(?:whats|what is|how is|hows) my day(?: like| look(?:ing)?(?: like)?)?", r"read (?:me )?my day", r"whats on today",
          r"what (?:have i got|have i|do i have|is|s) left(?: to do)?(?: for)?(?: today)?", r"whats left(?: to do)?(?: for)?(?: today)?"],
         rank=34)
def my_day(d: Dialog, g):
    _speak_day(d, d.today())


@command("whats_next", "What's next", ["what's next"],
         [r"(?:whats|what is) next", r"next task", r"what should i do (?:now|next)", r"what am i doing now"], rank=33)
def whats_next(d: Dialog, g):
    with d.app.Session() as s:
        now = d.now()
        tasks = [t for t in svc.tasks_for_day(s, d.today()) if t.status == TaskStatus.PENDING.value and t.start_at]
        running = [t for t in tasks if t.start_at <= now < t.end_at]
        upcoming = sorted((t for t in tasks if t.start_at > now), key=lambda t: t.start_at)
        parts = []
        if running:
            parts.append(f"Now: {running[0].title} until {running[0].end_at:%H:%M}.")
        if upcoming:
            n = upcoming[0]
            parts.append(f"Next: {n.title} at {clock(n.start_time)} for {svc.format_duration(n.duration_min)}.")
            d.state.last_task_id = n.id
        d.say(" ".join(parts) if parts else "Nothing else is planned for today.")


@command("open_tracking", "Open the day / week / month pages", ["open this week", "show last month"],
         [r"(?:open|show|go to)(?: me)?(?: the)? (?P<what>(?:(?:this|last|previous|next|current) )?(?:day|week|month)|today|yesterday|tomorrow|this weeks|this months)(?: page| view| goals| tracking)?",
          r"(?:open|show)(?: the)? (?:tracking|goals|goal pages|day week month pages)"],
         typed=[(TIMETABLE, "g", "tracking"), (TRACKING, "d", "view_day_page"), (TRACKING, "w", "view_week_page"),
                (TRACKING, "m", "view_month_page"), (TRACKING, "c", "go_current")], rank=32)
def open_tracking(d: Dialog, g):
    kind, day, _ = P.extract_period(g.get("what") or "today", d.today())
    kind, day = kind or "day", day or d.today()
    d.state.view_kind, d.state.view_start = kind, PER.period_start(kind, day)
    _speak_page(d)


@command("go_period", "Go to the previous / next period", ["go to the next week", "previous month"],
         [r"(?:go to )?(?:the )?(?P<dir>previous|last|next) (?P<kind>day|week|month)?(?: page)?", r"go (?P<dir>back|forward) (?:a|one) (?P<kind>day|week|month)"],
         typed=[(TRACKING, "[", "go_prev"), (TRACKING, "]", "go_next")], rank=31)
def go_period(d: Dialog, g):
    kind = g.get("kind") or d.state.view_kind or "day"
    base = d.state.view_start if d.state.view_kind == kind and d.state.view_start else PER.period_start(kind, d.today())
    step = -1 if g["dir"] in ("previous", "last", "back") else 1
    d.state.view_kind, d.state.view_start = kind, PER.shift(kind, base, step)
    _speak_page(d)


def _speak_page(d: Dialog) -> None:
    kind, start = d.state.view_kind, d.state.view_start
    d.app.render_tracking(kind, start)
    with d.app.Session() as s:
        entry = tr.get_entry(s, kind, start)
        goals = list(entry.goals) if entry else []
        name = period_name(kind, start, d.today())
        msg = f"{name.capitalize()}: "
        msg += ("; ".join(f"{g_.title}, {tr.progress(g_).text}" for g_ in goals) if goals else "no goals yet") + "."
        msg += " Process is set." if entry and entry.process else " No process yet."
        if entry and entry.sacrifices:
            msg += f" {len(entry.sacrifices)} sacrifice{'s' if len(entry.sacrifices) != 1 else ''}."
        if PER.is_locked(kind, start, d.today()):
            msg += " This period has ended, so it's read-only."
        d.say(msg)


@command("close_tracking", "Back to the timetable", ["go back"],
         [r"(?:go )?back(?: to (?:the )?(?:timetable|dashboard|main screen))?", r"close (?:the )?(?:page|tracking)"],
         typed=[(TRACKING, "b", "go_back")], rank=25)
def close_tracking(d: Dialog, g):
    d.state.view_kind = d.state.view_start = None
    d.say("Back to the timetable.")
    return "close_tracking"


@command("refresh", "Refresh the screen", ["refresh"], [r"refresh", r"show (?:the )?dashboard", r"show my timetable"],
         typed=[(TIMETABLE, "", "refresh")], rank=24)
def refresh(d: Dialog, g):
    d.app.dashboard()
    d.say("Here's your timetable.")


@command("quit", "Quit tomits", ["quit"], [r"(?:quit|exit|close)(?: tomits| the app)?", r"goodbye"],
         typed=[(TIMETABLE, "q", "quit")], rank=23)
def quit_app(d: Dialog, g):
    d.app.quit_requested = True
    d.say("Saved. Bye.")


@command("help", "What can I say", ["what can i say"], [r"help", r"what can i say", r"what can you do"], rank=22)
def help_cmd(d: Dialog, g):
    from .registry import REGISTRY
    d.say("You can say: " + "; ".join([c.examples[0] for c in REGISTRY if c.examples and MAIN in c.contexts][:12]) + ".")


# ======================= tracking =======================

KIND_WORDS = {"daily": "day", "day": "day", "weekly": "week", "week": "week", "monthly": "month", "month": "month"}


@command("new_goal", "Create a goal", ["add a monthly goal run 40 km",
                                       "new weekly goal run 12 km linked to run 40 km"],
         [r"(?:add|create|new|set)(?: a| an)?(?: new)? (?P<kind>daily|weekly|monthly|day|week|month)? ?goal(?: for (?P<period>today|tomorrow|this week|next week|this month|next month))?(?: (?P<rest>.+))?"],
         typed=[(TRACKING, "n", "new_goal")], rank=12)
def new_goal(d: Dialog, g):
    today = d.today()
    rest = g.get("rest") or ""
    parent_name = None
    m = re.search(r"\b(?:linked to|link(?:ed)? it to|under|towards|as part of)\s+(?:the\s+)?(?:goal\s+)?(?P<p>.+)$", rest)
    if m:
        parent_name, rest = m.group("p"), rest[:m.start()].strip()
    no_target = bool(re.search(r"\b(?:no|without a) target\b", rest))
    rest = re.sub(r"\b(?:with )?(?:no|without a) target\b", "", rest).strip()
    if g.get("period"):
        kind, day, _ = P.extract_period(g["period"], today)
    elif g.get("kind"):
        kind, day = KIND_WORDS[g["kind"]], today
    else:
        kind, day, _ = period_of(d, "", ask=True)
    target, unit, rest, _ = (None, None, rest, False) if no_target else P.extract_target(rest)
    title = d.dictate("goal title", initial=rest or None, question="What's the goal?")
    with d.app.Session() as s:
        parent_id = None
        if parent_name:
            cands = tr.link_candidates(s, kind, day, unit)
            if not cands:
                raise TaskError(f"There's no goal one level up with {('unit ' + unit) if unit else 'no target'} to link to.")
            parent_id = resolve_goal(d, s, parent_name, goals=cands, what="goal to link to").id
        goal = tr.create_goal(s, kind, day, title, target, unit, parent_id, today=today)
        msg = f"Created the {kind}ly goal {goal.title}" if kind != "day" else f"Created the daily goal {goal.title}"
        msg += f", target {tr.fmt_amount(target)} {unit}" if target else ", done or not done"
        msg += f", linked to {goal.parent.title}." if goal.parent else "."
        d.say(msg)


@command("edit_goal", "Rename, re-target or (un)link a goal",
         ["rename goal run to run more", "change the target of run 40 km to 50", "link goal run 12 km to run 40 km"],
         [r"rename (?:the )?goal " + NAME + r" to (?P<new>.+)",
          r"(?:change|set) (?:the )?target (?:of|for) (?:the )?(?:goal )?" + NAME + r" to (?P<target>.+)",
          r"link (?:the )?goal " + NAME + r" to (?:the )?(?:goal )?(?P<parent>.+)",
          r"unlink (?:the )?goal " + NAME],
         typed=[(TRACKING, "e", "edit_goal")], rank=11)
def edit_goal(d: Dialog, g):
    with d.app.Session() as s:
        goal = resolve_goal(d, s, g["name"])
        changes = {}
        if g.get("new"):
            changes["title"] = d.dictate("new goal title", initial=g["new"])
        if g.get("target"):
            if re.search(r"\b(?:no|none|nothing)\b", g["target"]):
                changes["target"] = None
            else:
                n, unit, _, _ = P.extract_target(g["target"])
                if n is None:
                    num = P.parse_number(g["target"])
                    n = float(num) if num is not None else None
                if n is None:
                    raise TaskError(f"I didn't get a number from '{g['target']}'.")
                changes["target"] = n
                if unit and not P.same_unit(unit, goal.unit):
                    changes["unit"] = unit
        if "parent" in g and g.get("parent"):
            cands = tr.link_candidates(s, goal.kind, goal.period_start, goal.unit)
            changes["parent_id"] = resolve_goal(d, s, g["parent"], goals=cands, what="goal to link to").id
        elif g.get("parent") is None and "unlink" in (d.state.history[-1] if d.state.history else ""):
            changes["parent_id"] = None
        if not changes:
            changes["parent_id"] = None  # "unlink goal X"
        goal = tr.update_goal(s, goal.id, today=d.today(), **changes)
        d.say(f"Updated the goal: {goal.title}, {tr.progress(goal).text}" +
              (f", linked to {goal.parent.title}." if goal.parent else "."))


@command("delete_goal", "Delete a goal (only unused ones)", ["delete goal spare"],
         [r"(?:delete|remove) (?:the )?goal " + NAME], typed=[(TRACKING, "x", "delete_goal")], risky=True, rank=10)
def delete_goal(d: Dialog, g):
    with d.app.Session() as s:
        goal = resolve_goal(d, s, g["name"])
        if not d.confirm(f"Delete the {goal.kind.value} goal {goal.title}?"):
            d.say("Kept it.")
            return
        title = goal.title
        tr.delete_goal(s, goal.id, today=d.today())
        d.say(f"Deleted the goal {title}.")


@command("log_progress", "Log progress on a goal", ["i ran 3 km", "log 5 km to running"],
         [r"i (?:have )?(?:read|did|ran|wrote|walked|studied|practiced|practised|cycled|swam|made|finished|completed|logged|done) (?P<n>\d+(?:\.\d+)?) (?P<unit>[a-z]+)(?: (?:for|on|towards|to) (?:the )?(?:goal )?(?P<goal>.+?))?(?: (?P<when>yesterday|today))?",
          r"(?:log|add|record) (?P<n>\d+(?:\.\d+)?) (?P<unit>[a-z]+)(?: (?:to|on|for|towards) (?:the )?(?:goal )?(?P<goal>.+?))?(?: (?P<when>yesterday|today))?"],
         typed=[(TRACKING, "l", "log_progress")], rank=9)
def log_progress(d: Dialog, g):
    today = d.today()
    on = today - timedelta(days=1) if g.get("when") == "yesterday" else today
    amount, unit = float(g["n"]), g["unit"]
    with d.app.Session() as s:
        goals = [x for x in tr.open_goals(s, today) if x.has_target and PER.contains(x.kind, x.period_start, on)]
        if g.get("goal"):
            goal = resolve_goal(d, s, g["goal"], goals=goals)
        else:
            same = [x for x in goals if P.same_unit(x.unit, unit)]
            if not same:
                raise TaskError(f"There's no open goal measured in {unit}.")
            lowest = min(PER.ORDER[x.kind] for x in same)  # log on the day goal if there is one
            level = [x for x in same if PER.ORDER[x.kind] == lowest]
            goal = level[0] if len(level) == 1 else d.choose(level, goal_desc, "goal")
        if not P.same_unit(goal.unit, unit):
            raise TaskError(f"{goal.title} is measured in {goal.unit}, not {unit}.")
        tr.log_progress(s, goal.id, amount, on=on, today=today)
        s.refresh(goal)
        d.say(f"Logged {tr.fmt_amount(amount)} {goal.unit}. " +
              "; ".join(f"{x.title} {tr.progress(x).text}" for x in [goal, *tr.ancestors(goal)]) + ".")


@command("remove_log", "Remove a progress log", ["remove the last log for run 12 km"],
         [r"(?:remove|delete|undo) (?:the )?last (?:progress )?(?:log|entry)(?: (?:for|on) (?:the )?(?:goal )?(?P<goal>.+))?",
          r"(?:remove|delete) (?:progress )?log (?P<id>\d+)"],
         typed=[(TRACKING, "u", "remove_log")], risky=True, rank=8)
def remove_log(d: Dialog, g):
    with d.app.Session() as s:
        if g.get("id"):
            log = s.get(tr.ProgressLog, int(g["id"]))
            if log is None:
                raise TaskError(f"There's no progress log {g['id']}.")
        else:
            goals = [x for x in tr.open_goals(s, d.today()) if x.logs]
            if g.get("goal"):
                goals = [resolve_goal(d, s, g["goal"], goals=goals)]
            logs = sorted((l for x in goals for l in x.logs), key=lambda l: l.id)
            if not logs:
                raise TaskError("There's no progress log to remove.")
            log = logs[-1]
        if not d.confirm(f"Remove {tr.fmt_amount(log.amount)} {log.goal.unit} logged on {log.logged_for:%A} for {log.goal.title}?"):
            d.say("Kept it.")
            return
        tr.delete_log(s, log.id, today=d.today())
        d.say("Removed.")


@command("goal_done", "Mark a no-target goal done / not done", ["mark goal call mom done"],
         [r"(?:mark|set) (?:the )?goal " + NAME + r" (?:as )?(?P<neg>not )?done",
          r"(?:the )?goal " + NAME + r" is (?P<neg>not )?done",
          r"i (?:finished|completed|achieved) (?:the )?goal " + NAME],
         typed=[(TRACKING, "k", "toggle_done")], rank=7)
def goal_done(d: Dialog, g):
    with d.app.Session() as s:
        goal = resolve_goal(d, s, g["name"])
        done = not g.get("neg")
        tr.set_goal_done(s, goal.id, done, today=d.today())
        d.say(f"{goal.title} is {'done' if done else 'not done'}.")


@command("set_process", "Set the process for a day / week / month", ["set today's process", "set this week's process to read every night"],
         [r"(?:set|write|change|update)(?: the| my)? (?P<period>todays|this weeks|this months|tomorrows|next weeks|next months)? ?process(?: for (?P<p2>today|tomorrow|this week|next week|this month|next month))?(?: to (?P<text>.+))?",
          r"(?:my )?process (?:for (?P<p3>today|this week|this month) )?is (?P<text2>.+)"],
         typed=[(TRACKING, "p", "set_process")], rank=6)
def set_process(d: Dialog, g):
    phrase = (g.get("period") or g.get("p2") or g.get("p3") or "").replace("todays", "today").replace("weeks", "week").replace("months", "month").replace("tomorrows", "tomorrow")
    kind, day, _ = period_of(d, phrase)
    text = d.dictate("process", initial=g.get("text") or g.get("text2"), question="What's the process?")
    with d.app.Session() as s:
        tr.set_process(s, kind, day, text, today=d.today())
    d.say(f"Process saved for {period_name(kind, day, d.today())}.")


@command("add_sacrifice", "Add a sacrifice (planned or made)", ["add a sacrifice no phone after 10, planned", "i gave up sugar"],
         [r"add (?:a )?sacrifice (?P<rest>.+)", r"i (?P<made>gave up|sacrificed|skipped out on) (?P<rest>.+)",
          r"i (?P<planned>will give up|am giving up|plan to give up|m giving up) (?P<rest>.+)"],
         typed=[(TRACKING, "s", "add_sacrifice")], rank=5)
def add_sacrifice(d: Dialog, g):
    rest = g["rest"]
    status = "made" if g.get("made") else "planned"
    m = re.search(r"\b(?:as )?(?P<st>planned|made)$", rest)
    if m:
        status, rest = m.group("st"), rest[:m.start()].strip()
    kind, day, rest = period_of(d, rest, ask=False, default_kind="day")
    rest = re.sub(r"\s+(?:for|this|on)$", "", rest).strip()
    with d.app.Session() as s:
        tr.add_sacrifice(s, kind, day, rest, status, today=d.today())
    d.say(f"Added the sacrifice {rest}, {status}, for {period_name(kind, day, d.today())}.")


def _find_sacrifice(d: Dialog, s, name: str, status: Optional[str] = None) -> Sacrifice:
    """A sacrifice by name, open periods first. One in an ended period is left
    to the logic layer, which refuses it and says why."""
    items = [x for x in s.query(Sacrifice).all() if status is None or x.status == status]
    matches = P.fuzzy_matches(name, items, key=lambda x: x.text)
    if not matches:
        raise TaskError(f"I couldn't find a {status + ' ' if status else ''}sacrifice called '{name}'.")
    open_ = [(sc, x) for sc, x in matches if not PER.is_locked(x.entry.kind, x.entry.start, d.today())]
    matches = open_ or matches
    return P.pick_unique(matches) or d.choose([x for _, x in matches], lambda x: f"{x.text}, {x.status}", "sacrifice")


@command("made_sacrifice", "Mark a planned sacrifice as made",
         ["mark sacrifice no phone as made", "i made the sacrifice no phone"],
         [r"(?:mark|set) (?:the )?sacrifice " + NAME + r" (?:as )?(?:made|done)",
          r"i (?:made|kept|did) (?:the )?sacrifice " + NAME,
          r"(?:the )?sacrifice " + NAME + r" is (?:made|done)"],
         typed=[(TRACKING, "h", "sacrifice_made")], rank=4)
def made_sacrifice(d: Dialog, g):
    with d.app.Session() as s:
        item = _find_sacrifice(d, s, g["name"], "planned")
        tr.mark_sacrifice_made(s, item.id, today=d.today())
        d.say(f"{item.text} is marked as made.")


@command("remove_sacrifice", "Delete a sacrifice", ["remove sacrifice no phone", "delete the sacrifice no phone"],
         [r"(?:remove|delete) (?:the )?sacrifice " + NAME],
         typed=[(TRACKING, "del", "remove_sacrifice")], rank=4)
def remove_sacrifice(d: Dialog, g):
    # No confirmation, by request: the web app's Undo (and "undo my last change") covers it.
    with d.app.Session() as s:
        item = _find_sacrifice(d, s, g["name"])
        text = item.text
        tr.remove_sacrifice(s, item.id, today=d.today())
        d.say(f"Deleted the sacrifice {text}.")


@command("write_review", "Write a review", ["write my review for today", "write the review for last week"],
         [r"(?:write|dictate|add|update|change)(?: my| the| a)? review(?: for (?P<period>.+))?",
          r"(?:my )?review (?:for (?P<p2>today|yesterday|this week|last week|this month|last month) )?is (?P<text>.+)"],
         typed=[(TRACKING, "r", "set_review")], rank=3)
def write_review(d: Dialog, g):
    kind, day, _ = period_of(d, g.get("period") or g.get("p2") or "")
    text = d.dictate("review", initial=g.get("text"), question="Go ahead with your review.")
    with d.app.Session() as s:
        tr.set_review(s, kind, day, text, today=d.today())
    d.say(f"Review saved for {period_name(kind, day, d.today())}.")


@command("progress", "Read goal progress aloud", ["how am i doing on this month's goal", "how am i doing"],
         [r"how am i doing(?: on (?P<what>.+))?", r"(?:read|whats|what is)(?: me)?(?: my)? (?:goal )?progress(?: on (?P<w2>.+))?",
          r"read(?: me)?(?: my)? goals(?: for (?P<w3>.+))?"], rank=2)
def progress(d: Dialog, g):
    what = (g.get("what") or g.get("w2") or g.get("w3") or "").strip()
    today = d.today()
    with d.app.Session() as s:
        kind, day, rest = P.extract_period(what.replace("s goal", " goal"), today)
        rest = re.sub(r"\b(?:goals?|my|the)\b", "", rest).strip()
        if rest:
            goals = [resolve_goal(d, s, rest)]
        elif kind:
            goals = tr.goals_for_period(s, kind, day)
        else:
            goals = tr.open_goals(s, today)
            goals = [x for x in goals if PER.contains(x.kind, x.period_start, today)]
        if not goals:
            d.say("There are no goals for that yet.")
            return
        d.say("; ".join(f"{x.kind.value} goal {x.title}: {tr.progress(x).text}" for x in goals[:6]) + ".")


@command("fill_in", "Fill in a missing goal or process (answers the reminder)", ["fill in my plan"],
         [r"fill (?:in|out) (?:my|the) plan", r"answer (?:the )?reminder", r"whats missing"], rank=1)
def fill_in(d: Dialog, g):
    with d.app.Session() as s:
        missing = tr.missing_fill_ins(s, d.today())
    if not missing:
        d.say("Nothing is missing. Today, this week and this month all have a goal and a process.")
        return
    for m in missing:
        name = period_name(m.kind.value, m.start, d.today())
        if "goal" in m.parts:
            title = d.dictate(f"goal for {name}", question=f"What's your goal for {name}?")
            target, unit, _, _ = P.extract_target(P.normalize(title))
            with d.app.Session() as s:
                tr.create_goal(s, m.kind, m.start, title, target, unit, today=d.today())
            d.say(f"Goal saved for {name}.")
        if "process" in m.parts:
            text = d.dictate(f"process for {name}", question=f"What's your process for {name}?")
            with d.app.Session() as s:
                tr.set_process(s, m.kind, m.start, text, today=d.today())
            d.say(f"Process saved for {name}.")
    d.say("All filled in.")


# ======================= settings and voice =======================

@command("settings", "Change the day window, snooze length or default task length",
         ["set my day from 8 am to 10 pm", "set snooze to 10 minutes", "set the default task length to 45 minutes"],
         [r"set (?:my |the )?day(?: window)? (?:from )?(?P<a>.+?) (?:to|until|till) (?P<b>.+)",
          r"(?:set |change )?(?:the )?snooze(?: length| time)? (?:to )?(?P<snooze>\d+)(?: minutes?)?",
          r"(?:set |change )?(?:the )?default (?:task )?(?:length|duration)(?: of a task)? (?:to )?(?P<deflen>.+)",
          r"(?:open |show |read )?(?:my )?settings"],
         typed=[(TIMETABLE, "o", "settings_menu"), (SETTINGS, "s", "change_settings"), (SETTINGS, "w", "change_window"),
                (SETTINGS, "d", "change_default_length")],
         rank=15)
def settings_cmd(d: Dialog, g):
    st = d.app.settings
    if g.get("a"):
        a, _ = P.extract_time("at " + g["a"] if not g["a"].startswith("at") else g["a"])
        b, _ = P.extract_time("at " + g["b"] if not g["b"].startswith("at") else g["b"])
        if not (a and b):
            raise TaskError("I need a start and end time, like from 8 am to 10 pm.")
        st.day_start, st.day_end = validate_window(a, b)
        save_settings(d.app.settings_file, st)
        d.say(f"Your day now runs from {clock(a)} to {clock(b)}.")
    elif g.get("deflen"):
        minutes, _ = P.extract_duration(g["deflen"])
        if minutes is None and g["deflen"].strip().isdigit():
            minutes = int(g["deflen"])
        if not minutes:
            raise TaskError(f"I didn't get a length from '{g['deflen']}'.")
        st.default_task_minutes = validate_task_minutes(minutes)
        save_settings(d.app.settings_file, st)
        d.say(f"A single time in a title now gives {svc.format_duration(st.default_task_minutes)}.")
    elif g.get("snooze"):
        st.snooze_minutes = validate_snooze(g["snooze"])
        save_settings(d.app.settings_file, st)
        d.say(f"Snooze is now {st.snooze_minutes} minutes.")
    else:
        d.say(f"Day from {st.day_start} to {st.day_end}. Snooze {st.snooze_minutes} minutes. Push to talk key "
              f"{st.push_to_talk_key}. Hands free {'on' if st.hands_free else 'off'}, wake phrase {st.wake_phrase}. "
              f"Spoken replies {'on' if st.spoken_replies else 'off'}.")


@command("voice_settings", "Voice settings", ["turn off spoken replies", "turn on hands free", "set the wake phrase to hello tomits",
                                              "set the push to talk key to b"],
         [r"turn (?P<sr>on|off) (?:the )?(?:spoken replies|voice replies|talking back|speech)",
          r"(?P<sr2>stop|start) talking(?: back)?",
          r"(?:turn (?P<hf>on|off) (?:the )?hands ?free(?: mode)?|(?P<hf2>enable|disable) hands ?free(?: mode)?)",
          r"set (?:the )?wake (?:phrase|word) to (?P<wake>.+)",
          r"set (?:the )?push to talk key to (?P<key>[a-z0-9])"], typed=[(SETTINGS, "v", "voice_options")], rank=16)
def voice_settings(d: Dialog, g):
    st = d.app.settings
    if g.get("sr") or g.get("sr2"):
        st.spoken_replies = (g.get("sr") == "on") or (g.get("sr2") == "start")
        msg = "Spoken replies are on." if st.spoken_replies else "Spoken replies are off; I'll only show text."
    elif g.get("hf") or g.get("hf2"):
        st.hands_free = (g.get("hf") == "on") or (g.get("hf2") == "enable")
        msg = (f"Hands-free is on. Say {st.wake_phrase} before a command." if st.hands_free else "Hands-free is off.")
    elif g.get("wake"):
        st.wake_phrase = g["wake"].strip()
        msg = f"The wake phrase is now {st.wake_phrase}."
    else:
        st.push_to_talk_key = validate_key(g["key"])
        msg = f"Push to talk key is now {st.push_to_talk_key}."
    save_settings(d.app.settings_file, st)
    d.say(msg)


@command("mute", "Mute / unmute the microphone", ["mute", "unmute"],
         [r"(?P<un>un)?mute(?: the)?(?: mic| microphone)?", r"stop listening", r"(?P<un2>start) listening"],
         typed=[(TIMETABLE, "m", "toggle_mute")], rank=14)
def mute(d: Dialog, g):
    st = d.app.settings
    st.muted = not (g.get("un") or g.get("un2"))
    save_settings(d.app.settings_file, st)
    d.say("Microphone muted. Press the push to talk key and say unmute, or press m." if st.muted else "Microphone on.")


# ======================= answers inside prompts =======================

@command("alarm_dismiss", "Dismiss a ringing alarm", ["dismiss"], [r"dismiss(?: it| the alarm)?", r"stop(?: it| the alarm)?", r"turn it off", r"ok"],
         typed=[(ALARM, "d", "dismiss")], contexts=(ALARM,))
def alarm_dismiss(d, g):
    return "d"


@command("alarm_snooze", "Snooze a ringing alarm", ["snooze", "snooze for 10 minutes"],
         [r"snooze(?: it)?(?: for (?P<n>\d+)(?: minutes?)?)?", r"remind me (?:again )?in (?P<n2>\d+)(?: minutes?)?"],
         typed=[(ALARM, "z", "snooze")], contexts=(ALARM,))
def alarm_snooze(d, g):
    n = g.get("n") or g.get("n2")
    return f"z:{n}" if n else "z"


@command("checkin_answer", "Answer the end-of-task check-in", ["done", "still going until 4", "failed", "skipped", "later"],
         [r"(?P<d>done|finished|yes|i finished)", r"(?:(?:i am |im )?still (?:going|working|on it))(?: (?:until|till|for) (?P<until>.+))?",
          r"(?P<f>failed|i failed|fail)", r"(?P<s>skipped|skip|i skipped)", r"(?P<l>later|not now|ask me later)"],
         typed=[(CHECKIN, "d", "done"), (CHECKIN, "g", "still going"), (CHECKIN, "f", "failed"), (CHECKIN, "s", "skipped"),
                (CHECKIN, "l", "later")], contexts=(CHECKIN,))
def checkin_answer(d, g):
    if g.get("d"):
        return "d"
    if g.get("f"):
        return "f"
    if g.get("s"):
        return "s"
    if g.get("l"):
        return "l"
    return f"g:{g.get('until') or ''}"


@command("proposal_answer", "Accept or reject a reschedule", ["yes", "no", "repeat"],
         [r"(?P<y>yes|accept|yes please|do it|ok|okay)", r"(?P<n>no|reject|no thanks|dont)", r"(?P<r>repeat|say it again|read it again)"],
         typed=[(PROPOSAL, "y", "accept"), (PROPOSAL, "n", "reject")], contexts=(PROPOSAL,), risky=True)
def proposal_answer(d, g):
    return "y" if g.get("y") else "n" if g.get("n") else "r"


@command("collision_answer", "Answer the fixed-task warning", ["shorten", "move the rest", "leave it"],
         [r"(?P<s>shorten(?: it)?)", r"(?P<m>move(?: the rest)?(?: after it)?)", r"(?P<l>leave(?: it)?)"],
         typed=[(COLLISION, "s", "shorten"), (COLLISION, "m", "continue"), (COLLISION, "l", "leave")], contexts=(COLLISION,))
def collision_answer(d, g):
    return "s" if g.get("s") else "m" if g.get("m") else "l"


@command("cap_answer", "Answer the reschedule-limit question", ["keep", "split", "drop"],
         [r"(?P<k>keep(?: rescheduling)?)", r"(?P<p>split(?: it)?)", r"(?P<d>drop(?: it)?)"],
         typed=[(CAP, "k", "keep"), (CAP, "p", "split"), (CAP, "d", "drop")], contexts=(CAP,), risky=True)
def cap_answer(d, g):
    return "k" if g.get("k") else "p" if g.get("p") else "d"


# ======================= voice versions of the typed prompts =======================

from .registry import match as _match  # noqa: E402

ALARM_GRAMMAR = ["dismiss", "stop", "snooze", "snooze for five minutes", "snooze for ten minutes",
                 "snooze for fifteen minutes", "snooze for twenty minutes", "snooze for thirty minutes"]


def voice_ringing(d: Dialog) -> None:
    """While an alarm rings, listen only for dismiss / snooze (the tone pauses
    while the mic listens; see VoiceIO.listen)."""
    app = d.app
    from ..ringer import key_of
    for r in app.ringer.ringing():
        alarm = r.alarm
        for _ in range(3):
            heard = d.io.listen(f"Alarm: {alarm.message} Say dismiss or snooze.", ALARM_GRAMMAR)
            found = _match(P.normalize(heard.text), ALARM)
            if found is None:
                continue
            answer = found[0].handler(d, found[1])
            if answer.startswith("z"):
                minutes = int(answer.split(":")[1]) if ":" in answer else None
                try:
                    due = app.ringer.snooze(key_of(alarm), minutes)
                    d.say(f"Snoozed until {due:%H:%M}.")
                except KeyError:
                    d.say("It already stopped.")
                    app._after_ringing(alarm)
            else:
                app.ringer.dismiss(key_of(alarm))
                app._after_ringing(alarm)
                d.say("Dismissed.")
            break
        else:
            d.say("The alarm is still ringing; press Enter to answer it by typing.")


def voice_checkin(d: Dialog, alarm) -> None:
    """End of a task: done, still going, failed, skipped or later, by voice."""
    app = d.app
    with app.Session() as s:
        task = s.get(Task, alarm.task_id)
        if task is None or task.status != TaskStatus.PENDING.value:
            return
        title, task_id = task.title, task.id
    d.state.last_task_id = task_id
    for _ in range(3):
        text = d.ask(f"{title} was planned to end now. Done, still going, failed, skipped, or later?")
        found = _match(text, CHECKIN)
        if found is None:
            continue
        answer = found[0].handler(d, found[1])
        if answer == "d":
            return mark_done(d, {"name": title})
        if answer == "f":
            return _close_by_voice(d, title, TaskStatus.FAILED)
        if answer == "s":
            return _close_by_voice(d, title, TaskStatus.SKIPPED)
        if answer == "l":
            d.say("OK, it stays open.")
            return
        return extend_task(d, {"name": title, "until": answer.split(":", 1)[1] or None})
    d.say("I'll leave it open.")



# ======================= v1.5.1: bulk delete, voice log, mic =======================

SCOPES = {"tasks and goals": "tasks and goals", "goals and tasks": "tasks and goals", "everything": "tasks and goals",
          "tasks": "tasks", "goals": "goals", None: "tasks and goals", "": "tasks and goals"}


@command("delete_all", "Delete all tasks and/or goals (only what the rules allow)",
         ["delete all the tasks and goals from everywhere", "delete all my goals"],
         [r"(?:delete|remove|clear|erase|wipe)(?: out)? (?:all|everything)(?: of)?(?: the| my)?"
          r"(?: (?P<what>tasks and goals|goals and tasks|tasks|goals|everything))?(?: from everywhere| everywhere| in the app| from the app)?"],
         typed=[(SETTINGS, "x", "bulk_delete_typed")], risky=True, rank=19)
def delete_all(d: Dialog, g):
    scope = SCOPES.get(g.get("what"), "tasks and goals")
    with d.app.Session() as s:
        plan = svc.bulk_delete_plan(s, scope, today=d.today())
        if plan.empty:
            d.say(plan.describe())
            return
        if not d.confirm(plan.describe() + " Delete them?"):
            d.say("Nothing was deleted.")
            return
        n_tasks, n_goals = svc.bulk_delete(s, plan, today=d.today())
        d.state.last_task_id = None
        d.say(f"Deleted {n_tasks} task{'s' if n_tasks != 1 else ''} and {n_goals} goal{'s' if n_goals != 1 else ''}.")


@command("clear_day", "Delete all pending tasks on a day", ["clear tomorrow", "delete all the tasks for friday"],
         [r"clear (?:all )?(?:of )?(?:the |my )?(?:tasks |plan )?(?:for |on |from )?(?P<when>today|tomorrow|.+day|next .+|on .+|the .+)",
          r"(?:delete|remove) all (?:the |my )?tasks (?:for|on|from) (?P<when>(?!everywhere|the app).+)"],
         risky=True, rank=18)
def clear_day(d: Dialog, g):
    day, _ = P.extract_date(g["when"], d.today())
    if day is None:
        raise TaskError(f"I didn't get a day from '{g['when']}'.")
    with d.app.Session() as s:
        plan = svc.bulk_delete_plan(s, "day", day=day, today=d.today())
        if plan.empty:
            d.say(plan.describe())
            return
        if not d.confirm(plan.describe() + " Delete them?"):
            d.say("Nothing was deleted.")
            return
        n, _ = svc.bulk_delete(s, plan, today=d.today())
        d.say(f"Cleared {n} task{'s' if n != 1 else ''} from {day:%A %d %B}.")


@command("show_voice_log", "Show recent voice commands", ["show the voice log"],
         [r"(?:show|read|open)(?: me)?(?: the| my)? (?:voice )?(?:log|transcripts?|voice history|recent (?:voice )?commands)",
          r"what did you (?:hear|understand)"],
         typed=[(SETTINGS, "l", "show_voice_log")], rank=17)
def show_voice_log(d: Dialog, g):
    rows = d.app.voice_log.recent(10)
    d.app.render_voice_log(rows)
    if not rows:
        d.say("The voice log is empty.")
        return
    d.say("Last commands: " + ". ".join(
        f"'{r.transcript}', {r.command or 'not understood'}, {'done' if r.acted else 'not acted on'}" for r in rows[:3]) + ".")


@command("mic_test", "Test the microphone", ["test my mic"],
         [r"(?:test|check)(?: my| the)? (?:mic|microphone|audio)", r"mic test"],
         typed=[(SETTINGS, "t", "mic_test")], rank=17)
def mic_test_cmd(d: Dialog, g):
    d.say("Starting the mic test.")
    d.app.mic_test()


@command("input_device", "List microphones / choose one", ["list my microphones", "use microphone 2"],
         [r"(?:list|show)(?: my| the)? (?:microphones|mics|input devices|audio inputs)",
          r"use (?:input )?(?:device|microphone|mic) (?:number )?(?P<n>\d+)", r"which (?:mic|microphone) (?:is|am i) (?:in use|using)"],
         typed=[(SETTINGS, "i", "pick_input_device")], rank=17)
def input_device_cmd(d: Dialog, g):
    from . import audio as A
    try:
        devices = A.list_input_devices()
    except Exception as e:
        raise TaskError(f"I can't list microphones: {e}")
    d.app.render_devices(devices)
    if g.get("n"):
        n = int(g["n"])
        if not any(x.index == n for x in devices):
            raise TaskError(f"There's no input device {n}.")
        d.app.settings.input_device = str(n)
        save_settings(d.app.settings_file, d.app.settings)
        d.app.voice_io = None  # reopen with the new device
        dev = [x for x in devices if x.index == n][0]
        d.say(f"Using {dev.describe()}." + (f" Warning: {dev.warning}" if dev.warning else ""))
    else:
        cur = d.app.settings.input_device or "the Windows default"
        d.say(f"{len(devices)} microphones found; the list is on screen. In use: {cur}. Say use microphone and a number to change.")


# ======================= v1.6: web app commands (also by voice and typing) =======================

LAYOUT_WORDS = r"(?:timeline|calendar grid|calendar|board|focus on now|focus|split dashboard|dashboard|voice first|voice)"
LAYOUT_NUMBERS = {"timeline": 1, "calendar grid": 2, "calendar": 2, "board": 3, "focus on now": 4, "focus": 4,
                  "split dashboard": 5, "dashboard": 5, "voice first": 6, "voice": 6}


@command("undo_action", "Undo my last change", ["undo my last change", "take that back"],
         [r"undo (?:my |the )?last (?:change|action|edit)", r"undo (?:my|that|this) (?:change|action|edit)",
          r"take (?:that|it) back", r"undo the change"], risky=True, rank=18)
def undo_action(d: Dialog, g):
    undo_fn = getattr(d.app, "undo_last_action", None)
    label_fn = getattr(d.app, "last_action_label", None)
    if undo_fn is None:
        raise TaskError("Undoing a single change works in the browser app. Here, z undoes the last reschedule.")
    label = label_fn() if label_fn else None
    if not label:
        raise TaskError("There's nothing to undo.")
    if not d.confirm(f"Undo {label}? Failure reasons are always kept."):
        d.say("Nothing was undone.")
        return
    undo_fn()
    d.say(f"Undone: {label}.")


@command("dismiss_reminder", "Hide the fill-in reminder banner", ["dismiss the reminders", "hide the reminder"],
         [r"(?:dismiss|hide|close|clear)(?: the| my| this)? reminders?(?: banner)?"], rank=15)
def dismiss_reminder_cmd(d: Dialog, g):
    from .. import reminders as REM
    with d.app.Session() as s:
        items = REM.active_reminders(s, d.today())
        if not items:
            d.say("There's no reminder showing.")
            return
        for item in items:
            REM.dismiss_reminder(s, item.kind, item.start, item.part, now=d.now())
    d.say("Hidden. It won't come back for these; fill them in on the day, week or month page.")


@command("switch_layout", "Switch the app layout", ["switch to the board layout", "use layout 2"],
         [r"(?:switch|change|go) (?:to )?(?:the )?(?P<layout>" + LAYOUT_WORDS + r") (?:layout|view|design)",
          r"(?:switch|change|set)(?: the)? layout to (?:the )?(?P<layout2>" + LAYOUT_WORDS + r")",
          r"use layout (?:number )?(?P<n>[1-6])"], rank=16)
def switch_layout_cmd(d: Dialog, g):
    from ..settings import LAYOUTS, validate_layout
    n = int(g["n"]) if g.get("n") else LAYOUT_NUMBERS[g.get("layout") or g.get("layout2")]
    d.app.settings.ui_layout = validate_layout(n)
    save_settings(d.app.settings_file, d.app.settings)
    d.say(f"Switched to the {LAYOUTS[n][0]} layout.")


@command("set_theme", "Light, dark or system theme", ["dark mode", "use the system theme"],
         [r"(?:switch to |use |turn on |go )?(?:the )?(?P<theme>dark|light|system|default) (?:mode|theme)"], rank=16)
def set_theme_cmd(d: Dialog, g):
    from ..settings import validate_theme
    theme = "system" if g["theme"] == "default" else g["theme"]
    d.app.settings.ui_theme = validate_theme(theme)
    save_settings(d.app.settings_file, d.app.settings)
    d.say(f"Theme set to {theme}.")


@command("finish_setup", "Finish or skip the first-run setup", ["finish the setup", "skip setup"],
         [r"(?:finish|skip|close|end|done with)(?: the)? (?:setup|set up|first run setup|welcome(?: steps)?)"], rank=15)
def finish_setup_cmd(d: Dialog, g):
    d.app.settings.setup_done = True
    save_settings(d.app.settings_file, d.app.settings)
    d.say("Setup finished. Any missing goal or process stays as a banner until you fill it in.")


# ======================= Remember (notes, v1.8) =======================

NOTE_COLOR_RE = re.compile(r"\s+in (?P<c>" + "|".join(N.COLORS) + r")$")


@command("add_note", "Add a note to Remember", ["remember to water the plants", "remember to call the bank at 5 pm tomorrow",
                                                "add a note buy stamps in sage"],
         [r"remember (?:to |that )?(?P<text>.+)", r"(?:add|new|make|write) (?:a )?note(?: to self)?(?: to| that)? (?P<text>.+)",
          r"note to self (?P<text>.+)"],
         typed=[(TIMETABLE, "note", "add_note")], rank=5)
def add_note(d: Dialog, g):
    text, color = g["text"], None
    m = NOTE_COLOR_RE.search(text)
    if m:
        color, text = m.group("c"), text[:m.start()]
    ampm = None
    with d.app.Session() as s:
        for _ in range(3):
            try:
                note = N.add_note(s, text, color=color, now=d.now(), window=d.app.settings.window, ampm=ampm)
                break
            except svc.AmbiguousTime as e:
                ampm = d.ask_choice(e.question + " Say am or pm.", AMPM_WORDS)
        else:
            raise Cancelled()
        d.say(f"Added the note: {N.describe(note, d.today())}.")
        if note.understood:
            d.show(note.understood)


@command("delete_note", "Delete a note from Remember", ["delete the note about stamps", "forget the note water the plants"],
         [r"(?:delete|remove|forget|clear|drop) (?:the |my )?note (?:about |that says |saying |called )?(?P<name>.+)"],
         typed=[(TIMETABLE, "delnote", "delete_note")], rank=5)
def delete_note(d: Dialog, g):
    # No confirmation, by request: the web app's Undo (and "undo my last change") brings it back.
    with d.app.Session() as s:
        found = N.matching(s, g["name"])
        if not found:
            raise TaskError(f"I couldn't find a note with '{g['name']}'.")
        note = found[0] if len(found) == 1 else d.choose(found, lambda n: N.describe(n, d.today()), "note")
        text = N.delete_note(s, note.id)
        d.say(f"Deleted the note: {text}.")


@command("notes_panel", "Show or hide the Remember notes", ["what do i need to remember", "show my notes", "hide my notes"],
         [r"(?P<show>show|open|read|list)(?: me)? (?:my |the )?(?:notes|remember(?: panel| list)?)",
          r"(?P<hide>hide|close|collapse) (?:my |the )?(?:notes|remember(?: panel| list)?)",
          r"what (?:do i (?:need|have) to|should i) remember"],
         typed=[(TIMETABLE, "notes", "show_notes")], rank=6)
def notes_panel(d: Dialog, g):
    open_ = not g.get("hide")
    d.app.settings.notes_open = open_
    save_settings(d.app.settings_file, d.app.settings)
    if not open_:
        d.say("Notes hidden.")
        return
    with d.app.Session() as s:
        sec = N.sections(s, d.now())
        if not sec.total:
            d.say("You have no notes. Say remember, then what to remember.")
            return
        parts = []
        if sec.overdue:
            parts.append(f"{len(sec.overdue)} overdue: " + "; ".join(N.describe(n, d.today()) for n in sec.overdue[:5]))
        if sec.upcoming:
            parts.append("coming up: " + "; ".join(N.describe(n, d.today()) for n in sec.upcoming[:5]))
        if sec.no_time:
            parts.append("no time: " + "; ".join(n.text for n in sec.no_time[:5]))
        d.say(f"You have {sec.total} note{'s' if sec.total != 1 else ''}. " + ". ".join(parts) + ".")


@command("dismiss_note_banner", "Dismiss the note reminder banners (the notes stay)",
         ["dismiss the note reminder", "hide the note banner"],
         [r"(?:dismiss|hide|close) (?:the )?note (?:reminders?|banners?)"], rank=6)
def dismiss_note_banner(d: Dialog, g):
    with d.app.Session() as s:
        for n in s.scalars(select(N.Note).where(N.Note.banner_open.is_(True))).all():
            N.dismiss_banner(s, n.id)
    if hasattr(d.app, "notes_away"):
        d.app.notes_away = 0
    d.say("Done. The notes stay in Remember until you delete them.")


# ======================= export and import (v1.8) =======================

@command("export_data", "Export all data to a file", ["export my data", "make an export"],
         [r"(?:export|make an export of|save a copy of)(?: all)?(?: of)?(?: my| the)? (?:data|everything)",
          r"make an export"],
         typed=[(SETTINGS, "e", "export_typed")], rank=14)
def export_data_cmd(d: Dialog, g):
    from .. import exporting as EX
    path = EX.write_export(d.app.Session.kw["bind"], d.app.db_path, d.now())
    d.say(f"Exported everything to {path.name}, in the exports folder next to your data.")


@command("import_data", "Import the latest export (replaces all data; backed up first)", ["import my latest export"],
         [r"(?:import|restore|load)(?: from)?(?: my| the)? (?:latest |last |newest )?export"],
         typed=[(SETTINGS, "m", "import_typed")], risky=True, rank=14)
def import_data_cmd(d: Dialog, g):
    import json
    from .. import exporting as EX
    path = EX.latest_export(d.app.db_path)
    if path is None:
        raise TaskError("There's no export yet. Say export my data first.")
    data = EX.check(json.loads(path.read_text(encoding="utf-8")))
    if not d.confirm(f"This replaces all your data with {path.name}: {EX.summary(data)}. "
                     "Your current data is backed up first. Go ahead?"):
        d.say("Nothing was changed.")
        return
    d.say(EX.import_data(d.app.Session.kw["bind"], d.app.db_path, data, d.now()))
