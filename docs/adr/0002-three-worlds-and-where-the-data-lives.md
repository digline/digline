# ADR 0002 — Three worlds, and where the data lives

> **Note on the name (2026-08-26).** «prompteval» was the project's working
> name; it became **digline** because the name was already taken in the
> category. The text below has been updated to the new name: this note is the
> only place where the old name remains written.

- Status: accepted
- Date: 2026-08-25
- Introduces: fixed decisions 8 (tenant) and 9 (payload/verdict) of `CLAUDE.md`
- Assumes: [ADR 0001](0001-verdict-not-score.md)

## Context

ADR 0001 was written assuming a single world: a developer evaluating their own prompts in
their own repository. The assumption was wrong, and not at the margins.

digline's typical customer is not a single team. It is a **software house** that builds
and maintains AI solutions for end companies that do not develop software. Three distinct
roles follow, with different interests in and rights over the same data:

**World 1 — the developer.** Works in the repository, writes the assertions, reads the
code. Sees everything they produce, because they produce it on data they chose.

**World 2 — the software house.** Maintains N customers at once. Must be able to answer
"did customer A's solution get worse after Tuesday's release?" **without holding customer
A's production data**, and without A's and B's data ever ending up in the same place by
inattention.

**World 3 — the end company.** Owns the production data and does not read code. Is
entitled to an understandable verdict about a system it cannot inspect, and is entitled to
its data not leaving.

The conflict is real and cannot be solved with a permission: the software house needs the
signal, the end company cannot hand over the content. The rest of this document exists to
separate the two so that the type guarantees it, not discipline.

## Decision

### 1. The tenant is the perimeter, and it is mandatory

`Run.tenant: str`, mandatory, non-empty. A tenant is a perimeter — an end customer of the
software house, a team's project. Not a label: a boundary.

- `compare()` **raises** if the two `Run`s have different tenants.
- `promote_baseline` **raises** if the run's tenant is not the one it is addressed with.
- The on-disk layout is `.digline/<tenant>/baselines/<suite>.json`, and tenant and suite
  names are validated as single path segments: `..` and `/` are refused.

The tenant is a **directory** and not only a field inside the file, because that way the
separation is enforced by the filesystem instead of being described by a document. A
software house with twelve customers must not be one typo away from reading one's history
as another's.

Two runs from different perimeters produce numbers on the same scale: a wrong comparison
would be arithmetically valid and factually meaningless. It is the kind of mistake that is
never noticed, so it has to be made impossible.

`SCHEMA_VERSION` goes to 3: a file without a tenant cannot be placed in a perimeter, and
one without the redaction flag is indistinguishable from a complete document. Both must be
refused, not guessed.

### 1-bis. No sub-perimeter: the environment is a field, not a hierarchy

The tenant does **not** break down into sub-perimeters. Production, staging and acceptance
for the same customer live in the same perimeter, because the perimeter is a property **of
the data**: it is the same data, of the same owner, under the same contract. Treating
staging as a perimeter of its own would suggest its data belongs less to someone, and it
does not.

`Run.environment: str` is mandatory, non-empty, with no default, and **does not enter the
on-disk layout**: a suite has one baseline per tenant, not one per environment.

`compare()` reports it — `Comparison.environment` and `Comparison.baseline_environment` —
and constrains nothing. The reason is that **comparing staging against the production
baseline is the pre-release check**, that is, the thing the product exists for: making it
an error would have prevented the main use case in order to defend a symmetry nobody had
asked for. Reporting it serves the reader, who must be able to see what was compared with
what; enforcing it serves nobody.

No default, because an implicit `environment` is the premise of a comparison in which
nobody knows any more what they are looking at.

`SCHEMA_VERSION` goes to 4: a comparison that cannot say whether it read staging or
production is one nobody should act on.

### 2. The payload stays where it is born, the verdict travels

> **Extended by [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md)
> (2026-08-26):** a run also records the files that *are* the thing under test.
> They are neither verdict nor measurement, and they do not cross a boundary
> unless the suite declares `Disclosure(artifacts=True)`.

This is the rule that makes the three worlds compatible.

**The verdict** — name, `assertion_id`, status, score, threshold, tolerance, and the
metadata *measured by an assertion* — describes how a system behaved. It does not contain
the data it behaved on. It may cross a boundary.

**The payload** — the `reason`, and metadata not covered by a `Disclosure` — is, or
contains, what the system processed. It does not cross.

The `reason` is payload and not a label because **a judge quotes what it judges**: that is
its usefulness, and it is exactly what makes it unpublishable outside the perimeter.

**Redaction is a function on the value.** `redact(run, disclosure) -> Run` is the
primitive; `run_to_json(run, redacted=True)` is built on top, not the reverse. A redaction
living only in the serializer would be an opt-out that every future transport — the
Postgres store, an HTTP push, an export — would have to remember to switch on: the exact
shape of promptfoo's `#9968` defect, where the beacon fired anyway. With the primitive on
the value, any transport redacts first and serializes afterwards.

In the document the payload fields are **absent, not emptied**: not even the length of the
original survives. The document carries `"redacted": true` at the top level, and
`Run.redacted` travels with the value, so no reader can mistake a redacted run for a
complete one in which the judge was terse.

**The flag is verified, not believed.** `Run.__post_init__` refuses a run marked
`redacted` whose verdicts still carry a `reason`. Without the check, one could hand-build
a run that *declares* itself redacted with the contents intact, and the serializer would
omit the reasons on trust: the flag would announce a guarantee that nothing provides,
which is worse than no flag. It is the same family as the `status` that cannot contradict
its own threshold (ADR 0001).

The check covers the reasons and not the metadata: whether a metadata value should have
survived depends on the `Disclosure` that produced that run, and a `Run` does not carry it
along. Using `redact()`, the flag is correct by construction.

What survives is enough for `compare()`: **an end company can send a verdict without
sending its own data**, and the software house sees the regression.

### 3. `Disclosure` is asymmetric, and the asymmetry is the point

    Disclosure(score_metadata: frozenset[str], run_metadata: frozenset[str])

- `Score.metadata` is written **only by assertions**. Numbers and booleans travel on their
  own merit (`travels()`); strings only if the key is declared.
- `Run.metadata` is what an integration annotated from production. **Nothing travels by
  default, numbers included.**

The reason for the asymmetry: `0.01` written by `CostBudget` is a measurement; `1499.00`
copied from a customer's request is their data dressed up as a measurement. Both are
`float`, but only the first has a provenance one can trust. "Numbers pass" is true of the
producer, not of the type.

The mapper **has no route** to `Score.metadata`: an assertion writes its own metadata from
what it measured, and what the mapper brings in through `EvaluatorInputs.metadata` does
not get there. It is structural, not a convention.

The allowlist is declared **in the suite's code, never read from the data**: widening what
leaves a perimeter must be a change someone writes and a reviewer sees. The default is
empty, so whoever redacts without knowing the suite's policy discloses *less*, never more.

### 4. `Comparison` inherits the payload of its inputs, and that is correct

`compare()` works between a redacted run and a complete baseline: everything it reads
survives redaction. But the `Comparison` it returns **contains the verdicts it received**,
so it carries the payload of what it was given.

This is not a defect to fix. Inside the end company's perimeter — where world 3's report
is generated — the comparison *must* carry the `reason`, because that is what makes a
failure understandable and actionable. An always-redacted `Comparison` would make the
report useless exactly where it is needed.

The operational consequence, which stands as a rule: **a `Comparison` does not cross a
boundary.** What crosses is a redacted `Run`, and the comparison is redone on the other
side. Whoever writes a transport for `Comparison` is going down the wrong road.

### 5. The `case_id` is not payload, and there is no way to copy one

The `case_id` has to cross the boundary: it is the key `compare()` pairs on, and without
it there is no comparison. So it cannot be payload.

It follows that it must never *contain* payload, and the guarantee is structural:

- **World 1.** The developer chooses the `case_id` and answers for it. It is their test
  data, chosen by them.
- **Production → repo bridge.** The id is **generated by digline** — date, sequence
  number, short hash of the *already redacted* response — and **there is no parameter to
  pass one in**. It is not that the application's identifier must not be copied: there is
  no way to copy it.

The difference between the two formulations is the whole decision. A rule that can be
skipped in a hurry will be skipped in a hurry; one that has no entry point does not need
to be remembered.

### 6. Production store: Postgres, and retention is mandatory

Production data does not live in the repository. The repository is the system of record
for the **verdict**; the production payload has a different volume, life cycle and owner.

**First implementation: Postgres**, inside the end company's perimeter. Decided now
because the decision informs the protocol, not because it has to be written now.
Reasons: it is the thing an end company already runs, it does not require a new service to
get approved, and it holds up under the per-case and per-time-window queries the report
needs. No dependency on a service run by us — not being able to exfiltrate is a selling
point only if it is true for paying customers too.

**Retention is mandatory, not freely configurable.** A production store without a declared
deletion policy is not compliant and digline must not allow creating one: the window is a
mandatory constructor parameter, not a setting with a generous default. An archive that
grows forever is an incident waiting to happen, and the convenient default is how you get
there.

### 7. A single way in: `EvaluatorInputs` via a mapper

Whatever is evaluated — an offline matrix, a production stream, a single response —
enters the core **only** as `EvaluatorInputs`, built by a mapper. The core does not know
what a trace, a matrix or a stream is.

It is the boundary that makes the three worlds the same engine, and it has to be defended:
if one day the driver needed to know `EvaluatorInputs` in a way other than "a mapper hands
it to me", that is the sign the boundary has broken.

**How production data reaches the mapper — in-process or over OTLP — is deferred to a
later ADR.** It is a choice with heavy operational consequences for the end company (an
OTLP receiver is one more service to run; in-process is a dependency inside their
application) and must not be taken by inertia. All that is recorded here is that the core
does not prejudge it.

### 8. Promotion has three conditions

`promote_baseline` refuses in three cases. They are collected here because they are the
same rule seen from three sides: **a baseline is an approved reference**, and each of the
three conditions prevents approving something that is not a reference. Each exists because
violating it produces a comparison that runs anyway and returns numbers anyway — the worst
way to be wrong.

1. **`TenantMismatchError`** — the run's tenant does not match the one it is addressed
   with. A perimeter is not crossed because of a wrong copy (§1).
2. **`ConfigMismatchError`** — the `config_hash` does not match the configuration in
   force. Otherwise the baseline would record scores obtained under thresholds different
   from the current ones (ADR 0001 §5).
3. **`ErroredRunError`** — one or more verdicts are in `error`, and the exception lists
   the cases. An error means the suite **could not judge**: there is nothing to measure a
   future run against. Promoting it would freeze a permanent red row that no reader could
   tell apart from a new failure — and the reader, in world 3, does not have the code to
   work it out for themselves.

   The remedy for an unstable case is to fix it or take it out of the suite, not to
   enshrine it. It is the natural sequel to ADR 0001's rule that `error` is not green and
   is not a regression: it is not a reference either.

*Numbering note: this section is the eighth, not the sixth, because inserting §1-bis
shifted the numbering after the initial draft. §6 remains the `case_id`.*

### 9. The suite is compiled from source, and git is read before importing it

The suite is Python code, not data (§7 and the decision on the configuration surface: a
`Judge` is an object, a `Target` a function, a `Disclosure` is declared in code by
construction). Two constraints on how the CLI loads it follow, **non-negotiable**, both of
which emerged running the CLI on a real repository and neither of which is visible
in-process.

**The suite is compiled from source, without reading or writing bytecode.** It does not go
through the ordinary import machinery.

1. *Writing* bytecode leaves `__pycache__` in the user's repository, and a repository with
   new untracked files is **dirty**: our own import would have made every run declare
   itself non-reproducible. A defect digline attributed to the user and was its own.
2. *Reading* bytecode can execute a stale suite. Python's freshness check is
   `(mtime, size)` with one-second granularity: a file modified within the same second and
   at the same length is served from the cache. **It is the only defect met in the whole
   project that could have let a test meant to fail pass** — and for a tool whose premise
   is reproducibility, the only acceptable answer to "what was executed" is "what is on
   disk".

**The suite's directory goes on `sys.path` before execution.** A suite imports the
application it evaluates: `from brief import judge` is the normal case, not the exception.
Without this, the first real suite fails on its first line with `ModuleNotFoundError`, and
the tool looks broken because it is. It is what `python file.py` and pytest from its own
rootdir do. It holds **only** for a spec that is a path: a `package.module:attr` is
already importable, and widening the path for it would mean reaching into the caller's
environment for no reason. The insertion is guarded against duplicates.

**What resolves inside the suite's directory is also read from source**, through a
`FileFinder` built with a `SourceOnlyLoader` — a derived `SourceFileLoader` that overrides
`get_code` to always compile from disk — registered in `sys.path_hooks` and in
`sys.path_importer_cache` **for that one directory only**. On top of that,
`sys.dont_write_bytecode` is true for the whole CLI process: we leave no debris.

The previous constraint covered the suite file; it did not cover what the suite imports,
that is, **the user's application — the only thing that really changes between two runs**.
The concrete case, reproduced and now in `tests/test_cli.py`: a `brief.py` next to the
suite, modified at the same length and within the same second, with a `__pycache__`
already left by an ordinary `python -c "import brief"`. The resulting `.pyc` looked fresh
to Python's `(mtime, size)` check, the application ran in its old version, and `compare`
answered **"nothing got worse"** while something had. The test was verified by disabling
the finder: without it, it fails.

The scope is a single directory, deliberately. A loader for every module would slow down
every import in order to protect files that do not change during an evaluation — stdlib
and site-packages — and would reach far beyond what this tool has the right to alter. Like
the other two, it holds only for a spec that is a path.

**Git status is read before any import of ours.** Otherwise the answer would depend on
what our loading had just done rather than on the state the user left the repository in.
The `-dirty` marker describes the user, not us.

A corollary recorded here because it is of the same family: `created_at` keeps the
microseconds. Truncating it to the second was an aesthetic choice, until listing the runs
showed the cost — a run's key derives from the timestamp and the configuration, so two
runs in the same second on the same suite produced the same key and **the second silently
replaced the first**.

### 10. The aggregate, and the one number you improve by doing less

`Run.aggregate` carries verdicts **on the run** — precision, recall, accuracy — alongside
those on the cases. They are `Verdict`s like any other: mandatory threshold, hence a gate
by construction, and `compare()` says whether they regressed. No new mechanism.

The reason is measured, not aesthetic. Four executions of one unchanged prompt agreed with
the human marking on **14, 14, 15, 15 cases out of 21**, while individual cases jumped by
three votes. `15/21 − 14/21 = 0.0476`: within a tolerance of one case. **The aggregate is
the gate, the per-case is the diagnosis.**

Three constraints, each for a real path to error:

1. **`over` names exactly one assertion.** A missing name aggregates over an empty set; an
   ambiguous name — two `contains` in the same suite are the ordinary case, and it is the
   reason `compare()` pairs by identity and not by name — aggregates over whichever comes
   first. They are the same mistake seen from two sides, and `Suite` refuses both, listing
   the candidates.
2. **Empty denominator → `error`.** If the system kept nothing, precision is not `1.0`: it
   is undefined. `1.0` would be the most dangerous possible answer.
3. **Mandatory labels** if an aggregate counts a confusion matrix. No implicit
   denominators.

**The note that must outlive this document.** `suspended_excluded` is the only number in
the product that **can be improved by removing work instead of doing it better**:
suspending a failing case raises the ratio without anyone lying. We do not forbid it — an
unstable case should be suspended, that is the reason suspension exists — but the two
exclusions travel *next to* the figure wherever it goes: in the `reason`, in the metadata,
in the report's table. **That number is never read on its own.**

**And where to put the threshold.** An aggregate is a contract about **present
behaviour**, not a target: the threshold is set where the system is — measured — and the
comparison protects against getting worse. A threshold set where you *wish* you were makes
the gate red by construction, hence useless for CI and soon ignored by whoever reads it.
With the numbers from the brief: measured precision ≈ 0.62, hence a threshold of **0.60**,
not 0.70. You reach 0.70 by improving the system and then raising the threshold, which is
a change to the configuration — visible in `config_hash` and in a pull request.

`SCHEMA_VERSION` goes to 6.

## Consequences

- `compare()` and `promote_baseline` have one more error path, and it is right that it is
  an exception and not a return value: crossing a perimeter is not an outcome.
- The production → repo bridge is the point where anonymization is **mandatory**: it is
  the only place where payload and verdict touch, and the only one where a mistake is
  irreversible — once committed, it is in git's history.
- Three planned packages, in the order they will be built after the offline driver:
  `digline.report` (the document for world 3), `digline.production` (the Postgres store
  with mandatory retention), `digline.bridge` (production → repo, with anonymization and a
  generated `case_id`).
- The build order is deliberate: **nothing online before the report.** The report is what
  world 3 sees, and it is the only one of the three artifacts that today exists in none of
  the audited competitors.

## Not decided here

- The production → mapper transport (in-process or OTLP), as above.
- The form of the report: whether it is HTML, PDF or both, and how much of the
  `Comparison` a non-technical reader should see.
- Which `environment` values are canonical. The string is free on purpose: end companies
  name their own environments as they like, and imposing an enumeration would have
  produced an `other` that half the real world falls into.
