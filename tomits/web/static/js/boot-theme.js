/* Runs before the page paints: apply the last known theme and layout so there
   is no flash. The server's saved choice (settings) wins once state loads. */
(function () {
  var theme = "system", layout = "1";
  try { theme = localStorage.getItem("tomits-theme") || "system"; layout = localStorage.getItem("tomits-layout") || "1"; } catch (e) {}
  var dark = theme === "dark" || (theme === "system" && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  if (/^[1-6]$/.test(layout)) {
    document.getElementById("layout-css").setAttribute("href", "/static/layouts/l" + layout + ".css");
    document.addEventListener("DOMContentLoaded", function () { document.body.setAttribute("data-layout", layout); });
  }
})();
