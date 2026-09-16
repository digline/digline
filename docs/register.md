# `digline register` — what a person decided about a comparison

`compare` answers the one question digline exists for and then forgets the
answer. So do `explain` and `report`, which gate on the same comparison. The
exit code reaches a pipeline, the sentence reaches a terminal, and **nothing
reaches the repository**.

A verdict is not a rejection: `compare` exiting 1 is the machine saying a check
got worse; *rejected* is a person reading that and deciding the change does not
ship. The first can be recomputed from two documents still on disk; the second
exists nowhere unless somebody writes it down.

> **The decision journal is what the operator decided. The register is what a
> person decided. The first is the machine's memory and is gitignored; the
> second is the human's memory and is committed by the human who wrote it.**

## Using it

```console
$ digline register --suite suite.py --run 2026-09-15T09-14-22-… --disposition rejected
support: recorded rejected for 2026-09-15T09-14-22-104553-00-00-331b1cfd9709f0cd against the reference 2026-09-12T09-14-22-104553-00-00-331b1cfd9709f0cd
commit .digline/northwind/register/support.jsonl — the reason belongs in that commit's message
```

It computes the comparison itself, with the same `compare()` and `headline()`
the gate uses, against the baseline in force when it runs — so the verdict an
entry records is the verdict the person was looking at, and the digline that
computed it is written beside it, because what a comparison returns for a given
pair has moved between releases.

**`--disposition` is mandatory, with no default**, like `environment` and like
`report --locale`. Three values, and a defaulted disposition is one nobody gave:

| | |
|---|---|
| `accepted` | a person read the comparison and the change ships |
| `rejected` | a person read it and it does not |
| `unsure` | a person read it and could not decide |

`unsure` is not an empty string: *I read it and could not decide* is a different
fact from *nobody read it*, and a register that could not say the first would
turn it into the second.

**`accepted` does not promote, and `promote` does not register.** They are two
gestures of one family — a person, the CLI, a file under the tenant, a commit —
and they stay two, because accepting a change and approving a new reference are
different decisions that often happen on different days.

## The reason is not a field

The entry is **counts and keys, by type**. One line of JSON per disposition:

```json
{"register_version": 1,
 "recorded_at": "2026-09-16T06:50:52.301208+00:00",
 "digline_version": "0.13.1",
 "disposition": "rejected",
 "run":      {"key": "…", "created_at": "…", "config_hash": "331b1cfd9709f0cd",
              "environment": "staging", "digline_version": "0.13.1",
              "rejudged": false},
 "baseline": {"key": "…", "config_hash": "331b1cfd9709f0cd",
              "promoted_at": "2026-09-12T16:30:11+00:00"},
 "outcome":  {"regressed": 2, "improved": 0, "unchanged": 0, "new": 0,
              "missing": 0, "errored": 0, "unjudged": 0, "suspended": 0,
              "within_noise": 0, "on_the_line": 0, "worse": true,
              "canary_moved": false, "config_changed": false,
              "artifacts_changed": false, "target_config_changed": true,
              "judge_config_changed": false, "rejudged": false},
 "exit_code": 1}
```

There is no field a case id, an assertion name, a sentence, free text or an
author could occupy — not by convention, but because the type has none. The
`outcome` block is `Headline`'s facts minus the one that is prose, and each
omission has its reason:

- **No case id**, no assertion or aggregate name. Case ids are slugged content —
  in the dogfood, the titles of the threads being judged. The register records
  *how much* moved, and the run it names says *what*.
- **No sentence.** `Headline.sentence` names the canary case that moved and the
  files that changed, so it carries exactly the identifiers the entry refused.
- **No free text.** A note field is where somebody writes *"fails on the Rossi
  account"*; **no author**, because a name is payload in a way a timestamp is
  not, and the register is committed, so the author is already in the commit.

That last point is where the *why* goes. **The reason for a rejection is the
commit message of the commit that adds the line** — written by the person who
recorded it, in the words they choose, in the history that already holds every
other human reason in the repository. What the register adds to that paragraph
is a run key to point at, which is what a paragraph in a commit message never
has.

`promoted_at` is `null` where the reference was promoted before the field
existed, and the reading says *not recorded* there. It is never filled in from
git.

## Append-only, and a second line is never an edit

    .digline/<tenant>/register/<suite>.jsonl        append-only, committed

Beside `baselines/` and committed like it, because it is a person's record; not
under `runs/` and not under `decisions/`, so the generated `.gitignore` tracks
it without a rule of its own. The tenant is the directory, as everywhere.

**A changed mind is a second line, never an edit.** Recording `accepted` over a
run already recorded `rejected` appends; both stand, and the newest disposition
for a (run, reference) pair is the current one. The history of having changed
one's mind is part of what the register is for. Nothing ever rewrites a
committed line — the bytes of a committed record must not depend on who last ran
a command — and a line this digline cannot read is refused by name and left on
disk rather than migrated. `REGISTER_VERSION` is 1, beside and independent of
`SCHEMA_VERSION`, because the register is a **format** and not a document.

**A torn tail is forgiven; a hole is not.** A last line that does not parse is
the write an interruption left: it is not read, and the reading says so. A line
that does not parse anywhere else is a corrupt register, refused by name — and
`register` refuses to append after one, because a new entry past a hole would
bury it. Restore that line from git in a commit of its own, then record again.

**The commit is yours.** `digline register` writes a tracked file and leaves the
tree dirty until somebody commits it, exactly as `promote` does with
`baselines/`. Two branches that each append meet at the end of the file, the one
place a line-based merge always conflicts, so `ensure_layout` writes a
`.digline/.gitattributes` beside the `.gitignore` — created only when absent,
never overwritten:

```
# Generated by digline. The register is append-only, so two branches that
# each added a line keep both when they merge.
*/register/*.jsonl merge=union
```

Git's union driver keeps both sides' lines. The reader orders entries by
`recorded_at` and never relies on file order, and it drops a line byte-identical
to one already read — which is what a union merge of two branches carrying the
same line produces.

## No agent runs it

**`register` is a writer, and it is absent from the MCP surface by
construction**, for the reason `promote` is: it writes into the repository, and
a disposition is by definition not the agent's to give. The server keeps
[eight tools](mcp.md), none of which writes, and this is not one of them.

Absence is not the whole of the rule, because the scheduled
[operator loop](https://github.com/digline/digline/tree/main/examples/operator)
drives the *CLI*, where the verb exists. What keeps it out is the shape of the
act: a register line is worthless until committed, and the operator does not
push. No script and no workflow under `examples/operator/` invokes
`digline register`, asserted the way `digline promote` already is. An agent
assembles the evidence and recommends; the human records the disposition and
writes the reason in the commit message.

## Exit codes, and the two refusals

It **exits 0 when it wrote**, like `promote`, and never with the comparison's
code: the gate is `compare`'s, and a recording command that failed a pipeline
would be a second gate on one fact. Everything it will not do exits `64`.

**No baseline.** There is no verdict to have decided about:

```console
$ digline register --suite suite.py --run latest --disposition accepted
digline: suite 'support' has no baseline for tenant 'northwind' yet. Run it, look at the result, then 'digline promote --run <key>'.
```

**A key that does not resolve**, or a tenant that is not the suite's — the
refusals every command that names a run already has. `--run latest` resolves
here as everywhere else.

**An unjudged run may be recorded.** A person rejecting a run that could not be
judged is a real act with a real reason, and refusing to write it down would
make exit 2 the one verdict the register cannot hold.

## Reading it back

[`digline log`](log.md) ends with the dispositions, grouped under the reference
each was judged against, in `recorded_at` order:

```console
$ digline log --suite suite.py
Dispositions recorded
  Against reference 2026-09-12T09-14-22-104553-00-00-331b1cfd9709f0cd:
    2026-09-16T06:50:52.301208+00:00 · rejected: 2026-09-15T09-14-22-104553-00-00-331b1cfd9709f0cd, exit 1 — 2 worse, 0 better, 0 not judged
    2026-09-16T06:51:09.241817+00:00 · accepted: 2026-09-13T09-14-22-104553-00-00-331b1cfd9709f0cd, exit 0 — 0 worse, 0 better, 0 not judged
```

Where two consecutive entries name different reference keys, the reading may say
the reference changed between them, because both entries declare it; where
nothing was recorded it says nothing. The register never replaces `promoted_at`
and never infers a signature: what it knows that the reference does not is
**every recorded disposition and the verdict it was taken against**, and what it
cannot say is a verdict nobody recorded. Being committed, it is on every clone
even where no run is — the runs are gitignored, the dispositions travel.

## See also

- [`digline log`](log.md) — the reading this register is the last section of
- [`adr/0021-the-register.md`](adr/0021-the-register.md) — the record
- [`adr/0014-what-may-ride-a-schema-bump.md`](adr/0014-what-may-ride-a-schema-bump.md) — a ledger is a decision with its own reason to exist
