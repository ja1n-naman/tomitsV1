/* ==========================================================================
   demo-content.js: GENERIC PLACEHOLDER CONTENT. DELETE BEFORE SHIPPING.

   Every piece of sample content the kit shows lives in this one file: items,
   progress entries, history rows, notes, banners, the alarm, voice phrases and
   app-specific labels. Nothing in shared/ or layout-N/ hard-codes content;
   they only hold generic UI wording (button labels, empty-state sentences).

   To remove the demo: replace `window.DEMO = {...}` with your own data in
   the same shapes (see UI_GUIDE.md §7.1), or with empty arrays. Every screen
   then shows its empty state.

   Dates are relative ("offset" days from today) so the demo never goes stale.
   "now" is a fixed placeholder clock so the timeline looks the same every time.
   ========================================================================== */
window.DEMO = {
  appName: "Your app",                       // placeholder brand name
  now: "10:20",                              // placeholder clock (HH:MM)
  window: { start: "08:00", end: "18:00" },  // placeholder working window

  /* App-specific vocabulary (placeholders). */
  kinds: {
    fixed:   { label: "Fixed",       icon: "anchor", hint: "Placeholder: has its own time and never moves" },
    pinned:  { label: "Pinned",      icon: "pin",    hint: "Placeholder: moved by hand; stays put" },
    auto:    { label: "Flexible",    icon: "route",  hint: "Placeholder: placed automatically" },
    untimed: { label: "Unscheduled", icon: "clock",  hint: "Placeholder: no time yet" }
  },
  priorities: { 1: "high", 2: "raised", 3: "normal", 4: "low" },
  mainAction: "Arrange automatically",       // the app's one-key automatic action (P)
  linkLabel: "Linked entry",                 // what an item's link chip points at

  /* Items: one entry per day, offset from today (0 = today). */
  days: [
    { offset: 0,
      items: [
        { id: 1, title: "Placeholder item 1", start: "08:30", end: "09:15", duration: 45, status: "done",    kind: "fixed",  priority: 3, reason: "Placeholder reason: a time the user set" },
        { id: 2, title: "Placeholder item 2", start: "09:30", end: "10:00", duration: 30, status: "failed",  kind: "auto",   priority: 2, fail_reason: "Placeholder reason: it took longer than planned" },
        { id: 3, title: "Placeholder item 3", start: "10:00", end: "11:00", duration: 60, status: "pending", kind: "auto",   priority: 1, running: true, elapsed: 0.33, minutes_left: 40,
          reason: "Placeholder reason: the first free slot that fits", link: { id: 101, title: "Placeholder entry A", text: "2 / 5" } },
        { id: 4, title: "Placeholder item 4", start: "11:30", end: "12:15", duration: 45, status: "pending", kind: "pinned", priority: 3, reason: "Placeholder reason: moved here by hand" },
        { id: 5, title: "Placeholder item 5", start: "13:00", end: "14:30", duration: 90, status: "pending", kind: "fixed",  priority: 2, reason: "Placeholder reason: a time the user set" },
        { id: 6, title: "Placeholder item 6", start: "15:00", end: "15:45", duration: 45, status: "pending", kind: "auto",   priority: 4, reason: "Placeholder reason: lower priority, so later in the day" }
      ],
      untimed: [
        { id: 7, title: "Placeholder item 7", duration: 30, status: "pending", kind: "untimed", priority: 3 },
        { id: 8, title: "Placeholder item 8", duration: 20, status: "pending", kind: "untimed", priority: 4 }
      ] },
    { offset: -2, items: [ { id: 21, title: "Placeholder item 21", start: "09:00", end: "10:30", duration: 90, status: "done", kind: "fixed", priority: 3 } ], untimed: [] },
    { offset: -1, items: [ { id: 22, title: "Placeholder item 22", start: "11:00", end: "12:00", duration: 60, status: "skipped", kind: "auto", priority: 3, fail_reason: "Placeholder reason: not needed any more" },
                           { id: 23, title: "Placeholder item 23", start: "14:00", end: "15:00", duration: 60, status: "done", kind: "auto", priority: 3 } ], untimed: [] },
    { offset: 1,  items: [ { id: 24, title: "Placeholder item 24", start: "09:00", end: "10:00", duration: 60, status: "pending", kind: "fixed", priority: 2 },
                           { id: 25, title: "Placeholder item 25", start: "13:30", end: "14:15", duration: 45, status: "pending", kind: "auto", priority: 3 } ],
      untimed: [ { id: 26, title: "Placeholder item 26", duration: 25, status: "pending", kind: "untimed", priority: 3 } ] },
    { offset: 2,  items: [ { id: 27, title: "Placeholder item 27", start: "10:00", end: "11:30", duration: 90, status: "pending", kind: "pinned", priority: 3 } ], untimed: [] }
  ],

  /* Older items still open from earlier days. */
  older: [ { id: 31, offset: -3, title: "Placeholder item 31", duration: 30, status: "pending", kind: "untimed", priority: 3 } ],

  /* Decision cards: a change waiting for Accept / Reject. */
  decisions: [
    { id: 1, title: "Placeholder decision", trigger: "after Placeholder item 2 failed",
      moves: [
        { kind: "Move", title: "Placeholder item 4", from: "11:30", to: "12:15–13:00", why: "Placeholder: the first free slot after the change" },
        { kind: "Copy", title: "Placeholder item 2", from: "09:30", to: "16:00–16:30", why: "Placeholder: try again later the same day" }
      ] }
  ],

  /* Progress: three placeholder groups; the last one is read-only. */
  progress: [
    { key: "a", label: "Group A", sub: "Placeholder period A", locked: false, entries: [
      { id: 101, title: "Placeholder entry A", value: 2, target: 5, unit: "units", parents: [ { title: "Placeholder entry D", text: "7 / 20" } ],
        logs: [ { id: 1, offset: 0, amount: 1 }, { id: 2, offset: -1, amount: 1 } ] },
      { id: 102, title: "Placeholder entry B", value: null, target: null, done: false } ],
      note: "Placeholder text area: autosaves 1.2 s after you stop typing." },
    { key: "b", label: "Group B", sub: "Placeholder period B", locked: false, entries: [
      { id: 104, title: "Placeholder entry D", value: 7, target: 20, unit: "units", logs: [] } ], note: "" },
    { key: "c", label: "Group C", sub: "Placeholder period C (ended)", locked: true, entries: [
      { id: 105, title: "Placeholder entry E", value: 3, target: 3, unit: "units", done: true, logs: [] } ], note: "Placeholder: read-only because the period ended." }
  ],

  /* History with filters. */
  history: [
    { id: 1, offset: 0,  title: "Placeholder item 2",  status: "failed",  reason: "Placeholder reason: it took longer than planned", group: "Group A", action: true },
    { id: 2, offset: -1, title: "Placeholder item 22", status: "skipped", reason: "Placeholder reason: not needed any more",          group: "Group B" },
    { id: 3, offset: -4, title: "Placeholder item 40", status: "failed",  reason: "Placeholder reason: something else came first",     group: "Group A" },
    { id: 4, offset: -6, title: "Placeholder item 41", status: "skipped", reason: "Placeholder reason: postponed",                     group: "" }
  ],

  /* Notes panel. due: offset days + time, or null. */
  notes: {
    max: 50, max_text: 200, colors: ["sand", "sage", "sky", "lilac", "rose", "slate"],
    items: [
      { id: 1, text: "Placeholder note with a time that has passed", due: { offset: -1, time: "17:00" }, color: "rose" },
      { id: 2, text: "Placeholder note due later", due: { offset: 1, time: "09:00" }, color: "sky" },
      { id: 3, text: "Placeholder note without a time", due: null, color: "sage" },
      { id: 4, text: "Another placeholder note", due: null, color: "sand" }
    ]
  },

  /* Banners. mode "once" = shown on one load only; "until-dismissed" = until Dismiss. */
  banners: [
    { id: "demo-once", tone: "info", mode: "once", text: "Placeholder banner shown once. Reload the page: it will not come back." },
    { id: "demo-remind", tone: "warn", mode: "until-dismissed", text: "Placeholder reminder: something still needs filling in.", action: { label: "Open", nav: "progress" } },
    { id: "demo-note", tone: "note", mode: "until-dismissed", text: "Placeholder note reminder: its time has arrived." }
  ],

  /* Alarm popup. */
  alarm: { eyebrow: "Placeholder alarm", title: "Placeholder item 4", message: "Placeholder alarm message: it starts in 5 minutes.", snooze_minutes: 5 },

  /* Voice (fake mic). */
  voice: {
    low_confidence: 0.6,
    micTestHeard: { text: "placeholder test sentence", confidence: 0.9 },   // what the fake mic test "hears"
    // What the fake mic "hears", in turn.
    heard: [ { text: "show the list", confidence: 0.93 }, { text: "add placeholder item", confidence: 0.88 },
             { text: "delete all placeholder items", confidence: 0.91 }, { text: "mumble", confidence: 0.41 } ],
    // Phrase → command. risky: needs a "yes" first.
    commands: [
      { match: "list",    name: "open_list",   result: "Opened the list.", nav: "list" },
      { match: "add",     name: "add_item",    result: "Placeholder: an item would be added here." },
      { match: "delete",  name: "delete_all",  risky: true, readback: "This deletes 6 placeholder items. Say yes to go ahead, or no to keep them.", result: "Placeholder: the items would be deleted here." },
      { match: "undo",    name: "undo",        result: "Placeholder: the last change would be undone." },
      { match: "settings",name: "open_settings", result: "Opened settings.", nav: "settings" }
    ],
    phrases: [
      { summary: "Open a screen", examples: ["show the list", "open settings"] },
      { summary: "Add an item", examples: ["add placeholder item"] },
      { summary: "Undo", examples: ["undo that"] },
      { summary: "Delete everything", examples: ["delete all placeholder items"], risky: true }
    ],
    log: [
      { at: "09:58", text: "show the list", confidence: 0.94, interpreted: "open_list", acted: true, result: "Opened the list." },
      { at: "09:41", text: "mumble", confidence: 0.38, interpreted: null, acted: false, result: "Below the confidence limit: nothing happened." },
      { at: "09:40", text: "add placeholder item", confidence: null, interpreted: "add_item", acted: true, result: "Placeholder: an item would be added here." }
    ],
    // Layout 6 rail: each screen shown as the phrase that opens it.
    rail: { home: "show the overview", list: "show the list", progress: "how is it going", history: "what was missed",
            voice: "test my mic", settings: "open settings", later: "(coming later)" }
  },

  /* Screens that aren't built yet (the "later" placeholder pattern). */
  later: { title: "Placeholder: a feature coming later", text: "Placeholder: one or two sentences on what this screen will do." }
};
