"""Rich terminal UI: the timetable. Only talks to services / tracking /
alarms / reminders; holds no rules itself."""

from __future__ import annotations

import queue
from pathlib import Path
import threading
from collections import deque
from datetime import date, datetime, timedelta
from typing import Callable, Deque, List, Optional, Tuple

from rich.console import Group
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from . import __version__, notes, periods as P, services as svc, tracking as tr
from .alarms import END_CHECK, HEADS_UP, Alarm, AlarmService
from .db import default_db_path, make_session_factory
from .models import PRIORITY_NAMES, Placement, Task, TaskStatus
from . import planner
from . import rescheduler as rs
from .voice import commands as voice_commands  # noqa: F401  (fills the registry)
from .voice import registry as vreg
from .voice.dialog import Dialog, Heard, VoiceState
from .notify import DesktopNotifier
from .reminders import ReminderService
from .ringer import RERUNG, TIMED_OUT, Ringer, key_of
from .settings import (load_settings, save_settings, settings_path, validate_snooze, validate_task_minutes,
                       validate_window)
from .tracking import Missing
from .ui_common import (
    ask_amount, ask_day, ask_duration, ask_text, ask_time, console, goal_line, rollup_line,
)
from .ui_tracking import TrackingScreen

STATUS_STYLE = {
    TaskStatus.PENDING.value: ("pending", "yellow"),
    TaskStatus.DONE.value: ("done", "green"),
    TaskStatus.FAILED.value: ("FAILED", "red"),
    TaskStatus.SKIPPED.value: ("skipped", "magenta"),
}

MENU = (
    "[bold]a[/] add task now   [bold]n[/] enter several tasks   [bold]p[/] plan my day / re-plan   "
    "[bold]e[/] move / set time (pins)   [bold]u[/] unpin\n"
    "[bold]d[/] done   [bold]f[/] fail   [bold]s[/] skip   [bold]x[/] still going (extend)   "
    "[bold]r[/] reschedule a missed task   [bold]z[/] undo last reschedule   [bold]h[/] history of misses\n"
    "[bold]c[/] change a task   [bold]typed[/] keep a title as typed   [bold]del[/] delete a task   [bold]l[/] link task to goal\n"
    "[bold]g[/] day / week / month pages   [bold]t[/] view another day   [bold]o[/] settings\n"
    "[bold]note[/] remember something   [bold]delnote[/] delete a note   [bold]notes[/] all notes\n"
    "[bold]v[/] talk (push-to-talk key)   [bold]m[/] mute / unmute mic   [bold]Enter[/] refresh / answer   [bold]q[/] quit"
)

PLACEMENT_STYLE = {
    Placement.FIXED.value: ("fixed", "cyan"),
    Placement.PINNED.value: ("pinned", "magenta"),
    Placement.AUTO.value: ("auto", "green"),
    Placement.OVERFLOW.value: ("didn't fit", "red"),
}
PRIORITY_STYLE = {1: "bold red", 2: "yellow", 3: "", 4: "dim"}


# ---------- rendering ----------

def _time_cell(t: Task) -> Text:
    dur = svc.format_duration(t.duration_min)
    cell = Text(dur if t.start_at is None else f"{t.start_at:%H:%M}-{t.end_at:%H:%M}\n{dur}")
    if t.placement in PLACEMENT_STYLE:
        label, style = PLACEMENT_STYLE[t.placement]
        cell.append(f"\n{label}", style=style)
    elif t.start_at is None and t.status == TaskStatus.PENDING.value:
        cell.append("\nnot planned", style="dim")
    return cell


def _priority_cell(t: Task) -> Text:
    return Text(PRIORITY_NAMES.get(t.priority, str(t.priority)), style=PRIORITY_STYLE.get(t.priority, ""))


def _task_table(tasks: List[Task], title: str, show_date: bool = False) -> Table:
    table = Table(title=title, title_justify="left", expand=True, show_lines=False)
    table.add_column("ID", justify="right", style="cyan", no_wrap=True)
    if show_date:
        table.add_column("Date", no_wrap=True)
    table.add_column("Task")
    table.add_column("Priority", no_wrap=True)
    table.add_column("Goal", style="dim")
    table.add_column("Time", justify="right", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    for t in tasks:
        label, style = STATUS_STYLE[t.status]
        task_cell = Text(t.title)
        if t.purpose:
            task_cell.append(f"\n→ {t.purpose}", style="dim italic")
        if t.move_reason and t.status == TaskStatus.PENDING.value:
            task_cell.append(f"\n↻ {t.move_reason}", style="yellow")
        elif t.plan_reason and t.status == TaskStatus.PENDING.value:
            task_cell.append(f"\nplan: {t.plan_reason}", style="dim green")
        if t.rescheduled_from_id:
            task_cell.append(f"\nrescheduled copy of task {t.rescheduled_from_id} "
                             f"(rescheduled {t.reschedule_count}x)", style="dim yellow")
        for c in t.rescheduled_copies:
            when = f"{c.planned_for:%a %d %b} {c.start_at:%H:%M}" if c.start_at else f"{c.planned_for:%a %d %b}, unplaced"
            task_cell.append(f"\n→ rescheduled as task {c.id} ({when})", style="dim yellow")
        if t.latest_reason:
            task_cell.append(f"\nwhy: {t.latest_reason}", style=style)
        row = [str(t.id)]
        if show_date:
            row.append(t.planned_for.isoformat())
        row += [task_cell, _priority_cell(t), t.goal.title if t.goal else "", _time_cell(t), Text(label, style=style)]
        table.add_row(*row)
    if not tasks:
        table.add_row(*([""] * (7 if show_date else 6)))
    return table


def _overflow_table(tasks: List[Task], title: str = "Didn't fit / unplaced (still on the day, no time)") -> Table:
    table = Table(title=title, title_justify="left", expand=True, border_style="red")
    table.add_column("ID", justify="right", style="cyan", no_wrap=True)
    table.add_column("Day", no_wrap=True)
    table.add_column("Task")
    table.add_column("Priority", no_wrap=True)
    table.add_column("Duration", justify="right", no_wrap=True)
    for t in tasks:
        table.add_row(str(t.id), f"{t.planned_for:%a %d %b}", t.title, _priority_cell(t),
                      svc.format_duration(t.duration_min))
    return table


def ask_priority(label: str = "Priority") -> int:
    while True:
        raw = Prompt.ask(f"{label} [1 urgent / 2 high / 3 normal / 4 low]", default="3", show_default=False)
        try:
            return svc.parse_priority(raw)
        except svc.TaskError as e:
            console.print(f"[red]{e}[/]")


def _summary(tasks: List[Task]) -> str:
    planned = sum(t.duration_min for t in tasks)
    done = sum(t.duration_min for t in tasks if t.status == TaskStatus.DONE.value)
    return f"planned {svc.format_duration(planned) if planned else '0m'}, done {svc.format_duration(done) if done else '0m'}"


def _alarm_style(alarm: Alarm) -> str:
    return "yellow" if alarm.kind == HEADS_UP else "bold red"


def _missing_panel(missing: List[Missing]) -> Panel:
    lines = Text()
    for m in missing:
        lines.append(f"{m.message}\n", style="bold red")
    lines.append("Press g to fill them in. Each one is reminded once; this list stays until they're filled in.", style="dim")
    return Panel(lines, title="Fill in your plan", title_align="left", border_style="red")


class App:
    def __init__(self, db_path=None, notifier=None, clock: Callable[[], datetime] = datetime.now, player=None):
        self.db_path = db_path or default_db_path()
        self.clock = clock
        self.Session = make_session_factory(self.db_path)
        self.settings_file = settings_path(self.db_path)
        self.settings = load_settings(self.settings_file)
        self.notifier = notifier if notifier is not None else DesktopNotifier()
        self.ringer = Ringer(player=player, snooze_minutes=lambda: self.settings.snooze_minutes,
                             clock=clock, on_event=self._on_ring_event)
        self.alarms = AlarmService(self.Session, self.notifier, on_alarm=self._on_alarm, clock=clock)
        self.reminders = ReminderService(self.Session, self.notifier, on_reminder=self._on_reminder, clock=clock)
        self.notes = notes.NoteService(self.Session, self._on_notes_due, clock=clock)
        self.notes_away = 0           # notes that became overdue while tomits wasn't running
        self.checkins: "queue.Queue[Alarm]" = queue.Queue()
        self.triggers: List[Tuple] = []  # ("closed", task_id, None) or ("overrun", task_id, new_end)
        # v1.5 voice
        self.voice_state = VoiceState()
        self.voice_io = None          # created on first use
        self.voice_error: Optional[str] = None
        self.voice_mode = False       # last input was voice: answer prompts by voice too
        self.pending_reminder: Optional[List[Missing]] = None
        self.quit_requested = False
        # v1.5.1: transcript log and understanding (rules + optional local model)
        from .voice.voicelog import VoiceLog
        self.voice_log = VoiceLog(Path(self.db_path).parent / "voice_log.db")
        self.understanding = self._make_understanding()
        self.recent: Deque[Tuple[datetime, Alarm]] = deque(maxlen=5)
        self._recent_lock = threading.Lock()

    def today(self) -> date:
        return self.clock().date()

    # ----- alarms and reminders (called from background threads) -----

    def _on_alarm(self, alarm: Alarm) -> None:
        """A live alarm went off: it starts ringing until dismissed or snoozed."""
        with self._recent_lock:
            self.recent.appendleft((datetime.now(), alarm))
        self.ringer.ring(alarm)
        console.print(f"\n[{_alarm_style(alarm)}]ALARM: {alarm.message}[/] "
                      "[bold]Ringing: press Enter to dismiss or snooze.[/]")

    def _on_ring_event(self, event: str, alarm: Alarm) -> None:
        """From the ringer thread: a snooze is over, or 2 minutes passed."""
        if event == RERUNG:
            console.print(f"\n[{_alarm_style(alarm)}]ALARM (snoozed): {alarm.message}[/] "
                          "[bold]Ringing: press Enter to dismiss or snooze.[/]")
        elif event == TIMED_OUT:
            console.print(f"\n[dim]Alarm stopped ringing after 2 minutes: {alarm.message}[/]")
            self._after_ringing(alarm)

    def _after_ringing(self, alarm: Alarm) -> None:
        """Once an end-of-task alarm stops ringing, ask whether it was done."""
        if alarm.kind == END_CHECK:
            self.checkins.put(alarm)

    def process_ringing(self) -> None:
        """Offer Dismiss / Snooze for each ringing alarm."""
        for r in self.ringer.ringing():
            alarm = r.alarm
            now = self.clock()
            info = Text(alarm.message + "\n", style=_alarm_style(alarm))
            info.append(f"Stops by itself in {r.seconds_left(now)} s.", style="dim")
            if self.ringer.sound_error:
                info.append(f"\n{self.ringer.sound_error}. The alarm is still on, shown here.", style="bold red")
            console.print(Panel(info, title="ALARM RINGING", border_style="bold red"))
            minutes = self.settings.snooze_minutes
            try:
                choice = Prompt.ask(f"[bold]d[/]ismiss / [bold]z[/] snooze {minutes} min",
                                    choices=vreg.typed_keys(vreg.ALARM), show_choices=False)
            except KeyboardInterrupt:
                choice = "d"
            if choice == "z":
                try:
                    due = self.ringer.snooze(key_of(alarm))
                    console.print(f"[yellow]Snoozed. Rings again at {due:%H:%M}.[/]")
                except KeyError:
                    console.print("[dim]It had already stopped.[/]")
                    self._after_ringing(alarm)
            else:
                if self.ringer.dismiss(key_of(alarm)) is not None:
                    console.print("[green]Dismissed.[/]")
                self._after_ringing(alarm)

    def attend(self) -> None:
        """Handle anything waiting for an answer: ringing alarms, reschedule
        proposals, then check-ins. After a voice turn these are answered by
        voice too (same logic calls)."""
        if self.voice_mode and self._voice() is not None:
            self.voice_attend()
            return
        self.process_ringing()
        self.process_triggers()
        self.process_checkins()

    # ----- voice (v1.5) -----

    def _make_understanding(self):
        from .voice.nlu import OllamaBackend, Understanding
        backend = OllamaBackend(self.settings.llm_model) if self.settings.llm_enabled else None
        return Understanding(backend)

    def voice_names(self):
        """Current task and goal names, given to the model and used for matching."""
        today = self.today()
        with self.Session() as s:
            tasks = [t.title for t in s.query(Task).filter(Task.status == TaskStatus.PENDING.value).all()
                     if today - timedelta(days=7) <= t.planned_for <= today + timedelta(days=1)]
            goals = [g.title for g in tr.open_goals(s, today)]
        return sorted(set(tasks)), sorted(set(goals))

    def voice_hint(self) -> str:
        """Spelling hint for Whisper: command words plus your task and goal names."""
        tasks, goals = self.voice_names()
        hint = ("tomits: add a task, mark done, failed, skip, plan my day, re-plan, move, push to tomorrow, "
                "still going, snooze, dismiss, goal, sacrifice, review, process. ")
        if tasks:
            hint += "Tasks: " + ", ".join(tasks[:25]) + ". "
        if goals:
            hint += "Goals: " + ", ".join(goals[:15]) + "."
        return hint[:700]

    def _voice(self):
        """The VoiceIO, or None (with self.voice_error set) if voice can't run."""
        if self.voice_io is not None:
            return self.voice_io
        from .voice.engine import VoiceIO, VoiceUnavailable, WhisperRecognizer, WindowsSpeaker
        try:
            rec = WhisperRecognizer(self.settings.stt_model, self.settings.input_device, self.voice_hint)
        except VoiceUnavailable as e:
            self.voice_error = f"Voice isn't available: {e} Using typed input."
            return None
        self.voice_io = VoiceIO(self, rec, WindowsSpeaker(), console,
                                lambda prompt: Heard(Prompt.ask(prompt or "you", default="", show_default=False), 1.0))
        self.voice_error = None
        return self.voice_io

    def dialog(self, io=None) -> Dialog:
        return Dialog(self, io or self._voice(), self.voice_state)

    def voice_turn(self, io=None) -> Optional[str]:
        """One spoken command (push-to-talk key or wake phrase)."""
        io = io or self._voice()
        if io is None:
            # never silent: say why, then take the same command typed
            from .voice.engine import TypedIO
            console.print(f"[red]{self.voice_error}[/] [dim]Type the command in words instead (blank = cancel).[/]")
            io = TypedIO(console, lambda label: Prompt.ask(label, default="", show_default=False))
            heard = io.listen(None)
            if not heard.text.strip():
                return None
            return Dialog(self, io, self.voice_state).handle(heard)
        self.voice_mode = True
        heard = io.listen(None)
        return Dialog(self, io, self.voice_state).handle(heard)

    def voice_attend(self, io=None) -> None:
        d = self.dialog(io)
        from .voice.commands import run_proposal, voice_checkin, voice_ringing
        try:
            voice_ringing(d)
            while self.triggers:
                run_proposal(d, self.triggers.pop(0))
            while not self.checkins.empty():
                voice_checkin(d, self.checkins.get_nowait())
            if self.pending_reminder:
                missing, self.pending_reminder = self.pending_reminder, None
                if d.confirm("Reminder: " + "; ".join(m.message for m in missing) + ". Fill it in now?"):
                    d.handle(Heard("fill in my plan"))
        except svc.TaskError as e:
            d.say(f"I can't do that. {e}")
        except Exception as e:  # never fail silently
            console.print(f"[red]Voice error: {e}. Back to typed input.[/]")
            self.voice_mode = False

    def hands_free(self, io=None) -> None:
        """Hands-free: listen for the wake phrase until a key is pressed."""
        from .voice.engine import keyboard_pressed
        io = io or self._voice()
        if io is None:
            console.print(f"[red]{self.voice_error}[/]")
            return
        self.voice_mode = True
        console.print(f"[bold white on blue] HANDS-FREE [/] Say '{self.settings.wake_phrase}' then a command. "
                      "Press any key to type instead.")
        wake = self.settings.wake_phrase.lower()
        while self.settings.hands_free and not self.quit_requested and not keyboard_pressed():
            self.voice_attend(io)
            if self.settings.muted:
                return
            heard = io.rec.listen([wake], max_seconds=4, start_timeout=4) if hasattr(io, "rec") else io.listen(None)
            if wake in (heard.text or "").lower():
                self.voice_turn(io)
                self.dashboard()

    def after_close(self, task_id: int) -> None:
        """After a fail / skip (typed or voice): no alarms for the record."""
        from .alarms import END_CHECK as _E, HEADS_UP as _H
        for kind in (_H, _E):
            self.ringer.dismiss((kind, task_id))

    def after_accept(self, prop) -> None:
        """After a reschedule is accepted (typed or voice)."""
        from .alarms import END_CHECK as _E, HEADS_UP as _H
        for m in prop.moves:  # drop ringing / snoozed alarms that belonged to the old times
            if m.task_id:
                for kind in (_H, _E):
                    self.ringer.dismiss((kind, m.task_id))

    # ----- rescheduling -----

    def process_triggers(self) -> None:
        while self.triggers:
            trigger = self.triggers.pop(0)
            try:
                with self.Session() as s:
                    self._run_trigger(s, trigger)
            except KeyboardInterrupt:
                console.print("\n[yellow]Proposal skipped. Nothing was changed.[/]")
            except svc.TaskError as e:
                console.print(f"[red]{e}[/]")

    def _build(self, s, trigger, choice=None):
        return rs.build(s, trigger, self.settings.window, now=self.clock(), choice=choice)

    def _run_trigger(self, s, trigger) -> None:
        prop = self._build(s, trigger)
        if prop.cap_reached and prop.choice is None:
            console.print(Panel(Text(f"'{prop.title}' has now been rescheduled {prop.chain_count} times.",
                                     style="bold yellow"), title="Reschedule limit", border_style="yellow"))
            choice = Prompt.ask("[bold]k[/]eep rescheduling / s[bold]p[/]lit it in two / [bold]d[/]rop it",
                                choices=vreg.typed_keys(vreg.CAP), show_choices=False)
            prop = self._build(s, trigger, {"k": "keep", "p": "split", "d": "drop"}[choice])
            if prop.choice == "drop":
                console.print(f"[yellow]Dropped. Task {prop.task_id} stays {prop.trigger} with its reason; "
                              "no new copy.[/]")
                return
        if prop.collisions:
            lines = Text(f"'{prop.title}' running until {prop.requested_end:%H:%M} would run into:\n", style="bold")
            for c in prop.collisions:
                lines.append(f"  {c.message}\n", style="red")
            lines.append("That task isn't moved.", style="dim")
            console.print(Panel(lines, title="Warning", border_style="red"))
            choice = Prompt.ask(
                f"[bold]s[/]horten to end at {prop.collisions[0].start:%H:%M} / "
                f"[bold]m[/]ove the rest after it / [bold]l[/]eave it, I'll sort it out",
                choices=vreg.typed_keys(vreg.COLLISION), show_choices=False)
            if choice == "l":
                console.print("[dim]Left as it is. Nothing was changed.[/]")
                return
            prop = self._build(s, trigger, {"s": "shorten", "m": "continue"}[choice])
        self._show_proposal(prop)
        if not prop.moves:
            console.print("[dim]Nothing to move.[/]")
            return
        if not Confirm.ask("Accept this plan?", default=True):
            msg = "Nothing was changed."
            if prop.trigger in ("failed", "skipped"):
                msg += f" Task {prop.task_id} stays {prop.trigger} with its reason; press r to reschedule it later."
            console.print(f"[yellow]{msg}[/]")
            return
        rs.accept(s, prop, now=self.clock())
        self.after_accept(prop)
        console.print("[green]Plan updated.[/] Undo with [bold]z[/].")

    def _show_proposal(self, prop) -> None:
        table = Table(title=f"Proposed changes: {prop.summary}", title_justify="left", expand=True)
        table.add_column("What", no_wrap=True)
        table.add_column("Task")
        table.add_column("Priority", no_wrap=True)
        table.add_column("From", no_wrap=True)
        table.add_column("To", no_wrap=True)
        table.add_column("Why")
        for m in prop.placed:
            src = f"{m.from_day:%a} {m.from_start:%H:%M}" if m.from_start else "no time"
            if m.kind == "extend":
                end = (datetime.combine(m.to_day, m.to_start) + timedelta(minutes=m.new_duration))
                dst = f"until {end:%H:%M}"
            else:
                end = datetime.combine(m.to_day, m.to_start) + timedelta(minutes=m.duration)
                dst = f"{m.to_day:%a} {m.to_start:%H:%M}-{end:%H:%M}"
            what = {"copy": "new copy", "shift": "move", "extend": "extend", "claim": "fixed time"}[m.kind]
            table.add_row(what, m.title, Text(PRIORITY_NAMES.get(m.priority, "")), src, dst, Text(m.reason, style="dim"))
        console.print(table)
        if prop.unplaced:
            ut = Table(title="Unplaced (no room today or tomorrow)", title_justify="left", expand=True, border_style="red")
            ut.add_column("Task")
            ut.add_column("Priority", no_wrap=True)
            ut.add_column("Duration", justify="right", no_wrap=True)
            for m in prop.unplaced:
                ut.add_row(m.title, PRIORITY_NAMES.get(m.priority, ""), svc.format_duration(m.duration))
            console.print(ut)

    def still_going(self) -> None:
        task_id = self._ask_task_id("mark as still going")
        if task_id is None:
            return
        with self.Session() as s:
            task = svc.get_task(s, task_id)
            self._ask_overrun(task)

    def _ask_overrun(self, task: Task) -> None:
        if task.start_at is None:
            raise svc.TaskError(f"Task {task.id} has no time, so it can't run over.")
        while True:
            raw = (Prompt.ask(f"'{task.title}' ends {task.end_at:%H:%M}. New end time, or minutes to add",
                              default="", show_default=False) or "").strip()
            if not raw:
                console.print("[dim]Cancelled.[/]")
                return
            try:
                if raw.isdigit() and len(raw) <= 3:
                    new_end = task.end_at + timedelta(minutes=int(raw))
                else:
                    new_end = datetime.combine(task.planned_for, svc.parse_time(raw))
                break
            except svc.TaskError as e:
                console.print(f"[red]{e}[/]")
        self.triggers.append(("overrun", task.id, new_end))
        console.print("[yellow]A reschedule proposal will follow.[/]")

    def reschedule_again(self) -> None:
        task_id = self._ask_task_id("reschedule (failed or skipped)")
        if task_id is not None:
            self.triggers.append(("closed", task_id, None))

    def undo_reschedule(self) -> None:
        with self.Session() as s:
            log = rs.last_log(s)
            if log is None or log.undone:
                raise svc.TaskError("There's no reschedule to undo.")
            if Confirm.ask(f"Undo the reschedule from {log.created_at:%H:%M} ({log.trigger})?", default=True):
                rs.undo_last(s)
                console.print("[green]Undone. The previous plan is back; failure reasons are kept.[/]")

    def history(self) -> None:
        with self.Session() as s:
            raw = Prompt.ask("Goal ID (blank = all goals)", default="", show_default=False).strip()
            goal_id = int(raw) if raw else None
            start = self._ask_date("From (blank = 30 days ago)", self.today() - timedelta(days=30))
            end = self._ask_date("To (blank = today)", self.today())
            rows = rs.reason_history(s, goal_id, start, end)
            self.render_history(rows, start, end)

    def render_history(self, rows, start: date, end: date) -> None:
        if True:
            table = Table(title=f"Failed and skipped, {start:%d %b} - {end:%d %b}", title_justify="left", expand=True)
            for col in ("Date", "Task", "Status", "Priority", "Goal", "Reason", "Rescheduled as"):
                table.add_column(col)
            for r in rows:
                copies = r.task.rescheduled_copies if r.task else []
                resched = ", ".join(
                    f"task {c.id} ({c.planned_for:%a %d %b}{' ' + c.start_at.strftime('%H:%M') if c.start_at else ', unplaced'}, {c.status})"
                    for c in copies) or "-"
                table.add_row(f"{r.task_date:%a %d %b}" if r.task_date else "", r.task_title or "", r.status,
                              PRIORITY_NAMES.get(r.priority, ""), r.goal_title or "", r.reason, resched)
            if not rows:
                table.add_row("", "[dim]Nothing in this range.[/]", "", "", "", "", "")
            console.print(table)

    def _ask_date(self, label: str, default: date) -> date:
        from .ui_common import parse_day
        while True:
            raw = Prompt.ask(label, default="", show_default=False)
            if not raw.strip():
                return default
            try:
                return parse_day(raw, self.today())
            except svc.TaskError as e:
                console.print(f"[red]{e}[/]")

    def _on_reminder(self, missing: List[Missing]) -> None:
        self.pending_reminder = missing  # answered by voice at the next turn if voice is in use
        console.print("\n[bold red]REMINDER:[/] " + "; ".join(m.message for m in missing) +
                      ". Press g to fill in, or say 'fill in my plan'.")

    def show_missed(self, missed: List[Alarm]) -> None:
        if not missed:
            return
        table = Table(expand=True, show_header=True)
        table.add_column("ID", justify="right", style="cyan", no_wrap=True)
        table.add_column("What happened")
        for a in missed:
            table.add_row(str(a.task_id), Text(a.message, style=_alarm_style(a)))
        console.print(Panel(table, title="Missed while tomits was closed", border_style="red"))
        console.print("Open tasks stay on the dashboard; close them with d, f or s.")
        Prompt.ask("[dim]Press Enter to continue[/]", default="", show_default=False)

    def process_checkins(self) -> None:
        """Ask about each task whose planned time is up."""
        while True:
            try:
                alarm = self.checkins.get_nowait()
            except queue.Empty:
                return
            with self.Session() as s:
                task = s.get(Task, alarm.task_id)
                if task is None or task.status != TaskStatus.PENDING.value:
                    continue
                console.print(Panel(Text(alarm.message), title="Check-in", border_style="red"))
                try:
                    choice = Prompt.ask(
                        "[bold]d[/]one / still [bold]g[/]oing / [bold]f[/]ailed / [bold]s[/]kipped / [bold]l[/]ater",
                        choices=vreg.typed_keys(vreg.CHECKIN), default="l", show_choices=False,
                    )
                    if choice == "d":
                        self._complete(s, task.id)
                    elif choice == "g":
                        self._ask_overrun(task)
                    elif choice in ("f", "s"):
                        status = TaskStatus.FAILED if choice == "f" else TaskStatus.SKIPPED
                        self._close_interactively(s, task, status)
                    else:
                        console.print("[dim]Left open. It stays on the dashboard.[/]")
                except KeyboardInterrupt:
                    console.print("\n[yellow]Left open.[/]")
                except svc.TaskError as e:
                    console.print(f"[red]{e}[/]")

    # ----- screens -----

    def dashboard(self) -> None:
        today = self.today()
        with self.Session() as s:
            tasks = svc.tasks_for_day(s, today)
            overdue = svc.overdue_tasks(s, today)
            parts = []
            if self.triggers:
                parts.append(Panel(Text(f"{len(self.triggers)} reschedule proposal(s) waiting. Press Enter to see them.",
                                        style="bold yellow"), border_style="yellow"))
            ringing = self.ringer.ringing()
            if ringing:
                lines = Text()
                for r in ringing:
                    lines.append(f"{r.alarm.message}\n", style="bold red")
                lines.append("Press Enter to dismiss or snooze.", style="bold")
                parts.append(Panel(lines, title="ALARM RINGING", title_align="left", border_style="bold red"))
            snoozed = self.ringer.snoozed()
            if snoozed:
                parts.append(Text("Snoozed: " + "; ".join(f"'{r.alarm.title}' rings again at {due:%H:%M}"
                                                          for r, due in snoozed), style="yellow"))
            if self.ringer.sound_error:
                parts.append(Text(f"{self.ringer.sound_error}. Alarms still show here.", style="bold red"))
            from .reminders import active_reminders
            missing = active_reminders(s, today)  # v1.6: dismissed items stay hidden
            if missing:
                parts.append(_missing_panel(missing))
            note_panel = self._notes_panel(s)
            if note_panel is not None:
                parts.append(note_panel)
            parts.append(_task_table(tasks, f"Today, {today:%a %d %b}  ({_summary(tasks)})"))
            overflow = planner.overflow_tasks(s, today) + planner.overflow_tasks(s, today + timedelta(days=1))
            if overflow:
                overflow.sort(key=lambda t: (t.priority, t.planned_for, t.id))
                parts.append(_overflow_table(overflow))
            if overdue:
                parts.append(_task_table(overdue, "[red]Overdue, still open[/]", show_date=True))
            with self._recent_lock:
                recent = list(self.recent)
            if recent:
                lines = Text()
                for when, a in recent:
                    lines.append(f"{when:%H:%M}  {a.message}\n", style=_alarm_style(a))
                parts.append(Panel(lines, title="Recent alarms", title_align="left", border_style="yellow"))
            if self.voice_error:
                parts.append(Text(self.voice_error, style="yellow"))
            if self.settings.muted:
                parts.append(Text("Microphone muted (m to unmute).", style="yellow"))
            for err in (self.alarms.last_error, self.reminders.last_error, getattr(self.notifier, "last_error", None)):
                if err:
                    parts.append(Text(err, style="dim red"))
            console.clear()
            console.print(Panel(Group(*parts), title=f"tomits v{__version__}", subtitle=str(self.db_path), border_style="blue"))
            console.print(MENU)

    # ----- Remember (notes, v1.8): logic in notes.py -----

    def _on_notes_due(self, due) -> None:
        """A note's time arrived: one line here and one desktop notification (only once)."""
        for n in due:
            console.print(f"\n[bold magenta]REMEMBER:[/] {n.text} ({n.due_at:%H:%M}).")
            self.notifier.notify("tomits: remember", n.text)

    def _notes_panel(self, s):
        sec = notes.sections(s, self.clock())
        banners = [n for n in sec.overdue if n.banner_open]
        if not sec.total and not self.notes_away:
            return None
        lines = Text()
        if self.notes_away:
            lines.append(f"{self.notes_away} note{'s' if self.notes_away != 1 else ''} became overdue while you were "
                         "away.\n", style="bold magenta")
        for n in banners:
            lines.append(f"Now: {n.text}\n", style="bold magenta")
        for label, items, style in (("Overdue", sec.overdue, "dim"), ("Upcoming", sec.upcoming, ""),
                                    ("No time", sec.no_time, "")):
            for n in items[:4]:
                when = f"{n.due_at:%a %d %b %H:%M}  " if n.due_at else ""
                lines.append(f"{label}: {when}{n.text}" + ("  (past)" if label == "Overdue" else "") + "\n", style=style)
        more = sec.total - sum(min(4, len(x)) for x in (sec.overdue, sec.upcoming, sec.no_time))
        if more > 0:
            lines.append(f"... and {more} more (type notes)\n", style="dim")
        title = f"Remember ({sec.total}" + (f", {len(sec.overdue)} overdue" if sec.overdue else "") + ")"
        return Panel(lines, title=title, title_align="left", border_style="magenta")

    def add_note(self) -> None:
        with self.Session() as s:
            text = ask_text(f"Note (up to {notes.MAX_TEXT} characters)")
            raw = Prompt.ask("Date and time (optional; or write the time in the note)", default="",
                             show_default=False).strip()
            due = None
            if raw:
                try:
                    due = datetime.fromisoformat(raw.replace(" ", "T") if len(raw) > 10 else raw + "T09:00")
                except ValueError:
                    raise svc.TaskError(f"Can't read the date and time {raw!r}. Try 2026-10-05 17:30.") from None
            color = Prompt.ask("Colour", choices=list(notes.COLORS), default=notes.DEFAULT_COLOR)
            ampm = None
            while True:
                try:
                    note = notes.add_note(s, text, due, color, now=self.clock(), window=self.settings.window, ampm=ampm)
                    break
                except svc.AmbiguousTime as e:
                    ampm = self._ask_ampm(e)
            console.print(f"[green]Note added: {notes.describe(note, self.today())}.[/]")
            if note.understood:
                console.print(f"[cyan]{note.understood}[/]")

    def delete_note(self) -> None:
        with self.Session() as s:
            all_notes = notes.sections(s, self.clock())
            listed = all_notes.overdue + all_notes.upcoming + all_notes.no_time
            if not listed:
                console.print("No notes.")
                return
            for i, n in enumerate(listed, 1):
                console.print(f"  {i}. {notes.describe(n, self.today())}")
            raw = Prompt.ask("Number of the note to delete (blank = cancel)", default="", show_default=False).strip()
            if not raw:
                return
            if not raw.isdigit() or not 1 <= int(raw) <= len(listed):
                raise svc.TaskError("Enter a number from the list.")
            text = notes.delete_note(s, listed[int(raw) - 1].id)
            console.print(f"[green]Deleted the note: {text}.[/]")

    def show_notes(self) -> None:
        with self.Session() as s:
            sec = notes.sections(s, self.clock())
            for label, items in (("Overdue", sec.overdue), ("Upcoming", sec.upcoming), ("No time", sec.no_time)):
                console.print(f"[bold]{label}[/] ({len(items)})")
                for n in items:
                    when = f"{n.due_at:%a %d %b %H:%M}  " if n.due_at else ""
                    console.print(f"  {when}{n.text}" + ("  [dim](past)[/]" if label == "Overdue" else ""))
            if not sec.total:
                console.print("Nothing to remember yet. Type note to add one.")
            open_banners = [n for n in sec.overdue if n.banner_open]
            if (open_banners or self.notes_away) and Confirm.ask("Dismiss the note reminders? (the notes stay)",
                                                                 default=True):
                for n in open_banners:
                    notes.dismiss_banner(s, n.id)
                self.notes_away = 0

    # ----- export and import (v1.8): logic in exporting.py -----

    def export_typed(self) -> None:
        from . import exporting
        path = exporting.write_export(self.Session.kw["bind"], self.db_path, self.clock())
        console.print(f"[green]Exported everything to {path}[/]")

    def import_typed(self) -> None:
        import json
        from . import exporting
        latest = exporting.latest_export(self.db_path)
        raw = Prompt.ask("Export file to import" + (f" (blank = {latest.name})" if latest else ""), default="",
                         show_default=False).strip().strip('"')
        path = Path(raw) if raw else latest
        if path is None or not path.exists():
            raise svc.TaskError("There's no such export file.")
        data = exporting.check(json.loads(path.read_text(encoding="utf-8")))
        console.print(f"This replaces ALL your data with {path.name}: {exporting.summary(data)}. "
                      "Your current data is backed up first.")
        if Prompt.ask("Type IMPORT to go ahead", default="", show_default=False).strip() != "IMPORT":
            console.print("[yellow]Nothing was changed.[/]")
            return
        console.print(f"[green]{exporting.import_data(self.Session.kw['bind'], self.db_path, data, self.clock())}[/]")

    def _pick_goal(self, s, allow_unlink: bool = False) -> Optional[int]:
        """Pick an existing goal from an open period. Goals can't be created here."""
        goals = tr.open_goals(s, self.today())
        if not goals:
            console.print("[dim]No open goals to link to. Goals are created on the tracking pages (g).[/]")
            return None
        console.print("Open goals:")
        for g in goals:
            console.print("  " + goal_line(g))
        hint = "blank = none" + (", '-' = unlink" if allow_unlink else "")
        raw = Prompt.ask(f"Goal ID ({hint})", default="", show_default=False).strip()
        if not raw or raw == "-":
            return None
        try:
            goal_id = int(raw)
        except ValueError:
            raise svc.TaskError("Enter a goal ID from the list.") from None
        tr.check_task_goal(s, goal_id, self.today())
        return goal_id

    # ----- actions -----

    # ----- a time written in a title (v1.7): read in the logic layer -----

    def _title_rules(self) -> dict:
        return dict(now=self.clock(), window=self.settings.window, default_minutes=self.settings.default_task_minutes)

    def _read_title(self, title: str, day: date, line: Optional[int] = None):
        """(what the title says, am/pm answer). Asks am or pm when the day
        window can't settle it."""
        ampm = None
        while True:
            try:
                rules = self._title_rules()
                tt = svc.read_title_time(title, None, day, self.today(), rules["window"], rules["default_minutes"],
                                         ampm, rules["now"], line)
                return tt, ampm
            except svc.AmbiguousTime as e:
                ampm = self._ask_ampm(e)

    def _ask_ampm(self, e) -> str:
        console.print(f"[yellow]{e.question}[/]")
        pick = Prompt.ask(" / ".join(f"[bold]{v[0]}[/] {label}" for label, v in e.choices), choices=["a", "p"],
                          show_choices=False)
        return "am" if pick == "a" else "pm"

    def _claiming(self, s, fn):
        """Run a change that gives a task its own time. If planner-placed tasks
        are in the way, show the v1.4 proposal to move them (nothing is saved
        unless accepted). am / pm questions are asked and the change retried."""
        ampm = None
        while True:
            try:
                return fn(ampm)
            except svc.AmbiguousTime as e:
                ampm = self._ask_ampm(e)
            except svc.SlotTaken as e:
                console.print(f"[yellow]{e}[/]")
                self._run_trigger(s, ("claim", e.claim, None))
                if e.claim.understood:
                    console.print(f"[cyan]{e.claim.understood}[/]")
                return None

    def _understood(self, task) -> None:
        if task is not None and getattr(task, "understood", None):
            console.print(f"[cyan]{task.understood}[/] [dim](type [bold]typed[/] to keep the title as typed)[/]")

    def add_now(self) -> None:
        with self.Session() as s:
            title = ask_text("Task title")
            tt, _ = self._read_title(title, self.today())
            if tt is not None:
                console.print(f"[dim]Time in the title: {tt.start:%H:%M}, {svc.format_duration(tt.minutes)}"
                              f"{'' if tt.day == self.today() else f', {tt.day:%a %d %b}'}.[/]")
                raw = Prompt.ask(f"Duration (blank = {svc.format_duration(tt.minutes)})", default="",
                                 show_default=False).strip()
                duration = svc.parse_duration(raw) if raw else None
            else:
                duration = ask_duration()
            priority = ask_priority()
            start = None if tt is not None else self._ask_free_time(
                s, title, self.today(), duration, "Start time (optional, else plan it with p)")
            purpose = ask_text("Task goal: what does done look like? (optional)", required=False)
            goal_id = self._pick_goal(s)
            task = self._claiming(s, lambda ampm: svc.add_task(
                s, title, duration, goal_id, purpose, planned_for=self.today(), start_time=start, today=self.today(),
                priority=priority, ampm=ampm, **self._title_rules()))
            if task is None:
                return
            when = f" at {task.start_at:%H:%M}" if task.start_at else ""
            day = "today" if task.planned_for == self.today() else f"{task.planned_for:%a %d %b}"
            console.print(f"[green]Added task {task.id} for {day}{when}.[/]")
            self._understood(task)

    def keep_typed_title(self) -> None:
        task_id = self._ask_task_id("keep the title as typed for")
        if task_id is None:
            return
        with self.Session() as s:
            task = svc.restore_typed_title(s, task_id)
            console.print(f"[green]Task {task_id} is '{task.title}' again, with no time; the planner places it.[/]")

    def plan(self) -> None:
        with self.Session() as s:
            day = ask_day(self.today())
            existing = svc.tasks_for_day(s, day)
            console.print(f"Planning [bold]{day:%a %d %b}[/]. {len(existing)} task(s) already there. "
                          "Leave the title blank to finish.")
            drafts: List[svc.TaskDraft] = []
            while True:
                title = Prompt.ask(f"Task {len(drafts) + 1} title", default="", show_default=False).strip()
                if not title:
                    break
                tt, ampm = self._read_title(title, day, len(drafts))
                if tt is not None:
                    console.print(f"[dim]{tt.line}[/]")
                    raw = Prompt.ask(f"Duration (blank = {svc.format_duration(tt.minutes)})", default="",
                                     show_default=False).strip()
                    duration = svc.parse_duration(raw) if raw else None
                else:
                    duration = ask_duration()
                priority = ask_priority()
                purpose = ask_text("Task goal (optional)", required=False)
                goal_id = self._pick_goal(s)
                drafts.append(svc.TaskDraft(title, duration, goal_id, purpose, priority=priority, ampm=ampm))
                total = sum(d.duration_min or (tt.minutes if tt else 0) for d in drafts)
                console.print(f"[dim]Plan so far: {len(drafts)} task(s), {svc.format_duration(total)}[/]")
            if not drafts:
                console.print("Nothing planned.")
                return
            start = None
            if any(d.duration_min is None for d in drafts):
                console.print("[dim]Tasks with a time in their title keep it; the others are placed by p.[/]")
            else:
                while True:
                    start = ask_time("Start time of the first task (optional; blank = let the planner place them)")
                    if start is None:
                        break
                    try:
                        timed = svc.schedule_back_to_back(day, drafts, start)
                        svc.check_plan_overlaps(s, day, timed)
                        drafts = timed
                        break
                    except svc.TaskError as e:
                        console.print(f"[red]{e}[/]")
            if start is not None:
                for d in drafts:
                    end = (datetime.combine(day, d.start_time) + timedelta(minutes=d.duration_min)).time()
                    console.print(f"  {svc.format_time(d.start_time)}-{svc.format_time(end)}  {d.title}")
            if Confirm.ask(f"Save {len(drafts)} task(s) to {day:%d %b}?", default=True):
                tasks = svc.plan_day(s, day, drafts, today=self.today(), **self._title_rules())
                console.print("[green]Day planned.[/]")
                for t in tasks:
                    self._understood(t)

    def set_time(self) -> None:
        task_id = self._ask_task_id("move / set a time for")
        if task_id is None:
            return
        with self.Session() as s:
            task = svc.get_task(s, task_id)
            current = f" (now {task.start_at:%H:%M})" if task.start_at else ""
            while True:
                raw = (Prompt.ask(f"New start time for '{task.title}'{current}, or before/after <task ID> "
                                  "(blank = clear)", default="", show_default=False) or "").strip().lower()
                try:
                    words = raw.split()
                    if len(words) == 2 and words[0] in ("before", "after", "b", "a") and words[1].isdigit():
                        where = "before" if words[0].startswith("b") else "after"
                        task = svc.move_next_to(s, task_id, int(words[1]), where, now=self.clock())
                    else:
                        start = svc.parse_time(raw) if raw else None
                        task = svc.set_start_time(s, task_id, start, now=self.clock())
                    break
                except svc.SlotTaken as e:  # planner-placed tasks in the way: a proposal moves them
                    console.print(f"[yellow]{e}[/]")
                    self._run_trigger(s, ("claim", e.claim, None))
                    return
                except svc.TaskError as e:
                    console.print(f"[red]{e}[/]")
            if task.start_at:
                console.print(f"[green]Task {task_id} starts at {task.start_at:%H:%M} ({task.placement}).[/]")
            else:
                console.print(f"[green]Task {task_id} has no time now; the planner will place it.[/]")

    def unpin(self) -> None:
        task_id = self._ask_task_id("unpin (hand back to the planner)")
        if task_id is None:
            return
        with self.Session() as s:
            svc.unpin_task(s, task_id)
            console.print(f"[green]Task {task_id} unpinned. Press p to re-plan.[/]")

    def plan_my_day(self) -> None:
        day = ask_day(self.today())
        with self.Session() as s:
            result = planner.plan_day(s, day, self.settings.window, now=self.clock())
            self.render_plan(result)

    def render_plan(self, result) -> None:
        day = result.day
        if True:
            ws, we = self.settings.window
            table = Table(title=f"Plan for {day:%a %d %b} (window {ws:%H:%M}-{we:%H:%M})", title_justify="left",
                          expand=True)
            table.add_column("Time", no_wrap=True)
            table.add_column("ID", justify="right", style="cyan")
            table.add_column("Task")
            table.add_column("Priority", no_wrap=True)
            table.add_column("Why here")
            rows = sorted(result.placed + result.kept, key=lambda t: t.start_at)
            for t in rows:
                why = t.plan_reason if t in result.placed else (PLACEMENT_STYLE.get(t.placement, ("kept",))[0]
                                                                  + ": not moved")
                table.add_row(f"{t.start_at:%H:%M}-{t.end_at:%H:%M}", str(t.id), t.title, _priority_cell(t),
                              Text(why or "", style="green" if t in result.placed else "dim"))
            if not rows:
                table.add_row("", "", "[dim]Nothing to plan.[/]", "", "")
            console.print(table)
            if result.overflow:
                console.print(_overflow_table(result.overflow))
            console.print(f"[green]{len(result.placed)} placed[/], {len(result.kept)} kept, "
                          f"[red]{len(result.overflow)} didn't fit[/].")

    def link_task(self) -> None:
        task_id = self._ask_task_id("link to a goal")
        if task_id is None:
            return
        with self.Session() as s:
            task = svc.get_task(s, task_id)
            if task.goal:
                console.print(f"Currently linked to '{task.goal.title}'.")
            goal_id = self._pick_goal(s, allow_unlink=True)
            svc.link_task(s, task_id, goal_id, today=self.today())
            console.print(f"[green]Task {task_id} " + ("unlinked." if goal_id is None else "linked.") + "[/]")

    def _ask_free_time(self, s, title, day, duration, label, exclude_task_id=None, unchanged="none"):
        """Ask for a start time until it doesn't overlap another task.
        Keeping a task's current time (`unchanged`) is always accepted."""
        while True:
            start = ask_time(label)
            if start == unchanged:
                return start
            other = svc.find_overlap(s, day, start, duration, exclude_task_id)
            if other is None:
                return start
            console.print(f"[red]{svc.overlap_message(title, day, start, duration, other)}[/]")

    def _ask_task_id(self, action: str) -> Optional[int]:
        raw = Prompt.ask(f"ID of task to {action} (blank = cancel)", default="", show_default=False).strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            console.print("[red]Enter a number from the ID column.[/]")
            return None

    def _complete(self, s, task_id: int) -> None:
        """Done. For a linked task, ask how much it contributes to its goal."""
        task = svc.get_task(s, task_id)
        c = tr.contribution_for(task, self.today())
        amount, mark_done = 0.0, False
        if c.mode == "amount":
            amount = ask_amount(f"How many {task.goal.unit} did this add to '{task.goal.title}'?", default="0")
        elif c.mode == "mark_done":
            mark_done = Confirm.ask(f"Does this complete the goal '{task.goal.title}'?", default=False)
        elif c.mode == "closed":
            console.print(f"[yellow]{c.note}[/]")
        task = svc.complete_task(s, task_id, contribution=amount, mark_goal_done=mark_done, today=self.today())
        msg = f"[green]'{task.title}' done.[/]"
        if task.goal and (amount > 0 or mark_done):
            s.refresh(task.goal)
            msg += f" {rollup_line(task.goal)}"
        console.print(msg)

    def _close_interactively(self, s, task: Task, status: TaskStatus) -> None:
        verb = "failed" if status is TaskStatus.FAILED else "skipped"
        console.print(f"Why was '[bold]{task.title}[/]' {verb}? A reason is required.")
        # Loops until a non-empty reason is given. Ctrl+C leaves the task open.
        reason = ask_text("Reason")
        fn = svc.fail_task if status is TaskStatus.FAILED else svc.skip_task
        fn(s, task.id, reason)
        self.after_close(task.id)
        self.triggers.append(("closed", task.id, None))
        console.print(f"[magenta]Marked {verb}. Reason saved.[/] A reschedule proposal will follow.")

    def done(self) -> None:
        task_id = self._ask_task_id("mark done")
        if task_id is None:
            return
        with self.Session() as s:
            self._complete(s, task_id)

    def close_with_reason(self, status: TaskStatus) -> None:
        verb = "failed" if status is TaskStatus.FAILED else "skipped"
        task_id = self._ask_task_id(f"mark {verb}")
        if task_id is None:
            return
        with self.Session() as s:
            task = svc.get_task(s, task_id)
            if task.status != TaskStatus.PENDING.value:
                raise svc.TaskError(f"Task {task_id} is already {task.status}.")
            self._close_interactively(s, task, status)

    def view_day(self) -> None:
        self.render_day(ask_day(self.today()))

    def render_day(self, day: date) -> None:
        with self.Session() as s:
            tasks = svc.tasks_for_day(s, day)
            console.print(_task_table(tasks, f"{day:%a %d %b}  ({_summary(tasks)})"))

    def render_tracking(self, kind, start: date) -> None:
        screen = TrackingScreen(self, P.PeriodKind(kind))
        screen.start = start
        screen.render()

    def tracking(self) -> None:
        TrackingScreen(self).run()

    def fail(self) -> None:
        self.close_with_reason(TaskStatus.FAILED)

    def skip(self) -> None:
        self.close_with_reason(TaskStatus.SKIPPED)

    def refresh(self) -> None:
        pass

    def quit(self) -> None:
        self.quit_requested = True

    def toggle_mute(self) -> None:
        self.settings.muted = not self.settings.muted
        save_settings(self.settings_file, self.settings)
        console.print("[yellow]Microphone muted.[/]" if self.settings.muted else "[green]Microphone on.[/]")

    def change_task(self) -> None:
        task_id = self._ask_task_id("change")
        if task_id is None:
            return
        with self.Session() as s:
            task = svc.get_task(s, task_id)
            title = ask_text(f"Title [{task.title}]", required=False)
            raw = Prompt.ask(f"Duration [{svc.format_duration(task.duration_min)}]", default="", show_default=False).strip()
            minutes = svc.parse_duration(raw) if raw else None
            raw = Prompt.ask(f"Priority [{PRIORITY_NAMES[task.priority]}] (1-4)", default="", show_default=False).strip()
            task = self._claiming(s, lambda ampm: svc.update_task(
                s, task_id, title=title, duration_min=minutes, priority=raw or None, today=self.today(), ampm=ampm,
                **self._title_rules()))
            if task is not None:
                console.print(f"[green]Task {task_id} updated.[/]")
                self._understood(task)

    def delete_task_typed(self) -> None:
        task_id = self._ask_task_id("delete")
        if task_id is None:
            return
        with self.Session() as s:
            task = svc.get_task(s, task_id)
            if Confirm.ask(f"Delete '{task.title}'? This can't be undone.", default=False):
                svc.delete_task(s, task_id)
                console.print("[green]Deleted.[/]")

    # ----- v1.5.1 voice tools (typed; each has a voice command too) -----

    def render_voice_log(self, rows) -> None:
        table = Table(title="Recent voice commands (data/voice_log.db)", title_justify="left", expand=True)
        for col in ("Time", "Heard", "Sure", "Understood as", "By", "Acted", "Result", "Audio"):
            table.add_column(col)
        for r in rows:
            table.add_row(r.ts[11:16] if r.ts else "", r.transcript, f"{(r.confidence or 0):.0%}", r.interpreted or "-",
                          r.source or "-", "yes" if r.acted else "no", (r.result or "")[:60],
                          Path(r.audio_file).name if r.audio_file else "-")
        if not rows:
            table.add_row("", "[dim]No voice commands yet.[/]", "", "", "", "", "", "")
        console.print(table)

    def show_voice_log(self) -> None:
        self.render_voice_log(self.voice_log.recent(15))

    def render_devices(self, devices) -> None:
        table = Table(title="Microphones", title_justify="left", expand=True)
        for col in ("#", "Device", "Sample rate", "Note"):
            table.add_column(col)
        current = self.settings.input_device
        for d in devices:
            mark = " (in use)" if str(d.index) == current else ""
            table.add_row(str(d.index), d.name + mark, f"{d.samplerate} Hz", Text(d.warning or "", style="yellow"))
        console.print(table)
        console.print(f"In use: {'device ' + current if current else 'the Windows default'}")

    def pick_input_device(self) -> None:
        from .voice import audio as A
        devices = A.list_input_devices()
        self.render_devices(devices)
        raw = Prompt.ask("Device number (blank = keep, 'd' = Windows default)", default="", show_default=False).strip()
        if not raw:
            return
        if raw == "d":
            self.settings.input_device = ""
        elif raw.isdigit() and any(d.index == int(raw) for d in devices):
            self.settings.input_device = raw
        else:
            raise svc.TaskError("Pick a number from the list.")
        save_settings(self.settings_file, self.settings)
        self.voice_io = None
        console.print("[green]Saved.[/]")

    def mic_test(self) -> None:
        from .voice.mictest import run_mic_test
        run_mic_test(self.settings, console, understanding=self.understanding, names=self.voice_names())

    def voice_options(self) -> None:
        from .voice.stt import MODEL_SIZES_MB
        st = self.settings
        console.print(f"Whisper model: {st.stt_model}   local language model: "
                      f"{st.llm_model if st.llm_enabled else 'off'}   spoken replies: {'on' if st.spoken_replies else 'off'}"
                      f"   hands-free: {'on' if st.hands_free else 'off'} ('{st.wake_phrase}')   push-to-talk: {st.push_to_talk_key}")
        raw = Prompt.ask(f"Whisper model [{st.stt_model}] ({', '.join(MODEL_SIZES_MB)})", default="", show_default=False).strip()
        if raw:
            if raw not in MODEL_SIZES_MB:
                raise svc.TaskError("Unknown model size.")
            st.stt_model = raw
        raw = Prompt.ask(f"Local language model [{st.llm_model if st.llm_enabled else 'off'}] (a model name, or 'off')",
                         default="", show_default=False).strip()
        if raw == "off":
            st.llm_enabled = False
        elif raw:
            st.llm_enabled, st.llm_model = True, raw
        for name, label in (("spoken_replies", "Spoken replies"), ("hands_free", "Hands-free")):
            raw = Prompt.ask(f"{label} [{'on' if getattr(st, name) else 'off'}] (on/off)", default="", show_default=False).strip()
            if raw in ("on", "off"):
                setattr(st, name, raw == "on")
        save_settings(self.settings_file, st)
        self.voice_io, self.understanding = None, self._make_understanding()
        console.print("[green]Saved.[/] Download a new model with voice_setup.bat if needed.")

    def bulk_delete_typed(self) -> None:
        choice = Prompt.ask("Delete [bold]a[/]ll tasks and goals / all [bold]t[/]asks / all [bold]g[/]oals / "
                            "[bold]d[/] one day's tasks", choices=["a", "t", "g", "d"], show_choices=False)
        scope = {"a": "tasks and goals", "t": "tasks", "g": "goals", "d": "day"}[choice]
        day = ask_day(self.today()) if scope == "day" else None
        with self.Session() as s:
            plan = svc.bulk_delete_plan(s, scope, day=day, today=self.today())
            console.print(Panel(plan.describe(), title="Bulk delete", border_style="red"))
            if plan.empty:
                return
            if Prompt.ask("Type DELETE to confirm", default="", show_default=False).strip() != "DELETE":
                console.print("[yellow]Nothing was deleted.[/]")
                return
            n_t, n_g = svc.bulk_delete(s, plan, today=self.today())
            console.print(f"[green]Deleted {n_t} task(s) and {n_g} goal(s).[/]")

    def settings_menu(self) -> None:
        ws, we = self.settings.window
        choice = Prompt.ask(f"[bold]s[/]nooze length ({self.settings.snooze_minutes} min) / "
                            f"[bold]w[/] day window ({ws:%H:%M}-{we:%H:%M}) / "
                            f"[bold]d[/] default task length ({self.settings.default_task_minutes} min) / "
                            "[bold]v[/] voice options / "
                            "[bold]i[/] microphone / [bold]t[/] mic test / [bold]l[/] voice log / [bold]x[/] bulk delete / "
                            "[bold]e[/] export / [bold]m[/] import",
                            choices=vreg.typed_keys(vreg.SETTINGS), default="s")
        getattr(self, vreg.typed_map(vreg.SETTINGS)[choice])()

    def change_window(self) -> None:
        start = ask_time(f"Day starts at [{self.settings.day_start}]") or self.settings.day_start
        end = ask_time(f"Day ends at [{self.settings.day_end}]") or self.settings.day_end
        self.settings.day_start, self.settings.day_end = validate_window(start, end)
        save_settings(self.settings_file, self.settings)
        console.print(f"[green]The planner now uses {self.settings.day_start}-{self.settings.day_end}.[/]")

    def change_default_length(self) -> None:
        raw = Prompt.ask(f"Length of a task whose title gives one time, in minutes [{self.settings.default_task_minutes}]",
                         default="", show_default=False).strip()
        if not raw:
            return
        self.settings.default_task_minutes = validate_task_minutes(raw)
        save_settings(self.settings_file, self.settings)
        console.print(f"[green]A single time in a title now gives {self.settings.default_task_minutes} minutes.[/]")

    def change_settings(self) -> None:
        raw = Prompt.ask(f"Snooze length in minutes [{self.settings.snooze_minutes}]", default="",
                         show_default=False).strip()
        if not raw:
            return
        self.settings.snooze_minutes = validate_snooze(raw)
        save_settings(self.settings_file, self.settings)
        m = self.settings.snooze_minutes
        console.print(f"[green]Snooze length is now {m} minute{'' if m == 1 else 's'}.[/]")

    # ----- loop -----

    def typed_actions(self):
        """Typed menu keys -> methods, built from the shared command registry."""
        return {key: getattr(self, method) for key, method in vreg.typed_map(vreg.TIMETABLE).items()}

    def run(self) -> None:
        actions = self.typed_actions()
        missed = [a for a in self.alarms.check(startup=True) if a.missed]
        self.show_missed(missed)
        # the app noticed today's tasks ended with no mark: ask what happened
        with self.Session() as s:
            for a in missed:
                t = s.get(Task, a.task_id)
                if a.kind == END_CHECK and t is not None and t.planned_for == self.today():
                    self.checkins.put(a)
        self.alarms.start()
        self.reminders.start()
        self.notes_away = self.notes.startup()
        self.notes.start()
        self.ringer.start()
        try:
            while True:
                self.attend()
                if self.quit_requested:
                    console.print("Saved. Bye.")
                    return
                self.dashboard()
                if self.settings.hands_free and not self.settings.muted:
                    self.hands_free()
                    if self.quit_requested:
                        console.print("Saved. Bye.")
                        return
                self.voice_mode = False
                ptt = self.settings.push_to_talk_key
                try:
                    choice = Prompt.ask("\n>", choices=[k for k in actions if k] + [ptt], default="",
                                        show_choices=False, show_default=False).lower()
                except (KeyboardInterrupt, EOFError):
                    choice = "q"
                if choice == "q":
                    console.print("Saved. Bye.")
                    return
                if choice == "":
                    continue  # refresh; also answers any pending check-ins
                if choice == "g":
                    self.tracking()  # has its own loop and "Press Enter" handling
                    continue
                if choice == ptt:
                    try:
                        self.voice_turn()
                    except Exception as e:  # never fail silently
                        console.print(f"[red]Voice error: {e}. Typed input still works.[/]")
                    if self.quit_requested:
                        console.print("Saved. Bye.")
                        return
                    Prompt.ask("[dim]Press Enter to continue[/]", default="", show_default=False)
                    continue
                try:
                    actions[choice]()
                except KeyboardInterrupt:
                    console.print("\n[yellow]Cancelled. Nothing was changed.[/]")
                except (svc.TaskError, ValueError) as e:
                    console.print(f"[red]{e}[/]")
                Prompt.ask("[dim]Press Enter to continue[/]", default="", show_default=False)
        finally:
            self.alarms.stop()
            self.reminders.stop()
            self.notes.stop()
            self.ringer.stop()


def main() -> None:
    App().run()
