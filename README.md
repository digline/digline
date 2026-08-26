# digline

Python-native evaluation engine for LLM output.

It checks that the answers of an LLM-based system keep doing what they are supposed
to, and **keeps the verdict in the repository** instead of on somebody else's server:
the baseline is a committed JSON file, the comparison against it runs locally, and the
report for people who do not read code is a self-contained HTML file.

From that follows the difference that matters against equivalent tools: you do not need
a login to know whether an answer got worse than last week. A threshold catches "below
0.7"; a baseline catches "was 0.91, now 0.78, still above the threshold".

The suite is **Python code**, not YAML: a judge is an object, a target is a function,
and what may leave a perimeter is declared in code — things a configuration file cannot
express without reinventing a language.

## The cycle

A suite, `suite_qa.py`, declares who, where, what is checked and on what — and imports
the application it evaluates, like any test:

```python
from brief import score_for                      # your application, next to the suite
from digline.core import Contains, CostBudget, JudgeReply, LlmRubric
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme-bank", environment="staging", name="qa",
    assertions=[
        Contains(needle="Rome"),
        CostBudget(max_usd=0.10, tolerance=0.02),
        LlmRubric(rubric="does it answer the question?", judge=judge,
                  threshold=0.7, tolerance=0.05),
    ],
    cases=[Case(id="capital-it"), Case(id="capital-fr")],
)

def target(case):
    ...  # call your system and return a Response
```

**1. Run.** It prints the run key, and nothing else, so a shell can capture it.

```console
$ digline run --suite suite_qa.py
2026-08-25T16-23-31-885559-00-00-d3af2e5df21baa95
```

**2. Promote to reference.** A deliberate act, never a side effect: it is what makes the
baseline a committed, reviewable artifact. `--run latest` is the most recent run of this
suite — explicit, not guessed.

```console
$ digline promote --suite suite_qa.py --run latest
qa baseline set to 2026-08-26T06-44-01-706255-00-00-d3af2e5df21baa95
```

**3. Compare.** After a change that makes an answer worse:

```console
$ digline compare --suite suite_qa.py --run latest
1 check got worse compared with the reference. Every case could be judged. No case is suspended. The configuration is the same as the reference.

capital-fr · llm_rubric · Score fell from 0.930000 to 0.780000.

$ echo $?
1
```

It says *which*, not just how many — and the sentence on each line is the same one that
will appear in the report, because a single function composes it. If there are many, it
shows twenty and declares how many it left out.

The exit code is the same answer the customer will read: `1` got worse, `2` could not be
judged, `0` fine. In the terminal `--locale` is optional (default `en`).
For a pipeline: `--json` gives the headline, `--json full` adds the deltas.

**4. Render the report.** Self-contained HTML, no JavaScript, deterministic byte for
byte, printable to PDF with the sections open. Here `--locale` is **mandatory**: a
document has a recipient, and its language is not chosen by omission.

```console
$ digline report --suite suite_qa.py --run latest --locale it --out report.html
$ echo $?
1
```

With `--redacted` the document loses the judge's reasons and the undeclared metadata,
and keeps the verdicts: an end company can send the signal without sending its own
data.

**And to find a run from yesterday:**

```console
$ digline list --suite suite_qa.py
  KEY                                                CREATED                            ENV           COMMIT          CASES
  2026-08-26T06-44-36-918226-00-00-d3af2e5df21baa95  2026-08-26T06:44:36.918226+00:00   staging       51f0e25-dirty   2
  2026-08-26T06-44-01-851352-00-00-d3af2e5df21baa95  2026-08-26T06:44:01.851352+00:00   staging       51f0e25-dirty   2
* 2026-08-26T06-44-01-706255-00-00-d3af2e5df21baa95  2026-08-26T06:44:01.706255+00:00   staging       51f0e25         2

* = current baseline
```

`51f0e25-dirty` means that run was produced with uncommitted changes: it is not
reproducible from the repository, and the report says so to whoever reads it.

**And to look at them all together:**

```console
$ digline view --suite suite_qa.py
digline view on http://127.0.0.1:7373/ — ctrl-c to stop
```

Four screens, stdlib only, no JavaScript, no state of its own: it reads
`.digline/` and writes only what the CLI would write.

- **Run list** — key, date, environment, commit **and the aggregates**: it is the table
  you use to choose which run to promote, reading precision and accuracy down a column
  and taking the median. Without the aggregates the choice cannot be made, and you end
  up promoting the first green run.
- **Comparison** — you pick **both** runs, not just the reference: comparing run 1 with
  run 3 of a calibration is what shows the noise. The page calls `render_html`, the same
  function as `digline report`: if they diverged it would be a bug, and a test checks it
  by stripping the navigation bar and comparing byte for byte.
- **History of a case** — one row per run, the scores per assertion, and for sampled
  assertions the **raw votes** too. It is the calibration table you used to build by
  hand with a script.
- **Suspension** — it shows the line to add to the suite and writes nothing: a
  suspension lives in the code, and the reason must travel with the case in the same
  revision as everything else.

The only route that writes is promotion, which goes through `promote_baseline` with the
same three refusal conditions as the CLI and **checks the `Origin` header**: loopback is
not a boundary, because any page open in the browser can POST to `localhost`. A run that
cannot become the reference — because it has unjudged cases — says so on its row instead
of letting you find out by clicking.

**When the schema changes:**

```console
$ digline migrate --suite suite_qa.py
migrated 2026-08-25T…-a1b2.json from schema 5
2 migrated, 7 already current, 0 refused
```

A scan (`list`, `--run latest`, the view) **skips** documents of a schema this version
does not read and **declares** how many it skipped; a key asked for by name is refused
instead, because there the caller named that file. `migrate` carries additive bumps
forward, rewriting in place **only after** re-reading the document with the new schema,
and refuses non-additive ones by saying what is missing — there is no `tenant` to invent
for a file written before perimeters existed.

## What ends up in the repository

```
.digline/
  <tenant>/baselines/<suite>.json   to be committed
  <tenant>/runs/<suite>/*.json      ignored (generated .gitignore)
```

## Status

Engine, offline driver, file store, report, CLI and local view work and are covered by
tests.
The production store, the production → repo bridge and the reactive side are designed in
the ADRs and not written yet.

## Documentation

- [`docs/api.md`](docs/api.md) — reference for the public API: what is imported from
  where, `Suite`, `Case`, `Target`, the assertions with their parameters, custom
  assertions, and the complete example in [`examples/quickstart/`](examples/quickstart/),
  which a test runs on every build.
- [`docs/adr/`](docs/adr/) — the architectural decisions, numbered, with the reasoning.
