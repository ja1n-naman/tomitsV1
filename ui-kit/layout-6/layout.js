/* Layout 6: Voice first (UI_GUIDE.md §4.6).
   Slots: rail (rail-nav, rail-more), stream (with screen-card), composer, context.
   Each screen is listed as the phrase that opens it (UI.data.voice.rail). */
(function () {
  var UI = window.UI, R = UI.r, esc = UI.esc, I = function (n) { return UI.icon(n); };
  var RAIL = [["home", "Overview", "today"], ["list", "List", "list"], ["progress", "Progress", "target"], ["history", "History", "history"],
    ["voice", "Voice and mic", "wave"], ["settings", "Settings", "settings"], ["later", "Later", "timer"]];

  function rail() {
    var phrases = UI.data.voice.rail || {}, n = R.decisions().length;
    return '<aside class="l6-rail" aria-label="Things you can ask" data-slot="rail"><p class="ask-h">Say it, or tap it</p><nav aria-label="Main navigation" data-slot="rail-nav">' + RAIL.map(function (r) {
      return '<a href="#' + r[0] + '" data-nav="' + r[0] + '"' + (r[0] === "later" ? ' class="later"' : "") + ">" + I(r[2]) + "<span><b>“" + esc(phrases[r[0]] || r[1]) + "”</b><small>" + r[1] +
        (r[0] === "list" && n ? " · " + n + " waiting" : "") + "</small></span></a>";
    }).join("") + '<a href="../index.html" data-act="open_layouts">' + I("layers") + "<span><b>Layouts</b><small>Switch to another layout</small></span></a>" +
      '</nav><p class="ask-h">More things to say</p><div class="more" data-slot="rail-more">' + UI.data.voice.phrases.map(function (c) { return "<p>“" + esc(c.examples[0]) + "”</p>"; }).join("") + "</div></aside>";
  }
  function stream(screen, inner) {
    var V = UI.voice || { history: [], asking: null };
    var lines = V.history.map(function (m) {
      if (m.role === "me") return '<div class="turn"><div class="bubble me"><p>' + esc(m.text) + "</p></div></div>";
      return '<div class="turn app"><div class="card' + (m.kind === "error" ? " card-err" : m.kind === "ask" ? " card-ask" : "") + '"><p>' + esc(m.text) + "</p></div></div>";
    }).join("");
    var tapped = RAIL.filter(function (r) { return r[0] === screen; })[0];
    return '<div class="stream" id="l6-stream" data-slot="stream">' + (lines || '<p class="day-sep">Say a command with V, or type it in the box above. Tap anything on the left to see it here.</p>') +
      (tapped ? '<div class="turn"><div class="bubble me tapped"><p>' + esc(tapped[1]) + '</p><span class="conf">tapped</span></div></div>' : "") +
      '<div class="turn app"><div class="card big" data-slot="screen-card">' + inner + "</div></div>" +
      (V.asking ? '<div class="turn app"><div class="card card-ask"><p>Waiting for your answer: say it (V) or type it above.</p></div></div>' : "") + "</div>";
  }
  function context() {
    var nn = UI.nowAndNext(), now = nn.now, muted = UI.store.get("uikit.muted", false);
    return '<aside class="l6-ctx" data-slot="context"><section class="ctx"><p class="eyebrow">Now</p>' + (now && UI.preview() === "normal" ? '<p class="ctx-big">' + esc(now.title) + '</p><p class="small muted">' + now.start + "–" + now.end + " · " + now.minutes_left +
      ' min left</p><div class="thin"><span style="width:' + Math.round((now.elapsed || 0) * 100) + '%"></span></div>' + R.itemActions(now, { short: true }) : '<p class="muted">Nothing running</p>') +
      (nn.next[0] && UI.preview() === "normal" ? '<p class="eyebrow">Next</p><p><b>' + nn.next[0].start + "</b> " + esc(nn.next[0].title) + "</p>" : "") + "</section>" +
      '<section class="ctx"><p class="eyebrow">' + I("mic") + ' Microphone</p><p class="small" data-mic-phase>Ready</p><p class="small muted">Push to talk: hold <kbd>V</kbd>. This kit\'s mic is fake.</p>' +
      '<div class="row">' + UI.btn("mic_mute", null, muted ? "Unmute" : "Mute", { cls: "tiny" }) + UI.navLink("voice", "Mic test", { cls: "btn tiny" }) + "</div></section></aside>";
  }
  function home() {
    var d = UI.day(UI.view.dayOffset), rows = d.items.concat(d.untimed), p = UI.preview();
    return '<p class="eyebrow">' + I("today") + ' Overview</p><h2 class="screen-title">' + esc(UI.date.long(d.date)) + "</h2>" + R.toolbar() +
      (p === "loading" || p === "error" ? UI.state("") : rows.length ? '<div class="items">' + rows.map(function (t) { return R.itemRow(t); }).join("") + "</div>" : R.emptyDay(d)) +
      R.decisions().map(R.decisionCard).join("") + R.olderList();
  }

  UI.on("conv", function () { if (UI.layout && UI.layout.id === 6) UI.render(); });
  UI.start({
    id: 6, defaultScreen: "home", home: home,
    frame: function (screen, inner) {
      return '<div class="l6">' + rail() + '<div class="l6-talk">' + stream(screen, inner) +
        '<div class="composer" data-slot="composer"><button type="button" class="mic-huge" data-act="mic_toggle" aria-pressed="false" aria-label="Talk (hold V)"><span class="mic-ring" data-level></span>' + I("mic") + "</button>" +
        '<div><p class="comp-phase" data-mic-phase>Ready</p><p class="small muted">Hold <kbd>V</kbd> or tap the mic · type in the box above</p></div></div></div>' + context() + "</div>";
    },
    after: function (root) { var s = root.querySelector("#l6-stream"); if (s && UI.voice && UI.voice.history.length) s.scrollTop = s.scrollHeight; }
  });
})();
