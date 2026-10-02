/* Shared pieces every layout composes. Layouts change arrangement and styling;
   the buttons, forms and wording come from here, so a fix lands everywhere.
   Every clickable thing carries data-act (an entry in actions.js), data-nav
   (a screen), or is a form submit (data-form names the action). */
(function () {
  var T = window.T, I = function (n, c) { return T.icon(n, c); };
  T.layouts = T.layouts || {};
  var DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function parse(iso) { var p = String(iso).split("-"); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function iso(d) { return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
  function addDays(isoDate, n) { var d = parse(isoDate); d.setDate(d.getDate() + n); return iso(d); }
  function dayLabel(isoDate, style) {
    if (!isoDate) return "";
    var d = parse(isoDate), st = T.state;
    if (style !== "plain" && st) {
      if (isoDate === st.today) return "Today";
      if (isoDate === st.tomorrow) return "Tomorrow";
      if (isoDate === addDays(st.today, -1)) return "Yesterday";
    }
    return DAYS[d.getDay()] + " " + d.getDate() + " " + MONTHS[d.getMonth()];
  }
  function toMin(hm) { var p = hm.split(":"); return +p[0] * 60 + +p[1]; }
  function fromMin(m) { return String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0"); }
  function dur(m) { var h = Math.floor(m / 60), r = m % 60; return h ? h + "h" + (r ? " " + r + "m" : "") : r + "m"; }

  /* a button bound to an action; args become data-args JSON */
  function btn(act, args, label, o) {
    o = o || {};
    return '<button type="button" class="btn' + (o.cls ? " " + o.cls : "") + '" data-act="' + act + '"' +
      (args ? " data-args='" + esc(JSON.stringify(args)) + "'" : "") +
      (o.title ? ' title="' + esc(o.title) + '"' : "") + (o.aria ? ' aria-label="' + esc(o.aria) + '"' : "") +
      (o.disabled ? " disabled" : "") + (o.pressed != null ? ' aria-pressed="' + o.pressed + '"' : "") + ">" +
      (o.icon ? I(o.icon) : "") + (label ? '<span class="btn-l">' + label + "</span>" : "") +
      (o.kbd ? '<kbd class="kbd">' + o.kbd + "</kbd>" : "") + "</button>";
  }
  function nav(screen, label, o) {
    o = o || {};
    return '<a href="#' + screen + '" data-nav="' + screen + '"' + (o.cls ? ' class="' + o.cls + '"' : "") + ">" +
      (o.icon ? I(o.icon) : "") + "<span>" + label + "</span>" + (o.badge ? '<b class="badge">' + o.badge + "</b>" : "") + "</a>";
  }
  function empty(text, action) {
    return '<div class="empty"><p>' + text + "</p>" + (action || "") + "</div>";
  }

  var KIND = {
    fixed: ["Fixed time", "anchor", "it has its own time; the planner and rescheduling never move it"],
    pinned: ["Pinned", "pin", "you moved it; re-planning won't move it"],
    auto: ["Auto-placed", "auto", "placed by the planner"],
    overflow: ["Didn't fit", "inbox", "no room in the day window"],
    untimed: ["No time yet", "clock", "Plan my day will place it"],
    timed: ["Fixed time", "anchor", "it has its own time; the planner and rescheduling never move it"]
  };
  function kind(t) { return KIND[t.placement] || KIND.untimed; }
  function kindBadge(t) {
    var k = kind(t);
    return '<span class="kind k-' + esc(t.placement) + '" title="' + esc(k[2]) + '">' + I(k[1]) + k[0] + "</span>";
  }
  /* a small "fixed time" marker for compact views (tiles, chips) */
  function fixedMark(t) {
    if (t.placement !== "fixed" && t.placement !== "timed") return "";
    return '<span class="fixedmark" title="Fixed time: it has its own time and never moves">' + I("anchor") + '<span class="sr">Fixed time</span></span>';
  }
  function statusBadge(t) {
    if (t.status === "pending") return t.running ? '<span class="st st-now">Now</span>' : "";
    return '<span class="st st-' + t.status + '">' + { done: "Done", failed: "Failed", skipped: "Skipped" }[t.status] + "</span>";
  }
  function prio(t) { return '<span class="prio p' + t.priority + '">P' + t.priority + " " + esc(t.priority_name) + "</span>"; }
  function when(t) {
    return t.start ? '<span class="tm">' + t.start + "–" + t.end + "</span>" : '<span class="tm tm-none">no time</span>';
  }
  function why(t) {
    if (t.status === "failed" || t.status === "skipped") {
      return '<p class="why why-closed"><b>' + (t.status === "failed" ? "Failed" : "Skipped") + ", because:</b> " + esc(t.fail_reason) + "</p>";
    }
    var text = t.reason || (t.placement === "fixed" ? (t.title_typed ? "fixed time, read from the title “" + t.title_typed + "”" : "fixed: you set this time") : t.start ? "" : "no time yet: Plan my day places it");
    return text ? '<p class="why"><b>Why here:</b> ' + esc(text) + "</p>" : "";
  }
  function goalChip(t) {
    return t.goal ? '<span class="goalchip" title="Linked goal">' + I("target") + esc(t.goal.title) + " <small>" + esc(t.goal.text) + "</small></span>" : "";
  }

  /* every action a task can take, shown on any layout */
  function taskActions(t, o) {
    o = o || {};
    var a = { id: t.id }, out = [];
    if (t.status === "pending") {
      out.push(btn("mark_done", a, "Done", { icon: "check", cls: "primary", kbd: o.keys ? "D" : null, aria: "Done: " + t.title }));
      out.push(btn("mark_failed", a, "Failed", { icon: "fail", kbd: o.keys ? "F" : null, aria: "Failed: " + t.title }));
      out.push(btn("mark_skipped", a, "Skip", { icon: "skip", kbd: o.keys ? "S" : null, aria: "Skip: " + t.title }));
      if (t.start && t.date === T.state.today && (t.running || t.past_end)) out.push(btn("extend_task", a, "Still going", { icon: "timer", kbd: o.keys ? "X" : null }));
      out.push(btn("move_task", a, t.start ? "Move" : "Set time", { icon: "clock", aria: "Move " + t.title }));
      if (t.placement === "pinned" || t.placement === "fixed") out.push(btn("unpin_task", a, "Unpin", { icon: "unlock", title: "Let the planner move it" }));
      else if (t.start) out.push(btn("pin_task", a, "Pin", { icon: "pin", title: "Keep it at this time" }));
      if (!o.short) {
        out.push(btn("link_task", a, t.goal ? "Goal" : "Link goal", { icon: "target" }));
        out.push(btn("edit_task", a, "Edit", { icon: "edit" }));
        if (t.title_typed) out.push(btn("keep_typed_title", a, "Keep title as typed", { icon: "undo", cls: "quiet", title: "Typed as “" + t.title_typed + "”. Puts that title back and drops the time read from it." }));
        out.push(btn("delete_task", a, "", { icon: "trash", aria: "Delete " + t.title, cls: "quiet" }));
      }
    } else if (t.status === "failed" || t.status === "skipped") {
      out.push(btn("reschedule_missed", a, "Reschedule", { icon: "reschedule" }));
    }
    return '<div class="actions">' + out.join("") + "</div>";
  }

  /* compact task row used by many layouts */
  function taskRow(t, o) {
    o = o || {};
    var sel = T.view.selected === t.id ? " is-sel" : "";
    return '<article class="task s-' + t.status + " k-" + esc(t.placement) + (t.running ? " is-now" : "") + sel + '" data-task="' + t.id + '">' +
      '<div class="task-top">' + when(t) + '<h3 class="task-title">' + esc(t.title) + "</h3>" + statusBadge(t) + "</div>" +
      '<div class="task-meta">' + kindBadge(t) + prio(t) + '<span class="dur">' + t.duration_text + "</span>" + goalChip(t) + "</div>" +
      why(t) + (o.noActions ? "" : taskActions(t, o)) + "</article>";
  }

  function selectedTask() {
    var st = T.state; if (!st) return null;
    var all = st.day.tasks.concat(st.day.untimed, (st.today_view ? st.today_view.tasks.concat(st.today_view.untimed) : []), st.overflow);
    var hit = all.filter(function (t) { return t.id === T.view.selected; })[0];
    if (hit) return hit;
    var today = st.today_view || st.day;
    return today.tasks.filter(function (t) { return t.running; })[0] ||
      today.tasks.filter(function (t) { return t.status === "pending"; })[0] ||
      today.untimed.filter(function (t) { return t.status === "pending"; })[0] || null;
  }
  function nowAndNext() {
    var st = T.state, today = st.today_view || st.day;
    var now = today.tasks.filter(function (t) { return t.running; })[0] || null;
    var nowMin = toMin(st.now.slice(11, 16));
    var next = today.tasks.filter(function (t) { return t.status === "pending" && !t.running && toMin(t.start) >= nowMin; });
    return { now: now, next: next, today: today };
  }

  /* ---------- day header: navigation + day actions ---------- */
  function dayBar(st, o) {
    o = o || {};
    var d = st.day;
    return '<div class="daybar">' +
      '<div class="daybar-nav">' + btn("day_shift", { n: -1 }, "", { icon: "chev-left", aria: "Previous day" }) +
      '<label class="sr" for="day-pick">Day</label><input type="date" id="day-pick" data-act="day_pick" value="' + d.date + '">' +
      btn("day_shift", { n: 1 }, "", { icon: "chev-right", aria: "Next day" }) +
      (d.is_today ? "" : btn("day_today", null, "Today", {})) + "</div>" +
      '<div class="daybar-act">' +
      btn("plan_day", { date: d.date }, d.tasks.some(function (t) { return t.placement === "auto"; }) ? "Re-plan" : "Plan my day",
        { icon: "auto", kbd: "P", disabled: d.is_past, title: d.is_past ? "Past days never change" : "Places movable tasks; fixed and pinned stay" }) +
      btn("add_task", { date: d.date }, "Add task", { icon: "plus", cls: "primary", kbd: "A" }) +
      (o.compact ? "" : btn("add_several", { date: d.date }, "Add several", { icon: "list" }) +
        btn("clear_day", { date: d.date }, "Clear day", { icon: "trash", cls: "quiet", disabled: d.is_past })) +
      "</div></div>";
  }
  function dayStats(d) {
    var c = d.counts;
    return '<dl class="stats"><div><dt>Planned</dt><dd>' + (d.tasks.length + d.untimed.length) + "</dd></div><div><dt>Done</dt><dd>" + c.done +
      "</dd></div><div><dt>Failed / skipped</dt><dd>" + (c.failed + c.skipped) + "</dd></div><div><dt>No time</dt><dd>" + d.untimed.length +
      "</dd></div><div><dt>Free time left</dt><dd>" + dur(d.free_minutes) + "</dd></div></dl>";
  }
  function untimedList(st, o) {
    var list = st.day.untimed;
    if (!list.length) return o && o.quiet ? "" : '<p class="muted small">Everything on this day has a time.</p>';
    return '<ul class="untimed">' + list.map(function (t) { return "<li>" + taskRow(t, { short: true }) + "</li>"; }).join("") + "</ul>";
  }
  function overdueList(st) {
    if (!st.overdue.length) return "";
    return '<section class="panel overdue"><h2 class="panel-h">' + I("alert") + "Still open from earlier days</h2>" +
      st.overdue.map(function (t) { return taskRow(t, { short: true }); }).join("") + "</section>";
  }

  /* ---------- reschedule proposals ---------- */
  function moveLine(m) {
    var from = m.from_start ? dayLabel(m.from_day) + " " + m.from_start : (m.from_day ? dayLabel(m.from_day) + ", no time" : "no time");
    var to = m.kind === "extend" ? "until " + m.to_end : dayLabel(m.to_day) + " " + m.to_start + "–" + m.to_end;
    if (m.kind === "claim") to = dayLabel(m.to_day) + " " + m.to_start + "–" + m.to_end;
    return '<li class="mv mv-' + m.kind + '"><span class="mv-kind">' + { copy: "New copy", shift: "Move", extend: "Extend", claim: "Fixed time" }[m.kind] + "</span>" +
      '<div><p class="mv-title">' + esc(m.title) + ' <small class="prio p' + m.priority + '">P' + m.priority + "</small></p>" +
      '<p class="mv-path"><s>' + esc(from) + "</s>" + I("arrow-right") + "<b>" + esc(to) + "</b></p>" +
      '<p class="why"><b>Why:</b> ' + esc(m.reason) + "</p></div></li>";
  }
  function proposalCard(p) {
    var body = "";
    if (p.cap_reached) {
      body = '<p class="ask">This task has now been rescheduled ' + p.chain_count + " times (limit " + p.max_reschedules + "). What now?</p>" +
        '<div class="actions">' + btn("cap_answer", { id: p.id, choice: "keep" }, "Keep rescheduling") +
        btn("cap_answer", { id: p.id, choice: "split" }, "Split in two") + btn("cap_answer", { id: p.id, choice: "drop" }, "Drop it", { cls: "quiet" }) + "</div>";
    } else if (p.collisions.length) {
      var c = p.collisions[0];
      body = '<p class="ask warn">Running until ' + p.requested_end + " would run into <b>" + esc(c.title) + "</b> at " + c.start + " (" + esc(c.placement) +
        ", it won't move).</p><div class=\"actions\">" + btn("collision_answer", { id: p.id, choice: "shorten" }, "Shorten to end at " + c.start) +
        btn("collision_answer", { id: p.id, choice: "continue" }, "Move the rest after it") +
        btn("collision_answer", { id: p.id, choice: "leave" }, "Leave it, I'll sort it out", { cls: "quiet" }) + "</div>";
    } else {
      body = (p.moves.length ? '<ol class="moves">' + p.moves.map(moveLine).join("") + "</ol>" : '<p class="muted">Nothing needs to move.</p>') +
        (p.unplaced.length ? '<p class="unplaced"><b>Unplaced (no room today or tomorrow):</b> ' + p.unplaced.map(function (m) { return esc(m.title) + " (" + m.duration_text + ")"; }).join(", ") + "</p>" : "") +
        '<div class="actions">' + btn("proposal_answer", { id: p.id, answer: "accept" }, "Accept", { icon: "check", cls: "primary", disabled: p.empty }) +
        btn("proposal_answer", { id: p.id, answer: "reject" }, "Reject", { icon: "x" }) + "</div>" +
        '<p class="muted small">Nothing changes until you accept. Fixed and pinned tasks never move, and nothing goes past tomorrow. Voice: “accept”, “reject”.</p>';
    }
    return '<section class="proposal" data-proposal="' + p.id + '"><p class="eyebrow">Reschedule proposal</p><h3>' + esc(p.title) + " " +
      { failed: "failed", skipped: "was skipped", overrun: "is running over", claim: "takes its own time" }[p.trigger] + "</h3>" + body + "</section>";
  }
  function reschedulePage(st) {
    var parts = st.proposals.map(proposalCard).join("");
    var undo = st.last_reschedule ? '<div class="panel"><p>Last accepted reschedule: ' + esc(st.last_reschedule.trigger) + " at " + st.last_reschedule.at + ".</p>" +
      btn("undo_reschedule", null, "Undo the last reschedule", { icon: "undo" }) + "</div>" : "";
    var missed = st.day.tasks.concat(st.day.untimed).filter(function (t) { return t.status === "failed" || t.status === "skipped"; });
    return (parts || empty("No reschedule proposals right now. When a task fails, is skipped or runs over, a proposal appears here; nothing moves until you accept it.")) +
      undo + (missed.length ? '<section class="panel"><h2 class="panel-h">Failed or skipped on ' + esc(st.day.short) + "</h2>" + missed.map(function (t) { return taskRow(t, { short: true }); }).join("") + "</section>" : "");
  }

  /* ---------- check-ins, alarms, reminders (banners) ---------- */
  function checkins(st) {
    return st.alarms.checkins.map(function (c) {
      return '<div class="banner checkin" role="status">' + I("clock") + "<span>" + esc(c.message) + "</span>" +
        btn("mark_done", { id: c.task_id }, "Done") + btn("extend_task", { id: c.task_id }, "Still going") +
        btn("mark_failed", { id: c.task_id }, "Failed") + btn("mark_skipped", { id: c.task_id }, "Skipped") +
        btn("checkin_answer", { id: c.task_id, answer: "later" }, "Later", { cls: "quiet" }) + "</div>";
    }).join("");
  }

  /* ---------- period pages ---------- */
  function lockLine(p) {
    if (p.locked) {
      return '<div class="lock l-' + (p.review_locked ? "locked" : "review") + '">' + I("lock") + "<span><b>Read-only:</b> this " + p.kind +
        " ended, so goals, sacrifices, process and progress can't change. " + (p.review_locked ? "The review closed at the end of " + dayLabel(p.review_cutoff, "plain") + "."
        : "The review is open until the end of " + dayLabel(p.review_cutoff) + ".") + "</span></div>";
    }
    return '<div class="lock l-open">' + I("unlock") + "<span>" + (p.future ? "Planned ahead. " : "Open. ") + "Ends " + dayLabel(p.end, "plain") +
      " at midnight; the review stays open until the end of " + dayLabel(p.review_cutoff, "plain") + ".</span></div>";
  }
  function goalCard(g, p) {
    var bar = g.target != null ? '<span class="bar" role="progressbar" aria-valuenow="' + Math.round(g.fraction * 100) + '" aria-valuemin="0" aria-valuemax="100"><span style="width:' + Math.min(100, g.fraction * 100) + '%"></span></span>' : "";
    var roll = g.ancestors.length ? '<p class="rolls">Rolls up: ' + g.ancestors.map(function (a) { return esc(a.title) + " <b>" + esc(a.text) + "</b> (" + a.kind + ")"; }).join(" → ") + "</p>" : "";
    var kids = g.children.length ? '<p class="kids">From: ' + g.children.map(function (c) { return esc(c.period) + " <b>" + (c.logged != null ? c.logged : "") + "</b>"; }).join(" · ") +
      (g.own_logged ? " · logged here <b>" + g.own_logged + "</b>" : "") + "</p>" : "";
    var logs = g.logs.length ? '<details class="logs"><summary>' + g.logs.length + " log" + (g.logs.length > 1 ? "s" : "") + "</summary><ul>" +
      g.logs.map(function (l) { return "<li>" + dayLabel(l.date, "plain") + ": <b>" + l.amount + "</b> " + esc(g.unit || "") + (l.task_id ? " (from a task)" : "") +
        (p.locked ? "" : btn("remove_log", { log_id: l.id }, "", { icon: "x", cls: "quiet tiny", aria: "Remove this log" })) + "</li>"; }).join("") + "</ul></details>" : "";
    var acts = p.locked ? "" : '<div class="actions">' +
      (g.target != null ? btn("log_progress", { goal_id: g.id, unit: g.unit, start: p.start, end: p.end }, "Log progress", { icon: "plus", cls: "primary" })
        : btn("goal_done", { id: g.id, done: !g.done }, g.done ? "Mark not done" : "Mark done", { icon: "check", cls: g.done ? "" : "primary" })) +
      btn("edit_goal", { id: g.id }, "Edit", { icon: "edit" }) + btn("delete_goal", { id: g.id }, "", { icon: "trash", cls: "quiet", aria: "Delete goal " + g.title }) + "</div>";
    return '<li class="goal' + (g.done ? " is-done" : "") + '"><div class="goal-top"><h3>' + esc(g.title) + '</h3><span class="goal-num">' + esc(g.text) + "</span></div>" +
      bar + roll + kids + logs + (g.task_count ? '<p class="muted small">' + g.task_count + " linked task" + (g.task_count > 1 ? "s" : "") + "</p>" : "") + acts + "</li>";
  }
  function weekStrip(p) {
    if (p.kind !== "week") return "";
    var rows = p.goals.filter(function (g) { return g.children.length; });
    if (!rows.length) return "";
    return '<table class="weekstrip"><caption class="sr">Per day</caption><thead><tr><th scope="col">Goal</th>' +
      p.days.map(function (d) { return '<th scope="col"' + (d === T.state.today ? ' class="is-today"' : "") + ">" + dayLabel(d, "plain").slice(0, 3) + "</th>"; }).join("") +
      "</tr></thead><tbody>" + rows.map(function (g) {
        return "<tr><th scope=\"row\">" + esc(g.title) + "</th>" + p.days.map(function (d) {
          var c = g.children.filter(function (x) { return x.start === d; })[0];
          return '<td' + (d === T.state.today ? ' class="is-today"' : "") + ">" + (c ? c.logged : "·") + "</td>";
        }).join("") + "</tr>";
      }).join("") + "</tbody></table>";
  }
  function sacrifices(p) {
    function list(status) {
      var items = p.sacrifices.filter(function (x) { return x.status === status; });
      if (!items.length) return '<li class="muted small">None ' + status + ".</li>";
      return items.map(function (x) {
        return '<li class="sac sac-' + status + '"><span>' + esc(x.text) + "</span>" + (p.locked ? "" :
          (status === "planned" ? btn("made_sacrifice", { id: x.id }, "Made", { cls: "tiny", title: "Mark as made" }) : "") +
          btn("remove_sacrifice", { id: x.id }, "", { icon: "trash", cls: "tiny quiet", aria: "Delete sacrifice", title: "Delete (Undo brings it back)" })) + "</li>";
      }).join("");
    }
    var add = p.locked ? "" : '<form class="inline-form" data-form="add_sacrifice"><input type="hidden" name="kind" value="' + p.kind + '"><input type="hidden" name="start" value="' + p.start + '">' +
      '<label class="sr" for="sac-' + p.kind + '">New sacrifice</label><input id="sac-' + p.kind + '" name="text" data-keep placeholder="Add a sacrifice" required maxlength="300">' +
      '<select name="status" aria-label="Planned or made"><option value="planned">planned</option><option value="made">made</option></select><button type="submit" class="btn">' + I("plus") + "Add</button></form>";
    return '<div class="sacs"><div><h4>Planned</h4><ul>' + list("planned") + '</ul></div><div><h4>Made</h4><ul>' + list("made") + "</ul></div></div>" + add;
  }
  function periodPage(kind, st, o) {
    o = o || {};
    var p = st.periods[kind];
    var title = kind === "day" ? dayLabel(p.start) : kind === "week" ? (p.current ? "This week" : "Week") : p.label;
    var head = '<header class="period-h"><div><p class="eyebrow">' + kind + '</p><h2 class="screen-title">' + esc(title) + '</h2><p class="muted">' + esc(p.label) + "</p></div>" +
      '<div class="pager">' + btn("period_shift", { kind: kind, to: p.prev }, "", { icon: "chev-left", aria: "Previous " + kind }) +
      btn("period_shift", { kind: kind, to: null }, "Current", { disabled: p.current }) +
      btn("period_shift", { kind: kind, to: p.next }, "", { icon: "chev-right", aria: "Next " + kind }) + "</div></header>";
    var tabs = o.tabs === false ? "" : '<nav class="ptabs" aria-label="Period">' + ["day", "week", "month"].map(function (k) {
      return '<a href="#' + k + '" data-nav="' + k + '"' + (k === kind ? ' aria-current="page"' : "") + ">" + k[0].toUpperCase() + k.slice(1) + "</a>"; }).join("") + "</nav>";
    var goals = p.goals.length ? '<ul class="goals">' + p.goals.map(function (g) { return goalCard(g, p); }).join("") + "</ul>"
      : empty("No goals for this " + kind + " yet. Every day, week and month needs one; goals live only on these pages, and tasks can link to them.", p.locked ? "" : "");
    var addGoal = p.locked ? "" : btn("new_goal", { kind: kind, start: p.start }, "New " + kind + " goal", { icon: "plus", cls: "primary" });
    var procMissing = !p.process && !p.locked ? ' <span class="missing">' + I("alert") + "missing</span>" : "";
    var proc = '<label class="field-l" for="proc-' + kind + '">Process' + procMissing + '</label><textarea id="proc-' + kind + '" rows="3" data-keep data-autosave="set_process" data-kind="' + kind + '" data-start="' + p.start + '"' +
      (p.locked ? " readonly" : "") + ' placeholder="How you will get there">' + esc(p.process || "") + "</textarea>";
    var rev = '<label class="field-l" for="rev-' + kind + '">Review <span class="cut">' + (p.review_locked ? "closed" : "open until end of " + dayLabel(p.review_cutoff, "plain")) + '</span></label><textarea id="rev-' + kind + '" rows="4" data-keep data-autosave="write_review" data-kind="' + kind + '" data-start="' + p.start + '"' +
      (p.review_locked || p.future ? " readonly" : "") + ' placeholder="' + (p.future ? "Opens when the " + kind + " starts" : "What went well, what didn't") + '">' + esc(p.review || "") + "</textarea>";
    return '<div class="period period-' + kind + '">' + tabs + head + lockLine(p) +
      '<div class="period-grid"><section class="pg-goals"><h3 class="sec-h">Goals</h3>' + goals + addGoal + weekStrip(p) + "</section>" +
      '<section class="pg-notes"><h3 class="sec-h">Sacrifices</h3>' + sacrifices(p) + '<div class="autosave">' + proc + '<p class="save-note" data-note-for="proc-' + kind + '"></p></div>' +
      '<div class="autosave">' + rev + '<p class="save-note" data-note-for="rev-' + kind + '"></p></div></section></div></div>';
  }

  /* ---------- history ---------- */
  function historyPage(st) {
    var h = st.history, f = T.view.history;
    var gopts = '<option value="">All goals</option>' + h.goals.map(function (g) { return '<option value="' + g.id + '"' + (String(f.goal) === String(g.id) ? " selected" : "") + ">" + esc(g.title) + "</option>"; }).join("") +
      '<option value="none"' + (f.goal === "none" ? " selected" : "") + ">No goal</option>";
    var filters = '<form class="filters" data-form="history_filter"><label>Goal <select name="goal">' + gopts + "</select></label>" +
      '<label>From <input type="date" name="from" value="' + esc(f.from || "") + '"></label><label>To <input type="date" name="to" value="' + esc(f.to || "") + '"></label>' +
      '<label>Status <select name="status"><option value="">Failed and skipped</option><option value="failed"' + (f.status === "failed" ? " selected" : "") + '>Failed</option><option value="skipped"' + (f.status === "skipped" ? " selected" : "") + ">Skipped</option></select></label>" +
      '<button type="submit" class="btn">' + I("filter") + "Apply</button>" + btn("history_clear", null, "Clear", { cls: "quiet" }) + '<span class="muted small">' + h.rows.length + " of " + h.total + "</span></form>";
    var rows = h.rows.map(function (r) {
      var copies = r.copies.length ? r.copies.map(function (c) { return "copy on " + dayLabel(c.date, "plain") + (c.start ? " " + c.start : ", unplaced") + " (" + c.status + ")"; }).join("; ") : "not rescheduled";
      return '<li class="hrow"><span class="st st-' + r.status + '">' + (r.status === "failed" ? "Failed" : "Skipped") + "</span><div><p><b>" + esc(r.title) + '</b> <span class="muted">' + dayLabel(r.date, "plain") +
        (r.goal_title ? " · " + esc(r.goal_title) : "") + '</span></p><p class="hreason">“' + esc(r.reason) + '”</p><p class="muted small">' + I("reschedule") + esc(copies) + "</p>" +
        (r.task_status === "failed" || r.task_status === "skipped" ? btn("reschedule_missed", { id: r.task_id }, "Reschedule", { icon: "reschedule", cls: "tiny" }) : "") + "</div></li>";
    }).join("");
    return '<h2 class="screen-title">Failed and skipped</h2><p class="muted">Every failed or skipped task with the reason given. Reasons are permanent.</p>' + filters +
      (h.total ? (rows ? '<ol class="hlist">' + rows + "</ol>" : empty("Nothing matches these filters.", btn("history_clear", null, "Clear filters")))
        : empty("Nothing has failed or been skipped yet. When a task fails or is skipped, its reason is kept here for good.", btn("add_task", { date: st.today }, "Add a task", { icon: "plus" })));
  }

  /* ---------- voice ---------- */
  function voicePage(st, o) {
    o = o || {};
    var v = st.voice;
    var stt = v.stt.available ? '<p class="ok small">' + I("check") + "Speech recognition is ready (model “" + esc(v.stt.model || st.settings.stt_model) + "”, on this computer).</p>"
      : '<p class="warn small">' + I("alert") + esc(v.stt.reason || "Speech recognition isn't ready.") + "</p>";
    var log = v.log.length ? '<ol class="vlog">' + v.log.map(function (l) {
      var low = l.confidence != null && l.confidence < v.low_confidence;
      return '<li class="' + (l.acted ? "acted" : "noact") + '"><span class="vt">' + esc((l.at || "").slice(11, 16)) + '</span><div><p class="vheard">“' + esc(l.text) + '” <span class="conf' + (low ? " low" : "") + '">' +
        (l.confidence != null ? Math.round(l.confidence * 100) + "%" : "typed") + '</span></p><p class="vcmd">' + (l.interpreted ? I("arrow-right") + esc(l.interpreted) : I("minus") + "No command") + '</p><p class="muted small">' + esc(l.result || "") + "</p></div></li>";
    }).join("") + "</ol>" : empty("No voice or typed commands yet. Press V (or the mic) and say “plan my day”, or type it in the box at the top.");
    var phr = '<div class="phrases">' + v.phrases.map(function (c) { return '<div><h4>' + esc(c.summary) + (c.risky ? ' <span class="muted small">(asks for a spoken yes)</span>' : "") + "</h4><p>" + c.examples.map(function (e) { return "“" + esc(e) + "”"; }).join(" · ") + "</p></div>"; }).join("") + "</div>";
    return '<h2 class="screen-title">Voice</h2><p class="muted">Everything you can click, you can say or type. Speech stays on this computer.</p>' + stt +
      '<div class="voice-grid"><section class="panel vstage"><button type="button" class="mic-big" data-act="mic_toggle" aria-pressed="false">' + I("mic") + '</button><div><p class="vphase" data-mic-phase>Ready</p>' +
      '<p class="muted small">Hold <kbd>V</kbd> to talk, or click the mic to start and stop.' + (st.settings.muted ? " The mic is muted." : "") + "</p></div>" +
      '<div class="meter" data-level aria-hidden="true"><span></span></div></section>' +
      '<section class="panel vtest"><h3 class="panel-h">' + I("volume") + 'Mic test</h3><p class="small">Speak normally: the bar should reach the middle. Then you’ll see what was understood.</p>' +
      '<label class="field-l" for="mic-select">Microphone</label><select id="mic-select" data-act="input_device"><option value="">Default microphone</option></select>' +
      '<div class="meter wide" data-level aria-hidden="true"><span></span><i></i></div><p class="small" data-mictest-result></p>' +
      btn("run_mic_test", null, "Start mic test", { icon: "play" }) + "</section>" +
      '<section class="panel vlogp"><h3 class="panel-h">' + I("list") + "Transcript log</h3>" + log + "</section>" +
      '<section class="panel"><h3 class="panel-h">' + I("help") + "What you can say</h3>" + phr + "</section></div>";
  }

  /* ---------- settings ---------- */
  function settingsPage(st) {
    var s = st.settings, ui = st.ui;
    var models = ["tiny", "base", "small", "medium", "large-v3-turbo"];
    return '<h2 class="screen-title">Settings</h2><p class="muted">Changes save as soon as you make them.</p><div class="settings">' +
      '<form class="panel" data-form="settings"><h3 class="panel-h">Day</h3><div class="row"><label for="s-ws">Day window starts</label><input id="s-ws" type="time" name="day_start" value="' + s.day_start + '" data-autosubmit></div>' +
      '<div class="row"><label for="s-we">Day window ends</label><input id="s-we" type="time" name="day_end" value="' + s.day_end + '" data-autosubmit></div>' +
      '<p class="muted small">Plan my day only places tasks inside this window. Fixed tasks outside it stay.</p>' +
      '<div class="row"><label for="s-dl">Length of a task whose title gives one time (minutes)</label><input id="s-dl" type="number" min="5" max="600" name="default_task_minutes" value="' + s.default_task_minutes + '" data-autosubmit></div>' +
      '<p class="muted small">A range in the title sets the length itself; a duration you type always wins.</p>' +
      '<h3 class="panel-h">Alarms</h3><div class="row"><label for="s-sn">Snooze length (minutes)</label><input id="s-sn" type="number" min="1" max="120" name="snooze_minutes" value="' + s.snooze_minutes + '" data-autosubmit></div>' +
      '<p class="muted small">Alarms ring in this browser tab while tomits is running, once per task; Snooze rings again after this many minutes.</p>' +
      '<div class="row">' + btn("enable_sound", null, "Test alarm sound", { icon: "volume" }) + btn("enable_notifications", null, "Allow desktop notifications", { icon: "bell" }) + '</div><p class="small" data-permission-note></p></form>' +
      '<div class="panel"><h3 class="panel-h">Your data</h3><p class="muted small">An export is one file with everything: tasks, reasons, goals, pages, sacrifices and notes. Importing one replaces all your data; your current data is backed up first.</p>' +
      '<div class="row">' + btn("export_data", null, "Export all data", { icon: "arrow-right" }) + "</div>" +
      '<form class="row" data-form="import_data"><label for="s-imp">Import an export</label><input id="s-imp" type="file" accept=".json,application/json" required><button type="submit" class="btn">Import…</button><p class="form-err" role="alert" hidden></p></form></div>' +
      '<form class="panel" data-form="voice_settings"><h3 class="panel-h">Voice</h3>' +
      '<div class="row"><label for="s-spk">Speak replies out loud</label><input id="s-spk" type="checkbox" name="spoken_replies"' + (s.spoken_replies ? " checked" : "") + ' data-autosubmit></div>' +
      '<div class="row"><label for="s-stt">Speech model (local)</label><select id="s-stt" name="stt_model" data-autosubmit>' + models.map(function (m) { return "<option" + (m === s.stt_model ? " selected" : "") + ">" + m + "</option>"; }).join("") + "</select></div>" +
      '<div class="row"><label for="s-llm">Understand rephrased commands (local language model, if installed)</label><input id="s-llm" type="checkbox" name="llm_enabled"' + (s.llm_enabled ? " checked" : "") + ' data-autosubmit></div>' +
      '<div class="row"><label for="s-wake">Wake phrase (terminal hands-free mode)</label><input id="s-wake" name="wake_phrase" value="' + esc(s.wake_phrase) + '" data-autosubmit></div>' +
      '<p class="muted small">Below ' + Math.round(st.voice.low_confidence * 100) + '% confidence nothing happens; deletes always need a spoken “yes”.</p>' +
      '<div class="row">' + btn("mute", { muted: !s.muted }, s.muted ? "Unmute the mic" : "Mute the mic", { icon: s.muted ? "mic" : "mic-off" }) + btn("nav_voice", null, "Mic test", { icon: "wave" }) + "</div></form>" +
      '<div class="panel"><h3 class="panel-h">Look</h3><div class="row"><span>Theme</span><span class="seg">' + ["system", "light", "dark"].map(function (t) {
        return btn("set_theme", { theme: t }, t[0].toUpperCase() + t.slice(1), { pressed: ui.theme === t }); }).join("") + "</span></div>" +
      '<div class="row"><span>Layout</span>' + btn("open_layouts", null, ui.layouts[ui.layout - 1].name + " · change", { icon: "layers", kbd: "L" }) + "</div>" +
      '<div class="row"><span>First-run setup</span>' + btn("open_setup", null, "Run it again", {}) + "</div></div>" +
      '<div class="panel danger-zone"><h3 class="panel-h">' + I("alert") + "Delete</h3><p class=\"small\">Deletes only what the rules allow: failed and skipped records (their reasons), done tasks and goals of ended periods are kept. You'll see exactly what goes before anything happens.</p>" +
      '<div class="row">' + btn("delete_all", { scope: "tasks" }, "Delete all pending tasks", { cls: "quiet" }) + btn("delete_all", { scope: "goals" }, "Delete all goals", { cls: "quiet" }) +
      btn("delete_all", { scope: "tasks and goals" }, "Delete tasks and goals", { cls: "danger" }) + "</div></div></div>";
  }

  function focusPage() {
    return '<h2 class="screen-title">Focus and pomodoro</h2><div class="later-box"><span class="tag">Coming in version 2.0</span>' +
      "<p>Not built yet. Planned: a pomodoro timer tied to the current task, blocking distracting sites and apps during focus, and breaks that respect your day window.</p>" +
      btn("nav_today", null, "Back to today", { icon: "today" }) + "</div>";
  }

  function layoutsPage(st) {
    var cur = st.ui.layout;
    return '<h2 class="screen-title">Choose a layout</h2><p class="muted">All six show every screen and every action; they differ in arrangement and look. Your choice is remembered.</p>' +
      '<ol class="layout-list">' + st.ui.layouts.map(function (l) {
        return '<li class="' + (l.id === cur ? "is-current" : "") + '"><button type="button" class="layout-pick" data-act="switch_layout" data-args=\'{"layout":' + l.id + "}'" + (l.id === cur ? ' aria-current="true"' : "") + ">" +
          '<span class="lp-n">' + l.id + '</span><span class="lp-body"><b>' + esc(l.name) + "</b><span>" + esc(l.description) + "</span></span>" + (l.id === cur ? '<span class="lp-cur">' + I("check") + "In use</span>" : "") + "</button></li>";
      }).join("") + "</ol>";
  }

  T.r = {
    esc: esc, parse: parse, iso: iso, addDays: addDays, dayLabel: dayLabel, toMin: toMin, fromMin: fromMin, dur: dur,
    btn: btn, nav: nav, empty: empty, kind: kind, kindBadge: kindBadge, fixedMark: fixedMark, statusBadge: statusBadge, prio: prio, when: when, why: why,
    goalChip: goalChip, taskActions: taskActions, taskRow: taskRow, selectedTask: selectedTask, nowAndNext: nowAndNext,
    dayBar: dayBar, dayStats: dayStats, untimedList: untimedList, overdueList: overdueList, proposalCard: proposalCard,
    reschedulePage: reschedulePage, checkins: checkins, periodPage: periodPage, goalCard: goalCard, historyPage: historyPage,
    voicePage: voicePage, settingsPage: settingsPage, focusPage: focusPage, layoutsPage: layoutsPage, lockLine: lockLine
  };
})();
