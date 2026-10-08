/* alarm.js: a time-based alert that must be answered (UI_GUIDE.md §5.12). Optional.
   - modal <dialog id="alarm-dlg">, red top edge, ringing bell, Snooze / Dismiss
   - Esc is blocked: the user must choose
   - tone made with Web Audio (no file, no network): 880 Hz .18 s, gap .09 s,
     880 Hz .18 s, gap .09 s, 1320 Hz .32 s, gain to .35, repeated every 1.7 s
   - browsers block sound until the first click: a banner offers "Enable sound"
   In the kit, Settings → "Ring the alarm now" triggers it, and Snooze rings again
   after 10 seconds (the button still says the real snooze length). */
(function () {
  var UI = window.UI, actx = null, timer = null, blocked = false, snoozeTimer = null;
  function ctx() { try { actx = actx || new (window.AudioContext || window.webkitAudioContext)(); if (actx.state === "suspended") actx.resume(); } catch (e) { actx = null; } return actx; }
  function burst() {
    var c = ctx();
    if (!c || c.state !== "running") { setBlocked(true); return false; }
    setBlocked(false);
    var t = c.currentTime;
    [[880, .18], [0, .09], [880, .18], [0, .09], [1320, .32]].forEach(function (p) {
      if (p[0]) {
        var o = c.createOscillator(), g = c.createGain();
        o.type = "sine"; o.frequency.value = p[0];
        g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(.35, t + .02); g.gain.exponentialRampToValueAtTime(.0001, t + p[1]);
        o.connect(g); g.connect(c.destination); o.start(t); o.stop(t + p[1] + .02);
      }
      t += p[1];
    });
    return true;
  }
  function setBlocked(b) {
    if (blocked === b) return; blocked = b;
    if (UI.banners) UI.banners.system("sound", b ? { tone: "warn", role: "alert", icon: "volume", html: "The browser is blocking sound, so alarms can't ring yet. Click Enable sound once.", action: UI.btn("sound_enable", null, "Enable sound", { cls: "primary" }) } : null);
  }
  function stopTone() { clearInterval(timer); timer = null; }
  UI.alarm = {
    ring: function (a) {
      a = a || UI.data.alarm || {};
      var d = document.getElementById("alarm-dlg"); if (!d) return;
      d.innerHTML = '<div class="alarm-top"><span class="alarm-bell">' + UI.icon("bell") + '</span><span class="eyebrow">' + UI.esc(a.eyebrow || "") + "</span></div>" +
        '<h2 id="alarm-title">' + UI.esc(a.title || "") + '</h2><p class="alarm-msg">' + UI.esc(a.message || "") + "</p>" +
        '<p class="muted small">Rings until you choose (stops by itself after 2 minutes). Voice: “dismiss” or “snooze”.</p>' +
        (blocked ? '<p class="small warn">Sound is blocked by the browser. ' + UI.btn("sound_enable", null, "Play sound", { cls: "tiny" }) + "</p>" : "") +
        '<div class="dlg-foot">' + UI.btn("alarm_snooze", null, "Snooze " + (a.snooze_minutes || 5) + " min", { icon: "clock" }) + UI.btn("alarm_dismiss", null, "Dismiss", { cls: "primary", icon: "check" }) + "</div>";
      if (!d.open) d.showModal();
      var b = d.querySelector(".primary"); if (b) b.focus();
      if (!timer) { burst(); timer = setInterval(burst, 1700); }
      setTimeout(function () { if (d.open) UI.actions.alarm_dismiss.run(); }, 120000);
    }
  };
  UI.actions.alarm_test = { run: function () { UI.alarm.ring(); } };
  UI.actions.alarm_dismiss = { run: function () { stopTone(); var d = document.getElementById("alarm-dlg"); if (d && d.open) d.close(); } };
  UI.actions.alarm_snooze = { run: function () { UI.actions.alarm_dismiss.run(); clearTimeout(snoozeTimer); snoozeTimer = setTimeout(function () { UI.alarm.ring(); }, 10000); UI.toast && UI.toast("Snoozed. In the kit it rings again in 10 seconds."); } };
  UI.actions.sound_enable = { run: function () {
    ctx(); setTimeout(function () { var ok = burst(); var msg = ok ? "Sound works. Alarms will ring in this tab." : "The browser is still blocking sound. Click anywhere on the page, then try again.";
      document.querySelectorAll("[data-permission-note]").forEach(function (el) { el.textContent = msg; }); UI.toast && UI.toast(msg); }, 60);
  } };
  document.addEventListener("DOMContentLoaded", function () {
    var d = document.getElementById("alarm-dlg");
    if (d) d.addEventListener("cancel", function (e) { e.preventDefault(); });   // no Esc: choose Snooze or Dismiss
  });
  ["pointerdown", "keydown"].forEach(function (ev) { document.addEventListener(ev, function () { if (actx && actx.state === "suspended") actx.resume().then(function () { setBlocked(false); }); }, true); });
})();
