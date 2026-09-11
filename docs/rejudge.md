# `digline rejudge` — judging stored answers again

Change the judge, or the rubric, or a threshold, and you want to know what the
*same answers* would have scored. Until 0.10.0 the only way to find out was to
pay the target for answers nobody doubted.

`rejudge` reads a stored run, replays the answers it recorded through the
**current** suite, and writes a run that says where the answers came from.

```console
$ digline rejudge --suite eval/suite.py --run latest
digline: 12 cases × 1 recorded answer = 12 answers replayed; no call to the target
2026-09-11T14-02-55-018244-00-00-6f2a1c4e5b7d9a01
```

## First, the suite has to record

Nothing is recorded unless the suite asks, and a run already produced cannot
gain answers nobody kept:

```python
suite = Suite(
    tenant="acme-bank",
    environment="staging",
    name="qa",
    assertions=[...],
    cases=[...],
    record_responses=True,
)
```

One line in `[suite]` for a data suite. It does **not** change `config_hash`, so
turning it on costs no baseline and no re-promotion — recording changes no
score, pairs no verdict differently and moves no bar.

What lands in the run file, per case and per sample: the answer, the rendered
prompt that produced it, and what that call cost in money and in milliseconds.
The prompt is recorded because most assertions that call a model read it — a
stored answer with no stored question cannot be judged again.

## Why not a cache

The field's usual answer to this is a response cache: a hidden directory, keyed
by something like the request, consulted before the provider is called. It is a
good engineering trade and a bad instrument. A cache returns an old answer *as
though it were a new one* — nothing in the resulting document says the model was
never asked, so a suite can go green against answers produced by a model that
has since been replaced.

A re-judged run says so, in the document, in the headline sentence, in
`compare --json`, and on the report a customer reads:

> The answers in this run were replayed from a stored run, not measured: the
> target was not asked anything.

## What it carries, and what is fresh

| | |
|---|---|
| the judge's configuration | **measured now** — the judge really ran, and it is what is under examination |
| the target's configuration, the artifacts | **carried from the source** — they describe the system and the prompt that produced these answers |
| `created_at`, `git_commit`, `digline_version` | fresh: this evaluation is happening now |
| `config_hash` | the current suite's — the rules moving is the point |
| `rejudged_from` | the key of the run the answers came from |

## The four refusals

Each one arrives before the first judge is paid, and each names what is missing.

1. **The stored run recorded no answers.** Recording is opt-in, so this is the
   ordinary first encounter: set `record_responses=True` and run it again.
2. **A case has no recorded answer.** A case added since the run was produced
   cannot be re-judged from it, and judging the rest would be a narrower
   measurement carrying the declared suite's name.
3. **An answer is withheld or over the size ceiling.** A partial replay is a
   weaker measurement claiming to be the declared one — the rule the driver
   already applies when one call of a sampled case fails. The ceiling is 65 536
   characters per field, and over it the run records neither the answer nor the
   prompt rather than half of either: a clipped answer re-judged produces a
   score that looks like every other score.
4. **The sample count does not match.** A replay at one count over a run taken
   at another is a different measurement wearing the suite's name.

## A replay is not promotable

```console
$ digline promote --suite eval/suite.py --run 2026-09-11T14-02-55-…
digline: ReplayedRunError: run … was judged from the recorded answers of …,
not from the target.
```

A replay has **zero target variance** by construction: the answers are fixed, so
the interval it records is the judge's wobble alone. Promoted, it would become
the reference every future real run is measured against — and a movement is
judged against the *baseline's* interval, so every ordinary wobble of the target
would then read as a movement beyond the noise. A replay promoted as a reference
is a noise floor measured without the noise.

It is the fourth condition on promotion, beside the three that were already
there: the tenant must be the perimeter, the configuration must match, the run
must have judged every case — and the answers must have been measured.

## Where the answers stay

In `.digline/<tenant>/runs/`, which is gitignored. They do not leave:

- `digline report --redacted` and every MCP response carry the verdicts and not
  the answers. No `Disclosure` releases them, and none can be added — a judge's
  `reason` is already withheld *because it quotes the output*.
- `digline promote` strips them. `baselines/` is committed, and a reference of
  verdicts has no business carrying the model's answers into a git history.

## See also

- [`api.md`](api.md) — `Suite.record_responses`, and what a re-judge needs
- [`adr/0015-the-recorded-output-and-the-declared-re-judge.md`](adr/0015-the-recorded-output-and-the-declared-re-judge.md) — the record
- [`adr/0002-three-worlds-and-where-the-data-lives.md`](adr/0002-three-worlds-and-where-the-data-lives.md) — the payload stays where it is born
