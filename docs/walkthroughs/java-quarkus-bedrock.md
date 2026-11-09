# A Quarkus application on Bedrock, from its first call to a gate

This page records the calls a Quarkus application makes to Bedrock,
turns the recordings into a suite, and ends with a gate on it.

## Who this is for

An application on Quarkus that calls Bedrock through the AWS SDK for Java v2,
`software.amazon.awssdk:bedrockruntime`, with the client built by a bean, and
that calls `converse` or `invokeModel` with an Anthropic model.

Everything on this page was run, on 2026-11-06, with digline installed from
this repository at `b28fdef8`, Quarkus 3.40.1.1 and the SDK 2.57.8. **No call
reached AWS or a model.** A stand-in for Bedrock on 127.0.0.1 answered the
application and the judge, and every answer, score and token count below is
the stand-in's. The SDK and the judge were pointed at it with
`AWS_ENDPOINT_URL_BEDROCK_RUNTIME`, which both read; on your machine that
variable is left out and Bedrock answers. Paths are shortened to `…`.

## Day one: recording

**Three files.** Copy `DiglineRecorder.java`, `DiglineAws.java` and
`DiglineMessages.java` from `recorders/java/src/main/java/dev/digline/` into
your project, in the package `dev.digline`
([which files, for which client](../record-java.md#with-an-official-sdk-the-files-to-copy)).

**One line on the builder**, in the bean that builds the client:

```java
@ApplicationScoped
public class BedrockClients {

    @ConfigProperty(name = "digline.root")
    Path root;

    DiglineRecorder recorder;
    BedrockRuntimeClient client;

    @PostConstruct
    void build() {
        recorder = DiglineRecorder.development(root, "acme", "triage-app");
        client = BedrockRuntimeClient.builder()
                .overrideConfiguration(c -> c.addExecutionInterceptor(new DiglineAws(recorder)))
                .build();
    }

    public DiglineRecorder recorder() {
        return recorder;
    }

    public BedrockRuntimeClient client() {
        return client;
    }
}
```

Other beans reach the client and the recorder through `client()` and
`recorder()`. Read through an injected bean's fields, both were `null`: what
is injected is the bean's proxy.

**The root comes from configuration**, `digline.root`, and not from the
working directory: the jar below and `mvn test` were each given theirs, and
the tests recorded or not by which one they were given (the last section).
Here it is set by the environment, `DIGLINE_ROOT`, the name MicroProfile
Config maps it to.

**The suite is named around the call.** A turn of the agent, Converse until
the model stops asking for a tool, is one episode, and its calls name the
suite inside it:

```java
try (var episode = bedrock.recorder().episode("triage", Map.of("ticket", ticket));
        var calls = DiglineRecorder.suite("triage")) {
    try {
        String answer = turn(ticket);
        episode.output(answer);
        return answer;
    } catch (RuntimeException failed) {
        episode.interrupted();
        throw failed;
    }
}
```

A single call names its suite through one method every call goes through:

```java
<T> T ask(String feature, Supplier<T> call) {
    try (var suite = DiglineRecorder.suite(feature)) {
        return call.get();
    }
}
```

```java
return ask("triage", () -> bedrock.client().invokeModel(r -> r
        .modelId(MODEL)
        .body(SdkBytes.fromString(body, StandardCharsets.UTF_8)))
        .body().asUtf8String());
```

**Development and production.** `DiglineRecorder.development` files every
recording under one tenant, and a switch file that leaves its values out
takes the defaults. An application that resolves its tenant per request is
production:

```java
recorder = DiglineRecorder.production(root, () -> tenantOf(request), "triage-app");
```

It refused to start on the file `digline record on` writes, which declares
none of the three values production asks for. It said:
*"switches recording on in production with no declared redaction (write
redact = "none", the one this release implements); no declared sampling
(write sample = p, above 0 and at most 1); no ceiling on the size of its
recordings (write ceiling = N, in bytes). In production all three are
declared (ADR 0058 §10)"*.

**Switch it on, and run the application**, from the project's root. The
first block was run again on 2026-11-07, with digline at `1b5cf083`, after
the sentence on production came to name Node:

```console
$ digline record on --tenant acme
recording on for tenant 'acme': …/triage/.digline/acme/recorder.toml
  values: on true, sample 1.0 (default), redact none (default), ceiling 104857600 bytes (default), interval 5.0 s (default)
  development: what the file leaves out is a default; an application that resolves its tenant per request is production (wrap(tenant=callable) in Python, DiglineRecorder.production in Java and Node; the proxy's --tenant is never production), and refuses this file unless it declares sample, redact and ceiling
```

```console
$ DIGLINE_ROOT=$PWD AWS_ENDPOINT_URL_BEDROCK_RUNTIME=http://127.0.0.1:18790 AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=fake AWS_SECRET_ACCESS_KEY=fake java -jar target/quarkus-app/quarkus-run.jar
__  ____  __  _____   ___  __ ____  ______ 
 --/ __ \/ / / / _ | / _ \/ //_/ / / / __/ 
 -/ /_/ / /_/ / __ |/ , _/ ,< / /_/ /\ \   
--\___\_\____/_/ |_/_/|_/_/|_|\____/___/   
2026-11-06 14:49:40,303 INFO  [io.quarkus] (main) triage 1.0.0-SNAPSHOT on JVM (powered by Quarkus 3.40.1.1) started in 0.574s. Listening on: http://0.0.0.0:8080
2026-11-06 14:49:40,308 INFO  [io.quarkus] (main) Profile prod activated. 
2026-11-06 14:49:40,308 INFO  [io.quarkus] (main) Installed features: [cdi, rest, smallrye-context-propagation, vertx]
digline recorder: invoke_model on amazon.titan-text-express-v1: this model family is not recorded
```

The application answered seven requests: two tickets through `invokeModel`,
four through the Converse turn, and one `invokeModel` on Titan, whose line is
the last above. The tickets went in through the application's own endpoint:

```console
$ curl -s -X POST --data 'Where is my refund for the blue jacket?' http://127.0.0.1:8080/triage/converse
{"category": "refund"}
```

```console
$ digline record status --tenant acme
tenant 'acme' · recording on
  switch:     …/triage/.digline/acme/recorder.toml
  values:     on true, sample 1.0 (default), redact none (default), ceiling 104857600 bytes (default), interval 5.0 s (default)
  writes to:  …/triage/.digline/acme/recordings
  size:       11732 bytes of recordings (as written; disk use is higher), ceiling 104857600
  suite triage: 6 calls, 4 inside episodes, 0 orphans, 4 episodes; since the last import: not read (pass --suite)
  not counted: 1 process keeps recordings and no counts, so what was not recorded there is not known
```

Six calls: the two `invokeModel` calls and the four Converse calls, each
inside its episode. The Titan call is not among them, and the last line is
why the status cannot count it: the Java writer keeps no counts file.

## Day two: from recordings to a suite

**A first suite, proposed**, from a directory `eval/` in the project:

```console
$ digline suggest --suite triage --tenant acme --repository private --root ..
digline suggest: wrote …/triage/eval/suite.proposed.toml. It is a proposal, not a suite: no command of digline reads it, nothing in it is a verdict, and no answer was marked. Adopt its lines into your suite, and the commit is yours
assumed:
  the form: suite.toml, the suite does not exist yet; the proposal is always TOML, and a target that is a function needs a suite.py (docs/declarative.md, What it cannot say)
  the setup its target reproduces: 9bd4f0e5 for single calls; 27430ce2 for episodes
  to read how two setups differ, once the proposal is your suite: digline record compare --tenant acme --suite <your suite> --setup 9bd4f0e5 27430ce2 --show-setup
  the judge: none read: llm_rubric is proposed with judge = "provider/model", a placeholder that is refused until you name the provider plugin and the model, which are yours to choose; the provider plugins installed here: anthropic, bedrock
  each check: 1. is_json, every one of 6 recordings answers JSON, top level object
  each check: 2. json_schema, the draft requires the keys every one of 6 recordings carries
  each check: 3. never, declared to the model and called in none of 6 recordings
  each check: 4. never, declared to the model and called in none of 6 recordings
  each check: 5. max_steps, the model's turns, in an agent's episode; limit is a placeholder, the strictest the check accepts: no run measured it
  each check: 6. latency_budget, every one of 6 recordings carries it, and the target has to report it too; max_ms is a placeholder, the strictest the check accepts: no run measured it; tolerance is a placeholder
  each check: 7. llm_rubric, the judged check the capture reviews answers for, asked three times with two in three to agree; threshold is a placeholder, the strictest the check accepts: no run measured it; the rubric, the judge and the tolerance are placeholders
  each starting number: no run read; 7 placeholders, each the strictest value its check accepts and marked in the file, failing until a measured number replaces it
  the calibration band: a skeleton for llm_rubric, with the answer to paste and the band to place, strictly between 0 and 1, both yours
  the counterexample: counterexample-1, constructed and marked as constructed: its input is yours to write, one whose answer llm_rubric must refuse, and nothing in it was recorded
  the regime: repository = 'private': without an assistant, the file quotes no recorded input or answer; the rules read from the recordings, a tool's name or a key, are in its checks
not yet examined: group 1 · single calls, text · 2 answers from 2 recordings
not yet examined: group 2 · episodes, text · 4 answers from 4 recordings
to examine them, once the proposal is your suite: digline record import --tenant acme --suite <your suite>
```

The two `never` checks are the two tools every call declares,
`lookup_order` and `escalate`, which no recording called. In the file, `max_steps` reads:

```toml
[[assertions]]
# the model's turns, in an agent's episode; limit is a placeholder, the
# strictest the check accepts: no run measured it
type = "max_steps"
limit = 1  # placeholder: yours to write
count = "model"
```

**A placeholder** is the strictest value its check accepts, written where no
run measured one, and marked `# placeholder`. It is replaced by hand with a
number the runs measured ([the guide](../guide.md), chapters 4 and 5). Which
placeholder can fail depends on the cases. Here every case is a reviewed
answer: the judged check runs on each of them, and the checks on the steps on
each episode, so `limit = 1` is asked of every turn. `is_json`, `json_schema`
and `latency_budget` produced no verdict on these cases, and wait for a case
the target answers.

**Adopting it** is copying the file to `suite.toml` and writing what it leaves
to you: where the suite runs, the rubric and the judge.

```console
$ diff suite.proposed.toml suite.toml
11c11
< # environment = WRITE: mandatory, with no default: where it runs
---
> environment = "dev"
75,76c75,76
<   rubric = "WRITE: one question a good answer says yes to"  # placeholder: yours to write
<   judge = "provider/model"  # placeholder: yours to write, docs/declarative.md#the-judge-by-coordinates
---
>   rubric = "Is the category right for the ticket?"
>   judge = "bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0"
```

**A person's yes or no**, on the page `digline view` serves with
`--allow-record`:

```console
$ digline view --suite eval/suite.toml --allow-record
digline view on http://127.0.0.1:7373/?launch=… — the recorder's writes enabled, for the first browser that opens this address; --allow-promote to promote — ctrl-c to stop
```

Its *Recordings* view lists what `digline record import` lists, in two
groups: *a single call, text*, the two `invokeModel` answers, and *an
episode, text, steps model, finish stop*, the four turns. Each answer is a
row with its id, when it was first recorded, its setup and its answer, and
each that can be written has two choices, `--good` and `--bad`. Under them
is one field, *Your name, the mark each case carries (--by)*, and one button,
*Write the answers named*. Under the button is the command that does what
the button does, served as `digline record import --tenant acme --suite
eval/suite.toml`; the page says it follows the form as you fill it in, where
its script runs. With the choices and the name written out, it is:

```console
$ digline record import --tenant acme --suite eval/suite.toml --good cap-2ff5a5465dc6d823-f8b3a680 --good cap-a6bd9f85bafda9c3-cdd80da0 --bad cap-379139c501bdf803-cdd80da0 --good cap-85b5e8c071506b9e-f8b3a680 --by 'Ada Lovelace'
tenant 'acme' · suite triage · writes to eval/captured.json · repository private · check llm_rubric
  wrote cap-85b5e8c071506b9e-f8b3a680
tenant 'acme' · suite triage · writes to eval/captured.json · repository private · check llm_rubric
  wrote cap-2ff5a5465dc6d823-f8b3a680
tenant 'acme' · suite triage · writes to eval/captured.json · repository private · check llm_rubric
  wrote cap-a6bd9f85bafda9c3-cdd80da0
tenant 'acme' · suite triage · writes to eval/captured.json · repository private · check llm_rubric
  wrote cap-379139c501bdf803-cdd80da0
4 cases written to eval/captured.json: the diff is the review and the commit is the signature; nothing was committed, run or promoted (ADR 0023 §7)
```

The button and this command, given the same four answers and the same name,
wrote the same `captured.json`, byte for byte. The no is the turn that
answered `other` to *"I want my money back for the shoes."*

**The run, and the gate.** The suite's cases are reviewed answers, so the
run asks the judge and never the application:

```console
$ AWS_ENDPOINT_URL_BEDROCK_RUNTIME=http://127.0.0.1:18790 AWS_DEFAULT_REGION=us-east-1 AWS_ACCESS_KEY_ID=fake AWS_SECRET_ACCESS_KEY=fake digline run --suite eval/suite.toml
digline: tenant 'acme' · 0 cases × 3 samples = 0 calls to the target; 4 reviewed answers judged 36 times, with no call to the target; each answer is judged 3 times by llm_rubric
digline: judge: 36 calls · counts: 756 in / 216 out · cost: 0.002020 USD
2026-11-06T13-50-44-669754-00-00-6ef68ce91ee1a1dd
digline: recorded .digline/acme/runs/triage/2026-11-06T13-50-44-669754-00-00-6ef68ce91ee1a1dd.json
digline: next: digline promote --suite eval/suite.toml --run latest --replacing none  # keeps this run as the reference
```

The judge's region is `boto3`'s, which reads `AWS_DEFAULT_REGION` and not
`AWS_REGION`. A run without it took the region of the machine's profile,
where the judge's model had no price, and no answer could be judged. The run
exited `0`, and a person made it the reference:

```console
$ digline promote --suite eval/suite.toml --run latest --replacing none
tenant 'acme' · triage baseline set to 2026-11-06T13-50-44-669754-00-00-6ef68ce91ee1a1dd
```

**When a check on the steps contradicts a yes.** A later ticket made the turn
ask for `lookup_order`, so the turn took two model calls and a tool call:

```console
$ curl -s -X POST --data 'I want a refund for order 42.' http://127.0.0.1:8080/triage/converse
{"category": "refund"}
```

The answer is right, and the person said yes to it:

```console
$ digline record import --tenant acme --suite eval/suite.toml --good cap-baa842f3dfae2b30-f8b3a680 --by 'Ada Lovelace'
tenant 'acme' · suite triage · writes to eval/captured.json · repository private · check llm_rubric
  wrote cap-baa842f3dfae2b30-f8b3a680
1 case written to eval/captured.json: the diff is the review and the commit is the signature; nothing was committed, run or promoted (ADR 0023 §7)
```

```console
$ AWS_ENDPOINT_URL_BEDROCK_RUNTIME=http://127.0.0.1:18790 AWS_DEFAULT_REGION=us-east-1 AWS_ACCESS_KEY_ID=fake AWS_SECRET_ACCESS_KEY=fake digline run --suite eval/suite.toml
digline: tenant 'acme' · 0 cases × 3 samples = 0 calls to the target; 5 reviewed answers judged 45 times, with no call to the target; each answer is judged 3 times by llm_rubric
digline: judge: 45 calls · counts: 945 in / 270 out · cost: 0.002524 USD
digline: checks on the steps contradicted a person on 1 reviewed answer: never, on case cap-baa842f3dfae2b30-f8b3a680; max_steps, on case cap-baa842f3dfae2b30-f8b3a680.
2026-11-06T13-51-08-432933-00-00-6ef68ce91ee1a1dd
digline: recorded .digline/acme/runs/triage/2026-11-06T13-51-08-432933-00-00-6ef68ce91ee1a1dd.json
digline: next: digline compare --suite eval/suite.toml --run latest  # says whether anything got worse
```

```console
$ digline explain --suite eval/suite.toml --run latest
What ran
Checks on the steps contradicted a person on 1 reviewed answer: never, on case cap-baa842f3dfae2b30-f8b3a680; max_steps, on case cap-baa842f3dfae2b30-f8b3a680, and each fails: cap-baa842f3dfae2b30-f8b3a680 for never, failed where the person said yes; cap-baa842f3dfae2b30-f8b3a680 for max_steps, failed where the person said yes. They are counted in no aggregate, and the target was not asked for them.
5 cases ran.
17 checks ran.
Every case could be judged.
No case is suspended.
The suite is unchanged from the reference.

What differed underneath
Nothing in this group.

What moved
cap-baa842f3dfae2b30-f8b3a680 · never failed at 0.000000, and a person said yes to the turn: its steps contradict the person, and the case fails.
cap-baa842f3dfae2b30-f8b3a680 · max_steps failed at 0.000000, and a person said yes to the turn: its steps contradict the person, and the case fails.
```

A yes on a turn is a yes to its steps too. Here the person vouched for a turn
that called `lookup_order`, which the suite says is never called, and that
took two model turns, past the placeholder `limit = 1`. Which of the two is
wrong, the rule or the yes, is the person's to say.
`digline compare --suite eval/suite.toml --run latest` exits `1`.

## What you get, and what stays out

- **Recorded**: Converse, in a turn or as a single call, and `invokeModel`
  with an Anthropic model, whose body is Messages. **Not recorded**:
  `invokeModel` on another family. The Titan call above wrote no recording
  and said so on standard error
  ([which calls](../record-java.md#with-an-official-sdk-the-files-to-copy)).
- **Converse and `invokeModel` record different setups.** Mixed as single
  calls in one suite, they are two setups of one form, and only the newest
  one's answers can be written: run with the `invokeModel` calls first and
  four Converse calls after, the import listed the two `invokeModel` answers
  as *not electable: recorded only under earlier setups*. The Java page
  recommends Converse for new code.
- **`mvn test` records**, with the switch on, when the tests run against the
  root that holds it: a Quarkus test that called the turn once, with
  `DIGLINE_ROOT` at the project, added two recordings, the call and its
  episode. With `DIGLINE_ROOT` at `target/`, which holds no `.digline/`, it
  added none.
- **No call in this story reached AWS or a model.** The application's
  answers, the judge's scores and the token counts the costs are printed
  from are a stand-in's.

The pages this one leans on: [the Java recorder](../record-java.md),
[`digline suggest`](../suggest.md), [`digline record`](../record.md) and
[`digline view`](../view.md#-allow-record).
