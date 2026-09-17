# Releasing

One workflow, `.github/workflows/publish.yml`, fires on a tag. What follows is
the part that is not in the file, plus the things that have already gone wrong
once.

## Choosing the version

Before 1.0, the **minor** number moves when something a user relies on stops
working as it did: a public name removed or renamed in `digline.core`,
`digline.run`, `digline.host` or `digline.wire`, a CLI subcommand or option
removed or changed in meaning, an exit code changed, or a schema change that
needs `migrate` or a re-promote. 0.12.0 was a minor for this reason.

The **patch** number is for everything that leaves existing suites, scripts and
stored documents working unchanged: fixes, documentation, CI, and additions — a
new public name, subcommand or option — as 0.10.1, 0.12.1 and 0.13.3 did.

Check it by diffing the public names, the CLI and `SCHEMA_VERSION` between the
last tag and `main`, not from memory.

## Before the tag: the changelog

`CHANGELOG.md` is updated **on the commit the tag will point at**, not after.
One entry per occasion, headed by the date and by what the tag releases — a
workspace tag lists the versions it carries (`digline 0.1.3, digline-anthropic
0.1.1, digline-openai 0.1.0`), a named tag heads its own package.

This is the step to do first, because it is the only one the workflow cannot
catch up on. A tag is a commit, and a changelog written afterwards describes a
release from a commit that is not in it: the file on PyPI and on `digline.dev`
stays the one that says nothing about the version somebody just installed.
Fixing that costs a re-tag, which is repeatable but only until the `pypi` job
has run.

The entry is also the **GitHub Release**. On a `v*` tag the `github-release`
job in `publish.yml` runs after PyPI, cuts the entry for that version out of the
tag's `CHANGELOG.md` with `.github/changelog_entry.py`, and publishes it as the
notes under the title `digline <version>`. It refuses a version with no entry or
an empty one, so an entry whose heading does not read `## <version> — <date>`
fails there — after PyPI, and not worth a re-tag: publish the release by hand
from the entry with `gh release create <tag> --notes-file`. A re-run rewrites
the notes rather than failing on the release it already made. Named plugin tags
get no release from it.

## Before the tag: the gates

Run **exactly what CI runs**, from the repository root:

```sh
uv sync --all-packages
uv run pytest -q -m "not live"
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run python tools/home_capture.py --check
```

Copied from `.github/workflows/ci.yml` and held to it by
`tests/test_releasing.py`, which reads the `gates` job and fails if this block
falls behind it. That test exists because the block went stale the first time it
mattered: v0.2.0 was tagged after a check that ran `ruff` over
`src packages tests` instead of `.`, and CI failed on the tag with a code sample
in `docs/api.md` — **`ruff format` formats the Python blocks inside a Markdown
file**, and no narrower path list ever sees them.

Two of these are easy to think you can skip, and both were the same mistake:

- **`.` and not a list of directories.** `docs/` and `examples/` are checked
  too, and they are where a sample rots.
- **`uv`, not the ambient interpreter.** `uv sync` is what updates `uv.lock`
  after a version bump; a lock still naming the previous version is a lock that
  describes a release that does not exist. Running `ruff` and `pytest` straight
  from a system Python never touches it.

## Before the tag: the home capture

`docs/assets/home/home.json` is what the home of digline.dev shows: the
quickstart and a one-line prompt regression, **run** by
`tools/home_capture.py`, with every command's stdout, stderr and exit code as
they came out. `sync-docs.sh` carries it to the site with the rest of `docs/`.

The file records the `digline_version` that produced it, and the last gate above
fails when that is not the **newest dated release in `CHANGELOG.md`** — the first
`## X.Y.Z — YYYY-MM-DD` heading, which is exactly what digline.dev's home hook
reads. Not `pyproject.toml`: the home is a public claim about what is released,
so it never shows the output of an untagged version, and a version set on a
branch ahead of its tag (`## X.Y.Z — unreleased`) keeps the last release's
capture until the tag PR. So this is a step of that PR, required rather than
remembered, and in this order:

1. Date the heading: `## X.Y.Z — unreleased` becomes `## X.Y.Z — YYYY-MM-DD`.
2. `uv run python tools/home_capture.py --check` now fails, naming the old
   capture. That failure is the step working.
3. Regenerate and stage the file, on the same branch, before the tag:

```sh
uv sync --all-packages
uv run python tools/home_capture.py
git add docs/assets/home/home.json
```

The script fails on its own if the regression it captures stops being red, or
if no case comes back worse — a capture that went green would put a claim on
the home the tool did not make. Read the diff of the file before committing it:
the run keys and the date always move, anything else moving is news.

## Before the tag: the alert list

One question, asked of the Code scanning tab: **new alerts since the last tag?**

```sh
gh api repos/digline/digline/code-scanning/alerts --paginate \
  -q '.[] | select(.state == "open")
      | "\(.created_at[:10])  \(.tool.name)  \(.rule.id)  \(.most_recent_instance.location.path // "-")"'
```

The list is meant to be short enough to read in one breath, and it is short on
purpose: every alert that is not going to be acted on has been dismissed *with
its reason written down*, so what stays open is what somebody still owes an
answer for. Dismissing to make a number go down is how the list stops being
worth reading; the reason is the part that keeps it honest, and it is the same
candour the security page prints.

An entry with a date after the last tag is the whole point of the step: judge
it, then either fix it before tagging or dismiss it with a sentence. An entry
older than the tag has already been judged — leave it.

## Before the tag: the site

The gates above check this repository. This one checks the **other** one, and it
is here because skipping it is what v0.3.0 cost.

```sh
git clone https://github.com/digline/digline.dev ../digline.dev   # once
cd ../digline.dev && uv sync
make preview DIGLINE=../digline
```

**`make preview`, and not `tools/sync-docs.sh` followed by
`uv run mkdocs build --strict`.** That is the target the `docs` job calls on a
pull request — called rather than copied, so this block cannot drift from the
gate. The two-step form this file carried until 0.13.2 is worse than nothing:
`tools/sync-docs.sh` refuses a checkout that is dirty or **ahead of
`origin/main`**, which a release branch always is, and the build run after it
renders whatever `docs/product/` already held and says `Documentation built`.
The refusal is an exit code two lines above, and nothing downstream reads it.
On this release it went green three times while `docs/product/` did not carry
the new changelog entry at all; the `docs` job, on the same tree, failed on the
first try — a relative link in that entry, `](tools/home_capture.py)`, which
resolves on GitHub and is not a page on the site. A check that can pass having
looked at nothing is the vacuously green assertion decision 3 of `CLAUDE.md`
forbids, and it had been sitting in this file.

digline.dev builds the site from two repositories: its own pages, and the
documentation here — `docs/`, `CHANGELOG.md`, `ROADMAP.md`, and one page per
`examples/*/README.md`. It builds `--strict`, so **two things that are correct
on GitHub fail there**:

- **a relative link in an example README.** `](report.html)` resolves in the
  directory and not on the site, where the target was never copied. The four
  oldest examples carry no links at all, which is why the rule went years
  without being written down.
- **a page with no entry in the site's `nav`.** Adding `examples/<name>/` here
  needs one line in `digline.dev`'s `mkdocs.yml`, under `- Examples:`:
  `- <label>: product/examples/<name>.md`. Adding `docs/adr/<name>.md` needs
  the same line under `- Decisions:`, as `product/adr/<name>.md`.

**A new page costs three lines there, not one**, and they are in three files:

| Where | What | Fails as |
|---|---|---|
| `mkdocs.yml`, `nav:` | the entry | a `--strict` warning, so a failed build |
| `tools/hooks/seo.py`, `PRODUCT` | the title and the `<meta name="description">` | a `PluginError` naming the page |
| `tools/hooks/llms.py`, `DESCRIPTIONS` | what the page answers, for llms.txt | a `PluginError` naming the page |

The last two are for pages under `product/` — everything copied out of this
repository. A page written in `digline.dev` itself carries its description in
its own front matter instead, and the same gate says so.

`PRODUCT` is the newest of the three and the one most likely to be forgotten,
because until it was gated a missing entry was silent: the hook fell back to the
page's first paragraph and shipped it to Google as the description. That
fallback is a net, not a decision.

All of it is gated — by the `docs` job in `ci.yml`, which runs this same build
on every push and on every pull request, calling the site's own targets rather
than a copy of them: `make preview` on a pull request, because the sync refuses
a checkout ahead of `origin/main` and a pull request is always at least one
commit ahead, and the ordinary build everywhere else. And, for the nav entry
specifically, by `tests/test_examples.py`, `tests/test_adr.py` and
`tests/test_docs_pages.py`, which name the page and the line to add.
So this block should already be green by the time you reach it. Run it anyway:
the job checks `digline.dev`'s **default branch**, and what the release will
actually build against is whatever that branch holds at dispatch time.

### Queued for the next site push

The three-line rule above collects a batch per release, and the pages are held
back deliberately: `digline.dev` is on its default branch and this documentation
is not merged yet, so adding the entries early would fail the site build on
pages that do not exist. They land together.

**Nothing is queued as of 0.13.3.** Read off `digline.dev`'s `origin/main`
rather than remembered — `rejudge`, `log` and `register`, and ADRs 0014, 0015,
0016 and 0024 each carry all three entries there: the `nav` line, `PRODUCT` in
`tools/hooks/seo.py`, `DESCRIPTIONS` in `tools/hooks/llms.py`. The batch this
section used to list went over with the pages themselves, and
`tests/test_docs_pages.py` and `tests/test_adr.py` are green here, which is what
an empty queue looks like from this side.

The next page added goes in this list with its destination, and comes out of it
when the site has it: **three lines each**, per the table above, in three files.
Check it the way the sentence above was checked — `git show origin/main:<file>`
in `digline.dev`, not from memory, because this list is exactly the kind that
rots quietly once it stops being true.

**A failure here is not a re-tag.** The site job is the last step of
`publish.yml` and runs *after* PyPI, so a docs defect discovered at that point
leaves the packages correct and the site describing the version before them.
Fix it on `main`, then re-run the failed `site` job. v0.3.0 went out that way.

CI also runs the gates on **3.12 and 3.13**. One locally is enough before a
tag — the second is what CI is for — but a failure on 3.13 alone is a real
failure, not a runner quirk.

## The two tag shapes

| Tag | Means |
|---|---|
| `v0.1.3` | a **workspace** release, led by the core |
| `digline-bedrock-v0.1.0` | a **single package**, on its own version line |
| `pytest-digline-v0.1.1` | the same shape — the package need not be named `digline-*` |

The named shape is **`<package>-v<version>`**, and the workflow's trigger has to
say so. It used to say `digline-*-v*`, which was true for as long as every
package was called `digline-something`. `pytest-digline` inverts the prefix —
that is the convention a pytest plugin is discovered by — so its first tag,
pushed on 2026-09-10, matched **neither** pattern and `publish.yml` never ran.
A release that silently does nothing is worse than one that fails: there is no
red to look at, no job to open, and the first sign is a package that never
appears on the index. Nothing was spent; the pattern became `*-v[0-9]*` and the
tag was deleted and re-pushed.

**Check the run started.** After pushing any tag, confirm `publish` is actually
queued before walking away — `gh run list --limit 3`. It is the one failure in
this file that produces no signal of its own.

Version numbers are per package and they collide: `digline-bedrock` at 0.1.0 has
no `v0.1.0` left to take, because that tag released the core in its own first
version. The named shape exists for exactly that, and it is checked more
strictly — `digline-bedrock-v0.1.0` verifies that *that* package is at that
version, where `v0.1.3` only asks that somebody in the workspace is.

Tags are annotated, with the released versions as the subject:

```sh
git tag -a v0.1.3 -m "digline 0.1.3, digline-anthropic 0.1.1, digline-openai 0.1.0"
git tag -a digline-bedrock-v0.1.0 -m "digline-bedrock 0.1.0"
git tag -a pytest-digline-v0.1.1 -m "pytest-digline 0.1.1"
git push origin <tag>
```

**The tag names the occasion; it does not decide the content.** Every package is
built on every tag, and `select_unpublished.py` uploads only what the index does
not already have. So a plugin-only tag publishes only that plugin — because
everything else is already released, not because the tag said so.

## Before the first tag of a *new* package

**Configure its pending publisher on TestPyPI *and* on PyPI.** Both, before
pushing the tag.

A package that has never been released has nothing for trusted publishing to
attach to, and the failure comes at the *end* — after the build, after the
checks, after TestPyPI — with a version number spent on one index and not the
other. This is not something the workflow can check for you: it is a setting in
an account.

**And wire it into `publish.yml` in the same pass.** A pending publisher with no
job to claim it is the same failure one step later: the tag builds nothing, and
nobody notices until somebody tries to install the package.

### `digline-mcp` was the first package this section was ever about

It was written after `digline-bedrock` and had never been exercised — every
release until then was a version bump of packages that already existed on both
indexes, so the section read as advice for a hypothetical. **v0.6.0 was the tag
that exercised it**, and it is history now rather than a plan. What was done
before that tag, in this order:

1. pending publisher on **TestPyPI**, for `digline-mcp`;
2. pending publisher on **PyPI**, for `digline-mcp`;
3. the **two hardcoded lists** in `publish.yml` updated. Discovery, `uv build
   --all-packages`, `select_unpublished.py` and both upload steps were
   glob-driven and picked a new package up on their own — the wiring that was
   *not* automatic was the post-publish check that installs from the index:
   the `pip install …` line and the `import …` line beside it. A package
   missing from those two lines was published and never verified, which is the
   failure that looks like success;
4. only then the tag.

The order matters and the first three are not reversible by a re-run: a spent
version number stays spent.

**Step 3 no longer exists, since 0.7.2.** `.github/dist_manifest.py` reads the
roster out of `dist/` — the wheels this tag just built — and writes the three
shapes the verification steps need: exact pins for the real index, unversioned
names for TestPyPI, and module names for the import check, which
`.github/verify_imports.sh` then imports one at a time. There is no list to
edit, so there is no list to forget. Both scripts refuse to run on an empty
roster rather than pass having checked nothing.

So the standing procedure for the next new package is **the two pending
publishers, then the tag**. Those are still settings in an account and still
not reversible by a re-run, and they remain the part of this section that no
amount of scripting can check for you.

## The one secret

`DIGLINE_DEV_DISPATCH_TOKEN`, a repository secret on `digline/digline`.

| | |
|---|---|
| What | fine-grained PAT, **Contents: read and write on `digline/digline.dev` only** — nothing else, no other repository |
| Why | the `site` job posts a `repository_dispatch` to the site's repository, and a workflow's own `github.token` is scoped to *this* one |
| Where | Settings → Secrets and variables → Actions, and it is read on the step, not the job |
| Created | 2026-08-31 |
| Expires | **2027-09-01**, the 366-day maximum. They always expire: record the date here on every rotation — a year from now this row is the only warning you get |

It fails at the **end** of a release, after PyPI, and a failure there needs no
re-tag: the packages are published, and only the site is behind. Add or renew
the secret and re-run the failed job.

**A re-run replays the workflow file from the tag's commit, not from `main`.**
So a fix pushed to `main` does not reach a re-run of an older release — for that
one, either the secret has to match the name *that* commit expects, or the
dispatch is sent by hand:

```sh
gh api repos/digline/digline.dev/dispatches --method POST \
  -f event_type=digline-release -f 'client_payload[ref]'=v0.2.0
```

**That shape is for a release, and only for one.** The site checks out
`client_payload.ref`, so the dispatch above rebuilds *the tag* — which is the
whole point when the tag is what went to PyPI and the site has to describe it.

To rebuild outside a release — docs edited on `main` after the tag, which is
the ordinary case — use `workflow_dispatch` instead:

```sh
gh workflow run docs.yml --repo digline/digline.dev
```

It carries no ref, and a checkout with no ref takes the default branch. Reach
for the release shape here and the build renders the tree **as the tag left
it**, then reports success: every edit made since is simply absent, and nothing
in the run says so. A `v0.4.0` rebuild sent an hour after the release would have
served the ROADMAP the tag carried, not the one on `main`.

## What CI proves about each index

Both indexes are now checked the same way: upload, then **install what was just
uploaded and run the quickstart against it**. The two steps are twins on purpose
— if one grows a check, the other should.

| Job | Index | Proves |
|---|---|---|
| `testpypi` | TestPyPI | the wheels are installable and the quickstart runs, *before* anything irreversible |
| `pypi` | PyPI | the index a user actually installs from serves this tag's versions |

The `pypi` half was missing until **0.7.1**. Every release before it verified
TestPyPI and took PyPI on trust, which is the wrong way round: TestPyPI is the
rehearsal and PyPI is the one somebody types. Two details in that step are load-
bearing and neither is obvious:

- **`--no-cache-dir`.** Minutes after the 0.7.1 upload, a warm pip cache still
  answered `No matching distribution found for digline==0.7.1` while PyPI's JSON
  API already served it. The cache is per runner and usually cold, so this is
  insurance against the day it is not.
- **Exact pins, read from `dist/`.** Without them a lagging index resolves the
  *previous* release, every command below succeeds, and the step goes green
  having proved nothing. That is not hypothetical: on the 0.7.1 release run the
  examples job did exactly this, and six of eight legs installed 0.7.0 and
  passed. The step also refuses to run when the glob matches no wheel, because a
  check that can pass by finding nothing is the vacuously green assertion
  `CLAUDE.md` decision 3 forbids.

`select_unpublished.py` copies rather than moves, which is what leaves `dist/`
whole for that step to read.

## The index race

**An upload returning 200 is not the index serving the file**, and the gap
between the two is a race our own ordering guarantees. `publish` uploads, and
the consumers start the moment it completes: `ci.yml` on
`workflow_run: [publish] types: [completed]`, `docker-publish.yml` beside it on
the same `v*` tag. So the first consumer to run is structurally early, and
whether it goes red used to be decided by scheduling rather than by anything in
the tree.

It has been paid for five times — 0.7.1's warm pip cache, 0.8.0's `rag` and
`llamaindex` legs, 0.11.0's classifier lock regen, v0.13.0's `docker-publish`,
and the follow-on `ci` after `digline-openai-v0.5.0`.

`.github/await_index.py` is the answer, and **it is a wait-and-verify, not a
retry**. That distinction is the whole design and it is worth keeping: a bare
retry cannot tell *not yet propagated* from *genuinely missing* — a typo'd pin,
a version that never uploaded, a project that does not exist. It burns its
budget and fails the same way for both, so a real defect becomes a slow flake
and the red says nothing about which it was. The wait asks the one question
that separates them — *is this exact file served?* — and answers in two shapes:

| The red says | It means |
|---|---|
| `/simple/digline/ is served and lists 41 file version(s), none at 0.13.0` | propagation, or a version that was never uploaded |
| `/simple/digline-mcp/ answered 404 — a project that has never been published, or a name that is misspelled` | a package **new to the index**, or a misspelling |

The second shape is there because a brand-new project has no page at all, so an
edge can hold a cached 404 for the project URL — a longer-lived thing than a
page that merely has to gain a line.

**It runs in each consuming job, not only in the one that uploaded.** One
runner's view of the index does not prove another's: on v0.13.0 the `pypi` job
verified its pins and the image build, ~30s later and inside a container's own
network namespace, was still told `digline==0.13.0` did not exist. A wait that
ran only at the publisher would have passed there and changed nothing.

| Job | Waits for | Deadline |
|---|---|---|
| `publish.yml` → `pypi` | every pin in `dist/` | 10 min |
| `docker-publish.yml` → `smoke` | the four pins in `docker/Dockerfile` | 30 min — it waits on a *person* approving `pypi` |
| `ci.yml` → `image` | the same four pins | 4 min |
| `ci.yml` → `examples-from-pypi` | this workspace's core version | 4 min |

**What still is not covered, stated rather than assumed.** The `testpypi` job
installs unversioned names, on purpose — TestPyPI resolves against a different
set of uploads — so nothing holds it to a version and a lagging index there can
still resolve an older one. The five examples carrying a `uv.lock` pin exact
versions that legitimately lag a release until the locks are regenerated, and
the wait says nothing about what any individual lock resolves to. The ten
`examples/*/.github/workflows/check.yml` are inert inside this monorepo and are
not reached by a release at all. `java-example.yml` installs no Python package
and is not a consumer.

And the part no amount of waiting closes: **PyPI's edges converge on their own
schedule.** The wait narrows the window to whatever the consuming runner can
see; it cannot make one edge speak for another.


## After the green, before the announcement: the delta-pass

**A release that adds surface gets an adversarial pass over that surface before
anyone is told about it.** Not the whole threat model again — the *delta*: what
this release made reachable that was not reachable before, and what a hostile
value in each new field would do at each boundary it can cross.

The rule is here because 0.8.0 earned it in hours. That release added three
surfaces, and the pass over them found that `resolved_model` travelled in clear
out of a redacted run from a compatible endpoint, beside a `base_url` withheld
for describing the same thing. It was not an implementation slip — ADR 0005 §9
had *decided* it that morning, applying two different tests to two fields
arriving in the same reply — which is exactly the class of thing that survives
code review and dies under an adversarial read. It shipped as 0.8.1 the same
day, before the announcement round, which is the whole value of the ordering:
after the announcement it would have been an advisory instead of a changelog
line.

Three questions per new field, and they are the ones that worked:

- **Where does it cross?** The stored document, `--json` and MCP, the HTML
  report, the terminal. A field is only as safe as its loosest boundary.
- **Who wrote the value?** A first-party provider, or software the customer
  runs and nobody here reviews. `base_url` being set is what tells them apart,
  and it is a fact the code already holds.
- **What does a hostile value do?** ANSI escapes at a terminal, markup in the
  report, a forged newline in a sentence a reader trusts. `!r` and `escape()`
  are the two answers; check that one of them is actually in the path.

Reproduce on the artifact that travels — `run_to_json(redact(run))`, not the
in-memory object — and write the regression test so it fails against the
release you just cut. A pass that finds nothing is worth recording too: 0.8.0's
`finish_raw` and `ToolsCalled` metadata both came back clean, and saying so
stops the next reader re-auditing them.

**When a finding earns a GHSA, the session creates the draft.** `SECURITY.md`
draws the line between an advisory and a changelog entry; this says who does
which half of the advisory. The session posts it to
`repos/digline/digline/security-advisories` with the text the gate approved —
summary, CWE, affected and patched ranges, the CVSS vector, and the body
verbatim. **Publication stays a person's click** in the Security tab, for the
reason the reviewer gate exists: an advisory is a public statement in the
project's name, and the last step before it is public is somebody deciding to
make it so.

Two things the API will teach you the hard way otherwise. It **refuses
`severity` and `cvss_vector_string` together** — send the vector, which is the
richer fact, and let GitHub derive the class from it; then check the derived
severity is the one the gate approved rather than assuming, because a vector
that scores differently is a discrepancy to report and not to quietly accept.
And a draft created this way carries no CVE: requesting one is part of the same
click. If the token lacks `repository_advisories: write`, the fallback is the
old one — hand the fields over for manual entry, which is a slower path to the
same draft and no less correct.

0.12.1's is the worked example: `GHSA-g25g-q7j3-jcgp`, drafted from the
delta-pass over 0.12.0, `low` derived from a vector scoring 2.5.

## After the tag: what to watch, and what to ignore

Three of these look like problems and are not, and the fourth is the one check
worth doing by hand.

**A red `ci` on the release commit is expected.** `docker/Dockerfile` pins
`digline==<the version being released>`, and the push-triggered `ci` fires
*before* the `pypi` job has uploaded it. So the image job fails, every time, on
the commit the tag points at. It self-heals: the `workflow_run` `ci` that
follows `publish` rebuilds it green. On 0.7.1 the failing build ran at 06:25:07
and the upload landed at 06:27:21. **Do not chase it, and do not re-tag for
it** — check that the follow-on run is green instead.

What changed is *which* red it is. It used to be `No matching distribution
found` from `pip`, which is the same sentence a typo'd pin produces. Now the
`Wait for every pinned version to be served to this runner` step fails first
and names the version and the shape of the absence, so the expected red and a
real defect no longer read alike. **If that step reports a project that has
never been published, that is not this race** — read it.

**A red `docker-publish` on the release tag no longer means "re-run it".** It
used to: the job's own wait asked only about `digline`, from the runner, and
the build then installed four versions from inside a container. Re-running was
how it got past a plugin the index had not caught up on. The job now waits for
all four pins, so a red there is a failure to read rather than a button to
press again. Re-run it only after reading which version it names.

**The nine example legs need a dispatch after the lock regen.** Two things
combine. `examples-from-pypi` is gated `if: github.event_name != 'push' &&
!= 'pull_request'`, so pushing the lock commit does not run it; and the
`workflow_run` run that follows the tag checks out **the tag's commit**, which by
construction predates the lock regen. So that run's legs read the *old* version
and that is not a failure. On 0.8.0 two legs went red in that run for a second
reason worth knowing apart from the first: not a stale lock but a **propagation
race** — `rag` and `llamaindex` burned their six retries between 10:26:29 and
10:27:29 while the index still served `<=0.7.2`, and the other seven won the
same race by being scheduled seconds later. That second reason is now waited
out rather than retried past (see *The index race*), and the legs fail naming
the version if it genuinely never arrives. Same verdict either way: the
dispatch against `main` is the run that counts. Run it by hand against `main` once the locks are in:

```sh
gh workflow run ci.yml --ref main
```

Five examples carry a `uv.lock` pinning the exact version — `classifier`,
`langchain`, `llamaindex`, `prompt-first`, `rag` — and the other four resolve at
install time. Regenerate the five with `uv lock --upgrade-package digline` in
each, commit, then dispatch. Three of them — `langchain`, `llamaindex`,
`prompt-first` — pin `digline-anthropic` as well, so the release that moves a
plugin needs `--upgrade-package digline-anthropic` beside it or those locks come
back naming a plugin version that is no longer current. *(Worth trying next release: regenerate the locks **before** the tag.
They cannot resolve a version PyPI does not have yet, so it probably has to stay
a post-tag commit — but if a lock can be written against the version about to
ship, the dispatch stops being necessary.)*

**Whether the reviewer gate actually held is not visible in the run's green.**
A fast approval passes through `waiting` in seconds — on 0.7.1 it was **16** —
so any poll can miss it entirely, and a gate that fails open looks exactly the
same from the outside. That matters because it *has* failed open once, on
v0.5.0. The retrospective record is the one to read:

```sh
gh api repos/digline/digline/actions/runs/<run-id>/approvals
```

Expect `state: approved`, the approver's login, and `can_admins_bypass: false`
on the `pypi` environment. `pending_deployments` only answers while the run is
still sitting there; `approvals` answers afterwards, which is when you are
asking.


## Two failures already paid for

**A plugin wheel cannot resolve the core from the index on the tag that releases
them together.** `digline-anthropic` requires `digline>=0.1.3`, which is not
published yet at the moment the build job checks that each wheel installs on its
own. Hence `--find-links dist/` on those installs: the core is resolved from the
wheel built beside it, while the index stays reachable for `anthropic`, `openai`
and `boto3`.

**A loop that installs every wheel leaves only the last one installed.** "The
last one imports" is not the check anybody meant to write, so each plugin is
imported in a venv of its own, with the core wheel passed in explicitly.

## What is irreversible, and what is not

A version on an index can never be reused. That is why the `pypi` job sits
behind a required reviewer, and why a mistyped tag is the one mistake here with
no repair — the check that refuses a tag naming no package exists for that
alone.

Everything before PyPI is repeatable. A tag can be deleted and re-pushed on a
fixed commit: the run starts over, and whatever reached TestPyPI in the meantime
is skipped rather than re-uploaded.

`digline.dev` is rebuilt only on a `v*` tag. The site describes what the core
says — the quickstart, the format, `docs/` — and a plugin release changes none
of it.
