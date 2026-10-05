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

**Open, not ruled: whether the criterion measures only what breaks.** Raised
on 2026-10-01, cutting 0.25.2. Its heading had been opened as the next
minor, `— unreleased`, with no reason recorded. The diff against `v0.25.1`
showed:
- no schema change and no CLI change;
- no public name removed, and three added;
- two new refusals, each on input that public digline could not produce
  before.

The rule above made it a patch, and it shipped as one. The question it left is
about the rule itself. **The rule measures only whether something stops
working, and `project_served` opens a capability that was refused before**:
projecting a run nobody promoted, which ADR 0034 §2 refused until ADR 0038
narrowed it. Whether a capability opened that way should move the minor is not
decided here. It is to be ruled on its own, away from a release, and not while
cutting one.

## Two rituals, and mapping one of them is how you get surprised

**A schema bump is two rituals, not one.** Moving `SCHEMA_VERSION` obliges the
schema ritual — the `_STEPS` entry, the committed baselines migrated, the caps
raised, the tests that name the schema by number. But a schema that has moved
belongs to no release, so it also obliges a **version** bump, and that is a
second ritual with a different set of files: `CHANGELOG.md`, the claims `LIVE`
pins, `docker/README.md`'s tags *and* its minor tag, and the previous release's
version literals moved into `RECORDED` because they have become history.

Paid for on schema 16. The schema ritual was mapped carefully and executed in
one coordinated edit; the run that followed it cleared all 31 schema reds and
produced **five new ones**, every one of them from the version half. Nothing had
gone wrong — the mapping had covered one ritual and been called done.

So when a change moves `SCHEMA_VERSION`, budget both, and read the version half
below rather than assuming the schema half was the work. Four traps inside it,
none of which a substitution will find:

- **`docker/README.md` names the version five times and the *minor* tag once.**
  A script that moves the row `LIVE` pins moves one of six.
- **Head the entry `— unreleased`, and do not date it until the release commit.**
  This is the one that is easy to get backwards, and getting it backwards breaks
  two things at once. `## 0.19.0 — 2026-09-23` on a version PyPI does not serve
  is a false claim in a public file — and it also **switches off the window
  machinery above**: `tools/image_pins.py` substitutes a served version only for
  a pin whose version the changelog declares `— unreleased`, so a dated heading
  sends the real pin to the index wait and the image job fails for a reason that
  looks like a defect. `a72a8c0` is the shape to copy: the feature commit writes
  `— unreleased`, and the release commit dates it.
- **`tools/home_capture.py --check` keys off the newest *dated* entry**, not off
  `pyproject.toml` and not off the unreleased heading. So inside the window it
  stays green with a capture from the **previous** release, and re-generating it
  early makes it red the other way — captured with the new version, newest dated
  still the old one. Leave it alone until the release commit dates the heading.

  **One rule, two opposite answers, both correct** — worth stating because the
  history shows it twice in one day and the first will read as a mistake. On
  2026-09-23 the capture was regenerated, then **reverted** to the previous
  release's, then regenerated again. Nothing changed its mind: the file must
  match the newest *dated* entry, and what moved was the heading. While 0.19.0
  said `— unreleased` the 0.18.0 capture was the correct one; the release commit
  dated the heading, and at that moment the 0.19.0 capture became correct. A
  revert that looks like an undo is the same rule reading a different tree.

- **The previous release's literals become unaccounted the moment the number
  moves.** They are evidence — build logs, digests, "since 0.X.0" — and they
  must go into `RECORDED` with a reason, never be rewritten: a release whose
  evidence moved is a release nobody looked at. `RECORDED` is one dict, so add
  to the file's **existing** key rather than writing a second one. Python keeps
  the last duplicate key and discards the other in silence, and `ruff` does not
  flag it (checked: `F601`, `F602`, `F811`, `B035` all pass over it).

**So read this list as what has been met, not as what there is.** It has been
extended three times by things it was written about — the duplicate `RECORDED`
key, the home capture, and the dated heading that broke the image build — and a
list of traps assembled by walking into them is complete only up to the last
walk. Budget a pass of *run the gates, fix, run again* after the ritual you
mapped, and treat a new red there as ordinary rather than as evidence something
went wrong. **Every one of the four was there to be found by reading this file**:
the one that cost the most was the dated heading, written by somebody who had
read the gates section and the push order and not the changelog step. Read the
step you are about to perform, not the step that failed last time.

## Before the tag: moving the number

`version` in `pyproject.toml` is one line and **four edits**, plus a fifth on a
minor. Nothing here is
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

# 2. The five claims written by hand. Every occurrence in these five files is
#    a live claim about what is released, so a plain substitution is right here
#    and nowhere else.
sed -i '' 's/<old>/<new>/g' README.md docker/Dockerfile docker/README.md \
    plugins/digline/.claude-plugin/plugin.json .claude-plugin/marketplace.json
```

`tests/test_versions.py::LIVE` names those five and what it reads in each:
`README.md`'s `## Status` line, `docker/Dockerfile`'s `ARG DIGLINE_VERSION`,
the tag table in `docker/README.md`, and the Claude Code plugin's `version`
beside the `ref` its marketplace installs it from. The ref names a tag this
release has not pushed yet, so between the merge and the tag an install fails;
it points at a release, never at `main`, on purpose. `test_the_minor_tag_follows_the_release`
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

**5. On a minor, raise the example caps and relock the examples that carry a
lock.** Every `examples/*/pyproject.toml` pins digline under the next minor —
`digline>=0.20,<0.22` while the tree is on 0.21 — so a bump to `0.22.0` is
excluded by all of them, and
`test_examples.py::test_every_example_admits_the_versions_this_workspace_declares`
says so, naming the first. Raise the bound by one minor in every pyproject and
in any README that quotes it (`examples/langchain4j/README.md` does), then run
`uv lock` in each example that carries a `uv.lock`. Only the specifier line of
each lock should move; the version it resolves stays the newest the index
serves, because the new one is not served until the tag. Moving the locks to the
new version is still *After the tag* work.

**This step became mandatory on 2026-09-28, and the gate changed the ritual
without telling it.** On 0.21.0 the caps moved in the bump (`4785a9e`) and the
locks followed after the release (`c6d0fc5`, *Lock every example to digline
0.21.0*): a lock whose `requires-dist` still read `<0.22` against a pyproject
reading `<0.23` bothered nothing, because nothing installed it before the
post-release check. Since #196, `gates` runs `uv sync --locked` in every example
with a lock, and `--locked` refuses a lock that does not match its pyproject. So
the caps and the locks now move in the same pull request, or the bump
cannot go green. Found on the way to 0.22.0, where the step had never been
written: the test's own message cited this file for a rule this file did not
contain.

**Then one more, which no test reddens: say which decisions this release
ships.** Every record in `docs/adr/` carries `- Shipped:`, a core version or
`unreleased`:

```sh
grep -l '^- Shipped: unreleased' docs/adr/*.md
```

For each one whose implementation is in this release, write the new version
and make sure its status is `accepted`. **A record that shipped in part says
which part**: the version, ` — `, and what is not built, as ADR 0030 does from
0.21.0 on. Half a thing shipped is neither `unreleased` nor shipped. Those
records are out of the grep above for good, so sweep them too, and when the
rest ships, drop the qualifier and leave the version: it names where the record
*first* shipped.

```sh
grep -l '^- Shipped: [0-9][^ ]* —' docs/adr/*.md
``` Decide *is in this release* from the
tree being tagged, not from the changelog: a changelog cites a record when it
mentions it, and that is how ADR 0030 — cited in 0.19.1 as "accepted, not
implemented" — would have been given a version it never shipped in. `tests/test_adr.py` refuses a version
that has no row in `RELEASED` and a `proposed` record that names a version,
but it cannot see a record left `unreleased` after its code shipped — nothing
in the tree says honestly that a decision is in force, and a status derived
from the code would be a guess. This step is the only thing that sees it. It
was missed for 0020, 0021, 0022 and 0024, which read `proposed` for over a
week after 0.13.0 and 0.14.0 shipped them.

**And one more that no test reddens: raise the floors owed to this release.**
`tests/test_plugin_floors.py` computes a plugin's floor from the names it
imports. It cannot see a widened signature: a plugin that passes a new argument
to a function it already imported needs the release that added the argument,
and the gate still reads the old floor as enough. A floor may not name a release
that does not exist yet (*A floor names a core version*, below), so the pull
request that creates the need cannot write it. It writes a row here instead,
and the cut that settles the row deletes it.

| Package | Owed because | Raise to | Then |
|---|---|---|---|
| `digline-mcp` | `errors.translated` imports `refused_exit`, new in the core release that carries #414 (ADR 0041 §4.3) | `0.28.0` | release digline-mcp on its own tag, once the core is on PyPI, and drop `refused_exit`'s note in `test_plugin_floors.py` and RELEASING.md's `0.28.0` in `test_versions.py`'s `RECORDED` |

**An empty table is the normal state.** `test_plugin_floors.py` refuses a
package whose `pyproject.toml` says *Owed at the cut* while this table has no
row naming it, so the two cannot drift apart in that direction. The other
direction is this step's job: a row left here after its floor moved is a row
nobody finished.

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
That is the next section, and both are steps of the same pull request: the
table above is the part that belongs to the bump.

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

## Before the tag: the release commit is its own landing

**The tag does not point at the commit that built the feature.** It points at a
later one whose only job is to say the release happened — and today, 2026-09-23,
that shape was nearly missed: the feature had merged, every gate was green, and
the commit about to be tagged carried `## 0.19.0 — unreleased`. Tagging it would
have published a release whose own notes deny it shipped.

The precedent, and check it rather than trusting this paragraph: `v0.17.0` points
at **`b70c5d4`, *Release digline 0.17.0***, which is not the commit that wrote
any of that release's features. `a72a8c0` built one of them and wrote
`## 0.17.0 — unreleased`; `b70c5d4` dated it and touched `CHANGELOG.md`,
`docs/assets/home/home.json` and four example locks. Two landings, in that order.

So after the feature merges and before the tag, on a branch of its own and
through a pull request like every other change — **the tag then goes on that
pull request's merge commit**, once it is on `main` (*Tag the merge commit, and
nothing else*):

1. **Date every heading the tag carries**, core and each plugin, in one commit.
   `test_a_dated_release_leaves_no_package_declared_unreleased` is green while the
   core still says `unreleased` and goes red the moment you date it with a package
   left behind, naming the package.
2. **Regenerate the home capture**, which becomes due at exactly that moment and
   not before — see the rule above for why the two answers differ.
3. **Expect the image job to *skip* on this commit, and do not read the skip as
   a check that went missing.** That holds because the bump is **not** in
   this pull request: see *The bump and the release are two pull requests*
   below. `image-touched` builds only when the diff
   touches `docker/` or `ci.yml`/`docker-publish.yml`, and a release commit that
   dates the changelog and regenerates the capture touches none of them. On
   v0.21.2 it skipped, and that was correct.

   This step used to say to expect a **red** here. That is true of the *bump*
   commit — which does edit `docker/Dockerfile` and `docker/README.md`, so it
   does trip `image-touched`, and where dating is irrelevant because the heading
   is still `unreleased` — and of any build with no base to diff against, such
   as the weekly scheduled `ci`, where the substitution is switched off by the
   dated heading and the wait fails on a version the index does not serve yet.
   It was never true of the release commit, and it read as a defect in reverse:
   **a step that promises a signal which never arrives teaches people to stop
   reading the step.** The short post-tag red it was describing is real and
   heals when `publish` finishes; it simply arrives somewhere else. This is not
   the days-long window red described above either.

### The bump and the release are two pull requests, by construction

The version moves **at the cut**, not when the `— unreleased` section opens: a
bump made early makes every pull request in between declare a version the
index does not serve (ruled 2026-09-28, before 0.22.0). That can tempt you to
fold the bump into the release commit, and doing so breaks step 3 above. The
bump edits `docker/Dockerfile` and `docker/README.md`, so `image-touched`
builds. The release commit dates the heading, which switches `image_pins.py`'s
substitution off, so the build waits for a version the index does not serve yet
and fails. One pull request would put that red on the release pull request and
on the merge commit about to be tagged: a red that blocks nothing (the image job
is not required) and is guaranteed every time, which is the kind people learn
to stop reading.

So cut in two, back to back:

1. **The bump pull request**: *Before the tag: moving the number*, steps 1 to 5
   and the `Shipped:` sweep, with the heading still `— unreleased`. The image job builds and is **green**,
   because the substitution is still on: on 0.22.0's bump (#204) the job
   printed `digline==0.21.2   (the Dockerfile says 0.22.0)` and a note that
   0.22.0 *is declared unreleased … and the index does not serve it*, then
   waited for 0.21.2 and got it at once. Merge it as soon as `gates` is green.
2. **The release pull request**, branched from that merge: date the headings,
   regenerate the home capture, write the walkthrough line. The image job
   **skips**, and the tag goes on this pull request's merge commit.

**The window between them is minutes, and it is the only one.** For those
minutes `main` declares a version the index does not serve. That is the same
state the early bump held for days, and it is harmless for the same reason: the
heading says `— unreleased`. Nothing is tagged in between, and nothing should
be.

The reason this needs writing down at all is that the feature commit is *tempting*:
it is green, it is the change everyone was working on, and nothing about it
announces that it is not the release.

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
has run — and, since release tags are protected, is the procedure in *Re-doing a
tag*.

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
when the heading is dated, and `home_capture.py --check` right after it. They
are gates of the table above, arriving later rather than gates of their own.

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

## Before the tag: a control a person meets first in a browser

A control whose first user clicks is **seen working in a browser before the
tag**, by a person, and the tag waits for it. HTTP-level tests check the
headers a browser is sent. They cannot check what the browser does with them,
and that is the part every user meets first. A control proven header by
header and never seen working is a control nobody has used.

### The walkthrough for `digline view --allow-promote` (ADR 0033 §8)

Run it before a tag whenever the launch key, the hand-over or the promote
form has changed. First done on 2026-09-25, before the release that shipped
the key; the steps below are the ones that were run, plus the two things that walkthrough had to find out
for itself.

**What it needs, which the first version of these steps did not say:**

- **A store with at least two runs, one of them the baseline.** Otherwise there
  is no row to promote and step 3 cannot happen. The quickstart gives you one
  offline, with no API key, in a scratch copy so nothing in the repository
  moves:

  ```sh
  cp -r examples/quickstart /tmp/walk && cd /tmp/walk
  git init -q && git add -A && git commit -qm walk
  uv run --project <digline checkout> digline run --suite suite.py
  uv run --project <digline checkout> digline promote --suite suite.py --run latest --replacing none
  git add .digline && git commit -qm baseline
  uv run --project <digline checkout> digline run --suite suite.py
  ```

  **Commit the baseline before step 3, or step 3 loses its check.** Step 3
  reads the promotion in `git diff .digline/*/baselines/`, and steps 4 to 6
  read the refusals there too. An untracked `.digline/` shows as `??`, and
  `git diff` says nothing whatever happens. On 2026-09-30, for 0.24.1, the
  store above had no such commit. The promotion and the four refusals were read
  off the page alone, and `git diff` could not be run. The `git add` line is
  there for that reason.

- **The digline you are releasing, not one from PyPI.** Every command runs as
  `uv run --project <digline checkout> …`, with the checkout synced
  (`uv sync --all-packages`). Never from inside an example's directory: each
  example has its own `.venv`, which resolves digline **from PyPI**. Measured
  on 2026-09-25, the four such venvs in one checkout held, from
  `.venv/bin/python -c "import digline; print(digline.__version__)"`:

  | example | digline in its `.venv` |
  |---|---|
  | `langchain` | 0.4.0 |
  | `llamaindex` | 0.7.2 |
  | `operator` | 0.12.1 |
  | `prompt-first` | 0.18.0 |

  Four published versions, none of them the code being released, and no
  command's output says which one ran. The first walkthrough ran the wrong
  digline three times before the key appeared, and a released
  `view --allow-promote` prints *promotion enabled*, truthfully, while testing
  none of what is being released.

0. **Check which digline you are running, before anything else.** From the
   directory you will run the steps in:

   ```sh
   uv run --project <digline checkout> python -c "import digline; print(digline.__file__)"
   ```

   It must print `<digline checkout>/src/digline/__init__.py`. A path under
   `site-packages` is a published digline: stop. **`digline --version` is not
   the check until the version has been bumped.** Before the bump the checkout
   says the same number PyPI's latest does (they printed the same line on
   2026-09-25), so it passes in exactly the case it exists to catch. After the bump it says the
   unreleased number, and it is worth running too. And the startup line is the
   last check: if it has no `?launch=`, you are not running the code under
   test.
1. In that store, run `digline view --suite suite.py --allow-promote`.
2. Click the address the startup line prints. The page loads, and the address
   bar ends in `/`, **without** `?launch=`.
3. Press *Make baseline* on a row that is not the baseline. The page says
   *Baseline set to …*, and `git diff .digline/*/baselines/` shows the move.
4. The control, which is what makes step 3 mean anything: in a private window,
   open the bare `http://127.0.0.1:<port>/` and press *Make baseline* on
   another row. It is refused with a 403 naming the printed address, and the
   baseline file does not change.
5. Stop the server, start it again, and press *Make baseline* in the tab from
   step 2 without reopening the new address. Refused, and the baseline does
   not move.
6. **What must fail: the printed address, opened a second time** (since
   0.21.1, ADR 0033 §11). After step 2 of a fresh start, paste the *same*
   address step 2 opened into a private window. All three of these must fail:
   - **The address itself is refused.** A 403 saying it *has already been
     opened*, and no runs page behind it.
   - **The button is refused.** Go to the bare `http://127.0.0.1:<port>/` in
     that window and press *Make baseline*: a 403 saying the request *carries
     no cookie from this server*.
   - **Nothing moves.** `git diff .digline/*/baselines/` shows nothing.

   **If any of the three succeeds, stop: the tag waits.** A working button in
   that window means the key was not spent. That is 0.21.0's K-1 exactly: the
   browser's history keeps this address, so anything that reads the history can
   do what that window just did. Step 2 is where the address has to work; this
   step is only the refusal, and a refusal is the only result that passes it.

Do it in the browser you use, and in a second engine if you have one. `SameSite`
is where engines have differed. If step 3 is refused, the release is wrong, not
the browser, and ADR 0033 is reopened before anything ships.

**Where it is recorded: the release's own changelog entry, whichever way it
went.** The tag waits for the walkthrough, and until 0.21.1 nothing kept
that it ran. 0.21.0's entry says so because somebody wrote it; 0.21.1's said
nothing, although the walkthrough had run, until a dated note was added on
2026-09-28. If the tree does not say it, nobody knows. So the release pull
request (*the release commit is its own landing*), which dates the entry,
also carries one of two lines:

- **It ran.** Say when and which steps, and what each control did, as
  0.21.0's *Seen working in a browser* bullet does. If the exact date is not
  known, write the window it fell in. Do not guess a date.
- **It was not owed.** Say so in one line, and say why: nothing in the
  launch key, the hand-over or the promote form changed since the last
  release that ran it. **The absence is declared, never left to be read.**
  Without that line, *not owed* and *skipped* look the same in the entry.

No test reads either line, on purpose. A check that the sentence exists would
teach writing the sentence, which is the reason given under *These three have
no gate, and must not be given one*. It is a record, and the person who ran
the walkthrough is the only one who can make it true.

## Before the tag: the gates

Run **exactly what CI runs**, from the repository root:

```sh
uv sync --all-packages --locked
uv run pytest -q -m "not live" -n 4 --dist loadgroup --ignore=tests/test_type_gate.py
uv run pytest -q -m "not live" tests/test_type_gate.py
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run python tools/home_capture.py --check
uv run python tools/example_locks.py
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

The Dependabot alerts are a second list, and nothing else in the release reads
them:

```sh
gh api repos/digline/digline/dependabot/alerts --paginate \
  -q '.[] | select(.state == "open")
      | "\(.dependency.package.name)  \(.dependency.manifest_path)  \(.security_advisory.ghsa_id)  fixed: \(.security_vulnerability.first_patched_version.identifier // "none")"'
```

An open entry with a `fixed:` version is owed an `--upgrade-package` that names
it, before the tag: neither Dependabot's version updates nor the example locks'
regeneration after the tag will move it (*After the tag*, step 3, *Dependabot
moves only what a manifest declares*).
An entry with `fixed: none` stays open with its reason written on it.

## Before the tag: the site

The gates above check this repository. This one checks the **other** one, and it
is here because skipping it is what v0.3.0 cost.

```sh
git clone https://github.com/digline/digline.dev ../digline.dev   # once
cd ../digline.dev && uv sync
make preview DIGLINE=../digline
uv run tools/check-glyphs.py site
```

The second line reads the build the first one made: every character a page
shows must be in the site's font subsets, which `mkdocs build --strict` does not
check. It is the `glyphs` job in `ci.yml`, whose comment says what a green there
does not cover.

**When, and it is not where you would put it: after the last *docs* edit, not
after the last *code* edit.** This check reads `docs/`, `CHANGELOG.md`,
`ROADMAP.md` and one page per `examples/*/README.md`. None of those is code, so
the moment the gates above go green is the wrong moment to run it — what
decides whether it still holds is the last prose written, and on a release the
last prose is usually written *after* the code is finished, in the commit that
carries the fix or in the changelog entry that describes it.

**So `make preview` before the tag does not cover an entry written after it.**
That is not a hypothetical: on digline-mcp 0.1.4 this check ran, passed, and
the `Security` entry was then written into `CHANGELOG.md` in the commit that
carried the fix — with a relative `](SECURITY.md)` link, which resolves on
GitHub and is not a page on the site. `mkdocs build --strict` aborted and the
`docs` job went red on `main`, after a check that had genuinely looked and had
genuinely been green when it looked.

Run it again whenever a docs file moves after it, which on most releases means
**last, immediately before the tag**, and always again after writing a
changelog entry. The `docs` job is **not** a required check on `main`, and
*Queued for the next site push* below is why it cannot be one. Since 2026-09-23
there is no longer a push that lands some other
way either — `main` refuses a ref whose `gates` have not passed (`CLAUDE.md`
§ Conventions) — so a red `docs` reaches `main` only through a merge somebody
chose. It does not make the timing optional: a green that looked at the wrong
tree is still green, which is why this has to be run at the right moment rather
than merely run.

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

Since 2026-09-23 "land" means the same thing in both: **push the branch, open a
pull request, wait for green, then merge.** Here, since 2026-09-29, "merge"
means enqueue. The queue runs the gates once more and lands the commit about
three minutes later, so "digline has landed" is the pull request reading
`MERGED`, not the enqueue returning. `main` here is protected by a
ruleset nothing bypasses — a pull request (zero approvals), the three `gates`
checks on the ref, and the branch up to date before merging — so a direct push
is refused and `git push origin main` is not a step in this file. The ruleset
has required the pull request only since 2026-09-24; it was needed before that
anyway, because `ci.yml` runs on `pull_request` and on pushes to `main`, so a
branch push produces no checks, and a ref with no checks cannot land. `CLAUDE.md` § Conventions is the
rule and says why. What it changes is only how each of the two pushes below
reaches its default branch; the order between the two repositories is
unaffected, and is still this one.

- `digline.dev`'s `main` requires a pull request **and** a `Build` check, and
  `docs.yml` checks out `digline/digline` at its **default branch** when no
  dispatch payload names a ref. So a site pull request carrying a nav entry
  **cannot go green** until the page is on this repository's `main`. Site-first
  is not risky, it is impossible.
- The window between the two merges is the one time that asymmetry costs
  something. A tag dispatched while the site's entries are still in a pull
  request rebuilds nothing: the site goes on describing the previous version
  until somebody merges them, and the red run reads as a broken release rather
  than as a wait somebody planned. Nothing is lost and no re-tag is needed —
  that merge rebuilds the site from the tag — so the `site_nav` job in
  `publish.yml` **says so and does not stop anything**. It compares this tag's
  `docs/adr/` against the site's nav, with the token it already has, and warns
  naming the records the site cannot show yet. It cannot block: it runs after
  `pypi`, where everything irreversible has already happened, and a failure
  there would stop nothing while making a foreseeable wait look like a defect.

- This repository's `main` requires `gates (3.12)`, `gates (3.13)` and `gates (3.14)`, and
  **nothing else**. The `docs` job — `The site still builds from these docs`,
  which clones the site and builds it — was required from 2026-09-22 and is
  **not** required since 2026-09-23. `gates` does not set
  `DIGLINE_SITE_CONFIG`, so `tests/_site.py` skips there and the two nav checks
  never run; `docs` is where they run for real.

**Why the `docs` job cannot be a required check here, which is the rule and not
a concession: a check that the documented process guarantees will be red cannot
be a required check.** The two bullets above are that guarantee. A site entry
cannot land before the page (bullet one), so between the two merges the page is
on `main` with no nav line — and that is the state the nav gate is built to
fail. Requiring it would mean no ADR and no docs page could ever land, because
each side is waiting for the other. Under the ruleset that required it the
deadlock was latent rather than harmless: `main-protection` exempted the
repository's admins with `bypass_mode: always`, so the requirement **never once
bound anybody**, which is why nobody met it. It was deleted rather than
reshaped; its payload is in the commit that deleted it — *Fold the two rulesets
into one, and record why the docs job is not among them* — so restoring it
verbatim is one `gh api -X POST repos/digline/digline/rulesets` call.

And the correction that finding turned up: **merging here first *is* seen by the
nav gate, contrary to what this section used to say.** The pull-request build is
`make preview`, where `MKDOCS_OMITTED_FILES=info` lets a page with no nav line
through — but `ci.yml`'s step *The nav gates, where they may not skip* then runs
`test_every_adr_has_a_page_in_the_site_nav` with `DIGLINE_SITE_REQUIRED=1`
against a fresh clone of the site, precisely because the preview build lets it
through. So `docs` is red on the pull request that adds the page, one merge
earlier than this file used to claim, and stays red on `main` until the site
entry lands. That blocks no merge (it is not required), no release and no
deploy: a failed site build does not deploy, and the live site keeps serving what
it already had. Close the window, then re-run `docs`.

**The open piece that would let the check be required again**, named here
because deleting a ruleset should not read as giving up a protection when what
it removed was an unusable one. Teach the pull-request nav gate to tolerate a
page **added by the pull request under test** while still failing for a
pre-existing page with no entry — the diff against the base ref is what
separates the two, and only the second is somebody's omission. The deadlock goes
with it and `docs` can join the required list. Not started, and it is not a
release step.

**What the requirement covers, and what it does not.** It covers the files this
repository sends to the site — `docs/`, `CHANGELOG.md`, `ROADMAP.md`,
`docker/README.md`, `examples/*/README.md` — and it refuses what `--strict`
refuses in them: a relative link that resolves on GitHub and not on the site, a
dead anchor, a nav entry pointing at nothing, a hook's `PluginError`. It does
**not** cover the site's own orphan pages: `omitted_files` is `info` on a pull
request here, and a page of digline.dev's that no nav entry lists is
digline.dev's `Build` to catch, not this one. Three site builds broke on
2026-09-22 — ADR 0028 with no nav entry, a chapter that grew the Handbook, and
a relative `SECURITY.md` link in the changelog — and all three came from this
side of the line.

**When the site is red for its own reasons.** The `docs` job checks out
digline.dev's default branch as it is, so a site that cannot build turns `docs`
red on every pull request here. That blocks no merge — `docs` is not a required
check, for the reason above — but it hides the next real red behind a known one,
so repair the site first: nearly always the right fix, and usually a minute.

**There is no way round a red required check, and there is not meant to be.**
This paragraph used to offer `gh pr merge --admin`, over a `RepositoryRole:
always` bypass kept for the purpose. That bypass is gone: the ruleset's
`bypass_actors` is empty, and `--admin` is refused like any other merge. When
a `gates` check is red, the remedy is to fix what reddened it —
the code, or the check if the check is wrong — on a branch, through a pull
request, like every other change. Suspending the requirement is not a remedy
either: it is the thing nobody remembers to restore.

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

CI also runs the gates on **3.12, 3.13 and 3.14**. One locally is enough before
a tag — the others are what CI is for — but a failure on one version alone is
a real failure, not a runner quirk. #365 was a defect on 3.14 alone.

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

### Tag the merge commit, and nothing else

**The tag goes on the merge commit of the release pull request, once it is on
`main`.** Not on the release commit on its branch, not on a branch head, not on
anything `main` does not contain. `main` is protected — a pull request, the three
`gates` checks on the ref — and a tag is not: before this rule a tag on an
unmerged branch would have built, uploaded and spent the version number from
code no gate had passed.

```sh
git fetch origin
git log --oneline -1 origin/main        # the merge commit of the release PR
git merge-base --is-ancestor <sha> origin/main && echo on-main
git tag -a v<version> -m "<every package the run publishes>" <sha>
git push origin v<version>
```

**`publish.yml` and `docker-publish.yml` refuse any other commit.** Their first
job, `on-main`, runs `.github/on_main.py`, and every job that builds or publishes
waits for it (`tests/test_release_from_main.py` fails if one does not — including
a job added later, which is recognised by what it does, not by its name). What
it actually checks is *is the tagged commit an ancestor of `origin/main`*; that
also admits the release branch's head once the pull request has merged, and an
older commit on `main`. The rule above is stricter than the check, on purpose:
the merge commit is the one `gates` ran on as `main`.

It does not refuse over a race. A commit that is not on `main` yet is fetched
again, then looked up with `GET /repos/digline/digline/commits/<sha>/pulls`, and
only then refused, with one of three messages. Each names the tag and the SHA:

| The red says | It means | Do |
|---|---|---|
| `not on main` | no pull request into `main` carries the commit, or only one closed without merging | the tag is wrong: re-do it on the merge commit (*Re-doing a tag* below) |
| `head of open PR #N: merge it, then tag the merge commit or re-run` | the tag went on before the merge | merge #N; then either re-run the failed workflow — the tagged commit is now on `main` — or re-do the tag on the merge commit, which is the rule |
| `on merged PR #N but main does not show it yet: re-run` | the merge and the tag raced, and `main` had not propagated | re-run the failed jobs (`gh run rerun <id> --failed`); nothing needs re-tagging |

A false red is the moment somebody is tempted to switch a guard off. None of the
three is a reason to: each says what to do instead, and none of them needs the
job removed.

**Exercised, and this line is what the check asked for.** It landed 2026-09-26
carrying an instruction to confirm the job on the first release after it and
then delete itself. That release was `v0.21.0`, and `v0.21.1` followed: in
both, `publish` and `docker-publish` each carry an `Is this commit on main?`
job that ran and passed — `publish` runs `36311430504` and `36319030686`,
`docker-publish` run `36319030731`. Read job by job, not from a run's rollup:
a green run whose job list lacks it is not the same evidence, which is the
whole reason the instruction existed. Confirmed on the way to 0.21.2, two
releases after it was owed.

### Re-doing a tag

**Release tags are protected.** The tag ruleset `release-tags` on
`digline/digline` covers `refs/tags/v*` and `refs/tags/*-v[0-9]*` — the two
shapes `publish.yml` fires on, written as the `pypi` and `testpypi`
environments write them — with the rules `deletion` and `update` and an empty
bypass list. Creating a tag is free; deleting one or moving it is refused, for
everybody. A re-tag is therefore a change to the ruleset, and it is written here
because it is needed in the middle of a release that has gone wrong, which is
the worst moment to work it out.

**First: can it be re-done at all?** Only until the `pypi` job has uploaded. A
version on PyPI is spent, and a re-tag after that re-releases nothing — cut the
next version instead. Check the run's `pypi` job before touching anything.

```sh
repo=digline/digline tag=v<version>

# 1. Stop what the old tag started, so nothing publishes while you work.
gh run list --repo $repo --branch "$tag" --json databaseId,workflowName,status
gh run cancel <id> --repo $repo            # each one still running

# 2. The ruleset, as it is now. Keep the file: it is what step 5 compares to.
id=$(gh api repos/$repo/rulesets --jq '.[] | select(.target == "tag") | .id')
gh api repos/$repo/rulesets/$id > /tmp/release-tags.before.json

# 3. Suspend it, delete the tag, and restore it — in that order, with nothing
#    in between. Creating the new tag does not need the ruleset off.
gh api -X PUT repos/$repo/rulesets/$id -f enforcement=disabled --jq .enforcement
git push origin ":refs/tags/$tag"
gh api -X PUT repos/$repo/rulesets/$id -f enforcement=active --jq .enforcement
git tag -d "$tag"

# 4. Tag the merge commit, as above, and push it.
git tag -a "$tag" -m "<every package the run publishes>" <sha>
git push origin "$tag"
```

**5. Confirm the ruleset is back, by reading it — not by remembering step 3.**

```sh
gh api repos/$repo/rulesets/$id --jq \
  '{enforcement, rules: [.rules[].type], include: .conditions.ref_name.include, bypass: .bypass_actors}'
```

Expect `"enforcement": "active"`, `rules` `["deletion", "update"]`, the two
patterns above, and `bypass` `[]` — the same as `/tmp/release-tags.before.json`
said. A ruleset left disabled is the failure this step exists for: nothing
reddens, and the next tag is unprotected. Then `gh run list --limit 3` to
confirm `publish` started for the new tag.

Why suspend the whole ruleset rather than add yourself to its bypass list: a
bypass entry is a line somebody has to notice is still there, and the state to
check afterwards is then a list; `enforcement` is one word, and step 5 reads it.

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

### Not built: a package whose text moved under a version the index serves

**`tag_names.py` asks which *versions* the index lacks, so it cannot see a
package whose shipped files changed while its version did not.** Such a package
is served already, the run uploads nothing for it, and the new text reaches
nobody who installs it. The version-literal gate cannot see it either: it
watches numbers, not what the numbers ship.

It happened on the way to `v0.21.0`. `digline-mcp`'s `list_runs` playbook
stopped letting an agent run `digline migrate` (d8cbbeb) after 0.4.0 was on
PyPI, and the version stayed 0.4.0. Run against that tree, `tag_names.py` listed
`digline 0.21.0` alone and exited 0, while the changelog said every agent-facing
surface carried the change. It was caught by reading, and 0.4.1 was cut for it.

**The proposed check**, in `tag_names.py` because that step already talks to the
index and already runs before every tag: for each workspace package whose
version the index serves, download that wheel, build one from the tree, and
compare the importable files — the wheel minus `.dist-info`. Any difference
refuses the tag and names the files. **On that tree it would have named
`digline_mcp/descriptions.py`**, and that is the control that must fail when it
is built: at `bc8eb16`, the first parent of `v0.21.0`'s commit, `digline-mcp`
still says 0.4.0 over the new text, and the check has to refuse there.

- **The built wheel, not a git diff.** A diff against the tag that published a
  version needs the tags, which a shallow CI clone does not have, and it needs
  the prose *Published by … tag* line to find the tag at all.
- **`.dist-info` is reported and not refused.** A change there alone is
  metadata, and metadata rides a package's next real release rather than
  earning its own.

Until it is built, the check is a person: before tagging, for each package
`tag_names.py` does **not** list, ask whether anything under its `src/` changed
since the tag that published its version.

**A change that alters nothing that runs and nothing a user reads rides the
package's next real release, and is not re-decided at every tag.** The
condition decides it, not the size of the diff. The typical case is a type
annotation, or an import under `TYPE_CHECKING`, in a module with
`from __future__ import annotations`. The installed code behaves identically,
and nothing a user reads changes. Such a change goes in the list below once,
with its package and its commit. At each later tag the check above only
confirms that the diff since the publishing tag is still exactly that. **Any
other change under that `src/` reopens the question**, and so does a change
that turns out to reach a message, a docstring a tool prints, or anything
executed. It is the same rule `.dist-info` follows above, applied to source
text: a release has to be earned by a change a user can meet.

Ruled 2026-09-30, after four releases in a row had given the same answer to
the same diff: v0.22.0, v0.23.0, v0.24.0 and v0.24.1.

Carried today: **nothing.** The list's first entry was `pytest-digline` 0.2.0,
published by `v0.19.0`: `1653ce6` changed `plugin.py` on two lines, an import
under `TYPE_CHECKING` and one annotation. It rode `pytest-digline` 0.2.1, a
real release for the refusals the delta-pass over 0.25.1 found, and came out
of this list then, as the entry said it would.

### A floor names a core version, so the core publishes first

**Not negotiable, and it is an ordering rule rather than a waiting one.** When a
plugin's `digline>=` floor names a core version, that core is published before
the plugin — or a user installs a plugin whose floor names a version that is not
there, and `pip` refuses to resolve it. The tag sweep above already does this
when both ride one tag: the core uploads in the same run and the index waits
cover propagation. What the rule forbids is the other shape — a plugin released
on a named tag of its own, ahead of the core release its floor points at.

The floor gate (`tests/test_plugin_floors.py`) catches the floor that is too
*low*. Nothing in this repository can catch a floor that is correct and
published too *early*: the failure is about which versions the index serves, and
no test here asks the index that question. This paragraph is the control.

It is why a floor may not name a release that does not exist yet, which
`packages/digline-mcp/pyproject.toml` says beside its own floor.

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
So a fix merged into `main` does not reach a re-run of an older release — for that
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

## Signatures on the GitHub release

From the first release after 0.19.1, the last step of `github-release` attaches
a `.sigstore.json` for every file the tag put on PyPI. They are **PyPI's own signatures**, not new
ones: `pypa/gh-action-pypi-publish` makes a PEP 740 attestation for every
upload under trusted publishing, and `.github/release_bundles.py` turns the ones
signed from this tag into bundles, which `sigstore verify github --ref` then
checks against the file PyPI serves before anything is attached. What it is
for: OpenSSF Scorecard's Signed-Releases looks only at a release's files, and
until this it saw none. It is the one Scorecard check we can move; the others
that score low are capped by there being one maintainer.

**Signatures, never packages.** Somebody will propose attaching the wheels and
the sdist too, "for completeness". The answer is no, and this is why. The
packages would make a second place serving the same bytes as PyPI, and nothing
would notice the day the two diverged — and they already diverge, because
**every tag rebuilds every package and `hatchling` is unpinned**
(`requires = ["hatchling>=1.27"]`), so the same version number can be built
from different source. Measured on 2026-09-24 by rebuilding `v0.19.1` and
comparing against PyPI's digests: the two files that tag published (the core's
wheel and sdist) came out identical, and of the ten older plugin files it
rebuilt, four did not — three
because the builder moved (`Generator: hatchling 1.32.3` on PyPI, `1.32.4` in
the rebuild), one because `digline_bedrock-0.5.1.tar.gz` now carries a test
added after 0.5.1 shipped. That is true whether or not anything is attached,
and it is the reason `dist/` is authoritative **only for the files its own run
uploaded**: the script reads `dist/` for names and versions, never for bytes. A
signature names the served file by digest and leaves PyPI the only place that
serves it, so the invariant "the release holds the bytes PyPI serves" never
comes into existence and nothing has to guard it.

Which files are this tag's is read from the signing certificate, which names
the ref the upload ran from — not from `to-publish/`, which a re-run finds
empty. The script **refuses**:

- **an empty list.** A job that attaches nothing and passes is the check that
  cannot fail, and the release would go out unsigned with a green on it.
  Anticipated rather than discovered.
- a file at the tag's own version with no attestation, or one signed from
  another ref;
- served bytes that do not match PyPI's own digest, or an attestation naming
  another repository or workflow.

A re-run writes the same bytes — `tests/test_release_bundles.py` pins it —
which is what makes `gh release upload --clobber` safe. **Safe for what it
uploads, not free:** it moves `publish` to a new attempt, and the approvals
endpoint forgets attempt 1. `release-followup` keeps its reading for exactly this
case; see *After the tag*, the reviewer gate.

**It waits for PyPI itself, because no other wait asks its question.** The
`pypi` job's wait (`await_index.py`) asks `/simple/`, which is what `pip`
resolves from. This script asks `/pypi/<name>/<version>/json` and then
`/integrity/…/provenance`, and the JSON page answered 404 behind `/simple/`
three times. On v0.21.0 that was ten seconds after the `pypi` job went green,
on v0.22.0 43 seconds after the upload, and on v0.23.0 36. *Corrected
2026-09-30: this said "twice", and v0.21.0's own Status entry records the
first.* Each time a single read took the 404 for an absence and refused, and the
re-run was what attached the signatures. So every read now asks again until it
answers or `TIMEOUT` (600 seconds in `publish.yml`) runs out, and it ends in
one of three words:
- **an answer**;
- **absent**, a 404 that held to the last read, which is refused as before;
- **unread**, an index that never answered, which exits **2** under *Signatures
  not judged*.

A re-run is the remedy for the third, and it is not a refusal, because nothing
was learned about the release. `tests/test_release_bundles.py` holds the wait
with a control: the same lagging index read once (`TIMEOUT=0`) is refused, and
the tests written for the wait fail against the script before it.

**Rehearsed by hand on `v0.19.1`, 2026-09-24,** before CI depended on it: two
bundles (the core's wheel and sdist), ten plugin files skipped by the tag that
published each (`v0.17.0`, `v0.15.0`, `v0.19.0`), both verified against the
served files, a control with the wrong ref refused, a second run
byte-identical, and the downloaded attachments identical to what was uploaded.

Not covered: a plugin released on its own tag has no GitHub release, so no
signature there; and Scorecard's 10 needs a SLSA `.intoto.jsonl`. Renaming a
bundle to that suffix would pass a check that reads names only, and is not
done.

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

The same `RUN` mounts that file a second time, as
`/tmp/index_capture/sitecustomize.py`, on the `PYTHONPATH` of the `pip` command
alone. That is the other half of the capture below, and it rides the same gate.

### The diagnostic, built — read two lines, not a log

**The four fields this was specified with would have measured the wrong thing,
and finding that out is what building it bought.** The specification was
`X-Served-By`, `X-Cache`, `Age` and the time, for both requests: on the reasoning
that two different servers in `X-Served-By` would confirm per-server luck and one
server would refute it. Measured on 2026-09-25, **two different edge servers is
the ordinary case** — see *The control* below: the wait and `pip`, 1.1s apart in
one `RUN` on a build where nothing was wrong, were answered by two different
Fastly edges holding the identical page. So `X-Served-By` differing carries
almost no information, and a reading built on it would have confirmed the
hypothesis on the first divergence it met, whatever the cause.

**The discriminator is `X-PyPI-Last-Serial`**, which was not in the
specification and costs nothing: it is PyPI's own monotonic counter of a
project's state, on the same response. It says *older* rather than merely
*different*, and it says it independently of routing — a lower serial on pip's
side is a stale snapshot whichever server sent it. `ETag` comes with it, for
free, and settles whether two pages are byte-identical. So the capture records
six fields, not four, and the two that decide it are the two that were not
asked for.

What follows from that is the table below: per-server luck is confirmed only by
`via` **and** `serial` moving together, and refuted by one server giving two
answers. The next reading is then a lookup rather than an argument, at the one
moment — mid-release, on a red — when nobody should be having the argument.

v0.20.1 was the condition this was kept ready for: `served digline==0.20.1` and
then, a second later in the same `RUN`, a version list ending at 0.20.0 —
**after** the same-question fix, so the variant is ruled out and per-server luck
is the one hypothesis left. Built 2026-09-25.

**One line shape, two producers.** Both halves print an `index-capture` line, so
a reading is a field-by-field comparison of two lines and not an archaeology of
a build log.

**The control, and it is from the real path.** This is the pair the paragraph
above rests on, taken from `ci`'s `image` job on PR #132 — the first build to run
this at all — and not from a laptop. One `RUN` (`#9`), the in-build wait and then
`pip`, on a build where **nothing was wrong**:

    index-capture side=wait name=digline t=2026-09-25T12:09:27.6Z took=0.025s
      status=200 variant=json serial=41442088 etag=r39LI8WAzV7Tls9SLWeqaA
      age=- cache=MISS,HIT
      via=cache-iad-khef600091-IAD,cache-iad-khef600091-IAD,cache-iad-kiad7000081-IAD
      versions=39 asked=0.20.1 served=yes
    index-capture side=pip  name=digline t=2026-09-25T12:09:28.7Z took=0.004s
      status=200 variant=json serial=41442088 etag=r39LI8WAzV7Tls9SLWeqaA
      age=- cache=MISS,HIT
      via=cache-iad-khef600091-IAD,cache-iad-khef600091-IAD,cache-iad-kcgs7200037-IAD
      versions=- asked=- served=-

(One line each; wrapped here to fit. `#9 1.503 Collecting digline==0.20.1`
follows, and `#9 8.626 Successfully installed … digline-0.20.1 …`.)

**Same object, different third node, 1.1 seconds apart, in one `RUN`.** The
`serial` and the `etag` are identical — one page — while the last hop of the
`via` chain is `kiad7000081` for the wait and `kcgs7200037` for `pip`. That is
row three of the table below, and it is the sentence that makes the table
readable: **different edge servers is what agreement looks like.** Not a
coincidence of one healthy build either — it is the same gap, in the same place,
that failed on v0.15.0 and v0.20.1, and the pip here is the image's own 25.0.1.

Which is why the four fields this was specified with would have read this build
as per-server luck. Keep the control: without it a divergence has nothing to be
compared against, and `via` alone would confirm the hypothesis on any red at all.

**How to read it.** Take the `side=wait` line for the pin and the `side=pip`
line for the same `name`, in the same `RUN`:

| `via` | `serial` / `etag` | Reading |
|---|---|---|
| differ | differ | **per-server luck confirmed** — two servers, and pip's is the older object |
| same | differ | **per-server luck refuted** — one server gave two answers; the question moves to the object, not the routing |
| differ | same | the routine case above: two servers, one object. Not the failure |

Row three is the control and will be most of what the logs hold. Row one is the
only row that confirms, and it needs **both** halves of the evidence — which is
the whole correction above: `via` alone was never going to be one of them.

**Where it lives, and why not in a step of its own.** Half one is in
`.github/await_index.py`, on every request it makes. Half two is the *same file*,
bind-mounted a second time as `/tmp/index_capture/sitecustomize.py` and put on
the `PYTHONPATH` of the Dockerfile's `pip` command alone, where `site` imports it
before pip's first line runs; it then reports each `/simple/` page pip resolves.
A step of its own could only make a **third** request, after the fact, to
whatever server answers next — and the failure is a disagreement between the two
requests that already happened. Nothing about pip changes: no proxy, no index
URL, no headers, no extra request.

**What it costs on a normal run**, which is the question that decides whether it
can exist at all. It is **always on wherever it runs**, because the observation
that has to be compared is the `served` one *preceding* the failure, and nothing
knows a failure is coming when that request is made. A capture armed by the
failure can only ever describe one of the two requests. So:

- the wait prints one line per pin per poll — **four** lines where the index is
  already ahead, **44** on a wait like v0.20.0's (eleven polls × four pins);
- pip's half prints one line per project page it resolves — **33** for the
  image's four pins, its own self-check and every transitive dependency
  included. Predicted with pip 26.2.1 before the first build, then **counted as
  33** in PR #132's `image` job, on the image's own pip. A number with a check
  attached, rather than a green standing in for one;
- **no extra HTTP request and no extra second of wall time** on either side:
  both read headers off a response that was going to be read anyway;
- both halves ride the existing `AWAIT_INDEX_TIMEOUT` gate, so a local
  `docker build docker/` waits for nothing and prints nothing, exactly as
  before. `tests/test_docker.py` holds the three release builds to turning it
  on, because a diagnostic that is silently off is the failure mode here.

**What it does not do.** It does not read the body of pip's request: consuming
that stream would break the install, and a diagnostic that can become the
outage it was to explain is not one to put on the release path. So `versions` is
`-` on pip's side, and the three things that stand in for it are exact — `etag`
(the same object), `serial` (which snapshot), and pip's own `(from versions: …)`,
which it prints itself in the case that matters. It also covers `pip` only: the
runner-level consumers resolve with `uv`, and the divergence has never been seen
anywhere but inside the build — which is also the one place both requests are in
the same `RUN`, and so the only place they are comparable.

### Status: what each path has proven

This is the part that changes from release to release. Step 4 of *After the
tag* updates it on every tag, and step 6 is what puts the capture's reading in
it — including the sentence that says the capture ran and found nothing, which
is the one a quiet log cannot supply.

- **digline-anthropic-v0.6.1 — one package, and the warning at the gate came
  after the click.** It shipped #392's repair: a US-only reply priced at 1.1x.
  `publish` (`37124536845`) passed on attempt 1. `github-release` and the site
  jobs were skipped, as on any plugin tag, and `docker-publish` did not run.
  - **`tag_names.py "digline-anthropic 0.6.1"`** ran on #418's merge commit,
    `2e67e42`, which was `origin/main`, immediately before the tag. Its whole
    output was read: one package, named, *"the message names every one of
    them"*, exit 0.
  - **The check a person makes until it is built.** No other package's `src/`
    moved since the tag that published its version: 0 files each for
    digline-openai 0.5.2 (`v0.17.0`), digline-bedrock 0.6.1 (its own tag),
    digline-mcp 0.4.3 (`v0.26.0`) and pytest-digline 0.2.1 (its own tag). The
    core's `src/` had moved since `v0.27.0` (#413, #416). That rides the next
    core release, and this tag did not publish the core.
  - **The reviewer gate held, and the session's warning came after the
    click.** `/approvals` reads `approved` by `alexpran` on `pypi`, and the
    environment reads `can_admins_bypass: false`. The `pypi` job was created,
    and so began waiting, at 12:59:04, and started at 12:59:14. The session
    watched with a poll every 20 seconds and never saw the waiting state, so
    the counts reached Alessandro after he had approved.
  - **The cause, which is worth more than the miss.** Those ten seconds were
    not a window of the workflow. They were the time to the click. On
    digline-bedrock-v0.6.1 the same wait lasted 76 seconds (14:39:13 to
    14:40:29), and the session reported in time. A watch that polls cannot
    promise to see a state that lasts exactly as long as the reviewer takes,
    and GitHub notifies the reviewer itself. The wait did not go wrong. It was
    too slow for that window, and any poll is a race against the person it
    exists to inform.
  - **The counts, read after the click from the finished jobs:**
    - 12 `twine check` `PASSED` in the build, then 2 on `to-publish/`;
    - TestPyPI's selection, and PyPI's, 2 `publish` and 10 `skip`. The two are
      `digline-anthropic` 0.6.1, wheel and sdist. The ten are the five other
      packages, each already on the index;
    - `imported 6`, and the quickstart's 3 calls, after TestPyPI and again
      after PyPI.
  - **On PyPI:** uploads at 12:59:30.5 and 12:59:31.7. The run's wait saw
    0.6.1 served `after 10s`. The version endpoint answered 200, and its
    control, `/pypi/digline-anthropic/9.9.9/json`, answered 404.
  - **Step 3 had work, for the first time on a plugin tag.** `langchain`,
    `llamaindex` and `prompt-first` locked `digline-anthropic` 0.6.0, and kept
    pricing a US-only reply low. Each moved to 0.6.1 with `--upgrade-package
    digline-anthropic`, three lines per lock and nothing else. `ci.yml` is
    dispatched once that lands. **Step 5 had nothing to do:** no committed
    report names digline-anthropic.

  **The next tag must show** the counts in front of the reviewer before the
  click, by a mechanism that does not race the click. Until there is one, a
  [GATE] that a session announces by polling is a courtesy, not a stop.

  *Corrected 2026-10-04, the paragraphs above kept as written.* They read the
  late warning as a miss, and the cause as new. Neither was. On 2026-10-02, at
  v0.26.0, *After the tag* ruled that **the counts come after the click**,
  after three releases in a row where the approval had come first (v0.25.2,
  v0.25.3, v0.26.0), and v0.25.3's entry already says *"a shorter poll does
  not fix that, because the reading takes longer than the click"*. So the
  session followed the rule, and the record should have cited it. What this tag
  adds is the contrast: 76 seconds of waiting on digline-bedrock-v0.6.1
  against 10 here, both the reviewer's time. The mechanism the paragraph asks
  for is the job summary. It followed this tag, and *After the tag* says what
  it writes.

- **v0.28.0 — the first tag with the counts in the job summary, the pair
  agreed for every pin in both builds, and the smoke build waited for the
  upload again.** `publish` (`37283374437`) and `docker-publish`
  (`37283374287`) both passed on attempt 1, `github-release` and the site jobs
  included. `tools/tag_names.py "digline 0.28.0"` ran on #439's merge commit,
  `ea8a1b3`, immediately before the tag: one package, named, exit 0.

  **The reviewer gate.** `/approvals` reads `approved` by `alexpran` on `pypi`,
  and the environment reads `can_admins_bypass: false`. The `pypi` job started
  at 08:28:18. **The counts reached the approver before the click this time**,
  in the session's message, read from the finished jobs' logs while the run
  waited:
  - 12 `twine check` `PASSED`;
  - TestPyPI's selection, and PyPI's read before the gate, 2 `publish` and 10
    `skip`. The two are `digline` 0.28.0, wheel and sdist;
  - `imported 6`, and the quickstart's 3 calls.

  The steps that write the job summary (`gate_summary.py`, *What PyPI would
  take, read before the gate*) succeeded in both jobs. The check-run API
  carries no summary, so this session could not see what the page showed
  beside *Review deployments*. Whether it was visible there is the approver's
  to say, and it is not recorded here yet.

  Uploads landed at 08:28:39.5 and 08:28:41.5. The version endpoint answered
  200 and its control, `/pypi/digline/9.9.9/json`, answered 404.

  **The index race, both builds.**
  - **The smoke build started at 08:24, before the click.** It saw `digline`
    0.28.0 absent from `/simple/` on every 30-second poll and was served
    `after 300s`, at 08:29:08, half a minute after the upload. The step's
    timeout is 1800 seconds, so that is the wait doing its job across the
    approval, not a near miss.
  - **The multi-arch build saw every pin served `after 1s`.** Its amd64 layers
    `#10` to `#13` were `CACHED`, and prove nothing new. The arm64 leg ran.
  - Both builds installed `digline-0.28.0`, `digline-anthropic-0.6.1`,
    `digline-bedrock-0.6.1` and `digline-openai-0.5.2`.
  - `0.28.0`, `0.28` and `latest` resolve to one digest,
    `sha256:4c6902060e6bd64bccd4026773cc148c308c9d8e562d965bb1cb4572673f4494`,
    read with `docker buildx imagetools inspect` on each tag.

  **Step 6, the capture: it ran, the pair was present for every pin, and it
  had nothing to explain.** In both builds, `side=wait` and `side=pip` were
  logged for `digline`, `digline-anthropic`, `digline-openai` and
  `digline-bedrock`, and each pair carried the same serial and the same etag.
  For `digline` that was serial 41829479, the one after the upload.

  **Elsewhere.**
  - The seven example locks moved to 0.28.0 with `--upgrade-package digline`.
    Their diff was read, three lines per lock, and nothing else moved.
  - Nine reports were re-rendered in a chain from that commit, each naming the
    one before it, and the reachability check found all of them reachable.
    `classifier` (`-dirty`) and `prompt-first` (live) were left alone.
  - **Masked for keys and times, every re-rendered report reads exactly as it
    did on 0.27.0.** Against a control, two different reports differ by 21
    lines, so the masking does not erase what it compares.
  - `rag`'s `report` exits 1. It is the example of a regression, and the exit
    code gates like `compare`'s.
  - `release-followup`'s first run, at 08:29:44, said the registry had no
    0.28.0 image. It asked before `docker-publish` had pushed, which finished
    at 08:33:57.

  **The next tag must show** the pair for every pin again, the counts before
  the click, and whether the job summary is where the approver reads it.

- **v0.27.0 — the pair agreed for every pin in both builds, and the smoke
  build waited for the upload instead of racing it.** `publish`
  (`37029824468`) and `docker-publish` (`37029824521`) both passed on attempt
  1, `github-release` and the site jobs included. `tools/tag_names.py "digline
  0.27.0"` ran on #407's merge commit, `0128afb`, immediately before the tag.
  Its whole output was read: one package, named, exit 0, and the `uv` note
  about a `VIRTUAL_ENV` it ignored.

  **The reviewer gate.** `/approvals` reads `approved` by `alexpran` on `pypi`,
  and the environment reads `can_admins_bypass: false`. The run was seen
  waiting at 15:53:23, and the `pypi` job started at 15:54:01. The counts,
  read after the click from the finished jobs:
  - 12 `twine check` `PASSED` in the build, then 2 on `to-publish/`;
  - TestPyPI's selection, and PyPI's, 2 `publish` and 10 `skip`. The two are
    `digline` 0.27.0, wheel and sdist. The ten are the five other packages,
    each already on the index;
  - `imported 6`, and the quickstart's 3 calls.

  Uploads landed at 15:54:23.1 and 15:54:24.6. The version endpoint answered
  200 and its control, `/pypi/digline/9.9.9/json`, answered 404.

  **The index race, both builds.**
  - **The smoke build started at 15:51, before the click.** It saw `digline`
    0.27.0 absent from `/simple/` on every 30-second poll from 15:51:31 to
    15:54:32. It was served at 15:55:02, `after 240s`. That is the wait doing
    its job across the approval, not a race.
  - **The multi-arch build saw every pin served `after 1s`.** Its amd64 layers
    `#10` to `#13` were `CACHED`, and prove nothing new.
  - Both builds installed `digline-0.27.0`, `digline-anthropic-0.6.0`,
    `digline-bedrock-0.6.1` and `digline-openai-0.5.2`.
  - `0.27.0`, `0.27` and `latest` were pushed onto one digest,
    `sha256:c9ee72309c0bc4a8d4d0508dd7f6bec66ca2067d07a68f16cbdb2cc9e5839623`.
    That was read from the push log, because the session's token cannot list
    the package.

  **Step 6, the capture: it ran, the pair was present for every pin, and it
  had nothing to explain.** In both builds, `side=wait` and `side=pip` were
  logged for `digline`, `digline-anthropic`, `digline-openai` and
  `digline-bedrock`, and each pair carried the same serial and the same etag.
  For `digline` that was serial 41738883, the one after the upload.

  **Elsewhere.**
  - The seven example locks moved to 0.27.0 with `--upgrade-package digline`.
    Their diff was read, three lines per lock, and nothing else moved.
  - Nine reports were re-rendered in a chain from that commit, each naming the
    one before it, and the reachability check found all of them reachable.
    `classifier` (`-dirty`) and `prompt-first` (live) were left alone.
  - **Masked for keys and times, every re-rendered report reads exactly as it
    did on 0.26.0.** Against a control, two different reports differ by 201
    lines, so the masking does not erase what it compares.
  - `rag`'s `report` exits 1. It is the example of a regression, and the exit
    code gates like `compare`'s.
  - `release-followup`'s first run, at 15:55:12, said the registry had no
    0.27.0 image. It asked before `docker-publish` had pushed, around 15:58.

  **The next tag must show** the pair for every pin again, the counts after
  the click, and the reports' text against the release before it.

- **digline-bedrock-v0.6.1 — a security patch, one package, and the gate
  read before the click.** It shipped the fix for F-1 of the delta-pass over
  0.6.0, the same day 0.6.0 was published. `publish` (`37021061817`) passed on
  attempt 1. `github-release` and the site jobs were skipped, as on any plugin
  tag, and `docker-publish` did not run.
  - **`tag_names.py "digline-bedrock 0.6.1"`** ran on #403's merge commit,
    `9c5be9d`, immediately before the tag. Its whole output was read: one
    package, named, and the `uv` note about a `VIRTUAL_ENV` it ignored. The
    first read sent stdout and the exit code to `/dev/null` together, so the
    code was read again on its own: 0.
  - **The reviewer gate.** `/approvals` reads `approved` by `alexpran` on
    `pypi`. The run was seen waiting at 14:39:17, and the `pypi` job started at
    14:40:29. **This time the counts were read and reported before the click**,
    from the jobs that had finished:
    - 12 `twine check` `PASSED` in the build;
    - TestPyPI's selection, 2 `publish` and 10 `skip`. The two are the wheel
      and sdist of `digline-bedrock` 0.6.1;
    - `imported 6`, and the quickstart's 3 calls;
    - the version endpoint answering 404.

    PyPI's own selection, read afterwards, was the same 2 and 10.
  - **On PyPI:** uploads at 14:40:49.2 and 14:40:50.6. The version endpoint
    answered 200 and its control, `/pypi/digline-bedrock/9.9.9/json`, answered
    404.
  - **Steps 3, 5 and 6 had nothing to do.** No example pins `digline-bedrock`,
    and no report names it. With no image build, the capture was never asked.
  - **The advisory:** GHSA-j589-v38m-4pwh, low, drafted by the session and
    published by Alessandro with a CVE requested. It is the first of the nine
    published advisories whose CVE was asked for at publication (see
    `SECURITY.md`).

- **digline-bedrock-v0.6.0 — the first tag to publish two plugins, and it
  published both.** One tag carried `digline-bedrock` 0.6.0 and
  `digline-anthropic` 0.6.0, because both versions moved in #395 and a tag
  publishes every workspace package the index lacks. `publish`
  (`37012587825`) passed on attempt 1. `github-release` and the two site jobs
  were skipped, as on any plugin tag.

  **`tag_names.py`, both directions.** On #395's tree, the message naming
  `digline-anthropic 0.6.0` alone exited 1 with *"this run will publish 2
  package(s)"*. That is what ruled one tag rather than two. On #397's merge
  commit, `b589136`, immediately before the tag, the message
  `digline-bedrock 0.6.0, digline-anthropic 0.6.0` printed *"this run will
  publish 2 package(s): digline-anthropic 0.6.0, digline-bedrock 0.6.0"* and
  *"the message names every one of them"*, and exited 0. Its whole output
  was read, not only the code: the one other line was `uv`'s warning about a
  `VIRTUAL_ENV` it ignored.

  **The reviewer gate.** `/approvals` reads `approved` by `alexpran` on `pypi`,
  and the environment reads `can_admins_bypass: false`. The TestPyPI job
  finished at 13:25:50, and the `pypi` job started at 13:39:15. Before the
  click, the session reported the jobs' states and that PyPI served neither
  0.6.0. The counts, read afterwards from the finished jobs:
  - 12 `twine check` `PASSED` in the build, then 4 on `to-publish/`;
  - TestPyPI's selection, and PyPI's, 4 `publish` and 8 `skip`. The four are
    the two plugins, wheel and sdist. The eight are `digline` 0.26.0,
    `digline-mcp` 0.4.3, `digline-openai` 0.5.2 and `pytest-digline` 0.2.1,
    each already on the index;
  - `imported 6`, and the quickstart's 3 calls.

  **Both on PyPI, and the project page said otherwise.** The four files were
  uploaded between 13:39:55.5 and 13:40:00.6. Read right after the run, the
  project JSON (`/pypi/<name>/json`) still named 0.5.4 and 0.5.1 as latest
  and listed no 0.6.0 file. The version JSON (`/pypi/<name>/0.6.0/json`)
  answered 200 with both files for each package, and the control,
  `/pypi/<name>/9.9.9/json`, answered 404. **Read the version endpoint, with a
  control that must fail.** The project endpoint lags, and on a check of what
  shipped, a lag looks the same as a package that did not.

  **Steps 2, 5 and 6 were not run, and none of them was skipped.**
  `docker-publish` triggers on `v*` only (its own comment says why), so no
  image was built. There was no `served` line to read, no digest to compare,
  and no `index-capture` pair: the capture was *never asked*, which is not the
  same as agreeing. The Dockerfile's pins already name both 0.6.0s, and the
  image takes them at the next workspace release. No committed `report.html`
  names a plugin's version, so nothing in step 5 moved.

  **Elsewhere.** The three example locks that pin `digline-anthropic` moved
  from 0.5.4 to 0.6.0, and their hashes match the release's attestations.
  **`examples/langchain`'s first `uv lock -q --upgrade-package
  digline-anthropic` exited 0 and moved nothing**, minutes after the upload;
  the second moved it. A quiet lock is not a moved lock: read the diff.

  **The next plugin-only tag must show** the version endpoint read with its
  control, and every lock's diff, not its exit code.

- **v0.26.0 — the pair agreed for every pin, the signatures' wait was
  answered on its first read, and the counts reached the approver after the
  click, now by rule.** `publish` (`36991389633`) and `docker-publish`
  (`36991389648`) both passed on attempt 1, `github-release` included.
  `tools/tag_names.py "digline 0.26.0, digline-mcp 0.4.3"` ran before the tag:
  two packages, both named. The control naming the core alone exited 1.

  **The reviewer gate.** `/approvals` reads `approved` by `alexpran` on `pypi`,
  and the environment reads `can_admins_bypass: false`. The run was seen
  waiting at 09:45:46 and the `pypi` job started at 09:45:47. It is the third
  release in a row where the approval came before the counts could, and the
  order is now written the other way round (*After the tag*, the paragraph
  after *The approval is a person's click*). The counts, read afterwards from
  the finished jobs:
  - 12 files built and 12 `twine check` `PASSED`, then 4 more on
    `to-publish/`;
  - TestPyPI's selection 4 `publish` and 8 `skip`. The four are `digline`
    0.26.0 and `digline-mcp` 0.4.3, wheel and sdist; the eight are the four
    other packages, each *already on the index*;
  - `imported 6`, and the quickstart's 3 calls.

  **The signatures' wait was answered on its first read.** The four uploads
  answered `200 OK` between 09:46:09.6 and 09:46:12.9. The step ran from
  09:46:52.5 to 09:46:53.5, with no `waiting` and no `served` line. **So the
  first read fell about 40 seconds after the last upload, and was answered.**
  Four bundles, the first release to carry four because `digline-mcp` rode the
  tag, all `OK`. Eight files skipped, each with the tag that published it.
  - **Against the earlier tags:** served at ~40 (here and v0.24.1), ~36–48
    (v0.25.2), ~44–45 (v0.25.3), 58.6 (v0.25.0) and 59 (v0.24.0). Not served
    at 36 (v0.23.0) and 43 (v0.22.0), before the loop existed. v0.25.1 was
    absent until about 92 and served at about 102.

  **`/simple/` caught up in 10 seconds**, the sixth tag in a row at 10 or 11:
  one `waiting` line per new package, then `every version is served (after
  10s)`.

  **Inside the builds, the pair agreed for every pin.**
  - The smoke build and the multi-arch build each carry a `side=wait` and a
    `side=pip` line for all four pins, with the same `serial` and `etag` on
    both sides. For `digline` that is `41724613` and
    `pCDsC+sFtKRY7XzSWbbVMw`: the page with 0.26.0, where v0.25.3's pip read
    the one before it.
  - The runner's wait for the smoke took 180 seconds. It started at 09:43:21,
    before the upload, and saw the new serial at 09:46:21. The in-build waits
    said `after 0s` and `after 1s`.
  - pip's half printed 66 lines across the two builds.
  - Both builds installed `digline-0.26.0`, `digline-anthropic-0.5.4`,
    `digline-openai-0.5.2` and `digline-bedrock-0.5.1`.
  - The multi-arch amd64 layers `#10` to `#13` were `CACHED`.
  - The three tags resolve to one digest,
    `sha256:ac722635e63bff589d729546d261213de75d4fe0a4d823d3dde50c23d6ae0315`.
  - **Row one did not recur.** v0.25.3's divergence stays one reading, and
    nothing makes it a pattern yet.

  **Elsewhere.** The seven example locks moved to 0.26.0 with
  `--upgrade-package digline` (#383). The three that pin `digline-anthropic`
  moved it from 0.5.3 to 0.5.4, which its own tag published that morning and
  which no lock had picked up.

  **The next tag must show** the pair for every pin again, and the counts
  after the click.

- **v0.25.3 — the capture caught its first divergence: inside the smoke
  build, the wait saw the new page and pip, 1.4 seconds later, the old one.
  Row one of the table: per-server luck, confirmed.** `publish`
  (`36866404637`) passed on attempt 1, `github-release` included.
  `docker-publish` (`36866404652`) failed on attempt 1 and passed on attempt 2.
  `tools/tag_names.py "digline 0.25.3"` ran before the tag: one package, named.

  **The reviewer gate, and why the counts before the click did not work.**
  `/approvals` reads `approved` by `alexpran` on `pypi`, and the environment
  reads `can_admins_bypass: false`. The session polled `pending_deployments`
  every 3 seconds this time, and saw the run waiting at 13:10:03. The `pypi` job
  started at 13:10:07. **So the window between the wait and the click was about
  4 seconds**, and the counts, read job by job from the finished jobs' logs,
  reached the approver after the click. It is the second time today: on
  v0.25.2 the approval fell in an 11-second window that a 20-second poll never
  saw. **Counts read out before the approval are not workable while the
  approver clicks as soon as the gate shows.** A shorter poll does not fix that,
  because the reading takes longer than the click. Nothing is ruled. The counts
  were right, and they are recorded below for the record:
  - 12 files built and 12 `twine check` `PASSED`;
  - TestPyPI's selection 2 `publish` and 10 `skip`, the five plugins' files
    each *already on the index*;
  - `imported 6`, and the quickstart's 3 calls.

  **The signatures' wait was answered on its first read again.** The uploads
  answered `200 OK` at 13:10:30.2 (wheel) and 13:10:32.5 (sdist). The step ran
  from 13:11:16.255 to 13:11:17.165, under a second for every read. No
  `waiting` and no `served` line, and `release_bundles.py` prints `served` only
  from the second read on. **So the first read fell about 44 to 45 seconds after
  the last upload, and was answered.** Two bundles, both `OK`, and ten files
  skipped with the tag that published each.
  - **Against the earlier tags:** not served at 36 s (v0.23.0) and 43 s
    (v0.22.0), before the loop existed. Served at 40 (v0.24.1), ~36–48
    (v0.25.2), ~44–45 (here), 58.6 (v0.25.0) and 59 (v0.24.0). v0.25.1 was
    absent until about 92 s and served at about 102.
  - **What that sample says:** the first read lands where the job's start puts
    it, 36 to 60 seconds after the upload. The page becomes available inside the
    same band, before or after the read. One more answered first read says
    nothing about v0.25.1's tail.

  **`/simple/` caught up in 11 seconds**, the fifth tag in a row at 10 or 11:
  one `waiting` line, then `every version is served (after 11s)`.

  **`docker-publish`, attempt 1: the divergence, in two lines.** The runner's
  wait printed `served digline==0.25.3 (after 210s)`. Then, inside the smoke
  build (`#9`), in one `RUN`:

      index-capture side=wait name=digline t=2026-10-01T13:11:29.1Z took=0.019s
        status=200 variant=json serial=41686473 etag=YEWhj7TmO1LShn6KMPfBdw
        age=- cache=MISS,HIT,HIT
        via=cache-iad-khef600031-IAD,cache-iad-khef600031-IAD,cache-iad-khef600079-IAD,cache-pao-kpao1770024-PAO
        versions=50 asked=0.25.3 served=yes
      index-capture side=pip  name=digline t=2026-10-01T13:11:30.5Z took=0.003s
        status=200 variant=json serial=41680881 etag=vDSQkATL4LOEwdCtRe4xCA
        age=- cache=MISS,HIT,HIT
        via=cache-iad-khef600020-IAD,cache-iad-khef600020-IAD,cache-iad-khef600079-IAD,cache-sjc10071-SJC
        versions=- asked=- served=-

  (One line each; wrapped here to fit.) pip then failed with *No matching
  distribution found for digline==0.25.3*.
  - **Read against the table:** the `via` chains differ at their first two
    hops, `khef600031` against `khef600020`. The `serial` and the `etag` differ
    too, and pip's serial is the **older** one: 41680881 is the page from before
    0.25.3, the serial the v0.25.2 builds read.
  - **That is row one: per-server luck, confirmed.** Two servers, and pip's held
    the older object.
  - **The first divergence the capture has recorded.** v0.15.0 and v0.20.1
    failed the same way before it existed. The paragraphs below record
    agreement for v0.25.0, v0.25.1 and v0.25.2. The tags between its building
    and v0.25.0 were not read for this paragraph.
  - **What the reading resolves to is the re-run** this file gives for this case
    (`gh run rerun 36866404652 --failed`).

  **Attempt 2 agreed everywhere.** Both builds (`#9` and `#15`) carry a
  `side=wait` and a `side=pip` line for all four pins, with the same `serial` and
  `etag` on both sides. For `digline` that is `41686473`. The runner's wait and
  both in-build waits said `after 0s`. Both builds installed `digline-0.25.3`,
  `digline-anthropic-0.5.3`, `digline-openai-0.5.2` and `digline-bedrock-0.5.1`.
  The multi-arch amd64 layers `#10` to `#13` were `CACHED`. The three tags
  resolve to one digest,
  `sha256:439b590f1e632375555a0d036c5565f8e24b873a302331d25b56b73649f9e43e`.

  **Elsewhere.** All seven example locks moved to 0.25.3 on the first pass, with
  `--upgrade-package digline` (#342). The versions were read back from the
  seven files.

  **The next tag must show** the pair for every pin again. **And whether row one
  recurs:** one divergence is a reading, and a second is what would make it a
  pattern. What a pattern would oblige is not decided here.

- **v0.25.2 — the signatures' wait was answered on its first read, between
  about 36 and 48 seconds after the upload, and the pair agreed for every
  pin.** `publish` (`36849970929`) and `docker-publish` (`36849970903`) both
  passed on attempt 1, `github-release` included. `/approvals` reads
  `approved` by `alexpran` on `pypi`, and the environment reads
  `can_admins_bypass: false`. The approval came between TestPyPI finishing
  (10:36:39) and the `pypi` job starting (10:36:50): bounded by those two
  times, since `/approvals` carries none of its own. The session polling
  `pending_deployments` every 20 seconds again never saw it waiting, so the
  counts were read after it and not at the `[GATE]`. The three tags resolve
  to one digest,
  `sha256:b786eae8840a58d8e475bd690a1451cb7406bcbd380ed19c0b0f8afef4a85680`.

  **The signatures' wait, with its numbers.** Silent, and silent by design:
  `release_bundles.py` prints a `served` line only from the second read on, so
  no line means the first read was answered.
  - The uploads answered `200 OK` at 10:37:17 and 10:37:19. The `github-release`
    job started at 10:37:54 and printed `2 bundle(s)` at 10:38:05. So the
    first read fell between about 36 and 48 seconds after the upload. The
    window is bounded from the job's times, not measured by the script.
  - It made two bundles and skipped ten files, each named with the tag that
    published it. Both bundles verified `OK`.
  - **Against v0.25.1's tail:** that tag was still absent at about 92 seconds.
    This one was served at 48 or sooner. One more point for the distribution,
    and it says nothing about the tail.

  **`/simple/` caught up in 10 seconds**, the fourth tag in a row at 10 or 11:
  one `waiting` line, then `every version is served (after 10s)`.

  **Inside the builds, the pair agreed for every pin.**
  - The smoke build (`#9`) and the multi-arch build (`#15`) each carry one
    `side=wait` and one `side=pip` line for all four pins, with the same
    `serial` and `etag` on both sides. For `digline` that is `41680881` and
    `vDSQkATL4LOEwdCtRe4xCA`.
  - The runner's wait for the smoke took 210 seconds. It started at 10:34:38,
    before the `publish` run had built anything, so it waited for the whole
    road to PyPI: the build, TestPyPI, the approval and the upload. The
    in-build waits did not have to wait: `after 0s` in `#9`, and
    `after 0s` and `after 1s` in `#15`.
  - The last `via` hop differed within all eight pairs.
  - pip's half printed 33 lines in each build.
  - Both builds installed `digline-0.25.2`, `digline-anthropic-0.5.3`,
    `digline-openai-0.5.2` and `digline-bedrock-0.5.1`.
  - The multi-arch amd64 layers `#10` to `#13` were `CACHED`.

  The capture ran, the pair was present for every pin, and it had nothing to
  explain.

  **Elsewhere.** All seven example locks moved to 0.25.2 on the first pass,
  with `--upgrade-package digline`. The versions were read back from the seven
  files.

  **The next tag must show** the pair for every pin again, and the
  signatures' wait's reads with their times. A first read answered says only
  that the page can be served that early.

- **v0.25.1 — the signatures' wait fired against a real index for the first
  time. The JSON page answered 404 six times and was served on the seventh
  read, about 100 seconds after the upload: the longest lag measured.**
  `publish` and `docker-publish` both passed on attempt 1, `github-release`
  included. `/approvals` reads `approved` by `alexpran` on `pypi`, and the
  environment reads `can_admins_bypass: false`. The approval came in the 45
  seconds between TestPyPI finishing (16:34:07) and the `pypi` job starting
  (16:34:52). The session polling `pending_deployments` every 20 seconds never
  saw it waiting, so the counts were read after it and not at the `[GATE]`. The
  smoke's runner wait printed `every version is served (after 241s)`, and most
  of that was the approval. The three tags resolve to one digest,
  `sha256:e665ed0fca0402e7f22e59aa39944a4dc8f6e2cc9d533d0d55a6c773340e4f79`.

  **The signatures' wait, with its numbers.**
  - The upload finished at 16:35:10.2. `release_bundles.py` started at
    16:35:51.9, and its first read came about 42 seconds after the upload.
  - `/pypi/digline/0.25.1/json` answered 404 on reads 1 to 6, ten seconds
    apart. The sixth came about 92 seconds after the upload.
  - Read 7 printed `served … (after 60s, read 7)`, about 102 seconds after the
    upload. No `absent` and no `unread`.
  - It made two bundles and skipped ten files, each named with the tag that
    published it. Both bundles verified `OK`.
  - The log's lines all carry 16:36:54, because the output was flushed at the
    end. The times above come from the script's own `after 60s`, counted from
    its start.

  **The loop's first real firing.** It had run on four tags (v0.24.0, v0.24.1,
  v0.25.0 and now) and on the first three it never read a 404.
  `tests/test_release_bundles.py`'s offline control was the only evidence it
  held. This is the case it was written for: v0.21.0, v0.22.0 and v0.23.0
  refused on a single 404 and needed a re-run. This time the same absence
  was waited out, and the job went green on attempt 1.

  **The windows observed until now were an optimistic sample.** Each earlier
  tag measured one read and nothing after it:
  - not served at 36 seconds (v0.23.0) and 43 (v0.22.0);
  - served at 40 (v0.24.1), 58.6 (v0.25.0) and 59 (v0.24.0).

  Read together, they suggested the page catches up within about a minute.
  This tag shows it **still absent at about 92 seconds** and served only at
  about 102. So the lag has a longer tail than the sample showed, and an answer
  at 40 or 59 seconds said that the page can be served by then, not that it
  will be. `TIMEOUT` is 600 seconds in `publish.yml`, so the margin is still
  wide. Nothing here moves it.

  **`/simple/` again caught up first.** The `pypi` job's wait printed one
  `waiting` line and then `every version is served (after 10s)`. That is the
  third tag in a row at 10 or 11 seconds, while the JSON page took ten times
  as long.

  **Inside the builds, the pair agreed for every pin.**
  - The smoke build (`#9`, amd64) and the multi-arch build (`#15`, arm64) each
    carry a `side=wait` and a `side=pip` line for all four pins, with the same
    `serial` and `etag` on both sides. For `digline` that is `41648520` and
    `wNf5UEB+Z7hNU00keaKFHw`.
  - The in-build waits did not have to wait: `after 0s` in `#9`, and `after 0s`
    and `after 1s` in `#15`. The smoke build started after the runner wait, by
    which time the new serial was everywhere it read.
  - The last `via` hop differed within every pair in `#9`, and within three of
    four in `#15`. For `digline-anthropic` in `#15`, both sides reached the same
    server (`cache-phx1710110-PHX`): one server, one object.
  - pip's half printed 33 lines in each build.
  - Both builds installed `digline-0.25.1`, `digline-anthropic-0.5.3`,
    `digline-openai-0.5.2` and `digline-bedrock-0.5.1`.
  - The multi-arch amd64 layers `#10` to `#13` were `CACHED`.

  The capture ran, the pair was present for every pin, and it had nothing to
  explain.

  **Elsewhere.** All seven example locks moved to 0.25.1 on the first pass,
  with `--refresh-package digline` used from the start after `classifier`'s
  cached page on v0.25.0. The versions were read back from the seven files.

  **The next tag must show** the pair for every pin again, and the
  signatures' wait's reads with their times. Whether it waits again, and for
  how long, is what turns one firing into a distribution.

- **v0.25.0 — the pair agreed for every pin, and the signatures' wait did not
  have to wait: its first read came 58.6 seconds after the upload, later than
  any read that has met a 404.** `publish` and `docker-publish` both passed on
  attempt 1. `/approvals` reads `approved` by `alexpran` on `pypi`, and the
  environment reads `can_admins_bypass: false`. The approval came before the
  smoke's 30-minute deadline. The smoke's runner wait printed
  `every version is served (after 211s)`, and most of that was the approval.
  The three tags resolve to one digest,
  `sha256:0fcf3c1260a73b1734416056d907a07068e702383c51984ca05473d0461f035f`.

  **Inside the builds, the pair agreed for every pin.**
  - The smoke build (`#9`, amd64) and the multi-arch build (`#15`, arm64) each
    carry a `side=wait` and a `side=pip` line for all four pins, with the same
    `serial` and `etag` on both sides. For `digline` that is `41642074` and
    `DSUdlMpHqLvbdKqlblDOiw`.
  - **In `#9` the in-build wait had to wait**, as it did on v0.23.0, v0.22.0
    and v0.21.1, and did not on v0.24.1 (v0.24.0's entry does not say). Its
    first read, at 14:04:19.5, saw serial `41633880` and 46
    versions, none at 0.25.0. That was the same object the runner wait had read
    before the upload. It printed one `waiting` line, and at 14:04:34.8 it read
    `41642074` and printed `served digline==0.25.0 (after 15s)`. pip's read at
    14:04:35.6 got that same object. The build's first read came 60 seconds
    after the upload finished and still saw the old object.
  - The last `via` hop differed within every pair in both builds, which is row
    three of the table.
  - pip's half printed 33 lines in each build.
  - Both builds installed `digline-0.25.0`, `digline-anthropic-0.5.3`,
    `digline-openai-0.5.2` and `digline-bedrock-0.5.1`.
  - The multi-arch amd64 layers `#10` to `#13` were `CACHED`.
  - The multi-arch in-build wait printed `after 0s` and `after 1s`.

  The capture ran, the pair was present for every pin, and it had nothing to
  explain.

  **The signatures' wait: no `waiting` line, no `served … (after Ns, read N)`,
  and neither `absent` nor `unread`.** The step started at 14:04:17.9 and its
  output ends at 14:04:19.4. The script prints no line per read, so the number
  of reads is derived from what it had to read, not counted: six JSON pages,
  twelve attestations and the two files at 0.25.0, the same 20 as on v0.24.1.
  The result was two bundles, and ten files skipped, each named with the tag
  that published it.

  **What 58.6 seconds says, and what it does not.** The upload finished at
  14:03:19.3 and the script's first read came at 14:04:17.9. The JSON page has
  404'd at 36 seconds (v0.23.0) and 43 (v0.22.0), and answered at 40 (v0.24.1)
  and 59 (v0.24.0). This read came as late as v0.24.0's, so an answer here
  says nothing new about the lag.
  - The loop has still not met a 404 on a real index. Four tags have now run
    it.
  - Only `tests/test_release_bundles.py`'s offline control has shown it
    holding.

  **`/simple/` again caught up first.** The `pypi` job's wait printed one
  `waiting` line and then `every version is served (after 10s)`, as on v0.23.0
  and v0.24.1.

  **Elsewhere.** `uv lock --upgrade-package digline` moved six of the seven
  example locks to 0.25.0 on the first pass. `classifier`'s stayed at 0.24.1
  and moved on a second pass with `--refresh-package digline`: a cached index
  page, and the first time one has held back a lock here. The versions were
  read back from the seven files.

  **The next tag must show** the pair for every pin again, and whether the
  signatures' wait has to wait. A `waiting` line from it, and what it read
  next, is still the first observation of the loop against a real index.

- **v0.24.1 — the pair agreed again, and the signatures' wait again did not
  have to wait, this time 40 seconds after the upload, inside the window where
  the JSON page had 404'd before.** `publish` and `docker-publish` both passed
  on attempt 1. `/approvals` reads `approved` by `alexpran` on `pypi`. The
  approval came before the smoke's 30-minute deadline. The smoke's runner wait
  printed `every version is served (after 270s)`, and most of that was the
  approval. The three tags resolve to one digest,
  `sha256:1615f7eb3ff3794d7c88df16b4be443cac06bbe32618caa8eb6b60c7b84a9a0d`.

  **Inside the builds, the pair agreed for every pin.**
  - The smoke build (`#9`, amd64) and the multi-arch build (`#15`, arm64) each
    carry a `side=wait` and a `side=pip` line for all four pins, with the same
    `serial` and `etag` on both sides. For `digline` that is `41633880` and
    `7AICkafxLz3xcRSW/vohfg`.
  - In `#9` the last `via` hop differed within each pair, which is row three
    of the table. In `#15` it was the same server on both sides: one server,
    one object.
  - pip's half printed 33 lines in each build.
  - Both builds installed `digline-0.24.1`, `digline-anthropic-0.5.3`,
    `digline-openai-0.5.2` and `digline-bedrock-0.5.1`.
  - The multi-arch amd64 layers `#10` to `#13` were `CACHED`.
  - The in-build waits printed `after 0s` and `after 1s`.

  The capture ran, the pair was present for every pin, and it had nothing to
  explain.

  **The signatures' wait: 20 reads, none repeated, no third word.** The script
  made 20 reads in a second and a half, from 10:01:25.0 to 10:01:26.5:
  - six JSON pages;
  - twelve attestations;
  - the two files at 0.24.1.

  Each one answered on its first read. There is no `waiting` line and no
  `served … (after Ns, read N)`, and neither `absent` nor `unread` fired. The
  result was two bundles, and ten files skipped, each named with the tag that
  published it.

  **What 40 seconds says, and what it does not.** The upload finished at
  10:00:45.1, and the script's first read came 40 seconds later. That is
  between v0.23.0's 36 and v0.22.0's 43, where the JSON page 404'd. This
  time it answered. So the JSON page's lag behind the upload varies: at 40
  seconds it has been served and it has not.
  - It still proves nothing about the loop: no read met a 404, so the loop has
    not yet run against a real index.
  - Only `tests/test_release_bundles.py`'s offline control has shown it
    holding.

  **The two endpoints are not in step, and that is why only one consumer ever
  failed.** On this tag:
  - the `pypi` job's wait, which asks `/simple/`, printed one `waiting` line at
    10:00:55 and then `every version is served (after 11s)`;
  - on v0.23.0, `/simple/` answered after 10 s.

  The JSON page, asked by `release_bundles.py`, has lagged further behind:
  - not served at 36 s (v0.23.0) and at 43 s (v0.22.0);
  - served at 40 s (v0.24.1) and at 59 s (v0.24.0).

  The `pypi` job's wait has never failed over this, because it asks the
  endpoint that catches up first. `github-release` asks the other one, and
  failed three times (v0.21.0, v0.22.0, v0.23.0) until it gained a wait of its
  own.

  **`listed` never warned.** The one `release-followup` run after the tag
  fired no `::warning`.

  **Elsewhere.** `uv lock --upgrade-package digline` moved all seven example
  locks to 0.24.1 on the first pass. The versions were read back from the
  seven files.

  **The next tag must show** the pair for every pin again. It must also show,
  once more, whether the signatures' wait has to wait. A `waiting` line from
  it, and what it read next, is still the first observation of the loop against
  a real index.

- **v0.24.0 — the pair agreed on both legs, and `release_bundles.py`'s wait
  ran for the first time and never had to wait, so this green does not prove
  it.** `publish` passed on attempt 1, `github-release` included. Its approval
  reads `approved` by `alexpran` on `pypi` from `/approvals`, not from the
  run's green. `docker-publish` needed an attempt 2, for the reason *Applying
  it* gives the smoke's 30-minute deadline: it waits on a person. Attempt 1's
  runner wait ran from 07:59:27 to 08:28:59 and failed with *`/simple/digline/`
  is served and lists 44 file version(s), none at 0.24.0*. The approval came
  after that, and the upload finished at 08:46:56. After
  `gh run rerun --failed`, the three tags resolve to one digest,
  `sha256:d0cb215ddab661ec326c7238b37fd6fde3dd74fd4a8014040054e30cdd622dfc`.

  **Runner level.** The `pypi` job printed `every version is served (after
  10s)` at 08:47:07. The smoke's own wait, on attempt 2, printed `after 0s`.

  **Inside the builds, the pair agreed for every pin.**
  - The smoke build (`#9`, amd64) and the multi-arch build (`#15`, arm64) each
    carry a `side=wait` and a `side=pip` line for all four pins. On both sides
    of each pair, `serial` and `etag` are the same. For `digline` that is
    `41631205` and `tJx93VHaOSEhmO9mY6IDgQ`.
  - The last hop of `via` differs within each pair: `kiad7000188` against
    `kiad7000023`, and `kiad7000153` against `kiad7000126`. That is row three
    of the table, the routine case.
  - pip's half printed 33 lines in each build.
  - Both builds printed `Successfully installed` with `digline-0.24.0`,
    `digline-anthropic-0.5.3`, `digline-openai-0.5.2` and
    `digline-bedrock-0.5.1`.
  - The multi-arch amd64 layers `#10` to `#13` were `CACHED` from the smoke
    build, so they proved nothing of their own.

  The capture ran, the pair was present for every pin, and it had nothing to
  explain.

  **The signatures' wait: 20 reads, none repeated, no third word.** The script
  made 20 reads in about two seconds, from 08:47:55.8 to 08:47:57.9:
  - six JSON pages, one per package in `dist/`;
  - twelve attestations, one per file;
  - the two files at 0.24.0, fetched to check their digests.

  Each one answered on its first read. The log has no `waiting` line, and no
  `served … (after Ns, read N)` line, which the script prints only for a read
  that took more than one. Neither `absent` nor `unread` fired, and there was
  no `::error`. The result was two bundles for `refs/tags/v0.24.0`, and ten
  files skipped, each named with the tag that published it.

  **But the green does not prove the wait.** The first read came 59 seconds
  after the upload finished. The JSON page 404'd at 43 seconds on v0.22.0 and
  at 36 on v0.23.0. This read came later than both, so the page was already
  served. The repair ran and had nothing to absorb. Only
  `tests/test_release_bundles.py`'s offline control has shown the loop
  holding against a lagging index.

  **`listed` never warned.** None of the four `release-followup` runs after
  the tag fired a `::warning`.

  **Elsewhere.** `uv lock --upgrade-package digline` moved all seven example
  locks to 0.24.0 on the first pass. The versions were read back from the seven
  files before committing.

  **The next tag must show** the pair for every pin again. It must also show,
  once more, whether `release_bundles.py`'s wait has to wait. A `waiting`
  line, and what it read next, is the first observation of the loop against a
  real index. A clean first read, like this one, says only when the script
  started.

- **v0.23.0 — the wait held on both legs again, and the JSON endpoint 404'd
  a second time, so `release_bundles.py` is now a consumer owed its own
  wait.** `docker-publish` passed on attempt 1. All three tags resolve to one
  digest,
  `sha256:9b8baabbd1344c71fc68ee6287940df02a890d85f903f68f55c0cab115f30db8`.
  `publish` needed an attempt 2, for the same reason as v0.22.0.

  **Runner level.** `every version is served (after 211s)`, and most of that
  was the approval: the wait started at 14:18:18 and the upload landed at
  14:20:50. It read `serial=41586071` (the serial v0.22.0 ended on) via
  `cache-iad-khef600052-IAD` seven times, the last at 14:21:18, 28 seconds
  after the upload. At 14:21:48 it read `41598687` via
  `cache-iad-khef600024-IAD`.

  **Inside the builds, the pair agreed on both legs.** In the smoke build (`#9`,
  amd64), `side=wait` and `side=pip` both read `41598687` via `khef600024`,
  and the wait printed `after 0s`. In the multi-arch build (`#15`, arm64), the
  wait read the stale `41586071` via `khef600052` at 14:24:10. That was three
  minutes and twenty seconds after the upload, the same lag v0.22.0 measured.
  At 14:24:26 it read `41598687` via `khef600024` (`served digline==0.23.0
  (after 16s)`), and only then did `pip` ask, on the same serial. Both legs
  printed `Successfully installed` with `digline-0.23.0`,
  `digline-anthropic-0.5.3`, `digline-openai-0.5.2` and
  `digline-bedrock-0.5.1`. The multi-arch amd64 layers `#10` to `#13` were
  `CACHED` from the smoke build, so they proved nothing of their own. The
  capture ran, and the pair was present for every pin. The stale server this
  time was `khef600052`, the fresh one on v0.22.0. That is the same reading
  v0.21.2 made: which server lags is luck.

  **The JSON endpoint, a second time.** `publish`'s `pypi` job printed
  `served digline==0.23.0 (after 10s)` on `/simple/` at 14:21:04. At 14:21:28,
  36 seconds after the upload and 24 after `/simple/` answered,
  `release_bundles.py` got a 404 from `/pypi/digline/0.23.0/json`: *digline
  0.23.0 is in dist/ and not on https://pypi.org*. The v0.22.0 entry said a
  second 404 would make this a consumer that needs its own wait rather than a
  one-off. It is that now. The change it names, with both halves (read more
  than once, and a third word for *could not be read*), is **owed and not
  made**. Until it is, `github-release` fails on attempt 1 as a matter of
  course, and the re-run is part of every release. *Made the same day, after
  this entry was written:* the script now waits for its own reads and keeps a
  third word (*Signatures on the GitHub release*, above). The next tag is the
  first to run it.
  - `gh run rerun --failed` attached both bundles on attempt 2.
  - Before the re-run, the attempt-1 approval had already been read and kept.
    `release-followup` run 36582483933 kept it, and #243 ticks the gate from
    that artifact.
  - Checked from outside the run: `sigstore verify github --ref
    refs/tags/v0.23.0` passed on the wheel and on the sdist, each downloaded
    from PyPI. With `--ref refs/tags/v0.22.0`, both were refused.

  **`listed` never warned.** None of the three `release-followup` runs after
  the tag printed a `::warning`, so no read needed a retry this time. That
  says nothing either way about whether the retry pays for itself.

  **Elsewhere.** `uv lock --upgrade-package digline` moved all seven example
  locks to 0.23.0 on the first pass, without `--refresh-package`. The versions
  were read back from the seven files before committing.

  **The next tag must show** the pair for every pin again. It must also show
  whether `github-release` still needs its re-run: yes, unless the owed wait
  lands first. And once more whether `listed`'s `::warning` lines ever fire.

- **v0.22.0 — the wait held on both legs, and the race reached an endpoint
  that nothing waits for.** `docker-publish` passed on attempt 1. All three
  tags resolve to one digest,
  `sha256:893ee00846b1405d212aa3435492d0e939d241f0641d4edefb1fd9a339347cf4`.
  `publish` needed an attempt 2, for the reason in the last paragraph.

  **Runner level.** `every version is served (after 240s)`, and the time is the
  approval's, not the index's: the wait started at 08:25:42 and the upload
  landed at 08:29:04. It read `serial=41552657` (the serial v0.21.2 ended on)
  via `cache-iad-khef600045-IAD` nine times, the last at 08:29:12, eight seconds
  after the upload. It read `41586071` via `cache-iad-khef600052-IAD` at
  08:29:42.

  **Inside the builds, the pair agreed on both legs.** In the smoke build (`#9`,
  amd64), `side=wait` and `side=pip` both read `41586071` via `khef600052`, and
  the wait printed `after 0s`. The multi-arch build (`#15`, arm64) is the one
  where the in-build wait earned its place. At 08:32:24, more than three
  minutes after the upload, it read the stale `41552657` via `khef600045` again.
  At 08:32:40 it read `41586071` via `khef600052` (`served digline==0.22.0
  (after 16s)`). Only then did `pip` ask, on the same serial. Both legs printed
  `Successfully installed` with `digline-0.22.0`, `digline-anthropic-0.5.3`,
  `digline-openai-0.5.2` and `digline-bedrock-0.5.1`. The multi-arch amd64
  layers `#10` to `#13` were `CACHED` from the smoke build, so they proved
  nothing of their own. The capture ran, and the pair was present for every
  pin.

  **The server, for the third release running, was a different one.** The
  stale answers came through `khef600045`, which was the *fresh* server on
  v0.21.2. That is the reading that entry predicted. Which server is behind is
  luck, and nothing is owed to PyPI.

  **The new surface: `/pypi/<name>/<version>/json`, which no wait covers.**
  `publish`'s `pypi` job waited on `/simple/`, and at 08:29:18 its wait printed
  `served digline==0.22.0 (after 11s)`. `github-release` runs after it
  (`needs: pypi`), and at 08:29:47 `.github/release_bundles.py` asked for
  `/pypi/digline/0.22.0/json` and got a 404: *digline 0.22.0 is in dist/ and
  not on https://pypi.org*. That is 43 seconds after the upload, and 29 seconds
  after `/simple/` answered on another runner. The two requests came from
  different runners, so this reading cannot say whether the gap was between the
  two endpoints or between two edges. What it does say is that the wait answers
  a question the next job does not ask:
  - `await_index.py` asks `/simple/`.
  - `release_bundles.py` asks `/pypi/…/json` and then `/integrity/…/provenance`.
  - Its `_get` makes one request, reads a 404 as an absence, and refuses on the
    spot.

  The remedy the index race settled on, a wait per consumer that asks the
  question `pip` asks, was never applied to this consumer. `gh run rerun
  --failed` attached both bundles on attempt 2. They were verified afterwards
  from outside the run: `sigstore verify github --ref refs/tags/v0.22.0` passed
  on each against the file PyPI serves, and the same bundle with `--ref
  refs/tags/v0.21.2` was refused as the control. The attempt-1 approval was
  read before the re-run (`approved`, environment `pypi`), because the
  approvals endpoint forgets it afterwards.

  **The same family, one floor up: a GitHub listing, read once.** At 09:20,
  `release-followup` run `36548467393` asked `gh run list
  --workflow=publish.yml --branch v0.22.0 --limit 1` and got nothing, although
  the run had existed since 08:25. Four runs either side of it (08:51, 09:01,
  09:12, 09:29) found it. The script wrote `[]` for the approvals, and the
  check said *"records no approved: either the gate did not hold"*, about a
  gate that had held and whose approval `release-followup` had already read
  and kept (artifact `11020349819`, 08:30). #215 said so from 09:20 to 09:29.
  The run list was not the only read of that kind in the step: the approvals
  endpoint (`|| echo "[]"`) and the artifact list (`|| true`) turned a failure
  into an empty answer the same way, and had not yet been caught doing it.

  **So three instances in one morning, and one shape: an absence of an
  answer read as an answer.** The 404 on `/pypi/…/json`, the empty run list,
  and the artifact list that could have. The remedy has two halves, and the
  second is the one that was missing everywhere:
  - **read more than once** before believing an empty listing;
  - **keep a third word.** Beside *yes* and *no* there has to be *could not be
    read*, and a check that meets it says *not judged* instead of either.

  `release-followup` now has both. Each of its three reads goes through
  `listed`, which asks up to four times, five seconds apart. A read that never
  answers writes `"unread"`, which `approvals_finding` reports as *not
  judged*, and a run whose only open findings are unread leaves the release's
  issue as it found it. It still goes red for whoever is watching.
  The open-issue listing in the same workflow had the defect too: a failed
  `gh issue list` was an error, but an empty one was believed on one read, and
  in front of `gh issue create` that opens a duplicate of the issue the listing
  failed to show. Simulated with a stub `gh` whose listing shows the issue on
  the third read, the step as it stood created a second issue. It now stops on
  a failed listing, and lists again up to three more times before opening
  anything. **`release_bundles.py` has neither half yet**: it makes one
  request, takes a 404 as an absence, and refuses on the spot. It is left for
  a change of its own, which needs both halves, not only the retry.

  **Elsewhere, and this one was not the index.** The first
  `uv lock --upgrade-package digline` pass left `classifier` at 0.21.2 while the
  other five moved. That pass ran **without** `--refresh-package digline`,
  which the v0.21.2 entry below names. With the flag, `classifier` moved at
  once, which points at uv's local cache rather than at the index; the order
  was not re-run to prove it. The versions were read back from all six files
  before committing.

  **The next tag must show** the pair for every pin again, and whether
  `github-release` meets the JSON endpoint behind `/simple/` a second time. A
  second 404 there would make it a consumer that needs its own wait, not a
  one-off. It must also show whether `listed`'s `::warning` lines ever fire.
  If they fire and a later read answers, the retry is paying for itself. If
  they fire and every read stays empty, *not judged* is the true reading, and
  somebody should look at why.

- **v0.21.2 — the divergence appeared again, the wait held again, and the
  second observation falsifies the per-server hypothesis rather than
  confirming it.** `publish` and `docker-publish` both passed on attempt 1.
  All three tags resolve to one digest,
  `sha256:6057342d7be85e4796c7aad94debfbb0ff745f9742dc8e65ed9de043d1091554`.

  **Runner level.** `every version is served (after 10s)` — not the five
  minutes of the last two releases, because the `pypi` approval came before
  the wait rather than during it. `digline` read `serial=41552657` via
  `cache-iad-khef600045-IAD`, `digline-mcp` `41552658` via
  `cache-iad-kcgs7200132-IAD`, both `served=yes`.

  **Inside the smoke build (`#9`, amd64) the index was older, and stayed
  older for 211 seconds.** The wait read `41515308` — the serial v0.21.1
  ended on — **seven times**, every one of them via
  `cache-iad-khef600044-IAD`, each saying `/simple/digline/ is served and
  lists 41 file version(s), none at 0.21.2`. It then read `41552657` via
  `cache-iad-khef600045-IAD` (`served digline==0.21.2 (after 211s)`), and only
  then did `pip` ask: `side=pip … serial=41552657`, same first hop, followed
  by `Successfully installed … digline-0.21.2 …` (`#9 9.729`). **The pair
  agreed because the wait refused to hand `pip` the stale answer**, for the
  second release running. The other three pins (`digline-anthropic`,
  `digline-openai`, `digline-bedrock`) paired on one serial each, and the
  multi-arch build (`#15`, arm64) read `41552657` on both sides.

  **The falsification, and it is the point of this entry.** v0.21.1 left the
  hypothesis that one cache server lags: there, `khef600057` served the stale
  serial and `khef600044` the fresh one, and the entry asked whether a second
  observation would name the same server. It did not. Here the stale server
  **is `khef600044`** — the one that was fresh last time — and the fresh one
  is `khef600045`. So what is stable is not *which* server is behind but
  *that* one of them can be: which server answers is luck, and a server fresh
  for one release is not fresh for the next. **No sentence to PyPI is owed**,
  and the two-observation question that entry opened is closed. What remains
  worth watching is only whether the wait keeps holding.

  **Elsewhere.** The example locks did **not** meet the race this time:
  `uv lock --upgrade-package digline --refresh-package digline` took all six
  to 0.21.2 on the first pass, where v0.21.1 needed a second run. The
  versions were still read back out of the six files before committing, which
  is the step that does not depend on which way the race went.

  **The next tag must show** the pair for every pin again. The `via=` first
  hop is still the line to read on a stale serial, but no longer to identify
  a culprit — only to confirm that it keeps moving. A stale serial arriving
  through the *same* server three releases running would reopen what this
  entry closed.

- **v0.21.1 — the capture caught the divergence, the in-build wait absorbed
  it, and the lines name the cache server.** This is the first release where
  the capture recorded the thing it was built to explain. `docker-publish`
  passed on attempt 1. All three tags resolve to one digest,
  `sha256:a3c4f1649abffc2ae9476c566b5d8ce92ef789c97aec64f0137fb113d90ad2a5`.

  **Runner level.** The wait read `serial=41512032` until `12:31:59.3`, then
  `41515308` at `12:32:29.4` (`every version is served (after 301s)`). As on
  0.21.0, those seconds were the `pypi` approval, not the index.

  **Inside the smoke build (`#9`, amd64), fifteen seconds later, the index was
  older again.** The in-build wait read `serial=41512032` at `12:32:44.7`
  (`waiting digline==0.21.1 — … none at 0.21.1`). It waited, read `41515308` at
  `12:32:59.9` (`served digline==0.21.1 (after 15s)`), and only then did `pip`
  ask: `side=pip … serial=41515308` at `12:33:00.9`, followed by `#9 22.83
  Successfully installed … digline-0.21.1 …`. **The pair agreed because the
  wait refused to hand `pip` the stale answer.** On v0.15.0 and v0.20.1 the
  wait said *served* and `pip` got the older list. Here the older list reached
  the wait first, and the wait held.

  **Per-server luck, observed rather than inferred.** Every reading at
  `41512032`, from the runner and from inside the build, came through the
  first hop `cache-iad-khef600057-IAD`. Every reading at `41515308` came
  through `cache-iad-khef600044-IAD`. Both are the `json` variant, so this is
  not the `Vary` defect #29 fixed: it is two cache servers of one variant, one
  refreshed and one not, and which one answers is luck. *The diagnostic,
  built* left that hypothesis standing after v0.20.1 with no way to decide it
  after the fact. These lines decide it for this release.

  **The multi-arch build (`#15`, arm64)** read `41515308` on both sides
  (`served … (after 0s)`, then `pip` at `12:35:19.5`), through `khef600044`,
  and installed at `#15 104.2`. The other three pins (`digline-anthropic`,
  `digline-openai`, `digline-bedrock`) paired on one serial each in both
  builds.

  **Elsewhere.** `publish`'s signatures job did not meet the race this time,
  and passed on attempt 1. **The example locks met it:** `uv lock
  --upgrade-package digline --refresh-package digline` left `classifier` at
  0.21.0 while five others took 0.21.1. A second run of the same command, once
  the simple index listed 0.21.1, fixed it, and the versions were read back out
  of all six locks before committing.

  **The next tag must show** the pair for every pin again. If a stale serial
  appears, the line to read is its `via=` first hop. One observation names a
  server; a second naming the same pattern would be worth a sentence to PyPI.

  *Answered by v0.21.2, above: the second observation named a **different**
  server as the stale one — `khef600044`, which is the one that was fresh
  here. No sentence to PyPI is owed. Read this entry as the observation it
  was, not as a standing suspicion.*

- **v0.21.0 — the capture ran, the pair was present for every pin, and it had
  nothing to explain.** The first release with *The diagnostic, built* in the
  image. `docker-publish` passed on attempt 1, and all three tags resolve to
  one digest, `sha256:c134a22330c3e9b8aef33b367440a98fc94496ff084a5d1b8a29ff3f579e7b49`.

  **The pairs.** In the smoke build (amd64, `#9`) and in the multi-arch build
  (arm64, `#15`), each of the four pins — `digline`, `digline-anthropic`,
  `digline-openai`, `digline-bedrock` — has a `side=wait` and a `side=pip`
  line, and each pair carries one `X-PyPI-Last-Serial`. For the core that is
  `41512032` on both sides of both builds: `#9` asked at `10:12:42.1` and `pip`
  at `10:12:43.4`, `#15` at `10:14:50.1` and `10:15:08.2`. Each `RUN` then
  reached `Successfully installed … digline-0.21.0 …` (`#9 8.445`,
  `#15 133.3`). *Agreed*, and read, not assumed from a quiet log. The
  multi-arch leg's `#10`–`#13` are `CACHED`: its amd64 half reused the smoke
  build and proves nothing new, so `#15` is the build that counts.

  **The runner-level wait was waiting for the approval, not the index.** It
  read `serial=41442088` thirteen times from `10:05:57.8` to `10:11:58.5`, then
  `41512032` at `10:12:28.5` (`every version is served (after 391s)`). The
  `pypi` deployment was `waiting` from `10:08:13` to `10:10:32`, and its job
  finished at `10:12:01`. That wait was the upload arriving, not the index
  lagging behind it.

  **The race showed up somewhere else instead.** In `publish`, *GitHub Release,
  from the changelog* failed at `10:12:11.7`, ten seconds after the `pypi` job
  went green: `digline 0.21.0 is in dist/ and not on https://pypi.org: this
  runs after the upload`. It has the same shape as the image's race, but in a
  runner-level consumer with no wait of its own, and one runner's view does not
  prove another's. `gh run rerun --failed` made it green, with four bundles
  attached. **That re-run had a cost that nobody had written down**: it erased
  the approval record `release-followup` reads, because the endpoint answers
  for the run's latest attempt and attempt 2 had nothing to approve. The gate
  had held. `release-followup` run `36311781707` read attempt 1 at
  `10:12:39.68`: *the publish run records an approved*. **The deployment's
  states are no substitute for that record.** `testpypi` has no reviewer and
  runs the same `waiting → queued → in_progress → success`; its only
  difference is 0s of waiting against `pypi`'s 2m19s. The fix for that check
  is separate from this block.

  **The next tag must show** the pair again, present for every pin, and, if
  `pip` is ever handed an older serial than the wait read, the two lines that
  say so. The signatures step may want the index wait `docker-publish` already
  has. Not ruled: one instance is weather until it recurs.

- **v0.20.1 — the in-build divergence came back, after the same-question
  fix. So the diagnostic is owed before the next tag.** `docker-publish` failed
  on attempt 1 and passed on attempt 2 (`gh run rerun --failed`), which is the
  one red this file still answers with a re-run. It is written down here
  because of what it rules out.

  **Attempt 1, the smoke build.** The runner-level wait printed
  `waiting digline==0.20.1 — … none at 0.20.1` eight times, then `every version
  is served (after 241s)`. Inside the build, `#9 0.449 served digline==0.20.1
  (after 0s)`, and in the same `RUN`, a second later, `#9 1.447 ERROR: Could not
  find a version that satisfies the requirement digline==0.20.1`. The version
  list `pip` was handed **ended at 0.20.0**. That is v0.15.0's shape exactly, and
  it arrived **after** #29 made the wait ask pip's own question (the same
  `Accept`, the same `Accept-Encoding`, `max-age=0`). The variant is therefore
  ruled out, as *The diagnostic, built* says, and one
  hypothesis is left: **per-server luck**. The wait and `pip` reached different
  cache servers of the same variant, one refreshed and one not. The multi-arch
  job never ran on attempt 1: it needs the smoke build.

  **Attempt 2 — both pairs proven.** amd64 in `smoke`: `#9 0.381 served
  digline==0.20.1 (after 0s)`, `#9 1.520 Collecting digline==0.20.1`, `#9 8.844
  Successfully installed … digline-0.20.1 …` in one `RUN`, with the runner-level
  wait at `0s`. arm64 in the multi-arch build: `#15 4.954 served
  digline==0.20.1 (after 0s)`, `#15 23.21 Collecting digline==0.20.1`, `#15 131.0
  Successfully installed … digline-0.20.1 …`, `#15 DONE 137.4s`. The amd64
  layers are `CACHED` there, as on the two tags before.

  The three tags, `0.20.1`, `0.20` and `latest`, resolve to one digest:
  `sha256:cb8280e439517b8b3427e6c833c33af63bec83469b81a13346870d46cb8a6080`.

  The six locks moved to `digline 0.20.1`, read back one at a time, all on the
  first try.

  **The capture this asked for exists, since 2026-09-25** — see *The
  diagnostic, built*. It changes what a repetition of attempt 1 is worth: the
  two `index-capture` lines are in the log already, so the divergence can be
  read instead of re-run past.

  **What the next tag must show:** the same two-pair reading, an honest note on
  whether the race was live — and the capture's reading, which is now **step 6 of
  *After the tag*** rather than a thing to remember. The first time a `served` is
  again followed by a `pip` failure, that reading is the point of the tag and not
  a footnote to it: it is what turns per-server luck from the last hypothesis
  standing into a finding or a dead end. And on a tag where nothing goes wrong,
  step 6 still has to be written — that the capture ran, that the pair was there,
  and that it had nothing to explain. A silent log would otherwise be read later
  as agreement, when it is equally a capture that never ran.

- **v0.20.0 — both pairs proven, one in each job, and the runner-level wait
  equal to v0.19.2's to the second.** The fourth tag in a row where the
  runner-level wait absorbs the race and the in-build one reads `0s`.
  `docker-publish` succeeded on attempt 1.

  **The race, at the runner.** `smoke`'s wait printed `waiting digline==0.20.0 —
  /simple/digline/ is served and lists 37 file version(s), none at 0.20.0`
  eleven times, then `every version is served (after 330s)`. That is the same
  count and the same total as v0.19.2, and it is noted rather than read as a
  pattern: two points are not a trend. None of the three plugins the image
  carries moved this release. `digline-mcp` did move, and the image does not
  carry it.

  **amd64 — proven in `smoke`'s build, and CACHED in the multi-arch one.**
  `#9 0.325 served digline==0.20.0 (after 0s)`, then `#9 1.235 Collecting
  digline==0.20.0` and `#9 6.674 Successfully installed … digline-0.20.0 …` in
  one `RUN`. The multi-arch job's amd64 await layer reports `#10 CACHED`, so
  as on v0.19.2 the amd64 pair is in `smoke` and nowhere else.

  **arm64 — proven in the multi-arch build.** `#15 DONE 140.4s`, with
  `#15 5.072 served digline==0.20.0 (after 0s)` — and `after 1s` for the three
  plugins — then `#15 23.69 Collecting digline==0.20.0` and `#15 133.9
  Successfully installed … digline-0.20.0 …`, in one `RUN`.

  The three tags, `0.20.0`, `0.20` and `latest`, resolve to one digest:
  `sha256:f261c86e780e9b67b4abeef4402f91d348cf014e546280241899363df0de7bb9`.

  **The locks, read back one at a time this time too.** Regenerated about half
  an hour after `publish` went green, all six resolved `digline 0.20.0` on the
  first try. That is the opposite of v0.19.2's `classifier`, and it proves
  nothing about the edge: it is a later hour, not a fixed race. The rule from
  v0.19.2 stands — read every lock back.

  **What the next tag must show:** still the two-pair reading, and still whether
  a tag ever arrives where the runner-level wait clears at `0s` *and* the
  in-build one does not. Four tags have now not shown it.

- **v0.19.2 — both pairs proven, one in each job, and the longest runner-level
  wait yet.** Same reading as v0.19.1, and the third tag in a row where the
  runner-level wait absorbs the race and the in-build one reads `0s`.

  **The race, at the runner.** `smoke`'s wait printed `waiting digline==0.19.2 —
  /simple/digline/ is served and lists 36 file version(s), none at 0.19.2`
  eleven times, then `every version is served (after 330s)`. The three plugins
  read `after 0s` throughout: none of them moved this release, so the index had
  served them for days. 330s against v0.19.1's 210s and v0.17.1's 241s.

  **amd64 — proven in `smoke`'s build, and CACHED in the multi-arch one.**
  `#9 0.344 served digline==0.19.2 (after 0s)`, then `#9 1.322 Collecting
  digline==0.19.2` and `#9 7.221 Successfully installed … digline-0.19.2 …` in
  one `RUN`. The multi-arch job's amd64 layer reports `#12 CACHED`, so that job
  proves nothing about amd64 on its own — the pair is in `smoke`, and reading
  the multi-arch job alone would have found an arch with no evidence and no
  failure. Read the two arches apart, or this is invisible.

  **arm64 — proven in the multi-arch build.** `#15 DONE 142.8s`, with
  `#15 5.073 served digline==0.19.2 (after 0s)` — and `after 1s` for the three
  plugins — then `#15 23.53 Collecting digline==0.19.2` and `#15 136.3
  Successfully installed … digline-0.19.2 …`, in one `RUN`.

  The three tags, `0.19.2`, `0.19` and `latest`, resolve to one digest:
  `sha256:5ceab38344ec7e425241fedb86518a46414c26a60a79a284e9629dec299b1174`.

  **And one observation from outside CI, which the waits do not cover.**
  Regenerating the example locks immediately after `publish` went green,
  `examples/classifier` — alphabetically first — resolved `digline 0.19.1`
  while reporting success. The retry minutes later said `Updated digline
  v0.19.1 -> v0.19.2`. `uv lock` has no wait and asks a different edge than any
  runner; the only thing that caught it was reading the six locks back one at a
  time. **A lock that silently resolves the previous release is the index race
  arriving where nothing is waiting for it.**

  **What the next tag must show:** still the two-pair reading, and still whether
  a tag ever arrives where the runner-level wait clears at `0s` *and* the
  in-build one does not. Three tags have now not shown it.

- **v0.19.1 — both pairs proven, one in each job, and the race met at the runner
  and waited out.** `docker-publish` succeeded on attempt 1.

  - **amd64 — proven in `smoke`'s build.** `#9 0.341 served digline==0.19.1
    (after 0s)` beside the three plugins, then `#9 1.073 Collecting
    digline==0.19.1` and `#9 5.906 Successfully installed … digline-0.19.1
    digline-anthropic-0.5.3 digline-bedrock-0.5.1 digline-openai-0.5.2 …`. The
    same `RUN` (`#9`), with the install 0.7s after `served`.
  - **arm64 — proven in the multi-arch push.** `#15 [linux/arm64 stage-0 3/5]`
    printed `#15 5.061 served digline==0.19.1 (after 1s)`, then `#15 23.06
    Collecting digline==0.19.1` and `#15 133.0 Successfully installed …
    digline-0.19.1 …`, in one `RUN`.
  - **amd64 in the multi-arch push proved nothing, as it does every time.**
    `#11 [linux/amd64 stage-0 3/5]` is `CACHED`.

  The three tags, `0.19.1`, `0.19` and `latest`, resolve to one digest,
  `sha256:c1b65a63…6ee6`.

  **The race was met this time, and it is a fourth observation.** `smoke`'s
  runner-level wait printed `waiting digline==0.19.1 — /simple/digline/ is
  served and lists 35 file version(s), none at 0.19.1` seven times, then
  `served digline==0.19.1 (after 210s)`. The plugins were served at 0s. This is
  the shape of v0.17.1's 241s wait. The index had not caught up when the job
  started, the wait held the build, and the install inside the build found the
  version at 0s. The observations now number four: v0.15.0's failure, v0.15.1's
  live race, v0.17.1's 241s wait, and this 210s wait.

  **What the next tag must show:** the same two-pair reading across the two
  jobs, and an honest note on whether the race was live.

- **v0.19.1 — held after the go-ahead, and nothing had to be retracted.** A
  reconnaissance aimed at something else found two defects in the Claude Code
  plugin, which was already on `main`. Its hook fired in any repository and
  matched a phrase anywhere in the payload. Its description named the MCP
  server's absence of `promote` but not the hook. The plugin's marketplace pins
  the release tag rather than `main`, so nothing had to be retracted: `main`
  carried the defects and nobody could install them. They were fixed in #97,
  the release branch was rebased onto the fix, and every pre-tag check was run
  again on the rebased tree rather than carried forward from the one before it.

- **v0.19.0 — the pair proven on arm64 only, and the race absorbed rather than
  met.** `docker-publish` succeeded on attempt 1.

  - **amd64 — proved nothing, as predicted.** `#12 [linux/amd64 stage-0 3/5]` is
    `CACHED`. It is written here rather than omitted, because a leg that proves
    nothing and is not named reads afterwards as a leg that passed.
  - **arm64 — the pair, in one `RUN`.** `#15 [linux/arm64 stage-0 3/5]` printed
    `#15 18.32 Collecting digline==0.19.0` and `#15 99.85 Successfully installed
    … digline-0.19.0 digline-anthropic-0.5.3 digline-bedrock-0.5.1
    digline-openai-0.5.2 …`. So the 0.19.0 pin is proven on one architecture.

  **The race was absorbed, not met, and this is not a fourth observation.**
  `await_index` reported `served digline==0.19.0 (after 0s)`,
  `digline-anthropic==0.5.3 (after 0s)`, `digline-openai==0.5.2 (after 1s)` —
  no `waiting` line at all. The index was ahead of the build, so the fix was
  never exercised. **Three real observations stand** (v0.15.0's failure,
  v0.15.1's live race, v0.17.1's 241s wait) and a green that did not exercise
  the fix is not one of them. Counting it would grow the sample with a run that
  tested nothing, which is the shape this whole file exists to refuse.

- **v0.19.0 — stopped three times by its own ritual, by three different
  controls, none of them a test.** Worth the lines because a release that ships
  smoothly teaches nothing, and the three failures are of three distinct kinds.

  1. **The delta-pass found the feature inert.** `read_pinned` had no caller, so
     `Run.pinned` was empty in every run digline wrote and no comparison could
     exit 2 — behind **39 green tests**, each of which constructed the record
     directly and so could not see the gap between the suite and the driver.
  2. **The floor gate found two plugins that would have been broken** for anyone
     resolving against PyPI: both imported a name that arrived in 0.19.0 while
     declaring older floors. Unreachable by any test in this repository, because
     the failure is about versions that are *not* present.
  3. **The runbook caught a tag about to point at the wrong commit** — the
     feature merge, whose changelog still said `## 0.19.0 — unreleased`. The
     defect was not a forgotten rule: the wrong point looked like the right one.

  The common property is what makes them worth recording together: **none was
  reachable by a test**, and each needed a control that looks at something a
  test cannot — a wiring, a promise about absent versions, and a commit's place
  in a sequence.

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

- **v0.18.0 answered the question the paragraph above asked, and the answer is
  no.** Four of the last five tags now: **the race happened at the runner and
  never inside the build.**

  The runner-level step printed `waiting digline==0.18.0 — /simple/digline/ is
  served and lists 33 file version(s), none at 0.18.0` **nine times** and
  cleared at `every version is served (after 271s)`. That is a real race, and
  the index answered it on the served/listed distinction the message was
  written to make. By the time either build asked, there was nothing left to
  wait for: `#9 0.559 every version is served (after 0s)` in `smoke`, `#15 3.963
  … (after 1s)` on arm64.

  The two pairs, in the same three parts as every entry above:

  - **amd64 — proven in `smoke`'s build.** `#9 1.747 Collecting digline==0.18.0`
    and `#9 10.73 Successfully installed … digline-0.18.0 …`, one `RUN` (`#9`).
  - **amd64 in the multi-arch push proved nothing, as predicted.** `#11 [linux/
    amd64 stage-0 3/5]` is `CACHED`. Fifth tag running.
  - **arm64 — proven in the multi-arch push.** `#15 18.76 Collecting
    digline==0.18.0`, `#15 99.75 Successfully installed … digline-0.18.0 …`,
    `#15 DONE 104.8s` — a real install, not a cache hit.

  Three tags, one digest: `0.18.0`, `0.18` and `latest` all resolve to
  `sha256:a10d9bd7947a120dfe9324f62d96a741b40f8958ea99af4ba63df6d3b69a9a04`,
  read from the registry rather than from the build's own summary.

  **What this tag proves, and what it now costs to keep saying it.** The
  in-build `await_index.py` has printed `after 0s` or `after 1s` on every tag
  since v0.15.1 — the only one where it ever waited. The question above asked
  whether it ever prints a non-zero wait of its own; on this tag it did not,
  while the runner-level wait sat for 271s. So it is said out loud, as that
  paragraph asked: **the in-build await is a belt whose braces have held five
  tags running**, and the case for keeping it rests on v0.15.0, where the two
  edges genuinely disagreed, and on nothing since.

  **What the next tag must show:** the same two-pair reading, and whether a tag
  ever arrives where the runner-level wait clears at 0s *and* the in-build one
  does not. That is the only observation left that would re-earn the in-build
  step, and if several more tags pass without it, removing it becomes a decision
  somebody should take deliberately rather than a question this block re-asks
  every release.

### What is not covered, stated rather than assumed

The `testpypi` job installs unversioned names, on purpose — TestPyPI resolves
against a different set of uploads — so nothing holds it to a version and a
lagging index there can still resolve an older one. The examples carrying
a `uv.lock` — `ls examples/*/uv.lock` — pin exact versions that legitimately lag
a release until the locks are regenerated, and the wait says nothing about what any individual lock
resolves to. The `examples/*/.github/workflows/check.yml` are inert inside
this monorepo and are not reached by a release at all. `java-example.yml`
installs no Python package and is not a consumer.

And the part no amount of waiting closes: **PyPI's edges converge on their own
schedule.** The wait narrows the window to whatever the consuming runner can
see; it cannot make one edge speak for another. What *The diagnostic, built*
adds is not a fix for that but a record of it: when two requests disagree, the
two `index-capture` lines say whether the disagreement was between two servers
or within one. A reading, not a remedy.

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

**A new public name earns the pass, even when a pass is where it came from, and
the pass covers the new names, not the whole surface.** A release of repairs
can still add names: 0.25.1's four refusal classes were each the fix of a
finding in the pass over 0.25.0, and a release made only of repairs reads as
having nothing to pass over. It has the names. Each one is a new message, and
each crosses the boundaries it is raised across, so the three questions below
apply to it as to any field. What it does not earn is a second pass over what
the earlier pass already read: that is the work it was born of.

**New public surface is three kinds of thing, and all three are listed.**
- **The names in an `__all__`.** Diff every `__all__` between the last tag and
  the tree being tagged. Do not count them from memory: on 0.25.1 a count
  given from memory said five, and there were four.
- **The keys of the JSON contract**, which a pipeline parses as surely as a
  program imports a name. Diff `_ADDED` in `src/digline/wire/contract.py`
  between the two tags: since #312 every key added without a bump of
  `OUTPUT_VERSION` is an entry there, with the issue or ADR that added it.
  Diff `_ADDED_WORDS` beside it: since #402 a word added to a map's closed key
  vocabulary, such as a cause in `spread_absence`, is an entry there. And
  `tests/test_wire_keys.py` refuses a document that carries a key the table
  does not name. For a tag older than the table, the record is the prose above
  `OUTPUT_VERSION`, written by hand. On 0.25.1 that diff names
  `on_record_not_read` and `unread_on_record` (#287). The pass over 0.25.1
  left them out, because the rule then said *names*.
- **The fields of every dataclass an `__all__` lists.** A dataclass is its
  fields, so a field added to a class that was already public is new surface,
  and the diff of the `__all__`s cannot see it: the class's name did not move.
  `tools/public_fields.py` finds them, by importing each package and reading
  `dataclasses.fields`. Run it in both trees and diff:

  ```sh
  uv run python tools/public_fields.py > /tmp/now.json
  git worktree add --detach /tmp/last v<last>
  (cd /tmp/last && uv sync -q --all-packages \
     && uv run python <this checkout>/tools/public_fields.py > /tmp/then.json)
  git worktree remove /tmp/last
  uv run python tools/public_fields.py --diff /tmp/then.json /tmp/now.json
  ```

  It prints one line per class or field added or removed, and nothing when
  nothing moved. **0.25.3 is why.** `SuiteRuns.unnamed` arrived on a class
  public since 0.25.2, beside one new name, `run_exit_code`. The diff of the
  `__all__`s found the name and not the field. The release entry counted
  one name, and the field was found by asking before the tag. Measured across
  all 92 public dataclasses between `v0.25.2` and the 0.25.3 tree: that field,
  and nothing else.

**Two gaps, declared rather than assumed.** Neither of these three diffs sees
them:
- **A class that is not a dataclass**, and first of all a `Protocol` and its
  methods. `NameRow`, in `digline.core`, is one, so the gap is already
  occupied. A method added to it, or a parameter added to a method, changes
  what an implementer owes and moves no name and no field.
- **A change inside a function that moves no name, no key and no field**: a
  key renamed, removed or retyped inside a `wire/` builder, read by nobody
  because no diff pointed at it. That is #312.
  *Narrowed 2026-10-02, the bullet above kept as written.* A key renamed,
  removed or retyped inside a `wire/` builder now fails
  `tests/test_wire_keys.py`. If the table is edited to match, `_BASE`'s digest
  fails it, and what that test asks for is a bump. What still moves no name,
  no key and no field, and is in no diff here: a value from a vocabulary that
  becomes another word, a number that changes meaning, bytes inside a string,
  and a type on a branch no fixture reaches. `contract.py` names the four
  beside the table (#312).

**What holds that record, said here because it is weaker than the first.** An
`__all__` is code, so a new name cannot be exported without appearing in it.
The record in `contract.py` is prose that whoever adds a key writes by hand,
and no test reads it. A golden key set would force it, and only one command
has one: `COMPARE_KEYS` in `tests/test_cli.py`, for `compare --json`. The
other commands' builders in `src/digline/wire/` are pinned partly or not at
all. `tests/test_log.py`, for one, pins the fields of `log`'s types, which are
not its wire keys. Counted on 2026-10-01: nineteen `*_json` functions in
`wire/`, and one golden set. So the control on `contract.py` is the diff of
`src/digline/wire/` between the same two tags, read for added keys. A key that
appears there and not in `contract.py` is a record somebody owes, and it is
still surface to pass over.

*Corrected 2026-10-02, the paragraph above kept as written.* The record is no
longer prose alone. `_BASE` and `_ADDED` in `contract.py` are a table, and
`tests/test_wire_keys.py` holds every document `wire/` builds to it, key and
type, at every level, under fixtures that reach every shape and key in it. An
addition cannot reach `main` without an `_ADDED` entry, so the diff of `_ADDED`
is the list, and the diff of `wire/` is no longer the control. The count above
was also short. There were twenty-three builders, the four `run_document`
helpers among them. `shape_json` and `config_json` were each pinned by one
test, which the search that counted them did not find. Measured before the
table: of sixteen changes to keys quoted in no test, fifteen left the suite
green (#312).

Ruled 2026-10-01, the names in the morning, the keys the same day, and the
fields of a listed dataclass that afternoon, before the tag of 0.25.3.
`private/delta-pass-0.25.1.md` is the first pass run under the first half.

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
3. **The example locks:** regenerate them, then dispatch `ci.yml`. See *The example
   legs* below.
4. **The status block:** update *The index race* → *Status: what each path has
   proven* with what this tag proved and what the next one must show. It
   changes every release, so it is updated by this step, not from memory.
5. **The example reports:** re-render every committed `report.html` **whose
   recorded commit is clean** against the tagged release, in the order the
   ritual requires — commit the example, render, commit the report on top,
   never amend and **never rebase** — so each report records a commit somebody
   can reach. A report
   is a photograph of the run that produced it, which is why a string change
   does **not** regenerate one: four of them carried a stale `What answered`
   heading from the moment that heading was corrected, deliberately, until the
   next tag. This step is what clears that debt, and it is a step so that it
   happens by procedure rather than because somebody noticed a heading.

   **`never rebase` is not a second way of saying `never amend`, and it is the
   one the process pushes you into.** A report names a commit; a rebase rewrites
   commits; so a rebase leaves every report naming something that no longer
   exists. Paid for on v0.21.2. Nine reports had been re-rendered, each
   recording its parent, when `main` moved and the branch went `BEHIND` — which
   the ruleset requires you to fix before merging. The branch was rebased, and
   **eight of the nine reports were left naming orphaned commits**: the files
   still said `86d2ff8`, `7904aa6` and six more, and those commits had ceased to
   be. Only the first survived, because it names a commit that was already on
   `main`.

   **The remedy is to merge `main` into the branch instead**, which is what
   every other branch in this repository does anyway — `git merge origin/main`,
   whose merge commit reads *Merge remote-tracking branch 'origin/main' into
   &lt;branch&gt;*. It satisfies the same up-to-date requirement and rewrites
   nothing.

   ```sh
   git merge origin/main        # not `git rebase origin/main`
   ```

   Then **check, rather than assume it held** — one line, and it is the only
   thing that answers the question the step exists for:

   ```sh
   for f in examples/*/report.html; do
     grep -q -- '-dirty' "$f" && continue          # curated: see the rule below
     c=$(grep -oE '\b[0-9a-f]{40}\b' "$f" | head -1)
     git merge-base --is-ancestor "$c" HEAD || echo "unreachable: $f ($c)"
   done
   ```

   The `-dirty` skip is not tidiness: a curated report names a commit that is on
   no branch **on purpose** — checked on v0.21.2, `examples/classifier`'s
   `b44ad6f` is a real object that `git branch --contains` finds nowhere — so
   without the skip this check reports the one report the step is telling you to
   leave alone. The same signature does both jobs, which is the point of it.

   Written down because the original rule named the door nobody is pushed
   through and stayed silent about the one the CI pushes everybody through:
   `--amend` is a choice somebody makes, a rebase is what an out-of-date branch
   asks for. A step that forbids the first and says nothing about the second is
   half a step.

   **A report whose commit ends in `-dirty` is curated, and this step leaves it
   alone.** Read it as a signature rather than as an accident: `-dirty` means
   the tree held uncommitted changes when the run was made, so the state that
   produced the report is **not in the repository and cannot be checked out**.
   For an ordinary report that would be a defect — the whole point of recording
   a commit is that a reader can reach it. For these it is the *declaration*:
   the example is showing something the committed application does not do on
   its own, and re-rendering it from a clean tree would silently replace the
   report its README explains with a weaker one that agrees with nothing
   written around it.

   `examples/classifier` is the one today, and its README says so in the same
   words: the perturbation that makes one case change its mind is not in this
   repository, so a clean run reproduces the baseline exactly and would render
   a report with nothing moved. The commit it records is marked `-dirty` and is
   not meant to be checked out.

   **Read the signature, do not keep a list.** `grep -l -- '-dirty' examples/*/
   report.html` is the whole rule, and it is the rule rather than a list of
   names for the reason this file has learned twice over — a count said `nine`
   while eleven legs ran, and a sentence named three locks while six existed. A
   name written here goes stale the day somebody curates a second report; the
   signature is carried by the artefact and cannot.

   So the step is not *re-render the examples*. It is **re-render the ones that
   are not claims**, and the discriminator is in the file you are about to
   overwrite.

   **There are two kinds of curated report and only one of them carries a
   signature.** A perturbed tree stamps `-dirty`. A **live measurement** stamps
   nothing, because the tree was clean when it ran: being live is not being
   dirty, and the rule above reads dirtiness. So the signature rule, which is
   right about what it can see, is blind to the second kind — and the second
   kind is the more valuable artefact, because it cost a key and a real model.

   `examples/prompt-first` is the one today, and **it is held by judgement, not
   by signature**. Its commit is clean, so the rule says re-render it; doing so
   without `DIGLINE_LIVE=1` and a key would replace a live measurement with a
   stand-in's. Its README says what that is worth, and the sentence is the
   reason this paragraph exists rather than a list: *"a baseline of canned
   answers scored that way is a measurement of nothing […] and the danger is
   precise: it looks exactly like a green run."*

   Naming it here contradicts *read the signature, do not keep a list* directly,
   and that is deliberate: **a declared list is less bad than a signature that
   silently fails to cover a case.** A stale name is a thing somebody notices; a
   rule that quietly does not apply is not. The list stands until the marker
   below exists, and the first thing that marker buys is deleting this
   paragraph.

   **Owed: a way for a run to declare that a real provider answered it — and it
   is an ADR before it is code**, because it adds a field to the run document,
   which is a published format under `SCHEMA_VERSION`.

   **The proof that nothing in the tree can answer it today**, checked on
   v0.21.2 rather than recalled:

   - A target's `config` property records **what it sends, and only that** — and
     that is correct, not a defect. `AnthropicTarget` keeps an injected client in
     `self._injected` and its `config` returns `super().config` plus
     `max_tokens` and `temperature`; the client is never mentioned
     (`packages/digline-anthropic/src/digline_anthropic/target.py`). **It is
     precisely because the target declares what it sends that the document
     cannot say who answered.** A run driven by `fake.FakeAnthropic()` writes the
     same `target_config` as a live one — `provider: anthropic`,
     `model: claude-haiku-4-5`, `resolved_model: …` — and no reader can tell them
     apart.
   - `DIGLINE_LIVE` appears **nowhere** under `src/` or any `packages/*/src/`. It
     is an example convention, read in four `suite.py` files to choose a client,
     and it never reaches a document.
   - Neither `Run` nor `Suite` has a field for it. `Run.metadata` is free-form,
     nothing in `src/` writes such a key, and every committed baseline has `{}`.
   - **`Run.rejudged_from` is the precedent to copy, and the near-miss that shows
     the shape is right.** `run/replay.py` says it exists so that *"no reader and
     no pipeline can mistake it for a measurement"* — exactly the job. But it
     separates *replayed from stored answers* from *measured now*, and a run
     against a stand-in is measured now by that definition: the field is absent
     for a faked run exactly as it is for a live one.

   **The trap, and it is the step immediately before this one: `uv sync` writes
   a `uv.lock` into the examples that deliberately keep none.** That lock
   is untracked, so the tree is dirty, and a report rendered from a dirty tree
   is stamped `-dirty` — *the exact marker the rule above reads as "leave this
   alone"*. Run the step as written and you curate, by accident, the reports it
   told you to re-render; the next release then skips them, and the one after
   that finds a report nobody can explain.

   It is written here rather than left in a commit message because a rule the
   preceding step can disarm needs the disarming named next to it. Two details
   make it bite:

   - **The report records the commit of the *run*, not of the render.** So
     re-rendering from a clean tree does not repair a run made from a dirty
     one: the whole example has to be run again.
   - **`git status --porcelain` is what digline reads** (`host/environment.py`),
     so the check is exactly that, from the repository root, and it must be
     clean **before the run**, not before the render.

   The order that works, per example:

   ```sh
   uv sync -q                       # may write a lock this example does not keep
   git ls-files --error-unmatch examples/<name>/uv.lock >/dev/null 2>&1 \
     || rm -f examples/<name>/uv.lock
   git status --porcelain           # must print nothing
   uv run --no-sync digline run    --suite <suite>
   uv run --no-sync digline report --suite <suite> --run latest --locale en \
       --out report.html
   ```

   `--no-sync` on the two digline calls is what keeps the lock from coming
   back between the check and the run. And some examples need more than a
   suite: `quickstart-toml` and `external-app` answer over HTTP, so their stub
   has to be running or every case fails the same way — the refusal says so,
   and says how many cases it would take with it.

6. **The capture's two lines:** in the same `docker-publish` log step 2 opens,
   find the `index-capture` pair for the core's pin — `side=wait` and `side=pip`,
   same `name`, same `RUN` — and read it against the table in *The index race* →
   *The diagnostic, built*. **Then write what it said into the Status block,
   including when it said nothing.**

   **A quiet log is not evidence of agreement.** It is equally evidence that the
   capture did not run — an `AWAIT_INDEX_TIMEOUT` that arrived as `0`, a mount
   that moved, a `PYTHONPATH` lost to an edit of the `RUN` — and a reader meeting
   a silent build later has no way to tell those apart. So the absence of the
   lines is itself the first finding, and it is a defect rather than a calm
   release: **go and look at why**, do not record a divergence that did not
   happen. Only once the lines are there does their agreement mean anything.

   Which makes the sentence to write, on a release where nothing went wrong,
   this one: *the capture ran, the pair was present for every pin, and it had
   nothing to explain.* It is the same principle as naming the `CACHED` amd64
   leg every time — a thing that proves nothing and is not named reads
   afterwards as a thing that passed — and the same distinction as a
   **cancelled** run being neither red nor green. Three surfaces, one rule: say
   which of *agreed*, *disagreed* and *never asked* you are looking at, because
   only the first two are readings and they all look alike in a log nobody
   annotated.

   Numbered last and not at 3, where its reading belongs: these numbers are
   addresses, cited from five places in this file and from
   `tests/test_release_followup.py`, and renumbering them to tidy an order would
   break the citations silently. Read it at step 2; write it at step 4's block.

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
never that what it says is true. **Step 6 is the same again, and one half of it
is the most mechanical thing on this list** — whether the `index-capture` lines
are in the log at all is a `grep`, and nobody has written it; what the pair
*means* is a reading and could not be written. All three stay yours. What the
job removes is the possibility of a step being *forgotten*, which is a different
thing from it being done well.

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

**The example legs need a dispatch after the lock regen.** Two things
combine. `examples-from-pypi` is gated `if: github.event_name != 'push' &&
!= 'pull_request'`, so landing the lock commit — its pull request, and the push
to `main` its merge makes — does not run it; and the
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

**Every example that has a leg**, and the number is deliberately not written
here. It said `nine` for as long as there were nine; by v0.17.1 the dispatch ran
**eleven** while this section still said nine. A count in prose is a claim the
repository can contradict, and this one did no work the rule does not do — the
same argument that took `seven so far` out of `SECURITY.md` one file over. The
legs are whatever `examples-from-pypi` expands to: read the run, not this
sentence.

The examples that carry a `uv.lock` pin the exact version; the rest resolve at
install time. Regenerate every one of them — `ls examples/*/uv.lock` is the
list, and `.github/release_followup.py` reads the same glob — with `uv lock
--upgrade-package digline` in each, commit on a branch, land it through a pull
request, then dispatch against `main`. Do not work from a
list written here: this sentence named five for as long as five was right, and
`mcp-tools` arrived with a sixth that the ritual then skipped for a release.

Some of those locks pin a **plugin** as well, so a release that moves a plugin
needs `--upgrade-package <plugin>` beside `digline` or they come back naming a
plugin version that is no longer current. **Which ones is the same question as
which locks exist, and it has the same answer — look:**

```sh
grep -l 'name = "digline-anthropic"' examples/*/uv.lock
```

This sentence named three of them by hand until 2026-09-22, and they were the
right three. That is the point: so were the five above, until they were not.

**Dependabot moves only what a manifest declares, so a transitive dependency
never moves on its own.** Its weekly version updates (`.github/dependabot.yml`)
cover the root lock and every example lock, but they bump the packages a
`pyproject.toml` names and nothing beneath them; its automated security
updates, which would, are off for this repository (the
`automated-security-fixes` endpoint reads `enabled: false`). Measured on
urllib3: the release that fixed three advisories was on PyPI on 2026-09-15;
the version updates of 2026-09-28 (#183, #184) moved `ruff`, `langchain` and
the other declared packages and left urllib3 on the release before it, in the
root lock and in two example locks, for two weeks, until the alerts raised
nine entries on it. This step does not close that gap and was never meant to:
`uv lock --upgrade-package <name>` moves the package it names and keeps every
other pin where it was, and it names only digline and the plugins.

**An advisory on a transitive dependency therefore needs an
`--upgrade-package` that names it, and whoever triages the alert runs it.**
In its own pull request, as soon as the alert is judged — not riding the next
release, which would not move it — in every lock the alert lists:

```sh
uv lock --upgrade-package <dependency>   # in the root and in each example the alert names
```

Only the named package should move; read the diff before committing. When no
fixed release exists yet (nltk, GHSA-8mgp-746c-j5xp), or a parent's bound
refuses it, there is nothing to name — say so on the alert and leave it open.
*Before the tag: the alert list* is the backstop: an open Dependabot alert
with a fixed version is judged there, before the tag, if nobody did it sooner.

*(Worth trying next release: regenerate the locks **before** the tag.
They cannot resolve a version PyPI does not have yet, so it probably has to stay
a post-tag commit — but if a lock can be written against the version about to
ship, the dispatch stops being necessary.)*

**The approval is a person's click, and never a session's.** A session that
drives a release stops at the `[GATE]`, says the run is waiting for `pypi`,
and waits. The approval is given in the Actions tab by the person who owns the
account. A session never approves it through the API — no `POST` to
`pending_deployments`, not even when told "approve". An API approval is
recorded under that person's login, and nothing afterwards tells it apart from
their click. It is the one point of this file where somebody has to stop. If a
session clicks it, the gate becomes an automatic step with a person's name on
it, which certifies a decision nobody made. Ruled on 2026-09-30, at v0.24.0,
after a session offered to approve it.

**The counts come after the click, and they are owed.** They are:
- the files built, and the `twine check` lines that read `PASSED`;
- TestPyPI's selection, `publish` against `skip`;
- the `imported` line;
- the quickstart's calls.

*Amended 2026-10-04: the counts are now in front of the approver before the
click.* `publish.yml` writes them to the job summary, on the run's page where
*Review deployments* is, before the `pypi` job starts waiting. The build job
writes the `twine check` count. The `testpypi` job writes TestPyPI's
selection, the `imported` line, the quickstart's calls, and **PyPI's own
selection, asked before the gate**. That last one is new: the `pypi` job
selects only after the click, and TestPyPI's selection is against another
index with another history. Nothing races the click, because the summary is
written by the run and not reported by a session
(`.github/gate_summary.py`). **Not yet seen:** whether the summary shows
beside the button on this repository's page, and how a wait timer on `pypi`
would interact with its required reviewer. The next release is the test of
both.

The ruling below stands for what it rules: a session still reads the counts
from the logs once the approval is recorded, and records them. As written on
2026-10-02:

They are read from the finished jobs' logs. That takes longer than the click,
so they reach the approver after it, and the session does not hold the gate
open to read them first. **They are still owed.** The session reads them once
the approval is recorded and gives them to the approver. They then go into the
release's paragraph in *Status: what each path has proven*. A count that never
arrives is the failure, not a count that arrives after the click. A count that
does not match what the tag was meant to publish is read as a finding, as it
would have been before the click: the upload is spent by then, and that is the
same as on every release before this rule.

Ruled on 2026-10-02, at v0.26.0, after three releases in a row where the
approval came before the counts could. It came in an 11-second window that a
20-second poll never saw (v0.25.2), about 4 seconds after the wait (v0.25.3),
and 1 second after it (v0.26.0). Recording each time that the old order had not
worked was recording the same thing three times. The order changed instead.

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

**Unless the run was re-run.** `approvals` answers for the run's **latest
attempt**, and `gh run rerun --failed` makes a new attempt that has nothing to
approve. The re-run that *Signatures on the GitHub release* calls safe (safe for
what it uploads) therefore returns `[]` from then on, and the approval of
attempt 1 cannot be read again. v0.21.0 met it: the signatures job lost the
index race, the re-run made it green, and `release-followup` went from *records
an approved* at 10:12 to *records no approved* at 10:14 about a gate that had
held. **The deployment's states do not replace the record.** `testpypi` has no
reviewer and goes through the same `waiting → queued → in_progress → success`;
all that tells the two apart is how long `waiting` lasted, and a duration is
not an approval.

So `release-followup` keeps what it reads. A run that reads an approval uploads
it as the artifact `followup-approvals-<publish run id>` (90 days), and a run
that finds `publish` on attempt 2 or later with an empty endpoint reads the
newest one back. It accepts only a record of *that* run, from an *earlier*
attempt. With nothing kept, the line says the approval is **unreadable after a
re-run**, never that the gate did not hold, and stays unticked. v0.21.0 is that
case, because it predates the artifact: its reading lives in the log of
`release-followup` run 36311781707, and #149 was closed by hand with that line
quoted.

**Considered and refused, 2026-09-27: an attestation file.** It would be a
reviewed file in the repository saying, for a release, *the gate held, here is
the evidence*, and it would tick the line. It is the obvious proposal and it
will be made again, so here is why not. Once it exists, it is a written way to
say *trust me, it happened*, and it works for any line and any release. Today
it would be used for an honest case; in six months somebody in a hurry will use
it, and the file cannot tell the two apart. It also replaces the evidence with
an assertion exactly when the evidence is missing, which is when the evidence
matters most. A release whose reading was not kept is closed by hand, once,
with the reason written in the issue.


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

Everything before PyPI is repeatable. A tag can be re-done on a fixed commit —
through the ruleset that protects it, by *Re-doing a tag*, and only on a commit
`main` contains: the run starts over, and whatever reached TestPyPI in the
meantime is skipped rather than re-uploaded.

`digline.dev` is rebuilt only on a `v*` tag. The site describes what the core
says — the quickstart, the format, `docs/` — and a plugin release changes none
of it.
