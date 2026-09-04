# `digline diff` — two runs, neither of them a baseline

`digline compare` answers **did it get worse?** It holds a run against the
baseline, the baseline is an *approved reference*, and the exit code gates your
pipeline on the answer.

`digline diff` answers a different question: **should I switch?** Prompt A or
prompt B. `claude-haiku-4-5` or `gpt-5-mini`. Temperature 0.3 or 0.7. Two
candidates, both measured, and **neither approved by anybody** — because
approving one of them is the decision you are trying to make.

It is a **report, never a verdict.** It always exits 0 on a completed report,
whatever the report says. Nothing about it gates anything, and that is not a
missing feature: a verdict exists only against an approved reference, and a tool
that exited 1 because run B scored lower than run A would be asserting that A
was the standard — which is exactly the thing nobody decided. The reasoning is
in [ADR 0008](adr/0008-the-two-run-report.md).

## Using it

Two run keys, in either order:

```console
$ digline diff --suite suite.py 2026-09-04T13-55-47-725244-00-00-331b1cfd9709f0cd latest
2026-09-04 13:55  2026-09-04T13-55-47-725244-00-00-331b1cfd9709f0cd  staging
2026-09-04 13:56  2026-09-04T13-56-48-910510-00-00-331b1cfd9709f0cd  staging

  The systems differ: temperature 0.3 vs 0.7.

2 of 2 checks differ: 2 favour 2026-09-04 13:55. 2 of 2026-09-04 13:55's advantages exceed both runs' observed intervals.

how-do-i-return · llm_rubric · 2026-09-04 13:55 0.950000, 2026-09-04 13:56 0.800000. Observed intervals 0.900000–1.000000 across 3 samples and 0.750000–0.850000 across 3 samples do not overlap.
where-is-my-order · llm_rubric · 2026-09-04 13:55 0.950000, 2026-09-04 13:56 0.800000. Observed intervals 0.900000–1.000000 across 3 samples and 0.750000–0.850000 across 3 samples do not overlap.
```

`latest` resolves on either argument, the same as everywhere else.

The two runs are bound to their labels on the first two lines, and everything
below names them by label. **Swapping the arguments swaps the columns and
nothing else** — the same checks, the same counts with the two "favour" figures
exchanged, the same intervals, the same refusal or lack of one. There is no
"reference", no "before" and "after", no "regressed" and "improved", because
none of those words is true of two runs neither of which was approved.

The report **opens by naming what differs about the systems**, before it says
what that did to the scores. That is why you opened it.

## The strongest sentence it will say

> 2 of 2026-09-04 13:55's advantages exceed both runs' observed intervals.

Read it carefully, because it is deliberately weaker than it could be. It does
**not** say the 13:55 run is better. It says that on two checks that run scored
higher, *and* the two runs' measured min–max intervals do not overlap — so the
difference is larger than the wobble either run showed on its own.

It appears only where both sides were sampled, since an interval needs
[repeated samples](adr/0006-repeated-samples-and-the-noise-floor.md) to exist.
A check sampled on one side and not the other is still counted as differing, and
is left out of this figure: there is no second interval for the first to be
disjoint from. When no pair was measured on both sides — a suite at `samples=1`,
which is most suites — the sentence is **not printed at all**, rather than
printed as "0 of …", which would report an absent measurement as a null result.

Where two intervals **do** overlap, the row says so:

> Observed intervals 0.700000–0.990000 across 5 samples and 0.600000–0.950000
> across 5 samples overlap, so these two are not distinguishable by this check.

That note is evidence beside the count, **not an excuse**. The difference is
still counted. This is the one place `diff` parts company with `compare`: there,
a movement inside the baseline's interval is reported as unchanged, because the
baseline is the promoted, reviewed measurement and has the standing to say what
its own noise is. Here neither run has that standing, so no interval is allowed
to overrule a difference — it is reported beside it and you weigh it.

## What it refuses

Two runs are only worth diffing if they were measured the same way. Two
refusals, both exiting `64` like any other usage error:

**Different rules.** The two runs must share a `config_hash` — the same
assertions, the same thresholds, the same tolerances, the same `samples`.

```console
$ digline diff --suite suite.py <run-a> <run-b>
digline: DifferentSuitesError: the two runs were produced under different suites (config_hash 331b1cfd9709f0cd against 8c1d0a44be71f209): a diff between them would compare the rulers, not the systems — re-run one side under the other's suite
```

You will meet this one. Tuning a threshold between two candidate runs moves the
hash, and the two runs then measure against different bars.

**Different judges.** The set of `provider/model` identities that graded must
match. A judge that moved is a *scale* that moved, and a difference measured on
two scales is not a difference.

```console
$ digline diff --suite suite.py <run-a> <run-b>
digline: DifferentJudgesError: the two runs were graded by different judges (anthropic/claude-haiku-4-5 against openai/gpt-5-mini): the instruments differ, so a difference between these scores is not a difference in the systems — re-run one side under the other's judge
```

A suite that declares no judge at all — `Contains`, `Regex`, `JsonSchema`, or a
plain function — records no identity on either side, and diffs fine. But a run
that recorded a judge against one that recorded none is **also** refused: it
cannot be established that the two were graded by the same instrument, and
"cannot be established" is not the same as "they match".

**The target is free**, and that freedom is the whole feature. Two models, two
temperatures, two prompts, two endpoints — that is the question `diff` exists to
answer, so it is never a refusal.

## `--json`

```console
$ digline diff --suite suite.py --json counts <run-a> <run-b>
```

`--json counts` gives the figures; `--json full` adds every check and the
configuration deltas. The value is **mandatory**, unlike `compare --json`: this
command takes two positional run keys, and an optional-valued flag in front of
them makes the argument parser swallow the first key.

The structure is symmetric — `runs.left` and `runs.right`, `favours_left` and
`favours_right`, `left_exceeds` and `right_exceeds` — and **there is no `worse`
field**. Its absence is the point, not an omission: there is nothing here for a
pipeline to gate on, which is why `diff` is a separate command rather than a
flag on `compare`. If you want a gate, use `compare`; that is what a gate is
for.

```json
{
  "counts": {
    "differing": 2, "favours_left": 2, "favours_right": 0,
    "within_tolerance": 0, "only_left": 0, "only_right": 0, "errored": 0,
    "interval_pairs": 2, "left_exceeds": 2, "right_exceeds": 0, "total": 2
  },
  "judges": [],
  "output_version": 1,
  "systems_differ": true,
  "suite": "support",
  "tenant": "northwind"
}
```

## In the view

`digline view` chooses on the same rule. Comparing a run **against the
baseline** — including the default, where you pick no second run — still gives
you the verdict document: that is a run held against an approved reference, and
"did it get worse?" is the right question to ask of it.

Comparing it against **any other stored run** gives you this report instead.

Before ADR 0008 that screen rendered the verdict for every pair, so two
candidates arrived under a heading asking *"Did it get worse?"* beside a column
called *Reference*. It was the diff's need served with the verdict's semantics,
and it shipped a release before the command that answers it properly.

## Which command do I want?

| | `compare` | `diff` |
|---|---|---|
| Question | did it get worse? | should I switch? |
| Against | the approved baseline | another run |
| Exit code | 0 / 1 / 2 — **it gates** | always 0 — it reports |
| Refuses | nothing (it reports and never fails) | different rules, different judges |
| An interval can | call a movement unchanged | note that two runs are not distinguishable |
| `--locale` | defaults to `en` | defaults to `en` |

If you find yourself promoting a candidate, comparing, and promoting back —
stop. That writes into `.digline/<tenant>/baselines/`, which is committed, and
it puts a decision nobody made into somebody's pull request. That workaround is
what this command replaces.
