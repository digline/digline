# Calibrating a judge

A check that calls a model, `LlmRubric` or `Faithfulness`, measures the system
through a judge, and every number it produces is as good as the judge. digline
has four ways to ask whether the judge can be believed. Each answers a
different question, each is read in a place you already look, and none is a
command of its own. This page puts the four in one suite and says what to read
and where. It does not say what to conclude: that is yours.

| Question | What to declare | Where it shows | What it moves |
|---|---|---|---|
| Does the judge agree with a person? | a reviewed answer | `explain`, the report, `compare --json` | exit `1` where it does not |
| Does the judge use the scale? | a calibration case | `explain`, the report | exit `2` where a score leaves its band |
| Does the judge agree with the labels? | `Accuracy`, `Precision`, `Recall` on labelled cases | the aggregate's verdict and its counts | the aggregate's own gate |
| Does the judge agree with itself? | `Repeated` with `min_agreement` | each verdict's `agreement` and `scores` | `error` below the floor |

## The suite

One judge, here a function that scores from a table so the run can be read
line by line. Its answers are the shapes the four tools are for: two good
answers and two bad ones with labels, one answer the judge is of two minds
about, two answers a person said yes and no to, and two answers known to be
partly right.

```python
from digline.core import Accuracy, JudgeReply, LlmRubric, Precision, Repeated
from digline.run import Calibration, Case, Response, ReviewedAnswer, Suite

QUESTION = "How long does a refund take?"

#: What the judge scores each answer, by a word the answer carries.
SCORES = {
    "fourteen": 1.0,
    "thirty": 0.0,
    "instant": 0.9,
    "partial": 0.5,
    "receipt": 0.95,
}


#: An answer the judge is of two minds about: its votes alternate.
VOTES = iter([1.0, 0.0] * 100)


def judge(prompt: str) -> JudgeReply:
    if "maybe" in prompt:
        return JudgeReply(score=next(VOTES), reason="read 'maybe'")
    for word, score in SCORES.items():
        if word in prompt:
            return JudgeReply(score=score, reason=f"read '{word}'")
    return JudgeReply(score=0.0, reason="no known word")


ANSWERS = {
    "good-1": "Refunds take fourteen days.",
    "good-2": "Refunds take fourteen days from the return.",
    "bad-1": "Refunds take thirty days.",
    "bad-2": "Refunds take thirty days and a receipt-free form.",
}

suite = Suite(
    tenant="acme",
    environment="dev",
    name="refunds",
    assertions=[
        Repeated(
            inner=LlmRubric(
                rubric="Is the refund period right?",
                judge=judge,
                threshold=0.7,
                tolerance=0.05,
            ),
            samples=3,
            min_agreement="3/3",
        )
    ],
    run_assertions=[
        Accuracy(over="llm_rubric", threshold="1/2", tolerance="0"),
        Precision(over="llm_rubric", threshold="1/2", tolerance="0"),
    ],
    cases=[
        Case(id="good-1", vars={"answer": ANSWERS["good-1"]}, label="positive"),
        Case(id="good-2", vars={"answer": ANSWERS["good-2"]}, label="positive"),
        Case(id="bad-1", vars={"answer": ANSWERS["bad-1"]}, label="negative"),
        Case(id="bad-2", vars={"answer": ANSWERS["bad-2"]}, label="negative"),
        Case(
            id="unsure", vars={"answer": "Refunds take maybe a week."}, label="positive"
        ),
        Case(
            id="said-yes",
            reviewed_answer=ReviewedAnswer(
                output="Fourteen days, counted from the return: fourteen.",
                check="llm_rubric",
                good=True,
                input=QUESTION,
            ),
        ),
        Case(
            id="said-no",
            reviewed_answer=ReviewedAnswer(
                output="Refunds are instant.",
                check="llm_rubric",
                good=False,
                input=QUESTION,
            ),
        ),
        Case(
            id="half-right",
            calibration=Calibration(
                output="A partial answer: the period, and not the form.",
                check="llm_rubric",
                low=0.3,
                high=0.7,
                input=QUESTION,
            ),
        ),
        Case(
            id="mostly-right",
            calibration=Calibration(
                output="Mostly right, and it asks for a receipt.",
                check="llm_rubric",
                low=0.6,
                high=0.9,
                input=QUESTION,
            ),
        ),
    ],
    samples=2,
    min_agreement="2/2",
)


def target(case: Case) -> Response:
    return Response(output=str(case.vars["answer"]), input=QUESTION)
```

```console
$ digline run --suite suite.py
$ digline explain --suite suite.py --run latest
What ran
1 calibration case scored outside its declared band: mostly-right for llm_rubric at 0.950000, above 0.600000–0.900000. The judged scores in this run are not placed on the scale they are compared on. It is counted in no aggregate, and the target was not asked for it.
The judge contradicted a person on 1 reviewed answer, and the case fails: said-no for llm_rubric, passed where the person said no. It is counted in no aggregate, and the target was not asked for it.
9 cases ran.
9 checks ran.
8 of 9 cases judged, 1 could not be.
No case is suspended.
2 checks measured a band that covers their own threshold, so which side they landed on is a property of the samples that were drawn.

How the judge agrees with the person
llm_rubric, held in: blind, 1 of 2 agree (1 passed a no, 0 failed a yes); after review, 1 of 2 agree (1 passed a no, 0 failed a yes).
No reviewed answer is held out: the agreement above was measured on the answers the rubric was tuned on.
No answer is set apart as unstable: this run's stability was not measured, so every answer is counted.
This suite does not say what a yes means.

How it was set up
Nothing in this group.

What it found
said-no · llm_rubric passed at 0.900000, and a person said no to the answer: the judge contradicts the person, and the case fails.
bad-1 · llm_rubric is under its bar at 0.000000. The bar is 0.700000.
bad-2 · llm_rubric is under its bar at 0.000000. The bar is 0.700000.
unsure · llm_rubric could not be judged.
```

`explain` exits `1`: a reviewed answer was contradicted, and that outranks
the `2` that a lost band and an unjudged case would give on their own.

## Does the judge agree with a person? Reviewed answers

A reviewed answer is an answer the application gave and a person's yes or no
about it, written by `digline record import` with `--good` or `--bad`, or by
hand. The target is not asked for it, and only the check it names runs on it,
except on an episode's answer, which carries its steps: the suite's checks on
the steps run beside it, and on a yes a red one is a contradiction
([API reference](api.md#casereviewed_answer-a-persons-yes-or-no-about-an-answer)).

**A suite of reviewed answers alone never calls the application.** It judges
the answers already recorded, and the plan `run` prints before the first call
says so: *0 cases × 3 samples = 0 calls to the target; 4 reviewed answers
judged 36 times, with no call to the target*. So a change to the application,
a new prompt or a fix in its code, is invisible to such a suite until the
application answers again: record, review and import, and the next run judges
the new answers. Until then a green run says the judge still agrees with the
person about the old ones. `digline where` reads the order: recordings made
after the last import hold the suite at `to_import`, and a setup that first
answered after the newest run is `new_setup`. A suite that should see a code
change on its own run needs cases the target answers, beside the reviewed
ones.

The judge passed `said-no`, an answer the person said no to. That is a
contradiction, and the case fails. Where to read it:

- **`explain`** names each one, its check, and which way the judge went:
  *passed where the person said no*, or *failed where the person said yes*,
  in the tally, and first among what the run found;
- **`explain --json`** carries them beside the count, on the `reviewed` fact:

  ```json
  {"about": "run", "contradictions": [{"case_id": "said-no", "check": "llm_rubric", "direction": "passed_no"}], "count": 1, "kind": "reviewed", "state": null}
  ```

- **the report** has a section, *What the judge said of the reviewed
  answers*, every reviewed answer beside what the judge found, open when the
  judge contradicted a person;
- **`compare --json`** counts the two directions on the headline,
  `reviewed_passed_no` and `reviewed_failed_yes`.

The two directions are counted apart because they are two faults: a judge
that passes what a person refused is lenient, one that fails what a person
accepted is strict. `said-yes`, where the judge agreed, is not in the
reading: among the three, only the report's section shows it.

### The judge first, the person blind, a revision after

*Arrives with digline 1.4.* A rubric tuned until the judge agrees with the
person, on the answers it is then measured on, agrees by construction. The
order that keeps the judge's verdict apart from the person's
([ADR 0067](adr/0067-calibrating-the-judge-against-a-person.md) §1, §2, §4):

- **Choose, then run.** `digline record import --choose ID` writes an answer
  **awaiting a verdict**, and the next run judges it before any person has:
  its verdict is in the stored run before the person's exists. An answer
  awaiting a verdict is in no gate and no aggregate; the headline, `explain`
  and `compare --json` (`awaiting`, `awaiting_unjudged`) say how many.
- **The person judges blind**, on the review page, which shows nothing of
  any run, under the suite's `review_rule`.
- **Two verdicts are kept.** The blind one, `good`, and the one after
  reading the disagreements, `revised`, written by `digline record revise`.
  The gate holds the newest, and the run records both, so the blind
  agreement and the agreement after review can be read apart.
- **Held in or held out.** `--held-out` marks the answers kept to test the
  rubric rather than tune it; held in is the default.
- **The agreement, criterion by criterion.** `explain` and the run's report
  read it per judged check, blind and after review, held in and held out,
  and close on the held-out figure alone: the one nobody tuned toward. A
  held-out answer is counted and never named
  ([explain](explain.md#the-judge-against-the-person)). The reading works on
  any run whose reviewed answers already carry the person's verdict, such as
  a new `digline run` after the review. The cheaper round, `digline rejudge
  --reviewed`, which judges the reviewed answers alone, comes with ADR 0067's
  third pull request. No answer is yet set apart as unstable, because
  stability is not measured in this release, and the reading says so.
- **About the whole answer.** `--whole` asks every judged check of the
  suite about one answer, with one verdict from the person: a yes expects
  each to pass, and a no names the checks that failed. Per answer it is
  cheaper for the person and dearer for the judge: judged checks × samples
  judgements, where a verdict about one check costs samples.

## Does the judge use the scale? Calibration cases

A calibration case is an answer you know to be partly right, and a band
strictly between `0` and `1` where a judge that still has a scale places it.
A judge collapsed onto `0` and `1` is more repeatable, not less, so no amount
of repetition sees the collapse; an answer that is half right, scored at the
edge, does ([API reference](api.md#casecalibration-watching-the-judges-scale)).

`half-right` scored `0.5` inside `0.3–0.7`. `mostly-right` scored `0.95`,
above its band `0.6–0.9`. Where to read it:

- **`explain`** names each case outside its band, its check, its score, the
  band and the side, `above` or `below`;
- **`explain --json`** carries them beside the count, on the `calibration`
  fact:

  ```json
  {"about": "run", "bands": [{"case_id": "mostly-right", "check": "llm_rubric", "high": 0.9, "low": 0.6, "score": 0.95, "side": "above"}], "count": 1, "kind": "calibration", "state": null}
  ```

- **the report** has a section, *Where the judge placed the calibration
  answers*, every calibration case against its band, open when one was left.

A band that was left exits `2`: the judged numbers in the run exist and are
not placed on the scale they are compared on. `digline promote` refuses such
a run.

## Does the judge agree with the labels? Accuracy, Precision and Recall

`Accuracy`, `Precision` and `Recall` count a confusion matrix over the cases
that carry a `label`, and read one per-case check, the one `over` names.
**The matrix reads that check's `pass` as agreement with the label**:

| label | the check passes | the check fails |
|---|---|---|
| `positive` | `true_positive` | `false_negative` |
| `negative` | `true_negative` | `false_positive` |

So the check named by `over` is meant to say whether the case agrees with its
mark, as `agrees_with_mark` does in chapter 7 of the [guide](guide.md). **An
ordinary judge says something else**: its `pass` is *a good answer*. Named as
`over` directly, its negatives read the other way round. Here the judge failed
`bad-1` and `bad-2`, the two answers labelled `negative`, which is the right
verdict on both, and the matrix counts them as two false positives. The
aggregate's reason, and the counts in its metadata, in the run document:

```text
accuracy 0.500000 = 2/4 (4 counted, 0 suspended, 1 could not be judged, 2 calibration, 2 reviewed)
```

```json
{"true_positive": 2, "false_positive": 2, "true_negative": 0, "false_negative": 0}
```

The judge was right on all four cases counted, and the figure reads `0.5`.
With a judge as `over`, read `false_positive` as *the judge failed a negative*
and `true_negative` as *the judge passed one*.

The reason also says what was left out, and every number in it is a case in
the suite: `unsure` could not be judged, and the two reviewed answers and the
two calibration cases are in no aggregate (*What is left out of a
denominator*, in [the metrics](metrics.md#what-is-left-out-of-a-denominator)).

## Does the judge agree with itself? Repeated and min_agreement

`Repeated` asks the judge several times about one answer and folds the votes,
and `min_agreement` is how many of them must share the majority verdict
([the metrics](metrics.md#repeated)). Here each answer is judged 3 times and
all 3 must agree. On `unsure` the judge voted one way and then the other:

```text
unsure · llm_rubric could not be judged.
```

and its reason, in the run document and the report, says why: *the samples did
not agree: 0.67 of them share the majority verdict*. Below the floor the
verdict is `error`, never a pass, so the case is unjudged and exits `2`.
`Suite(samples=…)` is another question: it asks the target again, not the
judge, and here it asks twice, so each verdict's `agreement`, `spread` and
`scores` are those two samples'.

The two decide the same way, and neither is a majority vote: the judgements'
mean is held against the check's `threshold`, and `min_agreement` is a floor
on the share that reached the majority verdict, below which the verdict is
`error`. Three judgements of 1, 0 and 0 against a threshold of 0.3 pass at
0.333333. For *at least k of n* with a judge that answers 0 or 1, the
threshold is k/n at six decimals, `0.666667` for two of three, with a
`min_agreement` that admits the split; `0.67` fails two of three. The [suite
as data](declarative.md#repeated-wraps-another-check) has the measurement.

## Choosing the judge

The sections above measure a judge once it is chosen. Choosing it is advice,
and this section is that: nothing in digline checks it.

- **A judge at least as able as the model it judges.** A smaller model asked
  whether a larger one's answer is right is asked a question it may not be
  able to answer, and a reviewed answer the judge contradicts is where that
  shows.
- **One check per criterion, rather than one long rubric.** A rubric that asks
  five things gives one score, and a fall in it does not say which of the five
  fell. Five checks, each named, fall one at a time, and `compare` names the
  one that did.
- **To choose between the two, declare both and read them.** *Arrives with
  digline 1.4.* Keep the composite check and one check per criterion in the
  suite, and say which are its criteria with `criteria` on the composite's
  table (`criteria = ["addressee", "language"]` in a `suite.toml`, or
  `Suite(criteria={"overall": ["addressee", "language"]})` in Python). On every
  reviewed answer about the whole answer, the agreement reading then names
  the answers where the composite is not the conjunction of its criteria. A
  name that is not a judged check of the suite is refused, and so is a check
  listed as its own criterion or under two composites. `criteria` is outside
  `config_hash` and every identity: it changes how a run is read, not what is
  checked. Once you have chosen, delete the other form
  ([ADR 0067](adr/0067-calibrating-the-judge-against-a-person.md) §5).
- **What one check per criterion costs.** Each judged check asks the judge
  once per answer. 50 cases at `samples = 3` with four checks, one per
  criterion, are 150 calls to the target and 600 to the judge; the same cases
  with one rubric that asks the four things are 150 and 150: *cases × samples
  × criteria* judge calls, against *cases × samples*. A `Repeated` of 3
  multiplies its check by 3 again. Counted on 2026-11-14 with a judge that
  counted its calls. Each of the four calls sends the answer again, so the
  answer's tokens are paid four times: what that buys is a fall that names its
  criterion.
- **In a rubric that asks several things, each exception says which criterion
  it applies to.** *Asking a clarifying question is a correct answer* is an
  exception to *answers the question*; written loose in a rubric that also
  asks for the person's language and no internal ids, it reads as an
  exception to all of them.
- **The exceptions, with their examples, are the part that aligns the rubric
  with the person.** They are where a reviewer's judgement is written down,
  case by case, and not noise to trim when the rubric is shortened.
- **A few cases first.** Point the suite's `cases` at a file of three to five,
  run it with a ceiling, `digline run --suite suite.toml --max-cost 0.50`, and
  read what the judge said of each before paying for every case.

**Criteria a product assistant is usually held to**, each a check of its own.
These four, in a suite that loaded on 2026-11-12 at `2aaae91d`:

```toml
[[assertions]]
type = "llm_rubric"
name = "addressee"
rubric = "Does the answer speak to the person who asked, and not about them to someone else?"
judge = "anthropic/claude-haiku-4-5"
threshold = 0.7
tolerance = 0.05

[[assertions]]
type = "llm_rubric"
name = "no_internal_ids"
rubric = "Is the answer free of internal identifiers: ticket numbers, database ids, internal codes the person was not given?"
judge = "anthropic/claude-haiku-4-5"
threshold = 0.7
tolerance = 0.05

[[assertions]]
type = "llm_rubric"
name = "clarifies_or_answers"
rubric = "Does the answer either answer the question, or ask one clarifying question where the question cannot be answered as asked? Asking is a correct answer here."
judge = "anthropic/claude-haiku-4-5"
threshold = 0.7
tolerance = 0.05

[[assertions]]
type = "llm_rubric"
name = "same_language"
rubric = "Is the answer in the language the question was asked in?"
judge = "anthropic/claude-haiku-4-5"
threshold = 0.7
tolerance = 0.05
```

`name` is what tells them apart: four checks of the same type under the
default name would be one name four times. The third says what a rubric for
an assistant usually forgets, that asking back can be the right answer.

## What the application did to the answer

**A recording holds what the model answered, not what the application
showed.** The recorder and the proxy record the provider's reply. An
application that post-processes it, taking out internal markers, citation
tags or a block of reasoning before the person sees the answer, leaves those
in the recording, and the import writes them into the reviewed answer the
judge reads. A judge that reads them as part of the answer may fail it for
text nobody was shown.

Two ways, and where each one works:

- **Say it in the rubric**, for every suite and on the command line: *"Text
  between `[[` and `]]` is the application's internal markup, removed before
  the person reads the answer: judge the answer without it."* Whether the judge
  then leaves it out is what a reviewed answer that carries markers measures.
- **Judge what the application shows**: a suite's target that is a function
  of yours can return the answer after the application's own post-processing,
  so the answers the target gives carry no markers. A recorded answer cannot
  be changed this way: `digline run` passes the answer to its judge as it was
  recorded, with no step between, and only a caller of `execute()` in Python
  can pass a `mapper` that would.

## See also

- [The API reference](api.md), for `ReviewedAnswer`, `Calibration` and the
  exit codes.
- [`digline record`](record.md), which writes reviewed answers from what your
  application answered.
- [`digline explain`](explain.md), the reading this page quotes.
- [Letting an agent propose a suite](proposing-a-suite.md), where a coding
  agent proposes the suite, its calibration case and its counterexample, and
  you decide.
