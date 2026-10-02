/* Remember: the notes panel on the right, shared by all six layouts.
   Notes are added and deleted only (registry commands add_note / delete_note);
   the panel's open state is a setting (notes_panel), so it is remembered. */
(function () {
  var T = window.T, I = function (n) { return T.icon(n); };
  var esc = function (s) { return T.r.esc(s); };
  var btn = function () { return T.r.btn.apply(null, arguments); };

  function noteItem(n, section) {
    return '<li class="note c-' + esc(n.color) + (section === "overdue" ? " is-past" : "") + '">' +
      '<p class="note-text">' + esc(n.text) + "</p>" +
      '<p class="note-meta">' + (n.due_label ? '<span class="note-when">' + I("clock") + esc(n.due_label) + "</span>" : "") +
      (section === "overdue" ? '<span class="note-past">past</span>' : "") + "</p>" +
      btn("delete_note", { id: n.id }, "", { icon: "trash", cls: "tiny quiet note-del", aria: "Delete note: " + n.text, title: "Delete (Undo brings it back)" }) +
      "</li>";
  }
  function section(title, list, key, empty) {
    if (!list.length) return empty ? '<section class="note-sec"><h3 class="note-h">' + title + ' <small>0</small></h3><p class="muted small">' + empty + "</p></section>" : "";
    return '<section class="note-sec note-' + key + '"><h3 class="note-h">' + title + " <small>" + list.length + "</small></h3><ul>" +
      list.map(function (n) { return noteItem(n, key); }).join("") + "</ul></section>";
  }
  function addForm(nt) {
    var full = nt.count >= nt.max;
    var colors = nt.colors.map(function (c, i) {
      return '<label class="swatch c-' + c + '" title="' + c + '"><input type="radio" name="color" value="' + c + '"' + (i ? "" : " checked") + '><span class="sr">' + c + "</span></label>";
    }).join("");
    return '<form class="note-add" data-form="add_note" data-then="note_added" data-full="' + (full ? "1" : "0") + '" autocomplete="off">' +
      '<label class="sr" for="note-text">Note</label>' +
      '<textarea id="note-text" name="text" rows="2" maxlength="' + nt.max_text + '" placeholder="Write a note" required data-keep data-counter="note-count"' + (full ? " disabled" : "") + "></textarea>" +
      '<p class="note-counter"><span id="note-count">0</span>/' + nt.max_text + "</p>" +
      '<label class="field-l small" for="note-due">Date and time (optional)</label><input id="note-due" type="datetime-local" name="due"' + (full ? " disabled" : "") + ">" +
      '<fieldset class="swatches"><legend class="sr">Colour</legend>' + colors + "</fieldset>" +
      '<p class="form-err" role="alert" hidden></p>' +
      (full ? '<p class="small warn">You have ' + nt.max + " notes, the most there can be. Delete one to add another.</p>"
        : '<button type="submit" class="btn primary tiny">' + I("plus") + 'Add note<kbd class="kbd">N</kbd></button>') + "</form>";
  }

  T.notes = {
    render: function (st) {
      var host = document.getElementById("notes-panel"), nt = st.notes;
      if (!host || !nt) return;
      var keepText = host.querySelector("#note-text") ? host.querySelector("#note-text").value : "";
      var keepDue = host.querySelector("#note-due") ? host.querySelector("#note-due").value : "";
      var focused = document.activeElement && host.contains(document.activeElement) ? document.activeElement.id : null;
      document.body.classList.toggle("notes-open", !!nt.open);
      var count = '<span class="nt-count">' + nt.count + "</span>" + (nt.overdue_count ? '<span class="nt-over" title="Overdue">' + nt.overdue_count + " overdue</span>" : "");
      if (!nt.open) {
        host.innerHTML = btn("notes_panel", { open: true }, "Remember", { icon: "pin", cls: "nt-tab", title: "Show Remember (N adds a note)" }).replace("</button>", count + "</button>");
      } else {
        var body = nt.count ? section("Overdue", nt.overdue, "overdue") + section("Upcoming", nt.upcoming, "upcoming") + section("No time", nt.no_time, "no_time")
          : '<div class="empty small"><p>Things you mustn’t forget, with or without a time. They stay here until you delete them.</p>' +
            btn("note_focus", null, "Add a note", { icon: "plus", kbd: "N" }) + "</div>";
        var full = nt.count >= nt.max ? "1" : "0", form = host.querySelector(".note-add");
        if (form && form.getAttribute("data-full") === full) {
          // the add form stays as it is (typing isn't interrupted); only the lists and counts change
          host.querySelector(".nt-title").innerHTML = "Remember " + count;
          var b = host.querySelector(".nt-body");
          b.innerHTML = body;
          T.hydrateIcons(b);
          return;
        }
        host.innerHTML = '<div class="nt-head"><h2 class="nt-title">Remember ' + count + "</h2>" +
          btn("notes_panel", { open: false }, "", { icon: "x", cls: "quiet tiny", aria: "Hide Remember" }) + "</div>" +
          addForm(nt) + '<div class="nt-body">' + body + "</div>";
        var ta = host.querySelector("#note-text");
        if (ta) { ta.value = keepText; T.notes.count(ta); }
        if (host.querySelector("#note-due")) host.querySelector("#note-due").value = keepDue;
        if (focused && document.getElementById(focused)) document.getElementById(focused).focus();
      }
      T.hydrateIcons(host);
      if (nt.open && T.notes.wantFocus && host.querySelector("#note-text")) { T.notes.wantFocus = false; host.querySelector("#note-text").focus(); }
    },
    count: function (ta) {
      var c = document.getElementById(ta.getAttribute("data-counter"));
      if (c) { c.textContent = ta.value.length; c.parentNode.classList.toggle("near", ta.value.length > 180); }
    },
    focusAdd: function () {
      var ta = document.getElementById("note-text");
      if (ta) { ta.focus(); return; }
      T.notes.wantFocus = true;   // focused as soon as the opened panel is drawn
      T.run("notes_panel", { open: true }, null, { quiet: true });
    },
    /* one desktop notification per note: the same tag in every open tab shows it once */
    notify: function (n) {
      if (!("Notification" in window) || Notification.permission !== "granted") return;
      try { new Notification("Remember", { body: n.text, tag: "tomits-note-" + n.id, silent: true, renotify: false }); } catch (e) {}
    },
    banners: function (st) {
      var nt = st.notes, out = [];
      if (!nt) return out;
      if (nt.away) out.push('<div class="banner note-banner" role="status">' + I("pin") + "<span><b>" + nt.away + " note" + (nt.away > 1 ? "s" : "") +
        " became overdue while you were away.</b> " + (nt.away > 1 ? "They’re" : "It’s") + " under Overdue in Remember.</span>" + btn("dismiss_note_banner", { id: "away" }, "Dismiss", { cls: "quiet" }) + "</div>");
      nt.banners.forEach(function (n) {
        out.push('<div class="banner note-banner" role="status">' + I("pin") + "<span><b>Remember:</b> " + esc(n.text) + (n.due_label ? " <small>(" + esc(n.due_label) + ")</small>" : "") +
          "</span>" + btn("dismiss_note_banner", { id: n.id }, "Dismiss", { cls: "quiet", title: "Hide this banner; the note stays" }) + "</div>");
      });
      return out;
    }
  };

  document.addEventListener("input", function (e) {
    if (e.target.matches && e.target.matches("textarea[data-counter]")) T.notes.count(e.target);
  });
  T.on("note-event", function (n) { T.notes.notify(n); });
})();
