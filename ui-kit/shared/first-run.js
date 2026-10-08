/* first-run.js: first-run setup flow (UI_GUIDE.md §5.13).
   Shown once when localStorage "uikit.setupDone" isn't set; every step can be
   skipped, "Skip the whole setup" ends it, Settings can run it again.
   Steps are generic placeholders: Welcome, Preferences, Sound and notifications, Microphone. */
(function () {
  var UI = window.UI, STEPS = ["Welcome", "Preferences", "Sound and notifications", "Microphone"];
  function open(step) {
    var head = '<ol class="steps">' + STEPS.map(function (s, i) { return '<li class="' + (i === step ? "on" : i < step ? "done" : "") + '">' + (i + 1) + ". " + s + "</li>"; }).join("") + "</ol>";
    var next = function (label, primary) { return UI.btn("setup_step", { step: step + 1 }, label, { cls: primary ? "primary" : "" }); };
    var body;
    if (step === 0) body = "<p>Placeholder welcome text: one or two sentences on what the app does and that everything is saved as you go.</p>" +
      '<div class="dlg-foot">' + next("Continue", true) + "</div>";
    else if (step === 1) body = '<form data-form="setup_prefs" class="form"><p>Placeholder: the one or two settings the app can\'t work without.</p><div class="cols"><div><label class="field-l" for="su-s">Starts</label><input id="su-s" type="time" name="start" value="' + UI.data.window.start + '" required></div>' +
      '<div><label class="field-l" for="su-e">Ends</label><input id="su-e" type="time" name="end" value="' + UI.data.window.end + '" required></div></div><p class="form-err" role="alert" hidden></p>' +
      '<div class="dlg-foot">' + UI.btn("setup_step", { step: 2 }, "Skip") + '<button type="submit" class="btn primary">Save and continue</button></div></form>';
    else if (step === 2) body = "<p>Browsers stay silent until you allow sound once.</p><div class=\"row\">" + UI.btn("sound_enable", null, "Enable and test sound", { icon: "volume", cls: "primary" }) + UI.btn("setup_notify", null, "Allow notifications", { icon: "bell" }) + "</div>" +
      '<p class="small" data-permission-note></p><div class="dlg-foot">' + next("Continue", true) + "</div>";
    else body = "<p>Voice is optional; typing in the box at the top does the same.</p><div class=\"meter wide\" data-level aria-hidden=\"true\"><span></span><i></i></div><p class=\"small\" data-mictest-result></p>" +
      '<div class="row">' + UI.btn("mic_test", null, "Start mic test", { icon: "play" }) + '</div><div class="dlg-foot">' + UI.btn("setup_done", null, "Finish", { cls: "primary", icon: "check" }) + "</div>";
    UI.dlg.open("Welcome", head + body + '<p class="small muted setup-skip">' + UI.btn("setup_done", null, "Skip the whole setup", { cls: "quiet tiny" }) + "</p>", { cls: "setup" });
  }
  UI.setup = { open: open };
  UI.actions.setup_open = { run: function () { open(0); } };
  UI.actions.setup_step = { run: function (a) { if (a.step > 3) return UI.actions.setup_done.run(); open(a.step); } };
  UI.actions.setup_prefs = { submit: function (a) { UI.change("Saved.", function (data) { data.window.start = a.start; data.window.end = a.end; }, { quiet: true }); open(2); } };
  UI.actions.setup_notify = { run: function () {
    var note = function (m) { document.querySelectorAll("[data-permission-note]").forEach(function (el) { el.textContent = m; }); };
    if (!("Notification" in window)) { note("This browser can't show desktop notifications."); return; }
    Notification.requestPermission().then(function (p) { note(p === "granted" ? "Notifications are on." : "Notifications are blocked. Alarms still ring and show in the tab."); });
  } };
  UI.actions.setup_done = { run: function () { UI.store.set("uikit.setupDone", true); UI.dlg.close(); UI.toast && UI.toast("Setup finished. Run it again from Settings."); } };
  UI.on("start", function () { if (!UI.store.get("uikit.setupDone", false)) setTimeout(function () { open(0); }, 50); });
})();
