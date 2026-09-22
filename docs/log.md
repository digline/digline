# `digline log` — which model answered, down the stored runs

`digline compare` answers **did it get worse?** about one run, against one
approved reference. `digline log` answers the question no single run can hold:
**has the model behind my alias changed?**

You pinned `claude-sonnet-5`, which is an alias. Some months later the provider
points it at a different snapshot. Your suite did not change, your prompt did
not change, nothing in git changed — and the thing answering is not the thing
that answered in March. The evidence was in your store the whole time, one run
document at a time, and nobody reads run documents by hand.

`log` reads the identity down the runs: what each side **sent**, what the
provider **said answered**, the rolls between the two, and — on real history,
mostly — every run that recorded nothing, named for what it is.

## Using it

```console
$ digline log --suite suite.py
support · 14 run(s) read in this store, 2026-09-02T09:14:22.104553+00:00 to 2026-09-15T11:02:07.551901+00:00

Target
  anthropic claude-haiku-4-5: not recorded: the document does not name its writer — 2026-09-02T09:14:22.104553+00:00 to 2026-09-05T09:14:22.104553+00:00, 4 run(s) (staging)
  anthropic claude-sonnet-5: no answering model was reported — 2026-09-06T09:14:22.104553+00:00 to 2026-09-08T09:14:22.104553+00:00, 3 run(s) (staging)
  anthropic claude-sonnet-5: the endpoint echoed the requested id, so what answered is not identified — 2026-09-09T09:14:22.104553+00:00 to 2026-09-11T09:14:22.104553+00:00, 3 run(s) (staging)
  anthropic claude-sonnet-5, reported as claude-sonnet-5-20260210 — 2026-09-12T09:14:22.104553+00:00 to 2026-09-12T09:14:22.104553+00:00, 1 run(s) (staging)
  anthropic claude-sonnet-5: no answering model was reported — 2026-09-13T09:14:22.104553+00:00 to 2026-09-13T09:14:22.104553+00:00, 1 run(s) (staging)
  anthropic claude-sonnet-5, reported as claude-sonnet-5-20260415 — 2026-09-15T09:14:22.104553+00:00 to 2026-09-15T09:14:22.104553+00:00, 1 run(s) (staging)
  2026-09-15T11-02-07-551901-00-00-331b1cfd9709f0cd re-judged 2026-09-15T09-14-22-104553-00-00-331b1cfd9709f0cd and asked the target nothing; it is not counted as a sighting of the target.

Judge
  declared no configuration — 2026-09-02T09:14:22.104553+00:00 to 2026-09-15T11:02:07.551901+00:00, 14 run(s) (staging)

Where what answered is not identified, only a canary sees whether the model's behaviour changed.

Target: anthropic claude-sonnet-5 reported claude-sonnet-5-20260210 last at 2026-09-12T09:14:22.104553+00:00, and claude-sonnet-5-20260415 first at 2026-09-15T09:14:22.104553+00:00.
  1 run(s) between them recorded no answering model.

Reference 2026-09-12T09-14-22-104553-00-00-331b1cfd9709f0cd, recorded 2026-09-12T09:14:22.104553+00:00, approved 2026-09-12T16:30:11+00:00.
  Target: anthropic claude-sonnet-5, reported as claude-sonnet-5-20260210
  Judge: declared no configuration

Dispositions recorded
  Against reference 2026-09-12T09-14-22-104553-00-00-331b1cfd9709f0cd:
    2026-09-16T06:50:52.301208+00:00 · rejected: 2026-09-15T09-14-22-104553-00-00-331b1cfd9709f0cd, exit 1 — 2 worse, 0 better, 0 not judged
    2026-09-16T06:51:09.241817+00:00 · accepted: 2026-09-13T09-14-22-104553-00-00-331b1cfd9709f0cd, exit 0 — 0 worse, 0 better, 0 not judged
```

That is one suite's fourteen runs, and the honest thing about it is how much of
it is absence. Read the target side down: four runs written by a release that
did not record what answered; three by one that did, against a provider that
returned no id; three against an endpoint that returned the id it was sent; then
two named snapshots with a silent run between them. **Two reported sightings out
of thirteen**, and the roll sits between them.

*Reported*, not *verified*, and the distinction is the whole point of the page.
A provider that names a snapshot we did not ask for has told us more than one
that echoes the id we sent — no passthrough produces a string nobody supplied —
but it has still only told us. Nothing here attests anything: the provider could
report any string, and a proxy in front of it could rewrite the one it did.
digline has a vocabulary for *we cannot identify what answered* — the seven
absences below — and none for *we were told and could not check*, which is why
this paragraph once said "verified". The gap is named, not filled.

A **span** is consecutive runs whose sighting on one side was the same, with the
first and last `created_at`, the number of runs, and the environments they ran
in — the environment is reported and never splits a span, because
[decision 8](adr/0002-three-worlds-and-where-the-data-lives.md) keeps it inside
the perimeter and out of every constraint.

A **replay** is listed under the target and counted as no sighting of it: a
re-judged run copies its source's target configuration, so counting it would
stretch the source's last sighting onto a copy. Its judge really did run, so on
that side it is an ordinary sighting.

## A roll is declared by the record, never deduced

The one sentence that matters:

> Target: anthropic claude-sonnet-5 reported claude-sonnet-5-20260210 last
> at …, and claude-sonnet-5-20260415 first at ….

A **roll** is two sightings of the same *sent* model whose recorded *answering*
models differ. Nothing in this reading looks at a score, a verdict or a canary,
and no type in it has a field one could occupy — so it cannot be tempted into
the arithmetic it refuses. If you switch your suite from `claude-haiku-4-5` to
`claude-sonnet-5`, that is not a roll and does not appear here: it is somebody
editing the suite, on a date the suite's own history records.

**The moment is never pinned.** A roll happened after the last run that recorded
`before` and no later than the first that recorded `after`, and the runs in
between that recorded nothing are counted rather than skipped — the
`1 run(s) between them recorded no answering model.` line. A roll compares with
the previous *recorded* sighting and not with the previous run, so a stretch of
silence widens the window instead of breaking the comparison.

Where no roll is found the reading says `No roll recorded.`, and that sentence is
scoped by the spans above it: on a history where eleven of thirteen sightings
identify nothing, it means *there was almost nothing to compare*, not *the
provider held still*.

## The absences, and there are seven

A reading of identity over real history is mostly absence, and **each absence is
a different fact**. They are checked in this order, and the first that applies
names the run:

| # | What the document shows | What the line says |
|---|---|---|
| 1 | a file the scan could not read at all | `N run(s) at schema K were not read.` / `N file(s) could not be read.` |
| 2 | the side recorded no configuration | `declared no configuration` |
| 3 | several instruments on the judge side | `several judges; no single answering model` |
| 4 | `resolved_model` withheld at a named endpoint | `the answering model is withheld at a named endpoint` |
| 5 | a configuration, a writer that names itself, no `resolved_model` | `no answering model was reported` |
| 6 | a configuration, no `resolved_model`, and no `digline_version` | `not recorded: the document does not name its writer` |
| 7 | `resolved_model` in clear and **literally equal** to the sent model | `the endpoint echoed the requested id, so what answered is not identified` |

Row 1 is not a sighting of anything, so it is a count on the reading rather than
a kind on a span; rows 2–7 are the six kinds a span can carry.

**Row 5 cannot say who was silent.** The provider may return no model id — AWS
Bedrock does not, by its own service model — or a plugin may not pass one on.
The document does not distinguish the two, so the sentence does not either.

**Row 6 is undated by principle.** The dependency pin at the run's `git_commit`
would put a release on most of those runs, but that is a derivation off a second
record, read from trees that are commonly `-dirty`. The document is the
authority, and *not recorded* is the honest sentence.

**Row 7 is an absence disguised as a presence.** A `resolved_model` equal to the
sent id looks like the provider confirming the model, and it confirms nothing:
an endpoint that returns the id it was sent has said what was asked for, not
what answered. An honest provider may legitimately do that — an alias with no
snapshot behind it, an aggregator that passes the request's id through — so the
row says *echoed* and stops. It is a fact, never a diagnosis: it does not say
the provider hid anything and it does not say nothing changed. The comparison is
literal and nothing is normalised, because normalising is interpretation. It is
checked only where `resolved_model` is in clear: at a named endpoint row 4
applies first and has to, since the sent id travels in clear and saying *echoed*
about a withheld value would disclose it exactly.

Four of those rows — **withheld, not reported, not recorded, echoed** — identify
no answering model, and the reading says so once, beneath any span table holding
one of them:

> Where what answered is not identified, only a canary sees whether the model's
> behaviour changed.

That is a fact about which instruments can see what, and not advice: a
[canary case](adr/0016-the-canary-case.md) measures behaviour and needs no id to
do it, while the record measures identity and cannot see behaviour at all.

**Absence is never collapsed into its neighbours.** The silent run of 2026-09-13
is its own line between the two named snapshots, so *nothing was recorded that
day* can never be read as *the same model answered that day*.

## How much the suite moves between runs

The identity half of this page answers *what answered*. This half answers a
different question, and the only one in digline that needs a **store** rather
than a pair of documents: **how much does this suite move when nothing
changes?**

```console
Run-to-run spread
  Across 10 comparable run(s) in this store, in this window — the latest not among them; excluded: 1 re-judged, 2 not fully judged.
  9 of the 10 run(s) did not identify the answering model.
  The counted runs were written at 4 commit(s).
  Written by digline 0.16.0, 0.17.0.
  accuracy: the latest run scored 0.810000 against the reference's 0.760000, a difference of 0.050000. accuracy ranged 0.710000 to 0.860000 across the counted runs.
    Within the latest run, the same aggregate per sample ranged 0.780000 to 0.840000 — a different measurement, not comparable with the range above.
  Whether the latest score is inside this spread is not stated: a range describes the runs it read and cannot carry that clause. A value under the low or over the high widens the range, so falling outside it names a score not seen before, not a change.
```

**Aggregates only.** One reading per run-level check the latest run measured —
`Accuracy`, `Precision`, a `CostBudget`, whatever the suite declares. A suite
that declares none gets `This suite declares no run-level check, so there is
nothing to read across runs.`, and no suite-wide number is invented out of the
per-case checks: a summary nobody asked for is the thing this product exists to
argue against.

It is read off the **latest run's** aggregates, and it comes out empty for four
different reasons. Each gets its own sentence, because only one of them is a
fact about the suite:

| No spread because | and the reading says |
|---|---|
| no run was read in this store, in this window | so, and that whether the suite declares a run-level check is not something a reading of runs can say |
| the suite declares no run-level check | exactly that — the one case that *is* about the suite |
| every check changed status against the reference | how many, and that a changed status carries no interval |
| every check recorded no score | how many |

Where two hold at once — one check flipped, another scoreless — **both**
sentences print, counted by cause and never as a total. Until 2026-09-22 all
four printed the second one, so a fresh clone was told its suite declared no
run-level check: on a fresh clone or a hosted runner, where
[decision 2](adr/0002-three-worlds-and-where-the-data-lives.md) means there is
no history at all, that is the first thing the command ever said. A checkable
sentence standing in for one that cannot be checked.

### Comparable is checked, never assumed

A range is only worth reading over runs that measured the same thing, so every
stored run is tested against the latest one and **every run left out is counted
by its reason and printed**. A number excluded silently is a number nobody can
check.

| Excluded as | When |
|---|---|
| `re-judged` | it declared `rejudged_from`: a replay asked the target nothing, and zero target variance would narrow the spread |
| `not fully judged` | a case could not be judged, which moves the denominator |
| `uncalibrated` | its calibration case lost the scale, so it is not a measurement |
| `measuring other rules` | a different `config_hash` |
| `counting other cases` | a different case-id set, or different suspensions, canaries or calibration cases |
| `testing another prompt` | a declared artifact's digest differs — a run declaring no artifacts is counted, and the reading says so |
| `asking another system` | the target configuration differs, as sent |
| `grading with another instrument` | the judge configuration differs |
| `another model was reported` | equal configurations whose recorded sighting differs |

Nothing here refuses the command, and `--since`/`--until` narrow this set like
everything else on the page.

Three things it **cannot** hold equal, so it reports them instead of pretending:
the **commits** the counted runs were written at (commonly `-dirty`, and
excluding on it would collapse the set to one run), the **releases** that wrote
them, and how many of them **identified the answering model** — because a roll
inside the set is absorbed into the range, and where the provider names nothing
the [canary](adr/0016-the-canary-case.md) is the only instrument that sees one.

### The latest run is never inside its own range

It is not in the range and not in the count. A spread that contained the value
it is read against would answer *inside* by construction, which is an excuse
dressed as a measurement. So a store holding one run reads `0` comparable runs
and prints no range — with the exclusions, which is exactly when you need them.

### Two intervals, and they are not the same quantity

The range is over the **recorded** aggregate of each run, which is computed from
the folded verdicts. The indented line under it is the same aggregate
re-evaluated per sample index **inside the latest run** — *what would one run at
one sample have said, at this moment* — and at `samples > 1` those are different
quantities. The folded aggregate is steadier than any single-sample one, and on
both stores this has been measured on, the between-run range came out
*narrower* than the within-run interval. They are printed labelled and never set
against each other.

### Why it does not say *inside* or *outside*

Because a range cannot carry that clause. A min–max range over a growing sample
only ever widens: it never converges, so a score outside it names **a value not
seen before**, not a change. That is measured rather than assumed — on twelve
runs of one suite at one configuration, *outside* fired on 4 of 12 readings, and
every firing above the range became the next reading's range. Waiting for more
runs does not fix a statistic that cannot settle.

So the reading prints the range, the count and the exclusions, says that it is
withholding the clause, and stops. If a reading is ever to say *inside*, it
needs a statistic that converges, which is a decision nobody has taken.
[ADR 0024 §7.4](adr/0024-the-judge-as-an-instrument.md) has the measurement.

**Silent on a flip.** Where an aggregate's status differs between the reference
and the latest run — pass against fail — no spread is printed for it at all. A
flip carries no interval, and printing one invites the reader to argue it away.

## It is never a gate

`log` **exits 0 whenever it could read the store**, whatever it found — a roll,
thirteen absences, or nothing at all. There is no `exit_code` in `--json`
either, and its absence is the point.

A roll is a fact about the system; the verdict about a suite is `compare`'s,
where a changed `resolved_model` is already a named delta and a moved canary
already exits 1. Two commands gating on one fact is how a pipeline learns to
mute one of them.

The spread adds no path to any other code either, and no field to `compare`: it
cannot feed the noise floor, move an outcome or reach `promote`. It is read
where the store is, and a gitignored per-machine history must never decide
whether a run passed — the same two runs would read differently on your laptop
and on a runner with no history at all. The one thing that exits 64 is a request it could not be
asked — a suite that will not load, or a window bound it will not accept:

```console
$ digline log --suite suite.py --since 2026-09-14T08:00
digline: --since '2026-09-14T08:00' names no time zone. A stored run is dated in UTC, and an instant without a zone could be any hour of that day: add one, such as +00:00, or give a date.
```

## The window

`--since` and `--until` take a calendar date or an ISO 8601 instant **with a
time zone**, and are inclusive at both ends. A date needs no zone, because it is
compared as a day: `--until 2026-09-14` includes every run of that day. An
instant without one is refused rather than assumed, which is the refusal above.

```console
$ digline log --suite suite.py --since 2026-09-12 --until 2026-09-15
support · 4 run(s) read in this store, 2026-09-12T09:14:22.104553+00:00 to 2026-09-15T11:02:07.551901+00:00
Window: 2026-09-12 to 2026-09-15.
```

The window is over `created_at`, the recorded fact — so a resumed run is one
sighting at its original date — and the reading's words are scoped to it.
*First seen* means **first seen in this store, in this window**. Runs are
gitignored by [fixed decision 2](adr/0002-three-worlds-and-where-the-data-lives.md),
so a fresh clone and a hosted runner have no history at all, and the reading
says `no run read in this store, in this window.` rather than reporting a flat
line. The **dispositions** are windowed too, on their own `recorded_at` and not
on the run they name — so a window ending before somebody read the comparison
shows the runs and no dispositions.

## The reference, and what people decided about it

The baseline is named once, at the end, with its own sighting: it is the one
sighting that is committed, and the one that travels between machines with the
repository. `promoted_at` is printed where it was recorded, and *when it was
approved was not recorded* where it was not — never filled in from git.

Under it comes the register — the dispositions a person recorded against that
reference, in `recorded_at` order, with the exit code they were looking at. The
story of the alias and the story of the reference are one reading, and the
register is committed, so it is on every clone even where no run is.
[`digline register`](register.md) is what wrote those lines.

## `--json`

```console
$ digline log --suite suite.py --json
```

emits the same reading for a program: `spans`, `rolls`, `replays`, `spread`,
`spread_absence`, `reference`, `register`, the `window`, and the counts `runs`,
`skipped` and `unreadable`. `spread_absence` is why `spread` is empty, counted
by cause — a consumer reading `[]` could not tell a store with no runs from a
suite with no run-level check from a run whose every check flipped, which is
the same reason the absences above cross. `answered` is `null` exactly when `absence` names why.

**No score crosses beside an identity**, and **no case id crosses at all** — the
reading is about the system and has no reason to name a case. `spans` and
`rolls` have no field a score could occupy, which is what keeps a reader from
deducing a roll out of scores printed next to identities. `spread` is a
type of its own that shares no row with them, and it uses that juxtaposition in
the one direction that cannot produce the deduction: **identity decides which
runs are grouped; scores never decide identity.** It carries the range, the
count, the exclusion tallies by reason, and no `inside` boolean — a bit there
would be read as the verdict the sentence declines to give.

`runs` is the count read **in this store**, and a `0` is stated rather than
folded into an empty list of rolls: a runner with no history and a history with
no roll are different facts, and a consumer must not deduce which one it holds.
Every side's configuration is reduced at the boundary *inside the fold*, before
a span exists, so the terminal, `--json` and the MCP `log` tool read the same
reduced value and a perimeter field never reaches a shape to be left out of.

## `--locale`

`en` or `it`, defaulting to `en` — the terminal rule, as on `compare`, `diff`
and `explain`. The multi-run vocabulary — *first seen*, *last*, *between them* —
is permitted here and nowhere else; *likely* is permitted nowhere, because that
word belongs to the canary and a reading of the record does not speculate.

## See also

- [`digline register`](register.md) — the dispositions this reading ends with
- [`adr/0020-the-reading-across-runs.md`](adr/0020-the-reading-across-runs.md) — the record
- [`adr/0005-the-configuration-of-the-system-under-test.md`](adr/0005-the-configuration-of-the-system-under-test.md) — what the provider *said* answered
- [`adr/0016-the-canary-case.md`](adr/0016-the-canary-case.md) — the behavioural half of identity
- [`adr/0024-the-judge-as-an-instrument.md`](adr/0024-the-judge-as-an-instrument.md) — §7, the spread, and why it withholds its clause
