"""The recording as a public contract: what a writer in another language must
produce and what every reader holds it to. (ADR 0062 §2)

What is held here:

- a float enters the setup's digest as text, in the form Java writes from the
  same double, pinned value by value and on one whole digest;
- `recorded_at` has one form, UTC written with `+00:00`, and any other is
  refused by name, on write and on read;
- the import compares `recorded_at` as instants: one instant written with
  three digits of fraction and with six is not *after* itself, and on a tie
  the setup in force is the later file's;
- the `label` compartment is gone, and a document written with one is still
  read, the key ignored;
- `digline record status` says *not counted* of a process that wrote
  recordings and keeps no counts file, as a writer outside digline does;
- the page's smallest recording reads back as written, with its digest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tests.test_recorder_import import (
    A_NEW,
    A_OLD,
    S1,
    S2,
    A,
    argv,
    listed,
    loaded,
    recording,
    suite_file,
)

from digline.cli.main import main
from digline.core.recording import (
    RecordingRefusedError,
    float_text,
    input_of,
    instant_of,
    recording_from_dict,
    recording_to_dict,
    setup_digest_of,
)
from digline.host import answer_id, imported_since, recorder_status
from digline.store.file_store import COUNTS_FILENAME, FileResultStore, RecordingWriter
from digline.wire.recorder import recorder_status_json

# -- a float in the digest ---------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "text"),
    [
        # Each beside what Java's `Double.toString` writes for it, measured
        # with JDK 21: the text Java and Python write differs, the form agrees.
        (0.7, "0.7"),  # Java 0.7
        (1e-05, "0.00001"),  # Java 1.0E-5
        (100.0, "100"),  # Java 100.0
        (1e16, "10000000000000000"),  # Java 1.0E16
        (0.1 + 0.2, "0.30000000000000004"),  # Java 0.30000000000000004
        (-2.5, "-2.5"),  # Java -2.5
        (123456789.125, "123456789.125"),  # Java 1.23456789125E8
        (0.0, "0"),  # Java 0.0
        (-0.0, "0"),  # Java -0.0, which BigDecimal has no sign for
    ],
)
def test_a_float_is_written_in_the_form_both_languages_write(
    value: float, text: str
) -> None:
    assert float_text(value) == text


def test_the_digest_is_taken_of_the_floats_as_text() -> None:
    setup: dict[str, object] = {
        "model": "m",
        "max_tokens": 200,
        "temperature": 0.7,
        "top_p": 1e-05,
        "stop": [".", 1.5],
        "stream": False,
    }
    # The payload a writer in any language hashes, written out by hand.
    payload = (
        '{"max_tokens":200,"model":"m","stop":[".","1.5"],"stream":false,'
        '"temperature":"0.7","top_p":"0.00001"}'
    )
    assert setup_digest_of(setup) == hashlib.sha256(payload.encode()).hexdigest()[:16]


def test_an_integer_and_a_boolean_are_not_floats() -> None:
    assert setup_digest_of({"n": 1}) != setup_digest_of({"n": 1.0})
    assert setup_digest_of({"n": True}) != setup_digest_of({"n": 1})


# -- recorded_at -------------------------------------------------------------- #


@pytest.mark.parametrize(
    "written",
    [
        "2026-11-04T08:00:00Z",  # what Java's Instant.toString writes
        "2026-11-04T10:00:00+02:00",
        "2026-11-04T08:00:00",
        "2026-11-04 08:00:00+00:00",
        "2026-11-04T08:00:00.1234567+00:00",
        "2026-13-04T08:00:00+00:00",
    ],
)
def test_recorded_at_in_another_form_is_refused_by_name(written: str) -> None:
    with pytest.raises(RecordingRefusedError, match=r"recorded_at .*\+00:00"):
        recording(A, S1, A_OLD, "01", recorded_at=written)
    document = recording_to_dict(recording(A, S1, A_OLD, "01"))
    document["recorded_at"] = written
    with pytest.raises(RecordingRefusedError, match=r"recorded_at .*\+00:00"):
        recording_from_dict(document)


@pytest.mark.parametrize(
    "written",
    [
        "2026-11-04T08:00:00+00:00",
        "2026-11-04T08:00:00.1+00:00",
        "2026-11-04T08:00:00.123456+00:00",
    ],
)
def test_recorded_at_in_the_form_is_read(written: str) -> None:
    document = recording_to_dict(recording(A, S1, A_OLD, "01", recorded_at=written))
    assert recording_from_dict(document).recorded_at == written


def test_one_instant_has_one_key_whatever_its_fraction() -> None:
    assert instant_of("2026-11-04T08:00:00.100+00:00") == instant_of(
        "2026-11-04T08:00:00.100000+00:00"
    )
    assert instant_of("2026-11-04T08:00:00+00:00") == instant_of(
        "2026-11-04T08:00:00.000000+00:00"
    )
    assert instant_of("2026-11-04T08:00:00.9+00:00") < instant_of(
        "2026-11-04T08:00:01+00:00"
    )


def test_the_import_reads_a_watermark_as_an_instant(tmp_path: Path) -> None:
    # A writer that keeps milliseconds files a recording; the import names
    # it and writes its recorded_at as the watermark.
    writer = RecordingWriter(FileResultStore(tmp_path))
    at = "2026-11-03T08:00:00.100+00:00"
    writer.write(recording(A, S1, A_OLD, "01", recorded_at=at))
    suite_file(tmp_path)
    assert main(argv(tmp_path, "--good", answer_id(A, A_OLD), "--by", "Ada")) == 0
    # Python then files the same answer at the same instant, as it writes it.
    writer.write(
        recording(A, S1, A_OLD, "01", recorded_at="2026-11-03T08:00:00.100000+00:00")
    )
    suite, module = loaded(tmp_path)
    # Not after the watermark: the same instant. As text it would be one.
    assert imported_since(tmp_path, suite, module, "acme") == (0, 2)


def test_the_setup_in_force_is_read_by_instant_the_later_file_on_a_tie(
    tmp_path: Path,
) -> None:
    # One instant, two setups, written by two writers in two forms: the later
    # file wins, as it does where nothing is dated. As text, the six digits
    # would be the newer.
    writer = RecordingWriter(FileResultStore(tmp_path))
    at = "2026-11-03T08:00:00.100"
    writer.write(recording(A, S2, A_NEW, "01", recorded_at=at + "000+00:00"))
    writer.write(recording(A, S1, A_OLD, "01", recorded_at=at + "+00:00"))
    suite_file(tmp_path)
    assert listed(tmp_path).setup == S1


# -- label -------------------------------------------------------------------- #


def test_a_recording_has_no_label_and_one_written_with_it_is_still_read() -> None:
    written = recording_to_dict(recording(A, S1, A_OLD, "01"))
    assert "label" not in written
    with pytest.raises(TypeError, match="label"):
        recording(A, S1, A_OLD, "01", label="positive")
    read = recording_from_dict({**written, "label": "positive"})
    assert recording_to_dict(read) == written


# -- the counts file ---------------------------------------------------------- #


def test_a_process_with_no_counts_file_is_not_counted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    writer = RecordingWriter(FileResultStore(tmp_path))
    writer.write(recording(A, S1, A_OLD, "01"))
    [tenant] = recorder_status(tmp_path, "acme")
    assert tenant.uncounted == 1
    document = recorder_status_json([tenant])
    assert (
        json.loads(json.dumps(document))["tenants"][0]["recordings"]["uncounted"] == 1
    )
    assert main(["record", "status", "--tenant", "acme", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert (
        "  not counted: 1 process keeps recordings and no counts, so what was "
        "not recorded there is not known"
    ) in out

    (writer.place("acme") / COUNTS_FILENAME).write_text(
        json.dumps({"pid": 1, "suites": {}}), encoding="utf-8"
    )
    [tenant] = recorder_status(tmp_path, "acme")
    assert tenant.uncounted == 0
    assert main(["record", "status", "--tenant", "acme", "--root", str(tmp_path)]) == 0
    assert "not counted" not in capsys.readouterr().out


# -- the page ----------------------------------------------------------------- #


def test_the_pages_smallest_recording_is_read_as_it_is_written() -> None:
    """`docs/recording-format.md` shows what a writer must produce. Held here,
    so the example cannot drift from what the reader reads and the digest it
    shows from the one digline computes."""
    page = Path(__file__).parents[1] / "docs" / "recording-format.md"
    text = page.read_text(encoding="utf-8")
    block = text.split("```json\n", 1)[1].split("```", 1)[0]
    document = json.loads(block)
    read = recording_from_dict(document)
    assert read.setup_digest == setup_digest_of(read.setup)
    assert read.response.input == input_of(document["case"]["messages"])
    assert recording_to_dict(read) == document
