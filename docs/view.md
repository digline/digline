# `digline view` — the local browser UI

```console
$ digline view --suite suite.py
digline view on http://127.0.0.1:7373/ — ctrl-c to stop
```

Four screens over `.digline/`, stdlib only, no JavaScript, no state of its own:
no session, no preference, no cache. Restarting it loses nothing, because there
was nothing to lose. `--host` and `--port` are available; `--port 0` lets the
operating system choose and the printed line carries the bound port.

## The four screens

**Run list** (`/`) — key, date, environment, commit **and the aggregates**. It
is the table you choose a run to promote from, reading precision and accuracy
down a column and taking the median. Without the aggregates the choice cannot be
made and the first green run gets frozen as the baseline.

Every action belongs to a row; there is nothing to select first.

| On the row | What it does |
|---|---|
| `Compare` | this run against the baseline — `GET /compare?run=KEY` |
| `Make baseline` | promotes it — the one route that writes |

The button appears only where `promote_baseline` would accept. Where it does
not, a marker takes its place and its tooltip carries the sentence:

| Marker | Why there is no button |
|---|---|
| `BASELINE` | it already is the baseline; promoting it to itself is not an action |
| `OLDER SUITE` | produced under an earlier version of the suite — the row stays, attenuated: comparable still, since those numbers were measured, only under other rules |
| `N NOT JUDGED` | `N` cases errored, and an error is not a reference |

The order is `promote_baseline`'s own — the suite before errors — so the
page can never announce a different reason from the one the call would give. The
store's refusal stays underneath as the second line of defence.

Below the table, two pickers compare **any two runs**. Comparing with the
baseline is not among them: that question is the button on the row.

**Comparison** (`/compare`) — the exported report with a navigation bar in front
of it. It calls `render_html`, the same function `digline report` writes to a
file, so the unified diff of any file under test appears here too, above the
score deltas.

**History of a case** (`/case/<id>`) — one row per run, one column per
assertion, and for sampled assertions the **raw votes** under the combined
score. That is where judge noise is visible, and it is the calibration table
that used to be built by hand with a script.

**Suspension** (`/suspend/<id>`) — produces the line to add to the suite and
writes nothing. A suspension lives in the code, so the reason travels with the
case in the same review as everything else.

## The one route that writes

`POST /promote` goes through the same `promote_baseline` as `digline promote`,
with the same three refusals (tenant, configuration, errored verdicts), and it
**checks the `Origin` header**. Binding to loopback is not a boundary: any page
open in the developer's browser can POST to `localhost`, and this server needs
no credential to act. A missing `Origin` is allowed — that is `curl`, not the
attack — an `Origin` that is not ours is refused with `403`.

A path outside the routes is a `404` and never a file: the view serves pages it
renders, never bytes off the disk.

## What keeps it honest

Every screen is a pure function in `digline.report.pages`, so the tests are
about the page and not about a socket. Two of them are structural rather than
cosmetic:

- the comparison page, with the navigation bar and its stylesheet stripped out,
  must equal what `render_html` produces **byte for byte**. If the page and the
  exported document ever disagreed about a run, that would be a defect and not a
  difference of medium.
- the server is exercised once, end to end in a subprocess, for the two things
  only a real server can show: that the routes are wired, and that a POST from
  another origin is refused.

## See also

- [`api.md`](api.md) — the public API
- [`adr/0002-three-worlds-and-where-the-data-lives.md`](adr/0002-three-worlds-and-where-the-data-lives.md) — why the baseline is a reviewed artifact and what may cross a perimeter
