/* ==========================================================================
   core.js: the small runtime every page needs. Everything else is optional.
   - UI.esc, UI.store (localStorage / sessionStorage with try/catch), event bus
   - UI.data: an in-memory copy of window.DEMO (stand-in for your backend)
   - UI.change(): apply a change, show Saved, offer Undo (stand-in for a save)
   - action wiring: [data-act] click/change, [data-form] submit, [data-nav] links
   - UI.dlg (one shared <dialog>), UI.overlay (help / search), UI.keys (shortcuts)
   - router: #screen in the URL, layout frame render, focus on the new heading
   Components call each other only through optional hooks (UI.toast && …), so
   any shared/<component>.js file can be deleted without breaking the rest.
   ========================================================================== */
(function () {
  var UI = window.UI = window.UI || {};

  /* ---------- small helpers ---------- */
  UI.esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  function storage(kind) {
    return {
      // Strings are stored as they are (boot.js reads them raw before paint); anything else as JSON.
      get: function (k, d) { var v; try { v = window[kind].getItem(k); } catch (e) { return d; } if (v == null) return d; try { return JSON.parse(v); } catch (e) { return v; } },
      set: function (k, v) { try { window[kind].setItem(k, typeof v === "string" ? v : JSON.stringify(v)); } catch (e) {} }
    };
  }
  UI.store = storage("localStorage");      // remembered choices (theme, layout, notes open, banners)
  UI.session = storage("sessionStorage");  // per-tab view (selected item, filters, preview state)
  var listeners = {};
  UI.on = function (evt, fn) { (listeners[evt] = listeners[evt] || []).push(fn); };
  UI.emit = function (evt, data) { (listeners[evt] || []).forEach(function (fn) { fn(data); }); };

  /* dates and times */
  var DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function iso(d) { return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
  function parse(s) { var p = String(s).split("-"); return new Date(+p[0], +p[1] - 1, +p[2]); }
  UI.date = {
    today: function () { return iso(new Date()); },
    offset: function (n) { var d = new Date(); d.setHours(12, 0, 0, 0); d.setDate(d.getDate() + n); return iso(d); },
    label: function (isoDate, plain) {
      var d = parse(isoDate), t = UI.date.today();
      if (!plain) { if (isoDate === t) return "Today"; if (isoDate === UI.date.offset(1)) return "Tomorrow"; if (isoDate === UI.date.offset(-1)) return "Yesterday"; }
      return DAYS[d.getDay()] + " " + d.getDate() + " " + MONTHS[d.getMonth()];
    },
    long: function (isoDate) { var d = parse(isoDate); return ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][d.getDay()] + " " + d.getDate() + " " + MONTHS[d.getMonth()]; },
    weekday: function (isoDate) { return DAYS[parse(isoDate).getDay()]; },
    dayNum: function (isoDate) { return parse(isoDate).getDate(); },
    toMin: function (hm) { var p = String(hm).split(":"); return +p[0] * 60 + +p[1]; },
    fromMin: function (m) { return String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0"); },
    dur: function (m) { var h = Math.floor(m / 60), r = m % 60; return h ? h + "h" + (r ? " " + r + "m" : "") : r + "m"; }
  };

  /* ---------- data (stand-in for a backend; see UI_GUIDE.md §7) ---------- */
  function build() {
    var D = JSON.parse(JSON.stringify(window.DEMO || {}));
    D.days = D.days || []; D.older = D.older || []; D.decisions = D.decisions || []; D.progress = D.progress || []; D.history = D.history || [];
    D.banners = D.banners || []; D.voice = D.voice || { heard: [], commands: [], phrases: [], log: [], rail: {} };
    D.notes = D.notes || { max: 50, max_text: 200, colors: [], items: [] };
    D.kinds = D.kinds || {}; D.priorities = D.priorities || {}; D.window = D.window || { start: "08:00", end: "18:00" };
    D.now = D.now || new Date().toTimeString().slice(0, 5);
    function norm(t, date) {
      t.date = date; t.duration_text = UI.date.dur(t.duration || 0); t.priority_name = D.priorities[t.priority] || ""; return t;
    }
    D.days.forEach(function (d) { d.date = UI.date.offset(d.offset); d.items = (d.items || []).map(function (t) { return norm(t, d.date); }); d.untimed = (d.untimed || []).map(function (t) { return norm(t, d.date); }); });
    D.older.forEach(function (t) { norm(t, UI.date.offset(t.offset || -1)); });
    D.history.forEach(function (h) { h.date = UI.date.offset(h.offset || 0); });
    D.notes.items.forEach(function (n) { if (n.due) n.due_date = UI.date.offset(n.due.offset) + "T" + n.due.time; });
    return D;
  }
  UI.data = build();
  UI.preview = function () { return UI.session.get("uikit.preview", "normal"); };   // normal | empty | loading | error
  UI.view = Object.assign({ dayOffset: 0, selected: null, group: "a", history: { group: "", status: "" } }, UI.session.get("uikit.view", {}));
  UI.saveView = function () { UI.session.set("uikit.view", UI.view); };
  UI.day = function (offset) {
    if (UI.preview() === "empty") return { date: UI.date.offset(offset), items: [], untimed: [], offset: offset };
    var d = UI.data.days.filter(function (x) { return x.offset === offset; })[0];
    return d || { date: UI.date.offset(offset), items: [], untimed: [], offset: offset };
  };
  UI.allItems = function () {
    var out = []; UI.data.days.forEach(function (d) { out = out.concat(d.items, d.untimed); }); return out.concat(UI.data.older);
  };
  UI.findItem = function (id) { return UI.allItems().filter(function (t) { return t.id === +id; })[0] || null; };
  UI.selectedItem = function () {
    var d = UI.day(UI.view.dayOffset), all = d.items.concat(d.untimed);
    return all.filter(function (t) { return t.id === UI.view.selected; })[0] || all.filter(function (t) { return t.running; })[0] ||
      all.filter(function (t) { return t.status === "pending"; })[0] || null;
  };
  UI.nowAndNext = function () {
    var d = UI.day(0), nowM = UI.date.toMin(UI.data.now);
    var now = d.items.filter(function (t) { return t.running && t.status === "pending"; })[0] || null;
    var next = d.items.filter(function (t) { return t.status === "pending" && !t.running && UI.date.toMin(t.start) >= nowM; });
    return { now: now, next: next, day: d };
  };

  /* ---------- changes, Saved and Undo (stand-in for a backend write) ---------- */
  var undo = [], undoId = 0;
  UI.online = true;
  UI.setOnline = function (on) { if (UI.online === on) return; UI.online = on; document.body.classList.toggle("is-offline", !on); UI.emit("connection", on); };
  // fn changes UI.data; message is the toast text. Returns the undo id, or false if offline.
  UI.change = function (message, fn, o) {
    o = o || {};
    if (!UI.online) { UI.saved && UI.saved("offline"); UI.toast && UI.toast("Not saved: the connection is lost. Your input is still here.", { error: true }); return false; }
    var before = JSON.stringify(UI.data);
    UI.saved && UI.saved("saving");
    fn(UI.data);
    var id = ++undoId; undo.push({ id: id, data: before });
    setTimeout(function () { UI.saved && UI.saved("saved"); }, 300);
    if (!o.quiet) UI.toast && UI.toast(message, { undo: id, long: o.long });
    UI.render();
    return id;
  };
  UI.undoLast = function (id) {
    var hit = id ? undo.filter(function (u) { return u.id === id; })[0] : undo[undo.length - 1];
    if (!hit) { UI.toast && UI.toast("There's nothing to undo."); return; }
    UI.data = JSON.parse(hit.data);
    undo = undo.filter(function (u) { return u.id < hit.id; });
    UI.saved && UI.saved("saved");
    UI.toast && UI.toast("Undone.");
    UI.render();
  };
  UI.hasUndo = function () { return undo.length > 0; };

  /* ---------- HTML builders ---------- */
  UI.btn = function (act, args, label, o) {
    o = o || {};
    return '<button type="button" class="btn' + (o.cls ? " " + o.cls : "") + '" data-act="' + act + '"' +
      (args ? " data-args='" + UI.esc(JSON.stringify(args)) + "'" : "") +
      (o.title ? ' title="' + UI.esc(o.title) + '"' : "") + (o.aria ? ' aria-label="' + UI.esc(o.aria) + '"' : "") +
      (o.disabled ? " disabled" : "") + (o.pressed != null ? ' aria-pressed="' + o.pressed + '"' : "") + ">" +
      (o.icon ? UI.icon(o.icon) : "") + (label ? '<span class="btn-l">' + label + "</span>" : "") +
      (o.kbd ? '<kbd class="kbd">' + o.kbd + "</kbd>" : "") + "</button>";
  };
  UI.navLink = function (screen, label, o) {
    o = o || {};
    return '<a href="#' + screen + '" data-nav="' + screen + '"' + (o.cls ? ' class="' + o.cls + '"' : "") + ">" +
      (o.icon ? UI.icon(o.icon) : "") + "<span>" + label + "</span>" + (o.badge ? '<b class="badge">' + o.badge + "</b>" : "") + "</a>";
  };
  UI.empty = function (text, action) { return '<div class="empty"><p>' + text + "</p>" + (action || "") + "</div>"; };
  UI.state = function (emptyHtml) {   // loading / error preview for a whole screen or pane
    var p = UI.preview();
    if (p === "loading") return '<p class="loading" role="status">Loading…</p>';
    if (p === "error") return UI.empty("Placeholder error: the data couldn't be loaded. Nothing you typed is lost.", UI.btn("preview_normal", null, "Try again"));
    return emptyHtml;
  };

  /* ---------- actions ---------- */
  UI.actions = {
    nav: { run: function (a) { UI.go(a.screen); } },
    select_item: { run: function (a) { UI.view.selected = a.id; UI.saveView(); UI.render(); } },
    preview_normal: { run: function () { UI.session.set("uikit.preview", "normal"); UI.render(); } },
    overlay_close: { run: function () { UI.overlay.close(); } },
    undo: { run: function (a) { UI.undoLast(a && a.id); } }
  };
  function argsOf(el) { try { return JSON.parse(el.getAttribute("data-args") || "{}"); } catch (e) { return {}; } }
  UI.trigger = function (name, args, el) {
    var a = UI.actions[name];
    if (a && a.run) return a.run(args || {}, el);
    if (window.console) console.warn("No action named", name, "(its component may have been removed).");
  };
  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("[data-act]");
    if (!el || el.tagName === "SELECT" || (el.tagName === "INPUT" && el.type !== "button")) return;
    if (el.disabled) return;
    e.preventDefault();
    UI.trigger(el.getAttribute("data-act"), argsOf(el), el);
  });
  document.addEventListener("change", function (e) {
    var el = e.target;
    if (el.matches && el.matches("select[data-act], input[data-act]")) {
      var a = UI.actions[el.getAttribute("data-act")];
      if (a && a.change) a.change(el.type === "checkbox" ? el.checked : el.value, el);
    }
  });
  UI.formArgs = function (form) {
    var a = {};
    new FormData(form).forEach(function (v, k) { if (!(k in a)) a[k] = typeof v === "string" ? v : ""; });
    form.querySelectorAll("input[type=checkbox][name]").forEach(function (c) { a[c.name] = c.checked; });
    return a;
  };
  UI.formError = function (form, msg) {
    var e = form && form.querySelector(".form-err");
    if (e) { e.textContent = msg; e.hidden = !msg; }
  };
  document.addEventListener("submit", function (e) {
    var form = e.target, name = form.getAttribute("data-form");
    if (!name) return;
    e.preventDefault();
    var a = UI.actions[name];
    if (a && a.submit) a.submit(UI.formArgs(form), form);
  });
  /* A refusal next to the control that was used (guide §5.15). */
  UI.inlineError = function (el, msg) {
    if (!el) { UI.toast && UI.toast(msg, { error: true }); return; }
    var form = el.closest("form");
    if (form && form.querySelector(".form-err")) { UI.formError(form, msg); return; }
    var host = el.closest(".actions, .row, .toolbar, .banner, .item, li, section") || el.parentNode;
    host.querySelectorAll(":scope > .inline-err").forEach(function (x) { x.remove(); });
    var p = document.createElement("p");
    p.className = "inline-err"; p.setAttribute("role", "alert"); p.textContent = msg;
    host.appendChild(p);
    setTimeout(function () { p.remove(); }, 15000);
  };

  /* ---------- the shared dialog ---------- */
  var dlg;
  UI.dlg = {
    open: function (title, body, o) {
      o = o || {};
      dlg = dlg || document.getElementById("dlg");
      if (!dlg) return null;
      dlg.className = "dlg" + (o.cls ? " " + o.cls : "");
      dlg.innerHTML = '<div class="dlg-head"><h2 id="dlg-title">' + title + '</h2><button type="button" class="btn quiet" data-close aria-label="Close">' + UI.icon("x") + "</button></div>" + body;
      if (!dlg.open) dlg.showModal();
      var first = dlg.querySelector("[autofocus], textarea, input:not([type=hidden]), select, button[type=submit]");
      if (first) first.focus();
      if (o.onOpen) o.onOpen(dlg);
      return dlg;
    },
    close: function () { if (dlg && dlg.open) dlg.close(); },
    isOpen: function () { return !!(dlg && dlg.open); }
  };
  document.addEventListener("click", function (e) {
    var c = e.target.closest && e.target.closest("[data-close]");
    if (c) { var d = c.closest("dialog"); if (d) d.close(); }
  });
  UI.dlg.foot = function (label, o) {
    o = o || {};
    return '<p class="form-err" role="alert" hidden></p><div class="dlg-foot"><button type="button" class="btn" data-close>' + (o.cancel || "Cancel") + '</button><button type="submit" class="btn ' + (o.danger ? "danger" : "primary") + '">' + label + "</button></div>";
  };

  /* ---------- overlay (help, search) ---------- */
  UI.overlay = {
    open: function (html, label) {
      var ov = document.getElementById("overlay"); if (!ov) return;
      ov.innerHTML = '<div class="ov-card" role="dialog" aria-modal="true" aria-label="' + UI.esc(label) + '">' + html + "</div>";
      ov.hidden = false;
      var f = ov.querySelector("input, button"); if (f) f.focus();
    },
    close: function () { var ov = document.getElementById("overlay"); if (ov && !ov.hidden) { ov.hidden = true; ov.innerHTML = ""; } },
    isOpen: function () { var ov = document.getElementById("overlay"); return !!(ov && !ov.hidden); }
  };
  document.addEventListener("click", function (e) { if (e.target.id === "overlay") UI.overlay.close(); });

  /* ---------- keyboard shortcuts registry (help overlay lists these) ---------- */
  UI.keys = [];
  UI.addKey = function (key, label, run, o) { UI.keys.push(Object.assign({ key: key, label: label, run: run }, o || {})); };
  function typing(t) { return t.closest && t.closest("input, textarea, select, [contenteditable]"); }
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { var q = document.getElementById("qa-input"); if (q) { e.preventDefault(); q.focus(); } return; }
    if (e.key === "Escape") { UI.emit("escape"); UI.overlay.close(); return; }
    var alarmOpen = document.getElementById("alarm-dlg") && document.getElementById("alarm-dlg").open;
    if (e.ctrlKey || e.metaKey || e.altKey || typing(e.target) || UI.dlg.isOpen()) return;
    var k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    var hit = UI.keys.filter(function (s) { return !s.display && (s.key.toLowerCase() === k || s.key === e.key); })[0];
    if (!hit || (alarmOpen && !hit.duringAlarm)) return;
    e.preventDefault();
    hit.run(e);
  });

  /* ---------- router + render ---------- */
  UI.SCREENS = ["home", "list", "progress", "history", "voice", "settings", "later"];
  UI.TITLES = { home: "Home", list: "List", progress: "Progress", history: "History", voice: "Voice", settings: "Settings", later: "Later", now: "Now" };
  UI.screen = function () {
    var L = UI.layout || {}, h = location.hash.slice(1);
    var known = UI.SCREENS.concat(Object.keys(L.extraScreens || {}));
    if (L.mapScreen && L.mapScreen[h]) return L.mapScreen[h];
    if (h && known.indexOf(h) > -1) return h;
    return L.defaultScreen || "home";
  };
  UI.go = function (screen) { if (location.hash !== "#" + screen) location.hash = "#" + screen; else UI.render(); };
  function keepInputs(root) {
    var kept = {}, active = document.activeElement;
    root.querySelectorAll("[data-keep][id]").forEach(function (el) {
      if (el.value !== el.defaultValue || el === active) kept[el.id] = { value: el.value, dirty: el.value !== el.defaultValue, focus: el === active };
    });
    return { kept: kept, activeId: active && root.contains(active) ? active.id : null };
  }
  function restoreInputs(k) {
    Object.keys(k.kept).forEach(function (id) {
      var el = document.getElementById(id), v = k.kept[id];
      if (!el) return;
      if (v.dirty) el.value = v.value;
      if (v.focus) el.focus();
    });
    if (k.activeId && !k.kept[k.activeId]) { var a = document.getElementById(k.activeId); if (a) a.focus({ preventScroll: true }); }
  }
  UI.render = function () {
    var L = UI.layout; if (!L) return;
    var sc = UI.screen(), root = document.getElementById("layout-root");
    document.body.setAttribute("data-screen", sc);
    var fn = (L.screens && L.screens[sc]) || (L.extraScreens && L.extraScreens[sc]) || (sc === "home" ? L.home : UI.screens && UI.screens[sc]);
    var inner = fn ? fn() : UI.empty("This screen isn't built yet.");
    var k = keepInputs(root);
    root.innerHTML = L.frame(sc, inner);
    UI.hydrateIcons(root);
    root.querySelectorAll("a[data-nav]").forEach(function (a) { if (a.getAttribute("data-nav") === sc) a.setAttribute("aria-current", "page"); });
    restoreInputs(k);
    if (L.after) L.after(root, sc);
    document.title = (UI.TITLES[sc] || sc) + " · " + (UI.data.appName || "App") + " · UI kit";
    UI.emit("render", sc);
  };
  window.addEventListener("hashchange", function () {
    UI.render();
    var h = document.querySelector("#layout-root .screen-title, #layout-root h1, #layout-root h2");
    if (h) { h.setAttribute("tabindex", "-1"); h.focus({ preventScroll: false }); }
  });

  /* Start a layout page: layout.js calls UI.start({ id, frame, home, ... }). */
  UI.start = function (layout) {
    UI.layout = layout;
    UI.store.set("uikit.layout", String(layout.id));   // the last layout opened is the remembered one
    document.querySelectorAll("[data-app-name]").forEach(function (el) { el.textContent = UI.data.appName || "App"; });
    UI.hydrateIcons();
    UI.emit("start");
    UI.render();
  };
})();
