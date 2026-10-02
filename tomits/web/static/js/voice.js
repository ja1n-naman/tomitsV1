/* Voice in the browser, alarm tone and desktop notifications.
   - The mic is recorded here and sent to this computer's own server, which
     transcribes it with the local Whisper model. Nothing leaves the PC.
   - What was heard is shown first; the server's dialog decides (same registry,
     same "yes" for risky actions, nothing below the confidence limit).
   - Spoken replies use only voices installed on this computer. */
(function () {
  var T = window.T;
  var esc = function (s) { return T.r.esc(s); };

  /* ================= conversation panel ================= */
  var convEl;
  T.conv = { history: [], id: null, asking: false };
  function convAdd(role, text, kind) {
    T.conv.history.push({ role: role, text: text, kind: kind || "", at: new Date() });
    if (T.conv.history.length > 60) T.conv.history.shift();
    renderConv();
    T.emit("conv", T.conv);
  }
  function renderConv() {
    convEl = convEl || document.getElementById("conv");
    var recent = T.conv.history.slice(-6);
    if (!recent.length) { convEl.hidden = true; return; }
    convEl.hidden = false;
    convEl.innerHTML = '<div class="conv-lines">' + recent.map(function (m) {
      return '<p class="cv cv-' + m.role + (m.kind ? " cv-" + m.kind : "") + '">' + (m.role === "me" ? "<b>You:</b> " : m.kind === "ask" ? "<b>Question:</b> " : "") + esc(m.text) + "</p>";
    }).join("") + "</div>" +
      (T.conv.asking ? '<p class="cv-hint">Answer in the box above or press V and speak. Say “cancel” to stop.</p>' : "") +
      '<div class="conv-act">' + (T.conv.undo ? T.r.btn("undo_action", { id: T.conv.undo }, "Undo that", { icon: "undo" }) : "") +
      T.r.btn("conv_close", null, "", { icon: "x", aria: "Close the conversation", cls: "quiet" }) + "</div>";
    T.hydrateIcons(convEl);
  }
  T.conv.clear = function () { T.conv.history = []; T.conv.undo = null; renderConv(); T.emit("conv", T.conv); };

  /* send typed or spoken words through the server's dialog */
  T.voice = { phase: "idle" };
  function setPhase(p, label) {
    T.voice.phase = p;
    document.documentElement.setAttribute("data-mic", p);
    var text = label || { idle: "Ready", listening: "Listening…", thinking: "Understanding…", asking: "Waiting for your answer", muted: "Muted" }[p];
    document.querySelectorAll("[data-mic-phase]").forEach(function (el) { el.textContent = text; });
    var sr = document.getElementById("mic-state-sr"); if (sr) sr.textContent = "Microphone: " + text;
    document.querySelectorAll('[data-act="mic_toggle"]').forEach(function (b) { b.setAttribute("aria-pressed", p === "listening" ? "true" : "false"); });
  }
  T.voice.setPhase = setPhase;

  T.voice.send = async function (text, confidence) {
    text = (text || "").trim();
    if (!text) return;
    convAdd("me", text + (confidence != null && confidence < 1 ? "  (" + Math.round(confidence * 100) + "% sure)" : ""));
    setPhase("thinking");
    try {
      var out = await T.api.post("/api/say", { text: text, confidence: confidence == null ? 1 : confidence, conv: T.conv.asking ? T.conv.id : null });
      out.messages.forEach(function (m) {
        // "Heard:" / "→" lines are already shown as "You:"; what was read from a title is shown, not spoken
        if (m.type === "show") { if (/^Read from the title/.test(m.text)) convAdd("app", m.text, "note"); return; }
        convAdd("app", m.text, m.type);
        speak(m.text);
      });
      T.conv.id = out.conv; T.conv.asking = !!out.asking;
      T.conv.undo = out.undo_id || null;
      renderConv();
      if (out.undo_id) T.toast("Saved: " + out.undo_label, { undo: out.undo_id });
      if (out.view && out.view.screen) T.applyView(out.view);
      setPhase(T.conv.asking ? "asking" : "idle");
      T.refresh(true);
    } catch (p) {
      convAdd("app", p.message, "error");
      setPhase("idle");
    }
  };

  /* ================= spoken replies (local voices only) ================= */
  function speak(text) {
    if (!T.state || !T.state.settings.spoken_replies || !window.speechSynthesis) return;
    var voices = speechSynthesis.getVoices().filter(function (v) { return v.localService && /^en/i.test(v.lang); });
    if (!voices.length) return;  // never use an online voice
    var u = new SpeechSynthesisUtterance(text);
    u.voice = voices[0];
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
  }
  T.voice.speak = speak;

  /* ================= microphone ================= */
  var rec = null;
  function setLevel(v) {
    document.querySelectorAll("[data-level]").forEach(function (el) { el.style.setProperty("--level", v.toFixed(3)); });
  }
  async function startRecording() {
    if (rec) return rec;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new T.Problem("This browser can't use a microphone here. Type the command instead.");
    var mic = T.state && T.state.settings.browser_mic;
    var stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: mic ? { deviceId: { exact: mic } } : true });
    } catch (e) {
      if (mic) { try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (e2) { e = e2; stream = null; } }
      if (!stream) throw new T.Problem(e && e.name === "NotAllowedError"
        ? "The browser blocked the microphone. Click the icon at the left of the address bar, allow the microphone, and try again. Typing works meanwhile."
        : "No microphone could be opened (" + (e && e.name || "unknown") + "). Check one is plugged in; typing works meanwhile.");
    }
    var ctx = new (window.AudioContext || window.webkitAudioContext)();
    var src = ctx.createMediaStreamSource(stream);
    var proc = ctx.createScriptProcessor(4096, 1, 1);
    var mute = ctx.createGain(); mute.gain.value = 0;
    var chunks = [], level = 0;
    proc.onaudioprocess = function (ev) {
      var d = ev.inputBuffer.getChannelData(0);
      chunks.push(new Float32Array(d));
      var sum = 0; for (var i = 0; i < d.length; i += 4) sum += d[i] * d[i];
      var rms = Math.sqrt(sum / (d.length / 4));
      level = level * 0.6 + Math.min(1, rms * 6) * 0.4;
      setLevel(level);
    };
    src.connect(proc); proc.connect(mute); mute.connect(ctx.destination);
    rec = { stream: stream, ctx: ctx, proc: proc, chunks: chunks, rate: ctx.sampleRate, started: Date.now() };
    T.alarmTone.quiet(true);
    return rec;
  }
  async function stopRecording() {
    var r = rec; rec = null;
    if (!r) return null;
    r.proc.disconnect(); r.stream.getTracks().forEach(function (t) { t.stop(); });
    try { await r.ctx.close(); } catch (e) {}
    setLevel(0);
    T.alarmTone.quiet(false);
    var n = r.chunks.reduce(function (s, c) { return s + c.length; }, 0);
    var all = new Float32Array(n), o = 0;
    r.chunks.forEach(function (c) { all.set(c, o); o += c.length; });
    // down-sample to 16 kHz 16-bit mono
    var ratio = r.rate / 16000, len = Math.floor(n / ratio), out = new Int16Array(len);
    for (var i = 0; i < len; i++) {
      var start = Math.floor(i * ratio), end = Math.min(n, Math.floor((i + 1) * ratio)), acc = 0;
      for (var j = start; j < end; j++) acc += all[j];
      var v = end > start ? acc / (end - start) : 0;
      out[i] = Math.max(-1, Math.min(1, v)) * 32767;
    }
    return { pcm: out, seconds: n / r.rate };
  }
  async function transcribe(clip) {
    if (!clip || clip.seconds < 0.3) throw new T.Problem("That was too short to hear anything. Hold V (or keep the mic on) while you speak.");
    setPhase("thinking");
    return T.api.postRaw("/api/voice/transcribe?rate=16000", clip.pcm.buffer);
  }

  T.voice.start = async function () {
    if (T.state && T.state.settings.muted) { T.toast("The microphone is muted. Unmute it in Settings, or say it by typing."); return; }
    try {
      await startRecording();
      setPhase("listening");
    } catch (p) {
      setPhase("idle"); convAdd("app", p.message, "error");
    }
  };
  T.voice.stop = async function () {
    if (!rec) return;
    try {
      var clip = await stopRecording();
      var heard = await transcribe(clip);
      if (!heard.text) { convAdd("app", "I didn't hear anything. Try again a little closer to the mic.", "error"); setPhase(T.conv.asking ? "asking" : "idle"); return; }
      await T.voice.send(heard.text, heard.confidence);
    } catch (p) {
      convAdd("app", p.message, "error");
      setPhase(T.conv.asking ? "asking" : "idle");
    }
  };
  T.voice.toggle = function () { return rec ? T.voice.stop() : T.voice.start(); };
  T.voice.recording = function () { return !!rec; };

  /* mic test: 4 seconds with a level meter, then what was understood */
  T.voice.micTest = async function () {
    var out = function (t) { document.querySelectorAll("[data-mictest-result]").forEach(function (el) { el.textContent = t; }); };
    try {
      await startRecording();
      setPhase("listening", "Mic test: say a short sentence…");
      out("Listening for 4 seconds…");
      await new Promise(function (r) { setTimeout(r, 4000); });
      var clip = await stopRecording();
      var peak = clip.pcm.reduce(function (m, v) { return Math.max(m, Math.abs(v)); }, 0) / 32767;
      if (peak < 0.02) { out("Almost no sound reached the mic. Check the right microphone is chosen and not muted."); setPhase("idle"); return; }
      try {
        var heard = await transcribe(clip);
        out(heard.text ? "Heard: “" + heard.text + "” (" + Math.round(heard.confidence * 100) + "% sure)" + (heard.low ? ". That's below the limit, so a command like this would do nothing." : ".")
          : "Sound reached the mic, but no words were recognised. Speak a little louder or closer.");
      } catch (p) { out("The mic works (level " + Math.round(peak * 100) + "%). " + p.message); }
      setPhase("idle");
      listDevices();
    } catch (p) { out(p.message); setPhase("idle"); }
  };

  async function listDevices() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
    var devs = (await navigator.mediaDevices.enumerateDevices()).filter(function (d) { return d.kind === "audioinput"; });
    var cur = T.state && T.state.settings.browser_mic;
    document.querySelectorAll("#mic-select").forEach(function (sel) {
      sel.innerHTML = '<option value="">Default microphone</option>' + devs.filter(function (d) { return d.deviceId && d.deviceId !== "default"; }).map(function (d, i) {
        return '<option value="' + esc(d.deviceId) + '"' + (d.deviceId === cur ? " selected" : "") + ">" + esc(d.label || "Microphone " + (i + 1)) + "</option>";
      }).join("");
    });
  }
  T.voice.listDevices = listDevices;

  /* ================= alarm tone (built-in, made in the browser) ================= */
  var actx = null, timer = null, quiet = false;
  T.alarmTone = {
    blocked: false,
    unlock: function () {
      try {
        actx = actx || new (window.AudioContext || window.webkitAudioContext)();
        if (actx.state === "suspended") actx.resume();
      } catch (e) { this.blocked = true; }
      return actx;
    },
    burst: function () {
      var c = this.unlock();
      if (!c || c.state !== "running") { this.blocked = true; T.emit("sound-blocked"); return false; }
      this.blocked = false;
      var t = c.currentTime, pattern = [[880, 0.18], [0, 0.09], [880, 0.18], [0, 0.09], [1320, 0.32]];
      pattern.forEach(function (p) {
        if (p[0]) {
          var o = c.createOscillator(), g = c.createGain();
          o.frequency.value = p[0]; o.type = "sine";
          g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.35, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + p[1]);
          o.connect(g); g.connect(c.destination); o.start(t); o.stop(t + p[1] + 0.02);
        }
        t += p[1];
      });
      return true;
    },
    start: function () {
      if (timer) return;
      var self = this;
      var tick = function () { if (!quiet) self.burst(); };
      tick();
      timer = setInterval(tick, 1700);
    },
    stop: function () { clearInterval(timer); timer = null; },
    quiet: function (on) { quiet = on; },
    playing: function () { return !!timer; }
  };
  ["pointerdown", "keydown"].forEach(function (ev) {
    document.addEventListener(ev, function () {
      if (actx && actx.state === "suspended") actx.resume().then(function () { if (T.alarmTone.blocked) { T.alarmTone.blocked = false; T.emit("sound-unblocked"); } });
    }, true);
  });

  /* ================= desktop notifications ================= */
  T.notifyAlarm = function (a) {
    if (!("Notification" in window)) return "unsupported";
    if (Notification.permission !== "granted") return Notification.permission;
    if (!document.hidden && document.hasFocus()) return "focused";
    try {
      var n = new Notification(a.title_line, { body: a.message, tag: a.kind + ":" + a.task_id, requireInteraction: true });
      n.onclick = function () { window.focus(); n.close(); };
      return "shown";
    } catch (e) { return "failed"; }
  };
})();
