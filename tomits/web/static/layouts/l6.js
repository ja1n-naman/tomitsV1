/* Layout 6: Voice first. A conversation down the middle; what you said shows as
   bubbles and every answer is a card you can act on. The left rail lists the
   screens as the words that open them, so you learn what to say by looking. */
(function () {
  var T = window.T, R = T.r, I = function (n) { return T.icon(n); };
  var RAIL = [["today", "what’s my day like", "Today", "today"], ["reschedule", "accept", "Reschedule", "reschedule"],
    ["day", "open today", "Day page", "target"], ["week", "open this week", "Week page", "calendar"], ["month", "open this month", "Month page", "grid"],
    ["history", "show my history", "Missed and skipped", "history"], ["voice", "test my mic", "Voice and mic", "wave"],
    ["settings", "show my settings", "Settings", "settings"], ["focus", "(coming in 2.0)", "Pomodoro", "timer"], ["layouts", "switch to the board layout", "Layouts", "layers"]];

  function rail(st) {
    var ex = st.voice.phrases.filter(function (c) { return ["plan_day", "add_task", "mark_done", "log_progress", "alarm_snooze", "undo_action"].indexOf(c.name) > -1; });
    return '<aside class="l6-rail" aria-label="Things you can ask"><p class="ask-h">Say it, or tap it</p><nav aria-label="Main navigation">' + RAIL.map(function (r) {
      return '<a href="#' + r[0] + '" data-nav="' + r[0] + '"' + (r[0] === "focus" ? ' class="later"' : "") + ">" + I(r[3]) + "<span><b>“" + R.esc(r[1]) + "”</b><small>" + r[2] +
        (r[0] === "reschedule" && st.proposals.length ? " · " + st.proposals.length + " waiting" : "") + "</small></span></a>";
    }).join("") + '</nav><p class="ask-h">More things to say</p><div class="more">' + ex.map(function (c) { return "<p>“" + R.esc(c.examples[0]) + "”</p>"; }).join("") + "</div></aside>";
  }

  function stream(st, screen, inner) {
    var lines = T.conv.history.map(function (m) {
      if (m.role === "me") return '<div class="turn"><div class="bubble me"><p>' + R.esc(m.text) + "</p></div></div>";
      return '<div class="turn app"><div class="card' + (m.kind === "error" ? " card-err" : m.kind === "ask" ? " card-ask" : "") + '"><p>' + R.esc(m.text) + "</p></div></div>";
    }).join("");
    var tapped = RAIL.filter(function (r) { return r[0] === screen; })[0];
    return '<div class="stream" id="l6-stream">' + (lines || '<p class="day-sep">Say a command with V, or type it in the box below. Tap anything on the left to see it here.</p>') +
      (tapped ? '<div class="turn"><div class="bubble me tapped"><p>' + R.esc(tapped[2]) + '</p><span class="conf">tapped</span></div></div>' : "") +
      '<div class="turn app"><div class="card big">' + inner + "</div></div>" +
      (T.conv.asking ? '<div class="turn app"><div class="card card-ask"><p>Waiting for your answer: say it (V) or type it below.</p></div></div>' : "") + "</div>";
  }

  function context(st) {
    var nn = R.nowAndNext();
    return '<aside class="l6-ctx"><section class="ctx"><p class="eyebrow">Now</p>' + (nn.now ? '<p class="ctx-big">' + R.esc(nn.now.title) + '</p><p class="small muted">' + nn.now.start + "–" + nn.now.end + " · " + nn.now.minutes_left + ' min left</p><div class="thin"><span style="width:' + Math.round(nn.now.elapsed * 100) + '%"></span></div>' + R.taskActions(nn.now, { short: true })
      : '<p class="muted">Nothing running</p>') + (nn.next[0] ? '<p class="eyebrow">Next</p><p><b>' + nn.next[0].start + "</b> " + R.esc(nn.next[0].title) + "</p>" : "") + "</section>" +
      '<section class="ctx"><p class="eyebrow">' + I("mic") + ' Microphone</p><p class="small" data-mic-phase>Ready</p><p class="small muted">Push to talk: hold <kbd>V</kbd>. Speech is turned into text on this computer.</p>' +
      '<div class="row">' + R.btn("mute", { muted: !st.settings.muted }, st.settings.muted ? "Unmute" : "Mute", { cls: "tiny" }) + R.nav("voice", "Mic test", { cls: "btn tiny" }) + "</div></section>" +
      (st.alarms.snoozed.length ? '<section class="ctx"><p class="eyebrow">' + I("bell") + " Snoozed</p>" + st.alarms.snoozed.map(function (s) { return "<p>" + R.esc(s.title) + " at " + s.due + "</p>"; }).join("") + "</section>" : "") + "</aside>";
  }

  function today(st) {
    var d = st.day, rows = d.tasks.concat(d.untimed);
    return '<p class="eyebrow">' + I("today") + " Your day</p><h2 class=\"screen-title\">" + R.esc(d.label) + "</h2>" + R.dayBar(st) +
      (rows.length ? '<div class="trs">' + rows.map(function (t) { return R.taskRow(t); }).join("") + "</div>"
        : R.empty("Nothing planned yet. Say “add a task” and what it is, or use Add task. Plan my day places anything without a time.", R.btn("add_task", { date: d.date }, "Add a task", { icon: "plus", cls: "primary" }))) +
      st.proposals.map(R.proposalCard).join("") + R.overdueList(st);
  }

  T.on("conv", function () { if (T.state && T.state.ui.layout === 6) T.render(); });

  T.layouts[6] = {
    id: 6, defaultScreen: "today", today: today,
    frame: function (st, screen, inner) {
      return '<div class="l6">' + rail(st) + '<div class="l6-talk">' + stream(st, screen, inner) +
        '<div class="composer"><button type="button" class="mic-huge" data-act="mic_toggle" aria-pressed="false" aria-label="Talk (hold V)"><span class="mic-ring" data-level></span>' + I("mic") + "</button>" +
        '<div><p class="comp-phase" data-mic-phase>Ready</p><p class="small muted">Hold <kbd>V</kbd> or tap the mic · type in the box above · offline</p></div></div></div>' + context(st) + "</div>";
    },
    after: function (root) {
      var s = root.querySelector("#l6-stream");
      if (s && T.conv.history.length) s.scrollTop = s.scrollHeight;
    }
  };
})();
