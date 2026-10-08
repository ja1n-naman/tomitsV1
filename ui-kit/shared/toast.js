/* toast.js: UI.toast(message, { undo, error, long }) (UI_GUIDE.md §5.7).
   At most 3 at once (oldest goes first). 5 s plain, 9 s with Undo, 15 s long;
   then a .4 s fade. Undo runs the "undo" action; U does the same from anywhere. */
(function () {
  var UI = window.UI;
  UI.toast = function (msg, o) {
    o = o || {};
    var host = document.getElementById("toasts"); if (!host) return;
    var el = document.createElement("div");
    el.className = "toast" + (o.error ? " toast-err" : "");
    el.setAttribute("role", "status");
    el.innerHTML = "<span>" + UI.esc(msg) + "</span>" + (o.undo ? UI.btn("undo", { id: o.undo }, "Undo", { icon: "undo", kbd: "U" }) : "");
    host.appendChild(el);
    while (host.children.length > 3) host.firstChild.remove();
    var ms = o.long ? 15000 : o.undo ? 9000 : 5000;
    setTimeout(function () { el.classList.add("out"); }, ms);
    setTimeout(function () { el.remove(); }, ms + 500);
  };
})();
