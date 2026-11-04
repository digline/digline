"""The import: a suite's recorded answers, listed by the shape of their output,
and written only where a person named them, as reviewed answers with the
person's mark. (ADR 0058 §4, §10; ADR 0059 §1–§4; ADR 0023 §3, §4, §6, §7, §8,
§9, §11)

The recordings are written with the store's own writer, so what is read is
what the recorder files: single calls under two setups, an episode with its
calls, an orphan, an interrupted episode, a recording over the ceiling of what
a recording keeps, and a call whose episode is not among the files.

What is held here:

- an answer's id is the input's `capture_id` and the answer's digest;
- recordings of another tenant than the suite's are refused before anything
  is shown, and a suite with no capture source by name;
- the source is declared in Python or in a `[capture]` table, `repository`
  with no default in either, `check` one judged assertion of the suite, and a
  suite that does not load its capture file is refused, in both forms;
- `deterministic_output` is a declaration outside `config_hash`;
- the listing writes nothing, prints the declaration at its head, groups by
  the shape of the output in the files' order, counts each group, and says of
  each answer whether it can be elected and why not;
- an election writes the answers named and no other, as reviewed answers for
  the source's check with the person's `--by`, never an `expected` unless the
  suite declares `deterministic_output`, where a yes also writes one; and it
  refuses, writing nothing, every name it cannot honour;
- a writing invocation prints the declaration before the line of each case;
- `digline record status --suite` says *never imported* and then how many
  recordings came after the last import.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from digline.cli.main import main
from digline.core.capture import capture_id
from digline.core.recording import Recording, setup_digest_of
from digline.core.refused import RefusedError
from digline.core.run import RecordedResponse, RecordedStep, RecordedToolCall
from digline.host import (
    UsageError,
    answer_id,
    import_elect,
    import_listing,
    imported_since,
    listing_lines,
    load_suite,
    read_cases,
)
from digline.run import CaptureSource
from digline.store.file_store import FileResultStore, RecordingWriter
from digline.wire import EXIT_USAGE

S1 = setup_digest_of({"model": "m", "system": "Be brief."})
S2 = setup_digest_of({"model": "m", "system": "Be brief and kind."})
EPISODE = "e" * 32
ELSEWHERE = "f" * 32


def case(text: str) -> dict[str, object]:
    return {"messages": [{"role": "user", "content": text}]}


A, B, C, E = case("refund?"), case("hours?"), case("address?"), case("lost parcel")

#: The answers, and the id of each answer to its input.
A_OLD, A_NEW = "old answer about refunds", "new answer about refunds"
B_OLD, C_NEW, E_NEW = "open nine to five", "Via Roma 1", "we have found it"
ID_A_OLD, ID_A_NEW = answer_id(A, A_OLD), answer_id(A, A_NEW)
ID_B, ID_C, ID_E = answer_id(B, B_OLD), answer_id(C, C_NEW), answer_id(E, E_NEW)

SUITE = """\
from pathlib import Path
from digline.core import JudgeReply, LlmRubric
from digline.host import read_cases
from digline.run import Case, CaptureSource, Suite
HERE = Path(__file__).parent


def judge(prompt):
    return JudgeReply(score=1.0, reason="r")


suite = Suite(
    tenant='acme', environment='dev', name='triage',
    assertions=[LlmRubric(rubric='right?', judge=judge, threshold=0.7, tolerance=0.05)],
    cases=[Case(id='by-hand')%(captured)s],
    samples=%(samples)d,
    min_agreement=%(agreement)s,
    deterministic_output=%(deterministic)s,
    capture=CaptureSource(
        cases_file='captured.json', repository=%(regime)r, check=%(check)r
    ),
)
"""


def suite_file(
    root: Path,
    regime: str = "private",
    *,
    loads: bool = True,
    samples: int = 2,
    deterministic: bool = False,
    check: str | None = "llm_rubric",
) -> Path:
    path = root / "suite.py"
    path.write_text(
        SUITE
        % {
            "captured": ", *read_cases(HERE / 'captured.json')" if loads else "",
            "samples": samples,
            "agreement": repr("2/2") if samples == 2 else "None",
            "deterministic": deterministic,
            "regime": regime,
            "check": check,
        },
        encoding="utf-8",
    )
    return path


def recording(
    vars: dict[str, object],  # noqa: A002
    setup: str,
    output: str | None,
    at: str,
    **changes: Any,
) -> Recording:
    fields: dict[str, Any] = {
        "source_tenant": "acme",
        "app": "support",
        "suite": "triage",
        "case": vars,
        "setup": {"digest": setup},
        "setup_digest": setup,
        "response": RecordedResponse(
            output=output or "", kind="text", input=f"Q: {json.dumps(vars)}"
        )
        if "response" not in changes
        else changes["response"],
        "recorded_at": f"2026-11-03T08:{at}:00+00:00",
    }
    fields.update(changes)
    return Recording(**fields)


def recorded(root: Path) -> None:
    """The recordings every test reads, in the order the writer files them."""
    writer = RecordingWriter(FileResultStore(root))
    for item in (
        recording(A, S1, A_OLD, "01"),
        recording(B, S1, B_OLD, "02"),
        recording(A, S2, A_NEW, "03"),
        recording(C, S2, C_NEW, "04"),
        recording(
            E,
            S2,
            E_NEW,
            "05",
            steps=(
                RecordedStep(index=0, actor="model"),
                RecordedStep(
                    index=1,
                    actor="tool",
                    call=RecordedToolCall(tool="lookup", arguments="{}"),
                ),
                RecordedStep(index=2, actor="model", finish="end_turn"),
            ),
            id=EPISODE,
        ),
        recording(case("where is it?"), S2, "looking", "06", episode=EPISODE),
        recording(case("tracking?"), S2, "AB123", "07", episode=EPISODE),
        recording(case("orphan?"), S2, "alone", "08", orphan=True),
        recording(
            case("cut short"),
            S2,
            "half",
            "09",
            steps=(),
            id="1" * 32,
            interrupted=True,
        ),
        recording(
            case("too long"),
            S2,
            None,
            "10",
            response=RecordedResponse(oversize=True),
        ),
        recording(case("adrift"), S2, "where", "11", episode=ELSEWHERE),
    ):
        writer.write(item)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    recorded(tmp_path)
    suite_file(tmp_path)
    return tmp_path


def loaded(root: Path, name: str = "suite.py") -> tuple[Any, Any]:
    suite, how = load_suite(str(root / name), root=root)
    return suite, how.module


def listed(root: Path, tenant: str = "acme", name: str = "suite.py") -> Any:
    suite, module = loaded(root, name)
    return import_listing(root, suite, module, tenant)


def argv(root: Path, *extra: str) -> list[str]:
    return [
        "record",
        "import",
        "--tenant",
        "acme",
        "--suite",
        str(root / "suite.py"),
        "--root",
        str(root),
        *extra,
    ]


# -- the id ------------------------------------------------------------------- #


def test_an_answer_is_named_by_its_input_and_its_text() -> None:
    digest = hashlib.sha256(A_NEW.encode("utf-8")).hexdigest()[:8]
    assert f"{capture_id(A)}-{digest}" == ID_A_NEW
    # Two answers to one input are two ids; the key order of the input is not.
    assert ID_A_OLD != ID_A_NEW
    assert answer_id({"b": 1, "a": 2}, "x") == answer_id({"a": 2, "b": 1}, "x")


# -- refused before anything is shown ------------------------------------------ #


def test_another_tenants_recordings_are_refused_before_anything_is_shown(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(
        RefusedError, match="the bridge, which is planned and not built"
    ):
        listed(root, tenant="globex")
    code = main(
        [
            "record",
            "import",
            "--tenant",
            "globex",
            "--suite",
            str(root / "suite.py"),
            "--root",
            str(root),
        ]
    )
    out, err = capsys.readouterr()
    assert code == EXIT_USAGE
    assert out == ""
    assert "ADR 0058 §4" in err


def test_a_suite_with_no_capture_source_is_refused(root: Path) -> None:
    (root / "plain.py").write_text(
        "from digline.core import Contains\n"
        "from digline.run import Case, Suite\n"
        "suite = Suite(tenant='acme', environment='dev', name='triage',\n"
        "    assertions=[Contains(needle='x')], cases=[Case(id='one')])\n",
        encoding="utf-8",
    )
    suite, how = load_suite(str(root / "plain.py"), root=root)
    with pytest.raises(RefusedError, match="declares no capture source"):
        import_listing(root, suite, how.module, "acme")


# -- the source --------------------------------------------------------------- #


def test_repository_has_no_default_in_python() -> None:
    with pytest.raises(TypeError, match="repository"):
        CaptureSource(cases_file="captured.json")  # type: ignore[call-arg]  # pyright: ignore[reportCallIssue]
    with pytest.raises(RefusedError, match="must name a judged assertion"):
        CaptureSource(cases_file=Path("c.json"), repository="private", check="")


@pytest.mark.parametrize(
    ("check", "said"),
    [
        ("faithfulness", "which no assertion is called"),
        ("contains", "which is not a judged check"),
    ],
)
def test_the_source_check_is_one_judged_assertion(
    tmp_path: Path, check: str, said: str
) -> None:
    path = suite_file(tmp_path, check=check, loads=False)
    path.write_text(
        path.read_text(encoding="utf-8")
        .replace(
            "from digline.core import JudgeReply, LlmRubric",
            "from digline.core import Contains, JudgeReply, LlmRubric",
        )
        .replace("tolerance=0.05)],", "tolerance=0.05), Contains(needle='x')],"),
        encoding="utf-8",
    )
    with pytest.raises(RefusedError, match=said):
        loaded(tmp_path)


TOML = """\
[suite]
tenant = "acme"
environment = "dev"
name = "triage"
cases = %(cases)s
samples = 2
min_agreement = "2/2"
%(extra)s

[capture]
cases_file = "captured.json"
%(capture)s

[[assertions]]
type = "contains"
needle = "x"
name = "contains"

[target]
type = "http"
url = "http://127.0.0.1:9/answer"
output_path = "data"

  [target.body]
  question = "case.vars.question"
"""


def toml_suite(
    root: Path,
    *,
    cases: str = '["cases.json", "captured.json"]',
    capture: str = 'repository = "private"',
    extra: str = "",
) -> Path:
    (root / "cases.json").write_text('[{"id": "by-hand"}]', encoding="utf-8")
    path = root / "suite.toml"
    path.write_text(
        TOML % {"cases": cases, "capture": capture, "extra": extra}, encoding="utf-8"
    )
    return path


def test_a_data_suite_declares_its_source_as_a_table(root: Path) -> None:
    toml_suite(root)
    suite, _ = loaded(root, "suite.toml")
    assert suite.capture is not None
    assert suite.capture.repository == "private"
    assert suite.capture.cases_file == (root / "captured.json").resolve()
    found = listed(root, name="suite.toml")
    assert found.declaration.cases_file == (root / "captured.json").resolve()
    assert found.declaration.check is None
    # A source with no check lists, and refuses to write, by name.
    with pytest.raises(RefusedError, match="declares a capture source with no check"):
        import_elect(found, good=[ID_A_NEW], by="Ada")


@pytest.mark.parametrize(
    ("capture", "said"),
    [
        ("", "no `repository`"),
        ('repository = "secret"', 'must be "private" or "public"'),
        ('repository = "private"\nread = "x"', "read"),
    ],
    ids=["no repository", "unknown regime", "unknown key"],
)
def test_a_capture_table_is_refused_by_name(
    tmp_path: Path, capture: str, said: str
) -> None:
    toml_suite(tmp_path, capture=capture)
    with pytest.raises(UsageError, match=said):
        loaded(tmp_path, "suite.toml")


@pytest.mark.parametrize("cases", ['["cases.json", 3]', "[]"], ids=["mixed", "empty"])
def test_cases_is_a_path_or_an_array_of_paths(tmp_path: Path, cases: str) -> None:
    """Anything else is refused with the sentence that quotes nothing of what
    was written, since a value there may be a case."""
    toml_suite(tmp_path, cases=cases)
    with pytest.raises(UsageError) as refused:
        loaded(tmp_path, "suite.toml")
    assert str(refused.value) == (
        "suite.toml, [suite]: `cases` must be the path of a JSON file or an "
        "array of paths, not a table or cases written in the suite"
    )


def test_capture_inside_suite_points_at_the_table(tmp_path: Path) -> None:
    toml_suite(tmp_path, extra='capture = "captured.json"')
    with pytest.raises(
        UsageError, match=r"`capture` is a table of its own, `\[capture\]`"
    ):
        loaded(tmp_path, "suite.toml")


def test_a_data_suite_that_does_not_load_its_capture_file_is_refused(
    tmp_path: Path,
) -> None:
    # A case in the capture file, as an import would have left one.
    (tmp_path / "captured.json").write_text('[{"id": "cap-elected"}]')
    toml_suite(tmp_path, cases='"cases.json"')
    with pytest.raises(UsageError) as refused:
        loaded(tmp_path, "suite.toml")
    assert "declares [capture]" in str(refused.value)
    assert "cap-elected" in str(refused.value)
    # Named in `cases`, it loads.
    toml_suite(tmp_path)
    suite, _ = loaded(tmp_path, "suite.toml")
    assert [c.id for c in suite.cases] == ["by-hand", "cap-elected"]


def test_deterministic_output_is_declared_and_outside_config_hash(
    tmp_path: Path,
) -> None:
    suite_file(tmp_path, loads=False)
    plain, _ = loaded(tmp_path)
    suite_file(tmp_path, loads=False, deterministic=True)
    declared, _ = loaded(tmp_path)
    assert (plain.deterministic_output, declared.deterministic_output) == (False, True)
    assert plain.config_hash() == declared.config_hash()
    toml_suite(tmp_path, extra="deterministic_output = true")
    data, _ = loaded(tmp_path, "suite.toml")
    assert data.deterministic_output is True
    with pytest.raises(RefusedError, match="deterministic_output=1"):
        type(plain)(**{**_fields(plain), "deterministic_output": 1})


def _fields(suite: Any) -> dict[str, Any]:
    return {
        "tenant": suite.tenant,
        "environment": suite.environment,
        "name": suite.name,
        "assertions": suite.assertions,
        "cases": suite.cases,
        "samples": suite.samples,
        "min_agreement": suite.min_agreement,
    }


# -- the suite loads what was elected ----------------------------------------- #


def test_a_suite_that_does_not_load_its_capture_file_is_refused_with_the_ids(
    root: Path,
) -> None:
    import_elect(listed(root), good=[ID_A_NEW], bad=[ID_C], by="Ada")
    suite_file(root, loads=False)
    with pytest.raises(UsageError) as refused:
        loaded(root)
    message = str(refused.value)
    assert "does not load 2 of its cases" in message
    assert f"{ID_A_NEW}, {ID_C}" in message


@pytest.mark.parametrize("content", [None, "[]\n"], ids=["absent", "empty"])
def test_an_absent_or_empty_capture_file_is_no_refusal(
    root: Path, content: str | None
) -> None:
    suite_file(root, loads=False)
    if content is not None:
        (root / "captured.json").write_text(content, encoding="utf-8")
    suite, _ = loaded(root)
    assert [c.id for c in suite.cases] == ["by-hand"]


# -- the listing -------------------------------------------------------------- #


def test_the_listing_groups_by_shape_in_the_files_order(root: Path) -> None:
    found = listed(root)
    assert found.setup == S2
    calls, episodes = found.groups
    assert (calls.shape.episode, calls.shape.kind) == (False, "text")
    assert [a.id for a in calls.answers] == [ID_A_OLD, ID_B, ID_A_NEW, ID_C]
    assert (episodes.shape.actors, episodes.shape.finish) == (
        ("model", "tool", "model"),
        "end_turn",
    )
    [episode] = episodes.answers
    assert episode.id == ID_E and episode.attached == 2
    by_id = {a.id: a for a in found.answers}
    assert by_id[ID_A_NEW].electable and by_id[ID_C].electable
    assert "recorded only under earlier setups" in (by_id[ID_A_OLD].refusal or "")
    assert by_id[ID_A_OLD].setups == (S1,)
    assert (found.orphans, found.detached, found.interrupted, found.oversize) == (
        1,
        1,
        1,
        1,
    )
    assert found.recordings == 11
    assert found.examined_through == "2026-11-03T08:11:00+00:00"


def test_the_listing_writes_nothing_and_says_the_declaration_first(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def tree() -> list[Path]:
        return sorted(
            p.relative_to(root) for p in root.rglob("*") if "__pycache__" not in p.parts
        )

    before = tree()
    assert main(argv(root)) == 0
    assert tree() == before
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == (
        f"tenant 'acme' · suite triage · writes to {root / 'captured.json'} · "
        "repository private · check llm_rubric"
    )
    text = "\n".join(lines)
    assert f"setup in force: {S2[:8]} · deterministic_output false" in text
    assert "group 1 · a single call, text · 4 answers from 4 recordings" in text
    assert (
        "group 2 · an episode, text, steps model → tool → model, finish end_turn "
        "· 1 answer from 1 recording"
    ) in text
    assert f"  {ID_A_NEW} · 2026-11-03T08:03:00+00:00 · setup {S2[:8]}\n" in text
    assert (
        f"  {ID_A_OLD} · 2026-11-03T08:01:00+00:00 · setup {S1[:8]} (earlier)" in text
    )
    assert "    answer: new answer about refunds\n    electable" in text
    assert "1 orphans" in text and "1 interrupted episodes" in text
    assert "--good ID or --bad ID, and give --by NAME" in text


def test_equal_answers_are_one_line_counted(root: Path) -> None:
    RecordingWriter(FileResultStore(root)).write(recording(C, S2, C_NEW, "12"))
    found = listed(root)
    [c] = [a for a in found.answers if a.id == ID_C]
    assert c.times == 2
    assert f"  {ID_C} · 2026-11-03T08:04:00+00:00 · setup {S2[:8]} · ×2" in (
        "\n".join(listing_lines(found))
    )


#: Words that rank, propose or judge. `good` and `bad` are not among them: they
#: are the person's own flags, and the listing names them.
JUDGING = ("better", "worse", "regress", "improve", "likely", "suggest", "recommend")


def test_no_word_of_the_listing_ranks_or_proposes(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv(root)) == 0
    out = capsys.readouterr().out.lower()
    for word in JUDGING:
        assert word not in out, word
    assert "import all" not in out and "--all" not in out
    assert "better" in "the better answer"  # the search finds a word that is there


# -- the election ------------------------------------------------------------- #


def test_an_election_writes_reviewed_answers_with_the_mark(root: Path) -> None:
    written = import_elect(listed(root), good=[ID_C], bad=[ID_A_NEW], by="Ada")
    # In the listing's order, not the command line's.
    assert written == (ID_A_NEW, ID_C)
    document = json.loads((root / "captured.json").read_text(encoding="utf-8"))
    assert document[0] == {
        "id": ID_A_NEW,
        "reviewed_answer": {
            "output": A_NEW,
            "check": "llm_rubric",
            "good": False,
            "input": f"Q: {json.dumps(A)}",
        },
        "metadata": {
            "source": "recordings",
            "reviewed_by": "Ada",
            "setup_digest": S2,
            "examined_through": "2026-11-03T08:11:00+00:00",
        },
    }
    assert all("expected" not in entry and "label" not in entry for entry in document)
    answers = [c.reviewed_answer for c in read_cases(root / "captured.json")]
    assert [a.good for a in answers if a is not None] == [False, True]
    suite, _ = loaded(root)
    assert [c.id for c in suite.cases] == ["by-hand", ID_A_NEW, ID_C]
    # And the listing reads the yes or no back, by the pair.
    by_id = {a.id: a for a in listed(root).answers}
    assert (by_id[ID_A_NEW].elected, by_id[ID_C].elected) == (False, True)
    assert by_id[ID_A_NEW].refusal == "already in the file"


def test_a_structured_answer_is_written_as_its_structure(root: Path) -> None:
    text = '{"refund": 14}'
    RecordingWriter(FileResultStore(root)).write(
        recording(
            case("as json?"),
            S2,
            None,
            "12",
            response=RecordedResponse(output=text, kind="structured", input="Q"),
        )
    )
    import_elect(listed(root), good=[answer_id(case("as json?"), text)], by="Ada")
    [entry] = json.loads((root / "captured.json").read_text(encoding="utf-8"))
    assert entry["reviewed_answer"]["output"] == {"refund": 14}


@pytest.mark.parametrize(
    ("good", "by", "match"),
    [
        (["cap-0000000000000000-00000000"], "Ada", "is not an answer the recordings"),
        ([ID_A_OLD], "Ada", "recorded only under earlier setups"),
        ([], "Ada", "no answer named"),
        ([ID_C], None, "--by NAME is missing"),
        ([ID_C], "  ", "--by NAME is missing"),
    ],
    ids=["unknown", "earlier-setup", "none", "no mark", "blank mark"],
)
def test_an_election_refused_writes_nothing(
    root: Path, good: list[str], by: str | None, match: str
) -> None:
    with pytest.raises(RefusedError, match=match):
        import_elect(listed(root), good=good, by=by)
    assert not (root / "captured.json").exists()


def test_an_answer_named_twice_is_refused(root: Path) -> None:
    with pytest.raises(RefusedError, match="named twice"):
        import_elect(listed(root), good=[ID_C], bad=[ID_C], by="Ada")
    assert not (root / "captured.json").exists()


def test_an_answer_with_no_input_or_a_conversation_cannot_be_written(
    root: Path,
) -> None:
    writer = RecordingWriter(FileResultStore(root))
    writer.write(
        recording(
            case("no question"),
            S2,
            None,
            "12",
            response=RecordedResponse(output="x", kind="text"),
        )
    )
    turns = '[{"role": "assistant", "content": "hi"}]'
    writer.write(
        recording(
            case("a chat"),
            S2,
            None,
            "13",
            response=RecordedResponse(output=turns, kind="conversation", input="Q"),
        )
    )
    found = listed(root)
    with pytest.raises(RefusedError, match="recorded with no input"):
        import_elect(found, good=[answer_id(case("no question"), "x")], by="Ada")
    with pytest.raises(RefusedError, match="a conversation"):
        import_elect(found, good=[answer_id(case("a chat"), turns)], by="Ada")
    assert not (root / "captured.json").exists()


def test_an_answer_already_written_is_refused(root: Path) -> None:
    import_elect(listed(root), good=[ID_C], by="Ada")
    before = (root / "captured.json").read_bytes()
    with pytest.raises(RefusedError, match="already in the file"):
        import_elect(listed(root), bad=[ID_C], by="Ada")
    assert (root / "captured.json").read_bytes() == before


def test_one_sample_is_refused_before_a_case_is_written(tmp_path: Path) -> None:
    recorded(tmp_path)
    suite_file(tmp_path, samples=1)
    with pytest.raises(RefusedError, match="needs at least 2"):
        import_elect(listed(tmp_path), good=[ID_C], by="Ada")
    assert not (tmp_path / "captured.json").exists()


def test_a_second_election_appends_and_never_rewrites(root: Path) -> None:
    import_elect(listed(root), good=[ID_A_NEW], by="Ada")
    before = (root / "captured.json").read_text(encoding="utf-8")
    import_elect(listed(root), bad=[ID_E], by="Grace")
    after = (root / "captured.json").read_text(encoding="utf-8")
    kept = before.rstrip()[: before.rstrip().rfind("]")].rstrip()
    assert after.startswith(kept)
    assert [c.id for c in read_cases(root / "captured.json")] == [ID_A_NEW, ID_E]


def test_a_public_regime_lists_and_refuses_to_write(root: Path) -> None:
    suite_file(root, regime="public")
    found = listed(root)
    assert len(found.answers) == 5
    with pytest.raises(
        RefusedError, match="derogation is a person writing the case by hand"
    ):
        import_elect(found, good=[ID_A_NEW], by="Ada")
    assert not (root / "captured.json").exists()
    assert "writing is refused" in listing_lines(found)[-1]


# -- a deterministic output --------------------------------------------------- #


def test_a_yes_in_a_deterministic_suite_also_writes_the_expected(
    tmp_path: Path,
) -> None:
    recorded(tmp_path)
    suite_file(tmp_path, deterministic=True)
    written = import_elect(listed(tmp_path), good=[ID_C], bad=[ID_A_NEW], by="Ada")
    assert written == (ID_A_NEW, ID_C, capture_id(C))
    document = json.loads((tmp_path / "captured.json").read_text(encoding="utf-8"))
    expected = document[-1]
    assert expected["id"] == capture_id(C)
    assert (expected["vars"], expected["expected"]) == (C, C_NEW)
    assert expected["metadata"]["reviewed_by"] == "Ada"
    # A no writes no expected.
    assert sum(1 for entry in document if "expected" in entry) == 1
    suite, _ = loaded(tmp_path)
    assert [c.id for c in suite.cases] == ["by-hand", ID_A_NEW, ID_C, capture_id(C)]


def test_two_yeses_to_one_input_or_an_expected_held_are_refused(
    tmp_path: Path,
) -> None:
    recorded(tmp_path)
    suite_file(tmp_path, deterministic=True)
    RecordingWriter(FileResultStore(tmp_path)).write(
        recording(C, S2, "Via Roma 1, Milano", "12")
    )
    other = answer_id(C, "Via Roma 1, Milano")
    with pytest.raises(RefusedError, match="two answers to one input"):
        import_elect(listed(tmp_path), good=[ID_C, other], by="Ada")
    import_elect(listed(tmp_path), good=[ID_C], by="Ada")
    with pytest.raises(RefusedError, match="and the file holds one for it"):
        import_elect(listed(tmp_path), good=[other], by="Ada")


# -- the command -------------------------------------------------------------- #


def test_the_command_prints_the_declaration_before_each_case_written(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv(root, "--good", ID_C, "--bad", ID_E, "--by", "Ada")) == 0
    lines = capsys.readouterr().out.splitlines()
    declaration = (
        f"tenant 'acme' · suite triage · writes to {root / 'captured.json'} · "
        "repository private · check llm_rubric"
    )
    assert lines[:4] == [
        declaration,
        f"  wrote {ID_C}",
        declaration,
        f"  wrote {ID_E}",
    ]
    assert "nothing was committed, run or promoted" in lines[-1]
    assert [c.id for c in read_cases(root / "captured.json")] == [ID_C, ID_E]


def test_the_command_refuses_a_write_with_no_mark(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv(root, "--good", ID_C)) == EXIT_USAGE
    assert "--by NAME is missing" in capsys.readouterr().err
    assert not (root / "captured.json").exists()


# -- since the last import ---------------------------------------------------- #


def test_status_says_never_imported_and_then_how_many_came_after(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    suite, module = loaded(root)
    assert imported_since(root, suite, module, "acme") == (None, 11)
    status = [
        "record",
        "status",
        "--tenant",
        "acme",
        "--suite",
        str(root / "suite.py"),
        "--root",
        str(root),
    ]
    assert main(status) == 0
    assert "never imported, 11 in all" in capsys.readouterr().out

    import_elect(listed(root), good=[ID_A_NEW], by="Ada")
    RecordingWriter(FileResultStore(root)).write(
        recording(case("later"), S2, "after", "30")
    )
    assert imported_since(root, suite, module, "acme") == (1, 12)
    assert main([*status, "--json"]) == 0
    [tenant] = json.loads(capsys.readouterr().out)["tenants"]
    [triage] = tenant["recordings"]["suites"]
    assert (triage["imported"], triage["since_last_import"]) == (True, 1)


def test_status_without_a_suite_does_not_read_the_draft(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["record", "status", "--root", str(root), "--json"]) == 0
    [tenant] = json.loads(capsys.readouterr().out)["tenants"]
    [triage] = tenant["recordings"]["suites"]
    assert (triage["imported"], triage["since_last_import"]) == (None, None)


@pytest.mark.parametrize(
    "command",
    [
        ["record", "on", "--tenant", "acme", "--good", "x"],
        ["record", "off", "--tenant", "acme", "--suite", "s.py"],
        ["record", "status", "--bad", "x"],
        ["record", "status", "--by", "Ada"],
    ],
)
def test_the_import_options_belong_to_import(
    root: Path, command: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([*command, "--root", str(root)]) == EXIT_USAGE
    assert "belongs to" in capsys.readouterr().err
