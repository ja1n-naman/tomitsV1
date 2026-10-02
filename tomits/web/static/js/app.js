/* Boot, screens, banners, alarm panel, overlays and first-run setup. */
(function () {
  var T = window.T, R = T.r, I = function (n) { return T.icon(n); };
  var esc = R.esc;
  T.layouts = T.layouts || {};
  T.SCREENS = ["today", "reschedule", "day", "week", "month", "history", "voice", "settings", "focus", "layouts"];
  var DEFAULTS = {
    reschedule: function (st) { return '<h2 class="screen-title">Reschedule</h2>' + R.reschedulePage(st); },
    day: function (st) { return R.periodPage("day", st); },
    week: function (st) { return R.periodPage("week", st); },
    month: function (st) { return R.periodPage("month", st); },
    history: R.historyPage, voice: R.voicePage, settings: R.settingsPage, focus: R.focusPage, layouts: R.layoutsPage
  };
  T.screenTitle = { today: "Today", reschedule: "Reschedule", day: "Day", week: "Week", month: "Month", history: "Missed & skipped",
    voice: "Voice", settings: "Settings", focus: "Focus (2.0)", layouts: "Layouts", now: "Now" };

  function layout() { return T.layouts[(T.state && T.state.ui.layout) || 1] || T.layouts[1]; }
  function screen() {
    var L = layout(), h = location.hash.slice(1);
    var known = T.SCREENS.concat(Object.keys(L.extraScreens || {}));
    if (h && known.indexOf(h) > -1) return h;
    if (h && L.mapScreen && L.mapScreen[h]) return L.mapScreen[h];
    return L.defaultScreen || "today";
  }
  T.currentScreen = screen;

  /* where a voice command or a search result wants to go */
  T.applyView = function (v) {
    if (v.day !== undefined) T.view.day = v.day && v.day !== (T.state && T.state.today) ? v.day : null;
    if (v.start && /^(day|week|month)$/.test(v.screen)) T.view.periods[v.screen] = v.start;
    if (v.screen === "history" && (v.from || v.to)) T.view.history = Object.assign({}, T.view.history, { from: v.from || "", to: v.to || "" });
    if (v.task) T.view.selected = v.task;
    T.saveView();
    if (v.screen) { if (location.hash !== "#" + v.screen) location.hash = "#" + v.screen; }
    T.refresh(true);
    if (v.mic_test) setTimeout(function () { T.voice.micTest(); }, 300);
  };

  /* ---------- theme + layout (saved as settings on the server) ---------- */
  function applyLook(st) {
    var theme = st.ui.theme;
    var dark = theme === "dark" || (theme === "system" && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    var css = document.getElementById("layout-css"), href = "/static/layouts/l" + st.ui.layout + ".css";
    if (css.getAttribute("href") !== href) css.setAttribute("href", href);
    document.body.setAttribute("data-layout", st.ui.layout);
    try { localStorage.setItem("tomits-theme", theme); localStorage.setItem("tomits-layout", String(st.ui.layout)); } catch (e) {}
  }
  if (window.matchMedia) matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () { if (T.state) applyLook(T.state); });

  /* ---------- render, keeping unsaved input ---------- */
  function keepInputs(root) {
    var kept = {}, active = document.activeElement;
    root.querySelectorAll("[data-keep][id]").forEach(function (el) {
      if (el.value !== el.defaultValue || el === active) kept[el.id] = { value: el.value, dirty: el.value !== el.defaultValue, focus: el === active, s: el.selectionStart, e: el.selectionEnd };
    });
    return { kept: kept, activeId: active && root.contains(active) ? active.id : null };
  }
  function restoreInputs(root, k) {
    Object.keys(k.kept).forEach(function (id) {
      var el = document.getElementById(id), v = k.kept[id];
      if (!el) return;
      if (v.dirty) el.value = v.value;
      if (v.focus) { el.focus(); try { el.setSelectionRange(v.s, v.e); } catch (x) {} }
    });
    if (k.activeId && !k.kept[k.activeId]) { var a = document.getElementById(k.activeId); if (a) a.focus({ preventScroll: true }); }
  }
  T.render = function () {
    var st = T.state; if (!st) return;
    applyLook(st);
    var L = layout(), sc = screen();
    document.body.setAttribute("data-screen", sc);
    var fn = (L.screens && L.screens[sc]) || (L.extraScreens && L.extraScreens[sc]) || (sc === "today" ? L.today : DEFAULTS[sc]);
    var root = document.getElementById("layout-root");
    var k = keepInputs(root);
    root.innerHTML = L.frame(st, sc, fn(st, L));
    T.hydrateIcons(root);
    root.querySelectorAll("textarea[data-autosave]").forEach(function (t) { t.setAttribute("data-saved", t.value); });
    root.querySelectorAll('a[data-nav]').forEach(function (a) { if (a.getAttribute("data-nav") === sc) a.setAttribute("aria-current", "page"); });
    restoreInputs(root, k);
    if (L.after) L.after(root, st, sc);
    if (sc === "voice" || sc === "settings") T.voice.listDevices();
    document.title = (T.screenTitle[sc] || "tomits") + " · tomits";
    banners(st, sc);
    T.notes.render(st);
    alarmPanel(st);
    if (st.setup.needed && !T.setupShown) { T.setupShown = true; T.setup.open(0); }
    if (T.pendingProposal) {
      var p = st.proposals.filter(function (x) { return x.id === T.pendingProposal; })[0];
      T.pendingProposal = null;
      if (p && !T.dlg.isOpen()) T.dlg.open("Reschedule proposal", R.proposalCard(p), { cls: "wide" });
    }
  };

  /* ---------- banners ---------- */
  function banners(st, sc) {
    var out = [];
    if (!T.online) out.push('<div class="banner bad" role="alert">' + I("alert") + "<span><b>Can't reach tomits.</b> Changes aren't being saved right now. Anything you typed stays on screen. Is the tomits window still open? Start it again with start-tomits.bat.</span>" + R.btn("retry", null, "Try again") + "</div>");
    if (T.alarmTone.blocked) out.push('<div class="banner warn" role="alert">' + I("volume") + "<span>The browser is blocking sound, so alarms can't ring yet. Click Enable sound once.</span>" + R.btn("enable_sound", null, "Enable sound", { cls: "primary" }) + "</div>");
    st.alarms.errors.forEach(function (e) { out.push('<div class="banner warn">' + I("alert") + "<span>" + esc(e) + "</span></div>"); });
    if (st.alarms.missed.length && !T.hideMissed) {
      out.push('<div class="banner warn">' + I("bell") + "<span><b>Missed while tomits wasn't running:</b> " + st.alarms.missed.map(function (m) { return esc(m.message); }).join(" · ") + "</span>" + R.btn("dismiss_missed", null, "Hide", { cls: "quiet" }) + "</div>");
    }
    out.push(R.checkins(st));
    if (st.reminders.length) {
      out.push('<div class="banner remind" role="status">' + I("alert") + '<div class="remind-body"><b>Fill in your plan.</b> Each period needs a goal and a process. This banner stays until they’re filled in.<ul>' +
        st.reminders.map(function (r) {
          return "<li>" + esc(r.message) + R.btn("open_fill_in", { kind: r.kind, start: r.start }, "Fill in", { cls: "tiny primary" }) +
            R.btn("dismiss_reminder", { kind: r.kind, start: r.start, part: r.part }, "Dismiss", { cls: "tiny quiet", aria: "Dismiss: " + r.message }) + "</li>";
        }).join("") + "</ul></div></div>");
    }
    if (st.update_waiting) out.push('<div class="banner warn" role="status">' + I("alert") + "<span><b>tomits was updated while it was running.</b> Close the tomits window and start it again (start-tomits.bat) to use the new version. Until then this page stays on the version that's running, so every button keeps working.</span></div>");
    out = out.concat(T.notes.banners(st));
    if (st.proposals.length && sc !== "reschedule") out.push('<div class="banner info">' + I("reschedule") + "<span>" + st.proposals.length + " reschedule proposal" + (st.proposals.length > 1 ? "s are" : " is") + " waiting. Nothing moves until you accept.</span>" + R.btn("nav_reschedule", null, "Review", { cls: "primary" }) + "</div>");
    var el = document.getElementById("banners");
    el.innerHTML = out.join("");
    T.hydrateIcons(el);
  }
  T.ACTIONS.retry = { ui: "reconnect", run: function () { T.refresh(true); } };

  /* ---------- alarm panel: rings in the tab, notifies when the tab is hidden ---------- */
  var notified = {};
  function alarmPanel(st) {
    var d = document.getElementById("alarm-dlg"), ringing = st.alarms.ringing;
    if (!ringing.length) { if (d.open) d.close(); T.alarmTone.stop(); return; }
    var a = ringing[0], key = a.kind + ":" + a.task_id + ":" + a.snoozes;
    var notify = notified[key] || T.notifyAlarm(a);
    notified[key] = notify;
    T.alarmTone.start();
    var notes = [];
    if (T.alarmTone.blocked) notes.push("Sound is blocked by the browser. " + R.btn("enable_sound", null, "Play sound", { cls: "tiny" }));
    if (notify === "denied") notes.push("Desktop notifications are blocked, so this only shows in the tab.");
    if (notify === "default") notes.push(R.btn("enable_notifications", null, "Also notify me when this tab is in the background", { cls: "tiny" }));
    d.innerHTML = '<div class="alarm-top"><span class="alarm-bell">' + I("bell") + '</span><span class="eyebrow">' + esc(a.title_line.replace("tomits: ", "")) + "</span></div>" +
      '<h2 id="alarm-title">' + esc(a.title) + '</h2><p class="alarm-msg">' + esc(a.message) + "</p>" +
      '<p class="muted small">Rings until you choose (stops by itself after 2 minutes). Voice: “dismiss” or “snooze”.' + (ringing.length > 1 ? " " + (ringing.length - 1) + " more ringing." : "") + "</p>" +
      (notes.length ? '<p class="small warn">' + notes.join(" ") + "</p>" : "") +
      '<div class="dlg-foot">' + R.btn("alarm_snooze", { kind: a.kind, task_id: a.task_id }, "Snooze " + st.alarms.snooze_minutes + " min", { icon: "clock" }) +
      R.btn("alarm_dismiss", { kind: a.kind, task_id: a.task_id }, "Dismiss", { cls: "primary", icon: "check" }) + "</div>";
    T.hydrateIcons(d);
    if (!d.open) { d.showModal(); var b = d.querySelector(".primary"); if (b) b.focus(); }
  }
  document.getElementById("alarm-dlg").addEventListener("cancel", function (e) { e.preventDefault(); });  // choose dismiss or snooze
  T.on("sound-blocked", function () { if (T.state) banners(T.state, screen()); });
  T.on("sound-unblocked", function () { if (T.state) banners(T.state, screen()); });
  T.on("connection", function () { if (T.state) banners(T.state, screen()); });

  /* ---------- overlays: help, search ---------- */
  var ov = document.getElementById("overlay");
  T.overlay = {
    open: function (html, label) {
      ov.innerHTML = '<div class="ov-card" role="dialog" aria-modal="true" aria-label="' + esc(label) + '">' + html + "</div>";
      ov.hidden = false; T.hydrateIcons(ov);
      var f = ov.querySelector("input, button"); if (f) f.focus();
    },
    close: function () { if (!ov.hidden) { ov.hidden = true; ov.innerHTML = ""; } },
    help: function () {
      T.overlay.open('<div class="dlg-head"><h2>Keyboard shortcuts</h2>' + R.btn("overlay_close", null, "", { icon: "x", aria: "Close", cls: "quiet" }) + "</div>" +
        '<dl class="keys">' + T.SHORTCUTS.map(function (s) { return "<div><dt><kbd>" + s[0] + "</kbd></dt><dd>" + esc(s[1]) + "</dd></div>"; }).join("") + "</dl>" +
        '<p class="small muted">Shortcuts work when you’re not typing in a box. “Selected” is the last task you clicked; otherwise the one running now, or the next one.</p>' +
        '<p class="small">Anything you can click, you can also type in the box at the top or say after pressing V. ' + R.btn("nav_voice", null, "See what you can say") + "</p>", "Keyboard shortcuts");
    },
    search: function () {
      T.overlay.open('<div class="dlg-head"><h2>Search</h2>' + R.btn("overlay_close", null, "", { icon: "x", aria: "Close", cls: "quiet" }) + "</div>" +
        '<label class="sr" for="search-q">Search</label><input id="search-q" class="search-q" placeholder="Search tasks, goals and failure reasons" autocomplete="off"><div id="search-res" class="search-res"></div>', "Search");
      var q = document.getElementById("search-q");
      q.addEventListener("input", function () { searchResults(q.value); });
      searchResults("");
    }
  };
  ov.addEventListener("click", function (e) { if (e.target === ov) T.overlay.close(); });
  function searchResults(q) {
    var st = T.state, out = [], t = q.trim().toLowerCase();
    var res = document.getElementById("search-res"); if (!res) return;
    if (!t) { res.innerHTML = '<p class="muted small">Type to search this week’s tasks, open goals and the failed / skipped history.</p>'; return; }
    var seen = {};
    st.week.days.concat([st.day]).forEach(function (d) { d.tasks.concat(d.untimed).forEach(function (x) {
      if (!seen[x.id] && x.title.toLowerCase().indexOf(t) > -1) { seen[x.id] = 1; out.push(R.btn("search_go", { screen: "today", day: x.date, task: x.id }, esc(x.title) + ' <small>' + R.dayLabel(x.date) + (x.start ? " " + x.start : "") + " · " + x.status + "</small>", { cls: "sr-item" })); }
    }); });
    st.open_goals.forEach(function (g) { if (g.title.toLowerCase().indexOf(t) > -1) out.push(R.btn("search_go", { screen: g.kind, start: g.start }, esc(g.title) + " <small>" + g.kind + " goal · " + esc(g.text) + "</small>", { cls: "sr-item" })); });
    st.history.rows.forEach(function (h) { if ((h.title + " " + h.reason).toLowerCase().indexOf(t) > -1) out.push(R.btn("search_go", { screen: "history" }, esc(h.title) + " <small>" + h.status + ": " + esc(h.reason) + "</small>", { cls: "sr-item" })); });
    res.innerHTML = out.length ? out.join("") : '<p class="muted small">Nothing found.</p>';
  }

  /* ---------- first-run setup ---------- */
  T.setup = {
    open: function (step) {
      var st = T.state, steps = ["Your day", "First goal and process", "Sound and notifications", "Microphone"];
      var head = '<ol class="steps">' + steps.map(function (s, i) { return '<li class="' + (i === step ? "on" : i < step ? "done" : "") + '">' + (i + 1) + ". " + s + "</li>"; }).join("") + "</ol>";
      var body = "";
      if (step === 0) {
        body = "<p>tomits plans your day around the times you choose, keeps goals for each day, week and month, and saves every change as you make it. Everything stays on this computer.</p>" +
          '<form data-form="settings" data-then="setup_next_1" class="form"><p class="field-l">When does your day usually run? Plan my day only places tasks in this window.</p><div class="cols"><div><label class="field-l" for="su-s">Starts</label><input id="su-s" type="time" name="day_start" value="' + st.settings.day_start + '" required></div>' +
          '<div><label class="field-l" for="su-e">Ends</label><input id="su-e" type="time" name="day_end" value="' + st.settings.day_end + '" required></div></div><p class="form-err" role="alert" hidden></p>' +
          '<div class="dlg-foot">' + R.btn("setup_next", { step: 1 }, "Skip") + '<button type="submit" class="btn primary">Save and continue</button></div></form>';
      } else if (step === 1) {
        body = "<p>Each day, week and month needs a goal and a process (how you’ll get there). Start with today’s. You can skip this; a banner will stay until they’re filled in.</p>" +
          '<form data-form="setup_goal" class="form"><label class="field-l" for="su-g">Today’s goal</label><input id="su-g" name="title" required maxlength="200">' +
          '<div class="cols"><div><label class="field-l" for="su-t">Target (optional)</label><input id="su-t" type="number" step="any" min="0" name="target"></div><div><label class="field-l" for="su-u">Unit</label><input id="su-u" name="unit" maxlength="40"></div></div>' +
          '<label class="field-l" for="su-p">Today’s process</label><textarea id="su-p" name="process" rows="2" required maxlength="1000"></textarea><p class="form-err" role="alert" hidden></p>' +
          '<div class="dlg-foot">' + R.btn("setup_next", { step: 2 }, "Skip for now") + '<button type="submit" class="btn primary">Save and continue</button></div></form>';
      } else if (step === 2) {
        body = "<p>Browsers stay silent until you allow sound once. Alarms ring in this tab; with notifications on they also pop up when the tab is in the background.</p>" +
          '<div class="row">' + R.btn("enable_sound", null, "Enable and test sound", { icon: "volume", cls: "primary" }) + R.btn("enable_notifications", null, "Allow notifications", { icon: "bell" }) + "</div>" +
          '<p class="small" data-permission-note></p><div class="dlg-foot">' + R.btn("setup_next", { step: 3 }, "Continue", { cls: "primary" }) + "</div>";
      } else {
        body = "<p>Voice is optional; typing in the box at the top does the same. Test the mic: speak a short sentence when it starts listening.</p>" +
          '<div class="meter wide" data-level aria-hidden="true"><span></span><i></i></div><p class="small" data-mictest-result></p>' +
          '<div class="row">' + R.btn("run_mic_test", null, "Start mic test", { icon: "play" }) + "</div>" + (st.voice.stt.available ? "" : '<p class="small warn">' + esc(st.voice.stt.reason || "") + "</p>") +
          '<div class="dlg-foot">' + R.btn("finish_setup", null, "Finish", { cls: "primary", icon: "check" }) + "</div>";
      }
      T.dlg.open("Welcome to tomits", head + body + '<p class="small muted setup-skip">' + R.btn("finish_setup", null, "Skip the whole setup", { cls: "quiet tiny" }) + "</p>", { cls: "setup" });
    }
  };
  T.after.setup_next_1 = function () { T.setup.open(1); };
  T.ACTIONS.setup_goal = { ui: "save today's goal and process (two registry commands), then the next setup step", submit: function (a, form) {
    T.api.command("new_goal", { kind: "day", start: T.state.today, title: a.title, target: a.target, unit: a.unit })
      .then(function () { return T.api.command("set_process", { kind: "day", start: T.state.today, text: a.process }); })
      .then(function () { T.toast("Today’s goal and process are saved."); T.refresh(true); T.setup.open(2); })
      .catch(function (p) { T.formError(form, p.message); });
  } };

  /* ---------- start ---------- */
  window.addEventListener("hashchange", function () {
    T.render();
    var h = document.querySelector("#layout-root .screen-title, #layout-root h1, #layout-root h2");
    if (h) { h.setAttribute("tabindex", "-1"); h.focus({ preventScroll: false }); }
  });
  T.on("state", function () { T.render(); });
  T.on("load-error", function (p) {
    if (!T.state) document.getElementById("layout-root").innerHTML = '<div class="empty"><p>' + esc(p.message) + "</p>" + R.btn("retry", null, "Try again") + "</div>";
  });
  T.hydrateIcons();
  T.connect();
  T.refresh(true);
  setInterval(function () { if (T.state) T.refresh(); }, 60000);  // the clock moves: "now" lines and running tasks
})();
