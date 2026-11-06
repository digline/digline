# `digline suggest` — a first suite, proposed

A first suite is the hard part: which checks, which numbers, which cases.
`digline suggest` reads what your application recorded, what a person said
about its answers and what your runs measured, and writes a first suite into
one file, `suite.proposed.toml`. It proposes; you decide. Nothing in the file
is a verdict, no answer is marked, and no command of digline reads it until
you copy its lines into your suite.

The reasoning is [ADR 0063](adr/0063-suggest-a-first-suite-proposed-and-never-marked.md).

## Running it

For a suite you already have, which declares where its captured cases go
(`[capture]`, [the suite as data](declarative.md#capture)):

```console
$ digline suggest --suite eval/suite.toml
```

The proposal is written beside the suite, as `eval/suite.proposed.toml`. A
`suite.py` works the same way, and its proposal is TOML too: you translate
its lines into Python.

For a suite that does not exist yet, give its name, the tenant its recordings
are filed under, and where its captured cases may live:

```console
$ digline suggest --suite triage --tenant acme --repository private
```

The proposal is written in the directory you run from. `--tenant` and
`--repository` are mandatory here, with no default: there is no suite to read
the tenant from, and whether the cases file stays inside the perimeter of
whoever owns the text, `"private"`, or not, `"public"`, is yours to say
([`record.md`](record.md#from-recordings-to-cases-digline-record-import)).
Where the suite exists, `--repository` is refused: its capture already
declares the regime.

`--suite` is read as a suite when it is a file that is there, a path ending
in `.py` or `.toml`, or `module:attribute`. Anything else is the name of a
suite that does not exist yet, and is never imported.

A `suite.proposed.toml` already there is never overwritten: the command
refuses and names it, and you move it or delete it. What you wrote in a
proposal is not the command's to throw away.

## What it reads

- **The suite's recordings**: every recording whose `suite` names the suite,
  in every process directory of the tenant, through the same functions
  `digline record import` reads them with. The calls that named no suite,
  `_unassigned`, are counted and never read for anything else: a proposal made
  from them would give them a suite, and that is yours to do, with
  `digline record import --from _unassigned`.
- **The reviewed answers** in the cases file the suite's capture names: a
  person's yes or no. They are counted, and a no is the counterexample (below).
- **The suite's runs**, where there are any, for the limits.

With no recording and no reviewed answer it writes nothing, and says where a
suite begins: `digline record on`, which is yours to run.

## What it proposes

**Checks, only from a rule every recording holds.** Every case of a suite is
asked every check ([ADR 0010](adr/0010-per-group-aggregates.md) §5), so a
check one recording contradicts would fail that case. One recording that
breaks a rule takes the check out.

| The recordings | The check |
|---|---|
| every answer is text that parses as JSON | `is_json`, and a draft `json_schema` that requires the keys every answer carries |
| every answer is a structure | a draft `json_schema` |
| every answer is text | `length` |
| every one calls the same tools in the same order | `tools_called` |
| otherwise, two or more tools in one order common to all | `subsequence` |
| every call to one tool has a call to another before it | `before` |
| a tool declared to the model and called in none: under the setup's `tools`, by `name` or `function.name`, or under Bedrock Converse's `toolConfig`, by `toolSpec.name` | `never` |
| an agent's episodes | `max_steps` over the model's turns |
| every one carries a cost, or a latency | `cost_budget`, `latency_budget`: the target you declare has to report it too |

Answers of more than one kind hold no shape in common, and no shape check is
proposed from them. A tool call nobody named takes out every check that names
a tool, since it may be any of them. A check the suite already declares, by
name, is not proposed again.

**The judged check the capture reviews answers for**, where the suite does
not declare it: `llm_rubric`, wrapped in `repeated` with three samples and
`"2/3"`, the starting point of [the guide](guide.md), chapter 3. Its rubric
and its judge are yours to write: the judge is written as `"provider/model"`,
which no plugin is, so the suite refuses to load until you name one.

**Limits**, read from the runs where they measured them: the longest answer,
the most model turns, the highest cost and latency, a check's lowest score.
Where no run measured a limit, it is a **placeholder**: the strictest value
the check accepts, marked `# placeholder` in the file. A placeholder fails
until you write a measured number, and is never a default that passes. A
threshold goes where the system measurably is, which takes several runs
([the guide](guide.md), chapters 4 and 5).

**A counterexample**, because a suite that cannot fail measures nothing. The
reviewed noes for the judged check, where there are any, named by id: they
are already in your cases file, and the check must fail them. Otherwise a case
constructed and marked as constructed, `counterexample-1`, written as a line
to paste into a cases file, whose input is yours to write: one whose answer
the check must refuse.

**A calibration skeleton**, where the suite has no calibration case for the
judged check: the answer to paste, one you know is partly right, and the band
to place, strictly between 0 and 1
([Calibrating a judge](calibration.md)).

**No case is chosen, and no answer is chosen for review.** The command says
how many recordings and answers are not yet examined, by group, and the
command that examines them. Choosing which recordings become cases is a
pre-selection, which [ADR 0023](adr/0023-capture.md) §4 forbids.

## What it says

On standard error, what it assumed, in the words of the fifth step of
[the method](proposing-a-suite.md): the form, the setup its target
reproduces, the judge, each check and each starting number, the calibration
band, the counterexample. Then the counts. Standard output stays empty.

What it says is digline's own words: kinds, counts and the names of checks.
**No recorded text reaches either stream**, under either regime: not an
input, not an answer, and not a tool's name or a key read from a recording.
Those last two are the rules, and they are in the file's checks.

## What it never does

It never writes a reviewed answer, a `good`, a `--by`, a label or a
promotion, and it writes no file but `suite.proposed.toml`. Your suite and
its cases file are byte for byte what they were, and the suite loads to the
same `config_hash`. The yes and the no are yours, and so is the commit.

The file quotes no recorded input or answer, under either regime: it holds
the rules read from the recordings and the placeholders you fill. A file of
proposal stands where the suite's capture says its cases may
([ADR 0023](adr/0023-capture.md) §8).

## Not yet

- **An assistant**: a model of its own, declared under `[suggest]`, that
  drafts a rubric, says why each check is there and fills the placeholders.
  [ADR 0063](adr/0063-suggest-a-first-suite-proposed-and-never-marked.md) §4
  rules it, and it is not built.
- A `--json`, an MCP tool, and a view at the page.
