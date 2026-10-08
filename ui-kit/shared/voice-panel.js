/* voice-panel.js: voice with a FAKE mic (UI_GUIDE.md §5.10). Optional.
   Nothing is recorded and nothing leaves the page: the "mic" animates a level,
   then "hears" the next phrase from UI.data.voice.heard.
   - phases on <html data-mic>: idle | listening | thinking | asking | muted;
     the text goes into every [data-mic-phase]; levels into every [data-level] (--level 0..1)
   - what was heard is shown first (with % when unsure), then the interpreted command
   - risky commands read back and wait for "yes" (the fake mic hears "yes" next)
   - below UI.data.voice.low_confidence nothing happens
   - conversation panel (#conv), transcript log, mic test, the V key (hold or tap)
   To use a real recogniser, replace hear() and decide() with calls to your backend. */
(function () {
  var UI = window.UI, V = UI.voice = { phase: "idle", history: [], asking: null }, idx = 0, anim = null, level = 0, undoId = null;
  var PHASE = { idle: "Ready", listening: "Listening…", thinking: "Understanding…", asking: "Waiting for your answer", muted: "Muted" };
  function muted() { return !!UI.store.get("uikit.muted", false); }
  function setPhase(p, label) {
    V.phase = p;
    document.documentElement.setAttribute("data-mic", p);
    var text = label || PHASE[p];
    document.querySelectorAll("[data-mic-phase]").forEach(function (el) { el.textContent = text; });
    var sr = document.getElementById("mic-state-sr"); if (sr) sr.textContent = "Microphone: " + text;
    document.querySelectorAll('[data-act="mic_toggle"]').forEach(function (b) { b.setAttribute("aria-pressed", p === "listening" ? "true" : "false"); });
  }
  function setLevel(v) { document.querySelectorAll("[data-level]").forEach(function (el) { el.style.setProperty("--level", v.toFixed(3)); }); }
  function animate(on) {
    cancelAnimationFrame(anim); level = 0;
    if (!on) { setLevel(0); return; }
    (function tick() { level = level * 0.6 + Math.random() * 0.75 * 0.4; setLevel(level); anim = requestAnimationFrame(tick); })();
  }

  /* conversation */
  function add(role, text, kind) { V.history.push({ role: role, text: text, kind: kind || "" }); if (V.history.length > 60) V.history.shift(); renderConv(); UI.emit("conv"); }
  function renderConv() {
    var el = document.getElementById("conv"); if (!el) return;
    var recent = V.history.slice(-6);
    if (!recent.length) { el.hidden = true; el.innerHTML = ""; return; }
    el.hidden = false;
    el.innerHTML = '<div class="conv-lines">' + recent.map(function (m) {
      return '<p class="cv cv-' + m.role + (m.kind ? " cv-" + m.kind : "") + '">' + (m.role === "me" ? "<b>You:</b> " : m.kind === "ask" ? "<b>Question:</b> " : "") + UI.esc(m.text) + "</p>";
    }).join("") + "</div>" + (V.asking ? '<p class="cv-hint">Answer in the box above or press V and speak. Say “cancel” to stop.</p>' : "") +
      '<div class="conv-act">' + (undoId ? UI.btn("undo", { id: undoId }, "Undo that", { icon: "undo" }) : "") + UI.btn("conv_close", null, "", { icon: "x", aria: "Close the conversation", cls: "quiet" }) + "</div>";
  }
  V.clear = function () { V.history = []; undoId = null; renderConv(); UI.emit("conv"); };
  UI.actions.conv_close = { run: V.clear };
  UI.on("escape", function () { if (!V.asking) V.clear(); });

  function log(text, confidence, interpreted, acted, result) {
    UI.data.voice.log.unshift({ at: new Date().toTimeString().slice(0, 5), text: text, confidence: confidence, interpreted: interpreted, acted: acted, result: result });
  }
  function decide(text, confidence) {
    var vd = UI.data.voice, t = text.toLowerCase();
    if (V.asking) {
      var c = V.asking; V.asking = null;
      if (/^(yes|yeah|yep|go ahead)\b/.test(t)) {
        add("app", c.result); log(text, confidence, c.name, true, c.result);
        if (c.name === "delete_all") undoId = UI.change("Deleted all placeholder items (by voice).", function (data) { data.days.forEach(function (d) { d.items = []; d.untimed = []; }); data.older = []; }) || null;
      } else { add("app", "Cancelled. Nothing changed."); log(text, confidence, c.name, false, "Cancelled."); }
      return;
    }
    if (confidence != null && confidence < vd.low_confidence) {
      add("app", "I heard “" + text + "” but I'm only " + Math.round(confidence * 100) + "% sure, so nothing happened. Please say it again.", "error");
      log(text, confidence, null, false, "Below the confidence limit: nothing happened."); return;
    }
    var cmd = (vd.commands || []).filter(function (c) { return t.indexOf(c.match) > -1; })[0];
    if (!cmd) { add("app", "No command matched “" + text + "”. Nothing happened.", "error"); log(text, confidence, null, false, "No command matched."); return; }
    if (cmd.risky) { V.asking = cmd; add("app", cmd.readback, "ask"); log(text, confidence, cmd.name, false, "Waiting for yes."); return; }
    add("app", cmd.result); log(text, confidence, cmd.name, true, cmd.result);
    if (cmd.nav) UI.go(cmd.nav);
  }
  V.send = function (text, confidence) {
    text = (text || "").trim(); if (!text) return;
    undoId = null;
    add("me", text + (confidence != null && confidence < 1 ? "  (" + Math.round(confidence * 100) + "% sure)" : ""));
    setPhase("thinking");
    setTimeout(function () { decide(text, confidence); setPhase(V.asking ? "asking" : "idle"); renderConv(); if (UI.screen() === "voice") UI.render(); }, 450);
  };

  /* the fake mic */
  function hear() { if (V.asking) return { text: "yes", confidence: 0.95 }; var h = UI.data.voice.heard; return h.length ? h[idx++ % h.length] : { text: "", confidence: 0 }; }
  V.recording = function () { return V.phase === "listening"; };
  V.start = function () {
    if (muted()) { setPhase("muted"); UI.toast && UI.toast("The microphone is muted. Unmute it in Settings, or type the command."); return; }
    setPhase("listening"); animate(true);
  };
  V.stop = function () {
    if (!V.recording()) return;
    animate(false); setPhase("thinking");
    var h = hear();
    setTimeout(function () { if (!h.text) { add("app", "I didn't hear anything. Try again.", "error"); setPhase("idle"); return; } V.send(h.text, h.confidence); }, 350);
  };
  V.toggle = function () { return V.recording() ? V.stop() : V.start(); };
  UI.actions.mic_toggle = { run: V.toggle };
  V.micTest = function () {
    var out = function (t) { document.querySelectorAll("[data-mictest-result]").forEach(function (el) { el.textContent = t; }); };
    if (muted()) { out("The microphone is muted."); return; }
    setPhase("listening", "Mic test: say a short sentence…"); animate(true); out("Listening for 4 seconds…");
    setTimeout(function () {
      animate(false); setPhase("idle");
      var h = UI.data.voice.micTestHeard || { text: "", confidence: 0 }, low = h.confidence < UI.data.voice.low_confidence;
      out(h.text ? "Heard: “" + h.text + "” (" + Math.round(h.confidence * 100) + "% sure)" + (low ? ". That's below the limit, so a command like this would do nothing." : ".") : "Sound reached the mic, but no words were recognised.");
    }, 4000);
  };
  UI.actions.mic_test = { run: V.micTest };
  UI.on("muted", function (m) { setPhase(m ? "muted" : "idle"); });

  /* V: hold to talk, or tap to start and tap again to stop */
  var vDown = 0;
  UI.addKey("V", "Push to talk: hold to speak, or tap to start and tap again to stop", function (e) { if (e.repeat) return; vDown = Date.now(); V.toggle(); }, { duringAlarm: true });
  document.addEventListener("keyup", function (e) {
    if (e.key.toLowerCase() !== "v" || !vDown) return;
    var held = Date.now() - vDown; vDown = 0;
    if (held > 350 && V.recording()) V.stop();
  });

  /* the voice screen (pattern) */
  UI.screens = UI.screens || {};
  UI.screens.voice = function () {
    var vd = UI.data.voice;
    var logHtml = vd.log.length && UI.preview() === "normal" ? '<ol class="vlog">' + vd.log.map(function (l) {
      var low = l.confidence != null && l.confidence < vd.low_confidence;
      return '<li class="' + (l.acted ? "acted" : "noact") + '"><span class="vt">' + UI.esc(l.at) + '</span><div><p class="vheard">“' + UI.esc(l.text) + '” <span class="conf' + (low ? " low" : "") + '">' +
        (l.confidence != null ? Math.round(l.confidence * 100) + "%" : "typed") + '</span></p><p class="vcmd">' + (l.interpreted ? UI.icon("arrow-right") + UI.esc(l.interpreted) : UI.icon("minus") + "No command") +
        '</p><p class="muted small">' + UI.esc(l.result || "") + "</p></div></li>";
    }).join("") + "</ol>" : UI.state(UI.empty("No voice or typed commands yet. Press V (or the mic) and speak, or type in the box at the top."));
    var phr = '<div class="phrases">' + vd.phrases.map(function (c) { return "<div><h4>" + UI.esc(c.summary) + (c.risky ? ' <span class="muted small">(asks for a spoken yes)</span>' : "") + "</h4><p>" + c.examples.map(function (e) { return "“" + UI.esc(e) + "”"; }).join(" · ") + "</p></div>"; }).join("") + "</div>";
    return '<h2 class="screen-title">Voice</h2><p class="lead-line">Everything you can click, you can say or type.</p><p class="warn small">' + UI.icon("alert") + " This kit's mic is fake: nothing is recorded or sent anywhere.</p>" +
      '<div class="voice-grid"><section class="panel vstage"><button type="button" class="mic-big" data-act="mic_toggle" aria-pressed="false" aria-label="Talk">' + UI.icon("mic") + '</button><div><p class="vphase" data-mic-phase>' + PHASE[V.phase] + "</p>" +
      '<p class="muted small">Hold <kbd>V</kbd> to talk, or click the mic to start and stop. Below ' + Math.round(vd.low_confidence * 100) + "% nothing happens.</p></div>" +
      '<div class="meter" data-level aria-hidden="true"><span></span></div></section>' +
      '<section class="panel vtest"><h3 class="panel-h">' + UI.icon("volume") + 'Mic test</h3><p class="small">Speak normally: the bar should reach the middle. Then you’ll see what was understood.</p>' +
      '<label class="field-l" for="mic-select">Microphone</label><select id="mic-select"><option>Default microphone (fake)</option></select>' +
      '<div class="meter wide" data-level aria-hidden="true"><span></span><i></i></div><p class="small" data-mictest-result></p>' + UI.btn("mic_test", null, "Start mic test", { icon: "play" }) + "</section>" +
      '<section class="panel vlogp"><h3 class="panel-h">' + UI.icon("list") + "Transcript log</h3>" + logHtml + "</section>" +
      '<section class="panel vlogp"><h3 class="panel-h">' + UI.icon("help") + "What you can say</h3>" + phr + "</section></div>";
  };
  UI.on("render", function () { setPhase(V.phase === "idle" && muted() ? "muted" : V.phase); });
  UI.on("start", function () { setPhase(muted() ? "muted" : "idle"); });
})();
