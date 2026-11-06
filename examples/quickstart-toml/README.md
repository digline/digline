# My team does not write Python: can we still gate a prompt?

Yes. This suite is two data files and no code at all.

The reader this is for has an application in Java, Go, C# or TypeScript, an
endpoint that answers questions, and a CI job that needs to fail when the
answers get worse. digline needs a body it can post and a field it can read out
of the answer; what produced the answer is not its business, unless your
endpoint runs an agent: then it reports the tool calls it made too, under
`tool_calls_path` (below).

    suite.toml    the rules  — what is checked, and how badly it may drift
    cases.json    the data   — the questions, and which ones are set aside
    stub.py       your application, standing in until you delete it

Two files rather than one, on purpose. A rule changes when somebody decides the
bar moved. A case is added every time production produces a new one. In one
file those two arrive as one diff, and a reviewer has to read the whole thing
to find out which happened.

## Run it

The application is a separate process — here as in production — so it starts in
its own terminal:

    python stub.py

Then the cycle, in another:

    uv sync
    uv run digline run     --suite suite.toml
    uv run digline promote --suite suite.toml --run latest \
        --replacing 2026-09-03T13-12-00-669324-00-00-8a745d27d002e7dd
    uv run digline compare --suite suite.toml --run latest

`--replacing` names the baseline this promotion replaces: here, the one
this example ships, whose key `compare` prints under its verdict and
`digline list` marks with `*`. If the baseline has moved since you
compared, `promote` refuses and names both keys.

`run` writes a run and prints its key. `promote` makes it the baseline — a JSON
file under `.digline/northwind/`, committed to this repository, reviewed like
any other change. `compare` holds a later run against it and answers with an
exit code: `0` fine, `1` got worse, `2` could not be judged.

Now make it worse. Open `stub.py` and delete `— Northwind Support` from one of
the answers, then run and compare again:

    1 check got worse compared with the reference. Every case could be judged. 1 case is suspended. The suite is unchanged from the reference. The system under test answered under the same configuration as the reference.

    how-do-i-return · contains · Went from passing to failing (1.000000 → 0.000000).

That is the gate. It fails on a change no test would have caught, because there
was no correct answer to compare against — only a better and a worse one. The
last sentence of the headline is `config_path` earning its keep: the answer got
worse and the model did not change, so this is a finding and not a comparison
between two different systems.

## What is in the suite

`[target]` names your endpoint and says where the three things live in its
answer, dotted: the answer itself, what the call cost, how long it took. For an
agent it says where the tool calls are too, `tool_calls_path`, which this stub
does not need. It also
names `config_path`, and that one earns its line — it is where your service says
which model answered and how it was set up. Without it a run records nothing
about the system under test, and the day somebody bumps the model the comparison
reports the configuration as unchanged.

`[target.body]` is the payload, shaped like the payload. A leaf that starts with
`case.` reads from the case; everything else is a literal. One level of
reference and no expressions, so the nesting, the arrays and the types of a real
body survive — and a body that has to be *computed* is the one shape this form
gives up.

`[[assertions]]` is an ordered list, and the order is the order the report shows
them in. Each entry names a check with `type` and then passes it its own
parameters. Every check here has a threshold that can fail; there is no default
in this format that passes vacuously.

The two budgets are there for the same reason they are in every other example:
they are graded rather than binary, so a cost creeping up *within* budget is
visible long before it is a problem.

## What this file cannot say, and what to do about it

A suite that is data cannot hold a judge with rules of its own, a target that is
a function, a custom assertion, or a body it has to compute. That is deliberate:
what a data file cannot express is exactly what a data file should not be able
to smuggle past a review.

When you need one of those, the answer is a `suite.py` — the same objects, the
same semantics, the same engine. Neither form is the advanced one. The error
messages say which wall you have hit and where to go, rather than telling you a
key is invalid.

There is one more thing a data suite cannot do, and it is a feature: it cannot
widen what leaves your perimeter. `Disclosure` is not settable here, so a run
from this suite carries verdicts and no payload, whatever anyone edits into the
file later.

## The CI gate

`.github/workflows/check.yml` is the whole thing: start the application, run,
compare. No `promote` — promoting is the human decision that this is the new
normal, made by somebody who read the report and committed the result. A job
that promotes before it compares compares a run with itself and passes by
construction.

The application being started from outside the suite is not a workaround for
the format. It is what is true: the thing under test is another process, owned
by another team, deployed on a schedule you do not control. That is why the
weekly cron is there — the run nobody triggered is the one that notices.

## What this example shows, and what it does not

It is a **demonstration, not a specification**: what it shows is what runs, on
every release, against the published package. What it leaves out is not ruled
out. It is simply not proven here, and for those parts the documentation is the
contract, not this directory.

Exercised here, end to end:

| | |
|---|---|
| `[target.body]` with `case.` references | **exercised** |
| `output_path`, `cost_path`, `latency_from_response` | **exercised** |
| `config_path` | **exercised**, and the headline's last sentence reads it |
| a suspended case | **exercised**: `refund-status` in `cases.json` |

Not shown, so do not read this directory as evidence for any of it:

- **A real model.** `stub.py` answers fixed text, so every run is identical.
  Your service will not be, and a first comparison against it is where the
  tolerances earn or lose their keep.
- **An endpoint behind authentication.** No `headers` here, and nothing about
  where a token would come from.
- **`usage_path`, `tools_path` and `tool_calls_path`.** The stub reports no
  token counts and calls no tools. `examples/langchain4j/` exercises
  `usage_path`. No example exercises the other two, and langchain4j's README
  says so.
- **A judge.** Every check here is deterministic. A judge has rules of its own,
  and that is a `suite.py` (see above).

## Which check covers what

Two checks in this repository touch this example, and they answer different
questions. Anybody adding or changing an example should know which is which:

- **The example-locks gate** (`tools/example_locks.py`, in `gates` on every pull
  request) runs `uv sync --locked` here into a throwaway environment. A green
  means *it installs as the lock pins it, on Linux, on 3.12 and 3.13*. It
  imports nothing and runs nothing: it does not start the stub, it does not run
  the suite, and it does not notice a lock that is out of date, only one that no
  longer matches `pyproject.toml`.
- **`examples-from-pypi`** (in `ci.yml`: after a release, weekly, and by
  dispatch) installs from the index, starts the stub and runs the cycle a reader would
  run. That is the check that says the example *works*, and it does not run on
  a pull request. A change that breaks this example goes green on its pull
  request and red after the release.

The full statement of what the first one does not prove is beside its step in
`ci.yml`.

**What the lock costs, stated so nobody has to discover it.** `uv.lock` is here
so that the first check covers this example. The price is that it pins an exact
digline version. After every release it still names the previous one until
somebody regenerates it, and until then `uv sync` installs that previous
version. It is the same post-release step every example with a lock waits on:
*After the tag* in `RELEASING.md`, which finds the locks by `ls
examples/*/uv.lock`. And a minor bump moves this lock in the same pull request
as the caps, or `--locked` refuses it.
