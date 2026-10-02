/* Dialogs and forms. A form's data-form names the action it runs; on a refusal
   the logic layer's reason appears inside the form and your input stays. */
(function () {
  var T = window.T, R = function () { return T.r; }, I = function (n) { return T.icon(n); };
  var esc = function (s) { return T.r.esc(s); };

  /* ---------- finding things in the current state ---------- */
  T.findTask = function (id) {
    var st = T.state; if (!st) return null;
    var lists = [st.day.tasks, st.day.untimed, st.overflow, st.overdue];
    if (st.today_view) lists.push(st.today_view.tasks, st.today_view.untimed);
    st.week.days.forEach(function (d) { lists.push(d.tasks, d.untimed); });
    for (var i = 0; i < lists.length; i++) {
      var hit = lists[i].filter(function (t) { return t.id === +id; })[0];
      if (hit) return hit;
    }
    return null;
  };
  T.findGoal = function (id) {
    var st = T.state; if (!st) return null;
    for (var k in st.periods) {
      var hit = st.periods[k].goals.filter(function (g) { return g.id === +id; })[0];
      if (hit) return hit;
    }
    return null;
  };

  /* ---------- the dialog ---------- */
  var dlg;
  T.dlg = {
    open: function (title, body, o) {
      o = o || {};
      dlg = dlg || document.getElementById("dlg");
      dlg.className = "dlg" + (o.cls ? " " + o.cls : "");
      dlg.innerHTML = '<div class="dlg-head"><h2 id="dlg-title">' + title + '</h2><button type="button" class="btn quiet" data-close aria-label="Close">' + I("x") + "</button></div>" + body;
      T.hydrateIcons(dlg);
      if (!dlg.open) dlg.showModal();
      var first = dlg.querySelector("[autofocus], textarea, input:not([type=hidden]), select, button[type=submit]");
      if (first) first.focus();
      if (o.onOpen) o.onOpen(dlg);
      return dlg;
    },
    close: function () { if (dlg && dlg.open) dlg.close(); },
    isOpen: function () { return !!(dlg && dlg.open); }
  };
  document.addEventListener("click", function (e) {
    var c = e.target.closest && e.target.closest("[data-close]");
    if (c) { var d = c.closest("dialog"); if (d) d.close(); }
  });

  function hidden(name, value) { return value == null ? "" : '<input type="hidden" name="' + name + '" value="' + esc(value) + '">'; }
  function err() { return '<p class="form-err" role="alert" hidden></p>'; }
  function foot(label, o) {
    o = o || {};
    return '<div class="dlg-foot"><button type="button" class="btn" data-close>' + (o.cancel || "Cancel") + '</button><button type="submit" class="btn ' + (o.danger ? "danger" : "primary") + '">' + label + "</button></div>";
  }
  function goalOptions(selected, allowNone) {
    var goals = (T.state && T.state.open_goals) || [];
    return (allowNone ? '<option value="">No goal</option>' : "") + goals.map(function (g) {
      return '<option value="' + g.id + '"' + (+selected === g.id ? " selected" : "") + ">" + esc(g.title) + " (" + esc(g.period) + ", " + esc(g.text) + ")</option>";
    }).join("");
  }
  function prioOptions(p) {
    return [[1, "1 urgent"], [2, "2 high"], [3, "3 normal"], [4, "4 low"]].map(function (x) {
      return '<option value="' + x[0] + '"' + (+p === x[0] ? " selected" : "") + ">" + x[1] + "</option>"; }).join("");
  }

  T.forms = {
    task: function (task, defaults) {
      defaults = defaults || {};
      var t = task || {};
      var edit = !!task;
      var body = '<form data-form="' + (edit ? "edit_task" : "add_task") + '" class="form">' + hidden("id", t.id) +
        '<label class="field-l" for="f-title">Title</label><input id="f-title" name="title" required maxlength="200" value="' + esc(t.title || "") + '" autofocus aria-describedby="f-title-h">' +
        '<p class="hint" id="f-title-h">A clear time in the title (with am or pm, 24-hour, after “at”, or a range) becomes the task’s fixed time and is taken out of the title.</p>' +
        '<div class="cols"><div><label class="field-l" for="f-dur">Duration</label><input id="f-dur" name="duration" value="' + esc(t.duration || "") + '" aria-describedby="f-dur-h"><p class="hint" id="f-dur-h">Minutes, or like 1h30m. Optional when the title has a time.</p></div>' +
        '<div><label class="field-l" for="f-pri">Priority</label><select id="f-pri" name="priority">' + prioOptions(t.priority || 3) + "</select></div></div>" +
        (edit ? "" : '<div class="cols"><div><label class="field-l" for="f-date">Day</label><input id="f-date" type="date" name="date" value="' + esc(defaults.date || T.state.today) + '" min="' + T.state.today + '"></div>' +
          '<div><label class="field-l" for="f-start">Start time (optional)</label><input id="f-start" type="time" name="start" aria-describedby="f-start-h"><p class="hint" id="f-start-h">With a time it’s fixed; without one, Plan my day places it.</p></div></div>' +
          '<label class="field-l" for="f-goal">Goal (optional)</label><select id="f-goal" name="goal_id">' + goalOptions(null, true) + "</select>") +
        '<label class="field-l" for="f-purpose">What does done look like? (optional)</label><input id="f-purpose" name="purpose" maxlength="500" value="' + esc(t.purpose || "") + '">' +
        err() + foot(edit ? "Save changes" : "Add task") + "</form>";
      T.dlg.open(edit ? "Edit task" : "Add a task", body);
    },
    several: function (date) {
      var row = function (i) {
        return '<div class="sev-row"><label class="sr" for="sv-t' + i + '">Title ' + (i + 1) + '</label><input id="sv-t' + i + '" name="title_' + i + '" maxlength="200" placeholder="Title">' +
          '<label class="sr" for="sv-d' + i + '">Duration</label><input id="sv-d' + i + '" name="duration_' + i + '" placeholder="Duration" size="8">' +
          '<label class="sr" for="sv-p' + i + '">Priority</label><select id="sv-p' + i + '" name="priority_' + i + '">' + prioOptions(3) + "</select></div>";
      };
      var rows = ""; for (var i = 0; i < 6; i++) rows += row(i);
      T.dlg.open("Add several tasks", '<form data-form="add_several" class="form"><div class="cols"><div><label class="field-l" for="sv-date">Day</label><input id="sv-date" type="date" name="date" value="' + esc(date || T.state.today) + '" min="' + T.state.today + '"></div>' +
        '<div><label class="field-l" for="sv-start">Start the first at (optional)</label><input id="sv-start" type="time" name="start"></div></div>' +
        '<p class="hint">Blank rows are ignored. All or nothing: if one line is invalid, nothing is saved. A clear time in a title gives that task its time (its duration is then optional); Plan my day places the rest.</p>' + rows + err() + foot("Add tasks") + "</form>");
    },
    move: function (t) {
      var st = T.state;
      var others = (t.date === st.day.date ? st.day.tasks : []).filter(function (o) { return o.id !== t.id && o.start; });
      var otherOpts = others.map(function (o) { return '<option value="' + o.id + '">' + o.start + " " + esc(o.title) + "</option>"; }).join("");
      T.dlg.open("Move “" + esc(t.title) + "”", '<form data-form="move_task" class="form">' + hidden("id", t.id) +
        '<fieldset class="choice"><legend class="field-l">How</legend>' +
        '<label><input type="radio" name="mode" value="time" checked> To a time today (' + esc(T.r.dayLabel(t.date)) + ")</label>" +
        (otherOpts ? '<label><input type="radio" name="mode" value="before"> Right before another task</label><label><input type="radio" name="mode" value="after"> Right after another task</label>' : "") +
        '<label><input type="radio" name="mode" value="day"> To another day</label></fieldset>' +
        '<div class="cols"><div><label class="field-l" for="m-start">Time</label><input id="m-start" type="time" name="start" value="' + esc(t.start || "") + '"><p class="hint">Leave empty to clear the time (the planner places it).</p></div>' +
        '<div><label class="field-l" for="m-date">Day</label><input id="m-date" type="date" name="date" value="' + esc(t.date) + '" min="' + st.today + '"></div></div>' +
        (otherOpts ? '<label class="field-l" for="m-other">Other task</label><select id="m-other" name="other_id">' + otherOpts + "</select>" : "") +
        '<p class="hint">Moving a planned task pins it, so re-planning won’t move it. Overlaps are refused.</p>' + err() + foot("Move") + "</form>");
    },
    reason: function (t, status) {
      var failed = status === "failed";
      T.dlg.open("Why " + (failed ? "didn’t" : "skip") + " “" + esc(t.title) + "”" + (failed ? " work?" : "?"),
        '<form data-form="' + (failed ? "mark_failed" : "mark_skipped") + '" class="form reason-form">' + hidden("id", t.id) +
        '<p class="muted">' + (t.start ? t.start + "–" + t.end + ". " : "") + "Nothing changes until a reason is saved. Reasons are kept permanently; undo never deletes them.</p>" +
        '<label class="field-l" for="r-text">Reason</label><textarea id="r-text" name="reason" rows="4" required maxlength="1000" data-keep autofocus></textarea>' +
        '<p class="hint" data-reason-hint>Required. You can also say it: press V.</p>' + err() + foot(failed ? "Save reason, mark failed" : "Save reason, skip") + "</form>",
        { onOpen: function (d) {
          var ta = d.querySelector("textarea"), sub = d.querySelector("[type=submit]");
          var sync = function () { sub.disabled = !ta.value.trim(); };
          ta.addEventListener("input", sync); sync();
        } });
    },
    done: function (t) {
      var c = t.contribution || { mode: "none" };
      var extra = "";
      if (c.mode === "amount") {
        extra = '<label class="field-l" for="d-amt">How many ' + esc(t.goal.unit || "") + " did this add to “" + esc(t.goal.title) + "”?</label>" +
          '<input id="d-amt" type="number" name="contribution" min="0" step="any" value="0" autofocus><p class="hint">Logged for today; it rolls up to the week and month goals linked above it.</p>';
      } else if (c.mode === "mark_done") {
        extra = '<label class="check"><input type="checkbox" name="mark_goal_done" value="true"> This completes the goal “' + esc(t.goal.title) + "”</label>";
      } else if (c.mode === "closed") {
        extra = '<p class="warn small">' + esc(c.note) + "</p>";
      }
      if (c.mode === "none" || c.mode === "closed") return T.run("mark_done", { id: t.id });
      T.dlg.open("Done: “" + esc(t.title) + "”", '<form data-form="mark_done" class="form">' + hidden("id", t.id) + extra + err() + foot("Mark done") + "</form>");
    },
    extend: function (t) {
      T.dlg.open("“" + esc(t.title) + "” is still going", '<form data-form="extend_task" class="form">' + hidden("id", t.id) +
        '<p class="muted">Planned to end at ' + esc(t.end) + ". You’ll see a proposal first: tasks behind it may shift; fixed and pinned ones never move.</p>" +
        '<div class="cols"><div><label class="field-l" for="x-min">Minutes to add</label><input id="x-min" type="number" name="minutes" min="1" max="600" value="15" autofocus></div>' +
        '<div><label class="field-l" for="x-until">or until</label><input id="x-until" type="time" name="until"></div></div>' + err() + foot("Show the proposal") + "</form>");
    },
    link: function (t) {
      T.dlg.open("Goal for “" + esc(t.title) + "”", '<form data-form="link_task" class="form">' + hidden("id", t.id) +
        '<label class="field-l" for="l-goal">Goal</label><select id="l-goal" name="goal_id">' + goalOptions(t.goal && t.goal.id, true) + "</select>" +
        '<p class="hint">Only goals of periods that haven’t ended. Goals are created on the day, week and month pages.</p>' +
        ((T.state.open_goals || []).length ? "" : '<p class="small">No open goals yet. ' + T.r.btn("nav_day", null, "Open today’s page") + "</p>") + err() + foot("Save") + "</form>");
    },
    goal: function (o) {
      var g = o.goal, edit = !!g, kind = edit ? g.kind : o.kind, p = T.state.periods[kind];
      var parents = (edit ? g.link_options : p.parent_options) || [];
      var unitHint = parents.length ? "Linking up needs the same unit as the goal above." : "";
      var body = '<form data-form="' + (edit ? "edit_goal" : "new_goal") + '" class="form">' + hidden("id", edit ? g.id : null) + hidden("kind", edit ? null : kind) + hidden("start", edit ? null : o.start) +
        '<label class="field-l" for="g-title">Goal</label><input id="g-title" name="title" required maxlength="200" value="' + esc(edit ? g.title : "") + '" autofocus>' +
        '<div class="cols"><div><label class="field-l" for="g-target">Target (optional)</label><input id="g-target" type="number" step="any" min="0" name="target" value="' + esc(edit && g.target != null ? g.target : "") + '"></div>' +
        '<div><label class="field-l" for="g-unit">Unit</label><input id="g-unit" name="unit" maxlength="40" value="' + esc(edit && g.unit ? g.unit : "") + '"></div></div>' +
        '<p class="hint">With a target, progress is logged / target. Without one, the goal is done or not done.</p>' +
        (kind === "month" ? "" : '<label class="field-l" for="g-parent">Counts toward (optional)</label><select id="g-parent" name="parent_id"><option value="">Nothing</option>' +
          parents.map(function (x) { return '<option value="' + x.id + '"' + (edit && g.parent && g.parent.id === x.id ? " selected" : "") + ">" + esc(x.title) + " (" + esc(x.period) + (x.unit ? ", " + esc(x.unit) : "") + ")</option>"; }).join("") +
          '</select><p class="hint">' + unitHint + "</p>") + err() + foot(edit ? "Save goal" : "Add goal") + "</form>";
      T.dlg.open(edit ? "Edit goal" : "New " + kind + " goal (" + esc(p.label) + ")", body);
    },
    log: function (a) {
      var today = T.state.today, max = a.end < today ? a.end : today;
      T.dlg.open("Log progress", '<form data-form="log_progress" class="form">' + hidden("goal_id", a.goal_id) +
        '<div class="cols"><div><label class="field-l" for="lg-amt">Amount' + (a.unit ? " (" + esc(a.unit) + ")" : "") + '</label><input id="lg-amt" type="number" step="any" min="0" name="amount" required autofocus></div>' +
        '<div><label class="field-l" for="lg-date">On</label><input id="lg-date" type="date" name="date" value="' + esc(max) + '" min="' + esc(a.start) + '" max="' + esc(max) + '"></div></div>' + err() + foot("Log it") + "</form>");
    },
    confirm: function (cmd, args, message) {
      T.dlg.open("Please confirm", '<form data-form="confirm" class="form">' + hidden("cmd", cmd) + hidden("args", JSON.stringify(args || {})) +
        '<p class="readback">' + esc(message) + "</p>" + err() + foot("Yes, go ahead", { danger: true, cancel: "No, keep everything" }) + "</form>");
    },
    /* am or pm? The logic layer couldn't tell from the day window; nothing is saved until you answer. */
    choice: function (cmd, args, out) {
      var opts = out.choices.map(function (c, i) {
        return '<label><input type="radio" name="value" value="' + esc(c.value) + '" required' + (i ? "" : " autofocus") + "> " + esc(c.label) + "</label>";
      }).join("");
      T.dlg.open("Which time?", '<form data-form="choose_ampm" class="form">' + hidden("cmd", cmd) + hidden("args", JSON.stringify(args || {})) +
        hidden("line", out.line == null ? "" : out.line) + '<p class="readback">' + esc(out.message) + "</p>" +
        '<fieldset class="choice"><legend class="sr">Time</legend>' + opts + "</fieldset>" + err() + foot("Use this time") + "</form>");
    }
  };

  /* ---------- reading a form ---------- */
  T.formArgs = function (form) {
    var a = {};
    new FormData(form).forEach(function (v, k) {
      if (k in a) return;
      a[k] = typeof v === "string" ? v : "";
    });
    form.querySelectorAll("input[type=checkbox][name]").forEach(function (c) { a[c.name] = c.checked; });
    return a;
  };
  T.formError = function (form, msg) {
    var e = form && form.querySelector(".form-err");
    if (e) { e.textContent = msg; e.hidden = !msg; if (msg) e.focus && e.setAttribute("tabindex", "-1"); }
  };
})();
