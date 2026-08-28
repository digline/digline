# digline-bedrock

An [Amazon Bedrock](https://aws.amazon.com/bedrock/) target **and judges** for
[digline](https://pypi.org/project/digline/), on the Converse API: a prompt file
goes in, a priced `Response` comes out.

```sh
pip install digline-bedrock
```

**Requires Python 3.12+**, like digline itself.

## Quickstart

No credential argument exists: the AWS chain — environment, profile, IAM role,
instance metadata — is boto3's job, and this package never reads it.

```python
from digline_bedrock import BedrockTarget

target = BedrockTarget(
    "prompts/answer.md",
    model="eu.anthropic.claude-sonnet-4-20250514-v1:0",
    max_tokens=1024,
)
```

`model` takes a model id or an inference profile id. The **region** is resolved
when the target is built — from `region=` if you pass one, otherwise from the
client the chain produced — and the price list follows from it:

```python
from digline_bedrock import BedrockTarget

target = BedrockTarget(
    "prompts/answer.md",
    model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    max_tokens=1024,
    region="us-east-1",
)
```

`target.region` is read-only, and that is the point: what was priced is what was
called. A missing region fails **there**, when the target is built, not on case
thirty-seven with thirty-six paid calls behind it.

## The judges run in the same account

A plugin is a target **and** a judge ([ADR
0004](https://github.com/digline/digline/blob/main/docs/adr/0004-every-plugin-is-a-target-and-a-judge.md)),
which on Bedrock is usually the whole reason the model is there: what a judge is
sent is the model's *output*, and it stays inside the same account, the same
region and the same IAM role.

```python
from digline.core import LlmRubric
from digline_bedrock import BedrockJudge

judge = BedrockJudge(model="eu.anthropic.claude-haiku-4-5-20251001-v1:0")
rubric = LlmRubric(
    rubric="The answer is one sentence and cites the passage it came from.",
    judge=judge,
    threshold=0.8,
    tolerance=0.05,
)
```

```python
from digline.core import Faithfulness
from digline_bedrock import BedrockClaimJudge

faithful = Faithfulness(
    judge=BedrockClaimJudge(model="eu.anthropic.claude-haiku-4-5-20251001-v1:0"),
    threshold=0.9,
    tolerance=0.05,
)
```

Converse has no structured-output mode, so the reply shape is asked for in the
system prompt and read back leniently — a fenced block or a sentence in front of
the object both parse. What judging cost is counted on the judge and never
reset:

```python
from digline_bedrock import BedrockJudge

judge = BedrockJudge(model="eu.anthropic.claude-haiku-4-5-20251001-v1:0")
print(f"{judge.calls} judgements, {judge.spent_usd:.4f} USD, {judge.latency_ms:.0f} ms")
```

## Prices, and what is not priced

`bedrock_pricing(region)` is seeded for **us-east-1, us-west-2, eu-west-1,
eu-central-1 and eu-west-3**, with the Anthropic models. Bedrock prices by model
*and* by region, and a figure invented for a region nobody checked would be
wrong in the direction nobody notices — so everything else raises at `preflight`
and is served with one argument:

```python
from digline.targets import ModelPrice
from digline_bedrock import BedrockTarget, bedrock_pricing

target = BedrockTarget(
    "prompts/answer.md",
    model="amazon.nova-pro-v1:0",
    max_tokens=1024,
    region="us-east-1",
    pricing=bedrock_pricing("us-east-1").override(
        "amazon.nova-pro-v1:0", ModelPrice(input_per_mtok=0.80, output_per_mtok=3.20)
    ),
)
```

An **application inference profile** is an ARN and is opaque: it is never in the
list, fails `preflight`, and is served the same way. That is intended, not a
gap — a run that cannot say what it cost must not run.

A model you brought in through **Custom Model Import**, or one behind
**Provisioned Throughput**, has no per-token bill at all: it is billed by
model-copy-hour and model-unit-hour. Say so out loud rather than leaving it
unpriced:

```python
from digline_bedrock import BedrockTarget, free

target = BedrockTarget(
    "prompts/answer.md",
    model="my-imported-model",
    max_tokens=1024,
    region="eu-west-1",
    pricing=free("my-imported-model"),
)
```

## The details that bite

**Your account never leaves the machine.** A botocore failure names the assumed
role — `arn:aws:sts::<account>:assumed-role/…` — and digline quotes a target's
exception into the `reason` of every verdict of that case, which lands in a
committed run file. So every AWS error is re-raised as `BedrockCallFailed` with
ARNs and account ids removed; the original stays on `__cause__`, in memory, for
a debugger.

**Cached tokens.** Converse counts cached reads **beside** `inputTokens`, not
inside them — measured against the API on 2026-08-28, not inferred from the
field names: a warm call reported `inputTokens=10`, `cacheReadInputTokens=12002`
and `totalTokens=12016`. So they are added rather than subtracted, which is the
opposite of OpenAI's convention. It is one constant in `digline_bedrock.client`,
re-measured by a live test, because getting it wrong is invisible in the
direction of good news.

**`additional_request_fields`** reaches Converse's
`additionalModelRequestFields` and changes what the model does. It is **not**
part of `config_hash` — no more than `temperature`, `model` or `max_tokens` are:
the fingerprint covers the rules that judge a run, not the system being judged.
Two runs differing only in these fields will read as "same configuration as the
reference". If you need the difference to show, keep the fields in a file and
declare it in `Suite.artifacts`, and the report carries the diff.

Apache-2.0. Docs: [digline/digline](https://github.com/digline/digline).
