# Changelog

Each release tells its story here — what changed, what it means for a reader
upgrading, and what deliberately did not move. The reasoning lives in
[`docs/adr/`](docs/adr/); this says what to expect. For the one-line version,
read the [release titles](https://github.com/digline/digline/releases) — the
notes under them are this file, verbatim.

## 0.19.2 — 2026-09-24

digline **0.19.2**, with **digline-mcp 0.3.0**. Seven findings from a pass over
the code that was already there — not over what a release added — and three of
them are published as advisories.

**A patch, checked against the rule rather than assumed.** `RELEASING.md` moves
the minor only when something a user relies on stops working as it did. These
are refusals of defects: a register that resolves inside the store still works,
a well-formed document still reads, and no schema, public name or CLI option
has moved. Four exception types are added, none removed. `digline-mcp` is the
exception and takes a **minor**, because its `digline>=` floor rose to 0.19.2
and a floor is a thing users rely on — a plugin claiming it is broken for
anyone still on 0.19.1. Install the core first; a floor may not name a release
the index does not serve.

### Security

Seven findings from a pass over digline's **standing** code on 2026-09-23 — not
a delta-pass. Sixteen delta-passes and five advisories had never reached any of
them, because a delta-pass looks at the delta by construction and every one of
these lived in code no release had touched. Three of the seven are published as
advisories; for the other four the line `SECURITY.md` draws is exposure, and it
is stated per entry rather than left to be inferred.

- **`digline register` could create and append to a file outside the store, on
  the write that creates the register** (advisory **GHSA-TBD**). `append_register`
  reached its containment check only inside `if joined:`, where it had been
  called to read the last byte rather than to check anything, and `joined` needs
  the file to already exist; `read_register` returns early on the same
  `exists()`. Both guards hung off a predicate that follows a link, so a
  **dangling** symlink at `.digline/<tenant>/register/<suite>.jsonl` skipped
  both and the `O_CREAT` that follows created the file it named, anywhere the
  running user could write. The skip was exactly once per register, and that
  once is the ordinary first use. `register/` is committed by design, so the
  link travels in a pull request and the victim's action is reviewing it — **no
  contributor code runs.** Affected `>= 0.13.0`: there is no earlier version
  with the feature, and every version that has had it is affected.

- **`digline view` served the store, and promoted baselines, to any page that
  asked from a name it controlled** (advisory **GHSA-TBD**). The origin check
  compared the request's `Origin` header against its own `Host` header — two
  values describing one request — so it established that a request was
  same-origin with itself, which every request is. A page served from a
  hostname its author controls that resolves to the loopback address is
  therefore same-origin with the server: one request read the whole unredacted
  store or moved the baseline. `Host` is now checked against the address the
  server actually bound to, on every route and not only the one that writes.
  Affected from **0.1.0**: the comparison is in the first commit of the project
  and was never different.

- **`digline migrate` wrote through a symlink committed in the store**
  (advisory **GHSA-TBD**). Neither collector was containment-checked:
  `run_paths()` returned a glob where its sibling `scan_runs` guards the
  identical one, and the baseline path was appended behind nothing but an
  `exists()`. `migrate_file` ends in `write_text`, which follows a link. The
  route a pull request carries is `baselines/<suite>.json`, which is committed;
  a link under `runs/` is the same defect reached with local write access only,
  because `*/runs/` is gitignored. Affected from **0.1.0**.

- **A malformed stored document exited 1, which means "worse".** `EXIT_WORSE`
  is the contract a CI job reads, and a crash exits 1 too, so a corrupt or
  hostile baseline was indistinguishable from a regression somebody should look
  at. `run_from_dict` now refuses anything that is not an object and re-raises
  any shape error as `DocumentRefusedError`, so the answer is exit 64 and a
  sentence; `migrate_file` does the same and lists the file as refused instead
  of ending the migration. **Not an advisory:** nothing is disclosed and no
  boundary moves — what was wrong was the verdict a reader drew from an exit
  code.

- **`promote` wrote the baseline of the suite the *document* named.** `read_run`
  validated the stored document's tenant and never its suite, and
  `promote_baseline` then wrote to the path that field chose: a run filed under
  `qa` declaring `"suite": "other"` overwrote another suite's committed
  baseline, exit 0, no output. Both readers now refuse a document whose suite
  differs from where it is filed. **Refused and never redirected, and the reason
  is the house rule and nothing else: digline does not repair documents.** (An
  argument that a redirect is unsafe because `read_baseline` would refuse what
  was just written is circular — before this fix `read_baseline` never looked at
  the suite.) **Not an advisory:** the tenant perimeter held throughout, so this
  misfiles within one tenant and crosses nothing.

- **Text that is never language is neutralised on every surface.**
  `report.visible()`, `core.json_visible()` and `report.escape()` now escape the
  bidi embeddings and overrides (U+202A–U+202E), the interlinear annotation
  characters (U+FFF9–U+FFFB) and the tag block (U+E0000–U+E007F), listed once in
  `core.NEVER_LANGUAGE`.

  The rest of `Cf` is deliberately untouched, and that is the fix rather than a
  caveat: U+200E/U+200F and U+061C set direction in Arabic and Hebrew, ZWNJ and
  ZWJ carry meaning in Indic scripts and hold emoji sequences together, and the
  isolates are what Unicode recommends instead of the overrides. Neutralising
  the category would corrupt a report rendered in a language this project
  exists to serve.

  `SECURITY.md` recorded this as open, on the argument that it *"is not a way
  in ... it changes what a human believes they are looking at"*. **That argument
  is withdrawn, not amended.** It holds for U+202E and never covered the tag
  block, which is invisible to every surface here and is an exact encoding of
  ASCII: the reader it addresses is an agent holding tools, on a surface
  `core/text.py` already declared untrusted. Measured: an invisible
  49-character instruction in a `case_id` survived `redact()` and reached all
  five surfaces, while a reviewer reading the committed baseline saw
  `capital-of-italy`.

  Not an advisory: no payload crosses a boundary and no file is read. What
  moved was an instruction, into the context of the one reader that acts on
  them.

- **The store's two refusals have types, so a boundary can tell them from a
  bug.** `_check_name` raised a bare `ValueError` and `read_run` a bare
  `FileNotFoundError`. `digline-mcp` translates the exceptions digline raises
  deliberately and lets everything else travel as a crash, so with no type to
  list, the two refusals an agent meets most often — an unsafe run key, and a
  run file that links out of the store — arrived as `Error executing tool
  get_run` with the reason on stderr where no client reads it. They are now
  `PathRefusedError` and `RunNotFoundError`, each subclassing what it already
  raised, so every existing handler is unchanged.

  Found by the standing-code security pass of 2026-09-23. Not an advisory:
  nothing was disclosed and no boundary moved — the refusal held, only its
  reason was lost.

  **And the half that is about the test.** The test guarding that path asserted
  `"exfiltrated" not in message`, which is true of the refusal and equally true
  of the crash string, a typo'd tool name and the empty string. It was green
  while the reason was being lost, so it could not fail for the reason it
  names. It now requires the sentence digline wrote.

## 0.19.1 — 2026-09-23

digline **0.19.1**, and on PyPI the core alone. An HTTP target can now report
what the agent called and what it spent, so an application in any language can
be measured the way a Python one is. And digline installs into Claude Code as a
plugin that ships the judgement layer: the `operating-digline` skill, and a
server that measures, reads and explains and cannot promote a baseline.

**A patch, checked against the rule rather than assumed.** `RELEASING.md` moves
the minor only when something a user relies on stops working as it did. Since
0.19.0 no schema, public name or CLI option has moved. Three optional
parameters and a plugin that did not exist before break nothing for anybody
already on 0.19.0, the same as 0.10.1, 0.12.1 and 0.13.3.

```sh
uv add --upgrade digline
```

### Added — an HTTP target can report its trajectory and its counts

`HttpTarget` takes `tools_path`, `tool_calls_path` and `usage_path`. Until now it
could read the answer and nothing else, so on a non-Python application
`tools_called` and `tool_called_with` **loaded from a TOML suite and then errored
on every case** — a check that cannot be answered rather than one that refuses,
which is the worse of the two. `Response.usage` was always `None`, so a run
against an application recorded no counts and no token totals.

All three reach a data suite with no change to the loader: the `[target]` table
is splatted and its allow-list is derived from the constructor's signature. A
typo is refused at load, by name.

**Declare `tool_calls_path` alone and the names are derived from it**, so the two
readings of one answer cannot disagree. Declare both and they must agree in the
same order, or the answer is refused rather than one reading chosen.

**The vocabularies are closed at this boundary**, not downstream: `status` is
mandatory on every call — `success`, `error` or `not_reported` — with no default,
because a tool that ran and failed must not be able to report as one that worked
by saying nothing. `usage_path` reads the counts by `Usage`'s own field names and
refuses any other key, and refuses a boolean or a fractional count, which keeps
F-1 of the 0.17.0 delta-pass unreachable: `Usage` accepts both, and an
application's JSON would have been the first path able to deliver one.

### Unchanged — and stated, because a reader will assume otherwise

**`resolved_model` stays closed over HTTP** (ADR 0005 §9, amended). And the
configuration an application reports is still not reviewed the way a suite is:
`model` travels in clear from it today. [ADR 0030](docs/adr/0030-the-configuration-an-application-reports.md)
rules what to do about that and **is accepted, not implemented** — these three
paths do not close it.

### Added — a Claude Code plugin, pinned to the release it describes

`claude plugin marketplace add digline/digline`, then `claude plugin install
digline@digline --scope project`, with `digline-mcp` in the project's `.venv`:
two lines plus one dependency. The dependency stays yours, because the server
imports your suite and its providers.

What it ships first is the judgement layer. The `operating-digline` skill had
reached nobody outside this repository, and now it loads in the repository that
uses digline. Beside it: the MCP server, which measures, reads and explains and
cannot promote a baseline, because approval is a person's commit; and a hook
that **asks** before `digline promote` and `digline register`, since both
commit a person's judgement. The hook is a preference, not a wall: the wall is
the reviewed diff under `.digline/<tenant>/`. It reads a command from its first
word, so a `grep` for `digline register` is a grep, and it is silent in a
project without `.digline/` at its root — which matters because `claude plugin
install` without `--scope` installs at user scope, in every repository.

The plugin's version is digline's, and the marketplace installs from the
release tag rather than from `main`. Both are gated in `test_versions.py`,
beside the other numbers written by hand. The launcher starts the server from
the project's `.venv` and from nowhere else, because `uv run` wrote a
`uv.lock` into a repository that lacked the dependency, and an activated
environment put another project's server in its place.

## pytest-digline 0.2.0 — 2026-09-23

Published by digline's `v0.19.0` tag, with `digline-mcp 0.2.0` and the core.

### Changed — the floor moves to `digline>=0.19.0`, and here is why

Not "compatibility". The plugin **imports `digline.host.read_pinned`**, which
arrived in digline 0.19.0 (ADR 0029). A user with an older core would install
this plugin and get an `ImportError` on their first run, which is the exact trap
`tests/test_plugin_floors.py` exists to catch, and it caught it.

It imports it because `execute()` refuses a suite that declares `pinned` while
being handed no resolved pin set. That refusal is deliberate — a run that
recorded no pin would compare green whatever the watched file did — so a front
end that did not read the pins would refuse every pinning suite instead of
silently mis-recording one. **A pinned suite therefore works under `pytest`
exactly as it does under the CLI**, which is the point: a control that works on
one interface is a promise that breaks where somebody tries it, and running
digline inside an existing pytest suite is the most natural way to use it.

**The floor is stated with its reason so that it can be lowered by somebody who
reads it.** If `read_pinned` is ever the only 0.19.0 name here, and a caller needs
an older core, the honest move is to drop the feature from this front end — not
to reach the name dynamically. `tests/test_plugin_floors.py`'s docstring argues
that at length.

## digline-mcp 0.3.0 — 2026-09-24

Published by digline's `v0.19.2` tag, with the core.

A **minor** for one reason: the `digline>=` floor rises to **0.19.2**. The
server now translates four refusals the store and the reader raise — two from
0.19.2's security pass (`SuiteMismatchError`, `DocumentRefusedError`) beside the
two 0.19.2 gave the store — and those names do not exist in an older core, so
an older core would give this package an `ImportError` rather than a refusal.
Nothing else about the surface moves: the same eight tools, the same
read-only hints, and still no way to promote a baseline.

What changes for an agent driving it is what it is told when something is
refused. A run key that is not a safe name, a run that links out of the store,
a run that is simply absent, a stored document that is not a run, and one that
names a suite other than the one it is filed under each now arrive as the
sentence digline wrote. Before, each arrived as `Error executing tool get_run`
with the reason on stderr, where no client reads it — and an agent told only
that something failed retries, which is the one response that cannot help.

## digline-mcp 0.2.0 — 2026-09-23

Published by digline's `v0.19.0` tag, with `pytest-digline 0.2.0` and the core.

### Changed — the floor moves to `digline>=0.19.0`, and here is why

The same reason, and it is worth stating twice rather than cross-referencing:
this server **imports `digline.host.read_pinned`**, which arrived in digline
0.19.0 (ADR 0029). A user with an older core would get an `ImportError`, so the
floor names the version that carries the name.

`digline_run` reads the pins beside the artifacts and hands both to `measure()`.
Without that, `execute()`'s invariant would refuse every suite declaring `pinned`
over this surface — correctly, and uselessly. With it, a comparison over MCP
returns `pinned_drifted` and `pinned_unchecked` on the same headline the CLI
prints, which is what `digline.wire` is for.

## 0.19.0 — 2026-09-23

digline **0.19.0**, and the core alone. A suite can now declare that a file
**must not change**, and a run whose declared file drifted **exits 2** instead
of passing quietly.

**A tool description is not documentation.** It is text in the model's context
that decides when the model calls, with what, and instead of what — and a third
party can rewrite it under you without the tool's *name* changing, which is the
part a pinned version does not pin. EvalSeal measured 51 tool descriptions
rewritten under unchanged names across 10 published MCP servers. digline could
already record the dump and show the diff; what it could not do was fail.

```sh
uv add --upgrade digline
digline migrate --suite suite.py
```

### Added — the artifact that must not drift

- **`Suite.pinned` names the paths that must not drift**, beside the
  `artifacts` they are drawn from. `suite.toml` takes it too. A pinned path that
  names nothing the run recorded is **refused when the suite loads**, the way a
  declared artifact that is not a file already is — otherwise a typo would be a
  control that never runs and never says so.
- **Exit 2, not 1, and the distinction is not cosmetic.** A drifted artifact is
  **not a regression**: no score moved, the input did. Reporting it as one would
  make the report say something untrue in order to produce a tidier number, and
  a reader who went looking for the check that got worse would find none. So
  `pinned_drifted` is its own fact beside `worse`, exactly as a moved canary is,
  and `2` — which already means *the numbers beside this are not what they look
  like* — is what a pipeline sees.
- **A comparison that cannot answer says so, and does not pass.** This is the
  third state, and it is not a detail: redaction takes the digest with the text,
  so a withheld comparison has nothing to compare and **cannot** tell you
  whether a pinned file moved. That is not *it did not move*. `pinned_unchecked`
  counts those paths, in the headline sentence, in the report and in `--json`.
  **Silence there would be the worst outcome available** — a control that
  reports nothing when it could not run produces the same green as one that ran.
  The party holding both runs *can* answer, and `withhold_artifacts()` is how
  they answer it for the party holding neither.
- **Only `changed` fires.** A pinned path the reference never had is `new`, not
  drift — absent is not a change, which is the rule every outcome in
  `digline.core` is read by, and the one that stops a pin going red on the day
  you declare it.
- **It stays out of `config_hash`.** Declaring a pin unpromotes nothing.

### Schema 16 — one command, and nothing else

`SCHEMA_VERSION` moves to 16 for one field, `Run.pinned`: which declared files
the suite said must not change, recorded in the document the exit code is about,
so two archived runs answer the same way tomorrow as today.

**A schema bump reads as expensive, and this one costs one command.** The
migration step **writes nothing** — a run from before this release pinned
nothing, and an absent key already says exactly that. `digline migrate` rewrites
the `schema_version` line and touches nothing else. **Your baselines stay
promotable**: no re-promotion, no re-run, no configuration moved.

`OUTPUT_VERSION` does not move. `pinned_drifted` and `pinned_unchecked` are
added keys on the `--json` headline, which the contract's own rule has always
allowed.

### Unchanged on purpose

- **A prompt still does not gate, and must not.** For a prompt, changing the
  file *is* the experiment; gating on it would fail the run every time the work
  being measured was done. The difference between the two cases is something the
  author declares, which is why this is a declaration and not a default.
- **`digline diff` still never exits non-zero.** A verdict exists only against
  an approved reference, and neither side of a diff was approved by anybody. A
  drifted pin marks the row there and stops.
- **A pin is removable.** Deleting the line disarms the check, with nothing but
  code review in front of it — the price of keeping it out of `config_hash`,
  stated in ADR 0029 §9 rather than discovered.

The reasoning is [ADR 0029](docs/adr/0029-the-artifact-that-must-not-drift.md);
[`docs/tools.md`](docs/tools.md) is the guide, and it now describes this instead
of promising it. The gap was found while reading EvalSeal's work.

### Stopped twice by its own ritual

Recorded because a release that ships smoothly teaches nothing.

The delta-pass found the feature **inert**: `read_pinned` had no caller, so
`Run.pinned` was empty in every run digline wrote and no comparison could exit 2
— with **39 green tests** behind it, each constructing the record directly. Then
the floor gate found **two plugins** importing a 0.19.0 name while declaring
older floors, which would have broken for anyone resolving against PyPI.

**Neither was reachable by a test.** The first was a wire that was never
connected; the second a promise about versions not present. Both are checks now
rather than memories: `execute()` refuses a suite that pins while being handed no
pin set, and the floor table is what caught the second.

## digline-mcp 0.1.4 — 2026-09-22

`digline-mcp` alone, on its own version line. digline stays at **0.18.0**: the
defect is at this package's door and nothing in the core moves, so nothing in
the core earns a version.

```sh
uv add --upgrade digline-mcp
```

### Security — a refusal reached an MCP client with its control bytes intact

Found by the release delta-pass over 0.18.0, before the announcements. **A
`Security` entry and no advisory**, under the second rule in
`SECURITY.md`: our own process caught it, and the exposure is
the turnaround between a tag and its delta-pass. It is written here in full
rather than called a hardening.

`digline_mcp.errors.translated()` re-raised every deliberate refusal as
`ToolError(str(exc))` — *message intact*, which is what its own docstring
promised. A refusal's text is not all digline's own words: it interpolates
tenants, suite names, provider ids, and **since 0.18.0 the names of the rules
that moved**, which arrive inside a stored run document somebody else may have
written. So DEL and the C1 block — and U+009B *is* CSI, which opens on a
terminal what ESC `[` opens — reached the client raw. Both doors out of that
module, `translated()` and `refuse()`, now pass their message through
`json_visible`. C0 is not included and does not need to be: the SDK serialises
this message as JSON and a JSON encoder escapes C0, which is the division of
labour `json_visible` was written to.

**What makes it worth recording is not the string.** 0.15.1 moved this exact
rule out of `digline.cli` and into `digline.wire` *because* the CLI's approach
— escaping the finished JSON text — could not cover MCP, which hands
dictionaries to an SDK that serialises them itself. That fix was right and it
holds: every rendered document still goes through `wire`, and the twelve
reading sinks this release's pass walked are all clean. But an exception
message is **not a rendered document**, and it never entered `wire`. 0.18.0
then wrote free text into one for the first time.

So the defect is not that somebody forgot to escape. **It is that a new path to
the client was opened beside the one that was fixed** — the fifth time this
family has bitten, and the second at a door built after the rule was written.
The regression test is parametrized over the whole `TRANSLATED` surface rather
than over the message that was found to leak, because pinning
`DifferentSuitesError` would test the instance and leave the door: the next
refusal to interpolate somebody else's string will not come back to ask.
Whether that door can be made impossible to open — a type that carries the
guarantee, a chokepoint, a test that walks the error surface by construction —
is a question of its own and is not answered here.

## 0.18.0 — 2026-09-22

digline **0.18.0**, and the core alone. **No schema change** — it writes
schema 15 exactly as 0.17.0 and 0.17.1 did, so no `digline migrate`, no
re-promotion, and every baseline ever written is read by it — and **no
`OUTPUT_VERSION` bump**: three keys are added to `--json` documents, which the
contract's own rule has always allowed.

A minor rather than a patch because the first of the three is a feature, and
what the three have in common is the one thing this release is about: **a
reading that could not say which of several things it meant.** The comparison
said the rules changed without saying which way; the spread printed a range and
left the reader to guess whether being outside it meant anything; and a silent
spread printed a sentence about the suite whatever had actually silenced it.

### Added — the rules that moved are named, and so is the direction

- **A comparison whose suite changed now says which rule moved and which way.**
  Until now `config_hash` moving printed one boolean and one sentence — *the
  suite changed since the reference, so these numbers compare different rules* —
  so somebody who lowered a threshold from 0.6 to 0.5 and re-promoted produced a
  report indistinguishable from somebody who added a test case. The comparison
  carries `suite_deltas`: one row per moved value, with the rule named, both
  numbers, and **`loosened` or `tightened`** beside it.
- **The quietest edit is the one this was written for.** `compare()` judges
  movement against the *current run's* tolerance, so a raised tolerance never
  produces a flip — it turns a `regressed` into an `unchanged`. The one place a
  moved bar was named before this fired only on a flip, and so could not see it.
- **`samples` moves without a verb, deliberately.** More samples is a
  better-founded score *and* a wider measured interval that the noise floor then
  forgives more movement inside. Both are true, neither dominates, so the row
  prints both counts and stops (ADR 0028 §4).
- **Nothing was recorded to make this possible, and no schema moved.** Every
  verdict has always carried `assertion_id`, `threshold` and `tolerance` as
  mandatory fields, and the sample count rides the metadata — so the rows are
  *derived* from the two documents, and a baseline promoted a year ago is read
  as well as one promoted today. There is no migration and nothing to re-promote.
- **It reports and it never gates.** Where the bar sits is a person's
  declaration; the gate already exists and it is `promote_baseline` refusing
  across a changed `config_hash`. No exit code moves, no check is reclassified,
  and a run that was promotable still is.
- **A redacted run gets the complete table.** Nothing a rule is made of can be
  withheld, so the party holding the signal and none of the payload — the one
  least able to see a bar quietly lowered — sees all of it.
- **`digline diff` now says what differs** instead of only that something does.
  The refusal stands; it names up to five rules and counts the rest.
- **One thing it cannot say, and says so:** `min_agreement` is in `config_hash`
  and in no document. Where either side sampled and the fingerprint moved, one
  `unknown` row states that; it is never derived from the measured `agreement`.
- Reading: a `rules` line in the terminal with the loosened rules first, a
  *What the rules were* section in the report in both locales, a `"rule"` kind
  in `explain`, and `suite_deltas` under `compare --json full` and over MCP —
  added keys under `OUTPUT_VERSION = 2`'s rule, not a bump.

### Changed — the run-to-run spread says why it withholds its clause

`digline log`'s spread section has printed a range and declined to say whether
the latest score is inside it, on the grounds that the least N making *inside*
mean anything had not been measured yet. **It has now been measured, and there
is no such N.** A min–max range over a growing sample is monotone: it cannot
converge, so a score outside it names a value not seen before rather than a
change. On scout's first kept operator history — twelve runs over four days at
one `config_hash`, eight comparable — *outside* fired on 4 of 12 readings at
N≥6, and every firing above the high became the next reading's high.

So the clause is withheld **because the range describes and cannot gate**, and
the reading says that instead of promising a number:

> Whether the latest score is inside this spread is not stated: a range
> describes the runs it read and cannot carry that clause. A value under the
> low or over the high widens the range, so falling outside it names a score
> not seen before, not a change.

The range itself does not move — it is honest about what was seen, which is
what the reading is for. If a reading is ever to say *inside*, it needs a
statistic that converges, and that is its own decision. ADR 0024 §7.4 carries
the ruling, the measurement and three findings that would otherwise be
re-derived: a floor could not be one number across aggregates whose
denominators differ by 7×, the effective N grows at 67% of the cycle count, and
the between-run range is *narrower* than the latest run's own within-run
interval on three of four aggregates.

### Fixed — a reading that ended in a verbless fragment

The spread's exclusion clause carried its verb on a single one of its reasons,
so it read as a sentence only when *re-judged* happened to come first. On the store
the measurement was made from it did not: every exclusion there is *not fully
judged*, and the reading ended **"; 3 as not fully judged."** The verb is the
clause's now, once, with each reason a bare counted phrase after it — in both
locales, where the Italian fragment was the worse of the two.

    — the latest not among them; excluded: 3 not fully judged.

No schema change, no `OUTPUT_VERSION` bump, and no number in any reading moves:
the range, the count and the exclusion tallies are what they were.

### Fixed — four reasons the spread is empty, and one sentence for all four

`log.spread` comes out empty for four different reasons, and **only one of them
is a fact about the suite** — which was the sentence printed for all four. So a
fresh clone was told *"This suite declares no run-level check."*, and so was a
run whose every check had flipped against the reference. A checkable sentence
standing in for one that cannot be checked.

ADR 0024 §7.5 had ruled the spread *silent* on a flip without saying what
silence prints, and the section's heading is unconditional, so silence printed
whatever sentence was already there. Ruled, dated: **silent on a flip means do
not report a range, not print nothing** — naming the flip is not printing an
interval. Four sentences for four facts now:

- no run read in this store and window, *and* that whether the suite declares a
  run-level check is not something a reading of runs can say — which is the
  sentence every first reading on a new machine now gets:

  > No run was read in this store, in this window, so there is nothing to read
  > across runs. Whether this suite declares a run-level check is not something
  > this reading can say: it reads the runs, and there are none.

- the suite declares no run-level check — the one case that is about the suite,
  and its sentence is unchanged;
- how many checks changed status against the reference, and that a changed
  status carries no interval;
- how many checks recorded no score.

Counted by cause and never as a total, so a run with one flipped check and one
scoreless check prints both: picking one would be the substitution this
removes. `--json` gains `spread_absence` beside `spread`, an added key with
`OUTPUT_VERSION` unchanged — reading `[]` could not tell the four apart either.

### Documentation — the spread has a page at last

[`docs/log.md`](docs/log.md) documented every section of `digline log` except
the spread, which ADR 0024's *Turns into surface* line had promised: a record
promising something nobody could find. It now has the transcript, the exclusion
table by reason, the latest-run asymmetry, the two intervals and why the
sentence stops where it does.

Two claims on that page went stale when the spread shipped and are corrected
with it. `--json` said **"No score crosses"** — the spread's range makes that
false, so it now says no score crosses *beside an identity*, names `spread` in
the key list, and states the one direction the amendment permits. *It is never
a gate* now says the spread adds no exit path and no field to `compare`,
because a gitignored per-machine history must never decide whether a run
passed.

## 0.17.1 — 2026-09-21

digline **0.17.1**, the delta-pass patch over 0.17.0, and the core alone: every
plugin version in the workspace is already served by the index, so this tag
publishes nothing beside it. **No schema change** — it writes schema 15 exactly
as 0.17.0 did, so no `digline migrate` and no re-promotion — and no
`OUTPUT_VERSION` bump: one key is added to `compare --json` and one tally kind
to `explain --json`, which the contract's own rule has always allowed.

Five fixes, and what they have in common is the thing being fixed: **a sentence
a reader could act on that was not true.** Four came out of a second
adversarial pass over 0.17.0's own new surface, read back against the code
rather than against the report it produces; the fifth is the row a listing
printed for a replay. A run that reconciles, against a reference that
reconciles, reads exactly as it did.

### Fixed — four readings that said something false

The second delta-pass over 0.17.0, an internal adversarial review, read the
release's own new surface back against the code rather than against the report
it produces. Four findings — one of them in two parts — and each is a sentence
a reader could act on that was not true. No schema change, no `OUTPUT_VERSION` bump, and a run
that reconciles against a reference that reconciles reads exactly as it did.

- **A reference that does not reconcile is now named every time it is used, not
  only when it was promoted.** This is the one with the sharpest symptom: the
  report opened with *"Every case could be judged."* while its own reading said
  *"c2 · agrees could not be judged."* three lines below, and the comparison
  exited 0. ADR 0027 §3 refuses to promote a run that does not reconcile
  because *"a reference nobody can say that of is no reference"* — and that
  refusal fires once, on the machine that promoted. Every reader afterwards
  asked the run and none of them asked the baseline, so a reference admitting
  it did not know what it measured was compared against in silence. It matters
  more than the run's own case because `.digline/<tenant>/baselines/` is
  **versioned in git**: that document's surface is a pull request, and
  `config_hash` cannot catch it, because it hashes the suite and not the
  results. `compare()` now reads the baseline's gaps into
  `Comparison.reference_unreconciled`, the headline and `explain` both name
  them, and `compare --json` and `explain --json` carry the count as an added
  key. It moves **no exit code**: the run being compared may reconcile
  perfectly, and failing it for the state of a document promoted weeks ago
  would fail the wrong run — what the clause withdraws is the standing of the
  comparison, which is `config_changed`'s shape.

- **A token count that is not a number is refused where the number is made.**
  0.17.0 shipped exactly this guard for `CallTotals.spent_usd` and wrote the
  reason into the code — *"the honest place to stop a number that is not a
  number is where it is made"* — while `Usage` kept the `< 0` pattern that same
  comment calls *"written for the wrong half of the problem"*. `NaN` is not
  negative and no ordering comparison against it is true, so it passed both
  checks on all five counts, including the `thinking_tokens` the release had
  just added; `inf` was refused only by accident, for being more thinking than
  output. A `NaN` reaching a run file is worse than it was for the bill: the
  document is written carrying a bare `NaN`, which no strict parser reads, and
  `usage_from_dict` then refuses it through `int()` — so the run was written,
  listed, and unreadable for good, by its own reader. `Usage.__post_init__` now
  refuses a non-finite count by name. What a third-party target may hand us
  otherwise — a `bool`, a whole `float` — is unchanged and remains a separate
  question about the type's contract.

- **The fold raises instead of asserting.** `Usage.__add__` guarded its
  invariant with an `assert`, on the argument that only digline's own
  arithmetic could fire it. Both halves of that were wrong: `NaN` reached it
  from a reply, so the one value that did fire it told the user *"this fold is
  wrong, not the replies it added"*; and `python -O` strips an assert, so the
  release that could least afford the check had none at all and the `NaN` total
  went through in silence. It is a `ValueError` now, with a message that states
  the arithmetic and blames neither side.

- **An aggregate's denominator is checked against its own parts and against the
  run.** `compare()` decides whether two run-level figures are comparable by
  reading `considered` out of the verdict's metadata, and checked only its
  *type*. `as_metadata()` writes the four matrix cells beside it and
  `considered` is exactly their sum, so the document carries the total and the
  addition that produced it, and nothing compared the two. Three sentences came
  out of that: *"-5 of 2 cases counted"*, *"43 of 36 cases counted; -7 could
  not be judged."*, and — the one worth catching — *"All 20 cases counted."*
  over a run holding five cases nobody judged. A negative count is refused like
  a boolean, a total its own cells contradict is not read, and a figure is
  refused where the run disproves it: a whole-run aggregate saw every case the
  run holds, and no aggregate can have counted a suspended one. A **grouped**
  aggregate is exempt from the first of those, deliberately — it is computed
  over its own group's cases, so its count is meant to be smaller, and a stored
  run records no group per case. The report's per-delta sentence now reads the
  checked figure off the row rather than recomputing it, because a delta holds
  no run to check against and was the one of the three surfaces that could not.

  **This is a correctness fix and not an advisory.** The route to a
  mis-declared `considered` is a run-level assertion, which is suite code, and
  `SECURITY.md` already declares that writing `suite.py` is the capability to
  execute code. GHSA-8c38-f965-cgww's `I:L` bound is untouched and still
  correct: it rests on the excluded case being an **error**, which is what an
  endpoint can cause without touching the repository.

- **The unreconciled clause has a ceiling.** It named every gap, and that
  clause leads `Headline.sentence`, which `compare_json` copies whole and the
  MCP `compare` tool returns — so a run that gapped a whole suite put 20 131
  characters of names into the document a customer reads and into a model's
  context. ADR 0027 §3's argument for the names is right for the one to three
  gaps a dispatch defect produces and does not survive the thousand-gap run, so
  five are named and the count carries the rest, which is `calibration_fact`'s
  precedent one function above it. **A run with five gaps or fewer reads byte
  for byte what it did.**

### Documentation

- **Two docstrings claimed a barrier and a wire route the code does not have.**
  `UNRECONCILED` said the marker *"travels under `travels()` like every other
  measurement"*; `travels()` does admit a boolean, but the run projection never
  consults it — `_verdict_document` filters verdict metadata to the suite's
  `Disclosure` alone, which `wire/run.py` states in as many words. So a run read
  through MCP carries `status: "error"` and nothing telling a gap from a judge
  that failed, unless the suite discloses the key by name; the readings do carry
  the count. And `unreconciled()` said the marker *"counts only on an errored
  verdict"* as though that were a barrier — `Verdict` **forces** an errored
  status on any verdict with no score, so it is the shape any assertion that
  declines to score produces. The narrowing that does work is `is True`.
  Recorded rather than changed: widening a projection is a boundary decision,
  and not one a docstring gets to make by describing it.
- **ADR 0027's *Consequences* now says what §4 leaves open.** The check runs in
  the driver and nowhere else, by that section's own decision, so a stored run
  is never reconciled again and every reader reads back a marker the document
  carries about itself. Deleting the errored verdict that carries it removes
  the gap, the exit code and the promotion refusal together. That is the price
  of the decision rather than a defect in it, and the alternative stays
  rejected — what is written down is that **exit 2 is not tamper-evidence**, so
  that nobody reads a red exit as proof the file was not edited.

### Declared — `digline-bedrock` reports no thinking split

No version bump, and none is coming for this one: a declared absence does not
earn its own release. The sentence rides `digline-bedrock`'s next real one, and
is written now so the absence is on the record from the release that created
the field rather than from whenever the plugin next moves.

- **Bedrock Converse reports no thinking-token split, so `Usage.thinking_tokens`
  is `None` from this plugin — never `0`.** The model may well have thought: a
  reasoning budget goes in through `additionalModelRequestFields`, and the reply
  carries `reasoningContent` blocks. What the `usage` object does not carry is
  the count. 0.17.0's three states exist for exactly this — `None` is *not
  reported*, `0` is a provider that reported a split and a reply that did no
  thinking — and writing `0` here would report the absence of a field as the
  absence of thinking, on the provider where the thinking is most likely to have
  happened and least likely to be visible.
- Same shape as the model id: Converse's reply names no model, and the plugin
  leaves `resolved_model` unset rather than echoing the request back
  (ADR 0005 §9). A provider that says nothing is recorded as having said
  nothing.

### Changed — the verb on a reported identity, not the reading

ADR 0020 is **amended, not revised**: §3's doctrine stands. An id that differs
from the one we sent is a sighting, because no passthrough returns a string
nobody supplied, and distinguishing it from an echo is right. The verb was
wrong all the same.

- **`digline log` said a model "answered as" a snapshot.** Nothing attests
  that: a provider may report any string, and a proxy in front of it may
  rewrite the one it did. The same field sits in `OBSERVED_FIELDS` — what a
  provider **reported** rather than what the target **sent** — and the
  configuration surface has said *reported* about it since ADR 0005 §9, so one
  field was carrying two verbs in two renderings. `log.sighting.answered`,
  `log.roll` and `log.spread.excluded.identity` now say *reported*, in both
  locales.
- **`docs/log.md` told a reader "Two verified sightings out of thirteen".**
  Neither was verified. That line is now *reported*, and the paragraph under it
  says why the word was reached for: digline has a vocabulary for *we cannot
  identify what answered* — the seven absences — and **none at all for "we were
  told and could not check"**. Everything that was not an absence fell into one
  bucket and the bucket took the strongest available word. The amendment does
  not fill that gap; it stops the strongest word standing in for it. The same
  correction lands in ADR 0020's four prose locations.
- **The wire key stays `answered`** (`wire/log.py`). It is older than the
  distinction, and renaming it is an `OUTPUT_VERSION` bump for a word that
  would break every consumer parsing it to tell them what they already knew.
  The note saying so now sits beside the field, not only in the ADR, because
  that is where somebody would go to "fix" it.
- **`log.*` joins the `EXECUTION` gate.** It was held out when that gate landed
  because the decision had not been taken; the comment pointing at the missing
  decision is replaced by the decision. Headings are now checked **whole-string**
  against `EXECUTION_TITLE` rather than as substrings, because as a clause the
  identical words are how digline declines to claim: ADR 0020 §3 row 7 reads
  "so what answered is not identified", and a substring rule would have forced
  the most careful sentence in the product to be rewritten to satisfy a gate.

### Changed — four sentences the record could not support

- **`explain` said the system under test "answered with" a configuration
  field**, where that field is, outside `OBSERVED_FIELDS`, what the run
  *sent*. ADR 0020 §3 row 7 is the rule it broke: a sent id says what was
  asked for, not what answered. A sent parameter now reads *configured*, and
  the fields a provider reported read *reported* — the split `render.py`
  already made off the same set. `explain.setting.judge.missing` carried the
  same verb and was found by the new gate rather than by reading.
- **`config.title` was "What answered"** over a table of sent parameters, and
  `config.judge.title` "What judged". Both now name the set-up.
- **The Italian `log.rolls.none` said *no model change recorded*** where the
  English says "No roll recorded." — the reading `docs/log.md` explicitly
  refuses, because the sentence means *there was almost nothing to compare*
  and not *the provider held still*. Nothing compared the two locales, so the
  stronger one stood for as long as it was written.
- **The gate is `EXECUTION` in `tests/_vocabulary.py`**, over `explain.*`,
  `fact.*` and `config.*` in both locales. The last two were behind no prefix
  gate at all, which is where `config.title` sat. It is anchored to the
  placeholder because the object is what decides: *answered under a different
  configuration* is supportable and stays, *answered with `{name}`* is the
  claim itself. Both new gates ship with a control that must fail.
- **`log.*` is deliberately outside that gate.** "Answered as" there rests on
  ADR 0020's ruling that a *differing* reported id is a sighting — doctrine to
  amend, not prose to fix.
- **SECURITY.md said four published advisories and listed four.**
  [GHSA-8c38-f965-cgww][adv-5] — the denominator article, closed in 0.15.3 —
  is the fifth, and it was published. The page is the public security record,
  so the omission was that record saying something untrue about our own
  history.
- **`examples/rag` claimed a frozen retrieval it did not have.** The docstring
  and the README said the passages were frozen into the cases; `suite.py`
  called the retriever at every import. An edit to `corpus.py` moved every
  score with nothing in the run saying so — cases are outside `config_hash` by
  design, the example declared no artifact, and `case.context` never reaches
  the store. The passages are now written into `cases.json` and read from it,
  with `freeze.py` to re-retrieve as a deliberate act that leaves a diff.
- **The example `report.html` files still read the old headings, and that is
  not an oversight.** A committed example report records the run that produced
  it, at a commit somebody can reach; it is re-rendered with a release, under
  the full ritual, and never amended in place to match a string change. Four
  of them carry `What answered` until the next tag, where regenerating them is
  a named step.

[adv-5]: https://github.com/digline/digline/security/advisories/GHSA-8c38-f965-cgww

### Changed — a listing that showed a replay as a measurement

The same defect as the four above, on the surface a reader meets first. The
others were a verb over a field; this one is a whole row.

- **`digline list` did not mark a rejudged run as a replay.** `rejudge` writes
  a run like any other — its own key, a date, an environment, a commit, a case
  count — and the listing printed it like any other. Nothing in the row said
  the answers under it were replayed from a stored run rather than measured;
  only `rejudged_from`, inside the document, said so. A replay is also the
  *newest* thing in the store the moment it is written, so it sorts to the top
  of the listing and is what `--run latest` resolves to: the row most likely to
  be read and reused was the one making the strongest unsupported claim.
  Rejudged runs now carry `~`, with `~ = rejudged: another run's recorded
  answers judged again, not a measurement` under the table.
- **It shares the baseline's column rather than adding one.** The two markers
  cannot collide — `promote` refuses a run that declares `rejudged_from`
  (`ReplayedRunError`), so nothing listed is both the baseline and a replay —
  and a sixth field on a row that already carries five would push the line past
  a terminal, which is how a marker stops being read. That the baseline was
  given a marker and not a column is the precedent, and it is the right one.
- **The legend is built, not printed inline**, so the blank line above it
  appears once whichever markers a listing actually used. A store with no
  replay in it says nothing about replays, the same way it already said nothing
  about a baseline it did not have.
- **Found from outside.** A `rejudge --judge-samples` on another project's
  suite left a replay at the top of that store's listing, indistinguishable
  from the runs around it, and the reading that caught it was opening the JSON.
  The regression test lists a real run and a replay of it together and fails on
  the row, not on the legend: against 0.17.0 it fails saying *the rejudged run
  is listed as an ordinary run*, which is the defect in one sentence.

## 0.17.0 — 2026-09-20

### Added — the thinking a model charged for

digline **0.17.0** opens schema 15 with one passenger.

- **`Usage.thinking_tokens`**, the output tokens a model spent thinking where
  the provider reports the split. `SCHEMA_VERSION` moves to **15**; run
  `digline migrate` before comparing or promoting. `OUTPUT_VERSION` stays 2.
- **Three states, and `None` is not `0`.** `None` is *not reported* — a
  provider that says nothing, or an SDK too old to carry the field; `0` is a
  provider that reported a split and a reply that did no thinking. A `0`
  written for the first would report the absence of a field as the absence of
  thinking.
- **It is a breakdown, not a new billable quantity**, and that is the **inverse
  of the cache-write case**: both providers report it *inside* the output
  count, so `Pricing.cost` does not read it and nothing is added. Adding it
  would bill every reasoning call twice.
- **A reply claiming more thinking than output is refused by name**, never
  clamped: a clamp hides a provider whose accounting drifted and a plugin
  reading the wrong field into the right one, and both need somebody told.
- **The count is re-tokenised and therefore approximate** — derived after the
  fact rather than counted as the model emitted — so it may not reconcile to
  the digit, and nothing derives anything from it.
- **A total that folds an unreported split is unreported**, not the smaller
  number it could print: a call that said nothing did an unknown amount of
  thinking, not none. An empty line is the one exception — a line that counted
  nothing is *no* measurement rather than an unreported one — and the three
  folds that build a bill each apply that distinction.
- In a run total the field crosses a boundary; on a recorded response it does
  not. The same grain rule as the four counts beside it.

  The reasoning is
  [ADR 0026](docs/adr/0026-the-thinking-a-model-charged-for.md), which also
  records that this field was mistaken for shipped: the 0.16.0 reconnaissance
  proposed it, 0.16.0 shipped `Usage` with four counts, and the gap was found
  by somebody sitting down to write the plugin patch.

### Changed

- **A run now checks that it recorded an answer to every question it asked.**
  Before any aggregate is computed, the driver reads its own dispatch back. A
  suspended case is asked nothing, a calibration case is asked its one check,
  and every other case, canary included, is asked every assertion. The driver
  checks that each declared case has exactly one result and that each result
  holds exactly one verdict per question and none it was not asked. A gap
  becomes an errored verdict that **names the case and the check**. The run
  exits 2 and cannot be promoted, and the headline, `explain` and the report
  open with *"The run does not reconcile with what the suite asked, at 1
  check: c2 · agrees. This is not a regression: what the run measured is not
  known."* A run that reconciles, which is every run the shipped driver
  produced before this, reads exactly as it did. No schema change: the marker
  rides the errored verdict. `compare --json` gains an `unreconciled` count on
  the headline, and `explain --json` gains an `unreconciled` tally kind.
  - **Why it exists.** **nitish-kmr** pointed out, on the Reddit thread about
    the denominator article, what our refusal of errored runs rewards: wrapping
    the exception so that the run finishes, which turns the error into a skip
    inside the user's own code. That is the denominator defect again, and our
    own cure pushes people towards it. Nothing that counts verdicts can see an
    exception the user's code caught; [ADR 0027](docs/adr/0027-the-run-reconciles.md)
    §2 says so and says what can. This closes the losses digline could cause
    itself. It is the eighth defect this week in the same family: **a case that
    vanishes, rather than a number that fails to declare itself.**
  - **Two losses it found, both fixed.** An aggregate found its verdict by
    `score.name` while `Suite` resolves `over` by declared name. A third-party
    assertion that names its `Score` otherwise had its cases counted as
    *suspended* when nobody had suspended them, so a failing verdict named
    that way silently left the count. It is now found by identity. And a
    resumed journal entry with no verdict and no suspension was accepted and
    counted as suspended. It is now refused where the journal is read, before
    the first call, beside the refusal of case ids the suite does not declare.

- **The count of unjudged cases now comes with the number it is out of.** The
  headline that `compare` prints and the report opens with, the reading
  `explain` gives, and the single-run document all used to say *"7 cases could
  not be judged."* Now they say *"43 of 50 cases judged, 7 could not be."* Every
  run-level figure that left cases out also says how many and why, wherever
  that figure is named: *"43 of 50 cases counted; 7 could not be judged."* That
  applies to `compare`'s line for it, the report's "what happened" column and
  `explain`. Every exclusion is named, including the canary, the calibration
  case and the unlabelled case, so the two numbers always add up. The report's
  column of counts (*"43 counted · 0 suspended · 7 not judged"*) is now the same
  sentence, and it used to leave those last three out of the sum. The counts
  were always recorded. They just were not where people read. This is
  presentation only: no new fact, no schema change, and no field added to
  `--json` or MCP. The headline string they already carry is the new sentence. **A run that judged every case reads exactly as before.**
  The zero case keeps its sentence, *"Every case could be judged."*, and no
  figure gets a clause saying it left nothing out.
  Suggested by **nitish-kmr** on the Reddit thread about the denominator
  article.

### Fixed

- **A cost that was neither a number nor an error passed the guard beside it.**
  `CallTotals.spent_usd` was refused when negative, and `inf` and `NaN` are not
  negative — so a bill that is not a bill went through. Since 0.16.0 that figure
  flows into a run-level total, where two journal bill lines at `1e308` summed
  to `inf`, and the run document was then written carrying a bare `Infinity`.
  CPython's `json` reads that as an extension; **no strict parser does**, so the
  file round-tripped locally and was refused by the first conforming reader — a
  parser in another language, a linter, or an MCP client's JSON layer. Refused
  now where the number is made, which covers the sum as well as the literal,
  because `+` builds a new line and revalidates it. Found by the 0.16.0
  delta-pass (B-1).

### CI only

- The two merges after ADR 0026 changed nothing a user installs: `codeql.yml`
  and `scorecard.yml`, and a new `tools/actions.py` with the test that asserts
  every action is pinned to a commit. No file under `src/`, and no format
  version moved.

## digline-anthropic 0.5.3 — 2026-09-20

> Published by the **`v0.17.0`** tag rather than by a named tag of its own.
> `publish.yml` builds the whole workspace and uploads everything the index
> does not have, so a workspace tag releases a plugin whose version has moved.
> That is the combined release the workflow is written for; recorded here
> because the reader would otherwise look for a `digline-anthropic-v0.5.3` tag and find none.

- Reads `output_tokens_details.thinking_tokens` into `Usage.thinking_tokens`.
  An `anthropic` too old to carry the container, and a reply without the
  split, both record **not reported** rather than a zero. The old SDK is not a
  hypothesis: `anthropic` 0.40.0, the oldest this package admits, has a `Usage`
  of two fields and no container at all.
- Needs digline **0.17.0 or later**, which is where the field arrives.

## digline-openai 0.5.2 — 2026-09-20

> Published by the **`v0.17.0`** tag rather than by a named tag of its own.
> `publish.yml` builds the whole workspace and uploads everything the index
> does not have, so a workspace tag releases a plugin whose version has moved.
> That is the combined release the workflow is written for; recorded here
> because the reader would otherwise look for a `digline-openai-v0.5.2` tag and find none.

- Reads `completion_tokens_details.reasoning_tokens` into
  `Usage.thinking_tokens`, the same way.
- **Only that one of the type's five fields.** `audio_tokens`,
  `accepted_prediction_tokens`, `rejected_prediction_tokens` and `text_tokens`
  answer different questions and are left alone — named here so the next reader
  knows they were seen.
- `CACHE_WRITES_ARE_INSIDE_PROMPT_TOKENS` is **unchanged at `None`**. A user on
  a compatible endpoint confirmed `prompt_tokens_details.cache_write_tokens` is
  present in a live reply, and presence was never the open question: whether
  those tokens sit inside `prompt_tokens` still needs the committed three-call
  probe, so cache writes are still reported as 0 and still stated as a known
  undercount.
- Needs digline **0.17.0 or later**.

## digline-bedrock — no release, and this is why

- **Converse reports no reasoning split at all.** Its `TokenUsage` carries
  `inputTokens`, `outputTokens`, `cacheReadInputTokens` and
  `cacheWriteInputTokens`, and nothing else — so this plugin can only ever
  record `thinking_tokens` as **not reported**, which is what it does by
  writing nothing.
- It is **not bumped**, because a no-op is not a release: there would be
  nothing for a user to install. The absence is written down here rather than
  left silent, so the next reader learns it from the changelog instead of
  rediscovering it from the provider's API.

## 0.16.0 — 2026-09-19

**Four things a digline document could not say before this release, in the
order you meet them.** The document can say **what a run consumed and what it
cost** — both lines of it, the target's and the judge's. The judge can say
**when it could not answer**, instead of guessing a number or crashing. The
wire stops letting a model **read means as judgements**. And the instrument's
own **four measurements are complete**: the calibration case, repeatability,
the shape across the suite, and now the spread between runs.

**If judged scores move on this upgrade, it is neither your system nor your
model — it is our instruction to the judge.** `SCORE_SYSTEM` and `CLAIM_SYSTEM`
changed so a judge may decline, and a model told it may decline will sometimes
decline where it used to guess. Nothing records that: the judge's instruction
is in neither `config_hash` nor `judge_config`, so a comparison across this
upgrade reports `judge_config_changed` **false**. Read the movement, and
**re-promote if it is acceptable**.

**What a run consumed, written down.** digline **0.16.0** opens schema 14 with
one passenger: the bill. Until now digline recorded **no token count
anywhere**, for every provider: `ProviderTarget` priced the counts, kept
the money on `Response.cost_usd` and copied the four numbers into
`Response.metadata`, which is never persisted. `JudgeBase.spent_usd` reached no
document at all, so one of the two lines of the bill had never been written
down since the first release.

`SCHEMA_VERSION` moves to **14** and `JOURNAL_VERSION` to **2**. Run
`digline migrate` before comparing or promoting: a document at 13 is refused by
name until it is migrated, and a **journal** at format 1 is refused and left on
disk — start that run again rather than resuming it. The two versions moving in
one release is a coincidence of one train, not a coupling: they are independent
by design (ADR 0017 §2) and the journal stood still through schemas 11, 12 and
13.

### Added

- **`Run.usage`** — two lines of one bill, the **target's** and the **judge's**,
  on every run whether or not it records responses. Each carries `calls`,
  `counted`, the four token counts and `spent_usd`. `counted` below `calls` says
  the total covers only part of the run — a target that reports no counts, or a
  leg somebody resumed by hand without figures — and the CLI prints that
  parenthesis only when it is true.
- **`RecordedResponse.usage`** — the four counts of one call, beside the answer
  it belongs to, under the existing `record_responses`. A bill is a total and a
  discrepancy is found in the detail.
- The totals cross a boundary and the per-call counts do not: a run total is
  the software house's own invoice and names no case, while a per-call count is
  a fact about one of the end company's requests. `redact()` keeps the first and
  drops the second with its response; `--json` and MCP carry the first only.
- **The journal keeps a bill line per case**, written whatever the suite
  records, so a resumed run states the whole run's bill rather than the last
  leg's — and is still byte for byte the document the kill prevented
  (ADR 0017 §10).

### Changed

- **`Usage` moved to `digline.core`** and is re-exported from
  `digline.targets.pricing`. It is the same class object, so
  `from digline.targets.pricing import Usage` is unchanged and **no plugin needs
  a release**.
- `execute()` gained `spent=`, and refuses a non-empty `done` without it: a
  resumed run that could not say what its earlier legs cost would under-bill in
  silence.

### Added — the judge may say it cannot answer

- **A judge can now decline instead of inventing a number.** Asked to score an
  output it cannot score — a refusal, an empty answer, text the rubric does not
  apply to — a model used to have two ways out: guess, or crash. A guess is
  usually a `0`, and a `0` is a **fail**: the system under test marked down for
  the instrument's inability. A judge replies `{"abstain": true, "reason": "…"}`
  instead, and the check is *unjudged* carrying the judge's own sentence.
- **A judge that never abstains behaves exactly as today.** A missing `score`,
  a `"score": null` and an `"abstain": false` all stay broken replies. Declining
  is the thing a judge has to say on purpose: it is unreachable by omission, by
  a malformed value, and without a reason.
- **`Faithfulness` can tell its two zeros apart.** *"The judge found no claims"*
  used to cover both an output that asserts nothing and a judge that could not
  tell what it asserts. A judge that cannot decompose now declines, so the
  remaining zero says what it means: *the judge counted the claims in this
  output and found none*.
- It adds no status (`error` is already *a judgement that could not be given*),
  no field to any stored document, and no schema move.

  **If judged scores move on this upgrade, it is neither your system nor your
  model — it is our instruction to the judge.** `SCORE_SYSTEM` and
  `CLAIM_SYSTEM` changed, and a model told it may decline will sometimes decline
  where it used to guess. Nothing records that: the judge's instruction is in
  neither `config_hash` nor `judge_config`, so a comparison across this upgrade
  reports `judge_config_changed` **false**. Read the movement, and **re-promote
  if it is acceptable**.

  The reasoning is [ADR 0004 §7](docs/adr/0004-every-plugin-is-a-target-and-a-judge.md).

### Added — what `get_run` says about the instrument

- **The MCP run document follows the instrument's own flags.** `get_run` and
  `get_baseline` now mark a judged check (`judged`), a canary (`canary`), a
  calibration case (`calibration` with its band), a replay (`rejudged_from`, the
  key of the run whose answers were re-judged) and scores that are means of
  judgements rather than judgements (`sample_means`, beside `samples`). None of
  them was ever withheld: they were absent, and a caller reading **one run with
  no reference** could not get them anywhere — `compare` and `explain` need a
  baseline, and two of the five were carried by neither surface.
- `sample_means` is the one whose absence made a reader **misread** rather than
  miss: `samples: [0.5, 0.5]` is two judgements or two means of them, and the
  surface built for a model to read was shipping the misreading schema 13 was
  spent to stop.
- **`Run.judge_samples` deliberately does not travel**, and a test asserts its
  absence so this reads as a ruling: the numbers it qualifies live in verdict
  metadata, which crosses only by `Disclosure`, so the bare count would arrive
  with nothing to count against.
- `OUTPUT_VERSION` stays **2**. These are added keys, which this contract has
  admitted nine times; the bump to 2 was for a change *inside values a consumer
  already reads*, which is a different rule.

- **The two front ends had stopped answering the same way, and neither had
  shipped.** Between the change that put `usage` on a run and this one,
  `digline run --json` carried what the run consumed and the same tool over MCP
  did not — one fact, two answers, which is the thing `digline.wire` exists to
  make impossible. Nobody outside saw it because neither change was released,
  and it is recorded here rather than left in a commit message because the
  reason it survived three branches is worth more than the fix: the gate for it
  is this package's own parity test, and the narrowed `pytest tests/` that was
  being run does not collect it.

  The reasoning is [ADR 0011 §5](docs/adr/0011-the-mcp-server.md), amended.

### Added — how much the suite moves between runs

- **`digline log` reads the spread**, the fourth measurement of ADR 0024: for
  each run-level aggregate, the range it took across the **comparable** runs in
  this store and this window. Comparable is checked and never assumed — a run
  is excluded, counted and named where it re-judged, where a case could not be
  judged, where it lost its scale, or where its rules, its counted cases, its
  prompt, the system it asked or the instrument that graded were not the
  latest run's.
- **The latest run is never in its own range.** A spread that contained the
  value it is read against would answer *inside* by construction, which is an
  excuse promoted to a feature.
- **Whether the latest score is inside that spread is not said yet**, and the
  reading says that it is not saying it: a range over two runs is a single
  difference, and the least N that makes *inside* mean anything has to be
  measured on real history first — the same way the shape and calibration
  thresholds are declared to be measured rather than guessed.
- Where the latest run also carries the aggregate's per-sample interval, both
  are printed and **labelled apart**: they are different measurements, and the
  reading never sets one against the other.
- Silent on a flip, no new exit code, nothing in `compare`: `log` exits 0
  whenever it read the store, and this adds no path to any other number.
- `--json` gains `spread` beside `spans` and `rolls`, and the MCP `log` tool
  returns the same value. `OUTPUT_VERSION` stays **2**: an added key.

  The reasoning is [ADR 0024 §7](docs/adr/0024-the-judge-as-an-instrument.md),
  with the one sentence it needed from
  [ADR 0020 §4](docs/adr/0020-the-reading-across-runs.md) written there as a
  dated amendment.

### Added — an autoevals scorer says whether it asks a model

- **`FromAutoevals` was neither judged nor announced, and both halves are
  closed.** It declares `wrapper`, meaning *read my nature through what I
  wrap* — but it wraps an autoevals scorer, not a digline check, so there was
  nothing to read through. A scorer that calls a model was invisible to the
  shape reading, could not calibrate, was never repeated by `--judge-samples`,
  and nothing on your terminal said so.
- **The floor: an adapter that has not declared is named**, beside the
  planned-calls line, in the channel that already names a check declaring no
  `KIND`. `wrapper` is a declaration that *points*, and a pointer into a scorer
  digline cannot inspect is unresolvable rather than answered.
- **The declaration: `FromAutoevals(..., judged=True)`** puts the check in the
  shape reading, makes it eligible for a calibration case and lets
  `--judge-samples` repeat it. Three states: undeclared (the default) is named
  until somebody answers, `False` is an answer too and silences the line, and
  `True` is the one that changes the reading.
- **No baseline moves.** The declaration is excluded from the check's identity,
  beside `threshold` and `tolerance` and for their reason — it says *how* a
  result is judged, not *what* is checked. Without that, declaring would have
  changed `config_hash` and unpromoted every baseline of every suite using an
  autoevals check, for a declaration that changed no number.
- **What it still cannot do**, stated because it will not be closed by trying
  harder: a declared-judged autoevals check is **judged but unidentified**. The
  scorer holds its own client, so `judge_config` stays empty and *the instrument
  moved* cannot see it. A hand-written configuration is refused rather than
  offered — a second source of truth kept in sync by memory is confidently wrong
  the first time the two diverge.

  The reasoning is [ADR 0024 §6.4](docs/adr/0024-the-judge-as-an-instrument.md),
  amended.

### Fixed

- **A corrupt trajectory took the whole command down instead of refusing one
  file.** `tool_calls` had its *elements* shape-checked since 0.12.1 and its
  **container** not, so a document holding `"tool_calls": 5` reached a `for`
  loop and raised a bare `TypeError` — which is not a `ValueError`, and so was
  in none of the CLI's handler lists. `digline migrate` aborted the whole run
  rather than printing `refused <file>: <reason>` for that one file, and
  `digline view` unwound into `socketserver`: a traceback on the terminal and
  **no response at all** in the browser. The container is refused by name now,
  like its elements, and a string is refused rather than walked — iterating one
  yields characters, so the reader used to answer with six refusals about the
  letters of a tool name.
- **`"status": null` was read as `success` — and it is one family with
  `"usage": null`, not two incidents.** `.get()` plus `is None` made an absent
  key and an explicit null one value, so a document could forge a successful
  tool call by writing nothing into the field this project calls *the one field
  a fake cannot forge into vacuity*. `tool_absence`, on the same line of the
  same function, was already refused by name; the asymmetry was the finding.
  The same collapse appeared two days later on `"usage": null` while 0.16.0 was
  being built, and both are closed the same way: `in` decides whether a key is
  there, and its value is then read on its merits. `result_absence` and
  `tool_calls` are closed with them. An omitted `status` still means `success`,
  which is the convention the writer depends on.
- **A stripped `sample_means` on the run side made means read as judgements,
  unannounced.** The compensation that pairs an unstamped sampled verdict with
  a stamped one of the same identity was passed only on the *reference* branch:
  a stripped baseline stamp was recovered and a stripped run stamp was believed.
  Measured on a document with the run's stamp removed, the reading called four
  means four judgements at 0% at the extremes — the precise opposite of a judge
  alternating 0 and 1. The rule is one rule and applies to both sides now: err
  toward leaving a verdict out, never toward misreading one. Where **neither**
  side is stamped nothing can tell, which is the residue ADR 0024 §6.5 already
  declares and re-promotion closes.

- **A judging prompt that could not be composed was reported as the judge
  failing.** `LlmRubric` and `Faithfulness` built the prompt *inside* the `try`
  that catches the judge, so a mapper handing in a context with a non-string in
  it produced *the judge raised TypeError* — naming the one component that was
  innocent, in the sentence somebody reads to decide between re-running and
  investigating. The render now has its own site: *the judging prompt could not
  be composed from these inputs: …*, with the cause still in the sentence. A
  judge that really raises is still reported as the judge.

### Not moved

- `OUTPUT_VERSION` stays **2**: keys are added to `--json`, none removed.
- `config_hash` is untouched — what a run consumed cannot change what it was
  asked to do — so **no baseline needs re-promoting**, and the migration writes
  nothing: a run measured before this release consumed tokens nobody recorded,
  and `0` would state that it consumed none.
- No `TokenBudget`. This release records; a ceiling is a gate and would need its
  own threshold, tolerance and exit code.
- **Known, unchanged:** `ModelPrice` declares one `cache_write_per_mtok`, and a
  provider that bills short- and long-lived cache writes at different rates
  cannot be priced by one. Digline now records `cache_write_tokens`, so the
  count the money was computed from is visible.

The reasoning is [ADR 0025](docs/adr/0025-the-tokens-and-the-bill.md).

## pytest-digline 0.1.6 — 2026-09-18

**The plugin failed a row that `digline compare` calls incomparable.** The
drift was opened by digline 0.15.2 rather than by this plugin:
`Comparison.counts` stopped counting these deltas, so `exit_code()` cannot read
one, while `_failing()` still read `outcome == "regressed"` straight off the
row. A run-level gate that dropped
over a denominator that moved therefore passed `digline compare` and failed
`pytest` — one fact answered twice, which that function's own docstring exists
to forbid.

The row passes and nothing is swallowed: the suite's headline, which this
plugin prints once verbatim, has carried *"N run-level checks were measured
over a different number of cases"* since 0.15.2. A case that could not be
judged is still an ERROR row, and a check that really got worse still fails.
Needs digline **0.15.2 or later**, which is where the flag it reads arrives.

## 0.15.3 — 2026-09-18

**The gate the advisory is about, which two releases had gone past.**
digline **0.15.3**, the delta-pass patch over 0.15.2, alongside pytest-digline
**0.1.6**.
`OUTPUT_VERSION` stays **2** and `SCHEMA_VERSION` stays **13**: no key is added
to or removed from any `--json` document, no stored document changes, nothing
needs migrating and no baseline needs re-promoting.

### Security

- **A gate raised from `fail` to `pass` was still reported as an improvement.**
  [GHSA-8c38-f965-cgww][adv] describes one sentence: a run-level aggregate whose
  denominator shrank because an endpoint made a case unjudgeable, read against a
  reference that counted more cases. 0.15.1 gave that pair a name — an
  incomparability — and 0.15.2 stopped it counting. **Both went past the case in
  the advisory's own table**, because `compare()` classifies a *flip* before a
  denominator is compared at all, on the argument that a flip is each side
  measured against its own threshold.

  That argument holds downward only as an asymmetry, and is wrong upward.
  `pass` to `fail` stays a regression, red and exit 1, because withdrawing it
  would make a run greener — not because it needs no reference: below a
  threshold of 1.0 a case that passed can leave the count and turn the gate red
  on its own, a false alarm this release accepts. `fail` to `pass`
  is also the sentence *"the gate got better"* — a claim about the pair, and the
  pair was never a comparison. So a reference reading `recall fail 0.750000 =
  3/4`, held against a run reading `pass 1.000000 = 3/3` because the case it was
  failing errored, was counted under `improved`, filed in the report under *"What
  got better"* and read by `explain` as a rise. It now carries
  `denominator_moved`, leaves `counts` like every other incomparability, and
  states both numbers of cases: *"the whole run · recall: measured over 3 cases
  here and 4 in the reference, so 0.750000 and 1.000000 are not a movement of one
  another."*

  No new sentence was written for it, in either locale: an incomparable flip
  prints what an incomparable movement already printed. The advisory's range
  moves to `< 0.15.3` and it now carries the fix history of all three releases.
  Found by the delta-pass over 0.15.2. (ADR 0012 §3, amended again)

[adv]: https://github.com/digline/digline/security/advisories/GHSA-8c38-f965-cgww

### What deliberately did not move

- **No exit code changes, and that is the honest measure of this fix.**
  `improved` has never made a run red, so what was corrupted was the reading and
  only the reading — the count, the section of the report, the sentence. The run
  in the advisory's table still exits **2**, because the case the endpoint broke
  is still unjudged. This is the same `I:L` the advisory scores and the reason it
  scores it.

- **`digline diff` still reads two such scores as `same`**, unchanged from
  0.15.2's note: it has its own closed vocabulary, does not read `considered`,
  and teaching it this rule is a decision rather than a patch. The register's
  line is unchanged too, so `digline log` still does not mention an incomparable
  gate; it remains the first passenger on the next `REGISTER_VERSION` move.

## 0.15.2 — 2026-09-18

**The reading a gate gets when it was never compared.** digline **0.15.2**, the
delta-pass patch over 0.15.1. `OUTPUT_VERSION` stays **2** and `SCHEMA_VERSION`
stays **13**: no key is added to or removed from any `--json` document, no stored
document changes, nothing needs migrating and no baseline needs re-promoting.

0.15.1 closed a gate that could be raised from `fail` to `pass` by the operator
of an endpoint ([GHSA-8c38-f965-cgww][adv]) and **did not say so in this file** —
the fix is in that release's commit message and in `tests/test_denominator.py`,
and the entry above it names only the escape work. This release finishes the fix
and records both halves.

[adv]: https://github.com/digline/digline/security/advisories/GHSA-8c38-f965-cgww

### Security

- **A run-level gate that was never compared could still be read as a verdict,
  in either direction.** A run-level aggregate — `recall`, `precision`,
  `accuracy` — is computed over the cases that entered its denominator, and a
  case leaves for five reasons: it errored, it was suspended, it carries no
  label, it is a canary, it calibrates the judge. 0.15.1 taught `compare` to
  notice when the two sides counted different numbers of cases and to refuse
  `unchanged` for them, and it stated, on the field itself, that such a delta
  "never makes `worse` true ... and moves no exit code". The code kept only the
  half nobody could see. `outcome` still pointed wherever the arithmetic
  pointed, and `counts` still counted it — so a gate whose score happened to
  **fall** was counted as a regression, made the run `worse` and exited **1**,
  which is the conversion that sentence promised never happens; and one whose
  score **rose or stood still** was counted under `improved`, filed in the
  report under *"What got better"* and, at 1.0 against 1.0, printed by `explain`
  as `recall got better: 1.000000 to 1.000000` directly under a line saying the
  two were not the same measurement.

  `Comparison.counts` and `Comparison.of` now leave these deltas out, exactly as
  they leave out a calibration delta, and that is the single place `worse` is
  computed from. The direction stays on the row for a reader who wants it; what
  it may no longer do is count. Found by the release delta-pass over 0.15.1. No
  new advisory: [GHSA-8c38-f965-cgww][adv] covers the defect and its range
  (`< 0.15.1`) is unchanged — what shipped in 0.15.1 was the fix to the reading,
  and what was wrong afterwards could make a run **redder**, never greener.

### Fixed

- **The terminal `compare` said nothing about it, and neither did the report.**
  0.15.1 reached `explain` and `--json` only, while the decision it implemented
  names the terminal explicitly. `compare` now prints a clause beside the
  sentence it qualifies — *"Nothing got worse compared with the reference. 1
  run-level check was measured over a different number of cases than the
  reference, so it is not a comparison."* — and names the check on its own line,
  in a group between the regressions and the checks that could not run. The HTML
  report gains a block under the aggregates, *"What was not compared"*, and the
  row is gone from *"What got better"* and from the `improved` tally.

  The block is a block and **not** a seventh section: every entry in the report's
  section list renders even when it is empty, so a seventh would have added an
  empty `(0)` to every report ever rendered, including the ten committed under
  `examples/`. Nothing in this release changes a byte of a report whose
  denominators held.

- **`explain` stopped contradicting its own tally.** The check line now reads
  *"the whole run · recall: measured over 3 cases here and 4 in the reference, so
  1.000000 and 1.000000 are not a movement of one another."* — no verb of
  movement in either direction. `denominator_moved` rides beside `kind` on each
  check fact in `explain --json` rather than becoming a seventh `kind`, so a
  consumer matching on the six it knows keeps working.

### Documentation

- **The operator's design document claimed the payload never reaches your own
  repository. It does, by design, and the sentence was false.**
  `examples/operator/DESIGN.md`, in the *Designed with pilots* section, listed
  four open questions about turning production traffic into cases and wrote the
  fourth as an assertion: *"How redaction happens at birth, so the payload never
  leaves the perimeter even toward your own repository."*

  Two things are wrong with it. A committed case file **is** payload — this
  repository's own `examples/classifier/cases.json` carries a merchant name and
  a free-text note in git, and a promoted baseline carries every verdict's
  `reason`, which with an LLM judge quotes what the model answered. That is
  world 1 of [ADR 0002](docs/adr/0002-three-worlds-and-where-the-data-lives.md)
  working as designed: fixed decision 9 governs what crosses a boundary toward
  another world, and a commit into your own repository crosses none. The
  sentence collapsed the two. And redaction at birth is not something digline
  does — `src/digline/bridge/` is `[planned]` — so it described a mechanism
  nobody has written, in the present indicative.

  Thirty lines away, `examples/operator/README.md` already said the true thing
  about the half that has shipped: *"the judgment layer on a hosted runner means
  your model key lives in GitHub Actions secrets and the reasoning happens
  there."* The fourth item is a question again, and it names the limit that
  makes it hard: a judge that reads text needs the text.

  **It appeared twice, and the other copy was not in this repository.**
  `tools/sync-docs.sh` on digline.dev copies `docs/`, `CHANGELOG.md`,
  `ROADMAP.md`, `docker/README.md` and `examples/*/README.md` — not
  `DESIGN.md` — and the operator page there is written in that repository
  rather than copied from this one. The same sentence was live on
  `digline.dev/product/operator/` and is corrected there separately, in wording
  for a reader who has no ADR beside them. The two texts are deliberately not
  identical.

  Found while reading what ADR 0023 (`proposed`, not merged) says it would have
  to amend. No surface of that record is named here or there.

### What deliberately did not move

- **A flip is still a regression, and still exits 1.** A gate that read
  `pass 1.0` and now reads `fail 0.666667` is failing against *its own*
  threshold, which needs no reference to be true. It is classified before a
  denominator is compared at all, and it stays red. What a moved denominator
  withdraws is the meaning of a *distance*; a flip is not one.

- **`digline log` will not name these runs, and the register is why.** The
  register's line records a comparison as three numbers — worse, better, not
  judged — and an incomparable delta is now in none of them, so a run whose gate
  was not compared appears in `digline log` as a comparison in which nothing
  happened. Adding a fourth number to that line moves `REGISTER_VERSION`, and a
  register at a version this digline does not read is **refused**, not migrated:
  every register written before the change would stop being readable. That is
  not something a patch release may do to a file users already hold, so the gap
  is declared here and is the first passenger on the next register move. Until
  then, `compare`, `explain`, the report and `--json` all state it; only the
  cross-run reading does not.

- **`digline diff` still reads two such scores as `same`.** `diff` answers a
  different question from `compare` — two runs, neither of them approved — and
  it has its own closed vocabulary, in which `same` means "within tolerance". It
  does not read `considered`, so two aggregates of `1.0` computed over four cases
  and over three are still reported as the same, with no clause anywhere saying
  otherwise. **This release does not cover it.** It is the same reasoning in a
  second vocabulary rather than the same edit, it would change what `diff --json`
  can return, and it is a decision rather than a patch. Until it is taken, read a
  `diff` of runs whose case sets may differ the way you would have read a
  `compare` before 0.15.1: check the `counted / not judged` line under each
  aggregate before trusting `same`.

## pytest-digline 0.1.5 — 2026-09-18

**A suite's own text could reach a terminal unescaped.** The plugin prints one
line before a run — `digline: <the call plan>` — and that line names the model
the suite configured, which is a string out of a file somebody else may have
written. It was the only direct terminal write left in any front end once the
escape rule was widened past `digline.cli`, and it did not go through
`report.visible()` while every other sentence this plugin prints did.

Escaped, not stripped: a value that carried an escape is still a value somebody
should look at. Needs no digline upgrade — `visible()` has been exported since
0.10.1.

## 0.15.1 — 2026-09-18

**The escape rule moves to the wire, and `--json` changes shape for the first
time.** digline **0.15.1**, the delta-pass patch over 0.15.0, alongside
pytest-digline 0.1.5. `OUTPUT_VERSION` moves to **2**. `SCHEMA_VERSION` stays
13: no stored document changes, nothing needs migrating, and no baseline needs
re-promoting.

**What changed in `--json`, and what it costs you.** Every string digline renders
for a program — through `digline compare --json`, `explain --json`, `diff
--json`, `log --json` and every `digline-mcp` tool — now has DEL (U+007F) and the
C1 block (U+0080–U+009F) written as their JSON escapes. Six ASCII characters
where there used to be one character, in values and in keys.

A pipeline that read a control character out of a provider-supplied string — a
tool name, a model id, a finish reason — now reads its escape spelling instead.
Nothing else moves: no key is added or removed, no number changes, and text
without those two ranges is byte-identical.

**Why it had to be the value.** `digline.cli` escaped those two ranges on the
finished JSON text, where a parser cannot tell: `\u009b` and the raw byte are the
same character to `json.loads`. That only ever worked for one front end.
`digline-mcp` hands dictionaries to an SDK that serialises them itself, so
digline never touches those bytes — and a tool name carrying U+009B, which *is*
CSI and opens on a terminal exactly what `ESC [` opens, reached an MCP client
raw. The only surface both front ends share is the value, so that is where the
rule now lives, in `digline.wire`. A third front end inherits it without knowing
it exists.

The trade, stated rather than assumed: a control byte inside text the measured
system chose is not data anybody needs verbatim, and one fact must not read
differently at two front ends.

### Security

- **A tool name could carry a terminal escape onto the MCP wire.** Found by the
  release delta-pass over 0.15.0. All three provider plugins pass any non-empty
  string through as a tool name; `ToolsCalled` records it, and a suite declaring
  `Disclosure(score_metadata={"called"})` put it on the wire, where `digline-mcp`
  had no equivalent of the CLI's `emit()`. No advisory, by `SECURITY.md`'s rule:
  the exposure needed a suite to disclose `called`, and the fix ships before the
  surface was announced.

### Fixed

- **The structural escape rule only ever watched `digline.cli`.** It is now
  enforced over every front end, in two halves: a scan for a direct terminal
  write, and — the half that would have caught the MCP hole, which has no `print`
  in it — a check that the bytes the real serialisers emit carry no raw DEL or
  C1. It found one offender outside the core, released separately as
  pytest-digline 0.1.5.
- **A lone surrogate cost a run that had already been paid for.** One unpaired
  surrogate anywhere in provider text made the whole run document un-encodable,
  so `digline run` ended at exit 64 with **no run file** after every call had
  been billed, and `--resume` replayed the recorded answers and died at the
  identical byte, every time, naming neither the field nor the case. A provider
  chooses that text and no plugin validates it, so it needed no repo access.

  The broken code point is now written as its escape spelling and nothing else
  is touched. `ensure_ascii=True` would also have fixed it, and was refused: it
  escapes every accent and arrow in every recorded reason, in the one artifact a
  human reviews in a pull request. A baseline nobody can read is a baseline
  nobody can review, and that readability is the premise of the whole escaping
  argument.

- **`tests/test_example_caps.py` failed on files that were never committed.** It
  gathered documents with `rglob`, while each example's `.digline/.gitignore`
  excludes `*/runs/`, so anyone who had *run* an example went red after a schema
  bump — and the message told them to commit files that are ignored by
  construction. It asks git now.
- **The strict type gate was blind to newly added symbols.** During the
  delta-pass pyright reported every newly added public name in `digline` as an
  unknown import symbol while names that already existed resolved normally — so
  it was green because nobody had added a symbol, not because it was working.
  `src` is now in `[tool.pyright] extraPaths`, which had listed every plugin's
  source root and not the core's own.

  Two things changed before it cleared — that path, and a rebuild of the editable
  install — and the incident cannot be split between them after the fact; the
  blind state could not be reproduced afterwards by removing the path alone. The
  path is kept because it makes resolution independent of install state, not
  because it was proven to be the cause. `tests/test_type_gate.py` now asks
  pyright to accept names this project exports, which catches the symptom
  whatever causes it next time, and is itself unproven for the same reason.

## 0.15.0 — 2026-09-17

**A tool call nobody named is recorded as one.** digline **0.15.0**, with
digline-anthropic 0.5.2, digline-openai 0.5.1 and digline-bedrock 0.5.1.
`SCHEMA_VERSION` moves to **13** and `OUTPUT_VERSION` stays 1: every
stored document has to be migrated, no `--json` shape breaks, and **no baseline
needs re-promoting**, because nothing here touches an identity or `config_hash`.

**Schema 13 carries two passengers, and the train is full**
([ADR 0014](docs/adr/0014-what-may-ride-a-schema-bump.md) §1: a bump is paid
once).

- **The tool call nobody named.** A provider can hand over a call without the
  name of its tool: none of the three SDKs validates a reply. Until now digline
  either errored the whole case or read the call as a tool named `"None"`. The
  run document now omits `tool` for such a call and writes
  `"tool_absence": "not_reported"`, and the named calls beside it are kept.
  `ToolsCalled` never passes over one. It **fails** where the reply settles the
  mismatch without it, and **errors** where every named call matches. Its
  `called` metadata holds `null` at that position. `ToolCalledWith` judges the
  named calls, as it did. `digline-anthropic`, `digline-openai` and
  `digline-bedrock` record the call this way, with their floors raised to
  `digline>=0.15.0`. See [`metrics.md`](docs/metrics.md#toolscalled) and
  ADR 0018 §1, amended 2026-09-17.
- **Not repaired: a `"None"` already recorded.** A run written before this
  release may hold a tool call recorded as `"None"` that was really a call the
  provider did not name: digline-anthropic 0.5.0 or earlier behind an endpoint
  that omitted the name, or a plain-function target that reported
  `"tool": None`. It cannot be told apart from a tool really named `None`, so
  `digline migrate` neither rewrites it nor refuses the document.
- **The shape line stops misreading a fold of folds.** In 0.14.x, a judged
  check wrapped in `Repeated` in a sampled suite stored the means of its
  judgements where the judgements belonged, and the shape line in `explain`
  read them as judgements. A judge that alternated 0 and 1 read as 0% at the
  extremes, which is the opposite of what it was. A nested `Repeated` did the
  same at `samples=1`, and so did a `--judge-samples` replay of a `Repeated`
  check. Such a verdict is now written with `"sample_means": true` beside its
  `samples`. The shape line leaves it out, counts it, and says its
  per-judgement scores were not recorded; `compare --json full` carries the
  count as `sample_means`. A reference from 0.14.x holds these folds unstamped,
  and nothing can stamp them afterwards. Where your run stamps a check, the
  reference's matching sampled verdicts are left out and counted, not read.
  **Your baselines keep comparing**, and nothing re-promotes. For such a check the
  shape line has no share to show on either side, because the per-judgement
  scores it would read were never recorded. To read a judge's shape, declare
  the check without nesting `Repeated` and run the suite at `samples=1`. See
  [`explain.md`](docs/explain.md) and ADR 0024 §6.5.

## digline-anthropic 0.5.2 — 2026-09-17

- **Changed: a tool call with no name is recorded, not errored.** 0.5.1 made
  such a reply error the whole case, so the named calls beside it were lost with
  it. Now the call is `None` at its position in `tools` and `tool_calls`, the
  document records it as a call the provider did not name, and the named calls
  are judged. See digline 0.15.0 above.
- Requires `digline>=0.15.0`.

## digline-openai 0.5.1 — 2026-09-17

- **Fixed: a function call with no name errored the whole case.** A compatible
  server that leaves `function.name` or `custom.name` out, or sends `null`,
  hands the SDK's `None` to the plugin, which built a call named `""` and
  raised. The call is now recorded as one the provider did not name, and the
  named calls beside it are kept and judged. See digline 0.15.0 above.
- Requires `digline>=0.15.0`.

## digline-bedrock 0.5.1 — 2026-09-17

- **Fixed: a `toolUse` with no name errored the whole case.** The service model
  lists `name` as required, but botocore does not check a reply, and its
  parser drops a `null`. Such a call is now recorded as one the provider did
  not name, and the named calls beside it are kept and judged. See digline
  0.15.0 above.
- Requires `digline>=0.15.0`.

## digline-anthropic 0.5.1 — 2026-09-17

`digline-anthropic` alone. digline stays at 0.14.1, and the other two provider
plugins stay at 0.5.0.

```sh
uv add --upgrade digline-anthropic
```

- **Fixed: a tool call with no name was recorded as a tool named `"None"`.**
  The SDK declares the name required but does not check the reply, so a server
  that leaves it out or sends `null` — a gateway behind `ANTHROPIC_BASE_URL` —
  handed over `None`, and the plugin wrote `"None"` into `tools` and
  `tool_calls` with nothing to notice. `ToolsCalled` judged it as a call to
  `"None"`, and a recorded run kept it. The reply now **errors the case**,
  as it already did on `digline-openai` and `digline-bedrock`: an errored case
  is honest, and a misread verdict is not. Recording a call nobody named — so
  that the named calls beside it can still be judged — needs the document to
  say so, and arrives with the next schema.
- **What it does not do:** repair runs already written. A `"None"` recorded
  by 0.5.0 cannot be told apart from a tool really named `None`, so it is
  left as it is.
- Requires `digline>=0.13.0`, unchanged.

## pytest-digline 0.1.4 — 2026-09-17

`pytest-digline` alone, on its own version line. digline stays at 0.14.1 and
nothing else moves. The floor is now **`digline>=0.14.0`**, because the plugin
reads the calibration case's facts, which that release introduced.

```sh
uv add --dev --upgrade pytest-digline
```

- **A calibration case outside its band is an ERROR row.** It is the plugin's
  unjudged state, and it carries the report's own sentence: *the calibration
  case … scored 1.000000 across 2 samples (…), outside its declared band …*. The
  judged numbers in that run are not measurements, which is what ERROR already
  says and what `digline compare` exits 2 for.
- **A calibration case that moved inside its band fails nothing.** Its only gate
  is the band, and the target was never asked, so a movement there is not a
  check of the system that got worse. Every other row is unchanged.
- **What it does not do:** name the checks whose class declares no `KIND`.
  `digline run` prints that line; the plugin's `--digline-run` does not, and
  [`pytest.md`](docs/pytest.md) says so.

## 0.14.1 — 2026-09-17

**Two corrections from 0.14.0's delta-pass, and no behaviour change.**
digline **0.14.1**, alone: `pytest-digline` 0.1.4 follows it as a named tag,
and the provider plugins and `digline-mcp` do not move. `SCHEMA_VERSION` stays
**12** and `OUTPUT_VERSION` stays 1. No stored document moves, and **no baseline
needs re-promoting**. The example locks stay at 0.14.0: their caps admit 0.14.1,
and nothing in this patch changes what they run.

```sh
uv add --upgrade digline
```

- **A correction to what 0.14.0 promised about the calibration answer, and it
  applies to every suite, not only to calibration.** 0.14.0 said a calibration
  case's `output` and `input` are *never written into a run*. The **fields**
  never are, and that holds. A judge's own `reason` can still quote them: when
  every judgement of a case errors, the samples' reasons are kept verbatim, and a
  judge that replied in prose instead of JSON is refused with its reply quoted —
  which commonly restates the answer and the question. That quote reaches the
  run file, the journal, the complete report and the pytest row, all inside the
  perimeter. **No boundary carries it**: `--redacted`, `compare --json`,
  `explain --json` and the MCP server drop every reason, so nothing crossed and
  there is no advisory. This is not new, and it is not specific to calibration:
  **a judge's reason has always been payload inside the perimeter**, able to
  quote whatever answer it graded, in a suite of any kind. The sentence in 0.14.0
  promised more than digline promises anywhere else, so it is corrected rather
  than enforced. The reason is not scrubbed either, because scrubbing it would
  delete the diagnosis a mute judge gives. A test now pins every boundary sink
  for a calibration case on that path. See ADR 0024 §4.7, amended.
- **A known limit of the shape reading, stated before it is fixed.** In a suite
  with `samples > 1`, a check wrapped in `Repeated` stores the per-answer means
  of its judgements, not the judgements. So `explain`'s shape line for it can
  read **0%** at 0 or 1 for a judge that is always at 0 or 1. The run document
  cannot yet say which verdicts are such folds, so the line cannot leave them
  out: do not read a shape line for a `Repeated` check in a sampled suite. At
  `samples=1` the reading is exact. The fix changes the document, which a patch
  does not do. It is ruled as the first passenger of the next schema bump: those
  verdicts will be left out and counted, never shown as zero. See
  [`explain.md`](docs/explain.md) and ADR 0024 §6.2, amended.
- **A known gap in the MCP server, recorded.** `get_run` and `get_baseline` do not
  mark a judged check, a calibration case, a canary or a re-judged run. Nothing
  is withheld by that; `explain` and `compare` carry each as a fact. Closing it
  is a decision about what crosses a boundary, and it is not taken here. See
  [`mcp.md`](docs/mcp.md).

## 0.14.0 — 2026-09-17

**The judge gets a known point.** digline **0.14.0**, not yet tagged.
`SCHEMA_VERSION` moves to **12** and `OUTPUT_VERSION` stays 1: every stored
document has to be migrated, no `--json` shape breaks, and **no baseline needs
re-promoting**, because nothing here touches an identity or `config_hash`.

**Schema 12 is an open train, and that is a rule rather than a note.** Its first
passenger is `CaseResult.calibration`; `Verdict.scale` and `Run.judge_samples`
are ruled onto the same bump by
[ADR 0024](docs/adr/0024-the-judge-as-an-instrument.md) §9. A bump is paid once
— every stored document migrated, every example cap raised
([ADR 0014](docs/adr/0014-what-may-ride-a-schema-bump.md) §1) — so **0.14.0 is
not tagged until both have boarded 12**, or each of them needs a 13 of its own.

- **The calibration case.** `Case(calibration=Calibration(output=…, check=…,
  low=…, high=…, input=…))` declares an answer you know to be partially correct
  and the band a judge that still has a scale places it in. The target is never
  called for it and only the named check runs; it is in no aggregate
  (`calibration_excluded`, silent at zero), and a movement inside its band is
  shown but never counted as better or worse. When the score lands **outside
  the band**, the headline leads with the calibration clause, the run exits
  **`2`** on `Headline.scale_lost` — with or without a baseline — and it cannot
  be promoted (`UncalibratedRunError`). A regression beside it still exits `1`.
  It exists because a judge that has gone binary is *more* repeatable, not less,
  and a repeatability figure alone would call it perfectly stable.
  `pytest-digline` shows a lost scale as the calibration row's ERROR, with the
  report's sentence, in its release that follows; its floor is raised to
  `digline>=0.14.0`. See the
  [API reference](docs/api.md#casecalibration-watching-the-judges-scale) and
  ADR 0024 §4, amended in §4.8 with what building it found.
- **`digline rejudge --judge-samples M`.** On a replay, each judged check asks
  the judge M times per recorded answer, and the verdicts still record what a
  plain replay records. The judge's own range goes into metadata
  (`judge_samples`, `judge_errored`, and the widest answer's `judge_min`,
  `judge_max` and `judge_answer`) and never onto the noise floor. The run
  records `judge_samples` — the second passenger of schema 12. The range is
  never reported without the calibration result beside it: `rejudge` prints both
  in one sentence on stderr and as `judge_reading` in `--json`. See
  [`rejudge.md`](docs/rejudge.md) and ADR 0024 §5, amended in §5.5.
- **Shape, measured and not yet judged.** Against a reference, `explain` adds
  one line per judged check: the share of its raw per-sample scores at exactly
  0 or 1, beside the reference's share
  (`faithfulness: 97.1% of 208 judged scores at 0 or 1, against 41.3% of 204 in
  the reference.`). `compare --json full` carries the counts as `shape`. There is
  deliberately no sentence saying *more*: that threshold is sized on data and
  added later. Shape is never in the headline and never an exit code. It reads
  a new document key, `"judged": true`, written only on verdicts whose check
  declares `KIND = "judged"` — the third and last passenger of schema 12. A suite
  with a judge gains one key per judged verdict. No score, status or identity
  moves, and no comparison against an older baseline reports a delta. See
  [`explain.md`](docs/explain.md) and ADR 0024 §6, amended in §6.4.
- **New lines on your terminal: `KIND` is optional but no longer unread.**
  0.13.3's documentation said nothing that runs reads `KIND`. That is no longer
  true. From this release, `digline run` names on stderr, on every run, each
  check whose class declares no `KIND`, because the shape reading leaves it out
  and the exclusion must not be silent. Nothing fails; declare `KIND` on the
  class to stop the line. digline's own dogfood suite is the first to be named:
  scout's `agrees_with_mark` and `agrees_on_comment` declare none.
- **The known hole: `FromAutoevals`.** An autoevals scorer that calls a model is
  **neither judged nor announced**. The adapter declares `wrapper` and wraps a
  scorer, not an assertion, so nothing can be read through it: the shape
  reading cannot see that scorer, and no line tells you. Closing the hole needs
  its own decision, on how the adapter declares what its scorer is. It is not
  taken in this release.

## 0.13.3 — 2026-09-16

**A check says what kind it is, and the home stops being a hand-kept list.**
digline **0.13.3**, alone: the three provider plugins stay at 0.5.0,
`digline-mcp` at 0.1.3 and `pytest-digline` at 0.1.3, and no floor moves.
`SCHEMA_VERSION` stays **11** and `OUTPUT_VERSION` stays 1 — no stored document
moves, **no baseline needs re-promoting**.

A patch, by the rule `RELEASING.md` now writes down: between v0.13.2 and this
release one public name is added — `CheckKind` in `digline.core` — and nothing
is removed or renamed, no CLI subcommand, option or exit code moves, and the
schema stays where it was.

```sh
uv add --upgrade digline
```

- **`KIND` on every shipped check.** Each of the 22 checks `digline.core`
  exports declares a `KIND: ClassVar[CheckKind]`: `deterministic`, `judged`
  (`LlmRubric`, `Faithfulness`), `budget` (`CostBudget`, `LatencyBudget`),
  `aggregate` (`Precision`, `Recall`, `Accuracy`, `F1`) or `wrapper`
  (`Repeated`, and `FromAutoevals`, whose scorer may or may not call a model).
  `AssertionBase` and `RunAssertionBase` declare it without a value, so a shipped
  check cannot be `deterministic` by omission; on a check of your own it is
  optional, and nothing that runs, compares or promotes reads it. It is a class
  variable and not a dataclass field, so **no `identity` and no `config_hash`
  moves** — pinned against values computed before it existed, and against every
  committed example baseline, which still pairs and still promotes. The
  *Custom assertions* section of the API reference explains the five values.

- **The home capture carries the commands and the checks.**
  `docs/assets/home/home.json` gains two keys, each with the `source` sentence
  the other keys have:
  - `cli_commands` — every public subcommand of `digline` with its help line,
    in the order the parser declares them, read from the CLI's own
    `build_parser()`;
  - `checks` — every exported check with its `KIND` and the anchor of its card
    in the metrics page.

  The capture refuses to write a list with a hole in it. It stops on a check
  with no `KIND`, a `KIND` outside the five, a check with no card, or an
  argparse that no longer exposes its subcommands.

- **Docs: the guide shows `digline list`.** Chapter 6 lists the five runs it
  has just recorded, above the baseline chapter 5 promoted, before choosing
  which one to promote. It was the one public subcommand the guide never ran.

  The replay that executes the guide now compares run keys by **identity**
  rather than blanking them: the first time a key on the page meets a key a
  command printed, the two are bound for the rest of the page, so one key cannot
  stand for two runs and two keys cannot stand for one. That found two keys the
  page had carried since it was written and no execution produced — chapter 1's
  second run printed the first run's key, and chapter 8's fresh reference named
  a run the page never ran. The first line is gone and the second now names the
  run the page does run.

- **Docs: ADR 0024, *The judge as an instrument*, proposed.** Four
  measurements of the judge — noise and scale, at one point and across the
  suite — written and checkpointed before any code; nothing in it is
  implemented in this release. ADR 0020 §4 gains one sentence: identity decides
  which runs are grouped, and scores never decide identity. `AGENTS.md` and the
  operating-digline skill gain a rule: read what the judge reads before
  measuring how it moves.

- **Releasing: how a version is chosen is written down.** The minor moves when
  something a user relies on stops working as it did; everything that leaves
  existing suites, scripts and stored documents working — fixes, documentation,
  CI and additions — is a patch.

## 0.13.2 — 2026-09-16

**The pages those commands were owed, and a home that was run rather than
typed.** digline **0.13.2**, alone: the three provider plugins stay at 0.5.0,
`digline-mcp` at 0.1.3 and `pytest-digline` at 0.1.3, and no floor moves.
`SCHEMA_VERSION` stays **11** and `OUTPUT_VERSION` stays 1 — no stored document
moves, **no baseline needs re-promoting**.

The honest headline first, because the diff says it plainly: **nothing under
`src/` changed.** A 0.13.2 wheel answers every command exactly as 0.13.1 does,
and a reader who upgrades for the code gains nothing. This is the documentation
0.13.0 shipped without. It is a release rather than a commit because
digline.dev documents the version people install. Since these pages reached
main, the site has shown them for a version nobody can install, and a release
build from v0.13.1 no longer passes.

```sh
uv add --upgrade digline
```

- **Docs: `log` and `register` have the command pages they were owed.** 0.13.0
  shipped both commands and sent the reader to an ADR, which records *why* a
  decision was made and is not a page about how to run something.
  [`docs/log.md`](docs/log.md) and [`docs/register.md`](docs/register.md) are
  those pages: the question each command answers that no other one does — *has
  the model behind my alias changed?* for `log`, *what did a person decide?*
  for `register` — with the shipped output quoted rather than sketched, and the
  README table now links the page beside each command instead of the decision.

  One correction rides inside the first: **"No roll recorded." is scoped to the
  history it was read on.** A store with nothing in it and a store whose runs
  all agree are not the same finding, and the page said so in a sentence that
  read like the second when it meant the first.

- **Docs: ADR 0020 and 0021 amended where the shipped code says otherwise.**
  Three factual corrections, no decision revisited, each dated in the record it
  amends. ADR 0020 §10 drew the reading as a column table and `log_text` prints
  one sentence per span, so the sketch was a draft and the page now quotes what
  shipped. ADR 0021 §3 gave `recorded_at` to the second, and `digline register`
  reads the clock through `host.utc_now_iso()`, which keeps microseconds on
  purpose — truncating once let two runs in the same second share a key. And
  ADR 0021 §8's section of the reading **is windowed**, on each disposition's
  own `recorded_at` rather than on the `created_at` of the run it names: a
  window that closes before a person read a comparison shows the run and not
  the decision about it, and no record said so.

- **Docs: the home of digline.dev is a capture now, and the capture is run.**
  The home carried a console block typed into the page, printed by a version
  three minors old and reproducible by nobody.
  `tools/home_capture.py` replaces it with
  `docs/assets/home/home.json`, written by **running digline** in two throwaway
  git repositories: the guide's first chapter, read out of its own fences so the
  guide cannot drift from it, and a one-line prompt regression that must end
  **red** with at least one case worse or the capture fails — a home that went
  green would put a claim on the page the tool did not make. Every command's
  stdout, stderr and exit code are recorded as they came out, nothing is
  stripped or re-typed, and nothing reaches the network: the provider keys are
  removed from the environment and the proxies point at a closed port. The file
  also records what the installed digline **declares** — its runtime
  dependencies, and its `Requires-Python` range — each beside a sentence saying
  what was read and in which interpreter. CI fails when the capture is not the
  version in `pyproject.toml`, so the page cannot describe a release that is not
  this one.

- **CI: a release is waited for, not retried past.** The consumers of a publish
  used to race the index and fail on a schedule rather than on anything in the
  tree — five times, counted. `.github/await_index.py` asks the one question a
  retry cannot answer: *is this exact file served to this runner?* — and its red
  says which of the two it is, a version still propagating or a project that was
  never published. It runs in each consuming job, because one runner's view of
  the index does not prove another's.

- **Docs:** the README, ROADMAP and SECURITY front doors say what digline is at
  0.13.1 rather than what it was, the adversarial delta-pass before an
  announcement is written down as a standing rule rather than remembered, and
  the README carries the PyPI downloads badge beside the others.

## 0.13.1 — 2026-09-15

**The register, read as the hostile document it is.** digline **0.13.1**,
alone: the three provider plugins stay at 0.5.0, `digline-mcp` at 0.1.3 and
`pytest-digline` at 0.1.3, and no floor moves. `SCHEMA_VERSION` stays **11** and
`OUTPUT_VERSION` stays 1 — no stored document moves, **no baseline needs
re-promoting**.

The honest headline first: **0.13.0 could refuse a register it had written
itself.** Its reader split lines wherever Python's `splitlines()` does — at NEL
and the Unicode line separators as well as at `\n` — and the writer puts those
characters down raw inside a string, so a line digline recorded read back as a
corrupt register. That, and six ways a hostile line defeated the same reader,
are fixed below. All of it comes from the delta-pass over 0.13.0 and the tests
written to close what it found, before any announcement.

```sh
uv add --upgrade digline
```

- **Fixed: a committed register is read as the hostile document it is.**
  `log`, `register` and the MCP `log` all read `.digline/<tenant>/register/`,
  and anyone who lands a pull request writes it. Six ways a line could defeat
  the reader in 0.13.0, each now **refused by name, with its line number, and
  the file left untouched** — the way the journal and the run file refuse
  theirs:

  - `Infinity` in a count, or nesting deeper than a line holds, reached every
    reader as a **traceback** (`OverflowError`, `RecursionError`) — to the MCP
    client as a bug report;
  - a wrong-typed field was **coerced into a different record**: `"worse":
    "false"` read as *worse*, `2.9` regressions as 2, `"exit_code": true` as 1.
    ADR 0021 §5 already said a line this digline cannot read is refused; the
    reader had been converting instead. A refusal names the field and the kind
    of value it held, never the value;
  - a **duplicate key** resolved last-wins, so one line could say `accepted` and
    `rejected` and be read as the second;
  - an integer thousands of digits long, and a line starting with a
    **byte-order mark**, read as a **torn tail** — which also made `register`
    refuse to append, on a false reason. A mark is not a tear, and neither is a
    line that parses into something no writer produces, so none of these is
    forgiven on the last line either.

  And one the tests found on the way: the reader split lines with
  `str.splitlines()`, which also breaks at NEL (U+0085) and the Unicode line
  and paragraph separators. The writer puts strings down raw, so **a register
  digline itself wrote could read back as corrupt**. A register line ends at
  `\n` and nowhere else. Where the register cannot be read, `log` still reads
  the runs and says so, as before; `digline register` is where the named
  refusal is printed.

- **Security:** `log --json` **no longer puts a C1 control character on your
  terminal**. The register is committed, so a pull request writes its strings,
  and a `run.environment` holding U+009B — CSI on its own, the same sequence
  ESC `[` opens — reached stdout raw. `emit()` printed every `--json` document
  unescaped on a premise its own docstring stated: that `json.dumps` escapes
  every control character. **It does not escape DEL or C1.** It writes C0 as
  `\u00XX` and, under `ensure_ascii=False`, which is how every document here is
  built, leaves U+007F and U+0080–U+009F as they came. `emit()` now escapes those
  two ranges itself, at the sink, so every `--json` command inherits it; the
  value a parser reads is unchanged.

  The class predates this release — the premise was written in 0.10.1, beside
  `say()` — and 0.13.0 added a source anyone with repository write access can
  fill. That capability is, in `SECURITY.md`'s words, "already the capability to
  edit `suite.py`, which is code and executes". So no advisory, by
  `SECURITY.md`'s line, on the precedent of 0.10.1 and 0.12.1.

  **It is the third time this family bit, so the rule is now standing rather
  than remembered:** every source of third-party text reaches a terminal through
  `digline.cli.output` — `say()` for a sentence, `emit()` for a document — **by
  construction**. One test enforces it, and it is the one place to look:
  `test_nothing_in_the_cli_prints_except_through_say_or_emit` refuses any
  `print` or stream write in `digline.cli` outside that module. It found one on
  its first run — `digline view`'s start-up line — which now goes through
  `say()` too.

- **Fixed: one unreadable tool call no longer decides a check about another.**
  `ToolCalledWith` errored as soon as *any* call to its tool had arguments that
  were not JSON — even beside a call that matched, in either order — and a call
  that was not a mapping errored the whole trajectory. `digline-openai` 0.5.0
  keeps a non-JSON `function` argument verbatim, so a real provider reaches this.
  An unreadable call — not a mapping, no tool name, or arguments that do not
  decode — is now counted and stepped over: a match elsewhere passes the check,
  and it errors only when nothing readable matched, because then the call it
  needs may be the one that could not be read. The logic dates from 0.12.0.

- **Docs:** `digline.targets.free`'s docstring no longer promises delegation
  "from their next releases"; the OpenAI and Bedrock plugins have shipped it.

## digline-openai 0.5.0 — 2026-09-15

- **Added: the trajectory.** Every tool call reaches `Response.metadata` with
  its arguments, so `ToolCalledWith` judges an OpenAI target. `function`
  arguments are decoded when the model wrote a JSON object and kept verbatim
  when it did not; a `custom` call's free-form input is kept as written. Chat
  Completions returns what the model asked for and stops, so every call is
  recorded `status="not_reported"` with its result `not_reported`.
- **Fixed:** a `custom` tool call was recorded under the name `""` —
  `function.name` was read on a call that has none.
- **Changed: `free()` is a declared price.** It delegates to
  `digline.targets.free`, so a Python suite hashes as its data-suite twin with
  four declared zeros ([ADR 0022](docs/adr/0022-the-declared-price.md) §2). **A
  suite that already used it gets a new `config_hash` on upgrade**: its baseline
  stays comparable and is no longer promotable until a new one is signed.
  **Re-promote when you upgrade**: run the suite once on the new plugin, read
  the comparison, and promote that run as the reference.
- **Added: `gpt-6-astra`**, priced from the list read on 2026-09-11 — in the
  repository since digline 0.10.0, on the index for the first time.
- **Known: cache writes are undercounted, in the good-news direction.** openai
  3.13.0 reports `prompt_tokens_details.cache_write_tokens` and GPT-5.6 and
  later bill them, but whether they sit inside `prompt_tokens` is **unmeasured**,
  and each guess misprices. So the plugin still reports zero, and a call that
  writes a cache costs more than the run says. `CACHE_WRITES_ARE_INSIDE_PROMPT_TOKENS`
  is `None` until the live test that measures it — three calls, caching off as
  the baseline — has been run; this is not fixed.
- Requires `digline>=0.13.0`.

## digline-anthropic 0.5.0 — 2026-09-15

- **Added: the trajectory.** Every `tool_use` and `server_tool_use` block
  reaches `Response.metadata` with its input, so `ToolCalledWith` judges an
  Anthropic target. A client-side call is recorded `status="not_reported"` —
  the tool runs after the reply. A server tool's outcome is read from its result
  block in the same reply: an error records `status="error"` and the provider's
  `error_code`; a success records `status="success"` and its payload as
  `not_recorded`, because search pages and code output would push the answer
  over the recording ceiling with them.
- No `free()`: Anthropic hosts every model it serves, so there is nothing to
  delegate.
- Requires `digline>=0.13.0`.

## digline-bedrock 0.5.0 — 2026-09-15

- **Added: the trajectory.** Every `toolUse` block reaches `Response.metadata`
  with its input (a non-object input as canonical JSON), so `ToolCalledWith`
  judges a Bedrock target. A client-side call is recorded
  `status="not_reported"`. A server tool with a `toolResult` in the output
  records `error` with **the error text** — Converse carries words where the
  other providers carry a code, and they are the only diagnostic — or `success`
  with its payload `not_recorded`; without the `status` AWS documents for Nova
  and Claude only, neither is claimed. Read from botocore's service model; not
  yet checked against a real server-tool reply.
- **Changed: `free()` is a declared price**, delegating to
  `digline.targets.free`. **A suite that already used it gets a new
  `config_hash` on upgrade**: its baseline stays comparable and is no longer
  promotable until a new one is signed. **Re-promote when you upgrade**: run the
  suite once on the new plugin, read the comparison, and promote that run as the
  reference.
- Requires `digline>=0.13.0`.

## digline-mcp 0.1.3 — 2026-09-15

`digline-mcp` alone, on its own version line, one tag after the digline it
imports from: digline stays at 0.13.0, the provider plugins at 0.4.0 and
`pytest-digline` at 0.1.3.

```sh
uv add --upgrade digline-mcp
```

- **`explain` and `log` join the surface, which moves once from six tools to
  eight** — [ADR 0020](docs/adr/0020-the-reading-across-runs.md) §9, amending
  ADR 0011 §1. `explain` is `digline explain --json` — the fact list and the
  exit code, composed once in the host so the two front ends cannot read one
  run differently — and it takes no locale, because the list ships no prose.
  `log` is `digline log --json`, register included, and carries no exit code.
  Neither writes, and nothing that writes joined them: `promote`, `migrate`,
  `view`, `report` and the register's writer stay absent.
- **Requires `digline>=0.13.0`.** The two tools import names that first ship in
  digline 0.13.0, so they ship in the release after it, with the floor raised
  to it: a floor cannot name a release that does not exist yet, which is the
  shape ADR 0017 §11 gave `prepare` and `measure`.

## 0.13.0 — 2026-09-15

**The ledger.** digline **0.13.0**, alone on this tag: `digline-mcp` stays at
0.1.2 and `pytest-digline` at 0.1.3, and the three provider plugins stay at
0.4.0 here and follow in their own 0.5.0, which needs this release.
`SCHEMA_VERSION` stays **11** and `OUTPUT_VERSION` stays 1 — no stored document
moves, no `--json` shape breaks, and **no baseline needs re-promoting** unless
you declare a price.

Four strands, and they are one question asked of a run from four sides: what
answered, what it cost, what it did, and what a person decided about it.

- **The reading across runs, and the human's memory of a verdict.**
  `digline log` ([ADR 0020](docs/adr/0020-the-reading-across-runs.md)) reads
  which model answered down a suite's stored runs, and names each absence
  rather than collapsing it. `digline register`
  ([ADR 0021](docs/adr/0021-the-register.md)) keeps what a person decided about
  a comparison, committed like a baseline — until now `compare` answered and
  the decision lived in whatever commit message mentioned it.
- **The declared price** ([ADR 0022](docs/adr/0022-the-declared-price.md)). A
  data suite can now describe what an OpenAI-compatible endpoint, a gateway or
  a self-hosted model actually charges, so a `CostBudget` stops measuring
  somebody else's prices. The price enters `config_hash`, which is why
  `promote`, `view` and `rejudge` now take `--target`: a multi-target suite
  names what it signs.
- **An echoed id is not a verified identity, and a withheld one is not a
  match.** The seventh absence: an endpoint that returns the requested id as the
  model that answered has identified nothing, and `compare`, the report,
  `explain` and `log` say so. And a comparison no longer reads *the same
  configuration* over an answering model it withheld.
- **The trajectory, for anyone using the three SDKs.** 0.12.0 recorded a
  trajectory only a plain-function target could fill. This release gives a
  provider plugin the words for what it cannot see — `not_reported`,
  `result_absence`, `digline.targets.ToolCall` — and the 0.5.0 plugins that
  follow fill it for OpenAI, Anthropic and Bedrock.

**What it costs you, in order.** Nothing, for a suite that declares no price.
Declaring one moves `config_hash` once: the old baseline stays comparable, and
the first run under the declared price is the one to read and promote. A Python
suite priced with `digline_openai.free()` or `digline_bedrock.free()` moves once
too — not on this upgrade, but on the plugin's 0.5.0, which is where the window
named below closes. A document recorded with the 0.5.0 plugins can carry
`not_reported`, which 0.12.x refuses by name: read it with this digline or
newer. The examples' cap moves to `<0.14` and their floor does not.

```sh
uv add --upgrade digline
```

- **Fixed:** `compare` and the report **no longer say "the same configuration"
  over an answering model they withheld**. At a named endpoint — an
  OpenAI-compatible aggregator, a corporate gateway, a self-hosted server
  behind `base_url` — `resolved_model` is a perimeter field and is withheld
  inside the comparison, so every declared field can match while the model
  behind the endpoint changed. The headline read that as *"answered under the
  same configuration as the reference"*: a withheld identity read as
  confirmation. It now says *"the same declared configuration; what answered is
  withheld, so whether the model changed is not known."* Nothing leaked, and
  still nothing does — the value stays withheld and the sentence reveals nothing
  about it; the report simply stops asserting what it does not know. Found by
  the first external run of the TOML quickstart, against an OpenAI-compatible
  aggregator.

- **Added: `[target.pricing]`, what the endpoint actually charges** —
  [ADR 0022](docs/adr/0022-the-declared-price.md). A data suite pointed at an
  OpenAI-compatible aggregator, a corporate gateway or a self-hosted model
  priced every call from the plugin's own list, so a `CostBudget` measured
  somebody else's prices; `pricing` was refused as an object. Four per-million
  rates under a provider target are data, and now declarable. The declared price
  replaces the plugin's entry for the model, the run records
  `pricing = "declared"` and the rates, and a Python suite declares the same way
  with `override()`.

  **A declared price enters `config_hash`**, because the rate is the ruler a
  `CostBudget` reads cost on, not a property of the system: declaring or
  changing one makes the baseline comparable and not promotable. A suite that
  declares no price hashes exactly as before, and no stored run or baseline
  moves. At a named endpoint the rates are withheld, and **that withholding is a
  latch, not a constraint** — the value never prints, but the hash narrows it; a
  rate you cannot afford to narrow belongs in a Python suite, or at an unnamed
  endpoint.

  One pair disagrees for a window, and it is named here so nobody finds it: a
  Python suite that prices a hosted model with `digline_openai.free()` or
  `digline_bedrock.free()` still hashes as it did, while its data-suite twin
  with four declared zeros hashes with the declared price. The two forms agree
  about that suite from `digline-openai` 0.5.0 and `digline-bedrock` 0.5.0,
  whose `free()` delegates to `digline.targets.free`; with an older plugin the
  window stays open. `digline-anthropic` has no `free()` to delegate. Closing it
  moves that suite's hash once, so **re-promote when you upgrade** the plugin.

- **Added: a provider's tool calls reach the record, and what the provider does
  not report is named** — [ADR 0018](docs/adr/0018-the-recorded-trajectory-and-the-agent-under-test.md)
  §1, amended. A provider plugin sees the model *ask* for a tool and nothing
  after: the tool runs later, in the application. So `ToolStatus` gains
  **`not_reported`** — *the provider never reports a status for a client-side
  call; the call may have succeeded or failed, and the document does not
  know* — and `RecordedToolCall.result_absence` says why a result is empty:
  `not_reported` for a client-side call, `not_recorded` for a server tool's
  successful payload, which is bulk. A failed server tool records its error.
  An assertion may assert on the tool and its arguments, and never on a status
  or a result nobody reported. `Completion` gains `tool_calls` beside `tools`,
  built from `digline.targets.ToolCall`.

  **No schema bump, and an old reader refuses rather than misreads.** 0.12.x
  rejects a document carrying `not_reported` by name — *RecordedToolCall.status
  must be 'success' or 'error', got 'not_reported'* — so read runs recorded with
  the 0.5.0 plugins with this digline or newer. Every document 0.12 wrote reads
  as it did, and a plain-function target that leaves `status` out still records
  `success`.

- **Fixed: `promote`, `view` and `rejudge` take `--target`.** `run --target`
  could choose among a `suite.py`'s targets and `promote` could not, so a
  multi-target suite could sign a run made against one system as the reference
  for another, with nothing in the promotion saying which. The declared price
  made it visible, because the hash now depends on the target; the flag has
  `run`'s meaning, and a data suite, which has one target, refuses it.

- **Added: `digline log`, which model answered, read down a suite's stored
  runs** — [ADR 0020](docs/adr/0020-the-reading-across-runs.md). For each side,
  target and judge, the reading shows spans of the same sent model and the same
  answering model, and the **rolls** between them. A roll is only one thing: the
  same sent model, recorded answering as a different model. A changed sent model
  is somebody editing the suite, and a roll across runs that recorded nothing
  carries a window — the last run that recorded the old model, the first that
  recorded the new one — and never a date inside it.

  Real history is mostly absence, so the absences are named rather than
  collapsed: *declared no configuration*, *several judges; no single answering
  model*, *withheld at a named endpoint*, *no answering model was reported*, and
  *not recorded* for a document that does not name the digline that wrote it —
  which stays undated, because the dependency pin at its `git_commit` is a
  second record read off a tree that was commonly dirty — and *echoed*, where the
  endpoint returned the requested id as the model that answered. That last one
  is an absence disguised as a presence, stated as a fact and never as a
  diagnosis: an honest provider may legitimately echo, and an echo cannot be one
  side of a roll. Where what answered is not identified the reading says the
  canary is the only instrument that sees behaviour. Files the scan could not
  read are counted. A replay is never counted as a sighting of the target,
  because it asked the target nothing.

  **The reading reads no score, and its types have no field for one**: a roll
  is declared by the record and never deduced from numbers moving, which is the
  canary's job in `compare`. The configuration is redacted inside the fold, so
  the answering model behind a named endpoint reaches no rendering — and the
  cost is stated: a roll there cannot be declared at all. `log` is **never a
  gate**: it exits 0 whatever it finds. Checked against the dogfood's real
  store, it says what that store can say: *No roll recorded*, over three
  sightings and twelve runs that recorded nothing.

- **`compare`, the report and `explain` say when an endpoint echoed the
  requested id.** Where the run being compared recorded the id it sent as the
  model that answered, the headline adds *"the endpoint returned the requested
  id, `gpt-5.6-sol`, as the model that answered, so which model answered is not
  identified; only a canary sees whether its behaviour changed"*, `compare
  --json` carries `target_echoed`, and `explain` carries the tally `echoed` — the
  fourth amendment to ADR 0012 §3's closed list. It moves no exit code. Behind a
  named endpoint it is never said, because the answering model is withheld there
  and *echoed* would disclose it. `OUTPUT_VERSION` stays 1.

- **`runs_json` carries each run's aggregate verdicts**, the column `digline
  view`'s grid already shows — `name`, `assertion_id`, `status`, `score`,
  `threshold` and `tolerance`, and nothing else a verdict carries. Its one
  caller is the MCP `list_runs` tool, so the machine surface an agent reads is no
  longer thinner than the one a person does. An added key: `OUTPUT_VERSION`
  stays 1.

- **Added: `digline register`, and the register it writes** —
  [ADR 0021](docs/adr/0021-the-register.md). `compare` answers and then forgets;
  a rejection lived only in whatever commit message mentioned it, and named no
  run. `digline register --run KEY --disposition accepted|rejected|unsure`
  records what a person decided about a comparison, as one line under
  `.digline/<tenant>/register/<suite>.jsonl`, **committed like a baseline**.
  The disposition is mandatory. The line carries the verdict the person was
  looking at — computed by the gate's own comparison, with the digline that
  computed it — as **counts and keys only**: no case id, no sentence, no free
  text, no author. The reason goes in the message of the commit that adds the
  line, which the run key in it now joins to its run.

  The register is only ever appended to: a changed mind is a second line. An
  incomplete last line is stated and never appended after; a corrupt line
  anywhere else is refused by name and the file is left alone; the format has
  its own version and no migration. A generated `.digline/.gitattributes` merges
  it by union, so two branches that each record keep both lines. `digline log`
  shows it beside the story of the alias — and because it is committed, it is
  there on a clone that has no runs at all. The decision journal of ADR 0019
  stays the machine's memory, ignored by git; the register is the human's.

- **`AGENTS.md` and the `operating-digline` skill: a disposition is a person's
  too.** Never recorded on an agent's own initiative, and never on a schedule.

- **`examples/operator/` gains a policy, a judgment seat and a decision
  journal** — [ADR 0019](docs/adr/0019-the-reasoning-operator.md). The loop's
  classification does not move: `draw`, `drift`, `structural` and
  `system-error` are decided exactly as before, and four tests still hold them.
  What is new is what happens after it. `decide.py` reads a `[policy]` table in
  `operator.toml` and decides whether the classification wakes anybody, and a
  decision that holds a cycle **names the clause that held it** — a reason that
  cites no clause is the model's opinion, and there is no branch that produces
  one. A clause may only narrow: it holds, it never wakes, and three floors
  refuse it by name — a canary that moved, the stopping rule mid-cycle, a run
  that could not be judged.

  Every decision is appended to `.digline/<tenant>/decisions/<suite>.jsonl`,
  gitignored and append-forever, holds most of all: a hold nobody records is
  indistinguishable from a cycle that never ran. `answer.py` is where a person
  says later whether they would have wanted waking. The probe grows a second
  negative — can this identity write the policy it exercises, reported
  `enforced`, `unenforced` or `inconclusive` rather than as a collapse, because
  on an ordinary checkout it simply can — and a fourth check: the
  `policy_digest` a cycle reports must be the digest of the policy on disk.
  `AGENTS.md` and the `operating-digline` skill carry the rule in one paragraph:
  a policy is approved in a diff, like a baseline, and never edited by what
  exercises it.

  **Nothing under `src/` changed.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no
  plugin floor, no baseline re-promoted, and a fork with no `[policy]` table
  escalates exactly as it did.

- **`examples/operator/`: `cycle.json` moves from format 3 to 4**, because a
  cycle now carries the tenant, the `policy_digest` it was measured under and
  the probe's policy wall — and `decide.py` refuses a cycle below 4 by name
  rather than deciding about one on a guess. A forked loop writes format 4 on
  its next run and alerts already written are untouched, but the new seat and
  dossier cannot read a format-3 cycle. The decision arrives beside it as its
  own file, `decision.json` at `DECISION_FORMAT` 1. The captured alerts were
  regenerated through the new path, and a third joined them: `held` is the
  **same cycle** as `drift`, decided under the policy, so the two documents
  differ in nothing except what a declared policy did about an identical
  measurement.

- **Fixed:** the operator example's workflow **lost the decision journal between
  cycles**, which switched `max_cycles` off without a word. The journal is
  gitignored and a hosted runner starts empty, so every scheduled cycle read an
  empty history, every streak counted from zero, and a clause allowing two
  cycles held the tenth. The workflow now carries the journal as an artifact,
  restored from the newest one uploaded rather than from the last green run. A
  journal that exists and cannot be restored is **not** an empty one:
  `decide.py --streak-unknown` says so, and a clause with `max_cycles` does not
  hold on a streak nobody can count. Found by the ledger's reconnaissance, in
  the example as published; the dogfood had already carried the journal, and
  swallowed a failed restore the same way.

## 0.12.1 — 2026-09-13

digline **0.12.1**, alone: the three provider plugins stay at 0.4.0,
`digline-mcp` at 0.1.2 and `pytest-digline` at 0.1.3 — every fix here is in the
core, and each of those readers inherits it. `SCHEMA_VERSION` stays **11** and
`OUTPUT_VERSION` stays 1: no stored document moves, **no baseline needs
re-promoting**.

Two security fixes and three correctness ones, all five **found by the release
delta-pass over 0.12.0's own new surface** — the standing rule in
`RELEASING.md`, run before the announcement round rather than after it. The
surface the pass was convened for came back clean: a tool call's name, its
arguments and its result are printed at no sink at all, and no `Disclosure`
reaches them. What it found instead was older than the release it was auditing.

```sh
uv add --upgrade digline
```

- **Security:** a **perimeter field no longer crosses a boundary inside a
  comparison**. `base_url`, `fingerprint`, and `resolved_model` at a named
  endpoint are withheld from a redacted document — 0.8.1 established that, for
  the reason ADR 0005 §2 gives: a custom endpoint describes the *client's own
  topology*, and `acme-legal-assistant.internal.bank.example` is a customer
  name. `config_deltas()` read `SystemConfig.values` raw, so the same field
  walked out of the **delta** instead of the projection.

  The reach is what makes it worth a fix rather than a note. `compare --json`
  ships these deltas to a CI log, and **`digline-mcp` returns the same object to
  a model** — so one server answered two ways about one run: `get_run` reported
  `withheld: ["base_url"]` while `compare` handed over the value. It travelled in
  both `--json` modes, not only `full`. `config_json`'s own docstring asserted
  the opposite ("a withheld field carries no value to print in the first
  place"), true only when both runs had already been redacted, which is the
  `report --redacted` path and not this one.

  Both sides now go through `redacted()` **inside `config_deltas`**, so `diff()`
  inherits it and the door closes once. It needed no new rule: reducing first
  turns a perimeter field into a withheld one, and the existing rule 3 already
  answers `unknown` for those — the value goes, the question is answered
  honestly, and a model id still travels in clear because it is a measurement.
  A marker is now driven through `compare_json` and `diff_json`, in both modes,
  which is the surface the boundary suite had never driven.

  Affected: **digline >= 0.6.0, < 0.12.1**, where a comparison or a diff is read
  over MCP — or from `--json` — and `target_config` carries a perimeter field,
  which means a target with an explicit `base_url`. Filed as a GitHub Security
  Advisory, **Low**: it shipped, so the rule in `SECURITY.md` says advisory
  rather than changelog line, and the exposure is a hostname to a reader who
  already has the run.

- **Security:** `digline report` **with no `--out` no longer puts a control
  character on your terminal**. It prints the document to stdout, `emit()`
  deliberately bypasses the sanitiser, and its reason said why: the values are
  "already HTML-escaped where they are rendered". They are — and `html.escape`
  covers `& < > " '`, which does nothing at all to `0x1b`. A judge's `reason`
  quotes what a model wrote, so an answer carrying `\x1b[2K\r` forged a line
  over the one above it: in the probe that found this, *"digline: Nothing got
  worse."* appeared under a run that was red.

  0.10.1 closed this class at `say()` and missed `emit()`. The fix is in the
  escaping and not in a check for a tty: C0, DEL and C1 become **numeric
  character references**, so the bytes are safe at a terminal and a browser
  still resolves them to the inert characters the model actually sent. One
  document, whether it is piped to a file or read on a screen. No advisory, by
  `SECURITY.md`'s line — the class predates this release and the fix is
  reported here, where it happened.

- **Zero telemetry, pinned properly.** `examples/langgraph` pinned two of the
  four names LangSmith consults and said so in three places. It reads the first
  non-empty of `LANGSMITH_TRACING_V2`, `LANGCHAIN_TRACING_V2`,
  `LANGSMITH_TRACING`, `LANGCHAIN_TRACING` — and the one left unpinned was the
  *first* of them, so a single variable defeated both pins. All four are now set
  in both workflows, the claim is corrected wherever it shipped, and the test
  asserts four names in two files rather than two names in one.

  The sharper half: this suite runs every example's whole cycle on each push
  through a subprocess that **inherited the ambient environment**, and two
  examples import `langsmith` transitively. Anyone who uses LangSmith has a
  tracing variable and a key exported, so digline's own tests could ship runs to
  a third party from a developer's machine — pins in two CI jobs, and neither
  was the job that runs on every push. The fixture now scrubs those names.
  Present since `examples/langchain`, not new here.

- **Fixed: an honest zero-call run can be re-judged.** A target that reports *the
  model called nothing* has measured something, and `ToolsCalled` scores it. The
  record collapsed that into *nobody reported*, so such a run scored `fail` when
  it was measured and was **refused** when it was replayed — with a sentence
  saying the target reported none, which was false of the run it described.
  `RecordedResponse.tool_calls` is now `tuple | None`: absent where nothing was
  reported, `[]` where zero calls were. Additive on read — `[]` is a shape
  0.12.0 never wrote — so no schema bump and no migration. ADR 0018 §1 carries a
  dated correction rather than a silent edit.

- **Fixed: a corrupt trajectory is refused by name.** A `tool_calls` holding
  anything but mappings raised `AttributeError`, which is not a `ValueError` and
  escaped the CLI's handlers as a traceback. The writer had always refused those
  shapes in a sentence; the reader does now too.

## 0.12.0 — 2026-09-13

**The agent under test.** digline **0.12.0** with **digline-mcp 0.1.2**: the
three provider plugins stay at 0.4.0 and `pytest-digline` at 0.1.3, neither
needing a floor move. `SCHEMA_VERSION` moves to **11** and `OUTPUT_VERSION`
stays 1 — every stored document has to be migrated, no `--json` shape breaks,
and **no baseline needs re-promoting**, because nothing here touches
`config_hash`.

**The trajectory is recorded, and a gate that silently was not one becomes
one.** `SCHEMA_VERSION` moves **10 → 11**, and the reason is not the feature it
looks like. A suite holding `tools_called` could never be re-judged: `Replay`
rebuilt a `Response` from the recorded answer, `RecordedResponse` had no field a
trajectory could live in, so the assertion read an empty mapping, took its
*nobody reported* branch and **errored**. That is precisely the failure ADR 0015
§1 named when it made `cost_usd` and `latency_ms` ride the record — same defect,
one door over, and nothing in the test suite paired the two to notice.

So `RecordedResponse` gains `tool_calls`: the tool, its arguments as canonical
JSON, what the tool returned, and whether it failed. It rides *there* rather
than anywhere else because that structure is already payload by construction —
`redact()` drops it whole, `digline.wire` does not know its name, and
`promote_baseline` strips it — so a tool argument, which is the end company's
data by construction, inherits every one of those sentences and adds no new
mechanism. Recording stays behind `record_responses`, still off by default.
`Replay` now hands the trajectory back, and a fifth refusal joins ADR 0015 §6's
four: a suite that judges a trajectory over a run that recorded none is refused
by name, before a judge is paid, rather than quietly erroring the check.

**`ToolCalledWith`**, the assertion ADR 0004 said would have to bring the
arguments with it. `ToolCalledWith(tool="lookup", arguments={"order_id": "4711"})`,
with `match="exact"` or `"subset"`. `ToolsCalled` is untouched and still owns the
order. Nothing the model sent reaches the verdict: the score metadata carries
`arguments_matched` and `arguments_expected`, both counts, so nothing has to be
declared and no reviewer has to notice that it should have been.

**`resumed_at` rides as the second passenger**, pre-vetted by ADR 0017 §11 and
waiting for a bump something else forced. Both passengers are checked against
ADR 0014 §1 in ADR 0018 §3, the migration `10 → 11` writes nothing, and
`_NON_ADDITIVE` gains no row.

**What it costs you, in order.** Every stored document must be migrated —
`digline migrate` per suite — and every example cap moved from `<0.12` to
`<0.13`. No baseline needs re-promoting: none of this touches `config_hash`. A
digline behind this one meets a schema 11 file and refuses it, correctly, saying
to upgrade rather than to migrate.

**Five lines the report has been missing.** A check whose measured band covers
its own threshold is now **named** — it passed or failed by which samples were
drawn, and a reader shown it as a clean pass has been told more than was
measured. It carries a `Headline` field and gates nothing; the exit codes do not
move. `explain` now **opens** with a judge that changed, before any number,
instead of mentioning it last under the counts it invalidates. A diff says at its
head how many differences sit inside both runs' intervals, so *no claim can be
made* about them arrives with the counts rather than after them. A `cost_budget`
that passes on the fold now says how many individual calls went over the cap and
what the worst one was. And a check that errored because its samples disagreed
says which three ways they went — two directions is disagreement, three is a
judge that is not measuring one thing, and `spread` prints the same figure for
both.

**A tenth example: an agent under the gate.** `examples/langgraph/` puts a
LangGraph agent with two tools under digline, judged on **what it did** — which
tools, in what order, with which arguments — rather than on what it wrote. The
tools execute for real and only the model is scripted, so no key and no network
are needed; `create_agent` is the current entry point, since
`langgraph.prebuilt.create_react_agent` is deprecated and goes away in v2. The
target records a projection rather than the message list, because LangGraph
mints `ToolMessage.id` as a uuid4 with no way to pin it and a baseline built on
one would churn every run. `langsmith` is a hard dependency of `langchain-core`
and the workflow pins its tracing off explicitly rather than trusting the
default.

**`digline-mcp` 0.1.2 moves onto the host composition, and gets the journal for
free.** The `run` tool called `execute()` and `write_run()` itself, which meant
journalling was wired in one front end and not the other — so a killed
MCP-launched run left nothing to finish while a killed CLI one left a journal.
It now sits on `host.prepare()` and `host.measure()`, the same pair the CLI
sits on, which is what ADR 0017 §11 said would happen in the release *after* the
one that built them: a floor cannot name a version that does not exist yet.

It gains **no `resume` verb**, and that is a decision rather than an omission —
resuming without the acknowledged call count would be a second way to spend
money, which is the one thing ADR 0011 §2 refuses. One consequence falls out
and is worth stating: with `resume=None` every refusal `prepare` carries lives
on a branch this never takes, so the error translation needs nothing added.
Its floor rises to `digline>=0.11.0` — raised by hand as well as held by the
gate, because a names-based gate cannot see a widened *field*, which is the
trap `pytest-digline`'s floor comment already records.

**A check that trips the agreement floor now records four numbers it used to
throw away.** Worth knowing if you diff run files: a verdict that errors because
its samples disagreed carries `samples`, `agreement`, `errored_samples` and
`scores` in its score metadata, where before it carried nothing at all. That is
what lets the reading say *which three ways* the samples went, and it is the one
check a reader most needs explained. All four are numbers, so all four cross a
boundary on their own merit. A suite that never trips the floor writes the bytes
it wrote before.

**A forged journal record is refused before the journal opens.** From 0.11.0's
delta-pass. `execute()` has always refused a `done` naming a case the suite does
not declare — it is an invariant of the driver — but on a resume that refusal
arrived *after* `open_journal`, so a journal holding a record for a case nobody
declared cost an empty leg file per attempt and answered in a `ValueError`.
`prepare()` now refuses it by name, with the journal exactly as it was and no
call made, which is what ADR 0017 §6 promises for every other input on that
list.

**The operator proves the wall each cycle.** `examples/operator/loop.py` used
to trust that `promote` is absent from its surface. Now it checks, before it
compares anything, with two operations under its own credentials. It calls
`promote` by name on the MCP server and expects *unknown tool*. Beside that, it
writes its own cycle file. Refusal alone proves nothing: an identity refused
everything is refused `promote` too.

The outcome uses digline's own trichotomy:

- **intact** is one log line;
- **collapsed** is any answer but *unknown tool*, a refusal included, because on
  that surface the wall is the absence. It opens a high-severity issue, and
  anything written under the baselines is rolled back before the comparison
  reads them;
- **inconclusive** is a different issue: the instrument is down.

`cycle.json` carries the probe, and `cycle_format` goes to 3. The two captured
alerts were regenerated with it: the same scores, new run keys, and a probe line
in layer 2.

The probe proves the wall only for the identity that ran it. The push probe a
deployment runs against its own protected branch is documented in `DESIGN.md`,
not exercised: an example has no protected remote. `AGENTS.md` and the skill
carry the rule in one line, and `test_agents.py` holds it word for word in both.
Nothing in `src/` or in `digline-mcp` moved. Its `promote` is still absent, and
no disabled one was added to test against.

**`docs/rejudge.md` says how to tell whether a run recorded its answers.** Look
at the data, because no field restates it. A case that recorded carries a
`responses` list with an `output` per sample. A redacted document keeps one
`{"withheld": true}` per sample, so the count survives. A run that recorded
nothing has no `responses` key.

**An errored sample counts against agreement, never for it.** This was found
while writing documentation the code refused to support. The documentation was
a table of what each `min_agreement` floor can catch, and the code would not
make its `3/5` row true.

Until now `error` could be the majority of a sampled check like any other
status. Four samples that could not judge beside one pass therefore met a floor
of `4/5`, and the check passed on the single vote that was judged. At `3/5`,
three errors beside one pass and one fail passed at a mean of 0.5. No ADR ever
decided that. ADR 0006 §12 now decides the opposite: only `pass` and `fail` can
be the majority, and an errored sample sits in the denominator and never in the
numerator. Those votes are now `error`, and the reason says which side an error
counts on.

A vote with no errored sample agrees exactly as it did, so no run without one
moves. That covers the classifier, the brief fixtures, and the 144-case scout
run of 2026-09-11. A stored run keeps what it recorded. The same answers folded
under this release are an `error`.

§13 is the table that started it, in the guide and in `as_agreement` too. At
five samples, `3/5` binds only when an errored sample splits the vote, `4/5`
binds on a genuine 3–2 split, and `5/5` is unanimity. Nothing is refused for
reaching too little, so a floor is chosen knowing its reach.

## 0.11.0 — 2026-09-11

**The journal.** digline **0.11.0**, alone: the three provider plugins stay at
0.4.0, `digline-mcp` at 0.1.1 and `pytest-digline` at 0.1.3. `SCHEMA_VERSION`
stays **10** and `OUTPUT_VERSION` stays 1 — no stored document moves, no
`--json` shape moves, **no baseline needs re-promoting**, and a completed run is
the file it has always been.

```sh
uv add --upgrade digline
```

### A killed run is finished, not paid for twice

A run is written once, at the end. A 144-case suite at five samples — 720 calls,
about four dollars — was killed mid-flight by a supervisor outside digline, and
everything went with it: seven hundred paid calls, a judged run that existed
only as objects in a process, and nothing on disk.

digline now keeps a **journal** beside the run as it goes. One record per case,
flushed and `fsync`ed before the next case starts, under
`.digline/<tenant>/runs/<suite>/.pending/<run key>.<leg>.jsonl` — the same
directory the runs live in, covered by the same generated `.gitignore`, holding
exactly what the finished run file would hold and nothing more. A suite that
does not record its answers does not journal them either. It is deleted the
moment the run file exists.

```sh
digline run --suite eval/suite.py --resume
# 112 of 144 cases × 5 samples = 560 calls to the target; 32 cases already judged
```

No key resumes the most recent unfinished run; `--resume KEY` names one. A plain
`digline run` never resumes and says on stderr that a journal is pending, so
paid calls are not abandoned by accident; `--resume` with nothing pending
refuses rather than quietly starting a full one.

Each leg is a file of its own, created with `O_CREAT|O_EXCL`. That is the whole
concurrency story and it needs no lock: a second process resuming the same run
is refused by name, and the process this feature exists for is one that was
*killed* — a lock it could not release would block the very rescue it was meant
to protect.

**A resumed run carries no marker, because there is nothing to mark.** It keeps
the `created_at` of the run it finishes, lands at that run's key, and is the
document the kill prevented — byte for byte, which is asserted rather than
hoped. What makes that legitimate is the refusal list: a resume stops, **before
the first call of the new leg**, when `config_hash`, the cases, the declared
artifacts, `target_config`, `judge_config`, `record_responses`, `git_commit` or
the digline version has moved. That list is not a collection of good ideas — it
is exactly the set of facts the run document asserts. Half a run under one
prompt and half under another is not a run.

**An alias that rolled between the halves errors instead of being averaged.**
What the provider said answered is journalled as it is learnt and given back to
the target and the judges on resume, so a model that changed across the seam
raises on the first call of the new leg exactly as it would have raised on the
next call of the old one: that case errors, the run is still written, and it
exits 2 and cannot be promoted (ADR 0005 §8).

**Errored cases are retried by default**, and that closes a second loss this
release was not opened for. A target that raises at sample 4 of 5 errors its
whole case — correctly, since a partly-sampled case would be a weaker
measurement wearing the declared suite's name — and an errored verdict exits 2
and cannot be promoted. So a 529 that outlived the SDK's own retries used to
cost the price of the whole suite. The rule in the driver is unchanged; what
changed is the remedy, which is now `--resume` re-paying for that one case.
`--keep-errors` keeps them as journalled.

For a script that drives digline: `digline.host.prepare()` decides what a launch
is and refuses a resume that would not be one, at no cost, before anything is
called; `digline.host.measure()` opens the journal, runs, writes the run and
deletes the journal. `execute()` gained `done=` and `on_case=` and still knows
nothing about the store. `digline run --json` gained `resumed` and `reused` —
facts about the launch, not about the run, which is why they are there and not
in the document.

The reasoning in full is
[ADR 0017](docs/adr/0017-the-journal-and-the-resumed-run.md).

**The MCP `run` tool does not journal yet.** Both front ends will sit on the
same host composition, but `digline-mcp` declares a floor — `digline>=…` — and a
floor cannot name a release that does not exist yet, so its call site moves in
the `digline-mcp` release that follows this one. It gains no `resume` verb
either way: that collides with its acknowledged call count rather than extending
it. A killed CLI run leaves a journal today; a killed MCP-launched one does not.

### The examples' cap moved, and the floor did not

Every example now reads `digline>=0.9,<0.12`. Nothing about the format required
it — schema 10 documents are read the same either side of this release, so the
floor stays where it was and no example migrates anything. What required it is
arithmetic: a lock regenerated against 0.11.0 cannot resolve under `<0.11`.

### Also

A redaction gate had a flake worth naming, since it is the kind that fires on a
release day and cannot be reproduced: a test asserting that `2500` had been
removed from a report read a `created_at` stamped by the real clock, and the
microseconds of `…T14:11:03.525004+00:00` contain those four digits. The
timestamps now come out of the haystack first; every digit the run did not stamp
is still asserted.

## 0.10.1 — 2026-09-11

**The delta-pass patch.** digline 0.10.1 and **`pytest-digline` 0.1.3**. The three
provider plugins stay at 0.4.0 and `digline-mcp` at 0.1.1. `SCHEMA_VERSION` stays
**10** and `OUTPUT_VERSION` stays 1: no stored document moves, no `--json` shape
moves, **no baseline needs re-promoting**.

```sh
uv add --upgrade digline
uv add --dev --upgrade pytest-digline
```

Both findings from 0.10.0's release delta-pass, closed the same day. The pass is
the standing rule: a release that adds surface gets an adversarial read **before**
any announcement, and 0.10.0 added the most sensitive surface this product has —
the model's own answers, recorded in a run file.

### Security: a document could rewrite the terminal reading it

**Found by the release delta-pass, before any announcement. No advisory**, by the
line `SECURITY.md` draws: an advisory is for a vulnerability that shipped with
real exposure, and a `Security` entry for one the process caught. Nothing here
crosses a privilege boundary, nothing is disclosed, and the **exit code — the
contract — was never affected.** What was affected is the sentence beside it.

Strings read out of a stored document reached a terminal unsanitised, so ANSI
escapes in them could erase the line being printed and forge one that reads as
digline's own output — *"digline: Nothing got worse."* — while the exit code said
`1`. Escape injection is precisely what defeats a reading, and a reading is what
a review of a committed baseline is.

**The class predates 0.10.0.** `digline list` has printed `environment` and
`git_commit` straight from the document since 0.1.x; 0.10.0 added
`digline_version` to the same class, in the installed-behind warning, which is
how the pass found it. So the fix is **at the sink and not on a field**: every
sentence the CLI prints now goes through `say()`, and every control character in
it is *shown* (`\x1b`, four printable characters) rather than obeyed. `emit()` is
the named exception for the two things that are documents rather than sentences —
`--json`, where `json.dumps` has already escaped everything, and the HTML report,
whose values are HTML-escaped where they are rendered. A test per sink, with the
forgery planted in a different field each time.

**`pytest-digline` had the same class and a shorter fuse**, which the pass only
established by trying it: the plugin prints `Verdict.reason` into pytest's report,
and a reason is *a judge quoting what a model answered*. No hostile document is
needed there — only an answer with `\x1b[2K\r` in it. Fixed the same way, with
the same function: `report.visible()` lives in `digline.report` because both front
ends need it and a front end may not import another one. That is why the plugin
moves to 0.1.3 with a floor of `digline>=0.10.1`.

What was checked and is **not** affected: every HTML surface, every `--json`
surface, the MCP responses, and the exit codes.

### Fixed: a recorded response's `kind` is validated where it is read

A forged `kind` — `"../../etc/passwd"` — parsed, and failed later inside
`restore_output` as a `JSONDecodeError` that the driver reported as an *errored*
case. Every sibling field in that document is checked on the way in; this one was
cast. It now refuses at load, naming the field and the three branches `Output`
has. Found by the same pass, and low: an error is neither green nor a regression,
so nothing was ever reported as passing.

## 0.10.0 — 2026-09-11

**The honest ledger.** digline 0.10.0 and **`pytest-digline` 0.1.2**. The three
provider plugins stay at 0.4.0 and `digline-mcp` at 0.1.1: nothing in them
changed and their floors already admit this core.

`SCHEMA_VERSION` moves to **10** — the first bump since 8 → 9, and the first one
with a written rule for what a bump may carry. `OUTPUT_VERSION` stays 1: three
keys join `compare --json`, and an added key leaves a consumer working.

```sh
uv add --upgrade digline
uv add --dev --upgrade pytest-digline
digline migrate --suite eval/suite.py       # first, before anything else
```

**Nothing needs re-promoting.** The migration invents nothing and `config_hash`
does not move — the nine baselines committed under `examples/` changed by exactly
one line each, which is what that promise looks like in a diff.

Three things the run document can now say that it could not before: which digline
wrote it, what the target actually answered, and which of its cases was watching
the model rather than measuring it.

- **Changed (storage):** `SCHEMA_VERSION` is **10**. A run document written by
  0.10.0 is refused by 0.9.0 and a 0.9.0 document is refused here, in both
  directions and by name, so `digline migrate` is the first thing to run after
  the upgrade — `AGENTS.md` §8's rule, unchanged. The step is **additive and
  writes nothing**: all three of the fields this version adds mean what their
  absence already means, so a migrated baseline keeps its `config_hash` byte for
  byte and **nothing needs re-promoting**. The nine committed example baselines
  moved by exactly one line each, which is what that promise looks like in a
  diff. New: [ADR 0014](docs/adr/0014-what-may-ride-a-schema-bump.md), the rule
  for what a future bump may carry — a field rides only if it leaves
  `config_hash` untouched, migrates without inventing, and does not widen what
  travels.

- **Added:** `Run.digline_version` — the document says what wrote it, beside the
  `schema_version` that says what shape it is. Stamped by the driver; empty
  means *not recorded*, which is what a migrated file honestly carries, and the
  migration never stamps its own version on a document it only rewrote. When a
  document turns out to have been written by a **newer** digline than the one
  reading it, the CLI says so on stderr and the wire carries the fact. It is
  never an exit code: the codes are a contract about the suite.

- **Added:** `promote_baseline` stamps **`promoted_at`** on the baseline it
  writes. `created_at` says when the run was *measured*; a promotion happens once
  somebody has read it, which is commonly days later — `AGENTS.md` §2 is an
  entire rule about not promoting the first green run — and until now the
  reference carried no time of its own. It is one field and deliberately not a
  ledger: a history of past promotions, and who made them, is a different
  decision with its own retention and boundary questions. Absent on a run, absent
  on a baseline promoted before this release, and never invented by the
  migration: a plausible date on a human signature is exactly what it must not
  write. The comparison's header names it beside the reference — *Reference
  approved* — and `get_baseline` carries it over MCP.

  **It is a `ResultStore` protocol change**: `promoted_at` is a mandatory
  keyword, passed in rather than read, because the store may not touch the clock
  — the rule `created_at` already follows — and a default would have made *not
  recorded* the ordinary outcome, which is the gap the field closes.

- **Fixed:** the view's promote button could return a 500 instead of a refusal
  screen. It caught three of the store's refusals and `ReplayedRunError` had
  joined them as the fourth, so promoting a re-judged run through the browser
  would have raised where the CLI says why. Found while stamping the promotion
  time through both front ends.

- **Fixed:** the listing's advice about documents it stepped over now matches
  the direction it found them in. It had been unconditionally *"run `digline
  migrate`"*, which pointed backwards is advice to do the one thing nothing can
  do — and could not be noticed until now, because until schema 10 no released
  digline had ever met a document from a newer one.

- **Added:** `Suite(record_responses=True)` records what the target answered —
  per case, per sample, beside the rendered prompt that produced it and what the
  call cost — and **`digline rejudge`** replays those answers through the current
  suite. A changed judge, rubric or threshold, measured at no cost to the target.
  Off by default, outside `config_hash`, and it is **not** a `Disclosure`: what
  crosses a boundary and what is written inside the perimeter are two decisions.
  The answers never travel — `redact()` drops them, `digline.wire` does not know
  the field's name, and `digline promote` strips them from the reference, because
  `baselines/` is committed. A re-judged run declares its source and **cannot be
  promoted**: a replay has no target variance, so its interval would freeze a
  noise floor measured without the noise — the fourth condition on promotion.
  Whole or nothing at 65 536 characters per field: a clipped answer re-judged
  produces a score that looks like every other score.
  [ADR 0015](docs/adr/0015-the-recorded-output-and-the-declared-re-judge.md),
  [`docs/rejudge.md`](docs/rejudge.md).

- **Added:** `Case(canary=True)` — a case that watches the model behind the alias
  instead of measuring quality. It is counted in **no** aggregate, and the
  exclusion is a figure in the verdict's metadata so a denominator stays
  reconcilable with the case file; it needs no label and may declare no group. If
  it moves **at all** — worse or better, since its score is a fingerprint rather
  than a quality — the headline says *the model under this alias likely changed*
  and the run exits `1`, on a fact of its own rather than on `worse`. A suite
  that declares one must sample at least twice: at one sample there is no noise
  to measure, and a canary that fires on a wobble is a canary its owner learns to
  ignore. Complementary to `resolved_model`, which is silent on the providers
  that name nothing. [ADR 0016](docs/adr/0016-the-canary-case.md).

- **Added (`pytest-digline` 0.1.2):** a canary that moved is a **FAILED** row,
  including one whose outcome is `improved` — the one place the per-row mapping
  cannot be read straight off `regressed`. Its floor rises to `digline>=0.10.0`,
  because it reads a field rather than an imported name and the floors gate
  tracks names.

- **Unchanged:** `OUTPUT_VERSION` stays `1`. `rejudged`, `canary_moved` and the
  per-delta `canary` are added keys, and an added key leaves a consumer working.
  `canary_moved` is the first addition that can change an exit code, and only for
  a suite that declares a canary — which no suite did before this release.

- **Changed:** CodeQL now runs the **default** suite instead of
  `security-and-quality`. The earlier entry below argued the wider set says
  more about a library; what it said in practice was 74 quality findings, 19 of
  them a single extractor limitation — PEP 695 `type` aliases named in
  `__all__` read as undefined exports. None of it was reachable by a fix,
  because the quality half is already gated by checks that fail the build:
  ruff (F401, F822) and pyright strict. A code-scanning list too long to read
  is one where a real alert arrives as noise, which is the opposite of what the
  scan is for. The suite is selected by *omitting* `queries:`, not by naming
  it: there is no pack called `security`, and asking for one by that name fails
  the run outright. The 74 are gone from the list, the 19 stand dismissed with
  their reason, and what remains open is one real advisory waiting upstream.
  `RELEASING.md` gains the step that only makes sense now that the list is
  short: before the tag, ask whether anything new has arrived since the last
  one.

- **Added (in the repository, not on the index):** `digline-openai` prices
  `gpt-6-astra`, read from the published
  list on 2026-09-11 along with every other entry, which is unchanged. The
  package stays at **0.4.0** and is not part of this tag, so the entry rides
  `digline-openai`'s next release: packaging and a price list do not earn a
  version of their own. Short
  context only, on the same terms as the GPT-5.6 entries: crossing 272K input
  tokens reprices the whole request and that meter is still not modeled here.
  Until this entry existed the model was refused at `preflight` rather than
  guessed at — the honest failure, and the one fixed decision 3 asks for. The
  price sentinel never knew the family had shipped and is not meant to: it
  guards the prices of entries the list already carries, and its docstring now
  says so, because watching a provider's catalogue would be a network call
  nobody configured (fixed decision 5).

- **Fixed:** `digline-mcp` and `pytest-digline` now ship `py.typed`. Both
  classified themselves `Typing :: Typed` and neither carried the marker PEP
  561 says makes it true, so a consumer importing either one from the wheel got
  `reportMissingTypeStubs` under pyright — and, with `useLibraryCodeForTypes`
  off, `Unknown` for every name it imported. `digline` itself and the three
  provider plugins were unaffected and are unchanged. Verified the way the
  defect had to be verified: in a scratch project against the built wheels,
  where the annotations this repository resolves from source are not on the
  path. `tests/test_packaging.py` now holds the classifier and the marker
  together, in both directions.

- **Fixed:** a target that returned no text now names the ending the provider
  declared, where the sentence used to come from the parser. An empty
  completion is still a legal *output* — the assertions get to fail it, and
  that is unchanged — but a suite that judges a *shape* parses the reply first,
  and a mute one died there as `JSONDecodeError: Expecting value: line 1 column
  1`, throwing away the `finish` the provider had reported one line earlier.
  `ProviderTarget` now reads that failure before letting it out: with nothing
  in the reply the case errors with the sentence 0.8.0 wrote for a judge —
  *"the target returned no text: the provider reported 'max_tokens' (512 of 512
  output tokens), so it was truncated before the first character — raise
  max_tokens"* — and the parser's own exception is kept underneath as its
  cause. The concrete case is an adaptive model that spends its whole budget
  thinking and ends at the cap with nothing written, which a token count cannot
  tell apart from a tool call.

  `JudgeBase._no_text` is the twin that already did this on the other side, and
  the two are **one implementation** now: `no_text_reason` builds both
  sentences, `said_something` is the check that sees past an assistant prefill
  for both, and a judge keeps one sentence of its own because it asked for a
  JSON object and a target asked for whatever the suite judges. All three
  published plugins inherit the reading — **nothing under `packages/`
  changed** — and a target that sends no token cap gets a sentence that claims
  none, rather than one about a cap nobody set.

- **Fixed:** a repeated check whose samples all errored now says *why* none of
  them could be judged. The fold replaced every sample's reason with *"no
  sample could be judged over 3 attempts"*, and that sentence was the whole of
  what reached the run file: the cause 0.8.0 taught a mute judge to report
  never survived sampling, so the one place a noisy judge is actually used —
  `Repeated`, and `Suite.samples` with it — was the one place its diagnosis was
  dropped.

  The summary stays, because it is true and it is what decides the status, and
  it now carries the cause under it: *"no sample could be judged over 3
  attempts: the judge returned no text: the provider reported 'max_tokens'
  (512 of 512 output tokens), so it was truncated before the first character —
  raise max_tokens"*. Where the samples died of different things the
  distribution is named rather than the dominant one — *"...for 2 different
  reasons — 2 of 3: …; 1 of 3: …"* — because a cause that appeared once is
  exactly the one worth seeing: the check is not flaky in one way, it is
  failing in two. The partial case, where some samples were judged, is
  untouched.

  **No document changed shape.** The wire and the report render whatever
  `reason` says, and what moved is what `reason` says. Worth knowing where it
  does *not* arrive: `digline explain` carries no reason by decision (ADR 0012
  §4), so an operator reading the fact list still sees *"could not be judged"*
  and finds the cause in the run file or in a complete report.

- **`examples/operator/`: `cycle.json` moves from format 1 to 2**, because the
  dossier now reads `digline explain --json`'s fact list instead of `compare
  --json full` — a forked loop writes format 2 on its next run and alerts
  already written are untouched, but the new `dossier.py` cannot re-render a
  format-1 cycle (the example's own captured alerts were regenerated through
  the new path).

- **The example reports were re-rendered** on the commit they name, against the
  migrated baselines, so `Code version` is a hash a reader can check out. Seven
  of the nine had been carrying `-dirty`. **Two still do, by design**, and the
  sentence beside the hash is the reason: `prompt-first`'s report is the
  comparison after a line was added to a prompt the example deliberately does not
  ship, and `classifier`'s is a narrated comparison at five samples — the README
  walks through the wobble that run recorded, and a fresh sampled run does not
  reproduce it. Re-rendering either would replace a document the prose explains
  with one it does not.

Everything below is the repository's own security posture — the supply chain
around the code, not the code. **No published package changes.** It is recorded
here because a reader checking how digline is built is entitled to the same
evidence as one checking what it does.

- **Security:** every workflow job now declares exactly the token it spends. A
  job-level `permissions:` **replaces** the top-level block rather than adding
  to it, so `publish.yml`'s two OIDC jobs had `contents` at none while running
  `actions/checkout`, and worked only because this repository is public. Both
  scopes are written out. The `site` job went the other way, to
  `permissions: {}`: it has no checkout and authenticates to another repository
  with a PAT, so it spends nothing from `GITHUB_TOKEN` — worth saying on the one
  job holding a credential that can write somewhere else.
- **Security:** every GitHub Action is pinned by commit SHA, with the tag in a
  comment beside it, and `docker/Dockerfile`'s base image is pinned by digest.
  A pin without an update tool is a freeze, so `.github/dependabot.yml` arrives
  with it and watches all four ecosystems — actions, the image, the `uv` locks,
  and the two Maven examples.
- **Security:** CodeQL runs on every push and pull request, and weekly, because
  the queries move even when the code does not. `security-and-quality`, not the
  default set: digline is a CLI with a written threat model, and the wider set
  is the one that says something useful about a library.
- **Added:** `scorecard.yml` — the weekly OpenSSF Scorecard run, SARIF to code
  scanning, results published so the number can be checked against its source
  rather than against a picture.
- **Added:** `SECURITY.md` says when a finding becomes a published advisory and
  when it is a changelog entry instead. The line is exposure: an advisory for a
  vulnerability that shipped, a `Security` entry for one our own process caught
  before it could reach anybody. The delta-pass rule is written down beside it.
- **Fixed:** the two `examples/langchain4j` services carried 63 known-vulnerable
  transitive dependencies between them — nothing in digline, nothing on PyPI,
  but a demo that ships those is a demo teaching the wrong thing. Spring Boot
  3.4.5 → 4.1.1 and Quarkus 3.20.1 → 3.39.3, both at **zero** advisories now,
  measured against OSV on the resolved runtime trees. The Quarkus service loses
  its `ChatLanguageModel`, which existed only because its extension lagged
  langchain4j's rename; the two services now read the same, and the README
  paragraph that explained the difference is gone.

## pytest-digline 0.1.1 — 2026-09-10

`pytest-digline` alone. digline stays at 0.9.0 and nothing else moves: this is
one package on its own version line, which is what the named tag shape exists
for.

```sh
uv add --dev --upgrade pytest-digline
```

- **The plugin no longer imports digline when no suite is named.** A `pytest11`
  entry point is loaded at pytest startup in **every** environment where the
  package is installed, including projects that never use digline — and
  importing the core at module level pulled 44 modules with it: the store, the
  driver, the report, the host, and `jsonschema` behind the assertions. A bare
  collection on an unrelated project measured **138 ms against 88 ms** without
  the plugin, which is 50 ms on a command people press hundreds of times a day,
  spent on a tool they are not using.

  The imports moved inside the four functions that reach for them, all of which
  run only once a suite has been named. A bare collection now imports **no**
  digline module at all and costs **8 ms**. Two tests hold it: one asserts that
  nothing named `digline` is in `sys.modules` after a bare run, and its guard
  asserts that naming a suite *does* load it — laziness that never loads is not
  laziness.

  Behaviour is unchanged in every other respect: same rows, same four states,
  same exit codes. ADR 0013 §8 said this plugin is inert when unconfigured, and
  it was inert in everything a reader could see; startup was not one of those
  things. Found by the 0.9.0 delta-pass, which is what the pass is for.

## 0.9.0 — 2026-09-10

**The adoption release.** digline 0.9.0 and **`pytest-digline` 0.1.0**, which
is new. The three provider plugins stay at 0.4.0 and `digline-mcp` at 0.1.1:
nothing in them changed and their floors already admit this.
`SCHEMA_VERSION` stays 9 and `OUTPUT_VERSION` stays 1 — no stored document
moves, no `--json` shape moves, and **no baseline needs re-promoting.**

```sh
uv add --upgrade digline
uv add --dev pytest-digline        # 0.1.0, new
```

Two front ends, and neither of them is a new way to decide anything. The engine,
the assertions, the comparison and the exit codes are unchanged; what this
release adds is two more places to meet them — the test report a Python team
already reads, and the pull request a reviewer is already looking at.

### `pytest-digline` — the comparison as rows in pytest

A pytest plugin that gates on the baseline committed in your repository, one row
per **check**:

```sh
pytest --digline-suite eval/suite.py
```

```
eval/suite.py::how-do-i-return::llm_rubric     FAILED
eval/suite.py::beta::contains                  PASSED
eval/suite.py::refund-status                   SKIPPED (the refund API is down, ticket 412)
```

- **One item per check** — one assertion on one case — because that is digline's
  own unit of verdict. A row per *case* would fold several verdicts together
  under a rule invented in a front end, and would have to choose which of a
  simultaneous regression and error to show.
- **Four states, and the fourth is the news.** Fine is a pass, worse is a
  `FAILED`, could-not-be-judged is an `ERROR` — pytest's error state, because
  an error is neither green nor a regression — and **a suspended case is a
  `SKIPPED` carrying the reason the suite declared.** That last one is a state
  the exit code cannot express: a suspension never fails, so on the CLI route it
  disappears into `0` and nothing in the number says the run was smaller than
  the suite.
- **It compares and does not run**, by default and by construction: two
  documents read off disk and a pure function, no provider call at all. pytest
  is a command people run on a keystroke. `--digline-run` opts into producing a
  run first, prints the planned call count before the first call, and **refuses
  under `--collect-only`** — a command whose job is to list test names must
  never be able to spend a hundred model calls.
- **There is no promote surface.** Not refused — *absent*, the way it is absent
  from `digline-mcp`, and a test in the package sweeps its own sources for the
  name so it stays that way. A green test run is the likeliest place in this
  product for a baseline to be promoted by accident.
- **It is inert until you name a suite**: no rows, no header, no output.
  Installing it changes nothing about a repository that has not asked for it.

**What pytest cannot carry, said out loud:** the process exit code. `digline
compare` exits `1` for a regression and `2` for a run it could not judge; a
pytest run exits `1` for either. The distinction survives in the report — `F`
and `E` are counted apart, `-rE` lists the errored rows, `--junit-xml` keeps
them separate — and a job that needs `1` versus `2` runs `digline compare`.

The reasoning is [ADR 0013](docs/adr/0013-the-pytest-plugin.md); the page is
[`docs/pytest.md`](docs/pytest.md).

### `digline/digline-action` — the gate on the pull request

A GitHub Action, in its own repository because the Marketplace requires one.
**Composite over the official image**, so the action's version and
`ghcr.io/digline/digline` are released together:

```yaml
- uses: digline/digline-action@v1
  with:
    suite: eval/suite.py
```

- It comments the comparison on the pull request as **`digline compare`'s own
  output, verbatim, in a fence** — not reassembled into a table, because the
  sentence a reviewer reads has to be the sentence the HTML report shows and the
  sentence the CLI prints.
- It **exits with digline's code**, unchanged: `0`, `1`, `2` reach
  `steps.<id>.outputs.exit-code`, so a later step can still tell a regression
  from a run nobody could judge.
- `image:` is an input, which is the point of the composite form. The official
  image contains the CLI and the three plugins and nothing else — no dynamic
  installs, ever — but `digline compare` loads your suite and your suite imports
  your application, so a suite with dependencies of its own derives the image
  and points the action at it. A docker action's image is a static string and
  could not have offered that.
- It comments on `1` and `2` always; `comment-on-success` is off by default,
  because a comment on every green pull request is what teaches a reviewer to
  scroll past them.

### Also in this release

- **`check_line` is public in `digline.report`.** The per-check sentence — *"dropped
  from 0.910000 to 0.640000, below its threshold of 0.700000, and beyond the
  0.880000–0.950000 this check measured across 5 samples"* — already filled the
  report's "what happened" column and `compare`'s summary lines; it was private,
  and `summary_lines` only ever emitted the whole list. Now a third front end
  can print the report's own line instead of composing a fourth rendering of one
  comparison. `summary_lines` is expressed over it, so they cannot drift.
- **digline's PyPI page gains its links.** The `[project.urls]` block — homepage,
  documentation, changelog, repository, issues — was added after 0.8.1 was
  already uploaded, and a package's metadata only reaches the index with an
  upload. This is that upload. The four plugin pages got theirs the same way and
  will show them on their next release.

## 0.8.1 — 2026-09-10

digline 0.8.1. One security fix, **found by the release delta-pass over 0.8.0's
own new surface, the same day** — hours after the tag and before the
announcement round. The three plugins stay at 0.4.0 and `digline-mcp` at 0.1.1:
the fix is in the core and every reader inherits it. `SCHEMA_VERSION` stays 9
and `OUTPUT_VERSION` stays 1.

```sh
uv add --upgrade digline
```

- **Security:** a redacted run from an **OpenAI-compatible endpoint** no longer
  carries the model id that endpoint reported. 0.8.0 recorded
  `resolved_model` — what the provider said answered — and let it travel in
  clear, on the ground that a model id is a public product name. That is true
  of `claude-sonnet-5-20260115` and false of what a customer's own vLLM,
  Ollama or gateway puts in the same field: `acme-legal-assistant-prod-eu-west-v3`
  is a project codename, an environment and a region, and it travelled beside a
  `base_url` withheld for describing exactly that.

  It arrives in the **same reply from the same server** as `fingerprint`, which
  0.8.0 withheld for precisely this reason — so the rule had been written once
  and applied to one of the two fields. It is now conditional on the fact
  redaction already holds: `resolved_model` travels in clear where no
  `base_url` was set, and is withheld — key recorded, value discarded,
  `compare()` answering `unknown` rather than `same` — where one was. **Inside
  the perimeter nothing changes**: an unredacted run records it whatever the
  endpoint, and the alias-rolled delta ADR 0005 §9 exists for still fires on a
  first-party endpoint, which was its motivating case. The *sent* `model` keeps
  travelling and is not affected: it is written in the suite, and the suite goes
  through a review. (ADR 0005 §9, amended)

  **One thing to know if you already have a redacted run from a compatible
  endpoint.** Such a document claims a perimeter it does not keep, so it is now
  **refused on read** rather than loaded — the same stance `run_from_json`
  takes on a schema it cannot be trusted to interpret. The message says which
  field is wrong and distinguishes the two readers: rebuild it with `redact()`
  if you hold the original, and ask the sender again if it arrived from
  elsewhere. Only runs written by 0.8.0, redacted, from an endpoint with a
  `base_url` are affected — a window of hours.

  No advisory was filed, and that is a judgement rather than an omission: a
  server-chosen name in a feature that had been public for hours is what a
  changelog line is for. The GHSA practice stays for shipped vulnerabilities
  with real exposure.

- The release runbook gains the standing rule the day earned: **a release that
  adds surface gets a delta-pass over that surface before the announcement
  round**, not after it.

## 0.8.0 — 2026-09-10

digline 0.8.0, and **`digline-anthropic`, `digline-openai` and
`digline-bedrock` 0.4.0** — the trio moves together because all three implement
the widened contract this release is about. `digline-mcp` stays at 0.1.1:
nothing in the server changed, and its floor already admitted this.

```sh
pip install digline                # 0.8.0
pip install digline-anthropic      # 0.4.0
pip install digline-openai         # 0.4.0
pip install digline-bedrock        # 0.4.0
```

The release is **the record**: what a provider hands back stops being a pair of
numbers and becomes a document of what happened. `_complete` widens from
`(text, Usage)` to a `Completion`, so the judge **reads** the cause of an empty
answer where the provider states one instead of inferring it from a token
count; `ToolsCalled` makes *how* an answer was produced assertable for the first
time, with an error — not a failure — when a provider contradicts itself; and
every run records which model actually answered, so an alias that rolled is a
named delta rather than an invisible one.

**Third-party plugins are unaffected, by construction.** The old
`(text, Usage)` pair is still accepted and always will be — the union is
permanent, not a deprecation window — so a plugin written against any previous
release keeps working untouched. That is why the floor moves only for the three
plugins in this workspace, which reach for the new names.

The observed identity is exactly as measured, and the sentence says so:
observed on Anthropic (`claude-haiku-4-5` → `claude-haiku-4-5-20251001`);
OpenAI carries the fields per SDK shape, unmeasured here; Bedrock returns no
model id, by its own service model.

**`SCHEMA_VERSION` stays 9 and `OUTPUT_VERSION` stays 1.** No document changes
shape, nothing migrates, and no baseline is re-promoted.

- **`_complete` returns a record — the oldest contract debt in the project.**
  A plugin's one method returned `(text, Usage)`, decided when the only question
  asked of a provider was what it said and what it cost. Since then `_no_text`
  has been *inferring* why a judge produced nothing — "likely truncated", "a
  non-text reply or a refusal" — from a token count against a cap, with a
  docstring naming the pair as the reason it could do no better. All three
  providers return the answer as a field.

  So it returns a `Completion`: `text` and `usage` as before, plus `finish` in
  one vocabulary across every provider, `finish_raw` (the provider's own word,
  uninterpreted), `tools`, and what the provider said answered. The judge's
  sentence now **reads** the cause where there is one, and falls back to today's
  inference — word for word — where the provider says nothing, which is the
  ordinary case on a compatible endpoint. A model cut off at the cap and one
  that answered with a tool call are identical to a token count and need
  opposite fixes; that is the case the widening is for. (ADR 0004 §6)

  **The old pair is still accepted and always will be.** A third-party plugin
  written against the previous contract keeps working, unchanged: the union is
  permanent rather than a deprecation window, because the pair is the honest
  return for a provider with nothing else to report. Every test double in this
  repository still returns it, which is how that is proved.

- **`ToolsCalled`.** The first assertion about *how* an answer was produced
  rather than what it says. An agent that was supposed to look something up and
  answered from memory produces a well-formed answer that happens to be
  invented, and every other assertion was blind to it.

  ```python
  ToolsCalled(expected=["search", "cite"])
  ```

  It **errors** rather than failing when the target reports no trajectory — a
  plain function, or a provider that names none — because "called nothing" would
  be a finding nobody established. It errors too when a provider contradicts
  itself, ending the turn on a tool call and then naming none, which is what a
  compatible endpoint emitting the call as text looks like. The call *count*
  crosses a boundary on its own merit; the tool *names* are strings and need a
  `Disclosure`, exactly as a model name does.

- **A run records which model actually answered.** `model="claude-sonnet-5"` is
  an alias, and an alias is a promise about a family rather than the name of a
  system: the provider decides which snapshot behind it answers, and rolls that
  decision without anyone touching the suite, the prompt or a parameter. Runs
  recorded the alias on Monday and the alias on Friday, `compare()` reported the
  configuration unchanged, and a drop between the two sent a reviewer to the
  prompt.

  `target_config` and `judge_config` now also carry `resolved_model` and, where
  a provider names one, `fingerprint` — **observed** rather than sent, so an
  alias that rolled is a named delta and the *"this drop coincides with…"*
  sentence fires beside the regression. Bedrock Converse returns no model id at
  all, and the record says so rather than echoing the request back. A model that
  rolls part way through a run errors that case, on the rule ADR 0005 §8 already
  set for an endpoint that answers on two systems; a rotated `fingerprint` goes
  absent instead, because a backend build changing does not mean a different
  model answered. `fingerprint` is withheld under redaction, joining `base_url`:
  on a custom endpoint its value is written by a server nobody here reviews.
  (ADR 0005 §9)

  A comparison against a baseline promoted before this says *"not reported for
  the reference"*, not *"not sent"* — nobody sent a resolved model id, on either
  side — in both locales. The existing sentences were not reworded.

  **`SCHEMA_VERSION` stays 9 and `OUTPUT_VERSION` stays 1.** A new key inside
  `target_config.values` is the same event as a plugin declaring a parameter it
  did not declare before: no document changes shape, nothing migrates, and no
  baseline is re-promoted.

  The judge's configuration is now read after the last case as well as before
  the first, so a judge whose alias rolled stops being the one instrument change
  ADR 0005 §4 could not see.

- **A ninth example: `examples/llamaindex`.** A LlamaIndex query engine — a real
  `VectorStoreIndex`, retriever, prompt template and `RetrieverQueryEngine` —
  queried in process, with **retrieval left running** rather than frozen. That
  is the difference from `examples/rag`, which freezes the passages and measures
  the generator: here each case declares the page that *ought* to answer it, so
  `Faithfulness` goes red when an answer is fluent, correctly cited and
  synthesised from the wrong page.

  Keyless like `examples/langchain`, and for a harder reason. LlamaIndex's own
  fakes cannot do it: `MockLLM` hands the prompt back verbatim, which would make
  every grounded-fact check pass on the question rather than the answer, and
  `MockEmbedding` returns one constant vector for every text, which is not
  retrieval at all. So the example ships a `CustomLLM` keyed on the retrieved
  page and a deterministic local embedding, and says plainly in its README what
  each one does not test. The dependency is `llama-index-core`, not the
  `llama-index` meta-package — no PyTorch, no model download, no key.

## 0.7.2 — 2026-09-10

digline 0.7.2. Two more path-and-secrecy fixes, **found by our own adversarial
pass over the four that shipped in 0.7.1** rather than by a report: we went back
and tried to break them, and two of the four turned out to hold a door open
somewhere else. `digline-mcp` stays at 0.1.1 — both fixes are in the core, and
the server reads through the same store, which is now pinned by a test that says
so. `SCHEMA_VERSION` stays 9 and `OUTPUT_VERSION` stays 1: no baseline is
re-promoted.

Each was reproduced before it was fixed and is pinned by a test that fails on
0.7.1.

```sh
uv add --upgrade digline
```

- **Security:** an endpoint error can no longer carry the credential somebody
  put in the URL. 0.7.1 reduced `HttpTarget`'s `url` to its host in every
  message **digline** writes; it did not cover the messages `urllib` writes, and
  urllib quotes the authority back. `https://svc:sk-live-…@gateway/answer` — a
  URL with userinfo and no explicit port — raised
  `http.client.InvalidURL: nonnumeric port: 'sk-live-…@gateway'` as an
  **unhandled traceback**, to stderr and in CI to a build log. Two reasons it
  got through: `InvalidURL` is an `HTTPException` and not an `OSError`, so
  `preflight`'s handler never saw it, and `__call__` had no handler at all. Both
  call sites now catch it, and the exception's own text is kept — "connection
  refused" is the whole diagnosis on the ordinary bad day — with the literal
  userinfo of *this* URL removed from it, which is exact rather than a guess.
  The `endpoint_host(url) or url` fallback is gone: a value with no host is
  refused when the target is built, because that fallback made the reduction
  conditional on the URL being well formed, which is the case where a mistyped
  secret is most likely. `endpoint_host` itself now answers `None` for a value
  that is not a host — it used to return the whole lowercased string, so a
  malformed `base_url` was recorded as a "host" with spaces in it.
- **Security:** a run or baseline that **links out of the store** is refused.
  0.7.1 checked the run key like the other two path segments, which closed
  `?run=../../../../elsewhere`. That proved the *name* was one safe segment; it
  could not prove where the name led. A symlink placed inside `.digline/` under
  a perfectly legal key — `planted-key.json -> ../../../../outside/evil.json` —
  passed every check, and `digline view` answered **200** with the outside
  document rendered, `digline compare --run` reported on it, and the MCP
  `get_run` returned it to an agent. Reads now verify where the path resolves,
  for runs and for baselines, and `scan_runs` counts a linked-out file
  unreadable rather than opening it. A `.digline` that is *itself* a symlink — a
  store on another volume — still works: both sides are resolved, so what is
  refused is leaving the store, not reaching it by a link.
- **Documented:** two decisions the pass made explicit rather than changed. A
  **race** between the check and the read is out of scope, and `SECURITY.md` now
  says so and why — the capability it needs, writing to the repository mid-run,
  is already the capability to edit `suite.py`, which is code; and a run records
  the key its artifact *actually resolved to*, so a race that wins still leaves
  its name in the record. And **a suite inside the root is trusted**: the MCP
  perimeter decides which file the agent may name, not what that file may then
  do, and [ADR 0011 §8](https://digline.dev/product/adr/0011-the-mcp-server/)
  now says that in as many words, so the next person to confirm it reads a
  decision rather than a miss.

## 0.7.1 — 2026-09-10

digline 0.7.1 and digline-mcp 0.1.1: a security pass, and nothing else. Four
findings from a review of digline's own surfaces — the tool mishandling what it
is given, which is what `SECURITY.md` says is in scope. None of them is a
vulnerability in a model you evaluate, and none needs a baseline re-promoted:
`SCHEMA_VERSION` stays 9 and `OUTPUT_VERSION` stays 1.

Each was reproduced before it was fixed and is pinned by a test that fails on
the old code.

```sh
uv add --upgrade digline digline-mcp
```

- **Security:** `digline-mcp` now checks that the `suite` a tool names is a file
  inside `--root`. It did not, and `load_suite` executes a `.py`, so every tool
  was a way to run a file from anywhere on the disk — including the five
  annotated `read_only_hint=True`, which is the annotation a client reads to
  decide it may call one without asking a person first. The check sits in the
  one function all six tools cross, and it is stricter than the loader: it also
  refuses the dotted-module form, which resolves through `sys.path` and so names
  something the server cannot place inside the repository at all. The CLI still
  takes that form — a person's tool has no perimeter to keep.
  ([ADR 0011 §8](https://digline.dev/product/adr/0011-the-mcp-server/), amended)
- **Security:** a run key is validated like the other two path segments. The
  store checked the tenant and the suite and took the key verbatim, and the key
  is the one segment that arrives from outside — `--run`, and `?run=` in the
  view's query string. `digline view` would answer
  `/compare?run=../../../../elsewhere` with a 200 and render a run document from
  outside `.digline/`. Bounded in practice: only files ending `.json` that parse
  as a run, and a run addressed through the wrong tenant was already refused. It
  is now a 400.
- **Security:** a suite that is **data** reads inside the repository, or it is
  refused. `artifacts = ["/etc/passwd"]` in a file with no Python in it read the
  file and recorded its contents in every run; `cases` and a `[target]`'s
  `prompt_file` could do the same. The code boundary was closed when the format
  shipped — no `python =`, no `import =`, no dotted path to a callable — and it
  held; the read boundary had never been drawn. It is drawn at the **perimeter**,
  the repository, and not at the suite file's directory: `eval/suite.toml`
  naming `../prompts/system.md` is reading its own project, and that is the
  layout the format is for. Outside it is a load error naming the field and the
  resolved path. A `suite.py` is unaffected — it is code, and code can already
  open anything.
  ([ADR 0007 §6](https://digline.dev/product/adr/0007-the-declarative-suite-format/),
  amended)
- **Security:** `HttpTarget` names its endpoint by **host** in every message it
  raises, never by URL. `url = "https://user:sk-secret@gateway/answer"` is a URL
  people write, and "nothing answered at …" carried it whole — to stderr, and in
  CI to a build log, which is often read more widely than the repository is. The
  reduction is the one `base_url` has had since 0.2.0; a target that took its
  endpoint under another name had simply never been looked at. The URL itself is
  untouched: only what is *said* about it changes.
- **Changed:** artifacts are keyed relative to the **perimeter** rather than to
  the suite file's directory. The old rule fell back to the bare filename for
  anything outside that directory, so a file from elsewhere was recorded under
  the same name a file in the project would have had. For a suite at the root of
  its project — every example in this repository, and the ordinary layout — the
  keys are byte-identical and nothing moves. A suite kept in a subdirectory will
  see its artifacts renamed once, from `system.md` to `prompts/system.md`: it
  shows in the report's artifact section and **does not fail a run**, since an
  artifact change has never affected the exit code.
- **Fixed:** `digline-mcp`'s `run` executes the suite module **once**. It loaded
  the file twice — once for the suite, once for the module the target is read
  from — so a suite that opens a connection or seeds a fixture at import time
  did it twice for one tool call, and the second load silently replaced the
  first. Not a security finding and it changes no output; it is the same defect
  underneath the check above, which is why it travels with it. The five reading
  tools always loaded once and are unchanged.

## 0.7.0 — 2026-09-09

digline 0.7.0, the second release today and a different kind from the first.
0.6.0 added surfaces; this one is **correctness and reading**: one rule for
every limit digline compares, and a command that reads a run back at length.
No new packages — the three provider plugins stay at 0.3.0 and `digline-mcp`
at 0.1.0 — no breaking change, and **nothing on disk moves**: `SCHEMA_VERSION`
stays 9 and `OUTPUT_VERSION` stays 1, so no baseline needs re-promoting and no
pipeline sees a byte change.

```sh
uv add --upgrade digline
```

- **Changed:** one rule for every limit — **every limit in digline is compared
  at `FLOAT_PRECISION`, and every limit is inclusive**. Thresholds, tolerances,
  the measured noise floor, budgets and `min_agreement` all read the numbers as
  the document stores them, so an edge case is decidable from the six decimals
  in front of you instead of from the residue underneath. In practice one
  comparison moves: a delta exactly at its declared tolerance is now
  `unchanged` (and `same` under `diff`) even where the subtraction left a
  remainder in the last bits. On the `brief` fixtures the run ADR 0006 was
  written about is still `unchanged`; what changed is which control says so,
  and its `reason` and `within_noise` name the declared tolerance rather than
  the measured floor. `digline.core` now exports `meets`, `within`,
  `at_precision` and `STORAGE_STEP` so an assertion of your own compares the
  way the built-in ones do. The reasoning is
  [ADR 0009](https://digline.dev/product/adr/0009-boundary-semantics/).
- **Added:** `digline explain` — the run read back at length. The report
  compresses; this expands: what ran, what moved and by how much, inside or
  outside which measured interval, what was set aside, what could not be
  judged, which of the three configurations differed. It compares when the
  suite has a baseline and reads the run alone when it does not, with no mode
  flag — whether a reference exists is a fact the store already knows. It gates
  like `report` (`0` fine, `1` worse, `2` unjudged) and can never exit `1`
  without a reference. `--json` emits the **fact list the prose is rendered
  from** — typed facts with case and assertion references, no sentences — so a
  terminal and a pipeline cannot drift into two descriptions of one run.
  `--locale en|it`, defaulting to `en`, and there is no `--out`: a reading
  written to a file would have a recipient who did not choose English.
  **It states and never advises**, and quotes no judge — no fact has a field a
  reason fits in, which is what makes that boundary something no later edit can
  open by accident. For the judge's words, `digline report` is one command
  away. ([`docs/explain.md`](https://digline.dev/product/explain/),
  [ADR 0012](https://digline.dev/product/adr/0012-the-reading/))
- **Added:** `examples/operator/` — the reference assembly for the **operator
  loop**: a suite watched on a schedule by an agent that re-runs within a
  stopping rule declared in a file, tells a draw from a drift from a structural
  flip, and opens an issue in your own repository when the answer deserves a
  decision. The alert is a document in three layers — the wire's facts, a
  deterministic dossier, and a judgment marked as the operator's opinion and
  never as digline's verdict — and only the third needs a key. `promote` is
  absent from the whole assembly, as it is from the MCP surface. Two real
  alerts ship with it: the drift that escalates and the draw that deliberately
  does not, both rebuilt from their committed cycle on every build.
  ([The operator loop](https://digline.dev/product/operator/))
- **Fixed:** a cost or latency budget **over its cap now fails**. Both budgets
  answered their own question twice — the word in the reason came from
  `measured <= cap`, the pass/fail came from the rounded score — and near the
  cap the two disagreed: a run 0.000002 USD over a 1.000000 USD cap passed
  while its own reason read `(over budget)`. Fixed decision 4 says a declared
  ceiling fails the run, and the document was contradicting the gate. There is
  now one comparison, so the sentence and the status cannot drift apart. Only
  overruns within about 2e-6 of the cap change verdict; anything already
  failing still fails, and a cost exactly at the cap still passes at `0.5`.
- **Fixed:** a `min_agreement` no float could spell. With three samples,
  `min_agreement=0.666667` was accepted at construction — the guard checks
  reachability at `FLOAT_PRECISION` — and then failed two-of-three with "did
  not agree: 0.67 of them share the majority verdict, below the required 0.67",
  a sentence that refutes itself. There was no float spelling of "two of three"
  that worked, and the resulting `error` is an outcome that cannot be promoted
  to a baseline. The guard and the gate now compare at the same precision.
  **Write the fraction anyway** — `"2/3"` says what it means, and it is the
  form that cannot be spelled wrong. `docs/api.md` says so, and its own
  `Repeated` example no longer shows `0.67`, which raises.
- **Fixed:** an artifact is refused by field name at the door.
  `Suite(artifacts=["prompt.md"])` — a `str` where a `Path` is meant — is
  coerced on construction instead of failing later and elsewhere, inside
  `read_artifacts`, with an `AttributeError` naming neither the suite nor the
  field. It is the rule the TOML loader already applied, moved to the one place
  both forms pass through; what cannot be a path is now refused by name, so
  `artifacts = [3]` in a data suite stops loading quietly as the path `3`.

## 0.6.0 — 2026-09-09

digline 0.6.0, and **`digline-mcp` 0.1.0**, the first new package this
workspace has published since `digline-bedrock`. The three provider plugins
stay at 0.3.0: nothing in this release changes what a plugin has to do.

```sh
pip install digline          # 0.6.0
pip install digline-mcp      # 0.1.0, the MCP server
```

The release has two halves. One is about **an agent**: `AGENTS.md` writes down
the judgment digline deliberately does not encode, and `digline-mcp` turns it
into a surface — six tools, read and measurement only, with `promote` absent
rather than refused. The other is about **you**: `digline diff` answers *"should
I switch?"* where `compare` answers *"did it get worse?"*, `by_group` splits an
aggregate by class so an average stops hiding one that is broken, and `digline
report` finally renders a run that has no baseline instead of sending its first
reader to a dead end.

**One breaking change**, and it is an import: `from digline.cli.loader import
load_suite` is now `from digline.host import load_suite`. Only code that loads a
suite programmatically is affected — writing a suite, and every CLI command, is
unchanged. The bullet below says what else moved with it.

Nothing in the stored documents moved. `SCHEMA_VERSION` stays at **9** and
`OUTPUT_VERSION` stays at **1**: no run needs migrating, no baseline needs
re-promoting, and a run recorded at 0.4.0 diffs against one recorded today with
no ceremony.

- **Added:** `AGENTS.md`, the operating layer digline deliberately does not
  encode. The tool refuses what is unsafe and reports what it measured;
  everything between those two — whether a red run is a regression or a
  wobble, which run deserves to become the reference, when to stop re-running
  and start reading — is judgment, and it stays with a person. Eight numbered
  rules, the first of them that an agent never runs `promote` on its own
  initiative: a baseline is an approved reference, not the most recent
  measurement. The same content ships as a Claude Code skill in
  `.claude/skills/operating-digline/`, and `tests/test_agents.py` fails if the
  two drift apart.
- **Added:** `digline-mcp`, the [MCP](https://modelcontextprotocol.io) server. A
  coding agent can read a digline result and measure a new one, and **cannot
  promote a baseline** — not because promotion is refused, but because there is
  no such tool. A refusal is a conversation an agent can argue with, retry, or
  decide is a bug; an absence is not. `migrate`, `view` and `report` are absent
  too: upgrade maintenance somebody chose the moment for, and two documents
  written for a person. Six tools, read and measurement only.
  ([ADR 0011](docs/adr/0011-the-mcp-server.md), and
  [`docs/mcp.md`](docs/mcp.md))
- **Added:** `run` takes a mandatory `acknowledge_calls` that must equal the
  suite's planned calls to the target. Called without it, the tool refuses **and
  hands back the number** — so the first call is the probe, and an agent cannot
  spend a hundred model calls without having stated the number. `AGENTS.md` §7
  as a contract rather than as advice.
- **Added:** the tool descriptions carry the playbook — the stopping rule on
  `run`, "promote the median, never the first green" on `list_runs`, "within
  noise explains, it does not excuse" on `compare`. A tool description reaches
  the model deciding whether to call the tool, which makes it the one place
  `AGENTS.md` reaches an agent that never read it. A test checks both
  directions, so a rule reworded in the file cannot leave a tool quoting one the
  project has stopped making.
- **Added:** `exit_code` on `compare --json`. It is the number `AGENTS.md` §6
  calls the contract, computed by the same function the process exits with — it
  is a field because the MCP server returns this same object and has no process
  to exit, and it is on both surfaces so the two cannot answer differently.
  `output_version` stays at **1**: added keys leave a consumer working.
  `digline diff` has no such field and must not.
- **Added:** `digline.wire`, the machine surface. Every `--json` the CLI prints
  and every response the server returns is built by one function, so two front
  ends cannot drift into two answers. `digline.cli` re-exports `OUTPUT_VERSION`
  and the exit codes, so `from digline.cli import EXIT_OK` is unchanged.
- **Changed, and breaking for anyone who followed the guide:** the suite loader
  moved out of the CLI. `from digline.cli.loader import load_suite` is now
  `from digline.host import load_suite`. `digline.cli` was two layers wearing
  one name — the host that reads the clock, asks git and imports your suite, and
  the terminal that parses arguments and prints. A second front end needs the
  first and not the second. `git_commit`, `utc_now_iso`, `load_target` and
  `read_artifacts` moved with it. (ADR 0011 §7)
- **Added:** `digline diff <run1> <run2>` — what differs between two runs,
  neither of them a baseline. It answers *"should I switch?"* where `compare`
  answers *"did it get worse?"*: prompt A against prompt B, one model against
  another, temperature 0.3 against 0.7. It is a **report and never a verdict**,
  so it **always exits 0** on a completed report — a verdict exists only
  against an approved reference, and neither side of a diff was approved by
  anybody. A separate command rather than a flag on `compare`, because the exit
  code is the contract and nobody should have to remember which mode they are
  in. (ADR 0008, and [`docs/diff.md`](docs/diff.md))
- **Added:** the report is **symmetric**. Swapping the two arguments swaps the
  columns and nothing else — the same checks, the same counts with the two
  "favour" figures exchanged, the same intervals. It carries no "reference", no
  "before" and "after", no "regressed" and "improved": none of those words is
  true of two runs neither of which was approved. Both locales, and `--json
  counts` / `--json full` with a symmetric structure and **no `worse` field** —
  the absence is the point.
- **Added:** where both sides were sampled, each row shows the two recorded
  min–max intervals, and the headline will say *"2 of `<run>`'s advantages
  exceed both runs' observed intervals"* — the strongest sentence two
  unapproved runs support. Where the intervals overlap the row says the two are
  not distinguishable by that check, as **evidence beside the count and never
  an excuse**: a diff has no baseline, so no interval has the standing to
  overrule a difference. Where nothing was measured on both sides the sentence
  is not printed at all, rather than printed as "0 of …".
- **Changed:** `digline view`'s compare screen now chooses. Against the
  **baseline** — including the default — it is still the verdict document;
  against **any other run** it is the diff report. Since 0.4.0 that screen
  rendered the verdict for every pair, which put two candidates under a heading
  asking "Did it get worse?" beside a column called "Reference". ADR 0008
  closes it in the release that states the principle.
- **Refused:** a diff needs both runs measured the same way. Different rules
  (`config_hash`) and different judges (the ADR 0005 identity set) are refused
  by name, with the remedy in the message — including the case where one side
  recorded a judge and the other recorded none, which cannot be established as
  a match. Crossing a tenant or a suite name raises, as it does in `compare`.
  The **target is free**, and that freedom is the feature.
- **Unchanged:** `SCHEMA_VERSION` stays at 9 and `OUTPUT_VERSION` stays at 1.
  No run needs migrating, no baseline needs re-promoting: everything `diff`
  reads has been in the document since 0.4.0. Two runs recorded before this
  release diff against each other with no ceremony.
- **Added:** `by_group=True` on an aggregate — precision and accuracy **per
  class**, beside the whole-run figure and never instead of it. A `Case` gains
  an optional `group` (so `cases.json` and a TOML suite carry it with nothing
  to learn), and every aggregate that asks expands into one instance per group
  present in the cases, named `precision[group=refunds]`. Thresholds, tolerance
  and the ADR 0006 §7 noise floor are inherited and computed over the group's
  cases: the same machinery on a smaller set, no new semantics anywhere. An
  aggregate over the whole run is an average, and an average carries a class
  that is broken. (ADR 0010)
- **Refused:** there is no `Precision(group="x")`. You get every class or none
  — the class that degrades is the one you were not watching, so watching the
  three you already suspect is watching your own assumptions. In a TOML suite
  `group` on an aggregate is an unknown parameter, and the message points at
  `by_group`. No weighting, no group hierarchies, no cross-group comparison:
  each is a different question, and the last one is a real one, deferred rather
  than declined.
- **Changed:** `digline view`'s run grid sorts its measure columns — whole-run
  figure first, then that family's groups alphabetically — instead of taking
  them in the order they arrived. Arrival order was the newest run's order, so
  a group only older runs carried landed last and the columns rearranged
  themselves as runs came and went.
- **Changed:** the report explains a combination it can now show often — a
  measure **below its threshold beside an answer of "no"**. `compare` gates on
  movement, so a class that failed in the reference too is `unchanged` and the
  pipeline stays green. Both facts are true, and the sentence is printed under
  the figures rather than left for a reader to mistake for a defect.
- **Changed:** the `classifier` example ships its third act, and **four of its
  twelve figures are red**: precision and accuracy for `travel` and for
  `tools`, at the bars it always declared. Every run agrees and every one of
  those intervals is zero-width, so the noise floor itself certifies the
  failure is real. Nothing was tuned to make the demo green — that would be the
  vacuously green assertion shipped as the thing people copy first.
- **Unchanged:** a suite that sets `by_group` nowhere is byte for byte the
  suite it was — same `config_hash`, same identities, same run file. That
  covers baselines promoted **before** this release: an aggregate's identity is
  what `compare()` pairs on, so neither `by_group` nor `group` enters it. Set
  the flag and `config_hash` does move, because the suite now declares more
  gates: comparable, and not promotable until you re-promote deliberately.
  `SCHEMA_VERSION` stays at 9 — an expanded aggregate is an ordinary verdict
  under an ordinary name — and no plugin needs a release.
- **Fixed:** an aggregate whose ratio sits on a rounding boundary raised
  `ValueError` instead of producing a verdict — 14 of 21 cases against a
  threshold of `0.666667` crashed the run's gate. The status was decided from
  the unrounded ratio while `Verdict` re-derives it from the score it stores at
  six decimals, so the two disagreed by one part in a million. Both numbers are
  now rounded before the comparison, as the per-case and sampled paths already
  were.
- **Fixed:** `Case(expected="")` is refused. An empty expectation scored a
  perfect 1.0 against an empty output — `levenshtein`'s both-empty branch and
  an optional `expected` are each defensible, and together they were a check
  that could not fail. Refused where the case is declared, so both entrances
  are covered: Python and `cases.json`. `expected=None` stays legal; absence is
  not emptiness.
- **Added:** `digline --version` prints the version and exits 0, with no
  subcommand.
- **Fixed:** `digline.__version__` said `0.4.0` while the release was `0.5.0`.
  It is now read from the installed distribution's metadata, so it cannot drift
  again, and a new gate holds every remaining hand-written version claim to
  `pyproject.toml`: each one is either pinned or registered as a record of a
  version that has already shipped. Bump the release and any claim nobody
  updated fails by file and line. Two sentences that named a version for no
  reason were reworded without one — a claim that cannot go stale beats a gated
  one — and the image's minor tag, documented as `0.4` since 0.5.0 shipped, is
  correct again.
- **Fixed:** an example could cap digline below a release able to read its own
  committed baseline. `uv sync` in an example installs the newest release the
  cap admits, and `run_from_json` refuses any schema but its own, so the wrong
  ceiling makes the example unrunnable by the only person it is for — it had
  already happened once, four baselines deep. It held by luck until now: schema
  9 arrived in 0.4.0 and the caps admit 0.4.0. `tests/test_example_caps.py`
  makes it hold by construction, with the schema each release wrote pinned from
  its tag, and a release cannot be cut without recording what it writes.
- **Changed:** the official image is built and smoke-tested on every change to
  it, not only by the workflow that publishes it. Same context, same quickstart,
  no registry — the smoke moved into `docker/smoke.sh` so the two workflows run
  one script rather than two copies. The job is gated on the paths that decide
  what the image is, because the Dockerfile installs from PyPI and a change
  under `src/` cannot change the image being built.
- **Fixed:** `digline report` no longer refuses a run that has no baseline. It
  used to say *"run it, look at the result, then promote"* while being the only
  way to look — a dead end whose first victim is always someone on their first
  run. It now renders the run on its own: the same header, aggregates, files
  under test and configuration, with the cases grouped by what each verdict
  **is** — met its threshold, did not, could not be judged, set aside — instead
  of by what it did against a reference it does not have. Where the verdict
  goes, the document states the fact rather than answering a question it cannot
  ask: *"No reference to compare against."* Both locales.

  No flag decides this, the way `--redacted` is not what makes a report
  redacted: complete or redacted follows from the run, comparative or not
  follows from whether a reference exists. It **never exits 1** — "worse" is a
  relation and there is nothing to be worse than — but a case the suite could
  not judge still exits 2, because that is a fact about the harness rather than
  about a reference. `digline compare` is unchanged and still refuses: a
  comparison needs a reference, a document does not.
- **Changed:** a judge that returns no text now says so. An empty completion is
  a legal *output* — the assertions get to fail it, and that is unchanged — but
  it is not a legal *judgment*: there is nothing to parse, so nothing was
  judged. The verdict was already `error`; what was wrong was the sentence,
  which reported that the reply held no JSON object and sent whoever read it
  looking for malformed JSON that was not there. It now names the fact first
  and the likely cause second, marked as the inference it is: *"output hit the
  max_tokens cap (512 of 512) — likely truncated before the first character"*
  against *"output well under the cap (7 of 512) — a non-text reply or a
  refusal"*. The two need different actions, and raising the cap fixes only one
  of them.

  The check sees past an assistant **prefill**, which is what makes it work for
  the provider most likely to be judging: Anthropic's judge opens the reply with
  `{` so the model's output is an object either way, and a model that produced
  nothing arrived as `"{"` rather than as `""`. No plugin changed and none needs
  a release. The provider's own `finish_reason` is still not reported — it does
  not reach this layer — so the cause is stated as a reading of the token
  counts and never as the provider's word.

## 0.5.0 — 2026-09-08

digline 0.5.0, with digline-anthropic, digline-openai and digline-bedrock at
0.3.0. The plugins move because they now register themselves, and their
`digline>=` floor moves with them: a plugin at 0.3.0 needs a core that has
`Provider`, and claiming otherwise would resolve for somebody and then fail on
import.

- **Added:** a suite can be **TOML**. `digline run --suite eval/suite.toml`
  reads `[suite]`, an ordered `[[assertions]]` list with the check named by
  `type`, and a `[target]` that is either an HTTP endpoint or a provider. The
  extension chooses the format; there is no new flag. Cases are always a
  separate file, because a rule and a case change at different rhythms and a
  diff has to say which one moved. The loader builds the same objects the
  Python form builds — the same assertion identities and the same
  `config_hash` — so a suite can be ported between the two forms **without
  re-promoting its baseline**. (ADR 0007, and
  [`docs/declarative.md`](https://digline.dev/product/declarative/))
- **Added:** providers are found through **entry points**. Each plugin
  registers its name under `digline.providers`, and a suite names a judge or a
  target by coordinate — `judge = "anthropic/claude-haiku-4-5"`, which is the
  same `provider/model` identity a run already records. Resolution is by name
  and never by import: nothing shipped with digline imports a plugin, and
  resolving one provider does not load the others. Fixed decision 6 in
  `CLAUDE.md` has said this since the first commit; this is the release where
  it is true. (ADR 0007 §3)
- **Added:** `HttpTarget(body=…)`, a table shaped like the payload whose
  leaves name case fields — `question = "case.vars.question"`. One level of
  reference and no expressions, so the nesting, the arrays and the types of a
  real body survive. Additive: `request=` is untouched and remains what a body
  that has to be *computed* is written with. A reference that names no case
  field is refused when the suite loads, not once per case half way through a
  run.
- **Added:** `examples/quickstart-toml/` — the two-file suite against a local
  stub, with no Python in it and no key anywhere. The stub reports `config`
  like a real service, so the example shows the sentence that says the answer
  got worse while the model did not change.
- **Changed:** what a TOML suite cannot express, it refuses **by name**. An
  unknown key is a load error with the near miss when there is one — a
  silently dropped `treshold` would be a check running on the default that
  passes — and a custom judge, a computed body, a custom assertion or a
  `disclosure` gets a sentence saying which wall it is and where to go. A
  credential is refused outright: there is no `api_key` in this format, and
  each provider's SDK reads the key from the environment.
- **Note:** `disclosure` is not settable from a data file, deliberately. What
  it widens is what leaves a perimeter, and a suite that is data cannot widen
  it — in world 3 that is a security property, not a missing feature. A suite
  that genuinely needs to disclose more is a `suite.py`.
- **Added:** an **official container image**, `ghcr.io/digline/digline`, with
  the three plugins already in it. `docker run -v $PWD:/work
  ghcr.io/digline/digline:0.5.0 compare --suite eval/suite.py` runs the whole
  cycle with no Python installation, which is what a CI job that is not a
  Python job has to have. Tagged `:0.5.0`, `:0.5` and `:latest`, built on the
  release tag for `amd64` and `arm64`. The versions it carries are read out of
  `docker/Dockerfile` and gated against this workspace, so an image that lags a
  release fails the build instead of quietly running the version before it. It
  writes into the mounted repository, as the user who owns it and not as root —
  decision 2, checked on the filesystem before anything is pushed.
  ([`docker/README.md`](https://github.com/digline/digline/blob/main/docker/README.md))
- **Added:** a published security posture. `SECURITY.md` says that the
  supported version is the latest release and nothing else, points reports at
  GitHub's private vulnerability reporting, and states the scope: jailbreak and
  prompt injection **of the models under test** are what digline measures, not
  a vulnerability in digline. There is no bounty; there is a fast reply.
- **Note:** ADR 0008 records the **two-run report** — the decision, not the
  command. `digline diff` is not in this release; the ADR is here because the
  design was settled in this cycle and the format it fixes is the one the next
  release will implement. ([ADR 0008](https://digline.dev/product/adr/0008-the-two-run-report/))
- **Unchanged:** `SCHEMA_VERSION` stays at 9. No baseline needs re-promoting,
  no run needs migrating, and no example was re-recorded: nothing downstream
  can tell how a `Suite` was built, which is the point.

## 0.4.0 — 2026-09-02

digline 0.4.0. The plugins stay at 0.2.0: a sample is taken by the driver,
which calls a target the same way it always did, so nothing in this release
changes a protocol they implement.

- **Added:** a **noise floor**. A sampled check now records the raw per-sample
  scores and the interval they span, and `compare` reads the *baseline's*
  interval: a movement that lands inside it is `unchanged`, with
  `within_noise` on the delta and a sentence saying so in the report and in
  `--json`. Nothing rescues a flip, an interval of zero width is not a floor,
  and a baseline with no interval keeps the absolute rule. Two controls now
  exist and the reason says which one spoke: `tolerance` is *declared* — what a
  reviewer allows — and this one is *measured*. (ADR 0006)
- **Added:** aggregates get an interval of their own. Precision and accuracy are
  computed once per run and so have no samples, but the noise they need sizing
  against is real — one case in twenty-one moving and coming back was what
  prompted the ADR. The driver evaluates each aggregate once more per sample
  index and records those N values. No call to a target, no call to a judge, and
  the recorded score is unchanged. (ADR 0006 §7)
- **Added:** `digline run` announces the multiplied call count on stderr before
  the first call — `20 cases × 5 samples = 100 calls to the target`. Arithmetic
  over the declared suite; a suspended case is not counted, and a `Repeated` is
  named with its own factor. A money estimate is deferred to an ADR of its own:
  it would need a new optional method on every target. (ADR 0006 §8)
- **Changed:** `SCHEMA_VERSION` 8 → 9, additively. **No baseline needs
  re-promoting and no example was re-recorded**: the score is still the mean, so
  every stored number is the one this release computes, and the migration
  *derives* the new fields from the `metadata["scores"]` a sampled run already
  carried. A run at `samples=1` gains only the version number. Run
  `digline migrate` after upgrading — a stored run at schema 8 is skipped by a
  scan and refused by name until you do. Aggregate intervals are the one thing
  migration cannot supply; they arrive with your next promotion.
- **Added:** `examples/langchain/` — a LangChain pipeline evaluated in process:
  the target is a function that invokes the chain, so there is no server and no
  HTTP. The default path runs on LangChain's own `FakeListChatModel`, which is
  what CI runs — no key, no network — and `DIGLINE_LIVE=1` puts a real model
  under the chain and `AnthropicJudge` behind the rubric. Tested against
  langchain 1.3.18.
- **Added:** `ci.yml` builds the digline.dev site on every push — the site's own
  config and its own sync script, `mkdocs build --strict` — so a relative link
  in an example README, or an example with no entry in the site's nav, fails on
  the pull request instead of in `publish.yml`, where the build runs *after*
  PyPI. `tests/test_examples.py` checks the nav entry too, and names the example
  and the line to add. Both are on the pre-tag checklist in `RELEASING.md`.
- **Note on 0.3.0:** the tag `v0.3.0` is the release that is on PyPI and needs
  nothing done to it, but the examples at that commit do not resolve — they
  still pinned `digline<0.2` while their baselines had moved to schema 8, and
  `examples/langchain4j/` was missing the `[tool.pyright]` block that keeps
  pyright out of the virtualenv. Three commits on `main` after the tag fixed
  both, along with the README links that failed the site build. If you are
  reading the examples, read them from `main`, not from the tag.

## 0.3.0 — 2026-09-01

digline 0.3.0. The plugins stay at 0.2.0: nothing in this release changes a
protocol they implement, and `config` is still the optional property it was.

- **Added:** `HttpTarget(config_path=…)`. An application digline cannot import
  can now say which model answered and how it was set up, in the same answer
  that already carries the cost — so a run from a Java or Go service is as
  complete a document as one from a plugin, and `compare` names a model change
  instead of reporting the configuration as unchanged (ADR 0005 §8). Left out,
  the target declares nothing, exactly as before.
- **Added:** `examples/langchain4j/` — a Spring Boot + LangChain4j service with
  one endpoint, the suite that evaluates it, and the CI gate. The walkthrough
  for a team whose application is not Python.
- **Fixed:** every example's CI workflow promoted the fresh run and *then*
  compared it, which compares a run with itself and passes whatever happened.
  They now compare against the baseline committed in the repository and key on
  the exit code. `prompt-first` and `rag` are shipped red on purpose, so theirs
  assert exit 1 — a green run there means the example stopped demonstrating
  what its README claims.
- **Fixed:** the four shipped example baselines were still schema 7 and could
  not be read by 0.2.0 at all — `compare` against them raised. Migrated in
  place. The workflow bug above is why nobody noticed.
- **Changed:** `execute()` asks a target for its `config` twice, before the
  first case and after the last, and records the second answer. A target that
  declares statically gives the same answer both times; nothing a plugin does
  changes.

## 0.2.0 — 2026-08-31

digline 0.2.0, digline-anthropic 0.2.0, digline-openai 0.2.0,
digline-bedrock 0.2.0. **Run files move to schema 8**, so stored runs and
baselines must be migrated once: `digline migrate --suite <your suite>` rewrites
them in place, and until it is run, `compare`, `report` and `promote` refuse a
schema-7 document rather than half-reading it. Migration is not a re-promotion —
the baseline keeps its key, its date and its scores, gains an empty
configuration, and compares as `unknown` against it.

- **Added:** a run records the configuration of the system under test —
  provider, model, token cap, temperature, region, endpoint host, and the shape
  the answer was asked for — as `target_config`, and the judge's as
  `judge_config` (ADR 0005). Not folded into `config_hash`: two runs at two
  temperatures stay comparable, which is the experiment.
- **Added:** `compare` names what moved instead of hashing it. The report, the
  terminal and `--json` say `temperature 0.3 → 0.7`, and where a regression
  lands in the same comparison the report says *"this drop coincides with
  temperature 0.3 → 0.7"* beside it.
- **Added:** a suite that grades with several judges records **which**
  instruments graded, one identity per distinct `provider/model`. Replacing one
  of two judges is reported as one removed and one added — and reported more
  strongly than a target change, because the scale moved rather than the thing
  measured.
- **Changed:** the headline no longer uses "configuration" for two different
  things. The first sentence is now **"The suite is unchanged from the
  reference."** — the rules — and "configuration" is left to mean how the
  system under test was set up. Both locales, the terminal, and `view`'s
  `OLDER SUITE` marker. A pipeline matching on the sentence rather than on
  `--json` needs updating.
- **Changed:** a plugin's `Target` and `Judge` now answer a `config` property.
  It is **optional**, like `preflight` and `artifacts`: a plain-function target
  and a hand-written fake judge keep working and simply record nothing.
- **Compatibility:** `SCHEMA_VERSION` 7 → 8, additive. A baseline with no
  recorded configuration compares as `unknown` rather than as a change.
  `OUTPUT_VERSION` is unchanged: `--json` only gained keys.
- **Privacy:** a model id and a decoding parameter travel in clear; `base_url`
  is recorded as a host and is withheld under redaction, exactly as an artifact
  is (ADR 0003 §4). No `Disclosure` releases it. `prefill` is not recorded —
  it is prompt, so it belongs to `Suite.artifacts` — and neither are
  `additional_request_fields`, `extra_body` or `token_param`.

## digline-bedrock 0.1.0 — 2026-08-28

Tag `digline-bedrock-v0.1.0`; nothing in the core changed.

- **Added:** `BedrockTarget`, `BedrockJudge` and `BedrockClaimJudge`, on the
  Converse API. The region is resolved at construction, not at the first call,
  so a missing one fails before anything is paid for; `bedrock_pricing(region)`
  is the price list for the region you actually called, and `free()` covers a
  model billed by provisioned capacity.
- **Added:** ARNs are scrubbed out of error messages — an account id does not
  belong in a `Verdict.reason` that ends up in a committed baseline.
- **Added:** the cache-read convention was verified against the live API:
  Converse reports cached input **outside** `inputTokens`, so it is added, not
  subtracted, when the cost is computed.

## 0.1.3 — 2026-08-28

Tag `v0.1.3`: digline 0.1.3, digline-anthropic 0.1.1, digline-openai 0.1.0.

- **Added:** `JudgeBase` in `digline.targets` is public API. A plugin now ships
  a target *and* a judge — `Target` + `Judge` + `ClaimJudge` — instead of the
  core owning a judge it cannot call (ADR 0004).
- **Added:** `digline-openai`, with `OpenAITarget`, `OpenAIJudge` and
  `OpenAIClaimJudge`. `base_url` points them at any OpenAI-compatible provider,
  and the JSON parser is lenient: `response_format` is an optimisation, so a
  provider that refuses it falls back to reading the object out of the reply.
- **Added:** `AnthropicJudge` and `AnthropicClaimJudge` in `digline-anthropic`.
- **Added:** a judge counts what it spends — `calls`, `spent_usd`, `latency_ms`
  — so the budget covers the judging, not only the answer under test.
- **Docs:** "Requires Python 3.12+" in the README and on each plugin's install
  page, where it is read before the install fails instead of after.

## 0.1.2 — 2026-08-27

- **Fixed:** a rubric score landing exactly on the threshold inside `Repeated`
  produced `error` instead of `pass`.
- **Changed:** every assertion that asks a judge now sends one prompt shape —
  instruction first, `Output to judge:` last and once, exported as
  `JUDGE_OUTPUT_LABEL`. `Faithfulness` used a different label and a trailing
  line; judges that parsed the old shape need updating.
- **Added:** `HttpTarget`, for an application digline cannot import.

## 0.1.1 — 2026-08-27

- **Changed:** `digline --help` describes the command instead of printing the
  module's docstring.

## 0.1.0 — 2026-08-26

- First release: the offline cycle — write a suite, run, promote, compare,
  report — with the baseline committed in your own repository.
