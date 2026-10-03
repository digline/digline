# ADR 0041 — The exit code of a failure nobody anticipated

- Status: accepted 2026-10-03. Ruled before any code, on the measurement in
  §*Context*: a fifth exit code, 70, for a failure digline did not anticipate;
  the three refusals that reached the same path moved to 64 in the same change;
  and a traceback printed beside one line that says what it is not
- Shipped: unreleased
- Date: 2026-10-03
- Opens: **a fifth exit code.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`: a
  failure of this kind produces no document, and the MCP server has no process
  to exit
- Assumes: [ADR 0008](0008-the-two-run-report.md) §2 (the exit code is the
  contract); [ADR 0011](0011-the-mcp-server.md) §4 (`exit_code` is a field
  because a tool has no process to exit), §7 (two front ends over one host);
  [ADR 0020](0020-the-reading-across-runs.md) §5 (`log` exits 0 whenever it
  read the store); [ADR 0024](0024-the-judge-as-an-instrument.md) §7.5 (the
  spread adds no path to any other code)
- Touches, in `CLAUDE.md`'s *fixed* section: nothing. **It touches the exit
  code contract**, which `AGENTS.md` §6 states to every agent and ADR 0008 §2
  makes the contract. It adds a fifth meaning, so it is a record of its own
  rather than an amendment that would stretch §2
- Number: 0041. Swept on 2026-10-03, before a line was written, across
  `origin/main` (`2906a96`), every local and remote branch and tag, the
  `docs/adr/` of every sibling worktree, and the open pull requests (none). The
  highest number taken anywhere is 0040

## Context

**An exception `main()` does not translate ends the process through Python's
default handler, which exits 1.** In digline's table 1 is `EXIT_WORSE`. So a
failure nobody anticipated tells a pipeline that the suite got worse, on every
command. That includes the three that gate (`compare`, `report`, `explain`)
and the eight that, by their own docstrings, never do. #402 was one such
failure: `digline log` on a projected baseline, `KeyError`, exit 1. #412
records the path.

`main()` translates `UsageError`, every class in `host.REFUSALS`, `ValueError`
and `FileNotFoundError` to 64. Everything else propagates.

**Measured, at `2906a96`, in three ways.**

1. **The whole test suite, with `main()` instrumented** to log every exception
   that escaped the translation: **three**, all `SystemExit` raised on purpose
   by a test suite simulating a killed run (`tests/test_journal.py`). The suite
   tests code that works. It is no measure of what a user meets.
2. **Every `raise` in `src/digline`, classified statically**: 420 sites, and
   seven types outside the translation. Three reach `main()`. Two
   `RuntimeError`s in `run/driver.py` and the `KeyError` of `report.phrase` are
   declared defects. Three `TypeError`s, in `core.assertions.dataclass_identity`
   and twice in `core.aggregate._check_expandable`, are **deliberate refusals of
   the user's suite**. `ImportError`, `JudgeAbstained` and `_MalformedLine`
   are caught before they reach a front end. A failure nobody raises on purpose
   cannot be enumerated, by definition.
3. **Scenarios a user can reach, run from the CLI in a real repository:**

| scenario | exit | what escaped |
|---|---|---|
| `compare`, baseline unreadable (mode 000) | **1** | `PermissionError` |
| `compare`, baseline path is a directory | **1** | `IsADirectoryError` |
| `compare` or `run`, the suite raises `RuntimeError` while it loads | **1** | `RuntimeError` |
| `run`, a custom assertion that is not a dataclass | **1** | `TypeError`, a deliberate refusal |
| `log`, baseline unreadable | **1** | `PermissionError` |
| the suite does not parse, or imports a module that is not installed | 64 | already translated by the loader |
| the runs directory unreadable | 64 | `DirectoryUnreadableError`, already a refusal |
| Ctrl-C during `run` | −2 (130 in a shell) | `KeyboardInterrupt`, the convention |

**What reaches the path is four classes, not one:**

- **(A)** deliberate refusals raised with the wrong type;
- **(B)** the environment: `PermissionError` and `IsADirectoryError` on a
  file, where the same thing on a directory is already 64;
- **(C)** the user's suite raising while it loads, where `SyntaxError` and
  `ImportError` are already 64;
- **(D)** failures nobody anticipated: the declared defects, and every one like
  #402.

Only (D) is digline failing. (A), (B) and (C) are refusals that slipped past
the translation. Each has a precedent that points at 64, so they are
inconsistencies, not decisions.

**And one consumer branches on the code in code.** `examples/operator/loop.py`
treats any code outside `(0, 1, 2)` as no verdict and stops. Today a failure of
class (D) reads 1 there, so **the operator carries on and hunts a regression
that does not exist.**

## 1. Which commands gate, from what they already say

Taken from the docstrings and the table, not decided here:

- **Gates**, returning `exit_code(...)`: `compare`, `report`, and `explain`
  (*"It gates like `report` and not like `diff`"*).
- **Never a gate**, exiting 0 on success: `log` (*"it exits 0 whenever it could
  read the store"*), `diff` (*"Always exits 0 on a report"*), `register`
  (*"never with the comparison's code"*), `rejudge` (*"gates nothing — the gate
  is `compare`"*), `list`, `view`, `promote`, and `run`, whose code returns
  `EXIT_OK` alone.
- `migrate` exits 0 or 64, and neither is a verdict.

## 2. A fifth code: 70, for a failure nobody anticipated

**None of the four codes is true of it.** 1 sends a person after a regression
that does not exist. 2 is a verdict about the run, *"could not be judged"*,
with `unjudged` and `scale_lost` on the headline, and this failure has no
headline. 64 says the request was wrong, which puts the failure on the user.

**Ruled: `EXIT_INTERNAL = 70`.** It is `EX_SOFTWARE` in BSD's `sysexits.h`,
*"An internal software error has been detected."*. 64 is `EX_USAGE` in the same
header. **The repository never declared 64 as a `sysexits.h` value, so pairing
the two is a choice, not a precedent.** It is chosen because a reader who knows
the header reads both correctly, and a reader who does not loses nothing.

`exit_code()` never returns it, as it never returns 64: it is not a verdict.

## 3. One code for a gate and for a reading

**A gate must fail closed.** A failure inside `compare` is a gate that measured
nothing, and exiting 0 there would pass a change nobody checked. That would be
worse than exiting 1. 70 is non-zero, so every pipeline that stops on non-zero
stops. And it is not 1 or 2, so nobody reads a verdict into it.

**A reading must not exit 0 either.** *"It exits 0 whenever it could read the
store"* presupposes the reading came out, and here it did not. So the same 70.
What differs between a gate and a reading is the consequence of a non-zero
code, not the number.

## 4. What exits 70, and what moves to 64 with it

**70 is born right only if (A), (B) and (C) leave the path first.** Without
them, a `PermissionError` on a file would read *"digline failed"* when it is
the environment. So they move in the same change, each to its precedent:

- **(A)** The three deliberate `TypeError`s become `AssertionShapeError`, a
  subclass of `TypeError`, so a library caller that catches `TypeError` still
  catches them. It is listed in `REFUSALS`.
- **(B)** `main()` translates `OSError` where it translated
  `FileNotFoundError`, which is one of its subclasses. The store's
  `DirectoryUnreadableError` is the precedent: *could not look* is a refusal.
- **(C)** The loader wraps any exception the suite raises while it loads, as it
  already wraps `SyntaxError` and `ImportError`, on the file form and on the
  dotted form. A refusal or a `ValueError` the suite raises passes through
  unwrapped, as before.
- **(D)** Everything else that is an `Exception` exits 70.

`KeyboardInterrupt` and `SystemExit` are `BaseException`s and keep their
behaviour. Ctrl-C is the convention, and a suite's `SystemExit` is #414.

## 5. A traceback, and one line beside it

A refusal prints one line, because it was written for a reader. A failure
nobody anticipated was written for nobody, and **the traceback is the most
useful report of it there is**, so it is printed. The line after it says what
it is not:

> digline: the failure above was not anticipated. It is not a verdict on the
> suite (exit 70).

*Not anticipated*, not *a defect in digline*. The exception may come from a
provider plugin or from a user's own assertion code at run time, and the line
claims only what is known.

## 6. Where the table is written, and what changes there

- `wire/contract.py`: `EXIT_INTERNAL = 70`, beside `EXIT_USAGE`, with the
  same note that `exit_code()` never returns it.
- **`AGENTS.md` §6, and both copies of the `operating-digline` skill.** They say
  *"Anything else (`64`) is the CLI refusing the request you made"*. Read
  literally, an agent would take 70 for a refusal. The sentence names both
  codes.
- The pages that state the codes.
- `examples/operator/loop.py` needs no change. Its `not in (0, 1, 2)` already
  stops on 70. That is the behaviour this record exists to produce, and a
  comment there now names it.

## Not decided here

- **A suite that calls `sys.exit(n)` while it loads** makes `n` digline's exit
  code, so `sys.exit(1)` reads as worse (#414). Some uses are deliberate, so
  it is not translated here.
- **Every `ValueError` still exits 64**, so a `ValueError` that is a failure
  inside digline still tells the user their request was wrong (#415, and
  `main()`'s own comment, friction 59). Narrowing it would turn each
  deliberate `ValueError` refusal into a 70, and how many there are has not
  been counted.
- **The MCP server.** It has no exit code. A refusal reaches the agent as a
  `ToolError`, and anything else as the SDK's unexpected error. Whether (B) and
  (C) should be translated there too, for parity with the CLI, is not ruled
  here.
- **`pytest-digline`** reports through pytest's own exit codes and is not
  touched.

## Consequences

- A script matching `1` stops treating a failure nobody anticipated as a
  regression. A script that stops on any non-zero code behaves exactly as
  before.
- A failure of class (A), (B) or (C) exits 64 with one line instead of 1 with
  a traceback.
- `AGENTS.md` §6 has five codes, not four.
