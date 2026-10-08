/* quick-add.js: type any command (UI_GUIDE.md §5.4). Ctrl K focuses the box
   (handled in core.js so it works even while typing elsewhere). Enter sends the
   text to the voice dialog when voice-panel.js is present, otherwise it echoes
   a toast. Replace UI.actions.say with a call to your backend. */
(function () {
  var UI = window.UI;
  UI.actions.say = { submit: function (a, form) {
    var input = form.querySelector("input[name=text]"), text = (input.value || "").trim();
    if (!text) return;
    input.value = "";
    if (UI.voice && UI.voice.send) UI.voice.send(text, null);
    else if (UI.toast) UI.toast("Placeholder: “" + text + "” would be sent to the backend.");
  } };
  UI.addKey("Ctrl K", "Type a command (quick add box)", null, { display: true });
})();
