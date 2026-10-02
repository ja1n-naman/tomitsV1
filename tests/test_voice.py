"""v1.5 voice control, tested from text transcripts (no microphone)."""

import io
import re
from datetime import date, datetime, time, timedelta

import pytest
from rich.console import Console

from tomits import planner as pl
from tomits import rescheduler as rs
from tomits import services as svc
from tomits import tracking as tr
from tomits import ui, ui_tracking
from tomits.alarms import END_CHECK, HEADS_UP, Alarm
from tomits.errors import TaskError
from tomits.models import Placement, Task, TaskReason, TaskStatus
from tomits.periods import PeriodKind
from tomits.voice import parse as P
from tomits.voice import registry as R
from tomits.voice.dialog import LOW_CONFIDENCE, Dialog, Heard

TODAY = date(2026, 10, 5)            # Monday
NOW = datetime(2026, 10, 5, 8, 30)


class ScriptedIO:
    """A microphone that 'hears' a list of utterances and records replies."""

    def __init__(self, utterances):
        self.queue = [u if isinstance(u, tuple) else (u, 1.0) for u in utterances]
        self.said, self.prompts, self.grammars = [], [], []

    def say(self, text):
        self.said.append(text)

    def listen(self, prompt=None, grammar=None):
        if prompt:
            self.said.append(prompt)
            self.prompts.append(prompt)
        self.grammars.append(grammar)
        if not self.queue:
            raise AssertionError(f"ran out of utterances; last prompt: {prompt}")
        text, conf = self.queue.pop(0)
        return Heard(text, conf)

    @property
    def text(self):
        return " | ".join(self.said)


class Quiet:
    def notify(self, *a, **k):
        pass


class Silent:
    def play_burst(self):
        pass


@pytest.fixture
def app(db_file, monkeypatch):
    monkeypatch.setattr(ui, "console", Console(file=io.StringIO(), width=160))
    monkeypatch.setattr(ui_tracking, "console", Console(file=io.StringIO(), width=160))
    monkeypatch.setattr("tomits.ui_common.console", Console(file=io.StringIO()))
    clock = {"now": NOW}
    a = ui.App(db_file, notifier=Quiet(), clock=lambda: clock["now"], player=Silent())
    a.clock_box = clock
    return a


def talk(app, *utterances):
    io_ = ScriptedIO(utterances)
    app.voice_turn(io_)
    assert io_.queue == [], f"not all utterances used: {io_.queue}"
    return io_


def tasks(app, day=TODAY):
    with app.Session() as s:
        return [(t.title, t.status, t.start_time, t.duration_min, t.priority) for t in svc.tasks_for_day(s, day)]


def add(app, title, minutes=60, start=None, priority=3, day=TODAY, placement=None):
    with app.Session() as s:
        t = svc.add_task(s, title, minutes, planned_for=day, start_time=start, priority=priority, today=TODAY)
        if placement:
            t.placement = placement
            s.commit()
        return t.id


# ======================= registry coverage =======================

def test_every_typed_action_has_a_voice_command():
    """Fails if a typed key is added anywhere without a voice command."""
    surfaces = [R.TIMETABLE, R.TRACKING, R.ALARM, R.CHECKIN, R.PROPOSAL, R.COLLISION, R.CAP, R.SETTINGS]
    for surface in surfaces:
        keys = R.typed_map(surface)
        assert keys, surface
        for key in keys:
            owners = [c for c in R.REGISTRY if any(sc == surface and k == key for sc, k, _ in c.typed)]
            assert len(owners) == 1, (surface, key)
            c = owners[0]
            assert c.patterns and c.examples and callable(c.handler), (surface, key, c.name)


def test_every_menu_key_on_screen_is_in_the_registry():
    for menu, surface in ((ui.MENU, R.TIMETABLE), (ui_tracking.MENU, R.TRACKING)):
        shown = set(re.findall(r"\[bold\](.+?)\[/\]", menu))
        shown -= {"v", "Enter"}                     # the voice key itself, and refresh (key "")
        shown = {k for part in shown for k in part.split("/")} if surface == R.TRACKING else shown
        for key in shown:
            key = {"[[": "["}.get(key, key)
            assert key in R.typed_map(surface), (surface, key)


def test_typed_menus_are_built_from_the_registry(app):
    assert set(app.typed_actions()) == set(R.typed_map(R.TIMETABLE))
    for method in R.typed_map(R.TIMETABLE).values():
        assert callable(getattr(app, method))
    screen = ui_tracking.TrackingScreen(app)
    for method in R.typed_map(R.TRACKING).values():
        assert callable(getattr(screen, method))


@pytest.mark.parametrize("cmd", R.REGISTRY, ids=lambda c: c.name)
def test_each_command_understands_its_own_examples(cmd):
    for example in cmd.examples:
        context = cmd.contexts[0]
        found = R.match(P.normalize(example), context)
        assert found is not None and found[0].name == cmd.name, (example, found and found[0].name)


# ======================= phrasing variations =======================

@pytest.mark.parametrize("said,expected", [
    ("mark it done", "mark_done"), ("I finished reading", "mark_done"), ("done with the report", "mark_done"),
    ("the report is done", "mark_done"), ("I'm done", "mark_done"), ("mark gym as complete", "mark_done"),
    ("I failed the report", "mark_failed"), ("mark gym as failed", "mark_failed"), ("I couldn't do the gym", "mark_failed"),
    ("skip the gym", "mark_skipped"), ("I'm skipping email", "mark_skipped"),
    ("add a task read for 45 minutes", "add_task"), ("remind me to call mom tomorrow at 9", "add_task"),
    ("schedule a new task report at 3 pm", "add_task"),
    ("plan my day", "plan_day"), ("re-plan", "plan_day"), ("replan", "plan_day"), ("plan tomorrow", "plan_day"),
    ("move report to 4 pm", "move_task"), ("put email after report", "move_task"), ("start report at 2", "move_task"),
    ("what's next", "whats_next"), ("what's my day like", "my_day"), ("what do I have tomorrow", "show_day"),
    ("I'm still working on the report until 4 pm", "extend_task"), ("still going", "extend_task"),
    ("extend it by 15 minutes", "extend_task"),
    ("undo the reschedule", "undo_reschedule"), ("undo", "undo_reschedule"),
    ("I read 10 pages", "log_progress"), ("log 5 km to running", "log_progress"),
    ("add a monthly goal read 500 pages", "new_goal"), ("new weekly goal read 110 pages", "new_goal"),
    ("how am I doing on this month's goal", "progress"), ("how am I doing", "progress"),
    ("open this week", "open_tracking"), ("show last month", "open_tracking"), ("go to the next week", "go_period"),
    ("set today's process", "set_process"), ("my process is read every night", "set_process"),
    ("add a sacrifice no phone after 10, planned", "add_sacrifice"), ("I gave up sugar", "add_sacrifice"),
    ("write my review for today", "write_review"), ("show my failures", "history"),
    ("set my day from 8 am to 10 pm", "settings"), ("set snooze to 10 minutes", "settings"),
    ("turn off spoken replies", "voice_settings"), ("turn on hands free", "voice_settings"),
    ("mute", "mute"), ("unmute", "mute"), ("fill in my plan", "fill_in"), ("quit", "quit"), ("help", "help"),
    ("delete the task email", "delete_task"), ("rename report to quarterly report", "edit_task"),
    ("make email urgent", "edit_task"), ("unpin the report", "unpin_task"), ("pin the report", "pin_task"),
    ("link report to goal ship", "link_task"), ("reschedule the report", "reschedule_missed"),
    ("delete goal spare", "delete_goal"), ("mark goal call mom done", "goal_done"),
    ("remove the last log", "remove_log"), ("remove sacrifice no phone", "remove_sacrifice"),
        ("mark sacrifice no phone as made", "made_sacrifice"), ("keep the title as typed", "keep_typed_title"),
        ("set the default task length to 45 minutes", "settings"),
])
def test_natural_variations(said, expected):
    found = R.match(P.normalize(said))
    assert found is not None and found[0].name == expected, (said, found and found[0].name)


@pytest.mark.parametrize("said,context,answer", [
    ("dismiss", R.ALARM, "d"), ("stop the alarm", R.ALARM, "d"), ("snooze", R.ALARM, "z"),
    ("snooze for ten minutes", R.ALARM, "z:10"), ("remind me in 15 minutes", R.ALARM, "z:15"),
    ("done", R.CHECKIN, "d"), ("still going until 4", R.CHECKIN, "g:4"), ("failed", R.CHECKIN, "f"),
    ("skipped", R.CHECKIN, "s"), ("later", R.CHECKIN, "l"),
    ("yes", R.PROPOSAL, "y"), ("reject", R.PROPOSAL, "n"), ("repeat", R.PROPOSAL, "r"),
    ("shorten it", R.COLLISION, "s"), ("move the rest", R.COLLISION, "m"), ("leave it", R.COLLISION, "l"),
    ("keep", R.CAP, "k"), ("split it", R.CAP, "p"), ("drop it", R.CAP, "d"),
])
def test_prompt_answers(said, context, answer):
    cmd, groups = R.match(P.normalize(said), context)
    assert cmd.handler(None, groups) == answer


def test_prompt_words_dont_leak_into_main_commands():
    assert R.match("snooze") is None and R.match("dismiss") is None


# ======================= parsing times, dates, numbers =======================

@pytest.mark.parametrize("said,expected", [
    ("at 3 pm", time(15, 0)), ("at 3", time(15, 0)), ("at 9", time(9, 0)), ("at 10 30", time(10, 30)),
    ("at 10:30 pm", time(22, 30)), ("half past nine", time(9, 30)), ("quarter to five", time(16, 45)),
    ("at noon", time(12, 0)), ("tomorrow at 9", time(9, 0)), ("at 7 am", time(7, 0)), ("at twelve thirty", time(12, 30)),
])
def test_time_parsing(said, expected):
    assert P.extract_time(P.normalize(said))[0] == expected


def test_bare_numbers_are_not_times():
    assert P.extract_time(P.normalize("read 10 pages"))[0] is None


@pytest.mark.parametrize("said,expected", [
    ("for 45 minutes", 45), ("for an hour", 60), ("for half an hour", 30), ("for an hour and a half", 90),
    ("for 1 hour 30 minutes", 90), ("for two hours", 120), ("for 90 mins", 90), ("for forty-five minutes", 45),
])
def test_duration_parsing(said, expected):
    assert P.extract_duration(P.normalize(said))[0] == expected


@pytest.mark.parametrize("said,expected", [
    ("today", TODAY), ("tomorrow", TODAY + timedelta(days=1)), ("next sunday", date(2026, 10, 11)),
    ("on friday", date(2026, 10, 9)), ("monday", TODAY), ("next monday", date(2026, 10, 12)),
    ("in 3 days", date(2026, 10, 8)), ("on the 12th of october", date(2026, 10, 12)), ("october 20th", date(2026, 10, 20)),
    ("yesterday", date(2026, 10, 4)), ("last friday", date(2026, 10, 2)),
])
def test_date_parsing(said, expected):
    assert P.extract_date(P.normalize(said), TODAY)[0] == expected


@pytest.mark.parametrize("said,expected", [("urgent", 1), ("high priority", 2), ("priority 3", 3), ("low", 4),
                                           ("important", 2), ("normal priority", 3)])
def test_priority_parsing(said, expected):
    assert P.extract_priority(P.normalize(said))[0] == expected


def test_number_words_and_ordinals():
    assert P.normalize("one hundred twenty pages") == "120 pages"
    assert P.parse_number("the second one") == 2 and P.parse_number("number three") == 3


# ======================= timetable by voice =======================

def test_add_task_with_everything_in_one_sentence(app):
    io_ = talk(app, "add a task read for 45 minutes at 3 pm, high priority")
    assert tasks(app) == [("read", "pending", time(15, 0), 45, 2)]
    assert io_.said[-1] == "Added read, 45m, high priority, today at 3 pm."


def test_follow_up_questions_for_missing_duration_and_priority(app):
    io_ = talk(app, "add a task write report", "an hour", "urgent")
    assert "How long will write report take?" in io_.prompts
    assert "What priority: urgent, high, normal or low?" in io_.prompts
    assert tasks(app) == [("write report", "pending", None, 60, 1)]


def test_follow_up_retries_until_it_understands(app):
    talk(app, "add a task stretch", "banana", "20 minutes", "low")
    assert tasks(app)[0][3] == 20


def test_add_for_tomorrow(app):
    talk(app, "remind me to call mom tomorrow at 9 for half an hour normal priority")
    assert tasks(app, TODAY + timedelta(days=1)) == [("call mom", "pending", time(9, 0), 30, 3)]


def test_cancel_at_any_point(app):
    io_ = talk(app, "add a task write report", "cancel")
    assert tasks(app) == [] and io_.said[-1] == "Cancelled. Nothing was changed."
    io_ = talk(app, "add a task write report", "30 minutes", "never mind")
    assert tasks(app) == []


def test_silence_gives_up_without_acting(app):
    io_ = talk(app, "add a task write report", "", "", "")
    assert tasks(app) == [] and "Cancelled" in io_.said[-1]


def test_not_understood_gives_an_example_and_does_nothing(app):
    io_ = talk(app, "make me a sandwich")
    assert io_.said[-1].startswith("Sorry, I didn't understand 'make me a sandwich'. You could say:")
    assert tasks(app) == []


def test_low_confidence_does_nothing_and_asks_to_repeat(app):
    """v1.5.1 rule (replaces the v1.5 read-back-and-confirm): low confidence never acts."""
    add(app, "report")
    io_ = talk(app, ("mark report done", LOW_CONFIDENCE - 0.1))
    assert io_.said[-1] == ("I heard: mark report done. I'm not sure I heard that right, so I did nothing. "
                            "Please repeat or rephrase.")
    assert tasks(app)[0][1] == "pending"
    talk(app, ("mark report done", LOW_CONFIDENCE + 0.1))
    assert tasks(app)[0][1] == "done"


def test_ambiguous_name_lists_matches_and_picks_by_number(app):
    add(app, "write report", start=time(10, 0))
    add(app, "read report", start=time(11, 0))
    io_ = talk(app, "mark report done", "the second one")
    assert any(p.startswith("I found 2. 1: ") for p in io_.prompts)
    with app.Session() as s:
        done = [t.title for t in svc.tasks_for_day(s, TODAY) if t.status == "done"]
    assert done == ["read report"]


def test_mark_it_done_uses_the_current_task(app):
    add(app, "report", start=time(8, 0), minutes=60)
    talk(app, "mark it done")
    assert tasks(app)[0][1] == "done"


def test_done_asks_contribution_for_a_linked_goal(app):
    with app.Session() as s:
        g = tr.create_goal(s, PeriodKind.DAY, TODAY, "read", 20, "pages", today=TODAY)
        svc.add_task(s, "read ch 1", 30, goal_id=g.id, planned_for=TODAY, today=TODAY)
    io_ = talk(app, "I finished read ch 1", "12")
    assert "read 12/20 pages" in io_.said[-1]


def test_overlap_is_refused_by_voice_like_typing(app):
    add(app, "meeting", start=time(15, 0), minutes=60)
    io_ = talk(app, "add a task call mom at 3 30 pm for 30 minutes normal priority")
    assert io_.said[-1].startswith("I can't do that. 'call mom' (15:30-16:00) overlaps task 1 'meeting' (15:00-16:00)")
    assert [t[0] for t in tasks(app)] == ["meeting"]


def test_move_pins_and_overlap_move_refused(app):
    a = add(app, "report", start=time(10, 0), placement=Placement.AUTO.value)
    add(app, "email", start=time(12, 0), minutes=30)
    io_ = talk(app, "move report to 12 15")
    assert "overlaps" in io_.said[-1]
    talk(app, "move report to 4 pm")
    with app.Session() as s:
        t = svc.get_task(s, a)
        assert (t.start_time, t.placement) == (time(16, 0), "pinned")


def test_put_after_and_unpin(app):
    a = add(app, "report", start=time(10, 0), placement=Placement.AUTO.value)
    add(app, "email", start=time(13, 0), minutes=30)
    talk(app, "put report after email")
    with app.Session() as s:
        assert svc.get_task(s, a).start_time == time(13, 30)
    talk(app, "unpin the report")
    with app.Session() as s:
        assert svc.get_task(s, a).placement == "auto"


def test_edit_and_delete_task(app):
    add(app, "report", minutes=30)
    talk(app, "rename report to quarterly report")
    talk(app, "change the duration of quarterly report to 90 minutes")
    talk(app, "make quarterly report urgent")
    assert tasks(app) == [("quarterly report", "pending", None, 90, 1)]
    io_ = talk(app, "delete the task quarterly report", "no")
    assert len(tasks(app)) == 1 and "Delete quarterly report" in io_.prompts[0]
    talk(app, "delete the task quarterly report", "yes")
    assert tasks(app) == []


def test_failed_records_cannot_be_deleted_by_voice(app):
    a = add(app, "report")
    with app.Session() as s:
        svc.fail_task(s, a, "sick")
    io_ = talk(app, "delete the task report")
    assert "couldn't find" in io_.said[-1]


def test_plan_my_day_by_voice(app):
    add(app, "meeting", start=time(10, 0))
    add(app, "deep work", minutes=60, priority=1)
    add(app, "email", minutes=30, priority=3)
    io_ = talk(app, "plan my day")
    assert io_.said[-1] == "Planned today: 9 am deep work, 10 am meeting, 11 am email."


def test_whats_next_and_my_day(app):
    add(app, "report", start=time(9, 0))
    add(app, "email", start=time(11, 0), minutes=30)
    assert talk(app, "what's next").said[-1] == "Next: report at 9 am for 1h."
    assert talk(app, "what's my day like").said[-1].startswith("Today: 2 to do. 9 am report, 11 am email.")


def test_add_several_tasks(app):
    talk(app, "add several tasks for tomorrow", "gym for an hour low", "email for 30 minutes normal", "that's all")
    assert [t[0] for t in tasks(app, TODAY + timedelta(days=1))] == ["gym", "email"]


def test_link_and_show_day(app):
    with app.Session() as s:
        tr.create_goal(s, PeriodKind.MONTH, TODAY, "ship tomits", today=TODAY)
    add(app, "report")
    talk(app, "link report to goal ship tomits")
    with app.Session() as s:
        assert svc.tasks_for_day(s, TODAY)[0].goal.title == "ship tomits"
    assert "Tomorrow" in talk(app, "what do I have tomorrow").said[-1] or "Nothing on tomorrow" in talk(app, "what do i have tomorrow").said[-1]


# ======================= mandatory reason =======================

def test_fail_without_reason_leaves_task_unchanged(app):
    add(app, "report", start=time(10, 0), placement=Placement.AUTO.value)
    io_ = talk(app, "I failed the report", "cancel")
    assert "What's the reason report failed?" in io_.prompts
    assert tasks(app)[0][1] == "pending"
    talk(app, "skip the report", "", "", "")      # silence: no reason
    assert tasks(app)[0][1] == "pending"
    with app.Session() as s:
        assert s.query(TaskReason).count() == 0


def test_fail_reason_read_back_corrected_saved_then_reschedule_accepted(app):
    a = add(app, "report", start=time(10, 0), placement=Placement.AUTO.value)
    io_ = talk(app, "I failed the report", "I got sick", "change sick to called away", "save", "yes")
    assert "I heard: I got sick. Say save, redo, or change something to something." in io_.prompts
    assert "I heard: I got called away. Say save, redo, or change something to something." in io_.prompts
    assert any(p.startswith("Here's the new plan: a new copy of report to today at 9 am") for p in io_.prompts)
    assert io_.said[-1].startswith("Plan updated.")
    with app.Session() as s:
        orig = svc.get_task(s, a)
        assert orig.status == "failed" and orig.latest_reason == "I got called away"
        r = orig.reasons[0]
        assert (r.task_title, r.task_date, r.priority) == ("report", TODAY, 3)  # stored like a typed reason
        assert len(orig.rescheduled_copies) == 1


def test_reason_redo(app):
    a = add(app, "report")
    talk(app, "skip the report", "tired", "redo", "not needed today", "save", "no")
    with app.Session() as s:
        assert svc.get_task(s, a).latest_reason == "not needed today"


def test_rejecting_the_proposal_changes_nothing_and_undo_needs_yes(app):
    a = add(app, "report", start=time(10, 0), placement=Placement.AUTO.value)
    io_ = talk(app, "I failed the report", "power cut", "save", "no")
    assert "stays failed with its reason" in io_.said[-1]
    talk(app, "reschedule the report", "yes")
    io_ = talk(app, "undo the reschedule", "no")
    with app.Session() as s:
        assert len(svc.get_task(s, a).rescheduled_copies) == 1
    talk(app, "undo the reschedule", "yes")
    with app.Session() as s:
        t = svc.get_task(s, a)
        assert t.rescheduled_copies == [] and t.latest_reason == "power cut"


def test_proposal_repeat_then_accept(app):
    add(app, "report", start=time(10, 0), placement=Placement.AUTO.value)
    io_ = talk(app, "I failed the report", "sick", "save", "repeat", "yes")
    assert sum(p.startswith("Here's the new plan") for p in io_.prompts) == 2


# ======================= overrun, collision, cap by voice =======================

def test_extend_by_voice_shifts_next_task(app):
    app.clock_box["now"] = datetime(2026, 10, 5, 10, 50)
    a = add(app, "report", start=time(10, 0), placement=Placement.AUTO.value)
    b = add(app, "email", start=time(11, 0), minutes=30, placement=Placement.AUTO.value)
    io_ = talk(app, "I'm still working on the report until 11 30", "yes")
    with app.Session() as s:
        assert svc.get_task(s, a).end_at.time() == time(11, 30)
        assert svc.get_task(s, b).start_time == time(11, 30)


def test_collision_warning_by_voice_shorten(app):
    app.clock_box["now"] = datetime(2026, 10, 5, 10, 50)
    a = add(app, "report", start=time(10, 0), placement=Placement.AUTO.value)
    add(app, "meeting", start=time(11, 30))
    io_ = talk(app, "extend report until 12 pm", "shorten", "yes")
    assert any("would run into meeting at 11:30, which is fixed" in p for p in io_.prompts)
    with app.Session() as s:
        assert svc.get_task(s, a).end_at.time() == time(11, 30)


def test_collision_leave_it(app):
    app.clock_box["now"] = datetime(2026, 10, 5, 10, 50)
    a = add(app, "report", start=time(10, 0), placement=Placement.AUTO.value)
    add(app, "meeting", start=time(11, 30))
    talk(app, "extend report until 12 pm", "leave it")
    with app.Session() as s:
        assert svc.get_task(s, a).duration_min == 60


def test_reschedule_cap_by_voice(app):
    t = add(app, "essay", start=time(10, 0), placement=Placement.AUTO.value)
    for i in range(2):
        talk(app, "I failed the essay", f"miss {i}", "save", "yes")
    io_ = talk(app, "I failed the essay", "again", "save", "split", "yes")
    assert any("has now been rescheduled 3 times" in p for p in io_.prompts)
    assert [x[0] for x in tasks(app) if x[1] == "pending"] == ["essay (part 1)", "essay (part 2)"]


# ======================= alarms and check-ins by voice =======================

def test_snooze_and_dismiss_alarm_by_voice(app):
    t = add(app, "report", start=time(8, 33))
    alarm = Alarm(HEADS_UP, t, "report", datetime(2026, 10, 5, 8, 33), datetime(2026, 10, 5, 9, 33))
    app.ringer.ring(alarm)
    io_ = ScriptedIO(["snooze for ten minutes"])
    app.voice_mode = True
    app.voice_attend(io_)
    assert not app.ringer.is_ringing
    assert app.ringer.snoozed()[0][1] == NOW + timedelta(minutes=10)
    assert io_.grammars[0] and "dismiss" in io_.grammars[0]    # only listens for dismiss / snooze
    app.clock_box["now"] = NOW + timedelta(minutes=10)
    app.ringer.tick()
    app.voice_attend(ScriptedIO(["dismiss"]))
    assert not app.ringer.is_ringing and app.ringer.snoozed() == []


def test_checkin_still_going_by_voice(app):
    app.clock_box["now"] = datetime(2026, 10, 5, 11, 0)
    a = add(app, "report", start=time(10, 0), placement=Placement.AUTO.value)
    app.checkins.put(Alarm(END_CHECK, a, "report", datetime(2026, 10, 5, 10), datetime(2026, 10, 5, 11)))
    app.voice_mode = True
    app.voice_attend(ScriptedIO(["still going for 20 minutes", "yes"]))
    with app.Session() as s:
        assert svc.get_task(s, a).end_at.time() == time(11, 20)


def test_checkin_failed_by_voice_needs_reason(app):
    app.clock_box["now"] = datetime(2026, 10, 5, 11, 0)
    a = add(app, "report", start=time(10, 0), placement=Placement.AUTO.value)
    app.checkins.put(Alarm(END_CHECK, a, "report", datetime(2026, 10, 5, 10), datetime(2026, 10, 5, 11)))
    app.voice_mode = True
    app.voice_attend(ScriptedIO(["failed", "cancel"]))
    assert tasks(app)[0][1] == "pending"


def test_reminder_answered_by_voice(app):
    with app.Session() as s:
        app.pending_reminder = tr.missing_fill_ins(s, TODAY)
    app.voice_mode = True
    app.voice_attend(ScriptedIO(["yes",
                                 "read 10 pages", "save", "read before bed", "save",        # day
                                 "read 110 pages", "save", "read every night", "save",      # week
                                 "read 500 pages", "save", "read daily", "save"]))          # month
    with app.Session() as s:
        assert tr.missing_fill_ins(s, TODAY) == []
        assert tr.goals_for_period(s, PeriodKind.MONTH, TODAY)[0].target == 500


# ======================= tracking by voice =======================

def test_goal_chain_log_progress_and_read_it_back(app):
    talk(app, "add a monthly goal read 500 pages", "save")
    talk(app, "new weekly goal read 110 pages linked to read 500 pages", "save")
    io_ = talk(app, "add a daily goal read 10 pages linked to read 110 pages", "save")
    assert io_.said[-1] == "Created the daily goal read 10 pages, target 10 pages, linked to read 110 pages."
    io_ = talk(app, "I read 10 pages")
    assert io_.said[-1] == "Logged 10 pages. read 10 pages 10/10 pages; read 110 pages 10/110 pages; read 500 pages 10/500 pages."
    io_ = talk(app, "how am I doing on this month's goal")
    assert io_.said[-1] == "month goal read 500 pages: 10/500 pages."


def test_goal_title_is_read_back_and_editable(app):
    io_ = talk(app, "add a weekly goal", "finish chapter three", "change three to four", "save")
    assert "What's the goal?" in io_.prompts
    with app.Session() as s:
        assert tr.goals_for_period(s, PeriodKind.WEEK, TODAY)[0].title == "finish chapter four"


def test_goal_period_follow_up(app):
    talk(app, "add a goal call mom", "this week", "save")
    with app.Session() as s:
        assert tr.goals_for_period(s, PeriodKind.WEEK, TODAY)[0].title == "call mom"


def test_goal_done_edit_and_delete(app):
    talk(app, "add a daily goal call mom", "save")
    talk(app, "mark goal call mom done")
    with app.Session() as s:
        assert tr.progress(tr.goals_for_period(s, PeriodKind.DAY, TODAY)[0]).done
    talk(app, "rename goal call mom to call mum", "save")
    talk(app, "add a daily goal spare", "save")
    io_ = talk(app, "delete goal spare", "yes")
    with app.Session() as s:
        assert [g.title for g in tr.goals_for_period(s, PeriodKind.DAY, TODAY)] == ["call mum"]


def test_unit_mismatch_refused_by_voice(app):
    talk(app, "add a weekly goal read 110 pages", "save")
    io_ = talk(app, "add a daily goal run 5 km linked to read 110 pages", "save")
    assert io_.said[-1].startswith("I can't do that.")


def test_process_sacrifice_review_by_voice(app):
    io_ = talk(app, "set this week's process", "read every night before bed", "save")
    assert "What's the process?" in io_.prompts and io_.said[-1] == "Process saved for this week."
    talk(app, "add a sacrifice no phone after 10, planned")
    talk(app, "I gave up sugar")
    talk(app, "mark sacrifice no phone as made")
    io_ = talk(app, "write my review for today", "good focus, bad sleep", "save")
    with app.Session() as s:
        week = tr.get_entry(s, PeriodKind.WEEK, TODAY)
        day = tr.get_entry(s, PeriodKind.DAY, TODAY)
        assert week.process == "read every night before bed"
        assert [(x.text, x.status) for x in day.sacrifices] == [("no phone after 10", "made"), ("sugar", "made")]
        assert day.review == "good focus, bad sleep"


def test_locked_period_refused_by_voice(app):
    io_ = talk(app, "add a sacrifice no phone for yesterday")
    assert io_.said[-1] == "I can't do that. Sun 04 Oct 2026 has ended; its sacrifices are read-only."
    io_ = talk(app, "write my review for last month", "it was fine", "save")
    assert io_.said[-1].startswith("I can't do that. The review for September 2026 closed")


def test_open_views_and_navigate(app):
    talk(app, "add a weekly goal walk daily", "save")
    io_ = talk(app, "open this week")
    assert io_.said[-1].startswith("This week: walk daily, not done.")
    assert (app.voice_state.view_kind, app.voice_state.view_start) == ("week", date(2026, 10, 4))
    talk(app, "go to the next week")
    assert app.voice_state.view_start == date(2026, 10, 11)
    talk(app, "go back")
    assert app.voice_state.view_kind is None


def test_voice_uses_open_page_as_default_period(app):
    app.voice_state.view_kind, app.voice_state.view_start = "month", date(2026, 10, 1)
    talk(app, "add a goal save money", "save")
    with app.Session() as s:
        assert tr.goals_for_period(s, PeriodKind.MONTH, TODAY)[0].title == "save money"


def test_remove_last_log_needs_yes(app):
    talk(app, "add a daily goal read 10 pages", "save")
    talk(app, "I read 4 pages")
    talk(app, "remove the last log", "no")
    with app.Session() as s:
        assert len(tr.goals_for_period(s, PeriodKind.DAY, TODAY)[0].logs) == 1
    talk(app, "remove the last log", "yes")
    with app.Session() as s:
        assert tr.goals_for_period(s, PeriodKind.DAY, TODAY)[0].logs == []


# ======================= history, settings, voice controls =======================

def test_history_by_voice_filtered(app):
    with app.Session() as s:
        g = tr.create_goal(s, PeriodKind.MONTH, TODAY, "fitness", today=TODAY)
        t = svc.add_task(s, "run", 30, goal_id=g.id, planned_for=TODAY, today=TODAY)
        svc.fail_task(s, t.id, "rain")
        u = svc.add_task(s, "read", 30, planned_for=TODAY, today=TODAY)
        svc.skip_task(s, u.id, "tired")
    io_ = talk(app, "show my failures for fitness")
    assert io_.said[-1] == "1 missed for fitness. Monday 05 October, run, failed, because rain."
    assert talk(app, "show my history this month").said[-1].startswith("2 missed for all goals.")


def test_settings_by_voice(app):
    talk(app, "set my day from 8 am to 10 pm")
    talk(app, "set snooze to 10 minutes")
    talk(app, "turn off spoken replies")
    talk(app, "set the wake phrase to hello tomits")
    talk(app, "turn on hands free")
    io_ = talk(app, "set the push to talk key to d")
    assert "already a menu key" in io_.said[-1]
    talk(app, "set the push to talk key to b")
    st = ui.load_settings(app.settings_file)
    assert (st.day_start, st.day_end, st.snooze_minutes, st.spoken_replies, st.wake_phrase, st.hands_free,
            st.push_to_talk_key) == ("08:00", "22:00", 10, False, "hello tomits", True, "b")
    app.settings.hands_free = False


def test_mute_by_voice_and_key(app):
    talk(app, "mute")
    assert app.settings.muted
    app.toggle_mute()
    assert not app.settings.muted


def test_quit_and_help(app):
    talk(app, "quit")
    assert app.quit_requested
    assert talk(app, "what can I say").said[-1].startswith("You can say:")


# ======================= engine fallbacks (no real mic) =======================

class FakeRecognizer:
    def __init__(self, text="mark report done", conf=0.9, fail=False):
        self.text, self.conf, self.fail, self.calls = text, conf, fail, []

    def listen(self, grammar=None, **kw):
        self.calls.append(grammar)
        if self.fail:
            raise RuntimeError("device unplugged")
        return Heard(self.text, self.conf)


def _voice_io(app, rec):
    from tomits.voice.engine import VoiceIO
    out = io.StringIO()
    typed = []
    vio = VoiceIO(app, rec, None, Console(file=out, width=160), lambda p: (typed.append(p), Heard("typed answer"))[1])
    return vio, out, typed


def test_listening_indicator_and_tone_paused_while_listening(app):
    seen = {}

    class Rec(FakeRecognizer):
        def listen(self, grammar=None, **kw):
            seen["quiet"] = app.ringer.is_quiet
            return Heard("dismiss", 0.9)

    t = add(app, "report", start=time(9, 0))
    app.ringer.ring(Alarm(HEADS_UP, t, "report", datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 10)))
    vio, out, _ = _voice_io(app, Rec())
    vio.listen("Say dismiss", ["dismiss"])
    assert seen["quiet"] is True and not app.ringer.is_quiet
    assert "LISTENING" in out.getvalue()


def test_muted_mic_falls_back_to_typing(app):
    app.settings.muted = True
    rec = FakeRecognizer()
    vio, out, typed = _voice_io(app, rec)
    assert vio.listen("Which task?").text == "typed answer"
    assert rec.calls == [] and "muted" in out.getvalue()


def test_mic_failure_is_shown_and_falls_back(app):
    vio, out, typed = _voice_io(app, FakeRecognizer(fail=True))
    assert vio.listen("Which task?").text == "typed answer"
    assert "microphone failed (device unplugged)" in out.getvalue()


def test_no_voice_engine_is_reported_not_silent(app, monkeypatch):
    from tomits.voice import engine
    def boom(path):
        raise engine.VoiceUnavailable("no microphone was found.")
    monkeypatch.setattr(engine, "WhisperRecognizer", lambda *a, **k: boom(None))
    monkeypatch.setattr(ui.Prompt, "ask", classmethod(lambda cls, *a, **k: "add a task stretch for 10 minutes low"))
    assert app.voice_turn() == "add_task"      # the same command, typed instead
    assert app.voice_error == "Voice isn't available: no microphone was found. Using typed input."
    assert tasks(app)[0][:4] == ("stretch", "pending", None, 10)


def test_whisper_result_to_heard():
    """(v1.5.1: replaces the Vosk result test) word probabilities -> confidence;
    segments Whisper itself marks as silence are dropped."""
    import numpy as np
    from types import SimpleNamespace as NS
    from tomits.voice.stt import WhisperEngine
    eng = WhisperEngine.__new__(WhisperEngine)
    segs = [NS(text=" Snooze", no_speech_prob=0.1, avg_logprob=-0.2, words=[NS(probability=0.8)]),
            NS(text=" thank you", no_speech_prob=0.9, avg_logprob=-1.2, words=[NS(probability=0.3)])]
    eng.model = NS(transcribe=lambda *a, **k: (iter(segs), None))
    h = eng.transcribe(np.ones(16000, dtype=np.float32) * 0.1)
    assert (h.text, round(h.confidence, 2)) == ("Snooze", 0.8)


# ======================= the done-means walk-through =======================

def test_full_day_by_voice(app):
    talk(app, "add a monthly goal read 500 pages", "save")
    talk(app, "add a task read for 45 minutes high priority")
    talk(app, "add a task report for an hour urgent")
    talk(app, "add a task email for 30 minutes low")
    assert talk(app, "plan my day").said[-1] == "Planned today: 9 am report, 10 am read, 10:45 am email."
    app.clock_box["now"] = datetime(2026, 10, 5, 10, 0)
    talk(app, "done with the report")
    talk(app, "I finished read")                              # not linked to a goal: no extra question
    io_ = talk(app, "I failed email", "ran out of time", "save", "yes")
    assert io_.said[-1].startswith("Plan updated.")
    talk(app, "I read 25 pages")
    talk(app, "write my review for today", "solid morning", "save")
    t = add(app, "call", start=time(12, 0), minutes=15)
    app.ringer.ring(Alarm(HEADS_UP, t, "call", datetime(2026, 10, 5, 12), datetime(2026, 10, 5, 12, 15)))
    app.voice_mode = True
    app.voice_attend(ScriptedIO(["snooze"]))
    assert len(app.ringer.snoozed()) == 1
    with app.Session() as s:
        statuses = {t.title: t.status for t in svc.tasks_for_day(s, TODAY)}
        assert statuses["report"] == "done" and statuses["read"] == "done" and statuses["email"] == "failed"
        assert tr.progress(tr.goals_for_period(s, PeriodKind.MONTH, TODAY)[0]).text == "25/500 pages"
        assert tr.get_entry(s, PeriodKind.DAY, TODAY).review == "solid morning"


def test_voice_examples_avoid_the_removed_sample_text():
    """v1.2 removed '500' / '110' / '10 pages' samples; spoken examples must not bring them back."""
    from pathlib import Path
    for path in (Path(ui.__file__).parent / "voice").glob("*.py"):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            assert "e.g." not in line, f"{path.name}:{n}"
            assert not re.search(r"\b(500|110)\b|\b10 pages\b", line), f"{path.name}:{n}: {line.strip()}"
