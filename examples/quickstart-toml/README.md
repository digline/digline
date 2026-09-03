# My team does not write Python: can we still gate a prompt?

Yes. This suite is two data files and no code at all.

The reader this is for has an application in Java, Go, C# or TypeScript, an
endpoint that answers questions, and a CI job that needs to fail when the
answers get worse. digline needs a body it can post and a field it can read out
of the answer; what produced the answer is not its business.

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
    uv run digline promote --suite suite.toml --run latest
    uv run digline compare --suite suite.toml --run latest

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
answer, dotted: the answer itself, what the call cost, how long it took. It also
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
