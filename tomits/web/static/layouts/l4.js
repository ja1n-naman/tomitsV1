/* Layout 4: Focus on now. One calm stage: the current task large, what's next
   below. Everything else is one click away in a dock that opens full sheets. */
(function () {
  var T = window.T, R = T.r, I = function (n) { return T.icon(n); };

  function dock(st) {
    var p = st.proposals.length;
    return '<nav class="dock" aria-label="Everything else">' + R.nav("now", "Now", { icon: "focus" }) + R.nav("today", "Whole day", { icon: "list" }) +
      R.nav("reschedule", "Reschedule", { icon: "reschedule", badge: p || "" }) + R.nav("day", "Goals", { icon: "target" }) + R.nav("history", "Missed", { icon: "history" }) +
      R.nav("voice", "Voice", { icon: "wave" }) + R.nav("settings", "Settings", { icon: "settings" }) + R.nav("focus", "Pomodoro <em>later</em>", { icon: "timer" }) +
      R.nav("layouts", "Layouts", { icon: "layers" }) + "</nav>";
  }

  function stage(st) {
    var nn = R.nowAndNext(), now = nn.now, next = nn.next, today = nn.today;
    var untimed = today.untimed.filter(function (t) { return t.status === "pending"; });
    var html = "";
    if (now) {
      html += '<p class="now-k"><span class="dot-live" aria-hidden="true"></span>Now · ' + now.start + "–" + now.end + " · " + now.minutes_left + " min left</p>" +
        '<h2 class="now-title screen-title">' + R.esc(now.title) + "</h2>" +
        '<div class="now-line" role="progressbar" aria-label="Time used" aria-valuenow="' + Math.round(now.elapsed * 100) + '" aria-valuemin="0" aria-valuemax="100"><span style="width:' + Math.round(now.elapsed * 100) + '%"></span></div>' +
        '<p class="now-why">' + R.kind(now)[0] + ", P" + now.priority + " " + R.esc(now.priority_name) + (now.reason ? ". Placed here because " + R.esc(now.reason) : "") + ".</p>" +
        '<div class="now-act">' + R.btn("mark_done", { id: now.id }, "Done", { icon: "check", cls: "primary big", kbd: "D" }) + R.btn("extend_task", { id: now.id }, "Still going", { cls: "big", kbd: "X" }) +
        R.btn("mark_failed", { id: now.id }, "Didn’t work", { cls: "big", kbd: "F" }) + R.btn("mark_skipped", { id: now.id }, "Skip", { cls: "big", kbd: "S" }) + "</div>";
    } else {
      var has = today.tasks.length + today.untimed.length;
      html += '<p class="now-k">Nothing running right now</p><h2 class="now-title screen-title soft">' +
        (next[0] ? "Free until " + next[0].start : has ? "No more timed tasks today" : "A clear day") + "</h2>" +
        (has ? "" : '<p class="now-why">Add what you want to do today. Plan my day will place it in your day window around anything with a fixed time.</p>') +
        '<div class="now-act">' + R.btn("add_task", { date: st.today }, "Add a task", { icon: "plus", cls: "primary big", kbd: "A" }) +
        (untimed.length ? R.btn("plan_day", { date: st.today }, "Plan my day", { icon: "auto", cls: "big", kbd: "P" }) : "") + "</div>";
    }
    if (next[0]) {
      var n = next[0];
      html += '<section class="next" aria-labelledby="next-h"><h3 id="next-h" class="next-k">Next</h3><p class="next-title"><span class="t">' + n.start + "</span>" + R.esc(n.title) + "</p>" +
        '<p class="next-why">' + R.kind(n)[0] + (n.reason ? " · " + R.esc(n.reason) : "") + "</p>" + R.taskActions(n, { short: true }) +
        '<ol class="then">' + next.slice(1, 4).map(function (t) { return '<li><span class="t">' + t.start + "</span>" + R.esc(t.title) + "</li>"; }).join("") + "</ol></section>";
    }
    var extras = [];
    extras.push('<a href="#today" data-nav="today">See the whole day</a>');
    if (untimed.length) extras.push('<a href="#today" data-nav="today">' + untimed.length + " without a time</a>");
    if (st.proposals.length) extras.push('<a href="#reschedule" data-nav="reschedule">' + st.proposals.length + " reschedule proposal waiting</a>");
    html += '<p class="extras">' + extras.join(" · ") + "</p>";
    return '<div class="stage">' + html + "</div>";
  }

  function wholeDay(st) {
    var d = st.day;
    var rows = d.tasks.concat(d.untimed);
    return '<h2 class="screen-title">The whole day</h2><p class="lead">' + R.esc(d.label) + ". Fixed tasks keep their time; pinned ones stay where you put them; the rest were placed for you.</p>" +
      R.dayBar(st) + (rows.length ? '<ol class="agenda">' + d.tasks.map(function (t) { return "<li>" + R.taskRow(t) + "</li>"; }).join("") + "</ol>" +
        (d.untimed.length ? '<h3 class="sh-h">No time yet</h3><ol class="agenda">' + d.untimed.map(function (t) { return "<li>" + R.taskRow(t) + "</li>"; }).join("") + "</ol>" : "")
        : R.empty("Nothing on " + R.esc(d.short) + " yet. Add tasks; anything with a time stays put, and Plan my day places the rest.", R.btn("add_task", { date: d.date }, "Add a task", { icon: "plus", cls: "primary" }))) +
      R.overdueList(st);
  }

  T.layouts[4] = {
    id: 4, defaultScreen: "now", today: wholeDay, extraScreens: { now: stage },
    frame: function (st, screen, inner) {
      var top = '<div class="quiet-top"><span class="clock">' + R.esc(R.dayLabel(st.today, "plain")) + " · " + st.now.slice(11, 16) + "</span></div>";
      if (screen === "now") return '<div class="l4">' + top + inner + dock(st) + "</div>";
      return '<div class="l4">' + '<section class="sheet"><div class="sheet-in"><a class="back" href="#now" data-nav="now">' + I("chev-left") + "Back to now</a>" + inner + "</div></section>" + dock(st) + "</div>";
    }
  };
})();
