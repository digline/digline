# A Python application with three prompts, from its first calls to three gates

This page records the calls of an application with three prompts,
turns the recordings into one suite per prompt, and ends with three gates.

## Who this is for

An application in Python that asks a model more than one thing: here, a
hiring tool that screens a CV against a job, writes a job ad, and answers a
candidate's question. Each of the three is its own prompt, called through
the `anthropic` SDK.

Everything on this page was run, on 2026-11-07, with digline,
`digline-anthropic` and `pytest-digline` installed from this repository at
`37d5c1dd`, `anthropic` 2.6.0 and Python 3.13. **No call reached Anthropic or
a model.** A stand-in for the Messages API on 127.0.0.1,
`tests/_story_python_stand_in.py` in this repository, answered the
application and the judge, and every answer, score and token count below is
the stand-in's. The SDK and the judge were pointed at it with
`ANTHROPIC_BASE_URL`, which both read, and given `ANTHROPIC_API_KEY=fake`; on
your machine the first is left out and the second is your key. Paths are
shortened to `…`.

## Day one: recording

**The prompts**, in a file of their own:

```python
# prompts.py
SCREEN = (
    "Read the CV against the job. Answer with one JSON object, "
    '{"fit": "yes" or "no", "reason": one sentence}, and nothing else.'
)
AD = "Write a job ad in two sentences."
REPLY = "Answer the candidate's question in one or two sentences."
```

**One client, wrapped once, and the suite named at each call.** Each prompt
is a suite of its own, named by `suite=` where the call is made:

```python
# hiring.py
import anthropic
from digline import recorder
from prompts import AD, REPLY, SCREEN

client = recorder.wrap(anthropic.Anthropic(), app="hiring", tenant="acme")
MODEL = "claude-haiku-4-5"


def screen(cv: str, job: str) -> str:
    reply = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=SCREEN,
        messages=[{"role": "user", "content": f"CV: {cv}\nJob: {job}"}],
        suite="screening",
    )
    return reply.content[0].text


def write_ad(role: str, city: str, work: str) -> str:
    reply = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=AD,
        messages=[
            {"role": "user", "content": f"Role: {role}. City: {city}. Work: {work}."}
        ],
        suite="job-ad",
    )
    return reply.content[0].text


def reply_to(question: str) -> str:
    reply = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=REPLY,
        messages=[{"role": "user", "content": question}],
        suite="candidate-reply",
    )
    return reply.content[0].text
```

`suite=` is taken out of the call before it reaches the SDK
([`digline record`](../record.md#wrapping-the-client)). A call that named no
suite would be recorded under `_unassigned`.

**The day's traffic** is a script that calls the three functions:

```python
# traffic.py
from hiring import reply_to, screen, write_ad

JOB = "backend developer"
for cv in (
    "five years of Python and Django, PostgreSQL.",
    "graphic designer, Figma and Illustrator.",
    "two years of Java and Spring.",
):
    print(screen(cv, JOB))
print(write_ad("backend developer", "Milan", "hybrid"))
print(write_ad("data engineer", "Rome", "remote"))
print(reply_to("When will I hear back about the backend role?"))
print(reply_to("Can I apply for two roles at once?"))
```

**Switch it on, and run it**, from the project's root. The first block was
run again on 2026-11-07, with digline at `1b5cf083`, after the sentence on
production came to name Node:

```console
$ digline record on --tenant acme
recording on for tenant 'acme': …/hiring/.digline/acme/recorder.toml
  values: on true, sample 1.0 (default), redact none (default), ceiling 104857600 bytes (default), interval 5.0 s (default)
  development: what the file leaves out is a default; an application that resolves its tenant per request is production (wrap(tenant=callable) in Python, DiglineRecorder.production in Java and Node; the proxy's --tenant is never production), and refuses this file unless it declares sample, redact and ceiling
```

```console
$ ANTHROPIC_BASE_URL=http://127.0.0.1:18799 ANTHROPIC_API_KEY=fake python traffic.py
{"fit": "yes", "reason": "Python and Django are the job."}
{"fit": "no", "reason": "No backend work in the CV."}
{"fit": "yes", "reason": "Java is a backend language."}
We are hiring a backend developer in Milan. The work is hybrid, three days in the office.
Join us as a data engineer, from Rome or anywhere in Italy. The work is fully remote.
Thank you for applying. We answer every candidate within ten working days.
Yes. Apply to each role on its own page, and we read each application separately.
```

```console
$ digline record status --tenant acme
tenant 'acme' · recording on
  switch:     …/hiring/.digline/acme/recorder.toml
  values:     on true, sample 1.0 (default), redact none (default), ceiling 104857600 bytes (default), interval 5.0 s (default)
  writes to:  …/hiring/.digline/acme/recordings
  size:       7223 bytes of recordings (as written; disk use is higher), ceiling 104857600
  suite candidate-reply: 2 calls, 0 orphans; since the last import: not read (pass --suite)
  suite job-ad: 2 calls, 0 orphans; since the last import: not read (pass --suite)
  suite screening: 3 calls, 0 orphans; since the last import: not read (pass --suite)
```

One tenant, one application, three suites, each counted on its own.

**One prompt changes.** The ad now has to name the salary band, and the other
two prompts stay as they were:

```python
# prompts.py
SCREEN = (
    "Read the CV against the job. Answer with one JSON object, "
    '{"fit": "yes" or "no", "reason": one sentence}, and nothing else.'
)
AD = "Write a job ad in two sentences. Name the salary band."
REPLY = "Answer the candidate's question in one or two sentences."
```

```console
$ ANTHROPIC_BASE_URL=http://127.0.0.1:18799 ANTHROPIC_API_KEY=fake python traffic.py
{"fit": "yes", "reason": "Python and Django are the job."}
{"fit": "no", "reason": "No backend work in the CV."}
{"fit": "yes", "reason": "Java is a backend language."}
We are hiring a backend developer in Milan, hybrid, three days in the office. The salary band is 45,000 to 55,000 euros.
Join us as a data engineer, fully remote from Rome. The salary band is 50,000 to 60,000 euros.
Thank you for applying. We answer every candidate within ten working days.
Yes. Apply to each role on its own page, and we read each application separately.
```

```console
$ digline record status --tenant acme
tenant 'acme' · recording on
  switch:     …/hiring/.digline/acme/recorder.toml
  values:     on true, sample 1.0 (default), redact none (default), ceiling 104857600 bytes (default), interval 5.0 s (default)
  writes to:  …/hiring/.digline/acme/recordings
  size:       14532 bytes of recordings (as written; disk use is higher), ceiling 104857600
  suite candidate-reply: 4 calls, 0 orphans; since the last import: not read (pass --suite)
  suite job-ad: 4 calls, 0 orphans; since the last import: not read (pass --suite)
  suite screening: 6 calls, 0 orphans; since the last import: not read (pass --suite)
```

The system prompt is part of a call's setup, so `job-ad` now has two setups
and the other two suites still have one.

## Day two: from recordings to a suite

**Three suites, three proposals**, each from a directory of its own under
`eval/`:

```console
$ digline suggest --suite screening --tenant acme --repository private --root ../..
digline suggest: wrote …/hiring/eval/screening/suite.proposed.toml. It is a proposal, not a suite: no command of digline reads it, nothing in it is a verdict, and no answer was marked. Adopt its lines into your suite, and the commit is yours
assumed:
  the form: suite.toml, the suite does not exist yet; the proposal is always TOML, and a target that is a function needs a suite.py (docs/declarative.md, What it cannot say)
  the setup its target reproduces: 0915adea for single calls
  the judge: none read: llm_rubric is proposed with judge = "provider/model", a placeholder that is refused until you name the provider plugin and the model, which are yours to choose; the provider plugins installed here: anthropic
  each check: 1. is_json, every one of 6 recordings answers JSON, top level object
  each check: 2. json_schema, the draft requires the keys every one of 6 recordings carries
  each check: 3. latency_budget, every one of 6 recordings carries it, and the target has to report it too; max_ms is a placeholder, the strictest the check accepts: no run measured it; tolerance is a placeholder
  each check: 4. llm_rubric, the judged check the capture reviews answers for, asked three times with two in three to agree; threshold is a placeholder, the strictest the check accepts: no run measured it; the rubric, the judge and the tolerance are placeholders
  each starting number: no run read; 6 placeholders, each the strictest value its check accepts and marked in the file, failing until a measured number replaces it
  the calibration band: a skeleton for llm_rubric, with the answer to paste and the band to place, strictly between 0 and 1, both yours
  the counterexample: counterexample-1, constructed and marked as constructed: its input is yours to write, one whose answer llm_rubric must refuse, and nothing in it was recorded
  the regime: repository = 'private': without an assistant, the file quotes no recorded input or answer; the rules read from the recordings, a tool's name or a key, are in its checks
not yet examined: group 1 · single calls, text · 3 answers from 6 recordings
to examine them, once the proposal is your suite: digline record import --tenant acme --suite <your suite>
```

```console
$ digline suggest --suite job-ad --tenant acme --repository private --root ../..
digline suggest: wrote …/hiring/eval/job-ad/suite.proposed.toml. It is a proposal, not a suite: no command of digline reads it, nothing in it is a verdict, and no answer was marked. Adopt its lines into your suite, and the commit is yours
assumed:
  the form: suite.toml, the suite does not exist yet; the proposal is always TOML, and a target that is a function needs a suite.py (docs/declarative.md, What it cannot say)
  the setup its target reproduces: 78d672ab for single calls, the newest of 2 recorded, after f6343794
  to read how two setups differ, once the proposal is your suite: digline record compare --tenant acme --suite <your suite> --setup f6343794 78d672ab --show-setup
  the judge: none read: llm_rubric is proposed with judge = "provider/model", a placeholder that is refused until you name the provider plugin and the model, which are yours to choose; the provider plugins installed here: anthropic
  each check: 1. length, every one of 4 recordings answers text; maximum is a placeholder, the strictest the check accepts: no run measured it
  each check: 2. latency_budget, every one of 4 recordings carries it, and the target has to report it too; max_ms is a placeholder, the strictest the check accepts: no run measured it; tolerance is a placeholder
  each check: 3. llm_rubric, the judged check the capture reviews answers for, asked three times with two in three to agree; threshold is a placeholder, the strictest the check accepts: no run measured it; the rubric, the judge and the tolerance are placeholders
  each starting number: no run read; 7 placeholders, each the strictest value its check accepts and marked in the file, failing until a measured number replaces it
  the calibration band: a skeleton for llm_rubric, with the answer to paste and the band to place, strictly between 0 and 1, both yours
  the counterexample: counterexample-1, constructed and marked as constructed: its input is yours to write, one whose answer llm_rubric must refuse, and nothing in it was recorded
  the regime: repository = 'private': without an assistant, the file quotes no recorded input or answer; the rules read from the recordings, a tool's name or a key, are in its checks
not yet examined: group 1 · single calls, text · 4 answers from 4 recordings
to examine them, once the proposal is your suite: digline record import --tenant acme --suite <your suite>
```

```console
$ digline suggest --suite candidate-reply --tenant acme --repository private --root ../..
digline suggest: wrote …/hiring/eval/candidate-reply/suite.proposed.toml. It is a proposal, not a suite: no command of digline reads it, nothing in it is a verdict, and no answer was marked. Adopt its lines into your suite, and the commit is yours
assumed:
  the form: suite.toml, the suite does not exist yet; the proposal is always TOML, and a target that is a function needs a suite.py (docs/declarative.md, What it cannot say)
  the setup its target reproduces: 8583d65f for single calls
  the judge: none read: llm_rubric is proposed with judge = "provider/model", a placeholder that is refused until you name the provider plugin and the model, which are yours to choose; the provider plugins installed here: anthropic
  each check: 1. length, every one of 4 recordings answers text; maximum is a placeholder, the strictest the check accepts: no run measured it
  each check: 2. latency_budget, every one of 4 recordings carries it, and the target has to report it too; max_ms is a placeholder, the strictest the check accepts: no run measured it; tolerance is a placeholder
  each check: 3. llm_rubric, the judged check the capture reviews answers for, asked three times with two in three to agree; threshold is a placeholder, the strictest the check accepts: no run measured it; the rubric, the judge and the tolerance are placeholders
  each starting number: no run read; 7 placeholders, each the strictest value its check accepts and marked in the file, failing until a measured number replaces it
  the calibration band: a skeleton for llm_rubric, with the answer to paste and the band to place, strictly between 0 and 1, both yours
  the counterexample: counterexample-1, constructed and marked as constructed: its input is yours to write, one whose answer llm_rubric must refuse, and nothing in it was recorded
  the regime: repository = 'private': without an assistant, the file quotes no recorded input or answer; the rules read from the recordings, a tool's name or a key, are in its checks
not yet examined: group 1 · single calls, text · 2 answers from 4 recordings
to examine them, once the proposal is your suite: digline record import --tenant acme --suite <your suite>
```

The proposals differ where the recordings do. `screening` answers JSON, so it
gets `is_json` and a draft `json_schema` that requires `fit` and `reason`;
the other two answer text, so they get `length`. `job-ad` reproduces the
newer of its two setups, the one that names the salary band, and points to
the command that shows how the two differ:

```console
$ digline record compare --tenant acme --suite eval/job-ad/suite.toml --setup f6343794 78d672ab --show-setup
tenant 'acme' · suite job-ad · 4 recordings · 2 setups: f6343794, 78d672ab
  side by side: A f6343794, B 78d672ab
  keys the two setups differ on (2 the same):
    system: A "Write a job ad in two sentences." · B "Write a job ad in two sentences. Name the salary band."

case cap-ff48a9d46ce99ae8 · call
  input:  {"messages": [{"content": "Role: backend developer. City: Milan. Work: hybrid.", "role": "user"}]}
  setup A f6343794
    2026-11-07T10:32:13.126024+00:00  afd848e0: We are hiring a backend developer in Milan. The work is hybrid, three days in the office.
  setup B 78d672ab
    2026-11-07T10:32:17.683743+00:00  8677c2f7: We are hiring a backend developer in Milan, hybrid, three days in the office. The salary band is 45,000 to 55,000 euros.

case cap-fafdab2cdb403bdd · call
  input:  {"messages": [{"content": "Role: data engineer. City: Rome. Work: remote.", "role": "user"}]}
  setup A f6343794
    2026-11-07T10:32:13.127475+00:00  cbd72a24: Join us as a data engineer, from Rome or anywhere in Italy. The work is fully remote.
  setup B 78d672ab
    2026-11-07T10:32:17.684897+00:00  41f97d5c: Join us as a data engineer, fully remote from Rome. The salary band is 50,000 to 60,000 euros.

2 cases; not shown: 0 orphans, 0 calls whose episode is not among the files, 0 interrupted episodes, 0 over the ceiling of a recording, 0 files that are not readable recordings
```

It was run from the project's root once `eval/job-ad/suite.toml` existed,
as the proposal says. So were the commands below, except `diff`, which ran
in `eval/screening/`.

**Adopting them** is copying each file to `suite.toml` and writing what it
leaves to you: where the suite runs, the rubric and the judge. For
`screening`:

```console
$ diff suite.proposed.toml suite.toml
11c11
< # environment = WRITE: mandatory, with no default: where it runs
---
> environment = "dev"
58,59c58,59
<   rubric = "WRITE: one question a good answer says yes to"  # placeholder: yours to write
<   judge = "provider/model"  # placeholder: yours to write, docs/declarative.md#the-judge-by-coordinates
---
>   rubric = "Does the fit follow from the CV and the job?"
>   judge = "anthropic/claude-haiku-4-5"
```

The other two took the same three lines, with their own rubric: *"Does the ad
name the role, the city and the way of working?"* for `job-ad`, and *"Does
the reply answer the candidate's question?"* for `candidate-reply`.

**A person's yes or no**, on the page `digline view` serves with
`--allow-record`. The page serves one suite, so it was opened three times,
once per suite. It was given `--port 7381` because another process held the
default port:

```console
$ digline view --suite eval/screening/suite.toml --allow-record --port 7381
digline view on http://127.0.0.1:7381/?launch=… — the recorder's writes enabled, for the first browser that opens this address; --allow-promote to promote — ctrl-c to stop
```

Its *Recordings* view lists the suite's answers in one group, *a single call,
text*, each with its id, when it was first recorded, its setup, its answer,
how many recordings gave the same answer, and two choices, `--good` and
`--bad`. Under them are a field for your name and one button, *Write the
answers named*. For `screening`, two yeses and a no, the no for the answer
that called two years of Java and Spring a fit, written under the name *Ada
Lovelace*, wrote three cases to `eval/screening/captured.json`. The form was
sent as the button sends it, by a client that runs no script. Under the
button the page prints `digline record import --tenant acme --suite
eval/screening/suite.toml`, and says the command follows the form where its
script runs. With the same choices written out, it is:

```console
$ digline record import --tenant acme --suite eval/screening/suite.toml --good cap-3999ce78477dd215-225602d6 --good cap-99aa0a266644cff8-1d469d1f --bad cap-450165eceed21c10-9bda3cec --by 'Ada Lovelace'
tenant 'acme' · suite screening · writes to eval/screening/captured.json · repository private · check llm_rubric
  wrote cap-3999ce78477dd215-225602d6
tenant 'acme' · suite screening · writes to eval/screening/captured.json · repository private · check llm_rubric
  wrote cap-99aa0a266644cff8-1d469d1f
tenant 'acme' · suite screening · writes to eval/screening/captured.json · repository private · check llm_rubric
  wrote cap-450165eceed21c10-9bda3cec
3 cases written to eval/screening/captured.json: the diff is the review and the commit is the signature; nothing was committed, run or promoted (ADR 0023 §7)
```

Run against a copy of the same recordings, it wrote the same
`captured.json` as the button, byte for byte.

On `job-ad`'s page the two answers of the first prompt are listed and have no
choices: *not electable: recorded only under earlier setups: a yes or no
about an answer the setup in force did not give says nothing about it*. The
two answers with the salary band took a yes each. On `candidate-reply`'s, its
two answers took a yes each.

**Three runs.** The suites' cases are reviewed answers, so each run asks the
judge and never the application:

```console
$ ANTHROPIC_BASE_URL=http://127.0.0.1:18799 ANTHROPIC_API_KEY=fake digline run --suite eval/screening/suite.toml
digline: tenant 'acme' · 0 cases × 3 samples = 0 calls to the target; 3 reviewed answers judged 27 times, with no call to the target; each answer is judged 3 times by llm_rubric
digline: judge: 27 calls · counts: 4860 in / 378 out · cost: 0.006750 USD
digline: recorded .digline/acme/runs/screening/2026-11-07T10-35-18-897245-00-00-98ea9e30692a365a.json
digline: next: digline promote --suite eval/screening/suite.toml --run latest --replacing none  # keeps this run as the reference
2026-11-07T10-35-18-897245-00-00-98ea9e30692a365a
```

```console
$ ANTHROPIC_BASE_URL=http://127.0.0.1:18799 ANTHROPIC_API_KEY=fake digline run --suite eval/job-ad/suite.toml
digline: tenant 'acme' · 0 cases × 3 samples = 0 calls to the target; 2 reviewed answers judged 18 times, with no call to the target; each answer is judged 3 times by llm_rubric
digline: judge: 18 calls · counts: 3240 in / 252 out · cost: 0.004500 USD
digline: recorded .digline/acme/runs/job-ad/2026-11-07T10-35-19-833594-00-00-864f71b825690ccc.json
digline: next: digline promote --suite eval/job-ad/suite.toml --run latest --replacing none  # keeps this run as the reference
2026-11-07T10-35-19-833594-00-00-864f71b825690ccc
```

```console
$ ANTHROPIC_BASE_URL=http://127.0.0.1:18799 ANTHROPIC_API_KEY=fake digline run --suite eval/candidate-reply/suite.toml
digline: tenant 'acme' · 0 cases × 3 samples = 0 calls to the target; 2 reviewed answers judged 18 times, with no call to the target; each answer is judged 3 times by llm_rubric
digline: judge: 18 calls · counts: 3240 in / 252 out · cost: 0.004500 USD
digline: recorded .digline/acme/runs/candidate-reply/2026-11-07T10-35-20-498179-00-00-176631b427e4199e.json
digline: next: digline promote --suite eval/candidate-reply/suite.toml --run latest --replacing none  # keeps this run as the reference
2026-11-07T10-35-20-498179-00-00-176631b427e4199e
```

Each answer was judged nine times: three samples of the suite, each a
`repeated` check of three. Only the judged check gave a verdict. A reviewed
answer of a single call is asked its judged check alone, so the placeholders
of `is_json`, `json_schema`, `length` and `latency_budget` gave none, and
wait for a case the application answers.

A person made each run the reference of its suite:

```console
$ digline promote --suite eval/screening/suite.toml --run latest --replacing none
tenant 'acme' · screening baseline set to 2026-11-07T10-35-18-897245-00-00-98ea9e30692a365a
```

```console
$ digline promote --suite eval/job-ad/suite.toml --run latest --replacing none
tenant 'acme' · job-ad baseline set to 2026-11-07T10-35-19-833594-00-00-864f71b825690ccc
```

```console
$ digline promote --suite eval/candidate-reply/suite.toml --run latest --replacing none
tenant 'acme' · candidate-reply baseline set to 2026-11-07T10-35-20-498179-00-00-176631b427e4199e
```

**Three gates.** A candidate then asked a question the reply prompt could not
answer:

```python
# later.py
from hiring import reply_to

print(reply_to("Do you sponsor work visas?"))
```

```console
$ ANTHROPIC_BASE_URL=http://127.0.0.1:18799 ANTHROPIC_API_KEY=fake python later.py
I do not know.
```

The person said no to it:

```console
$ digline record import --tenant acme --suite eval/candidate-reply/suite.toml --bad cap-e86d1ffe511d405b-1bc2c6cb --by 'Ada Lovelace'
tenant 'acme' · suite candidate-reply · writes to eval/candidate-reply/captured.json · repository private · check llm_rubric
  wrote cap-e86d1ffe511d405b-1bc2c6cb
1 case written to eval/candidate-reply/captured.json: the diff is the review and the commit is the signature; nothing was committed, run or promoted (ADR 0023 §7)
```

Each suite ran again, `screening` and `job-ad` as before. The run of
`candidate-reply` said what its judge did, and exited `0`:

```console
$ ANTHROPIC_BASE_URL=http://127.0.0.1:18799 ANTHROPIC_API_KEY=fake digline run --suite eval/candidate-reply/suite.toml
digline: tenant 'acme' · 0 cases × 3 samples = 0 calls to the target; 3 reviewed answers judged 27 times, with no call to the target; each answer is judged 3 times by llm_rubric
digline: judge: 27 calls · counts: 4860 in / 378 out · cost: 0.006750 USD
digline: the judge contradicted a person on 1 reviewed answer.
digline: recorded .digline/acme/runs/candidate-reply/2026-11-07T10-35-59-970252-00-00-176631b427e4199e.json
digline: next: digline compare --suite eval/candidate-reply/suite.toml --run latest  # says whether anything got worse
2026-11-07T10-35-59-970252-00-00-176631b427e4199e
```

The gate is `digline compare`, once per suite:

```console
$ digline compare --suite eval/screening/suite.toml --run latest
Nothing got worse compared with the reference. Every case could be judged. No case is suspended. The suite's checks are unchanged from the reference.
tenant 'acme', against baseline 2026-11-07T10-35-18-897245-00-00-98ea9e30692a365a
```

> **Arrives with digline 1.3.** On 1.2.0 the sentence reads *The suite is
> unchanged from the reference.*, here and below.

```console
$ digline compare --suite eval/job-ad/suite.toml --run latest
Nothing got worse compared with the reference. Every case could be judged. No case is suspended. The suite's checks are unchanged from the reference.
tenant 'acme', against baseline 2026-11-07T10-35-19-833594-00-00-864f71b825690ccc
```

```console
$ digline compare --suite eval/candidate-reply/suite.toml --run latest
The judge contradicted a person on 1 reviewed answer, and the case fails: cap-e86d1ffe511d405b-1bc2c6cb for llm_rubric, passed where the person said no. Nothing got worse compared with the reference. Every case could be judged. No case is suspended. The suite's checks are unchanged from the reference.
tenant 'acme', against baseline 2026-11-07T10-35-20-498179-00-00-176631b427e4199e
```

The first two exited `0` and the third `1`. The judge passed an answer the
person said no to, and which of the two is wrong is the person's to say.

## What you get, and what stays out

**Three prompts are three suites, and three verdicts.** Each has its own
recordings, its own proposal, its own reviewed answers, its own reference
and its own exit code. There is no verdict of the application: digline does
not say whether the hiring tool, as a whole, got worse.

**`pytest-digline` holds the three in one session**, one line per suite, and
the session does not end green if any of them is not. This block was run
again on 2026-11-07, with digline and pytest-digline at `1b5cf083`, over the
same recordings, reviewed answers, references and runs, made again with
it from the start, after its failure row came to name the contradiction:

```console
$ pytest -q -p no:cacheprovider --digline-suite eval/screening/suite.toml --digline-suite eval/job-ad/suite.toml --digline-suite eval/candidate-reply/suite.toml
.......F                                                                 [100%]
=================================== FAILURES ===================================
__________________ cap-e86d1ffe511d405b-1bc2c6cb::llm_rubric ___________________
digline: cap-e86d1ffe511d405b-1bc2c6cb · llm_rubric
  llm_rubric passed where the person said no.
  reason: mean of 3 samples (1.000000, 1.000000, 1.000000)
=================================== digline ====================================
eval/screening/suite.toml: Nothing got worse compared with the reference. Every case could be judged. No case is suspended. The suite's checks are unchanged from the reference.
eval/job-ad/suite.toml: Nothing got worse compared with the reference. Every case could be judged. No case is suspended. The suite's checks are unchanged from the reference.
eval/candidate-reply/suite.toml: The judge contradicted a person on 1 reviewed answer, and the case fails: cap-e86d1ffe511d405b-1bc2c6cb for llm_rubric, passed where the person said no. Nothing got worse compared with the reference. Every case could be judged. No case is suspended. The suite's checks are unchanged from the reference.
eval/candidate-reply/suite.toml: digline exits 1, so this session does not end green.
=========================== short test summary info ============================
FAILED eval/candidate-reply/suite.toml::cap-e86d1ffe511d405b-1bc2c6cb::llm_rubric
1 failed, 7 passed in 0.11s
```

It exited `1`. The session's exit says that one of the three suites is
red, and nothing more: it is not a verdict of the application, and it
weighs no suite against another. It compares the latest stored run of each
suite with its reference and never runs one, unless given `--digline-run`.

- **The GitHub Action takes one suite**, its `suite` input. Three suites are
  three steps, and each keeps a comment of its own on the pull request.
- **A change to one prompt touches one suite.** The ad's new prompt gave
  `job-ad` a second setup, and only that suite's older answers stopped being
  electable. `screening` and `candidate-reply` kept the setup they had.
- **`digline run` exits `0` when the judge contradicts a person**, and says
  so on standard error. The verdict is `compare`'s.
- **No call in this story reached Anthropic or a model.** The application's
  answers, the judge's scores and the token counts the costs are printed from
  are the stand-in's.

The pages this one leans on: [`digline record`](../record.md),
[`digline suggest`](../suggest.md) and
[`digline view`](../view.md#-allow-record).
