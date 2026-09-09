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

If `skipped` or `note` is non-empty, stored runs were written under an older
schema and this listing does not show them. Say so, and propose
`digline migrate` — do not run it."""

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
fact measures your patience rather than the system."""

DIFF = """\
Two runs, neither of them a reference. Answers: should I switch?

Prompt A against prompt B, one model against another, temperature 0.3 against
0.7. This is a report and never a verdict, so there is **no `worse` field and no
exit code** — a verdict exists only against an approved reference, and neither
side of a diff was approved by anybody. Do not synthesise one.

Where both sides were sampled, each check carries the two measured intervals.
Overlapping intervals mean the two are not distinguishable by that check. That
is evidence beside the count, never an excuse: a diff has no baseline, so no
interval has the standing to overrule a difference."""

RUN = """\
Execute the suite against its target and store the result.

**This spends money.** `acknowledge_calls` must equal the suite's planned calls
to the target; call without it once and the refusal tells you the number. That
number counts calls to the target only — where an assertion judges each answer
several times, the returned `sentence` names the multiplier, and the honest
figure you report is the whole sentence.

Before proposing a hunt that means several runs, multiply that line by the
number of runs and say the figure out loud in your recommendation. Five runs
over a hundred-call suite is five hundred model calls, and that is a decision
for whoever pays for them.

Decide the number of re-runs before running them, and stop at the signal. Never
keep rolling until the answer looks right."""

DESCRIPTIONS: dict[str, str] = {
    "list_runs": LIST_RUNS,
    "get_run": GET_RUN,
    "get_baseline": GET_BASELINE,
    "compare": COMPARE,
    "diff": DIFF,
    "run": RUN,
}
