/* Layout 1: Timeline (UI_GUIDE.md §4.1).
   Slots: nav, nav-foot, main (home: main-head, toolbar, timeline, aside). */
(function () {
  var UI = window.UI, R = UI.r, D = UI.date, esc = UI.esc, I = function (n) { return UI.icon(n); };
  var PX = 1.4;   // pixels per minute

  function sideNav() {
    var n = R.decisions().length;
    return '<nav class="l1-nav" aria-label="Main navigation"><p class="nav-h">Main</p>' +
      UI.navLink("home", "Home", { icon: "today" }) + UI.navLink("list", "List", { icon: "list", badge: n || "" }) +
      '<p class="nav-h">Track</p>' + UI.navLink("progress", "Progress", { icon: "target" }) + UI.navLink("history", "History", { icon: "history" }) +
      '<p class="nav-h">App</p>' + UI.navLink("voice", "Voice", { icon: "wave" }) + UI.navLink("settings", "Settings", { icon: "settings" }) +
      UI.navLink("later", 'Later <small class="tag">soon</small>', { icon: "timer", cls: "later" }) +
      '<a href="../index.html" data-act="open_layouts">' + I("layers") + "<span>Layouts</span></a></nav>" +
      '<div class="l1-mic" data-slot="nav-foot"><button type="button" class="mic-big small" data-act="mic_toggle" aria-pressed="false" aria-label="Talk">' + I("mic") + '</button><div><b data-mic-phase>Ready</b><span class="small muted">Hold <kbd>V</kbd> to talk</span></div></div>';
  }

  function gaps(d, w0, w1) {
    var out = [], cur = w0;
    d.items.slice().sort(function (a, b) { return D.toMin(a.start) - D.toMin(b.start); }).forEach(function (t) {
      var s = D.toMin(t.start); if (s - cur >= 30) out.push([cur, s]); cur = Math.max(cur, D.toMin(t.end));
    });
    if (w1 - cur >= 30) out.push([cur, w1]);
    return out;
  }
  function timeline(d) {
    var w0 = D.toMin(UI.data.window.start), w1 = D.toMin(UI.data.window.end);
    d.items.forEach(function (t) { w0 = Math.min(w0, D.toMin(t.start)); w1 = Math.max(w1, Math.min(1440, D.toMin(t.end))); });
    var g0 = D.toMin(UI.data.window.start), g1 = D.toMin(UI.data.window.end);
    w0 = Math.floor(w0 / 60) * 60; w1 = Math.ceil(w1 / 60) * 60;
    var hours = "";
    for (var m = w0; m <= w1; m += 60) hours += '<div class="hr" style="top:' + (m - w0) * PX + 'px"><span>' + D.fromMin(m) + "</span></div>";
    var gapHtml = gaps(d, g0, g1).map(function (g) {
      return '<div class="gap" style="top:' + (g[0] - w0) * PX + "px;height:" + (g[1] - g[0]) * PX + 'px"><span>Free ' + D.fromMin(g[0]) + "–" + D.fromMin(g[1]) + " · " + D.dur(g[1] - g[0]) + "</span></div>";
    }).join("");
    var blocks = d.items.map(function (t) {
      var h = Math.max((D.toMin(t.end) - D.toMin(t.start)) * PX, 22), tight = h < 60, sel = UI.view.selected === t.id ? " is-sel" : "";
      return '<article class="blk s-' + t.status + " k-" + t.kind + (t.running && t.status === "pending" ? " is-now" : "") + (tight ? " tight" : "") + sel + '" style="top:' + (D.toMin(t.start) - w0) * PX + "px;height:" + h + 'px">' +
        '<button type="button" class="blk-sel" data-act="select_item" data-args=\'{"id":' + t.id + '}\' aria-label="Select ' + esc(t.title) + ", " + t.start + '"></button>' +
        '<div class="blk-main"><p class="blk-title">' + R.when(t) + " <b>" + esc(t.title) + "</b> " + R.statusBadge(t) + "</p>" +
        '<p class="blk-meta">' + R.kindBadge(t) + R.prio(t) + '<span class="dur">' + t.duration_text + "</span>" + R.linkChip(t) + "</p>" + R.why(t) + "</div>" +
        (tight ? "" : R.itemActions(t, { short: true })) + "</article>";
    }).join("");
    var now = d.offset === 0 ? '<div class="nowline" style="top:' + (D.toMin(UI.data.now) - w0) * PX + 'px"><span>' + UI.data.now + "</span></div>" : "";
    return '<div class="tl" style="height:' + ((w1 - w0) * PX + 20) + 'px"><div class="tl-hours">' + hours + '</div><div class="tl-lane">' + gapHtml + blocks + now + "</div></div>";
  }

  function home() {
    var d = UI.day(UI.view.dayOffset), sel = UI.selectedItem(), p = UI.preview();
    var head = '<header class="l1-head" data-slot="main-head"><div><h2 class="screen-title">' + esc(D.long(d.date)) + '</h2><p class="muted">Window ' + UI.data.window.start + "–" + UI.data.window.end +
      (d.offset === 0 ? " · it is " + UI.data.now + " (placeholder clock)" : d.offset < 0 ? " · past days never change" : "") + "</p></div></header>";
    var main = p === "loading" || p === "error" ? UI.state("") : d.items.length ? timeline(d) : d.untimed.length
      ? UI.empty("No timed items on this day yet. " + esc(UI.data.mainAction) + " places the items on the right into the free time.", UI.btn("main_action", null, esc(UI.data.mainAction), { icon: "route", cls: "primary" }))
      : R.emptyDay(d);
    var aside = '<aside class="l1-aside" data-slot="aside">' +
      (sel && p === "normal" ? '<section class="panel"><h3 class="panel-h">' + I("focus") + "Selected</h3>" + UI.screens.detail(sel) + "</section>" : "") +
      '<section class="panel"><h3 class="panel-h">' + I("inbox") + "Unscheduled</h3>" + (p === "normal" || p === "empty" ? R.untimedList(d) : UI.state("")) + "</section>" +
      R.decisions().map(R.decisionCard).join("") + R.olderList() + "</aside>";
    return head + '<div data-slot="toolbar">' + R.toolbar() + "</div>" + R.stats(d) + '<div class="l1-today"><div class="l1-tl" data-slot="timeline">' + main + "</div>" + aside + "</div>";
  }

  UI.start({
    id: 1, defaultScreen: "home", home: home,
    frame: function (screen, inner) {
      return '<div class="l1"><aside class="l1-side" data-slot="nav">' + sideNav() + '</aside><div class="l1-main" data-slot="main">' + inner + "</div></div>";
    }
  });
})();
