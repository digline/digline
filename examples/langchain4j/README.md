# My app is LangChain4j: what do I put in my repo?

One HTTP endpoint on your side, and three files in an `eval/` directory. digline
never imports your application — it posts a question and reads the answer — so
nothing about your build, your framework or your deployment has to change.

`app/` is a Spring Boot + LangChain4j service standing in for yours: one
endpoint, one prompt file, one model. `stub.py` answers the same shape without a
JVM, so everything below runs with no Java and no API key.

```console
$ uv sync && uv run digline run --suite suite.py
```

---

## 1. One endpoint

digline needs three things back, and each is something it cannot work out for
itself once the model call happens on your side of HTTP.

```json
{
  "data": "Order 4821 left our warehouse on Tuesday. — Northwind Support",
  "usage": { "cost_usd": 0.00021, "elapsed_ms": 380.0 },
  "config": { "provider": "openai", "model": "gpt-4o-mini",
              "temperature": 0.0, "max_tokens": 512 }
}
```

- **`data`** — what the assistant said. This is what gets judged. A string, or
  an object if that is what your endpoint returns.
- **`usage`** — what the call cost and how long it took. digline cannot price a
  call it did not make, so you report it. The price list lives in your code
  (`app/src/main/java/dev/digline/example/SupportService.java`),
  dated, because a price is a fact about a day.
- **`config`** — which model answered and how it was set up. Without this a run
  records nothing about the system under test, and the day somebody bumps the
  model the comparison says the configuration is unchanged. With it, the report
  says *"this drop coincides with model gpt-4o-mini → gpt-4o"*.

The keys under `config` are a **closed set**: `provider`, `model`, `max_tokens`,
`temperature`, `top_p`, `top_k`, `seed`, `region`, `base_url`, `response_format`,
`json_mode`. `provider` and `model` are required; the rest are optional and a
`null` means "we did not send it". An unknown key is refused by name rather than
recorded — an open bag of fields is where a customer identifier ends up.

The whole integration is `EvaluationController.java`, under
`app/src/main/java/dev/digline/example/`: about forty lines, and it calls a
service that already existed.

## 2. Three files in `eval/`

Here they are at the top level, because this directory *is* the eval directory.
In your repository they go in `eval/` beside `src/`, and they are the only
Python you own.

**`cases.json`** — your questions. Plain data; keep adding to it. Every failure
worth not repeating becomes a case here.

**`suite.py`** — about forty lines, and three of them are yours. They are marked
`EDIT` in the file:

1. `URL` — where your service listens.
2. `request=` — the body your endpoint expects, built from the case.
3. `output_path` / `cost_path` / `latency_from_response` / `config_path` —
   where those four things sit in your answer, written as dotted paths.

Everything else is the checks. Read them once and change them when you have a
reason:

```python
(Contains(needle="Northwind Support"),)  # the sign-off the prompt requires
(NotContains(needle="As an AI"),)  # the hedging that creeps in
(Length(minimum=12, maximum=60, unit="words"),)
(CostBudget(max_usd=0.002, tolerance=0.05),)
(LatencyBudget(max_ms=2000.0, tolerance=0.10),)
```

A budget is a ceiling, not a metric: exceeding it fails the run.

The suite also names your prompt as an artifact:

```python
artifacts = [Path("app/src/main/resources/prompts/system.txt")]
```

The prompt is the thing under test, so every run records it and the report shows
the diff above the scores it moved. It stays in your Java resources where a Java
developer would look for it.

**The baseline** — `.digline/northwind/baselines/support.json`, written by
`promote` and committed. This is the file that makes the whole thing work: the
approved answers, in your repository, moving with it, reviewed in your pull
requests. Runs go to `.digline/northwind/runs/` and are gitignored.

## 3. Run it, read it, approve it

```console
$ uv run digline run --suite suite.py
2026-09-01T13-12-52-981903-00-00-bc060bda8aefb7f4

$ uv run digline report --suite suite.py --run latest --locale en --out report.html
$ uv run digline promote --suite suite.py --run latest
```

Read the report before you promote. `promote` means *these answers are the ones
we stand behind* — it is a decision, not a build step, which is why nothing
does it for you and why the result is a file you commit.

`report.html` in this directory is the one this example produced.
`--locale it` renders the same run in Italian; the dates and the numbers do not
move, so two reports of one run stay comparable line by line.

## 4. Compare on every change

```console
$ uv run digline compare --suite suite.py --run latest
```

Not only when you edit the prompt. The three changes this catches that a diff
cannot:

- **the prompt moved** — the report shows the diff of the file, above the scores;
- **the model moved** — someone bumps `support.model` in
  `application.properties`, and the comparison names it: `model gpt-4o-mini →
  gpt-4o`, beside any score that dropped with it;
- **nothing you did moved** — the provider updated the model under a name that
  did not change. This is the one nobody notices, and it is why the workflow
  below also runs on a schedule.

`compare` reports a configuration change; it never fails on one. What fails the
run is a score that got worse.

## 5. The gate

`.github/workflows/check.yml`. Two jobs: your Maven build, and the
comparison.

```yaml
- name: Compare with the committed baseline
  run: |
    KEY=$(uv run digline run --suite suite.py)
    uv run digline compare --suite suite.py --run "$KEY"
```

`compare` exits **0** when nothing got worse, **1** when something did, **2**
when a case could not be judged at all. That is the gate — no parsing of output,
no threshold in the workflow.

Note what is *not* there: `promote`. A job that promotes and then compares is
comparing a run with itself, and passes whatever happened.

Set `SUPPORT_URL` to a deployed instance of your service, and keep the provider
key on that side. Unset, the suite runs against `stub.py`.

## 6. What it costs you

Honestly:

- **`uv` and Python 3.12+ on the CI runner.** One `uv sync`, cached.
- **One Python file in review.** `suite.py` is about forty lines and someone on
  the team has to be able to read it. That is the real cost, and it is not zero.
  It is Python because a judge is an object and a check is a function; there is
  no configuration file today.
- **Reporting three fields from one endpoint,** and keeping the price list in
  `SupportService.java` current.

And what it does not require:

- **No port, no server, no account.** digline is a command that reads and writes
  files in your repository.
- **No data leaves.** The only network call is the one your suite makes, to your
  own service. Baselines, runs and reports stay in your repository.
- **No rewrite.** The endpoint calls a service you already have.

## Running the Java service for real

```console
$ cd app && OPENAI_API_KEY=sk-... mvn spring-boot:run
$ cd .. && SUPPORT_URL=http://localhost:8080/evaluate uv run digline run --suite suite.py
```

Needs a JDK 21 and an OpenAI key; the answers then stop being deterministic,
which is what `tolerance` on the budgets and `Repeated` on a judge are for. See
the guide (`docs/guide.md`) — the chapter on judge noise.

Needs digline `0.3.0` (`config_path` on `HttpTarget`).
