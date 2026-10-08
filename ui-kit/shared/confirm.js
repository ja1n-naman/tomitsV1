/* confirm.js: confirmation prompt for risky actions (UI_GUIDE.md §5.9).
   UI.confirm(readback, onYes): a dialog titled "Please confirm" with the exact
   read-back, "No, keep everything" first and a danger "Yes, go ahead". In a real
   app the read-back text comes from the backend's "needs confirmation" answer. */
(function () {
  var UI = window.UI, pending = null;
  UI.confirm = function (readback, onYes) {
    pending = onYes;
    UI.dlg.open("Please confirm", '<form data-form="confirm_yes" class="form"><p class="readback">' + UI.esc(readback) + "</p>" +
      UI.dlg.foot("Yes, go ahead", { danger: true, cancel: "No, keep everything" }) + "</form>",
      // Kit: focus the safe choice. (The original focuses the danger button first; see guide §8.)
      { onOpen: function (d) { var c = d.querySelector(".dlg-foot [data-close]"); if (c) c.focus(); } });
  };
  UI.actions.confirm_yes = { submit: function () { var fn = pending; pending = null; UI.dlg.close(); if (fn) fn(); } };
})();
