"""The command registry: one list of actions shared by the typed menus and
voice. Each Command says how it's typed (screen + key + method on that
screen object), how it's spoken (regex patterns on normalized text), what it
calls (a voice handler that uses the same logic-layer functions as the typed
method), and example phrases for help / "didn't understand" replies.

The typed menus build their key -> method maps from here, so a typed action
can't exist without an entry; a test checks every entry with a typed key also
has voice patterns and a handler. Since v1.6 a command can also carry a `web`
handler: every control in the browser runs one of these, and a test checks
each one also has voice patterns, so clicking, typing and speaking share one
list of actions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

# Screens and prompts where typed keys live. The UI takes its choices from
# here (see ui.py / ui_tracking.py).
TIMETABLE = "timetable"
TRACKING = "tracking"
ALARM = "alarm"            # while an alarm rings: d dismiss, z snooze
CHECKIN = "checkin"        # end of task: d done, g still going, f failed, s skipped, l later
PROPOSAL = "proposal"      # reschedule: y accept, n reject
COLLISION = "collision"    # overrun hits a fixed task: s shorten, m move the rest, l leave
CAP = "cap"                # rescheduled 3 times: k keep, p split, d drop
SETTINGS = "settings"      # o menu: s snooze, w day window

MAIN = "main"              # voice context for free commands


@dataclass
class Command:
    name: str
    summary: str
    examples: List[str]
    patterns: List[str]
    handler: Callable
    typed: List[Tuple[str, str, str]] = field(default_factory=list)  # (screen, key, method name or answer)
    contexts: Tuple[str, ...] = (MAIN,)
    risky: bool = False       # deletes / discards / accepts: needs a spoken "yes"
    rank: int = 50            # lower is tried first (more specific patterns first)
    compiled: List[re.Pattern] = field(default_factory=list, repr=False)
    # v1.6 web app: the structured handler the browser calls (see tomits/web/actions.py).
    # It calls the same logic-layer functions as the voice handler and the typed menu.
    web: Optional[Callable] = field(default=None, repr=False)
    web_confirm: bool = False  # destructive: the browser must confirm (read-back first)

    def match(self, text: str) -> Optional[Dict[str, Optional[str]]]:
        for rx in self.compiled:
            m = rx.fullmatch(text)
            if m:
                return {k: (v.strip() if isinstance(v, str) else v) for k, v in m.groupdict().items()}
        return None


REGISTRY: List[Command] = []


def command(name, summary, examples, patterns, typed=(), contexts=(MAIN,), risky=False, rank=50):
    """Decorator: register a voice handler as a command."""
    def wrap(fn):
        cmd = Command(name, summary, list(examples), list(patterns), fn, list(typed), tuple(contexts), risky, rank,
                      [re.compile(p) for p in patterns])
        if any(c.name == name for c in REGISTRY):
            raise ValueError(f"duplicate command {name}")
        REGISTRY.append(cmd)
        REGISTRY.sort(key=lambda c: (c.rank, c.name))
        return fn
    return wrap


def match(text: str, context: str = MAIN) -> Optional[Tuple[Command, Dict[str, Optional[str]]]]:
    for cmd in REGISTRY:
        if context in cmd.contexts:
            groups = cmd.match(text)
            if groups is not None:
                return cmd, groups
    return None


def web_action(name: str, confirm: bool = False):
    """Decorator: attach the browser's handler to an existing command."""
    def wrap(fn):
        cmd = get(name)
        if cmd.web is not None:
            raise ValueError(f"command {name} already has a web handler")
        cmd.web, cmd.web_confirm = fn, confirm
        return fn
    return wrap


def get(name: str) -> Command:
    for c in REGISTRY:
        if c.name == name:
            return c
    raise KeyError(name)


def typed_map(screen: str) -> Dict[str, str]:
    """key -> method name (or answer) for a typed screen / prompt."""
    out: Dict[str, str] = {}
    for c in REGISTRY:
        for sc, key, target in c.typed:
            if sc == screen:
                out[key] = target
    return out


def typed_keys(screen: str) -> List[str]:
    return list(typed_map(screen))


def example_for(context: str = MAIN) -> str:
    if context == MAIN:
        for c in REGISTRY:
            if c.name == "add_task" and c.examples:
                return c.examples[0]
    for c in REGISTRY:
        if context in c.contexts and c.examples:
            return c.examples[0]
    return "help"
