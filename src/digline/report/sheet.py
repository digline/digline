"""The one stylesheet: the HTML report's and every page `digline view` serves.

One string, so the report's functions stay pure and the two surfaces cannot
drift into two looks (ADR 0061 §7). A report written to a file carries it
inline, because a file opened from disk has no server to fetch from; the server
serves the same string at `/static/digline.css` and every page it sends links
to it, which is what lets its policy say `style-src 'self'` (ADR 0061 §4.4).

System fonts and no web font, tabular figures in every column of numbers, and
a light and a dark theme from `prefers-color-scheme`, through custom
properties, so a colour is changed in one place. Each setup has one hue,
`--s1` to `--s3`, the same in a table, in the chart and in a row.
"""

from __future__ import annotations

__all__ = ["SHEET", "UPLOT_CSS"]

_OURS = """\
/* digline — one sheet for the HTML report and for digline view (ADR 0061 §7).
   System type, no web font, no framework. Light and dark from the system,
   through custom properties. */

:root {
  color-scheme: light dark;
  --font: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;

  --bg: #fbfbfc;
  --surface: #ffffff;
  --sunken: #f3f4f7;
  --text: #16181d;
  --muted: #5b6270;
  --faint: #8a919e;
  --line: #e3e6eb;
  --line-strong: #cfd4dc;
  --accent: #2f5bd3;
  --accent-text: #ffffff;
  --good: #17733a;
  --good-bg: #e7f5ec;
  --bad: #a3262a;
  --bad-bg: #fcebec;
  --warn: #8a4b1c;
  --warn-bg: #fbf0e6;

  /* One hue per setup, in the order they were first seen. */
  --s1: #8a63d2;
  --s2: #d08a1f;
  --s3: #1f8f8a;

  --radius: .5rem;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111318;
    --surface: #171a21;
    --sunken: #1d2129;
    --text: #e6e8ec;
    --muted: #a2a9b6;
    --faint: #737b89;
    --line: #262b35;
    --line-strong: #353b47;
    --accent: #7ea2ff;
    --accent-text: #0d1020;
    --good: #6fd197;
    --good-bg: #13291d;
    --bad: #ff8f8f;
    --bad-bg: #331618;
    --warn: #f0b27a;
    --warn-bg: #2e2117;
    --s1: #b398ff;
    --s2: #f2b456;
    --s3: #4fd1c9;
  }
}

* { box-sizing: border-box; }

body {
  margin: 0 auto; max-width: 52rem; padding: 2rem 1rem;
  background: var(--bg); color: var(--text);
  font: 15px/1.55 var(--font);
  -webkit-font-smoothing: antialiased;
}
/* A screen of digline view that is a grid, not a document, needs the room. */
body.wide { max-width: 68rem; }

h1 { font-size: 1.5rem; line-height: 1.25; margin: 0 0 .25rem; letter-spacing: -.01em; }
h2 { font-size: 1.1rem; margin: 0 0 .25rem; }
a { color: var(--accent); }
code { font-family: var(--mono); font-size: .86em; }

/* ------------------------------------------------------------ the report */

.aggregates { margin: 0 0 2rem; }
dl.meta {
  display: grid; grid-template-columns: max-content 1fr; gap: .3rem 1.25rem;
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: .9rem 1.1rem; margin: 1rem 0 2rem; font-size: .9rem;
}
dt { color: var(--muted); }
dd { margin: 0; }

.answer { border: 2px solid currentColor; border-radius: var(--radius);
          padding: 1rem 1.25rem; margin: 0 0 2rem; background: var(--surface); }
.answer.worse { color: var(--bad); }
.answer.fine { color: var(--good); }
.answer .verdict { font-size: 2rem; font-weight: 700; line-height: 1; }
.answer p { color: var(--text); margin: .75rem 0 0; }
.tally { list-style: none; display: flex; flex-wrap: wrap; gap: 1rem;
         padding: 0; margin: 1rem 0 0; font-size: .85rem; color: var(--muted); }
.tally b { color: var(--text); }

details { border-top: 1px solid var(--line); padding: .75rem 0; }
summary { cursor: pointer; font-weight: 600; }

table { border-collapse: collapse; width: 100%; margin-top: .75rem; font-size: .9rem; }
th, td { border-bottom: 1px solid var(--line); padding: .5rem .75rem .5rem 0;
         text-align: left; vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: .85rem; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.empty { color: var(--muted); font-style: italic; margin: .5rem 0 0; }

/* The diff of a file under test. Fixed width because alignment is the content,
   and coloured rather than only signed so the eye finds the change before it
   reads it. */
pre.diff { background: var(--sunken); border: 1px solid var(--line);
           border-radius: .375rem;
           padding: .75rem 1rem; overflow-x: auto; font-size: .8125rem;
           line-height: 1.45; margin: .5rem 0 1rem; white-space: pre; }
pre.diff span { display: block; }
.d-add { background: var(--good-bg); color: var(--good); }
.d-del { background: var(--bad-bg); color: var(--bad); }
.d-meta { color: var(--faint); }
.d-ctx { color: var(--muted); }
section.config { margin: 0 0 2rem; }
section.artifacts details { border-top: none; padding: .25rem 0; }
section.artifacts summary { font-weight: 400; }

/* ------------------------------------------------------- digline view */

nav.bar { display: flex; flex-wrap: wrap; gap: .5rem 1rem; align-items: baseline;
          border-bottom: 1px solid var(--line); padding: 0 0 .75rem;
          margin: 0 0 1.75rem; font-size: .9rem; }
nav.bar a { color: var(--muted); text-decoration: none; }
nav.bar a:hover { color: var(--text); text-decoration: underline; }
nav.bar .suite { color: var(--text); font-weight: 600; }
nav.bar .spacer { flex: 1; }
nav.bar .here { color: var(--text); font-weight: 700; }
/* A view another package added: in the menu, quieter than digline's own, with
   the package that added it beside its name (ADR 0061 §1, §5). */
nav.bar a.ext { color: var(--faint); }
nav.bar a.ext small { font-size: .75rem; margin-left: .3rem; }
/* This server writes nothing — a fact about the server, so it sits in the
   header beside the suite and never in a row. Lower case on purpose: it
   carries a flag somebody has to type, and `.chip` uppercases. */
nav.bar .readonly { background: var(--warn-bg); color: var(--warn); font-weight: 600;
                    border-radius: .25rem; padding: .1rem .45rem; font-size: .8rem; }

/* One row is one run: a readable moment, with its address beneath it. */
.when { font-weight: 600; white-space: nowrap; font-variant-numeric: tabular-nums; }
.key { display: block; font-family: var(--mono); font-size: .7rem; color: var(--faint);
       margin-top: .15rem; user-select: all; -webkit-user-select: all; }
.key:hover { color: var(--text); }

/* The digest of what was under test: a label beside the moment rather than
   a column of its own, read to group runs, not compared down a column. */
.stamp { display: inline-block; font-size: .7rem; color: var(--muted);
         margin-left: .5rem;
         font-family: var(--mono); }

body.wide td, body.wide th { white-space: nowrap; }
body.wide th { background: var(--sunken); padding-left: .5rem; }
body.wide td { padding-left: .5rem; }
body.wide tbody tr:hover { background: var(--sunken); }
tbody tr.is-baseline { background: var(--good-bg); }

/* The row's own actions, and — where a row can do less — the marker that says
   why, in the same place the missing button would have been. */
td.act, th.act { text-align: right; }
td.act form { display: inline; margin: 0; }
td.act .chip { margin-left: 0; }
td.act a.action { margin-right: .6rem; }
td.act button { font-size: .8rem; padding: .2rem .55rem; }
a.action { color: var(--accent); text-decoration: none; }
a.action:hover { text-decoration: underline; }

/* Produced under another configuration: comparable still, promotable no
   longer. Attenuated rather than hidden. */
tbody tr.stale td, tbody tr.stale td .delta { color: var(--faint); }
tbody tr.stale td.commit code { color: inherit; }

.chip { display: inline-block; font-size: .7rem; font-weight: 600;
        text-transform: uppercase; letter-spacing: .04em; padding: .1rem .45rem;
        border-radius: 999px; background: var(--good-bg); color: var(--good);
        margin-left: .4rem; vertical-align: .05em; white-space: nowrap; }
.chip.warn { background: var(--warn-bg); color: var(--warn); }
.chip.plain { background: var(--sunken); color: var(--muted); }

.delta { font-size: .75rem; font-variant-numeric: tabular-nums; display: block;
         margin-top: .1rem; }
.delta.up { color: var(--good); }
.delta.down { color: var(--bad); }
.delta.same { color: var(--faint); }

.picker { display: flex; flex-wrap: wrap; gap: .75rem 1rem; align-items: baseline;
          background: var(--surface); border: 1px solid var(--line);
          border-radius: var(--radius);
          padding: .75rem 1rem; margin: 1.75rem 0 .5rem; font-size: .9rem; }
button { font: inherit; font-size: .9rem; font-weight: 600; cursor: pointer;
         background: var(--accent); color: var(--accent-text);
         border: 1px solid transparent; border-radius: .375rem; padding: .35rem .8rem; }
select, input[type=text] { font: inherit; font-size: .9rem; color: var(--text);
                           background: var(--bg); border: 1px solid var(--line-strong);
                           border-radius: .375rem; padding: .25rem .4rem; }
input:focus-visible, button:focus-visible, select:focus-visible, a:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}

.votes { color: var(--faint); font-size: .75rem; font-variant-numeric: tabular-nums;
         margin-top: .15rem; }
td.absent { color: var(--faint); font-style: italic; }
.commit code { color: var(--text); }
pre.snippet { background: var(--sunken); border: 1px dashed var(--line-strong);
              border-radius: .375rem; padding: .75rem 1rem; overflow-x: auto;
              font-size: .875rem; user-select: all; -webkit-user-select: all; }
p.note, ul.note { color: var(--muted); font-size: .85rem; margin: .5rem 0 0;
                  max-width: 46rem; }
ul.note { padding-left: 1.25rem; }
ul.note ul { padding-left: 1.25rem; }
ul.note li { overflow-wrap: anywhere; }

/* A setup, in the hue it has everywhere on the page. */
.setup { font-family: var(--mono); font-size: .8rem; white-space: nowrap;
         padding: .05rem .45rem; border-radius: .3rem; border: 1px solid currentColor; }
.setup.s1 { color: var(--s1); }
.setup.s2 { color: var(--s2); }
.setup.s3 { color: var(--s3); }

/* The recorder's views: a declaration read back, four figures, a chart. */
p.declaration { font-family: var(--mono); font-size: .85rem; overflow-wrap: anywhere;
                background: var(--surface); border: 1px solid var(--line);
                border-radius: var(--radius); padding: .6rem .9rem; }
.figures { display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
           gap: .75rem; margin: 1rem 0; }
.figure { background: var(--surface); border: 1px solid var(--line);
          border-radius: var(--radius); padding: .7rem .9rem; }
.figure .label, .figure small { display: block; color: var(--muted); font-size: .8rem; }
.figure .value { display: block; font-size: 1.3rem;
                 font-variant-numeric: tabular-nums; }
td.said { max-width: 32rem; overflow-wrap: anywhere; }
.card { background: var(--surface); border: 1px solid var(--line);
        border-radius: var(--radius); margin: 1rem 0; }
.chart { padding: .5rem .25rem 0; }
.legend-note { font-size: .82rem; color: var(--muted); padding: 0 1.1rem .9rem;
                margin: 0; }

/* ---------------------------------------------------------------- uPlot
   uPlot 1.6.31, dist/uPlot.min.css, absorbed verbatim so there is one sheet.
   Copyright (c) 2022 Leon Sorokin. MIT licence: static/uPlot.LICENSE.
   The version is held equal to static/uPlot.iife.min.js by a test. */
"""

#: uPlot 1.6.31's `dist/uPlot.min.css`, absorbed verbatim: the file's bytes,
#: cut into literals only so no line is long. A test holds its digest to the
#: file in the npm tarball, so an edit to it is a red, not a drift.
UPLOT_CSS = (
    ".uplot, .uplot *, .uplot *::before, .uplot *::after {box-sizing: "
    'border-box;}.uplot {font-family: system-ui, -apple-system, "Segoe '
    'UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif, "Apple '
    'Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji";'
    "line-height: 1.5;width: min-content;}.u-title {text-align: center;"
    "font-size: 18px;font-weight: bold;}.u-wrap {position: relative;"
    "user-select: none;}.u-over, .u-under {position: absolute;}.u-under "
    "{overflow: hidden;}.uplot canvas {display: block;position: relative;"
    "width: 100%;height: 100%;}.u-axis {position: absolute;}.u-legend "
    "{font-size: 14px;margin: auto;text-align: center;}.u-inline {display: "
    "block;}.u-inline * {display: inline-block;}.u-inline tr "
    "{margin-right: 16px;}.u-legend th {font-weight: 600;}.u-legend th > * "
    "{vertical-align: middle;display: inline-block;}.u-legend .u-marker "
    "{width: 1em;height: 1em;margin-right: 4px;background-clip: "
    'padding-box !important;}.u-inline.u-live th::after {content: ":";'
    "vertical-align: middle;}.u-inline:not(.u-live) .u-value {display: "
    "none;}.u-series > * {padding: 4px;}.u-series th {cursor: pointer;}"
    ".u-legend .u-off > * {opacity: 0.3;}.u-select {background: "
    "rgba(0,0,0,0.07);position: absolute;pointer-events: none;}"
    ".u-cursor-x, .u-cursor-y {position: absolute;left: 0;top: 0;"
    "pointer-events: none;will-change: transform;}.u-hz .u-cursor-x, .u-vt "
    ".u-cursor-y {height: 100%;border-right: 1px dashed #607D8B;}.u-hz "
    ".u-cursor-y, .u-vt .u-cursor-x {width: 100%;border-bottom: 1px dashed "
    "#607D8B;}.u-cursor-pt {position: absolute;top: 0;left: 0;"
    "border-radius: 50%;border: 0 solid;pointer-events: none;will-change: "
    "transform;/*this has to be !important since we set inline "
    '"background" shorthand */background-clip: padding-box !important;}'
    ".u-axis.u-off, .u-select.u-off, .u-cursor-x.u-off, .u-cursor-y.u-off, "
    ".u-cursor-pt.u-off {display: none;}"
)

_AFTER = """
/* digline's own, after uPlot's, so the chart follows the theme. */
.uplot { font-family: var(--font); }
.u-legend { font-size: .8rem; color: var(--muted); }
.u-select { background: var(--sunken); }
.u-hz .u-cursor-x, .u-vt .u-cursor-y { border-right-color: var(--faint); }
.u-hz .u-cursor-y, .u-vt .u-cursor-x { border-bottom-color: var(--faint); }

/* Printing is the declared route to PDF, and a printed report that hides the
   regressions is a wrong report. Collapsed sections open on paper, and paper
   is light whatever the screen was. */
@media print {
  :root { color-scheme: light; --bg: #fff; --surface: #fff; --text: #000; }
  body { max-width: none; padding: 0; background: #fff; color: #000; }
  nav.bar { display: none; }
  details { display: block; }
  details > summary { list-style: none; }
  details > *:not(summary) { display: block !important; }
  details[open] > *, details:not([open]) > * { display: block !important; }
  .answer { border-color: #000; }
  a[href]::after { content: ""; }
}
"""

#: The sheet. Its uPlot section names the release its rules were absorbed from,
#: and a test holds that version equal to the header of the vendored
#: `static/uPlot.iife.min.js`, so upgrading one is a red until the other
#: follows (ADR 0061 §7).
SHEET = _OURS + UPLOT_CSS + _AFTER
