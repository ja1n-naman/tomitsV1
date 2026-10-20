/* Layout 2: Calendar grid. Top tabs; a week grid with the chosen day widened,
   a "no time" row like all-day events, and a side panel (selected task + goals ladder). */
(function () {
  var T = window.T, R = T.r, I = function (n) { return T.icon(n); };
  var PX = 1.25;

  function tabs(st) {
    var p = st.proposals.length;
    return '<nav class="l2-tabs" aria-label="Main navigation">' + R.nav("today", "Today") + R.nav("reschedule", "Reschedule", { badge: p || "" }) +
      '<span class="l2-group">' + R.nav("day", "Day") + R.nav("week", "Week") + R.nav("month", "Month") + "</span>" +
      R.nav("history", "History") + R.nav("voice", "Voice") + R.nav("settings", "Settings") + R.nav("focus", "Focus <small>2.0</small>", { cls: "soon" }) + R.nav("layouts", "Layouts") + "</nav>";
  }

  function bounds(st, days) {
    var w0 = R.toMin(st.settings.day_start), w1 = R.toMin(st.settings.day_end);
    days.forEach(function (d) { d.tasks.forEach(function (t) { w0 = Math.min(w0, R.toMin(t.start)); w1 = Math.max(w1, Math.min(1440, R.toMin(t.start) + t.duration)); }); });
    return [Math.floor(w0 / 60) * 60, Math.ceil(w1 / 60) * 60];
  }

  function tile(t, wide) {
    var sel = T.view.selected === t.id ? " is-sel" : "";
    return '<button type="button" class="tile k-' + t.placement + " s-" + t.status + (t.running ? " is-now" : "") + sel + '" data-act="select_task" data-args=\'{"id":' + t.id + "}'" +
      ' style="top:{top}px;height:{h}px" aria-label="' + R.esc(t.title + ", " + t.start + "–" + t.end + ", " + t.status) + '">' +
      '<span class="t-row">' + R.fixedMark(t) + '<span class="t-title">' + R.esc(t.title) + "</span>" + (wide ? '<span class="t-time">' + t.start + "–" + t.end + "</span>" : "") + "</span>" +
      (wide ? '<span class="t-why">' + R.esc(t.status === "failed" || t.status === "skipped" ? t.status + ": " + (t.fail_reason || "") : (t.reason || R.kind(t)[0])) + "</span>" : "") + "</button>";
  }

  function grid(st, days, ghosts) {
    var b = bounds(st, days), w0 = b[0], w1 = b[1];
    var cols = days.map(function (d) { return d.date === st.day.date ? "2.6fr" : "1fr"; }).join(" ");
    var head = '<div class="cal-head" style="grid-template-columns:56px ' + cols + '"><div></div>' + days.map(function (d) {
      return '<button type="button" class="dh' + (d.date === st.day.date ? " is-sel" : "") + (d.is_today ? " is-today" : "") + (d.is_past ? " is-past" : "") + '" data-act="day_pick_btn" data-args=\'{"date":"' + d.date + "\"}'>" +
        '<span class="dh-d">' + R.dayLabel(d.date, "plain").slice(0, 3) + '</span><span class="dh-n">' + R.parse(d.date).getDate() + "</span>" + (d.is_past ? '<span class="dh-l">' + I("lock") + "past</span>" : d.is_today ? '<span class="dh-l now">today</span>' : "") + "</button>";
    }).join("") + "</div>";
    var notime = '<div class="cal-notime" style="grid-template-columns:56px ' + cols + '"><div class="nt-l">No time</div>' + days.map(function (d) {
      return '<div class="nt">' + d.untimed.map(function (t) {
        return '<button type="button" class="chip' + (T.view.selected === t.id ? " is-sel" : "") + '" data-act="select_task" data-args=\'{"id":' + t.id + "}'>" + I("inbox") + R.esc(t.title) + " · " + t.duration_text + "</button>"; }).join("") + "</div>";
    }).join("") + "</div>";
    var hours = "";
    for (var m = w0; m < w1; m += 60) hours += '<div class="hcell" style="height:' + 60 * PX + 'px"><span>' + R.fromMin(m) + "</span></div>";
    var body = '<div class="cal-body" style="grid-template-columns:56px ' + cols + '"><div class="hcol">' + hours + "</div>" + days.map(function (d) {
      var wide = d.date === st.day.date;
      var tiles = d.tasks.map(function (t) { return tile(t, wide).replace("{top}", (R.toMin(t.start) - w0) * PX).replace("{h}", Math.max(18, t.duration * PX)); }).join("");
      var gh = (ghosts || []).filter(function (g) { return g.to_day === d.date && g.to_start; }).map(function (g) {
        var dur = g.kind === "extend" ? g.new_duration : g.duration;
        return '<div class="gtile" style="top:' + (R.toMin(g.to_start) - w0) * PX + "px;height:" + Math.max(18, dur * PX) + 'px"><span class="g-tag">' + { copy: "NEW COPY", shift: "MOVED HERE", extend: "EXTENDED" }[g.kind] + "</span><b>" + R.esc(g.title) + "</b><span>" + g.to_start + "–" + g.to_end + "</span></div>";
      }).join("");
      var now = d.is_today ? '<div class="nowline" style="top:' + (R.toMin(st.now.slice(11, 16)) - w0) * PX + 'px"><span>' + st.now.slice(11, 16) + "</span></div>" : "";
      return '<div class="dcol' + (wide ? " is-sel" : "") + (d.is_past ? " is-past" : "") + '" style="height:' + (w1 - w0) * PX + 'px">' + tiles + gh + now + "</div>";
    }).join("") + "</div>";
    return '<div class="cal">' + head + notime + '<div class="cal-scroll">' + body + "</div></div>";
  }

  function ladder(st) {
    var p = st.periods.day;
    if (!p.goals.length) return '<section class="side-sec"><h3 class="panel-h">Goals</h3>' + R.empty("No goal for " + R.esc(R.dayLabel(p.start)) + " yet. Each day needs one; it can count toward a week and month goal.",
      R.btn("new_goal", { kind: "day", start: p.start }, "New day goal", { icon: "plus" })) + "</section>";
    return '<section class="side-sec"><h3 class="panel-h">Goals <a href="#day" data-nav="day" class="small">day page</a></h3><ul class="ladders">' + p.goals.map(function (g) {
      var chain = [g].concat(g.ancestors);
      return '<li class="lad">' + chain.map(function (c, i) {
        return '<div class="lad-row l' + i + '"><span class="lad-l">' + c.kind + '</span><span class="lad-t">' + R.esc(c.title) + '</span><span class="lad-n">' + R.esc(c.text) + "</span>" +
          (c.target != null ? '<span class="bar"><span style="width:' + Math.min(100, c.fraction * 100) + '%"></span></span>' : "") + "</div>";
      }).join("") + "</li>";
    }).join("") + "</ul></section>";
  }

  function side(st) {
    var sel = R.selectedTask();
    return '<aside class="l2-side">' + (sel ? '<section class="side-sec"><p class="eyebrow">Selected</p>' + R.taskRow(sel, { keys: true }) + "</section>"
      : '<section class="side-sec">' + R.empty("Click a block in the grid to see why it’s there and what you can do with it.") + "</section>") +
      st.proposals.map(function (p) { return '<section class="side-sec">' + R.proposalCard(p) + "</section>"; }).join("") + ladder(st) +
      (st.overdue.length ? '<section class="side-sec">' + R.overdueList(st) + "</section>" : "") + "</aside>";
  }

  function today(st) {
    var any = st.week.days.some(function (d) { return d.tasks.length || d.untimed.length; });
    var main = any ? grid(st, st.week.days) : R.empty("Nothing planned this week yet. Add a task; give it a time to fix it in place, or let Plan my day place it in your day window.",
      R.btn("add_task", { date: st.day.date }, "Add your first task (v0)", { icon: "plus", cls: "primary", kbd: "A" }));
    return '<div class="l2-cal"><div class="l2-calwrap"><div class="cal-bar"><h2 class="screen-title">Week of ' + R.esc(R.dayLabel(st.week.start, "plain")) + ' <span class="muted">· ' + R.esc(st.day.label) + "</span></h2>" +
      '<div class="legend"><span class="kind k-fixed">' + I("anchor") + 'Fixed</span><span class="kind k-pinned">' + I("pin") + 'Pinned</span><span class="kind k-auto">' + I("auto") + "Auto-placed</span></div></div>" +
      '<div class="l2-daybar">' + R.dayBar(st, { compact: true }) + "</div>" + main + "</div>" + side(st) + "</div>";
  }

  function reschedule(st) {
    var p = st.proposals[0];
    var days = st.week.days.filter(function (d) { return d.date === st.today || d.date === st.tomorrow; });
    if (days.length < 2) days = [st.week.days[0]];
    var g = p ? p.moves : [];
    return '<div class="l2-cal"><div class="l2-calwrap"><div class="cal-bar"><h2 class="screen-title">Reschedule <span class="muted">· today and tomorrow only</span></h2>' +
      '<div class="legend"><span class="kind k-ghost">Proposed</span></div></div>' + (p ? grid(st, days, g) : '<div class="l2-pad">' + R.empty("Nothing to reschedule now. A proposal appears here, drawn on the grid, when a task fails, is skipped or runs over.") + "</div>") +
      '</div><aside class="l2-side"><section class="side-sec">' + R.reschedulePage(st) + "</section></aside></div>";
  }

  T.ACTIONS.day_pick_btn = { ui: "show that day", run: function (a) { T.view.day = a.date === T.state.today ? null : a.date; T.saveView(); T.refresh(true); } };

  T.layouts[2] = {
    id: 2, defaultScreen: "today", today: today, screens: { reschedule: reschedule },
    frame: function (st, screen, inner) {
      var full = screen === "today" || screen === "reschedule";
      return '<div class="l2">' + tabs(st) + (full ? inner : '<div class="l2-page">' + inner + "</div>") + "</div>";
    }
  };
})();
