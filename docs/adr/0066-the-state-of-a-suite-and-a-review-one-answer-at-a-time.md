# ADR 0066 — The state of a suite, and a review one answer at a time

- Status: proposed 2026-11-13, from a first use outside the project, on an
  application with a judged suite. Its decisions were dictated before this
  record was written, in the conversation of the session that wrote it, and
  are stated here in this record's own words. **What this record adds is
  marked *decided here***: the routes, where the name lives, what the
  page does after a press, and the two facts the state needs that no command
  prints yet. Each is proposed, for acceptance to take or remove item by item.
  Nothing is built until this record is accepted
- Shipped: unreleased
- Date: 2026-11-13
- Opens: **nothing.** No `SCHEMA_VERSION`, no `OUTPUT_VERSION`, no
  `RECORDING_VERSION`, no line of `_STEPS` and no entry in the layout of
  `.digline/<tenant>/`. The pages read what the store and the suite already
  hold, and the one write is the one `digline record import` makes (§5)
- Amends, by a dated note beside the place it amends, which points here, the
  text kept as written: [ADR 0061](0061-a-local-page-whose-views-other-packages-may-extend.md)
  §2, its sentence on the person's mark, *"the person types it in the form, as
  on the command line, and the page reads it from nowhere else"*, which §3
  here narrows (the name is typed once per session of the page, and read from
  the server's memory after that)
- Assumes: [ADR 0023](0023-capture.md) §4 (nothing ranked or pre-selected,
  no *elect all*) and §9 (the election is absent from the MCP server);
  [ADR 0032](0032-the-second-path-to-an-absent-tool.md) §1 and §2 (a write
  sits behind a flag, and the refusal is an absence);
  [ADR 0033](0033-the-server-that-promotes-for-one-browser.md) (the launch
  key, spent for one browser's session);
  [ADR 0037](0037-the-review-interface-and-the-election-recorded-where-the-text-is-not.md)
  §6 (ADR 0023 §4 at a served page);
  [ADR 0059](0059-a-reviewed-answer-a-grouped-listing-a-source-as-data.md)
  §1 (the reviewed answer, and `--by NAME`, never read from git or the
  environment); [ADR 0061](0061-a-local-page-whose-views-other-packages-may-extend.md)
  §1 to §6, and its note of 2026-11-12 (a group's answers put together by
  case, `by_case`); [ADR 0065](0065-a-case-excluded-at-promotion-and-the-cases-a-run-was-made-with.md)
  §1 (the cases excluded at promotion)
- Touches: nothing in `CLAUDE.md`'s *fixed* section moves. Decision 5 is
  upheld: the pages make no network call. Decision 9 is upheld: the answers
  shown are payload, and they reach the browser of the person who started the
  server on loopback, never the MCP server. Decision 2 is not touched
- Number: 0066. Swept on 2026-11-13 across `origin/main` (`71f0fbad`), whose
  highest record is 0065; the branches on the remote, `capture` and `main`;
  every worktree of this repository; and the open pull requests, of which
  there were none
- Owed: the three lines on digline.dev that every new record needs (the nav,
  and the two tables the site builds its pages from)

**How to read the clauses.** *Dictated* is a decision taken before this
record and transcribed. *Decided here* is a name or a detail this record
proposes, and acceptance rules on it.

## Context

**What happened.** On an application with a judged suite, the person who
had to review 27 recorded answers had a separate file prepared to read them
in, and then passed the verdicts through one command line carrying 27
`--good` and `--bad`, typed by hand. Nothing showed the suite's state
whole: how many cases it declares, how many answers a person has reviewed,
which checks judge which cases, what is waiting to be imported. The figure
and the sequence are as reported from that use, in the brief that asked for
this record; no file of that use is held here.

**What `digline view` already holds**, read at `71f0fbad`:

- **one state, not the inventory.** `/where/<tenant>/<suite>/` lays out what
  `digline.host.where.where` returns (`src/digline/host/where.py:143`): the
  first state that holds, its count, the newest run's key and exit code, the
  last import, `idle_checks` and the command for the next step. It says where
  the project is, not what the suite holds;
- **the recordings, grouped, and each answer whole.**
  `/recordings/<tenant>/<suite>/` lists what `import_listing` returns
  (`src/digline/host/importing.py:599`), and
  `/recordings/<tenant>/<suite>/<id>` shows one answer whole with its input
  (`src/digline/cli/view.py:1086`). Each `ImportAnswer` already carries what
  a review needs (`importing.py:178`): the case and its `vars`, the `input`,
  the answer's text, `elected` (the yes or no the draft already holds, or
  `None`), `in_force` (the setup in force for its form) and, for an episode,
  `steps`, each with its tool call's `arguments` and `result`
  (`src/digline/core/run.py:1031`);
- **one write for many answers.** Under `--allow-record`, the recordings
  page is one form: a choice of `--good` or `--bad` beside each answer and a
  name typed once, posted together, through `import_listing` and
  `import_elect` (`_post_import`, `view.py:1596`). It is the command with 27
  flags, in a form. **It is not a review**: the answers are rows of 200
  characters, and the one that is read whole is on another page, which has
  no button.

**So the person's two needs are two pages that do not exist.** A page that
says the suite whole, and a page that shows one answer whole with its yes and
its no beside it.

## Decision

### 1. The state of a suite

*Dictated.* **A page for a suite says its state whole**, from facts the
store and the suite already hold. In this order:

1. **the cases the suite declares**, their number and their ids, from
   `Suite.declared()`;
2. **the reviewed answers**, how many are a yes and how many a no;
3. **which checks judge which cases**, and the checks no case is asked
   (`idle_checks`, `src/digline/run/suite.py:1311`), by name;
4. **the newest run**: its key and its exit code, as `where` reads them;
5. **the reference in force**: its key and when it was promoted, and the
   cases excluded at its promotion, each with who (ADR 0065 §1), in the
   sentence the run list already says (`excluded_fact`,
   `src/digline/report/pages.py:601`);
6. **the recordings waiting**: how many came after the last import
   (`since_last_import`, which `digline record status` reads), and how many
   of them were recorded under the setup in force and how many under an
   earlier one (`SetupsRead`, `importing.py:701`, which `record status` and
   the import's head read);
7. **the next step**: the state's sentence and its command, from `where`,
   shown and never run, with a link to *Where you are*.

**No new computation.** Every line calls the function a command already
calls and renders what it returns, which is ADR 0061 §1's rule, *one
function that can be wrong*.

**Two facts the list needs are computed today and printed by no command**,
read at `71f0fbad`. *Decided here*, for each: the function moves, and is not
written again.

- **The reviewed answers by yes and no** are counted in one place,
  `digline.host.assistant.material` (`src/digline/host/assistant.py:261`),
  for the prompt `digline suggest --assist` sends: `reviewed_yes` and
  `reviewed_no`. The count moves into a function of its own beside the
  suite, which `material` and the page both call.
- **Which checks a case is asked** is `checks_asked(suite, case)`
  (`src/digline/run/suite.py:1288`): the dispatch the driver follows, and
  what `idle_checks` unions over every case. The page calls it once per case
  and renders the result. No command prints it per case today.

**Where it is served.** *Decided here.* At `/suite/<tenant>/<suite>/`, the
**first entry of the menu**, before *Where you are*, and linked from the head
of the run list. It is not `/`: the run list stays there, because the
browser that spends the launch key is sent to the constant `/` and that
constant is a property of the hand-over (`view.py:705`), and because no route
changes (§6). A server without `--suite` serves it for none: its pages are a
tenant's (`docs/view.md`, *Where you are*), and a suite's state needs the
suite.

It reads, in clear, as every view does, and writes nothing. It takes no
POST.

### 2. The review, one answer at a time

*Dictated.* **For each recorded answer to review, a page of its own**, in
the order of the recordings grouped by case (ADR 0061, the note of
2026-11-12, `by_case`, `importing.py:1038`). The page shows:

- **the question and its context**: the case's input as the recording holds
  it, and its `vars`;
- **the answer whole**, never cut;
- **the steps, where the answer is an episode's**: each step in its order,
  with the tool called, its arguments and its result, as the recording holds
  them. A step whose result was not recorded says so;
- **the pages or documents the answer cites, where the recording carries
  them.** There is no field of their own: a document reaches a recording in
  the input, or as a tool's result inside a step, and the page shows it
  there, where it is. This record adds no field for them (§6).

Then **the verdict**: two buttons, *good* (`--good`) and *bad* (`--bad`),
neither chosen, and the name (`--by`) of §3. **Each press writes one
answer**, through `import_listing` and `import_elect` with that one id, the
path `digline record import` takes (ADR 0061 §2, #904). Under the buttons,
the command that does the same thing, with the values in the form, as on
every form of the page (ADR 0061 §2):

    digline record import --tenant acme --suite eval/suite.py --good ID --by 'Ada Lovelace'

**An answer already reviewed is shown as such, and never offered again.**
Its page says *already in the file, `--good`, by NAME*, read from the draft
(`ImportAnswer.elected`), and has no buttons. *Next* passes over it. An answer
that cannot be elected says why, in the sentence the import gives
(`ImportAnswer.refusal`), and has no buttons either.

**What the page may not do**, ADR 0023 §4 and ADR 0037 §6, word for word:
nothing ranked, scored or starred; nothing pre-selected, so neither button is
the default and neither radio is checked; no *all*, no *this group*, and no
threshold under which the page writes on its own. **No order is suggested
beyond the file's**: the next answer is the next one in `by_case`'s order
that has not been reviewed.

**After a press.** *Decided here.* A press that writes is answered, as every
write of the page is, with a `303` (ADR 0061 §4.2), to the page of the next
answer not yet reviewed. That page opens with what the press wrote, **read
back from the draft**, not carried from the request: *ID written, `--good`,
by NAME*. The address carries the id that was written, and nothing else; an
id the draft does not hold is said as not in the file. A crafted link can
make the page read back a fact, never say a sentence of its own, which is the
reason the note of 2026-11-04 on ADR 0061 §7 gives for carrying no command
line in an address. After the last answer, the `303` leads to the state of
§1. A refusal is the command's sentence, with a `400`, and nothing written.

**A link, *next*, writes nothing.** It is a GET to the next answer not yet
reviewed, for the person who wants to leave one for later. It is the file's
order, and suggests nothing.

**Where it is served.** *Decided here.* `/review/<tenant>/<suite>/` is the
first answer not yet reviewed, and `/review/<tenant>/<suite>/<id>` is one
answer. The POST goes to the second. Without `--allow-record` the pages read
and show no button, and say where the writes are, as the recordings do; the
POST route is absent, and answers the `404` any unknown path gets (ADR 0032
§2, ADR 0061 §4). The state of §1 links to the review, with the number of
answers waiting.

### 3. The name, written once per session of the page

*Dictated.* **The person writes their name once per session of the page, and
it is shown on every answer.** It is the `--by` each press writes.

*Decided here, where it lives.* **In the server's memory, beside the session
the launch key was traded for** (`Launch.session`, `view.py:365`), for as
long as the server runs, and nowhere else: not in a file, not in a cookie,
not in an address. The first press carries it in the form; the server keeps
it; every review page after it shows it in the name field, filled and
editable, with the line *reviewing as NAME*. A press that carries another
name replaces it. A server started again asks for it again.

**It keeps ADR 0059 §1's reason**: the mark is *"never read from git's
configuration or from the environment: a name taken from a machine is
inferred, and the mark is the person's own"*. Here the person typed it, in
this session, in this browser. **It narrows ADR 0061 §2's wording**: *"the
person types it in the form, as on the command line, and the page reads it
from nowhere else"* becomes *the person types it once per session, and the
page reads it from that typing and from nowhere else*. The note on ADR 0061
§2 says so.

**The alternative not taken: a cookie of its own**, signed by the session's
secret. It would survive nothing the memory does not, since a new server
mints a new key and a new session, and it would be a second secret in the
browser to get right.

The recordings page keeps its form and its name field as they are.

### 4. What stays out

*Dictated.*

- **No automatic verdict.** The page proposes no yes or no, and no judge is
  asked for one. A model's opinion beside the buttons would be what ADR 0037
  §6 refuses: *"an election the tool made and the person ratified"*.
- **`promote` does not enter the review.** It keeps its button on the run
  list, behind `--allow-promote` and its key (ADR 0032, ADR 0033), and the
  state of §1 links to it and does not carry it.
- **Nothing reaches the MCP server.** No tool reads the review or writes a
  verdict: the election is absent from the MCP server (ADR 0023 §9), and the
  answers shown are payload (fixed decision 9).
- **No server beyond 127.0.0.1.** `digline view` takes no `--host`
  (ADR 0061 §4.1), and this record adds none.

### 5. The alternatives not taken

*Dictated.*

- **A Markdown file, generated for the person to read.** It is what the
  person had to have made. It goes stale the moment an answer is recorded,
  nothing reads it back, and the verdicts still have to travel by hand from
  the file to a command line.
- **An interactive command in the terminal.** ADR 0023's ruling 6 refuses an
  interactive ceremony on the command line, and the reason holds here too: a
  terminal that asks *good or bad?* is answered by whoever holds its input,
  and an agent holds it as easily as a person. At a page, the launch key
  decides who writes (ADR 0061 §4).
- **The view inside the IDE's plugin.** The plugin runs inside an agent's
  session: what it shows, the agent reads, and what it can write, the agent
  can. The election is absent from that surface for the reason it is absent
  from the MCP server (ADR 0023 §9). It would also be a second rendering of
  one page.

### 6. Compatibility

*Dictated: a minor.* Under `RELEASING.md`'s *Choosing the version*, new pages
and a new form move the minor.

- **New routes, and no route changed**: `/suite/<tenant>/<suite>/`,
  `/review/<tenant>/<suite>/`, and `/review/<tenant>/<suite>/<id>`, which takes
  the POST under `--allow-record`. `/`, `/where/`, `/recordings/` and every
  other route answer as they do at `71f0fbad`. The menu gains two entries.
- **No schema change**: nothing is written that `record import` does not
  write already, and no document gains a key. No `--json` changes, so no
  `OUTPUT_VERSION`.
- **The startup line does not change**, nor the hand-over's `/`.
- **The tests that hold the routes**, which every route of this record joins
  (ADR 0061 §6):
  - `tests/test_view.py::test_the_four_routes_answer` (`:592`), which lists
    the routes that answer;
  - `tests/test_view_policy.py`: the policy of ADR 0061 §4.4 on every
    response, and no HTML response with anything inline;
  - `tests/test_view_rebinding.py`: a request addressed to another name is
    refused, on the reading routes as on the writing one;
  - `tests/test_view_recorder.py`: without `--allow-record`, no form and a
    `404` on the POST;
  - `tests/test_view_tenant.py`: a server without `--suite` serves a
    tenant's pages, and no suite's.

### 7. The build, in three pull requests at most

*Dictated: the state, the review, the finishing.* Each says what it
measures.

1. **The state of §1.** The page, its route and its menu entry; the two
   functions moved (§1). *It measures* that every fact on the page equals
   what its command says about the same store: the page against
   `digline where --json` and `digline record status --json`, and the
   reviewed counts against `suggest --assist`'s material, each held by a
   mutation that makes its test fail. The route joins the tests of §6.
2. **The review of §2 and §3.** The pages, the POST and the name. *It
   measures*:
   - that a press and the command, run on two copies of one store, leave the
     two stores identical (ADR 0061 §6);
   - that one press writes one answer, and an answer already reviewed has no
     button;
   - that no button and no radio is served chosen, and that no route writes
     more than one answer;
   - that the name is read from the session's typing alone: a server whose
     environment and git configuration carry a name serves an empty field;
   - that a POST without the session's cookie, or on a server without
     `--allow-record`, writes nothing;
   - the case of the Context: a store of 27 recorded answers reviewed in 27
     presses leaves the file the command with 27 flags leaves.
3. **The finishing.** The Italian of every new sentence, `docs/view.md` and
   `docs/record.md`, a walkthrough's block where one shows the view, and the
   rows `RELEASING.md` asks of a release. *It measures* the pages' replay:
   every line a page quotes comes out of a real server.

## Consequences

**A person reviews an answer reading it whole**, presses one of two buttons,
and moves to the next, with the command under the buttons that would have
done the same. The 27 flags of the Context become 27 presses, each of one
answer, each read back.

**The state of a suite has a page**, built from the functions its commands
call, so the page and the commands cannot say two things about one store.

**The server keeps one name in memory** for its session, which it did not
before: a value typed by the person, never written to disk, gone when the
server stops.

## Not decided here

- Reviewing an answer that is already a case, to change its yes or no. The
  review shows it as reviewed and offers nothing.
- A review of the run's verdicts, case by case. This record reviews recorded
  answers before they are cases.
- Every view and every write this record does not name.
