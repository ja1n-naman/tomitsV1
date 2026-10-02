/* API client, live updates (server push) and the "Saved" indicator.
   One data layer for all six layouts: T.state is always what the database
   holds; nothing is kept or changed only in the browser. */
(function () {
  var T = window.T;
  var listeners = {};
  T.on = function (evt, fn) { (listeners[evt] = listeners[evt] || []).push(fn); };
  T.emit = function (evt, data) { (listeners[evt] || []).forEach(function (fn) { fn(data); }); };

  /* ---------- what the user is looking at (kept for this browser tab) ---------- */
  var saved = {};
  try { saved = JSON.parse(sessionStorage.getItem("tomits-view") || "{}"); } catch (e) { saved = {}; }
  T.view = Object.assign({ day: null, periods: { day: null, week: null, month: null },
                           history: { goal: "", from: "", to: "", status: "" }, selected: null }, saved);
  T.saveView = function () {
    try { sessionStorage.setItem("tomits-view", JSON.stringify(T.view)); } catch (e) {}
  };

  /* ---------- connection + saved indicator ---------- */
  T.online = true;
  var savedEl, savedText, savedTimer;
  T.savedState = function (state, text) {
    savedEl = savedEl || document.getElementById("saved");
    savedText = savedText || document.getElementById("saved-text");
    if (!savedEl) return;
    savedEl.setAttribute("data-state", state);
    savedText.textContent = text || { saving: "Saving…", saved: "Saved", error: "Not saved", offline: "Offline" }[state];
    clearTimeout(savedTimer);
    if (state === "saved") savedTimer = setTimeout(function () { savedEl.setAttribute("data-state", "idle"); }, 4000);
  };
  T.setOnline = function (on) {
    if (T.online === on) return;
    T.online = on;
    document.body.classList.toggle("is-offline", !on);
    if (!on) T.savedState("offline");
    T.emit("connection", on);
  };

  function Problem(message, opts) { this.message = message; Object.assign(this, opts || {}); }
  T.Problem = Problem;

  async function request(method, path, body, raw) {
    var opts = { method: method, headers: { "X-Tomits": "1" }, cache: "no-store" };
    if (body !== undefined) {
      if (raw) { opts.body = body; opts.headers["Content-Type"] = "application/octet-stream"; }
      else { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
    }
    var res;
    try {
      res = await fetch(path, opts);
    } catch (e) {
      T.setOnline(false);
      throw new Problem("Can't reach tomits. Is its window still open? Your input is still here; try again once it's running.", { offline: true });
    }
    T.setOnline(true);
    var data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok || !data || data.ok === false) {
      throw new Problem((data && data.error) || ("The server answered " + res.status + "."), { status: res.status, refused: res.status === 422 });
    }
    return data;
  }
  T.api = {
    get: function (path) { return request("GET", path); },
    post: function (path, body) { return request("POST", path, body); },
    postRaw: function (path, bytes) { return request("POST", path, bytes, true); },
    /* Every change goes through here: one registry command, committed at once. */
    command: async function (cmd, args) {
      T.savedState("saving");
      try {
        var out = await request("POST", "/api/command", { cmd: cmd, args: args || {} });
        if (!out.needs_confirm) T.savedState("saved", out.saved === false ? "Done" : "Saved");
        else T.savedState("idle");
        return out;
      } catch (p) {
        T.savedState(p.offline ? "offline" : p.refused ? "idle" : "error", p.refused ? "Not changed" : undefined);
        throw p;
      }
    }
  };

  /* ---------- state ---------- */
  function query() {
    var q = new URLSearchParams();
    if (T.view.day) q.set("day", T.view.day);
    ["day", "week", "month"].forEach(function (k) { if (T.view.periods[k]) q.set(k, T.view.periods[k]); });
    ["goal", "from", "to", "status"].forEach(function (k) { if (T.view.history[k]) q.set("h_" + k, T.view.history[k]); });
    return q.toString();
  }
  var inflight = null, again = false, timer = null;
  T.refresh = function (now) {
    clearTimeout(timer);
    timer = setTimeout(load, now ? 0 : 120);
  };
  async function load() {
    if (inflight) { again = true; return; }
    inflight = T.api.get("/api/state?" + query());
    try {
      T.state = await inflight;
      T.emit("state", T.state);
    } catch (p) {
      T.emit("load-error", p);
    } finally {
      inflight = null;
      if (again) { again = false; load(); }
    }
  }

  /* ---------- server push: every open view updates without a refresh ---------- */
  T.connect = function () {
    var es;
    function open() {
      es = new EventSource("/api/events");
      es.addEventListener("hello", function () { T.setOnline(true); T.refresh(true); });
      es.addEventListener("changed", function () { T.refresh(); });
      es.addEventListener("reminder", function () { T.refresh(); });
      es.addEventListener("note", function (e) { T.refresh(true); try { T.emit("note-event", JSON.parse(e.data)); } catch (x) {} });
      es.addEventListener("alarm", function (e) { T.refresh(true); try { T.emit("alarm-event", JSON.parse(e.data)); } catch (x) {} });
      es.onerror = function () {
        T.setOnline(false);
        if (es.readyState === EventSource.CLOSED) { setTimeout(open, 2000); }
      };
    }
    open();
  };
})();
