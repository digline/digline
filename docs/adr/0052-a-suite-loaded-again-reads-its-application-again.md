# ADR 0052 — A suite loaded again reads its application again

- Status: proposed 2026-10-17. The decision below was ruled on 2026-10-17,
  on #513, before this record was written. The text is not yet accepted, and
  nothing in it is implemented. #513 stays open: this record answers its
  question, and the issue closes when the code lands
- Shipped: unreleased
- Date: 2026-10-17
- Opens: **nothing on landing.** No code, no `SCHEMA_VERSION`, no
  `OUTPUT_VERSION`. The code that implements it opens an additive schema bump,
  with its step in `_STEPS`, for `modules_unchecked` on the run (*The field on
  the run*, below). The number is not written here: another branch may raise
  the version before that code lands
- Amends: the guarantee in the docstring of `digline/host/loader.py`, that
  *"everything that resolves in that directory"* is read *"through a finder
  scoped to it alone — because the application under test is what changes
  between two runs, and a stale copy of it hides the very regression the tool
  exists to find"*; and [ADR 0002](0002-three-worlds-and-where-the-data-lives.md)
  §9, *"What resolves inside the suite's directory is also read from source"*,
  which carries a dated note pointing here and is kept as written. No other
  public page promises it: a search of `README.md`, `AGENTS.md`, `docs/*.md`,
  the packages' READMEs and the plugin's pages, at `415f773`, found none
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §9 (the
  suite and what resolves in its directory are read from source, for a spec
  that is a path); [ADR 0029](0029-the-artifact-that-must-not-drift.md) §7 (an
  outcome that would go red on a healthy first comparison teaches that the
  feature is noise), §8 (a control that could not run is counted, not
  passed, and moves no number) and §9 (the run being judged declares)
- Touches: nothing in `CLAUDE.md`'s *fixed* section. `CLAUDE.md`'s fixed
  decision 3 — *no vacuously green assertion* — is the reason: a run measured
  on an application that is not the one on disk is a green nobody measured
- Number: 0052. Swept on 2026-10-17, before a line was written, across
  `origin/main` (`415f773`), every local and remote branch and tag (83 refs,
  after a fetch with `--prune`), the worktrees of this repository and the open
  pull requests (#586, open at the time of the sweep, which adds no record).
  The highest number taken anywhere is 0051

## Context

*digline#513.*

**The mechanism, read in the code at `415f773`.** `load_suite` compiles the
suite's own file from source into a new module every time it is called
(`_import`, `digline/host/loader.py`). The modules that file imports do not
go through that path. `import brief` goes through Python's own import, which
answers from `sys.modules` before it consults `sys.path` or any finder. The
finder that scopes the suite's directory to source is reached only for a name
that is not already in `sys.modules`. So within one process, the first load
of a name decides what every later load gets, whatever is on disk by then.

A process that loads one suite and exits does not meet this. `digline run`
is such a process. Three are not:

- `digline-mcp` serves many tool calls in one long-lived process, and each
  calls `load_suite` again (`opened`, `server.py:185`, `load_suite` at `:195`
  at `415f773`). The `run` tool calls the target (`:373`) and writes the run.
- `pytest-digline` loads every suite a session names, one after another, in
  pytest's process (`plugin.py:472`), and calls each target under
  `--digline-run` (`plugin.py:526`). Read in the code, not measured.
- Within one `digline` command, `--target <file>` loads a second file through
  the same `_import` (`loader.py`, `load_target`). Read in the code, not
  measured, and outside this record.

**Measured through the real server, at `415f773`, Python 3.13.11, macOS,**
`digline-mcp` started as `python -m digline_mcp --root <repo>` and driven over
stdio by the `mcp` client 2.2.0. Each suite recorded its responses
(`record_responses=True`), so the store holds what the target answered.

*(a) One suite, its application edited on disk between two `run` calls of one
session.* The suite's check was `Contains(needle="answer v1")`.

| step | what happened |
|---|---|
| `run` | the target answered `answer v1 to c1`; the run was promoted, with the CLI, in its own process |
| `brief.py` edited on disk to answer `answer v2` | |
| `run`, same session | the target answered **`answer v1 to c1`**, and the store recorded that answer, in a run that declares `git_commit = 1d811f4…-dirty`: the edited tree, which the target did not execute |
| `compare` through the server | **`exit_code 0`**, *"Nothing got worse compared with the reference."* |
| control: `digline run` then `digline compare`, each a fresh process, same disk | the target answered `answer v2 to c1`; **exit 1**, *"1 check got worse compared with the reference."* |

*(b) Two suites in one session, `one/` and `two/`, each importing a module
named `brief` from its own directory.* Each suite's check was
`Contains(needle="answer")`.

| step | what happened |
|---|---|
| `run one/suite.py` | the target answered `answer from one to c1` |
| `run two/suite.py`, same session | the target answered **`answer from one to c1`**, and `two`'s store recorded it: the answer of `one/brief.py` |
| control: `digline run --suite two/suite.py`, a fresh process | the target answered `answer from two to c1` |

**The green in (b) is the silent case, not the lucky one.** `Contains(needle=
"answer")` passes on both answers, so `two`'s run is green whichever
application answered it. With a needle that told the two apart, `two`'s check
would have failed on `one`'s answer: deduced from the check and the recorded
answer, not run. A suite whose checks cannot tell its application from
another's is the ordinary case, and there nothing at all shows.

*(c) Two suites in one session, where the second imports a name that exists
only in the first one's directory.* `first/` holds `helper.py`, which `first`'s
suite never imports, so it is never in `sys.modules`; `second/suite.py` imports
`helper`. Measured the same way, at `d8df3aa`, where `digline/host/loader.py`
is unchanged from `415f773`.

| step | what happened |
|---|---|
| `run first/suite.py` | the target answered `answer from first` |
| `run second/suite.py`, same session | the import **succeeded**: `second`'s target answered **`answer from first/helper.py`**, and `second`'s store recorded it |
| control: `run second/suite.py` alone, a fresh session | refused: *"could not import 'helper': No module named 'helper'"* |
| control: `digline run --suite second/suite.py`, a fresh process | the same refusal, **exit 64** |

Here it is `first/` left on `sys.path`, not `sys.modules`, that answered: an
import that fails on its own succeeded, and a refusal became a measurement.

**Not measured:** the reverse order in (b); an application that is a package
rather than one module; Python versions other than 3.13.11; `pytest-digline`
and `--target`.

**What `load_suite` changes in the process**, read in `digline/host/loader.py`
at `415f773`, and what this record decides for each:

| state | where | restored today | after this record |
|---|---|---|---|
| the suite's own module, `sys.modules["_digline_suite_<stem>"]` | `:170`, `:214` | never; the next suite with the same file name replaces it | removed |
| every module the suite imports that resolves in its directory, in `sys.modules` | Python's import | never | removed |
| the suite's directory, at the front of `sys.path` | `:206` | never | removed |
| a path hook for that directory, at the front of `sys.path_hooks` | `:134` | never | removed |
| a finder for that directory, in `sys.path_importer_cache` | `:137` | never | removed |
| the directory, in the module-level set `_scoped` | `:104`, `:126` | never | removed |

A spec that is a dotted module (`package.module:attr`) goes through
`importlib.import_module` (`:258`): it is outside the scope ADR 0002 §9 draws,
and outside this record.

## The decision

*Ruled 2026-10-17.* Two facts, a rule for where the second is read, and two
costs declared.

1. **What digline put in place for a suite's scope is taken out before the
   next load.** The accounting is digline's: it keeps what it inserted while it
   loaded a suite, and before it loads a suite again in the same process it
   removes exactly that. Nothing it did not insert is touched: no name from the
   standard library or a third party, only what it put there for the suite's
   scope. That is every row of the table above:

   - **the modules the suite imported that resolved in its directory, and the
     suite's own module**, so that the next load reads them from disk;
   - **the directory on `sys.path`.** Left in place, it would sit behind the
     next suite's directory, and a name the next suite imports that exists
     only in the earlier suite's directory would be **found** there, where
     otherwise the import would have failed. That turns an error into a wrong
     measurement, the same class of defect as #513, and (c) measured it;
   - **the path hook, the importer cache entry and `_scoped`.** These are taken
     out for symmetry, not because they were found harmful. Each is keyed on
     one directory and holds no module, so today they do no harm; but that is
     true of today's code and would have to be checked again at every change,
     where taking out everything that was put in does not.

2. **A name already loaded from somewhere digline did not load it is named,
   not refused: `modules_unchecked`.** A name that would resolve inside the
   suite's scope and is already in `sys.modules` from an origin digline did not
   load stays as it is, and the run says so: the names and their count, on the
   wire and in the document, moving no number, in the form of
   `pinned_unchecked`.

   **Why it is named.** The authority is ADR 0029 §8: *"A control that quietly
   reports success when it could not run is worse than no control, because it
   produces the same green as a control that ran."* Reading from source is that
   control here. Where a name was loaded before digline could read it, the
   control did not run for that name, and a run that said nothing would read
   the same as one where it did.

   **The precedent for its form** is the comment attached to
   `Headline.pinned_unchecked`, `report/render.py:221-223` at `415f773`: *"a
   control that reports nothing when it could not run produces the same green
   as one that ran. So it is named in the sentence, on the wire and in the
   document"*. The two citations do different work: §8 is why it is said, the
   comment is how a fact of this kind is said.

   **Why it is not refused.** Under pytest, a test module and a suite that
   import the same application module is the normal arrangement, not a
   mistake: the tests import `brief` to test it, and the suite imports `brief`
   to evaluate it. A refusal there would arrive red on a healthy repository,
   on the first session that names a suite. That is ADR 0029 §7's argument
   against firing on `new`: the first comparison after a pin is added *"would
   go red on arrival, teaching the author that the feature is noise before it
   has ever caught anything."* digline cannot unload what it did not load
   without reaching into state that belongs to the process it runs in, so what
   it can do is say it.

3. **The rule: `modules_unchecked` is read in the comparison's headline too,
   from the run being judged only.** The comparison is where the exit code is
   read, and a verdict built on a measurement with a declared gap cannot be
   silent there: ADR 0029 §8, applied one level up. Only the judged run is
   read, as pins are read from the judged run alone (`core/compare.py:1812`
   at `415f773`, `pinned = set(run.pinned)`) and as ADR 0029 §9 rules that the
   run being judged declares. What is read is its count, **or the fact that
   its value is not recorded**, and that fact is said too (*Its price*, from
   its third paragraph). Neither moves a number, as `pinned_unchecked` moves
   none.

**The name.** `modules_unchecked` follows `pinned_unchecked`. Three candidates
were weighed, at `415f773`:

| candidate | follows | ruling |
|---|---|---|
| `modules_unchecked` | `pinned_unchecked`, `core/compare.py:422-423`: *"The pinned paths this comparison could not answer for"*; `report/render.py:206`: *"How many pinned paths this comparison could not answer for."* | **Chosen.** The same shape: a control that could not run, counted, moving no number. |
| `modules_unreconciled` | `unreconciled`, `report/render.py:280-282`: *"a run that does not reconcile does not know what it measured"* | Set aside: `unreconciled` moves the exit code, through the errored verdict each gap is (`render.py:283-284`), and this fact moves none. |
| `modules_echoed` | `target_echoed`, `report/render.py:242-248`: *"an absence disguised as a presence, stated and never diagnosed… It moves no exit code."* | Set aside: the module is there. It is not an absence disguised as a presence; it is a presence nobody read. |

## What does not change

- **A process that loads one suite.** `digline run`, and every other `digline`
  command, loads one suite and exits; nothing here changes what it measures.
- **The scope.** ADR 0002 §9's one directory, for a spec that is a path. A
  dotted spec, the standard library and third-party modules stay under the
  ordinary machinery.
- **Reading from source.** What is loaded again is still read through the
  scoped finder and the `SourceOnlyLoader`.

## The field on the run, checked against ADR 0014 §1

`modules_unchecked` is recorded on the run, so that a stored run's document
says it and a comparison can read it (decision 3). ADR 0014 §1 lets a field
ride a schema bump only if three conditions hold, *"checked in the ADR that
proposes the field, and the ADR says so in its own words"*. Here they are.

1. **It leaves `config_hash` untouched.** Two runs of one identical
   configuration can carry different values: one in a fresh `digline` process,
   where nothing was loaded before the suite, and one as the second call in a
   `digline-mcp` session, where something was. A field that varies while the
   configuration does not cannot be part of the configuration's identity
   without renaming stored runs, and unpromoting baselines, for a reason that
   is not a change of rule.

2. **It migrates additively, with the value *not recorded*.** A document
   written before this field records nothing about it, and the migration says
   exactly that. It is the rule two fields already follow, at `d8df3aa`:
   `Run.digline_version` (`core/run.py:1369`), where *"`""` means **not
   recorded** — a migrated file, a document built in a test — and is never read
   as version zero"* (`:1365-1366`); and `Run.usage` (`:1416`), where *"`None`
   is **not recorded**: a migrated document, a `Run` built by hand in a test, a
   library caller who built one directly. It is never read as zero, on the rule
   `digline_version = ""` already follows — a run measured last month consumed
   something, and nothing in its document can say what"* (`:1405-1408`).
   ADR 0014 §1 names the case among its examples: *"`{}` for a record nobody
   kept"*.

   **Zero is excluded.** Zero would state that the control ran for every
   module, in exactly the runs this record says cannot be known: the false
   green of ADR 0029 §8, written into a migration. An old run says *I do not
   know*, not *none*.

   **`_NON_ADDITIVE` was weighed and set aside.** A version listed there has no
   step, so every document older than it, every run and every baseline, stops
   being readable (`store/migrate.py:375-384`, `:410-419`), and what it costs
   whoever holds the store is a choice between staying behind and doing it all
   again.

   **The refusal inside a step is not needed either.** `store/migrate.py:330`
   refuses one document inside an additive step, because that document lacks
   something its reading requires. A document written before this field lacks
   nothing: it did not record it.

3. **It does not widen what travels.** The count and the names both cross, and
   `redact()` drops neither. The second fact is limited to names that would
   resolve inside the suite's scope, which is the perimeter from which
   artifact paths and pinned paths already cross: an artifact's path stays when
   its text is withheld (`wire/run.py:413-415` at `d8df3aa`: *"The path stays
   either way, and `withheld` says which absence it is"*, by ADR 0003), and a
   pinned path crosses after `redact()` (ADR 0029 §3, held by
   `test_a_run_document_carries_the_pin_across_the_boundary`). This is not a
   new kind of name at the boundary. It is decided here and not later because
   ADR 0014 §1 says why: *"There is no third answer, and 'we will decide at the
   boundary later' is the answer that ships the leak."*

## Its price

**A suite that counts on module state persisting between runs in one process
changes behaviour.** A module-level cache, a counter, a client opened at
import time: after the next load they start again, where they persisted
before. Inside `digline-mcp` and `pytest-digline` that is the point of the
change; a suite that relied on it was relying on the defect.

**Runs already in a store, measured by a long-lived process after an edit,
are suspect and cannot be told apart.** The `-dirty` marker does not separate
them: in (a) it was present and named a tree that was not executed, and in (b)
the provenance was correct, the suite was `two`'s, while the answer was
another application's. Nothing recorded in those runs says which application
answered. A baseline promoted from such a run carries the same doubt. This
record cannot repair them, and says so.

**A judged run can carry the value *not recorded*, and the headline says so.**
Every line number in this paragraph and the four after it is read at
`d8df3aa`. The reader does not migrate on its own: a document of an older schema is
refused (`core/run.py:3047-3051` at `d8df3aa`, `if version !=
SCHEMA_VERSION`). After a deliberate `digline migrate`, a run written before
the code that implements this record carries `modules_unchecked` as *not
recorded*, and it can be the judged run by every road: `digline compare --run`
with its key or with `latest` (`cli/main.py:135`, `host/resolve.py:98`); the
`compare` tool of `digline-mcp` (`server.py:266`, resolving at `:223`); and
`pytest-digline`, which always compares `latest` (`plugin.py:479`).

The rule: the headline says it, and it moves no number. The precedent for the
form is `fact.target_config.unknown` (`report/render.py:1390-1391`): *"The
configuration of the system under test is not recorded on both sides, so
whether it changed is not known."* (`report/text.py:334-337`).

The same precedent is silent in one case, and that silence does not apply
here. It rests on *"a sentence that reassures about a configuration nobody
recorded is one the reader learns to skip"* (`render.py:954-956`). This
sentence does not reassure. It warns, about runs this record declares suspect
and indistinguishable.

`usage` and `digline_version` are not counter-precedents. Neither puts the
ground of the verdict in doubt, and the freshness of the modules a run
measured does. An empty `digline_version` is read outside the headline, and
never into the exit code (`_warn_if_ahead`, `cli/main.py:223-237`).

What the sentence states is exact: that the value is not recorded, and so
that whether the application was read from source is not known. It does not
state that the run comes from before the correction. *Not recorded* also
covers a document built by hand in a test or by a library caller, as the
comment on `Run.usage` says (`core/run.py:1405-1408`). Its wording is measured
when the failing tests are written; what this record fixes is the fact and the
work the sentence has to do.

**Not covered here.**

- `--target <file>` within one `digline` command, which loads a second file
  through the same `_import`; and a dotted spec.
- **Promotion.** A baseline promoted from a run that declares
  `modules_unchecked` carries the same doubt as the run. This is coupled to
  the half of #483 about `promote`, which reads no comparison. A refusal at
  promotion would arrive red on the pytest layout this record calls normal,
  so this record does not add one.
