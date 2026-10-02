/* Layout 3: Board. Today is a board of cards (No time, Planned, Now, Done,
   Missed). Cards really drag: Done marks done, Missed asks for the reason
   first, and dropping on a planned card moves it right before that card.
   Every other page slides in as a drawer over the board. */
(function () {
  var T = window.T, R = T.r, I = function (n) { return T.icon(n); };

  function navBar(st) {
    var p = st.proposals.length;
    return '<nav class="l3-nav" aria-label="Open a page">' + R.nav("today", "Board", { icon: "columns" }) + R.nav("reschedule", "Reschedule", { icon: "reschedule", badge: p || "" }) +
      R.nav("day", "Goals", { icon: "target" }) + R.nav("history", "Missed log", { icon: "history" }) + R.nav("voice", "Voice", { icon: "wave" }) +
      R.nav("settings", "Settings", { icon: "settings" }) + R.nav("focus", "Focus <small>2.0</small>", { icon: "timer", cls: "later" }) + R.nav("layouts", "Layouts", { icon: "layers" }) + "</nav>";
  }

  function card(t) {
    var drag = t.status === "pending" && t.placement !== "fixed";
    return '<li><article class="card k-' + t.placement + " s-" + t.status + (t.running ? " is-now" : "") + (T.view.selected === t.id ? " is-sel" : "") + '" data-card="' + t.id + '" draggable="' + (t.status === "pending") + '">' +
      '<div class="c-top"><span class="c-time">' + (t.start ? t.start + "<small>–" + t.end + "</small>" : "no time") + '</span><span class="c-dur">' + t.duration_text + "</span>" + R.prio(t) +
      (drag ? '<span class="handle" title="Drag to another column, or onto a planned card to put it right before it">' + I("grip") + "</span>" : "") + "</div>" +
      '<h3 class="c-title">' + R.esc(t.title) + "</h3>" + '<div class="task-meta">' + R.kindBadge(t) + R.goalChip(t) + "</div>" +
      (t.running ? '<div class="c-prog"><span style="width:' + Math.round((t.elapsed || 0) * 100) + '%"></span></div><p class="c-left">' + t.minutes_left + " min left</p>" : "") +
      R.why(t) + R.taskActions(t) + "</article></li>";
  }

  function board(st) {
    var d = st.day, all = d.tasks;
    var cols = [
      ["untimed", "No time / didn’t fit", "Stays on the day without a time; Plan my day places it.", d.untimed.filter(function (t) { return t.status === "pending"; })],
      ["planned", "Planned", "In time order. Drag a card onto another to put it right before it.", all.filter(function (t) { return t.status === "pending" && !t.running; })],
      ["now", "Now", "", all.filter(function (t) { return t.running; })],
      ["done", "Done", "Drop a card here to mark it done.", all.concat(d.untimed).filter(function (t) { return t.status === "done"; })],
      ["missed", "Missed", "Drop here to mark failed; a reason is asked first.", all.concat(d.untimed).filter(function (t) { return t.status === "failed" || t.status === "skipped"; })]
    ];
    var empties = { untimed: "Nothing without a time.", planned: d.is_past ? "Nothing was planned." : "Nothing planned. Add a task, then Plan my day.", now: "Nothing running right now.", done: "Nothing done yet.", missed: "Nothing missed." };
    return '<div class="l3-board" aria-label="Board for ' + R.esc(d.label) + '">' + cols.map(function (c) {
      return '<section class="col col-' + c[0] + '" data-col="' + c[0] + '" aria-labelledby="col-' + c[0] + '"><header class="col-h"><h2 id="col-' + c[0] + '">' + c[1] + '</h2><span class="col-n">' + c[3].length + "</span></header>" +
        (c[2] ? '<p class="col-note">' + c[2] + "</p>" : "") + (c[3].length ? '<ol class="cards">' + c[3].map(card).join("") + "</ol>" : '<p class="col-empty">' + empties[c[0]] + "</p>") +
        (c[0] === "planned" ? R.btn("add_task", { date: d.date }, "Add a card", { icon: "plus", cls: "addcard" }) : "") + "</section>";
    }).join("") + "</div>";
  }

  function strip(st) {
    var d = st.day, w0 = R.toMin(st.settings.day_start), w1 = R.toMin(st.settings.day_end), span = Math.max(60, w1 - w0);
    var segs = d.tasks.map(function (t) {
      var a = Math.max(0, R.toMin(t.start) - w0), b = Math.min(span, R.toMin(t.start) + t.duration - w0);
      return b > a ? '<span class="sg k-' + t.placement + " s-" + t.status + '" style="left:' + (a / span * 100) + "%;width:" + ((b - a) / span * 100) + '%" title="' + R.esc(t.start + " " + t.title) + '"></span>' : "";
    }).join("");
    var nowM = R.toMin(st.now.slice(11, 16)) - w0;
    return '<div class="l3-strip"><div class="strip-bar" aria-hidden="true">' + segs + (d.is_today && nowM >= 0 && nowM <= span ? '<span class="sg-now" style="left:' + (nowM / span * 100) + '%"></span>' : "") + "</div>" +
      '<p class="strip-sum">' + R.dur(d.free_minutes) + " free · " + d.counts.done + " done · " + d.untimed.length + " without a time</p></div>";
  }

  function today(st) {
    var d = st.day;
    var empty = !d.tasks.length && !d.untimed.length;
    return '<div class="l3-day"><div class="l3-title"><h2 class="screen-title">' + R.esc(R.dayLabel(d.date)) + " · " + R.esc(d.short) + '</h2><span class="muted">Window ' + st.settings.day_start + "–" + st.settings.day_end + "</span></div>" +
      R.dayBar(st) + strip(st) + "</div>" +
      (empty ? '<div class="l3-pad">' + R.empty("An empty board. Add a card for each thing you want to do today; then Plan my day lays them out in time.", R.btn("add_task", { date: d.date }, "Add your first card", { icon: "plus", cls: "primary", kbd: "A" })) + "</div>" : board(st)) +
      (st.proposals.length || st.overdue.length ? '<div class="l3-extra">' + st.proposals.map(R.proposalCard).join("") + R.overdueList(st) + "</div>" : "");
  }

  /* drag and drop: real actions through the same commands */
  var dragId = null;
  function wire(root) {
    root.querySelectorAll("[data-card][draggable=true]").forEach(function (c) {
      c.addEventListener("dragstart", function (e) { dragId = +c.getAttribute("data-card"); c.classList.add("is-drag"); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", String(dragId)); });
      c.addEventListener("dragend", function () { c.classList.remove("is-drag"); root.querySelectorAll(".is-over").forEach(function (x) { x.classList.remove("is-over"); }); });
    });
    root.querySelectorAll("[data-col]").forEach(function (col) {
      col.addEventListener("dragover", function (e) { if (dragId == null) return; e.preventDefault(); col.classList.add("is-over"); });
      col.addEventListener("dragleave", function () { col.classList.remove("is-over"); });
      col.addEventListener("drop", function (e) {
        if (dragId == null) return;
        e.preventDefault(); col.classList.remove("is-over");
        var id = dragId; dragId = null;
        var to = col.getAttribute("data-col"), target = e.target.closest("[data-card]"), t = T.findTask(id);
        if (!t) return;
        if (to === "done") return T.trigger("mark_done", { id: id });
        if (to === "missed") return T.trigger("mark_failed", { id: id });
        if (to === "now") return T.toast("A task is “now” while its time runs. Move it to a time instead.");
        if (to === "planned" && target && +target.getAttribute("data-card") !== id) {
          return T.run("move_task", { id: id, mode: "before", other_id: +target.getAttribute("data-card") }, target);
        }
        if (to === "planned" && !t.start) return T.trigger("move_task", { id: id });
        if (to === "untimed" && t.start) return T.run("move_task", { id: id, mode: "time", start: "" }, col);
      });
    });
  }

  document.addEventListener("keydown", function (e) {  // Esc closes a drawer
    if (e.key === "Escape" && T.state && T.state.ui.layout === 3 && T.currentScreen() !== "today" && !T.dlg.isOpen() && document.getElementById("overlay").hidden) location.hash = "#today";
  });

  T.layouts[3] = {
    id: 3, defaultScreen: "today", today: today,
    frame: function (st, screen, inner) {
      var drawer = screen !== "today";
      return '<div class="l3' + (drawer ? " drawer-open" : "") + '">' + navBar(st) +
        '<div class="l3-main"' + (drawer ? " inert" : "") + ">" + (drawer ? today(st) : inner) + "</div>" +
        (drawer ? '<a href="#today" class="scrim" aria-label="Close and go back to the board" data-nav="today"></a><section class="drawer" aria-label="' + R.esc(T.screenTitle[screen] || screen) + '">' +
          '<div class="dr-h"><a class="close" href="#today" data-nav="today" aria-label="Back to the board">' + I("x") + '</a></div><div class="dr-body">' + inner + "</div></section>" : "") + "</div>";
    },
    after: function (root) { wire(root); }
  };
})();
