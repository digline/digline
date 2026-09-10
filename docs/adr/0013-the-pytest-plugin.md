# ADR 0013 — The pytest plugin (`pytest-digline`)

- Status: accepted — the text first, the implementation written against it on
  `pytest-plugin`, the way
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md),
  [ADR 0007](0007-the-declarative-suite-format.md),
  [ADR 0008](0008-the-two-run-report.md) and
  [ADR 0011](0011-the-mcp-server.md) were
- Date: 2026-09-10
- Assumes: [ADR 0001](0001-verdict-not-score.md) §1 (three states, and an error
  is neither green nor a regression);
  [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §8 (a baseline is an
  approved reference);
  [ADR 0006](0006-repeated-samples-and-the-noise-floor.md) §5 (the interval is
  the baseline's), §8 (the planned call count, announced before the first call);
  [ADR 0008](0008-the-two-run-report.md) §1–§2 (a verdict exists only against an
  approved reference; the exit code is the contract);
  [ADR 0011](0011-the-mcp-server.md) §1 (`promote` absent by construction), §3
  (a separate package importing digline as a library), §6–§7 (`wire/` and
  `host/`, and the gate that keeps a front end from importing another)
- Turns into surface: [`AGENTS.md`](../../AGENTS.md) §1 (the agent proposes, the
  human approves), §6 (the exit codes are the contract), §7 (say what a hunt
  will cost before starting it)
- Requires: digline **0.9.0**, for `report.check_line` (§6). This package ships
  with that release and never below it
- Touches: `CLAUDE.md`'s **Structure** section — a third front end joins `cli/`
  and `digline-mcp` at the top of the dependency chain, under the same rule.
  Nothing in the *fixed* section is amended: decisions 3, 6 and 8 are
  reaffirmed, and §3 below extends ADR 0011 §1's construction to a second
  front end rather than restating it

## Context

digline's gate is an exit code. `digline run` writes a run, `digline compare`
holds it against the committed baseline, and the process exits `0`, `1` or `2`.
That is the primary route, it is language-neutral, and nothing here replaces it.

What it is not is a route a Python team already has a habit for. A repository
with an LLM feature in it has a `tests/` directory, a CI job that says
`pytest -q`, and a developer whose muscle memory is `pytest -k thing --lf`. For
that reader the gate arrives as a second command, in a second place, reporting
in a second vocabulary — and the tool that measures their model's output is the
one thing in their build that does not show up in their test report.

So: a plugin that puts the comparison into pytest's own report, one row per
check. It is a **bridge, not a second engine.** Every number it shows was
computed by `digline.core`, every sentence it prints was rendered by
`digline.report`, and the run it reads was written by the same driver the CLI
uses. If any of that stops being true the plugin has become a fork of the
product with a nicer report, which is the failure this record exists to prevent.

There is a second hazard and it is about money. pytest is a command people run
on a keystroke, in a watcher, in a pre-commit hook, dozens of times an hour. A
plugin that called a provider on collection would turn `pytest --collect-only`
— a command whose entire purpose is to *list test names* — into a hundred model
calls. §2 makes that structurally impossible rather than merely discouraged.

## §1 — The unit is the check, and there are four states

**One pytest item per `AssertionDelta`**: one assertion, on one case. Run-scope
verdicts — precision, recall, the per-group aggregates of
[ADR 0010](0010-per-group-aggregates.md) — become items too, carrying no case
and saying so.

```
eval/suite.py::how-do-i-return::llm_rubric      FAILED
eval/suite.py::how-do-i-return::contains        .
eval/suite.py::<run>::precision                 .
eval/suite.py::refund-status                    SKIPPED
```

The check and not the case, because **the check is digline's own unit of
verdict**. `AssertionDelta` is one assertion on one case; `summary_lines` emits
one line per regressed or unjudged check; `compare` counts checks. A per-case
item would have to fold several verdicts into one, and the folding rule would be
invented here — in a front end, where no ADR governs it and no test in
`digline.core` can see it. Two front ends folding differently is the drift
`digline.wire` exists to prevent, arriving through the door marked "convenience".

It also loses a fact the trichotomy is built on. A single case can hold a
regression **and** an error at once. Per case, the item has to pick which one to
report, and picking hides the other — that is `exit_code()`'s precedence
problem, solved once for a process, re-created at every row of a table.

The states map onto pytest's own, and the fourth is the reason this mapping is
better than the exit code's:

| digline | pytest | why |
|---|---|---|
| fine | passed | — |
| worse | **FAILED** | a statement about behaviour that got worse |
| could not judge | **ERROR** | ADR 0001 §1: an error is neither green nor a regression, and pytest has a state for "this never ran" |
| suspended | **SKIPPED**, with the reason | a decision somebody made, not an outcome |

A suspension is the one digline state the exit code cannot express — it never
fails, so it disappears into `0` — and pytest has carried exactly that idea
since it was written. `SKIPPED [1] eval/suite.py::refund-status: the refund API
is down, ticket 412` shows the set-aside case, in its own state, with the
mandatory reason attached, where no reader can mistake it for a check that
passed.

**Which delta is which is not re-derived here.** "Unjudged" is *not*
`outcome == "errored"`: rule 1 of `compare()` classifies an absent counterpart
as `new` before rule 2 can call it `errored`, so a case added today that fails
on its first day is `new` and errored at once. `report._summarized()` already
holds the correct rule, and the plugin applies it per row in the same order
`exit_code()` applies it per run:

    d.outcome == "regressed"                              -> FAILED
    d.current is not None and d.current.status == "error" -> ERROR
    otherwise                                             -> passed

Regression is tested first, so a regression outranks an unjudged check here for
the reason it outranks one there: the louder fact has to be the one reported.
Note that `compare()` cannot in fact produce both — rule 2 classifies an errored
verdict before rule 3 can call it a regression — so the ordering is defensive.
It is written in that order anyway, because the day a rule changes upstream this
front end should agree with `exit_code()` by construction rather than by luck.

One counting consequence, stated because a reader will meet it. `Headline`
counts unjudged **cases**; these rows are **checks**. A case with two errored
checks reads as "1 case could not be judged" beside two `E`s. Both are right and
the documentation says so rather than leaving somebody to reconcile them.

## §2 — Compare-only by default; running is typed, announced, and impossible under `--collect-only`

Comparing costs nothing: two documents read off disk and a pure function.
Running costs money. So the default is the free half.

**Default:** compare the suite's latest stored run against its committed
baseline. No provider is called, nothing is written, and the invocation is
repeatable in a watcher. The pytest run is the *gate*; producing the run stays a
separate act — `digline run`, the image, the Action.

**Opt-in:** `--digline-run` runs the suite first and compares afterwards. Three
constraints on it, and the third is the one that matters:

1. it is a **command-line flag**, so the cost is visible in the line somebody
   typed and in the CI log that recorded it;
2. it prints `planned_calls(suite).sentence()` on stderr before the first call,
   which is AGENTS §7 and ADR 0006 §8 unchanged — the multiplication is the part
   that surprises people;
3. **under `--collect-only` it refuses**, with a message, rather than running.
   A command whose entire purpose is to list test names must never be able to
   spend a hundred model calls, and the refusal is a gate rather than a
   convention because the person who types `--co` after `--digline-run` is
   always doing it to find out what would happen.

A marker was the obvious alternative and is rejected in §10: a marker is per
test where the run is per suite, and a marker that spends money hides the cost
in a source file instead of in the command line.

`acknowledge_calls`, ADR 0011 §2's gate, is deliberately **not** copied here.
It exists because an agent typed nothing; a person who typed `--digline-run`
typed it. The stderr sentence stays mandatory either way.

When there is no stored run at all, collection fails with the host's own
sentence — *"no runs stored for suite 'support' in tenant 'northwind', so there
is no latest one. Run it first."* — because that is already the right answer,
in words this project already owns.

## §3 — No promote surface, absent by construction

There is no flag, no fixture, no marker and no ini option that promotes a
baseline. Not refused, not gated: **absent**, exactly as `promote` is absent
from the MCP server (ADR 0011 §1), and for the same reason. A refusal is a
conversation — it can be argued with, retried, worked around — and an absence is
not.

The construction is checked rather than asserted: an AST sweep over the
package's sources fails on any reference to `promote_baseline`, in the shape
`tests/test_layering.py` already uses to keep a front end from importing
another. A baseline is an approved reference (ADR 0002 §8) and `promote` writes
into `.digline/<tenant>/baselines/`, which is committed. Anything landing there
arrives in somebody's diff and must arrive because they put it there — and a
green pytest run is the single most likely place for a promotion to be
performed by accident, because "the tests pass" is the sentence people act on
without reading.

## §4 — The committed baseline is the only reference

The plugin has no thresholds of its own, no tolerances of its own, and no
configuration beyond **pointing at the suite**. Every bar it reports against was
declared in the suite and frozen in the baseline somebody promoted.

This is the line that separates digline from the pytest-native tools it will sit
beside. Where a threshold lives in the test file, the test file is the reference
and it moves when somebody edits it; here the reference is a document that was
approved, is versioned, and appears in a diff when it changes. A plugin that
grew a `--digline-threshold` would dissolve that in one flag, and it would
dissolve it in the place where it is least visible — a CI invocation line.

Fixed decision 3 applies unchanged and is worth restating in this context: no
vacuously green assertion. A plugin invoked with no suite collects nothing (§8),
and collecting nothing is pytest's exit code 5, not a pass.

## §5 — Discovery is naming, never convention

The plugin does **not** hook `pytest_collect_file` on files called `suite.py`,
and does not walk the tree looking for suites. `digline.host.loader`'s own
record settles it — *"it never goes looking: a file found by convention is a
file that runs by accident"* — and it settles it harder here than in the CLI: a
suite is a file that **executes**, and pytest is a tool that recursively visits
directories a user did not enumerate.

Two ways to name one, both explicit, the command line winning:

    pytest --digline-suite eval/suite.py            # repeatable
    [pytest] digline_suites = eval/suite.py         # an ini option, in pytest's own config

An ini option rather than a `[tool.digline]` block, because it is pytest
configuration: it lives where the rest of this project's pytest settings live,
the plugin owns it through `parser.addini`, and a reader who knows pytest knows
where to look. It is also the whole of the configuration §4 permits — *pointing
at the suite* — and it is what makes `pytest` with no arguments gate an
already-configured repository.

`--digline-root` names the perimeter and defaults to pytest's rootdir. It is
`--root` and it means what `--root` means.

**No fixture and no marker in this version.** The collector is the way in. A
fixture for folding a comparison into an existing test — `assert_no_regression`,
the shape a Python reader will expect from elsewhere — is a second way in, and
a second way in before anybody has asked for one is a surface invented ahead of
its use. When somebody asks, it is additive and this record gets an amendment.

## §6 — `check_line`: one rendering of the truth, promoted out of the report

A failing row has to say what moved, and the sentence that says it already
exists: `report.render._detail()` fills both the report's "what happened" column
and `compare`'s summary lines, which is why a terminal and a document cannot
describe one delta two ways. It is private, and `summary_lines()` emits only the
whole list, joined and truncated.

So `digline.report` gains one public function:

```python
def check_line(delta: AssertionDelta, *, locale: Locale, coincides: str = "") -> str
```

and `summary_lines()` is re-expressed over it. This is a **refactor, not a new
rendering**: the string is the one that was already being produced, given a name
so a third front end can ask for it instead of writing its own. The alternative
— the plugin composing its own sentence out of `delta.current.score`,
`delta.threshold` and the noise interval — is a fourth prose rendering of one
comparison with nothing binding it to the other three, and the first divergence
would be found by a user reading two descriptions of one regression.

It is dated in `tests/test_plugin_floors.py`'s `INTRODUCED` at **0.9.0**, which
sets this package's floor at `digline>=0.9.0`. Nothing else in the core moves.

The failure message is that line, the case and check that own it, and the
judge's own words:

```
digline: how-do-i-return · llm_rubric
         0.910 → 0.640 (threshold 0.700), outside the baseline's
         0.880–0.950 across 5 samples
         reason: signed=True, concise=False
```

and **no traceback**. There is no Python frame worth showing: the exception was
raised by this plugin, one line from where the message was composed, and a
stack trace through `_pytest/runner.py` tells a reader nothing about a rubric
score. That is not free, and the mechanic is recorded here because it is not
discoverable from the documentation: `Item.repr_failure` is consulted **only for
the `call` phase** (`_pytest/reports.py:_format_failed_longrepr`), so the ERROR
rows of §1 — which must be raised in `setup()` to be errors at all — would print
a full internal traceback. The plugin therefore also implements
`pytest_runtest_makereport` as a wrapper and replaces `report.longrepr` for its
own items. Both halves are needed; either alone leaves one of the two states
printing a stack trace.

**The headline sentence is printed once**, in `pytest_terminal_summary`, not
stamped on every failing row. It is a statement about the *run* — "3 checks got
worse, 1 case could not be judged, the rules are unchanged" — and forty copies
of one sentence is forty lines a reader learns to skip, taking the row detail
beside it. Same sentence as `compare`'s and the report's, from `headline()`,
because a gate and a document must never say two different things about one run.

## §7 — What pytest's exit code cannot carry, said out loud

AGENTS §6 calls the exit codes the contract: `0` proceed, `1` stop and report
what got worse, `2` stop, nothing downstream is meaningful. **pytest cannot
carry that distinction**, and pretending otherwise would be worse than losing
it. A pytest run with only errors exits `1`, exactly as a run with only failures
does; the process code says "something was not green" and nothing finer.

So the trichotomy survives where it can and the loss is documented where it
cannot:

- **in the report it survives** — `F` and `E` are different characters, they are
  counted separately, `-rE` lists the errored rows on their own, and every
  machine-readable pytest output (`--junit-xml`, `--report-log`) keeps failure
  and error apart;
- **in the process exit code it does not**, and a job that needs `1` versus `2`
  runs `digline compare`, which is one command away and is the contract.

Stating this is the whole of the section. A gate built on a distinction the
runner erases is a gate that will one day treat "could not be judged" as "got
worse" and act on it, and the person who built it will have had no way to know.

## §8 — Inert when no suite is named

Installing this package must change nothing about a repository that has not
asked for it. With no `--digline-suite` and no `digline_suites`, the plugin
collects nothing, prints nothing, adds no header line and registers no hooks
that do work.

This is not politeness, it is self-defence: `uv sync --all-packages` installs
every workspace member into this repository's own development environment, so
the `pytest11` entry point is **active for digline's own test suite**. The
inert-when-unconfigured rule is what stops a plugin under development from
changing the result of the gates that judge it, and it is the first test
written rather than the last.

## §9 — A separate package, and what it depends on

`packages/pytest-digline/`, a workspace member, importing digline as a library —
ADR 0011 §3's shape, for its reasons: a front end is not part of the core, and a
core that shipped a pytest integration would put pytest in the dependency tree
of everyone who does not use one.

- distribution `pytest-digline`, module **`pytest_digline`**. The module name is
  forced, not chosen: `.github/dist_manifest.py` derives the post-publish import
  check from the wheel name with `-` → `_`, so a package whose top-level module
  is named anything else is published and never verified — the failure that
  looks like success, arriving through the automation that removed the
  hardcoded list it replaced;
- entry point `[project.entry-points.pytest11]`, named `digline`, so
  `-p no:digline` is what a user types to switch it off;
- `digline>=0.9.0` (§6), `pytest>=8.0`, and **nothing else**. No provider SDK,
  no third-party helper. The floor on pytest is verified against a real 8.0
  environment rather than asserted, because a floor is a promise about a version
  that is not present — which is precisely what `test_plugin_floors.py` exists
  to stop us making on trust;
- no upper cap on pytest, unlike `digline-mcp`'s `mcp<3`. That cap records a
  rename that actually happened; pytest has not moved `pytest11` in a decade,
  and a cap here would fight the one dependency the user certainly already has;
- it imports `digline.host`, `digline.core` and `digline.report`, and **never
  `digline.cli`** — `tests/test_layering.py` already sweeps `packages/` for that
  and needs no amendment to cover it.

## §10 — Alternatives rejected

**One item per suite.** A single pass/fail/error for a whole comparison. This is
`digline compare` with a pytest-shaped wrapper around it: it adds a dependency
and a plugin and buys nothing the exit code does not already give, while
discarding the rows that are the only reason to cross the bridge. If the answer
is one character, the command that produces it should be the one that already
does.

**One item per case.** Rejected in §1: it invents a folding rule in a front end
and it hides one of two simultaneous states.

**A marker — `@pytest.mark.digline`.** Rejected in §2. The run is per suite and
a marker is per test; and a marker that spends money puts the cost in a source
file, where a reader of the CI log cannot see it and a person adding a case
cannot feel it.

**A fixture instead of a collector.** Deferred, not rejected — §5. The collector
gives `-k`, `--lf`, the node id and the four states for free; a fixture gives an
assertion inside a test somebody else wrote, and reaches none of them.

**Reading `compare --json` by subprocess.** Rejected: it would make the plugin a
consumer of the CLI's stdout, which is the coupling ADR 0011 §7 drew `wire/` and
`host/` to remove. The plugin imports the same functions the CLI imports.

**Promoting on green, behind a flag.** Rejected without qualification — §3, and
AGENTS §1 and §2 are the reasoning. The first green run is green partly on
merit and partly on luck, and a plugin that promoted on green would launder
exactly that run into the reference, on the invocation where nobody is reading.

**Rendering the failure line inside the plugin.** Rejected in §6: a fourth prose
rendering of one comparison, bound to the other three by nothing.

## §11 — Test plan

Beyond a failing case for every rule, which the conventions already require.
Driven by `pytester`, so each one is a real pytest run:

**Inert when unconfigured, first.** A pytest run with the plugin installed and
no suite named collects the same items, prints the same header and exits the
same code as one without it. This is §8 and it is the test that protects every
other test in this repository.

**`--collect-only` never calls a provider.** With `--digline-run` *and*
`--collect-only`, the invocation refuses and the target is never called — proved
with a target that fails the test if it is called at all, not by counting calls
after the fact. §2's third constraint.

**The four states, from one fixture comparison.** A suite whose comparison
carries a regression, an errored check, a suspended case and several fine ones
yields exactly one `F`, one `E`, one `S` and the rest passed — asserted through
`RunResult.assert_outcomes`, which distinguishes `failed` from `errors`.

**An error is never a regression.** A check that was passing and now cannot be
judged is one `ERROR` and no `FAILED`. Rule 2 of `compare()` runs before rule 3,
so a delta cannot be both `regressed` and errored and the ordering inside
`Check.setup()` is defensive rather than reachable — which is worth knowing
before somebody writes a test that cannot fail. This is the reachable half, and
it is the test to read first if the mapping is ever doubted.

**`new` and errored is unjudged.** A case added since the baseline whose check
errors is an `E`, not a pass — the trap `_summarized()` documents, checked here
because a per-row mapping is exactly where somebody would write
`outcome == "errored"` and be wrong.

**No traceback, in both states.** The failure text of the `F` row and of the `E`
row each contain `check_line`'s sentence and neither contains `_pytest` or
`Traceback`. The `E` half is the one that fails without the
`pytest_runtest_makereport` wrapper, and it is written so that removing the
wrapper turns it red.

**One headline, once.** The headline sentence appears exactly once in the
terminal output of a run with several failures, and it is byte-for-byte
`headline(...).sentence` for the same comparison.

**The line is the report's.** A row's message is byte-for-byte
`check_line(delta, locale=...)` for that delta, and the same delta's line inside
`summary_lines()` — the check that would catch §6's refactor growing a second
rendering.

**No promote surface.** The AST sweep of §3, plus a run that goes green leaving
the baseline file's digest unchanged.

**Exit codes, and the one that is lost.** A regressed-only run and an
errored-only run both exit `1` from pytest and are asserted to do so — the test
that records §7 as a known property rather than leaving it to be discovered.

## Consequences

**A third front end exists, and the rule that governs it is already written.**
`cli/`, `digline-mcp` and now `pytest-digline` sit at the top of the dependency
chain, import `host/`, `wire/` and `report/`, and import nothing of each
other's. `tests/test_layering.py` covers the newcomer without amendment, which
is the sign ADR 0011 §7 drew the layer in the right place.

**`report.check_line` is public and can never quietly change.** It is now on
three renderings' critical path, and the test that binds a row to a summary line
is what will notice.

**A repository can gate on digline without learning a second command**, and the
cost of that is one more package with a version line, a floor to keep honest and
a pending publisher to register. That trade is the whole of the adoption
release.

**Somebody will want to promote from pytest and will not be able to.** That is
§3, it is deliberate, and the message they get points at the command that does
it — which is a person's command, run by a person who read the comparison.

**The suspended state gets a home it never had.** The exit code cannot express a
set-aside case; pytest can, and does. It is the first thing this bridge carries
that the primary route cannot.
