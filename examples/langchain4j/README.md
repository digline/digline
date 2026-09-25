# My app is LangChain4j: what do I put in my repo?

One HTTP endpoint on your side, and three files in an `eval/` directory. digline
never imports your application — it posts a question and reads the answer — so
nothing about your build, your framework or your deployment has to change.

There are **two** services here standing in for yours — `app-spring/` on Spring
Boot, `app-quarkus/` on Quarkus — and they share one prompt file, one model and
one endpoint contract. The suite, the cases, the stub and the baseline do not
know which of them answered, and do not change when you swap one for the other.
That is the claim this example is making: **the framework is not the contract;
the endpoint is.**

Tested against **Spring Boot 4.1.x** and **Quarkus 3.39.x**, on a JDK 21 —
built, started, and answering on `/evaluate`. `java-example.yml` in CI proves
only that both services *compile*: neither ships a test, so the boot-and-answer
half was verified by hand and the floor above is the version pair it was
verified at.

`stub.py` answers the same shape without a JVM, so everything below runs with no
Java and no API key.

```console
$ uv sync && uv run digline run --suite suite.py
```

---

## 1. One endpoint

digline needs three things back, and each is something it cannot work out for
itself once the model call happens on your side of HTTP. A fourth — the
trajectory — if your application calls tools.

```json
{
  "data": "Order 4821 left our warehouse on Tuesday. — Northwind Support",
  "usage": { "cost_usd": 0.00021, "elapsed_ms": 380.0,
             "tokens": { "input_tokens": 190, "output_tokens": 38 } },
  "config": { "provider": "openai", "model": "gpt-4o-mini",
              "temperature": 0.0, "max_tokens": 512 }
}
```

- **`data`** — what the assistant said. This is what gets judged. A string, or
  an object if that is what your endpoint returns.
- **`usage`** — what the call cost and how long it took. digline cannot price a
  call it did not make, so you report it. The price list lives in your code
  (`SupportService.java`, in either service),
  dated, because a price is a fact about a day.
- **`usage.tokens`** — the counts behind the price, by digline's own names:
  `input_tokens` and `output_tokens` are required, `cache_read_tokens`,
  `cache_write_tokens` and `thinking_tokens` optional, and **any other key is
  refused** — a count under another name is a count nothing adds up. Its own
  object, and not merged in beside `cost_usd`, for exactly that reason.
  Report no `tokens` at all where the provider told you nothing: digline records
  an absent count as absent, and would record a `0` as a measurement you did not
  make.
- **`config`** — which model answered and how it was set up. Without this a run
  records nothing about the system under test, and the day somebody bumps the
  model the comparison says the configuration is unchanged. With it, the report
  says *"this drop coincides with model gpt-4o-mini → gpt-4o"*.

The keys under `config` are a **closed set**: `provider`, `model`, `max_tokens`,
`temperature`, `top_p`, `top_k`, `seed`, `region`, `base_url`, `response_format`,
`json_mode`. `provider` and `model` are required; the rest are optional and a
`null` means "we did not send it". An unknown key is refused by name rather than
recorded — an open bag of fields is where a customer identifier ends up.

The whole integration is about forty lines that call a service you already
have. In `app-spring/` it is `EvaluationController.java`; in `app-quarkus/` it
is `EvaluationResource.java`. Spring MVC and JAX-RS, same fields, same JSON,
and neither one imports anything from digline.

### If your application calls tools

This assistant does not, so it reports none — a demonstration that invented some
would be demonstrating nothing. If yours does, the trajectory goes in the same
answer, under a key the suite names with `tool_calls_path`:

```json
{
  "data": "Order 4821 is due Thursday. — Northwind Support",
  "trajectory": { "calls": [
    { "tool": "lookup_order",
      "arguments": { "id": "4821" },
      "status": "success",
      "result": "shipped Tuesday" }
  ] }
}
```

`status` is **mandatory** on every call and is one of `success`, `error` or
`not_reported`. There is no default, on purpose: a tool that ran and failed must
not be able to report as one that worked by saying nothing. A call you cannot
name is `"tool": null`, which keeps its position; `""` is refused rather than
read as that absence. Declare only `tool_calls_path` and the names are derived
from the calls, so the two cannot disagree.

Arguments never leave your perimeter: a `tool_called_with` check records how much
of what the *suite* declared matched, never what the model sent.

### What your application reports is not reviewed

Everything above is checked for **shape** — closed keys, scalar values. None of
it is checked for truth. Whatever your service puts in `model` is what the run
records and what crosses a boundary, and nobody on digline's side wrote it.

The answer is `expect_config` in the suite: you declare the system you expect,
your service reports, and digline refuses an answer that contradicts it — so the
value in the record is one that went through a pull request.

```python
target = HttpTarget(
    URL,
    ...,
    config_path="config",
    expect_config={"provider": "openai", "model": "gpt-4o-mini"},
)
```

**Not in `suite.py` yet, and the reason is worth knowing**: this example installs
digline **from PyPI like any user**, under a `digline>=0.20,<0.21` pin, and the
key arrives in the release after 0.20.1. The line goes in when the pin moves.
Until then, treat `provider` and `model` in this example's runs as values the
service chose (digline ADR 0030 §6).

### How much of this had been run end to end, and by whom

`tools_path`, `tool_calls_path` and `usage_path` shipped in digline **0.19.1**,
and until this page was written **no example used any of them**. They worked and
they were documented; nothing had posted a real answer through them and read it
back except digline's own tests. That is written down rather than quietly fixed,
because the general form is the part worth carrying: **a feature whose example
does not exercise it is a feature nobody has run end to end but us.**

So, precisely, where each stands here:

| | |
|---|---|
| `config_path` | **exercised**, since 0.3.0 |
| `usage_path` | **exercised.** The token counts above are read out of a real answer on every run of this example |
| `tools_path`, `tool_calls_path` | **not exercised.** This assistant calls no tools, so the trajectory JSON above is a contract you may be the first to run |

If you are wiring the trajectory and something does not fit the shape above, that
is worth reporting rather than working around: on those two paths this page is a
specification and not a demonstration, and that difference is the one this
section exists to admit.

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
3. `output_path` / `cost_path` / `latency_from_response` / `config_path` /
   `usage_path` — where those things sit in your answer, written as dotted
   paths.

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
artifacts = [Path("prompts/system.txt")]
```

The prompt is the thing under test, so every run records it and the report shows
the diff above the scores it moved. It sits at the top level here rather than
inside either service, because both package it from there — one file, so the two
cannot drift, and the suite names it without naming a framework. In your own
repository it goes wherever your service reads it from.

**The baseline** — `.digline/northwind/baselines/support.json`, written by
`promote` and committed. This is the file that makes the whole thing work: the
approved answers, in your repository, moving with it, reviewed in your pull
requests. Runs go to `.digline/northwind/runs/` and are gitignored.

## 3. Run it, read it, approve it

```console
$ uv run digline run --suite suite.py
2026-09-01T13-12-52-981903-00-00-bc060bda8aefb7f4

$ uv run digline report --suite suite.py --run latest --locale en --out report.html
$ uv run digline promote --suite suite.py --run latest --replacing 2026-09-01T13-59-15-058158-00-00-bc060bda8aefb7f4
```

`--replacing` names the baseline this promotion replaces: here, the one
this example ships, whose key `compare` prints under its verdict and
`digline list` marks with `*`. If the baseline has moved since you
compared, `promote` refuses and names both keys.

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
- **Reporting those fields from one endpoint,** and keeping the price list in
  `SupportService.java` current.

And what it does not require:

- **No port, no server, no account.** digline is a command that reads and writes
  files in your repository.
- **Nothing leaves on the default path.** With `SUPPORT_URL` set, the only call
  your suite makes is to your own service, which talks to the model provider on
  its own side. Baselines, runs and reports stay in your repository.
- **No rewrite.** The endpoint calls a service you already have.

## Running a real service

Either one. They answer the same thing, and the suite does not change between
them — which is the easiest way to see what this example is claiming.

**Spring Boot:**

```console
$ cd app-spring && OPENAI_API_KEY=sk-... mvn spring-boot:run
$ cd .. && SUPPORT_URL=http://localhost:8080/evaluate uv run digline run --suite suite.py
```

**Quarkus:**

```console
$ cd app-quarkus && OPENAI_API_KEY=sk-... mvn quarkus:dev
$ cd .. && SUPPORT_URL=http://localhost:8080/evaluate uv run digline run --suite suite.py
```

Both need a JDK 21 and an OpenAI key. The answers then stop being deterministic,
which is what `tolerance` on the budgets and `Repeated` on a judge are for — see
the guide (`docs/guide.md`), the chapter on judge noise.

The two differ inside, and none of it reaches the endpoint: Spring builds the
model in a constructor, Quarkus has the `quarkus-langchain4j` extension build it
from `application.properties`. They used to differ in a second way too — the
extension lagged behind langchain4j's `ChatLanguageModel` → `ChatModel` rename,
so each service named the interface its own dependency gave it — and they no
longer do. Run the suite against either and the run file is the same document.

Needs digline `0.3.0` (`config_path` on `HttpTarget`).
