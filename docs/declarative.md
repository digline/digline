# The suite as data

A suite can be a `suite.py` or a `suite.toml`. The extension chooses; there is
no flag. Both build the same objects and run through the same engine, and a
suite ported from one to the other keeps its baseline.

Reach for the TOML form when the suite is plain data — cases, checks,
thresholds, an endpoint — and nobody on the team writes Python. Reach for the
Python form when it is not, which the next-to-last section names exactly.

The reasoning behind every rule here is
[ADR 0007](adr/0007-the-declarative-suite-format.md).

## The two files

A suite is always two files. The rules and the data change at different rhythms,
usually by different hands, and a diff has to say which one moved.

```toml
# suite.toml
[suite]
tenant = "northwind"
environment = "staging"
name = "support"
cases = "cases.json"

[target]
type = "http"
url = "http://127.0.0.1:8730/answer"
output_path = "data.answer"
cost_path = "usage.cost_usd"

  [target.body]
  question = "case.vars.question"

[[assertions]]
type = "contains"
needle = "Northwind Support"

[[assertions]]
type = "cost_budget"
max_usd = 0.02
tolerance = 0.05
```

```json
[
  {"id": "where-is-my-order", "vars": {"question": "Where is order 4821?"}},
  {"id": "how-do-i-return",   "vars": {"question": "How do I send it back?"}}
]
```

Then the cycle you already know:

```console
$ digline run     --suite suite.toml
$ digline promote --suite suite.toml --run latest
$ digline compare --suite suite.toml --run latest
```

A complete, runnable version of this is in `examples/quickstart-toml/`, with the
application it talks to.

**Every relative path is relative to the suite file**, never to the directory
you happen to run from: `cases.json` sits beside `suite.toml`, and so does the
prompt a `[target]` names.

## `[suite]`

The same names as `Suite`'s own fields, the same defaults, the same refusals.

| Key | |
|---|---|
| `tenant` | mandatory. The perimeter, and a directory: everything lands in `.digline/<tenant>/` |
| `environment` | mandatory, no default. Where inside the perimeter this ran — `staging`, `production` |
| `name` | mandatory. The suite's name, which is what a baseline is filed under |
| `cases` | mandatory. The cases file, always a file |
| `samples` | how many times to ask the target per case. Default 1 |
| `min_agreement` | mandatory as soon as `samples > 1`. Written as a count: `"2/3"` |
| `artifacts` | files that *are* the thing under test — a prompt above all |

`disclosure` is **not** settable here. See "What it cannot say".

A suite that samples without a floor, declares no assertions, repeats a case id
or asks for a ratio no sample count can produce is refused when it loads — with
the same sentence the Python form gives, because it is the same check running.

## `[[assertions]]`

An ordered list. `type` selects the check; every other key is passed to it as
its own parameter, and the parameters are the ones in
[`docs/metrics.md`](metrics.md) — this format adds none and renames none.

The order is kept, because it is the order the report shows.

```toml
[[assertions]]
type = "regex"
pattern = "^[A-Z]"
name = "starts_capitalised"
```

`name` is worth setting whenever a suite has two checks of one kind: it is what
the report prints and what a comparison pairs on.

**Per case:** `equals`, `contains`, `not_contains`, `affix`, `is_json`,
`json_schema`, `length`, `levenshtein`, `regex`, `llm_rubric`, `faithfulness`,
`pii_absent`, `cost_budget`, `latency_budget`, `repeated`.

**Per run:** `precision`, `recall`, `accuracy`, `f1`.

The token is the name the check already carries in a report and in a baseline,
so if you have read the output you can write the file.

### Aggregates go in the same list

They are written as entries like any other and land where they belong. `over`
names a **check's name**, not a type:

```toml
[[assertions]]
type = "precision"
over = "contains"
threshold = "9/10"
tolerance = "1/10"
```

A `threshold` that is really a count of cases is written as one. An `over` that
matches nothing is refused; so is one that matches two, and the fix is to give
one of them a `name`.

### `repeated` wraps another check

For judge noise: the same output graded several times.

```toml
[[assertions]]
type = "repeated"
samples = 3
min_agreement = "2/3"

  [assertions.inner]
  type = "llm_rubric"
  rubric = "Does the reply answer the question in at most three sentences?"
  judge = "anthropic/claude-haiku-4-5"
  threshold = 0.7
  tolerance = 0.05
```

`[assertions.inner]` is a check written the same way as any other — the rules
above, applied again.

## The judge, by coordinates

```toml
judge = "anthropic/claude-haiku-4-5"
```

`provider/model`. The provider half is the name a plugin registers under; the
model half is handed to that plugin untouched, so an identifier with slashes of
its own — a Bedrock inference profile ARN, say — arrives whole.

The plugin has to be installed: `uv add digline-anthropic`, or the equivalent
for `digline-openai` and `digline-bedrock`. Naming one that is not installed
tells you which package to install.

One coordinate answers for both kinds of judge. `llm_rubric` is given the
plugin's scoring judge and `faithfulness` its claim judge, because every plugin
ships both.

**No key appears in a suite file.** There is no `api_key` and there will not
be: a suite is a file that gets committed, and each provider's own SDK reads the
key from the environment. Set `ANTHROPIC_API_KEY` (or the equivalent) where the
run happens.

**A coordinate carries the instrument, not its settings.** The judge grades with
the plugin's own defaults. A judge that needs a different `max_tokens`, a
different temperature, or rules of its own is an object, and objects live in a
`suite.py`.

## `[target]`

Two forms, and there is no third.

### `type = "http"`

Your application, on the other end of a URL. It can be written in anything.

| Key | |
|---|---|
| `url` | mandatory |
| `output_path` | mandatory. Where the answer lives in the response, dotted |
| `cost_path` | where the application reports what the call cost |
| `latency_from_response` | where it reports its own time. Left out, digline times the round trip, which includes the network |
| `config_path` | where it says which model answered and how it was set up. Worth writing: without it a run records nothing about the system under test |
| `headers` | sent with every request |
| `timeout` | seconds. Default 30 |
| `[target.body]` | mandatory: the payload |

`[target.body]` is shaped like the payload itself. A leaf string that starts
with `case.` reads from the case; anything else is a literal:

```toml
  [target.body]
  question = "case.vars.question"
  channel  = "email"
```

Readable: `case.id`, `case.expected`, `case.context`, `case.vars.<key>`,
`case.metadata.<key>`. One level of reference and no expressions — no
concatenation, no conditionals, no formatting — so the nesting, the arrays and
the types of a real payload survive, because the table *is* the payload. A
reference that names no case field is refused when the suite loads, not once
per case half way through a run.

The one shape this gives up is a body that has to be *computed*. That is what
`HttpTarget(request=…)` remains for, in a `suite.py`.

### `type = "provider"`

A model, called directly. This one needs a key in the environment.

```toml
[target]
type = "provider"
provider = "anthropic/claude-haiku-4-5"
prompt_file = "prompt.md"
max_tokens = 500
temperature = 0.0
```

`provider` is the coordinate. Everything else is a parameter **that plugin**
names — `prompt_file`, `system`, `system_file`, `temperature`, `max_tokens`,
`prefill` and its peers; a misspelling is refused with what the plugin does
accept. `model` is not among them: it is the coordinate's second half, and
writing it twice would give one fact two places to be wrong.

`client` and `pricing` are not configuration either — they are where a test
injects a stand-in, and a data file has nothing to put there.

## What it cannot say

Deliberately. What a data file cannot express is what a data file should not be
able to smuggle past a review.

| | |
|---|---|
| A judge with rules of its own | it has no coordinates |
| A judge set up differently from the plugin's defaults | the coordinate carries the instrument, not its settings |
| A target that is a function | including an HTTP body that must be computed |
| A custom assertion, and `from_autoevals` | a scorer is a Python object |
| Custom `pii_absent` patterns | they carry a checksum function |
| `disclosure` | see below |

Each of these fails when the suite loads, with a sentence that names the wall
and where to go — never "invalid value".

**`disclosure` deserves its own line.** It is not settable from a data file at
all, and that is a security property rather than a limitation: what a
`Disclosure` widens is what leaves the end company's perimeter, and a data file
is the artifact most likely to be generated, templated, or copied between
customers. A suite that is data cannot widen the boundary. Widening it means
writing Python, in a repository, under review.

## Moving between the two forms

Neither form is the advanced one. They build the same objects, so the same
suite written both ways has the same assertion identities and the same
`config_hash` — which is what a stored baseline is matched on.

So a suite can be ported in either direction **without re-promoting**: rewrite
it, run it, and `compare` against the baseline you already had. If the
comparison reports the suite as changed, the two are not the same suite, and the
difference is a real one worth finding.

## When something is wrong

Every refusal names the file, the entry inside it, and the key:

```console
suite.toml, [[assertions]] #2: `contains` has no parameter `treshold`. Did you mean `threshold`?
```

An unknown key is always an error, never a warning and never ignored. A
silently dropped `treshold` would be a check running on its default, and for a
threshold the default a typo falls back to is the one that passes — a check
that is present, green, and never set.
