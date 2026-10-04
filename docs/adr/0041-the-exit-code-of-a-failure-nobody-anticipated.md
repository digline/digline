# ADR 0041 — The exit code of a failure nobody anticipated

- Status: accepted 2026-10-03. Ruled before any code, on the measurement in
  §*Context*: a fifth exit code, 70, for a failure digline did not anticipate;
  the three refusals that reached the same path moved to 64 in the same change;
  a traceback printed beside one line that says what it is not; and, ruled
  after the first text when the MCP test pinning 27bc37e turned red, the rule
  in §4.1 by which a suite's failure while it loads is refused with its
  location
- Shipped: unreleased
- Date: 2026-10-03
- Amended: 2026-10-04, before 0.28.0 was cut, in §4.1's rule 1, in a new §4.2,
  in *Not decided here* and in *Consequences*. A bare `ValueError` no longer
  passes through as a refusal. A refusal written in words is `RefusedError`, a
  subclass, and a bare `ValueError` that reaches a front end exits 70 (#415).
  No other section changes, and the five codes do not move
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
- **(C)** A suite that raises while it loads is refused with the location of
  what raised, by the rule in §4.1, on the file form and on the dotted form.
- **(D)** Everything else that is an `Exception` exits 70.

`KeyboardInterrupt` and `SystemExit` are `BaseException`s and keep their
behaviour. Ctrl-C is the convention, and a suite's `SystemExit` is #414.

### 4.1 (C), and the commit it reverses

**It reverses
[27bc37e](https://github.com/digline/digline/commit/27bc37e), of 2026-09-30.**
That commit wrapped a suite's `ImportError` in a refusal and left every other
exception from a suite unexpected, *"Only an import is wrapped"*. An MCP test
pinned it on ADR 0011 §10: *"dressing it as a tool result would hide a bug
behind a sentence"*. **That concern stands, and this record meets it with the
location instead of the traceback.** What hid the failure was a sentence with
no location in it, not the code 64. And what changed is that after this record
*unexpected* means exit 70, *"digline failed"*. 27bc37e did not have to
consider that. Said about the user's own code, 70 would be the very defect
this record repairs, pointed the other way.

**The rule, by who raised the exception**, read from the traceback's innermost
frame and checked in this order:

1. **A refusal, a `ValueError` or an `OSError` passes through as before**,
   whatever the frame, and exits 64 with digline's own sentence. That covers
   every misuse digline already refuses in words. **It keeps a known defect, on
   purpose:** a `ValueError` raised by a failure inside digline still reads as
   *"your request was wrong"*. The recon behind this record found it, and it is
   recorded as #415 and in *Not decided here*. It is held to its existing
   behaviour here, not forgotten.

   *__Amended 2026-10-04.__ The rule now reads "a refusal or an `OSError`". A
   bare `ValueError` is no longer in it, and falls under rule 2 or rule 3 by
   its frame like any other exception. A `ValueError` the suite raises itself
   is therefore refused with its location, and still exits 64: the sentence
   changes, not the verdict. The rule is kept as written above, because it was
   the ruling of 2026-10-03, and §4.2 is the repair.*
2. **Any other exception whose innermost frame is in the `digline` package is
   not wrapped.** It reaches the front end as a failure nobody anticipated,
   and the CLI exits 70. If a suite's misuse makes digline raise something it
   wrote no sentence for, the missing sentence is digline's defect.
3. **Anything else is a refusal, 64**: the suite, the application it imports,
   a third-party library, a provider plugin. The sentence carries the type, the
   message, the innermost frame's `file:line`, the suite's own `file:line`
   where that is another frame, and the command that prints the full
   traceback. For a file that is `cd DIR && python -c 'import runpy;
   runpy.run_path("suite.py")'`, which puts the directory on `sys.path` as the
   loader does and runs no `__main__` block. For a dotted name it is
   `python -c 'import pkg.module'`. The text is the same on every front end and
   passes through `visible`, because an exception's message is not digline's
   to vouch for.

**The measurement that makes rule 2 safe.** Calling a digline API with the
wrong arguments raises at the call site, so the innermost frame is the suite's
and the mistake falls under rule 3. Measured with a wrong keyword to a digline
dataclass (`Case(idd=...)`) and to a digline function: both innermost frames
were the suite's. Without that, *classify by who raised it* would have blamed
digline for a user's typo, and the most frequent mistake would have exited 70.

**The consequence for provider plugins, stated so it is seen rather than
found.** *The `digline` package* is the directory of `digline.__file__`. A
provider plugin is a separate package, so a plugin's failure while a suite
loads falls under rule 3. It exits 64, with a location that points into the
plugin's own files, such as `digline_anthropic/...`, and that path is what
says whose it is.

**Held by tests on both front ends.** The MCP test that pinned 27bc37e is
rewritten to the new rule and keeps its control. It asserts that the type, the
message and the line reach the agent, because a sentence without them would
be the hiding §10 refused. A second test holds rule 2: a failure raised inside
digline while a suite loads still reaches the agent as an unexpected error.

### 4.2 A bare `ValueError` (amended 2026-10-04, #415)

**Rule 1 kept a known defect, and this repairs it.** Until now a `ValueError`
digline raised by mistake read *"your request was wrong"*. It is the defect
this record repaired one level further in.

**Measured at `2e67e42`, in four ways.**

1. **The whole test suite, with `main()` instrumented** to log each exception
   its 64 branch caught (`pytest -m "not live" -n 4`, 4152 tests): 67, and one
   bare `ValueError`. That one was raised by a test's own suite while it
   loaded. The rest were classes already in `REFUSALS`, or `OSError`s.
2. **Every `raise` in `src/digline`, by AST**: 282 sites raise from the
   `ValueError` family. 47 raise one of the 17 typed refusals that subclass it.
   **235 raise the bare builtin, and every one of them carries a sentence
   written for a reader**. None declares a defect.
3. **Scenarios run from the CLI in a real repository.** `Contains(needle="")`,
   `Length()` with no bound, an `HttpTarget` whose URL names no host, and an
   endpoint that does not answer at preflight: each exits 64 on a bare
   `ValueError`. A baseline, a run file or a suite that is not UTF-8 exits 64 on
   an **implicit** `UnicodeDecodeError`. It is right by accident.
4. **Implicit sources**: 84 calls to `int`, `float`, `json.loads`, `decode`
   and `read_text`, 64 of them unguarded in their own function. They cannot be
   enumerated, for the reason §*Context* gives.

**The frame cannot tell them apart.** A deliberate refusal and a bug both
start inside digline. `Contains(needle="")` has its innermost frame at
`core/assertions.py:312`. An `int("x")` written by mistake in a digline
function has its innermost frame in that function, because `int` has no
Python frame. A `json.loads` written by mistake has its innermost frame in the
standard library, which would classify it as *not digline's*, the wrong way
round. The frame says *who* raised. Only the type can say *on purpose*. §4.1's
frame rule stays where it is, separating the suite's code from digline's.

**Ruled: a class, not a rule.** `RefusedError(ValueError)` is defined in the
core and listed in `REFUSALS`. It follows the move §4 made for (A),
`AssertionShapeError` under `TypeError`, so a caller catching `ValueError`
still catches it. `main()`, `digline view`'s request handler and the loader's
pass-through list drop the bare `ValueError` and keep `OSError`. One handler in
`view` goes the other way: the page after a promotion now catches every
exception, because that page exists to say a promotion happened whatever the
list of runs under it does (friction 59), and a bug in the list must not
close the connection on a baseline that has already moved.

**Which sites become `RefusedError`: decided by the road the error takes to a
front end, not by who builds the object.** There are four roads, each measured
from the CLI:

| road | measured with | ends |
|---|---|---|
| the user, at run time | a check's `_graded(1.5, …)`; a target's `Usage(input_tokens=-1)`; a judge's `JudgeReply(score=2.0)` | an errored verdict or case, exit 0. The driver and the assertion catch it, and `main()` never sees it |
| the user, while the suite loads | `Contains(needle="")`, `Score(name="x", score=1.5)` at module level | the front end |
| a document | a baseline whose score is out of range | the boundaries in `run_from_dict`, `projection` and `resolution`, which convert to a typed refusal |
| digline's own computation | none observed | the front end: the bug this separates |

So, of the 235:

- **86 become `RefusedError`.** These are the sites whose error reaches a front
  end along the user's road:
  - the shipped checks' declarations and `Suite`, `Case` and `Calibration`;
  - a target's and a judge's construction and preflight;
  - `HttpTarget`'s load-time checks and `expected_config`;
  - `free()`, `split_coordinate` and a provider's registration;
  - `Repeated`, `PiiPattern`, `as_ratio` and `as_agreement`;
  - the locale, `diff` across suites, `--judge-samples` below two;
  - a trajectory a target reported in a shape that cannot be recorded, which
    the driver records outside its catch.
- **84 stay bare** because the same `raise` serves digline's own computation:
  - `Score`, `Verdict`, `Usage`, `JudgeReply` and `ClaimReply` (25);
  - the `Run` family, `CalibrationBand` included (50);
  - four guards only digline reaches from a front end: `combine_samples`,
    `fold_judgements`, `record_output` and `Usage.__add__`, whose two operands
    each already satisfy the bound their sum is checked against (4);
  - `Completion`, `ToolCall` and `SuiteRuns` (4).

  From a front end their error arrives along digline's road, or along the
  document's, which the boundaries already convert.
- **41 stay bare because they are raised inside a run-time catch**: a reply
  parsed by a judge, an endpoint's answer read by `HttpTarget`, a template
  rendered during a call. The exit code never sees them. Their **type name is
  written into the errored verdict's `reason`**, and that reason is committed
  in the baseline.
- **21 stay bare in the document readers behind `run_from_dict`**, which
  converts them.
- **4 stay bare in `execute`**: the pin-set invariant, a non-replay under
  `judge_samples`, and the two `done` checks. A front end cannot reach them
  except through its own wiring mistake. The journal is refused earlier, by
  ADR 0017 §6.

`CalibrationBand.bounds` is one of the 86 and not of the 50. `Calibration`
calls it at declaration, so its error reaches a front end along the user's
road. Left bare, a band declared at 0 would have moved from 64 to 70.

**The number was corrected before it was ruled.** The first count of the sites
in the second bullet was *about six*. It was taken from the messages, and a
message does not say who calls the code. Counted again over the callers, by
AST, it is 84.

**Two alternatives were refused.**

- ***`RefusedError` on the value types as well.*** It would make a bug in
  digline's computation read as the user's request once more, on the types
  where such a bug is most likely. And it changes a versioned document: an
  errored verdict's reason would read *"assertion raised RefusedError: …"* in
  every baseline that carries one, which puts the name of an internal class
  into the committed format. The same reason keeps the 41 run-time sites bare.
- ***A frame rule for the loader***, by which an exception raised in a
  `__post_init__` entered directly from the suite's frame is the suite's. It
  would repair the module-level case below, at the cost of a second frame rule
  and an amendment to rule 2.

**The `UnicodeDecodeError`, at its five sites.** A file that is not UTF-8 is
the user's, so it is refused at the read where it happens. Those reads are a
Python suite read by the loader, a cases file read by the TOML loader, a run
and a baseline read by the store, and a declared artifact. The TOML suite file
and the register already refused it, and `migrate` lists it among the
documents it refused. It is not refused in `main()` beside `OSError`: a
general rule there would also catch a decode error inside digline itself,
which is the confusion this removes.

**What it gives the MCP server, which is where it matters most.** The server
translates `REFUSALS` and nothing else (`digline_mcp/errors.py`). Every bare `ValueError`
refusal therefore reached an agent as the SDK's *unexpected error*, with the
sentence on stderr, where no client reads it. The loader's comment on its
pass-through list said *"the front ends translate each of these already"*, and
for `ValueError` that was false on the MCP. After this amendment the 86 reach
an agent as their sentence, and the comment is true.

**What it leaves, stated where it is.**

- **A bug in a document reader still exits 64.** The three boundaries keep
  converting a bare `ValueError` into a typed refusal, because a document
  whose score is out of range is the document's fault. A reader that fails by
  mistake is converted the same way. This is the cost `run_from_dict`'s
  docstring already states, and it is not repaired here.
- **A value type built at module level while the suite loads exits 70.** It is
  measured with `Score(name="x", score=1.5)`: its innermost frame is digline's,
  so it falls under rule 2. No example, test or page builds one there.
- **A caller that tests `type(exc) is ValueError`** no longer matches the 86.
  `except ValueError` still does. The three such tests inside digline are the
  boundaries above, and they keep their meaning.
- **A library caller's own misuse of the 8 bare guards** (`combine_samples`,
  `execute`, …) still raises a `ValueError`, as before. Only what a front end
  does with it changes.

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
  *Decided 2026-10-04, in §4.2: they were counted, 86 of them became
  `RefusedError`, and a bare `ValueError` exits 70.*
- **(B) on the MCP server.** It has no exit code. A refusal reaches the agent
  as a `ToolError`, and anything else as the SDK's unexpected error. (A) and (C)
  reach it as refusals, because `AssertionShapeError` is in `REFUSALS` and (C)
  is done in the loader both front ends share. (B) is done in the CLI's
  `main()`, so on the MCP an unreadable file is still an unexpected error.
  Whether it should be translated there too is not ruled here.
- **`pytest-digline`** reports through pytest's own exit codes and is not
  touched.

## Consequences

- A script matching `1` stops treating a failure nobody anticipated as a
  regression. A script that stops on any non-zero code behaves exactly as
  before.
- A failure of class (A), (B) or (C) exits 64 with one line instead of 1 with
  a traceback. For (C), that line carries the location and the command that
  prints the traceback.
- `AGENTS.md` §6 has five codes, not four.
- *Amended 2026-10-04 (§4.2).* A refusal digline writes in words is a
  `RefusedError`, and on the MCP server it reaches an agent as its sentence
  instead of an unexpected error. A bare `ValueError` that reaches a front end
  exits 70. On the command line the refusal's line names `RefusedError` where
  it named `ValueError`, and the exit code stays 64.
