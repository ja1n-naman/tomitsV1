/* search.js: the search overlay (/) over the current data (UI_GUIDE.md §5.5). */
(function () {
  var UI = window.UI;
  function results(q) {
    var res = document.getElementById("search-res"); if (!res) return;
    var t = q.trim().toLowerCase();
    if (!t) { res.innerHTML = '<p class="muted small">Type to search items and history.</p>'; return; }
    var out = UI.allItems().filter(function (x) { return x.title.toLowerCase().indexOf(t) > -1; }).map(function (x) {
      return UI.btn("search_go", { id: x.id, offset: UI.data.days.filter(function (d) { return d.date === x.date; }).map(function (d) { return d.offset; })[0] || 0 },
        UI.esc(x.title) + " <small>" + UI.date.label(x.date) + (x.start ? " " + x.start : "") + " · " + x.status + "</small>", { cls: "sr-item" });
    }).concat(UI.data.history.filter(function (h) { return (h.title + " " + h.reason).toLowerCase().indexOf(t) > -1; }).map(function (h) {
      return UI.btn("nav", { screen: "history" }, UI.esc(h.title) + " <small>" + h.status + ": " + UI.esc(h.reason) + "</small>", { cls: "sr-item" });
    }));
    res.innerHTML = out.length ? out.join("") : '<p class="muted small">Nothing found.</p>';
  }
  function open() {
    UI.overlay.open('<div class="dlg-head"><h2>Search</h2>' + UI.btn("overlay_close", null, "", { icon: "x", aria: "Close", cls: "quiet" }) + "</div>" +
      '<label class="sr" for="search-q">Search</label><input id="search-q" class="search-q" placeholder="Search items and history" autocomplete="off"><div id="search-res" class="search-res"></div>', "Search");
    var q = document.getElementById("search-q");
    q.addEventListener("input", function () { results(q.value); });
    results("");
  }
  UI.actions.open_search = { run: open };
  UI.actions.search_go = { run: function (a) { UI.overlay.close(); UI.view.selected = a.id; UI.view.dayOffset = a.offset; UI.saveView(); UI.go(UI.layout && UI.layout.defaultScreen === "now" ? "list" : "home"); UI.render(); } };
  UI.addKey("/", "Search", open);
})();
