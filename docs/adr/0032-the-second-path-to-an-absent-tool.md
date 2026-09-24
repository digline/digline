# ADR 0032 — The second path to an absent tool

- Status: accepted — the text first, then the implementation written against
  it, the way
  [ADR 0014](0014-what-may-ride-a-schema-bump.md),
  [ADR 0027](0027-the-run-reconciles.md),
  [ADR 0028](0028-the-rules-that-moved.md) and
  [ADR 0029](0029-the-artifact-that-must-not-drift.md) were
- Date: 2026-09-24
- Opens: **nothing.** No schema moves, no document grows a field, no wire key
  is added or removed. `SCHEMA_VERSION`, `OUTPUT_VERSION`, `REGISTER_VERSION`
  and `JOURNAL_VERSION` all stay where they are. What moves is one default in
  the CLI and one sentence in four shipped descriptions
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §1 (the
  baseline is a reviewed artifact and the tenant is the perimeter);
  [ADR 0011](0011-the-mcp-server.md) §*the shape of the API is the argument*
  (there is no policy here, there is no promote) and its Consequences — the
  sentence this record falsifies and amends;
  [ADR 0022](0022-the-declared-price.md) §5 (a promotion checks the declared
  price digest, which is why `view` carries `pricing` at all);
  [ADR 0031](0031-the-reference-promote-replaces.md), merged as #108 while
  this record was being written — §6 below is the one place the two touch
- Touches: `CLAUDE.md`'s *fixed* section only through decision 2 — the baseline
  lives in `.digline/<tenant>/` and is versioned in git, so what may write
  there is a perimeter question and not a convenience question. No fixed
  decision is amended
- Turns into surface: `docs/view.md` — the section *The one route that writes*,
  whose title stops being true by default; `README.md` and
  `plugins/digline/.claude-plugin/plugin.json` and
  `.claude-plugin/marketplace.json`, whose promise acquires the clause it
  always needed; [`AGENTS.md`](../../AGENTS.md) §1 and both copies of
  `operating-digline`'s `SKILL.md` §1, where the rule stops naming a command
  and starts naming the act; and — for §4a — `SKILL.md` §8 plus
  `digline-mcp`'s `descriptions.py`, which stop disagreeing about `migrate` and
  both carry the condition the permission rests on
- Credit: **kantorcodes1**, who found it while writing a digline profile for
  HOL Guard — by classifying what each command *does* rather than by using it.
  That is the reading nobody here performs, and §7 is about why

## Context

digline ships a guarantee, in the places a machine reads and the places a
person does — `plugin.json`, `marketplace.json`, the MCP server's own
`instructions` and tool descriptions, its `pyproject.toml`, `README.md`,
`docs/mcp.md`, `examples/operator/README.md`, the `pytest-digline` plugin, and
[ADR 0011](0011-the-mcp-server.md). The shortest form of it is in
`plugins/digline/.claude-plugin/plugin.json`:

> an MCP server that measures, reads and explains, and **cannot promote a
> baseline, because approval is a person's commit**

The reason is not a preference about tidiness. It is
[ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §1 made operational:
a baseline is an *approved reference*, it is committed under
`.digline/<tenant>/baselines/`, and the approval is the whole of its meaning.
`operating-digline` §1 says what follows for an agent — *an agent that promotes
on its own dissolves the word; the file still says `baseline`, and nobody
decided anything.*

[ADR 0011](0011-the-mcp-server.md) built the surface to match, and argued the
shape rather than asserting it:

> A `promote` tool that raised "not permitted for agents" would be a better
> error message and a worse design: it teaches that promotion is something this
> surface does, subject to a policy, and a policy is exactly the kind of thing a
> future release relaxes "just for CI". There is no policy here. There is no
> promote.

The absence is even proved rather than trusted: `examples/operator/loop.py`
calls `promote` by name on the MCP surface every cycle and expects *unknown
tool*, beside one write that must succeed, because refusal alone proves
nothing.

**And `digline view` serves `POST /promote`.**

It is not a loophole in the sense of something overlooked in the small. It is
the documented design of that command — `view --help` says *"browse stored
runs, compare any two, promote"*, `docs/view.md` has a section called *The one
route that writes*, and `view.py`'s own module docstring lists it as the second
of three deliberate properties. Every part of it was decided. What was never
decided is what it means next to the sentence above.

### What was measured

Read from the code, this looks like it needs a browser and a click. It does
not. `_allowed_origin` (`src/digline/cli/view.py`) returns `True` when there
is no `Origin` header at all, and says why: *"no `Origin` at all is allowed —
that is a curl or an old browser, neither of which is the attack"*. Against a
cross-site POST from a page the developer has open, that reasoning is right.
Against a caller with a shell, it is the whole door.

Measured, not read off the source. Two runs in a store, the first one
promoted; then `digline view` started on an ephemeral port, and one POST with
**no `Origin` header and no credential of any kind**:

    RESULT POST /promote (no Origin) -> 200; promoted_at moved: True;
    baseline now equals run(s): ['2026-09-24T13-43-18-776131-…'];
    POSTed=2026-09-24T13-43-18-776131-…; first=2026-09-24T13-43-18-538378-…

The baseline moved from the first run to the second. No `digline promote` ran.
No MCP tool was called — none exists to call. The plugin hook
(`plugins/digline/scripts/ask_a_person.py`) never fired, because it reads the
first word after `digline` and that word was `view`.

First measured on `6528af7`, and **re-measured on `69af0b7`** — this record's
branch after `main` was merged into it, carrying #108 (ADR 0031) and #114 (the
refusal classification), both of which changed `view.py`. `_allowed_origin`
grew a signature and a real `Host` check in between; its first line is still
`if not origin: return True`, and the result above is the second run, not the
first. A green describes one tree, so this one was re-run against the tree that
carries it.

### Why this is a contradiction and not a gap in the documentation

The tempting repair is to write it down: say in `docs/view.md` that the view
promotes, cross-reference it from the plugin description, and the reader is
informed. That repair does not work here, and the reason is worth stating
because it is the general case.

Documenting a perimeter closes the gap where **somebody does not know**. This
gap is not that. It is a *declared guarantee with an undeclared exception* —
and the declaration is consumed by readers who cannot act on a correction
elsewhere. `plugin.json`'s description is loaded into an agent's context at
install time as a statement of what is possible. An agent that has read
*cannot promote a baseline* and then finds a `POST /promote` has not caught the
project in an inconsistency it should resolve toward the prose; it has been
told something false about the world it is acting in. The honest forms are two:
either the sentence acquires *"except from `digline view`"* everywhere it
appears, or the exception goes. §1 rules which.

### The shape underneath, which is the part that generalises

Three surfaces defend this decision, and **all three key on a name**:

| surface | what it matches | file |
|---|---|---|
| MCP | tool named `promote` — absent | `packages/digline-mcp/src/digline_mcp/server.py:385` |
| plugin hook | first word after `digline` is `promote` or `register` | `plugins/digline/scripts/ask_a_person.py` |
| the skill | *"Never run `digline promote` on your own initiative"* | `operating-digline/SKILL.md:23` |

`digline view` is the **act without the name**. Each of the three is correct
about what it matches, and the act they exist to govern reaches the store
through a fourth word. Nobody was careless — a guarantee written three times
against a command name is a guarantee about vocabulary, and the store does not
read vocabulary.

Two further facts make this worse than an omission, and both were found by the
sweep in §4 rather than by looking at `view`:

- **The skill does not merely fail to mention `view`; it points the agent at
  it.** `operating-digline` §1 says *"Never run `digline promote` on your own
  initiative."* Two sections later, §2 says *"`digline view` is the table you
  pick from … Take the run whose per-case profile is closest to typical."*
  That advice is good advice, and the surface it recommends is the one route
  that promotes without any of the three defences noticing. The skill's own
  `USE WHEN` clause names `digline view` as a trigger, so it knows the command
  exists; its rule is still written about `digline promote`.
- **The hook's silence on `view` is a tested invariant, not an oversight.**
  `tests/test_claude_plugin.py` lists `"digline view --suite s.py"` in the set
  asserted silent by `test_the_hook_stays_silent_on_everything_else`, beside
  `grep -rn promote src/` and `echo digline promote`. The reasoning behind that
  test is sound — asking about everything trains people to approve without
  reading — and it was written when `view` belonged in that company. §1 is what
  makes it belong there again; §3 is what keeps the test honest about the one
  spelling that no longer does.

## Decision

### 1. `digline view` does not promote. A flag enables it

`digline view` refuses promotion **by default**. `digline view
--allow-promote` is the server that promotes. Both are supported; the default
is the refusing one.

The reason is not consistency with the MCP, and it matters that it is not:
consistency is an argument about surfaces matching each other, which a future
release can trade away for a good-enough reason. The reason is **the same
reason the MCP has no promote**, applied to the same facts. ADR 0002 §1 and
`operating-digline` §1 do not say *the MCP must not promote*; they say the
approval is a person's, and that it is a person's is the meaning of the word
`baseline`. A rule about **who decides** is not satisfied by a surface that
lets a non-person decide — whatever that surface is called, and however
thoroughly its own behaviour is documented.

**Why the default and not an opt-in `--read-only`**, which is the shape this
would take if it were about tidiness. An opt-in guarantee is a guarantee
**nobody has**. The sentence in `plugin.json` is unconditional and is read
before any flag is typed; a `--read-only` that must be remembered makes it true
for the careful and false for everyone else, which is the state we are already
in with extra steps.

The decisive test is who pays for each mistake, because the two are not the
same size:

- Forgetting `--allow-promote`: a person opens the page, finds no button,
  reads the line naming the flag, restarts the server. Cost: one restart.
- Forgetting `--read-only`: an unreviewed baseline is written and committed,
  and the record of what was approved now contains something nobody approved.
  Cost: exactly the thing the perimeter exists to prevent, and it is **silent**
  — a promotion that happened looks like a promotion that was meant.

A default belongs on the cheap side of an asymmetry that large.

**And the asymmetry that makes the flag safe rather than a fig leaf.** The
person who wants to promote from a browser is standing at the terminal that
typed `digline view`; they can type eight more characters, and the refusal
tells them which eight. The agent will not — not because it is forbidden, but
because it has read a description saying this surface does not promote, and an
agent does not go looking for a flag to enable a capability it has been told is
absent. That asymmetry is the whole design: **the flag is reachable by
intention and unreachable by inertia.**

### 2. The refusal is an absence, in both of the two places a caller looks

Two different callers read this server and they do not read the same thing, so
"absent" has to be true twice.

**On the page, for a person: the button is not rendered.** Not rendered and
disabled, not rendered and failing on click. ADR 0011's argument against a
`promote` tool that raises *not permitted* is the same argument here and
transfers without amendment: a control that is present and refuses teaches its
reader that promotion is something this surface does, subject to a policy —
and it teaches it every time the page is read, to every reader, including the
one deciding what to try next.

This is already the house pattern. `_actions` (`src/digline/report/pages.py`)
omits the button in three cases today — the baseline's own row, a stale
configuration, a run with errored verdicts — and puts a chip naming the refusal
that would have come. Read-only joins that chain.

**But it joins it differently, and the difference is the ruling.** Those three
are facts about *a run*: this run cannot be promoted. Read-only is a fact about
*the server*: nothing here can be. So its marker does not go in the row. A chip
repeated down twenty rows would be both noise and a lie about its own subject —
it would read as twenty per-run refusals rather than one property of what the
person started. The marker belongs once, in the header, next to the suite name,
and it names the flag: this is the only line in the product that has to teach
`--allow-promote` to somebody who did not know it existed.

**On the wire, for a program: `/promote` is not a route.** This is the half
that carries the guarantee, and the half that absenting the button does not
provide: a caller with a shell never renders the page. In the default server a
POST to `/promote` gets the **404** that any other unknown path gets — *no such
action* — because that is the true statement. Not a 403, and not a 405: both
of those say *you may not*, which implies a someone who may, which is the
policy ADR 0011 refused to create. There is no policy here. On this server
there is no promote.

A note on the mechanism, because the obvious one is a trap. `_ROUTES`
(`src/digline/cli/view.py:47`) looks like the place to make this change and is
**dead code**: grepped across the tree, it has zero readers, and it is also
wrong — `do_GET` dispatches on a chain of literal comparisons and serves
`/case/` and `/suspend/`, neither of which `_ROUTES` lists, under a comment
calling it *"everything this server answers"*. Implementing §2 by editing it
would produce a change that reads correctly in review and does nothing. Either
it becomes the real dispatch table or it goes; it must not stay as a tuple that
describes the server incorrectly while the server ignores it.

**And the two must be computed from one fact, not implemented twice.** A page
that decides independently of the dispatcher is a page that will eventually
show a button the route rejects, or hide one it would have accepted. The flag
reaches `pages` as an argument, the same way `locale` and `has_baseline` do;
one value, read in both places.

### 3. The hook does not watch `digline view`. It watches `view --allow-promote`

The plugin hook keeps its hands off bare `digline view`, and the reason is
stronger than the cost of noise. Once §1 holds, `digline view` **is** a reading
tool — there is nothing to ask a person about, and a prompt would be asking
about the wrong act. It would also be expensive in the only currency a hook
has: a hook that interrupts reading is a hook people learn to dismiss without
reading, and it spends that credibility on a prompt that has no decision behind
it, leaving less of it for the `promote` and `register` prompts that do.

**The sharper half is the flag, and it inverts the intuition.** `digline view
--allow-promote` is not a smaller thing than `digline promote` — it is a
larger one. `digline promote` is one decision about one named run; the flag is
that decision delegated in advance, for every run in the store, for as long as
the server is up. It is exactly the decision `REASONS["promote"]` describes,
taken once and made ambient. So the hook watches it.

This costs something honest, and the cost should be recorded rather than
discovered later. `subcommand()` deliberately steps *over* leading flags to
find the subcommand and then stops reading; watching `--allow-promote` means
the hook reads a word that is not the subcommand, which is a change to its
matching model. It is **not** a change to its principle: the hook's docstring
says *"what is matched is the command, never a string"*, and `--allow-promote`
is a word of the parsed simple command, produced by the same `shlex` split
that produces `promote`. `grep -r "digline view --allow-promote" notes/` is
still a grep. The principle holds; only the reach changes, and the change is
from *the first word* to *the first word and, for one subcommand, its flags*.

The hook remains what it says it is: **a preference, not a wall.** It is not
the guarantee, and §1 does not lean on it. The guarantee is the default; the
hook is what makes the deliberate case deliberate.

### 4. The sweep: `view`/`promote` is not the only one

All twelve subcommands were classified — `run`, `rejudge`, `compare`, `diff`,
`list`, `migrate`, `promote`, `register`, `view`, `explain`, `log`, `report`
(`src/digline/cli/main.py:974-1159`). The question asked of each was the one
that found this defect: *what does it write, and does any surface that claims
to withhold that write reach it anyway?*

The boundary that matters is which files are committed. The generated
`.gitignore` covers `*/runs/` only (`src/digline/store/file_store.py:88-92`),
so **`baselines/` and `register/` are the committed surface** — the diff a
reviewer signs — and a write there is the act this project governs.

**`register` is the template, and it is worth naming because it shows the four
parts fitting together.** No MCP tool; the absence is *stated to the model* in
the playbook — *"There is no tool that records one"*
(`descriptions.py`); `view`'s `/suspend/` route produces the line and
applies nothing (`docs/view.md`); and the hook watches the command.
`promote` has every one of those parts except that one of its own surfaces
reaches around them.

**The second instance is `migrate`, and it is worse in one specific way.**
`cmd_migrate` appends `store.baseline_path(...)` to the list it rewrites
(`src/digline/cli/main.py:745-748`), so `digline migrate` rewrites the
committed baseline file. The hook does not watch it. And the two shipped texts
do not merely fail to cover it — **they contradict each other in plain
words**:

| surface | what it tells the agent |
|---|---|
| MCP playbook | *"propose `digline migrate` — **do not run it**"* (`descriptions.py`) |
| shipped skill §8 | *"**Run `digline migrate`** after the bump."* (`operating-digline/SKILL.md`) |

An agent with both loaded has been given an instruction and its negation about
a command that rewrites a committed file.

**The skill is right and the MCP playbook is wrong.** But the answer is not the
part worth writing down, because the answer can flip. The reason is:

> `promote` changes **what the reference says**. `migrate` changes **how it is
> spelled.**

That difference is not a matter of degree. A promotion selects — it names one
run out of several as the approved one, and nothing but a person's judgement
determines which. A migration has no selection in it: every step is required to
write nothing semantic, so there is exactly one output for any input, and the
transformation is empty of content by construction. **A mechanical
transformation whose emptiness is testable is not a decision**, and it does not
become one by touching a committed file. The wall is the same either way — the
reviewed diff — and it is the wall that catches a migration that misbehaved,
which is precisely what a reviewer can check on a migration and cannot check on
a promotion.

The emptiness is not a hope. `_add_schema_sixteen` is literally `return raw`,
with a docstring explaining that inventing there *"would be worse than usual,
because the field is a control"*; `_STEPS`' own comment says a version absent
from the table *"is one whose bump was not additive, and the absence is the
whole statement"*; and
[ADR 0014](0014-what-may-ride-a-schema-bump.md) §2 requires additive migration
without invention. This week's bump showed exactly one changed line per
baseline, which is the observable form of all of it.

#### 4a. So the rule is the condition, not the permission

> **An agent may run `digline migrate` for as long as every step is required to
> write nothing semantic. The day a step has to change content, `migrate`
> becomes a decision, and this answer flips.**

Written that way, the rule carries its own expiry. The permission is a
consequence of a property, so a future release that breaks the property
withdraws the permission without anybody having to remember that it once
depended on one. `operating-digline` §8 and the MCP playbook both say the
condition, not just the verdict — the MCP's line stops being *"do not run it"*
and becomes the same sentence the skill carries.

**And the condition needs teeth it does not fully have.**
`test_the_step_moves_no_hash_and_no_timestamp` upgrades a schema-9 fixture
through the whole chain, so it covers every step — including steps not yet
written — and it checks that `config_hash` and `created_at` survive untouched.
That is real, and it is two fields. There is no standing test that a *new* step
writes nothing semantic in general; today the ritual and a human reading a
one-line diff are what check it. A condition whose failure is caught by a
person noticing is a condition that expires silently, which is the failure mode
§4b exists to prevent. The test that the semantic content of a document is
unchanged across `upgrade_document` is owed by whichever release first ships a
step that is not `return raw` or an added absence.

**A third finding, on a different axis, and deliberately not ruled here.**
`digline view` renders `render_html` directly (`src/digline/report/pages.py`),
which emits `verdict.reason` and artifact text for any run not marked
redacted. `digline report` has `--redacted` for precisely that document
(`main.py:1157`); `view` has no counterpart — its parser takes `--host`,
`--port`, `--target` and nothing else (`main.py:1101-1108`). On loopback this
is not a defect but the design: the view serves world 1, and
[ADR 0002](0002-three-worlds-and-where-the-data-lives.md) says the developer
sees everything. The finding is narrower and sharper than "the view leaks":
**`--host` is the control that moves the view out of world 1, and it is
unconstrained and uncontrolled.** `serve()` binds whatever it is given, and the
docstring says loopback *"is not a default anyone should change lightly"* —
which is a request, not a mechanism. One flag moves a world-1 surface into a
world where the payload/verdict boundary applies, and nothing notices. That is
decision 9 territory and needs its own record; it is filed and not decided
here, because folding a disclosure ruling into a promotion ruling is how one of
them ends up unargued.

**Everything else is clean on this question.** `compare`, `diff`, `list`,
`explain` and `log` write nothing, and the `wire` layer's omission of `reason`
holds across all of them. `run` and `rejudge` write only under gitignored
`runs/`, so the hook's silence about them is consistent with its stated scope
rather than a hole in it.

#### 4b. The standing test

A sweep is a fact about today. The rule that survives it:

> **Every write to a committed path under `.digline/` is reachable from a
> known, enumerated set of surfaces, and a new one fails the test.**

The test is not "does `view` promote". It is that the set of code paths reaching
`promote_baseline` and `append_register` is written down, and that a path not on
the list is a failure. That is what catches the **next** `view` — the one nobody
has thought of — and it is the same construction friction 59 chose for the
refusal types, for the same reason: a list without a test that fails is a
fourth place to forget.

**That construction now exists and should be copied rather than reinvented.**
`src/digline/host/refusals.py` sorts every exception digline defines into
refusals and everything else, and `tests/test_refusals.py` *"walks every module
under `digline` and fails on any exception class that is in neither table"* —
which, in its own words, is what turns *a type somebody added* into *a type
somebody classified*. The test here is the same sentence with the nouns
changed: walk every call site reaching `promote_baseline` and `append_register`,
and fail on one that is not classified. Both records answer the same question
— what happens to the thing nobody remembered to add — and neither answers it
with a list.

#### 4c. Three hook evasions, found by the sweep and confirmed by running it

Not part of the perimeter — the hook is a preference, not a wall, and §1 does
not lean on it — but they are defects in what it claims to match, and two are
outside the evasions its own docstring accepts (`bash -c`, `eval`, `ssh`,
aliases, variables). Measured by piping a payload into the script, not read:

| spelling | hook fires? |
|---|---|
| `digline promote --run x` | yes |
| `uvx digline promote --run x` | yes |
| `python -m digline.cli promote --run x` | yes |
| **`uv tool run digline promote --run x`** | **no** |
| **`python -m digline.cli.main promote --run x`** | **no** |

`uv tool run` is the long form of `uvx`, which the matcher handles; it checks
`words[1:2] == ["run"]` and `uv tool run` fails that. And
`python -m digline.cli.main` is a working entry point — verified, `digline
0.19.0`, exit 0 — that `MODULES = {"digline", "digline.cli"}` does not list.
In the same line, `"digline"` is **dead**: there is no `src/digline/__main__.py`
and `python -m digline` refuses with *"cannot be directly executed"*. The set
lists a spelling that cannot run and omits one that can.

**These do not ride this record's code.** The hook is a plugin file and this
ADR is core; the two live on different release trains, and folding a
`plugins/` fix into a change to `src/digline/cli/view.py` would couple them for
no reason but that one sweep found both. They ship as their own small piece
with the plugin's next release, the dead `"digline"` entry going with them.

**And that piece should say what it confirms**, because it is not a separate
lesson: **the hook keys on a name, and a name can be spelled differently.**
That is this record's finding one level down. §*The shape underneath* is about
three surfaces keying on the *word* `promote` while the act reaches the store
through the word `view`; this is the same surface keying on the word `digline`
while the same command arrives spelled `uv tool run` or `digline.cli.main`. The
first was found by classifying, the second by **running it** — and both were
invisible to reading the code, which is the only thing either of them has in
common with how they were missed.

### 5. What the shipped sentences say now

The clause every description needed is not *"except from `digline view`"* —
§1 removes the exception rather than documenting it. But two sentences were
saying more than they had checked, and they are corrected rather than left to
become true by luck:

- **ADR 0011's Consequences** — *"A coding agent can read a digline result
  correctly and cannot promote a baseline, **because there is nothing to
  call**"* — is the sentence this record falsifies. Its subject is the agent,
  not the server, and its reason was a claim about the whole reachable surface
  that had only been checked against one package. It is amended in place, with
  a pointer here: the claim stands, and now stands for the stated reason.
- **`operating-digline` §1 and `AGENTS.md` §1** stop naming a command. *"Never
  run `digline promote` on your own initiative"* becomes a rule about the act —
  never move a baseline on your own initiative, by any route — with the command
  as its example rather than its definition. This is the correction with the
  longest reach, because it is the one that would have caught the next instance
  without anybody finding it first.

`plugin.json`, `marketplace.json`, `README.md` and `docs/mcp.md` are left
alone. They say the *MCP server* cannot promote; that was true, is true, and
was never the sentence at fault.

### 6. Where this meets ADR 0031

[ADR 0031](0031-the-reference-promote-replaces.md) and friction 59 fixed
`do_POST`'s refusal tuple — the hand-listed exception types that let
`SuiteMismatchError` and `DocumentRefusedError` through as a dropped
connection. **All of it landed while this record was being written**, which is
the ordering this section asked for: 0031 first, because it fixed a defect in a
published release, and this record only changes a default.

*Corrected 2026-09-24, when the code was written against this text.* Until
then this paragraph named **#108 and #114** as the pull requests that fixed the
refusal tuple. Neither did. #108 was ADR 0031's `--replacing`, #114 was the
refusal **classification** — `host/refusals.py` and the walk that keeps it
honest — and the tuple in `view.py` was still six hand-written names after both
had merged. **#117** replaced it with `REFUSALS` (commit `927a16e`, *"Catch the
classification in every front end"*), in the same change that made
`_after_promotion` say *"Baseline set to …"* even when the run list cannot be
drawn. The error is the one this whole record is about, one level down: a claim
read off two branch names instead of resolved against the tree. Both facts are
inherited by the code here rather than rebuilt, and neither may regress.

That work is **not** made redundant by what §1 decides, and the reason is worth
keeping. §1 removes the route from the *default* server; it does not remove it
from `--allow-promote`, which is precisely the server a person promoting from a
browser is using — and a promotion that silently succeeds while appearing to
fail is at its worst for exactly that person. The classification in
`host/refusals.py` is what keeps the flagged server correct, and §4b is the
same construction pointed at call sites instead of exception types.

### 7. The reading that found it

This was not found by using digline. It was found by **classifying** it —
writing down, for an external tool, what each command does to the world. That
reading asks one question this project's own reviews do not: *is this command a
read or a write?* Every surface here was reviewed by someone asking whether it
was correct, and `POST /promote` is correct; it does what its documentation
says, with an `Origin` check, through the same call as the CLI, with the same
refusals. Correct and contradictory are independent properties, and only the
second one is visible from a table of what-writes-what.

The generalisation, which is the reusable part: **a guarantee stated about one
surface is a claim about every surface**, and nothing in a per-surface review
ever puts two of them side by side. The test in §4 is the standing form of that
question, and §7 is why it is a test rather than a note asking people to
remember.

## Consequences

- `digline view` changes behaviour for existing users: the button a person
  clicked yesterday is gone until they pass `--allow-promote`. This is a
  deliberate break in a minor release, announced in `CHANGELOG.md` under its
  own heading rather than in a list of fixes, and the refusing server names the
  flag in two places — the startup line and the header chip — so the discovery
  path does not run through the documentation.
- `view --help` stops saying *"browse stored runs, compare any two, promote"*.
- The guarantee becomes **provable on the surface that is shipped to agents**,
  the way `examples/operator/loop.py` already proves the MCP's. That probe
  proved the narrow thing correctly and the sentence beside it stated the broad
  thing; §4's test is what closes the distance between them.
- What this does **not** do, so nobody assumes more: it does not authenticate
  the view, and it does not make `--allow-promote` safe against a cross-site
  POST beyond the `Origin` check that is there. A person who passes the flag
  has the server that existed before this record, with its existing
  protections. The default stops being that server; the flagged one is not
  hardened by this change.
- It does not touch the store. `promote_baseline` is unchanged, its refusals
  are unchanged, and a `.digline/` written before this release reads
  identically after it.
- Corrections ride this change because they are in the files it opens, and each
  is a statement that is wrong rather than a preference: `_ROUTES` (dead, and
  describes the server incorrectly — §2, and it goes rather than becoming the
  dispatch table); and the hook's `MODULES`, which lists a spelling that cannot
  run and omits one that can (§4b).

  *Corrected 2026-09-24.* This list also planned a `docs/view.md` fix — its
  *"the same three refusals (tenant, configuration, errored verdicts)"* against
  a `promote_baseline` that raises four types and a `view.py` that catches six.
  **#117 already made it**: that sentence now reads *"with the same
  refusals"*, and there was nothing left here to correct. Written before #117
  merged and not re-read against the tree afterwards — the same mistake as §6's,
  in the same record, which is why the code was built from the tree.
- **`migrate` is ruled in §4 and §4a**, and what lands is the condition rather
  than the permission: the MCP playbook's *"do not run it"* is replaced by the
  same sentence `operating-digline` §8 carries, and both state what the
  permission rests on. The owed test is named in §4a and is not written here.
- **`--host` is filed and deliberately not decided here** (§4). It is decision
  9 territory and gets its own record; settling a disclosure boundary as a side
  effect of a promotion ruling is how one of the two ends up unargued.
- **The hook evasions do not ride this change** (§4c). They are a `plugins/`
  fix on the plugin's release train, carrying the sentence about what they
  confirm.
