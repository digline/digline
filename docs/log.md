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
  anthropic claude-sonnet-5, answered as claude-sonnet-5-20260210 — 2026-09-12T09:14:22.104553+00:00 to 2026-09-12T09:14:22.104553+00:00, 1 run(s) (staging)
  anthropic claude-sonnet-5: no answering model was reported — 2026-09-13T09:14:22.104553+00:00 to 2026-09-13T09:14:22.104553+00:00, 1 run(s) (staging)
  anthropic claude-sonnet-5, answered as claude-sonnet-5-20260415 — 2026-09-15T09:14:22.104553+00:00 to 2026-09-15T09:14:22.104553+00:00, 1 run(s) (staging)
  2026-09-15T11-02-07-551901-00-00-331b1cfd9709f0cd re-judged 2026-09-15T09-14-22-104553-00-00-331b1cfd9709f0cd and asked the target nothing; it is not counted as a sighting of the target.

Judge
  declared no configuration — 2026-09-02T09:14:22.104553+00:00 to 2026-09-15T11:02:07.551901+00:00, 14 run(s) (staging)

Where what answered is not identified, only a canary sees whether the model's behaviour changed.

Target: anthropic claude-sonnet-5 answered as claude-sonnet-5-20260210 last at 2026-09-12T09:14:22.104553+00:00, and as claude-sonnet-5-20260415 first at 2026-09-15T09:14:22.104553+00:00.
  1 run(s) between them recorded no answering model.

Reference 2026-09-12T09-14-22-104553-00-00-331b1cfd9709f0cd, recorded 2026-09-12T09:14:22.104553+00:00, approved 2026-09-12T16:30:11+00:00.
  Target: anthropic claude-sonnet-5, answered as claude-sonnet-5-20260210
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
two named snapshots with a silent run between them. **Two verified sightings out
of thirteen**, and the roll sits between them.

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

> Target: anthropic claude-sonnet-5 answered as claude-sonnet-5-20260210 last
> at …, and as claude-sonnet-5-20260415 first at ….

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

## It is never a gate

`log` **exits 0 whenever it could read the store**, whatever it found — a roll,
thirteen absences, or nothing at all. There is no `exit_code` in `--json`
either, and its absence is the point.

A roll is a fact about the system; the verdict about a suite is `compare`'s,
where a changed `resolved_model` is already a named delta and a moved canary
already exits 1. Two commands gating on one fact is how a pipeline learns to
mute one of them. The one thing that exits 64 is a request it could not be
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

emits the same reading for a program: `spans`, `rolls`, `replays`, `reference`,
`register`, the `window`, and the counts `runs`, `skipped` and `unreadable`.
`answered` is `null` exactly when `absence` names why. **No score crosses**,
because no type here has a field one could occupy, and no case id either — the
reading is about the system and has no reason to name a case.

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
