/* Layout 4: Focus on now (UI_GUIDE.md §4.4).
   Slots: quiet-top, stage (now), next, dock; other screens: sheet.
   The home screen is #now; "home" maps to it. */
(function () {
  var UI = window.UI, R = UI.r, D = UI.date, esc = UI.esc, I = function (n) { return UI.icon(n); };

  function dock() {
    var n = R.decisions().length;
    return '<nav class="dock" aria-label="Everything else" data-slot="dock">' + UI.navLink("now", "Now", { icon: "focus" }) + UI.navLink("list", "Whole list", { icon: "list", badge: n || "" }) +
      UI.navLink("progress", "Progress", { icon: "target" }) + UI.navLink("history", "History", { icon: "history" }) + UI.navLink("voice", "Voice", { icon: "wave" }) +
      UI.navLink("settings", "Settings", { icon: "settings" }) + UI.navLink("later", "Later <em>soon</em>", { icon: "timer" }) +
      '<a href="../index.html" data-act="open_layouts">' + I("layers") + "<span>Layouts</span></a></nav>";
  }
  function stage() {
    var p = UI.preview();
    if (p === "loading" || p === "error") return '<div class="stage" data-slot="stage">' + UI.state("") + "</div>";
    var nn = UI.nowAndNext(), now = nn.now, next = nn.next, untimed = nn.day.untimed.filter(function (t) { return t.status === "pending"; }), html = "";
    if (now) {
      var pct = Math.round((now.elapsed || 0) * 100);
      html += '<p class="now-k"><span class="dot-live" aria-hidden="true"></span>Now · ' + now.start + "–" + now.end + " · " + now.minutes_left + " min left</p>" +
        '<h2 class="now-title screen-title">' + esc(now.title) + "</h2>" +
        '<div class="now-line" role="progressbar" aria-label="Time used" aria-valuenow="' + pct + '" aria-valuemin="0" aria-valuemax="100"><span style="width:' + pct + '%"></span></div>' +
        '<p class="now-why">' + esc(R.kind(now).label) + ", P" + now.priority + " " + esc(now.priority_name) + (now.reason ? ". " + esc(now.reason) : "") + ".</p>" +
        '<div class="now-act">' + UI.btn("item_done", { id: now.id }, "Done", { icon: "check", cls: "primary big", kbd: "D" }) + UI.btn("item_extend", { id: now.id }, "Extend", { cls: "big", kbd: "X" }) +
        UI.btn("item_failed", { id: now.id }, "Didn’t work", { cls: "big", kbd: "F" }) + UI.btn("item_skip", { id: now.id }, "Skip", { cls: "big", kbd: "S" }) + "</div>";
    } else {
      var has = nn.day.items.length + nn.day.untimed.length;
      html += '<p class="now-k">Nothing running right now</p><h2 class="now-title screen-title soft">' + (next[0] ? "Free until " + next[0].start : has ? "Nothing more today" : "A clear day") + "</h2>" +
        (has ? "" : '<p class="now-why">Add what you want to do. ' + esc(UI.data.mainAction) + " places it around anything with a fixed time.</p>") +
        '<div class="now-act">' + UI.btn("item_add", null, "Add an item", { icon: "plus", cls: "primary big", kbd: "A" }) + (untimed.length ? UI.btn("main_action", null, esc(UI.data.mainAction), { icon: "route", cls: "big", kbd: "P" }) : "") + "</div>";
    }
    var nx = "";
    if (next[0]) {
      var n = next[0];
      nx = '<section class="next" aria-labelledby="next-h" data-slot="next"><h3 id="next-h" class="next-k">Next</h3><p class="next-title"><span class="t">' + n.start + "</span>" + esc(n.title) + "</p>" +
        '<p class="next-why">' + esc(R.kind(n).label) + (n.reason ? " · " + esc(n.reason) : "") + "</p>" + R.itemActions(n, { short: true }) +
        '<ol class="then">' + next.slice(1, 4).map(function (t) { return '<li><span class="t">' + t.start + "</span>" + esc(t.title) + "</li>"; }).join("") + "</ol></section>";
    }
    var extras = ['<a href="#list">See the whole list</a>'];
    if (untimed.length) extras.push('<a href="#list">' + untimed.length + " unscheduled</a>");
    if (R.decisions().length) extras.push('<a href="#list">' + R.decisions().length + " change waiting for a decision</a>");
    return '<div class="stage" data-slot="stage">' + html + nx + '<p class="extras">' + extras.join(" · ") + "</p></div>";
  }
  var listScreen = function () { return UI.screens.list() + R.decisions().map(R.decisionCard).join(""); };

  UI.TITLES.now = "Now";
  UI.start({
    id: 4, defaultScreen: "now", decisionsScreen: "list", mapScreen: { home: "now" }, extraScreens: { now: stage }, screens: { list: listScreen },
    frame: function (screen, inner) {
      var top = '<div class="quiet-top" data-slot="quiet-top"><span>' + esc(D.label(D.today(), true)) + " · " + UI.data.now + " (placeholder clock)</span></div>";
      if (screen === "now") return '<div class="l4">' + top + inner + dock() + "</div>";
      return '<div class="l4"><section class="sheet" data-slot="sheet"><div class="sheet-in"><a class="back" href="#now">' + I("chev-left") + "Back to now</a>" + inner + "</div></section>" + dock() + "</div>";
    }
  });
})();
