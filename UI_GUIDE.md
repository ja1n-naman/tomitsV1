# UI guide: six desktop layouts and one shared shell

This guide documents six page layouts and the shell components they share, so the same six UIs can be rebuilt in a different project. Every value here was taken from the original CSS, HTML and JavaScript. Where a value could not be read from the code, it says **could not confirm**.

The guide only describes the UI. It contains no backend design, no database and no API. It is written for an AI agent (or a developer) building a different planner-style app. That app's screens will be different, so each layout is described as a **skeleton with named slots**, and any screen can be dropped into those slots.

A working starter kit sits next to this file in `ui-kit/`. It uses plain HTML, CSS and JavaScript, with no build step and no network requests. Open `ui-kit/index.html` by double-clicking it.

---

## 1. How to use this guide

**Who this is for.** This is for an agent rebuilding these layouts in a new app whose stack is unknown. The reference implementation is plain HTML, CSS and JavaScript. If the new project uses a framework, port the structure and tokens, not the code.

**Work in this order.** Finish each step before starting the next.

1. **Read section 2 (principles).** It explains why the six look like one family and lists what never to do. Most rebuild mistakes are in that list.
2. **Copy the tokens (section 3).** Use `ui-kit/tokens.css` as the source of truth. Put the shared token names in one place and each layout's overrides in its own block, for light and for dark. Don't invent new colours. If you need one, derive it with `color-mix()` from an existing token, the way the originals do.
3. **Build the shell once (section 5).** Build the shell before any layout. It includes the top bar with the layout and theme buttons, quick add, the Saved indicator, banners, toasts, dialogs, the help overlay, and the optional voice, notes and alarm panels. Every layout reuses the same shell. Layouts only arrange it and restyle it through tokens.
4. **Build one layout end to end (section 4).** Start with layout 1. It is the most conventional, and the others are easier to check against it. Fill every slot with your app's real screens using the patterns in section 6.
5. **Add the other five layouts.** Each one must use a different skeleton, not the same skeleton with different colours (section 2).
6. **Connect data (section 7).** The UI expects a small set of data shapes and a "something changed" push. Keep all wording and rules on the backend. The UI only displays and sends actions.
7. **Check accessibility (section 8),** then tick the **rebuild checklist (section 9)** for every screen, in both themes, in all six layouts.

**One attribute mechanism.** Everything that switches is an attribute on `<html>`:

| Attribute | Values | Set by | Used for |
|---|---|---|---|
| `data-layout` | `1` to `6` | the page, or the boot script | which token block applies, and which layout CSS styles the frame |
| `data-theme` | `light`, `dark` | the boot script and the theme switch (the saved choice may be `system`, which resolves to one of these) | light or dark token values |
| `data-mic` | `idle`, `listening`, `thinking`, `asking`, `muted` | the voice panel | mic button colours and labels |

In the original app, `data-layout` sits on `<body>` and one layout stylesheet at a time is swapped in through a `<link id="layout-css">`. The kit puts `data-layout` on `<html>`, keeps all token blocks in one `tokens.css` scoped by `[data-layout]`, and gives each layout its own page. That is the one deliberate structural difference; section 4 lists the rest. The visual result is the same.

**Where the kit maps to this guide**

| Guide section | Kit file(s) |
|---|---|
| 3 Design tokens | `ui-kit/tokens.css` |
| 2, 8 Base look, focus, reduced motion | `ui-kit/base.css` |
| 4 Layout skeletons | `ui-kit/layout-1/` … `ui-kit/layout-6/` (`index.html`, `layout.css`, `layout.js`) |
| 5 Shell components | `ui-kit/shared/*.js` and `*.css`, one pair per component |
| 5 Layout chooser | `ui-kit/index.html` |
| 6 Screen patterns | `ui-kit/shared/screens.js` |
| 7 Data shapes | `ui-kit/demo-content.js` (the shapes, filled with placeholders) |
| Screenshots | `ui-guide-images/`: kit only, with placeholder content |

**Screenshots** (`ui-guide-images/`, 1440 × 900):

| Files | What they show |
|---|---|
| `layout-N-light.png`, `layout-N-dark.png` | each layout's home screen |
| `layout-N-slots.png` | the same with slot labels on |
| `chooser-*.png` | the layout chooser |
| `component-*.png` | shell components |
| `screen-*.png` | screen patterns |
| `state-empty.png` | an empty state |
| `layout-3-dark-drawer.png`, `layout-4-light-sheet.png`, `layout-6-dark-conversation.png` | how other screens open in those layouts |

**Desktop only.** The originals set `body { min-width: 1024px }` and have **no width media queries at all**: no responsive breakpoints, no mobile layout. The target is a desktop window of 1280px and wider. The 1280px figure comes from the brief. **Could not confirm** it in the code: no rule mentions 1280, and the only width rule is the 1024px minimum. Several frames assume roughly 1280px or more: layout 3's five columns, layout 5's three panes, and layout 6's three columns.

---

## 2. Design principles: why the six feel like one family

**What they share**

1. **One token vocabulary.** Every colour in every layout uses the same 16 token names:
   - surfaces: `--bg`, `--surface`, `--surface-2`;
   - text: `--ink`, `--muted`;
   - borders: `--line`, `--line-2`;
   - accent: `--accent`, `--accent-ink`, `--accent-soft`;
   - states: `--bad`, `--bad-soft`, `--ok`, `--warn`, `--warn-soft`;
   - focus: `--focus`.

   Type and shape use four more: `--font`, `--display`, `--mono`, `--radius`. A layout changes the values, never the meaning. A shared component written once therefore looks native in all six.
2. **The shell never moves.** Every layout has the same top bar, in the same order:
   1. brand;
   2. Layout button;
   3. quick add, with its mic;
   4. Search;
   5. Saved;
   6. theme button;
   7. help.

   The same banners, toasts, dialogs and notes tab appear everywhere. A layout may restyle the bar (transparent in 4, black in 5) but never removes or reorders it.
3. **Same components, same wording, same actions.** Buttons, item rows, empty states, forms and confirmation prompts are built by one shared set of functions. A layout composes them and never rewrites them. In the original, `render.js` and `forms.js` hold all of them.
4. **Flat and bordered, not floating.** Surfaces are separated by 1px lines (`--line`, `--line-2`). Shadows appear only on things that float above the page:
   - dialogs: `0 20px 50px rgba(0,0,0,.25)`;
   - the conversation panel: `0 12px 30px rgba(0,0,0,.18)`;
   - the notes tab: `0 1px 4px rgb(0 0 0 / .12)`.

   Everything else uses an inset bar or a 1px ring for emphasis, such as `inset 3px 0 0 var(--accent)` or `0 0 0 1px var(--accent)`.
5. **Colour carries state, and the same states everywhere:**
   - accent: selected, current, primary;
   - `--bad`: failed or error, often as a diagonal hatch;
   - `--warn`: needs attention, pinned, a question being asked;
   - `--ok`: saved or done;
   - `--muted`: secondary.

   Layouts 1 and 2 add a `--now` colour for the current time line.
6. **System fonts only.** No web fonts are downloaded. Each layout picks a system font stack with a particular character (section 3.2). The stacks are Windows-first (Segoe UI, Bahnschrift, Corbel, Franklin Gothic, Georgia, Cascadia Mono), with fallbacks.
7. **Numbers line up.** Times, durations and counts use the mono stack or `font-variant-numeric: tabular-nums`.
8. **Small, exact type.** Body text is 13 to 15.5px. Labels are 11 to 12.5px, often uppercase with letter-spacing .04em to .14em. Only layout 4 uses large display type (64px).
9. **One icon set.** Inline SVG on a 24px grid, stroke 1.75, round caps and joins, `currentColor`. Never emoji.
10. **Every action is explained and reversible.** Failed items show their reason. Risky actions show a read-back first. Every change gives an Undo toast. Nothing is saved only in the browser.

**Habits to avoid.** The originals avoid all of these. So must the rebuild.

- No purple-to-blue (or any decorative) gradients. The only gradients are functional:
  - diagonal hatches for failed items or "no time" columns;
  - a short accent-to-surface fade marking a timeline block (layout 1) or the current row (layout 4);
  - the hour-line pattern (layout 2).
- No emoji as icons, labels or status markers. Use the SVG set.
- No glassmorphism: no `backdrop-filter`, no translucent blurred panels. Overlays use a plain dim backdrop, `rgba(10,14,20,.45)` to `.5`.
- No cream backgrounds with serif headings everywhere. Only layout 4 uses a serif, and only for titles. Its background is a pale grey-green (`#f3f5f4`), not cream.
- No neon glow. No coloured `box-shadow` blur. Rings are hard 1 to 2px.
- No generic card grids with big shadows. The board (layout 3) uses cards, but with hard 1.5px ink borders, a coloured top band and no shadow.
- No lorem ipsum. Placeholder text is short, plain and labelled as a placeholder.
- No two layouts sharing a skeleton. Each one differs in **where navigation lives** and **how the main area is divided** (see the table in section 4).
- Avoided on purpose:
  - big rounded "pill everything", except layout 4, where it is that layout's personality;
  - auto-dismissing confirmations;
  - spinners for whole pages;
  - modal popups for reminders (reminders are banners, shown once);
  - colour as the only signal (states also have a word: "Failed", "past", "Now");
  - hover-only controls;
  - icon-only buttons without an `aria-label`.
- No sound or motion that ignores the user. Animations stop under `prefers-reduced-motion`. The alarm tone needs a click first, because browsers require it, and the page says so.

---

## 3. Design tokens

All values are exact copies from the original CSS: `css/base.css` for the shared set, and `layouts/l1.css` to `l6.css` for each layout. The kit holds all of them in `ui-kit/tokens.css`.

### 3.1 Shared token set (fallback values)

These sit on `:root` in the shared stylesheet. Every layout redefines all 16 colour tokens for light and dark, so these values only show if a layout block is missing. **The shared set has no dark values.** Dark exists only per layout.

| Token | Value | Role |
|---|---|---|
| `--bg` | `#fff` | page background |
| `--surface` | `#fff` | cards, panels, bars, inputs |
| `--surface-2` | `#f4f6f8` | secondary surface: sidebars, rails, chips, hover fills |
| `--ink` | `#15191e` | main text; also the "selected" outline |
| `--muted` | `#59636e` | secondary text, labels, icons |
| `--line` | `#dde2e7` | hairline borders and dividers |
| `--line-2` | `#c3cad2` | stronger borders: inputs, buttons, dialogs |
| `--accent` | `#0b6e63` | primary action, current item, progress, links |
| `--accent-ink` | `#fff` | text on accent |
| `--accent-soft` | `#e2f1ee` | accent tint: selected backgrounds, info banners |
| `--bad` | `#b3261e` | failed, error, destructive |
| `--bad-soft` | `#fbe9e7` | error tint |
| `--ok` | `#1b7a43` | saved, done |
| `--warn` | `#8a5800` | attention, pinned, question |
| `--warn-soft` | `#fdf2d9` | warning tint, read-back box |
| `--focus` | `#0b57d0` | keyboard focus ring |
| `--font` | `"Segoe UI", system-ui, -apple-system, Arial, sans-serif` | body font stack |
| `--display` | `var(--font)` | headings font stack |
| `--mono` | `"Cascadia Mono", Consolas, monospace` | times, durations, keys |
| `--radius` | `4px` | corner radius of controls and panels |

Hard-coded colours the components use directly, not through tokens:

| Where | Value |
|---|---|
| Text on the danger button, error toast, listening mic button, alarm bell, layout 4 dock badge | `#fff` |
| Dialog backdrop | `rgba(10, 14, 20, .5)` |
| Overlay backdrop (help, search) | `rgba(10, 14, 20, .45)` |
| Layout 3 drawer scrim | `rgba(23, 27, 21, .45)` |
| Layout 5 top-bar button borders | `rgba(255,255,255,.25)` |
| Layout 5 top bar in dark | `#000` |
| Layout 3 badge text on mustard | `#1c1400` |
| Layout 1 "now" label text in dark | `#2b1203` (light uses `#fff`) |
| Note colours, mixed into `--surface` | sand `#c9a96e` 22%, sage `#8fae8b` 24%, sky `#7fa6c4` 24%, lilac `#a796c4` 24%, rose `#c49393` 24%, slate `#8c96a0` 24% |
| Note banner | `color-mix(in srgb, #a796c4 16%, var(--surface))`, border `#a796c4` 50% mixed into `--line` |

Derived colours always use `color-mix(in srgb, …)`. Examples:
- warn banner border: `color-mix(in srgb, var(--warn) 45%, transparent)`;
- info banner border: accent at 40%;
- failed item border: `var(--bad)` at 40% mixed into `--line`;
- danger-zone panel border: `var(--bad)` at 40% mixed into `--line`.

### 3.2 Colour tokens per layout: light (`:root[data-layout="N"]`)

| Token | 1 Timeline | 2 Calendar grid | 3 Board | 4 Focus on now | 5 Split dashboard | 6 Voice first |
|---|---|---|---|---|---|---|
| `--bg` | `#ffffff` | `#eef1f5` | `#d6dcd1` | `#f3f5f4` | `#d9dde2` | `#ffffff` |
| `--surface` | `#ffffff` | `#ffffff` | `#ffffff` | `#fbfcfb` | `#ffffff` | `#ffffff` |
| `--surface-2` | `#f2f5f5` | `#f6f8fb` | `#e6eae1` | `#eef1ef` | `#f4f6f8` | `#f4f5f7` |
| `--ink` | `#10232a` | `#141922` | `#171b15` | `#1a2a23` | `#111418` | `#11151b` |
| `--muted` | `#52666d` | `#556071` | `#4f574b` | `#5a6962` | `#58616b` | `#59636f` |
| `--line` | `#dbe3e5` | `#dde2ea` | `#b5bdae` | `#d6deda` | `#c9cfd6` | `#e1e4e9` |
| `--line-2` | `#b6c4c8` | `#c3cad6` | `#171b15` | `#b9c4bf` | `#a9b1bb` | `#c4cad3` |
| `--accent` | `#0b7366` | `#1f56d1` | `#2c6a4a` | `#2b6a4e` | `#c2410c` | `#c8401a` |
| `--accent-ink` | `#ffffff` | `#fff` | `#fff` | `#fff` | `#fff` | `#ffffff` |
| `--accent-soft` | `#e2f2ef` | `#e3ebff` | `#dff0e6` | `#e1eee7` | `#fdeee6` | `#fdebe5` |
| `--bad` | `#b3261e` | `#c0262d` | `#b0301d` | `#a83226` | `#b42318` | `#b42318` |
| `--bad-soft` | `#fbe9e7` | `#fdeaea` | `#f8e1dc` | `#f6e3e0` | `#fde8e6` | `#fde8e6` |
| `--ok` | `#1d7a3d` | `#18794e` | `#2c7a33` | `#2b6a4e` | `#157f3b` | `#1b7a43` |
| `--warn` | `#8a5a00` | `#9a5b00` | `#8a5f00` | `#8a5800` | `#a15c00` | `#995c00` |
| `--warn-soft` | `#fdf3dc` | `#fff3d6` | `#fbefcc` | `#f7ecd3` | `#fff1d6` | `#fff2d9` |
| `--focus` | `#0b63c4` | `#1f56d1` | `#1d4ed8` | `#1f5fbf` | `#0b57d0` | `#1a5fd0` |

### 3.3 Colour tokens per layout: dark (`:root[data-layout="N"][data-theme="dark"]`)

| Token | 1 Timeline | 2 Calendar grid | 3 Board | 4 Focus on now | 5 Split dashboard | 6 Voice first |
|---|---|---|---|---|---|---|
| `--bg` | `#0e1619` | `#0f1115` | `#141612` | `#111312` | `#05070a` | `#0e1013` |
| `--surface` | `#131e22` | `#171a20` | `#272b23` | `#161917` | `#0e1217` | `#171a20` |
| `--surface-2` | `#0b1316` | `#1d2128` | `#1c1f19` | `#1c1f1d` | `#131820` | `#13161b` |
| `--ink` | `#e2ecee` | `#e5e8ee` | `#ebeee5` | `#ece7de` | `#d9dfe6` | `#e9ecf1` |
| `--muted` | `#98aaaf` | `#9ba4b3` | `#a5ad9d` | `#a19d94` | `#8893a0` | `#9ba4b1` |
| `--line` | `#22333a` | `#262b34` | `#3a4035` | `#2b2e2c` | `#222a34` | `#262b33` |
| `--line-2` | `#3a5057` | `#3a414d` | `#6a7362` | `#45494a` | `#36414e` | `#3b424d` |
| `--accent` | `#46c2b0` | `#7aa3ff` | `#8fd3ad` | `#e3b266` | `#f0a020` | `#ff7a57` |
| `--accent-ink` | `#062520` | `#0b1a3d` | `#10231a` | `#1e1607` | `#1c1203` | `#2a0d03` |
| `--accent-soft` | `#143430` | `#1b2847` | `#1b3127` | `#2c2416` | `#2b2110` | `#3a1c13` |
| `--bad` | `#ff8a80` | `#ff7f7f` | `#ff8670` | `#f08a7c` | `#f2786c` | `#ff8a7a` |
| `--bad-soft` | `#3a1714` | `#3a1618` | `#3c1b15` | `#351b17` | `#2d1513` | `#3a1915` |
| `--ok` | `#6fd28f` | `#5fd39a` | `#84d18a` | `#b9d48f` | `#5cc98a` | `#6fd39a` |
| `--warn` | `#f0bd5e` | `#f2b84b` | `#f1c04a` | `#e9b65c` | `#f0b44c` | `#f2b955` |
| `--warn-soft` | `#33280f` | `#33270f` | `#3a2f10` | `#2e2512` | `#2b2110` | `#30250f` |
| `--focus` | `#7cb8ff` | `#9bbcff` | `#8db4ff` | `#9fc2ff` | `#8ab4f8` | `#8fb6ff` |

Each layout also sets `color-scheme: light` or `dark` in the matching block, so native controls (date pickers, scrollbars, checkboxes) follow the theme.

### 3.4 Extra tokens only some layouts define

| Layout | Theme | Token | Value |
|---|---|---|---|
| 1 Timeline | light | `--now` | `#c2410c` |
| 1 Timeline | dark | `--now` | `#ff9a5c` |
| 2 Calendar grid | light | `--now` | `#e0451f` |
| 2 Calendar grid | light | `--fixed-bg` | `#253049` |
| 2 Calendar grid | light | `--fixed-ink` | `#f3f6ff` |
| 2 Calendar grid | light | `--auto-bg` | `#dce7ff` |
| 2 Calendar grid | light | `--auto-ink` | `#12357f` |
| 2 Calendar grid | dark | `--now` | `#ff7a52` |
| 2 Calendar grid | dark | `--fixed-bg` | `#3a4766` |
| 2 Calendar grid | dark | `--fixed-ink` | `#eef2ff` |
| 2 Calendar grid | dark | `--auto-bg` | `#1c2a4c` |
| 2 Calendar grid | dark | `--auto-ink` | `#c6d6ff` |
| 3 Board | light | `--mustard` | `#d39400` |
| 3 Board | light | `--mustard-soft` | `#fbefcc` |
| 3 Board | light | `--fixed` | `#3b5870` |
| 3 Board | dark | `--mustard` | `#f1c04a` |
| 3 Board | dark | `--mustard-soft` | `#3a2f10` |
| 3 Board | dark | `--fixed` | `#a9c3d8` |
| 6 Voice first | light | `--me` | `#11151b` |
| 6 Voice first | light | `--me-ink` | `#fff` |
| 6 Voice first | dark | `--me` | `#2c333e` |
| 6 Voice first | dark | `--me-ink` | `#f1f3f6` |

What they are for:
- `--now`: the current-time line and the current block (layouts 1 and 2).
- `--fixed-bg`, `--fixed-ink`, `--auto-bg`, `--auto-ink`: solid tile fills for two item kinds (layout 2).
- `--mustard`, `--mustard-soft`, `--fixed`: the "now" column and card bands (layout 3).
- `--me`, `--me-ink`: the user's speech bubble (layout 6).
- Layout 4 also defines `--serif: Georgia, "Sitka Display", "Iowan Old Style", "Palatino Linotype", serif` and sets `--display: var(--serif)`.

### 3.5 Typography

**Font stacks and radius per layout.** "(base)" means the layout keeps the shared value.

| Layout | `--font` (body) | `--display` (headings) | `--mono` | `--radius` |
|---|---|---|---|---|
| 1 Timeline | `"Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system, Arial, sans-serif` | `"Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif` | `"Cascadia Mono", Consolas, monospace (base)` | `4px` |
| 2 Calendar grid | `Bahnschrift, "DIN Alternate", "Roboto Condensed", "Arial Narrow", "Segoe UI", sans-serif` | `var(--font)` | `"Cascadia Mono", Consolas, monospace (base)` | `1px` |
| 3 Board | `Corbel, "Gill Sans", "Gill Sans MT", Calibri, "Segoe UI", sans-serif` | `"Franklin Gothic Medium", "Franklin Gothic", "Arial Narrow", sans-serif` | `"Cascadia Mono", Consolas, monospace (base)` | `4px` |
| 4 Focus on now | `"Segoe UI", system-ui, -apple-system, Arial, sans-serif` | `var(--serif)` | `"Cascadia Mono", Consolas, monospace (base)` | `10px` |
| 5 Split dashboard | `"Segoe UI", system-ui, Arial, sans-serif` | `var(--font)` | `"Cascadia Mono", "Cascadia Code", Consolas, monospace` | `0` |
| 6 Voice first | `"Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system, Arial, sans-serif` | `"Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif` | `"Cascadia Mono", Consolas, monospace (base)` | `10px` |

**Base text:** `body { font: 14px/1.5 var(--font) }`. Layouts change only the size: layout 3 uses 15px, layout 4 15.5px, layout 5 13px, layout 6 15px. Layouts 1 and 2 keep 14px. Layout 2 adds `font-variant-numeric: tabular-nums`. Layout 3 adds `lining-nums tabular-nums`.

**Weights used:** 400, 500 (buttons, tabs), 600 (titles, labels, current nav; by far the most common), 700 (status tags, layout 5 headings, layout 3 card titles). Layout 3 card titles are 700 at 16px, and 20px for the current card.

**Line heights:** 1.5 body. Fixed ones:
- screen title `22px/1.25`;
- dialog title `19px/1.3`;
- layout 2 tiles `12px/1.3`;
- layout 4 titles `64px/1.06`, `40px/1.1`, `30px/1.2`;
- layout 6 context title `19px/1.2`;
- layout 3 card title line-height 1.2.

**Shared type scale** (`base.css`):

| Use | Size / weight |
|---|---|
| Screen title (`.screen-title`) | 600 22px/1.25 `--display` |
| Dialog title | 600 19px/1.3 `--display` |
| Decision card / section card title | 600 17px `--display` |
| Brand in top bar | 600 17px `--display` |
| Alarm title | 600 24px `--display` |
| Stat value | 600 18px `--display` |
| Body | 14px |
| Item title (`.task-title`) | 600 14.5px |
| Buttons | 500 13px |
| Banner text, toast text | 13.5px |
| Panel header (`.panel-h`) | 600 13px uppercase, letter-spacing .05em, `--muted` |
| Eyebrow label (`.eyebrow`) | 600 11px uppercase, letter-spacing .09em, `--muted` |
| Small text (`.small`) | 12.5px |
| Hints | 12px |
| Status tag (`.st`) | 700 11px uppercase, letter-spacing .05em |
| Kind badge (`.kind`) | 600 11.5px |
| Time and duration | 12.5px `--mono` (time 600 `--ink`) |
| `kbd` | 11px `--mono`, 1px `--line-2` border (2px bottom), radius 3px |

**Per-layout title overrides:**

| Layout | Title style |
|---|---|
| 1 | 26px |
| 2 | 18px |
| 3 | `--display` uppercase, letter-spacing .01em, 24px |
| 4 | 64px serif on the home screen, 40px serif on sheets |
| 5 | 700 16px `--mono`, uppercase, letter-spacing .04em |
| 6 | shared 22px |

### 3.6 Spacing

There is no named spacing scale in the code (**could not confirm** a token set; spacing is written in pixels). The values actually used, by frequency, form an effective 2px-based scale:

`2 · 4 · 6 · 8 · 10 · 12 · 14 · 16 · 18 · 20 · 24 · 28 · 40` px, plus a few large page paddings: `60px` page bottom, `150px` / `180px` layout 4 bottom space above the dock, and `7vh` top on layout 4.

The most common values are 8px (64 uses), 6px (58), 4px (54), 10px (53), 12px (39) and 14px (29).

| Spot | Value |
|---|---|
| Top bar | padding `8px 16px`, gap `10px` |
| Panel | padding `12px 14px`, gap `8px` |
| Item row | padding `8px 10px`, gap `3px` |
| Button | padding `5px 11px`, gap `5px` (tiny: `1px 7px`, 12px text) |
| Action row | gap `4px`, margin-top `6px` |
| Dialog | padding `18px 20px`, footer margin-top `16px`, footer gap `8px` |
| Empty state | padding `18px`, gap `10px` |
| Banner | padding `8px 12px`, gap `8px`; banner stack padding `8px 16px 0`, gap `6px` |

The kit names these as `--space-1` … `--space-12` in `tokens.css` for convenience, mapped to the pixel values above. The originals use the raw pixels.

### 3.7 Radii, borders, shadows

**Radius per layout (`--radius`):**

| Layout | `--radius` | Notes |
|---|---|---|
| shared | `4px` | |
| 1 | `4px` | |
| 2 | `1px` | panels, banners, items and decision cards forced to `0` |
| 3 | `4px` | columns use `6px` |
| 4 | `10px` | buttons and quick add `999px` |
| 5 | `0` | everything forced to `0`, including dialogs, toasts and kinds |
| 6 | `10px` | buttons `8px`; cards, context boxes `12px`; bubbles `18px 18px 4px 18px` |

**Fixed radii used in components:**
- dialogs and overlays: `calc(var(--radius) + 2px)`;
- `kbd`, kind, status: `3px`;
- mic button: `16px`;
- badges and counts: `9px`;
- big mic, swatches, bell: `50%`.

**Borders:**
- 1px `--line` for dividers and panels;
- 1px `--line-2` for inputs, buttons, dialogs;
- 1.5px `--line-2` throughout layout 3 (where `--line-2` is the ink colour);
- 2px for the layout 3 top bar and drawer edge;
- `1px dashed --line-2` for empty states;
- 3 to 4px left bars for emphasis: conversation panel, inline errors, decision cards, layout 1 blocks.

**Shadows (complete list):**

| Where | Value |
|---|---|
| Dialog | `0 20px 50px rgba(0,0,0,.25)` |
| Conversation panel | `0 12px 30px rgba(0,0,0,.18)` |
| Notes tab | `0 1px 4px rgb(0 0 0 / .12)` |
| Rings and bars (no blur) | `0 0 0 1px var(--accent)`, `inset 3px 0 0 var(--accent)`, `inset 4px 0 0 var(--accent)`, `inset 0 3px 0 var(--accent)`, `inset 0 -2px 0 var(--accent)` |
| Layout 4 live dot | `0 0 0 4px var(--accent-soft)` |

### 3.8 Icons

- One inline SVG sprite (`<symbol id="i-NAME" viewBox="0 0 24 24">`):
  - `fill="none"`, `stroke="currentColor"`, `stroke-width="1.75"`;
  - `stroke-linecap="round"`, `stroke-linejoin="round"`;
  - used as `<svg class="icon" aria-hidden="true" focusable="false"><use href="#i-NAME"/></svg>`.
- Default size `16px × 16px` with `vertical-align: -3px`. Other sizes:
  - 12px inside badges, chips and notes;
  - 18px small mic;
  - 20px alarm bell;
  - 30px big mic;
  - 32px layout 6 mic.
- The kit's set (48 generic names): mic, mic-off, sun, moon, calendar, today, clock, list, target, history, settings, bell, pin, anchor, route, lock, unlock, check, check-circle, x, x-circle, skip, alert, grip, chev-left, chev-right, chev-down, chev-up, cycle, undo, play, timer, volume, filter, plus, minus, arrow-right, help, wave, inbox, columns, grid, layers, edit, focus, trash, search, split. The originals have 58 icons with the same drawing rules; the kit drops the unused ones and renames three after their shape (route, x-circle, cycle).
- The shapes are in `ui-kit/shared/icons.js`.

### 3.9 Motion

| What | Duration / easing |
|---|---|
| Saved "saving" spinner | `spin 1s linear infinite` (rotate 360°) |
| Alarm bell shake | `ring 1s ease-in-out infinite` (0/50/100%: 0°; 10/30%: −12°; 20/40%: 12°) |
| Toast fade out | `opacity .4s` |
| Mic level bars and level meter | `height .08s`, `width .08s` |
| Layout 6 mic ring | `transform .08s, opacity .08s` |
| Layout 3 drawer in | `slide .18s ease-out` from `translateX(40px)`, opacity 0 |
| Layout 4 sheet in | `rise .2s ease-out` from `translateY(20px)`, opacity 0 |

Under `prefers-reduced-motion: reduce` the originals switch off the spinner, the alarm bell, the layout 3 drawer and the layout 4 sheet. They do **not** switch off the toast fade, the level bars or the layout 6 ring (section 8). No other transitions exist: hovers change instantly.

### 3.10 Z-index order (low to high)

| z-index | Element |
|---|---|
| 2–3 | timeline / grid internals: selected block, proposed (ghost) tile, now line |
| 40 | layout 2 sticky tab bar |
| 50 | notes panel; layout 3 scrim |
| 55 | layout 3 drawer |
| 60 | top bar (sticky); layout 4 dock |
| 70 | conversation panel |
| 90 | overlay (help, search) |
| 95 | toasts |
| 1000 | skip link |
| top layer | native `<dialog>` (forms, confirmation, alarm, first-run) via `showModal()` |

### 3.11 Widths and fixed sizes

- Page: `min-width: 1024px` on `body`. No breakpoints. Designed for 1280px and up (see section 1).
- Top bar height: it has no explicit value; it is padding plus content. Measured at 1440px wide in headless Chromium, with the Windows fonts missing so fallbacks rendered: 56px (layouts 1 and 2), 58.5px (3), 69.25px (4), 46.5px (5), 57.5px (6). The exact figure depends on the fonts. The code offsets it by fixed values that don't always match: 54px (layout 1 sidebar, the conversation panel), 56px (notes panel, layout 1 conversation), 50px (layout 2 tabs), 70px (layout 4) and 78px / 92px (layouts 5 and 2).
- Quick add: `max-width: 640px`. Dialog: `min(560px, 92vw)` (wide `min(760px, 92vw)`). Overlay card: `min(620px, 92vw)`. Alarm: `min(460px, 92vw)`. Setup: `min(640px, 94vw)`. Conversation panel: `min(560px, 46vw)`. Notes panel open: `300px`. Toast max `640px`.
- Each layout's frame sizes are in section 4.

---

## 4. Layout skeletons

The six layouts differ in skeleton, not just in colour. Each one decides where the navigation lives and how the main area is divided.

| # | Name | Navigation | Main area | Other screens open as | Page scroll |
|---|---|---|---|---|---|
| 1 | Timeline | left sidebar, 232px, grouped | content + 330px sticky aside | replace the content column | page scrolls; sidebar pinned |
| 2 | Calendar grid | sticky top tab bar, 38px | full-bleed grid + 360px side panel | a centred page, max 1240px | grid area scrolls inside |
| 3 | Board | row of pill links under the top bar | five columns of cards | a right drawer over the board | page scrolls |
| 4 | Focus on now | floating bottom dock | one centred stage, max 880px | a full sheet, max 980px, "Back" link | page scrolls |
| 5 | Split dashboard | 28px mono status bar | five fixed panes, 3 columns × 2 rows | one pane maximised | each pane scrolls; page does not |
| 6 | Voice first | left rail of phrases, 270px | conversation stream + 280px context rail | a result card in the stream | stream scrolls; page does not |

The slot names used below match `data-slot="…"` in the kit. Every layout also has the shell slots from section 5:

| Shell slot | Contents |
|---|---|
| `topbar` | brand, Layout button, quick add, search, Saved, theme, help |
| `banners` | the banner stack |
| `notes` | the right-hand notes panel |
| `toasts` | toast stack |
| `dialog` | forms and confirmations |
| `alarm` | the alarm popup |
| `overlay` | help and search |

Navigation in all six is hash-based (`#screen`), in every layout:
- each nav link is `<a href="#name" data-nav="name">`, and the current one gets `aria-current="page"`;
- changing screen re-renders the frame and moves focus to the screen's first heading (`tabindex="-1"`, no visible outline on that programmatic focus);
- switching layouts keeps the current screen.

### 4.1 Layout 1: Timeline

**Idea.** A classic app frame with a quiet left sidebar and a calm, editorial main column. The home screen shows time as a proportional vertical timeline, and every block explains itself.

- **Best for:** anything ordered in time (a day plan, a schedule, a log), or a detail view next to a list.
- **Worst for:** very wide tables, or many parallel columns.

**Frame**

```
┌──────────────────────────────────────────────────────────────────────┐
│ [brand]  │ topbar: [Layout] [ quick add ··········· mic ] [⌕] Saved ◐ ? │ sticky, z60
├──────────┼───────────────────────────────────────────────────────────┤
│ nav      │ banners (padded 248px from the left)                       │
│ 232px    ├───────────────────────────────────────────────────────────┤
│ sticky   │ main-head: title (26px) ······················· actions   │
│ ┌──────┐ │ ─────────────────────────────────────────────────────────  │
│ │group │ │ toolbar (date nav + actions)                               │
│ │ link │ │ stats strip                                                │
│ │ link │ │ ┌────────────── main ───────────────┐ ┌─ aside 330px ───┐  │
│ │group │ │ │ timeline: 54px hours | lane        │ │ selected item   │  │
│ │ link │ │ │ blocks positioned by time          │ │ unscheduled     │  │
│ └──────┘ │ │                                    │ │ other panels    │  │
│ nav-foot │ └────────────────────────────────────┘ └─ sticky ────────┘  │
│ (mic)    │                                                            │
└──────────┴────────────────────────────────────────────────────────────┘
```

Slots: `nav`, `nav-foot`, `main`. On the home screen, `main` holds `main-head`, `toolbar`, `timeline` and `aside`.

**Grid and sizing**

- Top bar: `padding-left: 248px`. The brand is `position: fixed; left: 18px; top: 12px`, so it sits above the sidebar column.
- Frame: `display: grid; grid-template-columns: 232px 1fr; min-height: calc(100vh - 54px)`.
- Sidebar:
  - `background: var(--surface-2)`, with a 1px `--line` right border;
  - padding `8px 12px 14px`, flex column;
  - `position: sticky; top: 54px; height: calc(100vh - 54px); overflow: auto`;
  - the mic card is pushed to the bottom with `margin-top: auto`.
- Main: padding `18px 28px 60px`, grid gap `14px`, `min-width: 0`.
- Head: flex, space-between, 1px `--line` bottom border, `padding-bottom: 10px`.
- Home content: `grid-template-columns: 1fr 330px; gap: 22px; align-items: start`.
- Aside: `position: sticky; top: 70px; max-height: calc(100vh - 90px); overflow: auto`, gap `12px`.
- Timeline:
  - Scale and columns:
    - 1.4px per minute (84px per hour);
    - hour column 54px; hour lines 1px `--line`;
    - labels 12px `--mono` `--muted`, lifted 9px and masked with `--bg`.
  - Gaps of 30 minutes or more show as dashed `--line-2` boxes with a centred mono label.
  - Blocks:
    - absolutely positioned, minimum height 22px;
    - under 60px tall they become "tight": meta and reason hidden, no action buttons.
  - The timeline starts and ends on whole hours that cover the configured window and every item.
- Banners: `padding-left: 248px`. Conversation panel: `top: 56px`.

**Navigation**

- Grouped sidebar links:
  - group headings 11px uppercase, letter-spacing .08em, `--muted`, margin `14px 8px 4px`;
  - links: flex, gap 10px, padding `7px 8px`, radius `--radius`, icon `--muted`;
  - hover: `--line` background;
  - current: `--surface` background, `inset 3px 0 0 var(--accent)`, weight 600, icon `--accent`.
- Count badges: 600 11px `--mono` on `--accent`, radius 9px, padding `0 6px`, hidden when empty.
- Items that aren't built yet stay in the list, muted, with a dashed tag.

**Personality**

- `--display` "Segoe UI Variable Display", `--font` "Segoe UI Variable Text".
- Teal accent (`#0b7366` light, `#46c2b0` dark) on white. Dark is deep blue-green (`#0e1619`).
- Blocks have a 4px coloured left edge and a short accent-soft fade (`linear-gradient(90deg, var(--accent-soft), var(--surface) 45%)`), radius 3px.
- Kinds:
  - "fixed" uses an ink edge on a surface-2 fade;
  - "pinned" uses a warn edge on a warn-soft fade;
  - failed and skipped use a bad edge plus a 45° hatch: `repeating-linear-gradient(-45deg, var(--surface) 0 8px, var(--bad-soft) 8px 9px)`.
- The current block and the now line use `--now` (`#c2410c` light, `#ff9a5c` dark). The now label is a mono 600 11px chip.

**Shared components inside**

- Item rows in the aside.
- Toolbar and stats above the timeline.
- Decision cards (a pending change to accept or reject) and an "older open items" panel in the aside.
- A small mic card at the bottom of the sidebar: 40px round mic, phase text, "Hold V to talk".
- Everything else (top bar, banners, notes, toasts, dialogs) is unchanged.

**Empty, loading, error**

- Empty day: an `.empty` box in the main column with one sentence and one primary button. The wording depends on whether there are items without a time.
- Loading and error: shared behaviour (section 5.15).

### 4.2 Layout 2: Calendar grid

**Idea.** Technical and exact. The top tab bar is the navigation. The home screen is a full-bleed week grid with the chosen day widened, plus a fixed side panel. Hairlines, square corners, solid colour-coded tiles and a DIN-style face.

- **Best for:** comparing several days or columns at once, or anything calendar-like.
- **Worst for:** long text, or reading-heavy screens. Those open as a normal centred page.

**Frame (home screen)**

```
┌──────────────────────────────────────────────────────────────────────┐
│ topbar (border-bottom --line-2)                                        │ sticky z60
├──────────────────────────────────────────────────────────────────────┤
│ tabs: Home  Tab │ Tab  Tab  Tab │ Tab  Tab  Tab   (38px, sticky, z40)  │
├──────────────────────────────────────────────┬───────────────────────┤
│ grid-bar: title · subtitle ········ legend   │ side  360px           │
│ toolbar (compact)                             │ surface-2, sticky     │
│ ┌────┬──────┬──────┬────────────┬──────┬───┐ │ ┌───────────────────┐ │
│ │    │ Day  │ Day  │ SELECTED   │ Day  │ … │ │ │ section: detail   │ │
│ │ un-scheduled row (chips)                  │ │ ├───────────────────┤ │
│ ├────┼──────┼──────┼────────────┼──────┼───┤ │ │ section: progress │ │
│ │9:00│ tile │      │ wide tile  │      │   │ │ ├───────────────────┤ │
│ │    │      │      │ + reason   │      │   │ │ │ section: …        │ │
│ │ 56px hour col · scroll area ↕            │ │ └───────────────────┘ │
│ └────┴──────┴──────┴────────────┴──────┴───┘ │                       │
└──────────────────────────────────────────────┴───────────────────────┘
other screens:  tabs ▸ centred page (max-width 1240px, padding 18px 26px 60px)
```

Slots: `tabs`; on the home screen `grid-bar`, `toolbar`, `grid` and `side`; on other screens `page`.

**Grid and sizing**

- Tabs:
  - `display: flex; height: 38px; padding: 0 12px`;
  - `--surface` background, 1px `--line-2` bottom border;
  - `position: sticky; top: 50px; z-index: 40`.
- Home frame: `grid-template-columns: 1fr 360px; min-height: calc(100vh - 92px)`.
- Grid wrapper: flex column, `--surface`, 1px `--line-2` right border. Grid bar: padding `10px 14px`, gap 16px, 1px `--line` bottom.
- Calendar:
  - Columns:
    - hour column 56px;
    - the selected day `2.6fr`, every other day `1fr`.
  - Scale:
    - 1.25px per minute (75px per hour);
    - the hour lines are a background pattern: `repeating-linear-gradient(to bottom, var(--line) 0 1px, transparent 1px 75px)`.
  - The scroll area has `max-height: calc(100vh - 230px); overflow-y: auto`. The header and the unscheduled row stay above it.
- Side panel:
  - `--surface-2`, `position: sticky; top: 92px; max-height: calc(100vh - 92px); overflow-y: auto`;
  - sections: padding `12px 14px`, 1px `--line` bottom border, gap 8px.
- Other screens: `.l2-page { max-width: 1240px; margin: 0 auto; padding: 18px 26px 60px }`.

**Navigation**

- Tabs:
  - flex items, padding `0 12px`, `--muted`, weight 500;
  - `border-bottom: 3px solid transparent`; current tab gets `--ink` and a `--accent` underline.
- Related tabs are grouped between 1px `--line` dividers (margin `0 6px`).
- Badges are square accent boxes (`padding: 0 5px`, 11px).
- Clicking a day header selects that day (it widens). Clicking a tile selects it into the side panel.

**Personality**

- Bahnschrift / DIN Alternate / Roboto Condensed body and display, with tabular numbers.
- The brand is uppercase 15px, letter-spacing .14em. Its mark is two 16px bars (ink, then accent).
- `--radius: 1px`, and panels, items, banners and decision cards are forced to 0.
- Cobalt accent: `#1f56d1` light, `#7aa3ff` dark.
- Tiles:
  - solid fills: kind A uses `--auto-bg`/`--auto-ink` with a 3px inset accent bar, kind B uses `--fixed-bg`/`--fixed-ink`;
  - pinned uses `--warn-soft` with a 1.5px warn ring;
  - failed uses a 135° hatch plus a 1px bad ring;
  - now uses a 2px `--now` ring.
- Proposed (ghost) tiles: 2px dashed accent with a hatch and a 10.5px 700 tag letter-spaced .1em.
- Day header: name 12px uppercase .08em `--muted`, number 600 20px. The selected header gets an `--accent-soft` fill and `inset 0 3px 0 var(--accent)`.

**Shared components inside**

- The toolbar sits in compact form (no secondary actions) above the grid.
- The side panel stacks:
  1. selected item, as an item row with keyboard hints;
  2. decision cards;
  3. a compact progress summary (indented rows, one per level, each with a bar);
  4. older open items.
- With nothing selected, the side panel shows an empty state that explains what to click.

**Empty, loading, error**

- With no items in the whole week, the grid is replaced by one empty state with "Add your first …".
- An empty side panel has its own empty state.

### 4.3 Layout 3: Board

**Idea.** A workshop pin-board. The home screen is a set of columns, one per status, holding index cards with a hard ink outline and a coloured top band. Cards really drag between columns. Every other screen slides in as a right-hand drawer over the board, so the board stays as context.

- **Best for:** status workflows, triage, anything with "to do / doing / done".
- **Worst for:** precise time placement, or dense numbers.

**Frame**

```
┌──────────────────────────────────────────────────────────────────────┐
│ topbar on --bg, 2px ink rule below; brand 24px lowercase, no mark     │
├──────────────────────────────────────────────────────────────────────┤
│ nav:  [■ Home] ( Link ) ( Link ) ( Link ) ( Link )   pill links       │
├──────────────────────────────────────────────────────────────────────┤
│ board-head: TITLE IN CAPS · window    toolbar                         │
│ summary strip [■■  ■■■   ■  │now ]  "3h free · 2 done · 1 …"          │
├────────┬──────────┬──────────┬──────────┬───────────┤                │
│ col A  │  col B   │  col C   │  col D   │  col E    │ 230 | 1fr×3 |   │
│ 230px  │  ┌────┐  │  ┌────┐  │          │  250px    │ 250, gap 12     │
│ hatched│  │card│  │  │card│  │  empty   │           │                │
│        │  └────┘  │  └────┘  │  text    │           │                │
│        │ [+ Add]  │          │          │           │                │
└────────┴──────────┴──────────┴──────────┴───────────┘                │
other screens: board stays (inert) ▸ scrim ▸ drawer min(920px,76vw) ─▶ │
```

Slots: `nav`, `board-head`, `toolbar`, `summary`, `columns` (each column has a head with a count, an optional note and a card list), `extra` (below the board), and `drawer` on other screens.

**Grid and sizing**

- Nav: flex, gap 2px, padding `8px 20px`, wraps. Main: padding `0 20px 60px`.
- Board: `grid-template-columns: 230px repeat(3, 1fr) 250px; gap: 12px; align-items: start`.
- Column:
  - `--surface-2`, radius 6px, padding 10px, `min-height: 360px`, 1.5px transparent border;
  - while a card is dragged over it: 1.5px dashed `--line-2`.
- Column head: flex, 2px `--line-2` bottom rule; title `--display` 17px uppercase .04em; count `--display` 17px `--muted`.
- Special columns:
  - "now" column: `--mustard-soft` background, mustard rule;
  - "failed" column: bad rule;
  - "unscheduled" column: `repeating-linear-gradient(135deg, var(--surface-2) 0 10px, transparent 10px 20px)` with a 1.5px dashed `--line` border.
- Cards:
  - `--surface`, 1.5px `--line-2` border, `border-top: 7px solid var(--accent)`;
  - radius 4px, padding `0 10px 8px`, gap 4px.
- Card top bands by kind: fixed `--fixed`, pinned `--mustard`, unscheduled `--line`, failed `--bad`.
- Card text: time `--display` 16px; title 700 16px/1.2 (20px when current); progress bar 8px with a mustard fill.
- Summary strip:
  - a 22px bar on `--surface-2` with a 1.5px `--line-2` border;
  - segments positioned by time inside the configured window;
  - a 2px `--bad` now marker.
- Drawer:
  - `position: fixed; top: 0; right: 0; bottom: 0; width: min(920px, 76vw)`;
  - `--surface`, 2px `--line-2` left border, `z-index: 55`;
  - its header is sticky, with a 34px square close link;
  - body padding `0 26px 60px`.
- Scrim: `rgba(23,27,21,.45)`, `z-index: 50`. The board behind the drawer gets the `inert` attribute.

**Navigation**

- Pill links: padding `5px 10px`, radius 4px, weight 600, 1.5px transparent border. Hover: `--line` border. Current: `--ink` background with `--surface` text.
- Badges: mustard background, `#1c1400` text, radius 8px.
- Any screen other than home opens the drawer. **Esc**, the scrim or the × closes it and returns to home.

**Personality**

- Sage-grey board (`--bg: #d6dcd1`). `--line-2` is the ink colour, so every outline is black-ink 1.5px. Buttons are 600 with 1.5px borders.
- Fonts: condensed uppercase headings in Franklin Gothic, Corbel / Gill Sans body. Body 15px with lining tabular numbers.
- Mustard (`#d39400` light, `#f1c04a` dark) marks "now".
- A card being dragged gets `transform: rotate(-2deg); opacity: .8`.

**Shared components inside**

- Cards carry the shared kind badge, the reason line (above a dashed rule) and the shared action buttons at 12.5px.
- The toolbar sits under the title.
- Decision cards and older open items sit in a two-column `extra` area under the board.
- Drag and drop is only a shortcut: every drop runs the same action as a button. Dropping on "done" equals the Done button. Dropping on "failed" opens the reason form first.

**Empty, loading, error**

- Each empty column shows a short centred sentence, 14px `--muted`, padding 18px.
- A completely empty board is replaced by one empty state with "Add your first card".

### 4.4 Layout 4: Focus on now

**Idea.** One calm stage with no boxes. The current item is shown huge in a serif, with what's next below it. Everything else sits one click away in a floating dock and opens as a full-width sheet. Pale grey-green with deep green; dark is warm black with amber.

- **Best for:** a single "current thing" with a few actions, or a reading or focus mode.
- **Worst for:** overviews, comparisons, dense data. Those open as sheets with an agenda-style list.

**Frame**

```
┌──────────────────────────────────────────────────────────────────────┐
│ topbar: transparent, no border, padding 14px 40px; italic serif brand │
│ quiet-top:  Thu 8 Oct · 17:31   (muted 14px, max 880 centred)         │
│                                                                      │
│            stage (max-width 880px, padding 7vh 40px 180px)           │
│            ● NOW · 09:00–10:00 · 25 min left                         │
│            The current item, 64px serif                              │
│            ───────────── progress 3px ─────                          │
│            why line (muted)                                          │
│            ( Done ) ( Extend ) ( … )   pills                         │
│            ───────────────────────────────── margin-top 64px          │
│            NEXT                                                      │
│            10:30  Next item, 30px serif                              │
│            then: 11:00 · 12:00 · …                                   │
│                                                                      │
│        ╭──────────────────────────────────────────────────╮          │
│        │ (●Now) Whole list  Link  Link  Link  …            │ dock     │
│        ╰──────────────────────────────────────────────────╯ bottom 20│
└──────────────────────────────────────────────────────────────────────┘
other screens: sheet (surface, max-width 980px) with "‹ Back to now", dock stays
```

Slots: `quiet-top`, `stage` (holding the now label, title, progress line, why line and actions), `next`, `dock`, and `sheet` on other screens.

**Grid and sizing**

- No grid; everything is a centred column.
- Top bar: `background: transparent; border-bottom: 0; padding: 14px 40px`.
- `.l4 { min-height: calc(100vh - 70px) }`.
- Quiet top: `max-width: 880px; margin: 0 auto; padding: 0 40px`.
- Stage: `max-width: 880px; margin: 0 auto; padding: 7vh 40px 180px`. The 180px bottom keeps content clear of the dock.
- Now title: `font: 400 64px/1.06 var(--serif); letter-spacing: -.02em; margin: 14px 0 20px`.
- Progress line: 3px, `--line` track, `max-width: 560px`, radius 2px, `role="progressbar"`.
- Why line: `--muted`, margin `14px 0 26px`, max 640px.
- Next section: `margin-top: 64px; padding-top: 24px`, 1px `--line` top rule.
  - label: 500 13px uppercase .14em;
  - title: 30px/1.2 serif;
  - time column: 500 15px tabular, `min-width: 48px` (20px inside the next title).
- Dock:
  - `position: fixed; left: 50%; bottom: 20px; transform: translateX(-50%)`, `z-index: 60`;
  - flex, gap 2px, padding 6px, 1px `--line` border, radius 999px, `--surface`.
- Sheet:
  - `--surface`, `min-height: calc(100vh - 70px)`;
  - inner `max-width: 980px; margin: 0 auto; padding: 20px 40px 150px`, grid gap 14px.
- Banners: `max-width: 980px; margin: 0 auto`. Toasts: `bottom: 86px`, above the dock.

**Navigation**

- Dock links:
  - padding `8px 13px`, radius 999px, 14px, `--muted`;
  - hover: `--ink` on `--bg`;
  - current: `--accent` background, `--accent-ink` text.
- Badges: `#fff` on `--bad`, 11px, radius 8px.
- The home screen is "now" (`#now`). Other screens show a "‹ Back to now" link at the top of the sheet.

**Personality**

- Georgia / Sitka serif for titles. Body is Segoe UI at 15.5px. Radius 10px; buttons and quick add are full pills.
- Large buttons: padding `11px 22px`, 15.5px.
- Brand: italic 20px serif, no mark.
- Live dot: 9px circle with a 4px `--accent-soft` ring.
- Sheet titles: 400 40px/1.1 serif. Section labels: 500 13px uppercase .13em.
- Agenda rows on sheets have no box, only a bottom rule, padding `12px 0`, with a 21px serif title. The current row gets `linear-gradient(90deg, var(--accent-soft), transparent 70%)`.

**Shared components inside**

- The stage uses big versions of the shared actions.
- Sheets use the shared item row, styled flat.
- The toolbar appears on the full-list sheet.
- No side panel. Detail opens in a sheet.

**Empty, loading, error**

- With nothing current, the title becomes a soft muted line. Examples: "Free until 10:30", "Nothing more today", "A clear day".
- A clear day adds one sentence and an "Add" pill.

### 4.5 Layout 5: Split dashboard

**Idea.** An instrument panel. Five tiled panes with shared 1px borders are visible at once. Text is small, numbers are mono, the top bar is black. Any pane can be maximised to fill the screen.

- **Best for:** monitoring, power users, seeing many lists together.
- **Worst for:** first-time users, long reading, touch.

**Frame**

```
┌──────────────────────────────────────────────────────────────────────┐
│ topbar: --ink background, padding 4px 10px; brand = mono chip on accent│
├──────────────────────────────────────────────────────────────────────┤
│ status: All │ Tab │ Tab │ Tab │ Tab │ …            Thu 8 Oct 17:32   │ 28px mono
├───────────────────────┬────────────────────┬─────────────────────────┤
│ PANE A          [⤢]   │ PANE B        [⤢]  │ PANE D            [⤢]   │ 30px heads
│ (spans both rows)     │                    │                         │
│ table · toolbar       ├────────────────────┼─────────────────────────┤
│                       │ PANE C        [⤢]  │ PANE E            [⤢]   │
│ 1.25fr                │ 1fr                │ .95fr                   │
└───────────────────────┴────────────────────┴─────────────────────────┘
other screens: status ▸ one pane filling the area, head has [split] back icon
```

Slots: `status`, `pane-a` … `pane-e` (each with a 30px head and a scrolling body), and `pane-max` on other screens.

**Grid and sizing**

- Status bar:
  - `display: flex; height: 28px`, `--surface-2`, 1px `--line` bottom border, `font: 12px var(--mono)`;
  - links: padding `0 9px`, 1px `--line` right border;
  - the clock is pushed right with `margin-left: auto`.
- Grid:
  - `grid-template-columns: 1.25fr 1fr .95fr`;
  - `grid-template-rows: minmax(300px, 1fr) minmax(300px, 1fr)`;
  - `gap: 1px; background: var(--line)` (the gaps become the borders);
  - `height: calc(100vh - 78px)`.
- Placement: A `grid-row: 1 / 3`; B column 2 row 1; C column 2 row 2; D column 3 row 1; E column 3 row 2.
- Pane: `--surface`, flex column, `min-height: 0; min-width: 0`.
  - Head: height 30px, padding `0 8px 0 10px`, `--surface-2`, 1px bottom border. The head title is 700 11.5px `--mono` uppercase .08em.
  - Body: padding `8px 10px 14px; overflow: auto; flex: 1`, grid gap 8px. Each pane scrolls on its own.
- Maximised: `.l5-max { height: calc(100vh - 78px); display: flex }`. Its body has `max-width: 1180px; font-size: 14px`.
- Tables:
  - full width, collapsed;
  - `th`: 10.5px mono uppercase .06em, weight 400, `--muted`, padding `3px 5px`, 1px `--line` bottom;
  - `td`: padding `4px 5px`, 1px `--surface-2` bottom.
- Table row states:
  - done: `--muted` with struck title;
  - failed: `--bad-soft` row;
  - current: `--warn-soft` row;
  - selected: `inset 3px 0 0 var(--ink)` on the first cell.

**Navigation**

- Status-bar tabs:
  - current tab: `--ink` text, `--surface` background, `inset 0 -2px 0 var(--accent)`;
  - badges: plain accent boxes.
- Each pane head has a maximise icon (`focus`) linking to that screen. A maximised pane's head has a split icon linking back to "All".

**Personality**

- Signal orange: `#c2410c` light, `#f0a020` amber in dark. Dark is blue-black (`#05070a`).
- `--radius: 0` everywhere, including dialogs, toasts, the mic button, quick add and badges.
- Body 13px. Buttons: 12px mono, padding `2px 7px`.
- Top bar:
  - light: `--ink` background with `--surface` text;
  - dark: `#000` with a 1px `--line` bottom.
- Brand: 700 13px mono chip on `--accent`, padding `4px 8px`.
- Screen title: 700 16px mono uppercase. The big mic is a 52px square.

**Shared components inside**

- The toolbar (compact) sits at the top of pane A.
- The selected item appears below the table in a box with a 2px top rule.
- The voice pane has a compact mic (52px square), the phase and the last 5 log rows.
- History rows are tagged `FAIL` or `SKIP`.

**Empty, loading, error**

- Each pane shows its own small muted one-liner when empty, for example "No commands yet." Pane A uses the full empty state with a button.

### 4.6 Layout 6: Voice first

**Idea.** A conversation down the middle. What the user said shows as right-aligned bubbles, and each answer is a card that can be acted on; the current screen itself is rendered as a large result card. The left rail lists every screen as the phrase that opens it, so users learn what to say by looking. A big mic sits at the bottom.

- **Best for:** voice or command-driven apps, assistants, guided flows.
- **Worst for:** dense editing, tables, drag and drop.

**Frame**

```
┌──────────────────────────────────────────────────────────────────────┐
│ topbar (brand mark = 18×16 accent bars)                               │
├────────────┬───────────────────────────────────────────┬─────────────┤
│ rail 270px │ stream (max 820 centred, padding 18 28)    │ context     │
│ SAY IT, OR │      separator / hint (muted 13px)         │ 280px       │
│ TAP IT     │                         ┌─────────────┐   │ ┌─────────┐ │
│ ▸ "phrase" │                         │ you said …  │   │ │ NOW     │ │
│   Screen   │                         └─────────────┘   │ │ title   │ │
│ ▸ "phrase" │ ┌───────────────────┐                     │ │ ▬▬▬     │ │
│   Screen   │ │ answer card       │                     │ └─────────┘ │
│ …          │ └───────────────────┘                     │ ┌─────────┐ │
│ MORE THINGS│ ┌───────────────────────────────────────┐ │ │ MIC     │ │
│ TO SAY     │ │ big card: the current screen          │ │ │ state   │ │
│ "example"  │ └───────────────────────────────────────┘ │ └─────────┘ │
│            ├───────────────────────────────────────────┤             │
│            │ composer:   (( ● ))  Ready                 │             │
│            │             78px mic   hint                │             │
└────────────┴───────────────────────────────────────────┴─────────────┘
```

Slots: `rail` (with `rail-nav`, `rail-more`), `stream`, `screen-card`, `composer`, `context`.

**Grid and sizing**

- Frame: `display: grid; grid-template-columns: 270px 1fr 280px; height: calc(100vh - 54px)`.
- Rail: `--surface-2`, 1px right border, padding `16px 12px`, `overflow-y: auto`.
- Middle column: flex column.
  - Stream: `flex: 1; overflow-y: auto; padding: 18px 28px`, column gap 10px. Every child is `max-width: 820px; margin: 0 auto`.
  - Composer: flex, centred, gap 18px, padding `12px 20px 16px`, 1px `--line` top border.
- Context: `--surface-2`, 1px left border, padding `16px 14px`, `overflow-y: auto`, grid gap 12px.
- The stream scrolls to the end after each render while there is history.
- Banners: `max-width: 860px; margin: 0 auto`. The floating conversation panel is hidden (`display: none !important`), because the stream replaces it.

**Navigation**

- Rail links:
  - flex, gap 10px, padding `7px 8px`, radius 8px;
  - each shows the phrase in quotes (600 14px) above the screen name (12.5px `--muted`);
  - current: `--surface` background with `inset 3px 0 0 var(--accent)`.
- Heading "Say it, or tap it": 600 12px uppercase .1em.
- A "More things to say" list shows example phrases at 13.5px `--muted`.
- Tapping a rail item adds a "tapped" bubble (accent-soft) to the stream and shows the screen as a big card.

**Personality**

- Coral accent: `#c8401a` light, `#ff7a57` dark. Segoe UI Variable. Body 15px. Radius 10px; buttons 8px; cards 12px.
- User bubbles: `--me` / `--me-ink` (near-black in light, `#2c333e` in dark), radius `18px 18px 4px 18px`, padding `9px 16px`, 16px text, max 70%.
- Answer cards: `--surface`, 1px `--line`, radius 12px, padding `10px 14px`, max 84%.
  - error variant: `--bad` border on `--bad-soft`;
  - question variant: `--warn` border on `--warn-soft`, weight 600.
- Mic:
  - 78px circle, `--accent` background, 32px icon;
  - the ring sits 8px outside with a 3px accent border;
  - ring opacity is `calc(.15 + level × .85)` and scale is `calc(1 + level × .14)`;
  - while listening, the mic turns `--bad`.
- Phase text: 600 19px.

**Shared components inside**

- The whole current screen renders inside one big card (`max-width: 100%`, padding `16px 18px`, grid gap 10px).
- The context rail holds a "Now" card (title 600 19px/1.2, 4px progress, actions) and a mic card (phase, hint, mute and mic-test buttons).

**Empty, loading, error**

- With no conversation, the stream shows one centred muted hint line.
- Errors arrive as red answer cards.
- Questions waiting for an answer add a warn card: "Waiting for your answer…".

### 4.7 Differences between the kit and the originals (on purpose)

The kit was compared with the original app at 1440 × 900, in both themes. The original ran against a fresh temporary database holding only a few generic sample items, and that database was deleted afterwards. The frame structure, the measured top-bar heights and every token value match. These differences were chosen on purpose.

**Structure**
- `data-layout` sits on `<html>`, and every layout's tokens live in one `tokens.css`, instead of one stylesheet swapped at runtime. Each layout is its own page under `ui-kit/layout-N/`.
- The chooser is a stand-alone `index.html` page that uses the remembered layout's tokens. In the originals, the chooser is a screen inside the current layout.
- Choices are remembered in `localStorage`: `uikit.theme`, `uikit.layout`, `uikit.notesOpen`, `uikit.banners`, `uikit.slots`, `uikit.muted`, `uikit.setupDone`. The originals keep theme, layout and the notes panel's state as server settings, mirrored to `localStorage` for the boot script.

**Content**
- Screens are generic (home, list, progress, history, voice, settings, later) and the content is placeholder text. Kind names, priorities and the "main automatic action" label all come from `demo-content.js`.
- Layout 2 draws the pending decision's proposed tiles on the home grid. The originals draw them only on a separate screen.
- Layout 2's week starts on Monday. In the originals the week comes from the backend.
- Layout 3's columns are Unscheduled, Planned, Now, Done and Failed.
- Dropping a card on "Planned" opens the Move form.

**Kit-only tools**
- Visible slot labels (`data-slot`), toggled with **G** or in Settings.
- A "preview state" switch (normal / empty / loading / error).
- Simulate-offline, ring-alarm and reset-banners buttons in Settings.

**States and messages**
- A quiet "Loading…" state. The originals render nothing until the first data arrives (section 5.15).
- The fake mic in the kit hears a fixed list of phrases. Snooze rings again after 10 seconds instead of minutes.

**Fixes for the gaps listed in section 8**
- Text on `--bad` and `--now` uses `--bad-ink` and `--now-ink`.
- All motion stops under reduced motion.
- Sticky offsets match the measured bar: layout 1 sidebar `top: 56px`; layout 2 tabs `top: 56px` and side panel `top: 94px`.
- The layout 3 drawer starts below the top bar (`top: 59px`).
- Banners keep 200px clear of the collapsed notes tab.
- Confirmations focus "No, keep everything" first.
- Form fields always show a focus ring.

---

## 5. Shared shell components

Each component works in all six layouts and in both themes, without layout-specific code. A layout only restyles a component through tokens, plus a handful of overrides listed under "Per layout".

In the kit, each component is one `shared/<name>.js` (and `.css` where needed). It does nothing if its host element is missing, so removing a component means deleting its two files and its host element.

### 5.1 Top bar and layout switcher button

- **Purpose:** the one constant strip on every screen.
- **Optional:** no.

**Anatomy, in order:**
1. Brand: mark plus name.
2. Layout button: layers icon, "Layout" label, `kbd` "L".
3. Quick add form (5.4).
4. Search button: search icon, `kbd` "/".
5. Saved indicator (5.6).
6. Theme button (5.3).
7. Help button: help icon.

**Look**

- Bar:
  - `display: flex; align-items: center; gap: 10px; padding: 8px 16px`;
  - `--surface` background, 1px `--line` bottom border;
  - `position: sticky; top: 0; z-index: 60`.
- Brand: flex, gap 8px, 600 17px `--display`, `margin-right: 4px`. The default mark is a 12×18px "L" made of a 3px `--accent` left and bottom border.
- Bar buttons (`.ab-btn`): inline-flex, gap 6px, padding `6px 9px`, 1px `--line` border, radius `--radius`, transparent background, `--ink` text, `font: inherit`. Hover: `--line-2` border.

**Per layout**
- 1: brand fixed above the sidebar.
- 2: line-2 border; uppercase letter-spaced brand; bar mark.
- 3: bar on `--bg` with a 2px ink rule; 24px lowercase display brand; no mark.
- 4: transparent, no border, padding `14px 40px`; italic serif brand.
- 5: black or ink bar; mono chip brand; `rgba(255,255,255,.25)` button borders.
- 6: striped bar mark.

**Layout button behaviour**
- Opens the layout chooser (5.2). The `L` key does the same.
- Switching layout keeps the current screen.

**Accessibility**
- Icon-only buttons carry `aria-label` ("Search", "Switch theme", "Keyboard shortcuts and help").
- Every shortcut is shown on its button (`title` and a visible `kbd`).

### 5.2 Layout chooser page

- **Purpose:** pick one of the six layouts.
- **Optional:** no, if more than one layout ships.

**Anatomy**
- Screen title "Choose a layout", then one muted sentence: "All six show every screen and every action; they differ in arrangement and look. Your choice is remembered."
- An ordered list of six large buttons. Each has:
  - a number: 600 24px `--display`, `--accent`, 28px wide;
  - a name: 16px bold;
  - a one-line description: `--muted`;
  - on the current one, an "In use" label with a check icon.

**Look**
- List: `display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 14px`.
- Each button: full width, flex, gap 12px, padding 14px, 1px `--line` border, radius, `--surface`. Hover: `--accent` border.
- Current: `--accent` border plus `box-shadow: inset 4px 0 0 var(--accent)`, `aria-current="true"`, and the "In use" label (600 12.5px `--accent`).

**Descriptions** (the kit's generic wording; the originals say the same with app-specific nouns):

| # | Name | Description |
|---|---|---|
| 1 | Timeline | A left sidebar and a vertical timeline; each block shows why it is there. |
| 2 | Calendar grid | A grid of days with the chosen day widened, an unscheduled row and a side panel. |
| 3 | Board | Cards in status columns; other screens open as a drawer over the board. |
| 4 | Focus on now | One calm screen with the current item large; everything else in a dock. |
| 5 | Split dashboard | Dense panes side by side: list, progress, decisions, voice and history at once. |
| 6 | Voice first | A conversation with a big mic; answers come back as cards you can act on. |


**How the choice is remembered**
- The original saves it as a backend setting, so it survives restarts and other browsers. It also mirrors it to a `localStorage` key.
- A tiny script in `<head>` reads that mirror before the first paint and applies the layout and theme, so the page doesn't flash the wrong look. Once data arrives, the server's value wins.
- The kit uses `localStorage` key `uikit.layout`, wrapped in try/catch, and falls back to layout 1.

**Keyboard and accessibility**
- Plain buttons in a list. Tab and Enter work.

### 5.3 Light and dark theme switch

- **Purpose:** switch light and dark.
- **Optional:** no.

**Anatomy**
- In the top bar: one icon button. It shows a moon in light (meaning "go dark") and a sun in dark.
- In Settings: a three-button segmented control: System, Light, Dark. Each button has `aria-pressed`, and the pressed one is `--ink` on `--bg`.

**States**
- The saved value is `system`, `light` or `dark`. `system` follows `prefers-color-scheme` and updates live when the OS changes.
- The resolved value is always written as `data-theme="light"` or `"dark"` on `<html>`. Each layout block also sets `color-scheme`.

**Behaviour**
- The top-bar button toggles between light and dark. That sets an explicit value and leaves `system`.
- The original saves the value as a backend setting and mirrors it to a `localStorage` key. The head script applies it before paint.
- The kit uses `uikit.theme`.

**Accessibility**
- `aria-label="Switch theme"`. The sun and moon icons are `aria-hidden`.

### 5.4 Quick add bar

- **Purpose:** one box where any command can be typed, the typed twin of the mic.
- **Optional:** recommended.

**Anatomy:** a `<form role="search">` holding:
- a visually hidden label;
- an input with placeholder "Type a command, or press V and speak" and `maxlength="500"`;
- a pill mic button with a three-bar level meter;
- a send button (arrow icon);
- a `kbd` "Ctrl K".

**Look**
- Form:
  - `flex: 1; max-width: 640px; margin-left: auto`;
  - 1px `--line-2` border, radius, padding `2px 4px 2px 10px`, `--surface`;
  - `:focus-within` gives an `--accent` border plus `0 0 0 1px var(--accent)`.
- Input: borderless, transparent, padding `6px 0`.
- Mic button:
  - pill (radius 16px), padding `4px 9px`, `--surface-2`, 1px `--line` border;
  - level bars: 3px wide, heights `calc(2px + var(--level) * 12px)` (middle bar `* 8px`), `transition: height .08s`.
- Per layout: pill in layout 4; square in layout 5.

**Mic button states** (from `html[data-mic]`)

| State | Look |
|---|---|
| `listening` | `--bad` background, white icon |
| `thinking` | `--accent` border and text |
| `asking` | `--warn` border and text |

**Behaviour**
- **Ctrl K** (or Cmd K) focuses the input from anywhere, even while typing elsewhere.
- **Enter** sends the text and clears the input.
- The answer shows in the conversation panel (5.10), and as a toast when something was saved.
- Typed text stays in the box until it is sent. Re-renders never wipe typed text: inputs marked `data-keep` are kept.

### 5.5 Keyboard shortcuts and the help overlay

- **Purpose:** every main action from the keyboard, plus one place that lists them.
- **Optional:** no; the help overlay is the documentation.

**Shortcut list.** Original keys; the kit uses generic labels.

| Key | Action |
|---|---|
| Ctrl K | Focus the quick add box |
| / | Search |
| A | Add an item |
| D / F / S | Done, Failed, Skip on the selected (or current) item |
| X | Extend the current item |
| P | Run the main automatic action |
| N | Add a note |
| U | Undo the last change |
| L | Switch layout |
| V | Push to talk: hold to speak, or tap to start and tap again to stop (a hold over 350ms stops when released) |
| ? | Help |
| Esc | Close a dialog, overlay or panel; in layout 3, close the drawer |

**When shortcuts are ignored**
- with Ctrl, Cmd or Alt held (except Ctrl K);
- while typing in an input, textarea, select or contenteditable;
- while a dialog is open;
- while the alarm is open, except V.

**Help overlay**
- `position: fixed; inset: 0; background: rgba(10, 14, 20, .45); z-index: 90`, with the card placed `10vh` from the top.
- Card: `width: min(620px, 92vw); max-height: 75vh; overflow: auto`, radius `calc(var(--radius) + 2px)`, padding `16px 18px`, 1px `--line-2` border.
- The card has `role="dialog" aria-modal="true" aria-label="Keyboard shortcuts"`, a close × and a `<dl>` of keys (grid `90px 1fr`, gap 10px). After the list come two notes: that shortcuts don't work while typing, and that anything clickable can also be typed or said.
- Clicking the backdrop or pressing Esc closes it. Focus goes to the first button on open.

**Search overlay**
- Uses the same overlay: an input (16px, padding `9px 12px`) and live results as left-aligned buttons with a muted `<small>` describing where each result is.

### 5.6 "Saved" indicator and the save-failed banner

- **Purpose:** confirm every change was stored, without a save button.
- **Optional:** no.

**Anatomy**
- `<span class="saved" role="status" aria-live="polite">`: a check icon and a text, `min-width: 92px`, 12.5px, `--muted`.

**States** (`data-state`)

| State | Text | Look |
|---|---|---|
| `idle` | "Saved" | `--muted` |
| `saving` | "Saving…" | icon spins, `spin 1s linear infinite` (off under reduced motion) |
| `saved` | "Saved" (or "Done" if nothing was stored) | `--ok`; returns to idle after 4000ms |
| `error` | "Not saved" | `--bad`, weight 600 |
| `offline` | "Offline" | `--bad`, weight 600 |
| refusal by a rule | "Not changed" | idle look |

**Save-failed banner**

When the backend can't be reached, a red `.banner.bad` with `role="alert"` appears at the top of the banner stack:
- an alert icon;
- **"Can't reach …"**, then: changes aren't being saved right now, and anything you typed stays on screen;
- a "Try again" button.

Typed input stays on screen. The banner disappears as soon as the connection is back.

**Text areas that save as you type**
- They save 1200ms after the last keystroke, and also on blur.
- A small note under the field shows "Saving…", then "Saved HH:MM", or "Not saved: your text is still here."

### 5.7 Undo toast

- **Purpose:** every change can be undone, without asking first.
- **Optional:** no.

**Anatomy**
- A message and, when the change can be undone, an "Undo" button with an undo icon and `kbd` "U". Optionally one extra quiet action.

**Look**
- Stack: `position: fixed; left: 50%; transform: translateX(-50%); bottom: 18px` (`86px` in layout 4), `display: grid; gap: 6px; z-index: 95`.
- Toast:
  - flex, gap 12px, `--ink` background, `--bg` text;
  - padding `8px 10px 8px 14px`, radius, 13.5px, `max-width: 640px`;
  - `transition: opacity .4s`.
- Buttons in a toast are transparent, with a `--bg` 50% mixed border.
- Error toast: `--bad` background, `#fff` text.

**Behaviour**
- At most 3 toasts. The oldest is removed first.
- Each lasts 5000ms, or 9000ms with Undo, or 15000ms for "long" ones. Then it fades for 500ms and is removed.
- **U** undoes the last change from anywhere. With nothing to undo, a toast says "There's nothing to undo."

**Accessibility**
- Each toast has `role="status"`, inside an `aria-live="polite"` host.

### 5.8 Non-blocking banners

- **Purpose:** information that matters but must not interrupt. Reminders are banners, not popups.
- **Optional:** recommended.

**Anatomy**
- Each banner: an icon, a text `<span>` (`flex: 1; min-width: 240px`), then optional buttons: a primary action, and a quiet "Dismiss" or "Hide".
- A banner can also hold a short list of items, each with its own action and Dismiss.

**Look**
- Stack: `display: grid; gap: 6px; padding: 8px 16px 0`, hidden when empty.
- Banner: flex, wrap, gap 8px, padding `8px 12px`, radius, 1px `--line` border, `--surface-2`, 13.5px.

| Tone | Background | Border |
|---|---|---|
| `bad` | `--bad-soft` | `--bad` |
| `warn`, `remind` | `--warn-soft` | warn at 45% |
| `info` | `--accent-soft` | accent at 40% |
| note banner | lilac mix (section 3.1) | lilac mix |

**Order, top to bottom**
1. connection lost;
2. sound blocked;
3. alarm errors;
4. missed alarms;
5. questions about the current item ("Did you finish it?");
6. reminders;
7. "app was updated";
8. note banners;
9. "N changes waiting for a decision".

**Show-once behaviour**

A reminder or note reminder **fires once** and is never repeated. Its banner then stays while the thing is still missing, and **Dismiss hides that item for good**. Dismissing never deletes the underlying thing. A new missing item gets its own single reminder. The "while you were away" summary is shown once.

The original keeps these marks on the backend. The kit keeps them in `localStorage` (`uikit.banners`) with two modes:
- `once`: shown on one page load, then never again;
- `until-dismissed`: shown on every load until Dismiss.

**Accessibility**
- Blocking problems use `role="alert"`. Everything else uses `role="status"`.

### 5.9 Confirmation prompts for risky actions

- **Purpose:** destructive or wide-reaching actions never run on one click.
- **Optional:** no.

**Anatomy**
- The shared `<dialog>`, titled "Please confirm".
- A read-back paragraph saying exactly what will happen: `.readback`, 600 15px, padding `10px 12px`, `--warn-soft` background, radius.
- A footer with the cancel button first, "No, keep everything", then the danger button, "Yes, go ahead": `--bad` background, white text.

**Behaviour**
- The action is sent once. The backend answers "needs confirmation" with the read-back text. After "Yes", the same action is sent again with a confirmed flag.
- The read-back comes from the backend, so it is always exact.
- Esc or the × cancels. The original's alarm dialog is the only one that blocks Esc.

**Dialog primitive** (shared by all forms)
- Native `<dialog>` opened with `showModal()`, which provides the focus trap and the top layer.
- Look: 1px `--line-2` border, radius `calc(var(--radius) + 2px)`, padding `18px 20px`, `width: min(560px, 92vw)` (`.wide`: `min(760px, 92vw)`), `--surface`, shadow `0 20px 50px rgba(0,0,0,.25)`, backdrop `rgba(10,14,20,.5)`.
- Head: flex, space-between, title 600 19px/1.3, quiet × button with `aria-label="Close"`.
- Foot: right-aligned, gap 8px, margin-top 16px. Order: Cancel, then the primary action.
- The first field gets focus on open.
- Errors appear inside the form (`.form-err`, `role="alert"`) and the input stays.
- A reason field keeps its submit button disabled until it has text.

### 5.10 Voice panel (optional)

- **Purpose:** use everything by voice. Speech is turned into text locally, and the backend decides what it means.
- **Optional:** the whole voice system can be removed. Typing in quick add does the same.

**Mic states** (`html[data-mic]`; phase text in every `[data-mic-phase]` element)

| State | Text | Mic look |
|---|---|---|
| `idle` | "Ready" | neutral |
| `listening` | "Listening…" | `--bad` fill, white icon; layout 6 ring follows the level |
| `thinking` | "Understanding…" | accent outline |
| `asking` | "Waiting for your answer" | warn outline |
| `muted` | "Muted" | neutral; starting shows a toast instead |

- Every mic button gets `aria-pressed="true"` while listening.
- A hidden status text reads "Microphone: <phase>".

**Level**
- Every `[data-level]` element gets `--level` (0 to 1) as an inline custom property.
- It is smoothed with `level = level × .6 + min(1, rms × 6) × .4`.

**"What I heard" and the interpreted command**
- After speaking, the heard text is shown first, with confidence when under 100%: "… (82% sure)".
- Then come the backend's answer lines and the interpreted command.

**Conversation panel** (all layouts except 6, which uses the stream)
- `position: fixed; top: 54px; right: 16px; width: min(560px, 46vw); z-index: 70`.
- `--surface`, 1px `--line-2` border, `border-left: 3px solid var(--accent)`, padding `10px 12px`, shadow `0 12px 30px rgba(0,0,0,.18)`.
- It shows the last 6 lines (scroll at 40vh):
  - user lines in `--muted`, prefixed "You:";
  - question lines in 600 `--warn`, prefixed "Question:";
  - error lines in `--bad`.
- While asking, a hint line says: "Answer in the box above or press V and speak. Say "cancel" to stop."
- Footer: "Undo that" (when something changed) and a quiet ×. Esc clears it, unless a question is waiting.

**Confirm-by-voice state**
- Risky commands are read back and need a spoken (or typed) "yes". During that time the phase is `asking`, the question line is warn-coloured, and layout 6 adds a warn card.
- Below the confidence limit nothing happens. The limit comes from the backend and is displayed as "Below NN% nothing happens". **Could not confirm** the number in the front end; a running instance showed 60%.

**Transcript log**

A list of rows, each a grid `50px 1fr` with a 1px top rule and padding `7px 0`:
- time: 12px mono `--muted`;
- what was heard: italic, followed by the confidence (12px mono; under the limit in `--bad` 700, or "typed");
- the command (600 13px with an arrow icon), or "No command" (minus icon, muted);
- a small muted result line.

**Mic test**
1. Listens for 4 seconds while a level meter moves. The meter is 12px high (16px for `.wide`), radius 6px, `--line` track, `--accent` fill (`width: calc(var(--level) * 100%)`), with a dashed midline at 50% meaning "aim here".
2. Then it shows what it heard: "Heard: "…" (NN% sure)", plus a warning if that is under the limit.
3. If the peak is under 2%, it says no sound reached the mic and to check the device.

There is also a microphone `<select>`.

**Big mic sizes:** shared `72px` circle (30px icon); layout 1 small `40px`; layout 5 `52px` square; layout 6 `78px` with a level ring.

**Kit:** `shared/voice-panel.js` has a **fake mic**. It cycles through the states, animates a fake level, "hears" a fixed placeholder phrase, and asks for a "yes" on risky phrases. No microphone or network is used.

### 5.11 Collapsible side notes panel (optional)

- **Purpose:** short notes that must not be forgotten, with or without a time, outside any screen.
- **Optional:** yes.

**Anatomy, collapsed**
- A tab button on the right edge: pin icon, "Notes", a count pill and an optional "N overdue" pill.

**Anatomy, open**
1. Head: title with count, and a × close.
2. Add form:
   - textarea, placeholder "Write a note", `maxlength` 200, with a live counter "x/200";
   - optional `datetime-local`;
   - six colour swatches;
   - an "Add note" button with `kbd` "N".
3. Sections, in this order:
   - **Overdue**: earliest first; muted, struck through, with a "past" tag;
   - **Upcoming**: soonest first;
   - **No time**: newest first.

   Each section heading shows its count.

**Look**
- Panel: `position: fixed; right: 0; top: 56px; bottom: 0; z-index: 50`. Collapsed it is `pointer-events: none`, except for the tab itself.
- Tab: rounded only on the left (`var(--radius) 0 0 var(--radius)`), no right border, shadow `0 1px 4px rgb(0 0 0 / .12)`, margin-top 8px.
- Count pill: `--surface-2`, radius 9px, 12px. Overdue pill: `--warn-soft`/`--warn`.
- Open (`body.notes-open`):
  - width 300px, `--surface`, 1px `--line` left border, padding `10px 12px 16px`, `overflow-y: auto`;
  - the main area and banners get `margin-right: 300px`, so the page **makes room instead of covering**.
- Note:
  - padding `6px 30px 6px 8px`, radius, 1px `--line` border, background `--note-bg` (the colour mix from section 3.1);
  - the delete icon button is absolutely placed top-right.
- Overdue note: `opacity: .62`, `--surface-2`, dashed border, line-through in `--line-2`, and a "past" tag (10px uppercase on `--line`).
- Counter: 11px, right-aligned. Over 180 characters it turns `--warn` 600.
- Swatches:
  - 20px circles with a 1px `--line-2` border, built from radio inputs (visually hidden);
  - checked: `outline: 2px solid var(--focus); outline-offset: 1px`;
  - keyboard focus: a 2px focus outline.
- Sections: heading 12px uppercase .04em `--muted`; list gap 6px.

**States**
- Empty: an `.empty` box with one sentence and "Add a note (N)".
- Full: the original allows 50 notes. The add form becomes disabled with a warning line.

**Behaviour**
- Notes are add and delete only, with no editing. Delete has no confirmation; the Undo toast brings the note back.
- The open or closed state is remembered: a backend setting in the original, `uikit.notesOpen` in the kit.
- **N** opens the panel and focuses the textarea.
- Re-rendering never interrupts typing in the add form.
- When a note's time arrives, one banner appears, and one silent desktop notification if allowed.

### 5.12 Alarm popup (optional)

- **Purpose:** a time-based alert that must be answered.
- **Optional:** yes.

**Anatomy:** a modal `<dialog>` holding:
- a bell disc and an eyebrow line;
- a title (the item);
- the message;
- a muted note: "Rings until you choose (stops by itself after 2 minutes). Voice: "dismiss" or "snooze"." The original adds "N more ringing" when there is more than one;
- notes when sound or notifications are blocked;
- a footer: "Snooze N min" (clock icon), then "Dismiss" (primary, check icon).

**Look**
- `border-top: 5px solid var(--bad); width: min(460px, 92vw)`.
- Bell: 38px circle, `--bad` background, white 20px icon, `animation: ring 1s ease-in-out infinite` (none under reduced motion).
- Title 600 24px `--display`. Message 15px.

**Behaviour**
- Opens with `showModal()` and focuses Dismiss.
- **Esc is blocked** (the `cancel` event is prevented): the user must choose.
- The tone is made with Web Audio, with no audio file. It is a sine pattern:
  - 880Hz for 0.18s, a 0.09s gap, 880Hz for 0.18s, a 0.09s gap, 1320Hz for 0.32s;
  - gain ramps to 0.35;
  - the pattern repeats every 1700ms.
- If the browser blocks sound, a warn banner offers "Enable sound". The tone goes quiet while the mic is recording.
- When the tab is hidden and permission was given, a desktop notification is shown with `requireInteraction`.
- The 2-minute auto-stop is enforced by the backend. **Could not confirm** it in the front end.

### 5.13 Empty states and the first-run setup flow

**Empty state**
- Anatomy: one sentence saying what will appear here and how, then **one** button for the first action (usually primary).
- Look: `.empty`: `border: 1px dashed var(--line-2)`, radius, padding 18px, `display: grid; gap: 10px; justify-items: start`, `--muted` text, `--surface`. The paragraph is max 640px.
- Small panes use a muted one-liner instead.
- Never use an illustration, an emoji or a blank area.

**First-run setup**
- A wide dialog (`.setup`, `min(640px, 94vw)`) shown when the backend reports the setup is needed.
- A step list sits at the top: 12.5px `--muted`, with the current step in `--accent` 700 and finished steps in `--ok`.
- The four original steps:
  1. **Your day**: start and end time.
  2. **First entry**: the first item, with an optional target and unit.
  3. **Sound and notifications**: "Enable and test sound", "Allow notifications", with a live permission note.
  4. **Microphone**: the mic test.
- Every step can be skipped, and "Skip the whole setup" (quiet, tiny, bottom right) ends it. Anything skipped stays visible as a reminder banner.
- Setup can be run again from Settings.
- The kit's `shared/first-run.js` has four generic steps: Welcome, Preferences, Sound and notifications, Microphone. It stores `uikit.setupDone`.

### 5.14 Settings page pattern

**Anatomy**
- Screen title "Settings", then a muted line: "Changes save as soon as you make them."
- Below that, a two-column grid of panels (gap 14px, margin-top 12px). Each panel has an uppercase panel header and rows.

**Rows**
- `display: flex; justify-content: space-between; padding: 4px 0`, with `--muted` labels on the left and the control on the right.
- Help text sits below a row as a muted small paragraph.

**Controls**
- Native inputs, saved **on change** (`data-autosubmit`); there is no Save button.
- Segmented control (`.seg`) for small enumerations such as the theme.
- Action buttons for tests ("Test alarm sound", "Allow desktop notifications"). A live note under them reports the result.

**Original panel order**
1. Schedule / day window.
2. Alarms.
3. Your data: export and import.
4. Voice.
5. Look: theme, layout ("<name> · change" with `kbd` L), run setup again.
6. A **danger zone** panel: border `color-mix(in srgb, var(--bad) 40%, var(--line))`. Its buttons range from quiet to `.danger`, and each goes through the confirmation prompt (5.9).

### 5.15 Loading and error states, inline errors

**Loading**
- The original has **no loading indicator**. The main area stays empty until the first data arrives, which is usually instant from a local backend.
- The kit shows a quiet muted "Loading…" line in the main slot, with no spinner or shimmer, so the state can be designed.

**Load error**
- When the first load fails, the main area shows an `.empty` box with the error sentence and a "Try again" button.

**Later errors**
- Errors after the first load show as the save-failed banner (5.6).

**Inline errors** (a rule refused an action)
- A `<p class="inline-err" role="alert">` is appended next to the control that was used.
- Look: `--bad` text on `--bad-soft`, 3px `--bad` left border, padding `5px 9px`, 13px, radius `0 var(--radius) var(--radius) 0`, full row width.
- It is removed after 15000ms, or on the next try.
- Inside a dialog, the error goes into that form's `.form-err` instead.

---

## 6. Generic screen patterns, as slot fills for each layout

Every app screen is one of six patterns. Each layout puts the same pattern in a different place. The tables say which slot each pattern fills. The kit builds these patterns in `shared/screens.js` from `demo-content.js`.

### 6.1 The patterns

| Pattern | What it is built from |
|---|---|
| **List** | A toolbar (previous / date / next, plus actions) and rows of items. Each row has a time or "no time", a title, a status tag, kind and priority badges, a duration, an optional linked chip, a "why" line, and an action row. "No time" items are listed separately. |
| **Detail** | One item, larger: the same row with keyboard hints on its actions. Shown for the selected item. |
| **Form** | Always a dialog (5.9): labelled fields, hints under fields, an error slot, then Cancel and a primary button. |
| **Progress** | Cards with a title, a value text ("3 / 5 units"), a 6px bar (`--line` track, `--accent` fill, `role="progressbar"`), optional "rolls up to" and "made from" lines, a collapsible log, and actions. A read-only (locked) period shows a lock line. |
| **History with filters** | A filter form (select, from / to dates, status, Apply, Clear, "N of M"), then rows on a grid `80px 1fr`, each with a status tag, title, date, quoted reason and an action. |
| **Settings** | Section 5.14. |

### 6.2 Where each pattern goes

| Pattern | 1 Timeline | 2 Calendar grid | 3 Board | 4 Focus on now | 5 Split dashboard | 6 Voice first |
|---|---|---|---|---|---|---|
| Home | `timeline` + `aside` | `grid` + `side` | `columns` board | `stage` (now + next) | `pane-a` … `pane-e` | `screen-card` in `stream` |
| List | `main` column | `page` (centred) | `drawer` | `sheet`, flat agenda rows | `pane-max`, or `pane-a` as a table | `screen-card` |
| Detail | `aside` panel "Selected" | `side` section "Selected" | a selected card (3px focus outline), or its actions in the drawer | `sheet` | box under the table in `pane-a` | `context` "Now" card |
| Form | dialog | dialog | dialog | dialog | dialog (square corners) | dialog; the question also appears as a warn card in the stream |
| Progress | `main` column | `page`; compact summary in `side` | `drawer` | `sheet` | `pane-b` (table summary), or `pane-max` | `screen-card` |
| History | `main` column | `page` | `drawer` | `sheet` | `pane-e` (last 8 rows as a table), or `pane-max` | `screen-card` |
| Settings | `main` column | `page` | `drawer` | `sheet` | `pane-max` | `screen-card` |
| Voice page | `main`; plus the sidebar mic card | `page` | `drawer` | `sheet` | `pane-d` (mini), or `pane-max` | `composer` + `context`; the full page in `screen-card` |

### 6.3 Rules every pattern follows

- Toolbar first, content second. The toolbar keeps the same order everywhere:
  - navigation group on the left: previous / picker / next / "back to now";
  - action group on the right: secondary, then **primary**, then quiet or destructive.
- Every item row shows *why* it is in that state ("Why here: …", or "Failed, because: …").
- Action rows wrap and never scroll sideways.
- Icon-only actions (delete, close) are `quiet` buttons with an `aria-label`.
- Read-only periods show a dashed lock line and drop every edit control. Read-only text areas use a `--surface-2` background, `--muted` text and a dashed border.
- Status always has a word, not only a colour: "Now", "Done", "Failed", "Skipped", "past".

---

## 7. What the UI expects from a backend

This section is about shapes and behaviour only. Any backend works if it provides these. All wording that explains a rule ("why", refusals, read-backs) comes **from the backend**, so the UI never re-implements a rule.

### 7.1 Generic data shapes

```js
// List item (a row, card, block, tile)
{ id: 12, title: "…", date: "2026-01-31",
  start: "09:00" | null, end: "10:00" | null, duration: 60, duration_text: "1h",
  status: "pending" | "done" | "failed" | "skipped",
  running: false,                      // true = "now"
  kind: "fixed" | "pinned" | "auto" | "untimed",  // drives badge + colour
  priority: 1..4, priority_name: "normal",
  reason: "why it is here" | "",       // shown as "Why here: …"
  fail_reason: "…" | null,             // shown when failed / skipped
  link: { id, title, text } | null,    // optional chip (e.g. a parent entry)
  elapsed: 0..1, minutes_left: 25 }    // only when running

// Progress item
{ id, title, period: "day" | "week" | "month" | any label,
  value: 3, target: 5 | null, unit: "units", text: "3 / 5 units", fraction: 0.6,
  done: false, locked: false, parents: [ {title, text} ], children: [ {label, value} ],
  logs: [ {id, date, amount} ] }

// Banner
{ id: "unique-key", tone: "bad" | "warn" | "info" | "note",
  text: "…", action: { label, act, args } | null,
  dismissible: true, mode: "once" | "until-dismissed" }

// Toast (after any change)
{ message: "…", undo_id: 41 | null, error: false, long: false }

// Note
{ id, text, due: "2026-01-31T17:00" | null, due_label: "Today 17:00" | null,
  color: "sand" | "sage" | "sky" | "lilac" | "rose" | "slate",
  section: "overdue" | "upcoming" | "no_time" }

// Voice state
{ phase: "idle" | "listening" | "thinking" | "asking" | "muted",
  level: 0..1,
  heard: { text, confidence } | null,
  interpreted: "command name" | null,
  asking: false,                         // waiting for an answer / a "yes"
  log: [ { at: "17:02", text, confidence | null, interpreted | null, acted, result } ],
  low_confidence: 0.6 }

// Result of any action
{ ok: true, message: "…", saved: true, undo_id: 41,
  needs_confirm: false, message_readback: "…",   // → confirmation prompt (5.9)
  needs_choice: false, choices: [ {value, label} ] }
// Refusal: { ok: false, error: "the reason, in plain words" } → inline error
```

### 7.2 Live-update behaviour

- **One read endpoint for the whole screen.** The UI asks for the full current state, including everything any layout shows, and re-renders from it. Nothing is changed only in the browser.
- **One write path.** Every control sends one named action with arguments. The answer is one of:
  - saved: show "Saved", and an Undo toast if there is an undo id;
  - refused: show an inline error, and keep the input;
  - needs confirmation: open the read-back prompt;
  - needs a choice: open a small dialog with the options.
- **Push "something changed".** The original uses Server-Sent Events with these events:
  - `hello`;
  - `changed`;
  - `reminder`;
  - `note` (with the note);
  - `alarm` (with the alarm).

  On any event, the UI re-reads the state. "Changed" reloads are debounced by 120ms, and reloads are coalesced: if one is in flight, a single follow-up runs. The clock also re-reads once a minute, so "now" lines move.
- **Connection lost.** If the event stream errors, or a request fails to connect, the UI shows "Offline" and the red banner. The stream retries every 2000ms after closing. On reconnect, everything reloads.
- **Per-tab view state** stays in the browser: which day or period is shown, filters, the selected item. The original keeps it in `sessionStorage` and passes that state as query parameters when reading.
- **Typed input survives re-renders.** Fields marked `data-keep` keep their value, cursor and focus across a re-render.

---

## 8. Accessibility as the originals do it

**What is in place**

- **Skip link.** The skip link "Skip to content" jumps to the main area (`tabindex="-1"`). Look: `--ink` background, `--bg` text, padding `6px 10px`, `z-index: 1000`. It is off-screen until focused (`left: 6px; top: 6px`).
- **Focus is always visible.** `:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px }`. Each layout tunes `--focus` per theme. Its contrast with `--bg` is 4.7 to 10.3:1, above the 3:1 non-text minimum.
  - The quick add box shows focus on the container (`:focus-within`) instead.
  - Selected items get a separate 2px `--ink` outline, so "selected" and "focused" never look the same.
- **Keyboard everywhere.**
  - Every action is a real `<button>` or `<a href>`.
  - Drag and drop in layout 3 is only a shortcut: every drop has a button equivalent.
  - The layout 3 drawer closes on Esc, and the board behind it is `inert`.
  - Dialogs are native `showModal()`, which provides the focus trap and returns focus.
  - After a screen change, focus moves to the new screen's heading.
- **Names and roles.**
  - Icon-only buttons have `aria-label`. Decorative icons are `aria-hidden` and `focusable="false"`.
  - Navigation uses `aria-current="page"`. Toggles use `aria-pressed` (mic, theme segments).
  - Bars that show progress have `role="progressbar"` with `aria-valuenow`, min and max.
  - The board has `aria-label` on columns (`aria-labelledby`) and on itself.
  - Each layout's nav has an `aria-label` ("Main navigation", "Panes", "Everything else", "Open a page").
- **Live regions.** The Saved indicator, the conversation panel and the toast host are `aria-live="polite"`. Blocking banners are `role="alert"`, other banners `role="status"`. Form errors are `role="alert"`.
- **Text never relies on colour alone.** Status words, a "past" tag, and dashed versus solid styling all repeat the colour's meaning.
- **Reduced motion.** `prefers-reduced-motion: reduce` turns off the saving spinner, the alarm bell, the layout 3 drawer slide and the layout 4 sheet rise.
- **Sound.** Nothing plays until the user clicks (a browser rule). The page says when sound is blocked and offers a button.

**Contrast (WCAG ratio, computed from the tokens; ⚠ = below 4.5:1 for text)**

| Pair | Use | 1 L / D | 2 L / D | 3 L / D | 4 L / D | 5 L / D | 6 L / D |
|---|---|---|---|---|---|---|---|
| `--ink` on `--bg` | body text | 16.2 / 15.2 | 15.6 / 15.4 | 12.5 / 15.5 | 13.7 / 15.1 | 13.5 / 15.0 | 18.3 / 16.1 |
| `--muted` on `--surface` | muted text | 6.0 / 7.0 | 6.4 / 6.9 | 7.5 / 6.2 | 5.6 / 6.6 | 6.3 / 6.0 | 6.1 / 6.9 |
| `--muted` on `--surface-2` | muted on surface-2 | 5.5 / 7.8 | 6.0 / 6.4 | 6.2 / 7.2 | 5.1 / 6.1 | 5.8 / 5.7 | 5.6 / 7.2 |
| `--accent` on `--surface` | accent text / links | 5.7 / 7.8 | 6.3 / 7.1 | 6.4 / 8.3 | 6.2 / 9.1 | 5.2 / 8.7 | 5.0 / 6.8 |
| `--accent-ink` on `--accent` | primary button | 5.7 / 7.4 | 6.3 / 6.9 | 6.4 / 9.5 | 6.4 / 9.2 | 5.2 / 8.6 | 5.0 / 7.1 |
| `#fff` on `--bad` | danger button, error toast (hard-coded white) | 6.5 / 2.3 ⚠ | 5.9 / 2.4 ⚠ | 6.4 / 2.4 ⚠ | 6.7 / 2.4 ⚠ | 6.6 / 2.7 ⚠ | 6.6 / 2.3 ⚠ |
| `--bad` on `--bad-soft` | error text on error tint | 5.6 / 7.0 | 5.1 / 6.6 | 5.1 / 6.5 | 5.4 / 6.5 | 5.6 / 6.3 | 5.6 / 6.9 |
| `--warn` on `--warn-soft` | warning text on warning tint | 5.4 / 8.4 | 4.9 / 8.2 | 4.9 / 7.8 | 5.1 / 8.1 | 4.6 / 8.5 | 4.9 / 8.5 |
| `--ok` on `--surface` | Saved / ok text | 5.4 / 9.1 | 5.4 / 9.4 | 5.3 / 7.9 | 6.2 / 10.9 | 5.1 / 9.1 | 5.4 / 9.5 |
| `--focus` on `--bg` | focus ring vs page (needs 3:1) | 5.8 / 8.9 | 5.6 / 9.9 | 4.8 / 8.8 | 5.6 / 10.3 | 4.7 / 9.6 | 5.8 / 9.3 |
Other pairs checked:

| Pair | Ratios |
|---|---|
| `--muted` on `--bg` | 4.6:1 (layout 5 light, the lowest) to 7.9:1 |
| Layout 2 tiles: `--fixed-ink` on `--fixed-bg` | 12.2 / 8.3 |
| Layout 2 tiles: `--auto-ink` on `--auto-bg` | 9.2 / 9.7 |
| Layout 6 bubble: `--me-ink` on `--me` | 18.3 / 11.5 |
| Layout 3 badge: `#1c1400` on mustard | 7.0 / 10.8 |
| Layout 5 light top bar | 18.5 |

**Gaps found in the originals.** The kit fixes 1, 2, 3, 5, 6 (for layouts 1 and 2), 8, 9 and 10, and documents the rest. See 4.7.

1. **White text on `--bad` in dark mode is 2.3 to 2.7:1.** This affects the danger button, the error toast, the listening mic button, the alarm bell and the layout 4 dock badge. In dark, `--bad` is a light red (for example `#ff8a80`), so white on it fails. *Kit fix:* text on `--bad` uses a new token, `--bad-ink`: `#fff` in light, and in dark the theme's `--bg` value, which gives 7:1 or more.
2. **White "now" label on `--now`.** Layout 2 is 4.2:1 in light and 2.6:1 in dark, on 10.5px bold text. Layout 1 in light is 5.2:1, and layout 1 dark already switches to dark text. *Kit fix:* `--now-ink` per theme.
3. **Reduced motion is incomplete.** The toast fade (.4s), the level bars and meter (.08s) and the layout 6 ring transitions still animate. These are small, but the kit switches them off under reduced motion as well.
4. **Fixed-height frames ignore the banner stack.** Layouts 5 and 6 use `height: calc(100vh - 78px)` and `calc(100vh - 54px)`. When banners are showing, the page itself scrolls as well as the panes. The kit keeps this behaviour. A rebuild could use a flex column body instead.
5. **The collapsed notes tab covers the right end of the banner stack.** It is fixed at `top: 56px`, so it hides a banner's Dismiss button. The kit gives the banners 200px of right padding while the tab is collapsed.
6. **Hard-coded top-bar offsets** (54, 56, 50, 70, 78, 92px) don't match the bar's real height. Measured heights are 56px in layouts 1 and 2 (section 3.11). As a result:
   - the layout 2 tab bar (`top: 50px`) slides 6px under the bar while scrolling;
   - the layout 1 sidebar (`top: 54px`) slides 2px under it.

   A rebuild could measure the bar into a `--topbar-h` custom property.
7. **No responsive layout** below 1024px. Zoom at 200% on a 1280px screen falls below that width and scrolls sideways.
8. **The layout 3 drawer's head is hidden.** The drawer is `top: 0` at `z-index: 55`, under the 58.5px top bar (`z-index: 60`). Its sticky head, and the close button inside it (at 10px from the top), sit behind the bar. Esc and the scrim still close the drawer.
9. **Confirmation dialogs focus the danger button.** The shared dialog focuses the first submit button, which in a confirmation is "Yes, go ahead". Pressing Enter at once confirms.
10. **Date and time inputs can lose the focus ring.** They focus an inner field, so `:focus-visible` on the input may not match.
11. **The shortcut keys are single letters with no modifier.** They are disabled while typing, but they could clash with screen-reader quick-navigation keys. There is no setting to turn them off. **Could not confirm** any testing with a screen reader.

---

## 9. Rebuild checklist

Tick each line for **every layout (1–6) × both themes**. "Same as original" means the same structure, the same tokens and the same behaviour as described in sections 3 to 5.

**Global (once per theme)**

- [ ] Tokens: all 16 colour tokens defined per layout for light and dark. Extras: `--now` (1, 2), tile colours (2), mustard / fixed (3), serif (4), bubble colours (6).
- [ ] `color-scheme` set per theme. Native date and time pickers match.
- [ ] Theme: the top-bar button toggles. Settings has System / Light / Dark. The choice survives a reload. `system` follows the OS live. No flash of the wrong theme on load.
- [ ] Layout: the chooser lists six with descriptions and "In use". The choice survives a reload. Switching keeps the current screen. The `L` key opens the chooser.
- [ ] No external requests: no fonts, scripts, images or analytics from other hosts.
- [ ] Icons: SVG sprite only; stroke 1.75; 16px default; no emoji anywhere.

**Per layout × theme**

- [ ] Frame matches the diagram in section 4: navigation position, column widths, sticky parts, scroll containers.
- [ ] Every named slot exists and is filled.
- [ ] Navigation: every screen reachable. `aria-current` on the current link. Badges hidden when empty.
- [ ] Home screen: the layout's own arrangement (timeline / grid / board / stage / panes / stream).
- [ ] List, detail, form, progress, history and settings patterns all reachable and placed as in 6.2.
- [ ] Top bar: all seven parts, in order, with the layout's styling.
- [ ] Quick add: Ctrl K focuses it; Enter sends; the answer shows (conversation panel, or the stream in 6).
- [ ] Shortcuts: A, D, F, S, X, P, N, U, L, V, ?, /, Esc. Ignored while typing and while a dialog is open. The help overlay lists them.
- [ ] Saved indicator: saving → saved (green) → idle after 4s. The offline and error states, and the red banner, keep typed text.
- [ ] Undo toast: appears after a change; U undoes; at most 3; times 5 / 9 / 15s. Error toast readable in dark.
- [ ] Banners: tones bad, warn, info, note. Show-once works across a reload. Dismiss is permanent.
- [ ] Confirmation: read-back text; "No, keep everything" first; danger button; Esc cancels.
- [ ] Voice (if used): five mic states with matching colours and text; level moves; "heard" text with %; interpreted command; asking state needs a "yes"; transcript log; mic test with meter and result.
- [ ] Notes (if used): tab with count and overdue pill; opening pushes the page instead of covering it; the open state survives a reload; N focuses the box; counter turns warn after 180; six swatches; three sections in order; overdue styling; delete gives Undo.
- [ ] Alarm (if used): modal with red top border; ringing bell (still under reduced motion); Snooze and Dismiss; Esc does nothing; tone only after a click.
- [ ] Empty state on every list and pane: one sentence and one button (or a one-line muted text in small panes).
- [ ] Loading and error: an error box with Try again; the kit's "Loading…" line.
- [ ] First-run flow: step list, each step skippable, "Skip the whole setup", re-runnable from Settings.
- [ ] Settings: two-column panels; saves on change; danger zone uses confirmation.
- [ ] Focus visible on every control; Tab order follows the visual order; drawers and dialogs trap focus and return it.
- [ ] Reduced motion: no spin, no bell shake, no slide or rise, no toast fade.
- [ ] Contrast: body, muted, accent, primary and danger buttons at 4.5:1 or more, and the focus ring at 3:1 or more, in this theme.

**Layout-specific**

- [ ] 1: brand above the sidebar; sidebar sticky with a mic card at the bottom; timeline 1.4px per minute; free gaps of 30 minutes or more drawn; tight blocks under 60px; now line.
- [ ] 2: tabs sticky at 38px; selected day 2.6fr; 1.25px per minute; unscheduled row; ghost tiles; side panel sticky; other screens centred at 1240px.
- [ ] 3: five columns (230 / 1fr×3 / 250); 7px card bands; drag between columns runs the same actions; drawer `min(920px, 76vw)` with scrim, inert board, Esc closes.
- [ ] 4: transparent top bar; 64px serif title; dock fixed at bottom 20px; sheets with "Back"; toasts raised to 86px.
- [ ] 5: black top bar; 28px status bar; 3×2 grid with 1px gaps; panes scroll on their own; maximise and back.
- [ ] 6: 270 / 1fr / 280; phrases in the rail; bubbles and cards; big mic with level ring; conversation panel hidden; stream scrolls to the end.

---

## 10. Known gaps and "could not confirm" items

**Could not confirm from the code**

- **1280px design width.** Only `body { min-width: 1024px }` exists. There are no breakpoints. The 1280px target comes from the brief.
- **Top bar height on Windows.** It has no explicit height; its height is padding plus content. It was measured only with fallback fonts (section 3.11). The offsets in the CSS disagree with each other: 50, 54, 56, 70, 78, 92px.
- **Spacing scale.** No spacing tokens exist. The scale in 3.6 was derived from the values actually used.
- **Actual rendered fonts.** All are system stacks led by Windows fonts. On macOS or Linux the fallbacks render instead (system-ui, Arial Narrow, Gill Sans, Calibri and so on). The look was not confirmed on those systems.
- **Alarm auto-stop after 2 minutes.** It is stated in the UI text but enforced by the backend, not in the front end.
- **Voice confidence limit.** It is supplied by the backend (`low_confidence`). The UI only displays it; a running instance showed 60%.
- **Note limits.** The 50-note and 200-character limits are supplied by the backend (`max`, `max_text`). The UI displays them. The counter's "near" threshold of 180 characters is hard-coded in the front end.
- **Loading state.** None exists in the original (see 5.15).
- **Screen-reader testing.** No evidence of it in the code or notes.

**Known gaps in the originals.** Section 8 lists them. In short:
- white on `--bad` and on `--now` in dark;
- the layout 3 drawer head hidden under the top bar;
- confirmations that focus the danger button;
- reduced motion is incomplete;
- fixed-height frames don't account for banners;
- the notes tab overlaps banners;
- hard-coded bar offsets;
- no responsive layout;
- single-letter shortcuts can't be turned off.

**Kept out of this guide on purpose**

- The original app's own screens and their wording. Only the patterns underneath them are described.
- Everything on the backend: storage, rules, voice recognition, the action names. Section 7 only describes the shapes the UI expects.
