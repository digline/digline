# `digline record` — the calls your application makes, kept as cases

While an application is being built, the calls it makes to a model are the
material a suite is made of. The recorder keeps them, at the place where the
application makes them, in the shape a suite reads: what the call was asked,
what decided how it answered, and what it answered. A person then reads them
back and names the ones that become cases.

It is three things:

- **`digline.recorder.wrap`**, around the provider's own client, in the
  application;
- **a switch**, `.digline/<tenant>/recorder.toml`, and `digline record on`,
  `off` and `status`;
- **`digline record import`**, which lists a suite's recorded cases and writes
  the ones a person names into a file the suite loads.

The decision behind it is
[ADR 0058](adr/0058-the-recorder-a-call-recorded-where-the-application-makes-it.md),
and the rules the import follows are [ADR 0023](adr/0023-capture.md)'s.

## Wrapping the client

```python
import anthropic
import digline.recorder as recorder

client = recorder.wrap(anthropic.Anthropic(), app="helpdesk", tenant="acme")

reply = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=200,
    system="Give the category of the ticket.",
    messages=[{"role": "user", "content": ticket}],
    suite="category",
)
```

- **`app=`** names the application. It is written on every recording.
- **`tenant=`** is the tenant the recordings are filed under,
  `.digline/<tenant>/recordings/`. A name is **development**: one tenant,
  fixed. A function, called at every call, is **production**: each customer's
  calls are filed under that customer's tenant.
- **`root=`** is the directory that holds `.digline/`, the current directory
  if left out.
- **`suite=`**, on the call, is the name of the suite the call belongs to:
  the same name as that suite's `Suite(name=...)`. It is a name, where
  `--suite` on the command line is a path to the suite's file. A call that
  names no suite is recorded under `_unassigned`, with the function it was
  made from, and enters no suite until a person gives it one.
- **`digline_vars=`**, on the call, adds the variables a template was filled
  with to the case, beside the messages, where the user message mixes a
  template and the data.

`suite=` and `digline_vars=` are taken out of the call before it reaches the
provider's SDK, whether the recorder is on or off. The client returned is the
client: everything but the call is its own.

The clients recorded are the ones a plugin maps: `anthropic.Anthropic`'s
`messages.create` with `digline-anthropic`, `openai.OpenAI`'s
`chat.completions.create` with `digline-openai`, and a `bedrock-runtime`
client's `converse` with `digline-bedrock`. Any other client is refused when
it is wrapped, by name. A streamed call (`stream=True`) passes and is not
recorded, and an asynchronous client is not recorded yet.

**The application's call never fails because of the recorder.** Whatever goes
wrong while recording, the call returns what the provider returned, and the
reason it was not recorded is counted (below). An exception of the SDK itself
propagates as it always did.

## A turn of an agent: `episode`

```python
with recorder.episode(client, suite="order-agent", case={"ticket": ticket}) as ep:
    first = client.messages.create(..., tools=tools, suite="order-agent-step")
    result = run_the_tool(first)
    second = client.messages.create(..., tools=tools, suite="order-agent-step")
    ep.output(second.content[0].text)
```

An episode is one recording for the whole turn, with the calls made inside it
attached to it.

- **`case=` is required**: the input that started the turn, a mapping of
  names to JSON values, as the case will hold it. Two turns with the same
  `case` are the same case at the import.
- **`ep.output(...)`** is the turn's final answer. Without it, the episode's
  answer is the text of the last model call made inside it.
- Its trajectory is a list of steps: one `model` step per call, then a `tool`
  step per tool the model asked for. The recorder never sees what your tool
  returned, so a tool step says its result was `not_reported`.
- An exception inside the block propagates as it was raised, and the episode
  is still written with what was seen, marked `interrupted`.
- A call made in another thread or process does not inherit the episode. Pass
  `ep.id` there and wrap the call in `recorder.attach(...)`:

```python
def lookup(order, episode_id):
    with recorder.attach(episode_id):
        return client.messages.create(..., suite="lookup")

with recorder.episode(client, suite="order-agent", case={"ticket": ticket}) as ep:
    pool.submit(lookup, "A1", ep.id).result()
```

A call made with no episode while one is open in the process is recorded as
an **orphan**: the recorder cannot tell a child that was not attached from a
call that belongs to no episode, and it attaches neither.

## Switching it on

Off is the default, and off costs one comparison per call.

**In development**, either:

```console
$ DIGLINE_RECORD=1 python app.py
$ digline record on --tenant acme
```

The variable records with the defaults. `digline record on` writes
`.digline/<tenant>/recorder.toml`, which wins over the variable wherever it
exists, and prints every value the file now holds. A value written before
stays until it is changed: `record on` with no option switches on and keeps
the rest, and `record off` switches off and keeps the rest.

| Key | | Development default |
|---|---|---|
| `on` | `true` or `false` | required |
| `sample` | the share of calls recorded, above 0 and at most 1 | 1 |
| `redact` | `"none"`, the one implemented | `"none"` |
| `ceiling` | the bytes the tenant's recordings may reach | 100 MiB |
| `interval` | seconds between two looks at the file | 5 |
| `production` | the file is held to the production rules | `false` |

Any other key is refused by name. The file is looked at again at the interval,
so a change takes effect without a restart. An episode is sampled once: its
calls are in or out with it. At the ceiling the recorder stops recording for
that tenant and says so in the status; it never rotates or deletes.

**In production** (`tenant=` is a function), a file that switches a tenant on
must declare `redact`, `sample` and `ceiling`, and the tenant's directory must
be writable. Otherwise the client is refused when it is wrapped, and the
refusal names each missing declaration. `DIGLINE_RECORD=1` is refused there:
it declares neither redaction nor sampling.

```console
$ digline record on --tenant acme --production --sample 0.1 --redact none --ceiling 500000000
```

**In development a switch file that is invalid does not stop the
application.** The recorder says why on standard error, once, and records
nothing for that tenant until the file is right.

The switch file and the recordings are ignored by git, in the `.gitignore`
digline writes under `.digline/`.

## What was recorded, and what was not

```console
$ digline record status
$ digline record status --tenant acme --suite eval/suite.py --json
```

For each tenant: whether it records and with which values, where, the size
against the ceiling, and per suite the single calls (with how many were made
inside an episode), the episodes, the orphans, and **what was not recorded,
by reason**: `not JSON` for a request a recording cannot hold, `sampled out`,
`ceiling`, `streaming`, `config invalid` and the rest. Each process keeps its
counts beside its recordings, so the status reads them from any process. With
`--suite`, it also says how many recordings the suite gained since its last
import. In the application, `client.digline_counts` gives the counts of that
client, in that process.

## From recordings to cases: `digline record import`

The suite declares where its captured cases go, in a `suite.py`, and loads
that file beside its own cases:

```python
from pathlib import Path

from digline.host import read_cases
from digline.run import CaptureSource, Case, Suite

HERE = Path(__file__).parent

suite = Suite(
    tenant="acme",
    environment="dev",
    name="category",
    assertions=[...],
    cases=[*my_cases, *read_cases(HERE / "captured.json")],
    capture=CaptureSource(cases_file="captured.json", repository="private"),
)
```

`repository` has no default. `"private"` says the file is readable only inside
the perimeter of whoever owns the text, and the input is written whole.
`"public"` says it is not: the import lists and refuses to write, because a
recorded case is that text. A suite that declares `capture` and does not load
its file is refused when it is loaded, naming the cases it left out. A
`suite.toml` cannot declare `capture` in this release.

Then two invocations:

```console
$ digline record import --tenant acme --suite eval/suite.py
$ digline record import --tenant acme --suite eval/suite.py --positive cap-… --negative cap-…
```

The first lists and writes nothing. For each case: its id, its input, and
what it answered under the setup in force. Recordings under earlier setups are
counted and shown, and cannot be elected. Orphans, interrupted episodes and
recordings over the ceiling of what a recording keeps are counted, and are
never cases. The order is the files' order: nothing is ranked or preselected.

The second writes the cases named, each with the label given, and no other. A
case not named stays out. The case written carries the input and the label,
never the recorded answer as an expected. The import writes the file and
stops: the diff is the review, the commit is the signature. The next
`digline run` runs the new cases, and `digline compare` reports them as new
against a baseline that never saw them.

Recordings of another tenant than the suite's are refused before anything is
shown: bringing one tenant's material into another's suite is the bridge,
which is planned and not built, and until then the recordings stay in the
perimeter [ADR 0034](adr/0034-the-store-outside-and-the-reference-that-names-nothing.md)
§1 keeps them in.

## Not yet

- Streaming and asynchronous clients.
- An application in another language than Python.
- A label given at the import is a case's `label`, read by an aggregate that
  counts a confusion matrix; a run's results do not show it yet.
