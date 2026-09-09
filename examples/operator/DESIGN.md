# The operator loop

digline answers one question: *did the system get worse than what
somebody approved?* This page is about who asks that question when
nobody is looking.

An **operator** is an agent that runs the checks on a schedule,
absorbs the measurement's own noise, and wakes a human only for drift
that deserves a decision. Everything on this page is either shipped —
and linked — or explicitly marked as a hypothesis being designed with
pilots. There is no third category.

## Two questions, two sources

The loop watches one thing — the measurement — fed by two sources.
They are equal in the design and staggered in implementation.

**The committed suite, re-run on a schedule**, answers: *is the system
I approved still that system?* This is digline's thesis pointed at
production: the same suite that gates your CI, run against the real
endpoint with the real model under the real keys ([`HttpTarget`](/product/api/)
exists for exactly this), compared against the baseline somebody
signed. Synthetic monitoring, in the oldest sense: known probes, on a
cadence, against the live system. **Every brick of this runs today.**

**Production traffic, turned into cases**, answers a different
question: *is the world still the one I approved for?* A suite covers
what you knew to ask. Your users ask things its author never foresaw —
and drift hides best exactly there. Turning traffic into cases means
capture, correlation, redaction at birth, and a harvest that
*proposes* candidates the way an agent proposes anything in digline:
a human approves them, or they are nothing. **This source is
designed, not shipped.** The landing format already exists — a
harvested case is a [TOML suite](/product/declarative/) plus a
`cases.json`, diffable and reviewable like any other — but the
harvest itself is being designed with people who have real traffic.
Bring your history; the last section says how.

## What the operator decides alone, and what it escalates

The operator automates the judgment [`AGENTS.md`](https://github.com/digline/digline/blob/main/AGENTS.md)
writes down — and nothing beyond it.

**Alone**, it may re-run a suspicious run, classify a draw from a
drift, and use [`diff`](/product/diff/) between candidates. Two
constraints make that safe. The stopping rule is **declared in
configuration before anything runs** — "at most two re-runs" is a
parameter, never the model's mood in the moment: with a stochastic
judge, enough re-runs always produce a green one, and a stopping rule
chosen after the fact measures your patience rather than the system.
And every action carries a **declared cost**: `acknowledge_calls`
is already the contract on the [MCP surface](/product/mcp/), and the
loop inherits it — the operator cannot spend without stating what it
is spending, and the stopping rule is what bounds the total.

**Escalated**: drift that repeats beyond the measured floor; several
cases flipping together, which is investigated and never retried,
because retrying destroys the evidence either way; system errors — a
judge that returned no text, a target that stopped answering; and
anything that needs a signature. A baseline to re-approve always
needs one. `promote` does not exist on the operator's surface — not
refused, absent — so that last rule is not a policy a future release
could relax. It is a fact about what the operator can reach.

**Out of scope, by declared boundary: the remedy.** The operator
watches the measurement; it does not repair the system. Fixing a
prompt belongs to your engineer or your coding agent — and the alert
is the handover between the two.

## Where it lives, and what travels

**In your perimeter, with your keys.** A container beside your
application — the [official image](/product/docker/) with a different
entrypoint — a scheduler you already have, and the operator's model
called with your credentials. It is the same trust model as the
judge: the reasoning about a report happens where the report is born.

The alert is a document in three layers, and the model writes only
the third:

1. **The fact.** Machine truth from the wire: the `compare` or `diff`
   JSON, the exit code, the run keys. Versioned, reproducible, not
   prose.
2. **The dossier.** Deterministic: what the operator did and saw.
   Re-ran twice, per the declared stopping rule; the intervals the
   samples spanned; which cases flipped; which configuration values
   differed.
3. **The judgment.** The only layer a model writes: draw, drift, or
   structural — with its reasoning in the open, and **marked as the
   operator's opinion, never as digline's verdict.** The instrument
   measures; the operator opines; the document keeps them apart.

Delivery is deliberately boring: a webhook, an email, an issue opened
in your own repository. An alert is a document, not a platform. There
is no inbox to host, and no state of ours to keep.

## Why the loop is not a service

The first question this design gets asked is whether we could run it
for you. No — and the reason is yours, not ours.

The reports the loop reasons about carry verdict reasons,
configurations, case names: fragments of your system and of your end
clients' data. Hosted by us, your compliance perimeter would suddenly
include us — our servers, our keys, our subprocessor agreement, our
audit. digline exists so that none of that is needed. What leaves
your perimeter is the redacted alert that your own suite's
[`Disclosure`](/product/api/) declared could travel — and nothing
else.

(The one hosted thing this project may ever grow is a fleet console
that receives *only* those already-travel-safe alerts and verdicts,
for teams maintaining AI features across many end clients. That is a
different page, for a later day.)

The README has said it since before this page existed: **if digline
ever grows paid features, they will run inside your perimeter too.**

## Run it today

[`examples/operator/`](https://github.com/digline/digline/tree/main/examples/operator)
is the reference assembly: a suite, an operator configuration —
cadence, stopping rule, budget, in a file rather than a vibe — an
operator prompt written against this document, an `.mcp.json` for the
interactive path, and a scheduled workflow whose escalation opens an
issue in your own repository. The deterministic layers run without
any key; the judgment layer is an explicit opt-in, the same
convention every example in the repository follows. Fork it, point it
at your endpoint, change the cadence.

## Designed with pilots

The second source — traffic into cases — is being designed with
people who run LLM systems in production. What a capture looks like.
How a request correlates to a run boundary. What makes one sample a
candidate golden and another one noise. How redaction happens at
birth, so the payload never leaves the perimeter even toward your own
repository. These are questions your history answers better than our
whiteboard.

If that is you, [open an issue](https://github.com/digline/digline/issues)
— that is the fastest way to move this.
