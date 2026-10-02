# tomits: task checklist

## v1.0: tracking (done)

- [x] SQLite + SQLAlchemy models: Goal, Task, TaskReason
- [x] Tasks with a duration (accepts 25, 90m, 1h, 1h30m)
- [x] Each task can have its own goal ("what done looks like") and an optional big Goal
- [x] Goal progress auto-updates: completed tasks / total tasks
- [x] Mandatory reason when a task is failed or skipped (enforced in services and re-asked in the UI)
- [x] Plan a whole day up front (today, tomorrow, or any date), saved all-or-nothing
- [x] Add tasks on the fly (goes to the end of today)
- [x] Persistent storage survives restarts
- [x] Rich dashboard: today's tasks, open overdue tasks, goals with progress bars
- [x] One-command start on Windows: `run.bat` (installs deps first time)
- [x] Tests: progress, fail-reason rule, UI reason loop, persistence, durations (35 passing; `test.bat`)

## v1.1: day / week / month tracking (done, built after 1.2)

- [x] One page per day, week (Sunday start) and month: goals, sacrifices, process, review (`g` in the timetable)
- [x] Goals are created only on these pages; the timetable can only pick an existing, open goal
- [x] Goal = title + numeric target with unit (500 pages), or no target (done / not done)
- [x] Progress logged as dated amounts; shown as logged / target (10/500 pages)
- [x] Optional upward links day -> week -> month; progress rolls up the links (10/10, 10/110, 10/500)
- [x] Linked goals must use the same unit; a week spanning two months links to the month you pick
- [x] Timetable tasks: goal optional; `l` links/unlinks an existing task; completing a linked task asks its contribution (default 0) and logs it
- [x] Sacrifices: list of items, each planned or made; add, toggle, edit, remove while the period is open (v1.7: no more editing or toggling back; add, mark as made, delete)
- [x] Locks enforced in `tracking.py`: after a period ends, goals, sacrifices, process and progress logs are read-only; review until the end of the next day
- [x] Mandatory fill-in reminder every 5 minutes per current period missing a goal or process (toast + message + red banner); background thread, never blocks
- [x] Migration to schema v3: v1.0/v1.2 goals become current-month no-target goals, task links kept; backup `data/tomits.db.bak-v2` first
- [x] Tests: roll-up, link and unit rules, every lock and review cutoff incl. the week 27 Sep - 3 Oct 2026, reminder condition and service, task contributions, migration (158 passing)

## v1.2: alarms (done)

- [x] Optional start time per task (14:30, 930, 2pm, 2:30pm); untimed tasks get no alarms
- [x] Plan a day with a start time: tasks are timed back to back; rejected if it runs past midnight
- [x] `e` key: set, change or clear a pending task's time (re-arms its alarms)
- [x] Heads-up alarm 5 minutes before a task starts
- [x] End-of-duration check-in: done / failed / skipped / later; failed and skipped still need a reason
- [x] Windows toast (plyer) + system sound (winsound) + message in the window + "Recent alarms" panel
- [x] Alarms missed while the app was closed are listed once on startup, not replayed
- [x] Background alarm thread (`schedule`, checks every 15 s), logic in `alarms.py` with no UI code
- [x] Database migration v1 -> v2: adds the new columns, keeps data, backs up to `data/tomits.db.bak-v1` first
- [x] Tests: alarm timing, missed-at-startup, re-arming, check-in reason rule, time parsing, back-to-back planning, migration (78 passing)

## v1.2 fixes (done, before 1.3)

- [x] Removed the "Goals now" table from the timetable home screen; goals show only on the day / week / month pages. The pick-a-goal list used when linking a task stays (linking needs it).
- [x] Removed example text from every prompt ("e.g. 500", "e.g. pages, hours, km", "e.g. 14:30", "e.g. 25, 90m, 1h30m", "YYYY-MM-DD"). Prompts now read "Goal title", "Target (optional)", "Unit", "Duration", "Start time (optional)", "Which day?", "Date (blank = today)". Error messages still list accepted formats.
- [x] Sample data: none found. Your two goals ("tracker development", "complete tracker") are yours and were kept. Nothing deleted.
- [x] No overlapping tasks: enforced in `services.py` (`check_no_overlap`) for add, plan-a-day and changing a time. The message names the conflicting task, its time range and the nearest free start / end.
- [x] Alarm tone: built-in `winsound.Beep` pattern (no files, setup or online service); repeats until Dismiss or Snooze; stops by itself after 2 minutes (`ringer.py`)
- [x] Dismiss / Snooze: press Enter at any menu (timetable or tracking pages), then `d` or `z`. Snooze length is a setting (`o`, default 5 min, 1-120), saved in `data/settings.json`
- [x] If the tone can't play, the alarm still shows (red "ALARM RINGING" panel) with "Alarm sound failed: <reason>"
- [x] `sound_test.bat`: plays the tone 3 times and says OK or FAILED
- [x] Tests: overlap (partial, containment, exact match, back-to-back, pre-existing overlaps, plans, time edits), snooze timing, 2-minute stop, sound failure, settings, UI dismiss / snooze, cleanup guards (210 passing)

### How the sound was tested (a test suite can't hear it)

- **Automated:** the ringing logic runs against a fake clock and a fake tone player that counts bursts. The tests check that the tone repeats while ringing, stops after Dismiss, stops by itself at 2:00 (not at 1:59), that snooze re-rings at exactly the configured length, and that a player that raises an error produces a visible "sound failed" message while the alarm stays up. Two tests run the real background thread with the fake player.
- **Real app, scripted:** in the Linux test VM I ran the app with timed keystrokes. An alarm rang, I snoozed it with the snooze set to 1 minute, it rang again one minute later, and Dismiss cleared it. The VM has no Windows sound, so this run also showed the failure path: the red panel plus "Alarm sound failed: the built-in tone (winsound) only exists on Windows".
- **Not yet heard:** nobody has heard the real tone on your Windows PC yet. To check it, run `sound_test.bat` (you should hear 3 short beep patterns), then add a task starting 3 minutes from now and wait for it to ring. If `sound_test.bat` prints FAILED, send me the error.

## v1.3: automatic day planning (done)

- [x] Priority on every task: 1 urgent, 2 high, 3 normal (default), 4 low. Asked when adding tasks (`a`, `n`)
- [x] `p` Plan my day (any day from today on; past days refused): places movable tasks in the free gaps of the day window, highest priority first; shows the plan, what was kept, and "didn't fit"
- [x] Fixed tasks (you gave a time) and pinned tasks (you moved a planned task) never move; done tasks and planned tasks already under way only block time
- [x] History-based placement for tasks with enough similar past entries; priority fallback otherwise; a one-line reason stored and shown for every placement
- [x] Order from past days: adjacent planned tasks are swapped if the second one usually came first
- [x] Daily window setting (`o` -> `w`), default 09:00-21:00; tasks placed only inside it; fixed tasks outside it stay and block
- [x] "Didn't fit" list in priority order with durations; those tasks stay on the day, pending, without a time
- [x] Manual ordering: `e` takes a time or "before N" / "after N" and pins the task; overlapping moves refused with the conflict named; `u` unpins; re-running `p` re-plans only unpinned, unfixed tasks
- [x] Alarms work for planned tasks at their placed time (re-armed when the planner moves a task)
- [x] Migration to schema v4: priority 3 for existing tasks, existing timed tasks become "fixed"; backup `data/tomits.db.bak-v3`
- [x] Tests: priority order, fixed stay put, overflow, no-history fallback, history placement with fake history, failures pushing away, goal / title similarity, usual order, pinning across re-plans, unpin, overlapping moves refused, window edges, today after now, past days, alarms, determinism, settings, migration, UI (255 passing)

### How the planner decides (tune in `tomits/planner.py`)

**Constants** (top of the file):

| Name | Value | Meaning |
|---|---|---|
| `HISTORY_MIN_ENTRIES` | 3 | similar past tasks needed before history is used |
| `HISTORY_LOOKBACK_DAYS` | 90 | how far back to look |
| `FAIL_WEIGHT` | 1.0 | one failure cancels this many completions at that hour |
| `NEIGHBOR_WEIGHT` | 0.5 | share of each entry's weight given to the hour before and after |
| `TITLE_SIMILARITY` | 0.5 | shared-word ratio needed for "similar title" |
| `ORDER_MIN_DAYS` | 2 | extra days needed before "B usually comes before A" is used |
| `SLOT_STEP_MIN` | 5 | placements snap to 5-minute steps |

**Which past tasks count (the history pool):** tasks on earlier days within the lookback, with a start time, and status done or failed. Skipped and still-pending tasks don't count. Neither does anything on the day being planned or later.

**Similar-task match:** a past task is similar if any of these hold:

1. It has the same goal (both linked to the same goal).
2. Its title has the same set of words. Titles are lower-cased and reduced to letters, so digits and punctuation are dropped ("Gym #2!" = "gym").
3. Shared words divided by all distinct words across both titles is at least `TITLE_SIMILARITY`. For example, "read book" vs "read the book" = 2/3, which counts.

**History score:** each similar entry adds +1 if done, or -`FAIL_WEIGHT` if failed, to the hour it started in. It adds half that (`NEIGHBOR_WEIGHT`) to the hour before and the hour after, so 18:50 and 19:10 support each other. The best hour is the one with the highest total. Ties go to the hour with more completions, then the earlier hour. The target time is the average start time of the done entries in that hour, rounded to 5 minutes.

- With fewer than `HISTORY_MIN_ENTRIES` similar entries, the planner uses the fallback, and the reason says "no history" or "too little history (n similar, need 3)".
- If no hour scores above 0 (mostly failures), it also uses the fallback: "history shows mostly misses".

**Placement:**

1. Movable tasks are processed in order of priority, then shorter duration first, then the order they were added.
2. With a target time, a task takes the start time closest to the target that fits in a free gap. Ties go to the earlier time. If the result is 30 min or more from the target, the reason adds "nearest free slot HH:MM".
3. Without a target, a task takes the earliest free slot that fits, so higher priority ends up earlier in the day.
4. A task that fits no gap goes to "didn't fit", with the reason showing its length and the largest free gap left at that moment.

**Usual order:** for two tasks A and B, the planner counts the past days where something similar to B started before something similar to A, minus the days it went the other way. If that count is at least `ORDER_MIN_DAYS` and the planner put A directly before B (back-to-back), it swaps them within the same span. Because the span doesn't change, a swap can't create an overlap. This repeats until nothing changes.

## v1.4: automatic rescheduling (done)

- [x] Triggers: fail, skip, run over. Run over is told (`x`: new end time or minutes to add) or noticed (end alarm -> check-in "still going"; on startup, today's tasks that ended unmarked get the same check-in)
- [x] Reason is a hard rule: `services._close` refuses a blank reason (no status change), and `rescheduler.build_for_closed` refuses a failed / skipped task without a stored reason
- [x] Reasons stored permanently with a snapshot (title, date, priority, goal id and title); never updated or deleted by rescheduling or undo
- [x] History view (`h`): failed and skipped tasks with reasons, filter by goal and date range, shows what each was rescheduled as
- [x] Proposal first: shows every change (new copy / move / extend) with from, to and a one-line reason; nothing changes until accepted
- [x] Failed / skipped task stays on its day as a record; a linked copy (`rescheduled_from_id`) goes into today's remaining window, then tomorrow's; nothing beyond tomorrow; the rest is "unplaced" (no time, not failed, in the "Didn't fit / unplaced" list)
- [x] Fixed / pinned / done / started tasks never move; unpinned planned tasks may shift; a higher-priority item may displace a lower-priority unpinned task, which is re-placed by the same rules or unplaced
- [x] Overrun: task extended (not failed) and the back-to-back chain behind it shifts; a collision with a fixed / pinned task gives a warning naming it and its time, with a choice to shorten, move the rest after it, or leave it
- [x] Goal: nothing logged for the failed / skipped task; the copy logs its contribution only when completed
- [x] One-step undo (`z`) restores the exact previous plan (times, placements, reasons shown, alarm flags) and removes the copies; failure records and reasons untouched; refused if a copy or moved task has since been closed, or if restoring would overlap something added since
- [x] Alarms follow moves (re-armed at the new time); closed records get no alarms; ringing / snoozed alarms of moved or closed tasks are dismissed
- [x] Reschedule cap: `MAX_RESCHEDULES = 3`; at the 3rd reschedule of a chain you choose keep / split in two / drop
- [x] Migration to schema v5 (backup first); existing reasons get their snapshot filled from their task and goal
- [x] Tests: fail early / midday / late / after the window, skip, untimed, unplaced, never beyond tomorrow, displacement (incl. equal priority and pinned not displaced), overrun both ways, chain push, overrun noticed late, all three collision choices, validation, nothing-before-accept, undo (exact restore, reason kept, one step, refusals), stale proposal, cap choices, alarms, goal contribution on the copy, history filters, reason snapshot, migration, busy-day no-overlap, UI flows (308 passing)

### How failure reasons are stored

- **Table `task_reasons`:** one row per failed or skipped close. Columns: `task_id`, `status` (failed / skipped), `reason`, `created_at`, plus a snapshot taken at the moment of closing: `task_title`, `task_date`, `priority`, `goal_id`, `goal_title`. `task_date` and `goal_id` are indexed for queries.
- **Written in one place:** `services._close` writes the row, only when the reason is non-empty. Nothing ever updates or deletes these rows. The rescheduler and undo don't touch the table, and the failed task (which owns the rows) is never deleted.
- **Query:** `rescheduler.reason_history(session, goal_id=None, start=None, end=None)` returns rows newest first. Each row's `.task.rescheduled_copies` gives the linked copies.
- **Not used for placement yet:** v1.3 placement is unchanged. A later version can use these rows, e.g. to avoid hours with many "tired" reasons.

### How a reschedule proposal is built (tune in `tomits/rescheduler.py`)

**Constants:** `MAX_RESCHEDULES = 3` and `DAYS_AHEAD = 1` (today plus tomorrow). Placement reuses the constants in `planner.py`.

**The board (free time):**

- It covers today, from now rounded up to 5 minutes, to the window end, and then tomorrow's whole window.
- Tasks with a time that are done, or pending and fixed, pinned or already started, are fixed blocks.
- Pending, unpinned, planner-placed tasks that haven't started are movable blocks.
- Failed and skipped tasks don't block, so a failure frees its slot.

**What gets placed:**

- **Failed or skipped:** one new copy with the same title, duration, priority and goal. With the "split" choice it becomes two halves.
- **Overrun:** the chain of movable tasks it pushes. A task joins the chain if it starts before the pushed end of the one before it; a gap stops the chain. With "move the rest", a continuation copy for the leftover minutes is added.
- **During an overrun,** a planned task due to start at or after the overrunning task's original end counts as movable even if its start time has passed, because you were still on the other task.

**Order and slot (same as v1.3):**

1. Items are placed by priority, then shorter first, then a stable key. For each item, the planner tries today, then tomorrow.
2. With enough similar history, an item takes the fitting start nearest the usual time. Otherwise it takes the earliest fitting start.
3. If nothing fits on either day, the planner tries displacement. The candidates are movable tasks with a strictly lower priority. The least important goes first, then today before tomorrow, then the latest start. The first one whose removal makes room is displaced and goes back in the queue with the reason "made room for 'X' (higher priority)". Only one task is displaced per item.
4. Still no room means the item is unplaced.

**The reason line:** "moved from <old time>: <cause>", plus ", higher priority than 'Y'" if it displaced Y. That's followed by "; tomorrow," when placed tomorrow, then the placement detail ("usually completed around ..." or "first free slot, by priority"), or "; unplaced: no room today or tomorrow (needs ...)".

**Accept:**

1. Accept refuses if a choice is still open or a task changed since the proposal.
2. It creates the copies and applies moves and extensions.
3. It re-checks for overlaps. If any are found, it rolls back and changes nothing.
4. It writes `reschedule_log`: the trigger, the exact previous values of every changed task (JSON), and the new copy ids.

**Undo:** only the latest log entry, and only once.

## v1.5: complete voice control (done; real microphone not yet tested, see below)

- [x] One command registry (`tomits/voice/registry.py`, filled by `tomits/voice/commands.py`) used by both the typed menus and voice; typed keys are read from it
- [x] Voice handlers call the same logic-layer functions as typed actions, so every rule applies unchanged: no overlaps, locked periods, mandatory reasons, fixed / pinned never move
- [x] Test that fails if any typed key (timetable, tracking page, alarm, check-in, proposal, collision, cap, settings) has no voice command, and that every key shown in the menus is in the registry
- [x] Offline speech: Vosk speech-to-text + pyttsx3 (Windows voices) text-to-speech; `voice_setup.bat` downloads the model once; `voice_check.bat` tests mic, model and voice
- [x] Local, deterministic understanding: phrase patterns + fuzzy task / goal names; natural times ("at 3 pm", "tomorrow at 9", "half past nine"), durations ("for 45 minutes", "an hour and a half"), dates ("next Sunday", "in 3 days", "12th of October"), priorities
- [x] Follow-up questions for missing duration / priority / period / title; "cancel" at any point; silence gives up without acting
- [x] Ambiguous names: matches read out by number, pick by voice ("the second one")
- [x] Not understood: says so and gives one example; never guesses
- [x] Mandatory reason by voice: asked, read back, correctable ("redo" / "change X to Y"), saved exactly like a typed reason; no reason -> task unchanged
- [x] Dictation with read-back for reasons, reviews, process and goal titles
- [x] Spoken "yes" required for delete task / goal, remove log / sacrifice, undo reschedule, accept reschedule; and whenever recognition confidence is below `LOW_CONFIDENCE`
- [x] Refusals (locked period, overlap, missing reason, unit mismatch ...) are spoken with the logic layer's own message
- [x] All areas by voice: tasks (add / add several / edit / delete / move / pin / unpin / reorder / link), what's next, my day, plan / re-plan, done / failed / skipped / still going, reschedule proposals (read aloud, accept / reject / repeat / undo), collision choice, reschedule cap, goals (create with target, link, rename, retarget, done, delete), log progress, process, sacrifices, reviews, day / week / month pages and navigation, progress read-out, reminder answer ("fill in my plan"), alarms (dismiss / snooze / snooze for N minutes), history with goal / date filters, day window, snooze length, voice settings, mute
- [x] Listening: push-to-talk key (default `v`, setting), optional hands-free with wake phrase (default "hey tomits", off), red "LISTENING" indicator, mute by voice and `m`, spoken replies can be turned off
- [x] While an alarm rings: listens only for dismiss / snooze (short word list) and pauses the tone while listening
- [x] No mic / no model / library error: the reason is shown and the same command can be typed in words; typed menus unchanged
- [x] New typed keys added with their voice twins: `c` change a task, `del` delete a task, `m` mute
- [x] Tests from text transcripts (225): every registry command's examples, phrasing variations, times / dates / durations / priorities, follow-ups, ambiguity, cancel, silence, not-understood, low confidence, reason by voice (cancel, silence, correct, redo), risky confirmations, locked-period and overlap refusals, all rescheduling paths, alarms and check-ins by voice, reminder by voice, tracking, history, settings, mic fallbacks, the full done-means day (533 passing)

### Speech engine choice

- **Speech-to-text: Vosk** with the `vosk-model-small-en-us-0.15` model (~40 MB). It runs fully offline on Windows, with no account and no key, and audio never leaves the PC. It supports a restricted word list, which is used while an alarm rings. It's light enough to run on a laptop CPU. The model is downloaded once by `voice_setup.bat`; that download is the only network use, and no audio is sent.
- **Microphone: sounddevice**, whose Windows wheel includes PortAudio.
- **Text-to-speech: pyttsx3**, which uses the Windows built-in voices (SAPI5). It was already in the planned stack.
- **Not chosen:**
  - SpeechRecognition's default recogniser sends audio to Google, so it's out. Its offline modes wrap Vosk / Sphinx anyway.
  - Whisper would be more accurate but is heavier on CPU and has no word-list mode.
  - Nothing that needs an account or sends audio was added.

### How the command registry works

- **What an entry holds:** every action is a `Command` in `REGISTRY`, with:
  - `name` and `summary`
  - `examples`: phrases for help and for "didn't understand" replies
  - `patterns`: regexes, matched as a full match against normalized text, meaning lower-case, number words turned into digits, and punctuation dropped
  - `typed`: a list of (screen, key, method), where screen is `timetable`, `tracking`, `alarm`, `checkin`, `proposal`, `collision`, `cap` or `settings`
  - `contexts`: where voice may match it. "main" is free commands; the prompt names are for answers inside prompts.
  - `risky` and `rank`: rank is the order patterns are tried, lower first, so specific phrasings come before general ones
- **Typed menus:** `App.typed_actions()` and `TrackingScreen.run()` build their key -> method maps with `registry.typed_map(screen)`. The prompts take their allowed keys from `registry.typed_keys(...)`.
- **Voice:** `Dialog.handle(heard)` normalizes the text, finds the first matching command for the context, and runs its handler. It reads back first if confidence is below `LOW_CONFIDENCE`.
- **What handlers do:** they only collect what's missing, asking with `ask_duration`, `ask_priority`, `ask_choice`, `dictate`, `choose` or `confirm`. Then they call the logic layer: services, tracking, planner or rescheduler. A `TaskError` from there is spoken as "I can't do that. ...", and `Cancelled` becomes "Cancelled. Nothing was changed."

### How to add a command

1. Put the rule in the logic layer (a services / tracking / planner / rescheduler function), never in the UI.
2. Add the typed method on `App` (or `TrackingScreen`).
3. Add a handler in `tomits/voice/commands.py` with the `@command(...)` decorator. Give it a name, a summary, at least one example, the patterns, and `typed=[(screen, key, method name)]`. Set `risky=True` if it deletes, discards or accepts, and use `d.confirm(...)` in the handler.
4. Add the key to the menu text.
5. Run `test.bat`. `test_every_typed_action_has_a_voice_command`, `test_every_menu_key_on_screen_is_in_the_registry` and `test_each_command_understands_its_own_examples` fail until the entry is complete.

### How voice was tested with a real microphone

- **Not yet done.** The test VM has no microphone and no audio library, and both networks I have blocked the model download, so the real speech engine has not been run.
- **What is tested:**
  - All understanding and dialog logic, through 225 transcript tests.
  - The engine wrappers with fake recognisers: listening indicator, tone paused while listening, muted and failed-mic fallbacks, the no-engine message, and turning a Vosk result into text plus confidence.
  - The real app in the VM through the typed fallback: add, plan, fail with a corrected reason, reschedule, "what's my day like".
- **To check on your PC:**
  1. Run `voice_setup.bat` (downloads the model), then `voice_check.bat`. It checks the mic and model, asks you to say a command and "dismiss", shows what Vosk heard with its confidence and which command it matched, then speaks a sentence.
  2. In tomits, press `v` and try the done-means sequence.
- **Please report** misheard words. They can usually be fixed by adding a pattern, or by adding the word to the alarm word list.

### Voice and the alarm tone

- While an alarm rings, the mic listens with a short word list (dismiss, stop, snooze, snooze for 5 / 10 / 15 / 20 / 30 minutes). Vosk then only chooses between those phrases, which is much more robust against the tone.
- The tone pauses while the mic is open (`Ringer.quiet`) and resumes afterwards if the alarm is still ringing. Since each burst is short (under 1 s), the pause takes effect within a second.
- **What worked:** tested only in code so far (the tone is paused during listen). Real-world behaviour needs your check with `voice_check.bat` step 3 while an alarm rings.

## v1.5.1: better recognition and understanding (done; needs your clips for the benchmark)

- [x] Speech-to-text replaced: Vosk -> **faster-whisper** (local, CPU int8, no account). Model size is a setting (`stt_model`, default `small`)
- [x] Audio: mono 16 kHz, volume-normalized, silence-trimmed, 0.3 s end padding; stops 1 s after you stop speaking; input device name and sample rate shown; warning for low-rate / Bluetooth call-mode inputs
- [x] Whisper gets a spelling hint: command words plus your current task and goal names
- [x] **Local language model** (Ollama, default `qwen2.5:1.5b`) for rephrased commands; only chooses registry commands; output validated (see below); rules first, model only when no rule matches; falls back to rules when missing, slow (`LLM_TIMEOUT_SECONDS`) or invalid
- [x] Shows `Heard: "..." (NN% sure)` and `→ <plain words>` before acting
- [x] Low confidence (`LOW_CONFIDENCE`) or no clear meaning -> no action, says what it heard and asks to repeat (replaces v1.5's confirm-and-act)
- [x] Destructive commands read back exactly what will be deleted and how many, what's kept and why, say "can't be undone", and need a spoken yes; the model may only pick a destructive command if a delete-type word was actually said
- [x] Weak name matches (below `NAME_CONFIRM_SCORE`) are read back ("Did you mean ...?") instead of guessed; word stems help ("running" -> "run 5 km")
- [x] New commands (voice + typed): delete all tasks / goals (`o` -> `x`), clear a day, move a task to another day ("push my workout to tomorrow"; typed via voice or `e`-style), voice log (`o` -> `l`), mic test (`o` -> `t`), choose microphone (`o` -> `i`), voice options (`o` -> `v`)
- [x] Voice log: every attempt in `data/voice_log.db` (table `voice_log`); audio of the last `AUDIO_KEEP` = 50 attempts in `data/voice_audio/<id>.wav`, older audio deleted automatically, text kept
- [x] Mic test (`voice_mictest.bat`): device in use, live level, playback, transcript, how it would be understood, and a diagnosis (mic / audio / recognition); `--list`, `--device N`, `--record NAME`
- [x] Dry-run script (`voice_try.bat clip.wav` or `--text "..."`): transcript, confidence, command, fields, name matches, read-back for deletes, what would happen; never executes
- [x] Benchmark (`voice_benchmark.bat`) over your clips in `tests/audio` (list in `clips.csv`, first clip: "delete all the tasks and goals from everywhere")
- [x] Tests (73 new, 606 total): model output validation (valid / 11 kinds of invalid / destructive-word rule), fallback (off, not running, error, broken JSON, "none", timeout), rules-first, rephrasings with the model off, show-before-act, garbled -> no action, low confidence -> no action, delete-all read-back and yes / no, clear day, typed bulk delete, name matching against existing tasks and goals (model and rules, ambiguous, weak, unknown), rules can't be bypassed (overlap, locked period), log format and audio retention, dry-run never executes, audio preparation, device warning, mic test report, move to another day

### Models chosen, and why

**Speech-to-text: faster-whisper, multilingual `small` by default (about 484 MB).**

- It's a Whisper model converted to CTranslate2, running on the CPU in int8. Models come once from Hugging Face (public, no account), and audio never leaves the PC.
- Multilingual models are used with the language set to English, not the English-only `.en` models. Whisper's multilingual models were trained on far more accented and Indian English speech, and the benchmark lets you compare `small.en` on your own clips.
- `small` is a starting point until you run the benchmark on your Ryzen 7 7435HS. Expected: `base` fast but weaker, `small` usually well under 2 s per command, `medium` (1.5 GB) more accurate but slower. The benchmark decides.

**Understanding: Ollama with `qwen2.5:1.5b` (about 986 MB).**

- Ollama was already in the planned stack. It runs only on 127.0.0.1, needs no account, and its JSON-schema output mode fits the strict validation.
- Qwen 2.5 1.5B follows structured instructions well for its size and runs in a few seconds on your CPU.
- Smaller: `qwen2.5:0.5b` (398 MB, faster, weaker). Larger: `qwen2.5:3b` (about 1.9 GB).
- The model is optional. Without Ollama, the rule patterns work as before, including the new rephrasings.

**Not added:** anything needing an account, or sending audio or text off the PC. Hugging Face telemetry is switched off (`HF_HUB_DISABLE_TELEMETRY=1`).

### How to swap models

- **Whisper:** `o` -> `v` in the app, or `stt_model` in `data/settings.json`. The choices are `tiny`, `base`, `small`, `medium`, `large-v3-turbo`, `large-v3` and the `.en` variants. Download with `voice_setup.bat --whisper <size>`; it shows the size and asks first. The benchmark can also save its recommendation.
- **Language model:** `o` -> `v` (type a model name, or `off`), or `llm_model` / `llm_enabled` in settings. Download with `voice_setup.bat`, which runs `ollama pull` after showing the size.
- **Another backend** (for example llama.cpp): write a class with `available()` and `complete(prompt, schema, timeout)` (see `LlmBackend` in `tomits/voice/nlu.py`) and pass it to `Understanding(...)` in `App._make_understanding`. Validation stays the same.

### How the model's answer is validated (`tomits/voice/nlu.py`, `tomits/voice/specs.py`)

1. **Rules first.** If a rule pattern matches, the model isn't asked.
2. **What the model gets:** the transcript, the free registry commands with their allowed fields (from `SPECS`), and your current task and goal names. It must answer JSON `{command, fields, confidence}`, and Ollama enforces the schema.
3. **Rejected when:**
   - it isn't JSON, or `command` is `none`, or the command isn't in `SPECS` (prompt answers like "dismiss" aren't free commands)
   - a field isn't allowed for that command, a required field is missing, a value is outside its allowed set (for example `period` can only be an open-type period word), or a value is over 120 characters
   - the model's confidence is below `LLM_MIN_CONFIDENCE` (0.6)
   - it's a destructive command and no delete-type word (delete / remove / clear / erase / wipe / drop / cancel / undo ...) was said
4. **Canonical sentence:** the fields are rendered into the command's canonical sentence, for example `move {name} to {date}`. That sentence must match the same command through the ordinary rule patterns, so the handler that runs is the same one typing uses. A test checks that every template maps back.
5. **Fallbacks:** slower than `LLM_TIMEOUT_SECONDS` (8 s), not running, an error, or invalid output all count as "not understood": no action, and the rules' answer stands.

### How the benchmark works

1. Record clips with `voice_mictest.bat --record NAME`, using the names in `tests/audio/clips.csv`. Each line gives the file, the sentence to say, and the expected command. See `tests/audio/README.md`.
2. Run `voice_benchmark.bat`. The default sizes are `base small medium`, or list your own. For each size it transcribes every clip and measures:
   - word error rate against the expected sentence
   - how often the expected command is understood (rules; add `--llm` to include the local model)
   - median and slowest seconds per clip
3. It recommends the lowest error rate among sizes with a median of 3 s or less (`MAX_SECONDS_PER_COMMAND`), writes every result to `tests/audio/benchmark_results.csv`, and offers to save the choice.
4. Before downloading a size you don't have, it shows the size and asks. `base` + `small` + `medium` is about 2.2 GB in total.

**Benchmark results:** not run yet. It has to run on your PC with your voice and mic. The test VM here has 2 cores of your CPU, no microphone, and no access to the model sites. Please send me the table it prints and I'll record it here.

### Voice log (`data/voice_log.db`, table `voice_log`)

- **Columns:** `id`, `ts` (ISO time), `transcript`, `confidence` (0-1), `source` (`rules` / `model` / `none`), `command` (registry name), `interpreted` (plain words), `acted` (1 = carried out; 0 = low confidence, not understood, cancelled, refused, or a "no" to a confirmation), `result` (what the app said, with prefixes like `declined:` / `refused:`), `audio_file`, `device`, `note` (for example why the model's answer was rejected).
- **Audio:** kept for the last 50 attempts in `data/voice_audio/<id>.wav`. Older files are deleted automatically, and the row notes "audio removed".
- **View it:** `o` -> `l`, say "show the voice log", or open the file with any SQLite viewer.

## UI mockups (web app direction, static only)

- [x] `ui-mockups/`: 6 layout options, used as the design for the v1.6 web app
- [x] **`ui-mockups/sample-data.js` has been removed** (v1.6), with the rest of `ui-mockups/`: the mockups only worked with that fake data, and their designs now live in the real app (`tomits/web/static/layouts/`). Nothing fake is left in the interface, the code or saved data (`tests/test_web_ui.py::test_no_demo_data_left`).
- [ ] Mockup assumption still open: the reschedule proposal could also offer a "didn't fit" task a slot tomorrow. The rescheduler only handles failed / skipped / overrun tasks, so the web app doesn't do this.

## v1.6: local web app (done; needs your manual check, see the checklist below)

- [x] Web server on top of the same logic layer and database: `tomits/web/` (`python -m tomits.web`, or `start-tomits.bat`). The terminal version (`run.bat`) still works on the same data.
- [x] **Framework: Flask** (with its own Werkzeug server, threaded). Why: small, very widely used, pure Python, no account or paid service, nothing sent anywhere; its threaded server handles server push (Server-Sent Events) without an async rewrite of the logic layer; it has a built-in test client.
- [x] Every browser action is a registry command: `Command.web` handlers (`tomits/web/actions.py`) call the same logic-layer functions as the voice handlers and typed menus. The quick-add box and the mic run the same voice `Dialog` (same matching, follow-up questions, spoken "yes"). New registry commands, all with voice patterns: undo my last change, dismiss the reminder, switch layout, theme, finish setup.
- [x] No rule is reimplemented in the server or the UI: refusals come back from the logic layer (`TaskError`) and are shown next to the control that was used.
- [x] Saved in real time: no save button; each action commits, then the "Saved" indicator confirms it. Process and review save as you type (after a pause) and when you leave the box. If the server can't be reached, a red banner says so and your input stays on screen.
- [x] Live everywhere (server push): another tab, voice, or the terminal version change the database, and every open view refreshes without reloading. The server watches SQLite's `data_version`, so even changes from another process are noticed within half a second.
- [x] Concurrency: the terminal and the web app both write through SQLite with a 15 s busy timeout; web actions are serialised by a lock; settings are written atomically (temp file + replace).
- [x] Undo for every action: one-step undo toast (`tomits/undo.py`) restores the exact rows the action changed. Failure reasons are never touched; undo is refused if the rows changed again, if it would bring back an overlap, or if the period has since locked. Destructive actions still ask first and read back exactly what will go.
- [x] One shared data layer and API client (`static/js/api.js`), shared components (`render.js`, `forms.js`, `actions.js`, `voice.js`, `app.js`); the six layouts (`static/layouts/l1`-`l6`) only arrange and style them.
- [x] Layout chooser in the top bar (and `L`); remembered in settings (`ui_layout`) across restarts; switching keeps the screen you're on. Light / dark / system theme, remembered (`ui_theme`).
- [x] Quick-add box in every layout (`Ctrl K`), keyboard shortcuts with a help overlay (`?`), shortcut hints on buttons, search (`/`).
- [x] First-run setup on an empty database: day window, today's goal and process, sound and notifications, mic test. Each step can be skipped; a missing goal / process stays as the reminder banner.
- [x] Real empty states on every screen (one sentence + a button for the first action).
- [x] **Reminders: one per missing item** (`tomits/reminders.py`, table `reminder_marks`, schema v6). Shown once, never repeated, no sound, and a dismissed item stays hidden. The banner stays until the item is filled in. A new period's missing item gets its own single reminder. Replaces the v1.1 "every 5 minutes"; its tests were rewritten.
- [x] Alarms in the browser: the server keeps the alarm times and ringing / snooze state (reloading the tab loses nothing). The tab plays a built-in tone made with Web Audio and shows a Windows desktop notification when the tab isn't in front. If sound or notifications are blocked, the page says so and the alarm still shows. Each alarm rings once for its task, and again only after Snooze.
- [x] Migrations: before any schema change, a timestamped, integrity-checked backup (`tomits.db.bak-v<old>-<date>-<time>`, SQLite backup API); if it fails, nothing changes and tomits stops with a plain message. Tables are only ever added to, never rewritten.
- [x] Local only: binds 127.0.0.1; Host must be 127.0.0.1 / localhost with the app's port; foreign Origin or `Sec-Fetch-Site: cross-site` refused; writes need the `X-Tomits` header; no CORS headers; Content-Security-Policy `'self'`. The UI loads nothing from outside.
- [x] `start-tomits.bat`: checks Python (3.10+), makes `.venv`, asks before downloading (about 10 MB core, about 130 MB optional voice), starts the server on port 3000 or the next free one (says which), opens the browser, and stays open with a plain explanation if anything fails. Other .bat files now use `.venv` when it exists (`pyenv.bat`).
- [x] `.gitignore`: database, backups, settings, voice log, saved audio, downloaded models, `.venv`.
- [x] Tests (`tests/test_web_api.py`, `tests/test_web_ui.py`, plus migration and reminder tests): every rule through the API (overlaps, locked periods, mandatory reasons, fixed and pinned tasks, proposals, confirmations), writes persisting immediately, live updates to several clients, terminal changes reaching the browser, concurrent terminal + web writes, undo keeping reasons, the no-dead-buttons check, single reminders, first run on an empty database, migration with backup (and refusal when the backup fails), host / origin checks, localhost binding, busy port.
- [ ] **Planned later:** alarms while the browser (or tomits) is fully closed. That needs a background service.
- [ ] **Planned later:** Mac and Linux launchers (`start-tomits.sh`). Today only `start-tomits.bat` (Windows).

### How the web app is put together

- `tomits/web/context.py`: one `WebApp` per server: sessions, settings, alarm thread + ringing state (`Ringer` with a silent player; the browser makes the sound), reminder thread, pending reschedule proposals (rebuilt from the current plan whenever shown; nothing written until accepted), undo stack, voice log. It also provides the attributes the voice commands expect from the terminal `App`.
- `tomits/web/actions.py`: the web handler of each registry command. Destructive ones are registered with `confirm=True` and a `preview` that reads back what will happen.
- `tomits/web/server.py`: routes. `GET /api/state` (everything the screens show, read fresh from the database), `POST /api/command` (run one registry command), `POST /api/say` (typed or spoken words into the voice dialog), `POST /api/voice/transcribe` (16 kHz audio from the browser mic into the local Whisper model), `GET /api/events` (server push).
- `tomits/web/static/js/actions.js`: the action table. Every `data-act` / `data-form` in the UI names an entry; entries with `cmd` run a registry command, entries with `ui` only change the view. `tests/test_web_ui.py` fails if a control has no entry, an entry has no command, or a web command has no control.
- Speech: the browser records the mic (Web Audio), downsamples to 16 kHz and sends it to this computer's server, which runs faster-whisper locally. Spoken replies use only voices installed on Windows (`localService`). Without the voice packages, typing does everything.

### Manual checklist (tests can't hear or see)

Start with `start-tomits.bat`. Do the whole list in **one** layout, then do the starred items (*) in each of the other five (switch with the Layout button or `L`), in light and dark.

- [ ] First run (rename `data` to test it, then rename it back): setup appears; day window saves; today's goal + process save; Enable sound plays the tone; Allow notifications asks; mic test shows a level and what it heard; Skip works; the banner remains if the goal / process were skipped.
- [ ] Your existing tasks and goals appear unchanged (a timestamped backup was made in `data` on first start).
- [ ] (*) Today: Add task (`A`), with and without a time; Add several; Plan my day (`P`) places tasks and shows each one's reason; didn't-fit / no-time list; previous / next day and the date picker; Clear day asks first.
- [ ] (*) A task: Done (with an amount for a linked numeric goal, or "completes the goal" for a no-target goal); Failed and Skip refuse an empty reason; Still going on a running task shows a proposal; Move to a time, before / after another task, to another day; Pin / Unpin; Link goal; Edit; Delete asks first.
- [ ] (*) Overlap: moving a task onto another shows the refusal next to the button.
- [ ] (*) Reschedule: after Failed, the proposal opens; Accept, Reject; Undo toast; "Undo the last reschedule" on the Reschedule screen asks first; collision choice (extend into a fixed task) and the 3-reschedule limit choice.
- [ ] (*) Day / week / month: new goal (with a target and unit, and without); link a day goal to a week goal; Log progress rolls up; remove a log asks first; Mark done; Edit; Delete; sacrifices add / made / delete (no editing since v1.7); process and review save as you type; previous periods are read-only; review closes the day after.
- [ ] (*) Reminder banner: one line per missing goal / process; Fill in jumps to the page; Dismiss hides that item for good; nothing pops or beeps again.
- [ ] (*) History: filter by goal, dates and status; Reschedule from a row.
- [ ] (*) Alarm: a task 6 minutes from now rings at the heads-up; the tone plays; Snooze rings again after the snooze length; Dismiss stops it; with the tab in the background a Windows notification appears; with sound blocked (fresh tab, no click), the page says so and still shows the alarm.
- [ ] (*) Voice: hold `V` and say "plan my day"; "what's next"; "I failed the report" (asks for the reason, reads it back); "delete all tasks and goals" (needs a spoken yes; say no); a mumble does nothing; "dismiss" / "snooze" while an alarm rings; transcript log updates; mic test; choose another microphone.
- [ ] (*) Quick-add box (`Ctrl K`): the same phrases typed.
- [ ] (*) Undo toast (`U`) after an action; undoing a Failed keeps its reason in History.
- [ ] (*) Settings: day window, snooze, spoken replies, speech model, mute, theme, layout, Delete-all buttons read back first.
- [ ] (*) Search (`/`), help (`?`), layout chooser keeps the current screen.
- [ ] Live: open two tabs; a change in one shows in the other. Run `run.bat` at the same time; add a task there; it appears in the browser without reloading; mark it done in the browser; the terminal shows it after Enter.
- [ ] Stop the server (close its window): the red "Can't reach tomits" banner appears and typed text stays; start it again: the page reconnects.
- [ ] From another device on your network, `http://<this PC's IP>:3000` does not open.

## v1.7: times in task titles, fixed slots, sacrifices without editing (done; needs your manual check below)

### What happened before the change (reproduced on a scratch copy, 1 Oct 2026)

- **Time in a title, typed forms (web Add task / Edit, terminal `a` / `c` / `n`):** nothing was read. "gym at 7pm" was saved with exactly that title, no start time, and Plan my day placed it anywhere in the day window. A range ("call 7 to 8 pm") was the same: no time, and the duration field's value was used. Editing a title to include a time changed only the text.
- **Quick-add box and voice:** these already read times, through the voice parser (`voice/parse.py`): "add a task gym at 7 pm for 30 minutes" became "gym" at 19:00, fixed. But they used their own rule for a bare hour ("at 5" always meant 5 pm, "at 9" 9 am), didn't know ranges, and asked for a duration even when a time was given.
- **Sacrifices, web app:** the "Made" / "Planned" buttons and the Edit dialog both failed with an error ("A sacrifice needs some text." / "A sacrifice is either 'planned' or 'made'."), because the server passed an empty value for the field that wasn't being changed. Remove asked for confirmation first.
- **Sacrifices, terminal (`h`) and voice:** worked: toggle planned / made, edit the text, remove. Voice "rename sacrifice X to Y" worked; voice remove needed a spoken yes.

### Done

- [x] **Reading a time from a title** (`tomits/titletime.py`, called by `services.read_title_time`), in the logic layer, so typed forms, the quick-add box, voice, edits and the terminal all behave the same. Clear expressions only: am / pm ("11pm", "11:30 pm", "7.15 a.m."), 24-hour ("23:00", "07:30"), "at" + a time ("at 5", "at 17", "at 6:30"), ranges ("7 to 8 pm", "from 6:30 to 7:15", "7-8pm", "between 2 and 3 pm"), "noon" / "midnight". Bare numbers never count ("read 10 pages", "chapter 5", "pages 10 to 20", "verse 3:16", "look at 3 options").
- [x] The task gets that start time as a **fixed** task; the time (and a day word) is taken out of the title, which is tidied ("Gym - 7pm" -> "Gym"). The title as typed is kept in a new column (`tasks.title_typed`, schema v7, backup first) so it can be restored: "Keep title as typed" on the toast and on the task, voice "keep the title as typed", terminal `typed`. The ordinary Undo also restores it.
- [x] No time in the title: nothing changes; the planner places it as in v1.3.
- [x] Length: a range sets it; a single time gets the default **30 minutes** (setting `default_task_minutes`: web Settings, terminal `o` -> `d`, voice "set the default task length to 45 minutes"); a duration you give wins. In the web form the duration is now optional when the title has a time.
- [x] Unclear am / pm ("at 5", "6:30-7:15"): the reading that starts inside your day window wins; if both (or neither) do, a short question asks first (web dialog, voice "am or pm?", terminal prompt). Nothing is saved until answered.
- [x] Day words with a time: today, tonight, tomorrow, weekday names ("friday", "on friday", "this friday" = the coming one, today included), "next <weekday>" (the first one after today; weeks start Sunday, so "next sunday" is the coming Sunday). No day word: the day you are adding to.
- [x] A time already passed today: added anyway, with a notice in the "Read from the title" line.
- [x] **A task with its own time owns that time** (`services.check_slot`): never moved by the planner or rescheduling, priority unchanged. If it overlaps a planner-placed task, nothing is saved and the v1.4 proposal opens (new trigger "claim": the task takes its time, the planned task moves by the usual rules, with a one-line reason); accept, reject, or undo afterwards (Undo toast, or "undo the reschedule"). If the other task is fixed, pinned, done or already started: refused, naming both tasks and their times ("Neither task is moved"). No overlaps, back-to-back fine. Same for adding, editing a title or duration, and moving a task (time, day, before / after).
- [x] "Read from the title: ..." line after adding or editing (toast, voice conversation, terminal), e.g. start-end, day, length and where it came from, what was taken out.
- [x] "Fixed time" marker on tasks with their own time in all six layouts (shared `R.kindBadge` / `R.taskRow`; layout 2's compact tiles use `R.fixedMark`).
- [x] **Sacrifices: no editing anywhere.** `tracking.update_sacrifice` is gone; `tracking.mark_sacrifice_made` (planned -> made, nothing else changes) and `remove_sacrifice` remain, both refused once the period has ended. Registry: `change_sacrifice` replaced by `made_sacrifice` ("mark sacrifice X as made", terminal tracking `h`) and `remove_sacrifice` ("delete the sacrifice X", tracking `del`), no confirmation; the web Undo toast covers it. The web edit dialog, its action and the old route are removed; the no-dead-buttons test checks they're gone from both the UI and the registry. Existing sacrifices are untouched.
- [x] Tests (`tests/test_title_time.py`, 108, plus additions in `test_web_ui.py`): each time format, ranges, default length and its setting, day words, am / pm by window and by asking, ordinary numbers left alone, title clean-up and restore, Undo, past-time notice, midnight, fixed slot vs planner and rescheduling, proposal for a planned task (accept / reject / undo), refusal for two fixed tasks, started tasks, edits and moves, sacrifice add / made / delete and locking, removed routes, migration v6 -> v7, and the same behaviour through the web form, the quick-add box, voice and the terminal (789 passing).

### Decisions

- **A range past midnight** ("11pm to 1am"): the task ends at midnight (23:00-24:00) and the "Read from the title" line says so; add the rest for the next day as its own task. This keeps every task inside its own day, so the per-day overlap check sees everything and nothing can overlap the next day's tasks. The same applies to a single time whose length would cross midnight ("at 23:45" gets 15 minutes).
- **Day words count only together with a time**, so a title without a time is never changed ("call tomorrow" stays as typed). Voice keeps its v1.5 behaviour of reading a spoken day without a time.
- **The start-time field wins:** if you fill it in, the title is left exactly as typed.
- **Only the first time in a title is read.** A time after "until", "till" or "before" is an end, not a start, so it isn't read ("work until 5pm" stays as typed).
- **"noon" / "midnight"** count after at / by / from or at the end of the title, so a title like "midnight snack" stays as typed.
- **On a proposal for a new task**, rejecting it means the new task isn't added (adding it would overlap). Its text stays in the form.
- **"Add several"** reads each line's time too, but an overlap there is refused (all-or-nothing list) instead of opening a proposal; add that one on its own to get the proposal.
- **"Keep title as typed"** restores the title and removes the time read from it; the task keeps its day and length and goes back to the planner.
- **Sacrifice delete without confirmation** (your request) also applies to voice. CLAUDE.md says destructive voice commands always need a spoken yes; the request was specific, so it wins here. Say if voice should still ask.
- **Changed existing tests:** `test_planner.py`: the three "overlapping move refused" tests now expect a proposal (`SlotTaken`) when the other task was placed by the planner, plus a new refusal test for a pinned one; `test_ui_move_after_and_refusal_then_retry` became a refusal test (pinned) and a proposal test (accept / reject). `test_locking.py`: `update_sacrifice` -> `mark_sacrifice_made`. `test_voice.py`: "remove sacrifice no phone" now matches `remove_sacrifice`; new samples added.

### Manual checks (web app)

Start with `start-tomits.bat` (the first start makes a timestamped backup and adds one column). Do these in one layout, then the starred ones (*) in each of the other five.

- [ ] (*) Add task with a time in the title and the duration empty: it lands at that time with "Fixed time", the time is gone from the title, and the toast says what was read, with Undo and Keep title as typed.
- [ ] Add task with a range in the title: the length matches the range. Fill in a duration too: your duration wins.
- [ ] A title with only ordinary numbers and a duration: no time; Plan my day places it.
- [ ] A day word with a time ("tomorrow", a weekday, "next" + weekday): the task goes on that day.
- [ ] "at" + an hour where both am and pm fall in your day window: a "Which time?" question appears; nothing is saved until you pick.
- [ ] A time that has already passed today: added, with the notice.
- [ ] (*) A title time that overlaps a planned task: the proposal opens with the reason; Reject leaves everything; repeat and Accept: your task keeps its time and the planned one moves; Undo puts both back.
- [ ] (*) A title time that overlaps a fixed or pinned task: refused next to the form, naming both tasks and times.
- [ ] Edit a task's title to include a time: same reading, same proposal / refusal.
- [ ] Quick-add box (`Ctrl K`) and voice: "add a task" with a time: same result, and the "Read from the title" line in the conversation.
- [ ] Terminal: `a` with a time in the title (blank duration), `c` to change a title, `typed` to restore it; `o` -> `d` default length.
- [ ] (*) Day page sacrifices: no edit control; Made only on planned ones and changes only the status; Delete has no confirmation and Undo brings it back; on a past day neither button is there, and voice / terminal refuse it with the reason.
- [ ] Settings: default task length saves and is used by the next single-time title.
- [ ] (*) Layout switcher: open it from the top bar (and `L`) in each of the six layouts, switch, and check you stay on the same screen and the choice is remembered after a restart.

## v1.8: sacrifice buttons fixed, a stronger dead-button check, Remember notes, export / import (done; needs your manual check below)

### The sacrifice buttons: what was sent, and what the registry called it (reproduced 1 Oct 2026, 22:5x)

- **What the buttons send:** the Day page's "Made" button sends `made_sacrifice` and the delete icon sends `remove_sacrifice` (from `static/js/render.js` via `actions.js`).
- **What the running server's registry called them:** the tomits window you had open (`start-tomits.bat`, started 19:28, version 1.6.0) had only `change_sacrifice`. Sending the two new names to it gave exactly your errors: `Unknown action 'made_sacrifice'.` and `Unknown action 'remove_sacrifice'.` Sending `change_sacrifice` reached a handler.
- **Why they disagreed:** the v1.7 update (which renamed the actions) was made while that window was running. The server read the page files from disk on every request, but its Python code, and so its command registry, was loaded once at 19:28. So your browser got the new buttons and the old server didn't know their names. The code on disk agreed with itself, which is why the old check passed: it compared the files, not the running server.
- **Fixed at the source:**
  - **The page matches the server.** The server now takes a snapshot of the page files when it starts and serves only that (`tomits/web/codecheck.py`). The buttons you get always match the registry that is running.
  - **Restart banner.** If tomits' files change while it runs, a banner says "tomits was updated while it was running" and asks you to restart.
  - **One name per action, defined once, in the registry.** The server sends the registry's command names to the page (`state.commands`). Every button and form uses that exact name. The front end's second copy of each name is gone: 44 `cmd: "..."` entries were deleted from `actions.js`, and the action table now holds only forms to fill in first and screen-only actions.
  - **No silent failures.** The page refuses to send a name the running server doesn't have, and explains why.
  - **No aliases added.**
- **Rules unchanged:** "Made" changes planned to made only; delete has no confirmation (Undo restores it); both are refused once the period has ended, with the reason. There is still no way to edit a sacrifice.

### The check that missed it, replaced (`tests/test_actions_registry.py`, in the normal test run)

- **Scan:** every layout and shared front-end file is scanned for each name a control can send: `data-act`, `data-form` (including the two-way forms), `btn()`, `T.trigger`, `T.run`, `T.api.command` and `data-autosave`.
  - Each name must be a registry command with a web handler, or a declared screen-only action.
  - Screen-only names may not share a registry name.
  - No front-end file may carry a second copy of a command name.
- **End to end:** every web command (50) runs through the real API with valid sample input on a seeded database and must answer OK. A new command without a sample fails the test.
  - Every name the scan found is also sent as is; "Unknown action" or a crash fails.
- **Renames are caught:** the test renames buttons on purpose and checks they're caught. I also tried it on the real file: renaming the Made button's action failed 4 tests ("is not a registry command", "Unknown action 'mark_sacrifice_made'"); restoring it passed again.
- **Snapshot:** a test checks the page served stays the start-up snapshot even when the files change, and that a code change is noticed.
- **Other mismatches it found, all fixed:**
  - `fill_in` and `mic_test` were each two different things: a browser-only button (open the page / run the mic test here) and a voice-only registry command with the same name. The browser-only ones are now `open_fill_in` and `run_mic_test`.
  - The first-run setup's day-window form used an alias (`setup_window` -> `settings`); it now sends `settings` itself. The setup goal step is a declared screen-only action that sends `new_goal` and `set_process`, which are both checked.

### Remember (notes)

- [x] **Table `notes`, schema v8:** text (required, 200 characters at most), optional date and time, colour, created time, and reminder state. Migration is a new table only, with a timestamped, checked backup first; it stops if the backup fails. Existing data is untouched.
- [x] **Logic in `tomits/notes.py`:**
  - add and delete only, with no editing anywhere (logic, registry, web, voice, terminal);
  - at most 50 notes (the 51st is refused, with the reason);
  - six muted colours chosen when adding (sand, sage, sky, lilac, rose, slate);
  - not tied to any day, week or month, never locked, kept until deleted.
- [x] **Time in the text:** a clear time in a note's text is read like a task title (`titletime`). "call the bank tomorrow at 5pm" becomes "call the bank" due tomorrow at 17:00. Unclear am or pm is settled by the day window or asked; plain numbers stay as text. A time that has already passed puts the note straight under Overdue, with no reminder.
- [x] **Panel:** one shared panel on the right in all six layouts (`static/js/notes.js`, outside the layouts).
  - Collapsed, it's a small "Remember" tab with the count, plus "N overdue" when there are any.
  - Open, the page makes room instead of covering anything.
  - Open or closed is a setting (`notes_open`), so it's remembered across restarts. It isn't an undo step.
- [x] **Sections:** Upcoming (soonest first), No time (newest first) and Overdue (earliest first; muted, struck through, with a "past" label).
  - A note moves to Overdue when its time passes, and stays there until you delete it.
  - With no notes, the panel shows one sentence and an "Add a note" button.
  - The note box has a live counter (x/200). The placeholder is "Write a note".
- [x] **One reminder per note:** when its time arrives, ONE banner and ONE silent desktop notification.
  - The note is claimed with a conditional database update, so even with the terminal and the web app both running only one of them reminds.
  - Every open tab gets the same notification tag, so it shows once.
  - With no tab open, the server shows the desktop notification itself.
  - Dismissing the banner hides it and doesn't delete the note; it's never reminded again.
- [x] **Away summary:** notes whose time passed while tomits wasn't running are counted at start-up. You get one banner ("N notes became overdue while you were away"), with no notification for each.
- [x] **Actions:** add (button, `N` shortcut, on the button and in the help overlay), delete (no confirmation; the Undo toast restores the exact row, with the same id, text, time, colour and created time).
  - **Voice:**
    - "remember to ... [at ...]", optionally "in sage";
    - "delete the note <part of its text>"; several matches are read out by number to pick;
    - "what do I need to remember" / "show / hide my notes" and "dismiss the note reminder".
    - It says out loud what was added or deleted.
  - **Quick-add box:** the same phrases.
  - **Terminal:** `note`, `delnote`, `notes`. Its dashboard has a Remember panel with the away line.
- [x] **Saving and live updates:** every change is saved at once and appears live in every open tab, and in the terminal version on its next refresh. This covers changes made from the terminal too.
- [x] **Backups and export:** notes are in database backups (same file), in the export and in the import.

### Export and import (new; there wasn't one before)

- [x] **Export:** `tomits/exporting.py`. Every table, row by row exactly as stored, in one JSON file (`{"app": "tomits", "format": 1, "schema": 8, "tables": {...}}`).
  - Web: Settings -> Your data -> Export all data (downloads it).
  - Terminal: `o` -> `e`. Voice: "export my data".
  - Each export is also saved in `data/exports/`.
- [x] **Import:** replaces all data with an export.
  - Web: Settings -> Import an export (reads back what it contains and asks first).
  - Terminal: `o` -> `m` (type IMPORT). Voice: "import my latest export" (needs a spoken yes).
  - A timestamped backup is taken first, and it stops if that fails.
  - Only an export from the same database version is accepted, and it all happens in one transaction, so a bad file changes nothing.
  - The web Undo can take an import back.

### Decisions

- **The page is a snapshot taken when the server starts.** After updating tomits, restart it; until then the banner says so and every button keeps working with the running version.
- **Overdue order is earliest first**, so the one that's been waiting longest is on top.
- **`N` now adds a note.** It used to jump to the quick-add box without being listed anywhere; `Ctrl K` still does that.
- **Voice delete of a note has no "yes"**, same as sacrifices, by your request. CLAUDE.md says destructive voice commands always need a spoken yes; say if notes and sacrifices should be exceptions to that or not.
- **Server notification with no tab open** uses the same Windows toast as the terminal (plyer). The browser's notification is silent; whether Windows plays a sound for the toast depends on Windows' own notification settings.
- **Import replaces everything** rather than merging, because merging two databases' ids safely is a much bigger job. Your old data is always backed up first.
- **Changed existing tests:**
  - `test_web_ui.py`: the three weak registry checks were moved into `test_actions_registry.py` and made stronger.
  - `test_title_time.py`: the v6 -> v7 migration test accepts later schema versions.

### Manual checks (do the whole list in one layout, the starred ones in all six)

Restart tomits first: close the old tomits window (it's still the 1.6.0 server) and run `start-tomits.bat`. The first start adds the notes table after a backup.

- [ ] (*) Day page, a planned sacrifice: Made moves it to Made (the text doesn't change); the delete icon removes it with no question; Undo brings it back. On a past day, neither button is there; by voice or in the terminal, it's refused with the reason.
- [ ] (*) The Remember tab is on the right with the count; click it: the panel opens, the page makes room, and nothing is covered. Close it, restart tomits: it stays closed (and open stays open).
- [ ] (*) `N` opens the panel with the cursor in the note box. The counter counts to 200 and stops there.
- [ ] Add a note with no time (it's under No time, newest first); one with a date and time (Upcoming, soonest first); one with a time written in the text (the time leaves the text, and a "Read from the note" line appears).
- [ ] Add a note due 2 minutes from now and wait: it moves to Overdue (muted, "past"), ONE banner and ONE desktop notification appear (allow notifications first), no sound. Dismiss the banner: the note stays, and nothing repeats. Reload the page: nothing repeats.
- [ ] With two tabs open: a note added in one appears in the other; the reminder notification shows once.
- [ ] Add a note due 2 minutes ahead, close the tomits window, wait, start it again: one banner "1 note became overdue while you were away", no notification.
- [ ] Delete a note: no question; Undo restores it with the same colour, time and created time.
- [ ] 50 notes: the 51st is refused with the message.
- [ ] Voice: "remember to ... at 5 pm", "delete the note ..." (with two matching notes: it lists them by number; say "the second one"), "what do I need to remember".
- [ ] Quick-add box: the same phrases typed.
- [ ] Terminal (`run.bat`): `note`, `delnote`, `notes`; a note added there appears in the browser without reloading.
- [ ] Settings -> Export all data: a file downloads (and is in `data/exports`) and contains your notes. Import it again: it reads back what's in it and asks first; afterwards there's a new backup in `data`.
- [ ] (*) After updating files while tomits runs (or ask me to), the "tomits was updated while it was running" banner appears.

## Next
- [ ] 2.0 blocking + pomodoro (a placeholder screen "Focus (2.0)" exists in every layout), and asking for a task when none is running

## Found / open

- [ ] The old Vosk model folder `data/voice-model` (from v1.5) is no longer used; delete it to free space.
- [ ] A rule can match a sentence but capture an odd name ("finished off the chapter reading" -> "off the chapter reading"). Weak name matches are now read back before acting; if it's common, the rules could hand such cases to the model.
- [ ] While an alarm rings, Whisper can't be limited to a word list like Vosk could; it gets "dismiss / snooze" as a hint and the result is snapped to the closest of those phrases (60% similarity). Needs a real-mic check.
- [ ] Bulk delete follows every earlier rule, so "delete everything" keeps failed / skipped records (reasons are permanent), done tasks, goals in ended periods and goals with logged progress; the read-back lists them.

- [ ] Push-to-talk is "press the key, then Enter, then speak"; listening ends by itself after a pause. A true hold-to-talk key needs a system keyboard hook (the `keyboard` package), which wasn't added.
- [ ] Hands-free mode listens for the wake phrase in short windows and returns to the typed menu when you press a key. It hasn't been tried with a real mic.
- [ ] Voice can't move a task to another day ("move report to Friday" is refused with an explanation), same as typing: failing / skipping reschedules instead.
- [ ] Alarms that go off while you're in the typed menu (not in hands-free or right after a voice turn) are answered by typing, or by pressing `v` and saying dismiss / snooze.

- [ ] Displacement removes one task per item. Two small lower-priority tasks together could make room where neither alone does; that isn't tried.
- [ ] Only fail / skip copies count toward the reschedule cap. Tasks shifted by overruns or displacements don't.

- [ ] From ideation.docx (new, "future"): a table for measuring a specific thing. Not scheduled yet.
- [ ] Planner: a history target in the middle of a gap can split it, so a later lower-priority task may not fit even though the total free time would be enough. Possible tuning: snap history placements to a gap edge when within ~30 min.
- [ ] Planner: tasks without a start time on past days (never planned) don't count as history. Only timed done / failed tasks do.

- [ ] From changes.md: visual alarm you can see even when muted. Partly done: a ringing alarm now shows a red "ALARM RINGING" panel and a Windows toast. Still missing: a flashing or full-screen alert. Say if you want it.
- [ ] From changes.md: "ask what percentage of the goal is completed" when a linked task is done. The 1.1 spec asks for an amount instead (e.g. 10 pages), so that's what was built. Say if you still want a percentage.
- [ ] CLAUDE.md still says "Goal progress is task-count based" (v1.1 replaced that with logged / target), "Rich terminal UI" and that mockups live in ui-mockups/ (removed in v1.6). Those lines need updating (left for you, it's your file).
- [ ] Version label is now "1.8.0".
- [ ] Overlaps are checked per planned day. A task that runs past midnight (e.g. 23:30 for 90 min) is not compared with the next day's tasks.

- [ ] No edit or delete for tasks yet (goals can now be edited and, if unused, deleted on the tracking pages).
- [ ] Overdue pending tasks from earlier days still sit in a red list; failing or skipping one (with a reason) now reschedules it into today / tomorrow. They aren't picked up automatically.

- [ ] **Planned later change:** alarms ring only while tomits is open. Ringing while the app is closed needs a background service, which isn't built yet (by request).
- [ ] When an alarm fires while you're typing an answer, its message prints over the prompt line, and Dismiss / Snooze is offered once that action finishes. The tone keeps ringing (up to 2 minutes) until then.
- [ ] No alarm at the exact start time (not selected: heads-up at -5 min and end check only).

## Decisions (picked the simplest option)

- **Storage:** SQLite at `data/tomits.db` in the project folder (the stack in the brief). Set `TOMITS_DB` to put it somewhere else. `data/` is in `.gitignore`.
- **Progress math (v1.0, replaced in v1.1):** was completed tasks / total tasks. Now logged / target; see v1.1 below.
- **"Goal of the task" vs "big goal":** the ideation doc has both. Each task has an optional free-text `purpose` (its own goal) and an optional link to a big Goal ("auto-progress in big goals *if any*").
- **Statuses:** pending, done, failed, skipped. Only pending tasks can be closed; a closed task can't be closed again.
- **Reasons** live in their own `task_reasons` table, not on the task row, so rescheduling and analytics can keep a history later.
- **Cancel:** Ctrl+C during a prompt cancels the action and leaves the task open. You can't close a task without a reason.
- **Task selection** uses the database ID shown in the ID column.
- **Times** are stored as local naive datetimes (single user, single machine).
- **Layout:** `models.py` (data), `services.py` (all rules, no UI imports), `ui.py` (Rich only), so the logic can move to a background service later.

### v1.2

- **Alarm state** lives on the task (`heads_up_sent`, `end_alert_sent`) rather than a separate alarms table. Each alarm fires once. Changing a task's time resets both flags.
- **Only pending tasks alarm.** Closing a task early silences its remaining alarms.
- **Heads-up for a task that has already started** (e.g. added with a start time in the past) is skipped; its end check still fires.
- **Check-in answer "later"** leaves the task open on the dashboard and doesn't ask again; close it with d/f/s.
- **Check-ins appear** after your current action finishes, or when you press Enter at the menu. The toast and sound tell you one is waiting.
- **Missed at startup:** a task whose end passed is listed as "still open"; a task that is mid-way through its time is listed as "started at". Its end check then fires live.
- **Migrations** are a small built-in step in `db.py` (`PRAGMA user_version`, now 2), not Alembic. It copies the database to `<name>.bak-v1` before changing it.
- **Sounds:** Windows "Asterisk" for heads-up and "Exclamation" for check-ins. If plyer or sound fails, the error shows in dim red on the dashboard and the app keeps running.

### v1.1

- **Rescheduled task's contribution (the case you asked me to decide):** a task keeps its goal link wherever it is planned. The contribution is logged when the task is completed, dated on the completion day, to the linked goal, and only if that day is inside the goal's period (and the period hasn't ended). Otherwise the task still completes, nothing is logged, and the app says why. You can relink it to an open goal first with `l`. Simplest because it needs no extra state and never writes into a locked period.
- **Roll-up ignores dates:** a goal's progress = its own logs + everything logged on goals linked below it. So a week spanning Sep/Oct that you linked to September keeps adding to September's total after 30 Sep. September's own goals, logs, process and sacrifices are still read-only. If you'd rather freeze a month's total when it ends, it's a one-line change (count only logs dated inside the month).
- **"Same unit"** is case-insensitive and ignores spaces ("Pages" = "pages"). A no-target goal has no unit, so it can only link to (and be linked from) other no-target goals.
- **Links are one level up and must contain the period:** a day links to its own week; a week to one of the months it touches; months don't link.
- **Goals for future periods** can be planned now (tomorrow, next week, next month). Reviews can't be written before the period starts.
- **Progress log dates** must be inside the goal's period and not in the future. Amounts must be above 0; decimals are allowed. A wrong log can be removed (`u`) while the period is open.
- **Editing goals:** title, target, unit and link while the period is open. A goal with logs can't switch between numeric and done / not done. Unit changes that would break a link are refused.
- **Deleting goals** is only for mistakes: allowed while open and only if the goal has no logs, no goals linked to it and no tasks.
- **Completing a task linked to a no-target goal** asks "Does this complete the goal?" (default no) instead of an amount.
- **Reminder:** one toast per missing period, first check at startup, then every 5 minutes. The dashboard also shows a red "Fill in your plan" banner. A migrated v1.0 goal counts as this month's goal.
- **Old v1.0 goals** were moved into the month in which the upgrade runs, with no target and not done.
- **Tracking view switch** keeps today: from this month's page, `w` opens this week, not the week of the 1st.
- **Replaced tests:** 8 v1.0 tests checked task-count goals (all of `test_progress.py`, `test_data_survives_restart`, one assertion in the v1 migration test). Those tests now check the same things (progress, persistence, migration) under the new model.

### v1.2 fixes

- **Which tasks block a slot:** pending and done ones. Failed and skipped tasks free their slot for a replacement (your choice). Untimed tasks never overlap.
- **Existing overlaps** are untouched and not flagged. Changing anything but the time (linking, completing, failing) is never blocked. Setting a task to the time it already has is a no-op. Moving it to a new time is checked. Clearing its time is always allowed.
- **Moving a task within its own slot** (09:00 -> 09:30 on a 1-hour task, nothing else there) is allowed: a task isn't compared with itself.
- **Time prompts** check for overlaps right after you type the time and ask again, so you don't retype the whole task.
- **Plan a day** is refused as a whole if any planned task would clash with a saved task or with another task in the same plan.
- **Both alarm kinds ring** (5-minute heads-up and end of task). For the end-of-task alarm, "Did you finish?" comes after Dismiss or after the 2-minute stop. After a snooze it waits for the next ring.
- **Tone pattern:** 880 Hz, 880 Hz, 1320 Hz short beeps, then a short pause, repeated. `winsound.Beep` goes through the default audio device. If Windows volume is muted it's silent, and the red panel and toast remain.
- **The old system sound** (winsound "Asterisk" / "Exclamation" via PlaySound) was removed from notifications. It depended on the Windows sound scheme and was likely why alarms seemed silent. The toast remains.
- **Settings file:** `data/settings.json`. A missing or broken file falls back to defaults and never crashes the app.
- **Changed existing tests (2 files, no assertion weakened):** `test_alarms.py::test_closed_tasks_do_not_alarm` placed two tasks in the same 14:00 slot, which is now refused, so the second task moved to 16:00. `test_ui_checkin.py` (4 tests): the end alarm rings first, so each test now presses `d` (Dismiss) before the check-in answers.

### v1.3

- **Priority scale 1-4** (your choice): urgent, high, normal, low. Default 3. Type a number or the first letter.
- **Keys changed:** `p` is now Plan my day / re-plan. Entering several tasks for a day moved to `n`. `e` now also takes "before N" / "after N". `u` unpins.
- **Fixed vs pinned:** both are times you chose and both are never moved. "Fixed" means you gave the time yourself. "Pinned" means you moved (or confirmed) a time the planner had chosen. `u` works on both and hands the task to the planner. It keeps its time until the next re-plan. Clearing a task's time (`e`, blank) also hands it to the planner.
- **Today:** the planner only uses time from now (rounded up to 5 minutes) to the end of the window. A planned task that has already started is left where it is.
- **Manual moves may go outside the window.** The window only limits the planner.
- **The planner only writes when you run `p`.** Adding tasks during the day doesn't re-plan. They show "not planned" until the next `p`.
- **Moving a task back to the time it already had** pins it without an overlap check, since nothing moves.
- **"Didn't fit"** is saved on the task (placement `overflow`) so the list survives restarts. It's recalculated on the next `p`.
- **Changed existing code paths:** `set_start_time` now records who set the time (fixed / pinned). No existing test needed changes.

### v1.4

- **The fail itself is immediate:** once the reason is saved, the task is failed. The proposal only covers the new plan. Rejecting it leaves the task failed with its reason and no copy, and `r` proposes again later.
- **"Move the overrunning task"** on a collision means: it ends where the fixed / pinned task starts, and the leftover minutes become a linked "(rest)" copy placed by the usual rules. It isn't counted as a reschedule. "Shorten" ends it there with nothing more. "Leave" changes nothing.
- **Only today's timed, pending tasks can run over.** A new end must be later than the current end and not past midnight. "Minutes to add" means a number of up to 3 digits; anything else is read as a clock time.
- **Unplaced copies** are put on today's date with no time (placement "overflow"). Displaced tasks that end up unplaced stay on their own day with no time.
- **Proposals appear at the next Enter** (timetable or tracking pages), after ringing alarms and before check-ins. A yellow banner says when one is waiting.
- **The copy keeps** the title, purpose, duration, priority and goal. It starts pending with fresh alarms.
- **Changed existing test:** `test_planner.py::test_v3_database_gets_priority_and_fixed_placement` checked for schema version exactly 4; it now accepts 4 or later (the database is at 5).

### v1.5

- **Voice answers prompts only after a voice turn** (or in hands-free mode). Otherwise alarms, check-ins and proposals use the typed prompts as before, so typed behaviour is unchanged.
- **Low confidence** (`LOW_CONFIDENCE = 0.6`, in `voice/dialog.py`): the app reads back what it heard and needs a yes before acting.
- **Fuzzy names** (`MATCH_THRESHOLD = 0.6`, `UNIQUE_MARGIN = 0.15`, in `voice/parse.py`): a clear winner is used directly; otherwise the matches are read out by number.
- **Bare hours** ("at 3") mean 1-6 pm and 7-11 am. "next Monday" is the Monday after today; "Monday" / "on Monday" is the coming Monday (today if it's Monday).
- **Goal targets:** a number plus unit in a new goal's title becomes its target ("run 40 km"). "No target" makes it done / not done.
- **Progress without a goal name** goes to the open goal with that unit at the lowest level (today's day goal first); if several are at that level, they're read out.
- **Adds and status changes run at once and say what they did.** Free text is read back first. Deletes, removals, undo and accepting a reschedule need a yes.
- **New typed keys:** `c` change a task, `del` delete a task (pending only; failed / skipped records and their reasons are never deleted), `m` mute / unmute. `v` is the push-to-talk key and is configurable. Keys already used by menus are refused.
- **Voice settings** live in `data/settings.json`: `push_to_talk_key`, `hands_free`, `wake_phrase`, `spoken_replies`, `muted`, `voice_model`.
- **No existing test was changed.**

### v1.5.1

- **Low confidence now never acts.** This replaces v1.5's "read back and act on yes". `LOW_CONFIDENCE = 0.6` is Whisper's average word probability.
- **Rules are tried before the model,** because they're exact and instant. The model only sees what the rules don't understand.
- **Moving a task to another day** ("push my workout to tomorrow"): new `services.move_to_day`. Today or later only, overlap-checked. With a time it's fixed; without one the planner places it on that day. The rescheduler's "never beyond tomorrow" rule isn't affected: this is your own move.
- **Bulk delete:** voice needs a spoken yes after the read-back; typed (`o` -> `x`) needs the word DELETE. Tasks go first, then goals from day up to month, all through the normal delete rules.
- **Name matching:** your current pending tasks (last 7 days to tomorrow) and open goals are given to Whisper as a spelling hint and to the model as context. Spoken names are matched with word stems. A single match under 0.8 is read back; several close matches are listed by number.
- **Changed existing tests (all in `tests/test_voice.py`):**
  - `test_low_confidence_reads_back_first` became `test_low_confidence_does_nothing_and_asks_to_repeat` (the new rule).
  - `test_no_voice_engine_is_reported_not_silent` now patches the Whisper recogniser instead of Vosk.
  - `test_vosk_result_to_heard` became `test_whisper_result_to_heard`.
  - Engine replaced, as requested.
