# digline

Python-native evaluation engine for LLM output. Starting reference: promptfoo
(analysis in private/promptfoo-analysis.md). Not a clone: the decisions below
correct its structural mistakes and are not negotiable.

## Architectural decisions (fixed)

1. **One assertion engine, two drivers.** Assertions are pure functions
   `(EvaluatorInputs) -> Verdict` in `digline.core`, with no I/O, callable on
   their own (amended by ADR 0001: it used to be `(output, context) -> Score`).
   The offline driver (prompt × provider × test matrix) and the online one
   (stream of production responses) use the same code. If a change to the core
   makes an assertion callable only inside a runner, it is wrong.
2. **Per-project storage.** Everything lives in `.digline/<tenant>/` inside the
   user's repo: config and baselines versioned in git, run artifacts
   gitignored. Behind the `ResultStore` protocol, file-based implementation by
   default. Never a DB in the home directory, never global state on the machine.
   *Widened 2026-09-27 (ADR 0034 §1, amending ADR 0002 §6).* Where the cases
   are the end company's, the store lives **inside its perimeter**: cases,
   runs, recorded responses, the journal and the full reference, in the same
   `.digline/<tenant>/` layout and under the same key. The user's repository
   then commits the key and a **projection** of the reference. The reason above
   is unchanged: still no DB in the home directory and no global state. What
   moves is which perimeter the directory sits in.
   *Added to the list 2026-09-29 (ADR 0036 §2).* The same directory also holds
   the **name table**, under a reserved name. It is the one entry in the layout
   that is **not behind the `ResultStore` protocol** and not written by digline:
   the process that owns the table writes it, in a format of its own, and
   digline reserves the name, writes nothing under it, and reaches the table
   only through two callables it is handed. The table is never committed. The
   reason above is unchanged: the table is addressed by the tenant, not kept in
   a home directory or as global state.
3. **No vacuously green assertion.** Every assertion has a mandatory threshold
   or a default that can fail. A default of 0 that always passes is a bug.
4. **Cost and latency are budgets, not metrics.** A declared ceiling fails the
   run.
5. **Zero telemetry, zero phone-home.** No network call the user has not
   explicitly configured.
6. **Providers as plugins** (entry points), not vendored into the repo.
7. **The core must accept a single response**, not only a matrix: the reactive
   side (shadow path / in-path) is not decided yet, but must not be precluded.
8. **The tenant is the perimeter.** `Run.tenant` is mandatory and non-empty.
   `compare()` and `diff()` raise if the tenants differ, and a promotion is
   refused the same way through the `read_run` it begins with. The tenant is
   a directory in the layout — `.digline/<tenant>/` — so that **addressing** is
   enforced by the filesystem, not by a field inside a document: filing or
   reading one client's history as another's is a **refused mistake, not an
   impossible act**.
   *Corrected 2026-09-26, twice over. It said "the separation is enforced by the
   filesystem", which claimed access control digline does not provide — it never
   sets or inspects a mode, reads no uid, calls no `stat`, and one OS user reads
   every tenant. And it said `promote_baseline` raises: the refusal is real but
   it belongs to the `read_run` promotion calls first (ADR 0002 §8). Separating
   **access** is the operator's job (a repository per client, filesystem
   permissions, separate hosts), and the per-tenant directory is what makes those
   possible. The perimeter is enforced in the front ends and in the operations
   that pair two runs — `compare()`, `diff()`, replay, and promotion through
   `read_run` — never in the store's API, which takes a tenant as a string by
   design.
   `pytest-digline` combines suites into one session without comparing their
   tenants, and that crossing is **unruled**. (ADR 0002 §1)*
   **No sub-perimeter**: `Run.environment` (mandatory, no default) says where
   inside the perimeter the run happened, does not enter the layout, and
   `compare()` reports it without constraining — comparing staging against the
   production baseline is the pre-release check. (ADR 0002)
9. **The payload stays where it is born, the verdict travels.** These cross a
   boundary: name, `assertion_id`, status, score, threshold, tolerance, and the
   metadata *measured by an assertion*. These do not: the `reason` and any
   metadata not covered by a `Disclosure` declared in code. Redaction is a
   function on the value (`redact`), not a serializer option; in the document
   the payload fields are absent, not emptied, and `"redacted": true` declares
   it. (ADR 0002)
   *Added 2026-10-05 (ADR 0043).* The message of an exception raised by code
   digline did not write is payload too: the suite, the application it
   imports, a target, a library. Who wrote a message is read from the frame
   that raised it, through every wrap, never from its type. It reaches the
   person who ran the command and no other recipient.
   The **artifacts** a suite declares — the prompt is the thing under test — are
   recorded in every run and cross a boundary only under
   `Disclosure(artifacts=True)`: a prompt carries the end company's rules, so
   the prudent default holds here too. (ADR 0003)
   *Narrowed 2026-10-05 (ADR 0042).* The flag is necessary and no longer
   sufficient: the declared files cross only when they are inside the
   perimeter, and outside `.digline` and `.git`.
   *Narrowed 2026-09-27 (ADR 0034 §4, §5, §8).* A **projected** reference, the
   file committed when the store lives with the end company, carries less than
   the list above. The `case_id`, a verdict's name, a group label, a
   calibration band's check word, artifact paths and reported configuration
   keys and values become **tokens**, resolved only where the store is. Every
   field is classified, and an unclassified one is refused. The document
   declares the regime it was produced under, and that is verified, not
   believed. It is a narrowing, declared: nothing that *may* cross is forced to.
   The digests stay as they are. A green means *no string*, not *no content*,
   and no adversary is addressed by them, because the reference and the suite
   share a repository (ADR 0034 §12). That ruling holds only while no document
   that carries a digest can reach a place the suite does not.
   *Corrected 2026-10-02:* this sentence said "a reference" instead of "a
   document that carries a digest". The reason is where the digest's reader
   stands, and a reference is only one of these documents. A served
   projection, a page rendered from one that shows a comparison or a run key,
   a run file, the register, `compare --json` and an MCP response are others. This is the reading ruled
   on 2026-09-29, reaching the text. (ADR 0034 §12)
   *Added 2026-10-01 (ADR 0038).* A page served to the software house shows a
   **served projection**: a run, promoted or not, projected the same way. It
   carries what a projected reference carries, plus what a current run adds,
   which is a response count and digline's own vocabulary, never a name.
   *Added 2026-10-08 (ADR 0046).* A widening of what crosses is a class
   declared in reviewed code; a recorded act — a person, a reason, at a page —
   selects an instance within a declared class and is never a widening.

## Structure

    src/digline/core/       pure domain: Score, Verdict, assertions, protocols. No imports from other packages.
    src/digline/store/      ResultStore and its implementations (file-based, inside the repo)
    src/digline/targets/    prompt template, pricing, the ProviderTarget and JudgeBase bases.
                            No SDK, ever; real providers are separate packages under
                            packages/, and each one ships a Target *and* a Judge (ADR 0004)
    src/digline/run/        offline driver
    src/digline/report/     the document for world 3: pure functions, self-contained HTML, mandatory locale
    src/digline/wire/       the same facts for a program: OUTPUT_VERSION and the pure functions
                            that build every `--json` and every MCP response. One rendering of
                            the truth, so two front ends cannot drift. No I/O and no clock —
                            the constraints report/ is held to (ADR 0011 §6)
    src/digline/production/ [planned] production store, Postgres first, mandatory retention
    src/digline/bridge/     [planned] production → repo: mandatory anonymization, generated case_id
                            Corrected 2026-09-27: pseudonymisation, not anonymization.
                            - What is committed carries identifiers and no text, and identifies
                              nobody on its own.
                            - The mapping back to each case is held by the data owner, inside
                              its own perimeter.
                            - Anonymization cannot be met, because the input is what a judge
                              judges.
                            - Pseudonymised data is still personal data.
                            ADR 0002's Consequences has the correction and its reasons. ADR
                            0023, accepted 2026-10-06, no longer names the old requirement:
                            its Touches line says this line was corrected and does not wait
                            on it.
    src/digline/online/     production driver
    src/digline/host/       the layer that touches the world: the **only** one allowed to read
                            the clock and git, and the one that imports the user's suite and
                            reads the files it declares
                            (the *clock*, meaning wall time: `created_at` is passed in so a
                            run is reproducible. A **duration** is not a clock — it cannot
                            say what time it is — so `perf_counter` for `latency_ms` in a
                            target is allowed and is what fills `Response.latency_ms`.)
    src/digline/cli/        a front end: argparse, the printed output, the exit codes, and
                            nothing else. `digline-mcp` is a second front end over the same
                            host and the same wire, which is why **nothing imports this
                            package** (ADR 0011 §7)
    docs/                   public documentation: API reference, decisions (numbered ADRs)

Allowed dependencies: cli → host → targets → run/report/wire/bridge/online →
store/production → core. Never the other way round; nothing under `src/` ever
imports a plugin from `packages/`; and nothing under `src/` or `packages/`
imports `digline.cli`, which is a front end and therefore the top of the chain.
Tests are exempt from that last one by construction — they drive every layer.

Build order: offline driver → report → store and CLI. **Nothing online before
the report**: it is what world 3 sees, and it is the only one of the three
artifacts that today exists in none of the audited competitors.

## Conventions

- Python 3.12+, uv, ruff, pyright strict, pytest. Types everywhere, `Protocol`
  for abstractions, frozen dataclasses for values.
- **The whole repository is in English**: comments, docstrings, test and
  variable names, error messages and runtime strings (`Verdict.reason` ends up
  in the committed baseline, which is a public format), plus `docs/`, the ADRs
  and this file. Italian only in conversation and in `private/`, which is not
  committed.
  **The one declared exception: `digline/report/text.py`.** The report is not a
  runtime string, it is a document with a recipient who did not choose English.
  `TEXT` is the per-locale table; `render_html` and `headline` take a mandatory
  `locale` with no default, like `environment`. ISO dates and the decimal point
  are not localized: two reports of the same run must stay comparable line by
  line.
  In the CLI the distinction is between *document* and *terminal*:
  `report --locale` is mandatory, `compare --locale` defaults to `en` like every
  other terminal output. Consistency between the two sentences is guaranteed by
  `headline()`, not by the user.
- Every assertion has tests with at least one failing case.
- `tests/test_layering.py` is a **mandatory gate**, not a style test: it guarantees
  that the core stays pure and importable from Plumbline without dragging storage
  along. It must not be weakened or made optional; if it fails, the change is
  wrong, not the test.
- **A claim that cannot be sourced says so in the place it is made, never in a
  footnote and never nowhere.** The qualification travels with the sentence,
  because a reader who meets the claim and not the caveat has been told
  something stronger than we can support — and a reader who goes looking for the
  evidence and fails draws a worse conclusion than the one we could have handed
  them. Two instances, four minutes apart on 2026-09-22, on the two kinds of
  thing we write:
  [ADR 0024](docs/adr/0024-the-judge-as-an-instrument.md) §5.6 states the bound
  on what a replay can measure inside §5, beside the figure it qualifies, rather
  than leaving a reader to assume there is no bound; and the Handbook's chapter
  0 says, in the paragraph that describes the system it was written from, that
  the reading has no artefact behind it. The shape is the same on a
  measurement and on prose: name the limit where the claim is, and let it be
  read as a shape that recurs rather than as evidence.
- Every decision touching the "fixed" section requires an ADR in docs/adr/
  before the code.
- Small commits, message in English, imperative.
- **An issue is something to do; a record is something to know.** Before
  opening an issue, ask whether anybody will do something different for having
  read it. If yes, it is an issue. If it serves only whoever writes an ADR or
  picks the topic up again, it is a record in `private/`, or a line in a record
  that already exists.
  Two things made this plain on 2026-10-05. #448 was opened wrong and retitled
  22 seconds later: an issue opened that fast is also how issues that are not
  needed get opened. And #437 and #446 were opened and closed the same morning:
  they were not defects found, they were a to-do list passed through GitHub.
  That is allowed, **but say so when you do it**, in the issue itself, so they
  do not read as defects found.
  **Something found while working on something else goes into the report, not
  into an issue.** Name where you would put it — issue, record, or nothing —
  and the maintainer rules. Never open it on your own initiative from inside a
  report that is already doing something else.
- **A worktree audit reports; it never removes on its own judgement.** For each
  worktree give the path, the branch, whether that branch is merged into `main`,
  whether the tree is clean, and how many commits it is ahead — then let a person
  rule. The count grows past what anybody can hold in their head, and three
  incidents in the week of 2026-09-22 each needed a stale worktree to be
  indistinguishable from a live one: a session pushed onto another's branch, a
  reset was resolved against the wrong one, and a type gate reddened from a stale
  `.venv` with tracebacks naming a directory nobody was working in.

  **The case with teeth: a worktree on a detached HEAD whose commit is on no
  branch is reported and never removed by you.** Work on a branch is visible to
  anybody who lists branches; work on a detached HEAD is visible to nobody — so
  an audit that tidies worktrees destroys it *by doing exactly its job*. The
  guard is not "audit less", it is that this one case is always escalated. Before
  removing such a worktree once a person has ruled, confirm its commit is an
  ancestor of `main`.

  **And the correction that came with it, which is the sharper half.** The
  detached commit that prompted this rule was reported as reachable only by
  reflog. It was not: the **remote** branch already pointed at it and the pull
  request already carried it — only the *local* ref was stale, and the claim was
  made by reading `git worktree list` plus a local branch name. **A local ref is
  not the answer to what exists on the remote.** Resolve against `origin/` and
  ask the API for a pull request's head before saying what it contains. That was
  the second time in one day: `tools/sync-docs.sh` refuses a checkout "ahead of
  `origin/main`" and said the same false thing about a branch that was not.

- **`main` is protected, and nothing bypasses it.** A ruleset on the default
  branch requires the three `gates` checks — `gates (3.12)`, `gates (3.13)`
  and `gates (3.14)` — to have passed **on the ref** before it can land,
  requires a branch to be up to date with `main` before merging, sends every
  merge through a **merge queue** (since 2026-09-29, below), and blocks force
  pushes and deletions.
  *3.14 joined on 2026-10-02* (#389, ruleset updated 14:05 CEST). It was
  declared in `pyproject.toml` and nothing ran it, and #365 was a defect that
  existed only there. `tests/test_ci_matrix.py` now holds the matrix equal to
  the declared versions; adding the check to the ruleset is still by hand.
  **Those three are the whole list, and `docs` is deliberately not among
  them:** a check that the documented process guarantees will be red cannot be
  a required check. The reason, and the deadlock it avoids, are in
  [`RELEASING.md`](RELEASING.md) and stay there; a red `docs` on `main` between
  an ADR and its site entry is that decision working, not a protection anybody
  lifted. **`glyphs` is not among them either, for a reason of its own:** it
  checks this repository's pages against another repository's font subsets, so
  a subset cut again on the site's side would turn it red on a pull request here
  that caused nothing — and a check that depends on another repository must not
  block this one. It is read, not required. No actor bypasses those three checks: there is no `--admin` path, and
  asking for one is not a route either. So every change has one shape —
  **push the branch, wait for green, then put it in the queue.** A direct push
  to `main` is refused, and that refusal is the rule working rather than an
  obstacle to get around.
  `digline.dev` has worked this way all along, and the two are now the same in
  the part that matters — neither default branch takes a direct push, and
  neither has a bypass. Both route work through a pull request with zero
  approvals required — here since 2026-09-24, see below — and both ask for an
  up-to-date branch. *Corrected 2026-09-23:* until
  then this sentence said `digline.dev` did not, which was true until its
  `Build` check was made strict that day (the ruleset records its last update
  at 15:48 CEST). The sentences around this one were checked against both
  rulesets on the same day. "Up to date" there means with digline.dev's own
  `main`; it cannot see this repository's, and that cross-repository gap is
  written down, with its cost, in digline.dev's `RUNBOOK.md`.

  **Why, and not only what.** It cost two incidents in the week of 2026-09-22.
  One session swept another session's commit onto `main` behind a clean
  fast-forward — a fast-forward is not evidence that only your own commit
  moved, and requiring the branch to be up to date is what catches that. And a
  red sat on `main`, because a check that nothing requires stops nothing once
  the commit is already there; required status checks are what catch that, and
  they catch it *before* the ref lands rather than after.

  What it does **not** require, so nobody assumes more than is there: no
  review, no signed commits, no linear history. **A merge commit is the only
  way work lands**, in both repositories: squash and rebase merging are off in
  the repository settings, each `main` ruleset allows the method `merge` alone,
  and a merged branch is deleted. One method, so that "the merge commit of the
  release pull request" — where a tag goes (below) — always names the same kind
  of commit.

  **It requires a pull request, with zero approvals** — since 2026-09-24.
  Every change already went through one, so the rule adds no step: it turns a
  habit into a refusal, and what it refuses is the direct push a tired person
  makes at seven in the evening. Zero approvals because there is one
  maintainer and GitHub does not let an author approve their own pull request;
  a required review here would be a lock, not a check. The rule also lifts
  OpenSSF Scorecard's Branch-Protection from 3 to 4, which is incidental and
  not why it exists: that check caps at 4 for as long as there is no second
  reviewer, because its next tier needs one.

  `require_extra_approval_for_unattributed_changes` is **off** in both
  repositories' `main` rulesets, and was set off on purpose. Nobody chose it on: the API turns it on whenever an update omits
  the key, which is how it arrived with this rule. On, a commit from an address
  linked to no GitHub account would need one approval more than configured —
  one, here, which nobody can give — cleared only by fixing the attribution at
  the moment of merging. So **any edit to the ruleset through the API sends the
  key explicitly as `false`**, or the default quietly comes back.

  Before the rule, the pull request was needed anyway, and for a reason the
  rule does not remove: **nothing else can produce the checks.** `ci.yml` runs
  on `pull_request` and on pushes to `main`, and a push to any other branch
  starts nothing at all: the branch arrives green-looking with no checks on
  it, and a ref with no checks is a ref that cannot land. So the shape above,
  in full: push the branch, open a pull request, wait for the three gates,
  enqueue. Observed on the first try: the first push of the branch that recorded
  the status-check rule produced **zero check runs**, and PR #82 had to be
  opened before anything could go green.

  **The merge queue, since 2026-09-29.** Enqueuing is not merging. The queue
  builds `main` plus the pull request on a `gh-readonly-queue/main/...` ref,
  runs the three gates **again, on that ref**, and only then moves `main` to that
  commit. So a pull request is green twice: once on its own head, once as what
  `main` will be. The merge method is still `merge` and the commit that lands
  is still a merge commit. What the queue replaces is the step where a person
  checks that `main` has not moved and merges by hand.
  - **How to enqueue.** `gh pr merge` does not do it here. It falls to
    auto-merge, which this repository has off, and fails with *Auto merge is
    not allowed*. Use the web button, or the GraphQL mutation
    `enqueuePullRequest` with the pull request's id and `expectedHeadOid` set
    to the head you watched go green.
  - **Whoever merges closes the issues by hand.** Do it once the pull
    request's state reads `MERGED`, not when the enqueue returns: the enqueue
    returns at once and the merge comes one gate run later. Close each issue
    with a comment that names the pull request and its merge commit, then
    check that each one reads `CLOSED`.
    *Observed 2026-09-30, twice.* Through the queue, `Closes #N` in a pull
    request's description no longer links the issue and no longer closes it:
    the pull request's `closingIssuesReferences` came back empty. #253 left
    #234 open, and #259 left #256 and #232 open. Keep writing `Closes #N`
    anyway, because it still tells a reader which issues the pull request
    answers.
    *Observed 2026-10-01, three times, the other way.* #315 closed #276, #316
    closed #278 and #319 closed #277 through the queue, one or two seconds
    after each merge, and each pull request's `closingIssuesReferences`
    returned its issue. **All three closes were on 2026-10-01, and that day
    nothing failed to close.** Both misses were on 2026-09-30. So the count,
    three against two, does not show a queue that closes half the time: it
    splits by day, and something may have changed between the two. The
    keyword had the same shape in all five pull requests: `Closes #N` in the
    description and in a commit message. So the difference is not in how it
    was written, and it was not found. The rule stands, because closing by
    hand costs nothing.
    *Observed 2026-10-01, once, and it is the third shape: an issue closed
    that should not have been.* #348 said *"It does not close #332"*, and
    the merge closed #332 one second later. A closing keyword is read with
    no regard for a negation before it, so "does not close #332" is
    `close #332`. **To say a pull request does not close an issue, no
    closing keyword (close, fix, resolve, in any form) stands directly
    before `#N`.** Once the merge lands, check that every issue the pull
    request only refers to still reads `OPEN`. #332 was reopened by hand on
    2026-10-02.
  - **It depends on `merge_group` in `ci.yml`**, which is the same failure as
    PR #82 in a new place. Without that trigger nothing starts on the queue's
    ref, and the queue waits on checks that never report. The trigger landed
    first (#250) and the queue was switched on only after that. It was proved
    by the first entry through it: #251, gates green on
    `gh-readonly-queue/main/pr-251-...`, and `main` moved to that commit
    (eb486d5).
  - **"Merged" now arrives later.** It comes one gate run (about three minutes)
    after the enqueue, not at the click. Anything that waits for a merge waits
    for the pull request's state to read `MERGED`, not for the command to
    return. The release order in `RELEASING.md` is one of those.
  - **The queue settings.** Up to five entries built and merged together, and
    a group of one merged without waiting for company. `ALLGREEN`: every entry
    in a group must pass. Checks time out at 60 minutes. The ruleset's
    up-to-date requirement was left as it was: whether the queue makes it
    redundant has not been ruled.

  The release push order is in [`RELEASING.md`](RELEASING.md) and this rule does
  not change it — it changes only how each of those pushes reaches `main`.

  **Release tags are protected, and are only ever put on `main`.** A tag goes
  on the merge commit of the release pull request, once `main` has it.
  `publish.yml` and `docker-publish.yml` refuse any commit `main` does not
  contain, in a first job every building or publishing job waits for, and
  `tests/test_release_from_main.py` fails if a job does not. A tag ruleset
  covers `refs/tags/v*` and `refs/tags/*-v[0-9]*` with `deletion` and `update`
  and an empty bypass list: creating a tag is free, deleting or moving one is
  refused for everybody. Re-doing a tag suspends that ruleset for the one
  deletion and restores it at once; the procedure, and how to verify the
  restore, are in `RELEASING.md`, *Re-doing a tag*, and stay there.

## Relationship with Plumbline

Plumbline (CLI `plumb`) is the methodology for preventive verification of the
development process; digline verifies the model's output. digline.core must be
importable from Plumbline as a library. Plumbline's wall/friction dichotomy maps
onto in-path/shadow-path here: use the same terms.

## The three worlds (ADR 0002)

1. **Developer** — works in the repo, writes the assertions, sees everything.
2. **Software house** — maintains N customers, must see the signal **without
   holding the production data** of any of them.
3. **End company** — owns the data, does not read code, is entitled to an
   understandable verdict and to its data not leaving.

The tenant (decision 8) separates customers from each other; the
payload/verdict boundary (decision 9) separates what the end company may send
from what it must not.

## Where the working material lives

The frictions log — what tripped a real user, in order of discovery — lives
in `private/`, which is a **separate repository** and is gitignored here.
Commits to it are made there, not in this repo. It is the record of use, so
it is written in whatever language the using happened in.
