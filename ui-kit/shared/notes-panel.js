/* notes-panel.js: short notes kept outside any screen (UI_GUIDE.md §5.11). Optional.
   - collapsed tab with the count (+ "N overdue"); open, the page makes room
   - open state remembered: localStorage "uikit.notesOpen"
   - add (text ≤ max_text, optional date and time, one of six colours) and delete
     only (no editing); delete has no question, Undo brings it back
   - sections: Overdue (earliest first), Upcoming (soonest first), No time (newest first)
   - N opens the panel and puts the cursor in the box; typing is never interrupted */
(function () {
  var UI = window.UI, esc = UI.esc;
  function open() { return !!UI.store.get("uikit.notesOpen", false); }
  function nowIso() { return UI.date.today() + "T" + (UI.data.now || "00:00"); }
  function due(n) { return n.due_date ? UI.date.label(n.due_date.slice(0, 10)) + " " + n.due_date.slice(11, 16) : ""; }
  function sections() {
    var items = UI.preview() === "empty" ? [] : UI.data.notes.items, now = nowIso();
    var over = items.filter(function (n) { return n.due_date && n.due_date < now; }).sort(function (a, b) { return a.due_date < b.due_date ? -1 : 1; });
    var up = items.filter(function (n) { return n.due_date && n.due_date >= now; }).sort(function (a, b) { return a.due_date < b.due_date ? -1 : 1; });
    var none = items.filter(function (n) { return !n.due_date; }).slice().reverse();
    return { all: items, over: over, up: up, none: none };
  }
  function item(n, past) {
    return '<li class="note c-' + esc(n.color) + (past ? " is-past" : "") + '"><p class="note-text">' + esc(n.text) + '</p><p class="note-meta">' +
      (n.due_date ? '<span class="note-when">' + UI.icon("clock") + esc(due(n)) + "</span>" : "") + (past ? '<span class="note-past">past</span>' : "") + "</p>" +
      UI.btn("note_delete", { id: n.id }, "", { icon: "trash", cls: "tiny quiet note-del", aria: "Delete note: " + n.text, title: "Delete (Undo brings it back)" }) + "</li>";
  }
  function sec(title, list, past) {
    if (!list.length) return "";
    return '<section class="note-sec"><h3 class="note-h">' + title + " <small>" + list.length + "</small></h3><ul>" + list.map(function (n) { return item(n, past); }).join("") + "</ul></section>";
  }
  function form(full) {
    var nt = UI.data.notes;
    return '<form class="note-add" data-form="note_add" data-full="' + (full ? 1 : 0) + '" autocomplete="off"><label class="sr" for="note-text">Note</label>' +
      '<textarea id="note-text" name="text" rows="2" maxlength="' + nt.max_text + '" placeholder="Write a note" required data-counter="note-count"' + (full ? " disabled" : "") + "></textarea>" +
      '<p class="note-counter"><span id="note-count">0</span>/' + nt.max_text + "</p>" +
      '<label class="field-l small" for="note-due">Date and time (optional)</label><input id="note-due" type="datetime-local" name="due"' + (full ? " disabled" : "") + ">" +
      '<fieldset class="swatches"><legend class="sr">Colour</legend>' + nt.colors.map(function (c, i) {
        return '<label class="swatch c-' + c + '" title="' + c + '"><input type="radio" name="color" value="' + c + '"' + (i ? "" : " checked") + '><span class="sr">' + c + "</span></label>"; }).join("") + "</fieldset>" +
      '<p class="form-err" role="alert" hidden></p>' + (full ? '<p class="small warn">You have ' + nt.max + " notes, the most there can be. Delete one to add another.</p>"
        : '<button type="submit" class="btn primary tiny">' + UI.icon("plus") + 'Add note<kbd class="kbd">N</kbd></button>') + "</form>";
  }
  function render() {
    var host = document.getElementById("notes-panel"); if (!host) return;
    var s = sections(), full = s.all.length >= UI.data.notes.max;
    var count = '<span class="nt-count">' + s.all.length + "</span>" + (s.over.length ? '<span class="nt-over" title="Overdue">' + s.over.length + " overdue</span>" : "");
    document.body.classList.toggle("notes-open", open());
    if (!open()) { host.innerHTML = UI.btn("notes_toggle", { open: true }, "Notes", { icon: "pin", cls: "nt-tab", title: "Show notes (N adds a note)" }).replace("</button>", count + "</button>"); return; }
    var body = s.all.length ? sec("Overdue", s.over, true) + sec("Upcoming", s.up) + sec("No time", s.none)
      : '<div class="empty small"><p>Short things not to forget, with or without a time. They stay here until you delete them.</p>' + UI.btn("note_focus", null, "Add a note", { icon: "plus", kbd: "N" }) + "</div>";
    var f = host.querySelector(".note-add");
    if (f && f.getAttribute("data-full") === (full ? "1" : "0")) {   // keep the form as it is; typing isn't interrupted
      host.querySelector(".nt-title").innerHTML = "Notes " + count; host.querySelector(".nt-body").innerHTML = body; return;
    }
    host.innerHTML = '<div class="nt-head"><h2 class="nt-title">Notes ' + count + "</h2>" + UI.btn("notes_toggle", { open: false }, "", { icon: "x", cls: "quiet tiny", aria: "Hide notes" }) + "</div>" + form(full) + '<div class="nt-body">' + body + "</div>";
  }
  function setOpen(v, focus) { UI.store.set("uikit.notesOpen", v); render(); if (v && focus) { var ta = document.getElementById("note-text"); if (ta) ta.focus(); } }
  UI.actions.notes_toggle = { run: function (a) { setOpen(!!a.open, a.open); } };
  UI.actions.note_focus = { run: function () { setOpen(true, true); } };
  UI.actions.note_add = { submit: function (a, form) {
    var text = (a.text || "").trim();
    if (!text) { UI.formError(form, "Write a note first."); return; }
    var ok = UI.change("Note added.", function (data) {
      data.notes.items.push({ id: Date.now(), text: text, color: a.color || "sand", due_date: a.due || null });
    });
    if (ok) { form.reset(); var c = document.getElementById("note-count"); if (c) c.textContent = "0"; var ta = document.getElementById("note-text"); if (ta) ta.focus(); }
  } };
  UI.actions.note_delete = { run: function (a) { UI.change("Note deleted.", function (data) { data.notes.items = data.notes.items.filter(function (n) { return n.id !== a.id; }); }); } };
  document.addEventListener("input", function (e) {
    var ta = e.target; if (!ta.matches || !ta.matches("textarea[data-counter]")) return;
    var c = document.getElementById(ta.getAttribute("data-counter")); if (c) { c.textContent = ta.value.length; c.parentNode.classList.toggle("near", ta.value.length > 180); }
  });
  UI.addKey("N", "Add a note", function () { setOpen(true, true); });
  UI.on("render", render);
})();
