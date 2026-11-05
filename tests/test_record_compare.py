"""`digline record compare`: a suite's recorded answers, by case and by setup,
shown and never judged. (ADR 0058; the piece D4 of 1.1)

The recordings are written with the store's own writer, so what is read is what
the recorder files: three setups, answers that change between them and repeat
inside one, an episode, a recording with no `recorded_at`, and what the import
counts and never makes a case.

What is held here:

- for each case, grouped by its input, the answers under each setup in the
  order they were recorded, each with its digest and its date; equal answers
  one after the other under one setup are one line counted, never hidden, and
  equal answers apart are two;
- nothing is written, and the import's watermark is not moved;
- `--case`, `--since`, `--setup A B` and `--show-setup` keep what they say, and
  each is refused where it cannot mean anything, with how to write it;
- `--json` is the same structure, with digests and never a recorded word;
- no word of the output judges an answer;
- a suite with no recordings is a sentence and exit 0, not an error.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from digline.cli.main import main
from digline.core.capture import capture_id
from digline.core.recording import Recording, episode_setup, setup_digest_of
from digline.core.refused import RefusedError
from digline.core.run import RecordedResponse, RecordedStep
from digline.host import load_suite, record_compare
from digline.store.file_store import FileResultStore, RecordingWriter
from digline.wire import EXIT_OK, EXIT_USAGE, record_compare_json

LONG = "Be brief and kind.\n" + "Never promise a refund. " * 20
SETUP_1: dict[str, object] = {"model": "m", "system": "Be brief.", "temperature": 0}
SETUP_2: dict[str, object] = {"model": "m", "system": LONG, "temperature": 0}
SETUP_3: dict[str, object] = {"model": "m2", "system": LONG}
S1, S2, S3 = (setup_digest_of(s) for s in (SETUP_1, SETUP_2, SETUP_3))


def case(text: str) -> dict[str, object]:
    return {"messages": [{"role": "user", "content": text}]}


REFUND, HOURS, PARCEL = case("refund?"), case("hours?"), case("lost parcel")


def recording(
    vars: dict[str, object],  # noqa: A002
    setup: dict[str, object],
    output: str,
    at: str | None,
    **changes: Any,
) -> Recording:
    # An episode's steps are its response's (ADR 0060 §6).
    steps = changes.pop("steps", None)
    fields: dict[str, Any] = {
        "source_tenant": "acme",
        "app": "support",
        "suite": "triage",
        "case": vars,
        "setup": setup,
        "setup_digest": setup_digest_of(setup),
        "response": RecordedResponse(output=output, kind="text", steps=steps),
        "recorded_at": None if at is None else f"2026-11-03T08:{at}:00+00:00",
    }
    fields.update(changes)
    return Recording(**fields)


def recorded(root: Path) -> None:
    """Written out of time order on purpose: the view orders by recorded_at."""
    writer = RecordingWriter(FileResultStore(root))
    for item in (
        recording(REFUND, SETUP_2, "no refunds", "10"),
        recording(REFUND, SETUP_1, "refunds in 14 days", "01"),
        recording(REFUND, SETUP_1, "refunds in 14 days", "02"),
        recording(REFUND, SETUP_1, "refunds in 14 days", "03"),
        recording(REFUND, SETUP_1, "refunds in 30 days", "04"),
        recording(REFUND, SETUP_1, "refunds in 14 days", "05"),
        recording(REFUND, SETUP_3, "ask the shop", "20"),
        recording(HOURS, SETUP_1, "nine to five", "06"),
        recording(HOURS, SETUP_2, "nine to five", "11"),
        recording(
            PARCEL,
            SETUP_2,
            "we have found it",
            "12",
            steps=(RecordedStep(index=0, actor="model"),),
            id="e" * 32,
        ),
        recording(case("where is it?"), SETUP_2, "looking", "13", episode="e" * 32),
        recording(case("orphan?"), SETUP_2, "alone", "14", orphan=True),
        recording(HOURS, SETUP_3, "nine to six", None),
        recording(REFUND, SETUP_1, "a call of another suite", "07", suite="other"),
    ):
        writer.write(item)


def suite_file(root: Path) -> Path:
    path = root / "suite.py"
    path.write_text(
        "from digline.core import Contains\n"
        "from digline.run import Case, Suite\n"
        "suite = Suite(\n"
        "    tenant='acme', environment='dev', name='triage',\n"
        "    assertions=[Contains(needle='x')],\n"
        "    cases=[Case(id='by-hand')],\n"
        ")\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def root(tmp_path: Path) -> Path:
    recorded(tmp_path)
    suite_file(tmp_path)
    return tmp_path


def compared(root: Path, tenant: str = "acme", **options: Any) -> Any:
    suite, _ = load_suite(str(root / "suite.py"), root=root)
    return record_compare(root, suite, tenant, **options)


def run(root: Path, *extra: str) -> list[str]:
    return [
        "record",
        "compare",
        "--tenant",
        "acme",
        "--suite",
        str(root / "suite.py"),
        "--root",
        str(root),
        *extra,
    ]


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def answers(found: Any, vars: dict[str, object]) -> dict[str, list[tuple[str, int]]]:  # noqa: A002
    [one] = [c for c in found.cases if c.id == capture_id(vars)]
    return {s.setup: [(a.text, a.times) for a in s.answers] for s in one.setups}


# -- the view ----------------------------------------------------------------- #


def test_each_case_shows_its_answers_by_setup_in_the_order_they_were_recorded(
    root: Path,
) -> None:
    found = compared(root)
    # Setups in the order of their first answer, and only the suite's.
    assert found.setups == (S1, S2, S3)
    assert [c.id for c in found.cases] == [
        capture_id(REFUND),
        capture_id(HOURS),
        capture_id(PARCEL),
    ]
    assert answers(found, REFUND) == {
        S1: [
            # Three equal answers one after the other: one line, counted.
            ("refunds in 14 days", 3),
            ("refunds in 30 days", 1),
            # Equal to the first, and not next to it: a line of its own.
            ("refunds in 14 days", 1),
        ],
        S2: [("no refunds", 1)],
        S3: [("ask the shop", 1)],
    }
    [refund] = [c for c in found.cases if c.id == capture_id(REFUND)]
    run_of_three = refund.setups[0].answers[0]
    assert run_of_three.digest == digest("refunds in 14 days")
    assert run_of_three.first_at == "2026-11-03T08:01:00+00:00"
    assert run_of_three.last_at == "2026-11-03T08:03:00+00:00"
    # An answer with no recorded_at comes after the dated ones.
    assert answers(found, HOURS) == {
        S1: [("nine to five", 1)],
        S2: [("nine to five", 1)],
        S3: [("nine to six", 1)],
    }
    [parcel] = [c for c in found.cases if c.id == capture_id(PARCEL)]
    assert parcel.kind == "episode"
    # What the import counts and never makes a case is counted here too.
    assert (found.orphans, found.detached, found.interrupted) == (1, 0, 0)
    assert found.recordings == 13


def test_the_text_says_what_the_structure_holds(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(run(root)) == EXIT_OK
    out = capsys.readouterr().out
    assert f"3 setups: {S1[:8]}, {S2[:8]}, {S3[:8]}" in out
    assert f"case {capture_id(REFUND)} · call" in out
    assert f"case {capture_id(PARCEL)} · episode" in out
    assert (
        f"    2026-11-03T08:01:00+00:00  {digest('refunds in 14 days')}  ×3, "
        "through 2026-11-03T08:03:00+00:00: refunds in 14 days"
    ) in out
    assert f"    undated  {digest('nine to six')}: nine to six" in out
    assert "3 cases; not shown: 1 orphans" in out


def test_nothing_is_written_and_the_watermark_does_not_move(root: Path) -> None:
    def tree() -> dict[str, bytes]:
        return {
            str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts
        }

    before = tree()
    assert main(run(root)) == EXIT_OK
    assert main(run(root, "--json")) == EXIT_OK
    assert main(run(root, "--setup", S1[:8], S2[:8], "--show-setup")) == EXIT_OK
    assert tree() == before


# -- the filters -------------------------------------------------------------- #


def test_case_keeps_one_case_and_an_unknown_one_is_refused(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    found = compared(root, case=capture_id(HOURS))
    assert [c.id for c in found.cases] == [capture_id(HOURS)]
    assert main(run(root, "--case", "cap-0000000000000000")) == EXIT_USAGE
    assert "is not a case the recordings of suite 'triage' hold" in (
        capsys.readouterr().err
    )


def test_since_keeps_what_came_at_or_after_and_counts_the_undated(root: Path) -> None:
    found = compared(root, since="2026-11-03T08:10:00+00:00")
    assert answers(found, REFUND) == {
        S2: [("no refunds", 1)],
        S3: [("ask the shop", 1)],
    }
    assert found.undated == 1
    # Compared as an instant: the same moment in another offset.
    same = compared(root, since="2026-11-03T10:10:00+02:00")
    assert same.cases == found.cases


def test_since_without_an_offset_is_refused_with_the_form(root: Path) -> None:
    with pytest.raises(RefusedError, match=r"2026-11-03T08:00:00\+00:00"):
        compared(root, since="2026-11-03T08:10:00")


def test_two_setups_stand_side_by_side(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    found = compared(root, setups=(S1[:8], S3[:8]))
    assert found.pair == (S1, S3)
    assert found.setup_keys is None
    # Every case with an answer under one of the two, and both setups shown,
    # the empty one included.
    assert [c.id for c in found.cases] == [capture_id(REFUND), capture_id(HOURS)]
    assert answers(found, REFUND) == {
        S1: [
            ("refunds in 14 days", 3),
            ("refunds in 30 days", 1),
            ("refunds in 14 days", 1),
        ],
        S3: [("ask the shop", 1)],
    }
    assert main(run(root, "--setup", S2[:8], S3[:8])) == EXIT_OK
    out = capsys.readouterr().out
    assert f"side by side: A {S2[:8]}, B {S3[:8]}" in out
    assert f"  setup B {S3[:8]}\n    nothing recorded" in out


def test_show_setup_names_the_keys_and_never_a_prompt_whole(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    found = compared(root, setups=(S1[:8], S3[:8]), show_setup=True)
    assert found.same_keys == 0
    assert [(k.key, k.side) for k in found.setup_keys] == [
        ("model", "both"),
        ("system", "both"),
        ("temperature", "a"),
    ]
    [system] = [k for k in found.setup_keys if k.key == "system"]
    assert system.b.clipped and system.b.chars == len(LONG)
    assert system.b.preview == "Be brief and kind."
    assert main(run(root, "--setup", S1[:8], S2[:8], "--show-setup")) == EXIT_OK
    out = capsys.readouterr().out
    assert "keys the two setups differ on (2 the same):" in out
    assert (
        f'    system: A "Be brief." · B "Be brief and kind."… ({len(LONG)} characters)'
    ) in out
    assert "Never promise a refund" not in out


@pytest.mark.parametrize(
    ("extra", "said"),
    [
        (("--show-setup",), "needs the two: name them with --setup A B"),
        (("--setup", "0000000000", "1111111111"), "no answer of the suite was"),
        (("--setup", "abc", "def"), "at least the 8 characters"),
    ],
    ids=["show-setup alone", "unknown digests", "short digests"],
)
def test_a_setup_that_cannot_be_compared_is_refused_with_how(
    root: Path, capsys: pytest.CaptureFixture[str], extra: tuple[str, ...], said: str
) -> None:
    assert main(run(root, *extra)) == EXIT_USAGE
    assert said in capsys.readouterr().err


def test_the_same_setup_twice_and_one_setup_alone_are_refused(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(RefusedError, match="a setup beside itself is one"):
        compared(root, setups=(S1[:8], S1))
    with pytest.raises(RefusedError, match="was given 1"):
        compared(root, setups=(S1[:8],))
    # On the command line argparse asks for the second.
    with pytest.raises(SystemExit) as raised:
        main(run(root, "--setup", S1[:8]))
    assert raised.value.code != EXIT_OK
    assert "expected 2 arguments" in capsys.readouterr().err


def test_another_tenant_is_refused_before_anything_is_shown(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(RefusedError, match="are not compared for suite 'triage'"):
        compared(root, tenant="globex")


@pytest.mark.parametrize(
    "extra",
    [("--case", "cap-1"), ("--since", "2026-11-03T08:00:00+00:00"), ("--show-setup",)],
)
def test_the_options_of_compare_belong_to_it(
    root: Path, capsys: pytest.CaptureFixture[str], extra: tuple[str, ...]
) -> None:
    argv = ["record", "status", "--tenant", "acme", "--root", str(root), *extra]
    assert main(argv) == EXIT_USAGE
    assert "belongs to `digline record compare`, not `digline record status`" in (
        capsys.readouterr().err
    )


# -- for a program ------------------------------------------------------------ #


def test_json_is_the_structure_with_digests_and_never_the_text(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(run(root, "--json", "--setup", S1[:8], S2[:8], "--show-setup")) == (
        EXIT_OK
    )
    printed = json.loads(capsys.readouterr().out)
    found = compared(root, setups=(S1[:8], S2[:8]), show_setup=True)
    assert printed == json.loads(json.dumps(record_compare_json(found)))
    assert printed["pair"] == [S1[:8], S2[:8]]
    assert printed["setup_keys"] == {
        "same": 2,
        "keys": [{"key": "system", "side": "both"}],
    }
    [refund] = [c for c in printed["cases"] if c["id"] == capture_id(REFUND)]
    assert refund["setups"][0]["answers"][0] == {
        "digest": digest("refunds in 14 days"),
        "first_at": "2026-11-03T08:01:00+00:00",
        "last_at": "2026-11-03T08:03:00+00:00",
        "times": 3,
    }
    text = json.dumps(printed)
    for word in ("refunds in", "nine to", "Be brief", "refund?", "messages"):
        assert word not in text, word
    # The control: the same words are in the text the person reads.
    assert main(run(root, "--setup", S1[:8], S2[:8], "--show-setup")) == EXIT_OK
    out = capsys.readouterr().out
    for word in ("refunds in", "nine to", "Be brief", "refund?", "messages"):
        assert word in out, word


# -- nothing judged, nothing recorded ----------------------------------------- #


JUDGING = ("better", "worse", "regress", "improve", "changed", "good", "bad")


def test_no_word_of_the_output_judges_an_answer(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for extra in ((), ("--setup", S1[:8], S3[:8], "--show-setup"), ("--json",)):
        assert main(run(root, *extra)) == EXIT_OK
        out = capsys.readouterr().out.lower()
        for word in JUDGING:
            assert word not in out, (extra, word)
    # The control: the search finds a word where one is.
    assert "better" in "the better answer"


def test_a_suite_with_nothing_recorded_is_a_sentence_and_exit_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    suite_file(tmp_path)
    assert main(run(tmp_path)) == EXIT_OK
    out = capsys.readouterr().out
    assert "nothing recorded for suite triage in tenant 'acme'" in out
    assert "0 cases" in out


def test_a_system_of_messages_is_shown_by_its_first_text_never_as_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `system` the way Chat Completions carries it, a list of messages: each
    side shows its first message's text, clipped at 60, and how many messages
    there are. Before, it was the list as JSON, its quotes escaped."""
    first = (
        'You are the "support" agent of a shop that sells parcels, and nothing else.'
    )
    one: dict[str, object] = {
        "model": "m",
        "system": [{"role": "system", "content": "Be brief."}],
    }
    two: dict[str, object] = {
        "model": "m",
        "system": [
            {"role": "system", "content": [{"type": "text", "text": first}]},
            {"role": "developer", "content": "Use the tools."},
        ],
    }
    writer = RecordingWriter(FileResultStore(tmp_path))
    writer.write(recording(REFUND, one, "refunds in 14 days", "01"))
    writer.write(recording(REFUND, two, "refunds in 14 days", "02"))
    suite_file(tmp_path)
    a, b = (setup_digest_of(s)[:8] for s in (one, two))
    assert main(run(tmp_path, "--setup", a, b, "--show-setup")) == EXIT_OK
    out = capsys.readouterr().out
    assert (
        f'    system: A "Be brief." (1 message) · B "{first[:60]}"… (2 messages)'
    ) in out
    [line] = [line for line in out.splitlines() if line.startswith("    system:")]
    assert '\\"' not in line and "[{" not in line
    found = compared(tmp_path, setups=(a, b), show_setup=True)
    [system] = [k for k in found.setup_keys if k.key == "system"]
    assert (system.b.message_count, system.b.chars, system.b.clipped) == (
        2,
        len(first),
        True,
    )


def test_an_episode_shows_its_calls_and_models_and_its_children_one_per_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An episode's setup is shown by the shape of its steps: how many model
    calls each episode made, and the models its child setups name, beside the
    setup's name. `--show-setup` resolves `child_setups` one per line. A list,
    never a ranking."""
    haiku: dict[str, object] = {"model": "claude-haiku", "system": "Be brief."}
    sonnet: dict[str, object] = {"model": "claude-sonnet", "system": "Be brief."}
    dh, ds = setup_digest_of(haiku), setup_digest_of(sonnet)
    one = episode_setup([dh], "a" * 40)
    two = episode_setup([ds, dh], "a" * 40)
    model = RecordedStep(index=0, actor="model")
    writer = RecordingWriter(FileResultStore(tmp_path))
    for at, setup, steps, ident, children in (
        ("01", one, (model,), "1" * 32, (haiku,)),
        ("02", two, (model, replace(model, index=1)), "2" * 32, (sonnet, haiku)),
    ):
        writer.write(recording(PARCEL, setup, "found it", at, steps=steps, id=ident))
        for child in children:
            writer.write(recording(case("where?"), child, "looking", at, episode=ident))
    suite_file(tmp_path)
    a, b = (setup_digest_of(s)[:8] for s in (one, two))
    found = compared(tmp_path, setups=(a, b), show_setup=True)
    [parcel] = [c for c in found.cases if c.kind == "episode"]
    shapes = {s.setup[:8]: (s.calls, s.models) for s in parcel.setups}
    assert shapes == {
        a: ((1,), ("claude-haiku",)),
        b: ((2,), ("claude-haiku", "claude-sonnet")),
    }
    [children] = [k for k in found.setup_keys if k.key == "child_setups"]
    assert children.b is not None
    assert [(c.digest, c.model) for c in children.b.children] == sorted(
        [(dh[:8], "claude-haiku"), (ds[:8], "claude-sonnet")]
    )
    assert main(run(tmp_path, "--setup", a, b, "--show-setup")) == EXIT_OK
    out = capsys.readouterr().out
    assert (
        f"  setup B {b} · model calls per episode: 2 · "
        "models: claude-haiku, claude-sonnet"
    ) in out
    assert f"  setup A {a} · model calls per episode: 1 · models: claude-haiku" in out
    lines = out.splitlines()
    start = lines.index("    child_setups:")
    assert lines[start + 1 : start + 4] == [
        f"      A {dh[:8]} · claude-haiku",
        *sorted(
            [f"      B {dh[:8]} · claude-haiku", f"      B {ds[:8]} · claude-sonnet"]
        ),
    ]
