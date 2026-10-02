/* What a control does. Every control in every layout names either
   - a registry command, by its registry name (the server sends the list as
     state.commands; the name is defined once, in the registry). An entry
     here only adds a form to fill in first (`open` / `submit` / `change`);
     without an entry the command runs straight away;
   - or a screen-only action (`ui` entries below), which saves nothing.
   tests/test_actions_registry.py scans every layout and shared file for the
   names a control can send and fails if one isn't a registry command, then
   sends each one through the API. */
(function () {
  var T = window.T;
  function task(a) { var t = T.findTask(a.id); if (!t) T.toast("That task isn't on screen any more."); return t; }
  function go(screen) { if (location.hash !== "#" + screen) location.hash = "#" + screen; else T.render(); }

  var A = T.ACTIONS = {
    /* ---- registry commands that ask for details first ---- */
    input_device: { change: function (v) { T.run("input_device", { device: v }); } },
    add_task: { open: function (a) { T.forms.task(null, a); } },
    add_several: { open: function (a) { T.forms.several(a.date); },
      submit: function (a, form) {
        var lines = [];
        for (var i = 0; i < 6; i++) lines.push({ title: a["title_" + i] || "", duration: a["duration_" + i], priority: a["priority_" + i] });
        if (!lines.some(function (l) { return l.title.trim(); })) { T.formError(form, "Write at least one task title."); return; }
        T.run("add_several", { date: a.date, start: a.start, lines: lines }, form);
      } },
    edit_task: { open: function (a) { var t = task(a); if (t) T.forms.task(t); } },
    move_task: { open: function (a) { var t = task(a); if (t) T.forms.move(t); } },
    link_task: { open: function (a) { var t = task(a); if (t) T.forms.link(t); } },
    mark_done: { open: function (a) { var t = task(a); if (t) T.forms.done(t); } },
    mark_failed: { open: function (a) { var t = task(a); if (t) T.forms.reason(t, "failed"); } },
    mark_skipped: { open: function (a) { var t = task(a); if (t) T.forms.reason(t, "skipped"); } },
    extend_task: { open: function (a) { var t = task(a); if (t) T.forms.extend(t); } },
    new_goal: { open: function (a) { T.forms.goal({ kind: a.kind, start: a.start }); } },
    edit_goal: { open: function (a) { var g = T.findGoal(a.id); if (g) T.forms.goal({ goal: g }); },
      submit: function (a, form) {
        var g = T.findGoal(a.id), args = { id: a.id, title: a.title, target: a.target, unit: a.unit };
        if ("parent_id" in a) args.parent_id = a.parent_id;
        if (g && g.target == null && a.target === "") delete args.target;
        T.run("edit_goal", args, form);
      } },
    log_progress: { open: function (a) { T.forms.log(a); } },
    notes_panel: { run: function (a, el) { T.run("notes_panel", a, el, { quiet: true }); } },
    export_data: { run: function (a, el) {
      T.run("export_data", {}, el).then(function (out) {
        if (!out || !out.export) return;
        var url = URL.createObjectURL(new Blob([JSON.stringify(out.export, null, 1)], { type: "application/json" }));
        var link = document.createElement("a"); link.href = url; link.download = out.filename; document.body.appendChild(link); link.click();
        setTimeout(function () { URL.revokeObjectURL(url); link.remove(); }, 1000);
      });
    } },
    import_data: { submit: function (a, form) {
      var file = form.querySelector("input[type=file]").files[0];
      if (!file) { T.formError(form, "Choose an export file first."); return; }
      file.text().then(function (text) { T.run("import_data", { data: text }, form); });
    } },
    choose_ampm: { ui: "send a command again with the am / pm answer",
      submit: function (a, form) {
        var args = JSON.parse(a.args || "{}");
        if (a.line !== "" && args.lines) args.lines[+a.line].ampm = a.value; else args.ampm = a.value;
        T.run(a.cmd, args, form);
      } },
    confirm: { ui: "send a destructive command again with confirmed=true",
      submit: function (a, form) { var args = JSON.parse(a.args || "{}"); args.confirmed = true; T.run(a.cmd, args, form); } },

    /* ---- the quick-add box: typed words go through the same dialog as voice ---- */
    say: { ui: "send typed words to the command dialog",
      submit: function (a, form) { var input = form.querySelector("input[name=text]"); var text = input.value; input.value = ""; T.voice.send(text, 1); } },

    /* ---- screen-only ---- */
    open_layouts: { ui: "show the layout chooser", run: function () { go("layouts"); } },
    toggle_theme: { ui: "switch light / dark (saved as a setting)", run: function () {
      var cur = document.documentElement.getAttribute("data-theme");
      T.run("set_theme", { theme: cur === "dark" ? "light" : "dark" }, null, { quiet: true });
    } },
    open_help: { ui: "show shortcuts", run: function () { T.overlay.help(); } },
    note_focus: { ui: "open Remember and put the cursor in the new note box", run: function () { T.notes.focusAdd(); } },
    open_search: { ui: "search tasks, goals and history", run: function () { T.overlay.search(); } },
    search_go: { ui: "jump to a search result", run: function (a) { T.overlay.close(); T.applyView(a); } },
    overlay_close: { ui: "close the overlay", run: function () { T.overlay.close(); } },
    mic_toggle: { ui: "start / stop listening", run: function () { T.voice.toggle(); } },
    run_mic_test: { ui: "run the mic test in this browser", run: function () { T.voice.micTest(); } },
    conv_close: { ui: "hide the conversation", run: function () { T.conv.clear(); } },
    select_task: { ui: "select a task", run: function (a) { T.view.selected = a.id; T.saveView(); T.render(); } },
    day_shift: { ui: "show another day", run: function (a) { T.view.day = T.r.addDays((T.state && T.state.day.date) || T.view.day, a.n); T.saveView(); T.refresh(true); } },
    day_today: { ui: "show today", run: function () { T.view.day = null; T.saveView(); T.refresh(true); } },
    day_pick: { ui: "pick a day", change: function (v) { T.view.day = v || null; T.saveView(); T.refresh(true); } },
    period_shift: { ui: "show another period", run: function (a) { T.view.periods[a.kind] = a.to; T.saveView(); T.refresh(true); } },
    history_filter: { ui: "filter the history", submit: function (a) { T.view.history = { goal: a.goal, from: a.from, to: a.to, status: a.status }; T.saveView(); T.refresh(true); } },
    history_clear: { ui: "clear history filters", run: function () { T.view.history = { goal: "", from: "", to: "", status: "" }; T.saveView(); T.refresh(true); } },
    nav_today: { ui: "go to today", run: function () { go("today"); } },
    nav_day: { ui: "go to the day page", run: function () { T.dlg.close(); go("day"); } },
    nav_voice: { ui: "go to voice", run: function () { go("voice"); } },
    nav_reschedule: { ui: "go to reschedule", run: function () { go("reschedule"); } },
    open_fill_in: { ui: "open the page of a missing item", run: function (a) { T.view.periods[a.kind] = a.start; T.saveView(); go(a.kind); T.refresh(true); } },
    enable_sound: { ui: "unlock and test the alarm sound", run: function () {
      T.alarmTone.unlock();
      setTimeout(function () { var ok = T.alarmTone.burst(); T.note(ok ? "Sound works. Alarms will ring in this tab." : "The browser is still blocking sound. Click anywhere on the page, then try again."); }, 50);
    } },
    enable_notifications: { ui: "ask for notification permission", run: function () {
      if (!("Notification" in window)) { T.note("This browser can't show desktop notifications. Alarms still ring and show in the tab."); return; }
      Notification.requestPermission().then(function (p) {
        T.note(p === "granted" ? "Desktop notifications are on: alarms also pop up when this tab isn't in front."
          : "Notifications are blocked. Alarms still ring and show in the tab. To allow them later, use the icon left of the address bar.");
      });
    } },
    open_setup: { ui: "start the first-run setup", run: function () { T.setup.open(0); } },
    setup_next: { ui: "next setup step", run: function (a) { T.setup.open(a.step); } },
    dismiss_missed: { ui: "hide the missed-alarms list for now", run: function () { T.hideMissed = true; T.render(); } }
  };

  /* ---------- running a command ---------- */
  function clearInline(el) {
    var host = el && (el.closest(".actions, .row, .daybar, form, .banner, .task, .goal, li, section") || el.parentNode);
    if (host) host.querySelectorAll(":scope > .inline-err").forEach(function (x) { x.remove(); });
  }
  function showInline(el, msg) {
    if (!el) { T.toast(msg, { error: true }); return; }
    var form = el.closest && el.closest("form");
    if (form && form.querySelector(".form-err")) { T.formError(form, msg); return; }
    var host = el.closest(".actions, .row, .daybar, .banner, form, .task, .goal, li, section") || el.parentNode;
    var p = document.createElement("p");
    p.className = "inline-err"; p.setAttribute("role", "alert");
    p.textContent = msg;
    host.appendChild(p);
    setTimeout(function () { p.remove(); }, 15000);
  }
  T.isCommand = function (name) { return !!(T.state && T.state.commands && T.state.commands.indexOf(name) >= 0); };
  T.run = async function (cmd, args, el, o) {
    o = o || {};
    clearInline(el);
    if (el && el.closest && el.closest("form")) T.formError(el.closest("form"), "");
    if (T.state && !T.isCommand(cmd)) {   // never send a name the running server doesn't have
      showInline(el, "This button's action (" + cmd + ") isn't in the running tomits. Close the tomits window and start it again.");
      return null;
    }
    try {
      var out = await T.api.command(cmd, args);
      if (out.needs_confirm) { T.forms.confirm(cmd, args, out.message); return out; }
      if (out.needs_choice) { T.forms.choice(cmd, args, out); return out; }
      if (el && el.closest && el.closest("#dlg")) T.dlg.close();
      if (out.understood) T.toast((out.proposal_id ? out.message + " " : "") + out.understood, { undo: out.undo_id, keep: out.undo_id && out.task_id, long: true });
      else if (!o.quiet || out.undo_id || out.proposal_id) T.toast(out.message, { undo: out.undo_id });
      if (out.proposal_id) T.pendingProposal = out.proposal_id;
      if (cmd === "cap_answer" || cmd === "collision_answer") T.pendingProposal = args.id;
      T.refresh(true);
      if (o.after) o.after(out);
      return out;
    } catch (p) {
      showInline(el, p.message);
      return null;
    }
  };

  T.after = {     // follow-ups a form can ask for with data-then
    note_added: function (out, form) { form.reset(); var ta = form.querySelector("textarea"); if (ta) { T.notes.count(ta); ta.focus(); } }
  };

  /* ---------- toasts with Undo ---------- */
  T.toast = function (msg, o) {
    o = o || {};
    var host = document.getElementById("toasts");
    var el = document.createElement("div");
    el.className = "toast" + (o.error ? " toast-err" : "");
    el.setAttribute("role", "status");
    el.innerHTML = '<span>' + T.r.esc(msg) + "</span>" + (o.undo ? T.r.btn("undo_action", { id: o.undo }, "Undo", { icon: "undo", kbd: "U" }) : "") +
      (o.keep ? T.r.btn("keep_typed_title", { id: o.keep }, "Keep title as typed", { cls: "quiet", title: "Put the title back exactly as typed and drop the time read from it" }) : "");
    T.hydrateIcons(el);
    host.appendChild(el);
    while (host.children.length > 3) host.firstChild.remove();
    var ms = o.long ? 15000 : o.undo ? 9000 : 5000;
    setTimeout(function () { el.classList.add("out"); }, ms);
    setTimeout(function () { el.remove(); }, ms + 500);
  };
  T.note = function (msg) {
    document.querySelectorAll("[data-permission-note]").forEach(function (el) { el.textContent = msg; });
    T.toast(msg);
  };

  /* ---------- wiring: clicks, forms, changes ---------- */
  function argsOf(el) { try { return JSON.parse(el.getAttribute("data-args") || "{}"); } catch (e) { return {}; } }
  T.trigger = function (name, args, el) {
    var entry = A[name];
    if (entry && entry.open) return entry.open(args, el);
    if (entry && entry.run) return entry.run(args, el);
    if (!entry || !entry.ui) return T.run(name, args, el);   // a registry command
  };
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("[data-act]");
    if (!el || el.tagName === "SELECT" || (el.tagName === "INPUT" && el.type !== "button")) return;
    if (el.disabled) return;
    e.preventDefault();
    T.trigger(el.getAttribute("data-act"), argsOf(el), el);
  });
  document.addEventListener("change", function (e) {
    var el = e.target;
    if (el.matches && el.matches("select[data-act], input[data-act]")) {
      var entry = A[el.getAttribute("data-act")];
      if (entry && entry.change) entry.change(el.value, el);
    }
    if (el.matches && el.matches("[data-autosubmit]")) {
      var form = el.closest("form");
      if (form) form.requestSubmit();
    }
  });
  document.addEventListener("submit", function (e) {
    var form = e.target, name = form.getAttribute("data-form");
    if (!name) return;
    e.preventDefault();
    var entry = A[name], args = T.formArgs(form);
    if (entry && entry.submit) return entry.submit(args, form);
    if (name === "voice_settings") ["spoken_replies", "llm_enabled"].forEach(function (k) { args[k] = !!args[k]; });
    var then = form.getAttribute("data-then");   // e.g. the next setup step
    T.run(name, args, form).then(function (out) { if (out && then && T.after[then]) T.after[then](out, form); });
  });

  /* process / review: saved while you type (after a pause) and when you leave the box */
  var pending = {};
  function autosave(el) {
    var id = el.id, value = el.value;
    if (el.readOnly || el.getAttribute("data-saved") === value) return;
    clearTimeout(pending[id]);
    var note = document.querySelector('[data-note-for="' + id + '"]');
    if (note) note.textContent = "Saving…";
    T.run(el.getAttribute("data-autosave"), { kind: el.getAttribute("data-kind"), start: el.getAttribute("data-start"), text: value }, el, { quiet: true })
      .then(function (out) {
        if (out) { el.setAttribute("data-saved", value); el.defaultValue = value; }
        var n = document.querySelector('[data-note-for="' + id + '"]');
        if (n) n.textContent = out ? "Saved " + new Date().toTimeString().slice(0, 5) : "Not saved: your text is still here.";
      });
  }
  document.addEventListener("input", function (e) {
    var el = e.target;
    if (el.matches && el.matches("textarea[data-autosave]")) {
      clearTimeout(pending[el.id]);
      pending[el.id] = setTimeout(function () { autosave(el); }, 1200);
    }
  });
  document.addEventListener("focusout", function (e) {
    var el = e.target;
    if (el.matches && el.matches("textarea[data-autosave]")) { clearTimeout(pending[el.id]); autosave(el); }
  });

  /* ---------- keyboard shortcuts ---------- */
  T.SHORTCUTS = [
    ["Ctrl K", "Type or say a command (quick add box)"], ["/", "Search tasks, goals and history"],
    ["A", "Add a task"], ["D", "Done: the selected or current task"], ["F", "Failed: the selected or current task"],
    ["S", "Skip: the selected or current task"], ["X", "Still going: extend the current task"],
    ["P", "Plan my day"], ["N", "Add a note to Remember"], ["U", "Undo the last change"], ["L", "Switch layout"],
    ["V", "Push to talk: hold to speak, or tap to start and tap again to stop"], ["?", "This help"], ["Esc", "Close a dialog or panel"]
  ];
  var vDown = 0;
  function typing(t) { return t.closest && t.closest("input, textarea, select, [contenteditable]"); }
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) { e.preventDefault(); document.getElementById("qa-input").focus(); return; }
    if (e.key === "Escape") { if (!T.conv.asking) T.conv.clear(); T.overlay.close(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || typing(e.target) || T.dlg.isOpen() || document.getElementById("alarm-dlg").open && e.key !== "v") return;
    var k = e.key.toLowerCase(), sel = T.r.selectedTask(), st = T.state;
    if (!st) return;
    if (k === "v") { e.preventDefault(); if (e.repeat) return; vDown = Date.now(); if (!T.voice.recording()) T.voice.start(); else T.voice.stop(); return; }
    var map = {
      "/": function () { T.overlay.search(); }, "?": function () { T.overlay.help(); },
      n: function () { T.notes.focusAdd(); },
      a: function () { T.trigger("add_task", { date: st.day.date }); },
      p: function () { T.trigger("plan_day", { date: st.day.date }); },
      u: function () { if (st.undo) T.trigger("undo_action", { id: st.undo.id }); else T.toast("There's nothing to undo."); },
      l: function () { T.trigger("open_layouts", {}); },
      d: function () { if (sel) T.trigger("mark_done", { id: sel.id }); },
      f: function () { if (sel) T.trigger("mark_failed", { id: sel.id }); },
      s: function () { if (sel) T.trigger("mark_skipped", { id: sel.id }); },
      x: function () { if (sel) T.trigger("extend_task", { id: sel.id }); }
    };
    var fn = map[e.key] || map[k];
    if (fn) { e.preventDefault(); fn(); }
  });
  document.addEventListener("keyup", function (e) {
    if (e.key.toLowerCase() === "v" && vDown && !typing(e.target)) {
      var held = Date.now() - vDown; vDown = 0;
      if (held > 350 && T.voice.recording()) T.voice.stop();  // held: push-to-talk; a quick tap toggles
    }
  });
})();
