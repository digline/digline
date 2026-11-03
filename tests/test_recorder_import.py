"""The narrow import: a suite's recorded cases, listed, and written only where a
person named them. (ADR 0058 §4, §10; ADR 0023 §3, §4, §6, §7, §8, §9, §11)

The recordings are written with the store's own writer, so what is read is
what the recorder files: single calls under two setups, an episode with its
calls, an orphan, an interrupted episode, a recording over the ceiling of what
a recording keeps, and a call whose episode is not among the files.

What is held here:

- recordings of another tenant than the suite's are refused before anything
  is shown, and a data suite and a suite with no capture source by name;
- the listing writes nothing, groups by the case compartment under the id of
  ADR 0023 §6, separates the setup in force from earlier ones, and counts and
  names what is not a case;
- an election writes the cases named and no other, with `vars`, the label
  and the watermark and never an `expected`, after the draft's last case,
  and refuses an id it does not hold, a case seen only under an earlier setup,
  a case already elected, and a public regime, writing nothing each time;
- the file it writes is read by `read_cases` and loaded by the suite;
- `digline record status --suite` says *never imported* and then how many
  recordings came after the last import.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from digline.cli.main import main
from digline.core.capture import capture_id
from digline.core.recording import RecordedStep, Recording, setup_digest_of
from digline.core.refused import RefusedError
from digline.core.run import RecordedResponse
from digline.host import (
    import_elect,
    import_listing,
    imported_since,
    load_suite,
    read_cases,
)
from digline.store.file_store import FileResultStore, RecordingWriter
from digline.wire import EXIT_USAGE

S1 = setup_digest_of({"model": "m", "system": "Be brief."})
S2 = setup_digest_of({"model": "m", "system": "Be brief and kind."})
EPISODE = "e" * 32
ELSEWHERE = "f" * 32


def case(text: str) -> dict[str, object]:
    return {"messages": [{"role": "user", "content": text}]}


A, B, C, E = case("refund?"), case("hours?"), case("address?"), case("lost parcel")


def suite_file(root: Path, regime: str = "private", *, loads: bool = True) -> Path:
    path = root / "suite.py"
    captured = ", *read_cases(HERE / 'captured.json')" if loads else ""
    path.write_text(
        "from pathlib import Path\n"
        "from digline.core import Contains\n"
        "from digline.host import read_cases\n"
        "from digline.run import Case, CaptureSource, Suite\n"
        "HERE = Path(__file__).parent\n"
        "suite = Suite(\n"
        "    tenant='acme', environment='dev', name='triage',\n"
        "    assertions=[Contains(needle='x')],\n"
        f"    cases=[Case(id='by-hand'){captured}],\n"
        "    capture=CaptureSource(\n"
        f"        cases_file='captured.json', repository={regime!r}\n"
        "    ),\n"
        ")\n",
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
        "response": RecordedResponse(output=output or "", kind="text")
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
        recording(A, S1, "old answer about refunds", "01"),
        recording(B, S1, "open nine to five", "02"),
        recording(A, S2, "new answer about refunds", "03"),
        recording(C, S2, "Via Roma 1", "04"),
        recording(
            E,
            S2,
            "we have found it",
            "05",
            steps=(RecordedStep(index=0, actor="model"),),
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


def loaded(root: Path) -> tuple[Any, Any]:
    suite, how = load_suite(str(root / "suite.py"), root=root)
    return suite, how.module


def listed(root: Path, tenant: str = "acme") -> Any:
    suite, module = loaded(root)
    return import_listing(root, suite, module, tenant)


# -- the id ------------------------------------------------------------------- #


def test_the_id_is_the_inputs_and_the_key_order_does_not_move_it() -> None:
    one = capture_id({"a": 1, "b": {"c": [1, 2]}})
    assert one == capture_id({"b": {"c": [1, 2]}, "a": 1})
    assert one.startswith("cap-") and len(one) == len("cap-") + 16
    assert one != capture_id({"a": 2, "b": {"c": [1, 2]}})


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


def test_a_data_suite_cannot_import(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    toml = root / "suite.toml"
    toml.write_text("[suite]\n", encoding="utf-8")
    argv = ["record", "import", "--tenant", "acme", "--suite", str(toml)]
    assert main([*argv, "--root", str(root)]) == EXIT_USAGE
    err = capsys.readouterr().err
    assert "ADR 0023 §3" in err
    assert "Write a suite.py with Suite.capture = CaptureSource(" in err


def test_a_data_suite_cannot_declare_capture(tmp_path: Path) -> None:
    (tmp_path / "cases.json").write_text("[]", encoding="utf-8")
    toml = tmp_path / "suite.toml"
    toml.write_text(
        '[suite]\ntenant = "acme"\nenvironment = "dev"\nname = "q"\n'
        'cases = "cases.json"\ncapture = "captured.json"\n'
        '[[assertions]]\ntype = "contains"\nneedle = "x"\n',
        encoding="utf-8",
    )
    from digline.host import UsageError

    with pytest.raises(UsageError, match="`capture` is not settable from a data file"):
        load_suite(str(toml), root=tmp_path)


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


# -- the suite loads what was elected ----------------------------------------- #


def test_a_suite_that_declares_and_loads_its_capture_file_loads(root: Path) -> None:
    import_elect(listed(root), positive=[capture_id(A)])
    suite, _ = loaded(root)
    assert [c.id for c in suite.cases] == ["by-hand", capture_id(A)]


def test_a_suite_that_does_not_load_its_capture_file_is_refused_with_the_ids(
    root: Path,
) -> None:
    import_elect(listed(root), positive=[capture_id(A)], negative=[capture_id(C)])
    suite_file(root, loads=False)
    from digline.host import UsageError

    with pytest.raises(UsageError) as refused:
        loaded(root)
    message = str(refused.value)
    assert "does not load 2 of its cases" in message
    assert f"{capture_id(A)}, {capture_id(C)}" in message


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


def test_the_listing_groups_by_case_and_separates_the_setup_in_force(
    root: Path,
) -> None:
    found = listed(root)
    assert found.setup == S2
    assert [c.id for c in found.cases] == [
        capture_id(A),
        capture_id(B),
        capture_id(C),
        capture_id(E),
    ]
    by_id = {c.id: c for c in found.cases}
    a = by_id[capture_id(A)]
    assert a.answers == ("new answer about refunds",)
    assert (a.earlier, a.earlier_setups) == (1, 1)
    assert a.electable
    b = by_id[capture_id(B)]
    assert b.answers == () and b.earlier == 1 and not b.electable
    e = by_id[capture_id(E)]
    assert e.kind == "episode" and e.attached == 2
    assert (found.orphans, found.detached, found.interrupted, found.oversize) == (
        1,
        1,
        1,
        1,
    )
    assert found.recordings == 11
    assert found.examined_through == "2026-11-03T08:11:00+00:00"


def test_the_listing_writes_nothing(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = sorted(p.relative_to(root) for p in root.rglob("*"))
    code = main(
        [
            "record",
            "import",
            "--tenant",
            "acme",
            "--suite",
            str(root / "suite.py"),
            "--root",
            str(root),
        ]
    )
    assert code == 0
    after = sorted(
        p.relative_to(root) for p in root.rglob("*") if "__pycache__" not in p.parts
    )
    assert [p for p in after if "__pycache__" not in p.parts] == [
        p for p in before if "__pycache__" not in p.parts
    ]
    text = capsys.readouterr().out
    assert f"setup in force: {S2[:8]}\n" in text
    assert f"case {capture_id(A)} · call · electable" in text
    assert "answer: new answer about refunds" in text
    assert "old answer about refunds" not in text
    assert "earlier: 1 recordings under 1 earlier setups" in text
    assert f"case {capture_id(B)} · call · recorded only under earlier setups" in text
    assert "1 orphans" in text and "1 interrupted episodes" in text
    assert "--positive ID, --negative ID" in text


# -- the election ------------------------------------------------------------- #


def test_an_election_writes_the_named_cases_and_no_other(root: Path) -> None:
    written = import_elect(
        listed(root), positive=[capture_id(C)], negative=[capture_id(A)]
    )
    # In the listing's order, not the command line's.
    assert written == (capture_id(A), capture_id(C))
    document = json.loads((root / "captured.json").read_text(encoding="utf-8"))
    assert [entry["id"] for entry in document] == [capture_id(A), capture_id(C)]
    first = document[0]
    assert first == {
        "id": capture_id(A),
        "vars": A,
        "label": "negative",
        "metadata": {
            "source": "recordings",
            "setup_digest": S2,
            "examined_through": "2026-11-03T08:11:00+00:00",
        },
    }
    assert "expected" not in first
    # Read back by the reader a suite uses, and loaded by the suite.
    assert [c.label for c in read_cases(root / "captured.json")] == [
        "negative",
        "positive",
    ]
    suite, _ = loaded(root)
    assert [c.id for c in suite.cases] == ["by-hand", capture_id(A), capture_id(C)]


@pytest.mark.parametrize(
    ("positive", "match"),
    [
        (["cap-0000000000000000"], "is not a case the recordings"),
        ([capture_id(B)], "recorded only under earlier setups"),
        ([], "no case named"),
    ],
    ids=["unknown", "earlier-setup", "none"],
)
def test_an_election_refused_writes_nothing(
    root: Path, positive: list[str], match: str
) -> None:
    with pytest.raises(RefusedError, match=match):
        import_elect(listed(root), positive=positive)
    assert not (root / "captured.json").exists()


def test_an_id_named_twice_is_refused(root: Path) -> None:
    with pytest.raises(RefusedError, match="named twice"):
        import_elect(listed(root), positive=[capture_id(A)], negative=[capture_id(A)])
    assert not (root / "captured.json").exists()


def test_a_case_already_elected_is_refused_with_its_label(root: Path) -> None:
    import_elect(listed(root), positive=[capture_id(A)])
    before = (root / "captured.json").read_bytes()
    with pytest.raises(RefusedError, match="labelled positive"):
        import_elect(listed(root), negative=[capture_id(A)])
    assert (root / "captured.json").read_bytes() == before


def test_a_second_election_appends_and_never_rewrites(root: Path) -> None:
    import_elect(listed(root), positive=[capture_id(A)])
    before = (root / "captured.json").read_text(encoding="utf-8")
    import_elect(listed(root), negative=[capture_id(E)])
    after = (root / "captured.json").read_text(encoding="utf-8")
    kept = before.rstrip()[: before.rstrip().rfind("]")].rstrip()
    assert after.startswith(kept)
    assert [c.id for c in read_cases(root / "captured.json")] == [
        capture_id(A),
        capture_id(E),
    ]


def test_a_public_regime_lists_and_refuses_to_write(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    suite_file(root, regime="public")
    found = listed(root)
    assert len(found.cases) == 4
    with pytest.raises(
        RefusedError, match="derogation is a person writing the case by hand"
    ):
        import_elect(found, positive=[capture_id(A)])
    assert not (root / "captured.json").exists()


def test_identical_answers_are_one_line_and_nothing_left_says_nothing(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    RecordingWriter(FileResultStore(root)).write(recording(C, S2, "Via Roma 1", "12"))
    argv = [
        "record",
        "import",
        "--tenant",
        "acme",
        "--suite",
        str(root / "suite.py"),
        "--root",
        str(root),
    ]
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "answer: Via Roma 1  (×2)" in out
    assert "--positive ID, --negative ID" in out
    found = listed(root)
    import_elect(
        found,
        positive=[c.id for c in found.cases if c.electable],
    )
    assert main(argv) == 0
    assert "--positive ID, --negative ID" not in capsys.readouterr().out


def test_the_command_writes_the_named_cases(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [
        "record",
        "import",
        "--tenant",
        "acme",
        "--suite",
        str(root / "suite.py"),
        "--root",
        str(root),
        "--positive",
        capture_id(C),
        "--negative",
        capture_id(E),
    ]
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "wrote 2 cases" in out
    assert "nothing was committed, run or promoted" in out
    assert [c.id for c in read_cases(root / "captured.json")] == [
        capture_id(C),
        capture_id(E),
    ]


# -- since the last import ---------------------------------------------------- #


def test_status_says_never_imported_and_then_how_many_came_after(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    suite, module = loaded(root)
    assert imported_since(root, suite, module, "acme") == (None, 11)
    argv = [
        "record",
        "status",
        "--tenant",
        "acme",
        "--suite",
        str(root / "suite.py"),
        "--root",
        str(root),
    ]
    assert main(argv) == 0
    assert "never imported, 11 in all" in capsys.readouterr().out

    import_elect(listed(root), positive=[capture_id(A)])
    RecordingWriter(FileResultStore(root)).write(
        recording(case("later"), S2, "after", "30")
    )
    assert imported_since(root, suite, module, "acme") == (1, 12)
    assert main([*argv, "--json"]) == 0
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
    "argv",
    [
        ["record", "on", "--tenant", "acme", "--positive", "x"],
        ["record", "off", "--tenant", "acme", "--suite", "s.py"],
        ["record", "status", "--negative", "x"],
    ],
)
def test_the_import_options_belong_to_import(
    root: Path, argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([*argv, "--root", str(root)]) == EXIT_USAGE
    assert "belongs to" in capsys.readouterr().err
