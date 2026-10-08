/* theme-switch.js: light / dark switch (UI_GUIDE.md §5.3).
   Saved value: localStorage "uikit.theme" = "system" | "light" | "dark".
   Resolved value: <html data-theme="light|dark">. The top-bar button toggles
   light ↔ dark; Settings offers System / Light / Dark (action set_theme). */
(function () {
  var UI = window.UI;
  function resolve(v) { return v === "dark" || (v === "system" && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light"; }
  UI.theme = {
    get: function () { return UI.store.get("uikit.theme", "system"); },
    set: function (v) { UI.store.set("uikit.theme", v); document.documentElement.setAttribute("data-theme", resolve(v)); UI.emit("theme", v); }
  };
  UI.actions.toggle_theme = { run: function () { UI.theme.set(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark"); if (UI.screen && UI.screen() === "settings") UI.render(); } };
  UI.actions.set_theme = { run: function (a) { UI.theme.set(a.value); if (UI.render) UI.render(); } };
  if (window.matchMedia) matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () { if (UI.theme.get() === "system") UI.theme.set("system"); });
})();
