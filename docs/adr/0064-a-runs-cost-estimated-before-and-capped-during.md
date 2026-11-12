# ADR 0064 — A run's cost: estimated from the last run before it, capped on what it measures during it

- Status: accepted 2026-11-12, by Alessandro Prandini, proposed by a first use
  outside the project, on a Java application with a judged suite. Its two
  decisions were ruled on 2026-11-12, in the conversation of the session that
  wrote this record, on the question of what an estimate before the run could
  be; they are stated here in this record's own words. Built in the same pull
  request.
- Shipped: unreleased
- Date: 2026-11-12
- Opens: **nothing.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no
  `RECORDING_VERSION`, and no entry in the layout of `.digline/<tenant>/`: the
  estimate reads runs already stored, and the ceiling writes nothing the
  journal did not already write
- Amends, by a dated note beside the place it amends, which points here, the
  text kept as written: [ADR 0006](0006-repeated-samples-and-the-noise-floor.md)
  §8, *"A **money** estimate is not part of this ADR"*: the estimate is decided
  here, and not as the target's method that paragraph sketched
- Assumes: fixed decision 4, *"Cost and latency are budgets, not metrics. A
  declared ceiling fails the run."*; [ADR 0017](0017-the-journal-and-the-resumed-run.md)
  §4, the journal written per case; [ADR 0025](0025-the-tokens-and-the-bill.md) §4 and
  §11, the judges' share and the earlier legs' bill

## Context

A first use outside the project ran a judged suite whose judge had no price
inside `Repeated`. Every case was paid for, the target's calls and the
judge's, before each one errored on the price. The judge's own `preflight()`
now refuses that run before the first call (ADR 0004 §8.0, decided the same
day), but the use asked two more things: to know what a run will cost before
it starts, and to stop one that costs more than a person meant to spend.

The first was asked as a maximum, *"at most X USD"*. **No such figure exists
before the first call**, and saying one would be the vacuously true claim
fixed decision 3 forbids in another shape:

- a judge's input holds the target's answer, which does not exist yet, so a
  judge call's input tokens are unknown until the target has answered;
- a token count is bounded by the bytes of a text only within one tokenizer,
  and the target's answer, bounded by the target's `max_tokens` in its own
  tokens, has no bound in the judge's;
- a target that is an agent makes a number of calls per case nobody knows in
  advance, and a target behind HTTP reports what it spent only after it spent
  it;
- `Pricing.cost` needs a `Usage`, which is why ADR 0006 §8 deferred any money
  figure, and `CallPlan`'s docstring said so.

## Decision

### 1. Before the run: an estimate from the suite's newest run, said as one

Before the first call, beside the plan of calls it already prints, `digline
run` prints on standard error what the run is likely to cost:

- **where the suite has a stored run with a bill**, the newest one's measured
  spend, the target's and the judges' together, divided by the cases it ran
  and multiplied by the cases this run will call (subject, calibration and
  reviewed; a resumed run's journalled cases are not called and not counted):
  *"estimated from run `<key>`: 0.2400 USD, its 0.2400 USD over 3 cases scaled
  to 3; an estimate, not a ceiling"*. It names the run it read, says where that
  run was made under another configuration, and says where that run did not
  price every call (the figure is then low) or did not record whether it did;
- **where it has none**, no figure, and the sentence says why: *"no cost
  estimate: this suite has no stored run to read one from, and nothing before
  the first call can say what a run will cost"*. A newest run that ran no case,
  or recorded no bill, is named the same way.

The calls the plan announces stay what they were, arithmetic over the declared
suite, now with the judgements a case gets where `samples` is above one.

*Decided here:* the estimate is per case and not per call. A run's bill is
recorded as two lines, the target's and the judges', and the number of judge
calls a case makes depends on checks digline did not write (`CallPlan.repeats`
names only `Repeated`); the cases a run called are known on both sides.

### 2. During the run: a ceiling on what the run measures

`digline run --max-cost USD` stops the run **when the spend it has measured is
above USD**:

- read after each case, once the journal holds it (ADR 0017 §4): the target's
  calls of this leg and of the earlier legs (`Pending.spent`), and the judges'
  share of this leg (`judge_totals`, ADR 0025 §4), added up;
- above the ceiling, nothing more is called. The run stops with a refusal that
  says where it was, *"stopped by the cost ceiling of 0.1000 USD after 2 of 3
  cases: 0.1600 USD measured so far, the target's calls and the judges'
  together; nothing more was called, and the cases already run are kept for a
  resume"*, then the command that finishes it, `digline run --suite … --resume
  <key>`;
- **exit 2**: the request was taken, and the run did not judge every case it
  declares. Not 64, which is the CLI refusing a request it never acted on, and
  not 1, because nothing was compared. No run document is written, as with any
  run that did not finish;
- a ceiling that is not a positive finite number is refused before the first
  call.

**It is never compared with the estimate.** The estimate is a reading of
another run; the ceiling is the only figure here that cannot lie, because it
is read off calls already made. It is fixed decision 4 applied to the whole
run.

**What it does not see**, said where it is decided: a call whose cost is not
known adds nothing it does not know, so the ceiling reads at least what was
spent and never more; and on a resumed run the judges' spend of the earlier
legs is not in the journal (`Pending.spent` keeps the target's calls), so the
ceiling under-reads by that much. The run stops at the first case boundary
past the ceiling, so it can spend up to one case more than the ceiling.

## Not decided here

- **The estimate and the ceiling on other front ends.** MCP's `run` and
  `pytest --digline-run` take neither. `execute(max_cost=…)` is the library's
  form, and those front ends can pass it when somebody asks.
- **The estimate in `--json`.** `digline run --json` carries the plan's count;
  the estimate is a line on standard error only.
- **A ceiling a suite declares**, beside the one a command line passes.

## Consequences

- `execute()` takes `max_cost` and raises `CostCeilingReached`, a
  `RefusedError` whose fields are the four facts its sentence says.
- `digline.host.estimate` reads the newest run; the CLI prints its sentence.
- `tests/test_cost_estimate_and_ceiling.py` holds both on a suite of 3 cases ×
  2 samples × a `Repeated` of 3.
