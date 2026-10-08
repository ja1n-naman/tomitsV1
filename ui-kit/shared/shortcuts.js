/* shortcuts.js: the help overlay (?) listing every registered shortcut (UI_GUIDE.md §5.5).
   Components register keys with UI.addKey(key, label, run); this file only lists
   them. Shortcuts are ignored while typing, while a dialog is open, and (except
   V) while the alarm is open; that rule lives in core.js. */
(function () {
  var UI = window.UI;
  var ORDER = ["Ctrl K", "/", "A", "D", "F", "S", "X", "P", "N", "U", "L", "V", "G", "?", "Esc"];
  function help() {
    var keys = UI.keys.slice().sort(function (a, b) { return (ORDER.indexOf(a.key) + 1 || 99) - (ORDER.indexOf(b.key) + 1 || 99); });
    UI.overlay.open('<div class="dlg-head"><h2>Keyboard shortcuts</h2>' + UI.btn("overlay_close", null, "", { icon: "x", aria: "Close", cls: "quiet" }) + "</div>" +
      '<dl class="keys">' + keys.map(function (s) { return "<div><dt><kbd>" + UI.esc(s.key) + "</kbd></dt><dd>" + UI.esc(s.label) + "</dd></div>"; }).join("") + "</dl>" +
      '<p class="small muted">Shortcuts work when you’re not typing in a box. “Selected” is the last item you clicked; otherwise the current one, or the next one.</p>' +
      '<p class="small">Anything you can click, you can also type in the box at the top' + (UI.voice ? " or say after pressing V" : "") + ".</p>", "Keyboard shortcuts");
  }
  UI.actions.open_help = { run: help };
  UI.addKey("?", "This help", help);
  UI.addKey("Esc", "Close a dialog, overlay or panel", null, { display: true });
})();
