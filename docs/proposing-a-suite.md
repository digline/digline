# Letting an agent propose a suite

A first suite is the hard part: which checks, which numbers, which cases. If
you already work with a coding agent, it can propose one by digline's method,
from what your application recorded and what you said about its answers. It
proposes; you decide.

Without an agent, the first step is a command:
[`digline suggest`](suggest.md) reads the same recordings, reviewed answers
and runs, and writes a first suite into `suite.proposed.toml`, with its
counterexample and the numbers it could not know marked as placeholders. An
agent starts from that file too.

The method is the `proposing-a-suite` skill, shipped in the Claude Code plugin
at `plugins/digline/skills/proposing-a-suite/SKILL.md`, and written into
[`AGENTS.md`](https://github.com/digline/digline/blob/main/AGENTS.md) for any
other agent that reads that file. In five steps it reads what is there
(`digline suggest` first, then `digline record status`, the grouped listing of
[`digline record import`](record.md#from-recordings-to-cases-digline-record-import),
your reviewed answers), chooses the checks from the tree in
[the metrics](metrics.md#choosing-one), writes the suite in the form
[the suite as data](declarative.md) says fits, runs it once with `digline run`
and `digline explain`, and hands it to you.

Three rules hold whatever the agent:

- **It proposes, and never marks.** A yes or no about an answer, a label, a
  promotion and an import are yours. The agent writes no `--good` or `--bad`,
  promotes nothing and imports nothing, and where the judge contradicts one of
  your reviewed answers it says so rather than adjusting the judge until it
  agrees: your answer is the expected verdict
  ([ADR 0023](adr/0023-capture.md),
  [ADR 0037](adr/0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)).
- **Always a counterexample.** A suite that cannot fail measures nothing, so
  the proposal carries at least one case it fails on: one of your noes, or a
  case it constructed and names as constructed.
- **You commit.** The agent leaves the files in your working tree with a
  summary of what it assumed: the form, the setup its target reproduces, the
  judge, each check and each starting number, the calibration band, the
  counterexample. The diff is your review, and the commit is your signature.

Its numbers are starting points. A threshold goes where the system
measurably is, which takes several runs ([the guide](guide.md), chapters 4
and 5), and a calibration band is yours to place
([Calibrating a judge](calibration.md)).
