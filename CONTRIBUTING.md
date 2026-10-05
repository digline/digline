# Contributing

Thanks for looking. A few things worth knowing before you open a pull request.

- **Run the gates**, from the repository root:

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

  All of them are green on `main`, and CI runs them on 3.12, 3.13 and 3.14 — the
  `gates` job of `.github/workflows/ci.yml` is the list, and this is a copy of
  it, held to it by `tests/test_releasing.py`. The tests run in two commands
  because `tests/test_type_gate.py` writes into `src/digline/` while other tests
  read that tree; it refuses to share a parallel run. `--locked` matches CI: it refuses a `uv.lock` that has fallen behind
  `pyproject.toml` rather than rewriting it, so a lock you forgot to commit
  fails here instead of passing locally and reddening the pull request.
- **Run pyright as `uv run pyright`, which is how CI runs it.** pyright does
  not use the venv its own script sits in. It reads the packages of whichever
  `python` comes first on `PATH`. Called as `.venv/bin/pyright` from a shell
  where the venv is not activated, it checked `/usr/bin/python3`'s packages,
  found none of the plugins' SDKs, and reported **2567 errors on a tree that
  had none** (2026-10-02). `uv run` sets `VIRTUAL_ENV` and puts the venv first
  on `PATH`, and on the same tree it reported 0. So did `.venv/bin/pyright`
  with those two set by hand.
- **`tests/test_layering.py` is not a style test.** It keeps `digline.core`
  pure and importable on its own. If it fails, the change is wrong, not the test.
- **Every assertion needs a failing case.** A check that cannot fail is a bug
  (fixed decision 3), and the test that proves it can is the one that says so.
- **If you add a flag that turns something on, the flag's tests do not cover
  the default.** They feel like they do, which is why this is written down.
  Measured on `digline view --allow-promote` (ADR 0032): the refusal was deleted
  from `do_POST`, and **48 tests exercising the flag all passed** — every
  promotion through the enabled server, every refusal it forwards, the `Host`
  and `Origin` guards. Not one of them can see a default that stopped refusing,
  because not one of them runs on the default. Five tests caught it, and all
  five were written about the *off* state.

  So the rule, for the next opt-out as much as that one: **mutate the default
  away and run the suite.** If it stays green, what you have tested is the
  feature, not the boundary — and a boundary is the only reason an opt-out
  exists. The same run is what catches a test that *looks* like it covers the
  off state and cannot: one here went green under the mutation because its
  fixture had a single run that was already the baseline, so no row could have
  carried the button on any server at all.
- **If you add a guard in front of another one, the old guard's tests go
  empty.** A request that the new guard refuses never reaches the old one, and
  a test expecting a refusal cannot tell whose it got. When `digline view
  --allow-promote` gained its launch key (ADR 0033), the tests of the `Origin`
  check, the rebinding guards and the walk over every refusal type would all
  have passed **with their guards deleted**. The key refused first, and a
  403 from the key reads the same as a 403 from the origin check.

  So, for every test of a guard that now sits behind yours: **send what your
  guard asks for**, so the request reaches the guard the test names. Assert
  the sentence as well as the status, so the refusal says whose it is. Then
  **mutate the old guard away and run the suite.** Green means the test was
  already testing yours. This is the same family as the flag bullet above,
  where a test stays correct about a request while what stands in front of
  it moves, and it has four instances in one week.
- **A mutation is a red made on purpose, so look for another tree before you
  make one.** Two bullets above end in the same instruction, and the sweep
  bullet below repeats it: delete the thing the test is supposed to notice and
  run the suite. That instruction manufactures a failing test. The failure
  stays inside your checkout. **The red does not**: push it to a branch with a
  pull request open and it is a CI failure with your name on it, and saying
  *"`test_x` fails"* anywhere makes it a claim about the code. Whoever reads it
  has no way to know it was meant.

  **Two people on one file and two on one guard are different situations**, and
  only the first is one git can see. Editing the same file conflicts, out loud,
  at merge. Mutating a guard somebody else is building conflicts with nothing:
  their tree is untouched, no merge complains, and all they learn is that a
  test neither of them wrote is failing. Worktrees make this more likely, not
  less — they are how parallel work is done here (`CLAUDE.md`, the worktree
  audit) and each one hides its own mutations from the others.

  So: **mutate in your own worktree, restore before you push, and never leave a
  mutated tree to go and do something else.** Restore from a copy rather than
  `git checkout -- <file>`, which takes uncommitted work with it. If you report
  a red you caused deliberately, say in the same sentence that you caused it.
  And from the other side: **a red on a guard somebody is currently building is
  a worktree question before it is a defect** — run `git worktree list` and look
  at the branch names before filing it as one.

  **And nothing tells you which tree a session is in.** `git worktree list`
  gives you the trees; the listing of live sessions gives a name, a state and a
  start time, and **no working directory** — so a note about a red cannot be
  addressed to the tree that made it. Send it to every live session, open with
  *"if this is you"*, and let whoever it does not concern say so. Measured
  while writing this bullet: the note went to two sessions, one of them was not
  the one, and it said so in a minute. The noise is the price of the gap, spent
  deliberately rather than discovered.
- **A process stopped by name is stopped in every tree.** This is the bullet
  above one level down: worktrees separate files, not processes. `pkill -f
  'python3 stub.py'` stops the stub you started, and it also stops the one
  another session started for `quickstart-toml` in its own worktree. Whoever
  it hits sees a test fail against a service that was up a second earlier,
  and nothing in that failure points at you.

  The remedy is the same one: **narrow it to what you started.** Stop the
  process by the PID you know, not by the pattern: `python3 stub.py &
  STUB=$!`, and later `kill "$STUB"`. The instance that prompted this bullet
  is a pattern kill used on 2026-09-29 to stop the stub after re-rendering
  `quickstart-toml`'s report (#223). Whether it stopped anybody else's is not
  known, and that is the shape: the session on the receiving end would not
  know either.

  **The PID is not always there to keep, and the rule has to hold where it is
  not.** Three cases where `$!` does not name the process that is serving:
  - `uv run python stub.py &` gives you `uv`'s PID, not Python's, and a
    backgrounded `uv run` outlives the step that started it (`ci.yml` records
    why it starts the stub with `python3` for that reason).
  - A stub started by a script, or as an agent's background task, hands you
    the script's or the task's handle, or nothing — not the stub's PID.
  - **A second stub on the same port dies at once.** `stub.py` listens on
    8730, fixed. Started while another tree's stub holds it, yours exits with
    `Address already in use` on a stderr nobody reads — measured on
    2026-09-29, exit 1 within a second. `$!` then names a dead process,
    `kill "$STUB"` does nothing, and your tests talk to the other session's
    stub until it stops under them. That is this bullet's failure, reached
    without any kill of yours.

  So three rules, in order:
  1. **Take the PID when you start it, and check it is yours that serves.**
     `python3 stub.py & STUB=$!`, or `echo $! > .stub.pid` inside your own
     tree when something else will do the stopping; a stub in the foreground
     of a background task is stopped by stopping the task. Once it should be
     listening, `kill -0 "$STUB"`: a stub that lost the port has already
     exited, and whatever answers on it is somebody else's.
  2. **If the PID is lost, find yours by what only yours has**: its working
     directory, which is in your tree (`lsof -a -p <pid> -d cwd`). Confirm it
     before the kill, not after.
  3. **Never by port, and when in doubt, not at all.** `lsof -ti :8730 |
     xargs kill` is a kill by pattern under another name: it stops whatever
     holds the port, which is exactly the other tree's stub in the third case
     above. A stub left running costs less than one stopped under somebody
     else.
- **If you write a permission as a condition, write what fires it.** A
  condition says *when* the answer will change, and that is worth doing: ADR
  0032 §4a let an agent run `digline migrate` "for as long as every step is
  required to write nothing semantic", so the permission could not outlive the
  property it rested on. The day came with schema 17, and the answer flipped as
  written. **No test caught it.** The only standing check covered two fields,
  and the step that met the condition moved neither. A person noticed, by
  reading the previous release's changelog while writing the next one.

  That is the shape: **a condition that describes when it will fire, with
  nothing that fires it, is a condition somebody has to notice.** It expires
  silently on every day nobody is reading. So when you write the next one, put
  the check beside the sentence: a test that turns red on the day the property
  breaks, named where the condition is stated. If none can be written, say so
  in the same place, and say who is expected to notice. Then pin the answer
  once it has flipped, because the flip is a new rule and it can drift like
  any other.
- **Decisions in `CLAUDE.md` marked fixed need an ADR in `docs/adr/` first**,
  not a pull request that quietly works around them.
- **When you amend a record, sweep for its premise with the line breaks
  folded.** Prose here wraps at about 79 columns, so a sentence worth amending
  is usually two lines, and `grep "the whole sentence"` finds none of the places
  it is written — including the file you are editing. Match against a form with
  runs of whitespace collapsed (`re.sub(r"\s+", " ", text)`), over every `*.md`
  and the `*.py` under `src/` and `tests/`.

  **This is the difference between one site and two.** ADR 0010 §1's premise,
  *"Which cases were in it stays in the repository"*, returned **nothing** to a
  phrase search in the very record that contains it. Folded, it returned two:
  §1 itself, and ADR 0028's `Assumes` line citing the same property. The second
  one had to be read and deliberately left — what it depends on survived the
  amendment — and that is a decision nobody can make about a site they did not
  find. **The mirror is the method's own limit: a clean search hides a real
  site, and a full one can merge two questions** — the same fold matched *who
  are we protecting against* in two records, meaning who reads a digest in one
  and whether the reader already holds the text in the other, and only the
  first was ruled, so read every site it returns instead of counting them.

  **A folded search still only finds strings, and the same claim can be written
  twice in different words.** The tenant-separation correction (#141, ADR 0002
  §1) named three sites that repeat the claim it corrects. A **fourth** turned
  up two days later, found by somebody editing the file for another reason:
  `ResultStore`'s class docstring says *"the filesystem then enforces the
  separation that a field could only describe"*, where `file_store.py`'s module
  docstring — which the list did name — says *"the separation between
  perimeters is something the filesystem enforces"*. Folded and counted, `the
  filesystem enforces` matches the named site and **not** the missed one; `The
  tenant is a directory`, which both sentences open with, matches both. Note
  what does *not* explain the miss: both are code, and one of them was named.
  **So anchor on the part a paraphrase keeps** — the subject, the name of the
  thing, the path — and read what comes back, rather than on the phrase that
  made you notice the claim. (#140)

  **And a guard can be the thing that only finds strings.** Written **one hour
  after the paragraph above**, and found with it:
  `tests/test_promotion_conditions.py` holds an obligation no signature can
  state — that a store implementing `promote_baseline` reaches condition 8 —
  and its first version asked whether
  the class's source *contains* the name. It passed against a store that kept
  the private method holding that call and stopped calling it, which is exactly
  the backend the guard exists to catch. `inspect.getsource(cls)` had the name
  in it, because a class that never calls a method still contains it. The guard
  now parses the class and follows `self.…` calls out of `promote_baseline`.
  **The lesson is the paragraphs above, one layer in**: a search over source
  text is a claim about the text, and a test built on one inherits every limit
  the sweep has — with the difference that nobody reads a test again once it is
  green. What caught it was the mutation the bullets further up ask for: delete
  the thing the guard is supposed to notice, and watch it fail.

  **A test's name is the same kind of claim, one step further out.** Found on
  2026-09-28 while measuring what a comparison says about a reference with an
  errored verdict. F-10's headline test is
  `test_the_headline_no_longer_claims_every_case_could_be_judged`. Its body
  asserts that the reference's clause appears, and never that the claim went.
  The claim did not go: on that test's own fixture, the headline it builds
  still reads *"Every case could be judged."*, after the clause. The guard above
  had the name in its source and no call behind it. This test has the property
  in its name and no assertion behind it.

  **And the mutation would not have caught this one**, because there was
  nothing to delete: the property never held. Written into the body, the
  assertion would have been red the day the test was written. So read a test's
  name as its first assertion. If the name says *no longer*, *never* or
  *refuses*, one line of the body says it too.

  **Then say in the amendment which method built the list.** *"One other site"*
  is a claim about a search before it is a claim about the repository, and a
  reader who cannot tell which search you ran cannot tell whether the list is
  short or the sweep was. The same applies to `git grep -i <word>` for a word
  that appears in more spellings than you checked: state the pattern, not the
  count alone.
- **The three bullets above name one shape, and it is now measured: right about
  the fact, wrong about where it lives.** Each of them found it once and called
  it something else — a guard in front of another one, where a test was right
  that a refusal came and wrong about *whose*; a folded search, where a
  correction was right about its claim and wrong about which files carried it;
  a guard built on `inspect.getsource`, where the name was right there in the
  text and the call graph never reached it. Three anecdotes, three names, one
  shape.

  **Measured on 2026-09-28.** Seventeen claims about this repository and its
  three siblings — written down first, then checked one by one against
  `origin/main`. **Twelve right, five wrong, and not one of the five wrong
  about whether the thing existed.** Every miss was the address: which bullet
  of this file carried a count, which section of a record carried a correction,
  which of two ADRs had a qualified `Shipped:` line, how far a numbered series
  of files ran, and whether a row had *landed* or been *never owed*. Nothing
  was missing. Each thing sat one container over from where it was said to be —
  the neighbouring bullet, the neighbouring section, the sibling record, one
  item further along.

  **So the rule this adds to the three: check the container as hard as the
  content.** When you write *"X is in Y"*, grep for X and read **which** Y came
  back; when you write a count, enumerate it rather than recall it. The three
  bullets above tell you how to find every site of a claim. This one says that
  finding them is not the hard part — *saying which one you found* is, and a
  citation to the wrong section is read as a citation, not as a guess.

  **And the half worth the measurement:** two of the five re-made a correction
  the tree already held in writing. One said a row *landed* where the record
  says *"this row was never owed"*; one filed a correction under the section
  that has none instead of the section that carries it, dated, twice. **The
  repository was already right about the thing the claim was wrong about.**
  That is the failure mode with teeth, because it survives a careful reader:
  the sentence is true, the record agrees with it, and only the address is
  false — so nothing in the citation looks like something to check. **One of
  those two is repaired around this change** — ADR 0002 §5 had no dated note at
  all, so it read as settled; #179 gave it one while this was being written, and
  this adds what was still missing beside it: *which* sentence is owed, and that
  the structural half and world 1 do not wait. The other is in a working record
  outside this repository and is corrected there.

  **The fifth miss earned no repair, and that is the sharper lesson of the
  five.** The claim was that ADR 0033's `- Shipped:` line was qualified like ADR
  0030's; it is bare. The finding was right — and the fix drawn from it was
  **refused**, on 2026-09-28, in these words: *the bare line is correct, and
  "where the record first shipped" answers one question and answers it well.*
  `RELEASING.md`'s *say which decisions this release ships* step says to drop a
  qualifier once the rest ships, `tests/test_adr.py`
  defines the line as the release a record's behaviour **first** shipped in, and
  a qualifier names what is **not built** — §11 is built, so bare is what the
  convention produces, not what it failed to produce. #179 had already declined
  the same change for the same reason and said so in its body. **So: a
  difference is not a defect.** A reconnaissance says what the tree holds; whether
  it should hold something else is a second question, with a different owner and
  a convention to read first. Finding a surprise and proposing a repair are two
  passes, and the second one is where this went wrong even though the first was
  right.

  **And the measurement found a live one while the repairs were being written**,
  which is the argument for measuring rather than remembering. ADR 0023's
  *Amends* line cited *"ADR 0002's Consequences, **second** bullet"*. True the
  day it was written; ADR 0034 inserted a bullet above it on 2026-09-27 and made
  it the third, and nothing that anybody touched was the thing the line points
  at. It is now named instead of counted. **So the specific rule, because
  ordinals are where this shape breeds: cite a section, a bullet or an item by
  something it carries — a name, a key, a first phrase — not by its position.**
  ADR 0002 §8 has paid for this twice in one section, once for its conditions
  (*"the argument for naming conditions rather than counting them, made by the
  correction of a count"*) and once for its own number, which moved when §1-bis
  was inserted. A position is a claim about the neighbours, and the neighbours
  are not yours.

  **Fold the verification too, or it confirms anything.** Naming instead of
  counting is the remedy upstream; this is the remedy downstream, and **without
  the second you cannot confirm the first.** That ordinal wrapped across two
  lines in `0023-capture.md`, and the same wrap beat the same sentence three
  times on 2026-09-28:

  1. It hid the stale ordinal from whoever wrote #179, who carried *second
     bullet* across from 0023's *Amends* line into a new note in ADR 0002 §5
     (`89ad49d`) — two readings of the line, no recount.
  2. It hid it from the next pass, which wrote *the second bullet of
     Consequences* in its own first draft of that same note and caught it only
     by **enumerating** the bullets, never by searching for them.
  3. Then it lied about the repair. The check run against `origin/main`
     afterwards was `grep -c "the bridge bullet"` and returned **0**, with
     `grep -c "second bullet"` returning **1** — the exact reading of a tree
     that still carried the defect, on a tree that no longer did. The phrase had
     wrapped again, and the one remaining `second bullet` was the dated note
     quoting the old value as history.

  So a check written as a phrase search **cannot** confirm a fix to a phrase
  that wraps: it reports the same thing before and after, and the second report
  is the dangerous one, because that is the one somebody believes. Fold the
  check the way you fold the sweep — `re.sub(r"\s+", " ", text)` on both sides —
  and make it **discriminate**: run it against the tree before the fix as well,
  and if it answers the same, it is measuring your pattern and not the tree.
  Measured on these two trees — folded, the ordinal count goes **1 before,
  0 after**; as a phrase, `the bridge bullet` is **0 before and 0 after**, the
  same answer on the broken tree and the fixed one. Counting is not enough
  either: a count of 1 can be the correction quoting what it corrected, which is
  what the `second bullet` still in that file is. Read the hit.
- **`-m live` costs money** and needs `ANTHROPIC_API_KEY` *and* `DIGLINE_LIVE=1`.
  Never required to contribute.
- **One check runs only in CI, and it is not required.** The `docs` job builds
  the digline.dev site from your branch's docs. `main` requires only the three
  `gates` checks, and `RELEASING.md`, *Queued for the next site push*, says why
  `docs` cannot be one of them — so a red `docs` does not stop a merge. Read it
  anyway: it is the only place these mistakes show.
  - **On your pull request** it runs the site's preview, `make preview`: a
    `--strict` build that fails on a link that resolves on GitHub and not on
    the site, and that lets a page with no nav entry through as `info`. Beside
    it run the three nav tests, which do not: a new doc page, example or ADR
    with no line in digline.dev's nav turns `docs` red here. That red is
    expected — by the site's runbook the entry lands *after* the record does —
    and it blocks nothing.
  - **After the merge**, on the push to `main`, the ordinary `--strict` build
    runs with the nav guard included. A page on `main` with no nav line is a
    red `docs` on `main` until the entry merges in digline.dev — so that is
    where a missing entry is found to cost something: after your pull request
    has landed, not before.

  `RELEASING.md` names the line to add. Nothing you run locally catches any of
  this unless you have the site checked out beside this repository.

Small commits, imperative English messages. Open an issue first if the change
touches a boundary — it is cheaper to disagree before the code.
