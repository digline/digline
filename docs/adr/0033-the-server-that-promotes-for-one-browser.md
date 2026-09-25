# ADR 0033 — The server that promotes, for one browser

- Status: accepted — ruled on 2026-09-25, the design first and the code
  written against it on `view-launch-token`
- Shipped: unreleased
- Blocks: **the 0.21.0 tag**, until Alessandro has clicked the printed address
  in a real browser and pressed *Make baseline* — §8. Ruled 2026-09-25
- Date: 2026-09-25
- Amends: [ADR 0032](0032-the-second-path-to-an-absent-tool.md), in its
  Consequences only — the bullet saying the record *"does not authenticate the
  view"*. That bullet was true of 0032 and is amended in place with a pointer
  here. No decision in 0032 §1–§8 moves: the default still refuses, the flag
  still enables, and the hook still watches the flag
- Opens: **nothing.** No schema, no document field, no wire key.
  `SCHEMA_VERSION`, `OUTPUT_VERSION`, `REGISTER_VERSION` and `JOURNAL_VERSION`
  stay where they are. What moves is how the flagged `digline view` answers a
  POST, and the address its startup line prints
- Assumes: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §1 (the
  approval is a person's); [ADR 0011](0011-the-mcp-server.md) §*the shape of
  the API is the argument*; [ADR 0032](0032-the-second-path-to-an-absent-tool.md)
  §1 (the flag), §2 (the absence, and the 404) and §8 (a guard that keys on a
  name)
- Touches: nothing in `CLAUDE.md`'s *fixed* section. It is deliberately
  scoped to world 1, and §6 says why — one of the three reasons is that the
  world-2 version of the question reaches decision 2
- Turns into surface: `digline view --allow-promote`'s startup line (the
  address carries the key) and its `--help`; `POST /promote` on the flagged
  server (a new 403); `docs/view.md`; `CHANGELOG.md`
- Credit: **piekwerk**, on the Reddit thread under the four-ways post, who
  argued that a flag lives in the agent's environment and a token does not
- Number: 0033. Swept on 2026-09-25 across every ref and every sibling
  worktree; 0032 was the highest claimed

## Context

ADR 0032 made `digline view` refuse promotion unless it was started with
`--allow-promote`, and made the plugin's hook ask a person before any command
carrying that flag. The flag answers one question: **may this server write?**
It cannot answer the second one: **who is asking?**

And the flagged server did not ask. `_allowed_origin` admits a request with no
`Origin` header on purpose — *"that is a curl or an old browser, neither of
which is the attack"* — and nothing else stood behind it. So once a person had
started `digline view --allow-promote` in their own terminal, any process of
that user could move the baseline with one POST. That includes an agent's
shell. The hook never fired, because nobody typed the flag in the agent's
shell. The person did, in theirs.

### What was measured

The same script against both trees, and not read off the source. It uses
a store with two runs, the first promoted. `digline view --allow-promote` is
started on an ephemeral port, and one POST is sent with **no `Origin` header
and no cookie**:

    == origin/main cfcf47b
    startup: digline view on http://127.0.0.1:49319/ — promotion enabled — ctrl-c to stop
    POST /promote, no Origin, no cookie -> 200; baseline moved: True
    == this record's branch
    startup: digline view on http://127.0.0.1:49322/?launch=<key> — promotion enabled, from the browser that opens this address — ctrl-c to stop
    POST /promote, no Origin, no cookie -> 403; baseline moved: False

### The argument that decided it

It came from a reader, and it is the sharper form of 0032 §8. **A flag lives in
the agent's environment. A key does not.** The flag is a word on a command
line, and a command line is something an agent composes. The hook can ask about
a word before it runs, and that is all it can do. The hook is a preference, not
a wall (0032 §3), and one `curl` against a server somebody *else* started never
passes through it at all. A check that the caller holds something only the
person's browser was given does not depend on what the agent read, typed or
was told. It makes the act impossible, where the hook only makes it
deliberate. That is the difference between the two kinds of guard this project
has been naming all month: the wall stands outside the surface the caller
configures.

## Decision

### 1. The key has no home

`digline view --allow-promote` mints a **launch key** when it starts:
`secrets.token_urlsafe(32)`, 256 bits, held in the server's memory. It is never
written to disk, never read from the environment, and no option or parameter
supplies it — `serve()` has none.

The absence of a home is the design, not a simplification of it. Every home
that was considered is readable by the caller the key exists to refuse:

- **A file the person types from.** The agent runs as the same operating-system
  user, and reads files as that user. Only the agent's own sandbox could stop
  it, and that is exactly the surface the caller configures.
- **An environment variable the server reads at start.** Claude Code inherits
  the environment of the shell that launched it, so a variable in the person's
  profile is in the agent's shell too.
- **An option, `--token`.** Then it is a word on a command line again, which is
  where this started, and §4 refuses it for a second reason.

Minted per start and held in memory, the key has nowhere to be read from. It is
shown exactly once: in the process's output, on the startup line, as the query
of the address the person opens. Where that output goes is decided by whoever
started the process. Usually that is a person's terminal, which the agent does
not read. When an agent started the server, the output is the agent's pipe,
and the plugin's hook has asked a person before that could happen (0032 §3).

### 2. How it reaches a browser, and the one thing it must never reach

The printed address is `http://HOST:PORT/?launch=KEY`. A `GET` carrying the
right key is answered with a **303** to the same page without it, and sets the
key as a cookie: `HttpOnly`, `SameSite=Strict`, `Path=/`. `POST /promote`
compares the cookie with the key, using `hmac.compare_digest` so a comparison
that stops early does not reveal how much was right, and refuses without it.
Other query parameters survive the redirect, so `?locale=it` stays.

**The cookie's name carries the port** — `digline-view-7373`. A browser keeps
cookies by host and not by port, so two views on one machine, one per suite,
would otherwise overwrite each other's key. The first person would then find
their server refusing them the moment the second one started.

**The key never appears in anything the server renders.** Not in a page, a
form, a hidden field, a link or a `Location` header. This is the half that is
easy to lose in a later change, so it has its own test that walks every route.
The reading routes answer anybody with a shell, and must: they are how a
person and an agent both read a result. So a key written into a page would be
handed to exactly the caller it exists to refuse, by the server itself, on
request.

**The `Origin` check stays, and runs first.** It stops a *page* the developer
has open, and the key stops a *process*. Leaving no `Origin` allowed, for
`curl`, was safe only as long as something else refused `curl` on the route that
writes. Before this record nothing did. Now the key does, and `_allowed_origin`'s
docstring says so.

### 3. On this server the refusal is a 403, and on the default server it is still a 404

ADR 0032 §2 made a POST to `/promote` on the default server a **404**, the same
answer as any unknown path, and refused a 403 in so many words: a 403 says *you
may not*, which implies a someone who may. That is a policy, and on the default
server there is none. Nobody may promote there, so the route is absent.

On the flagged server somebody may — the person who started it and opened the
address it printed. So a caller without the key is **refused**, not told there
is nothing here: **403**, with a sentence that says what to do. A 404 here would
be the false statement, because the route plainly exists.

**The same fact, two servers, two truthful answers.** It is 0032 §2's reasoning,
not an exception to it: that record asked which statement is true, and the
answer depends on which server is being asked.

An address carrying a key from an **earlier start**, such as a tab left open
across a restart, is refused with a 403 as well. The sentence names what
happened, and no cookie is set. On the default server the parameter is ignored:
there is nothing to hand over, and the header already says what that server is.

### 4. The key is not a second control

There is no `--token`, no way to turn the key off, and nothing to configure.
The person operates **one** control, the flag. The key is how the flag's
decision stays with the person who made it. It is not a second decision beside
the first.

This holds by construction as well as by documentation. `ViewHandler` takes a
`launch_key` and derives `allow_promote` from it; it has no `allow_promote` to
set. A server that promotes without a key cannot be constructed, and `serve()`
has no parameter through which a key could be supplied.

**Why it matters enough to be a decision.** Two controls for one act are how one
of them stops being read, and that is this month's whole family. 0032 §8
records four guards that each named the act by one spelling while the act
arrived by another. A configurable key would be the same failure one level up:
a guard beside a guard, where whoever turns one off for a reason — "just for
CI", "just for the demo" — has removed the only one that was a wall, and nothing
anywhere says so. A key that cannot be configured cannot be configured away.

### 5. What it does not do

Said so the record is not over-read.

- **It is not a wall against an adversarial process of the same user.** The
  key sits in the server's memory and in the browser's cookie store. A process
  determined to reach either, by reading a browser profile or attaching to a
  process where the platform allows it, is attacking the operating system's
  user boundary, and no key held under that user survives that. What the key
  closes is the caller acting on *inference*, the one ADR 0032 §1 argues
  from: an agent that reads a result, concludes a baseline should move, and
  finds one POST enough. It is now not enough.
- **A server an agent starts itself is the agent's.** If the agent launches
  `view --allow-promote` through a spelling the hook does not read (0032 §8
  concedes `bash -c`, `eval`, aliases and variables), it holds both the server
  and the key, exactly as it could run `digline promote` itself under the same
  spellings. The key protects a person's server from the agent. It was never
  going to protect the agent's own.
- **A redirected startup line writes the key.** `digline view --allow-promote >
  log` puts the key in `log`. That is the launcher choosing a home for it, and
  it lasts only as long as that start does.
- **Any server on `localhost` receives the cookie.** Cookies are scoped by
  host, not by port, so a browser sends `digline-view-7373` to every port on
  the same host. Exploiting it needs another local server *and* the person
  visiting it. That is a same-user process again, the first bullet, not a
  new door.

### 6. World 2 stays out

The question came with a second one: if the store could live outside the
repository, in a client's perimeter, `view` would run where the data is and the
agent would not be on that machine at all. That does not make this record
unnecessary there. It makes it insufficient there, for three reasons, and each
belongs to a different record:

- **The network becomes the caller.** Off loopback, "no `Origin` is allowed"
  admits anything that can reach the port. A per-start key still serves one
  operator. Several operators need a person's *identity*: revocable, and
  perhaps recorded on the promotion. That is authentication, and it belongs to
  the `--host` record that 0032 §4 filed under decision 9.
- **The reviewed diff moves.** 0032 §4 treats the committed `baselines/` diff
  as the wall a promotion ends at. If the store sits in a client's perimeter,
  the baseline is not in the developer's reviewed diff, and where a world-2
  promotion is reviewed has to be answered before who may make one.
- **A store outside the repository reaches fixed decision 2**, which puts
  everything in `.digline/<tenant>/` inside the user's repository. That needs
  its own ADR first. A reconnaissance of it was under way in another session
  when this was ruled, and this record builds nothing that presumes its answer.

### 7. How it is held

- The measurement in §*What was measured* is a test:
  `test_a_shell_without_the_key_cannot_promote_on_a_flagged_server` reads the
  store on both sides of a keyless POST and a forged one, then of the same POST
  with the cookie, which is the control that proves the server can promote at
  all.
- §3 is `test_the_refusal_on_the_flagged_server_is_a_403_not_the_404`, beside
  the unchanged default-server tests that still require the 404 and the
  unknown-path sentence.
- §2's rule is `test_no_page_the_flagged_server_renders_contains_the_key`.
- **Every existing promotion test now sends the cookie**, and that is not
  bookkeeping. Without it the key refuses first, and the origin test, the
  rebinding tests and the walk over every refusal type would all have gone on
  passing with the guard they name deleted: *a test does not fail when it stops
  testing*, which is the lesson 0032's code already paid for once. Each file
  says so where it sends the cookie.
- Three mutations were run against the finished code, and each was caught:
  the key check removed (2 failures), the origin check removed (2, including
  the rebinding control), and the key rendered into every page (1).

### 8. A person uses it in a browser before the tag, and the tag waits

Everything in §7 is verified header by header: the 303, the cookie's
attributes, the POST that carries it. **Nobody has done the thing every user
will do first**: click the address the startup line prints and press *Make
baseline*. A browser's own handling of a `SameSite=Strict` cookie set by a
redirect, on a page opened from a terminal, is exactly the kind of fact an HTTP
test assumes rather than observes. A control proven at the HTTP level and never
seen working in a browser is a control nobody has used.

So this is not listed as owed. **It blocks the 0.21.0 tag.** Alessandro does it
before the release, not after, by the steps in `RELEASING.md` §*Before the tag:
a control a person meets first in a browser*. If the browser refuses the
person who opened the printed address, the release is wrong and not the
browser, and this record is reopened before anything ships.

### 9. The tests the key would have emptied

The key sits in front of three guards that already had tests: the `Origin`
check, the rebinding guards and the walk over every refusal type. Each of
those tests sends a POST, and without the cookie the key refuses it **first**.
They would have gone on passing with the guard they name deleted, because a 403
from the key looks like a 403 from the origin check. The mutations in §7 are
what show they did not: each file sends the cookie, and says why where it does.

This is the fourth instance of that family in a week, and the first one found
in the same commit that created it rather than afterwards. The construction
rule it adds is written where the next control gets written, in
`CONTRIBUTING.md`: **a new guard in front of an old one empties the old
one's tests.** Give those tests what the new guard asks for, then mutate the
old guard away and watch them fail.

## Consequences

- **A script that POSTs to a flagged server stops working.** That is the point,
  and it is why this is not a patch. A script that means to promote runs
  `digline promote`, which is a command the hook reads and a person can be
  asked about.
- **For a person in world 1, the ordinary case, the cost is one click.** The
  address on the startup line is the one to open, and terminals make it
  clickable. Opening the bare `http://127.0.0.1:7373/` still shows every page,
  but its buttons answer 403 with a sentence that names the address to use.
- **A restart invalidates open tabs and bookmarks**, because the key is per
  start. An old tab is refused with a sentence naming why.
- **`localhost` and `127.0.0.1` are two hosts to a browser.** A cookie set
  under one is not sent to the other, so a person who opens the printed address
  and then types the other name has the pages and not the button's permission.
  The 403 sentence tells them what to do. The printed address uses the host the
  server bound to.
- **Another browser or profile needs the printed address copied into it.** That
  is the key doing its job.
- **The tag waits for a person to use it** — §8.
