# tomits: personal task manager (Python, Windows, Rich terminal UI)

Source of truth for features: ideation.docx. Build in version order:
1.0 tracking, 1.2 alarms, 1.3 priority-based day planning,
1.4 rescheduling, 1.5 voice control, 2.0 blocking + pomodoro.

Rules:
- Goal progress is task-count based (completed tasks / total tasks).
- Every failed or skipped task requires a reason before it can be closed.
- Must run on Windows. Use pathlib, no Unix-only calls.
- App runs as a long-running Rich terminal app now; keep logic separate
  from UI so it can become a background service later.
- Keep a checklist in TASKS.md. Tick items when done, add anything new you find.

When a step doesn't need my input, keep going. Put status notes in the
same message as your next action.
Stop and ask only when you can't continue without me, or before anything
destructive: deleting data files, or changing anything outside this folder.

End every run with three headings: Blocked on me, Changed, Found.

Goals exist only in the day/week/month tracking pages, never in the
timetable. Goals, sacrifices and process lock when their period ends;
review locks 1 day after. Weeks start on Sunday.

Tasks must not overlap (back-to-back is fine). Alarms play a built-in
tone with dismiss and snooze, and only ring while the app is open.

The day planner never moves fixed or pinned tasks, never creates
overlaps, and never changes past days. Placement uses local history
statistics, not an external AI service.

Failing or skipping a task always requires a reason, which is stored
permanently. Rescheduling never moves fixed or pinned tasks, never
goes beyond tomorrow, and always shows a proposal for me to accept.

Every feature must be usable by voice as well as typing. Voice and
typing share one logic layer and one command registry. Voice never
bypasses rules and speech recognition stays local and offline.

The local language model may only choose from the command registry and
never executes anything itself. Low-confidence or unclear voice input
never triggers an action. Destructive commands always need a spoken
"yes" after a read-back.

UI mockups live in ui-mockups/ and are static (plain HTML/CSS/JS). All
sample content lives only in ui-mockups/sample-data.js and is removed
when the real web app is built. The final app will be a local web app
that others can download from GitHub, so keep it free of build tools
and accounts.

Times written in a task title are detected in the logic layer, stored as
the task's fixed start time, and removed from the title. Tasks with no
time are placed by the planner. A fixed-time task is never moved
silently. Sacrifices can only be added, marked as made, or deleted,
never edited.

Every UI control sends only action names defined in the command registry.
A test must fail if any front end action name is missing from it, or if
any action returns an error when run end to end. Remember notes can only
be added or deleted, never edited, and give one reminder each.