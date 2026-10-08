# UI kit: six layouts, one shell

This is a working starter kit for the six layouts in `../UI_GUIDE.md`. It uses plain HTML, CSS and JavaScript:

- no build step, no framework, no installs;
- no network requests: no CDN fonts, scripts or analytics;
- all sample content is generic placeholder text.

## Open it

Double-click **`index.html`**. It opens the layout chooser. Pick a layout, or open `layout-N/index.html` directly.

On the first visit a short first-run setup appears. Skip it, or click through it.

Try these on any layout:

| Key | Does |
|---|---|
| `?` | Shortcuts |
| `L` | Switch layout |
| Theme button | Light / dark |
| `Ctrl K` | Quick add |
| `V` | Fake mic |
| `N` | Notes |
| `U` | Undo |
| `G` | Show or hide the slot labels |

**Settings → Kit preview** shows every screen as normal, empty, loading or error. It can also simulate a lost connection, ring the alarm, bring back the demo banners and rerun the first-run setup.

Tested in headless Chromium. It uses `color-mix()`, `:has()` and `<dialog>`, which current Chrome, Edge, Firefox and Safari all support (2024 or later).

## How switching works

Switching uses one attribute mechanism on `<html>`:

```html
<html data-layout="3" data-theme="dark">
```

- `data-layout` is written into each layout page. The chooser page borrows the remembered value.
- `data-theme` is set before the first paint by `shared/boot.js`, from the saved choice.
- `tokens.css` holds the shared tokens on `:root`, then one block per layout: `:root[data-layout="N"]` for light and `:root[data-layout="N"][data-theme="dark"]` for dark.
- At runtime the voice panel also sets `data-mic`. It is one of `idle`, `listening`, `thinking`, `asking` or `muted`.

**What is remembered.** Everything is stored in `localStorage`, and every read and write is wrapped in try/catch.

| Key | Values |
|---|---|
| `uikit.theme` | `system`, `light` or `dark` |
| `uikit.layout` | `1` to `6` |
| `uikit.notesOpen` | open or closed |
| `uikit.banners` | which banners were seen or dismissed |
| `uikit.slots` | slot labels on or off |
| `uikit.muted` | mic muted |
| `uikit.setupDone` | first-run setup finished |

The current view (selected item, filters, preview state) is kept per tab in `sessionStorage`.

In a real app, theme, layout and the notes panel's state belong in your backend's settings. Keep the `localStorage` copy only for the no-flash boot.

## Folders, mapped to the guide

| Path | What | Guide |
|---|---|---|
| `index.html` | layout chooser | §5.2 |
| `tokens.css` | every token: shared + per layout, light and dark | §3 |
| `base.css` | reset, type, buttons, forms, panels, empty states, item row, decision card, progress, history, settings, dialog, overlay, slot labels, reduced motion | §3, §5.9, §5.13–5.15, §6 |
| `demo-content.js` | **all** placeholder content | §7.1 |
| `shared/boot.js` | applies the theme (and the chooser's layout) before paint | §5.2, §5.3 |
| `shared/icons.js` | the SVG icon sprite | §3.8 |
| `shared/core.js` | data copy, save / undo stand-in, action wiring, dialog, overlay, shortcut registry, router | §5, §7.2 |
| `shared/screens.js` | screen patterns: list, detail, progress, history, settings, later; item building blocks | §6 |
| `shared/topbar.css` | top bar | §5.1 |
| `shared/theme-switch.js` | light / dark switch | §5.3 |
| `shared/layout-switcher.js` | Layout button and the `L` key | §5.1, §5.2 |
| `shared/quick-add.*` | command box and its mic button | §5.4 |
| `shared/shortcuts.*` | help overlay | §5.5 |
| `shared/search.js` | search overlay | §5.5 |
| `shared/saved-indicator.*` | Saved / Offline, and the save-failed banner | §5.6 |
| `shared/toast.*` | undo toast | §5.7 |
| `shared/banners.*` | non-blocking banners, show once | §5.8 |
| `shared/confirm.js` | confirmation prompt | §5.9 |
| `shared/voice-panel.*` | conversation panel, fake mic, transcript log, mic test | §5.10 |
| `shared/notes-panel.*` | collapsible notes panel | §5.11 |
| `shared/alarm.*` | alarm popup, Web Audio tone | §5.12 |
| `shared/first-run.*` | first-run setup flow | §5.13 |
| `layout-N/index.html` | the page shell (identical in all six) | §5.1 |
| `layout-N/layout.css` | that layout's frame and overrides | §4.N |
| `layout-N/layout.js` | that layout's frame, navigation and home screen | §4.N |

Every frame region has a `data-slot="…"` attribute with the slot names used in guide §4. Press **G** to see them outlined.

## Copy one layout into another project

1. Copy `tokens.css`, `base.css`, `shared/` and one `layout-N/` folder.
2. In `tokens.css`, keep `:root` and that layout's two blocks. Delete the other layouts' blocks.
3. Keep `layout-N/index.html` as your page shell. It loads, in order:
   1. `boot.js`;
   2. the CSS files;
   3. `demo-content.js`, `icons.js`, `core.js`, `screens.js`;
   4. the components;
   5. `layout.js`.

   Fix the `../` paths if you move files around.
4. Replace the stand-ins with calls to your backend:
   - `UI.data` and `UI.change()` in `core.js`: read your state; send one named action per change, then show Saved and Undo from the answer;
   - `UI.actions.*` in `screens.js` and the components;
   - `decide()` and `hear()` in `voice-panel.js`.

   Guide §7 lists the data shapes the UI expects.
5. Replace the generic screens in `shared/screens.js` with your app's screens, keeping the patterns (§6). In `layout.js`, change the navigation labels and the `home()` function.

To drop a component (voice, notes, alarm, search, first-run…):
1. delete its `shared/<name>.js` and `.css`;
2. remove its `<link>` and `<script>` lines;
3. remove its host element (for example `#conv`, `#notes-panel`, `#alarm-dlg`) and any buttons that point to it (for example the mic button).

Other files only call components through checks like `UI.toast && UI.toast(…)`, so nothing else breaks.

## Delete the demo content

All sample content is in **`demo-content.js`** and nowhere else. Every item, note, banner, history row, voice phrase and app label in that file is a placeholder.

- **For an empty app:** replace the object with your data in the same shapes, or with empty arrays. Every screen then shows its empty state.
- **To remove the demo completely:** delete the file and its `<script>` line. `core.js` falls back to empty data.

UI wording (button labels, empty-state sentences) lives in `shared/screens.js` and the layout files. Edit it there.

## Differences from the original app

Guide §4.7 lists them, and §8 explains each fix. The kit fixes these:
- contrast of text on `--bad` and `--now` in dark;
- reduced motion everywhere;
- top-bar offsets in layouts 1 and 2;
- the layout 3 drawer head being hidden under the top bar;
- banner buttons hidden under the notes tab;
- focus on the safe button in confirmations;
- focus rings on date inputs.
