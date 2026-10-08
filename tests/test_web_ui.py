"""v1.6 web app front end, checked without a browser:
- raw buttons, links and forms are wired (the registry checks are in
  test_actions_registry.py);
- every layout offers every screen;
- nothing is loaded from outside, and no demo data is left anywhere."""

import re
from pathlib import Path

import pytest

import tomits.web.actions  # noqa: F401  (attaches web handlers)
from tomits.settings import LAYOUTS
from tomits.voice import registry as R

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "tomits" / "web" / "static"
FILES = sorted(p for p in STATIC.rglob("*") if p.suffix in (".js", ".html", ".css"))
CODE = {p: p.read_text(encoding="utf-8") for p in FILES if p.suffix in (".js", ".html")}
SCREENS = ["today", "reschedule", "day", "history", "voice", "settings", "focus", "layouts"]


def action_table():
    """name -> first line of its definition (cmd / ui / change are declared there)."""
    table = {}
    src = CODE[STATIC / "js" / "actions.js"]
    block = src[src.index("var A = T.ACTIONS = {"):src.index("  };", src.index("var A = T.ACTIONS = {"))]
    for m in re.finditer(r"^ {4}(\w+): (\{[^\n]*)", block, re.M):
        table[m.group(1)] = m.group(2)
    for text in CODE.values():
        for m in re.finditer(r"T\.ACTIONS\.(\w+) = (\{[^\n]*)", text):
            table[m.group(1)] = m.group(2)
    return table


def used_actions():
    used = {}
    pats = [r'data-act="(\w+)"', r"data-act=\\\"(\w+)", r'data-form="(\w+)"', r'\bbtn\("(\w+)"', r'R\.btn\("(\w+)"',
            r'T\.trigger\("(\w+)"', r"T\.r\.btn\(\"(\w+)\""]
    for path, text in CODE.items():
        for p in pats:
            for m in re.finditer(p, text):
                used.setdefault(m.group(1), set()).add(path.name)
    return used


# The registry-versus-front-end checks (every name a control can send is a
# registry command, and each one really runs through the API) live in
# tests/test_actions_registry.py.


def test_every_raw_button_link_and_form_is_wired():
    for path, text in CODE.items():
        for m in re.finditer(r"<button\b", text):
            tag = text[m.start():m.start() + 500].split("</button>")[0]
            assert re.search(r"data-act|type=\\?\"submit\\?\"|data-close", tag), f"{path.name}: unwired <button> near {text[m.start():m.start() + 80]!r}"
        for m in re.finditer(r"<a\b", text):
            tag = text[m.start():m.start() + 300].split(">")[0]
            assert 'href="#' in tag or "href='#" in tag or 'href="\' +' in tag or "skip-link" in tag, f"{path.name}: link without an in-app target {tag!r}"
        for m in re.finditer(r"<form\b", text):
            tag = text[m.start():m.start() + 300]
            assert "data-form=" in tag, f"{path.name}: form without data-form"


def test_selects_and_inputs_with_actions_have_change_handlers():
    table = action_table()
    for text in CODE.values():
        for m in re.finditer(r'<(?:select|input)[^>]*data-act="(\w+)"', text):
            assert "change:" in table[m.group(1)], m.group(1)


@pytest.mark.parametrize("n", sorted(LAYOUTS))
def test_each_layout_offers_every_screen(n):
    js = (STATIC / "layouts" / f"l{n}.js").read_text(encoding="utf-8")
    assert (STATIC / "layouts" / f"l{n}.css").exists()
    assert f"T.layouts[{n}] = {{" in js and "frame:" in js and "today:" in js
    for screen in SCREENS:
        assert re.search(r'(nav\("|\["|href="#)' + screen + r'"', js), f"layout {n} has no way to open {screen}"
    # week and month are reached from the shared period page tabs
    assert 'href="#\' + k + \'" data-nav' in CODE[STATIC / "js" / "render.js"]


def test_every_screen_has_a_renderer():
    app = CODE[STATIC / "js" / "app.js"]
    for screen in ["reschedule", "day", "week", "month", "history", "voice", "settings", "focus", "layouts"]:
        assert re.search(r"\b" + screen + r":", app[app.index("var DEFAULTS"):app.index("T.screenTitle")]), screen


def test_shortcuts_are_listed_and_shown_on_buttons():
    actions = CODE[STATIC / "js" / "actions.js"]
    for key in ("Ctrl K", "/", "\"A\"", "\"D\"", "\"F\"", "\"S\"", "\"P\"", "\"U\"", "\"L\"", "\"V\"", "\"?\""):
        assert key in actions
    render = CODE[STATIC / "js" / "render.js"]
    for k in ('kbd: "P"', 'kbd: "A"', 'kbd: o.keys ? "D"', 'kbd: o.keys ? "F"', 'kbd: o.keys ? "S"'):
        assert k in render


def test_no_external_requests_from_the_ui():
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        for url in re.findall(r"https?://[^\s\"')]+", text):
            assert url.startswith("http://www.w3.org/2000/svg"), f"{path.name} loads {url}"
        assert "@import" not in text and "fonts.googleapis" not in text


def test_no_demo_data_left():
    assert not (ROOT / "ui-mockups" / "sample-data.js").exists()
    for path in list((ROOT / "tomits").rglob("*.py")) + FILES + [ROOT / "README.md"]:
        text = path.read_text(encoding="utf-8")
        assert "sample-data" not in text and "TOMITS_SAMPLE" not in text, path


def test_ui_has_empty_states_not_blank_space():
    render = CODE[STATIC / "js" / "render.js"]
    assert render.count("empty(") >= 6
    for layout in sorted(LAYOUTS):
        js = (STATIC / "layouts" / f"l{layout}.js").read_text(encoding="utf-8")
        assert "R.empty(" in js, f"layout {layout} has no empty state for its own today view"


# ---------- v1.7 ----------

@pytest.mark.parametrize("n", sorted(LAYOUTS))
def test_each_layout_shows_the_fixed_time_marker(n):
    """Every layout draws its tasks with a shared helper that shows the
    "Fixed time" marker (kindBadge / taskRow / kind / fixedMark)."""
    js = (STATIC / "layouts" / f"l{n}.js").read_text(encoding="utf-8")
    assert re.search(r"R\.(kindBadge|taskRow|fixedMark)\(", js), f"layout {n} never shows a task's kind"
    render = CODE[STATIC / "js" / "render.js"]
    assert 'fixed: ["Fixed time"' in render and 'timed: ["Fixed time"' in render


def test_sacrifices_have_no_edit_control():
    every = "".join(CODE.values())
    assert "edit_sacrifice" not in every and "change_sacrifice" not in every and "Edit sacrifice" not in every
    render = CODE[STATIC / "js" / "render.js"]
    assert 'btn("made_sacrifice"' in render and 'btn("remove_sacrifice"' in render


def test_duration_is_optional_in_the_task_form():
    forms = CODE[STATIC / "js" / "forms.js"]
    assert 'name="duration" required' not in forms
    assert 'data-form="choose_ampm"' in forms


# ---------- v1.8 Remember ----------

def test_notes_panel_is_shared_by_all_six_layouts():
    html = CODE[STATIC / "index.html"]
    assert 'id="notes-panel"' in html and "/static/js/notes.js" in html   # outside the layouts: every layout has it
    app = CODE[STATIC / "js" / "app.js"]
    assert "T.notes.render(st)" in app and "T.notes.banners(st)" in app


def test_notes_ui_text_is_generic():
    js = CODE[STATIC / "js" / "notes.js"]
    assert 'placeholder="Write a note"' in js
    assert re.findall(r'placeholder="([^"]+)"', js) == ["Write a note"]


def test_add_note_shortcut_is_listed_and_on_the_button():
    actions = CODE[STATIC / "js" / "actions.js"]
    assert '["N", "Add a note to Remember"]' in actions and "n: function () { T.notes.focusAdd(); }" in actions
    assert '<kbd class="kbd">N</kbd>' in CODE[STATIC / "js" / "notes.js"]
