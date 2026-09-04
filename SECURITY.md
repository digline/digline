# Security

## Supported versions

**The latest release, and nothing else.** digline is alpha and moves quickly:
0.4.0 and 0.5.0 are three weeks apart, and a fix backported to a version nobody
is running is time not spent on the one everybody is. If you hit something on
an older version, please reproduce it on the current release before reporting —
and if you cannot upgrade far enough to try, say so in the report and we will
work out what to do.

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
