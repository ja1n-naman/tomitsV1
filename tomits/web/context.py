"""The web app's shared context: database, settings, alarms, reminders,
reschedule proposals, undo and voice. It also plays the role of the `app`
object the voice commands expect (same attributes as the terminal App), so a
spoken or typed command in the browser runs the exact same handler.

No rule lives here: every change goes through a registry command, whose
handler calls the logic layer (services / tracking / planner / rescheduler).
"""

from __future__ import annotations

import threading
from collections import OrderedDict, deque
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable, Deque, Dict, List, Optional, Tuple

from .. import notes as N
from .. import rescheduler as rs
from .. import services as svc
from .. import tracking as tr
from .. import undo as U
from ..alarms import END_CHECK, HEADS_UP, Alarm, AlarmService
from ..db import default_db_path, make_session_factory
from ..errors import TaskError
from ..models import Task, TaskStatus
from ..reminders import ReminderService
from ..ringer import RERUNG, TIMED_OUT, Ringer, key_of
from ..settings import load_settings, settings_path
from ..voice import registry as R
from ..voice.dialog import VoiceState
from .hub import Hub, Watcher


class NullPlayer:
    """The browser plays the tone; the server only keeps the ringing state."""

    def play_burst(self) -> None:
        pass


def _iso(d):
    return d.isoformat() if d is not None else None


def _hm(t: Optional[time]) -> Optional[str]:
    return t.strftime("%H:%M") if t is not None else None


# ---------------- reschedule proposals ----------------

def move_json(m: rs.Move) -> dict:
    end = None
    if m.to_start is not None and m.to_day is not None:
        minutes = m.new_duration if m.kind == "extend" else m.duration
        end = (datetime.combine(m.to_day, m.to_start) + timedelta(minutes=minutes)).strftime("%H:%M")
    return {"kind": m.kind, "title": m.title, "priority": m.priority, "duration": m.duration,
            "duration_text": svc.format_duration(m.duration), "reason": m.reason, "task_id": m.task_id,
            "source_id": m.source_id, "from_day": _iso(m.from_day), "from_start": _hm(m.from_start),
            "to_day": _iso(m.to_day), "to_start": _hm(m.to_start), "to_end": end, "new_duration": m.new_duration,
            "unplaced": m.unplaced}


class ProposalStore:
    """Proposals waiting for an answer. Nothing is written until accept();
    each one is rebuilt from the current plan whenever it is shown."""

    def __init__(self, app: "WebApp") -> None:
        self.app = app
        self._items: "OrderedDict[int, dict]" = OrderedDict()
        self._next = 1
        self._lock = threading.Lock()

    def add(self, s, trigger: Tuple) -> int:
        self.app._build(s, trigger)  # validates now: a failed task needs its reason
        with self._lock:
            pid = self._next
            self._next += 1
            self._items[pid] = {"trigger": trigger, "choice": None, "created": self.app.clock()}
            return pid

    def _entry(self, pid: int) -> dict:
        with self._lock:
            if pid not in self._items:
                raise TaskError("That proposal is no longer open.")
            return self._items[pid]

    def build(self, s, pid: int) -> rs.Proposal:
        e = self._entry(pid)
        return self.app._build(s, e["trigger"], e["choice"])

    def remove(self, pid: int) -> None:
        with self._lock:
            self._items.pop(pid, None)

    def ids(self) -> List[int]:
        with self._lock:
            return list(self._items)

    def accept(self, s, pid: int) -> rs.Proposal:
        prop = self.build(s, pid)
        if prop.needs_choice:
            raise TaskError("Choose what to do first (see the question on the proposal).")
        rs.accept(s, prop, now=self.app.clock())
        self.app.after_accept(prop)
        self.remove(pid)
        return prop

    def choose(self, s, pid: int, choice: str) -> str:
        e = self._entry(pid)
        if choice in ("drop", "leave"):
            self.remove(pid)
            return "Dropped: no new copy. It stays recorded with its reason." if choice == "drop" else \
                "Left as it is. Nothing was changed."
        e["choice"] = choice
        self.build(s, pid)
        return "Updated the proposal."

    def to_json(self, s) -> List[dict]:
        out = []
        for pid in self.ids():
            e = self._entry(pid)
            try:
                prop = self.build(s, pid)
            except TaskError as err:  # the task changed so much it can't be proposed any more
                self.remove(pid)
                continue
            out.append({
                "id": pid, "trigger": prop.trigger, "task_id": prop.task_id, "title": prop.title,
                "summary": prop.summary, "moves": [move_json(m) for m in prop.placed],
                "unplaced": [move_json(m) for m in prop.unplaced],
                "collisions": [{"task_id": c.task_id, "title": c.title, "start": c.start.strftime("%H:%M"),
                                "end": c.end.strftime("%H:%M"), "placement": c.placement, "message": c.message}
                               for c in prop.collisions],
                "cap_reached": prop.cap_reached and prop.choice is None, "chain_count": prop.chain_count,
                "max_reschedules": rs.MAX_RESCHEDULES,
                "requested_end": prop.requested_end.strftime("%H:%M") if prop.requested_end else None,
                "needs_choice": prop.needs_choice, "choice": prop.choice, "empty": not prop.moves,
                "created": e["created"].isoformat(timespec="seconds"),
            })
        return out


# ---------------- the context ----------------

class WebApp:
    def __init__(self, db_path=None, clock: Callable[[], datetime] = datetime.now, start_threads: bool = True,
                 watch_interval: float = 0.5) -> None:
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.clock = clock
        self.Session = make_session_factory(self.db_path)
        self.engine = self.Session.kw["bind"]
        self.settings_file = settings_path(self.db_path)
        self.settings = load_settings(self.settings_file)
        self.hub = Hub()
        self.write_lock = threading.RLock()
        self.undo = U.UndoStack()
        self.ringer = Ringer(player=NullPlayer(), snooze_minutes=lambda: self.settings.snooze_minutes,
                             clock=clock, on_event=self._on_ring_event)
        self.alarms = AlarmService(self.Session, None, on_alarm=self._on_alarm, interval_seconds=5, clock=clock)
        self.reminders = ReminderService(self.Session, None, on_reminder=self._on_reminder, clock=clock)
        self.notes = N.NoteService(self.Session, self._on_notes_due, clock=clock)
        self.notes_away = 0          # notes that became overdue while tomits wasn't running (one summary banner)
        self.notifier = None         # desktop toast from the server, only when no browser tab is open
        self.checkins: "OrderedDict[int, Alarm]" = OrderedDict()   # end-of-task check-ins waiting for an answer
        self.missed: List[Alarm] = []                               # came due while nothing was open
        self.recent: Deque[Tuple[datetime, Alarm]] = deque(maxlen=8)
        self.proposals = ProposalStore(self)
        # voice (same objects the terminal uses)
        from ..voice.voicelog import VoiceLog
        self.voice_state = VoiceState()
        self.voice_log = VoiceLog(self.db_path.parent / "voice_log.db")
        self._understanding = None
        self.voice_io = None
        self.quit_requested = False
        self.view: Optional[dict] = None           # where a voice command wants the browser to go
        self.voice_proposal: Optional[dict] = None
        self._stt = None
        self.stt_error: Optional[str] = None
        self._stt_lock = threading.Lock()
        from .conversation import ConversationManager
        self.conversations = ConversationManager(self)
        self.watcher = Watcher(self.db_path, self.settings_file, self.hub, self.reload_settings, watch_interval)
        self._started = False
        if start_threads:
            self.start()

    # ----- lifecycle -----

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        found = self.alarms.check(startup=True)
        self.missed = [a for a in found if a.missed]
        with self.Session() as s:
            for a in self.missed:
                t = s.get(Task, a.task_id)
                if a.kind == END_CHECK and t is not None and t.planned_for == self.today():
                    self.checkins[a.task_id] = a
        self.notes_away = self.notes.startup()
        self.alarms.start()
        self.reminders.start()
        self.notes.start()
        self.ringer.start()
        self.watcher.start()

    def stop(self) -> None:
        for part in (self.alarms, self.reminders, self.notes, self.ringer, self.watcher):
            try:
                part.stop()
            except Exception:
                pass

    def today(self) -> date:
        return self.clock().date()

    def reload_settings(self) -> None:
        fresh = load_settings(self.settings_file)
        for name, value in vars(fresh).items():
            setattr(self.settings, name, value)

    # ----- running a command (every browser action comes through here) -----

    def execute(self, name: str, args: dict) -> dict:
        try:
            cmd = R.get(name)
        except KeyError:
            raise TaskError(f"Unknown action '{name}'.") from None
        if cmd.web is None:
            raise TaskError(f"'{cmd.summary}' isn't available as a button; say it or type it instead.")
        args = dict(args or {})
        with self.write_lock:
            if cmd.web_confirm and not args.get("confirmed"):
                preview = getattr(cmd.web, "preview", None)
                with self.Session() as s:
                    text = preview(self, s, args) if preview else f"{cmd.summary}? This can't be undone."
                return {"ok": True, "needs_confirm": True, "message": text, "command": name}
            before = U.capture(self.engine, self.settings_file)
            result: dict = {}
            error: Optional[TaskError] = None
            try:
                with self.Session() as s:
                    try:
                        result = cmd.web(self, s, args) or {}
                    except svc.AmbiguousTime as e:
                        # am or pm? nothing was saved; the browser asks and sends the answer as "ampm"
                        result = {"needs_choice": True, "message": e.question, "field": "ampm", "line": e.line,
                                  "choices": [{"label": label, "value": value} for label, value in e.choices]}
                    except svc.SlotTaken as e:
                        # planner-placed tasks are in the way: nothing saved, a proposal moves them
                        s.rollback()
                        pid = self.proposals.add(s, ("claim", e.claim, None))
                        result = {"message": str(e), "proposal_id": pid, "understood": e.claim.understood}
            except TaskError as e:
                error = e
            after = U.capture(self.engine, self.settings_file)
            change = U.diff(before, after, label=result.pop("label", cmd.summary))
            # opening / closing the notes panel isn't a change worth an Undo toast
            uid = None if name in ("undo_action", "notes_panel") else self.undo.push(change)
        if change.settings_before != change.settings_after:
            self.reload_settings()
        self.hub.publish("changed", {"source": "app", "command": name})
        if error is not None:
            if not change.empty and uid:  # part of it was saved before the refusal: still undoable
                raise TaskError(f"{error} (Some of it was saved; use Undo to take it back.)")
            raise error
        out = {"ok": True, "command": name, "message": result.pop("message", "Saved."), "undo_id": uid,
               "undo_label": change.label if uid else None, "saved": not change.empty}
        out.update(result)
        return out

    def undo_last_action(self, uid: Optional[int] = None) -> str:
        with self.write_lock:
            uid, change = self.undo.get(uid)
            U.undo(self.engine, change, self.today(), self.settings_file)
            self.undo.remove(uid)
        self.reload_settings()
        return change.label

    def last_action_label(self) -> Optional[str]:
        latest = self.undo.latest()
        return latest[1] if latest else None

    # ----- alarms (called from background threads) -----

    def _alarm_payload(self, alarm: Alarm) -> dict:
        return {"kind": alarm.kind, "task_id": alarm.task_id, "title": alarm.title, "message": alarm.message,
                "title_line": alarm.title_line}

    def _on_alarm(self, alarm: Alarm) -> None:
        self.recent.appendleft((self.clock(), alarm))
        self.ringer.ring(alarm)
        self.hub.publish("alarm", self._alarm_payload(alarm))

    def _on_ring_event(self, event: str, alarm: Alarm) -> None:
        if event == TIMED_OUT:
            self._after_ringing(alarm)
        self.hub.publish("alarm" if event == RERUNG else "changed", self._alarm_payload(alarm))

    def _after_ringing(self, alarm: Alarm) -> None:
        """Once an end-of-task alarm stops ringing, ask whether it was done."""
        if alarm.kind == END_CHECK:
            self.checkins[alarm.task_id] = alarm

    def dismiss_alarm(self, kind: str, task_id: int) -> str:
        alarm = self.ringer.dismiss((kind, task_id))
        if alarm is None:
            raise TaskError("That alarm isn't ringing any more.")
        self._after_ringing(alarm)
        return "Dismissed."

    def snooze_alarm(self, kind: str, task_id: int, minutes: Optional[int] = None) -> str:
        try:
            due = self.ringer.snooze((kind, task_id), minutes)
        except KeyError:
            raise TaskError("That alarm isn't ringing any more.") from None
        return f"Snoozed. It rings again at {due:%H:%M}."

    def _on_notes_due(self, due) -> None:
        """A note's time arrived (claimed once, see notes.py): the open tabs show its
        banner and ONE desktop notification (same tag in every tab, so it shows
        once). With no tab open, the server shows the notification itself."""
        if self.hub.client_count:
            for n in due:
                self.hub.publish("note", {"id": n.id, "text": n.text, "due": n.due_at.isoformat(timespec="minutes")})
        else:
            if self.notifier is None:
                from ..notify import DesktopNotifier
                self.notifier = DesktopNotifier()
            for n in due:
                self.notifier.notify("tomits: remember", n.text)
        self.hub.publish("changed", {"source": "notes"})

    def _on_reminder(self, new) -> None:
        self.hub.publish("reminder", {"items": [m.message for m in new]})

    # ----- hooks the voice commands call (same names as the terminal App) -----

    def after_close(self, task_id: int) -> None:
        for kind in (HEADS_UP, END_CHECK):
            self.ringer.dismiss((kind, task_id))
        self.checkins.pop(task_id, None)

    def after_accept(self, prop) -> None:
        for m in prop.moves:
            if m.task_id:
                for kind in (HEADS_UP, END_CHECK):
                    self.ringer.dismiss((kind, m.task_id))

    def _build(self, s, trigger, choice=None):
        return rs.build(s, trigger, self.settings.window, now=self.clock(), choice=choice)

    def _show_proposal(self, prop) -> None:
        self.voice_proposal = {"title": prop.title, "summary": prop.summary,
                               "moves": [move_json(m) for m in prop.placed],
                               "unplaced": [move_json(m) for m in prop.unplaced]}
        self.view = {"screen": "reschedule"}

    def render_plan(self, result) -> None:
        self.view = {"screen": "today", "day": _iso(result.day)}

    def render_tracking(self, kind, start: date) -> None:
        kind = getattr(kind, "value", kind)
        self.view = {"screen": kind, "start": _iso(start)}

    def render_history(self, rows, start: date, end: date) -> None:
        self.view = {"screen": "history", "from": _iso(start), "to": _iso(end)}

    def render_day(self, day: date) -> None:
        self.view = {"screen": "today", "day": _iso(day)}

    def render_voice_log(self, rows) -> None:
        self.view = {"screen": "voice"}

    def render_devices(self, devices) -> None:
        self.view = {"screen": "settings"}

    def dashboard(self) -> None:
        self.view = {"screen": "today"}

    def mic_test(self) -> None:
        self.view = {"screen": "voice", "mic_test": True}

    @property
    def understanding(self):
        if self._understanding is None:
            from ..voice.nlu import OllamaBackend, Understanding
            backend = OllamaBackend(self.settings.llm_model) if self.settings.llm_enabled else None
            self._understanding = Understanding(backend)
        return self._understanding

    def voice_names(self):
        today = self.today()
        with self.Session() as s:
            tasks = [t.title for t in s.query(Task).filter(Task.status == TaskStatus.PENDING.value).all()
                     if today - timedelta(days=7) <= t.planned_for <= today + timedelta(days=1)]
            goals = [g.title for g in tr.open_goals(s, today)]
        return sorted(set(tasks)), sorted(set(goals))

    # ----- speech to text (local faster-whisper, loaded on first use) -----

    def stt_status(self) -> dict:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return {"available": False, "reason": "Speech recognition isn't installed. Run start-tomits.bat and "
                    "answer Y to the voice question, or type commands in the box instead."}
        from ..voice.stt import MODELS_DIR, model_label
        size = self.settings.stt_model
        if not any(MODELS_DIR.glob(f"*{size}*")) and not (MODELS_DIR / size).exists():
            return {"available": False, "reason": f"The {model_label(size)} speech model isn't downloaded yet. "
                    "Run voice_setup.bat once (it asks before downloading). Typing works meanwhile."}
        return {"available": self.stt_error is None, "reason": self.stt_error, "model": size}

    def transcribe(self, samples, sample_rate: int):
        """samples: numpy float32 mono. Returns a Heard. Raises TaskError with a
        plain reason if speech recognition can't run."""
        from ..voice import audio as A
        from ..voice.stt import SttUnavailable, WhisperEngine
        with self._stt_lock:
            if self._stt is None or self._stt.size != self.settings.stt_model:
                try:
                    self._stt = WhisperEngine(self.settings.stt_model)
                    self.stt_error = None
                except SttUnavailable as e:
                    self.stt_error = f"Speech recognition can't start: {e}"
                    raise TaskError(self.stt_error) from None
            prepared = A.prepare(samples, sample_rate)
            tasks, goals = self.voice_names()
            hint = ("tomits: add a task, mark done, failed, skip, plan my day, re-plan, move, still going, snooze, "
                    "dismiss, goal, sacrifice, review, process. ")
            if tasks:
                hint += "Tasks: " + ", ".join(tasks[:25]) + ". "
            if goals:
                hint += "Goals: " + ", ".join(goals[:15]) + "."
            heard = self._stt.transcribe(prepared, hint[:700])
            heard.audio = prepared
            heard.device = "browser microphone"
            return heard
