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

## Before the tag: moving the number

`version` in `pyproject.toml` is one line and **four edits**. Nothing here is
optional and nothing is subtle; what it is, is unwritten — until 0.15.2 this
section did not exist, and the six red tests below were the only instructions
anybody got. They are good instructions. They are also a quarter of an hour
spent rediscovering them, every time, by somebody who has done it before.

Do them in this order, from the repository root:

```sh
# 1. The number itself, then the environment that reports it.
#    Without the sync, `test_dunder_version_is_the_installed_version` fails on
#    an editable install still naming the release before this one.
uv sync --all-packages

# 2. The three claims written by hand. Every occurrence in these three files is
#    a live claim about what is released, so a plain substitution is right here
#    and nowhere else.
sed -i '' 's/<old>/<new>/g' README.md docker/Dockerfile docker/README.md
```

`tests/test_versions.py::LIVE` names those three and what it reads in each:
`README.md`'s `## Status` line, `docker/Dockerfile`'s `ARG DIGLINE_VERSION`,
and the tag table in `docker/README.md`. `test_the_minor_tag_follows_the_release`
reads a fourth thing in that table — the `<major>.<minor>` tag, which has its
own shape and went stale unnoticed once already.

**3. Register what the old number became.** Every literal of the *previous*
version left anywhere the sweep reads is now history, and history has to be
declared with its reason in `tests/test_versions.py::RECORDED`, file by file.
This is the step that takes the time, and it is the one worth taking: a version
in a sentence is either a claim about now, which the release moves, or a record
of what happened, which the release must not. There is no third kind, and the
test refuses to guess.

Two things fall out of it that are easy to miss. The comments written *during*
the change — "(the delta-pass over X)", naming which release's pass found what
— are literals like any other and need registering in the file they were
written in. And the existing reasons that say *"told as history now that X is
the tree's version"* are about the version that has just stopped being current:
reword them, or the record explains itself with a number that has moved on.

The sweep is wide on purpose: every root `*.md` but `CHANGELOG.md`, all of
`src/`, `docs/` outside `adr/`, `packages/*/src` and every `README.md` under
`packages/` and `examples/`. `CHANGELOG.md` and `docs/adr/` are out because
they are dated history in every line, and `tests/` is out because a fixture
names versions for a living.

**4. Add the release's row to `RELEASED`** in `tests/test_example_caps.py` —
`"<new version>": <SCHEMA_VERSION>`, the schema this tree writes. A patch that
moves no schema still gets a row; the row is what lets the example caps be
checked against a release rather than against a number in the air.

### The six that stay red until you have done all four

Run the gates once after the bump and read them as a checklist rather than as
breakage. In the order they usually appear:

| Test | Wants |
|---|---|
| `test_versions.py::test_the_live_claims_say_what_pyproject_says` | step 2 |
| `test_versions.py::test_no_version_literal_is_left_unaccounted_for` | step 3 |
| `test_readme.py::test_the_status_version_is_the_version_in_pyproject` | step 2, `README.md` |
| `test_docker.py::test_the_image_pins_the_versions_this_workspace_declares` | step 2, `Dockerfile` |
| `test_docker.py::test_the_image_readme_documents_the_version_it_ships` | step 2, `docker/README.md` |
| `test_example_caps.py::test_the_schema_this_workspace_writes_belongs_to_a_release` | step 4 |

Two more failures are not part of this and come later by design, both fired by
the same act — dating the changelog entry below. `tools/home_capture.py
--check` then refuses the capture that names the previous version, and
`test_versions.py::test_a_dated_release_leaves_no_package_declared_unreleased`
refuses a package the tag carries whose own heading still says `unreleased`.
That is the next section, and both are steps of the same pull request. Seven
gates, six of them here.

### The window before the tag

Step 2 above opens a window, and it can be days wide. `docker/Dockerfile` now
pins a version **PyPI does not serve**, and it has to: the test in the table
above requires the image to pin what the workspace declares, so the two move
together and the index cannot follow until the release. Every build of that
image in between fails at the index wait — not because anything in the tree is
wrong, but because the thing it waits for does not exist yet.

This is **not** the short red documented under *After the tag*, and the two are
worth keeping apart. That one lasts minutes, sits on the release commit, and
heals itself when `publish` finishes. This one lasts until the tag: 0.16.0 was
pinned at 20:50 on 2026-09-18 and released at 13:17 the next day, sixteen and a
half hours; 0.17.0 was pinned on 2026-09-19 and was still unreleased the day
after. And it is not only the commits that touch `docker/`: the weekly
scheduled `ci` has no base commit to diff against, so it builds the image every
Monday, window or no window.

A red that stands for days and that nobody is meant to act on is a red that
stops being read, and it stops being read on the job that also reports the ones
that matter. So `ci` handles the window rather than leaving it:

- **`tools/image_pins.py` decides what the build installs.** A pin the index
  does not serve, whose exact version `CHANGELOG.md` declares with an
  `— unreleased` heading, is built at the newest version the index *does*
  serve. The job summary names every version it moved and why.
- **It reads a declaration, never the index alone.** A pin that is simply
  wrong — `0.17.O`, a letter for a zero — is declared nowhere, so nothing is
  substituted for it and the wait fails it by name, inside the window as
  outside it. Same for a version no heading mentions: it reaches the wait
  untouched, which is what tells *propagating* from *never uploaded*.
- **The image is built, not skipped.** The window is exactly when `docker/` is
  edited, so a skipped build would go dark precisely when it is needed. What a
  window build stops proving is the pin itself, and the pin is proven twice
  elsewhere: by `test_the_image_pins_the_versions_this_workspace_declares` in
  the tree, and by the real build at release.
- **To see the window's red on purpose**, run `ci` from the Actions tab with
  `image_pins_as_written` set. Nothing is substituted, and an absence from the
  index fails the job. That is the check to run by hand if you have edited
  `docker/Dockerfile` itself during the window.

Nothing here changes at release. The moment the heading below is dated, it
stops being a declaration, the substitution stops with it, and the pins are
waited for as written.

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

**Date every package the tag carries, not only the core.** `publish.yml` builds
the whole workspace and uploads everything the index lacks, so a `v*` tag
releases each plugin whose version has moved since the last one — with no named
tag of its own, and with nothing in its heading to say so. `v0.17.0` published
`digline-anthropic 0.5.3` and `digline-openai 0.5.2` and left both headings
reading `— unreleased` on `main`. Date them the way the core's is dated, and
say which tag published them: a reader who goes looking for
`digline-anthropic-v0.5.3` will not find it.

`test_versions.py::test_a_dated_release_leaves_no_package_declared_unreleased`
is the gate, and it belongs to *this* step rather than to the four above: it is
green while the core's heading still says `unreleased`, and goes red the moment
you date it with a package left behind — naming the package. A plugin genuinely
waiting for a tag of its own goes in `UNRELEASED_ON_PURPOSE` with the reason,
which is a sentence somebody writes and somebody reads.

That makes two failures that arrive at this step and not at the bump: this one
when the heading is dated, and `home_capture.py --check` right after it. Seven
gates in all, six of them in the table above.

It is no longer only tidiness. `tools/image_pins.py` reads those headings to
decide whether a pin the index does not serve is expected (*The window before
the tag*). A stale `unreleased` cannot open that window by itself — the gate
asks the index first, and a version it serves ends the question — but it is a
trap for the day that version stops being served, when a real absence would
read as an expected one. The image job says so in its summary when it sees one.

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
uv sync --all-packages --locked
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
3. Regenerate and stage the file **and the lock**, on the same branch, before
   the tag:

```sh
uv lock
uv sync --all-packages --locked
uv run python tools/home_capture.py
git add uv.lock docs/assets/home/home.json
```

`uv lock` on its own line, and it is the **only** place in this file that moves
the lock. Everywhere else asks for `--locked`, which refuses a lock that does
not match `pyproject.toml` instead of rewriting it. That split is deliberate:
the version has just been bumped, so this is the one moment the lock is
*supposed* to change, and making it a named command rather than a side effect of
`uv sync` is what stops the change from happening somewhere nobody is looking.

v0.15.1 is why. Its tag points at a lock still naming 0.15.0: `uv sync` had
refreshed the lock while the home capture was regenerated, only the capture was
staged, and every gate went green over it — CI's own `uv sync` rewrote the lock
in the runner and exited 0. `git add uv.lock` is in the command above for that
reason.

**And a dependabot lock PR open across the bump is not a merge conflict, which
is the trap.** v0.17.1 was cut with #61 open — a `uv.lock` bump of five
dependencies — and the version bump had moved the same file. `git merge-tree`
reported it merges clean, because the two edits are in different regions of the
file, and that proves nothing about whether the result *resolves*: **a
three-way-merged lock is not a lock any tool generated.** `uv sync --locked` is
the only thing that can answer it, and by then the lock is in the tree. The
answer is to let dependabot rebase and regenerate against the new `main` rather
than to take the clean merge, and to judge its gates afterwards on their own
terms — a `ruff` bump finding new lint is a decision somebody makes, not a
release blocker.

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

**And they land in one order: this repository first, the site immediately
after.** Not the other way round, however much "never push digline alone"
sounds like it. The two repositories are not symmetrical:

- `digline.dev`'s `main` requires a pull request **and** a `Build` check, and
  `docs.yml` checks out `digline/digline` at its **default branch** when no
  dispatch payload names a ref. So a site pull request carrying a nav entry
  **cannot go green** until the page is on this repository's `main`. Site-first
  is not risky, it is impossible.
- This repository's `main` requires `gates (3.12)` and `gates (3.13)`, and
  neither sets `DIGLINE_SITE_CONFIG` — so `tests/_site.py` skips there and the
  two nav checks never run. What runs them for real is the `docs` job, which
  clones the site, and `docs` is **not a required check**.

So merging here first is not blocked, and the whole cost is that `docs` on
`main` is red for the window between the two merges. It blocks nobody: no
required check, no release, no deploy — a failed site build does not deploy,
and the live site keeps serving what it already had. Close the window, then
re-run `docs`.

This paragraph exists because the rule was stated backwards for three days
running, from a memory that had recorded it correctly and was read the wrong
way round. The direction is not intuitive — the repository whose required
checks are *blind* to the site is the one that has to move first — so it is
written down here rather than carried in anybody's head.

**Nothing is queued as of 0.15.3.** Read off `digline.dev`'s `origin/main`
rather than remembered — every `docs/` page and every ADR on this repository's
`main` carries all three entries there: the `nav` line, `PRODUCT` in
`tools/hooks/seo.py`, `DESCRIPTIONS` in `tools/hooks/llms.py`. Checked on
2026-09-18 against the site's live `sitemap.xml` (99 URLs) and the `docs` job of
the dispatch run on `main` after v0.15.3, which builds `--strict` and is green.

0.15.1, 0.15.2 and 0.15.3 added no page between them: 0.15.2 and 0.15.3 amended
ADR 0012, and an amendment needs no entry because the page already has its
three. **`docs/adr/0023` is not a gap in the site — it is a number claimed on
the `capture` branch and not yet on `main`**, which is what the ADR numbering
does; it becomes this list's next line on the day that branch merges.

This paragraph was dated *0.15.0* while the tree was at 0.15.3, which is the
rot it warns about two lines below: three releases passed and the sentence
still read as current. It says 0.15.3 because step 4 of *After the tag* moved
it, not because anybody remembered.

The next page added goes in this list with its destination, and comes out of it
when the site has it: **three lines each**, per the table above, in three files.
Check it the way the sentence above was checked — `git show origin/main:<file>`
in `digline.dev`, not from memory, because this list is exactly the kind that
rots quietly once it stops being true.

**A failure here is not a re-tag.** The site job is the last step of
`publish.yml` and runs *after* PyPI, so a docs defect discovered at that point
leaves the packages correct and the site describing the version before them.
Fix it on `main`, then re-run the failed `site` job. v0.3.0 went out that way.

**The three nav gates run in CI now, and may not skip there.**
`tests/test_docs_pages.py`, `tests/test_adr.py` and `tests/test_examples.py`
each carry one check that reads digline.dev's `nav`, and `tests/_site.py` skips
them wherever the site is not on disk — which was everywhere in CI, since the
`gates` job clones no site. Ten skipped at the bottom of a green run is a
silence, not an absence: nothing anywhere had checked that a page carries its
nav line. The `docs` job, which clones the site to build it, now runs those
three by node id with **`DIGLINE_SITE_REQUIRED=1`**, under which a skip is a
failure — and beside them a control that points the config at nothing and must
fail, because a gate whose whole value is that it refuses to skip has to be
shown refusing. `tests/test_releasing.py` holds that list to every test that
reads the site config, so a fourth cannot be written and quietly skip forever.

Locally nothing changes: without digline.dev beside the repository the three
still skip, and the skip now says what went unverified rather than only how to
fix it. Set `DIGLINE_SITE_CONFIG` to run them, or do not; the variable that
forbids the skip is set in one job, deliberately.

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

### Plugins ride the core tag, and the annotation names them

That sweep is **intended**: it is how a family ships in one run, and `v0.15.0`
used it deliberately to release digline with three plugins at once. A plugin
gets a named tag of its own when it needs a release of its own — between core
releases, or at a version the core is not moving to.

**What is not optional is naming them.** A tag is a signature, and the
annotation is the only place the occasion is recorded in a ref. So the message
lists **every package the run will publish, at its version**:

```sh
git tag -a v0.15.0 -m "digline 0.15.0, digline-anthropic 0.5.2, digline-openai 0.5.1, digline-bedrock 0.5.1"
```

Run the check before tagging, with the message you are about to use:

```sh
uv run tools/tag_names.py "digline <version>, digline-anthropic <version>"
```

It reads every workspace `pyproject.toml`, asks the index (the JSON API, not
`/project/<name>/<version>/`, which answers 200 for anything) which of those
versions it already serves, and prints what the run will upload. It exits
non-zero when the message names fewer packages than the run publishes — and
also when the run would publish **nothing at all**, which is a tag nobody
should cut and the shape a re-tag of an already-released version takes.

This is the same move as the counts at the `[GATE]`: a number read out loud
rather than a memory trusted. `tests/test_tag_names.py` covers it offline, with
`v0.17.0`'s real message as the control that must fail.

### Four releases that no ref names

Recorded here because the repository cannot answer it in refs, and **not**
backfilled: pushing a tag runs `publish`, and a run against versions the index
already serves is a run whose green means nothing. Read from PyPI's upload
timestamps, which are the only surviving record.

| package | version | uploaded (UTC) | carried by | that tag's message |
|---|---|---|---|---|
| `digline-anthropic` | 0.5.0 | 2026-09-15T14:57:35Z | `digline-openai-v0.5.0` | `digline-openai 0.5.0` |
| `digline-bedrock` | 0.5.0 | 2026-09-15T14:57:36Z | `digline-openai-v0.5.0` | `digline-openai 0.5.0` |
| `digline-anthropic` | 0.5.3 | 2026-09-20T09:43:57Z | `v0.17.0` | `digline 0.17.0` |
| `digline-openai` | 0.5.2 | 2026-09-20T09:43:58Z | `v0.17.0` | `digline 0.17.0` |

**And the same defect runs the other way, in the same window.**
`digline-anthropic-v0.5.0` and `digline-bedrock-v0.5.0` were cut *after* their
packages were already on the index — 14:59:35Z and 15:04:51Z against uploads at
14:57 — so both runs **published nothing, and both went green**. A release
ceremony was performed, a ref was written, `publish` ran to completion and
reported success, and not one file moved.

Read together with the four above, that is one defect with two faces. Above, a
tag published more than it named; here, a tag named something and published
nothing. In both the ref and the message stopped describing the run, and in
both the green said only that the machinery had executed — never that it had
done the thing the tag claimed. A green that cannot distinguish "uploaded four
packages" from "uploaded none" is not evidence about either.

`tools/tag_names.py` refuses **both** directions — a message naming fewer
packages than the run will publish, and a tag whose run would publish nothing
at all — and that is what makes it a gate rather than a reminder. A check that
caught only the omission would have let these two through with the same
meaningless success they already had.

And the habit did work twice: `v0.15.0` named all four packages it carried, and
`v0.15.3` named `pytest-digline 0.1.6` beside the core. It was a habit rather
than a rule, which is why it lapsed at `v0.17.0`, and why it is a check now.

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

**An upload returning 200 is not the index serving the file.** `publish`
uploads, and its consumers start the moment it completes. So the first
`pip install` after a tag is structurally early.

**The rule.** Every place `pip` resolves the index from gets its own wait. The
wait runs there, beside the install it protects. It asks exactly what `pip`
asks. It **never retries**: it waits for these exact files and names what is
missing.

**Reading a red:**

| The red says | It means | Do |
|---|---|---|
| `/simple/digline/ is served and lists 41 file version(s), none at 0.13.0` | propagation, or a version that was never uploaded | before `pypi` has uploaded, the expected red (*After the tag*); after it, check the `pypi` job's log lists the file, and re-run only if it does |
| `/simple/digline-mcp/ answered 404 — a project that has never been published, or a name that is misspelled` | a package **new to the index**, or a misspelling | check the spelling; for a new package, see *Before the first tag of a new package* |
| `served` for every pin, then `No matching distribution found` from `pip` in the same `RUN` | the wait and `pip` got different answers | `gh run rerun <id> --failed`, read the log, and see *The diagnostic* below |
| `No matching distribution found` from `pip`, with no `the index at … must serve` above it | a consumer with no wait | add one: see *Applying it* |

A green run proves a wait ran only if its `served` lines are in the log.

### Why each clause

- **A wait, not a retry.** A bare retry cannot tell *not yet propagated* from
  *genuinely missing*: a typo'd pin, a version that never uploaded, a project
  that does not exist. It burns its budget and fails the same way for both, so
  a real defect becomes a slow flake. The wait asks the one question that
  separates them, *is this exact file served?*, and answers in the two shapes
  above. The second shape exists because a brand-new project has no page at
  all, so an edge can hold a cached 404 for its URL. That lasts longer than a
  page that only has to gain a line.
- **From where `pip` resolves.** One place's view of the index proves nothing
  about another's. A runner, a container and a Docker build's network namespace
  can each reach a different edge. So a job can hold several consumers, and a
  wait protects only the one it runs in.
- **The same question `pip` asks.** PyPI answers `/simple/<name>/` with
  `Vary: Accept-Encoding, Accept`, so two requests that differ in either header
  read two different cached copies of one URL. `await_index.py` sends pip
  25.0.1's `Accept` (the JSON simple API first) and `Accept-Encoding`
  (`gzip, deflate`), and reads the JSON page. It keeps the HTML page as the
  fallback `pip` keeps. It also sends pip's `Cache-Control: max-age=0` in place of
  `no-cache`, not because that header is proven to matter but because the goal is the same
  question, not a better one. The script says so beside the headers, and
  `tests/test_await_index.py` holds each one to pip's.

### Applying it

**To find a consumer, do not list the workflow's jobs. List every
`pip install`, and ask where it runs.**

| Consumer | Where it resolves | Waits for | Deadline |
|---|---|---|---|
| `publish.yml` → `pypi` | the runner | every pin in `dist/` | 10 min |
| `docker-publish.yml` → `smoke` | the runner | the four pins in `docker/Dockerfile` | 30 min — it waits on a *person* approving `pypi` |
| `docker-publish.yml` → `smoke`, build step | **inside the build** | the same four pins, beside `pip install` | 5 min |
| `docker-publish.yml` → `publish`, multi-arch build | **inside the build**, amd64 and arm64 | the same four pins | 5 min |
| `ci.yml` → `image` | the runner | the same four pins | 4 min |
| `ci.yml` → `image`, build step | **inside the build** | the same four pins | 4 min |
| `ci.yml` → `examples-from-pypi` | the runner | this workspace's core version | 4 min |

The consumers start as `ci.yml` on `workflow_run: [publish] types: [completed]`,
and `docker-publish.yml` beside it on the same `v*` tag.

**How the wait inside a build works.** It is `docker/await_index.py`, the same
script as `.github/await_index.py`, copied into the build context and held byte
for byte by `tests/test_docker.py`. It is bind-mounted, so no byte of it lands
in the image. It runs in the same `RUN` as `pip install`, so a cached install is
never separated from its wait. It is gated by `ARG AWAIT_INDEX_TIMEOUT`,
**default `0`**: a local `docker build docker/` waits for nothing, and only the
three builds above pass a timeout. The same test holds each of them to a
non-zero one.

### The diagnostic, kept ready and not built

If a wait prints `served` and `pip` in the same `RUN` still finds no such
version, **after** the same-question fix, the variant is ruled out. One
hypothesis is left: **per-server luck**, the two requests landing on different
cache servers of the same variant, one refreshed and one not. That is when a
capture earns its cost, and not before. Build it into the step then, recording
for both requests, the wait's and `pip`'s own, at the moment of failure:

- the versions the page lists;
- `X-Served-By`, `X-Cache` and `Age`;
- the time, to the tenth of a second.

Same server with a different answer would refute per-server luck. Different
servers would confirm it.

### Status: what each path has proven

This is the part that changes from release to release. Step 4 of *After the
tag* updates it on every tag.

- **The wait inside the build runs on the release path.** Seen on v0.15.0: both
  `docker-publish.yml` legs printed `served` under `#… the index at
  https://pypi.org must serve`.
- **The same-question fix is proven on the release path, on v0.15.1, in a live
  race.** It published first time: `docker-publish` succeeded on attempt 1, with
  no rerun, where v0.15.0 had needed one.

  The race was real rather than arranged. The runner-level wait sat on
  `digline==0.15.1` for **1471s** — the upload was behind the `pypi` reviewer
  gate — and cleared at 09:17:04, so the build started roughly fifteen seconds
  after the version first appeared on the index. That is the window v0.15.0 lost
  in.

  **The pair, per architecture, and one of them is not what it looks like:**

  - **amd64 — proven in `smoke`'s build.** `#9 0.403 served digline==0.15.1
    (after 0s)`, then `#9 1.515 Collecting digline==0.15.1` and `#9 8.948
    Successfully installed … digline-0.15.1 …`. Same `RUN` (`#9`), install 1.1s
    after `served`. This is the exact shape that failed on v0.15.0, where
    `served` at 0s was followed 1.2s later by *No matching distribution found*.
  - **arm64 — proven in the multi-arch push.** `#15 [linux/arm64 stage-0 3/5]`
    printed `served digline==0.15.1 (after 0s)` and installed in the same `RUN`,
    which the step's own command line shows is one `await_index.py … && pip
    install …`.
  - **amd64 in the multi-arch push proved nothing, and that is expected.**
    `#12 [linux/amd64 stage-0 3/5]` is `CACHED` — the layer was reused from
    `smoke`'s build on the same runner architecture. A cache hit is not a second
    observation, and reading the multi-arch job alone would have shown one pair
    and a silence. Both architectures are covered only because `smoke` runs the
    amd64 one first.

  So: two architectures, two independent pairs, across two jobs — not three
  pairs in the job the checklist points at. The next tag needs the same reading
  rather than a green, because a cache hit and a pass look identical from the
  summary.

- **v0.15.2, written back on 2026-09-18 from that tag's own logs.** Step 4 was
  not performed at the time — this block went from v0.15.1 to v0.15.3 — and the
  gap was found by the check that now asks. It is filled rather than left,
  because the evidence is still there and a release with no line here reads as a
  release nobody looked at.

  The same three parts, and the same verdict. `#9 [stage-0 3/5]` in `smoke`:
  `#9 0.415 every version is served (after 0s)`, then `#9 1.542 Collecting
  digline==0.15.2` and `#9 8.852 Successfully installed … digline-0.15.2 …` —
  one `RUN`, install 1.1s after `served`, which is **amd64** proven.
  `#11 [linux/amd64 stage-0 3/5]` in the multi-arch push is `CACHED` and proves
  nothing, exactly as the v0.15.1 paragraph predicts it will be every time.
  `#15 [linux/arm64 stage-0 3/5]`: `served` *(after 1s)*, `#15 20.48 Collecting`
  and `#15 107.1 Successfully installed`, which is **arm64** proven.

  **And the race was not live here either.** `after 0s` and `after 1s`: the
  index was already serving when the build asked, and the whole run took under
  four minutes from tag to release. So v0.15.1 remains the only tag on which the
  same-question fix has been observed under a real race — one observation, now
  twice unrepeated, which is the fact this list exists to keep visible rather
  than to let three greens obscure.

- **v0.15.3 read the same way, and the shape held — but the race was not
  live.** The reading is the one above, a second time and in the same three
  parts: `#9 [stage-0 3/5]` in `smoke` printed `every version is served (after
  0s)`, then `#9 1.596 Collecting digline==0.15.3` and `#9 8.750 Successfully
  installed … digline-0.15.3 …` — same `RUN`, install 1.2s after `served`, which
  is **amd64** proven. `#11 [linux/amd64 stage-0 3/5]` in the multi-arch push is
  `CACHED`, exactly as the paragraph above predicts, and proves nothing. `#15
  [linux/arm64 stage-0 3/5]` printed `served` *(after 1s)*, `#15 23.22
  Collecting` and `#15 132.9 Successfully installed`, which is **arm64** proven.
  Two architectures, two pairs, two jobs.

  **What this tag did not prove, said plainly.** `after 0s` and `after 1s` mean
  the index was already serving when the build asked: there was nothing to wait
  for. v0.15.1 sat on `digline==0.15.1` for 1471s behind the reviewer gate and
  cleared fifteen seconds before the build; v0.15.3's approval came quickly
  enough that the window never opened. So this tag proves the wait **costs
  nothing when the index is ahead of it**, and it does not re-prove the fix
  under a live race. One observation of the race remains one observation.

  What it did prove, in the other direction, is the 0.15.1 improvement to the
  *expected* red: the `image` job on PR #38 failed at `Wait for every pinned
  version to be served to this runner`, naming `digline==0.15.3` and the shape
  of the absence — `is served and lists 29 file version(s), none at 0.15.3` —
  so a reader could tell it from a typo'd pin without opening anything else.

  **What the next tag must show:** the same two-pair reading, and, if its
  approval is slow again, a `served` measured in hundreds of seconds rather
  than in one. A fast approval is not evidence that the race is gone; it is
  evidence that it did not happen this time.

- **v0.16.0 showed exactly what that paragraph asked for: the race, live, a
  second time.** The approval was slow — the runner-level wait sat on
  `digline==0.16.0` for **571s** behind the `pypi` reviewer gate, printing
  `waiting digline==0.16.0 — /simple/digline/ is served and lists 30 file
  version(s), none at 0.16.0` throughout, which is the legible absence 0.15.1
  bought — and then `served digline==0.16.0 (after 571s)`. The build started
  about sixteen seconds later.

  The same three parts, and the same verdict. **amd64 proven in `smoke`:**
  `#9 0.533 served digline==0.16.0 (after 0s)`, then `#9 1.689 Collecting
  digline==0.16.0` and `#9 8.633 Successfully installed … digline-0.16.0 …` —
  one `RUN`, install **1.2s** after `served`. That is the shape that failed on
  v0.15.0, where `served` at 0s was followed 1.2s later by *No matching
  distribution found*. **`#11 [linux/amd64 stage-0 3/5]` in the multi-arch push
  is `CACHED`**, as this list has predicted it will be every time, and proves
  nothing. **arm64 proven in the multi-arch push:** `#15 5.099 served
  digline==0.16.0 (after 0s)`, `#15 23.79 Collecting`, `#15 132.1 Successfully
  installed … digline-0.16.0 …` — one `RUN`, on the job's single
  `await_index.py … && pip install …` command line.

  Two architectures, two pairs, two jobs. All three image tags — `0.16.0`,
  `0.16`, `latest` — resolve to one digest, `sha256:02f7639b`.

  **So the same-question fix now has two observations under a real race**,
  v0.15.1 and this one, and the gap between them is worth naming: 0.15.2 and
  0.15.3 were both approved fast enough that the window never opened. The race
  is not reproducible on demand — it is produced by a human taking their time
  at the reviewer gate — which is why this block records *whether it happened*
  and never treats a green as an answer to that question.

  **What the next tag must show:** the same two-pair reading, and the honest
  note about whether the race was live. Three observations would be better than
  two, and the way to get one is not to hurry the approval.

- **v0.17.0 got the third observation, and it came from a *plugin* rather than
  the core.** The approval was fast, so the core never raced: `served
  digline==0.17.0 (after 0s)` and `pip` took it. What failed on attempt 1 was
  `digline-anthropic==0.5.3` — **published by this same workspace tag**, since
  `publish.yml` uploads everything the index lacks — where the wait printed
  `served digline-anthropic==0.5.3 (after 0s)` and `pip`, **1.5s later in the
  same `RUN`**, was told *Could not find a version that satisfies the
  requirement digline-anthropic==0.5.3 (from versions: … 0.5.2)*. That is the
  v0.15.0 shape exactly, on a package the same-question fix has never been
  watched on: the plugins move rarely, and when they do it is usually on their
  own tag, minutes after the core's.

  **So the divergence is not specific to the core's name**, which is the thing
  this observation adds. It also says what the fix cannot do: `PIP_HEADERS`
  makes the wait ask pip's question, and two edges can still answer it
  differently — the last paragraph of *What is not covered* is the standing
  version of this, now with a release behind it.

  Attempt 2, run by hand about twenty minutes later, read clean. **amd64 proven
  in `smoke`:** `#9 0.569 served` for all four pins, `#9 1.686 Collecting
  digline==0.17.0`, `#9 8.973 Successfully installed … digline-0.17.0
  digline-anthropic-0.5.3 digline-bedrock-0.5.1 digline-openai-0.5.2 …` — one
  `RUN`, install **1.1s** after `served`. **`#12 [linux/amd64 stage-0 3/5]` in
  the multi-arch push is `CACHED`**, as predicted every time, and proves
  nothing. **arm64 proven in the multi-arch push:** `#15 5.182 served`, `#15
  23.94 Collecting`, `#15 135.2 Successfully installed …`. Two architectures,
  two pairs, two jobs. All three image tags — `0.17.0`, `0.17`, `latest` —
  resolve to one digest, `sha256:e4672e7e`.

  **What the next tag must show:** the same two-pair reading; and, if it
  publishes a plugin, whether the plugin's own pin was waited out on the first
  attempt. One re-run is not a defect, but two releases in a row needing one on
  a plugin pin would say the wait's budget is wrong for a package the edges
  cache differently from the core.

- **v0.17.1 raced at the runner and not inside the build, and the distinction
  is the whole of what it proved.** It published first time — no re-run — and
  the plugin question the paragraph above asks does not apply: this tag carried
  the core alone, every plugin version already served, checked with
  `tools/tag_names.py` before the tag rather than assumed.

  **The wait was real.** The runner-level step sat on `digline==0.17.1` for
  **241s**, printing `waiting digline==0.17.1 — /simple/digline/ is served and
  lists 32 file version(s), none at 0.17.1` eight times from 0s to 211s before
  `served digline==0.17.1 (after 241s)`. The three plugin pins read `after 0s`
  throughout, so the message did what it was written for: it named *which* pin
  the run was waiting on, and said the index had answered and lacked the
  version rather than failed to answer.

  **But the build never met the race.** By the time `#9` asked from inside the
  image it was `after 0s`, because the runner-level wait had already absorbed
  it. The upload landed at 13:44:15Z, the runner's wait cleared at 13:44:43Z,
  and the build asked about half a minute after the version first existed — a
  window, but one nothing went wrong in. So the same-question fix was **not**
  exercised here: **v0.15.1, v0.16.0 and v0.17.0 remain the three observations
  under a real divergence, and this is not a fourth.** Written that way so four
  greens do not come to read as four observations.

  One corroboration from outside CI, kept because it is the same divergence
  seen from the other side: minutes after the upload,
  `pypi.org/pypi/digline/json` still named `0.17.0` as the latest and did not
  list 0.17.1 at all, while `/simple/digline/` — what `pip` reads — already had
  it, and a cache-busted request to the first endpoint then agreed. Two
  endpoints, two answers, no failure. That is the shape the fix is for,
  observed on a release where it cost nothing.

  **The pair, per architecture.** **amd64 proven in `smoke`:** `#9 [stage-0
  3/5]` printed `every version is served (after 0s)` for all four pins, then
  `#9 1.799 Collecting digline==0.17.1` and `#9 10.55 Successfully installed …
  digline-0.17.1 digline-anthropic-0.5.3 digline-bedrock-0.5.1
  digline-openai-0.5.2 …`, `#9 DONE 11.3s` — one `RUN`, install **1.2s** after
  `served`. **`#12 [linux/amd64 stage-0 3/5]` in the multi-arch push is
  `CACHED`**, as this list has predicted every time since v0.15.1, and proves
  nothing. **arm64 proven in the multi-arch push:** `#15 5.090 every version is
  served (after 1s)`, `#15 23.87 Collecting`, `#15 138.4 Successfully installed
  …`. Two architectures, two pairs, two jobs. All three image tags — `0.17.1`,
  `0.17`, `latest` — resolve to one digest, `sha256:5c14eac4`, whose manifest
  carries `linux/amd64` and `linux/arm64`.

  **What the next tag must show:** the same two-pair reading, and — since the
  runner-level wait has absorbed the race on three of the last four tags —
  whether the in-build await ever prints a non-zero wait of its own. If it never
  does, that is worth saying out loud rather than leaving implied: the in-build
  `await_index.py` would be a belt whose braces have held every time, and the
  case for keeping it would rest on the tags where the edges disagreed rather
  than on anything since.

### What is not covered, stated rather than assumed

The `testpypi` job installs unversioned names, on purpose — TestPyPI resolves
against a different set of uploads — so nothing holds it to a version and a
lagging index there can still resolve an older one. The five examples carrying
a `uv.lock` pin exact versions that legitimately lag a release until the locks
are regenerated, and the wait says nothing about what any individual lock
resolves to. The ten `examples/*/.github/workflows/check.yml` are inert inside
this monorepo and are not reached by a release at all. `java-example.yml`
installs no Python package and is not a consumer.

And the part no amount of waiting closes: **PyPI's edges converge on their own
schedule.** The wait narrows the window to whatever the consuming runner can
see; it cannot make one edge speak for another.

### Evidence: eight times paid for

Each clause of the rule was learnt by losing the race, one floor further down
each time. Before the wait existed, whether the first consumer went red was
decided by scheduling, not by anything in the tree.

| Release | What failed | What it taught |
|---|---|---|
| 0.7.1 | a warm `pip` cache | the race, before any wait existed |
| 0.8.0 | the `rag` and `llamaindex` legs of the follow-on run (see *After the tag*) | the race, before any wait existed |
| 0.11.0 | the classifier lock regen | the race, before any wait existed |
| v0.13.0 | the `pypi` job verified its pins, and `docker-publish`'s image build ~30s later, inside a container's own network namespace, was still told `digline==0.13.0` did not exist | a wait in one job does not protect another: wait per consumer |
| `digline-openai-v0.5.0` | the follow-on `ci`: the core was current and a plugin was not, and the wait, which asked only about the core, passed | wait for every pin, not merely one (`tests/test_await_index.py` holds it) |
| v0.14.0, v0.14.1 | `docker-publish`: the image jobs' own wait on the runner passed, and `pip` *inside the Docker build* was served the previous version 16–20s later | a wait on the runner does not protect the build it starts: wait from where `pip` resolves. The first list of consumers was made by walking the jobs, which missed the in-build ones and cost two reruns |
| v0.15.0 | `docker-publish`, attempt 1: the wait inside `smoke`'s build printed `served digline==0.15.0 (after 0s)`, and `pip install` 1.2s later in the same `RUN` answered *No matching distribution found for digline==0.15.0*, listing versions up to 0.14.1. The job failed, the multi-arch push was skipped, and no image was published | the same place is not enough: ask the same question `pip` asks |

**v0.15.0, measured.** The two requests differed in both headers PyPI's `Vary`
names. The wait sent no `Accept` and `Accept-Encoding: identity`, and got the
HTML page. pip 25.0.1 sent the JSON simple API first and `gzip, deflate`, and got
the JSON page. Measured on the wire the same day, and consistent with that: each
copy was answered by a different shield server, and `Cache-Control: no-cache`
did not force a fresh copy. Attempt 2 (`gh run rerun --failed`): `smoke`'s build
printed `served` and installed all four. The multi-arch push's arm64 leg printed
`served` after waiting 16s and installed, and its amd64 layer was cached from the
same `RUN` in `smoke`. `0.15.0`, `0.15` and `latest` resolved to one digest.

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

**The report goes in `private/`, as `delta-pass-<version>.md`, and it goes there
the same day.** It is the working material the next pass reads to know what it
may skip, so where it is kept decides whether it exists at all: the 0.14.0
report was left in a session scratchpad, a scratchpad is per session and
temporary, and by the time the 0.15.0 pass went looking for the list of what had
come back clean it was gone — that pass took "the declared price and the tool
arguments" from a sentence in the brief rather than from the record. A findings
file that is not committed somewhere is a findings file that expires. `private/`
is the right somewhere: a separate repository, gitignored here, and already
where the frictions log lives for the same reason.

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

### These three have no gate, and must not be given one

The pass itself, the report in `private/`, and the GHSA draft are the three
steps of this file that nothing in the repository checks, and that is a decision
rather than an omission. Written down because the alternative keeps suggesting
itself, and because the audit that produced this paragraph listed all three as
holes.

**A check on a file's existence teaches the making of the file.** A gate that
refused a release without `private/delta-pass-<version>.md` would be satisfied
by a file containing one line, and satisfied *identically* by one containing the
reading it is supposed to hold — so the first time the pass is skipped under
time pressure, the cheap way past the gate is to write the file, and the gate
now certifies the opposite of what it was built for. That is worse than no
gate: it converts a step somebody knows they skipped into a step the record says
they took.

The same applies to the other two. There is no shape of "a delta-pass happened"
a test can read — a pass that finds nothing looks, from outside, exactly like a
pass nobody ran, and the difference is entirely in whether somebody adversarially
read the diff. And a GHSA draft that exists is not a GHSA draft that says the
right thing; `SECURITY.md` decides whether a finding earns one at all, which is
a judgement about impact that no predicate holds.

**What is gatable is the consequence, not the act.** Every finding a pass makes
becomes a regression test that fails against the release just cut — that is the
rule two paragraphs above, and it is the honest half: the tests in
`tests/test_terminal_escapes.py`, `tests/test_wire_boundary.py` and
`tests/test_journal.py` are the record that particular passes happened, and they
hold forever without anybody being asked to prove diligence. The act stays
human, unwatched and in this file, which is where a step belongs when the only
thing that can verify it is the person doing it.

## After the tag: what to watch, and what to ignore

**In order, after every tag.** Each step is explained below or in the section it
names.

1. **The reviewer gate:** read the approvals endpoint, not the run's green. See
   the last paragraph of this section.
2. **`docker-publish`:** read its log, not its green. That means the `served`
   lines and a clean `pip install` of the released versions in the same `RUN`,
   and all three image tags on one digest. See *The index race*.
3. **The example locks:** regenerate them, then dispatch `ci.yml`. See *The nine
   example legs* below.
4. **The status block:** update *The index race* → *Status: what each path has
   proven* with what this tag proved and what the next one must show. It
   changes every release, so it is updated by this step, not from memory.
5. **The example reports:** re-render every committed `report.html` against the
   tagged release, in the order the ritual requires — commit the example,
   render, commit the report on top, never amend — so each report records a
   commit somebody can reach. A report is a photograph of the run that
   produced it, which is why a string change does **not** regenerate one: four
   of them carried a stale `What answered` heading from the moment that
   heading was corrected, deliberately, until the next tag. This step is what
   clears that debt, and it is a step so that it happens by procedure rather
   than because somebody noticed a heading.

**Four of these now have a machine asking, and one place the answer lands.**
`release-followup.yml` runs after `publish` and on every push to `main`, and
asks the four questions of this list that have an answer a machine can check:
the example locks name the released version (step 3), the `publish` run's
approvals record an `approved` (step 1), the three image tags resolve to one
digest (step 2's other half), and the Status block names the release (step 4).
Each is asked twice — once for the answer and once for something that must be
false — because three of the four fail open by construction, and a check that
cannot fail has verified nothing.

**The finding is an issue, not a colour.** One open issue **per release**,
labelled `release-followup`, whose body is the current reading and whose title
names the step that is undone; a later run about the same release rewrites it,
and the run that finds that release's follow-up done closes it. Per release
rather than per repository, which is a correction rather than a preference: with
one issue for the whole repository, a green run about 0.15.3 closed an issue
naming 0.15.2 — a step nobody had done, marked done by a run that never looked
at it. An issue about another release is left open and named in the run's
notices, because a follow-up still outstanding is itself worth seeing.

**Two of the four are asked only about the newest release**, and this is what
keeps such an issue from being immortal. The example locks and the `<minor>` and
`latest` image tags are the *current state of a moving thing*: asked about a
superseded release they report that the locks name something else and that
`latest` points elsewhere — which is what they are supposed to do, so the
failure would be describing the repair. They answer **not applicable** there.
The other two keep their meaning for ever, because their subject is a record of
what happened at that release: the approvals of its publish run, and its
paragraph in the Status block. That is the line, and it is worth stating as a
rule because the next check added will sit on one side of it — *is this about
what was recorded then, or about what is true now?*

Without it the issue opened for 0.15.2 could never have been closed: two of its
lines could only go green by making the current tree wrong, so no run could
close it, and a red label open for ever is the signal people learn to ignore —
the failure this section exists to prevent, one level up.

That shape is the point rather than a convenience: this
checklist was skipped twice precisely because nothing stayed open, and the job
cannot use a red instead — between the tag and the follow-up commit the
repository is *supposed* to fail these, since a lock cannot name a version the
index has not served yet. A second expected red would undo the work spent making
the one expected red legible. The job does exit non-zero, for whoever is
watching; the issue is for whoever is not.

**What it does not check, and this is the important half.** It reads the image
*digests*, which is one line of step 2. The rest of step 2 — the `served` lines
in both legs, the clean `pip install` in the same `RUN`, and which of the pairs
was `CACHED` and therefore proved nothing — is a **reading**, and no predicate
holds it. Step 4 is the same: the job checks that the block names the release,
never that what it says is true. Both stay yours. What the job removes is the
possibility of the step being *forgotten*, which is a different thing from it
being done well.

Three of the paragraphs below look like problems and are not, and the fourth is
the one check worth doing by hand.

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

This red is the *short* one, and it belongs to the release commit. The days
between the version bump and the tag are the other window, and `ci` does not go
red through them: see *The window before the tag*. Dating the changelog heading
is what ends that window and hands the pins back to this race.

**A red `docker-publish` on the release tag no longer means "re-run it".** It
used to: the job's own wait asked only about `digline`, from the runner, and
the build then installed four versions from inside a container. Re-running was
how it got past a plugin the index had not caught up on. The job now waits for
all four pins, so a red there is a failure to read rather than a button to
press again. Re-run it only after reading which version it names.

**One red still ends in a re-run, and v0.15.0 is its example:** the in-build wait
prints `served` for every pin and `pip install` in the same `RUN` then finds no
such version. On v0.15.0 that was the variant divergence under *The index race*,
which the wait no longer has. If it happens again, it is the one hypothesis left
there, and the diagnostic described there is built before the next tag. Re-run the failed jobs (`gh run rerun <id> --failed`). Then **read the log,
not the green**: `served` lines in both legs, `Successfully installed` with the
released versions, and all three tags on one digest.

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
