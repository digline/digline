# Security

## Supported versions

**The latest release, and nothing else.** digline is alpha and moves quickly —
releases are weeks apart, not quarters — and a fix backported to a version
nobody is running is time not spent on the one everybody is. If you hit
something on an older version, please reproduce it on the current release
before reporting — and if you cannot upgrade far enough to try, say so in the
report and we will work out what to do.

## Reporting a vulnerability

Use GitHub's **private vulnerability reporting** on this repository:
[Security → Report a vulnerability](https://github.com/digline/digline/security/advisories/new).
It is enabled, it is private until we publish, and it keeps the whole exchange
in one place.

Please do not open a public issue for a vulnerability, and please do not send
it by email — a report that arrives in one person's inbox waits for that
person.

What to expect:

- an acknowledgement that a human has read it, not a receipt from a robot;
- a fix in the next release, or an explanation of why it is not one — see the
  scope note below, which rules out a whole category in advance;
- credit in the advisory and the changelog if you want it, and none if you
  prefer that. Say which.

There is no bounty. There is a fast reply and a name in the record.

## When a finding becomes an advisory

Not every security fix is an advisory, and a project that publishes one for
everything teaches its readers to skim them. The line here is **exposure**, and
it is drawn in one place:

- **A published advisory** — GitHub Security Advisory, with a CVE where one
  applies — for a vulnerability that **shipped**: a released version, on an
  index somebody could install from, that a user could be hurt by. The list
  below is a copy, written out because nothing here can read it at build time;
  the source is this repository's own advisories, which
  `gh api repos/digline/digline/security-advisories` returns and the Security
  tab shows — ask that, not this paragraph, for how many there are.

  **Grouped by what the looking was aimed at, because those are not
  interchangeable and the grouping is meant to help somebody decide where to
  look next.**

  *Looking at what a release added* — the delta-pass, on 0.7.1 and 0.7.2:
  [GHSA-x56p-g933-6xx6](https://github.com/digline/digline/security/advisories/GHSA-x56p-g933-6xx6)
  (high, `digline-mcp` executing a suite from anywhere on disk),
  [GHSA-j878-2v6m-m4vx](https://github.com/digline/digline/security/advisories/GHSA-j878-2v6m-m4vx)
  (medium, reads outside the perimeter), and
  [GHSA-xrvr-5x82-w7g7](https://github.com/digline/digline/security/advisories/GHSA-xrvr-5x82-w7g7)
  (low, a credential in a target URL reaching stderr and a CI log); and the
  delta-pass over 0.12.0, fixed in 0.12.1,
  [GHSA-g25g-q7j3-jcgp](https://github.com/digline/digline/security/advisories/GHSA-g25g-q7j3-jcgp)
  (low, perimeter fields in comparison deltas).

  *Looking at whatever a sentence had to be precise about* — the denominator
  article, fixed across 0.15.1 to 0.15.3,
  [GHSA-8c38-f965-cgww](https://github.com/digline/digline/security/advisories/GHSA-8c38-f965-cgww)
  (a gate raised from `fail` to `pass` reported as an improvement, where an
  unjudgeable case had shrunk the denominator under it).

  *Looking at what was already there* — the standing-code pass of 2026-09-23,
  fixed in 0.19.2 —
  [GHSA-m9mw-rwqm-g38r](https://github.com/digline/digline/security/advisories/GHSA-m9mw-rwqm-g38r)
  (medium, `digline register` creating and appending outside the store on the
  write that creates the register),
  [GHSA-qjqq-hrq4-rfgh](https://github.com/digline/digline/security/advisories/GHSA-qjqq-hrq4-rfgh)
  (medium, `digline view` comparing `Origin` against the request's own `Host`),
  and
  [GHSA-3q9c-qq5w-ff5m](https://github.com/digline/digline/security/advisories/GHSA-3q9c-qq5w-ff5m)
  (medium, `digline migrate` writing through a symlink committed in the store).

  **The third group is aimed somewhere the first cannot see, and the
  distinction earns its place here rather than in a changelog.** A delta-pass
  asks three questions of what a release *added*; the standing-code pass asked
  them of code no release had touched. Sixteen delta-passes and the
  advisories above had run before those three were found, and none of them reached any of the three — **not
  because they were done badly, but because a delta-pass looks at the delta by
  construction.** Each of the three lived in code that had been sitting still:
  a guard that exists but is not called from a call site added later, a check
  whose two inputs are both supplied by the attacker, a collector that skips
  the containment its sibling applies. A run of green delta-passes is evidence
  about deltas and about nothing else.

  The middle group is the least predictable of the three and the hardest to
  schedule: nobody set out to audit the denominator, somebody set out to
  **describe** it, and being made to write a sentence precisely is what turned
  up a gate that read `fail` as `pass`. It is here as a kind rather than as an
  anecdote, because "write down exactly what this does" is a way of looking,
  and it is the one that costs nothing to start.

- **A `Security` entry in the changelog, and no advisory**, for a finding our own
  process caught **before** it was exposed — the audit, the adversarial pass, the
  release delta-pass. There is no version to warn anybody off, and an advisory
  against a defect nobody could reach is noise in the one channel that must not
  become noise. It is still written down, in full, where the fix is.

The second category is not a lighter one. It is where the finding that never
reached anybody goes, and the changelog says what it was rather than that
something was hardened.

## Every severity argument names its reader

**A rule about how this file is written, taken from getting it wrong.** When a
finding is rated here — as an advisory or as a thing that does not need one —
the argument says *who is harmed*, in words, and that reader is checked against
the surfaces the finding actually reaches.

The one that failed said a gap was *"not a way in ... it changes what a human
believes they are looking at"*. Every clause was true of the character that had
been measured, and the class also contained characters no human can see at all,
on a surface whose reader had become a program holding tools. The argument was
not too weak; it was about somebody else. It stood for a release because
re-reading it looks like agreeing with it — the reasoning is sound, and nothing
in the sentence points at the assumption underneath.

So: name the reader, and name what they do with what they receive. A terminal
obeys. A browser renders. A person reviewing a baseline decides whether to
approve it. An agent acts. A finding that is harmless to one of them is not
thereby harmless, and a surface can gain a reader in a release without any of
the prose about it changing.

## The delta-pass

**A release that adds surface gets an adversarial pass over that surface before
the announcement round.** Not before the tag — before anyone is told to
upgrade. It is a standing rule, and `RELEASING.md` carries the procedure.

Three questions per new field or new entry point: *where does it cross a
boundary, who wrote the value, and what does a hostile value do there.*
Reproduce on the artifact that actually travels, not on the code that builds it,
and write the regression test so that it fails against the release just cut.

It has run on 0.7.1 and on every minor release since, each in the
changelog. The pass over 0.7.1's four fixes found two more, shipped the
same day as 0.7.2. The pass over 0.8.0 found `resolved_model` travelling in
clear out of a redacted run — a boundary decided that morning and wrong by
lunchtime — and 0.8.1 went out before the announcements. Neither became an
advisory, by the rule above; both are in the changelog under `Security`.

## What the design already commits to

None of this is a promise made by this file. Each line is a decision written
down before the code, with the record that argued it — read those rather than
trust this summary.

- **No network call digline makes on its own.** The ones your suite configures,
  to your provider, are the only ones there are. No telemetry, no update check,
  no phone home (fixed decision 5 in `CLAUDE.md`, and the README's *Not a
  funnel*).
- **No digline object holds a credential.** A key is never a constructor
  argument that gets stored, never in a `Response`, never in `Score.metadata`,
  never in an error message, never in a `repr`. Each provider's own SDK reads
  it from the environment
  ([ADR 0004 §5](docs/adr/0004-every-plugin-is-a-target-and-a-judge.md)). From
  0.5.0 the declarative suite format refuses an `api_key` key **by name**,
  because a suite file is a file that gets committed
  ([ADR 0007](docs/adr/0007-the-declarative-suite-format.md)).
- **A custom endpoint is recorded as a host, never as a URL.** `base_url`
  becomes host and port — never the scheme, never the path, and never the
  userinfo, so `https://user:secret@gateway/v1` cannot carry a credential into
  a run by accident. It is also the one field redaction holds back, because a
  host describes the client's own topology
  ([ADR 0005 §2](docs/adr/0005-the-configuration-of-the-system-under-test.md)).
- **A declared price is withheld at a named endpoint, and that is declared
  for what it is.** A negotiated rate is the customer's commercial fact, not a
  credential, so it never prints in a redacted document, a `--json`, an MCP
  response or `digline log`. But the suite's `config_hash` is computed from it
  and travels in clear:
  **withholding a declared rate is a latch, not a constraint** — the value never
  prints, but the hash narrows it; a rate you cannot afford to narrow belongs in
  a Python suite, or at an unnamed endpoint
  ([ADR 0022 §6](docs/adr/0022-the-declared-price.md)).
- **The payload stays where it is born; the verdict travels.** What crosses a
  boundary is a name, a status, a score, a threshold — not the prompt, not the
  output, not the reason, and not an artifact unless the suite declared a
  `Disclosure` in code that says so
  ([ADR 0002](docs/adr/0002-three-worlds-and-where-the-data-lives.md),
  [ADR 0003](docs/adr/0003-artifacts-travel-only-when-the-suite-says-so.md)).
- **There is no server side to disclose to.** The baseline and the runs are
  files in your own repository, under `.digline/`. digline has no hosted
  service, no account, and no database on your machine outside the project you
  ran it in (fixed decision 2). A vulnerability in digline is a vulnerability
  in a program you ran locally, not in something holding your data.

## Out of scope

**The behaviour of the models you evaluate.** Prompt injection, jailbreaks and
unsafe output from a model under test are not vulnerabilities in digline, and a
report about them will be closed as out of scope — kindly, and with this
paragraph.

digline measures whether answers got worse. It does not defend the model, it
generates no attacks, and it has no opinion about what an answer should say. An
attack that works on your application is a finding about your application, and
the useful thing to do with it is exactly what the README says: turn it into a
`Case`, so the suite makes sure it never works again.

What *is* in scope is digline mishandling what it is given — a credential
leaking into a run, a payload crossing a boundary the suite did not open, a
path escaping the working directory, a suite file causing execution nobody
asked for.

**A race against the filesystem is also out of scope, and this is the one place
it is written down.** Every path digline checks is checked and then opened:
`resolve()` says where a name leads, and the `open()` that follows is a second
call. Between them the filesystem can change, and an attacker who can replace a
file or a symlink *during a run* can have a checked path read a different file.
We have reproduced it — swapping a symlink in a loop while runs executed won 4
times in 30 — and we are not going to close it.

The reason is the shape of the tool, not the difficulty of the fix. digline runs
inside a repository you control, and the capability that race needs — writing to
that repository while a run is in progress — is already the capability to edit
`suite.py`, which is code and executes. A threat model where the attacker can
win a millisecond race but not change the file digline is about to run is not a
model of anything real.

Two things make it visible rather than silent, and both are deliberate: the
artifact is recorded under **the key it actually resolved to**, so a run that
read `../outside/secret.txt` says exactly that in its artifact section and in
every report built from it; and artifacts are hashed, so the same declared file
reading differently between two runs shows up as a change rather than as
nothing. A race that wins still leaves its name in the record.

What is **not** out of scope, and was fixed in 0.7.2, is a path that escapes
without any race at all — a symlink sitting in the store, checked once, read
once, no timing involved. The line is whether digline can tell: it can see where
a name leads at the moment it looks, and it is answerable for that.

## Closed: text that is never language is neutralised

**This section used to say bidirectional controls were open, and it argued that
they did not matter very much. The measurement — made by the 0.19.0 delta-pass,
whose subject was something else — was right, and the argument was wrong.** Both are kept here, because a reader who acted on the old sentence
deserves to see what replaced it and why.

### What is fixed

`report.visible()`, `core.json_visible()` and `report.escape()` now neutralise
the characters that are **never language**, listed once in
`core.NEVER_LANGUAGE`: the bidi embeddings and overrides U+202A–U+202E, the
interlinear annotation characters U+FFF9–U+FFFB, and the tag block
U+E0000–U+E007F. Each is written as its escape text — `\u202e`, `\U000e0041` —
so every surface shows that something was there.

0.10.1 closed DEL and the C1 block against a terminal; this is the range that
was never in that scope, and it is closed now for a reader that did not exist
then.

The rest of the `Cf` category is deliberately untouched, and the distinction is
the fix rather than a caveat. U+200E/U+200F and U+061C set direction in ordinary
Arabic and Hebrew prose; U+200C/U+200D carry meaning in Indic scripts and hold
emoji sequences together; U+2066–U+2069 are the isolates Unicode recommends
*instead of* the deprecated overrides. Neutralising the category would corrupt a
report rendered in a language this project exists to serve. The tests hold both
halves: eleven characters must be neutralised, five must survive, and a
ZWJ family emoji must come through every surface intact.

### The argument that was wrong

The old section said, of U+202E:

> *"It is **not** a way in. It moves no payload, crosses no boundary, and reads
> no file it was not given: it changes what a human believes they are looking
> at."*

That is true of U+202E and it was never the whole class. **The tag block does
not deceive a human at all — it is invisible to every surface here — and the
reader it addresses is an agent holding tools.** Since 0.15.0 `digline-mcp`
renders through `digline.wire`, and `core/text.py` had already written down what
that surface is for: *"a terminal is very often what reads the program's output
next"*. The reader changed and the argument did not follow it.

Measured rather than asserted: an invisible 49-character instruction spelled in
the tag block, embedded in a `case_id`, survived `redact()` with nothing
disclosed and arrived intact at all five surfaces — the run document, the
comparison JSON, the HTML report, a terminal line, and `--json`. A reviewer
reading the committed baseline saw `capital-of-italy`.

So the old sentence fails in its own terms. It still moves no payload, crosses
no boundary and reads no file. What it moves is an **instruction**, into the
context of the one reader that acts on instructions — and "not a way in" was a
claim about a human reader, made on a surface built for a machine one.

### What this cost, and the rule taken from it

The gap was found by a delta-pass whose subject was something else, recorded
here honestly, and then left open for a release on an argument about who was
reading. The lesson is not that the measurement was insufficient — it was
exact — but that **a severity argument has to name its reader**, and this one
named the wrong one for a surface that had gained a new reader in the meantime.
