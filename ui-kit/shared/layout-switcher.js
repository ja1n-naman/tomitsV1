/* layout-switcher.js: the top-bar Layout button and the L key (UI_GUIDE.md §5.1, §5.2).
   Opens the chooser page (../index.html) and passes the current screen along, so
   picking another layout keeps you on the same screen. */
(function () {
  var UI = window.UI;
  function open() {
    var sc = UI.screen ? UI.screen() : "";
    if (sc === "now") sc = "home";
    var page = document.documentElement.getAttribute("data-page") === "chooser" ? "index.html" : "../index.html";
    location.href = page + (sc && sc !== "home" ? "#" + sc : "");
  }
  UI.actions.open_layouts = { run: open };
  UI.addKey("L", "Switch layout", open);
})();
