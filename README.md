# tomits

Personal task manager that runs on your own computer: a local web app (and the original terminal version).
Your data stays on this PC; nothing is sent anywhere and no account is needed.

## Start (Windows)

1. Install Python 3.10 or newer from python.org (tick "Add python.exe to PATH").
2. Double-click `start-tomits.bat`. The first time it asks before downloading what it needs
   (about 10 MB, plus an optional 130 MB for voice), then opens your browser at http://127.0.0.1:3000
   (or the next free port; the window says which).
3. Keep that window open while you use tomits; close it to stop. Every change is saved as you make it.

A new install starts with an empty database and a short setup. Mac and Linux launchers are planned.

- Terminal version: `run.bat` (same database; changes show up live in the browser).
- Tests: `test.bat`. Alarm tone check: `sound_test.bat`.
- Voice: `voice_setup.bat` (installs the speech packages and downloads the models; asks first, shows sizes),
  `voice_mictest.bat`, `voice_try.bat`, `voice_benchmark.bat`. Speech is recognised on this PC (faster-whisper).
- Data: `data\tomits.db` and `data\settings.json` (override the folder with the `TOMITS_DB` environment variable).
  Before any database update a timestamped backup is written next to it. `data\` is never committed (.gitignore).

## The web app

- Six layouts (Timeline, Calendar grid, Board, Focus on now, Split dashboard, Voice first): the **Layout** button
  in the top bar (or `L`). Every layout has every screen and action; your choice and theme are remembered.
- The box at the top takes typed commands (`Ctrl K`), the same ones you can say after pressing `V`.
- Shortcuts: `A` add, `D` done, `F` failed, `S` skip, `X` still going, `P` plan my day, `N` add a note, `U` undo,
  `/` search, `?` help.
- **Remember** (the tab on the right in every layout): short notes of things not to forget, with or without a time.
  Added and deleted only. When a note's time comes you get one banner and one desktop notification; it then stays
  under Overdue until you delete it. Voice: "remember to ...", "delete the note ...", "what do I need to remember".
- **Your data:** Settings -> Export all data (one file, also saved in `data\exports`); importing an export replaces
  all data after a backup.
- After updating tomits' files, restart it (close its window, run `start-tomits.bat`); a banner says when that's needed.
- Every action can be undone from the toast that follows it. Failure reasons are never deleted.
- Alarms ring in the browser tab (and as a Windows notification when the tab is in the background) while tomits runs.

## Timetable keys

`a` add task now, `n` enter several tasks for a day, `p` plan my day / re-plan, `e` move / set a task's time (pins it),
`u` unpin, `d` done, `f` fail, `s` skip, `x` still going (extend), `r` reschedule a missed task,
`z` undo last reschedule, `h` history of misses, `c` change a task, `typed` keep a title as typed, `del` delete a task,
`l` link task to goal,
`g` day / week / month pages, `t` view another day, `o` settings (snooze length, day window, default task length,
`e` export, `m` import), `note` remember something, `delnote` delete a note, `notes` all notes,
`v` talk, `m` mute / unmute the mic, `Enter` refresh / answer, `q` quit.

Tasks with a start time can't overlap another pending or done task on the same day. Back-to-back is fine.

**A time in the title** (with am / pm, 24-hour, after "at", or a range, optionally with a day word like
tomorrow or a weekday) becomes the task's fixed start time and is taken out of the title; everywhere (web, quick-add
box, voice, terminal), when adding or editing. A range sets the length; a single time gets the default length
(30 min, a setting). Unclear am / pm is settled by your day window, or you're asked. Plain numbers are left alone. "Keep title as typed" undoes the reading.
A task with its own time owns it: if a planned task is in the way you get a reschedule proposal; if a fixed or
pinned one is, it's refused and both are named.

## Planning your day (`p`)

Give tasks a priority (1 urgent, 2 high, 3 normal, 4 low) and a duration. A task with a start time is fixed;
the rest are placed by `p` in the free gaps of your day window (default 09:00-21:00, change it with `o`),
highest priority first. If similar tasks have enough history, a task goes near the time you usually completed
them; otherwise earlier in the day by priority. Each placed task shows why it went there.
Tasks that don't fit stay on the day in a "didn't fit" list. Moving a task (`e`, a time or "before 3" / "after 3")
pins it, so re-planning never moves it; `u` unpins it. Past days are never changed.

## Day / week / month pages (`g`)

One page per day, week (starts Sunday) and month: goals, sacrifices, process, review.
Goals live only here. A goal has a target and a unit, or no target (done / not done),
and can link up one level (day -> week -> month); progress rolls up the links.
When a period ends, its page becomes read-only; the review stays open until the end of the next day.
Until today, this week and this month each have a goal and a process, you're reminded every 5 minutes.

Keys: `d`/`w`/`m` switch view, `[` `]` previous/next, `c` current, `n` new goal, `e` edit goal,
`x` delete goal, `l` log progress, `u` remove a log, `k` mark done/not done, `p` process,
`s` add sacrifice, `h` mark a sacrifice as made, `del` delete a sacrifice, `r` review, `b` back.
Sacrifices can't be edited: add, mark as made, or delete (until the period ends).

## When things go wrong (rescheduling)

Failing or skipping a task always needs a reason. The failed task stays on its day as a record, and tomits
proposes a new plan: a linked copy goes into the free time left today, then tomorrow (never later). Unpinned planned
tasks may shift, and more important tasks may push less important ones. Nothing changes until you accept,
and `z` undoes the last accepted reschedule. If a task runs over (`x`, or "still going" when its end alarm rings),
it's extended and the tasks behind it shift. If that would hit a fixed or pinned task, you're warned and choose to
shorten, move the rest after it, or leave it. After 3 reschedules of the same task you're asked to keep, split
or drop it. `h` lists past misses with their reasons, by goal and date.

## Alarms

A task with a start time rings 5 minutes before it starts and again when its time is up.
A ringing alarm plays a tone until you dismiss or snooze it (press Enter, then `d` or `z`),
and stops by itself after 2 minutes. Snooze length is set with `o` (default 5 minutes).
Alarms only ring while tomits is open.

## Voice

Press `v` (then Enter) and speak; listening stops after a short pause. Everything can be done by voice, for example:
"add a task read for 45 minutes at 3 pm, high priority", "plan my day", "mark it done", "I failed the report"
(you'll be asked for the reason), "I'm still working on the report until 4", "undo the reschedule",
"add a weekly goal run 12 km linked to run 40 km", "I ran 3 km", "write my review for today", "open this week",
"how am I doing on this month's goal", "show my failures for fitness last month", "snooze for 10 minutes".
Say "cancel" at any time, and "what can I say" for more. Free text is read back before it's saved; deleting,
undoing and accepting a reschedule need a spoken "yes". Speech recognition is offline (faster-whisper); a small local language model (Ollama, optional) understands
rephrased commands but can only pick existing commands. What it heard and how it understood it are shown before it
acts; unclear or low-confidence speech does nothing. Every attempt is logged (`o` -> `l`). Replies use the Windows
voices and can be turned off ("turn off spoken replies"). Hands-free mode with a wake phrase is off by default
("turn on hands free"). If there's no mic, `v` lets you type the same command in words.
