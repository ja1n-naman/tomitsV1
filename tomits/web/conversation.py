"""Typed or spoken commands from the browser's quick-add box and mic.

They run through the same voice Dialog as the terminal: the same registry
match, the same follow-up questions, the same handlers, the same spoken "yes"
for risky actions. The dialog runs on a worker thread; when it asks a question
the HTTP request returns the question, and the next request carries the answer.
"""

from __future__ import annotations

import queue
import threading
from typing import Callable, Dict, List, Optional

from .. import undo as U
from ..errors import TaskError
from ..voice import parse as P
from ..voice import registry as R
from ..voice.dialog import Cancelled, Dialog, Heard

ANSWER_TIMEOUT = 300        # seconds a question waits for an answer before it's cancelled
REPLY_WAIT = 120            # seconds an HTTP request waits for the dialog to answer or ask
_STOP = object()


class Conversation:
    def __init__(self, manager: "ConversationManager", cid: int, label: str) -> None:
        self.manager = manager
        self.id = cid
        self.label = label
        self.messages: List[dict] = []
        self.question: Optional[str] = None
        self.state = "running"
        self.cond = threading.Condition()
        self.inbox: "queue.Queue" = queue.Queue()
        self.undo_id: Optional[int] = None
        self.undo_label: Optional[str] = None

    # ----- the io object the Dialog talks to -----

    def say(self, text: str) -> None:
        self._push("say", text)

    def show(self, text: str) -> None:
        self._push("show", text)

    def listen(self, prompt: Optional[str] = None, grammar=None) -> Heard:
        if self.inbox.empty():
            with self.cond:
                self.question = prompt or "Yes?"
                self.messages.append({"type": "ask", "text": self.question})
                self.state = "asking"
                self.cond.notify_all()
        try:
            item = self.inbox.get(timeout=ANSWER_TIMEOUT)
        except queue.Empty:
            raise Cancelled() from None
        if item is _STOP:
            raise Cancelled()
        with self.cond:
            self.state = "running"
            self.question = None
        return item

    def _push(self, kind: str, text: str) -> None:
        with self.cond:
            self.messages.append({"type": kind, "text": text})

    # ----- driving it -----

    def answer(self, heard: Heard) -> None:
        self.inbox.put(heard)

    def cancel(self) -> None:
        self.inbox.put(_STOP)

    def wait(self, timeout: float = REPLY_WAIT) -> dict:
        with self.cond:
            self.cond.wait_for(lambda: self.state in ("asking", "done") and (self.state == "done" or self.inbox.empty()),
                               timeout)
            out = {"conv": self.id, "messages": list(self.messages), "question": self.question,
                   "done": self.state == "done", "asking": self.state == "asking",
                   "undo_id": self.undo_id, "undo_label": self.undo_label}
            self.messages.clear()
        app = self.manager.app
        out["view"], out["proposal"] = app.view, app.voice_proposal
        return out


class ConversationManager:
    def __init__(self, app) -> None:
        self.app = app
        self._convs: Dict[int, Conversation] = {}
        self._next = 1
        self._lock = threading.Lock()

    def _new(self, label: str) -> Conversation:
        with self._lock:
            for c in self._convs.values():   # one conversation at a time: a new command cancels an open question
                if c.state != "done":
                    c.cancel()
            cid = self._next
            self._next += 1
            conv = Conversation(self, cid, label)
            self._convs = {k: v for k, v in self._convs.items() if v.state != "done"}
            self._convs[cid] = conv
            return conv

    def _run(self, conv: Conversation, fn: Callable[[Dialog], None]) -> None:
        app = self.app
        app.view, app.voice_proposal = None, None

        def work():
            before = U.capture(app.engine, app.settings_file)
            try:
                fn(Dialog(app, conv, app.voice_state))
            except Cancelled:
                conv.say("Cancelled. Nothing was changed.")
            except TaskError as e:
                conv.say(f"I can't do that. {e}")
            except Exception as e:  # never fail silently
                conv._push("error", f"Something went wrong: {e}")
            finally:
                try:
                    after = U.capture(app.engine, app.settings_file)
                    change = U.diff(before, after, label=f"“{conv.label}”")
                    conv.undo_id = app.undo.push(change)
                    conv.undo_label = change.label if conv.undo_id else None
                    if change.settings_before != change.settings_after:
                        app.reload_settings()
                finally:
                    with conv.cond:
                        conv.state = "done"
                        conv.question = None
                        conv.cond.notify_all()
                    app.hub.publish("changed", {"source": "voice"})

        threading.Thread(target=work, name=f"tomits-conv-{conv.id}", daemon=True).start()

    def say(self, text: str, confidence: float = 1.0, audio=None, conv_id: Optional[int] = None) -> dict:
        """One utterance: an answer to an open question, or a new command."""
        heard = Heard(text or "", confidence, audio, "browser" if audio is not None else None)
        if conv_id is not None:
            with self._lock:
                conv = self._convs.get(conv_id)
            if conv is not None and conv.state == "asking":
                conv.answer(heard)
                return conv.wait()
        norm = P.normalize(text or "")
        app = self.app
        if norm and confidence >= 0.6:
            # answers to what's on screen come first: a ringing alarm, an open proposal, a check-in
            if app.ringer.ringing() and R.match(norm, R.ALARM):
                return self._quick(text, confidence, audio, self._alarm_answer(norm))
            if app.proposals.ids() and R.match(norm, R.PROPOSAL):
                return self._quick(text, confidence, audio, self._proposal_answer(norm))
            if app.checkins and R.match(norm, R.CHECKIN):
                from ..voice.commands import voice_checkin
                task_id, alarm = next(reversed(app.checkins.items()))
                conv = self._new(text)
                conv.answer(heard)  # its first question is answered by what was just said
                self._run(conv, lambda d: (voice_checkin(d, alarm), app.checkins.pop(task_id, None)))
                return conv.wait()
        conv = self._new(text or "(nothing)")
        self._run(conv, lambda d: d.handle(heard))
        return conv.wait()

    def _alarm_answer(self, norm: str) -> str:
        cmd, groups = R.match(norm, R.ALARM)
        r = self.app.ringer.ringing()[0]
        answer = cmd.handler(None, groups)
        if answer.startswith("z"):
            minutes = int(answer.split(":")[1]) if ":" in answer else None
            return self.app.execute("alarm_snooze", {"kind": r.alarm.kind, "task_id": r.alarm.task_id,
                                                     "minutes": minutes})["message"]
        return self.app.execute("alarm_dismiss", {"kind": r.alarm.kind, "task_id": r.alarm.task_id})["message"]

    def _proposal_answer(self, norm: str) -> str:
        cmd, groups = R.match(norm, R.PROPOSAL)
        answer = cmd.handler(None, groups)
        pid = self.app.proposals.ids()[-1]
        if answer == "r":
            with self.app.Session() as s:
                from ..voice.commands import speak_proposal
                return speak_proposal(Dialog(self.app, self, self.app.voice_state), self.app.proposals.build(s, pid))
        return self.app.execute("proposal_answer", {"id": pid, "answer": "accept" if answer == "y" else "reject"})["message"]

    def _quick(self, text: str, confidence: float, audio, reply: str) -> dict:
        log = self.app.voice_log
        try:
            row = log.add(text, confidence, audio, "browser" if audio is not None else None)
            log.update(row, source="rules", acted=True, result=reply)
        except Exception:
            pass
        self.app.hub.publish("changed", {"source": "voice"})
        return {"conv": None, "messages": [{"type": "show", "text": f'Heard: "{text}"'}, {"type": "say", "text": reply}],
                "question": None, "done": True, "asking": False, "undo_id": None, "undo_label": None,
                "view": None, "proposal": None}

    # the Dialog used for "read it again" needs an io; this manager answers nothing
    def say_text(self, text: str) -> None:  # pragma: no cover - not used as io
        pass
