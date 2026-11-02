# ADR 0057 — The replay reads the trajectory the live run read

- Status: accepted 2026-11-02, by Alessandro Prandini, the text first. Its
  decision was ruled on 2026-11-02, before this record was written, and is
  stated here as ruled. What is pending is its code, which `Shipped:` below
  will name when it lands
- Shipped: unreleased
- Date: 2026-11-02
- Opens: **schema 23 when its code lands, and nothing before.** This record
  writes no `SCHEMA_VERSION`, no line of `_STEPS` and no code. The code that
  implements it moves `SCHEMA_VERSION` from 22 to 23 with a `WritesNothing()`
  step; 23 is the next number at `4dd1c277`, and another branch may take it
  first
- Answers: [ADR 0018](0018-the-recorded-trajectory-and-the-agent-under-test.md),
  which promises three times that a replay judges a trajectory as the live run
  judged it, and the two `xfail(strict=True)` cases in
  `tests/test_recorded_output.py` that show where it does not
- Assumes: [ADR 0014](0014-what-may-ride-a-schema-bump.md) §1 (what may ride a
  bump) and §2 (absent is how *not recorded* is written);
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §1 and §3
  (what a re-judge needs rides the record, whole or nothing);
  [ADR 0025](0025-the-tokens-and-the-bill.md) §1 and §8 (`usage`, the field
  this one is modelled on)
- Touches: nothing in `CLAUDE.md`'s *fixed* section. `RecordedResponse` never
  crosses a boundary (ADR 0015 §4), so a field added to it widens nothing that
  travels
- Number: 0057. Swept on 2026-11-02 before a line was written, across
  `origin/main` (`4dd1c277`), every branch on the remote, every worktree of
  this repository and the two open pull requests. The highest number taken
  anywhere is 0056

**Lines cited here are at `4dd1c277`.** The behaviour was measured on
2026-11-02 at `83be8a52`; the code it describes is the same at both.

## Context

**A trajectory has three forms, and they are not the same thing.**

1. **What an assertion reads while the run is live**: `metadata["response"]`,
   the target's own report. `ToolsCalled` reads `tools` and `finish` from it
   (`core/assertions.py:1260` and `:1296`), and `ToolCalledWith` reads
   `tool_calls` (`:1430`). It is never persisted.
2. **What the document keeps**: `RecordedResponse.tool_calls` and nothing
   else. `record_trajectory` (`core/run.py:829-886`) reads
   `metadata["tool_calls"]` alone, canonicalises each call's arguments, and
   answers `None` where the key is absent.
3. **What a replay rebuilds**: `_reported_trajectory`
   (`run/replay.py:83-132`) writes `tools` from the names of the recorded
   calls, `tool_calls` from the calls, and never `finish`.

**Two fields an assertion reads are not in the document.**

- **`finish`.** `ToolsCalled` returns `error` where the reply ended on
  `tool_use` and named no tool: the provider contradicted itself
  (`core/assertions.py:1296-1306`). The replay never sees `finish`, so it
  judges the same reply as *the model called nothing*, which against a
  declared trajectory is `fail`. The shipped plugin reaches this case:
  `digline-anthropic` maps `stop_reason` `tool_use` to `finish="tool_use"`
  (`client.py:59` at the `digline-anthropic-v0.7.0` tag). It was measured on
  2026-11-02 at `83be8a52` through that plugin, with an injected client and no
  network. **`error` live, `fail` replayed.**
- **`tools` when it arrives without `tool_calls`, or disagrees with them.** A
  function target can report `Response(metadata={"tools": [...]})`, the form
  `ToolsCalled`'s own refusal suggests (`:1276`). It can also report two lists
  that name different calls: `Completion` and `HttpTarget` refuse the
  disagreement, and a function target is not held to it. Live, `ToolsCalled`
  judges `tools`. Replayed, it judges names rebuilt from `tool_calls`, which
  are a different trajectory, or which are absent, in which case the replay
  refuses the whole case (`run/replay.py:215-227`).

**ADR 0018 promises the identity three times, and the code breaks it.**

- `:370-371`: *"so a replayed `ToolsCalled` judges what the live one judged."*
- `:491-492`: *"`tools` is rebuilt from the recorded names so that
  `ToolsCalled` re-judges identically."*
- `:795-797`: *"…then re-judged, produces the same scores case for case."*

The two divergent cases are held in `tests/test_recorded_output.py` as
`xfail(strict=True)`, `tools-finish-tool-use-no-calls` and
`tools-and-calls-disagree`, since the merge `96efcb83`. Each one's reason names
the defect and says when it passes.

## Decision

### 1. `finish` and `tools` are recorded

They become fields of `RecordedResponse`, beside `tool_calls`. They are written
**when the target reports them**, under `Suite.record_responses`, and they gain
no switch of their own. The model is `usage` (ADR 0025 §1 and §8): a per-call
fact that rides the recorded answer it belongs to, under the switch that
already governs the answer, because a second flag is a second thing to forget.

`finish_raw`, `resolved_model` and `fingerprint` are not part of this. No
assertion reads `finish_raw`, and the other two are recorded for the run in
`target_config` (ADR 0005 §9).

### 2. Absent is *not recorded*

A response whose target reported no `finish`, or no `tools`, writes no key. The
absence says *not recorded*, as the 18→19 step writes it for
`modules_unchecked`, and never a default: an empty `tools` would say the model
called nothing, which nobody measured.

### 3. The replay rebuilds from the document

`_reported_trajectory` hands back the `finish` and the `tools` the document
holds, where it holds them. It stops deriving `tools` from the names of
`tool_calls`.

### 4. Schema 23, with a step that writes nothing

A document written before 23 recorded neither field, and the absent key is how
that is written. So the step is `WritesNothing()`, by ADR 0014 §2, and it
invents no value for a run already stored.

## Consequences

**No stored document changes its verdict.** In a document before 23 the two
keys are absent, and absent means not recorded, so a replay of that document
behaves as it does today. Only new runs change.

**The replay's refusal narrows.** Today a suite holding `ToolsCalled` or
`ToolCalledWith` is refused a replay of any case whose target reported no
`tool_calls` (`run/replay.py:215-227`). With `tools` recorded, `ToolsCalled`
can be re-judged where `tools` was reported and `tool_calls` was not.
`ToolCalledWith` reads the arguments, which only `tool_calls` carries, so for it
the refusal stays.

**`docs/api.md:851-853` describes the document as it was.** It says *"What is
not asserted on is not recorded"*, and names `finish` and `tools` among what is
not persisted. With this record's code it stops being true of either, and the
page moves with the code.

## How it will be known to be repaired

The two `xfail(strict=True)` markers in `tests/test_recorded_output.py` turn
into passes, and `strict=True` makes each one fail until its marker comes off.
Whoever repairs the code is made to remove the note.

## Alternatives considered

**Record only what an assertion reads.** That is, record `finish` only where the
suite holds `ToolsCalled`. Rejected, for three reasons:

- ADR 0018 already rejected *asserted on, therefore recorded* as a criterion
  (`:72-80`);
- **no field of the run document works that way.** What a response records
  depends on the target and on `record_responses`, never on the assertions:
  `tool_calls` and `usage` are written whenever the target reports them
  (`run/driver.py:599-633`). The one place that looks at which trajectory
  assertions a suite holds is the replay's refusal (`run/replay.py:160-164`),
  which reads and does not write;
- it would make the document's content depend on the suite instead of the
  target. Then two runs of the same target, under two suites, would record
  different facts about the same reply.

**Record `finish_raw` too.** It is the other key `Completion` writes into
`Response.metadata` that the document does not carry, and it stays out by
choice. No assertion reads it, so recording it would give the replay nothing to
judge again. The fidelity the replay needs is `finish`'s, the field
`ToolsCalled` reads, and that is the one §1 records.

## Not decided here

- Who performs the schema ritual, and in which release. The repair is meant
  for 1.1, with its schema; this record comes first.
- The text of `docs/api.md:851-853` once the code lands.
