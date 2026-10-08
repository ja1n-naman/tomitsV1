/* ==========================================================================
   screens.js: the generic screen patterns (UI_GUIDE.md §6) and the item
   building blocks every layout composes: item row, badges, actions, toolbar,
   stats, decision card, progress card, history with filters, settings, and a
   "later" placeholder. Layouts arrange these; they never rewrite them.
   All content comes from UI.data (demo-content.js). Wording here is generic UI.
   ========================================================================== */
(function () {
  var UI = window.UI, esc = UI.esc, btn = UI.btn, I = function (n) { return UI.icon(n); }, D = UI.date;
  var R = UI.r = {};

  /* ---------- item badges ---------- */
  R.kind = function (t) { return UI.data.kinds[t.kind] || { label: t.kind || "", icon: "clock", hint: "" }; };
  R.kindBadge = function (t) { var k = R.kind(t); return '<span class="kind k-' + esc(t.kind) + '" title="' + esc(k.hint) + '">' + I(k.icon) + esc(k.label) + "</span>"; };
  R.fixedMark = function (t) { return t.kind === "fixed" ? '<span class="fixedmark" title="' + esc(R.kind(t).hint) + '">' + I("anchor") + '<span class="sr">' + esc(R.kind(t).label) + "</span></span>" : ""; };
  R.statusBadge = function (t) {
    if (t.status === "pending") return t.running ? '<span class="st st-now">Now</span>' : "";
    return '<span class="st st-' + t.status + '">' + { done: "Done", failed: "Failed", skipped: "Skipped" }[t.status] + "</span>";
  };
  R.prio = function (t) { return '<span class="prio p' + t.priority + '">P' + t.priority + " " + esc(t.priority_name) + "</span>"; };
  R.when = function (t) { return t.start ? '<span class="tm">' + t.start + "–" + t.end + "</span>" : '<span class="tm tm-none">no time</span>'; };
  R.why = function (t) {
    if (t.status === "failed" || t.status === "skipped") return '<p class="why why-closed"><b>' + (t.status === "failed" ? "Failed" : "Skipped") + ", because:</b> " + esc(t.fail_reason) + "</p>";
    var text = t.reason || (t.start ? "" : "no time yet; " + esc(UI.data.mainAction || "the automatic action") + " places it");
    return text ? '<p class="why"><b>Why here:</b> ' + esc(text) + "</p>" : "";
  };
  R.linkChip = function (t) { return t.link ? '<span class="linkchip" title="' + esc(UI.data.linkLabel || "Linked") + '">' + I("target") + esc(t.link.title) + " <small>" + esc(t.link.text) + "</small></span>" : ""; };

  /* ---------- actions an item can take (same buttons in every layout) ---------- */
  R.itemActions = function (t, o) {
    o = o || {};
    var a = { id: t.id }, out = [];
    if (t.status === "pending") {
      out.push(btn("item_done", a, "Done", { icon: "check", cls: "primary", kbd: o.keys ? "D" : null, aria: "Done: " + t.title }));
      out.push(btn("item_failed", a, "Failed", { icon: "x-circle", kbd: o.keys ? "F" : null, aria: "Failed: " + t.title }));
      out.push(btn("item_skip", a, "Skip", { icon: "skip", kbd: o.keys ? "S" : null, aria: "Skip: " + t.title }));
      if (t.running) out.push(btn("item_extend", a, "Extend", { icon: "timer", kbd: o.keys ? "X" : null }));
      out.push(btn("item_move", a, t.start ? "Move" : "Set time", { icon: "clock", aria: "Move " + t.title }));
      if (t.kind === "pinned") out.push(btn("item_pin", { id: t.id, pin: false }, "Unpin", { icon: "unlock" }));
      else if (t.start && t.kind !== "fixed") out.push(btn("item_pin", { id: t.id, pin: true }, "Pin", { icon: "pin" }));
      if (!o.short) {
        out.push(btn("item_edit", a, "Edit", { icon: "edit" }));
        out.push(btn("item_delete", a, "", { icon: "trash", aria: "Delete " + t.title, cls: "quiet" }));
      }
    } else if (t.status === "failed" || t.status === "skipped") {
      out.push(btn("item_retry", a, "Try again later", { icon: "cycle" }));
    }
    return '<div class="actions">' + out.join("") + "</div>";
  };
  R.itemRow = function (t, o) {
    o = o || {};
    var sel = UI.view.selected === t.id ? " is-sel" : "";
    return '<article class="item s-' + t.status + " k-" + esc(t.kind) + (t.running && t.status === "pending" ? " is-now" : "") + sel + '" data-item="' + t.id + '">' +
      '<div class="item-top">' + R.when(t) + '<h3 class="item-title">' + esc(t.title) + "</h3>" + R.statusBadge(t) + "</div>" +
      '<div class="item-meta">' + R.kindBadge(t) + R.prio(t) + '<span class="dur">' + t.duration_text + "</span>" + R.linkChip(t) + "</div>" +
      R.why(t) + (o.noActions ? "" : R.itemActions(t, o)) + "</article>";
  };

  /* ---------- toolbar, stats, lists ---------- */
  var tbN = 0;
  R.toolbar = function (o) {
    o = o || {};
    var d = UI.day(UI.view.dayOffset), past = UI.view.dayOffset < 0, pid = "day-pick-" + (++tbN);   // unique id: a page can show two toolbars (layout 3 drawer)
    return '<div class="toolbar">' +
      '<div class="toolbar-nav">' + btn("day_shift", { n: -1 }, "", { icon: "chev-left", aria: "Previous day" }) +
      '<label class="sr" for="' + pid + '">Day</label><input type="date" id="' + pid + '" data-act="day_pick" value="' + d.date + '">' +
      btn("day_shift", { n: 1 }, "", { icon: "chev-right", aria: "Next day" }) + (UI.view.dayOffset ? btn("day_shift", { to: 0 }, "Today") : "") + "</div>" +
      '<div class="toolbar-act">' + btn("main_action", null, esc(UI.data.mainAction || "Run"), { icon: "route", kbd: "P", disabled: past, title: past ? "Past days never change" : "" }) +
      btn("item_add", null, "Add item", { icon: "plus", cls: "primary", kbd: "A" }) +
      (o.compact ? "" : btn("day_clear", null, "Clear", { icon: "trash", cls: "quiet", disabled: past })) + "</div></div>";
  };
  R.stats = function (d) {
    var all = d.items.concat(d.untimed), n = function (s) { return all.filter(function (t) { return t.status === s; }).length; };
    var busy = d.items.reduce(function (m, t) { return m + (t.duration || 0); }, 0);
    var span = D.toMin(UI.data.window.end) - D.toMin(UI.data.window.start);
    return '<dl class="stats"><div><dt>Items</dt><dd>' + all.length + "</dd></div><div><dt>Done</dt><dd>" + n("done") + "</dd></div><div><dt>Failed / skipped</dt><dd>" + (n("failed") + n("skipped")) +
      "</dd></div><div><dt>Unscheduled</dt><dd>" + d.untimed.length + "</dd></div><div><dt>Free time</dt><dd>" + D.dur(Math.max(0, span - busy)) + "</dd></div></dl>";
  };
  R.untimedList = function (d) {
    if (!d.untimed.length) return '<p class="muted small">Everything on this day has a time.</p>';
    return '<ul class="items">' + d.untimed.map(function (t) { return "<li>" + R.itemRow(t, { short: true }) + "</li>"; }).join("") + "</ul>";
  };
  R.olderList = function () {
    if (UI.preview() === "empty" || !UI.data.older.length) return "";
    return '<section class="panel older"><h2 class="panel-h">' + I("alert") + "Still open from earlier days</h2>" + UI.data.older.map(function (t) { return R.itemRow(t, { short: true }); }).join("") + "</section>";
  };
  R.emptyDay = function (d) {
    return UI.state(UI.empty("Nothing on " + esc(D.label(d.date)) + " yet. Add the first item; items with a time stay put, and " + esc(UI.data.mainAction || "the automatic action") + " places the rest.",
      btn("item_add", null, "Add your first item", { icon: "plus", cls: "primary", kbd: "A" })));
  };

  /* ---------- decision card ---------- */
  R.decisionCard = function (p) {
    return '<section class="decision" data-decision="' + p.id + '"><p class="eyebrow">Waiting for your decision</p><h3>' + esc(p.title) + ' <span class="muted small">' + esc(p.trigger || "") + "</span></h3>" +
      '<ol class="moves">' + p.moves.map(function (m) {
        return '<li class="mv"><span class="mv-kind">' + esc(m.kind) + '</span><div><p class="mv-title">' + esc(m.title) + '</p><p class="mv-path"><s>' + esc(m.from) + "</s>" + I("arrow-right") + "<b>" + esc(m.to) + "</b></p>" +
          '<p class="why"><b>Why:</b> ' + esc(m.why) + "</p></div></li>";
      }).join("") + "</ol>" +
      '<div class="actions">' + btn("decision", { id: p.id, answer: "accept" }, "Accept", { icon: "check", cls: "primary" }) + btn("decision", { id: p.id, answer: "reject" }, "Reject", { icon: "x" }) + "</div>" +
      '<p class="muted small">Nothing changes until you accept.</p></section>';
  };
  R.decisions = function () { return UI.preview() === "empty" ? [] : UI.data.decisions; };

  /* ---------- progress ---------- */
  R.group = function () { var g = UI.data.progress.filter(function (x) { return x.key === UI.view.group; })[0]; return g || UI.data.progress[0]; };
  R.progText = function (e) { return e.target != null ? (e.value || 0) + " / " + e.target + " " + (e.unit || "") : (e.done ? "done" : "not done"); };
  R.progressCard = function (e, g) {
    var frac = e.target ? Math.min(1, (e.value || 0) / e.target) : 0;
    var bar = e.target != null ? '<span class="bar" role="progressbar" aria-label="' + esc(e.title) + '" aria-valuenow="' + Math.round(frac * 100) + '" aria-valuemin="0" aria-valuemax="100"><span style="width:' + frac * 100 + '%"></span></span>' : "";
    var roll = (e.parents || []).length ? '<p class="rolls">Rolls up to: ' + e.parents.map(function (p) { return esc(p.title) + " <b>" + esc(p.text) + "</b>"; }).join(" → ") + "</p>" : "";
    var logs = (e.logs || []).length ? '<details class="logs"><summary>' + e.logs.length + " log" + (e.logs.length > 1 ? "s" : "") + "</summary><ul>" +
      e.logs.map(function (l) { return "<li>" + D.label(UI.date.offset(l.offset), true) + ": <b>" + l.amount + "</b> " + esc(e.unit || "") + "</li>"; }).join("") + "</ul></details>" : "";
    var acts = g.locked ? "" : '<div class="actions">' + (e.target != null ? btn("prog_log", { id: e.id }, "Log progress", { icon: "plus", cls: "primary" })
      : btn("prog_done", { id: e.id }, e.done ? "Mark not done" : "Mark done", { icon: "check", cls: e.done ? "" : "primary" })) + "</div>";
    return '<li class="prog' + (e.done ? " is-done" : "") + '"><div class="prog-top"><h3>' + esc(e.title) + '</h3><span class="prog-num">' + esc(R.progText(e)) + "</span></div>" + bar + roll + logs + acts + "</li>";
  };
  R.progressSummary = function () {   // compact rows for side panels and panes
    if (UI.preview() !== "normal") return UI.state(UI.empty("No progress entries yet."));
    return '<ul class="items">' + UI.data.progress.map(function (g) {
      return '<li class="prog"><div class="prog-top"><span class="eyebrow">' + esc(g.label) + "</span>" + (g.locked ? '<span class="muted small">' + I("lock") + "read-only</span>" : "") + "</div>" +
        (g.entries.length ? g.entries.map(function (e) { return '<div class="prog-top"><span>' + esc(e.title) + '</span><b class="prog-num">' + esc(R.progText(e)) + "</b></div>"; }).join("") : '<p class="warn small">nothing yet</p>') + "</li>";
    }).join("") + "</ul>";
  };

  /* ---------- screens (patterns) ---------- */
  var S = UI.screens = {};
  S.list = function () {
    var d = UI.day(UI.view.dayOffset), all = d.items.concat(d.untimed);
    return '<h2 class="screen-title">List</h2><p class="lead-line">' + esc(D.long(d.date)) + ". Placeholder list screen: every row shows why it is where it is.</p>" + R.toolbar() +
      (UI.preview() !== "normal" && UI.preview() !== "empty" ? UI.state("") : all.length ? '<ol class="items">' + d.items.map(function (t) { return "<li>" + R.itemRow(t) + "</li>"; }).join("") + "</ol>" +
        (d.untimed.length ? '<h3 class="sec-h">Unscheduled</h3><ol class="items">' + d.untimed.map(function (t) { return "<li>" + R.itemRow(t) + "</li>"; }).join("") + "</ol>" : "") : R.emptyDay(d)) + R.olderList();
  };
  S.detail = function (t) {   // the selected item, larger, with keyboard hints
    if (!t) return UI.empty("Select an item to see why it is there and what you can do with it.");
    return R.itemRow(t, { keys: true });
  };
  S.progress = function () {
    var g = R.group();
    if (!g) return '<h2 class="screen-title">Progress</h2>' + UI.state(UI.empty("No progress groups yet."));
    var tabs = '<nav class="ptabs" aria-label="Group">' + UI.data.progress.map(function (x) {
      return '<a href="#progress" data-act="prog_group" data-args=\'{"key":"' + x.key + '"}\'' + (x.key === g.key ? ' aria-current="page"' : "") + ">" + esc(x.label) + "</a>"; }).join("") + "</nav>";
    var lock = g.locked ? '<div class="lock l-locked">' + I("lock") + "<span><b>Read-only:</b> placeholder text explaining why this group can't change any more.</span></div>"
      : '<div class="lock l-open">' + I("unlock") + "<span>Open. Placeholder text saying until when this can change.</span></div>";
    var entries = UI.preview() === "normal" && g.entries.length ? '<ul class="progs">' + g.entries.map(function (e) { return R.progressCard(e, g); }).join("") + "</ul>"
      : UI.state(UI.empty("No entries in " + esc(g.label) + " yet. Add the first one; items can link to it.", g.locked ? "" : btn("prog_add", null, "Add an entry", { icon: "plus", cls: "primary" })));
    var note = '<label class="field-l" for="prog-note">Notes for this group</label><textarea id="prog-note" rows="3" data-keep data-autosave' + (g.locked ? " readonly" : "") + ' placeholder="Placeholder: free text that saves as you type">' + esc(g.note || "") + '</textarea><p class="save-note" data-note-for="prog-note"></p>';
    return '<div class="progress">' + tabs + '<header class="period-h"><div><p class="eyebrow">Progress</p><h2 class="screen-title">' + esc(g.label) + '</h2><p class="muted">' + esc(g.sub || "") + "</p></div></header>" + lock +
      '<div class="prog-grid"><section><h3 class="sec-h">Entries</h3>' + entries + (g.locked || UI.preview() !== "normal" ? "" : btn("prog_add", null, "New entry", { icon: "plus" })) + "</section>" +
      '<section><h3 class="sec-h">Notes</h3>' + note + "</section></div></div>";
  };
  S.history = function () {
    var f = UI.view.history, rows = UI.preview() === "normal" ? UI.data.history : [];
    var groups = []; UI.data.history.forEach(function (h) { if (h.group && groups.indexOf(h.group) < 0) groups.push(h.group); });
    var shown = rows.filter(function (h) { return (!f.group || h.group === f.group) && (!f.status || h.status === f.status); });
    var filters = '<form class="filters" data-form="history_filter"><label>Group <select name="group"><option value="">All groups</option>' +
      groups.map(function (g) { return "<option" + (f.group === g ? " selected" : "") + ">" + esc(g) + "</option>"; }).join("") + "</select></label>" +
      '<label>Status <select name="status"><option value="">Failed and skipped</option><option value="failed"' + (f.status === "failed" ? " selected" : "") + '>Failed</option><option value="skipped"' + (f.status === "skipped" ? " selected" : "") + ">Skipped</option></select></label>" +
      '<button type="submit" class="btn">' + I("filter") + "Apply</button>" + btn("history_clear", null, "Clear", { cls: "quiet" }) + '<span class="muted small">' + shown.length + " of " + rows.length + "</span></form>";
    var list = shown.map(function (r) {
      return '<li class="hrow"><span class="st st-' + r.status + '">' + (r.status === "failed" ? "Failed" : "Skipped") + "</span><div><p><b>" + esc(r.title) + '</b> <span class="muted">' + D.label(r.date, true) + (r.group ? " · " + esc(r.group) : "") +
        '</span></p><p class="hreason">“' + esc(r.reason) + '”</p>' + (r.action ? btn("item_retry", { id: 2 }, "Try again later", { icon: "cycle", cls: "tiny" }) : "") + "</div></li>";
    }).join("");
    return '<h2 class="screen-title">History</h2><p class="lead-line">Placeholder history screen: every failed or skipped item with its reason.</p>' + filters +
      (UI.preview() === "loading" || UI.preview() === "error" ? UI.state("") : rows.length ? (list ? '<ol class="hlist">' + list + "</ol>" : UI.empty("Nothing matches these filters.", btn("history_clear", null, "Clear filters")))
        : UI.empty("Nothing has failed or been skipped yet. Reasons will be kept here.", btn("item_add", null, "Add an item", { icon: "plus" })));
  };
  S.later = function () {
    var L = UI.data.later || {};
    return '<h2 class="screen-title">Later</h2><div class="later-box"><span class="tag">Coming later</span><p><b>' + esc(L.title || "") + "</b></p><p>" + esc(L.text || "") + "</p>" + btn("nav", { screen: "home" }, "Back to home", { icon: "today" }) + "</div>";
  };
  S.settings = function () {
    var theme = UI.store.get("uikit.theme", "system"), slots = document.documentElement.getAttribute("data-slots") !== "off", p = UI.preview();
    var seg = function (act, cur, opts) { return '<span class="seg">' + opts.map(function (o) { return btn(act, { value: o[0] }, o[1], { pressed: cur === o[0] }); }).join("") + "</span>"; };
    return '<h2 class="screen-title">Settings</h2><p class="lead-line">Changes save as soon as you make them.</p><div class="settings">' +
      '<div class="panel"><h3 class="panel-h">Look</h3><div class="row"><span>Theme</span>' + seg("set_theme", theme, [["system", "System"], ["light", "Light"], ["dark", "Dark"]]) + "</div>" +
      '<div class="row"><span>Layout</span>' + btn("open_layouts", null, "Layout " + UI.layout.id + " · change", { icon: "layers", kbd: "L" }) + "</div>" +
      '<div class="row"><label for="s-slots">Show slot labels (kit only)</label><input id="s-slots" type="checkbox" data-act="toggle_slots"' + (slots ? " checked" : "") + "> <kbd>G</kbd></div></div>" +
      '<form class="panel" data-form="settings_save"><h3 class="panel-h">Placeholder settings</h3>' +
      '<div class="row"><label for="s-ws">Window starts</label><input id="s-ws" type="time" name="start" value="' + UI.data.window.start + '" data-act="autosave"></div>' +
      '<div class="row"><label for="s-we">Window ends</label><input id="s-we" type="time" name="end" value="' + UI.data.window.end + '" data-act="autosave"></div>' +
      '<p class="muted small">Placeholder help text under a setting. Saved on change; there is no Save button.</p>' +
      '<div class="row">' + btn("alarm_test", null, "Ring the alarm now", { icon: "bell" }) + btn("sound_enable", null, "Test sound", { icon: "volume" }) + '</div><p class="small" data-permission-note></p></form>' +
      '<div class="panel"><h3 class="panel-h">Kit preview</h3>' +
      '<div class="row"><label for="s-prev">Screen state</label><select id="s-prev" data-act="set_preview">' + [["normal", "Normal"], ["empty", "Empty"], ["loading", "Loading"], ["error", "Error"]].map(function (o) { return '<option value="' + o[0] + '"' + (p === o[0] ? " selected" : "") + ">" + o[1] + "</option>"; }).join("") + "</select></div>" +
      '<div class="row"><span>Connection</span>' + btn("simulate_offline", null, UI.online ? "Simulate connection lost" : "Restore connection", { icon: "alert" }) + "</div>" +
      '<div class="row"><span>Banners</span>' + btn("banners_reset", null, "Show the demo banners again") + "</div>" +
      '<div class="row"><span>First-run setup</span>' + btn("setup_open", null, "Run it again") + "</div>" +
      '<div class="row"><span>Refusal</span>' + btn("demo_refuse", null, "Show an inline error") + "</div></div>" +
      '<div class="panel"><h3 class="panel-h">Voice</h3><div class="row"><span>Microphone</span>' + btn("mic_mute", null, UI.store.get("uikit.muted", false) ? "Unmute the mic" : "Mute the mic", { icon: "mic-off" }) + UI.navLink("voice", "Mic test", { cls: "btn" }) + "</div>" +
      '<p class="muted small">The kit\'s mic is fake: nothing is recorded or sent anywhere.</p></div>' +
      '<div class="panel danger-zone"><h3 class="panel-h">' + I("alert") + 'Delete</h3><p class="small">Placeholder text: what can and can\'t be deleted. You\'ll see exactly what goes before anything happens.</p>' +
      '<div class="row">' + btn("delete_all", null, "Delete all placeholder items", { cls: "danger" }) + "</div></div></div>";
  };

  /* ---------- actions ---------- */
  var A = UI.actions;
  function withItem(a, fn) { var t = UI.findItem(a.id); if (!t) { UI.toast && UI.toast("That item isn't on screen any more."); return; } fn(t); }
  function reasonForm(t, status) {
    var failed = status === "failed";
    UI.dlg.open((failed ? "Why didn’t “" : "Why skip “") + esc(t.title) + "”" + (failed ? " work?" : "?"),
      '<form data-form="item_reason" class="form"><input type="hidden" name="id" value="' + t.id + '"><input type="hidden" name="status" value="' + status + '">' +
      '<p class="muted">Nothing changes until a reason is saved. Reasons are kept.</p><label class="field-l" for="r-text">Reason</label><textarea id="r-text" name="reason" rows="4" required maxlength="1000" autofocus></textarea>' +
      '<p class="hint">Required.</p>' + UI.dlg.foot(failed ? "Save reason, mark failed" : "Save reason, skip") + "</form>",
      { onOpen: function (d) { var ta = d.querySelector("textarea"), sub = d.querySelector("[type=submit]"); var sync = function () { sub.disabled = !ta.value.trim(); }; ta.addEventListener("input", sync); sync(); } });
  }
  function overlaps(t, start, end) {
    var a = D.toMin(start), b = D.toMin(end);
    return UI.day(0).items.concat(UI.allItems().filter(function (x) { return x.date === t.date && x.start; })).filter(function (o) {
      return o.id !== t.id && o.start && o.date === t.date && D.toMin(o.start) < b && a < D.toMin(o.end);
    })[0];
  }
  A.item_done = { run: function (a) { withItem(a, function (t) { UI.change("Done: " + t.title, function () { var x = UI.findItem(t.id); x.status = "done"; x.running = false; }); }); } };
  A.item_failed = { run: function (a) { withItem(a, function (t) { reasonForm(t, "failed"); }); } };
  A.item_skip = { run: function (a) { withItem(a, function (t) { reasonForm(t, "skipped"); }); } };
  A.item_reason = { submit: function (f, form) {
    if (!f.reason.trim()) { UI.formError(form, "A reason is required."); return; }
    UI.dlg.close();
    UI.change((f.status === "failed" ? "Failed: " : "Skipped: ") + UI.findItem(f.id).title, function (data) {
      var x = UI.findItem(f.id); x.status = f.status; x.running = false; x.fail_reason = f.reason;
      data.history.unshift({ id: Date.now(), date: x.date, title: x.title, status: f.status, reason: f.reason, group: "" });
    });
  } };
  A.item_extend = { run: function (a) { withItem(a, function (t) {
    UI.dlg.open("Extend “" + esc(t.title) + "”", '<form data-form="item_extend" class="form"><input type="hidden" name="id" value="' + t.id + '"><p class="muted">Planned to end at ' + t.end + '.</p><label class="field-l" for="x-min">Minutes to add</label><input id="x-min" type="number" name="minutes" min="1" max="600" value="15" autofocus>' + UI.dlg.foot("Extend") + "</form>");
  }); }, submit: function (f, form) {
    var t = UI.findItem(f.id), end = D.fromMin(Math.min(1439, D.toMin(t.end) + (+f.minutes || 0))), hit = overlaps(t, t.start, end);
    if (hit) { UI.formError(form, "Placeholder refusal: that would overlap “" + hit.title + "” at " + hit.start + ". Nothing was changed."); return; }
    UI.dlg.close(); UI.change("Extended: " + t.title, function () { var x = UI.findItem(t.id); x.end = end; x.duration = D.toMin(end) - D.toMin(x.start); x.duration_text = D.dur(x.duration); });
  } };
  A.item_move = { run: function (a) { withItem(a, function (t) {
    UI.dlg.open("Move “" + esc(t.title) + "”", '<form data-form="item_move" class="form"><input type="hidden" name="id" value="' + t.id + '"><label class="field-l" for="m-start">New start time</label><input id="m-start" type="time" name="start" value="' + (t.start || "") + '" required autofocus>' +
      '<p class="hint">Moving an item pins it. Overlaps are refused.</p>' + UI.dlg.foot("Move") + "</form>");
  }); }, submit: function (f, form) {
    var t = UI.findItem(f.id), end = D.fromMin(D.toMin(f.start) + (t.duration || 30)), hit = overlaps(t, f.start, end);
    if (hit) { UI.formError(form, "Placeholder refusal: that would overlap “" + hit.title + "” (" + hit.start + "–" + hit.end + "). Nothing was changed."); return; }
    UI.dlg.close();
    UI.change("Moved: " + t.title + " to " + f.start, function (data) {
      var x = UI.findItem(t.id), day = data.days.filter(function (d) { return d.date === x.date; })[0];
      if (!x.start && day) { day.untimed = day.untimed.filter(function (u) { return u.id !== x.id; }); day.items.push(x); }
      x.start = f.start; x.end = end; if (x.kind !== "fixed") x.kind = "pinned";
      if (day) day.items.sort(function (p, q) { return D.toMin(p.start) - D.toMin(q.start); });
    });
  } };
  A.item_pin = { run: function (a) { withItem(a, function (t) { UI.change((a.pin ? "Pinned: " : "Unpinned: ") + t.title, function () { UI.findItem(t.id).kind = a.pin ? "pinned" : "auto"; }); }); } };
  function itemForm(t) {
    t = t || {};
    UI.dlg.open(t.id ? "Edit item" : "Add an item", '<form data-form="item_save" class="form">' + (t.id ? '<input type="hidden" name="id" value="' + t.id + '">' : "") +
      '<label class="field-l" for="f-title">Title</label><input id="f-title" name="title" required maxlength="200" value="' + esc(t.title || "") + '" autofocus>' +
      '<div class="cols"><div><label class="field-l" for="f-dur">Duration (minutes)</label><input id="f-dur" name="duration" type="number" min="5" max="600" value="' + (t.duration || 30) + '"></div>' +
      '<div><label class="field-l" for="f-start">Start time (optional)</label><input id="f-start" type="time" name="start" value="' + (t.start || "") + '"><p class="hint">With a time it stays put; without one it is placed for you.</p></div></div>' +
      UI.dlg.foot(t.id ? "Save changes" : "Add item") + "</form>");
  }
  A.item_add = { run: function () { itemForm(null); } };
  A.item_edit = { run: function (a) { withItem(a, itemForm); } };
  A.item_save = { submit: function (f, form) {
    if (!f.title.trim()) { UI.formError(form, "Write a title."); return; }
    var dur = Math.max(5, +f.duration || 30), cur = f.id ? UI.findItem(f.id) : { id: Date.now(), date: UI.day(UI.view.dayOffset).date };
    var end = f.start ? D.fromMin(D.toMin(f.start) + dur) : null;
    if (f.start) { var hit = overlaps(cur, f.start, end); if (hit) { UI.formError(form, "Placeholder refusal: that would overlap “" + hit.title + "” (" + hit.start + "–" + hit.end + ")."); return; } }
    UI.dlg.close();
    UI.change((f.id ? "Saved: " : "Added: ") + f.title, function (data) {
      var day = data.days.filter(function (d) { return d.offset === UI.view.dayOffset; })[0];
      if (!day) { day = { offset: UI.view.dayOffset, date: UI.date.offset(UI.view.dayOffset), items: [], untimed: [] }; data.days.push(day); }
      if (f.id) { day.items = day.items.filter(function (x) { return x.id !== +f.id; }); day.untimed = day.untimed.filter(function (x) { return x.id !== +f.id; }); }
      var old = f.id ? cur : {};
      var t = Object.assign({}, old, { id: f.id ? +f.id : cur.id, title: f.title.trim(), duration: dur, duration_text: D.dur(dur), start: f.start || null, end: end, date: day.date,
        status: old.status || "pending", kind: f.start ? (old.kind && old.kind !== "untimed" ? old.kind : "fixed") : "untimed", priority: old.priority || 3 });
      t.priority_name = data.priorities[t.priority] || "";
      if (t.start) { day.items.push(t); day.items.sort(function (p, q) { return D.toMin(p.start) - D.toMin(q.start); }); } else day.untimed.push(t);
    });
  } };
  A.item_delete = { run: function (a) { withItem(a, function (t) {
    var go = function () { UI.change("Deleted: " + t.title, function (data) { data.days.forEach(function (d) { d.items = d.items.filter(function (x) { return x.id !== t.id; }); d.untimed = d.untimed.filter(function (x) { return x.id !== t.id; }); }); data.older = data.older.filter(function (x) { return x.id !== t.id; }); }); };
    if (UI.confirm) UI.confirm("This deletes “" + t.title + "”" + (t.start ? " (" + t.start + "–" + t.end + ")" : "") + ". Undo can bring it back.", go); else go();
  }); } };
  A.item_retry = { run: function (a) { UI.toast && UI.toast("Placeholder: a decision card would offer a new time."); } };
  A.day_shift = { run: function (a) { UI.view.dayOffset = a.to != null ? a.to : UI.view.dayOffset + a.n; UI.saveView(); UI.render(); } };
  A.day_pick = { change: function (v) {
    var ms = (new Date(v + "T12:00") - new Date(UI.date.today() + "T12:00")) / 864e5; UI.view.dayOffset = isNaN(ms) ? 0 : Math.round(ms); UI.saveView(); UI.render();
  } };
  A.main_action = { run: function () {
    var d = UI.day(UI.view.dayOffset);
    if (!d.untimed.filter(function (t) { return t.status === "pending"; }).length) { UI.toast && UI.toast("Nothing to arrange: every item already has a time."); return; }
    UI.change(UI.data.mainAction + ": placed the unscheduled items.", function (data) {
      var day = data.days.filter(function (x) { return x.offset === UI.view.dayOffset; })[0], cur = Math.max(D.toMin(data.window.start), UI.view.dayOffset === 0 ? D.toMin(data.now) : 0);
      day.untimed.filter(function (t) { return t.status === "pending"; }).forEach(function (t) {
        var busy = day.items.map(function (x) { return [D.toMin(x.start), D.toMin(x.end)]; }).sort(function (p, q) { return p[0] - q[0]; }), s = cur;
        busy.forEach(function (b) { if (s + t.duration > b[0] && s < b[1]) s = b[1]; });
        t.start = D.fromMin(s); t.end = D.fromMin(s + t.duration); t.kind = "auto"; t.reason = "Placeholder reason: the first free slot that fits";
        day.items.push(t); day.items.sort(function (p, q) { return D.toMin(p.start) - D.toMin(q.start); });
      });
      day.untimed = day.untimed.filter(function (t) { return !t.start; });
    }, { long: true });
  } };
  A.day_clear = { run: function () {
    var d = UI.day(UI.view.dayOffset), n = d.items.concat(d.untimed).filter(function (t) { return t.status === "pending"; }).length;
    var go = function () { UI.change("Cleared " + n + " open items.", function (data) { var day = data.days.filter(function (x) { return x.offset === UI.view.dayOffset; })[0]; if (day) { day.items = day.items.filter(function (t) { return t.status !== "pending"; }); day.untimed = day.untimed.filter(function (t) { return t.status !== "pending"; }); } }); };
    if (UI.confirm) UI.confirm("This removes " + n + " open items from " + D.label(d.date) + ". Done, failed and skipped items stay.", go); else go();
  } };
  A.delete_all = { run: function () {
    var n = UI.allItems().length;
    var go = function () { UI.change("Deleted " + n + " placeholder items.", function (data) { data.days.forEach(function (d) { d.items = []; d.untimed = []; }); data.older = []; }); };
    if (UI.confirm) UI.confirm("This deletes all " + n + " placeholder items. History rows stay. Undo can bring them back.", go); else go();
  } };
  A.decision = { run: function (a) {
    UI.change(a.answer === "accept" ? "Accepted the placeholder decision." : "Rejected: nothing moved.", function (data) { data.decisions = data.decisions.filter(function (p) { return p.id !== a.id; }); });
  } };
  A.prog_group = { run: function (a) { UI.view.group = a.key; UI.saveView(); UI.render(); } };
  A.prog_add = { run: function () { UI.toast && UI.toast("Placeholder: a form for a new entry would open here."); } };
  A.prog_done = { run: function (a) { UI.change("Updated.", function (data) { data.progress.forEach(function (g) { g.entries.forEach(function (e) { if (e.id === a.id) e.done = !e.done; }); }); }); } };
  A.prog_log = { run: function (a) {
    UI.dlg.open("Log progress", '<form data-form="prog_log" class="form"><input type="hidden" name="id" value="' + a.id + '"><label class="field-l" for="lg-amt">Amount</label><input id="lg-amt" type="number" min="0" step="any" name="amount" required autofocus>' + UI.dlg.foot("Log it") + "</form>");
  }, submit: function (f, form) {
    if (!(+f.amount > 0)) { UI.formError(form, "Enter an amount above 0."); return; }
    UI.dlg.close();
    UI.change("Logged " + f.amount + ".", function (data) { data.progress.forEach(function (g) { g.entries.forEach(function (e) { if (e.id === +f.id) { e.value = (e.value || 0) + +f.amount; (e.logs = e.logs || []).unshift({ id: Date.now(), offset: 0, amount: +f.amount }); } }); }); });
  } };
  A.history_filter = { submit: function (f) { UI.view.history = { group: f.group, status: f.status }; UI.saveView(); UI.render(); } };
  A.history_clear = { run: function () { UI.view.history = { group: "", status: "" }; UI.saveView(); UI.render(); } };
  A.set_preview = { change: function (v) { UI.session.set("uikit.preview", v); UI.render(); } };
  A.toggle_slots = { change: function (on) { setSlots(on); } };
  function setSlots(on) { document.documentElement.setAttribute("data-slots", on ? "on" : "off"); UI.store.set("uikit.slots", on ? "on" : "off"); }
  A.autosave = { change: function (v, el) {
    UI.change("Saved.", function (data) { data.window[el.name] = v; }, { quiet: true });
  } };
  A.demo_refuse = { run: function (a, el) { UI.inlineError(el, "Placeholder refusal: the backend's reason, in plain words, appears next to the control that was used."); } };
  A.simulate_offline = { run: function () { UI.setOnline(!UI.online); UI.render(); } };
  A.mic_mute = { run: function () { var m = !UI.store.get("uikit.muted", false); UI.store.set("uikit.muted", m); UI.emit("muted", m); UI.render(); } };

  /* autosaving text areas: 1.2 s after typing stops, and on leaving the box (guide §5.6) */
  var pending = {};
  function autosave(el) {
    if (el.readOnly || el.getAttribute("data-saved") === el.value) return;
    var note = document.querySelector('[data-note-for="' + el.id + '"]'), ok = UI.online;
    if (note) note.textContent = "Saving…";
    UI.saved && UI.saved(ok ? "saving" : "offline");
    setTimeout(function () {
      if (ok) { el.setAttribute("data-saved", el.value); el.defaultValue = el.value; UI.saved && UI.saved("saved"); }
      var n = document.querySelector('[data-note-for="' + el.id + '"]');
      if (n) n.textContent = ok ? "Saved " + new Date().toTimeString().slice(0, 5) : "Not saved: your text is still here.";
    }, 300);
  }
  document.addEventListener("input", function (e) { var el = e.target; if (el.matches && el.matches("textarea[data-autosave]")) { clearTimeout(pending[el.id]); pending[el.id] = setTimeout(function () { autosave(el); }, 1200); } });
  document.addEventListener("focusout", function (e) { var el = e.target; if (el.matches && el.matches("textarea[data-autosave]")) { clearTimeout(pending[el.id]); autosave(el); } });

  /* shortcuts that act on items (guide §5.5) */
  function sel() { return UI.selectedItem(); }
  UI.addKey("A", "Add an item", function () { UI.trigger("item_add"); });
  UI.addKey("D", "Done: the selected or current item", function () { var t = sel(); if (t) UI.trigger("item_done", { id: t.id }); });
  UI.addKey("F", "Failed: the selected or current item", function () { var t = sel(); if (t) UI.trigger("item_failed", { id: t.id }); });
  UI.addKey("S", "Skip: the selected or current item", function () { var t = sel(); if (t) UI.trigger("item_skip", { id: t.id }); });
  UI.addKey("X", "Extend the current item", function () { var t = sel(); if (t && t.running) UI.trigger("item_extend", { id: t.id }); });
  UI.addKey("P", "Run the main automatic action", function () { UI.trigger("main_action"); });
  UI.addKey("U", "Undo the last change", function () { UI.undoLast(); });
  UI.addKey("G", "Show or hide slot labels (kit only)", function () { setSlots(document.documentElement.getAttribute("data-slots") === "off"); });
})();
