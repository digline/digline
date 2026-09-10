# Releasing

One workflow, `.github/workflows/publish.yml`, fires on a tag. What follows is
the part that is not in the file, plus the things that have already gone wrong
once.

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

## Before the tag: the gates

Run **exactly what CI runs**, from the repository root:

```sh
uv sync --all-packages
uv run pytest -q -m "not live"
uv run ruff format --check .
uv run ruff check .
uv run pyright
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

## Before the tag: the site

The gates above check this repository. This one checks the **other** one, and it
is here because skipping it is what v0.3.0 cost.

```sh
git clone https://github.com/digline/digline.dev ../digline.dev   # once
cd ../digline.dev && uv sync
tools/sync-docs.sh ../digline
uv run mkdocs build --strict
```

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
on every push, and, for the nav entry specifically, by `tests/test_examples.py`,
`tests/test_adr.py` and `tests/test_docs_pages.py`, which name the page and the
line to add.
So this block should already be green by the time you reach it. Run it anyway:
the job checks `digline.dev`'s **default branch**, and what the release will
actually build against is whatever that branch holds at dispatch time.

### Queued for the next site push

The three-line rule above has a first real batch, and the pages are held back
deliberately: `digline.dev` is on its default branch and this documentation is
not merged yet, so adding the entries early would fail the site build on pages
that do not exist. They land together. Three, with this branch on the pile —

- `docs/diff.md` → `product/diff.md`, under `- Reference:`;
- `docs/adr/0010-per-group-aggregates.md` → under `- Decisions:`;
- `docs/adr/0011-the-mcp-server.md` → under `- Decisions:`;

— and `tests/test_docs_pages.py` and `tests/test_adr.py` are red here for
exactly that reason, which is the gate keeping the two repositories in step
rather than a defect. Three lines each, per the table above.

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

Version numbers are per package and they collide: `digline-bedrock` at 0.1.0 has
no `v0.1.0` left to take, because that tag released the core in its own first
version. The named shape exists for exactly that, and it is checked more
strictly — `digline-bedrock-v0.1.0` verifies that *that* package is at that
version, where `v0.1.3` only asks that somebody in the workspace is.

Tags are annotated, with the released versions as the subject:

```sh
git tag -a v0.1.3 -m "digline 0.1.3, digline-anthropic 0.1.1, digline-openai 0.1.0"
git tag -a digline-bedrock-v0.1.0 -m "digline-bedrock 0.1.0"
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
   --all-packages`, `select_unpublished.py` and both upload steps are
   glob-driven and pick a new package up on their own — the wiring that is
   *not* automatic is the post-publish check that installs from the index:
   `pip install …` line and the `import …` line beside it. A package missing
   from those two lines is published and never verified, which is the failure
   that looks like success;
4. only then the tag.

The order matters and the first three are not reversible by a re-run: a spent
version number stays spent.

Read the four as the standing procedure, not as a record: the next package to
be published from this workspace needs all of it again, and only step 3 leaves
a trace in the repository that anyone would notice was missing.

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


## After the tag: what to watch, and what to ignore

Three of these look like problems and are not, and the fourth is the one check
worth doing by hand.

**A red `ci` on the release commit is expected.** `docker/Dockerfile` pins
`digline==<the version being released>`, and the push-triggered `ci` fires
*before* the `pypi` job has uploaded it. So the image job fails with
`No matching distribution found`, every time, on the commit the tag points at.
It self-heals: the `workflow_run` `ci` that follows `publish` rebuilds it green.
On 0.7.1 the failing build ran at 06:25:07 and the upload landed at 06:27:21.
**Do not chase it, and do not re-tag for it** — check that the follow-on run is
green instead.

**The eight example legs need a dispatch after the lock regen.** Two things
combine. `examples-from-pypi` is gated `if: github.event_name != 'push' &&
!= 'pull_request'`, so pushing the lock commit does not run it; and the
`workflow_run` run that follows the tag checks out **the tag's commit**, which by
construction predates the lock regen. So that run's legs read the *old* version
and that is not a failure. Run it by hand against `main` once the locks are in:

```sh
gh workflow run ci.yml --ref main
```

Four examples carry a `uv.lock` pinning the exact version — `classifier`,
`langchain`, `prompt-first`, `rag` — and the other four resolve at install time.
Regenerate the four with `uv lock --upgrade-package digline` in each, commit, then
dispatch. *(Worth trying next release: regenerate the locks **before** the tag.
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
