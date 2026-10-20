# Deck design bar and conventions

The deck is a presentation. Someone talks over it, so the slides support the talk and never replace it. Nobody can listen and read a page at the same time.

## The bar

- **One idea per slide.** Each slide has a headline, one visual, and at most about 20 other words.
- **Headlines are claims of 8 words or fewer.** "We hit 1,240 hives in June", not "Traction".
- **One visual.** A big number, a chart, a diagram, a timeline or a row of icons.
- **No tables, paragraphs or bullet walls on a slide.** At most 3 short labels per visual.
- **The talk track lives in the script.** `N` shows it under the slide. `P` opens the presenter view.
- **Honest labels, shown visually.** Mark each number measured (solid dot), inferred (half dot) or guess (dashed ring). Explain the key once, on slide 1 or 2. A guess that carries a goal must look like one: a dashed line, a hatched bar or a `chip guess`.
- **Motion with a purpose.** Lines draw in, numbers count up, bars grow, one build per spoken beat.
- **Looks designed.** Strong type hierarchy, a lot of whitespace, one accent plus the chart palette, inline SVG icons you draw yourself, no external assets.

## Technical constraints

- One self-contained HTML file under 200 KB. Inline CSS and JS, no CDN, no web fonts.
- The page renders in a chat frame about 728 px wide (about 360 px on phones) whose height grows to fit. The stage is 16:9 and scales to the frame width. Below 560 px it switches to 3:4. Never set `100vh` or `height: 100%` on html or body.
- Text stays readable at a 728 px stage. Headlines land around 28 to 34 px there. No text under 13 px.
- Respect `prefers-reduced-motion`. The engine already disables transitions and skips the count-in.
- Theme. The deck adapts to light and dark, and reads host variables when they exist: `--background`, `--foreground`, `--muted-foreground`, `--card`, `--border`, `--destructive`, `--radius`, `--font-sans`, `--font-mono`.

## Engine and template

`template/deck.html` holds the engine in two blocks, the style with id `vd-engine-css` and the script with id `vd-engine-js`. Do not edit them in a deck. `VD engine-sync deck.html` refreshes them from the template, and `VD engine-sync --check deck.html` fails when they drift.

The engine adds the control bar, notes drawer, presenter view, tooltip, captions and the voice overlay at load time. You write only the slides, their CSS, and the deck code.

### Slides

```html
<section class="slide" id="s2" aria-label="Slide 2">
 <div class="cv">
  <div class="kick"><b>02</b><span>The problem</span></div>
  <h2 class="hd">We lose a third of our hives.</h2>
  <div class="n abs b" data-b="1" data-count="38" data-suf="%">0%</div>
  <div class="cap abs b" data-b="2">of colonies lost <i class="lb m" title="measured"></i></div>
 </div>
</section>
```

- Slides are `section.slide` inside `#stage`, in order, with ids `s1`, `s2` and so on.
- `.cv` is the content box: 856 x 480 units in 16:9, 476 x 660 units in 3:4.
- Size everything as `calc(var(--u) * N)`. One unit is 1/960 of the stage width (1/540 below 560 px).
- Write the 3:4 layout in `@container (max-width:559px) { ... }`.
- `.kick` is the top rule with the slide number. `.hd` is the headline. The engine shrinks a wide headline to fit one line.

### Builds

- `data-b="k"` makes an element appear on build k of its slide. Add class `b` for the default fade-up.
- Other build styles: `reveal` (child `.ln` paths wipe in, `.mk` marks fade in after), `grow` and `growx` (scale from the base), `draw` with `pathLength="1"` (stroke draws in), `mk2` (fades in late inside a `.b`), `hl` (highlighter under a phrase).
- `[data-only=wide]` and `[data-only=narrow]` show an element in one layout only. Builds inside them count only in that layout, so both layouts must reach the same build count.
- The slide gets `data-step="k"` on each build, for CSS that keys on the step.
- Counters: `data-count="to" data-from="from" data-pre="$" data-suf="%" data-dec="1"`. They count up when their build fires.
- Labels: `<i class="lb m">` measured, `lb i` inferred, `lb g` guess. `.lkey` is the ready-made key. `.chip.guess` is a dashed chip.
- Add class `fin` to anything whose final state needs forcing in the presenter thumbnail.

### Deck code

Charts and hand-drawn pieces live in one script before the engine:

```js
window.DECK = {
  charts: { growth: function (box, api) { /* draw an SVG into box */ } },
  draw: function (api) { /* redraw non-chart SVG on every layout change */ },
  onStep: function (slideEl, step, api) { /* optional per-build side effects */ },
  init: function (api) { /* optional one-time setup */ }
};
```

- `<div class="chart" data-chart="growth">` calls `DECK.charts.growth(box, api)` at load and on every layout switch. Builds that a chart draws (`api.el("g", {class: "b", "data-b": 2}, svg)`) count like any other.
- `api` gives `el(tag, attrs, parent, text)`, `U()` (px per unit), `narrow()`, `fmt(n)`, `bindTip(node, title, rows)`, `showTip`, `hideTip`, `cssVar(name)`, `textW`, `reduce` (the reduced-motion query), `deck`, `stage` and `slides`.
- Colours: `--c1`, `--c2`, `--c3` for series, `--mark` for highlights, `--ink`, `--muted`, `--line`, `--paper`, `--red`. Classes `c-1`, `c-2`, `c-3` and `c-ink` set stroke and fill.

### Script block

`VD script script.md deck.html` writes `<script type="application/json" id="pitch">`. Each entry is `{slide, title, say, segments, target}`. `segments[0]` is spoken on slide entry and `segments[k]` after build k. `target` is the slide's seconds for the presenter timer. The engine logs a console error when a slide's builds differ from its segment count.

### Keys

Arrows, Space, PageUp and PageDown, Home and End navigate. `N` notes, `P` presenter, `F` fullscreen, `C` captions, `K` pause during the show, `Esc` stops. Tap zones (left 30% back) and swipe work on touch. `#3` in the URL opens slide 3, and `#pv3` opens it with the presenter view.

## Check it

`node tools/browser/audit.js /abs/deck.html shots` screenshots every slide fully built at 1280, 728 and 390 px in dark and light. It reports words per slide, headline length, overflow, text under 13 px, overlapping text and console errors. It exits non-zero on errors, overflow, small text, headlines over 8 words, slides over 30 words or a file over 200 KB. Overlap reports are hints: big numbers often overlap their own line box. Look at the PNGs yourself.
