/* Layout 1: Timeline. Left sidebar; the day as a proportional vertical timeline. */
(function () {
  var T = window.T, R = T.r, I = function (n) { return T.icon(n); };
  var PX = 1.4;

  function sideNav(st) {
    var p = st.proposals.length;
    return '<nav class="l1-nav" aria-label="Main navigation"><p class="nav-h">Plan</p>' +
      R.nav("today", "Today", { icon: "today" }) + R.nav("reschedule", "Reschedule", { icon: "reschedule", badge: p || "" }) +
      '<p class="nav-h">Track</p>' + R.nav("day", "Day", { icon: "target" }) + R.nav("week", "Week", { icon: "calendar" }) + R.nav("month", "Month", { icon: "grid" }) +
      R.nav("history", "Missed & skipped", { icon: "history" }) +
      '<p class="nav-h">App</p>' + R.nav("voice", "Voice", { icon: "wave" }) + R.nav("settings", "Settings", { icon: "settings" }) +
      R.nav("focus", "Focus <small class=\"tag\">2.0</small>", { icon: "timer", cls: "later" }) + R.nav("layouts", "Layouts", { icon: "layers" }) + "</nav>" +
      '<div class="l1-mic"><button type="button" class="mic-big small" data-act="mic_toggle" aria-pressed="false" aria-label="Talk">' + I("mic") + '</button><div><b data-mic-phase>Ready</b><span class="small muted">Hold <kbd>V</kbd> to talk</span></div></div>';
  }

  function timeline(st) {
    var d = st.day, w0 = R.toMin(st.settings.day_start), w1 = R.toMin(st.settings.day_end);
    d.tasks.forEach(function (t) { w0 = Math.min(w0, R.toMin(t.start)); w1 = Math.max(w1, Math.min(1440, R.toMin(t.start) + t.duration)); });
    w0 = Math.floor(w0 / 60) * 60; w1 = Math.ceil(w1 / 60) * 60;
    var hours = "";
    for (var m = w0; m <= w1; m += 60) hours += '<div class="hr" style="top:' + (m - w0) * PX + 'px"><span>' + R.fromMin(m) + "</span></div>";
    var gaps = d.gaps.filter(function (g) { return g.minutes >= 30; }).map(function (g) {
      return '<div class="gap" style="top:' + (R.toMin(g.start) - w0) * PX + "px;height:" + g.minutes * PX + 'px"><span>Free ' + g.start + "–" + g.end + " · " + R.dur(g.minutes) + "</span></div>";
    }).join("");
    var blocks = d.tasks.map(function (t) {
      var h = Math.max(t.duration * PX, 22), tight = h < 60;
      var sel = T.view.selected === t.id ? " is-sel" : "";
      return '<article class="blk s-' + t.status + " k-" + t.placement + (t.running ? " is-now" : "") + (tight ? " tight" : "") + sel + '" style="top:' + (R.toMin(t.start) - w0) * PX + "px;height:" + h + 'px">' +
        '<button type="button" class="blk-sel" data-act="select_task" data-args=\'{"id":' + t.id + '}\' aria-label="Select ' + R.esc(t.title) + ", " + t.start + '"></button>' +
        '<div class="blk-main"><p class="blk-title">' + R.when(t) + " <b>" + R.esc(t.title) + "</b> " + R.statusBadge(t) + "</p>" +
        '<p class="blk-meta">' + R.kindBadge(t) + R.prio(t) + '<span class="dur">' + t.duration_text + "</span>" + R.goalChip(t) + "</p>" + R.why(t) + "</div>" +
        (tight ? "" : R.taskActions(t, { short: true })) + "</article>";
    }).join("");
    var now = d.is_today ? '<div class="nowline" style="top:' + (R.toMin(st.now.slice(11, 16)) - w0) * PX + 'px"><span>' + st.now.slice(11, 16) + "</span></div>" : "";
    return '<div class="tl" style="height:' + ((w1 - w0) * PX + 20) + 'px"><div class="tl-hours">' + hours + '</div><div class="tl-lane">' + gaps + blocks + now + "</div></div>";
  }

  function today(st) {
    var d = st.day, sel = R.selectedTask();
    var all = d.tasks.length + d.untimed.length;
    var head = '<header class="l1-head"><div><h2 class="screen-title">' + R.esc(d.label) + '</h2><p class="muted">Day window ' + st.settings.day_start + "–" + st.settings.day_end +
      (d.is_today ? " · it is " + st.now.slice(11, 16) : d.is_past ? " · past days never change" : "") + "</p></div></header>";
    var main = all ? (d.tasks.length ? timeline(st) : R.empty("No timed tasks on this day yet. Plan my day places the tasks below into the free time; or give one a time yourself.",
      R.btn("plan_day", { date: d.date }, "Plan my day", { icon: "auto", cls: "primary", disabled: d.is_past })))
      : R.empty("Nothing planned for " + R.esc(d.short) + " yet. Add the things you want to do; tasks with a time stay put, and Plan my day places the rest.",
        R.btn("add_task", { date: d.date }, "Add your first task (v3)", { icon: "plus", cls: "primary", kbd: "A" }));
    var aside = '<aside class="l1-aside">' +
      (sel ? '<section class="panel"><h3 class="panel-h">' + I("focus") + "Selected</h3>" + R.taskRow(sel, { keys: true }) + "</section>" : "") +
      '<section class="panel"><h3 class="panel-h">' + I("inbox") + "No time / didn’t fit</h3>" + R.untimedList(st) + "</section>" +
      st.proposals.map(R.proposalCard).join("") + R.overdueList(st) +
      (st.alarms.snoozed.length ? '<section class="panel"><h3 class="panel-h">' + I("bell") + "Snoozed</h3>" + st.alarms.snoozed.map(function (s) { return "<p>" + R.esc(s.title) + " rings again at " + s.due + "</p>"; }).join("") + "</section>" : "") +
      "</aside>";
    return head + R.dayBar(st) + R.dayStats(d) + '<div class="l1-today">' + '<div class="l1-tl">' + main + "</div>" + aside + "</div>";
  }

  T.layouts[1] = {
    id: 1, defaultScreen: "today", today: today,
    frame: function (st, screen, inner) {
      return '<div class="l1"><aside class="l1-side">' + sideNav(st) + '</aside><div class="l1-main" data-screen-body="' + screen + '">' + inner + "</div></div>";
    }
  };
})();
