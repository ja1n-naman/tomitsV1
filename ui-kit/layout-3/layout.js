/* Layout 3: Board (UI_GUIDE.md §4.3).
   Slots: nav, board-head, toolbar, summary, columns, extra; other screens: drawer.
   Cards really drag: every drop runs the same action as a button. */
(function () {
  var UI = window.UI, R = UI.r, D = UI.date, esc = UI.esc, I = function (n) { return UI.icon(n); };

  function navBar() {
    var n = R.decisions().length;
    return '<nav class="l3-nav" aria-label="Open a page" data-slot="nav">' + UI.navLink("home", "Board", { icon: "columns" }) + UI.navLink("list", "List", { icon: "list", badge: n || "" }) +
      UI.navLink("progress", "Progress", { icon: "target" }) + UI.navLink("history", "History", { icon: "history" }) + UI.navLink("voice", "Voice", { icon: "wave" }) +
      UI.navLink("settings", "Settings", { icon: "settings" }) + UI.navLink("later", "Later <small>soon</small>", { icon: "timer" }) +
      '<a href="../index.html" data-act="open_layouts">' + I("layers") + "<span>Layouts</span></a></nav>";
  }
  function card(t) {
    var drag = t.status === "pending" && t.kind !== "fixed";
    return '<li><article class="card k-' + t.kind + " s-" + t.status + (t.running && t.status === "pending" ? " is-now" : "") + (UI.view.selected === t.id ? " is-sel" : "") + '" data-card="' + t.id + '" draggable="' + (t.status === "pending") + '">' +
      '<div class="c-top"><span class="c-time">' + (t.start ? t.start + "<small>–" + t.end + "</small>" : "no time") + '</span><span class="c-dur">' + t.duration_text + "</span>" + R.prio(t) +
      (drag ? '<span class="handle" title="Drag to another column">' + I("grip") + "</span>" : "") + "</div>" +
      '<h3 class="c-title">' + esc(t.title) + '</h3><div class="item-meta">' + R.kindBadge(t) + R.linkChip(t) + "</div>" +
      (t.running && t.status === "pending" ? '<div class="c-prog"><span style="width:' + Math.round((t.elapsed || 0) * 100) + '%"></span></div><p class="c-left">' + t.minutes_left + " min left</p>" : "") +
      R.why(t) + R.itemActions(t) + "</article></li>";
  }
  function board(d) {
    var all = d.items, both = d.items.concat(d.untimed);
    var cols = [
      ["unscheduled", "Unscheduled", "Stays on the day without a time.", d.untimed.filter(function (t) { return t.status === "pending"; })],
      ["planned", "Planned", "In time order.", all.filter(function (t) { return t.status === "pending" && !t.running; })],
      ["now", "Now", "", all.filter(function (t) { return t.running && t.status === "pending"; })],
      ["done", "Done", "Drop a card here to mark it done.", both.filter(function (t) { return t.status === "done"; })],
      ["failed", "Failed", "Drop here to mark failed; a reason is asked first.", both.filter(function (t) { return t.status === "failed" || t.status === "skipped"; })]
    ];
    var empties = { unscheduled: "Nothing without a time.", planned: "Nothing planned.", now: "Nothing running right now.", done: "Nothing done yet.", failed: "Nothing failed." };
    return '<div class="l3-board" aria-label="Board" data-slot="columns">' + cols.map(function (c) {
      return '<section class="col col-' + c[0] + '" data-col="' + c[0] + '" aria-labelledby="col-' + c[0] + '"><header class="col-h"><h2 id="col-' + c[0] + '">' + c[1] + '</h2><span class="col-n">' + c[3].length + "</span></header>" +
        (c[2] ? '<p class="col-note">' + c[2] + "</p>" : "") + (c[3].length ? '<ol class="cards">' + c[3].map(card).join("") + "</ol>" : '<p class="col-empty">' + empties[c[0]] + "</p>") +
        (c[0] === "planned" ? UI.btn("item_add", null, "Add a card", { icon: "plus", cls: "addcard" }) : "") + "</section>";
    }).join("") + "</div>";
  }
  function strip(d) {
    var w0 = D.toMin(UI.data.window.start), span = Math.max(60, D.toMin(UI.data.window.end) - w0);
    var segs = d.items.map(function (t) {
      var a = Math.max(0, D.toMin(t.start) - w0), b = Math.min(span, D.toMin(t.end) - w0);
      return b > a ? '<span class="sg k-' + t.kind + " s-" + t.status + '" style="left:' + a / span * 100 + "%;width:" + (b - a) / span * 100 + '%" title="' + esc(t.start + " " + t.title) + '"></span>' : "";
    }).join("");
    var nowM = D.toMin(UI.data.now) - w0, busy = d.items.reduce(function (m, t) { return m + (t.duration || 0); }, 0);
    return '<div class="l3-strip" data-slot="summary"><div class="strip-bar" aria-hidden="true">' + segs + (d.offset === 0 && nowM >= 0 && nowM <= span ? '<span class="sg-now" style="left:' + nowM / span * 100 + '%"></span>' : "") + "</div>" +
      '<p class="strip-sum">' + D.dur(Math.max(0, span - busy)) + " free · " + d.items.concat(d.untimed).filter(function (t) { return t.status === "done"; }).length + " done · " + d.untimed.length + " unscheduled</p></div>";
  }
  function home() {
    var d = UI.day(UI.view.dayOffset), p = UI.preview(), empty = !d.items.length && !d.untimed.length;
    var extra = R.decisions().map(R.decisionCard).join("") + R.olderList();
    return '<div class="l3-day"><div class="l3-title" data-slot="board-head"><h2 class="screen-title">' + esc(D.label(d.date)) + " · " + esc(D.label(d.date, true)) + '</h2><span class="muted">Window ' + UI.data.window.start + "–" + UI.data.window.end + "</span></div>" +
      '<div data-slot="toolbar">' + R.toolbar() + "</div>" + strip(d) + "</div>" +
      (p === "loading" || p === "error" ? UI.state("") : empty ? '<div class="l3-pad">' + UI.empty("An empty board. Add a card for each thing to do; then " + esc(UI.data.mainAction) + " lays them out in time.", UI.btn("item_add", null, "Add your first card", { icon: "plus", cls: "primary", kbd: "A" })) + "</div>" : board(d)) +
      (extra ? '<div class="l3-extra" data-slot="extra">' + extra + "</div>" : "");
  }

  /* drag and drop: a shortcut for the same actions the buttons run */
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
        var id = dragId, to = col.getAttribute("data-col"), t = UI.findItem(id); dragId = null;
        if (!t) return;
        if (to === "done") return UI.trigger("item_done", { id: id });
        if (to === "failed") return UI.trigger("item_failed", { id: id });
        if (to === "now") return UI.toast && UI.toast("An item is “now” while its time runs. Move it to a time instead.");
        if (to === "planned") return UI.trigger("item_move", { id: id });
      });
    });
  }
  UI.on("escape", function () { if (UI.layout && UI.layout.id === 3 && UI.screen() !== "home" && !UI.dlg.isOpen() && !UI.overlay.isOpen()) location.hash = "#home"; });

  UI.start({
    id: 3, defaultScreen: "home", home: home,
    frame: function (screen, inner) {
      var drawer = screen !== "home";
      return '<div class="l3">' + navBar() + '<div class="l3-main"' + (drawer ? " inert" : "") + ">" + (drawer ? home() : inner) + "</div>" +
        (drawer ? '<a href="#home" class="scrim" aria-label="Close and go back to the board"></a><section class="drawer" data-slot="drawer" aria-label="' + esc(UI.TITLES[screen] || screen) + '">' +
          '<div class="dr-h"><a class="close" href="#home" aria-label="Back to the board">' + I("x") + '</a></div><div class="dr-body">' + inner + "</div></section>" : "") + "</div>";
    },
    after: wire
  });
})();
