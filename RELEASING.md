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

**Then one more, which no test reddens: say which decisions this release
ships.** Every record in `docs/adr/` carries `- Shipped:`, a core version or
`unreleased`:

```sh
grep -l '^- Shipped: unreleased' docs/adr/*.md
```

For each one whose implementation is in this release, write the new version
and make sure its status is `accepted`. Decide *is in this release* from the
tree being tagged, not from the changelog: a changelog cites a record when it
mentions it, and that is how ADR 0030 — cited in 0.19.1 as "accepted, not
implemented" — would have been given a version it never shipped in. `tests/test_adr.py` refuses a version
that has no row in `RELEASED` and a `proposed` record that names a version,
but it cannot see a record left `unreleased` after its code shipped — nothing
in the tree says honestly that a decision is in force, and a status derived
from the code would be a guess. This step is the only thing that sees it. It
was missed for 0020, 0021, 0022 and 0024, which read `proposed` for over a
week after 0.13.0 and 0.14.0 shipped them.

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
3. **Expect the image job to go red on this commit** and read it as the short
   post-tag red rather than a defect: dating the heading switches off
   `image_pins.py`'s window substitution, so the build waits for a version the
   index does not serve yet. It heals when `publish` finishes. This is not the
   days-long window red described above.

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
  uv run --project <digline checkout> digline run --suite suite.py
  ```

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

Do it in the browser you use, and in a second engine if you have one. `SameSite`
is where engines have differed. If step 3 is refused, the release is wrong, not
the browser, and ADR 0033 is reopened before anything ships.

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
pull request, wait for green, then merge.** `main` here is protected by a
ruleset nothing bypasses — a pull request (zero approvals), the two `gates`
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

- This repository's `main` requires `gates (3.12)` and `gates (3.13)`, and
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
`gates (3.12)` or `gates (3.13)` is red, the remedy is to fix what reddened it —
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

### Tag the merge commit, and nothing else

**The tag goes on the merge commit of the release pull request, once it is on
`main`.** Not on the release commit on its branch, not on a branch head, not on
anything `main` does not contain. `main` is protected — a pull request, the two
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

**On the first release after this landed** (2026-09-26, not yet exercised):
open the `publish` run and the `docker-publish` run and confirm each has an
`Is this commit on main?` job that ran and passed, printing `<tag> (<sha>) is
on main.` — then delete this paragraph in the follow-up pull request. A green run
whose job list lacks it is not the same evidence.

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
which is what makes `gh release upload --clobber` safe.

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
   never amend — so each report records a commit somebody can reach. A report
   is a photograph of the run that produced it, which is why a string change
   does **not** regenerate one: four of them carried a stale `What answered`
   heading from the moment that heading was corrected, deliberately, until the
   next tag. This step is what clears that debt, and it is a step so that it
   happens by procedure rather than because somebody noticed a heading.

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

   **The trap, and it is the step immediately before this one: `uv sync` writes
   a `uv.lock` into the five examples that deliberately keep none.** That lock
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

*(Worth trying next release: regenerate the locks **before** the tag.
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

Everything before PyPI is repeatable. A tag can be re-done on a fixed commit —
through the ruleset that protects it, by *Re-doing a tag*, and only on a commit
`main` contains: the run starts over, and whatever reached TestPyPI in the
meantime is skipped rather than re-uploaded.

`digline.dev` is rebuilt only on a `v*` tag. The site describes what the core
says — the quickstart, the format, `docs/` — and a plugin release changes none
of it.
