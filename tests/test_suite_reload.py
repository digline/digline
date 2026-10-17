"""A suite loaded again reads its application again (ADR 0052, #513).

Three facts, tested here in the order the record gives them:

1. what digline put in place for a suite's scope is taken out before the next
   load, every row of the record's table;
2. a name already loaded from an origin digline did not load is named,
   `modules_unchecked`: by name on the run, the wire and the terminal, by count
   in the page, and it moves no number;
3. the comparison's headline reads it from the judged run alone, count or *not
   recorded*, and moves no number.

And the field's schema: it migrates additively to *not recorded*, which is never
read as zero, and it stays out of `config_hash`.

The three manifestations the record measured through `digline-mcp`, (a), (b)
and (c), are in `packages/digline-mcp/tests/test_reload.py`, through the server.

These tests load suites in this process, so every one of them runs inside
`process_state`, which puts back what a load changes: `sys.modules`, `sys.path`,
`sys.path_hooks`, `sys.path_importer_cache` and the loader's `_scoped`.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from digline.core import NOTHING_EXTRA, CaseResult, Run, Score, Verdict, compare, redact
from digline.core.run import SCHEMA_VERSION, run_from_dict, run_to_dict
from digline.host import load_suite, load_target
from digline.host import loader as loader_module
from digline.report import headline, module_lines, phrase, render_html
from digline.store.migrate import upgrade_document
from digline.wire import compare_json, exit_code
from digline.wire.run import run_document

# By name: `digline.cli` re-exports `main` the function over the module.
cli_main = importlib.import_module("digline.cli.main")

SUITE = """import brief
{extra}
from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="probe",
    environment="probe",
    name="{name}",
    assertions=[Contains(needle="answer")],
    cases=[Case(id="c1")],
)


def target(case):
    return Response(output=brief.reply(case.id), cost_usd=0.0, latency_ms=1.0)
"""

PLAIN_SUITE = """from digline.core import Contains
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="probe",
    environment="probe",
    name="{name}",
    assertions=[Contains(needle="answer")],
    cases=[Case(id="c1")],
)


def target(case):
    return Response(output="answer", cost_usd=0.0, latency_ms=1.0)
"""

BRIEF = """def reply(case_id):
    return "{text} to " + case_id
"""


@pytest.fixture
def process_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Put back what loading a suite changes in this process.

    `sys.path`, `sys.path_hooks` and `sys.path_importer_cache` are read by the
    import system from `sys` each time, so a copy set for the test and dropped
    after it is enough. `sys.modules` cannot be replaced, so the names a test
    added are deleted and the ones it replaced are put back.
    """
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "path_hooks", list(sys.path_hooks))
    monkeypatch.setattr(sys, "path_importer_cache", dict(sys.path_importer_cache))
    monkeypatch.setattr(
        loader_module,
        "_scoped",
        set(loader_module._scoped),  # pyright: ignore[reportPrivateUsage]
    )
    modules = dict(sys.modules)
    yield
    for name in [name for name in sys.modules if name not in modules]:
        del sys.modules[name]
    for name, module in modules.items():
        sys.modules[name] = module


def a_suite(
    root: Path,
    directory: str,
    *,
    stem: str = "suite",
    name: str = "probe",
    brief: str | None = "answer from {directory}",
    extra: str = "",
) -> Path:
    """A suite in `root/directory`, importing `brief` from beside it when
    `brief` is given, and returning `brief.reply(case.id)` from its target."""
    where = root / directory
    where.mkdir(parents=True, exist_ok=True)
    if brief is None:
        source = PLAIN_SUITE.format(name=name)
    else:
        source = SUITE.format(name=name, extra=extra)
        (where / "brief.py").write_text(
            BRIEF.format(text=brief.format(directory=directory)), encoding="utf-8"
        )
    path = where / f"{stem}.py"
    path.write_text(source, encoding="utf-8")
    return path


def answer(path: Path) -> str:
    """What the target of the suite at `path` answers, loaded now."""
    suite, loaded = load_suite(str(path))
    target = load_target(None, loaded, str(path))
    return target(suite.cases[0]).output  # pyright: ignore[reportReturnType]


# --------------------------------------------------------------------------- #
# Fact 1: what digline put in place for a suite's scope is taken out
# --------------------------------------------------------------------------- #


@pytest.mark.usefixtures("process_state")
def test_an_application_module_of_an_earlier_load_is_unloaded(tmp_path: Path) -> None:
    """The second row of the record's table: every module the suite imported
    that resolved in its directory. Not removed, the next load of a suite that
    imports the same name is answered from `sys.modules` (ADR 0052, (a), (b))."""
    first = a_suite(tmp_path, "one")
    second = a_suite(tmp_path, "two", brief=None)
    answer(first)
    assert "brief" in sys.modules
    load_suite(str(second))
    assert "brief" not in sys.modules, (
        "the application module `brief`, loaded for the suite in one/, is still "
        "in sys.modules after the next load: a later suite importing `brief` is "
        "answered with one/'s copy (ADR 0052, decision 1)"
    )


@pytest.mark.usefixtures("process_state")
def test_the_suite_module_of_an_earlier_load_is_unloaded(tmp_path: Path) -> None:
    """The first row: the suite's own module, `_digline_suite_<stem>`."""
    first = a_suite(tmp_path, "one", stem="alpha", brief=None)
    second = a_suite(tmp_path, "two", stem="beta", brief=None)
    load_suite(str(first))
    load_suite(str(second))
    assert "_digline_suite_alpha" not in sys.modules, (
        "`_digline_suite_alpha` is still in sys.modules after beta.py was "
        "loaded (ADR 0052, decision 1)"
    )


@pytest.mark.usefixtures("process_state")
def test_an_earlier_suite_directory_leaves_sys_path(tmp_path: Path) -> None:
    """The third row. Left in place, a name only that directory holds is found
    there by a later suite: (c) in the record."""
    first = a_suite(tmp_path, "one", brief=None)
    second = a_suite(tmp_path, "two", brief=None)
    load_suite(str(first))
    load_suite(str(second))
    assert str(first.parent) not in sys.path, (
        f"{first.parent} is still on sys.path after the next load (ADR 0052, "
        "decision 1)"
    )


@pytest.mark.usefixtures("process_state")
def test_an_earlier_suite_directory_hook_is_removed(tmp_path: Path) -> None:
    """The fourth row: one path hook per scoped directory. After two loads in
    two directories, one hook of digline's remains, the second's."""
    hooks = list(sys.path_hooks)
    load_suite(str(a_suite(tmp_path, "one", brief=None)))
    load_suite(str(a_suite(tmp_path, "two", brief=None)))
    added = [hook for hook in sys.path_hooks if hook not in hooks]
    assert len(added) == 1, (
        f"{len(added)} path hooks of digline's after two loads, not 1: the "
        "earlier directory's hook was not taken out (ADR 0052, decision 1)"
    )


@pytest.mark.usefixtures("process_state")
def test_an_earlier_suite_directory_leaves_the_importer_cache(tmp_path: Path) -> None:
    """The fifth row: the finder digline put in `sys.path_importer_cache`."""
    first = a_suite(tmp_path, "one", brief=None)
    load_suite(str(first))
    load_suite(str(a_suite(tmp_path, "two", brief=None)))
    assert str(first.parent) not in sys.path_importer_cache, (
        f"{first.parent} still has digline's finder in sys.path_importer_cache "
        "after the next load (ADR 0052, decision 1)"
    )


@pytest.mark.usefixtures("process_state")
def test_an_earlier_suite_directory_leaves_scoped(tmp_path: Path) -> None:
    """The sixth row: the loader's own record of the directories it scoped."""
    first = a_suite(tmp_path, "one", brief=None)
    load_suite(str(first))
    load_suite(str(a_suite(tmp_path, "two", brief=None)))
    scoped = loader_module._scoped  # pyright: ignore[reportPrivateUsage]
    assert os.path.realpath(first.parent) not in scoped, (
        f"{first.parent} is still in the loader's _scoped after the next load "
        "(ADR 0052, decision 1)"
    )


@pytest.mark.usefixtures("process_state")
def test_the_standard_library_and_third_parties_are_not_touched(tmp_path: Path) -> None:
    """The boundary: digline takes out what it put there for the suite's scope,
    and nothing else. A standard-library module and a third-party one the suite
    imported stay, as the same objects."""
    first = a_suite(tmp_path, "one", extra="import colorsys\nimport pytest")
    answer(first)
    stdlib, third_party = sys.modules["colorsys"], sys.modules["pytest"]
    load_suite(str(a_suite(tmp_path, "two", brief=None)))
    assert sys.modules.get("colorsys") is stdlib
    assert sys.modules.get("pytest") is third_party


# --------------------------------------------------------------------------- #
# Fact 2: a name already loaded from elsewhere is named, `modules_unchecked`
# --------------------------------------------------------------------------- #


def preload_brief(root: Path) -> None:
    """Put a module named `brief` in `sys.modules` from a directory digline
    never scoped, the way a test module importing the application would."""
    where = root / "elsewhere"
    where.mkdir()
    path = where / "brief.py"
    path.write_text(BRIEF.format(text="answer from elsewhere"), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("brief", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["brief"] = module


@pytest.mark.usefixtures("process_state")
def test_a_name_loaded_from_elsewhere_is_named_and_the_run_goes_on(
    tmp_path: Path,
) -> None:
    """`brief` is in `sys.modules` from a directory digline did not scope, and
    the suite's directory holds a `brief.py` it would have read. Named, not
    refused: the target still answers. The standard library and a third party
    the suite imports are never in the list (ADR 0052, decision 2)."""
    preload_brief(tmp_path)
    path = a_suite(tmp_path, "suite", extra="import json\nimport pytest")
    suite, loaded = load_suite(str(path))
    target = load_target(None, loaded, str(path))
    assert target(suite.cases[0]).output == "answer from elsewhere to c1"
    assert loaded.modules_unchecked == ("brief",), (
        "a name already loaded from elsewhere was not named"
    )


def a_run(
    modules_unchecked: tuple[str, ...] | None = (), *, judged: bool = True
) -> Run:
    """A run with one judged case, carrying `modules_unchecked` as given."""
    verdict = Verdict(
        score=Score(name="contains", score=1.0 if judged else 0.0),
        threshold=1.0,
        status="pass" if judged else "fail",
        reason="found",
        assertion_id="contains-1",
    )
    return Run(
        tenant="probe",
        environment="probe",
        suite="probe",
        config_hash="h",
        created_at="2026-10-17T10:00:00+00:00",
        results=(CaseResult("c1", (verdict,)),),
        modules_unchecked=modules_unchecked,
    )


def test_the_run_carries_the_names_on_the_wire_and_redaction_keeps_them() -> None:
    """Names and count cross, and `redact()` drops neither: the names come from
    the perimeter artifact and pinned paths already cross from (ADR 0052, the
    field on the run, condition 3)."""
    run = a_run(("brief", "helper"))
    assert run_document(run, NOTHING_EXTRA)["modules_unchecked"] == ["brief", "helper"]
    assert run_document(redact(run), NOTHING_EXTRA)["modules_unchecked"] == [
        "brief",
        "helper",
    ], "redact() dropped the names of the modules nobody read"


def test_the_names_reach_the_terminal_and_the_run_document_and_the_page_counts() -> (
    None
):
    """The names where the pin markers are, on the terminal, and in the run
    document; the page carries the count and never a name, by its rule that a
    path is never named there (`report/render.py`, `_artifacts`)."""
    run, baseline = a_run(("brief",)), a_run(())
    lines = module_lines(run, locale="en")
    assert lines == (f"brief · {phrase('en', 'modules_unchecked.marker')}",), (
        f"the terminal lines are {lines!r}: the module nobody read is not named "
        "where the pin markers are"
    )
    assert run_document(run, NOTHING_EXTRA)["modules_unchecked"] == ["brief"]
    page = render_html(
        compare(run, baseline), run, baseline, locale="en", declared=None
    )
    assert phrase("en", "fact.modules_unchecked.one", count=1) in page, (
        "the page does not count the module nobody read"
    )
    assert "brief" not in page, "the page names a module, where it carries a count"


@pytest.mark.usefixtures("process_state")
def test_digline_compare_names_on_the_terminal_what_digline_run_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Through the command a person runs, in this process: `run` records what
    the loader found, and `compare` says the count in its sentence and the name
    on its own line."""
    preload_brief(tmp_path)
    path = a_suite(tmp_path, "project")
    monkeypatch.chdir(path.parent)
    suite = ("--suite", path.name)
    assert cli_main.main(["run", *suite]) == 0
    key = capsys.readouterr().out.strip()
    assert cli_main.main(["promote", *suite, "--run", key, "--replacing", "none"]) == 0
    assert cli_main.main(["run", *suite]) == 0
    capsys.readouterr()
    assert cli_main.main(["compare", *suite, "--run", "latest"]) == 0
    out = capsys.readouterr().out
    assert phrase("en", "fact.modules_unchecked.one", count=1) in out
    assert f"brief · {phrase('en', 'modules_unchecked.marker')}" in out, (
        f"`digline compare` did not name the module on the terminal:\n{out}"
    )


# --------------------------------------------------------------------------- #
# Fact 3: the headline reads it from the judged run, and moves no number
# --------------------------------------------------------------------------- #


def test_the_headline_says_it_when_the_judged_run_declares_it() -> None:
    run, baseline = a_run(("brief",)), a_run(())
    head = headline(compare(run, baseline), run, baseline, locale="en", declared=None)
    assert head.modules_unchecked == 1
    for locale in ("en", "it"):
        clause = phrase(locale, "fact.modules_unchecked.one", count=1)
        said = headline(
            compare(run, baseline), run, baseline, locale=locale, declared=None
        )
        assert clause in said.sentence
    assert exit_code(head) == 0, "a module nobody read moved the exit code"


def test_the_headline_plural_names_the_count() -> None:
    run, baseline = a_run(("brief", "helper")), a_run(())
    head = headline(compare(run, baseline), run, baseline, locale="en", declared=None)
    assert phrase("en", "fact.modules_unchecked.many", count=2) in head.sentence


def test_the_reference_value_is_not_read() -> None:
    """Only the judged run is read, as pins are (ADR 0052, decision 3)."""
    run, baseline = a_run(()), a_run(("brief",))
    head = headline(compare(run, baseline), run, baseline, locale="en", declared=None)
    assert head.modules_unchecked == 0, (
        "the headline read the reference's modules_unchecked"
    )
    assert "brief" not in head.sentence


def test_a_judged_run_not_recorded_is_said_and_not_read_as_zero() -> None:
    """A run migrated from before the field carries *not recorded*, and can be
    the judged run. The headline says so, and does not read it as zero (ADR
    0052, Its price)."""
    run, baseline = a_run(None), a_run(())
    comparison = compare(run, baseline)
    head = headline(comparison, run, baseline, locale="en", declared=None)
    assert head.modules_unchecked is None, (
        f"not recorded read as {head.modules_unchecked!r}"
    )
    for locale in ("en", "it"):
        said = headline(comparison, run, baseline, locale=locale, declared=None)
        assert phrase(locale, "fact.modules_unchecked.unrecorded") in said.sentence
    assert exit_code(head) == 0
    payload = compare_json(comparison, head, baseline=baseline, full=False, run=run)
    assert payload["modules_unchecked"] is None, (
        f"compare --json carries {payload['modules_unchecked']!r} for a value "
        "that was not recorded"
    )


def test_the_fact_moves_no_number_beside_a_regression() -> None:
    """A regression still exits 1, with the fact beside it: it is not a cause of
    any code."""
    run, baseline = a_run(("brief",), judged=False), a_run(())
    head = headline(compare(run, baseline), run, baseline, locale="en", declared=None)
    assert exit_code(head) == 1


# --------------------------------------------------------------------------- #
# The field's schema (ADR 0052, the field on the run)
# --------------------------------------------------------------------------- #


def test_a_document_of_the_previous_schema_migrates_to_not_recorded() -> None:
    """Additive, with the value *not recorded*, as `digline_version` and `usage`
    are migrated: a document written before the field records nothing about
    it."""
    document = run_to_dict(a_run(()))
    document["schema_version"] = SCHEMA_VERSION - 1
    document.pop("modules_unchecked", None)
    migrated = run_from_dict(upgrade_document(document))
    assert migrated.modules_unchecked is None, (
        "the migration invented a value for a document that recorded none"
    )


def test_not_recorded_is_never_written_as_zero() -> None:
    document = run_document(a_run(None), NOTHING_EXTRA)
    assert document["modules_unchecked"] is None
    assert json.loads(json.dumps(document))["modules_unchecked"] is None


def test_the_field_stays_out_of_config_hash() -> None:
    """Two runs of one configuration can carry different values; a field that
    varies while the configuration does not stays out of its identity."""
    run, baseline = a_run(("brief",)), a_run(())
    assert not compare(run, baseline).config_changed
