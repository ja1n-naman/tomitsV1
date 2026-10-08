/* boot.js: runs in <head> before the first paint (UI_GUIDE.md §5.2, §5.3).
   Applies the remembered theme (and, on the chooser page, the remembered
   layout's tokens) so the page never flashes the wrong look.
   The one attribute mechanism:  <html data-layout="1..6" data-theme="light|dark">
   Saved choices (localStorage, wrapped in try/catch):
     uikit.theme  "system" | "light" | "dark"      (default "system")
     uikit.layout "1".."6"                          (default "1")
     uikit.slots  "on" | "off"                      (slot labels, default "on") */
(function () {
  var root = document.documentElement, theme = "system", layout = "1", slots = "on";
  try {
    theme = localStorage.getItem("uikit.theme") || "system";
    layout = localStorage.getItem("uikit.layout") || "1";
    slots = localStorage.getItem("uikit.slots") || "on";
  } catch (e) {}
  var dark = theme === "dark" || (theme === "system" && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches);
  root.setAttribute("data-theme", dark ? "dark" : "light");
  root.setAttribute("data-slots", slots === "off" ? "off" : "on");
  // A layout page carries its own data-layout; the chooser page borrows the remembered one.
  if (!root.hasAttribute("data-layout")) root.setAttribute("data-layout", /^[1-6]$/.test(layout) ? layout : "1");
})();
