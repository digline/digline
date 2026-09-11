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

## The wall, proved each cycle

*(Added 2026-09-11. From a thread on r/AI_Agents the same day — "a
wall I've never tested is a wall I'm trusting on its paperwork" —
with the positive-control half added in review.)*

An absent `promote` is a claim, and a claim nobody checks is
paperwork. So before it compares anything, the operator proves the
wall with two operations under its own credentials:

- **One that must be refused.** It calls a tool named `promote`, by
  name, on its own MCP surface, and expects the protocol's
  *unknown tool* error. Absence is verified at the wire, not read out
  of a config file. There is no disabled `promote` on the server to
  aim at: that would be the policy the absence replaces.
- **One that must succeed.** It writes its own cycle file, an
  operation it already owns. **Refusal alone proves nothing**: an
  identity with a dead token or a full disk is refused everything,
  `promote` included, and would read that as a wall standing.

The outcome is digline's own trichotomy, applied to the wall instead
of a check. **Intact** (refused, and the write succeeded) is one log
line. **Collapsed** (the negative got any answer but *unknown tool*)
opens a high-severity issue, *separation collapsed*, and whatever it
wrote under the baselines is rolled back before the comparison reads
them. On this surface the wall is the absence, so a `promote` that
answers "no" is still a collapse. **Inconclusive** (no answer, or the
write failed beside the refusal) opens a different issue: the
instrument is down. Like an errored verdict, it is not a pass. The
probe's only failure mode is a false alarm. A server that learnt to
say "unknown" in other words would read as collapsed, loudly, and
never as intact.

**It proves the wall for the identity that ran it, and no other.**
A probe run with an administrator's credentials is vacuous by
construction. Our own repository is the honest example: its `main`
ruleset lets repository admins bypass it, so a push probe run with the
maintainer's token proves only that admins can push. The operator's
credentials must be the narrow ones, and the probe is what enforces
that. Run the push probe below with an admin's token and it reports a
collapse every cycle, which is exactly what it should report.

**What makes it a wall at all.** A wall lives outside the constrained
identity's configuration surface. Measured against that identity, a
protection comes in three rungs:

- **a preference**, which the identity can bypass. Our ruleset's admin
  bypass is one;
- **a latch**, which the identity must first reconfigure to cross.
  `enforce_admins` is the classic form: the admin can still turn it
  off, but the change is an auditable event rather than a quiet push;
- **a constraint**, which the platform enforces against everyone. You
  cannot approve your own pull request, whoever you are.

So the operator's credential must exclude the surface that configures
its own wall. On GitHub that means no administration scope. An agent
that can rewrite its fence has a reminder, not a fence.

The honest note for a single-maintainer repository: measured against
the owner, nearly every repository-level wall is a preference with an
audit trail, because the owner holds the surface that configures all
of them. Only the platform's absolutes are constraints. That is what
the [security page](/product/security/)'s declared zeros already say:
a review requirement one person satisfies by approving themselves
would be theater. None of this is a defect to fix. It is what the wall
is for. It exists for the operator's narrow identity, not for the
person who holds the keys.

The probe proves the wall for the identity that ran it. This taxonomy
says which identities the wall exists for at all.

The MCP probe covers the interactive surface. The scheduled loop has a
shell, and the CLI it drives *has* `promote`. What keeps a baseline
from landing there is the token: `contents: read` cannot push. That
wall is the deployment's own to probe. It is **documented, not
exercised** in the example, because an example has no protected
remote. The pattern is to push a marked commit that touches the
baselines and expect the push to be refused:

```sh
probe=".digline/$TENANT/baselines/operator-probe"
echo "operator probe: this push must be refused" > "$probe"
git add -f "$probe" && git commit -qm "operator probe: must be refused"
if git push -q origin HEAD:main; then
  # collapsed: open the high-severity issue, then take it back
  git revert --no-edit HEAD && git push -q origin HEAD:main
fi
```

A push rather than a real `promote`: if it passes, it is a marked
commit anyone recognizes and a revert undoes, not a baseline that
looks approved.

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
   prose. *(Amended 2026-09-11: the dossier's engine has shipped as
   [`digline explain --json`](/product/explain/), and the scheduled
   loop renders layers 1 and 2 from its typed fact list.)*
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
