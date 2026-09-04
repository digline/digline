# AGENTS.md — operating digline

digline tells you what happened; this file tells you how to behave about it —
the judgment layer the tool deliberately does not encode.

It is written for a coding agent working in a repository that *uses* digline:
you will run the suite, read a comparison, and be tempted to act on it. The
tool refuses what is unsafe and reports what it measured. Everything between
those two — whether a red run is a regression or a wobble, which run deserves
to become the reference, when to stop re-running and start reading — is
judgment, and it is left to a person on purpose. These are the protocols that
keep an agent's share of it honest.

Contributing to digline itself is a different document:
[`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## 1. The prime rule: the agent proposes, the instrument measures, the human approves

> **Never run `digline promote` on your own initiative.** Assemble the
> evidence — the `compare` output, the run key, what moved and why you believe
> it — and recommend. The human runs the command, or tells you to.

A baseline is an **approved reference**, not the most recent measurement. The
approval is the whole of its meaning: it is what a reviewer signed, what ships
in the pull request, and what a customer is shown. An agent that promotes on
its own dissolves the word — the file still says `baseline`, and nobody
decided anything.

`promote` also writes into `.digline/<tenant>/baselines/`, which is committed.
Anything that lands there arrives in someone's diff, and it must arrive
because they put it there.

## 2. Never promote the first green run

Promote from the middle of several, never from the first one that goes green.
A baseline freezes one run, and the first green run is green partly on merit
and partly on luck — a case recorded at `0.667` where three runs out of three
say `1.000` becomes a red line nobody can explain a fortnight later.

`digline view` is the table you pick from: the run list carries the aggregates,
so precision and accuracy read down a column and the median is visible. Take
the run whose per-case profile is closest to typical.

A first-green promote after a red streak is the worst case of all: it launders
an outlier into the reference, and every later comparison is against luck.
Worked through with numbers in
[`docs/guide.md` §6](docs/guide.md#6-promote-the-median-not-the-first-green-run).

## 3. One bad run is a draw until it repeats

A dip that does not recur on re-run is sampling noise: document it and move on.
One that recurs is drift, and drift is investigated — the model, the judge, the
prompt, the dependency floor, in that order of likelihood.

**Decide the number of re-runs before running them.** Two is usually enough to
tell a wobble from a drift; write the number down, run exactly that many, and
stop at the signal. Never keep rolling until the answer looks right: with a
stochastic judge, enough re-runs always produce a green one, and a stopping
rule chosen after the fact measures your patience rather than the system.

## 4. A multi-flip is investigated, not retried

Several cases flipping together in one run is a different event from one case
moving. It is either a real regression or the judge itself moving, and both
are findings.

Do not retry it. Retrying until it passes destroys the evidence either way:
the regression gets a green run to hide behind, and the judge's drift — which
would have shown up as the same cases flipping again, differently — is never
measured. Read the run, name the cases, and look at what they have in common.

## 5. "Within noise" explains, it does not excuse

A movement inside the baseline's measured interval is reported as `unchanged`,
with `within_noise` on the delta and a sentence saying so. That sentence is an
explanation of a *comparison*, and nothing else.

An absolute threshold still gates: a check below its threshold fails whatever
the interval says. A flip — passing to failing — is never rescued by noise, by
construction. And a red exit code is never argued away by quoting an interval;
if you find yourself writing "but this is within noise" about an exit code
of `1`, you are arguing with the instrument. The rules are
[ADR 0006](docs/adr/0006-repeated-samples-and-the-noise-floor.md).

## 6. Respect the exit codes as the contract

`0` proceed. `1` stop and report what got worse. `2` stop — the run could not
be judged, and nothing downstream of it is meaningful, including any conclusion
you were about to draw from the green checks beside it. Anything else (`64`) is
the CLI refusing the request you made, not a verdict on the suite.

Never parse the prose headline in a script. It is a *document* sentence, it is
localized, and it is written for the customer who reads the report. `--json`
is the machine surface — `--json full` when you need the individual deltas —
and `output_version` is there so a consumer can tell when the shape changed.

## 7. Say what a hunt will cost before starting it

`digline run` prints the planned call count on stderr before the first call:
`20 cases × 5 samples = 100 calls to the target`, with each `Repeated` named
with its own factor. Read it. Sampling multiplies spend, and the multiplication
is the part that surprises people.

Before proposing a hunt that means several runs — rule 3's re-runs, rule 2's
calibration — multiply that line by the number of runs and say the figure out
loud in your recommendation. A calibration of five runs over a hundred-call
suite is five hundred model calls, and that is a decision for whoever pays for
them.

## 8. When upgrading digline itself, migrate before you promote

Run `digline migrate` after the bump. A stored run written under an older
schema is skipped by a scan and refused by name until you do, so `--run latest`
starts failing for a reason that has nothing to do with the run you asked for.

Re-promote only when the release notes say migration cannot supply something.
Migration derives what it can from what the document already carries, and a
release that changed no score changes no baseline. Aggregate intervals were
the one case in 0.4.0: they need marks a run file does not hold, so they arrive
with the next promotion rather than with the upgrade. Read
[`CHANGELOG.md`](CHANGELOG.md) for the version you moved to, and
[`docs/migrate.md`](docs/migrate.md) for what a migration will and will not do.

---

## What digline refuses, so you need not check

These are enforced by the tool. Knowing them keeps you from writing guards that
duplicate them, and from proposing something that will be refused anyway:

- a run containing an errored verdict cannot become the baseline — an error
  means *could not judge*, and that is not a reference;
- a run produced under a different `config_hash` cannot become the baseline;
  changing a threshold, a tolerance or a sample count means measuring again;
- a run from another tenant cannot be compared or promoted — the perimeter is
  a directory, not a field;
- a suspended case carries a mandatory reason, and the suspension is in the
  headline and in the report until it is lifted.

## Where the reasoning is

- [`docs/guide.md`](docs/guide.md) — the eight chapters, in the order the
  problems arrive. §6 is which run to promote; §7 is the aggregate as the gate
  and the cases as the diagnosis; §8 is the five triggers that call for a
  decision.
- [`docs/view.md`](docs/view.md) — the run list you choose from, and the case
  history where judge noise is visible as raw votes.
- [`docs/migrate.md`](docs/migrate.md) — what a scan skips and what a named key
  refuses.
- [`docs/declarative.md`](docs/declarative.md) — a suite may be `suite.py` or
  `suite.toml`; the extension chooses, both build the same objects, and a
  ported suite keeps its baseline. Nothing in this file depends on which form
  you are looking at.
- [`docs/adr/`](docs/adr/) — the decisions, numbered, with the reasoning.
