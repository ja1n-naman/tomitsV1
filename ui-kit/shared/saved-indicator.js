/* saved-indicator.js: Saving… → Saved → idle, plus Offline / Not saved, and the
   red save-failed banner when the connection is lost (UI_GUIDE.md §5.6).
   UI.saved(state, text): state = idle | saving | saved | error | offline. */
(function () {
  var UI = window.UI, timer;
  var TEXT = { idle: "Saved", saving: "Saving…", saved: "Saved", error: "Not saved", offline: "Offline" };
  UI.saved = function (state, text) {
    var el = document.getElementById("saved"), t = document.getElementById("saved-text");
    if (!el) return;
    el.setAttribute("data-state", state);
    if (t) t.textContent = text || TEXT[state] || "";
    clearTimeout(timer);
    if (state === "saved") timer = setTimeout(function () { el.setAttribute("data-state", "idle"); }, 4000);
  };
  UI.on("connection", function (on) {
    UI.saved(on ? "idle" : "offline");
    if (!UI.banners) return;
    if (on) UI.banners.system("offline", null);
    else UI.banners.system("offline", { tone: "bad", role: "alert", icon: "alert",
      html: "<b>Can't reach the app.</b> Changes aren't being saved right now. Anything you typed stays on screen.",
      action: UI.btn("retry", null, "Try again") });
  });
  UI.actions.retry = { run: function () { UI.setOnline(true); UI.render(); } };
})();
