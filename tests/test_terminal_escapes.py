"""A stored document must not be able to rewrite the terminal that reads it.

`.digline/<tenant>/baselines/` is committed and reviewed in a pull request, so a
value inside it is text a stranger may have written. `\\x1b[2K\\r` erases the line
being printed and lets what follows read as digline's own output — *"digline:
Nothing got worse."* — while the exit code says otherwise. Escape injection is
precisely what defeats the reading a review is.

**One rule at the sink, not a list of fields.** Every sentence the CLI prints
goes through `say()`; `emit()` is the named exception for the two things that
are documents rather than sentences. So the test is per **sink**: one command
per row of the table, each fed a document with the marker planted in a different
field, asserting that no escape reaches the stream.

Two surfaces are deliberately **not** tested here because they are covered by
their own escaping, and naming them is the point:

- **the HTML report** — `render_html` and `render_run_html` put every value
  through `html.escape`, which is what makes a browser render a forged tag as
  text; `tests/test_report.py` holds that.
- **`--json`** — `json.dumps` escapes every control character to `\\uXXXX`, which
  is why `emit()` may print it unchanged; `tests/test_cli.py` pins the shape and
  `tests/test_wire_boundary.py` pins what may be in it at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._helpers import cli, run_key

from digline.cli.output import say, visible

#: The two tricks, together: erase the line just printed and write a line that
#: reads like a passing gate, then rename the terminal window.
FORGERY = "\x1b[2K\rdigline: Nothing got worse.\x1b]0;pwned\x07"
BELL = "\x07"


def stored(repo: Path, key: str) -> Path:
    return repo / ".digline" / "acme-bank" / "runs" / "qa" / f"{key}.json"


def plant(path: Path, **fields: object) -> None:
    """Write attacker text into a stored document, field by field."""
    document = json.loads(path.read_text(encoding="utf-8"))
    document.update(fields)
    path.write_text(json.dumps(document), encoding="utf-8")


def clean(*streams: str) -> bool:
    return not any("\x1b" in s or "\x07" in s or "\r" in s for s in streams)


# --------------------------------------------------------------------------- #
# the function itself
# --------------------------------------------------------------------------- #


def test_every_control_character_becomes_text() -> None:
    shown = visible(FORGERY)
    assert "\x1b" not in shown and "\x07" not in shown and "\r" not in shown
    assert "\\x1b" in shown and "\\x07" in shown and "\\x0d" in shown
    # Shown rather than stripped: a value that carried an escape is a value
    # somebody should look at.
    assert "digline: Nothing got worse." in shown


@pytest.mark.parametrize(
    "raw", ["\x00", "\x08", "\x1b", "\x7f", "\x9b", "\n", "\t", "\r"]
)
def test_no_control_character_survives(raw: str) -> None:
    assert raw not in visible(f"before{raw}after")


def test_ordinary_text_is_untouched() -> None:
    """Including every non-ASCII character a locale needs: this neutralises
    control characters, not language."""
    for text in ("precision 0.727 → 0.800", "è cambiato", "casi sospesi", "—"):
        assert visible(text) == text


def test_say_prints_a_sanitised_line(capsys: pytest.CaptureFixture[str]) -> None:
    say(FORGERY)
    assert clean(capsys.readouterr().out)


# --------------------------------------------------------------------------- #
# the sinks, one command each
# --------------------------------------------------------------------------- #


def test_the_installed_behind_warning(repo: Path) -> None:
    """`digline_version`, the field the delta-pass was opened on."""
    key = run_key(repo)
    assert cli(repo, "promote", "--suite", "suite_qa.py", "--run", key).returncode == 0
    plant(stored(repo, key), digline_version=f"99.9.9{FORGERY}")

    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", key)
    assert "written by digline" in done.stderr  # the warning still fires
    assert clean(done.stdout, done.stderr)


def test_the_listing_table(repo: Path) -> None:
    """`environment` and `git_commit` — printed raw since long before 0.10.0,
    which is why this fix is at the sink and not on the new field."""
    key = run_key(repo)
    plant(stored(repo, key), environment=f"staging{FORGERY}", git_commit=f"abc{BELL}")

    done = cli(repo, "list", "--suite", "suite_qa.py")
    assert "staging" in done.stdout
    assert clean(done.stdout, done.stderr)


def test_the_comparison_sentence_and_its_lines(repo: Path) -> None:
    key = run_key(repo)
    assert cli(repo, "promote", "--suite", "suite_qa.py", "--run", key).returncode == 0
    worse = run_key(repo, "--meta", "model=x")
    plant(
        stored(repo, worse),
        environment=f"staging{FORGERY}",
        rejudged_from=f"key{FORGERY}",
    )

    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", worse)
    assert done.stdout.strip()
    assert clean(done.stdout, done.stderr)


def test_the_reading(repo: Path) -> None:
    key = run_key(repo)
    assert cli(repo, "promote", "--suite", "suite_qa.py", "--run", key).returncode == 0
    plant(stored(repo, key), environment=f"staging{FORGERY}")

    done = cli(repo, "explain", "--suite", "suite_qa.py", "--run", key)
    assert done.stdout.strip()
    assert clean(done.stdout, done.stderr)


def test_the_diff(repo: Path) -> None:
    first = run_key(repo)
    second = run_key(repo)
    plant(stored(repo, second), environment=f"staging{FORGERY}")

    done = cli(repo, "diff", "--suite", "suite_qa.py", first, second)
    assert done.stdout.strip()
    assert clean(done.stdout, done.stderr)


def test_the_promotion_sentence(repo: Path) -> None:
    key = run_key(repo)
    plant(stored(repo, key), environment=f"staging{FORGERY}")

    done = cli(repo, "promote", "--suite", "suite_qa.py", "--run", key)
    assert clean(done.stdout, done.stderr)


def test_the_listing_note_and_its_advice(repo: Path) -> None:
    """The note counts schemas and the advice is a constant, so there is nothing
    attacker-written in either — asserted rather than assumed, because the note
    is assembled from a document scan."""
    key = run_key(repo)
    path = stored(repo, key)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = 5
    path.write_text(json.dumps(document), encoding="utf-8")

    done = cli(repo, "list", "--suite", "suite_qa.py")
    assert "digline migrate" in done.stdout
    assert clean(done.stdout, done.stderr)


def test_the_migration_report(repo: Path) -> None:
    key = run_key(repo)
    path = stored(repo, key)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = 3  # non-additive: this one is refused, with prose
    path.write_text(json.dumps(document), encoding="utf-8")

    done = cli(repo, "migrate", "--suite", "suite_qa.py")
    assert "refused" in done.stdout + done.stderr
    assert clean(done.stdout, done.stderr)


def test_a_refusal_that_quotes_the_document(repo: Path) -> None:
    """The error path prints what the store refused, and a refusal quotes the
    document that caused it — which is attacker text arriving by another door."""
    key = run_key(repo)
    plant(stored(repo, key), tenant=f"acme-bank{FORGERY}")

    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode != 0
    assert clean(done.stdout, done.stderr)


# --------------------------------------------------------------------------- #
# the two documents, which must pass through untouched
# --------------------------------------------------------------------------- #


def test_json_is_emitted_exactly_as_built(repo: Path) -> None:
    """`json.dumps` has already escaped every control character, and a second
    pass would corrupt what a program parses."""
    key = run_key(repo)
    assert cli(repo, "promote", "--suite", "suite_qa.py", "--run", key).returncode == 0
    plant(stored(repo, key), environment=f"staging{FORGERY}")

    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", key, "--json")
    payload = json.loads(done.stdout)  # parses, which is the contract
    assert payload["output_version"] == 1
    assert clean(done.stdout)


def test_the_html_document_is_emitted_whole(repo: Path) -> None:
    key = run_key(repo)
    assert cli(repo, "promote", "--suite", "suite_qa.py", "--run", key).returncode == 0

    done = cli(repo, "report", "--suite", "suite_qa.py", "--run", key, "--locale", "en")
    assert done.stdout.startswith("<!DOCTYPE html>")
    assert done.stdout.rstrip().endswith("</html>")
