# ADR 0023 — Capture: the human's label, made a regression

- Status: proposed — the text first, checkpointed before any code, the way
  [ADR 0021](0021-the-register.md) was
- Date: 2026-09-16
- Assumes: [ADR 0001](0001-verdict-not-score.md) §1 (three states);
  [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §2 (the payload
  stays where it is born), §5 (the `case_id` is not payload), §6 (production
  data does not live in the repository), §8 (a baseline is an approved
  reference);
  [ADR 0003](0003-artifacts-travel-only-when-the-suite-says-so.md) §4 (a digest
  is a verifier);
  [ADR 0007](0007-the-declarative-suite-format.md) §7 (a data suite cannot
  widen a boundary);
  [ADR 0011](0011-the-mcp-server.md) §1 (a writer is absent by construction);
  [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §1
  (input beside output), §3 (whole or nothing), and its Context (no fourth
  signal is claimed);
  [ADR 0016](0016-the-canary-case.md) (a case file that moves is a promotion
  owed);
  [ADR 0019](0019-the-reasoning-operator.md) §8 (the decision journal), §10
  (the label loop);
  [ADR 0021](0021-the-register.md) §1 (the human's memory is committed by the
  human), §4 (the operator never writes it), §6 (absence is stated, never read
  as zero), §7 (content-derived identifiers)
- Amends: [ADR 0002](0002-three-worlds-and-where-the-data-lives.md) §5 — the
  generated `case_id`'s recipe (§6 below); ADR 0002's *Consequences*, second
  bullet — "anonymization is mandatory" at the bridge becomes a declared regime
  (§8); `examples/operator/DESIGN.md`'s *Designed with pilots* sentence, and
  the page on digline.dev built from it (§8)
- Closes: ADR 0015's deferred *traffic-to-case ADR*; ADR 0019 §10's and
  ADR 0021's deferred *label loop's distillation*, by ruling what it is (§10)
  and deferring only its reader
- Turns into surface: `digline capture`; `Suite.capture`; the operator's
  pending count; `AGENTS.md` §1 and the `operating-digline` skill (an agent
  does not elect an exemplar, for the reason it does not promote)
- Touches: nothing in `CLAUDE.md`'s *fixed* section, and §8 says why the
  closest call is not one. Decision 2 is upheld — the draft is a file in the
  user's repository; decision 3 — a captured case's expected is a human's,
  so it can fail; decision 5 — the regime is declared, never looked up;
  decision 9 — capture writes inside the perimeter and nothing it writes
  reaches the wire. `CLAUDE.md`'s *Structure* line for `bridge/` says
  "mandatory anonymization" and follows §8 when this record lands
- Requires: no `SCHEMA_VERSION`, no migration, no baseline re-promoted. One new
  command, one optional suite field outside `config_hash`, one additive
  `--json` shape under `OUTPUT_VERSION` 1
- Number: 0023. 0001–0022 are claimed on `main`; no local branch, no worktree
  and no remote ref carries a 0023 at the time of writing

## Context

Both applications this project is dogfooded on already turn a human judgment
into cases. Each asks, in context, what its owner actually did — scout *"c =
commented, u = upvoted, enter = ignored"*, brief *"which ones interest you?"* —
writes the answer beside the model's verdict in a gitignored `seen.json`, and
has a script that rewrites a committed case file from it: `scout.py casi`,
`brief/make_cases.py`. The test set is, in both apps' own words, *a by-product
of using the thing*.

That is capture already, done by hand twice, and the two hand-made versions
are the material this record was written against. They show four things a
design on a whiteboard would not have.

**The exporters capture by volume.** Every labelled record becomes a case. A
suite built that way grows with the owner's mornings, not with what the judge
gets wrong: the great majority of both case files are agreements, and each new
week adds more of them.

**One label means two things.** In scout, `enter` writes `ignored`, and
`ignored` means *the judge was wrong and I declined* as easily as *I had no
time*. Brief's `marked: false` is the same shape — *enter = none* at seven in
the morning. The exporters read both as a negative, so an expected value in the
committed suites is, for most of their cases, a reading of an answer that did
not say it.

**A log may hold the label and not the input.** Brief saves the summary it
judged only for items it showed. The 144 items it judged and never showed have a
score and no input: they are unlabelled, and even labelled they could not be
replayed. [ADR 0015](0015-the-recorded-output-and-the-declared-re-judge.md) §1
reached *input beside output* from the recording side; capture reaches *input
beside label* from this one.

**Third-party text is already committed.** scout's case file carries the bodies
of other people's threads, in a private repository. brief's carries 400-character
extracts of other people's feeds, in a public one. digline's own operator page
says, of capture, that *"the payload never leaves the perimeter even toward your
own repository"* — and both committed case files contradict it.

The design below was not derived from the material. It was **ruled**, question
by question, by the operator of both applications on 2026-09-13, and the six
rulings are the decision. What this record adds is the text, the places where
the material resists the rulings, and what an implementation needs. The
measured counts and the rulings' own record are kept in the working material:
`private/` is a separate repository and this one is public, the boundary
ADR 0015 and ADR 0019 drew before.

ADR 0015 is not capture's substrate, and its Context already says so: a stored
run's recorded output is a *model's* answer, and capture needs a *person's*.
Capture reads the application's log.

## Decision

### 1. The sentence

> **The apps collect the human judgment; capture turns it into a regression;
> the operator says when; the commit signs.**

Each clause is a boundary, and each of the sections below defends one:

- **the apps collect** — capture asks no question and has no UI (§2, §5);
- **capture turns** — it reads labels and a log and writes cases, and nothing
  else (§3, §4, §7, §11);
- **the operator says when** — it counts what is ripe and never launches (§9);
- **the commit signs** — the diff is the review, and no agent makes it (§7).

Capture sits on the **approve** side of the line `promote` and `register` sit
on: it writes a tracked file that means *a person decided this is a test*. It is
the third gesture of that family, and it is kept apart from both — electing an
exemplar is not approving a reference, and a case file that grew is a promotion
*owed*, not one made (§7).

### 2. What a label is, and which ones are capturable

A label is capturable when it is **an explicit act**: the person did something
that says what they wanted. It is not capturable when it is what an answer
defaults to. The distinction is declared per label value, in the suite's code
(§3), and a value the declaration does not name is refused by name — never
guessed into either set.

    explicit     scout: commented, upvoted     brief: marked
    ambiguous    scout: ignored                brief: not marked

**Going forward, the ambiguous label is split in the application**, not in
digline: *I read it and the judge was wrong* and *I had no time* become two
answers, and only the first is explicit. That is a change to each app's
prompt, and capture's only part in it is to read the new vocabulary when it is
declared.

**The historical ambiguous labels are not capturable, ever.** Reinterpreting
them — by date, by the judge's confidence, by what the owner "must have meant"
— is inventing an expected value, which is the one thing §11 forbids first.
*Invent nothing* is a rule about data; it applies to labels without change.

**From the past, capture draws only explicit disagreements**: an explicit label
that contradicts the application's verdict. And here the ruling resists itself,
which is worth stating exactly. Its first half says *never reinterpret an
ambiguous label*; its second says *draw the disagreements*. A record where the
judge said `comment` and the label is `ignored` *is* a contradiction — and its
label is the ambiguous one. The first half wins: **a contradiction carried by an
ambiguous label is not a disagreement**, because reading it as one is reading
`ignored` as *wrong*. It follows that a history labelled before the split yields
disagreements in **one direction only** — the judge under-called and the person
acted anyway — and that a history whose only explicit label is the positive one
may yield **none**. Brief is that history: a mark is only ever given to an item
the judge already put above the bar, so no explicit label there contradicts a
verdict. That is the ruling applied, not a defect of it, and brief's capturable
past is empty.

**What a person may do deliberately, capture may not do automatically.** The
rule binds the command, not its owner, and the distinction has to be said out
loud because the committed material looks like a contradiction of it: scout's
suite holds cases whose expected was read off the ambiguous label, and most of
its cases are those. They are not a mistake for a tool to correct. The person
who answered knows what he meant when he answered, and he committed them —
which is the signature ADR 0021 §1 gives that act. Capture holds no such
knowledge and cannot acquire it, so the same reading, made by the command,
would be an invention on his behalf.

Both sides of that follow. Capture never lists an ambiguous record, never mints
an id for one, and refuses one named to `--elect`, by name, saying which label
made it ambiguous. And a person stays free to write that case by hand, as world
1 of ADR 0002 §5 — their test data, chosen by them — and to answer for it in
the commit. **Capture cannot do automatically what a person may do
deliberately.**

### 3. The source is declared, and it is code

Capture knows no application's file. The suite declares a reader:

    Suite.capture: CaptureSource | None = None

    CaptureSource:
        cases_file:      Path                   capture's own file (§7)
        repository:      Literal["private", "public"]    no default (§8)
        read:            Callable[[], Iterable[Labelled]]
        explicit:        Mapping[str, Output]   label value -> expected (§5)
        ambiguous:       frozenset[str]
        max_per_pattern: int = 2                the declared default (§4)

    Labelled:
        source_id:   str             the application's own id for the item
        vars:        Mapping[str, object]    the input, as the judge saw it
        verdict:     str             what the application's judge said
        label:       str             what the person answered
        labelled_at: str             ISO, from the log

**Python suites only.** A reader is a function, and a declarative suite cannot
hold one — the same place [ADR 0007](0007-the-declarative-suite-format.md) §7
left every other boundary-widening thing, for the same reason: capture moves
third-party text into a committed file, and that must be a change somebody
wrote in code and a reviewer saw.

**Outside `config_hash`**, like `Disclosure` and `record_responses`: declaring a
source changes no score and no threshold. What moves a baseline is the cases
capture writes, and they move `cases_digest`, which is already how a grown case
file announces itself.

**A record without `vars` is not capturable**, and the reader cannot supply
them after the fact: the input is what the judge saw at `labelled_at`'s
judgement or it is nothing. Re-fetching a thread today would capture a
different input under an old label.

**`verdict` selects, `label` decides.** The application's verdict in the log
is the one its judge gave on the day, possibly under a prompt or a model since
replaced. It is used for exactly one thing — to find the disagreement and to
name its direction. The case's expected comes from the label alone (§5), so a
case captured against an old judge is still a correct test of the current one,
and may simply be a wall that already holds.

### 4. Proposed by pattern, elected by a person

    digline capture --suite suite.py                     lists; writes nothing
    digline capture --suite suite.py --elect ID [ID …]   writes the named cases

**The listing** groups every capturable disagreement not already in the draft
by **direction of error** — the pair (application's verdict, label), e.g.
`skip → commented` — and prints each group with its items, oldest label first:
the input, the verdict, the label, and the `case_id` each would receive (§6).
Nothing in the listing is ranked, scored, starred or pre-selected. The order is
`labelled_at`, which is a fact about the person and not an opinion about the
case.

**The election** names the cases, by that id, and writes those and only those.
It is two invocations and not a dialogue on purpose: ruling 6 forbids an
interactive ceremony, ruling 2 requires that a person choose, and a list of ids
on a command line is a choice that leaves nothing to click through.

**A declared default of two per pattern.** `max_per_pattern` is a field of the
source, and its default is 2. Naming more than it from one direction in one
election is refused **by name and with its reason** — the pattern, the count,
and the sentence about representatives rather than volume — and the person may
raise it, in their own suite, in a diff a reviewer sees. It is not a law in the
code. Capture assists a human gesture; it does not police it. What the default
buys is that the second exemplar is never added by momentum; what the
declaration buys is that widening it has a date and an author. A pattern of one
or two may be elected whole — for a direction that has happened once, the one
is its representative.

No `--all`, no `--pattern`, no threshold under which capture elects on its own.
There is no flag that makes the person optional, because a flag that could is
the flag that would be used.

### 5. The expected is the label, verbatim

Capture writes `expected` as the suite's `explicit` mapping gives it for the
label the person gave. The mapping is the suite's code, total over the explicit
values, and it is a **naming**, never a judgement: scout's `commented` becomes
`{"mark": "commented"}`, which is what `casi` already writes and what its
`AgreesWithMark` already reads. What the mark *means* for the verdict stays in
the assertion, where it always was.

**Capture asks nothing.** The expected is the answer given in the application,
in context, when the item was in front of the person. What was never labelled
is not capturable yet — brief's never-shown items are brief's backlog, not
capture's — and the remedy for a missing label is a question in the app, never
one in digline.

`Case.label`, where the suite counts a confusion matrix, is written only if the
source declares it the same way — a total mapping from explicit values — and
is otherwise left out, which the suite then refuses by its existing rule. It
is not derived from `expected` by capture.

### 6. The generated id comes from the input — ADR 0002 §5, amended

ADR 0002 §5 ruled that a case born in production gets an id **generated by
digline**, with **no parameter to pass one in**, from *date, sequence number,
short hash of the already redacted response*. The first half stands. The recipe
fails on both real histories, and each ingredient fails for a reason the
material shows:

- **the response** is the model's, and a captured case is defined by its input
  and a person's label. Scout records crossposts without judging them and brief
  records skipped items unjudged: a record may have no response to hash, and a
  re-judged input would get a new one;
- **the sequence number** depends on the order and the batch of capture, so the
  same item captured on two branches receives two ids — and a union of the two
  case files holds it twice;
- **the date** adds nothing a hash of the input lacks, and makes the id change
  if the same item is labelled again;
- **"already redacted"** has nothing to act on in §8's private regime, where the
  input is committed whole.

The amended recipe:

    case_id = "cap-" + sha256(canonical(vars))[:16]

**From the input**, because the input is what makes two cases the same case.
Two elections of one item on two branches mint one id; a second label on an
input already in the draft is refused by id, naming the expected it already
has — which is scout's own finding about crossposts (*two identical bodies with
opposite expected verdicts is not a hard case, it is an unanswerable one*)
enforced by construction rather than by a dedup pass.

**The application's id stays in the perimeter.** `source_id` is written to the
case's metadata, where it joins the case back to its record and makes an item
already captured recognisable across edits of its input. `Case.metadata` is
data by type — no document, no `--json` and no MCP response carries it — so an
application's identifier, which in brief is a URL with a title in it, never
reaches a surface that travels. It never enters the id.

**The id is a verifier, and that is accepted.** A hash of public text lets
whoever holds a candidate text confirm it is a case — ADR 0003 §4's objection,
asked here and answered: a `case_id` travels today by practice (ADR 0021 §7), a
slugged title in its place would be readable rather than confirmable, and a
salt would be a secret held outside the draft. The weaker leak is chosen and
written down.

The amendment note in ADR 0002 §5 is one dated paragraph and changes nothing
about world 1: a developer still chooses their own ids, and cases already
committed keep theirs.

### 7. Capture's own case file is the draft, and the commit is the signature

**No staging area, no review screen, no file nobody loads.** Capture appends the
elected cases to the case file the source names — a real file the suite reads,
not a holding pen — and the tree is dirty until a person commits it: the diff is
the review, the commit is the signature, a reviewable diff and never
auto-committed, taken literally. A run launched before that commit is stamped
`-dirty`, the same hazard `promote` and `register` already carry and meet the
same way.

**Append, never rewrite.** Every case already in the file is left byte for byte
as it was; capture reads the file to know what is there and writes new entries
after it. A file that does not parse is refused by name and left untouched.

**An elected exemplar is permanent.** Capture never removes, rotates, or
re-proposes a case that is in the file. Retirement is `suspended`, with its
mandatory reason, written by a person's hand in the same file — and a suspended
case is still *present* for capture, so it is not proposed again. A case that
has not regressed in months is not dead weight: it is a wall that holds, and
removing it is the one way to find out it was holding something.

**Capture writes a second file, and the suite loads both.** `casi` and
`make_cases.py` regenerate their case files wholesale from `seen.json`, so a
case that must survive cannot live in one: the next run would erase it, and
capture cannot detect that it happened. The precedent is already in the
material and is scout's own — **the canary lives in `suite.py` and not in
`cases.json`, precisely because `casi` rewrites `cases.json` every time**, and
`casi` never touches it. Capture's file is the same answer to the same problem:
its own file, named by the source, loaded by the suite beside whatever the
exporter produces.

The two never collide, because they are owned differently: one is regenerated
by volume and may change entirely between two runs, the other grows only by
election and is never rewritten. Capture reads only its own file, so the
exporter's cases are not elected exemplars and are never proposed, re-proposed
or edited by it — which is also how the cases §2 leaves to their owner stay
exactly where their owner put them.

**A grown case file is a promotion owed.** Capture writes cases, and the next
`compare` reports them as `new` against a baseline that never saw them; an
operator watching the suite escalates on the case file having grown. That is
correct and it is not capture's to silence. Run, compare, promote: three more
human gestures, on the day the person chooses.

### 8. The payload: a declared regime

    CaptureSource.repository = "private" | "public"      mandatory, no default

**Private: the input is committed whole.** A test that cannot replay the input
its label was given on is not a test, and a clipped input is a different input
under the same label — ADR 0015 §3's *whole or nothing*, for the same reason.

**Public: capture refuses to write third-party text, and says so.** The listing
still works, locally; `--elect` refuses before it writes, naming the regime,
the source, and the derogation. The derogation is **a person writing the case by
hand**: that is world 1 of ADR 0002 §5 — the developer chooses their test data
and answers for it — and it is a gesture capture cannot perform on anyone's
behalf, which is the point of calling it one.

**Declared, never looked up.** Whether a repository is public is a fact about a
hosting platform, and learning it would be a network call nobody configured —
fixed decision 5. So it is declared in code, and a declaration can go stale: a
repository made public after the fact carries its captured inputs in its
history. Capture cannot see that and does not claim to; the declaration's
presence in the suite is what makes the change reviewable.

**What "private" has to mean, and where the ruling's axis resists.** The
ruling's axis is *visibility*; ADR 0002's is *ownership*. For both applications
the two coincide: the person who owns the data, maintains the software and
writes the suite is one person. For a software house they do not. A private
repository of the software house holding an end company's production text is
exactly what ADR 0002 §6 refuses — *production data does not live in the
repository* — and what ADR 0015 §5 declined to let promotion do by side effect.
So `"private"` is defined, in the docstring and in the refusal texts, as
**readable only inside the perimeter of whoever owns the text**, and a
repository that is private but belongs to someone else is `"public"` for this
declaration. This is why the record touches no fixed decision: decision 9
governs what crosses a boundary, and a commit into a repository inside the
owner's perimeter crosses none. Declared falsely, it crosses one, and no type
can stop a false declaration — a sentence can only make it a lie rather than a
misunderstanding.

**ADR 0002's bridge said "anonymization is mandatory", and capture is that
bridge's first real instance.** Anonymising the input of a taste judge — a
thread body, an article's opening — destroys the case: the judge judges the
text. The choice the material leaves is *the text or no case*, and the declared
regime is that choice made visible. The *Consequences* bullet is amended to say
so; the Postgres bridge ADR 0002 §6 planned, holding world 3's production data
for a software house, keeps the refusal side of the regime by construction.

**The character ceiling: the rule stays flat.** Brief is public today with
400-character extracts, and the question was whether a declared ceiling should
be a fair-use exception. It should not, for three reasons:

1. **A number in a tool reads as a clearance the tool cannot give.** Whether a
   quotation is lawful depends on jurisdiction and purpose — the operator's own
   jurisdiction has a quotation exception bound to criticism and discussion, not
   a general fair use — and a constant in digline would be read as the answer.
2. **Brief's 400 is a performance setting.** `SUMMARY_MAX_CHARS` was cut from
   1500 to 400 to measure what the judge needs, and a ceiling copied from it
   would launder a model budget into a licence.
3. **The derogation already exists.** A person may commit a hand-written case
   with whatever extract they judge lawful, and answer for it. That is what
   brief's owner has done, as world 1, and nothing in this record condemns it.

**The operator page's sentence is amended.** *"The payload never leaves the
perimeter even toward your own repository"* is false of both committed case
files and of the regime above. The corrected sentence says what is true: *the
payload never leaves the perimeter; whether a repository is inside it is
declared, and where it is not, capture refuses.* It lands in
`examples/operator/DESIGN.md` and on the page digline.dev builds from it.

### 9. Cadence: the operator says when, and a person launches

**The operator counts.** A cycle may report *N disagreements not yet examined*,
per direction, from

    digline capture --suite suite.py --pending --json

which prints counts per pattern and nothing else — no ids, no inputs, no
application identifiers — writes nothing, and is the one mode of the command
the operator may invoke. `--elect` is never invoked by the operator, asserted
the way `promote` and `register` already are: no script and no workflow under
`examples/operator/` contains it.

**Absence is stated, never read as zero** — ADR 0021 §6, and here it is the
ordinary case rather than an edge. The labels live where the application runs.
A hosted runner checks out the repository and finds no `seen.json`, because
`seen.json` is gitignored in both applications and has to be. So a scheduled
cycle on a hosted runner reports *labels not reachable from this runner*, and
the ripe-batch signal is, in practice, a local cycle's. That is a limit of the
material, written into the example rather than solved: solving it would mean
carrying the owner's history to the platform, which is the thing §8 exists to
decide against.

**"Not yet examined" needs a memory, and the only one allowed is the draft.**
Capture touches nothing outside the draft (§11), so it keeps no ledger of what
it has shown. An item is examined when the draft already holds it, or when its
`labelled_at` is not after the newest `examined_through` recorded in the
metadata of an elected case. An election records that watermark — the newest
label in the batch the person was shown — on each case it writes.

The hole, stated: **an election of nothing writes nothing**, so a batch a person
read and found empty leaves the count where it was, and is proposed again.
Re-proposal is harmless; a count that cannot go down is a signal that stops
being read. The remedy is not decided here (*Not decided here*), and the
refusal to invent a side file for it is deliberate.

**Absent from the MCP**, in all three modes, for `promote`'s reason and one of
its own: `--elect` writes into the repository, and the listing prints
third-party text, which an agent has no need to hold. The server keeps its
eight tools.

### 10. The second consumer: the operator's own decisions

ADR 0019 §10 gave the decision journal a `wanted` field — *would you have
wanted to be woken?* — and deferred the command that distils
`(decision, wanted)` into cases. That history has the same shape as an
application's:

| | an application | the operator |
|---|---|---|
| the log | `seen.json` | the decision journal |
| the item | a thread, an article | a cycle |
| the machine's verdict | `comment`, a score | `escalate` / hold, and its clause |
| the person's label | what they did | `wanted: yes \| no \| unsure` |
| a direction of error | `skip → commented` | a hold that should have woken; a wake that should not have |

**Capture serves both, and it is not its own thing.** A separate distillation
would need every rule above — invent nothing, explicit labels only, patterns
and elected exemplars, permanent cases, the commit signs — and would restate
them in a second place where they could drift. The operator's judgment becomes
a suite exactly as ADR 0019 §10 promised, through a second declared reader, and
the reader is the only thing that is new.

**And it is not built by this record**, for three reasons the material gives:

1. **There is no history.** The decision journal exists in the example and in
   one fork, and no `wanted` has been answered in either. A reader written
   against no labels would be written against a guess.
2. **The ambiguity is already split there.** `unsure` is explicit and empty is
   *not answered*, so §2's historical problem does not arise — which is a
   difference in kind, and a reason to let the first real answers show whether
   `unsure` is capturable, rather than rule it now.
3. **The item is a cycle, and a cycle is identifiers.** Its inputs are facts
   naming cases and assertions, not third-party text, so §8's regime barely
   applies — except that the case ids those facts name are, in the dogfood,
   content (ADR 0021 §7). A suite over the operator in a public repository
   meets the refusal for a reason nobody would guess from the word *payload*,
   and that deserves to be met with a real journal in hand.

The one thing that is ruled now, because the table makes it cheap: ADR 0019's
Consequences warned that *a policy calibrated against its own journal can drift
toward whatever the person answering was feeling that month*. Elected exemplars,
two per direction by default, permanent, are the answer to that warning, and they
are an answer only if the operator's suite is built by capture rather than
beside it.

### 11. What capture never does

The list is closed.

1. **Writes a case whose expected it inferred.** The expected is the explicit
   label, mapped by the suite's declared naming (§5), or there is no case.
2. **Captures an item it did not read a label for.** No label in the log, no
   case — however obvious the verdict looks.
3. **Reads an ambiguous label as either answer**, historical or new (§2).
4. **Chooses.** It groups and lists; a person names what is written (§4).
5. **Touches anything outside the draft.** Not `seen.json`, not the baseline,
   not the register, not the journal, not the application's own case file, not
   a ledger of its own, and no commit (§7, §9).
6. **Rewrites a committed case**, including one it wrote (§7).
7. **Writes third-party text under `"public"`** (§8).
8. **Learns the regime from the network** (§8).

## Consequences

**The suite grows by what the judge gets wrong, and slowly.** Two exemplars per
direction per election, where the default stands, means a suite that doubles in
a year rather than a week, and whose new cases are all disagreements a person
thought representative. A volume exporter's suite measured the owner's habits;
this one measures the judge's errors.

**The backfill is not the prize, and that is the honest headline.** Measured
against the two real histories, the capturable past is thin. In the public one
it is empty (§2). In the private one, several hundred labels yield explicit
disagreements in the low tens, in a single direction — the exact figures stay
in the working material, with the rest of the reconnaissance. A command built
for the backfill would be a command with one afternoon of work behind it.

What makes it worth building is ruling 1 read forwards: **the split label**.
Every ambiguous answer that becomes an explicit one is a disagreement capture
may read for the rest of that suite's life, and the yield compounds with use
instead of being drawn down once. So the prerequisite is named here rather than
assumed: **splitting the application's ambiguous label is what makes this
command worth building**, and until each application asks the new question,
capture's yield is what §2 says it is — one direction in scout, nothing in
brief.

**A suite already committed is not re-ruled by this record.** Whether the cases
read off an ambiguous label stay, or are suspended, or are replaced by elected
exemplars, is their owner's decision and is made in a commit, not by a command
(§2, §7).

**A private repository becomes a place third-party text is committed by
design.** It already was, by hand. Now it is declared, reviewable in the suite,
and refused where the declaration says public — which is more than the
hand-made version could say for itself.

**The operator gains a count it can only take locally.** A hosted cycle says
so. The ripe-batch signal is as good as the machine the labels are on.

**Every election is followed by a promotion owed.** Capture is the start of a
sequence of human gestures, not the end of one.

## Alternatives considered

**Capture everything and let the diff filter it.** It satisfies *the diff is
the review* and fails *never all of them*: a person deleting forty lines from a
diff is a person approving the rest by fatigue. Rejected in §4.

**Pre-marking a suggested exemplar per pattern.** A ranked list is an election
the tool made and the person ratified. Rejected in §4, and ruled out before the
design by ruling 2.

**A hard ceiling of two, in the code.** Rejected in §4. A limit the owner of a
suite cannot raise in their own suite is the tool policing a gesture it exists
to assist, and the refusal it produces has nowhere to go but a fork. Declared,
the same number is a default somebody can move on the record.

**Reinterpreting historical `ignored` by the judge's confidence or the item's
age.** The most tempting, because it would multiply the yield. It invents an
expected value. Rejected in §2.

**An interactive election, one prompt per item.** Rejected by ruling 6, and in
§4 the command-line ids are what satisfy ruling 2 without it.

**A draft file reviewed and then merged into a case file.** A third file, which
is a staging area nobody commits. Rejected by ruling 6: capture's own case file
is the draft, and the suite loads it.

**Keeping ADR 0002 §5's recipe and adding a dedup pass.** A dedup pass is a
rule a hurry skips; an id from the input is a rule with no entry point, which
is the argument §5 itself made. Rejected in §6.

**A character ceiling for public repositories.** Rejected in §8: a legal
judgement dressed as a constant.

**Detecting a public repository from the remote.** A network call nobody
configured. Rejected in §8.

**A separate command for the operator's journal.** Rejected in §10: the same
rules in a second place.

**A ledger of examined items**, so that an empty election lowers the count.
Rejected for now in §9: it is state outside the draft, and the hole it closes is
named rather than closed by a file nobody ruled.

## Test plan

Beyond a failing case for every new rule, which the conventions already require:

**Invent nothing, planted.** A source whose log holds an ambiguous label that
contradicts its verdict, an explicit label that agrees, and a record with no
label: the listing shows none of the three.

**An undeclared label value is refused by name**, and the listing does not
start.

**The expected is the mapping, verbatim.** For every explicit value, the
written case's `expected` equals the source's mapping for it, and a case is
never written with an `expected` the mapping does not produce.

**The declared ceiling, both ways.** Under the default, electing three ids of
one direction is refused — naming the pattern, the count and the reason — and
writes nothing, while two of one direction and two of another write four, and a
pattern of one elected whole writes one. With `max_per_pattern = 3` declared,
the same three-id election writes three. Only the pair proves it is a default
and not a law.

**An ambiguous record is unreachable.** Its id appears in no listing, and one
constructed by hand and passed to `--elect` is refused, naming the label that
made it ambiguous; the draft is unchanged.

**Capture's file is its own.** After an election, running the application's own
exporter — which rewrites its case file wholesale — leaves capture's file byte
for byte as it was, and the suite loads both. The canary's precedent, asserted
rather than described.

**The id is the input's.** The same `vars` on two branches, elected on each,
produce one id and a union of the two files that the reader returns once; the
same `vars` under a second label is refused, naming the expected already held.
Changing `labelled_at`, the verdict or the order of election does not move the
id.

**Append, never rewrite.** The draft's bytes before an election are a prefix of
its bytes after, modulo the closing bracket of the array, and an existing
case — suspended or not — is byte-identical afterwards. A suspended case is
not re-proposed.

**The regime.** No `repository` is refused at suite load; `"public"` lists and
refuses `--elect` with the derogation in the message, and the draft is
unchanged; no mode opens a socket, asserted at runtime by a test that fails any
connection attempt — `tests/test_layering.py` holds the import side of decision
5 today, and nothing yet holds the call side for a command.

**Nothing outside the draft.** A capture over a temporary repository leaves
`git status --porcelain` showing the draft and nothing else.

**The boundary.** `--pending --json` over a source whose vars, verdicts and
`source_id`s carry markers: no marker appears, and the output's keys are
asserted as a set. The MCP tool set is ADR 0020's eight.

**The operator cannot elect.** No file under `examples/operator/` contains
`capture` with `--elect`; a hosted-shaped cycle with no reachable labels reports
the absence, never `0`.

## Not decided here

**The label split's words.** Each application chooses its own vocabulary for
*wrong* and *no time*; capture reads what is declared. Whether digline should
suggest names is a docs question.

**What an empty election records.** §9 names the hole and refuses a side file.
The candidates are a register-shaped line — counts and a watermark, no ids,
which would widen ADR 0021 — or accepting re-proposal. It waits for the first
count that would not go down.

**The operator's reader** (§10), until a journal holds answered `wanted`s.

**Whether `case_id` crosses a boundary at all** — still ADR 0021's open
question, and §6 chose the less readable id without settling it.

**A declarative capture source.** §3 keeps the reader in Python. A fixed set of
named readers for common log shapes could be data; none exists yet to name.
