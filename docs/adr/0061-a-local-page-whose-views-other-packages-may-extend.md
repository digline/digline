# ADR 0061 — A local page over `.digline/`, whose views other packages may extend

- Status: accepted 2026-11-04, by Alessandro Prandini, the text first, as it
  stands at `84d8ca79`: every item marked *decided here* taken, with the
  names it proposes (`--allow-record` and the address `/x/<name>/`).
  Proposed 2026-11-03. **Its decisions were ruled before this record
  was written**, on 2026-11-03, in the conversation of the session that wrote
  it, after a reading of what `digline view` and `digline record` already
  hold. They are stated here as ruled. **What this record adds is marked
  *decided here***: the flag that serves the two writes, where the contract of
  an extension lives, and the shape of an extension's name. Each was proposed,
  for acceptance to take or remove item by item. *Revised 2026-11-03, the
  same day, after a mockup in two variants:* the maintainer chose a stylesheet of digline's own over a
  vendored framework, and §4.4, §5 and §7 carry what that choice ruled. The
  mockup was built outside the repository and is not part of this record
- Shipped: unreleased
- Date: 2026-11-03
- Opens: **nothing at this record's landing.** No `SCHEMA_VERSION`, no
  `OUTPUT_VERSION`, no `RECORDING_VERSION` and no line of `_STEPS`. The page
  reads what the store already holds and writes what `digline record` already
  writes
- Amends, each by a dated note beside the place it amends, which points here.
  Every text is kept as written:
  - [ADR 0058](0058-the-recorder-a-call-recorded-where-the-application-makes-it.md),
    *Not decided here*, the first half of its last item, *"A review interface
    over recordings"*, which this record decides;
  - [ADR 0032](0032-the-second-path-to-an-absent-tool.md) §4a, its third
    finding, *"`--host` is the control that moves the view out of world 1"*,
    filed there and not ruled, which §4 here closes by removing the option;
  - [ADR 0033](0033-the-server-that-promotes-for-one-browser.md) §6, whose
    first bullet names *"the `--host` record"* as the place that question
    would be answered
- Assumes: [ADR 0023](0023-capture.md) §4 (elected by a person, nothing
  ranked or pre-selected), §7 (*the commit signs*, and no agent makes it), §9
  (the election is never the operator's, and is absent from the MCP);
  [ADR 0032](0032-the-second-path-to-an-absent-tool.md) §1 (`view` writes
  nothing by default, and a flag enables a write) and §2 (the refusal is an
  absence); [ADR 0033](0033-the-server-that-promotes-for-one-browser.md) §1
  (the key has no home), §2 (how it reaches a browser), §4 (the key is not a
  second control), §5 (what it does not do) and §11 (spent on its first
  hand-over); [ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)
  §1 (where it applies) and §6 (what a page that elects may not do);
  [ADR 0043](0043-a-message-digline-did-not-write.md) (a message digline did not
  write reaches the person who ran the command);
  [ADR 0058](0058-the-recorder-a-call-recorded-where-the-application-makes-it.md)
  §4 (the import refuses another tenant), §8 (an episode's setup, declared in
  code with `setup=`) and §10 (the switch);
  [ADR 0059](0059-a-reviewed-answer-a-grouped-listing-a-source-as-data.md),
  accepted, §1 (the yes or no and the person's mark) and §3 (the grouped
  listing)
- Touches: nothing in `CLAUDE.md`'s *fixed* section moves. Decision 5 is
  upheld: the page makes no network call and loads nothing from outside the
  installed package, and the one library it serves is shipped inside that
  package (§7). Decision 9 is upheld and narrowed: the one option that
  moved `view` out of world 1 goes (§4). Decision 2 is not touched: the page
  reads and writes `.digline/<tenant>/` through the functions that already do
- Number: 0061. Swept on 2026-11-03, before a line was written, across
  `origin/main` (`80cf7557`), whose highest record is 0058; the branches on the
  remote, `adr-amend-0058-0023` (`bee7cad4`, highest 0059), `capture` (highest
  0023) and `schema-23-trajectory` (`cd71a383`, highest 0057); every worktree
  of this repository; and the open pull requests, #888 (0059) and #869 (no
  record). 0060 is reserved for a record being written in another session
  and is not taken here
- Owed: the three lines on digline.dev that every new record needs (the nav,
  and the two tables the site builds its pages from). Until they land, the
  `docs` job reads red on this record's pull request, which is the state the
  site's runbook expects, and no required check reads it

**How to read the clauses.** *Ruled* is a decision taken before this record
and transcribed. *Decided here* is a name or a detail this record proposes,
and acceptance rules on it.

## Context

**A local server over `.digline/` already exists.** `digline view` serves four
screens on loopback, from `ThreadingHTTPServer` in the standard library
(`src/digline/cli/view.py:68`, `serve()` at `:804`). Every screen is a pure
function in `src/digline/report/pages.py` that takes values and returns a
string, and the comparison screen calls `render_html`, the function `digline
report` writes to a file. The pages contain no script: `<script` occurs zero
times in `pages.py` and in `render.py`, read at `80cf7557`. The one write,
`POST /promote`, exists only on a server started with `--allow-promote` (ADR
0032 §1), and only for the browser that spent the launch key (ADR 0033).
`Host` is checked against the address the server bound to on every route, and
`Origin` against that same value (`view.py:472-488`). The tests run the server
on loopback inside the pytest process and talk to it with `http.client` and
`urllib` (`tests/test_view.py:553`, `:569`). No browser is involved.

**The recorder's writes are host functions already.** `digline record on` and
`off` call `switch_on` and `switch_off` (`src/digline/host/recording.py:36`,
`:73`). `digline record import` calls `import_listing` and then `import_elect`
(`src/digline/host/importing.py:235`, `:319`), after `load_suite`
(`src/digline/host/loader.py:587`). `recorder_status` (`recording.py:130`) is
what `digline record status` reads, and `recorder_status_json`
(`src/digline/wire/recorder.py:89`) is its `--json`. **Some of what a person
reads at the import is written only in the command**:
`cmd_record_import` (`src/digline/cli/main.py:1386-1460`) counts identical
answers, prints the setup in force, and says what is not a case and why. A page
that showed the same listing would have to say it a second time.

**ADR 0058 left the question open.** Its *Not decided here* ends with *"A
review interface over recordings, and recording a response flagged from inside
the application. Neither is part of this record."*

**And ADR 0023's rule is about a person.** The election is a person's
(§4), *no agent makes it* (§7), and it is absent from the MCP server (§9). A
command line keeps that rule by who types the command. A page over HTTP
answers whoever reaches the port, and on a developer's machine an agent
reaches it with `curl`.

## Decision

### 1. What the page reads

*Ruled.* `digline view` gains the views of the recorder, beside its four
screens, and serves them on the same server:

- **the recordings of a suite, grouped**, as the import lists them: the
  grouping of ADR 0059 §3, from `import_listing`;
- **one case compared across setups**, from the host function that the
  command line's own comparison calls. That function and its command are
  designed elsewhere; the page calls the function and renders what it returns,
  and does not compute a comparison of its own;
- **the state of the recorder**, per tenant: the switch, its values, where it
  writes, the size and the ceiling, from `recorder_status`;
- **the latest report**, which is the screen `view` already serves.

**Every view calls the function the command calls, and renders what it
returns.** A page and a command that compute the same fact twice are two
places that can disagree, and the one that is wrong is the one nobody runs.
This is `pages.py`'s rule, *one function that can be wrong*, carried to the
recorder.

**Required of the import before the page, and not built here:** the lines
`cmd_record_import` prints that are not in `ImportListing` (the identical
answers counted, the setup in force, what is not a case and why) move into a
function outside `digline.cli` that both the command and the page render
from.

**Two pieces of shape, ruled.** The recorder's page opens with four figures
for the tenant: the size of its recordings and the ceiling (`size` and
`ceiling` in `TenantRecorder`), the recordings held (the calls and episodes
`SuiteRecordings` counts), and those still to import (`since_last_import`,
which is read only for a suite whose draft was read, and otherwise says *not
read* rather than a number). And the menu shows, beside each view another
package added (§5), the name of the package that added it.

### 2. The two writes

*Ruled.* The page writes two things, and only these:

1. **The recorder on or off, for a tenant**, through `switch_on` and
   `switch_off`, with the values `digline record on` takes.
2. **A recorded case imported, with the person's yes or no**, through
   `import_listing` and `import_elect`. Where the import asks for the person's
   mark (ADR 0059 §1, accepted), the person types it in the form, as on the
   command line, and the page reads it from nowhere else.

**The same host code, and under every button the line of the command.** Each
form posts to a route that calls the host function the command calls, with the
arguments the command would pass. Every refusal the function raises reaches
the page as the command prints it, and the page has none of its own. Under
each button the page prints the command that does the same thing, with the
values in the form. For example, `digline record on --tenant northwind`, or
the import with the flags it has when the page is built. The person can always
see that the button is the command, and can always run the command instead.

**Declaring a setup is not a write of the page.** An episode's setup is
declared in the application's code, with `setup=` on `digline.episode`
(ADR 0058 §8), and a single call's setup is derived from the request. There is
nothing in `.digline/` for a page to write.

**At the page, ADR 0037 §6 is the rule for the import.** *Decided here.* The
reason that section gives is about a page and not about a world. The command's
*"two invocations and not a dialogue"* falls at a page, and everything it
protected is required of the page, word for word: nothing ranked, scored or
starred; nothing pre-selected; no *import all*, no *import this group*, and no
threshold under which the page imports on its own. ADR 0037's other sections,
on which party elected and the line recorded at the software house, are about
a person who does not own the text, and do not apply to a developer importing
their own recordings. The import still refuses another tenant's recordings
(ADR 0058 §4), and that refusal is `import_listing`'s, not the page's.

### 3. Never the gate

*Ruled.* **No route of the page runs a suite, re-judges a run, or returns a
verdict on one.** The page has no exit code, and nothing it serves is read as
one. The writes above change what the next run will find: the switch, and the
cases file. They decide nothing about a run that has already happened.
Promotion stays where ADR 0032 and ADR 0033 put it: absent, unless the server
was started with `--allow-promote`.

### 4. Security

*Ruled, four points.* The page runs on the developer's machine and nowhere
else, and its threat is not the network. It is another process of the same
user, an agent among them, which reaches loopback with `curl` and reads
whatever the server prints.

1. **It listens on 127.0.0.1, and `digline view` takes no `--host`.** The
   option goes. ADR 0032 §4a filed it as *"the control that moves the view out
   of world 1"*, *"unconstrained and uncontrolled"*. A page that writes the
   switch and the cases file must not be one flag away from another network.
   `Host` and `Origin` are still checked against the bound address on every
   route (`view.py:472-488`), because a page on loopback is reachable from any
   page in the developer's browser.
2. **A write is a POST, and only a POST writes.** Every POST that succeeds is
   answered with a 303 to the page that reads what it wrote. A GET never
   writes, so a link, a prefetch or a reload cannot write.
3. **Every POST requires ADR 0033's launch key, as its cookie.** The key is
   minted when the server starts and held in memory. It is printed once, in
   the address the startup line gives, and spent on its first hand-over for a
   second secret set as an `HttpOnly`, `SameSite=Strict` cookie (ADR 0033 §2,
   §11). A POST without that cookie is refused. There is no option to pass a
   key, and none to turn it off (§4 there).
4. **Nothing inline, and a strict policy that says so.** *Revised the same
   day, ruled.* Every response carries
   `Content-Security-Policy: default-src 'none'; style-src 'self';
   script-src 'self'; form-action 'self'; frame-ancestors 'none'`, with
   `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`.
   - **Styles and scripts come from the server's own files** (§7), and from
     nowhere else: no `style` attribute, no `<style>` element, and no
     `<script>` with a body that runs. The one `<script>` without a `src` that
     a page may carry is a data block of `type="application/json"`, which a
     browser does not run and the policy does not govern. It carries numbers
     and setup identifiers, with `<` written `<`.
   - **No `img-src`.** No page shows an image: `<img`, `<svg`, `data:image`
     and `url(` occur zero times in `render.py` and `pages.py`, read at
     `80cf7557`. The chart draws on a canvas, which needs none.
   - **Every button is a `<form method="post">`**, and it writes with
     JavaScript disabled. The script of §7 is progressive: without it, every
     page still reads and every form still writes.
   - **The rule is a test.** It parses every HTML response the server sends,
     with `html.parser`, and finds no `style` attribute, no `<style>`, and no
     `<script>` that has neither a `src` nor `type="application/json"`. It
     parses rather than searches, because an answer a model gave can hold the
     characters `style=`, and the page shows it escaped as text.

**The launch key is how ADR 0023's rule holds at a page.** *A person, never an
agent* is kept on the command line by who types the command. At a page it is
kept by who holds the cookie. The key is printed on the terminal of the person
who started the server, and the cookie exists only in the browser that opened
that address. An agent that reads a result and concludes that a case should be
imported finds that one POST is not enough. That is the caller ADR 0033 §5
names, *the caller acting on inference*, and the key is what refuses it.

**What the key cannot answer, and what does.** *Decided here.* ADR 0033 §5
says it plainly: *"A server an agent starts itself is the agent's."* An agent
that starts `digline view` reads the startup line, holds the key, and could
import. So the two writes follow ADR 0032 §1, as promotion does. **They are
absent from the server unless it is started with `--allow-record`.** Without
the flag there is no form and no route, and a POST gets the 404 that any
unknown path gets (ADR 0032 §2). The plugin's hook asks a person before a
command that carries the flag, as it asks before `--allow-promote`. Today it
watches that one flag on `view`
(`plugins/digline/scripts/ask_a_person.py:69`). The flag is reachable by
intention and unreachable by inertia, which is ADR 0032 §1's reason, and the
key is the one control behind it (ADR 0033 §4). The flag's name is proposed;
the rule that the writes sit behind a flag is not.

### 5. Views from other packages

*Ruled.* **Another package adds a view by declaring an entry point**, on the
model of `digline.recording_maps` (`src/digline/recorder.py:173`): the name
says what the view is without importing anything, and the value is loaded
only when it is needed.

- **The group is `digline.views`.**
- **What an entry point gives.** *Decided here.* Its **name** is the view's
  address segment and its label in the menu: lowercase letters, digits and
  hyphens, and refused by name otherwise. The view is served at
  `/x/<name>/`, a prefix no screen of digline's uses, so two packages can
  collide with each other and never with digline. Two entry points with one
  name are refused when the server starts, both named. Its **value** is an
  object with one method, `render(context) -> str`, which returns the body of
  the page. The `context` carries values and no capability: the store's root,
  the locale and the query. A view that needs the store reads it through the
  read functions of `digline.host`, as any package may.
- **Loaded on first access.** The menu is built from the names, which are read
  from the installed metadata without importing any package. A view's module
  is imported the first time its address is requested. A value that does not
  load gives a page that names the entry point and its package. The message
  of the exception reaches the server's standard error, the perimeter of the
  person who started it (ADR 0043), and the rest of the server keeps
  answering.
- **Read only.** An extension serves GET and nothing else. A POST to an
  extension's address gets the 404 that any unknown path gets. The context
  holds neither the key nor the cookie, and no write of §2 is reachable
  through it. A package that wants to write offers a command, and that command
  is its own.
- **The contract lives outside `digline.cli`.** *Decided here:* in
  `digline.report`, beside `pages`, as a `Protocol` and a frozen dataclass for
  the context. `CLAUDE.md` forbids any package under `packages/` to import
  `digline.cli`, and `view.py` is there.
- **digline wraps what the view returns** in its own document: the sheet of
  §7, the navigation, and the headers of §4. An extension brings no
  stylesheet and no script, and the policy of §4.4 refuses one it inlines. The view returns a body,
  and escapes what it puts in it, with the `escape` that `digline.report`
  exports.
- **The dispatch becomes a table.** Today `do_GET` dispatches on literals
  (`view.py:489-514`), and the comment above it records why the old `_ROUTES`
  tuple was removed: it was read by nothing (ADR 0032 §2). With routes that
  arrive from installed packages there has to be a table, and this time it is
  the one the dispatch reads.

### 6. Tests, with no browser

*Ruled.* **No browser runs in the gate.** The page is tested the way
`digline view` is:

- **most of it without a socket.** Every view is a pure function that takes
  values and returns a string, as in `pages.py`. Its tests call the function;
- **the server in the pytest process**, bound to loopback on a free port, in a
  thread, and reached with `http.client`, as `tests/test_view.py` does. These
  tests hold §4:
  - a request addressed to another name, or from another origin, is refused;
  - a POST without the cookie is refused, and a spent key is not accepted
    twice;
  - a GET to every route writes nothing;
  - without `--allow-record`, the forms are absent and their routes answer
    404;
  - a POST to an extension's address answers 404;
  - every response carries the policy of §4.4, and no HTML response carries
    anything inline (§4.4, the rule as a test);
  - the command line served under each form is the command for the values
    the form is served with;
- **each write against its command.** A test runs the form and the command on
  two copies of one store, and the two stores come out identical;
- **each command line printed under a button is parsed by digline's own
  parser** in a test, so a renamed flag turns the page red, not the person's
  terminal;
- **an extension without an installed package.** The entry points are read in
  one function, and a test replaces that function, as
  `tests/test_registry.py` replaces `digline.targets.registry._entry_points`;
- **each refusal held by a mutation** that makes its test fail, as
  `CONTRIBUTING.md` requires of every test.

**What the gate does not run: the script of §7.** With no browser, nothing in
the gate executes it. What is tested is what it reads: the data block, and the
flag each field names. That bound is why the script holds no flag name and no
number of its own.

### 7. One stylesheet, one chart, one script

*Ruled, the same day, after the mockup.*

**One stylesheet of digline's own, shared by the HTML report and the page.**
- **What it holds.** System fonts and no web font, tabular figures in every
  column of numbers, and a light and a dark theme from
  `prefers-color-scheme`. Each setup has one colour, and that colour is the
  same in a table, in the chart and in the rows that name the setup.
- **Where it lives.** It is one string in `digline.report`, where `CSS` is
  today, so the report's functions stay pure. It replaces `CSS` and
  `VIEW_CSS` both.
- **How each document carries it.**
  - The report written to a file carries it inline. A file opened from disk
    has no server to fetch from and no policy.
  - The server serves the same string at an address of its own, and every
    page it sends, the report screen included, links to it instead. That is
    what lets §4.4 say `style-src 'self'`.

**uPlot, vendored, in the comparison across setups and nowhere else.**
- **The library.** uPlot 1.6.31 (MIT), the series of one case over time, one
  colour per setup. It is shipped in the package as one file, with its
  licence beside it.
- **Its stylesheet is absorbed into the sheet above.** It is 1 857 bytes of
  rules for the legend and the cursor, and the sheet has to restyle them for
  the dark theme anyway. Absorbed, there is one stylesheet. The rules keep
  uPlot's copyright line in a comment that names the version. A test holds
  that version equal to the one in the vendored file's header, so an upgrade
  of one is a red until the other follows.
- **What it does to styles.** It sets styles through the CSSOM (`.style.width`
  and the like), and never through a `style` attribute, `cssText` or
  `innerHTML`. That was read in the minified file, not measured in a browser
  under the policy.
- **Who updates it.** Dependabot does not see a vendored file, so an upgrade
  is by hand.

**The glue: one script of digline's own, served from the same origin.** It
does two things:
- **(a) It gives uPlot the numbers.** It reads them from the page's data block
  (§4.4), and it reads the colours from the sheet.
- **(b) It keeps the command line under each form equal to the form's
  fields as they are edited.**
  - **The line is the command the button will run.** Each field names the
    flag it fills, in an attribute the server writes, and the script holds
    no flag name of its own. It joins what the page names.
  - **What the server guarantees.** The line it serves is the command for the
    values the form is served with (§6).
  - **Without the script, the line can lag the form.** An edited field leaves
    the line as served until the form is posted, and the page that answers
    the POST shows the command that ran.

    *Noted 2026-11-04 (#904), the bullet above kept as written.* The page that
    answers the POST is the one the 303 leads to, and it shows the state the
    write left, read back from the files: the switch on or off, the answers
    *already in the file*. It does not show the command that ran. The server
    keeps nothing between two requests, and a line carried in the address to
    the next one would be text any link could make the page say.

**Weights**, measured with `wc -c` and `gzip -c` on 2026-11-03, on the mockup
and on the vendored files:

| File | Bytes | Gzip | Licence | Served on |
|---|---|---|---|---|
| uPlot 1.6.31, `uPlot.iife.min.js` | 50 312 | 21 730 | MIT, Copyright (c) 2022 Leon Sorokin, the file beside it | the comparison across setups |
| uPlot 1.6.31, `uPlot.min.css` | 1 857 | 772 | the same | absorbed into the sheet |
| the glue, digline's | 1 969 | 935 | digline's | the comparison across setups, and every page with a form |
| the sheet, digline's | 10 843 | 3 077 | digline's | every page, and inline in the report |

- **The glue's figure is the mockup's,** and it covers (a) alone. (b) is not
  written yet.
- **The sheet's figure is the mockup's**, before `CSS` and `VIEW_CSS` are
  folded into it.
- **The other variant, Pico.css 2.0.6** (82 194 bytes, 11 618 gzip), is not
  shipped.

## What does not change

- **`digline view` without a flag writes nothing**, as ADR 0032 §1 has it.
- **`--allow-promote` is unchanged**, and so is the key that serves it.
- **The commands stay.** Everything the page does, `digline record` does, and
  the page adds no write the command lacks.
- **The recorder is unchanged.** The page reads its files and writes its
  switch through the functions that already do.
- **The MCP server gains nothing.** No tool reads or writes what the page does
  (ADR 0023 §9).

## Consequences

**A person can read the recordings, switch the recorder and import cases on
one page**, and can see under every button the invocation they could have
typed.

**`digline view --host` is removed**, and that changes a command-line option.
Under `RELEASING.md`'s *Choosing the version*, a CLI option removed moves the
minor and not the major, and the CHANGELOG says so at the release that carries
the code. Anyone who served `view` beyond loopback loses that, and it is the
case ADR 0032 §4a filed as decision 9's question.

**The HTML report adopts the sheet of §7 in the release that ships the
page**: the report's look changes with it. Its content, its order and its
self-contained file do not: the sheet travels inline in it, and the report
still has no script.

**The page carries JavaScript for the first time**: uPlot on one view and the
glue. What changes for a reader without it is the chart, which is absent, and
the command line, which can lag an edited field. The policy of §4.4 names the
server as the one source of both.

**Installed packages can put pages on a developer's local server.** They are
read-only, served under their own prefix and wrapped in digline's policy. What
a package's view shows is that package's code, run in the developer's process,
like any library they installed.

## Not decided here

- Every view and every write this record does not name.
