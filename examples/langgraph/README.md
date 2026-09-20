# My agent calls the right tools, but with the right arguments?

A LangGraph dispatch agent with two tools — look an order up, refund its
shipping — and digline holding **the trajectory** against a baseline committed
here. The target is **a function**: digline imports `app.py` and invokes the
graph in process. No server, no HTTP, no port.

Tested against **langgraph 1.2.11** and **langchain 1.4.0**.

```console
$ uv sync && uv run digline run --suite suite.py
```

No API key, no network. The default path runs the graph on a scripted stand-in
model, so every run answers the same way and CI can run the whole cycle for
nothing. **The tools are real**: they execute, and the figures in the trajectory
are computed rather than scripted.

## 1. What is under test

Not the sentence. The sentence is a line about money that has already moved.

What this agent is *for* is a policy: **look the order up before refunding it,
and refund the figure the lookup returned** — not the one the customer stated.
An agent that skips the lookup writes a perfectly good sentence and moves real
money against a number it invented, and no assertion on the text can see it.

So four checks, in `suite.py`:

````python
ToolsCalled(expected=["lookup", "refund"])
ToolCalledWith(tool="lookup", arguments={"order_id": "4711"})
ToolCalledWith(
    tool="refund", arguments={"order_id": "4711", "amount_eur": 4.9}, match="subset"
)
Contains(needle="4.90")
````

One order and four phrasings, because what is under test is whether the agent
reads the request — not whether it can hold two orders apart. Two of the four
cases are the ones that earn their keep:

- **`decoy-number`** puts a second number in the sentence: *"I paid 12.50 for
  express on order 4711"*.
- **`amount-asserted-by-the-customer`** states the shipping confidently and
  wrongly: *"which I am fairly sure was 9.90"*. The shipping was 4.90.

`match="subset"` on the refund is deliberate: the call may carry keys this
example did not declare, and a framework adding one is not a regression. Under
`exact` it would be.

### What it looks like when the agent gets it wrong

The committed baseline is green, so set `DISPATCH_NAIVE=1` to put a careless
reader in the seat: it takes the **first** number it sees as the order id, and
believes any amount the customer states. Both are plausible mistakes rather than
invented ones. Then this suite says:

```
2 checks got worse compared with the reference. 3 of 4 cases judged, 1 could not be. No case is suspended. The suite is unchanged from the reference. The files under test are the same as the reference.

  amount-asserted-by-the-customer · tool_called_with · Went from passing to failing (1.000000 → 0.000000).
  amount-asserted-by-the-customer · contains · Went from passing to failing (1.000000 → 0.000000).
  decoy-number · tools_called · The check could not run.
  decoy-number · tool_called_with · The check could not run.
  decoy-number · tool_called_with · The check could not run.
  decoy-number · contains · The check could not run.
```

Two different outcomes, and the difference is the point.

**`amount-asserted-by-the-customer` fails.** The agent refunded 9.90 because the
customer said so. The trajectory is otherwise perfect — right tools, right
order, right order id — and the sentence it wrote reads impeccably. Only
`tool_called_with` on the *refund* sees it.

**`decoy-number` could not be judged at all.** Taking `12.50` as the order id
made `refund` raise, the exception came back out of the graph, and digline
reports a case it could not judge rather than a case that failed. That is a
different claim and digline refuses to blur it: nothing was measured here, so
nothing is reported as measured.

## 2. Why the baseline records a projection

The target returns the final text and an ordered list of
`(tool, arguments, result, status)` — not LangGraph's message list.

That is not a convenience. LangGraph mints `ToolMessage.id` as a uuid4 with no
public hook to pin it, so the raw list differs between two runs of the same
input, and a committed baseline built on it would churn on every run for a
reason that has nothing to do with the agent. The projection was measured
byte-identical across separate processes. The id it drops carries no evaluative
meaning, so dropping it is the payload rule working rather than a workaround.

`status` comes along for free and is worth having: it is a real field on
`ToolMessage`, so an agent that carried on after a call the framework marked
failed is visible in the trajectory and nowhere in the text.

What `status` does **not** cover is worth knowing before you rely on it, and it
was measured rather than assumed: in langgraph 1.2.11 a tool that *raises*
propagates the exception out of `invoke()` instead of coming back as a
`ToolMessage`. This example does not catch it, on purpose — section 1 shows what
that looks like, and a case digline could not judge is a more honest answer than
a check reported as failed.

## 3. The switch, and what the default path does not test

One line in `suite.py`:

```python
LIVE = os.environ.get("DIGLINE_LIVE") == "1"
```

Set it and the same graph, with the same two tools, runs on
`init_chat_model("anthropic:claude-haiku-4-5")`.

Unset, be honest about what you have: the stand-in replays a script and **never
reads the prompt**. On the default path the prompt is not under test — the graph
around it is. That the agent wires two tools, that the loop terminates, that the
trajectory still has the shape the checks read: those are exactly the things a
langgraph upgrade breaks, and they are worth a gate that costs nothing.

The two paths are two systems. Each keeps its own baseline; do not promote one
over the other.

## 4. No telemetry, and it is pinned rather than assumed

`langsmith` is a hard, non-optional dependency of `langchain-core`. With a clean
environment it opens no socket — checked by blocking the socket layer before
importing anything and running the agent through — but this example does not
rely on that. `.github/workflows/check.yml` sets `LANGSMITH_TRACING=false` and
`LANGCHAIN_TRACING_V2=false`.

They are set in the job environment and **not** from inside Python: the lookup
is cached on first read, so assigning them after the first langchain import does
nothing at all. **Four names are live across two namespaces, and all four are
pinned** — the lookup takes the first non-empty of `LANGSMITH_TRACING_V2`,
`LANGCHAIN_TRACING_V2`, `LANGSMITH_TRACING`, `LANGCHAIN_TRACING`, so the
highest-precedence name is the one that decides. Pinning a subset settles it
only against an environment where nothing else is set, which is the environment
that needed no pin.

## 5. The cycle

```console
$ uv run digline run --suite suite.py
$ uv run digline report --suite suite.py --run latest --locale en --out report.html
$ uv run digline promote --suite suite.py --run latest
```

Read the report before you promote. `promote` means *these calls are the ones we
stand behind* — a decision, not a build step, which is why nothing does it for
you and why the result is a file you commit:
`.digline/northwind/baselines/dispatch.json`.

This suite sets `record_responses=True`, so each run keeps what the agent
answered and the calls it made. They stay here: `promote` strips them from the
baseline, and no boundary ever carries them. What that buys is
`digline rejudge` — change the policy and re-judge the calls this run already
made, instead of paying the agent again.

## 6. The gate

`.github/workflows/check.yml` — `run`, then `compare`, and nothing else. It also
runs weekly: `langgraph>=1.2.11,<2` means a minor release lands under this agent
with nobody merging anything. The last one moved `create_agent` out of
`langgraph.prebuilt` and into `langchain.agents`, so that is not a hypothetical.

Note what is not there: `promote`. A job that promotes and then compares is
comparing a run with itself and passes whatever happened.

## 7. What it costs you

- **`uv` and Python 3.12+ on the CI runner.** One `uv sync`, cached. langgraph
  and its dependency tree are the heavy part — 43 packages — not digline.
- **One Python file in review.** `suite.py` is about a hundred and twenty lines,
  over half of them comments saying why each check is there, and somebody on the
  team has to be able to read it. That is the real cost and it is not zero.
- **The stand-in's script.** Two turns per case in `fake.py`. No stand-in in
  `langchain-core` can do this on its own: all five raise `NotImplementedError`
  from `bind_tools`, and `create_agent` binds before it runs. The subclass that
  closes the gap is three lines.

And what it does not require: no key, no account, no network on the default
path; no server and no port; no data leaving; and no rewrite — `app.py` is the
graph you already have.
