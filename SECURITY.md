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
  index somebody could install from, that a user could be hurt by. Three exist
  so far, all from the 0.7.1 and 0.7.2 pass:
  [GHSA-x56p-g933-6xx6](https://github.com/digline/digline/security/advisories/GHSA-x56p-g933-6xx6)
  (high, `digline-mcp` executing a suite from anywhere on disk),
  [GHSA-j878-2v6m-m4vx](https://github.com/digline/digline/security/advisories/GHSA-j878-2v6m-m4vx)
  (medium, reads outside the perimeter), and
  [GHSA-xrvr-5x82-w7g7](https://github.com/digline/digline/security/advisories/GHSA-xrvr-5x82-w7g7)
  (low, a credential in a target URL reaching stderr and a CI log).
- **A `Security` entry in the changelog, and no advisory**, for a finding our own
  process caught **before** it was exposed — the audit, the adversarial pass, the
  release delta-pass. There is no version to warn anybody off, and an advisory
  against a defect nobody could reach is noise in the one channel that must not
  become noise. It is still written down, in full, where the fix is.

The second category is not a lighter one. It is where the finding that never
reached anybody goes, and the changelog says what it was rather than that
something was hardened.

## The delta-pass

**A release that adds surface gets an adversarial pass over that surface before
the announcement round.** Not before the tag — before anyone is told to
upgrade. It is a standing rule, and `RELEASING.md` carries the procedure.

Three questions per new field or new entry point: *where does it cross a
boundary, who wrote the value, and what does a hostile value do there.*
Reproduce on the artifact that actually travels, not on the code that builds it,
and write the regression test so that it fails against the release just cut.

It has paid twice. The pass over 0.7.1's four fixes found two more, shipped the
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
