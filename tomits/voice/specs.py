"""What the local language model may fill in for each command (v1.5.1).

For every free command in the registry: the fields it may set, which are
required, allowed values for some fields, and the canonical sentences it
becomes. The model's answer is rendered into a canonical sentence, which is
then matched by the ordinary rule patterns; the match must be the same
command. So the model can only ever choose an existing registry action, and
the handler that runs is the same one typed / rule-based voice uses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import registry as R

DESTRUCTIVE_WORDS = {"delete", "remove", "clear", "erase", "wipe", "drop", "cancel", "undo", "destroy", "get rid"}


@dataclass
class Spec:
    templates: List[str]                      # tried in order; first whose {fields} are all present wins
    required: Tuple[str, ...] = ()
    enums: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    destructive: bool = False                 # needs a delete-like word in what you said
    hint: str = ""                            # extra meaning for the model

    @property
    def fields(self) -> List[str]:
        out: List[str] = []
        for t in self.templates:
            for f in re.findall(r"\{(\w+)\}", t):
                if f not in out:
                    out.append(f)
        return out

    def render(self, values: Dict[str, str]) -> Optional[str]:
        for t in self.templates:
            names = re.findall(r"\{(\w+)\}", t)
            if all(values.get(n) for n in names):
                return t.format(**{n: values[n] for n in names})
        return None


PERIODS = ("today", "tomorrow", "yesterday", "this week", "next week", "last week", "this month", "next month",
           "last month")
PERIOD_WORDS = ("today", "this week", "this month", "tomorrow", "next week", "next month")
PRIORITIES = ("urgent", "high", "normal", "low")
ON_OFF = ("on", "off")

SPECS: Dict[str, Spec] = {
    "add_task": Spec(["add a task {title} for {duration} at {time} {date} {priority} priority",
                      "add a task {title} for {duration} at {time} {priority} priority",
                      "add a task {title} for {duration} {date} {priority} priority",
                      "add a task {title} for {duration} {priority} priority",
                      "add a task {title} for {duration} at {time} {date}", "add a task {title} for {duration} at {time}",
                      "add a task {title} for {duration} {date}", "add a task {title} at {time} {date}",
                      "add a task {title} at {time}", "add a task {title} {date}", "add a task {title} for {duration}",
                      "add a task {title}"],
                     ("title",), {"priority": PRIORITIES},
                     hint="duration like '45 minutes'; time like '3 pm'; date like 'tomorrow' or 'next monday'"),
    "add_several": Spec(["add several tasks for {date}", "add several tasks"]),
    "plan_day": Spec(["plan {date}", "plan my day"], hint="also 're-plan' / 'organise my day'"),
    "move_task": Spec(["move {name} {where} {other}", "move {name} to {date} at {time}", "move {name} to {date}",
                       "move {name} to {time}"], ("name",), {"where": ("before", "after")},
                      hint="push / postpone / shift a task to another time or day"),
    "pin_task": Spec(["pin {name}"], ("name",)),
    "unpin_task": Spec(["unpin {name}"], ("name",)),
    "edit_task": Spec(["rename {name} to {new_title}", "change the duration of {name} to {duration}",
                       "set the priority of {name} to {priority}"], ("name",), {"priority": PRIORITIES}),
    "delete_task": Spec(["delete the task {name}"], ("name",), destructive=True),
    "mark_done": Spec(["mark {name} done", "mark it done"], hint="finished / completed / done with a task"),
    "mark_failed": Spec(["mark {name} as failed", "mark it as failed"], hint="couldn't do / didn't finish a task"),
    "mark_skipped": Spec(["skip {name}", "skip it"]),
    "extend_task": Spec(["extend {name} until {time}", "extend {name} by {duration}", "extend it until {time}",
                         "extend it by {duration}", "still going"], hint="a task is taking longer / still going"),
    "reschedule_missed": Spec(["reschedule {name}"], ("name",), hint="find a new time for a failed or skipped task"),
    "undo_reschedule": Spec(["undo the reschedule"], destructive=True),
    "history": Spec(["show my history for {goal} {period}", "show my history for {goal}", "show my history {period}",
                     "show my history"], enums={"period": PERIODS}, hint="failed / skipped / missed tasks"),
    "link_task": Spec(["link {name} to goal {goal}", "unlink {name}"], ("name",)),
    "show_day": Spec(["what do i have {date}"], ("date",), hint="which tasks are on a given day"),
    "my_day": Spec(["whats my day like"], hint="today's plan / what's left today"),
    "whats_next": Spec(["whats next"]),
    "open_tracking": Spec(["open {period}"], ("period",), {"period": PERIODS}, hint="day / week / month tracking page"),
    "go_period": Spec(["go to the {direction} {kind}"], ("direction", "kind"),
                      {"direction": ("previous", "next"), "kind": ("day", "week", "month")}),
    "close_tracking": Spec(["go back"]),
    "refresh": Spec(["refresh"]),
    "quit": Spec(["quit"]),
    "help": Spec(["help"]),
    "new_goal": Spec(["add a {kind} goal {title} linked to {parent}", "add a {kind} goal {title}", "add a goal {title}"],
                     ("title",), {"kind": ("daily", "weekly", "monthly")},
                     hint="a target with a unit stays in the title, like 'run 40 km'"),
    "edit_goal": Spec(["rename goal {name} to {new_title}", "change the target of goal {name} to {target}",
                       "link goal {name} to {parent}", "unlink goal {name}"], ("name",)),
    "delete_goal": Spec(["delete goal {name}"], ("name",), destructive=True),
    "log_progress": Spec(["log {amount} {unit} to {goal} {when}", "log {amount} {unit} to {goal}",
                          "log {amount} {unit} {when}", "log {amount} {unit}"], ("amount", "unit"),
                         {"when": ("today", "yesterday")}, hint="progress on a goal: 'I ran 3 km'"),
    "remove_log": Spec(["remove the last log for {goal}", "remove the last log"], destructive=True),
    "goal_done": Spec(["mark goal {name} {state}"], ("name", "state"), {"state": ("done", "not done")}),
    "set_process": Spec(["set the process for {period} to {text}", "set the process for {period}", "set the process"],
                        enums={"period": PERIOD_WORDS}),
    "add_sacrifice": Spec(["add a sacrifice {text} for {period} as {status}", "add a sacrifice {text} as {status}",
                           "add a sacrifice {text} for {period}", "add a sacrifice {text}"], ("text",),
                          {"status": ("planned", "made"), "period": PERIOD_WORDS}),
    "made_sacrifice": Spec(["mark sacrifice {name} as made"], ("name",)),
    "remove_sacrifice": Spec(["remove sacrifice {name}"], ("name",), destructive=True),
    "write_review": Spec(["write my review for {period}", "write my review"], enums={"period": PERIODS}),
    "progress": Spec(["how am i doing on {what}", "how am i doing"]),
    "fill_in": Spec(["fill in my plan"]),
    "settings": Spec(["set my day from {start} to {end}", "set snooze to {minutes} minutes",
                      "set the default task length to {length} minutes", "show my settings"]),
    "keep_typed_title": Spec(["keep the {name} title as typed", "keep the title as typed"],
                             hint="undo a time that was read from a task's title"),
    "voice_settings": Spec(["turn {state} spoken replies", "set the wake phrase to {phrase}"], enums={"state": ON_OFF}),
    "mute": Spec(["mute", "unmute"]),
    "delete_all": Spec(["delete all {what} from everywhere", "delete all tasks and goals from everywhere"],
                       enums={"what": ("tasks and goals", "tasks", "goals")}, destructive=True),
    "clear_day": Spec(["clear {date}"], ("date",), destructive=True),
    "show_voice_log": Spec(["show the voice log"]),
    "mic_test": Spec(["test my mic"]),
    "undo_action": Spec(["undo my last change"], destructive=True, hint="take back the last change made"),
    "dismiss_reminder": Spec(["dismiss the reminders"], hint="hide the fill-in reminder banner"),
    "switch_layout": Spec(["switch to the {layout} layout"], ("layout",),
                          {"layout": ("timeline", "calendar", "board", "focus", "dashboard", "voice")}),
    "set_theme": Spec(["use {theme} mode"], ("theme",), {"theme": ("dark", "light", "system")}),
    "finish_setup": Spec(["finish the setup"]),
    "input_device": Spec(["use microphone {number}", "list my microphones"]),
    "add_note": Spec(["remember to {text}"], ("text",), hint="a note to remember, optionally with a time"),
    "delete_note": Spec(["delete the note {name}"], ("name",), destructive=True),
    "notes_panel": Spec(["show my notes", "hide my notes"], hint="what do I need to remember"),
    "dismiss_note_banner": Spec(["dismiss the note reminder"]),
    "export_data": Spec(["export my data"]),
    "import_data": Spec(["import my latest export"], destructive=True),
}


def free_commands() -> List[R.Command]:
    return [c for c in R.REGISTRY if R.MAIN in c.contexts]
