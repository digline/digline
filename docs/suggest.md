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

With `--model provider/model`, an assistant writes into the proposal what the
rules leave as placeholders (below).

The proposal is written in the directory you run from. `--tenant` and
`--repository` are mandatory here, with no default: there is no suite to read
the tenant from, and whether the cases file stays inside the perimeter of
whoever owns the text, `"private"`, or not, `"public"`, is yours to say
([`record.md`](record.md#from-recordings-to-cases-digline-record-import)).
Where the suite exists, `--repository` is refused: its capture already
declares the regime.

`--suite` is read as a suite when it is a file that is there, a path ending
in `.py` or `.toml`, or `module:attribute`. Anything else is the name of a
suite that does not exist yet; digline does not look for one, and stops if
that name already has runs. A name is never imported.

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
suite begins: `digline record on`, which is yours to run. Where the tenant's
recorder is already on and no call named the suite, it says so instead, and
names the suites the calls did name.

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

**For a suite that does not exist yet, `[suite]` asks the target three
times**, `samples = 3` with `min_agreement = "2/3"`: a reviewed answer needs
the target asked at least twice
([`record.md`](record.md#from-recordings-to-cases-digline-record-import)), and
three is the starting point that leaves room for one sample to disagree.

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
the check must refuse. It is answered by the target, so the suite needs a
`[target]`.

**The cases file**, for a suite that does not exist yet, is the capture's,
`captured.json`, and the file says so beside `cases`: it is written by
`digline record import`, and until then the suite has no case.

**A calibration skeleton**, where the suite has no calibration case for the
judged check: the answer to paste, one you know is partly right, and the band
to place, strictly between 0 and 1
([Calibrating a judge](calibration.md)).

**No case is chosen, and no answer is chosen for review.** The command says
how many recordings and answers are not yet examined, by group (the shape of
the answers, as `record import` lists them), and the command that examines
them. Choosing which recordings become cases is a
pre-selection, which [ADR 0023](adr/0023-capture.md) §4 forbids.

## The assistant

A model of its own, never the suite's judge, asked once for what the rules
cannot know: a rubric for the judged check, a sentence on why each check is
there, limits in place of the placeholders, and a counterexample. It is
declared, or nothing is called:

```toml
[suggest]
model = "anthropic/claude-haiku-4-5"
```

in a `suite.toml`, by coordinates as [a judge is](declarative.md#the-judge-by-coordinates),
or with `--model`, which wins over it. A `suite.py` and a suite that does not
exist yet take `--model` alone. `[suggest]` is outside the suite: no run reads
it, and the suite's `config_hash` is the same with it or without it.

**What it costs is said before the call**, and not asked:

```console
$ digline suggest --suite eval/suite.toml --model anthropic/claude-haiku-4-5
assistant: anthropic/claude-haiku-4-5, from --model
assistant: 1 call to anthropic/claude-haiku-4-5, 42 recordings and 7 reviewed answers, about 31,000 input tokens (at the ratio the suite's recordings report) and at most 4,000 output; at most $0.05
```

The figures above are an example. The input tokens are estimated at the ratio
of tokens to characters that the suite's recordings report, or at 4
characters a token where none reports one, which is a convention and is said
as one. A model the plugin's price list does not know is refused before the
call: the judge's call it goes through refuses a reply it cannot price, once
that reply is paid for.

**What it reads follows the capture's regime:**

- **`"private"`**: the suite's recordings, their input, answer, kind and
  steps, and the reviewed answers, whole. That is at most 50 recordings and
  200,000 characters, the newest of the setups in force first, each whole and
  never cut; standard error says how many were left out.
- **`"public"`**: the shape, not the text. That is the kinds, the finishes,
  the tools declared and called, the checks already proposed, which carry the
  JSON keys and the regularities of the steps, and counts, of the reviewed
  answers how many yes and how many no. No input, no answer and no step's
  arguments reach it.

The calls no suite named are never given to it, under either regime.

**What it writes is merged, never obeyed.** It names the checks the proposal
already holds, and may write into them:

- a rubric for a judged check;
- a sentence of why beside a check;
- a limit in place of a placeholder, or stricter than one a run measured;
- a counterexample: an input and the answer the suite must refuse.

Each is marked as the assistant's in the file. These are discarded, and
standard error counts each by reason:

- a check of its own;
- a key outside the reply's form, `[capture]` or a case among them;
- a limit less strict than the runs measured;
- a value its check does not accept.

A reply that is no JSON object is not used at all. Its counterexample is asked
of the checks that need no judge, and where none refuses it, standard error
says that only the judge can.

## What it says

On standard error, what it assumed, in the words of the fifth step of
[the method](proposing-a-suite.md): the form, the setup its target
reproduces, the judge, each check and each starting number, the calibration
band, the counterexample. Then the counts. Standard output stays empty.

Where the suite's recordings were made under more than one setup, it names
each beside the one in force, and the `digline record compare` command that
shows the keys two of them differ on. The provider plugins installed are
named beside the judge, which is yours to choose.

What it says is digline's own words: kinds, counts and the names of checks.
**No recorded text reaches either stream**, under either regime: not an
input, not an answer, and not a tool's name or a key read from a recording.
Those last two are the rules, and they are in the file's checks.

## What it never does

It never writes a reviewed answer, a `good`, a `--by`, a label or a
promotion, and it writes no file but `suite.proposed.toml`. Your suite is
not rewritten, and neither are its limits: a placeholder you adopted stays
until you replace it, and on the next run the command counts those still at
their most severe value. Your suite and its cases file are byte for byte what
they were, and the suite loads to the
same `config_hash`. The yes and the no are yours, and so is the commit.

Without an assistant, the file quotes no recorded input or answer, under
either regime: it holds the rules read from the recordings and the
placeholders you fill. With one under `"private"`, the assistant's text may
quote what it read. A file of
proposal stands where the suite's capture says its cases may
([ADR 0023](adr/0023-capture.md) §8).

## Over MCP

The MCP server's `suggest` tool returns what this command says, as facts, and
the command that writes the file: it writes nothing, because the server writes
nothing into your repository. It asks no assistant there: what one costs is
said before its call, and a tool has no before, so the command with `--model`
is in its answer for you to run ([digline over MCP](mcp.md)).

## At the page

`digline view` shows the file read only, on its *Proposal* view: what it
declares, each check with why it is there, the placeholders marked as such and
a value the assistant wrote marked as not measured, the counterexample and the
calibration skeleton, and the command that writes one, without and with
`--model`, to copy. No button asks a model: what one costs is said before its
call. `digline where` names the file in the state `no_suite_yet`, by its path
([`digline view`](view.md#the-recorders-views)).

## Not yet

- A `--json`.
