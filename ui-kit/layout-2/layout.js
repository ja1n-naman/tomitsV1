/* Layout 2: Calendar grid (UI_GUIDE.md §4.2).
   Slots: tabs; home: grid-bar, toolbar, grid, side; other screens: page. */
(function () {
  var UI = window.UI, R = UI.r, D = UI.date, esc = UI.esc, I = function (n) { return UI.icon(n); };
  var PX = 1.25;   // pixels per minute (75px per hour)

  function tabs() {
    var n = R.decisions().length;
    return '<nav class="l2-tabs" aria-label="Main navigation" data-slot="tabs">' + UI.navLink("home", "Home") +
      '<span class="l2-group">' + UI.navLink("list", "List", { badge: n || "" }) + UI.navLink("progress", "Progress") + UI.navLink("history", "History") + "</span>" +
      UI.navLink("voice", "Voice") + UI.navLink("settings", "Settings") + UI.navLink("later", "Later <small>soon</small>", { cls: "soon" }) +
      '<a href="../index.html" data-act="open_layouts"><span>Layouts</span></a></nav>';
  }
  function week() {   // the 7 days around the chosen day, Monday first (the week start would come from your backend)
    var sel = UI.view.dayOffset, wd = new Date(D.offset(sel) + "T12:00").getDay(), first = sel - ((wd + 6) % 7), out = [];
    for (var i = 0; i < 7; i++) out.push(UI.day(first + i));
    return out;
  }
  function bounds(days) {
    var w0 = D.toMin(UI.data.window.start), w1 = D.toMin(UI.data.window.end);
    days.forEach(function (d) { d.items.forEach(function (t) { w0 = Math.min(w0, D.toMin(t.start)); w1 = Math.max(w1, Math.min(1440, D.toMin(t.end))); }); });
    return [Math.floor(w0 / 60) * 60, Math.ceil(w1 / 60) * 60];
  }
  function tile(t, wide, w0) {
    var sel = UI.view.selected === t.id ? " is-sel" : "", top = (D.toMin(t.start) - w0) * PX, h = Math.max(18, (D.toMin(t.end) - D.toMin(t.start)) * PX);
    return '<button type="button" class="tile k-' + t.kind + " s-" + t.status + (t.running && t.status === "pending" ? " is-now" : "") + sel + '" data-act="select_item" data-args=\'{"id":' + t.id + "}'" +
      ' style="top:' + top + "px;height:" + h + 'px" aria-label="' + esc(t.title + ", " + t.start + "–" + t.end + ", " + t.status) + '">' +
      '<span class="t-row">' + R.fixedMark(t) + '<span class="t-title">' + esc(t.title) + "</span>" + (wide ? '<span class="t-time">' + t.start + "–" + t.end + "</span>" : "") + "</span>" +
      (wide ? '<span class="t-why">' + esc(t.status === "failed" || t.status === "skipped" ? t.status + ": " + (t.fail_reason || "") : (t.reason || R.kind(t).label)) + "</span>" : "") + "</button>";
  }
  function ghosts(d, w0) {   // proposed changes drawn on the grid
    if (d.offset !== 0) return "";
    return R.decisions().map(function (p) { return p.moves.map(function (m) {
      var span = String(m.to).split("–"); if (span.length < 2) return "";
      var top = (D.toMin(span[0]) - w0) * PX, h = Math.max(18, (D.toMin(span[1]) - D.toMin(span[0])) * PX);
      return '<div class="gtile" style="top:' + top + "px;height:" + h + 'px"><span class="g-tag">PROPOSED · ' + esc(m.kind.toUpperCase()) + "</span><b>" + esc(m.title) + "</b><span>" + esc(m.to) + "</span></div>";
    }).join(""); }).join("");
  }
  function grid(days) {
    var b = bounds(days), w0 = b[0], w1 = b[1], selOff = UI.view.dayOffset;
    var cols = days.map(function (d) { return d.offset === selOff ? "2.6fr" : "1fr"; }).join(" ");
    var head = '<div class="cal-head" style="grid-template-columns:56px ' + cols + '"><div></div>' + days.map(function (d) {
      return '<button type="button" class="dh' + (d.offset === selOff ? " is-sel" : "") + (d.offset === 0 ? " is-today" : "") + (d.offset < 0 ? " is-past" : "") + '" data-act="day_shift" data-args=\'{"to":' + d.offset + "}'>" +
        '<span class="dh-d">' + D.weekday(d.date) + '</span><span class="dh-n">' + D.dayNum(d.date) + "</span>" + (d.offset < 0 ? '<span class="dh-l">' + I("lock") + "past</span>" : d.offset === 0 ? '<span class="dh-l now">today</span>' : "") + "</button>";
    }).join("") + "</div>";
    var notime = '<div class="cal-notime" style="grid-template-columns:56px ' + cols + '"><div class="nt-l">No time</div>' + days.map(function (d) {
      return '<div class="nt">' + d.untimed.map(function (t) { return '<button type="button" class="chip' + (UI.view.selected === t.id ? " is-sel" : "") + '" data-act="select_item" data-args=\'{"id":' + t.id + "}'>" + I("inbox") + esc(t.title) + " · " + t.duration_text + "</button>"; }).join("") + "</div>";
    }).join("") + "</div>";
    var hours = ""; for (var m = w0; m < w1; m += 60) hours += '<div class="hcell" style="height:' + 60 * PX + 'px"><span>' + D.fromMin(m) + "</span></div>";
    var body = '<div class="cal-body" style="grid-template-columns:56px ' + cols + '"><div class="hcol">' + hours + "</div>" + days.map(function (d) {
      var wide = d.offset === selOff;
      return '<div class="dcol' + (wide ? " is-sel" : "") + (d.offset < 0 ? " is-past" : "") + '" style="height:' + (w1 - w0) * PX + 'px">' + d.items.map(function (t) { return tile(t, wide, w0); }).join("") + ghosts(d, w0) +
        (d.offset === 0 ? '<div class="nowline" style="top:' + (D.toMin(UI.data.now) - w0) * PX + 'px"><span>' + UI.data.now + "</span></div>" : "") + "</div>";
    }).join("") + "</div>";
    return '<div class="cal" data-slot="grid">' + head + notime + '<div class="cal-scroll">' + body + "</div></div>";
  }
  function side() {
    var sel = UI.selectedItem(), p = UI.preview();
    return '<aside class="l2-side" data-slot="side">' + (sel && p === "normal" ? '<section class="side-sec"><p class="eyebrow">Selected</p>' + UI.screens.detail(sel) + "</section>"
      : '<section class="side-sec">' + UI.state(UI.empty("Click a block in the grid to see why it’s there and what you can do with it.")) + "</section>") +
      R.decisions().map(function (d) { return '<section class="side-sec">' + R.decisionCard(d) + "</section>"; }).join("") +
      '<section class="side-sec"><h3 class="panel-h">Progress ' + UI.navLink("progress", "open", { cls: "small" }) + "</h3>" + R.progressSummary() + "</section>" +
      (R.olderList() ? '<section class="side-sec">' + R.olderList() + "</section>" : "") + "</aside>";
  }
  function home() {
    var days = week(), any = days.some(function (d) { return d.items.length || d.untimed.length; }), p = UI.preview();
    var main = p === "loading" || p === "error" ? '<div class="l2-pad">' + UI.state("") + "</div>" : any ? grid(days)
      : '<div class="l2-pad" data-slot="grid">' + UI.empty("Nothing planned this week yet. Add an item; give it a time to fix it in place, or let " + esc(UI.data.mainAction) + " place it.", UI.btn("item_add", null, "Add your first item", { icon: "plus", cls: "primary", kbd: "A" })) + "</div>";
    return '<div class="l2-cal"><div class="l2-calwrap"><div class="cal-bar" data-slot="grid-bar"><h2 class="screen-title">Week of ' + esc(D.label(days[0].date, true)) + ' <span class="muted">· ' + esc(D.long(UI.day(UI.view.dayOffset).date)) + "</span></h2>" +
      '<div class="legend">' + ["fixed", "pinned", "auto"].map(function (k) { return R.kindBadge({ kind: k }); }).join("") + '<span class="kind k-ghost">Proposed</span></div></div>' +
      '<div class="l2-toolbar" data-slot="toolbar">' + R.toolbar({ compact: true }) + "</div>" + main + "</div>" + side() + "</div>";
  }

  UI.start({
    id: 2, defaultScreen: "home", home: home,
    frame: function (screen, inner) {
      return '<div class="l2">' + tabs() + (screen === "home" ? inner : '<div class="l2-page" data-slot="page">' + inner + "</div>") + "</div>";
    }
  });
})();
