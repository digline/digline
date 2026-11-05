# `digline view` — the local browser UI

```console
$ digline view --suite suite.py
digline view on http://127.0.0.1:7373/ — read-only; --allow-promote to promote — ctrl-c to stop
```

Screens over `.digline/`, stdlib only, no state of its own: no session, no
preference, no cache. Restarting it loses nothing, because there was nothing
to lose. `--port` is available; `--port 0` lets the operating system choose
and the printed line carries the bound port.

**It listens on 127.0.0.1 and nowhere else.** There is no `--host`: it was
removed, and a command that passes it is refused. Under `--allow-record` the
page writes the recorder's switch and a suite's cases, and a page that writes
must not be one flag away from another network.
([ADR 0061](adr/0061-a-local-page-whose-views-other-packages-may-extend.md) §4)

**It promotes nothing unless you say so.** Without `--allow-promote` there is
no button on any row and `POST /promote` is not a route — a POST to it gets the
404 any unknown path gets. With it, it promotes only for the first browser
that opens the address it prints, and that address works once. See [below](#promotion-and-the-flag-that-enables-it).

## The screens

**Run list** (`/`) — key, date, environment, commit **and the aggregates**. It
is the table you choose a run to promote from, reading precision and accuracy
down a column and taking the median. Without the aggregates the choice cannot be
made and the first green run gets frozen as the baseline.

Every action belongs to a row; there is nothing to select first.

| On the row | What it does |
|---|---|
| `Compare` | this run against the baseline — `GET /compare?run=KEY` |
| `Open` | before the first promotion, in place of `Compare`: the run on its own, at the same address |
| `Make baseline` | promotes it — only under `--allow-promote` |

On a server started without the flag there is no `Make baseline` anywhere, and
nothing stands in its place: that is a fact about the **server**, not about a
run, so it is said once in the header beside the suite name and never down a
column of rows. The markers below are the other kind — *this run* cannot be
promoted — and they stay either way, because they go on being true.

Where the flag is given, the button appears only where `promote_baseline` would
accept. Where it does not, a marker takes its place and its tooltip carries the
sentence:

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

**Comparison, or diff** (`/compare`) — one route, two questions, and the
reference is what tells them apart.

Against the **baseline** — which is what the row's button asks, and what an
omitted `against` means — this is a run held against an approved reference.
That is `compare()`'s question, so the page is the verdict document: it calls
`render_html`, the same function `digline report` writes to a file, and the
unified diff of any file under test appears here too, above the score deltas.

With **no baseline yet** there is nothing to hold the run against, so the
page is the run on its own: `render_run_html`, which is what `digline report`
writes in the same state, with its cases and the sentence saying there is no
reference. It is what the first baseline is chosen from — the table above
carries aggregates only, and a first promotion made from a row of numbers is
made by somebody who has not seen one case.

Against **any other run** — the two pickers — neither side was approved by
anybody, so the page is the [diff report](diff.md) instead. Until ADR 0008 this
route rendered the verdict for every pair, which put two candidates under a
heading asking *"Did it get worse?"* beside a column called *"Reference"*: the
diff's need served with the verdict's semantics. A refusal from a diff — two
runs measured under different rules — arrives here as the **same sentence the
CLI prints**, because it is the same refusal and a refusal worded twice would be
two refusals.

**History of a case** (`/case/<id>`) — one row per run, one column per
assertion, and for sampled assertions the **raw votes** under the combined
score. That is where judge noise is visible, and it is the calibration table
that used to be built by hand with a script.

**Suspension** (`/suspend/<id>`) — produces the line to add to the suite and
writes nothing. A suspension lives in the code, so the reason travels with the
case in the same review as everything else.

## Where you are

The first entry of the menu, `/where/<tenant>/<suite>/`, says where the
project is and what comes next, read from `.digline/`: one state, the first
of these that holds, with two sentences, the command for the next step, and
the page that says more. The runs stay at `/`.

| State | When it holds | The next step |
|---|---|---|
| *Nothing recorded yet* | no recording, and the suite has never run | the three lines that start recording, for Python, Java, Node or any other language, quoted from [`record.md`](record.md), [digline for Java](record-java.md) and [digline for Node](record-node.md) |
| *Recording is off* | the switch says off, every recording has been imported, and the suite has never run | `digline record on`; a button only with `--allow-record` |
| *N calls named no suite* | every recording named no suite | the suite at the call site, or `--from _unassigned` |
| *N recordings in S, no suite yet* | the suite has recordings and no capture declaration | the recordings counted by the shape of their output, and [an agent's proposal](proposing-a-suite.md) or [the capture declaration](declarative.md#capture) |
| *N since the last import* | recordings after the last import, or never imported | the Recordings view |
| *The suite has never run* | no run | `digline run`, shown and never run |
| *The judge disagrees with a person on N* | the newest run has a contradicted reviewed answer or a calibration case outside its band | [Calibrating a judge](calibration.md), `digline explain` |
| *Green without a red* | the newest run exits 0 and no run ever failed a check | a counterexample, as [an agent's proposal](proposing-a-suite.md) adds one |
| *N answers from a new setup* | the setup in force first answered after the newest run, on cases an earlier setup answered too | the Across setups view |
| *Nothing to do* | the newest run exits 0 | none: the counts, and the last import |
| *The newest run exits N* | the newest run exits 1 or 2 for a reason none of the above names | `digline explain` |

It is `digline.host.where`, which reads the store, writes nothing and renders
nothing: the page lays out what it returns, and a command can print the same
value. A command it names is shown, never run, and the page has no button that
starts a run or a gate. The switch is a button only where the recorder's are,
under [`--allow-record`](#-allow-record), with the command under it.

## The recorder's views

Three more views sit beside the screens, in the menu of every page, for the
suite the server was started with and its tenant. Each calls the function its
command calls and renders what it returns, so a page and a command cannot say
two different things about the same recordings.
([ADR 0061](adr/0061-a-local-page-whose-views-other-packages-may-extend.md) §1)

**Recordings** (`/recordings/<tenant>/<suite>/`) — what
[`digline record import`](record.md#from-recordings-to-cases-digline-record-import)
lists, from the same `import_listing`. The declaration that says where a case
would go is at the head, then the setup in force, then each group with its
count, in the sentences the command prints. Each answer is a row: its id, when
it was first recorded, the setups it was recorded under, the first 200
characters of the answer, and how many recordings gave the same answer. A
longer answer links to a page that shows it whole, with the input it was given
(`/recordings/<tenant>/<suite>/<id>`). Nothing is ranked, scored or chosen in
advance, and nothing acts on more than one answer.

**Across setups** (`/setups/<tenant>/<suite>/`) — what
[`digline record compare`](record.md#comparing-setups-digline-record-compare)
shows, from the same `record_compare`: per case, the answers under each setup
in the order they were recorded, each with its digest. `?case=ID` keeps one
case, and two `setup` values put those two setups side by side with the keys
they differ on, as `--setup A B --show-setup` does: each value by its first
line, up to 60 characters, never a prompt whole, and a list of messages by its
first message's text and how many there are. For one case a chart draws
each answer's length over time, one colour per setup: the same answer recorded
again is a point at the same height. It shows, and judges nothing.

**Recorder** (`/recorder/<tenant>/`) — what
[`digline record status`](record.md#switching-it-on) says, from the same
`recorder_status`. Four figures open it: the size of the recordings as written,
the ceiling, the recordings held, and those still to import. The last is a
number only for the suite the server was started with, when it declares where
captured cases go, and otherwise says *not read*: the draft is the suite's
file, and only the suite says where it is. Then the switch, its values, each
marked declared or default, where the recorder writes, and the recordings by
suite.

A refusal reaches the page as the command prints it: another tenant's
recordings, a `setup` given once, a tenant name that is not a name. A suite
other than the server's is no page. **Without `--allow-record` the three views
read and write nothing**, and a page that would write says where the writes
are. With it, the recordings and the recorder carry the two writes
[below](#-allow-record).

## Promotion, and the flag that enables it

`digline view --allow-promote` is the server that promotes. `digline view` is
not, and that is the default.

**The flag is spelled in full, and so is every `view` option.** Other commands
accept a shortened option, `--loc` for `--locale`, but `view` does not. The
Claude Code plugin asks a person before any command carrying
`--allow-promote`, and it recognises the flag by its name. On 0.20.0, `--a`
started the same server and nobody was asked, so now the full word is
the only spelling `view` takes.

The reason is not that the two surfaces should match. It is the reason the MCP
server has no `promote` tool, applied to the same facts: a baseline is an
**approved reference**, the approval is a person's, and a rule about who
decides is not satisfied by a surface that lets a non-person decide, whatever
that surface is called. The default falls on the cheap side of an asymmetry —
forgetting `--allow-promote` costs a restart and the header tells you which
eight characters to add; forgetting a hypothetical `--read-only` costs an
unreviewed baseline, silently. ([ADR 0032](adr/0032-the-second-path-to-an-absent-tool.md))

Without the flag the refusal is an **absence**, in both places a caller looks:
no button on the page, and `/promote` is not a route on the wire. A POST to it
answers `404 no such action`, the same as any unknown path — not `403`, which
would say *you may not* and so imply a someone who may. Both come from one
value, so the page and the dispatcher cannot drift into offering a button the
route rejects.

The Claude Code plugin's hook stays silent on `digline view` and asks a person
about `digline view --allow-promote`. The flag is not a smaller thing than
`digline promote` but a larger one: the same decision, made ambient for every
run in the store for as long as the server is up.

### It promotes for the browser that opens the address it prints

```console
$ digline view --suite suite.py --allow-promote
digline view on http://127.0.0.1:7373/?launch=… — promotion enabled, for the first browser that opens this address — ctrl-c to stop
```

Open **that** address. The server trades the `launch` value for a cookie and
sends you to `/` without it, and from then on `Make baseline` works
in that browser until the server stops. A POST without that cookie — a
`curl`, a script, an agent's shell, another browser — is refused with `403`.

**The address works once.** Opening it spends the key: the browser gets a
separate secret as its cookie, and the same address opened again is refused.
This matters because the address does not stay in your terminal. A browser
writes the pages it opened into its history file, and the key used to stay
valid there for as long as the server ran. In 0.21.0, a process that read that
file could promote with it. (ADR 0033 §11)

The flag decides whether this server may write. It cannot decide who is asking,
and before this, once a person had started the flagged server, any process of
that user could move the baseline with one POST, and the plugin's hook never
saw it. The key is what closes that. ([ADR 0033](adr/0033-the-server-that-promotes-for-one-browser.md))

- **There is nothing to configure.** The key is minted when the server starts
  and held in its memory — never written to disk, never read from a file or the
  environment, and no option sets or disables it. A key that could be supplied
  would live somewhere every process of the same user can read, and a key that
  could be switched off would become the control nobody reads.
- **It is never in a page.** Every screen answers anybody on the machine, so the
  key only ever appears on the startup line.
- **What changes for you:** restarting the server gives a new key, so an open
  tab or a bookmark from the last start is refused, with a sentence saying why.
  `localhost` and `127.0.0.1` are different hosts to a browser, so stay on the
  one the line printed. **A second browser, or the right one after opening the
  address in the wrong one, needs a restart and the new address**: the old
  address has been spent.
- **Why a `403` here and a `404` on the default server.** On the default server
  nobody may promote, so `/promote` does not exist. Here somebody may, so a
  caller without the key is refused rather than told there is nothing here.
  Same fact, two servers, two truthful answers.

With the flag, `POST /promote` goes through the same `promote_baseline` as `digline promote`,
with the same refusals, and it **checks the `Origin` header**. The form carries
the key of the baseline the page was drawn against, as `--replacing` does on the
command line: if somebody promoted in between — a second tab, a second person on
the same server — the promotion is refused and names both keys rather than
replacing a reference nobody on this page compared against. Binding to loopback is not a boundary: any page
open in the developer's browser can POST to `localhost`. A missing `Origin` is
allowed — that is `curl`, which the launch key refuses instead — and an
`Origin` that is not ours is refused with `403`. The origin check stops a page;
the key stops a process.

A path outside the routes is a `404` and never a file: the view serves pages it
renders and three files of its own, by name, never a path off the disk.

**What one connection can cost the server is bounded.** A promotion form is at
most 4096 bytes. A larger declared `Content-Length` is refused with `413`
before any of the body is read. A length that is not a count is refused with
`400`, and so is a body that ends before its declared length. Every connection
has 30 seconds to send its request and to take its answer. A body that stops
arriving is answered `408`, and headers that stop arriving are dropped.
Without these limits, one caller that declared a large body or went quiet held
a server thread for as long as it liked.

## What a browser may run

Every response carries one policy:

```text
Content-Security-Policy: default-src 'none'; style-src 'self'; script-src 'self'; form-action 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
```

`same-origin` lets a form this server served say where it came from, so the
origin check lets it write, and sends no referrer to any other site: a run key
in an address does not leave with a link. A request whose `Origin` is `null`,
as a page opened from a file sends, is refused, and says so.

Styles and scripts come from the server's own files, and nothing is inline: no
`style` attribute, no `<style>`, no `<script>` with a body that runs. A data
block, `<script type="application/json">`, is the one `<script>` without a
`src` a page may carry: a browser does not run it. A test parses every page the
server sends and holds that. It parses rather than searches, because an answer a
model gave can hold the characters `style=`, and the page shows it as text.

**One stylesheet, the report's and the server's.** System fonts, tabular
figures, and a light and a dark theme that follow the system. `digline report`
writes it inline, because a report is opened from disk; the server serves it at
`/static/digline.css` and every page links to it.

**Two scripts are served.** uPlot runs on one page, the answers across setups
for one case, where it draws the chart. digline's own script runs there and on
every page with a form that writes, where it keeps the command line under the
button equal to the form. Every other page carries no script.

| File | Bytes | Licence |
|---|---|---|
| `/static/uPlot.iife.min.js`, uPlot 1.6.31 | 50 312 | MIT, Copyright (c) 2022 Leon Sorokin, `uPlot.LICENSE` beside it in the package |
| `/static/chart.js`, digline's | 3 705 | digline's |

uPlot's own stylesheet, 1 857 bytes, is absorbed into the one sheet. Without
JavaScript every page still reads and every form still writes; what is missing
is the chart, and a command line that follows the form as it is edited.

## `--allow-record`

```console
$ digline view --suite eval/suite.py --allow-record
digline view on http://127.0.0.1:7373/?launch=… — the recorder's writes enabled, for the first browser that opens this address; --allow-promote to promote — ctrl-c to stop
```

The flag serves the page's two writes, and nothing else:

- **The recorder switched on or off** for the tenant, on its page, through
  `switch_on` and `switch_off`, the functions `digline record on` and `off`
  call. The form is served with the values the switch file declares; a field
  left empty keeps what the file has, as a flag not given does.
- **Recorded answers written as cases** with a person's yes or no, on the
  recordings, through `import_listing` and `import_elect`, the functions
  `digline record import` calls. Each answer that can be named has `--good`
  and `--bad` beside it, neither chosen; the person types their own name in
  the form, the `--by` the cases carry, and the page reads it from nowhere
  else. There is no *import all*, nothing is chosen in advance, and nothing is
  ranked.

**Under each button, the command that does the same thing**, with the values
in the form: `digline record on --tenant acme --sample 0.5`,
`digline record import --tenant acme --suite eval/suite.py --good ID --by
'Ada Lovelace'`. The server writes it for the form as served; digline's script
keeps it equal to the fields as they are edited, and without the script it
stays as served. A test parses every line the page serves with digline's own
parser, and runs the form and the command on two copies of one store and
finds them identical.

**A write is a POST, answered with a `303`** to the page that reads what it
wrote, so a reload reads and never writes again. A refusal is the command's
sentence, with a `400`, and nothing written. Like promotion, every write needs
the cookie of the browser that opened the address the server printed, the key
is spent on that first opening, and a request from another origin is refused.
Without the flag there is no form and no route: a POST gets the `404` any
unknown path gets. `--allow-record` does not promote, and `--allow-promote`
does not write the recorder; the two together share one key.

Like `--allow-promote`, it is spelled in full, and the Claude Code plugin asks
a person before a command that carries it.
([ADR 0061](adr/0061-a-local-page-whose-views-other-packages-may-extend.md) §2, §4)

## Views from other packages

A package adds a page by declaring an entry point in the group `digline.views`:

```toml
[project.entry-points."digline.views"]
latency-drift = "acme_views:VIEW"
```

- **The name is the address and the label.** Lowercase letters, digits and
  hyphens. The view is served at `/x/<name>/`, and the menu of every screen
  lists it with the package that declared it beside it. A name that is not one
  of those, or a name two entry points share, stops the server when it starts,
  every offender named.
- **The value is loaded the first time its address is asked for**, never to
  draw the menu. It is an object with one method, `render(context) -> str`,
  that returns the body of the page. `context` is a
  `digline.report.ViewContext`: the directory that holds `.digline/`, the
  locale and the parsed query. The body escapes what it carries, with
  `digline.report.escape`, and carries nothing inline.
- **Read only.** A view answers GET. A POST to its address gets the `404`
  any unknown path gets, and nothing in its context can write.
- **A view that fails** gives a page that names it and its package, with a
  `500`. What it raised goes to the standard error of the terminal that
  started the server, and every other page keeps answering.

The contract is `digline.report.View`, `ViewContext` and `MenuEntry`, and
the group name is `digline.report.views.GROUP`.
([ADR 0061](adr/0061-a-local-page-whose-views-other-packages-may-extend.md) §5)

## What keeps it honest

Every screen is a pure function in `digline.report.pages`, so the tests are
about the page and not about a socket. The recorder's views are pure functions
too, in `digline.cli.recorder_pages`, because the import's structure lives in
`digline.host`, which the report may not import. Two of the tests are
structural rather than cosmetic:

- the comparison page, with the navigation bar stripped out and the sheet put
  back inline where the page links to it, must equal what `render_html`
  produces **byte for byte**. If the page and the exported document ever
  disagreed about a run, that would be a defect and not a difference of medium.
- the server is exercised end to end in a subprocess, for the things only a
  real server can show: that the routes are wired, that a POST from another
  origin is refused, that the default server answers `POST /promote` with a
  404 **and leaves the baseline where it was** — a refusal that only returned
  the right status would prove nothing about the store — and that the flagged
  server answers a POST without its key with a 403, the store read on both
  sides again.

## See also

- [`api.md`](api.md) — the public API
- [`adr/0002-three-worlds-and-where-the-data-lives.md`](adr/0002-three-worlds-and-where-the-data-lives.md) — why the baseline is a reviewed artifact and what may cross a perimeter
