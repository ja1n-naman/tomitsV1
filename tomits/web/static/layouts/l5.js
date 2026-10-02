/* Layout 5: Split dashboard. Dense tiled panes - plan, goals, reschedule, voice,
   history - all on one screen; any pane can fill the screen. */
(function () {
  var T = window.T, R = T.r, I = function (n) { return T.icon(n); };

  function status(st) {
    var p = st.proposals.length;
    return '<nav class="l5-status" aria-label="Panes">' + R.nav("today", "All panes") + R.nav("reschedule", "Reschedule", { badge: p || "" }) +
      R.nav("day", "Goals") + R.nav("history", "History") + R.nav("voice", "Voice") + R.nav("settings", "Settings") + R.nav("focus", "Focus v2", { cls: "dim" }) +
      R.nav("layouts", "Layouts") + '<span class="st-clock">' + R.esc(R.dayLabel(st.today, "plain")) + " " + st.now.slice(11, 16) + "</span></nav>";
  }
  function pane(id, title, body, max, tools) {
    return '<section class="pane p-' + id + '" aria-labelledby="ph-' + id + '"><header class="ph"><h2 id="ph-' + id + '">' + title + "</h2>" + (tools || "") +
      (max ? '<a class="ph-max" href="#' + max + '" data-nav="' + max + '" aria-label="Open ' + R.esc(title.replace(/<[^>]*>/g, "")) + ' full size">' + I("focus") + "</a>" : "") + '</header><div class="pb">' + body + "</div></section>";
  }

  function planTable(st) {
    var d = st.day, rows = d.tasks.concat(d.untimed);
    if (!rows.length) return R.empty("Nothing on " + R.esc(d.short) + ". Add tasks; Plan my day places those without a time.", R.btn("add_task", { date: d.date }, "Add task", { icon: "plus", cls: "primary", kbd: "A" }));
    return '<table class="t plan"><thead><tr><th scope="col">Time</th><th scope="col">Dur</th><th scope="col">Pri</th><th scope="col">Type</th><th scope="col">Task, and why it is there</th><th scope="col"><span class="sr">Actions</span></th></tr></thead><tbody>' +
      rows.map(function (t) {
        return '<tr class="s-' + t.status + (t.running ? " is-now" : "") + (T.view.selected === t.id ? " is-sel" : "") + '"><td class="mono">' + (t.start || "--:--") + '</td><td class="mono dim">' + t.duration_text +
          '</td><td class="mono p' + t.priority + '">P' + t.priority + "</td><td>" + R.kindBadge(t) + '</td><td><b>' + R.esc(t.title) + "</b> " + R.statusBadge(t) + R.goalChip(t) + R.why(t) + "</td>" +
          '<td class="c-a">' + R.taskActions(t, { short: true }) + R.btn("select_task", { id: t.id }, "", { icon: "chev-right", cls: "quiet tiny", aria: "More actions for " + t.title }) + "</td></tr>";
      }).join("") + "</tbody></table>";
  }
  function goalsMini(st) {
    var p = st.periods.day;
    var rows = ["day", "week", "month"].map(function (k) {
      var pp = st.periods[k];
      return '<tr><th scope="row">' + k + '</th><td>' + (pp.goals.length ? pp.goals.map(function (g) { return R.esc(g.title) + ' <b class="mono">' + R.esc(g.text) + "</b>"; }).join("<br>")
        : '<span class="warn">no goal</span> ' + (pp.locked ? "" : R.btn("new_goal", { kind: k, start: pp.start }, "Add", { cls: "tiny" }))) + "</td><td>" + (pp.process ? '<span class="ok">process set</span>' : '<span class="warn">no process</span>') +
        "</td><td>" + (pp.locked ? '<span class="dim">' + (pp.review_locked ? "locked" : "review open") + "</span>" : "open") + '</td><td><a href="#' + k + '" data-nav="' + k + '">open</a></td></tr>';
    }).join("");
    return '<table class="t"><thead><tr><th scope="col">Period</th><th scope="col">Goals (logged / target)</th><th scope="col">Process</th><th scope="col">State</th><th scope="col"><span class="sr">Open</span></th></tr></thead><tbody>' + rows + "</tbody></table>";
  }
  function voiceMini(st) {
    var log = st.voice.log.slice(0, 5);
    return '<div class="vmini"><button type="button" class="mic-big" data-act="mic_toggle" aria-pressed="false" aria-label="Talk">' + I("mic") + '</button><div><p class="vphase" data-mic-phase>Ready</p><p class="small dim">Hold V to talk. Below ' +
      Math.round(st.voice.low_confidence * 100) + "% nothing happens.</p></div></div>" +
      (log.length ? '<table class="t"><tbody>' + log.map(function (l) {
        return '<tr class="' + (l.acted ? "" : "dim") + '"><td class="mono">' + R.esc((l.at || "").slice(11, 16)) + "</td><td>“" + R.esc(l.text) + '”</td><td class="mono' + (l.confidence != null && l.confidence < st.voice.low_confidence ? " bad" : "") + '">' +
          (l.confidence != null ? Math.round(l.confidence * 100) : "–") + "</td><td>" + R.esc(l.interpreted || "no command") + "</td></tr>"; }).join("") + "</tbody></table>"
        : '<p class="small dim">No commands yet. Say “what’s next” or type it in the box at the top.</p>');
  }
  function historyMini(st) {
    var rows = st.history.rows.slice(0, 8);
    return rows.length ? '<table class="t"><tbody>' + rows.map(function (r) {
      return '<tr><td class="mono">' + R.esc(R.dayLabel(r.date, "plain")) + "</td><td><b>" + R.esc(r.title) + '</b></td><td class="mono ' + (r.status === "failed" ? "bad" : "dim") + '">' + (r.status === "failed" ? "FAIL" : "SKIP") + '</td><td class="small">' + R.esc(r.reason) + "</td></tr>";
    }).join("") + "</tbody></table>" : '<p class="small dim">Nothing failed or skipped yet. Reasons will be kept here for good.</p>';
  }

  function today(st) {
    var sel = R.selectedTask();
    var plan = R.dayBar(st, { compact: true }) + planTable(st) + (sel ? '<div class="selbox"><p class="eyebrow">Selected</p>' + R.taskRow(sel, { keys: true }) + "</div>" : "") + R.overdueList(st);
    return '<div class="l5-grid">' +
      pane("plan", "Plan · " + R.esc(st.day.short), plan, null) +
      pane("goals", "Goals and fill-ins", goalsMini(st), "day") +
      pane("res", "Reschedule" + (st.proposals.length ? ' <span class="badge">' + st.proposals.length + " pending</span>" : ""), R.reschedulePage(st), "reschedule") +
      pane("voice", "Voice", voiceMini(st), "voice") +
      pane("hist", "Failed / skipped", historyMini(st), "history") + "</div>";
  }

  T.layouts[5] = {
    id: 5, defaultScreen: "today", today: today,
    frame: function (st, screen, inner) {
      if (screen === "today") return '<div class="l5">' + status(st) + inner + "</div>";
      return '<div class="l5">' + status(st) + '<div class="l5-max">' + pane("max", R.esc(T.screenTitle[screen] || screen), inner, null,
        '<a class="ph-max" href="#today" data-nav="today" aria-label="Back to all panes">' + I("split") + "</a>") + "</div></div>";
    }
  };
})();
