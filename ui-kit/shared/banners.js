/* banners.js: non-blocking banners with show-once memory (UI_GUIDE.md §5.8).
   Two kinds:
   - system banners (connection lost, sound blocked…): UI.banners.system(id, spec|null)
   - content banners from UI.data.banners, each with a mode:
       "once"            shown on one page load, then never again
       "until-dismissed" shown on every load until Dismiss
     Marks are kept in localStorage "uikit.banners" = { seen: {}, dismissed: {} }.
   Dismiss hides the banner for good; it never deletes the thing it is about. */
(function () {
  var UI = window.UI, sys = {}, shownNow = {};
  var ICON = { bad: "alert", warn: "alert", info: "cycle", note: "pin" };
  function marks() { return UI.store.get("uikit.banners", { seen: {}, dismissed: {} }); }
  function one(spec, body, actions) {
    return '<div class="banner ' + (spec.tone === "note" ? "note-banner" : spec.tone) + '" role="' + (spec.role || (spec.tone === "bad" ? "alert" : "status")) + '">' + UI.icon(spec.icon || ICON[spec.tone] || "alert") + "<span>" + body + "</span>" + (actions || "") + "</div>";
  }
  UI.banners = {
    system: function (id, spec) { if (spec) sys[id] = spec; else delete sys[id]; UI.banners.render(); },
    render: function () {
      var host = document.getElementById("banners"); if (!host) return;
      var m = marks(), out = [], changed = false;
      ["offline", "sound"].concat(Object.keys(sys)).forEach(function (id, i, arr) {
        if (sys[id] && arr.indexOf(id) === i) out.push(one(sys[id], sys[id].html, sys[id].action));
      });
      var n = UI.preview() === "empty" ? 0 : UI.data.decisions.length, where = (UI.layout && UI.layout.decisionsScreen) || "home";
      if (n && UI.screen && UI.screen() !== where)
        out.push(one({ tone: "info", icon: "cycle" }, n + " change" + (n > 1 ? "s are" : " is") + " waiting for a decision. Nothing moves until you accept.", UI.btn("nav", { screen: where }, "Review", { cls: "primary" })));
      UI.data.banners.forEach(function (b) {
        if (m.dismissed[b.id]) return;
        if (b.mode === "once" && m.seen[b.id] && !shownNow[b.id]) return;
        if (b.mode === "once" && !m.seen[b.id]) { m.seen[b.id] = true; shownNow[b.id] = true; changed = true; }
        var acts = (b.action ? UI.btn("nav", { screen: b.action.nav }, UI.esc(b.action.label), { cls: "tiny primary" }) : "") +
          UI.btn("banner_dismiss", { id: b.id }, "Dismiss", { cls: "quiet", aria: "Dismiss: " + b.text });
        out.push(one(b, UI.esc(b.text) + (b.mode === "once" ? ' <span class="ph-tag">shown once</span>' : ""), acts));
      });
      if (changed) UI.store.set("uikit.banners", m);
      host.innerHTML = out.join("");
    }
  };
  UI.actions.banner_dismiss = { run: function (a) { var m = marks(); m.dismissed[a.id] = true; UI.store.set("uikit.banners", m); UI.banners.render(); } };
  UI.actions.banners_reset = { run: function () { UI.store.set("uikit.banners", { seen: {}, dismissed: {} }); shownNow = {}; UI.banners.render(); UI.toast && UI.toast("The demo banners are back."); } };
  UI.on("render", function () { UI.banners.render(); });
})();
