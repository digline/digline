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
- **`--json`** — `json.dumps` escapes C0 to `\\uXXXX` and does **not** escape
  DEL or C1 under `ensure_ascii=False`, so `emit()` escapes those two itself; the
  last section of this file holds that, `tests/test_cli.py` pins the shape and
  `tests/test_wire_boundary.py` pins what may be in it at all. The premise that
  `json.dumps` escapes *every* control character was false until 0.13.1.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from tests._helpers import cli, run_key

from digline.cli.output import say, visible
from digline.core import json_visible
from digline.wire import OUTPUT_VERSION

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


def test_the_html_document_carries_no_control_character_to_a_terminal() -> None:
    """`digline report` with no `--out` prints the document to stdout.

    0.10.1 closed the escape sink at `say()` and left `emit()` out, on the
    ground that the report's values are "already HTML-escaped where they are
    rendered". They are — and `html.escape` covers `& < > " '`, which does
    nothing whatever to `0x1b`. A judge's `reason` quotes what a model wrote,
    so an erase-line sequence in an answer forged a line over the one above it
    in a reader's terminal while the run was red.

    The fix is in the escaping rather than in a tty check: C0, DEL and C1 become
    numeric character references, so the bytes are terminal-safe and a browser
    still resolves them to the inert characters the model actually sent. One
    document, whether it is piped to a file or read on a screen.
    (0.12.1, from the release delta-pass)
    """
    from digline.report import escape

    forged = (
        "the answer was poor.\x1b[31m\x1b[2K\rdigline: Nothing got worse."
        "\x1b]8;;http://evil.example\x07CLICK\x1b]8;;\x07\x00"
    )
    shown = escape(forged)
    assert clean(shown), shown
    assert "\x00" not in shown
    # Neutralised, not deleted: the document still says what the model said.
    assert "&#x1b;" in shown and "&#x07;" in shown and "&#x00;" in shown
    assert "digline: Nothing got worse." in shown
    # And the ordinary HTML escaping is still doing its own job.
    assert escape("<b>&</b>") == "&lt;b&gt;&amp;&lt;/b&gt;"


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
    """`json.dumps` has already escaped the C0 characters, and a second pass over
    those would corrupt what a program parses. DEL and C1 are the two it leaves
    raw, which the section below holds."""
    key = run_key(repo)
    assert cli(repo, "promote", "--suite", "suite_qa.py", "--run", key).returncode == 0
    plant(stored(repo, key), environment=f"staging{FORGERY}")

    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", key, "--json")
    payload = json.loads(done.stdout)  # parses, which is the contract
    assert payload["output_version"] == OUTPUT_VERSION
    assert clean(done.stdout)


def test_the_html_document_is_emitted_whole(repo: Path) -> None:
    key = run_key(repo)
    assert cli(repo, "promote", "--suite", "suite_qa.py", "--run", key).returncode == 0

    done = cli(repo, "report", "--suite", "suite_qa.py", "--run", key, "--locale", "en")
    assert done.stdout.startswith("<!DOCTYPE html>")
    assert done.stdout.rstrip().endswith("</html>")


# --------------------------------------------------------------------------- #
# DEL and C1, which `json.dumps` does not escape (0.13.1)
# --------------------------------------------------------------------------- #

#: U+009B is CSI on its own: one character that opens the same escape sequence
#: `\x1b[` does, on every terminal that honours 8-bit controls.
C1_FORGERY = "prod\x9b2K\rdigline: Nothing got worse.\x7f\x85"


def raw_del_or_c1(stream: str) -> list[str]:
    return [f"U+{ord(ch):04X}" for ch in stream if 0x7F <= ord(ch) <= 0x9F]


def test_the_register_reaches_log_json_without_a_raw_c1(repo: Path) -> None:
    """The register is committed, so a pull request writes its strings — and
    `log --json` printed a C1 CSI from one straight to the terminal. In 0.13.0
    `emit()` believed `json.dumps` escapes every control character; it escapes
    C0 and leaves DEL and C1 raw.

    **What the parsed value is changed in 0.15.1, and this is where that is
    pinned.** It used to be exactly what the file holds, because `emit()` escaped
    the *serialised text* and a parser read the raw character straight back. That
    only ever worked for this front end: `digline-mcp` hands dictionaries to an
    SDK that serialises them itself, so the rule had to move to the **value**, in
    `digline.wire`, where both front ends inherit it. A reader therefore gets the
    escape spelling — six characters where the file holds one — which is the cost
    `OUTPUT_VERSION` 2 declares. Escaped, still never stripped: what the file
    held stays legible in what the reader gets."""
    key = run_key(repo)
    assert cli(repo, "promote", "--suite", "suite_qa.py", "--run", key).returncode == 0
    recorded = cli(
        repo,
        "register",
        "--suite",
        "suite_qa.py",
        "--run",
        key,
        "--disposition",
        "rejected",
    )
    assert recorded.returncode == 0, recorded.stderr
    path = repo / ".digline" / "acme-bank" / "register" / "qa.jsonl"
    entry = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    entry["run"]["environment"] = C1_FORGERY
    path.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")

    done = cli(repo, "log", "--suite", "suite_qa.py", "--json")
    assert done.returncode == 0, done.stderr
    assert raw_del_or_c1(done.stdout) == []
    (shown,) = json.loads(done.stdout)["register"]
    assert shown["run"]["environment"] == json_visible(C1_FORGERY)
    # The C0 half is untouched by the wire and still arrives raw through the
    # parser, exactly as before: `json.dumps` escapes it on the way out, so it
    # was never the hole. Only DEL and C1 changed hands.
    assert "\r" in shown["run"]["environment"]


def test_emit_escapes_del_and_c1_and_a_parser_reads_the_same_document(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """At the sink, so the next `--json` command inherits it without anyone
    remembering to. Every C1 character and DEL, not a list of the dangerous
    ones: the list is what goes stale."""
    from digline.cli.output import emit

    value = {"every": "".join(chr(code) for code in (0x7F, *range(0x80, 0xA0)))}
    emit(json.dumps(value, ensure_ascii=False))
    printed = capsys.readouterr().out
    assert raw_del_or_c1(printed) == []
    assert json.loads(printed) == value


def test_nothing_in_the_cli_prints_except_through_say_or_emit() -> None:
    """The standing rule, enforced where it can be: **every** byte `digline.cli`
    puts on a terminal leaves through `output.say()` or `output.emit()`, so a new
    source of third-party text is sanitised by construction rather than by
    somebody remembering. This is the third time the family bit — 0.10.1 at
    `say()`, 0.12.1 at the HTML `emit()`, 0.13.1 at the JSON one — and each time
    the hole was a door the rule had not been written on."""
    import ast

    from digline import cli as package

    offenders: list[str] = []
    for source in sorted(Path(package.__file__).parent.glob("*.py")):
        if source.name == "output.py":
            continue
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                called = node.func
                name = (
                    called.id
                    if isinstance(called, ast.Name)
                    else f"{ast.unparse(called)}"
                    if isinstance(called, ast.Attribute)
                    else ""
                )
                if name in {"print", "sys.stdout.write", "sys.stderr.write"}:
                    offenders.append(f"{source.name}:{node.lineno} {name}(...)")
    assert offenders == [], (
        "these write to a terminal without going through digline.cli.output: "
        + ", ".join(offenders)
    )


# --------------------------------------------------------------------------- #
# The rule, widened past `digline.cli` (from the release delta-pass over 0.15.0)
# --------------------------------------------------------------------------- #
#
# The test above walks `digline.cli` for a direct terminal write, and it would
# not have caught the hole this section exists for. `digline-mcp` never calls
# `print`: it returns dictionaries and an SDK serialises them, so a tool name
# carrying U+009B left on the wire raw with no `print` anywhere near it. An AST
# scan is blind to that by construction, which is why the rule now has two halves
# and why the second one is the one that matters.


#: Every front end, and the module in each that is allowed to write.
FRONT_ENDS: tuple[tuple[str, str | None], ...] = (
    ("digline.cli", "output.py"),
    ("digline_mcp", None),
    ("pytest_digline", None),
)


@pytest.mark.parametrize(("module", "sanitiser"), FRONT_ENDS)
def test_no_front_end_writes_to_a_terminal_except_through_the_sanitiser(
    module: str, sanitiser: str | None
) -> None:
    """Half one, widened: the `print` scan, over **every** front end.

    `digline.cli` had this to itself, and the reason it needed company is in the
    section comment above: the rule was kept in the front end that happened to be
    written first, so the second one inherited nothing. A front end may not import
    another, so the escaping now lives in `digline.core` and `digline.wire`, and
    this holds the other end of it.
    """
    import ast
    import importlib

    package = importlib.import_module(module)
    # `__path__` rather than `__file__`: a namespace package has no `__file__`,
    # and `digline_mcp` is one in this workspace.
    roots = [Path(entry) for entry in package.__path__]
    assert roots, f"{module} has no importable directory"
    sources = sorted({s for root in roots for s in root.glob("*.py")})
    offenders: list[str] = []
    for source in sources:
        if sanitiser is not None and source.name == sanitiser:
            continue
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            name = (
                called.id
                if isinstance(called, ast.Name)
                else ast.unparse(called)
                if isinstance(called, ast.Attribute)
                else ""
            )
            if name not in {"print", "sys.stdout.write", "sys.stderr.write"}:
                continue
            # A write is fine where what it writes has already been through the
            # sanitiser: the rule is that nothing reaches a terminal unescaped,
            # not that nothing is ever printed.
            if "visible(" in ast.unparse(node):
                continue
            offenders.append(f"{module}/{source.name}:{node.lineno} {name}(...)")
    assert offenders == [], (
        f"these write to a terminal without going through a sanitiser: "
        f"{', '.join(offenders)}"
    )


def test_the_wire_neutralises_del_and_c1_for_every_front_end() -> None:
    """Half two, and the half that would have caught the hole.

    Not an AST scan but the bytes themselves, because the failure it guards has
    no `print` in it: `digline-mcp` hands a dictionary to an SDK, the SDK
    serialises with pydantic, and pydantic writes DEL and C1 raw exactly as
    `json.dumps` does under `ensure_ascii=False`. The only defence both front
    ends can share is the value, so the value is what this checks.

    Driven through the real serialisers — `json.dumps` for `--json`, pydantic's
    for MCP — rather than through a description of them, and with the control
    that must fail: the same document without the wire's pass **must** carry the
    raw bytes, or this test is asserting nothing.
    """
    from pydantic import BaseModel

    from digline.wire.text import neutralised

    hostile = "".join(chr(code) for code in (0x7F, *range(0x80, 0xA0)))
    document: dict[str, object] = {
        "called": [hostile],
        "tool": hostile,
        hostile: "a key, too",
    }

    class Wire(BaseModel):
        called: list[str]
        tool: str

    safe = neutralised(document)

    # `--json`: what `json.dumps` writes, before `emit()` gets its second pass.
    assert raw_del_or_c1(json.dumps(safe, ensure_ascii=False)) == []
    # MCP: what the SDK's serialiser writes, which digline never touches.
    called = cast("list[str]", safe["called"])
    served = Wire(called=called, tool=cast("str", safe["tool"])).model_dump_json()
    assert raw_del_or_c1(served) == []
    # Keys as well as values.
    assert raw_del_or_c1("".join(safe)) == []

    # The control that must fail.
    unsafe = Wire(called=[hostile], tool=hostile).model_dump_json()
    assert raw_del_or_c1(unsafe) != [], (
        "the serialiser escaped these on its own, so this test proves nothing"
    )

    # Both front ends read one value, which is the reason the rule sits in wire.
    assert (
        json.loads(json.dumps(safe, ensure_ascii=False))["tool"]
        == (json.loads(served)["tool"])
    )
