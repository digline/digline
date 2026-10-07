"""The playbook, where the model that is about to call a tool will read it.

A tool description is not `--help`. It is loaded into the context of the model
deciding whether to call the tool, at the moment it decides — which makes it the
one place `AGENTS.md` reaches an agent that never read `AGENTS.md`.

So each description carries the rule that governs its own misuse. The agent that
loads the tools receives the discipline with the instrument. (ADR 0011 §9)

`tests/test_playbook.py` checks each of these against `AGENTS.md` itself, the
way `tests/test_agents.py` checks the shipped skill: a rule reworded in one
place cannot stay stale in the other two.
"""

from __future__ import annotations

__all__ = ["DESCRIPTIONS"]

LIST_RUNS = """\
Every stored run of a suite, newest first, with the baseline marked.

This is the table you choose a run from, and choosing is the point: promote from
the middle of several, never from the first one that goes green. A baseline
freezes one run, and the first green run is green partly on merit and partly on
luck — a case recorded at 0.667 where three runs out of three say 1.000 becomes
a red line nobody can explain a fortnight later.

You cannot promote from here and there is no tool that can. Assemble the
evidence, name the run whose per-case profile is closest to typical, and
recommend it; the human runs `digline promote`, or tells you to.

`note` names what this listing left out: runs at a schema this digline does not
read, files it could not read or the store refused, files not named by their
run's key, and a baseline it could not read or whose run is not listed. An empty
note does not mean nothing is missing. Say what it names.

`advice` says what to do about runs skipped for their schema: for a newer schema,
upgrading digline; for an older one, propose `digline migrate`. Do not run it on
your own initiative: a person runs it, or tells you to. Since schema 17 a
migration can change what a stored run says — a run that exited 0 can read as
exit 2, a committed baseline included — so it is a decision about the reference,
like `promote`, and no longer a respelling of it.

A file left out for its name is not a migration. The note names the file and
the name it should have, and renaming it is for a person."""

# The rule every tool that resolves a run carries, because the note reaches all
# of them and the misuse is the same on each. AGENTS.md rule 6 states it. (#433)
_NOTE = """\
`note` is what resolving `latest` stepped over, and is empty for a key you
typed. Non-empty, it says the run you got is not the newest this store
remembers, or that files were left out on the way: say it beside the result.
Do not pass a run it names back as a run to read: by construction that run
cannot be read here. Do not run the suite to make the note go away: a newer
run silences it and finds nothing that was missing, and it costs a run. An
empty note does not mean nothing is missing."""

GET_RUN = """\
One stored run: its verdicts, its measured intervals, and the configuration that
produced it.

Several cases flipping together in one run is a different event from one case
moving. It is either a real regression or the judge itself moving, and both are
findings — read the run, name the cases, and look at what they have in common.
Do not retry it: retrying until it passes destroys the evidence either way.

The judge's reason is not here and cannot be. A reason quotes the output, so it
is the output, and it stays inside the perimeter it was measured in."""

GET_BASELINE = """\
The approved reference for this suite: the run a human decided to hold the
others against.

Same shape as get_run, and the same boundary. If the suite has no baseline yet,
that is not an error — it is the first round, and what it needs is a person."""

COMPARE = """\
A run against the baseline. Answers: did it get worse?

`exit_code` is the contract. 0 proceed. 1 stop and report what got worse. 2 stop
— the run could not be judged, and nothing downstream of it is meaningful,
including any conclusion you were about to draw from the green checks beside it.

A movement inside the baseline's measured interval is reported as `unchanged`,
with `within_noise` on the delta. That explains a comparison and excuses
nothing: an absolute threshold still gates, a flip from passing to failing is
never rescued by noise, and an exit code of 1 is never argued away by quoting an
interval. If you find yourself writing "but this is within noise" about a red
run, you are arguing with the instrument.

A dip that does not recur on re-run is sampling noise: document it and move on.
Decide the number of re-runs before running them — with a stochastic judge,
enough re-runs always produce a green one, and a stopping rule chosen after the
fact measures your patience rather than the system.

When `note` names a baseline newer than the run, this held an older run against
a newer reference: a `1` still stops you, and what you report is that the run is
older than its reference, not that something regressed.

`run_key` is the run this compared and `baseline_key` the reference it was held
against. Quote and recommend the run by `run_key`: calling `get_run` again to
learn it can resolve `latest` to a run that landed in between."""

DIFF = """\
Two runs, neither of them a reference. Answers: should I switch?

Prompt A against prompt B, one model against another, temperature 0.3 against
0.7. This is a report and never a verdict, so there is **no `worse` field and no
exit code** — a verdict exists only against an approved reference, and neither
side of a diff was approved by anybody. Do not synthesise one.

Where both sides were sampled, each check carries the two measured intervals.
Overlapping intervals mean the two are not distinguishable by that check. That
is evidence beside the count, never an excuse: a diff has no baseline, so no
interval has the standing to overrule a difference.

Each side carries its own note, beside its key: `runs.left.note` and
`runs.right.note`."""

RUN = """\
Execute the suite against its target and store the result.

**This spends money.** `acknowledge_calls` must equal the suite's planned calls
to the target; call without it once and the refusal tells you the number. That
number counts calls to the target only — where an assertion judges each answer
several times, the returned `sentence` names the multiplier, and the honest
figure you report is the whole sentence.

`notes` holds what `digline run` says about the suite before the first call: a
check whose class declares no `KIND`, which the shape reading leaves out, and a
tolerance so wide its check is reported only when it flips. Each is a sentence
for whoever wrote the suite: say it beside the run. A note stops nothing and is
not a verdict, and an empty list means the suite was read and had none.

Before proposing a hunt that means several runs, multiply that line by the
number of runs and say the figure out loud in your recommendation. Five runs
over a hundred-call suite is five hundred model calls, and that is a decision
for whoever pays for them.

Decide the number of re-runs before running them, and stop at the signal. Never
keep rolling until the answer looks right."""

EXPLAIN = """\
A run read back as typed facts: what ran, what moved and by how much, against
which measured interval, what was suspended, what could not be judged, and what
differed underneath. Held against the baseline when there is one, read alone
when there is not — `scope` says which. `run_key` names the run read, and
`baseline_key` the reference where `scope` is `comparison`.

`exit_code` is the contract, exactly as on `compare`: 0 proceed, 1 stop and
report what got worse, 2 stop because nothing downstream is meaningful.

The facts carry no prose and no judge's words. Do not reconstruct a verdict the
exit code does not state, and do not read a single run as a trend: a reading is
of one run and its reference."""

LOG = """\
Which model answered, read down this suite's stored runs: spans of the same sent
model and the same answering model, the rolls between them, and every absence
named for what it is.

A roll is declared by the record: the same sent model, recorded answering as a
different model. A changed sent model is somebody editing the suite. Never infer
a roll from scores moving — that is a deduction, and the only licensed one is
the canary, which lives in `compare`.

This is not a gate and carries no exit code. `runs` counts what is in this store:
a history of 0 runs is not "no roll", and a span marked withheld cannot say
whether the model changed behind a named endpoint.

`register` is what people decided about comparisons — accepted, rejected or
unsure, against which reference, with the exit code they were looking at. It is
committed, so it is there even where no run is. There is no tool that records
one: a disposition is a person's. Assemble the evidence and recommend; the human
runs `digline register` and puts the reason in the commit message."""

DESCRIPTIONS: dict[str, str] = {
    "list_runs": LIST_RUNS,
    "get_run": f"{GET_RUN}\n\n{_NOTE}",
    "get_baseline": GET_BASELINE,
    "log": LOG,
    "compare": f"{COMPARE}\n\n{_NOTE}",
    "diff": f"{DIFF}\n\n{_NOTE}",
    "explain": f"{EXPLAIN}\n\n{_NOTE}",
    "run": RUN,
}
