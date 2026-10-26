# ADR 0054 — The names a server lets out

- Status: proposed 2026-10-26. Nothing in it is implemented. The decisions
  below were ruled by Alessandro Prandini on 2026-10-26, on #548 (where the
  ruling is a comment) and on the reading of this record's draft, and this
  record is written before the code
- Shipped: unreleased
- Date: 2026-10-26
- Opens: **nothing in the schema**, and digline-mcp's command line, as a minor:
  0.7.0. The order is ruled and is not overtaken: `OUTPUT_VERSION` 4 in the
  core for #678 first, then digline-mcp 0.7.0 with #548 and #678, then the cap
  of #719
- Assumes:
  - [ADR 0011](0011-the-mcp-server.md) §5: an MCP response goes to a third
    party;
  - [ADR 0034](0034-the-store-outside-and-the-reference-that-names-nothing.md)
    §4, the three classes, and §13, what class (b) does and does not buy;
  - [ADR 0036](0036-the-name-table-and-the-process-that-owns-it.md) §2: the
    table is reached through two callables digline is handed; §4: tokens are
    stable per (tenant, suite);
  - [ADR 0038](0038-the-projection-of-a-run-nobody-promoted.md): the served
    projection, `project_served(run, mint)`;
  - [ADR 0043](0043-a-message-digline-did-not-write.md): the message of an
    exception digline did not write does not reach the agent;
  - `load_target` and `_split` in `digline/host/loader.py`: how digline names
    Python code on a command line.
- Touches: fixed decision 9 in `CLAUDE.md`, applied to one more surface, not
  amended. digline-mcp's command line breaks, as it did when `--root` became
  required in 0.5.0.

## Context

`digline_mcp/server.py` calls neither `project` nor `project_served`. #548,
read at `v0.31.0` and `digline-mcp-v0.5.0`, lists what its responses carry in
clear: `case_id`, verdict names, group labels, the names of calibration checks,
the configuration the application reports, artifact and pinned paths, the
tenant, and the names a refusal quotes. A measurement on stdio, as a real
client, on `quickstart-toml` and `prompt-first`, counted **33 texts** that
`get_baseline` returns in clear and a projection tokenises. It was reported on
2026-10-26 and was not repeated for this record, and the commit it was taken at
is not recorded here; the acceptance repeats it (*Consequences*).

Whether those names may leave depends on whose cases are in the store, and
nothing in a store says.

## Decision

### 1. A declaration, two values, no default

digline-mcp requires, at start, a declaration of whether the store's names may
leave in clear. It has two values:
- **`clear`**: the names leave as they do today;
- **`project`**: the server projects its own responses, and the names leave as
  tokens.

There is no default. A server started without the declaration does not start,
and says it needs one.

### 2. Why *refuse* is not a value

#548 proposed *in clear* and *refuse*, under which the server would not start.
It is not a value here. Not starting the server is a state the operator already
has: they do not start it. The declaration answers one question, whether the
names may leave in clear. *Refuse* answered another, whether the server should
exist. One key holding both is a `None` that means two things. A key that
disables the server from its configuration, for a deployment whose operator
controls the configuration and not the launch, would be a key of its own, and
nobody has asked for one.

### 3. The tokens come from the name table, handed over at start

Under `project`, the server is handed the name table's two callables at start,
as the served view of ADR 0038 is handed them, and projects with
`project_served(run, mint)`. digline-mcp is that arrangement's second consumer.
ADR 0038 takes a dated note naming it. The server mints through the callable
and reads the table through nothing else (ADR 0036 §2).

### 4. *project* with no table is a configuration error, not a refusal position

`project` declared and no name table given: the server does not start, and its
message names what is missing. **That message never names anything from the
store.** It is a configuration error: the operator asked for something and was
not given the means to do it. It is not the *refuse* of §2, which was a
position. A declaration says what the operator wants; a configuration refusal
says what is missing to do it.

### 5. The break, and why it is a minor

A configuration that passes `--root` and nothing else no longer starts. By
*Choosing the version*'s enumeration, an option whose absence changes what an
existing invocation does is a command-line option *changed in meaning*: **#548
ships as a minor, digline-mcp 0.7.0.** #548's body says 0.6.0; 0.6.0 to 0.6.3
have shipped since it was written.

**The precedent is `--root`.** digline-mcp 0.5.0 made it required: a
configuration that left it out exited 2 and started nothing, and the CHANGELOG
marked it *Breaking* and said what to add to a client's configuration. That was
the minor after 0.4.6. This break has the same shape and takes the same step.
ADR 0011 §8's example takes a dated note saying what a configuration now needs.

### 6. The callables arrive as `--name-table module:attribute`

Under `project`, the server is started with `--name-table`, naming an object
that holds the two callables of ADR 0036 §2: one that returns the token for a
(kind, text), minting if there is none, and one that returns the row a token
names, or nothing. The server imports it once, at start, and learns nothing
else about the table.

**The spelling is the one digline already has for naming Python code.**
`load_target` and the suite loader split a spec with `_split`
(`digline/host/loader.py`): `"pkg.mod:name"` or `"file.py:name"`, a trailing
identifier after the last colon. `--target` is documented as *"same syntax as
--suite"*. `--name-table` takes the same syntax and goes through the same
function, so an operator who has written a `--target` has written this.

A process started from a client's JSON configuration cannot be handed a
function as a parameter, the way ADR 0036 and ADR 0038 hand one. It can be
handed a name, and this is the name.

### 7. The rule is at the boundary, and a gate fails closed

Under `project`, **every** tool's response is projected, not a list of tools:
the rule is stated once, where a response leaves the server, and not per tool.
A tool added later is under it without anybody remembering to put it there.

The guarantee takes the shape of `tests/test_projection_gate.py`, whose first
half *"walks the projected document and fails **closed**"*. A gate drives every
tool the server registers, under `project`, and walks each response. A string
at a path it does not classify is red, and named. ADR 0034 §4 gives the reason:
*"a filter has to know what it is looking for"*, and a new field would pass it.
A gate that refuses what it does not classify does not need to know.

`get_run` and `get_baseline` go through `project_served`. `compare`, `diff` and
`explain` are computed over the two runs projected, which ADR 0036 §4's tokens,
stable per (tenant, suite), make comparable. The other tools are under the same
gate, and the tool list is read from the server, not written into the test.

### 8. A refusal carries its names in fields, and they are tokenised

Under `project`, a refusal **carries the names it quotes in fields, and its
sentence is composed from those fields.** The names are the ones
`digline_mcp/errors.py` lists: *"it quotes tenants, suite names, provider ids
and — since 0.18.0 — the names of the rules that moved"*. They leave as their
tokens, through the same callable, and the sentence is composed from the
tokens. §7's gate classifies those fields as it classifies any other string.
**It does not classify the prose.**

**A refusal is never stripped of its names, because a refusal without its names
is not actionable.** A refusal that says a rule moved and does not name it
tells the person reading it that something is wrong and not where. A token
tells them where, and the person who holds the table resolves it, which is the
arrangement every other projected name already has.

**Why fields and not the sentence.** A gate that claimed to classify prose
would give a false guarantee. A sentence is not a document with paths: what in
it is a name and what is digline's own word is not written anywhere a walk can
read, and a check that guessed would pass the names it did not guess. A field
is a path, and a path is what §7's gate classifies.

**The project has already moved this way.** `DocumentRefusedError` gained
`declared_schema` (#706) and `role` (#742): what a reader of a refusal needs is
carried by a field, where it used to be said only by the message. This takes
the same step for the names.

### 9. The tenant and the suite stay in clear

Under `project`, `tenant` and `suite` leave in clear. **They are class (b)** of
ADR 0034 §4, *"the committing party's own strings — `tenant`, `suite`,
`environment`, `git_commit`"*, and the projection already leaves them in clear:
`tests/test_projection_gate.py` classifies `"$.tenant"` and `"$.suite"` as
`("b", _anything)`. **The server does not invent a regime stricter than the
projection it applies.** A response under `project` carries what a served
projection carries, and no less.

**What this does not settle.** §4 sends class (b) to §13 for *"what that does
and does not buy"*, and §13 answers the tenant *"for the shape it builds and
**not in general**"*: *"A stringless document does not give a stringless
repository: `tenant` and `suite` are directory names, and the guarantee stops
at the file boundary."* That question stays open. This record follows the
projection's classification as it stands, and if ADR 0034's answer moves, this
section moves with it.

## Not decided here

- **The refusals whose names cannot be carried in fields where they are
  raised.** Enumerated at `12bf942a` over every construction of a class in
  `REFUSALS` under `src/` and `packages/*/src`, raised where it is built or
  returned to be raised, less `digline.cli` and pytest-digline, which are not
  this server's, and over the server's own `refuse` calls. A refusal whose
  sentence is composed at its raise from values in scope can carry those values
  as fields. One that quotes another digline refusal holds that refusal's
  object, in `Quoted.cause` or in the `from` chain, and can carry its fields
  on. One that quotes an exception digline did not write already keeps that
  message from the agent (ADR 0043). One is in none of the three:
  - **`JournalRefusedError`, raised from `Pending.refusal` in
    `digline/host/measure.py`.** The sentence is composed in the store, by
    `FileResultStore`'s survey of a run's journal, and reaches the raise as a
    `str` on `Pending`, a value of the `ResultStore` protocol. It quotes the
    run key, a record kind read from the journal file, and in two places the
    text of another exception. At the raise there is only the string. Carrying
    its names in fields is a change to a protocol value, not to a raise, and
    this record does not make it.

  What the enumeration does not cover: a refusal raised by a suite or by the
  application it imports, which is ADR 0043's and never reaches the agent with
  its message, and a class added to `REFUSALS` after `12bf942a`.
- **Whether a store should carry a declaration of its own** (#548). Nothing in
  the store changes here.
- **Whether the same requirement applies to other front ends** (#548). It
  starts in digline-mcp because there the store is built before any suite is
  loaded; that is not a ruling that it stops there.

## Consequences

- `server.json` gains a required `packageArguments` entry, and the MCP registry
  a 0.7.0 publication.
- `docs/mcp.md`, `packages/digline-mcp/README.md`,
  `examples/operator/.mcp.json` and `loop.py` pass the declaration.
- The Claude Code plugin's `scripts/serve` declares `clear` in the script,
  beside a comment saying why (the project open in the editor is its user's
  own) and when that line is wrong.
- ADR 0038 and ADR 0011 §8 take dated notes (§3, §5).
- A test per value, per missing declaration, per unknown value, and for
  `project` with no table. The stdio measurement is repeated in three
  directions on `quickstart-toml` and `prompt-first`.
