# My suite is green today: who watches it on Thursday?

An **operator**: an agent that runs the checks on a schedule, absorbs the
measurement's own noise, and wakes a human only for drift that deserves a
decision.

This directory is the reference assembly for that loop. A suite, a committed
baseline, a configuration file, an operator prompt, an `.mcp.json` for the
interactive path, and a scheduled workflow whose escalation opens an issue in
your own repository. It runs with no API key.

    suite.py        four cases, six checks — the quickstart's shape, deliberately
    fake.py         the system under test and the judge, both stand-ins
    operator.toml   cadence, stopping rule, budget, escalation — a file, not a vibe
    loop.py         run, re-run within the rule, classify
    dossier.py      the cycle, rendered as the three-layer alert
    judgment.py     layer 3, the only part a model writes — opt-in
    alerts/         two real alerts this loop produced

The suite is not the point. The loop is.

## The two answers, which is the whole story

Run the loop against a system having a bad day:

    uv sync
    OPERATOR_SCENARIO=wobble uv run python loop.py
    uv run python dossier.py --cycle cycle.json --out alert.md

The first run comes back red. The operator re-runs it once — the number was
decided in `operator.toml` before anything ran — and it comes back green. The
verdict is **draw**, and nobody is woken. `alerts/draw.md` is that document,
captured; its second layer is the argument in four lines:

    Run …638965 (seed 0, exit 1)
    | is-it-waterproof  | llm_rubric | regressed | 0.9104 | 0.5279 | no interval
    Run …834128 (seed 1, exit 0)
    | how-do-i-return   | llm_rubric | unchanged | 0.8947 | 0.8961 | 0.8603–0.9221 across 3 samples
    | is-it-waterproof  | llm_rubric | unchanged | 0.9104 | 0.9055 | 0.8694–0.9369 across 3 samples
    | where-is-my-order | llm_rubric | unchanged | 0.8913 | 0.9005 | 0.8700–0.9309 across 3 samples

Now the same thing, except it keeps happening:

    OPERATOR_SCENARIO=drift uv run python loop.py

Three runs, the same case and the same check red in every one, and the
stopping rule exhausted. The verdict is **drift**, and this one escalates.
`alerts/drift.md` is that document. It is not a summary of the red run: it is
the run keys, the exit codes, the three comparisons, the measured intervals of
the checks that held, and the one pair present in all three.

Those two cycles are the loop. Everything else is plumbing.

There are two more scenarios. `structural` flips several cases at once and
escalates on a **single** run — it is never retried, because retrying destroys
the evidence either way: the regression gets a green run to hide behind, and a
judge that has moved is never measured. `steady` is the ordinary week, and it
is what the committed baseline was promoted from.

## The alert is a document in three layers

1. **The fact** — the wire's own facts, from `digline explain --json`: the
   typed list digline renders its own reading from. Run keys, exit codes, what
   moved. Reproducible, and not prose.
2. **The dossier** — deterministic: what the operator did and saw. How many
   re-runs, against which declared rule, what it spent, which checks moved and
   what interval their samples had spanned.
3. **The judgment** — the only layer a model writes, and it is labelled as the
   operator's opinion, never as digline's verdict. The instrument measures; the
   operator opines; the document keeps them apart.

Layers 1 and 2 need no key and no network beyond your own endpoint. Layer 3 is
an explicit opt-in — `DIGLINE_LIVE=1` and a key — and when it does not run, the
heading is still there saying so. An absence is stated, never faked.

## What it may do alone, and what it escalates

The operator automates the judgment `AGENTS.md` writes down, and nothing beyond
it. Alone: re-run a suspicious run, tell a draw from a drift, diff two
candidates. Escalated: a drop that repeats, several cases moving together, a
run that could not be judged, and anything needing a signature.

It cannot promote a baseline. Not "is told not to" — **cannot**: the MCP
surface has no such tool, and there is nothing in this directory that shells out
to one. A baseline is an approved reference and the approval is a person's.

And it does not repair anything. The operator watches the measurement; fixing
the prompt belongs to your engineer or your coding agent, and the alert is the
handover between the two.

## The configuration is a file

`operator.toml` holds the four things an agent could otherwise talk itself into:

    cadence                 what the schedule says, checked against the workflow
    max_reruns              decided before the first run, never in the moment
    structural_flip_cases   at or above this, investigate — never retry
    max_target_calls        the cycle's ceiling, checked before anything is spent

The last one is the loop's own arithmetic, not digline's:
`acknowledge_calls` binds one call, so `loop.py` multiplies the suite's planned
calls by `1 + max_reruns` and refuses to start when the answer is over budget —
before spending anything, which is the only moment a budget means something.

The cadence is stated in both places because GitHub reads `schedule:` from the
YAML and nothing else. `loop.py` fails loudly when the two disagree, so the
field a reader is most likely to edit cannot quietly become decoration.

## The interactive path

`.mcp.json` points `digline-mcp` at this directory. Open a coding agent here and
it has six tools — list the runs, read one, read the baseline, compare, diff,
run — and no seventh. `operator-prompt.md` is what to hand it.

That is the same operator, driven by a person instead of by cron: same rules,
same boundary, same absent `promote`.

## Make it yours

Fork the directory. Then, in order:

- **Point it at your endpoint.** Replace `fake.py` with an `HttpTarget` at your
  service, or with your own function. Delete `OPERATOR_SCENARIO` from
  `.github/workflows/operator.yml` while you are there — there are no scenarios
  in a real system.
- **Promote your own baseline.** Run the suite a few times, read the table, and
  promote the run whose per-case profile is closest to typical. Never the first
  green one.
- **Change the cadence**, in `operator.toml` and in the workflow, together.
- **Turn escalation on** when you trust what it is telling you: set the
  repository variable `OPERATOR_ESCALATE` to `true`. Until then the alert is
  written to the job summary and uploaded as an artifact on every cycle, and no
  issue is opened. A loop that escalated the day you forked it would teach you
  to ignore it by the third week.

One thing to decide with your eyes open: the deterministic half runs entirely
inside your perimeter, but the judgment layer on a hosted runner means your
model key lives in GitHub Actions secrets and the reasoning happens there. If
that is a perimeter you do not want, run the loop on a self-hosted runner or
from your own scheduler beside the application — the scripts here do not care
which started them.

The design behind all of this is at https://digline.dev/product/operator/ and
in `DESIGN.md` beside this file, which is the contract this assembly was built
against.
