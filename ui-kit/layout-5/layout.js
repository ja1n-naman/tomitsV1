/* Layout 5: Split dashboard (UI_GUIDE.md §4.5).
   Slots: status, pane-a … pane-e (each with a head and a scrolling body); other screens: pane-max. */
(function () {
  var UI = window.UI, R = UI.r, D = UI.date, esc = UI.esc, I = function (n) { return UI.icon(n); };

  function status() {
    var n = R.decisions().length;
    return '<nav class="l5-status" aria-label="Panes" data-slot="status">' + UI.navLink("home", "All panes") + UI.navLink("list", "List", { badge: n || "" }) + UI.navLink("progress", "Progress") +
      UI.navLink("history", "History") + UI.navLink("voice", "Voice") + UI.navLink("settings", "Settings") + UI.navLink("later", "Later", { cls: "dim" }) +
      '<a href="../index.html" data-act="open_layouts"><span>Layouts</span></a><span class="st-clock">' + esc(D.label(D.today(), true)) + " " + UI.data.now + "</span></nav>";
  }
  function pane(id, title, body, max, tools) {
    return '<section class="pane p-' + id + '" data-slot="pane-' + id + '" aria-labelledby="ph-' + id + '"><header class="ph"><h2 id="ph-' + id + '">' + title + "</h2>" + (tools || "") +
      (max ? '<a class="ph-max" href="#' + max + '" aria-label="Open ' + esc(title.replace(/<[^>]*>/g, "")) + ' full size">' + I("focus") + "</a>" : "") + '</header><div class="pb">' + body + "</div></section>";
  }
  function table(d) {
    var rows = d.items.concat(d.untimed);
    if (UI.preview() === "loading" || UI.preview() === "error") return UI.state("");
    if (!rows.length) return R.emptyDay(d);
    return '<table class="tbl plan"><thead><tr><th scope="col">Time</th><th scope="col">Dur</th><th scope="col">Pri</th><th scope="col">Kind</th><th scope="col">Item, and why it is there</th><th scope="col"><span class="sr">Actions</span></th></tr></thead><tbody>' +
      rows.map(function (t) {
        return '<tr class="s-' + t.status + (t.running && t.status === "pending" ? " is-now" : "") + (UI.view.selected === t.id ? " is-sel" : "") + '"><td class="mono">' + (t.start || "--:--") + '</td><td class="mono dim">' + t.duration_text +
          '</td><td class="mono p' + t.priority + '">P' + t.priority + "</td><td>" + R.kindBadge(t) + "</td><td><b>" + esc(t.title) + "</b> " + R.statusBadge(t) + R.linkChip(t) + R.why(t) + "</td>" +
          '<td class="c-a">' + R.itemActions(t, { short: true }) + UI.btn("select_item", { id: t.id }, "", { icon: "chev-right", cls: "quiet tiny", aria: "More actions for " + t.title }) + "</td></tr>";
      }).join("") + "</tbody></table>";
  }
  function progressMini() {
    if (UI.preview() !== "normal") return UI.state('<p class="small dim">No progress entries yet.</p>');
    return '<table class="tbl"><thead><tr><th scope="col">Group</th><th scope="col">Entries (value / target)</th><th scope="col">State</th></tr></thead><tbody>' + UI.data.progress.map(function (g) {
      return '<tr><th scope="row">' + esc(g.label) + "</th><td>" + (g.entries.length ? g.entries.map(function (e) { return esc(e.title) + ' <b class="mono">' + esc(R.progText(e)) + "</b>"; }).join("<br>") : '<span class="warn">nothing yet</span>') +
        '</td><td class="dim">' + (g.locked ? "read-only" : "open") + "</td></tr>";
    }).join("") + "</tbody></table>";
  }
  function voiceMini() {
    var vd = UI.data.voice, log = UI.preview() === "normal" ? vd.log.slice(0, 5) : [];
    return '<div class="vmini"><button type="button" class="mic-big" data-act="mic_toggle" aria-pressed="false" aria-label="Talk">' + I("mic") + '</button><div><p class="vphase" data-mic-phase>Ready</p><p class="small dim">Hold V to talk. Below ' + Math.round(vd.low_confidence * 100) + "% nothing happens.</p></div></div>" +
      (log.length ? '<table class="tbl"><tbody>' + log.map(function (l) {
        return '<tr class="' + (l.acted ? "" : "dim") + '"><td class="mono">' + esc(l.at) + "</td><td>“" + esc(l.text) + '”</td><td class="mono' + (l.confidence != null && l.confidence < vd.low_confidence ? " bad" : "") + '">' +
          (l.confidence != null ? Math.round(l.confidence * 100) : "–") + "</td><td>" + esc(l.interpreted || "no command") + "</td></tr>"; }).join("") + "</tbody></table>"
        : '<p class="small dim">No commands yet. Say or type one in the box at the top.</p>');
  }
  function historyMini() {
    var rows = UI.preview() === "normal" ? UI.data.history.slice(0, 8) : [];
    return rows.length ? '<table class="tbl"><tbody>' + rows.map(function (r) {
      return '<tr><td class="mono">' + esc(D.label(r.date, true)) + "</td><td><b>" + esc(r.title) + '</b></td><td class="mono ' + (r.status === "failed" ? "bad" : "dim") + '">' + (r.status === "failed" ? "FAIL" : "SKIP") + '</td><td class="small">' + esc(r.reason) + "</td></tr>";
    }).join("") + "</tbody></table>" : UI.state('<p class="small dim">Nothing failed or skipped yet.</p>');
  }
  function home() {
    var d = UI.day(UI.view.dayOffset), sel = UI.selectedItem(), n = R.decisions().length;
    var a = R.toolbar({ compact: true }) + table(d) + (sel && UI.preview() === "normal" ? '<div class="selbox"><p class="eyebrow">Selected</p>' + UI.screens.detail(sel) + "</div>" : "") + R.olderList();
    return '<div class="l5-grid">' +
      pane("a", "List · " + esc(D.label(d.date, true)), a, "list") +
      pane("b", "Progress", progressMini(), "progress") +
      pane("c", "Decisions" + (n ? ' <span class="badge">' + n + " pending</span>" : ""), n ? R.decisions().map(R.decisionCard).join("") : UI.empty("Nothing waiting for a decision. A card appears here when a change needs your OK; nothing moves until you accept."), null) +
      pane("d", "Voice", voiceMini(), "voice") +
      pane("e", "Failed / skipped", historyMini(), "history") + "</div>";
  }

  UI.start({
    id: 5, defaultScreen: "home", home: home,
    frame: function (screen, inner) {
      if (screen === "home") return '<div class="l5">' + status() + inner + "</div>";
      return '<div class="l5">' + status() + '<div class="l5-max">' + pane("max", esc(UI.TITLES[screen] || screen), inner, null,
        '<a class="ph-max" href="#home" aria-label="Back to all panes">' + I("split") + "</a>") + "</div></div>";
    }
  });
})();
