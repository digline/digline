# Changelog

Each release tells its story here — what changed, what it means for a reader
upgrading, and what deliberately did not move. The reasoning lives in
[`docs/adr/`](docs/adr/); this says what to expect. For the one-line version,
read the [release titles](https://github.com/digline/digline/releases) — the
notes under them are this file, verbatim.

## Unreleased

**A forged journal record is refused before the journal opens.** From 0.11.0's
delta-pass. `execute()` has always refused a `done` naming a case the suite does
not declare — it is an invariant of the driver — but on a resume that refusal
arrived *after* `open_journal`, so a journal holding a record for a case nobody
declared cost an empty leg file per attempt and answered in a `ValueError`.
`prepare()` now refuses it by name, with the journal exactly as it was and no
call made, which is what ADR 0017 §6 promises for every other input on that
list.

## 0.11.0 — 2026-09-11

**The journal.** digline **0.11.0**, alone: the three provider plugins stay at
0.4.0, `digline-mcp` at 0.1.1 and `pytest-digline` at 0.1.3. `SCHEMA_VERSION`
stays **10** and `OUTPUT_VERSION` stays 1 — no stored document moves, no
`--json` shape moves, **no baseline needs re-promoting**, and a completed run is
the file it has always been.

```sh
uv add --upgrade digline
```

### A killed run is finished, not paid for twice

A run is written once, at the end. A 144-case suite at five samples — 720 calls,
about four dollars — was killed mid-flight by a supervisor outside digline, and
everything went with it: seven hundred paid calls, a judged run that existed
only as objects in a process, and nothing on disk.

digline now keeps a **journal** beside the run as it goes. One record per case,
flushed and `fsync`ed before the next case starts, under
`.digline/<tenant>/runs/<suite>/.pending/<run key>.<leg>.jsonl` — the same
directory the runs live in, covered by the same generated `.gitignore`, holding
exactly what the finished run file would hold and nothing more. A suite that
does not record its answers does not journal them either. It is deleted the
moment the run file exists.

```sh
digline run --suite eval/suite.py --resume
# 112 of 144 cases × 5 samples = 560 calls to the target; 32 cases already judged
```

No key resumes the most recent unfinished run; `--resume KEY` names one. A plain
`digline run` never resumes and says on stderr that a journal is pending, so
paid calls are not abandoned by accident; `--resume` with nothing pending
refuses rather than quietly starting a full one.

Each leg is a file of its own, created with `O_CREAT|O_EXCL`. That is the whole
concurrency story and it needs no lock: a second process resuming the same run
is refused by name, and the process this feature exists for is one that was
*killed* — a lock it could not release would block the very rescue it was meant
to protect.

**A resumed run carries no marker, because there is nothing to mark.** It keeps
the `created_at` of the run it finishes, lands at that run's key, and is the
document the kill prevented — byte for byte, which is asserted rather than
hoped. What makes that legitimate is the refusal list: a resume stops, **before
the first call of the new leg**, when `config_hash`, the cases, the declared
artifacts, `target_config`, `judge_config`, `record_responses`, `git_commit` or
the digline version has moved. That list is not a collection of good ideas — it
is exactly the set of facts the run document asserts. Half a run under one
prompt and half under another is not a run.

**An alias that rolled between the halves errors instead of being averaged.**
What the provider said answered is journalled as it is learnt and given back to
the target and the judges on resume, so a model that changed across the seam
raises on the first call of the new leg exactly as it would have raised on the
next call of the old one: that case errors, the run is still written, and it
exits 2 and cannot be promoted (ADR 0005 §8).

**Errored cases are retried by default**, and that closes a second loss this
release was not opened for. A target that raises at sample 4 of 5 errors its
whole case — correctly, since a partly-sampled case would be a weaker
measurement wearing the declared suite's name — and an errored verdict exits 2
and cannot be promoted. So a 529 that outlived the SDK's own retries used to
cost the price of the whole suite. The rule in the driver is unchanged; what
changed is the remedy, which is now `--resume` re-paying for that one case.
`--keep-errors` keeps them as journalled.

For a script that drives digline: `digline.host.prepare()` decides what a launch
is and refuses a resume that would not be one, at no cost, before anything is
called; `digline.host.measure()` opens the journal, runs, writes the run and
deletes the journal. `execute()` gained `done=` and `on_case=` and still knows
nothing about the store. `digline run --json` gained `resumed` and `reused` —
facts about the launch, not about the run, which is why they are there and not
in the document.

The reasoning in full is
[ADR 0017](docs/adr/0017-the-journal-and-the-resumed-run.md).

**The MCP `run` tool does not journal yet.** Both front ends will sit on the
same host composition, but `digline-mcp` declares a floor — `digline>=…` — and a
floor cannot name a release that does not exist yet, so its call site moves in
the `digline-mcp` release that follows this one. It gains no `resume` verb
either way: that collides with its acknowledged call count rather than extending
it. A killed CLI run leaves a journal today; a killed MCP-launched one does not.

### The examples' cap moved, and the floor did not

Every example now reads `digline>=0.9,<0.12`. Nothing about the format required
it — schema 10 documents are read the same either side of this release, so the
floor stays where it was and no example migrates anything. What required it is
arithmetic: a lock regenerated against 0.11.0 cannot resolve under `<0.11`.

### Also

A redaction gate had a flake worth naming, since it is the kind that fires on a
release day and cannot be reproduced: a test asserting that `2500` had been
removed from a report read a `created_at` stamped by the real clock, and the
microseconds of `…T14:11:03.525004+00:00` contain those four digits. The
timestamps now come out of the haystack first; every digit the run did not stamp
is still asserted.

## 0.10.1 — 2026-09-11

**The delta-pass patch.** digline 0.10.1 and **`pytest-digline` 0.1.3**. The three
provider plugins stay at 0.4.0 and `digline-mcp` at 0.1.1. `SCHEMA_VERSION` stays
**10** and `OUTPUT_VERSION` stays 1: no stored document moves, no `--json` shape
moves, **no baseline needs re-promoting**.

```sh
uv add --upgrade digline
uv add --dev --upgrade pytest-digline
```

Both findings from 0.10.0's release delta-pass, closed the same day. The pass is
the standing rule: a release that adds surface gets an adversarial read **before**
any announcement, and 0.10.0 added the most sensitive surface this product has —
the model's own answers, recorded in a run file.

### Security: a document could rewrite the terminal reading it

**Found by the release delta-pass, before any announcement. No advisory**, by the
line `SECURITY.md` draws: an advisory is for a vulnerability that shipped with
real exposure, and a `Security` entry for one the process caught. Nothing here
crosses a privilege boundary, nothing is disclosed, and the **exit code — the
contract — was never affected.** What was affected is the sentence beside it.

Strings read out of a stored document reached a terminal unsanitised, so ANSI
escapes in them could erase the line being printed and forge one that reads as
digline's own output — *"digline: Nothing got worse."* — while the exit code said
`1`. Escape injection is precisely what defeats a reading, and a reading is what
a review of a committed baseline is.

**The class predates 0.10.0.** `digline list` has printed `environment` and
`git_commit` straight from the document since 0.1.x; 0.10.0 added
`digline_version` to the same class, in the installed-behind warning, which is
how the pass found it. So the fix is **at the sink and not on a field**: every
sentence the CLI prints now goes through `say()`, and every control character in
it is *shown* (`\x1b`, four printable characters) rather than obeyed. `emit()` is
the named exception for the two things that are documents rather than sentences —
`--json`, where `json.dumps` has already escaped everything, and the HTML report,
whose values are HTML-escaped where they are rendered. A test per sink, with the
forgery planted in a different field each time.

**`pytest-digline` had the same class and a shorter fuse**, which the pass only
established by trying it: the plugin prints `Verdict.reason` into pytest's report,
and a reason is *a judge quoting what a model answered*. No hostile document is
needed there — only an answer with `\x1b[2K\r` in it. Fixed the same way, with
the same function: `report.visible()` lives in `digline.report` because both front
ends need it and a front end may not import another one. That is why the plugin
moves to 0.1.3 with a floor of `digline>=0.10.1`.

What was checked and is **not** affected: every HTML surface, every `--json`
surface, the MCP responses, and the exit codes.

### Fixed: a recorded response's `kind` is validated where it is read

A forged `kind` — `"../../etc/passwd"` — parsed, and failed later inside
`restore_output` as a `JSONDecodeError` that the driver reported as an *errored*
case. Every sibling field in that document is checked on the way in; this one was
cast. It now refuses at load, naming the field and the three branches `Output`
has. Found by the same pass, and low: an error is neither green nor a regression,
so nothing was ever reported as passing.

## 0.10.0 — 2026-09-11

**The honest ledger.** digline 0.10.0 and **`pytest-digline` 0.1.2**. The three
provider plugins stay at 0.4.0 and `digline-mcp` at 0.1.1: nothing in them
changed and their floors already admit this core.

`SCHEMA_VERSION` moves to **10** — the first bump since 8 → 9, and the first one
with a written rule for what a bump may carry. `OUTPUT_VERSION` stays 1: three
keys join `compare --json`, and an added key leaves a consumer working.

```sh
uv add --upgrade digline
uv add --dev --upgrade pytest-digline
digline migrate --suite eval/suite.py       # first, before anything else
```

**Nothing needs re-promoting.** The migration invents nothing and `config_hash`
does not move — the nine baselines committed under `examples/` changed by exactly
one line each, which is what that promise looks like in a diff.

Three things the run document can now say that it could not before: which digline
wrote it, what the target actually answered, and which of its cases was watching
the model rather than measuring it.

- **Changed (storage):** `SCHEMA_VERSION` is **10**. A run document written by
  0.10.0 is refused by 0.9.0 and a 0.9.0 document is refused here, in both
  directions and by name, so `digline migrate` is the first thing to run after
  the upgrade — `AGENTS.md` §8's rule, unchanged. The step is **additive and
  writes nothing**: all three of the fields this version adds mean what their
  absence already means, so a migrated baseline keeps its `config_hash` byte for
  byte and **nothing needs re-promoting**. The nine committed example baselines
  moved by exactly one line each, which is what that promise looks like in a
  diff. New: [ADR 0014](docs/adr/0014-what-may-ride-a-schema-bump.md), the rule
  for what a future bump may carry — a field rides only if it leaves
  `config_hash` untouched, migrates without inventing, and does not widen what
  travels.

- **Added:** `Run.digline_version` — the document says what wrote it, beside the
  `schema_version` that says what shape it is. Stamped by the driver; empty
  means *not recorded*, which is what a migrated file honestly carries, and the
  migration never stamps its own version on a document it only rewrote. When a
  document turns out to have been written by a **newer** digline than the one
  reading it, the CLI says so on stderr and the wire carries the fact. It is
  never an exit code: the codes are a contract about the suite.

- **Added:** `promote_baseline` stamps **`promoted_at`** on the baseline it
  writes. `created_at` says when the run was *measured*; a promotion happens once
  somebody has read it, which is commonly days later — `AGENTS.md` §2 is an
  entire rule about not promoting the first green run — and until now the
  reference carried no time of its own. It is one field and deliberately not a
  ledger: a history of past promotions, and who made them, is a different
  decision with its own retention and boundary questions. Absent on a run, absent
  on a baseline promoted before this release, and never invented by the
  migration: a plausible date on a human signature is exactly what it must not
  write. The comparison's header names it beside the reference — *Reference
  approved* — and `get_baseline` carries it over MCP.

  **It is a `ResultStore` protocol change**: `promoted_at` is a mandatory
  keyword, passed in rather than read, because the store may not touch the clock
  — the rule `created_at` already follows — and a default would have made *not
  recorded* the ordinary outcome, which is the gap the field closes.

- **Fixed:** the view's promote button could return a 500 instead of a refusal
  screen. It caught three of the store's refusals and `ReplayedRunError` had
  joined them as the fourth, so promoting a re-judged run through the browser
  would have raised where the CLI says why. Found while stamping the promotion
  time through both front ends.

- **Fixed:** the listing's advice about documents it stepped over now matches
  the direction it found them in. It had been unconditionally *"run `digline
  migrate`"*, which pointed backwards is advice to do the one thing nothing can
  do — and could not be noticed until now, because until schema 10 no released
  digline had ever met a document from a newer one.

- **Added:** `Suite(record_responses=True)` records what the target answered —
  per case, per sample, beside the rendered prompt that produced it and what the
  call cost — and **`digline rejudge`** replays those answers through the current
  suite. A changed judge, rubric or threshold, measured at no cost to the target.
  Off by default, outside `config_hash`, and it is **not** a `Disclosure`: what
  crosses a boundary and what is written inside the perimeter are two decisions.
  The answers never travel — `redact()` drops them, `digline.wire` does not know
  the field's name, and `digline promote` strips them from the reference, because
  `baselines/` is committed. A re-judged run declares its source and **cannot be
  promoted**: a replay has no target variance, so its interval would freeze a
  noise floor measured without the noise — the fourth condition on promotion.
  Whole or nothing at 65 536 characters per field: a clipped answer re-judged
  produces a score that looks like every other score.
  [ADR 0015](docs/adr/0015-the-recorded-output-and-the-declared-re-judge.md),
  [`docs/rejudge.md`](docs/rejudge.md).

- **Added:** `Case(canary=True)` — a case that watches the model behind the alias
  instead of measuring quality. It is counted in **no** aggregate, and the
  exclusion is a figure in the verdict's metadata so a denominator stays
  reconcilable with the case file; it needs no label and may declare no group. If
  it moves **at all** — worse or better, since its score is a fingerprint rather
  than a quality — the headline says *the model under this alias likely changed*
  and the run exits `1`, on a fact of its own rather than on `worse`. A suite
  that declares one must sample at least twice: at one sample there is no noise
  to measure, and a canary that fires on a wobble is a canary its owner learns to
  ignore. Complementary to `resolved_model`, which is silent on the providers
  that name nothing. [ADR 0016](docs/adr/0016-the-canary-case.md).

- **Added (`pytest-digline` 0.1.2):** a canary that moved is a **FAILED** row,
  including one whose outcome is `improved` — the one place the per-row mapping
  cannot be read straight off `regressed`. Its floor rises to `digline>=0.10.0`,
  because it reads a field rather than an imported name and the floors gate
  tracks names.

- **Unchanged:** `OUTPUT_VERSION` stays `1`. `rejudged`, `canary_moved` and the
  per-delta `canary` are added keys, and an added key leaves a consumer working.
  `canary_moved` is the first addition that can change an exit code, and only for
  a suite that declares a canary — which no suite did before this release.

- **Changed:** CodeQL now runs the **default** suite instead of
  `security-and-quality`. The earlier entry below argued the wider set says
  more about a library; what it said in practice was 74 quality findings, 19 of
  them a single extractor limitation — PEP 695 `type` aliases named in
  `__all__` read as undefined exports. None of it was reachable by a fix,
  because the quality half is already gated by checks that fail the build:
  ruff (F401, F822) and pyright strict. A code-scanning list too long to read
  is one where a real alert arrives as noise, which is the opposite of what the
  scan is for. The suite is selected by *omitting* `queries:`, not by naming
  it: there is no pack called `security`, and asking for one by that name fails
  the run outright. The 74 are gone from the list, the 19 stand dismissed with
  their reason, and what remains open is one real advisory waiting upstream.
  `RELEASING.md` gains the step that only makes sense now that the list is
  short: before the tag, ask whether anything new has arrived since the last
  one.

- **Added (in the repository, not on the index):** `digline-openai` prices
  `gpt-6-astra`, read from the published
  list on 2026-09-11 along with every other entry, which is unchanged. The
  package stays at **0.4.0** and is not part of this tag, so the entry rides
  `digline-openai`'s next release: packaging and a price list do not earn a
  version of their own. Short
  context only, on the same terms as the GPT-5.6 entries: crossing 272K input
  tokens reprices the whole request and that meter is still not modeled here.
  Until this entry existed the model was refused at `preflight` rather than
  guessed at — the honest failure, and the one fixed decision 3 asks for. The
  price sentinel never knew the family had shipped and is not meant to: it
  guards the prices of entries the list already carries, and its docstring now
  says so, because watching a provider's catalogue would be a network call
  nobody configured (fixed decision 5).

- **Fixed:** `digline-mcp` and `pytest-digline` now ship `py.typed`. Both
  classified themselves `Typing :: Typed` and neither carried the marker PEP
  561 says makes it true, so a consumer importing either one from the wheel got
  `reportMissingTypeStubs` under pyright — and, with `useLibraryCodeForTypes`
  off, `Unknown` for every name it imported. `digline` itself and the three
  provider plugins were unaffected and are unchanged. Verified the way the
  defect had to be verified: in a scratch project against the built wheels,
  where the annotations this repository resolves from source are not on the
  path. `tests/test_packaging.py` now holds the classifier and the marker
  together, in both directions.

- **Fixed:** a target that returned no text now names the ending the provider
  declared, where the sentence used to come from the parser. An empty
  completion is still a legal *output* — the assertions get to fail it, and
  that is unchanged — but a suite that judges a *shape* parses the reply first,
  and a mute one died there as `JSONDecodeError: Expecting value: line 1 column
  1`, throwing away the `finish` the provider had reported one line earlier.
  `ProviderTarget` now reads that failure before letting it out: with nothing
  in the reply the case errors with the sentence 0.8.0 wrote for a judge —
  *"the target returned no text: the provider reported 'max_tokens' (512 of 512
  output tokens), so it was truncated before the first character — raise
  max_tokens"* — and the parser's own exception is kept underneath as its
  cause. The concrete case is an adaptive model that spends its whole budget
  thinking and ends at the cap with nothing written, which a token count cannot
  tell apart from a tool call.

  `JudgeBase._no_text` is the twin that already did this on the other side, and
  the two are **one implementation** now: `no_text_reason` builds both
  sentences, `said_something` is the check that sees past an assistant prefill
  for both, and a judge keeps one sentence of its own because it asked for a
  JSON object and a target asked for whatever the suite judges. All three
  published plugins inherit the reading — **nothing under `packages/`
  changed** — and a target that sends no token cap gets a sentence that claims
  none, rather than one about a cap nobody set.

- **Fixed:** a repeated check whose samples all errored now says *why* none of
  them could be judged. The fold replaced every sample's reason with *"no
  sample could be judged over 3 attempts"*, and that sentence was the whole of
  what reached the run file: the cause 0.8.0 taught a mute judge to report
  never survived sampling, so the one place a noisy judge is actually used —
  `Repeated`, and `Suite.samples` with it — was the one place its diagnosis was
  dropped.

  The summary stays, because it is true and it is what decides the status, and
  it now carries the cause under it: *"no sample could be judged over 3
  attempts: the judge returned no text: the provider reported 'max_tokens'
  (512 of 512 output tokens), so it was truncated before the first character —
  raise max_tokens"*. Where the samples died of different things the
  distribution is named rather than the dominant one — *"...for 2 different
  reasons — 2 of 3: …; 1 of 3: …"* — because a cause that appeared once is
  exactly the one worth seeing: the check is not flaky in one way, it is
  failing in two. The partial case, where some samples were judged, is
  untouched.

  **No document changed shape.** The wire and the report render whatever
  `reason` says, and what moved is what `reason` says. Worth knowing where it
  does *not* arrive: `digline explain` carries no reason by decision (ADR 0012
  §4), so an operator reading the fact list still sees *"could not be judged"*
  and finds the cause in the run file or in a complete report.

- **`examples/operator/`: `cycle.json` moves from format 1 to 2**, because the
  dossier now reads `digline explain --json`'s fact list instead of `compare
  --json full` — a forked loop writes format 2 on its next run and alerts
  already written are untouched, but the new `dossier.py` cannot re-render a
  format-1 cycle (the example's own captured alerts were regenerated through
  the new path).

- **The example reports were re-rendered** on the commit they name, against the
  migrated baselines, so `Code version` is a hash a reader can check out. Seven
  of the nine had been carrying `-dirty`. **Two still do, by design**, and the
  sentence beside the hash is the reason: `prompt-first`'s report is the
  comparison after a line was added to a prompt the example deliberately does not
  ship, and `classifier`'s is a narrated comparison at five samples — the README
  walks through the wobble that run recorded, and a fresh sampled run does not
  reproduce it. Re-rendering either would replace a document the prose explains
  with one it does not.

Everything below is the repository's own security posture — the supply chain
around the code, not the code. **No published package changes.** It is recorded
here because a reader checking how digline is built is entitled to the same
evidence as one checking what it does.

- **Security:** every workflow job now declares exactly the token it spends. A
  job-level `permissions:` **replaces** the top-level block rather than adding
  to it, so `publish.yml`'s two OIDC jobs had `contents` at none while running
  `actions/checkout`, and worked only because this repository is public. Both
  scopes are written out. The `site` job went the other way, to
  `permissions: {}`: it has no checkout and authenticates to another repository
  with a PAT, so it spends nothing from `GITHUB_TOKEN` — worth saying on the one
  job holding a credential that can write somewhere else.
- **Security:** every GitHub Action is pinned by commit SHA, with the tag in a
  comment beside it, and `docker/Dockerfile`'s base image is pinned by digest.
  A pin without an update tool is a freeze, so `.github/dependabot.yml` arrives
  with it and watches all four ecosystems — actions, the image, the `uv` locks,
  and the two Maven examples.
- **Security:** CodeQL runs on every push and pull request, and weekly, because
  the queries move even when the code does not. `security-and-quality`, not the
  default set: digline is a CLI with a written threat model, and the wider set
  is the one that says something useful about a library.
- **Added:** `scorecard.yml` — the weekly OpenSSF Scorecard run, SARIF to code
  scanning, results published so the number can be checked against its source
  rather than against a picture.
- **Added:** `SECURITY.md` says when a finding becomes a published advisory and
  when it is a changelog entry instead. The line is exposure: an advisory for a
  vulnerability that shipped, a `Security` entry for one our own process caught
  before it could reach anybody. The delta-pass rule is written down beside it.
- **Fixed:** the two `examples/langchain4j` services carried 63 known-vulnerable
  transitive dependencies between them — nothing in digline, nothing on PyPI,
  but a demo that ships those is a demo teaching the wrong thing. Spring Boot
  3.4.5 → 4.1.1 and Quarkus 3.20.1 → 3.39.3, both at **zero** advisories now,
  measured against OSV on the resolved runtime trees. The Quarkus service loses
  its `ChatLanguageModel`, which existed only because its extension lagged
  langchain4j's rename; the two services now read the same, and the README
  paragraph that explained the difference is gone.


## pytest-digline 0.1.1 — 2026-09-10

`pytest-digline` alone. digline stays at 0.9.0 and nothing else moves: this is
one package on its own version line, which is what the named tag shape exists
for.

```sh
uv add --dev --upgrade pytest-digline
```

- **The plugin no longer imports digline when no suite is named.** A `pytest11`
  entry point is loaded at pytest startup in **every** environment where the
  package is installed, including projects that never use digline — and
  importing the core at module level pulled 44 modules with it: the store, the
  driver, the report, the host, and `jsonschema` behind the assertions. A bare
  collection on an unrelated project measured **138 ms against 88 ms** without
  the plugin, which is 50 ms on a command people press hundreds of times a day,
  spent on a tool they are not using.

  The imports moved inside the four functions that reach for them, all of which
  run only once a suite has been named. A bare collection now imports **no**
  digline module at all and costs **8 ms**. Two tests hold it: one asserts that
  nothing named `digline` is in `sys.modules` after a bare run, and its guard
  asserts that naming a suite *does* load it — laziness that never loads is not
  laziness.

  Behaviour is unchanged in every other respect: same rows, same four states,
  same exit codes. ADR 0013 §8 said this plugin is inert when unconfigured, and
  it was inert in everything a reader could see; startup was not one of those
  things. Found by the 0.9.0 delta-pass, which is what the pass is for.

## 0.9.0 — 2026-09-10

**The adoption release.** digline 0.9.0 and **`pytest-digline` 0.1.0**, which
is new. The three provider plugins stay at 0.4.0 and `digline-mcp` at 0.1.1:
nothing in them changed and their floors already admit this.
`SCHEMA_VERSION` stays 9 and `OUTPUT_VERSION` stays 1 — no stored document
moves, no `--json` shape moves, and **no baseline needs re-promoting.**

```sh
uv add --upgrade digline
uv add --dev pytest-digline        # 0.1.0, new
```

Two front ends, and neither of them is a new way to decide anything. The engine,
the assertions, the comparison and the exit codes are unchanged; what this
release adds is two more places to meet them — the test report a Python team
already reads, and the pull request a reviewer is already looking at.

### `pytest-digline` — the comparison as rows in pytest

A pytest plugin that gates on the baseline committed in your repository, one row
per **check**:

```sh
pytest --digline-suite eval/suite.py
```

```
eval/suite.py::how-do-i-return::llm_rubric     FAILED
eval/suite.py::beta::contains                  PASSED
eval/suite.py::refund-status                   SKIPPED (the refund API is down, ticket 412)
```

- **One item per check** — one assertion on one case — because that is digline's
  own unit of verdict. A row per *case* would fold several verdicts together
  under a rule invented in a front end, and would have to choose which of a
  simultaneous regression and error to show.
- **Four states, and the fourth is the news.** Fine is a pass, worse is a
  `FAILED`, could-not-be-judged is an `ERROR` — pytest's error state, because
  an error is neither green nor a regression — and **a suspended case is a
  `SKIPPED` carrying the reason the suite declared.** That last one is a state
  the exit code cannot express: a suspension never fails, so on the CLI route it
  disappears into `0` and nothing in the number says the run was smaller than
  the suite.
- **It compares and does not run**, by default and by construction: two
  documents read off disk and a pure function, no provider call at all. pytest
  is a command people run on a keystroke. `--digline-run` opts into producing a
  run first, prints the planned call count before the first call, and **refuses
  under `--collect-only`** — a command whose job is to list test names must
  never be able to spend a hundred model calls.
- **There is no promote surface.** Not refused — *absent*, the way it is absent
  from `digline-mcp`, and a test in the package sweeps its own sources for the
  name so it stays that way. A green test run is the likeliest place in this
  product for a baseline to be promoted by accident.
- **It is inert until you name a suite**: no rows, no header, no output.
  Installing it changes nothing about a repository that has not asked for it.

**What pytest cannot carry, said out loud:** the process exit code. `digline
compare` exits `1` for a regression and `2` for a run it could not judge; a
pytest run exits `1` for either. The distinction survives in the report — `F`
and `E` are counted apart, `-rE` lists the errored rows, `--junit-xml` keeps
them separate — and a job that needs `1` versus `2` runs `digline compare`.

The reasoning is [ADR 0013](docs/adr/0013-the-pytest-plugin.md); the page is
[`docs/pytest.md`](docs/pytest.md).

### `digline/digline-action` — the gate on the pull request

A GitHub Action, in its own repository because the Marketplace requires one.
**Composite over the official image**, so the action's version and
`ghcr.io/digline/digline` are released together:

```yaml
- uses: digline/digline-action@v1
  with:
    suite: eval/suite.py
```

- It comments the comparison on the pull request as **`digline compare`'s own
  output, verbatim, in a fence** — not reassembled into a table, because the
  sentence a reviewer reads has to be the sentence the HTML report shows and the
  sentence the CLI prints.
- It **exits with digline's code**, unchanged: `0`, `1`, `2` reach
  `steps.<id>.outputs.exit-code`, so a later step can still tell a regression
  from a run nobody could judge.
- `image:` is an input, which is the point of the composite form. The official
  image contains the CLI and the three plugins and nothing else — no dynamic
  installs, ever — but `digline compare` loads your suite and your suite imports
  your application, so a suite with dependencies of its own derives the image
  and points the action at it. A docker action's image is a static string and
  could not have offered that.
- It comments on `1` and `2` always; `comment-on-success` is off by default,
  because a comment on every green pull request is what teaches a reviewer to
  scroll past them.

### Also in this release

- **`check_line` is public in `digline.report`.** The per-check sentence — *"dropped
  from 0.910000 to 0.640000, below its threshold of 0.700000, and beyond the
  0.880000–0.950000 this check measured across 5 samples"* — already filled the
  report's "what happened" column and `compare`'s summary lines; it was private,
  and `summary_lines` only ever emitted the whole list. Now a third front end
  can print the report's own line instead of composing a fourth rendering of one
  comparison. `summary_lines` is expressed over it, so they cannot drift.
- **digline's PyPI page gains its links.** The `[project.urls]` block — homepage,
  documentation, changelog, repository, issues — was added after 0.8.1 was
  already uploaded, and a package's metadata only reaches the index with an
  upload. This is that upload. The four plugin pages got theirs the same way and
  will show them on their next release.


## 0.8.1 — 2026-09-10

digline 0.8.1. One security fix, **found by the release delta-pass over 0.8.0's
own new surface, the same day** — hours after the tag and before the
announcement round. The three plugins stay at 0.4.0 and `digline-mcp` at 0.1.1:
the fix is in the core and every reader inherits it. `SCHEMA_VERSION` stays 9
and `OUTPUT_VERSION` stays 1.

```sh
uv add --upgrade digline
```

- **Security:** a redacted run from an **OpenAI-compatible endpoint** no longer
  carries the model id that endpoint reported. 0.8.0 recorded
  `resolved_model` — what the provider said answered — and let it travel in
  clear, on the ground that a model id is a public product name. That is true
  of `claude-sonnet-5-20260115` and false of what a customer's own vLLM,
  Ollama or gateway puts in the same field: `acme-legal-assistant-prod-eu-west-v3`
  is a project codename, an environment and a region, and it travelled beside a
  `base_url` withheld for describing exactly that.

  It arrives in the **same reply from the same server** as `fingerprint`, which
  0.8.0 withheld for precisely this reason — so the rule had been written once
  and applied to one of the two fields. It is now conditional on the fact
  redaction already holds: `resolved_model` travels in clear where no
  `base_url` was set, and is withheld — key recorded, value discarded,
  `compare()` answering `unknown` rather than `same` — where one was. **Inside
  the perimeter nothing changes**: an unredacted run records it whatever the
  endpoint, and the alias-rolled delta ADR 0005 §9 exists for still fires on a
  first-party endpoint, which was its motivating case. The *sent* `model` keeps
  travelling and is not affected: it is written in the suite, and the suite goes
  through a review. (ADR 0005 §9, amended)

  **One thing to know if you already have a redacted run from a compatible
  endpoint.** Such a document claims a perimeter it does not keep, so it is now
  **refused on read** rather than loaded — the same stance `run_from_json`
  takes on a schema it cannot be trusted to interpret. The message says which
  field is wrong and distinguishes the two readers: rebuild it with `redact()`
  if you hold the original, and ask the sender again if it arrived from
  elsewhere. Only runs written by 0.8.0, redacted, from an endpoint with a
  `base_url` are affected — a window of hours.

  No advisory was filed, and that is a judgement rather than an omission: a
  server-chosen name in a feature that had been public for hours is what a
  changelog line is for. The GHSA practice stays for shipped vulnerabilities
  with real exposure.

- The release runbook gains the standing rule the day earned: **a release that
  adds surface gets a delta-pass over that surface before the announcement
  round**, not after it.


## 0.8.0 — 2026-09-10

digline 0.8.0, and **`digline-anthropic`, `digline-openai` and
`digline-bedrock` 0.4.0** — the trio moves together because all three implement
the widened contract this release is about. `digline-mcp` stays at 0.1.1:
nothing in the server changed, and its floor already admitted this.

```sh
pip install digline                # 0.8.0
pip install digline-anthropic      # 0.4.0
pip install digline-openai         # 0.4.0
pip install digline-bedrock        # 0.4.0
```

The release is **the record**: what a provider hands back stops being a pair of
numbers and becomes a document of what happened. `_complete` widens from
`(text, Usage)` to a `Completion`, so the judge **reads** the cause of an empty
answer where the provider states one instead of inferring it from a token
count; `ToolsCalled` makes *how* an answer was produced assertable for the first
time, with an error — not a failure — when a provider contradicts itself; and
every run records which model actually answered, so an alias that rolled is a
named delta rather than an invisible one.

**Third-party plugins are unaffected, by construction.** The old
`(text, Usage)` pair is still accepted and always will be — the union is
permanent, not a deprecation window — so a plugin written against any previous
release keeps working untouched. That is why the floor moves only for the three
plugins in this workspace, which reach for the new names.

The observed identity is exactly as measured, and the sentence says so:
observed on Anthropic (`claude-haiku-4-5` → `claude-haiku-4-5-20251001`);
OpenAI carries the fields per SDK shape, unmeasured here; Bedrock returns no
model id, by its own service model.

**`SCHEMA_VERSION` stays 9 and `OUTPUT_VERSION` stays 1.** No document changes
shape, nothing migrates, and no baseline is re-promoted.

- **`_complete` returns a record — the oldest contract debt in the project.**
  A plugin's one method returned `(text, Usage)`, decided when the only question
  asked of a provider was what it said and what it cost. Since then `_no_text`
  has been *inferring* why a judge produced nothing — "likely truncated", "a
  non-text reply or a refusal" — from a token count against a cap, with a
  docstring naming the pair as the reason it could do no better. All three
  providers return the answer as a field.

  So it returns a `Completion`: `text` and `usage` as before, plus `finish` in
  one vocabulary across every provider, `finish_raw` (the provider's own word,
  uninterpreted), `tools`, and what the provider said answered. The judge's
  sentence now **reads** the cause where there is one, and falls back to today's
  inference — word for word — where the provider says nothing, which is the
  ordinary case on a compatible endpoint. A model cut off at the cap and one
  that answered with a tool call are identical to a token count and need
  opposite fixes; that is the case the widening is for. (ADR 0004 §6)

  **The old pair is still accepted and always will be.** A third-party plugin
  written against the previous contract keeps working, unchanged: the union is
  permanent rather than a deprecation window, because the pair is the honest
  return for a provider with nothing else to report. Every test double in this
  repository still returns it, which is how that is proved.

- **`ToolsCalled`.** The first assertion about *how* an answer was produced
  rather than what it says. An agent that was supposed to look something up and
  answered from memory produces a well-formed answer that happens to be
  invented, and every other assertion was blind to it.

  ```python
  ToolsCalled(expected=["search", "cite"])
  ```

  It **errors** rather than failing when the target reports no trajectory — a
  plain function, or a provider that names none — because "called nothing" would
  be a finding nobody established. It errors too when a provider contradicts
  itself, ending the turn on a tool call and then naming none, which is what a
  compatible endpoint emitting the call as text looks like. The call *count*
  crosses a boundary on its own merit; the tool *names* are strings and need a
  `Disclosure`, exactly as a model name does.

- **A run records which model actually answered.** `model="claude-sonnet-5"` is
  an alias, and an alias is a promise about a family rather than the name of a
  system: the provider decides which snapshot behind it answers, and rolls that
  decision without anyone touching the suite, the prompt or a parameter. Runs
  recorded the alias on Monday and the alias on Friday, `compare()` reported the
  configuration unchanged, and a drop between the two sent a reviewer to the
  prompt.

  `target_config` and `judge_config` now also carry `resolved_model` and, where
  a provider names one, `fingerprint` — **observed** rather than sent, so an
  alias that rolled is a named delta and the *"this drop coincides with…"*
  sentence fires beside the regression. Bedrock Converse returns no model id at
  all, and the record says so rather than echoing the request back. A model that
  rolls part way through a run errors that case, on the rule ADR 0005 §8 already
  set for an endpoint that answers on two systems; a rotated `fingerprint` goes
  absent instead, because a backend build changing does not mean a different
  model answered. `fingerprint` is withheld under redaction, joining `base_url`:
  on a custom endpoint its value is written by a server nobody here reviews.
  (ADR 0005 §9)

  A comparison against a baseline promoted before this says *"not reported for
  the reference"*, not *"not sent"* — nobody sent a resolved model id, on either
  side — in both locales. The existing sentences were not reworded.

  **`SCHEMA_VERSION` stays 9 and `OUTPUT_VERSION` stays 1.** A new key inside
  `target_config.values` is the same event as a plugin declaring a parameter it
  did not declare before: no document changes shape, nothing migrates, and no
  baseline is re-promoted.

  The judge's configuration is now read after the last case as well as before
  the first, so a judge whose alias rolled stops being the one instrument change
  ADR 0005 §4 could not see.

- **A ninth example: `examples/llamaindex`.** A LlamaIndex query engine — a real
  `VectorStoreIndex`, retriever, prompt template and `RetrieverQueryEngine` —
  queried in process, with **retrieval left running** rather than frozen. That
  is the difference from `examples/rag`, which freezes the passages and measures
  the generator: here each case declares the page that *ought* to answer it, so
  `Faithfulness` goes red when an answer is fluent, correctly cited and
  synthesised from the wrong page.

  Keyless like `examples/langchain`, and for a harder reason. LlamaIndex's own
  fakes cannot do it: `MockLLM` hands the prompt back verbatim, which would make
  every grounded-fact check pass on the question rather than the answer, and
  `MockEmbedding` returns one constant vector for every text, which is not
  retrieval at all. So the example ships a `CustomLLM` keyed on the retrieved
  page and a deterministic local embedding, and says plainly in its README what
  each one does not test. The dependency is `llama-index-core`, not the
  `llama-index` meta-package — no PyTorch, no model download, no key.


## 0.7.2 — 2026-09-10

digline 0.7.2. Two more path-and-secrecy fixes, **found by our own adversarial
pass over the four that shipped in 0.7.1** rather than by a report: we went back
and tried to break them, and two of the four turned out to hold a door open
somewhere else. `digline-mcp` stays at 0.1.1 — both fixes are in the core, and
the server reads through the same store, which is now pinned by a test that says
so. `SCHEMA_VERSION` stays 9 and `OUTPUT_VERSION` stays 1: no baseline is
re-promoted.

Each was reproduced before it was fixed and is pinned by a test that fails on
0.7.1.

```sh
uv add --upgrade digline
```

- **Security:** an endpoint error can no longer carry the credential somebody
  put in the URL. 0.7.1 reduced `HttpTarget`'s `url` to its host in every
  message **digline** writes; it did not cover the messages `urllib` writes, and
  urllib quotes the authority back. `https://svc:sk-live-…@gateway/answer` — a
  URL with userinfo and no explicit port — raised
  `http.client.InvalidURL: nonnumeric port: 'sk-live-…@gateway'` as an
  **unhandled traceback**, to stderr and in CI to a build log. Two reasons it
  got through: `InvalidURL` is an `HTTPException` and not an `OSError`, so
  `preflight`'s handler never saw it, and `__call__` had no handler at all. Both
  call sites now catch it, and the exception's own text is kept — "connection
  refused" is the whole diagnosis on the ordinary bad day — with the literal
  userinfo of *this* URL removed from it, which is exact rather than a guess.
  The `endpoint_host(url) or url` fallback is gone: a value with no host is
  refused when the target is built, because that fallback made the reduction
  conditional on the URL being well formed, which is the case where a mistyped
  secret is most likely. `endpoint_host` itself now answers `None` for a value
  that is not a host — it used to return the whole lowercased string, so a
  malformed `base_url` was recorded as a "host" with spaces in it.
- **Security:** a run or baseline that **links out of the store** is refused.
  0.7.1 checked the run key like the other two path segments, which closed
  `?run=../../../../elsewhere`. That proved the *name* was one safe segment; it
  could not prove where the name led. A symlink placed inside `.digline/` under
  a perfectly legal key — `planted-key.json -> ../../../../outside/evil.json` —
  passed every check, and `digline view` answered **200** with the outside
  document rendered, `digline compare --run` reported on it, and the MCP
  `get_run` returned it to an agent. Reads now verify where the path resolves,
  for runs and for baselines, and `scan_runs` counts a linked-out file
  unreadable rather than opening it. A `.digline` that is *itself* a symlink — a
  store on another volume — still works: both sides are resolved, so what is
  refused is leaving the store, not reaching it by a link.
- **Documented:** two decisions the pass made explicit rather than changed. A
  **race** between the check and the read is out of scope, and `SECURITY.md` now
  says so and why — the capability it needs, writing to the repository mid-run,
  is already the capability to edit `suite.py`, which is code; and a run records
  the key its artifact *actually resolved to*, so a race that wins still leaves
  its name in the record. And **a suite inside the root is trusted**: the MCP
  perimeter decides which file the agent may name, not what that file may then
  do, and [ADR 0011 §8](https://digline.dev/product/adr/0011-the-mcp-server/)
  now says that in as many words, so the next person to confirm it reads a
  decision rather than a miss.


## 0.7.1 — 2026-09-10

digline 0.7.1 and digline-mcp 0.1.1: a security pass, and nothing else. Four
findings from a review of digline's own surfaces — the tool mishandling what it
is given, which is what `SECURITY.md` says is in scope. None of them is a
vulnerability in a model you evaluate, and none needs a baseline re-promoted:
`SCHEMA_VERSION` stays 9 and `OUTPUT_VERSION` stays 1.

Each was reproduced before it was fixed and is pinned by a test that fails on
the old code.

```sh
uv add --upgrade digline digline-mcp
```

- **Security:** `digline-mcp` now checks that the `suite` a tool names is a file
  inside `--root`. It did not, and `load_suite` executes a `.py`, so every tool
  was a way to run a file from anywhere on the disk — including the five
  annotated `read_only_hint=True`, which is the annotation a client reads to
  decide it may call one without asking a person first. The check sits in the
  one function all six tools cross, and it is stricter than the loader: it also
  refuses the dotted-module form, which resolves through `sys.path` and so names
  something the server cannot place inside the repository at all. The CLI still
  takes that form — a person's tool has no perimeter to keep.
  ([ADR 0011 §8](https://digline.dev/product/adr/0011-the-mcp-server/), amended)
- **Security:** a run key is validated like the other two path segments. The
  store checked the tenant and the suite and took the key verbatim, and the key
  is the one segment that arrives from outside — `--run`, and `?run=` in the
  view's query string. `digline view` would answer
  `/compare?run=../../../../elsewhere` with a 200 and render a run document from
  outside `.digline/`. Bounded in practice: only files ending `.json` that parse
  as a run, and a run addressed through the wrong tenant was already refused. It
  is now a 400.
- **Security:** a suite that is **data** reads inside the repository, or it is
  refused. `artifacts = ["/etc/passwd"]` in a file with no Python in it read the
  file and recorded its contents in every run; `cases` and a `[target]`'s
  `prompt_file` could do the same. The code boundary was closed when the format
  shipped — no `python =`, no `import =`, no dotted path to a callable — and it
  held; the read boundary had never been drawn. It is drawn at the **perimeter**,
  the repository, and not at the suite file's directory: `eval/suite.toml`
  naming `../prompts/system.md` is reading its own project, and that is the
  layout the format is for. Outside it is a load error naming the field and the
  resolved path. A `suite.py` is unaffected — it is code, and code can already
  open anything.
  ([ADR 0007 §6](https://digline.dev/product/adr/0007-the-declarative-suite-format/),
  amended)
- **Security:** `HttpTarget` names its endpoint by **host** in every message it
  raises, never by URL. `url = "https://user:sk-secret@gateway/answer"` is a URL
  people write, and "nothing answered at …" carried it whole — to stderr, and in
  CI to a build log, which is often read more widely than the repository is. The
  reduction is the one `base_url` has had since 0.2.0; a target that took its
  endpoint under another name had simply never been looked at. The URL itself is
  untouched: only what is *said* about it changes.
- **Changed:** artifacts are keyed relative to the **perimeter** rather than to
  the suite file's directory. The old rule fell back to the bare filename for
  anything outside that directory, so a file from elsewhere was recorded under
  the same name a file in the project would have had. For a suite at the root of
  its project — every example in this repository, and the ordinary layout — the
  keys are byte-identical and nothing moves. A suite kept in a subdirectory will
  see its artifacts renamed once, from `system.md` to `prompts/system.md`: it
  shows in the report's artifact section and **does not fail a run**, since an
  artifact change has never affected the exit code.
- **Fixed:** `digline-mcp`'s `run` executes the suite module **once**. It loaded
  the file twice — once for the suite, once for the module the target is read
  from — so a suite that opens a connection or seeds a fixture at import time
  did it twice for one tool call, and the second load silently replaced the
  first. Not a security finding and it changes no output; it is the same defect
  underneath the check above, which is why it travels with it. The five reading
  tools always loaded once and are unchanged.


## 0.7.0 — 2026-09-09

digline 0.7.0, the second release today and a different kind from the first.
0.6.0 added surfaces; this one is **correctness and reading**: one rule for
every limit digline compares, and a command that reads a run back at length.
No new packages — the three provider plugins stay at 0.3.0 and `digline-mcp`
at 0.1.0 — no breaking change, and **nothing on disk moves**: `SCHEMA_VERSION`
stays 9 and `OUTPUT_VERSION` stays 1, so no baseline needs re-promoting and no
pipeline sees a byte change.

```sh
uv add --upgrade digline
```

- **Changed:** one rule for every limit — **every limit in digline is compared
  at `FLOAT_PRECISION`, and every limit is inclusive**. Thresholds, tolerances,
  the measured noise floor, budgets and `min_agreement` all read the numbers as
  the document stores them, so an edge case is decidable from the six decimals
  in front of you instead of from the residue underneath. In practice one
  comparison moves: a delta exactly at its declared tolerance is now
  `unchanged` (and `same` under `diff`) even where the subtraction left a
  remainder in the last bits. On the `brief` fixtures the run ADR 0006 was
  written about is still `unchanged`; what changed is which control says so,
  and its `reason` and `within_noise` name the declared tolerance rather than
  the measured floor. `digline.core` now exports `meets`, `within`,
  `at_precision` and `STORAGE_STEP` so an assertion of your own compares the
  way the built-in ones do. The reasoning is
  [ADR 0009](https://digline.dev/product/adr/0009-boundary-semantics/).
- **Added:** `digline explain` — the run read back at length. The report
  compresses; this expands: what ran, what moved and by how much, inside or
  outside which measured interval, what was set aside, what could not be
  judged, which of the three configurations differed. It compares when the
  suite has a baseline and reads the run alone when it does not, with no mode
  flag — whether a reference exists is a fact the store already knows. It gates
  like `report` (`0` fine, `1` worse, `2` unjudged) and can never exit `1`
  without a reference. `--json` emits the **fact list the prose is rendered
  from** — typed facts with case and assertion references, no sentences — so a
  terminal and a pipeline cannot drift into two descriptions of one run.
  `--locale en|it`, defaulting to `en`, and there is no `--out`: a reading
  written to a file would have a recipient who did not choose English.
  **It states and never advises**, and quotes no judge — no fact has a field a
  reason fits in, which is what makes that boundary something no later edit can
  open by accident. For the judge's words, `digline report` is one command
  away. ([`docs/explain.md`](https://digline.dev/product/explain/),
  [ADR 0012](https://digline.dev/product/adr/0012-the-reading/))
- **Added:** `examples/operator/` — the reference assembly for the **operator
  loop**: a suite watched on a schedule by an agent that re-runs within a
  stopping rule declared in a file, tells a draw from a drift from a structural
  flip, and opens an issue in your own repository when the answer deserves a
  decision. The alert is a document in three layers — the wire's facts, a
  deterministic dossier, and a judgment marked as the operator's opinion and
  never as digline's verdict — and only the third needs a key. `promote` is
  absent from the whole assembly, as it is from the MCP surface. Two real
  alerts ship with it: the drift that escalates and the draw that deliberately
  does not, both rebuilt from their committed cycle on every build.
  ([The operator loop](https://digline.dev/product/operator/))
- **Fixed:** a cost or latency budget **over its cap now fails**. Both budgets
  answered their own question twice — the word in the reason came from
  `measured <= cap`, the pass/fail came from the rounded score — and near the
  cap the two disagreed: a run 0.000002 USD over a 1.000000 USD cap passed
  while its own reason read `(over budget)`. Fixed decision 4 says a declared
  ceiling fails the run, and the document was contradicting the gate. There is
  now one comparison, so the sentence and the status cannot drift apart. Only
  overruns within about 2e-6 of the cap change verdict; anything already
  failing still fails, and a cost exactly at the cap still passes at `0.5`.
- **Fixed:** a `min_agreement` no float could spell. With three samples,
  `min_agreement=0.666667` was accepted at construction — the guard checks
  reachability at `FLOAT_PRECISION` — and then failed two-of-three with "did
  not agree: 0.67 of them share the majority verdict, below the required 0.67",
  a sentence that refutes itself. There was no float spelling of "two of three"
  that worked, and the resulting `error` is an outcome that cannot be promoted
  to a baseline. The guard and the gate now compare at the same precision.
  **Write the fraction anyway** — `"2/3"` says what it means, and it is the
  form that cannot be spelled wrong. `docs/api.md` says so, and its own
  `Repeated` example no longer shows `0.67`, which raises.
- **Fixed:** an artifact is refused by field name at the door.
  `Suite(artifacts=["prompt.md"])` — a `str` where a `Path` is meant — is
  coerced on construction instead of failing later and elsewhere, inside
  `read_artifacts`, with an `AttributeError` naming neither the suite nor the
  field. It is the rule the TOML loader already applied, moved to the one place
  both forms pass through; what cannot be a path is now refused by name, so
  `artifacts = [3]` in a data suite stops loading quietly as the path `3`.

## 0.6.0 — 2026-09-09

digline 0.6.0, and **`digline-mcp` 0.1.0**, the first new package this
workspace has published since `digline-bedrock`. The three provider plugins
stay at 0.3.0: nothing in this release changes what a plugin has to do.

```sh
pip install digline          # 0.6.0
pip install digline-mcp      # 0.1.0, the MCP server
```

The release has two halves. One is about **an agent**: `AGENTS.md` writes down
the judgment digline deliberately does not encode, and `digline-mcp` turns it
into a surface — six tools, read and measurement only, with `promote` absent
rather than refused. The other is about **you**: `digline diff` answers *"should
I switch?"* where `compare` answers *"did it get worse?"*, `by_group` splits an
aggregate by class so an average stops hiding one that is broken, and `digline
report` finally renders a run that has no baseline instead of sending its first
reader to a dead end.

**One breaking change**, and it is an import: `from digline.cli.loader import
load_suite` is now `from digline.host import load_suite`. Only code that loads a
suite programmatically is affected — writing a suite, and every CLI command, is
unchanged. The bullet below says what else moved with it.

Nothing in the stored documents moved. `SCHEMA_VERSION` stays at **9** and
`OUTPUT_VERSION` stays at **1**: no run needs migrating, no baseline needs
re-promoting, and a run recorded at 0.4.0 diffs against one recorded today with
no ceremony.

- **Added:** `AGENTS.md`, the operating layer digline deliberately does not
  encode. The tool refuses what is unsafe and reports what it measured;
  everything between those two — whether a red run is a regression or a
  wobble, which run deserves to become the reference, when to stop re-running
  and start reading — is judgment, and it stays with a person. Eight numbered
  rules, the first of them that an agent never runs `promote` on its own
  initiative: a baseline is an approved reference, not the most recent
  measurement. The same content ships as a Claude Code skill in
  `.claude/skills/operating-digline/`, and `tests/test_agents.py` fails if the
  two drift apart.
- **Added:** `digline-mcp`, the [MCP](https://modelcontextprotocol.io) server. A
  coding agent can read a digline result and measure a new one, and **cannot
  promote a baseline** — not because promotion is refused, but because there is
  no such tool. A refusal is a conversation an agent can argue with, retry, or
  decide is a bug; an absence is not. `migrate`, `view` and `report` are absent
  too: upgrade maintenance somebody chose the moment for, and two documents
  written for a person. Six tools, read and measurement only.
  ([ADR 0011](docs/adr/0011-the-mcp-server.md), and
  [`docs/mcp.md`](docs/mcp.md))
- **Added:** `run` takes a mandatory `acknowledge_calls` that must equal the
  suite's planned calls to the target. Called without it, the tool refuses **and
  hands back the number** — so the first call is the probe, and an agent cannot
  spend a hundred model calls without having stated the number. `AGENTS.md` §7
  as a contract rather than as advice.
- **Added:** the tool descriptions carry the playbook — the stopping rule on
  `run`, "promote the median, never the first green" on `list_runs`, "within
  noise explains, it does not excuse" on `compare`. A tool description reaches
  the model deciding whether to call the tool, which makes it the one place
  `AGENTS.md` reaches an agent that never read it. A test checks both
  directions, so a rule reworded in the file cannot leave a tool quoting one the
  project has stopped making.
- **Added:** `exit_code` on `compare --json`. It is the number `AGENTS.md` §6
  calls the contract, computed by the same function the process exits with — it
  is a field because the MCP server returns this same object and has no process
  to exit, and it is on both surfaces so the two cannot answer differently.
  `output_version` stays at **1**: added keys leave a consumer working.
  `digline diff` has no such field and must not.
- **Added:** `digline.wire`, the machine surface. Every `--json` the CLI prints
  and every response the server returns is built by one function, so two front
  ends cannot drift into two answers. `digline.cli` re-exports `OUTPUT_VERSION`
  and the exit codes, so `from digline.cli import EXIT_OK` is unchanged.
- **Changed, and breaking for anyone who followed the guide:** the suite loader
  moved out of the CLI. `from digline.cli.loader import load_suite` is now
  `from digline.host import load_suite`. `digline.cli` was two layers wearing
  one name — the host that reads the clock, asks git and imports your suite, and
  the terminal that parses arguments and prints. A second front end needs the
  first and not the second. `git_commit`, `utc_now_iso`, `load_target` and
  `read_artifacts` moved with it. (ADR 0011 §7)
- **Added:** `digline diff <run1> <run2>` — what differs between two runs,
  neither of them a baseline. It answers *"should I switch?"* where `compare`
  answers *"did it get worse?"*: prompt A against prompt B, one model against
  another, temperature 0.3 against 0.7. It is a **report and never a verdict**,
  so it **always exits 0** on a completed report — a verdict exists only
  against an approved reference, and neither side of a diff was approved by
  anybody. A separate command rather than a flag on `compare`, because the exit
  code is the contract and nobody should have to remember which mode they are
  in. (ADR 0008, and [`docs/diff.md`](docs/diff.md))
- **Added:** the report is **symmetric**. Swapping the two arguments swaps the
  columns and nothing else — the same checks, the same counts with the two
  "favour" figures exchanged, the same intervals. It carries no "reference", no
  "before" and "after", no "regressed" and "improved": none of those words is
  true of two runs neither of which was approved. Both locales, and `--json
  counts` / `--json full` with a symmetric structure and **no `worse` field** —
  the absence is the point.
- **Added:** where both sides were sampled, each row shows the two recorded
  min–max intervals, and the headline will say *"2 of `<run>`'s advantages
  exceed both runs' observed intervals"* — the strongest sentence two
  unapproved runs support. Where the intervals overlap the row says the two are
  not distinguishable by that check, as **evidence beside the count and never
  an excuse**: a diff has no baseline, so no interval has the standing to
  overrule a difference. Where nothing was measured on both sides the sentence
  is not printed at all, rather than printed as "0 of …".
- **Changed:** `digline view`'s compare screen now chooses. Against the
  **baseline** — including the default — it is still the verdict document;
  against **any other run** it is the diff report. Since 0.4.0 that screen
  rendered the verdict for every pair, which put two candidates under a heading
  asking "Did it get worse?" beside a column called "Reference". ADR 0008
  closes it in the release that states the principle.
- **Refused:** a diff needs both runs measured the same way. Different rules
  (`config_hash`) and different judges (the ADR 0005 identity set) are refused
  by name, with the remedy in the message — including the case where one side
  recorded a judge and the other recorded none, which cannot be established as
  a match. Crossing a tenant or a suite name raises, as it does in `compare`.
  The **target is free**, and that freedom is the feature.
- **Unchanged:** `SCHEMA_VERSION` stays at 9 and `OUTPUT_VERSION` stays at 1.
  No run needs migrating, no baseline needs re-promoting: everything `diff`
  reads has been in the document since 0.4.0. Two runs recorded before this
  release diff against each other with no ceremony.
- **Added:** `by_group=True` on an aggregate — precision and accuracy **per
  class**, beside the whole-run figure and never instead of it. A `Case` gains
  an optional `group` (so `cases.json` and a TOML suite carry it with nothing
  to learn), and every aggregate that asks expands into one instance per group
  present in the cases, named `precision[group=refunds]`. Thresholds, tolerance
  and the ADR 0006 §7 noise floor are inherited and computed over the group's
  cases: the same machinery on a smaller set, no new semantics anywhere. An
  aggregate over the whole run is an average, and an average carries a class
  that is broken. (ADR 0010)
- **Refused:** there is no `Precision(group="x")`. You get every class or none
  — the class that degrades is the one you were not watching, so watching the
  three you already suspect is watching your own assumptions. In a TOML suite
  `group` on an aggregate is an unknown parameter, and the message points at
  `by_group`. No weighting, no group hierarchies, no cross-group comparison:
  each is a different question, and the last one is a real one, deferred rather
  than declined.
- **Changed:** `digline view`'s run grid sorts its measure columns — whole-run
  figure first, then that family's groups alphabetically — instead of taking
  them in the order they arrived. Arrival order was the newest run's order, so
  a group only older runs carried landed last and the columns rearranged
  themselves as runs came and went.
- **Changed:** the report explains a combination it can now show often — a
  measure **below its threshold beside an answer of "no"**. `compare` gates on
  movement, so a class that failed in the reference too is `unchanged` and the
  pipeline stays green. Both facts are true, and the sentence is printed under
  the figures rather than left for a reader to mistake for a defect.
- **Changed:** the `classifier` example ships its third act, and **four of its
  twelve figures are red**: precision and accuracy for `travel` and for
  `tools`, at the bars it always declared. Every run agrees and every one of
  those intervals is zero-width, so the noise floor itself certifies the
  failure is real. Nothing was tuned to make the demo green — that would be the
  vacuously green assertion shipped as the thing people copy first.
- **Unchanged:** a suite that sets `by_group` nowhere is byte for byte the
  suite it was — same `config_hash`, same identities, same run file. That
  covers baselines promoted **before** this release: an aggregate's identity is
  what `compare()` pairs on, so neither `by_group` nor `group` enters it. Set
  the flag and `config_hash` does move, because the suite now declares more
  gates: comparable, and not promotable until you re-promote deliberately.
  `SCHEMA_VERSION` stays at 9 — an expanded aggregate is an ordinary verdict
  under an ordinary name — and no plugin needs a release.
- **Fixed:** an aggregate whose ratio sits on a rounding boundary raised
  `ValueError` instead of producing a verdict — 14 of 21 cases against a
  threshold of `0.666667` crashed the run's gate. The status was decided from
  the unrounded ratio while `Verdict` re-derives it from the score it stores at
  six decimals, so the two disagreed by one part in a million. Both numbers are
  now rounded before the comparison, as the per-case and sampled paths already
  were.
- **Fixed:** `Case(expected="")` is refused. An empty expectation scored a
  perfect 1.0 against an empty output — `levenshtein`'s both-empty branch and
  an optional `expected` are each defensible, and together they were a check
  that could not fail. Refused where the case is declared, so both entrances
  are covered: Python and `cases.json`. `expected=None` stays legal; absence is
  not emptiness.
- **Added:** `digline --version` prints the version and exits 0, with no
  subcommand.
- **Fixed:** `digline.__version__` said `0.4.0` while the release was `0.5.0`.
  It is now read from the installed distribution's metadata, so it cannot drift
  again, and a new gate holds every remaining hand-written version claim to
  `pyproject.toml`: each one is either pinned or registered as a record of a
  version that has already shipped. Bump the release and any claim nobody
  updated fails by file and line. Two sentences that named a version for no
  reason were reworded without one — a claim that cannot go stale beats a gated
  one — and the image's minor tag, documented as `0.4` since 0.5.0 shipped, is
  correct again.
- **Fixed:** an example could cap digline below a release able to read its own
  committed baseline. `uv sync` in an example installs the newest release the
  cap admits, and `run_from_json` refuses any schema but its own, so the wrong
  ceiling makes the example unrunnable by the only person it is for — it had
  already happened once, four baselines deep. It held by luck until now: schema
  9 arrived in 0.4.0 and the caps admit 0.4.0. `tests/test_example_caps.py`
  makes it hold by construction, with the schema each release wrote pinned from
  its tag, and a release cannot be cut without recording what it writes.
- **Changed:** the official image is built and smoke-tested on every change to
  it, not only by the workflow that publishes it. Same context, same quickstart,
  no registry — the smoke moved into `docker/smoke.sh` so the two workflows run
  one script rather than two copies. The job is gated on the paths that decide
  what the image is, because the Dockerfile installs from PyPI and a change
  under `src/` cannot change the image being built.
- **Fixed:** `digline report` no longer refuses a run that has no baseline. It
  used to say *"run it, look at the result, then promote"* while being the only
  way to look — a dead end whose first victim is always someone on their first
  run. It now renders the run on its own: the same header, aggregates, files
  under test and configuration, with the cases grouped by what each verdict
  **is** — met its threshold, did not, could not be judged, set aside — instead
  of by what it did against a reference it does not have. Where the verdict
  goes, the document states the fact rather than answering a question it cannot
  ask: *"No reference to compare against."* Both locales.

  No flag decides this, the way `--redacted` is not what makes a report
  redacted: complete or redacted follows from the run, comparative or not
  follows from whether a reference exists. It **never exits 1** — "worse" is a
  relation and there is nothing to be worse than — but a case the suite could
  not judge still exits 2, because that is a fact about the harness rather than
  about a reference. `digline compare` is unchanged and still refuses: a
  comparison needs a reference, a document does not.
- **Changed:** a judge that returns no text now says so. An empty completion is
  a legal *output* — the assertions get to fail it, and that is unchanged — but
  it is not a legal *judgment*: there is nothing to parse, so nothing was
  judged. The verdict was already `error`; what was wrong was the sentence,
  which reported that the reply held no JSON object and sent whoever read it
  looking for malformed JSON that was not there. It now names the fact first
  and the likely cause second, marked as the inference it is: *"output hit the
  max_tokens cap (512 of 512) — likely truncated before the first character"*
  against *"output well under the cap (7 of 512) — a non-text reply or a
  refusal"*. The two need different actions, and raising the cap fixes only one
  of them.

  The check sees past an assistant **prefill**, which is what makes it work for
  the provider most likely to be judging: Anthropic's judge opens the reply with
  `{` so the model's output is an object either way, and a model that produced
  nothing arrived as `"{"` rather than as `""`. No plugin changed and none needs
  a release. The provider's own `finish_reason` is still not reported — it does
  not reach this layer — so the cause is stated as a reading of the token
  counts and never as the provider's word.

## 0.5.0 — 2026-09-08

digline 0.5.0, with digline-anthropic, digline-openai and digline-bedrock at
0.3.0. The plugins move because they now register themselves, and their
`digline>=` floor moves with them: a plugin at 0.3.0 needs a core that has
`Provider`, and claiming otherwise would resolve for somebody and then fail on
import.

- **Added:** a suite can be **TOML**. `digline run --suite eval/suite.toml`
  reads `[suite]`, an ordered `[[assertions]]` list with the check named by
  `type`, and a `[target]` that is either an HTTP endpoint or a provider. The
  extension chooses the format; there is no new flag. Cases are always a
  separate file, because a rule and a case change at different rhythms and a
  diff has to say which one moved. The loader builds the same objects the
  Python form builds — the same assertion identities and the same
  `config_hash` — so a suite can be ported between the two forms **without
  re-promoting its baseline**. (ADR 0007, and
  [`docs/declarative.md`](https://digline.dev/product/declarative/))
- **Added:** providers are found through **entry points**. Each plugin
  registers its name under `digline.providers`, and a suite names a judge or a
  target by coordinate — `judge = "anthropic/claude-haiku-4-5"`, which is the
  same `provider/model` identity a run already records. Resolution is by name
  and never by import: nothing shipped with digline imports a plugin, and
  resolving one provider does not load the others. Fixed decision 6 in
  `CLAUDE.md` has said this since the first commit; this is the release where
  it is true. (ADR 0007 §3)
- **Added:** `HttpTarget(body=…)`, a table shaped like the payload whose
  leaves name case fields — `question = "case.vars.question"`. One level of
  reference and no expressions, so the nesting, the arrays and the types of a
  real body survive. Additive: `request=` is untouched and remains what a body
  that has to be *computed* is written with. A reference that names no case
  field is refused when the suite loads, not once per case half way through a
  run.
- **Added:** `examples/quickstart-toml/` — the two-file suite against a local
  stub, with no Python in it and no key anywhere. The stub reports `config`
  like a real service, so the example shows the sentence that says the answer
  got worse while the model did not change.
- **Changed:** what a TOML suite cannot express, it refuses **by name**. An
  unknown key is a load error with the near miss when there is one — a
  silently dropped `treshold` would be a check running on the default that
  passes — and a custom judge, a computed body, a custom assertion or a
  `disclosure` gets a sentence saying which wall it is and where to go. A
  credential is refused outright: there is no `api_key` in this format, and
  each provider's SDK reads the key from the environment.
- **Note:** `disclosure` is not settable from a data file, deliberately. What
  it widens is what leaves a perimeter, and a suite that is data cannot widen
  it — in world 3 that is a security property, not a missing feature. A suite
  that genuinely needs to disclose more is a `suite.py`.
- **Added:** an **official container image**, `ghcr.io/digline/digline`, with
  the three plugins already in it. `docker run -v $PWD:/work
  ghcr.io/digline/digline:0.5.0 compare --suite eval/suite.py` runs the whole
  cycle with no Python installation, which is what a CI job that is not a
  Python job has to have. Tagged `:0.5.0`, `:0.5` and `:latest`, built on the
  release tag for `amd64` and `arm64`. The versions it carries are read out of
  `docker/Dockerfile` and gated against this workspace, so an image that lags a
  release fails the build instead of quietly running the version before it. It
  writes into the mounted repository, as the user who owns it and not as root —
  decision 2, checked on the filesystem before anything is pushed.
  ([`docker/README.md`](https://github.com/digline/digline/blob/main/docker/README.md))
- **Added:** a published security posture. `SECURITY.md` says that the
  supported version is the latest release and nothing else, points reports at
  GitHub's private vulnerability reporting, and states the scope: jailbreak and
  prompt injection **of the models under test** are what digline measures, not
  a vulnerability in digline. There is no bounty; there is a fast reply.
- **Note:** ADR 0008 records the **two-run report** — the decision, not the
  command. `digline diff` is not in this release; the ADR is here because the
  design was settled in this cycle and the format it fixes is the one the next
  release will implement. ([ADR 0008](https://digline.dev/product/adr/0008-the-two-run-report/))
- **Unchanged:** `SCHEMA_VERSION` stays at 9. No baseline needs re-promoting,
  no run needs migrating, and no example was re-recorded: nothing downstream
  can tell how a `Suite` was built, which is the point.

## 0.4.0 — 2026-09-02

digline 0.4.0. The plugins stay at 0.2.0: a sample is taken by the driver,
which calls a target the same way it always did, so nothing in this release
changes a protocol they implement.

- **Added:** a **noise floor**. A sampled check now records the raw per-sample
  scores and the interval they span, and `compare` reads the *baseline's*
  interval: a movement that lands inside it is `unchanged`, with
  `within_noise` on the delta and a sentence saying so in the report and in
  `--json`. Nothing rescues a flip, an interval of zero width is not a floor,
  and a baseline with no interval keeps the absolute rule. Two controls now
  exist and the reason says which one spoke: `tolerance` is *declared* — what a
  reviewer allows — and this one is *measured*. (ADR 0006)
- **Added:** aggregates get an interval of their own. Precision and accuracy are
  computed once per run and so have no samples, but the noise they need sizing
  against is real — one case in twenty-one moving and coming back was what
  prompted the ADR. The driver evaluates each aggregate once more per sample
  index and records those N values. No call to a target, no call to a judge, and
  the recorded score is unchanged. (ADR 0006 §7)
- **Added:** `digline run` announces the multiplied call count on stderr before
  the first call — `20 cases × 5 samples = 100 calls to the target`. Arithmetic
  over the declared suite; a suspended case is not counted, and a `Repeated` is
  named with its own factor. A money estimate is deferred to an ADR of its own:
  it would need a new optional method on every target. (ADR 0006 §8)
- **Changed:** `SCHEMA_VERSION` 8 → 9, additively. **No baseline needs
  re-promoting and no example was re-recorded**: the score is still the mean, so
  every stored number is the one this release computes, and the migration
  *derives* the new fields from the `metadata["scores"]` a sampled run already
  carried. A run at `samples=1` gains only the version number. Run
  `digline migrate` after upgrading — a stored run at schema 8 is skipped by a
  scan and refused by name until you do. Aggregate intervals are the one thing
  migration cannot supply; they arrive with your next promotion.
- **Added:** `examples/langchain/` — a LangChain pipeline evaluated in process:
  the target is a function that invokes the chain, so there is no server and no
  HTTP. The default path runs on LangChain's own `FakeListChatModel`, which is
  what CI runs — no key, no network — and `DIGLINE_LIVE=1` puts a real model
  under the chain and `AnthropicJudge` behind the rubric. Tested against
  langchain 1.3.18.
- **Added:** `ci.yml` builds the digline.dev site on every push — the site's own
  config and its own sync script, `mkdocs build --strict` — so a relative link
  in an example README, or an example with no entry in the site's nav, fails on
  the pull request instead of in `publish.yml`, where the build runs *after*
  PyPI. `tests/test_examples.py` checks the nav entry too, and names the example
  and the line to add. Both are on the pre-tag checklist in `RELEASING.md`.
- **Note on 0.3.0:** the tag `v0.3.0` is the release that is on PyPI and needs
  nothing done to it, but the examples at that commit do not resolve — they
  still pinned `digline<0.2` while their baselines had moved to schema 8, and
  `examples/langchain4j/` was missing the `[tool.pyright]` block that keeps
  pyright out of the virtualenv. Three commits on `main` after the tag fixed
  both, along with the README links that failed the site build. If you are
  reading the examples, read them from `main`, not from the tag.

## 0.3.0 — 2026-09-01

digline 0.3.0. The plugins stay at 0.2.0: nothing in this release changes a
protocol they implement, and `config` is still the optional property it was.

- **Added:** `HttpTarget(config_path=…)`. An application digline cannot import
  can now say which model answered and how it was set up, in the same answer
  that already carries the cost — so a run from a Java or Go service is as
  complete a document as one from a plugin, and `compare` names a model change
  instead of reporting the configuration as unchanged (ADR 0005 §8). Left out,
  the target declares nothing, exactly as before.
- **Added:** `examples/langchain4j/` — a Spring Boot + LangChain4j service with
  one endpoint, the suite that evaluates it, and the CI gate. The walkthrough
  for a team whose application is not Python.
- **Fixed:** every example's CI workflow promoted the fresh run and *then*
  compared it, which compares a run with itself and passes whatever happened.
  They now compare against the baseline committed in the repository and key on
  the exit code. `prompt-first` and `rag` are shipped red on purpose, so theirs
  assert exit 1 — a green run there means the example stopped demonstrating
  what its README claims.
- **Fixed:** the four shipped example baselines were still schema 7 and could
  not be read by 0.2.0 at all — `compare` against them raised. Migrated in
  place. The workflow bug above is why nobody noticed.
- **Changed:** `execute()` asks a target for its `config` twice, before the
  first case and after the last, and records the second answer. A target that
  declares statically gives the same answer both times; nothing a plugin does
  changes.

## 0.2.0 — 2026-08-31

digline 0.2.0, digline-anthropic 0.2.0, digline-openai 0.2.0,
digline-bedrock 0.2.0. **Run files move to schema 8**, so stored runs and
baselines must be migrated once: `digline migrate --suite <your suite>` rewrites
them in place, and until it is run, `compare`, `report` and `promote` refuse a
schema-7 document rather than half-reading it. Migration is not a re-promotion —
the baseline keeps its key, its date and its scores, gains an empty
configuration, and compares as `unknown` against it.

- **Added:** a run records the configuration of the system under test —
  provider, model, token cap, temperature, region, endpoint host, and the shape
  the answer was asked for — as `target_config`, and the judge's as
  `judge_config` (ADR 0005). Not folded into `config_hash`: two runs at two
  temperatures stay comparable, which is the experiment.
- **Added:** `compare` names what moved instead of hashing it. The report, the
  terminal and `--json` say `temperature 0.3 → 0.7`, and where a regression
  lands in the same comparison the report says *"this drop coincides with
  temperature 0.3 → 0.7"* beside it.
- **Added:** a suite that grades with several judges records **which**
  instruments graded, one identity per distinct `provider/model`. Replacing one
  of two judges is reported as one removed and one added — and reported more
  strongly than a target change, because the scale moved rather than the thing
  measured.
- **Changed:** the headline no longer uses "configuration" for two different
  things. The first sentence is now **"The suite is unchanged from the
  reference."** — the rules — and "configuration" is left to mean how the
  system under test was set up. Both locales, the terminal, and `view`'s
  `OLDER SUITE` marker. A pipeline matching on the sentence rather than on
  `--json` needs updating.
- **Changed:** a plugin's `Target` and `Judge` now answer a `config` property.
  It is **optional**, like `preflight` and `artifacts`: a plain-function target
  and a hand-written fake judge keep working and simply record nothing.
- **Compatibility:** `SCHEMA_VERSION` 7 → 8, additive. A baseline with no
  recorded configuration compares as `unknown` rather than as a change.
  `OUTPUT_VERSION` is unchanged: `--json` only gained keys.
- **Privacy:** a model id and a decoding parameter travel in clear; `base_url`
  is recorded as a host and is withheld under redaction, exactly as an artifact
  is (ADR 0003 §4). No `Disclosure` releases it. `prefill` is not recorded —
  it is prompt, so it belongs to `Suite.artifacts` — and neither are
  `additional_request_fields`, `extra_body` or `token_param`.

## digline-bedrock 0.1.0 — 2026-08-28

Tag `digline-bedrock-v0.1.0`; nothing in the core changed.

- **Added:** `BedrockTarget`, `BedrockJudge` and `BedrockClaimJudge`, on the
  Converse API. The region is resolved at construction, not at the first call,
  so a missing one fails before anything is paid for; `bedrock_pricing(region)`
  is the price list for the region you actually called, and `free()` covers a
  model billed by provisioned capacity.
- **Added:** ARNs are scrubbed out of error messages — an account id does not
  belong in a `Verdict.reason` that ends up in a committed baseline.
- **Added:** the cache-read convention was verified against the live API:
  Converse reports cached input **outside** `inputTokens`, so it is added, not
  subtracted, when the cost is computed.

## 0.1.3 — 2026-08-28

Tag `v0.1.3`: digline 0.1.3, digline-anthropic 0.1.1, digline-openai 0.1.0.

- **Added:** `JudgeBase` in `digline.targets` is public API. A plugin now ships
  a target *and* a judge — `Target` + `Judge` + `ClaimJudge` — instead of the
  core owning a judge it cannot call (ADR 0004).
- **Added:** `digline-openai`, with `OpenAITarget`, `OpenAIJudge` and
  `OpenAIClaimJudge`. `base_url` points them at any OpenAI-compatible provider,
  and the JSON parser is lenient: `response_format` is an optimisation, so a
  provider that refuses it falls back to reading the object out of the reply.
- **Added:** `AnthropicJudge` and `AnthropicClaimJudge` in `digline-anthropic`.
- **Added:** a judge counts what it spends — `calls`, `spent_usd`, `latency_ms`
  — so the budget covers the judging, not only the answer under test.
- **Docs:** "Requires Python 3.12+" in the README and on each plugin's install
  page, where it is read before the install fails instead of after.

## 0.1.2 — 2026-08-27

- **Fixed:** a rubric score landing exactly on the threshold inside `Repeated`
  produced `error` instead of `pass`.
- **Changed:** every assertion that asks a judge now sends one prompt shape —
  instruction first, `Output to judge:` last and once, exported as
  `JUDGE_OUTPUT_LABEL`. `Faithfulness` used a different label and a trailing
  line; judges that parsed the old shape need updating.
- **Added:** `HttpTarget`, for an application digline cannot import.

## 0.1.1 — 2026-08-27

- **Changed:** `digline --help` describes the command instead of printing the
  module's docstring.

## 0.1.0 — 2026-08-26

- First release: the offline cycle — write a suite, run, promote, compare,
  report — with the baseline committed in your own repository.
