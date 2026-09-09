# Changelog

What changed for you, three lines a version. The reasoning lives in
[`docs/adr/`](docs/adr/); this says what to expect.

## Unreleased

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
- **Changed:** artifacts are keyed relative to the **perimeter** rather than to
  the suite file's directory. The old rule fell back to the bare filename for
  anything outside that directory, so a file from elsewhere was recorded under
  the same name a file in the project would have had. For a suite at the root of
  its project — every example in this repository, and the ordinary layout — the
  keys are byte-identical and nothing moves. A suite kept in a subdirectory will
  see its artifacts renamed once, from `system.md` to `prompts/system.md`: it
  shows in the report's artifact section and **does not fail a run**, since an
  artifact change has never affected the exit code.


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
