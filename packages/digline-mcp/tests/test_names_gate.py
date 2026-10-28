"""Under `--names project` no answer carries a name the projection would
tokenise: the gate ADR 0054 §7 asks for, in the shape of
`tests/test_projection_gate.py`. (#548)

**It fails closed.** Every tool the server registers is driven, under
`project`, over a copy of `examples/prompt-first` with two runs and a baseline,
and every string in every answer sits at a path in `STRINGS` below, or the test
is red and names the tool and the path. A tool added to the server is red until
it is driven here, and a field added to an answer is red until it is
classified. The tool list is read from the server, not written into the test.

**The classes are ADR 0034 §4's**, and one more:

- (a) digline's own vocabulary or a form it writes: a digest, an instant, a
  run key, a version, a word of its own;
- (b) the committing party's own strings, `tenant`, `suite`, `environment`
  and the commit, in clear by ADR 0054 §9;
- (c) a token, and not only of a token's form: one **this table minted**;
- (p) **prose**, a sentence digline composed. ADR 0054 §8 says a gate cannot
  classify prose, and this one does not try: it checks that no text the table
  was asked to mint appears in it. That is a check on these names, in this
  fixture, and a weaker one than (c). What makes it hold is that the sentences
  are composed from projected values, never from the names.

**What it does not cover.** A path that does not occur in this fixture is not
seen: the walk is of answers, not of the model behind them, so a field that is
empty here is unclassified and unchecked. Numbers are not walked, as in the
projection's gate. ADR 0054 §8 wants a refusal's names in fields, which the
core's classes do not carry, and a test here holds that as an
`xfail(strict=True)`.

**Until they do, a refusal is walked as prose.** Every refusal in
`PROVOCATIONS` is driven under `project`, and its sentence is held against the
names the projection tokenises in this fixture, which are known. One that holds
a name is red unless `NAMED_IN_PROSE` declares it, and that table may only
shrink. What this walk does not cover:

- **A refusal nobody provokes here is not seen.** The walk is of the
  provocations, not of the code. Not provoked: the refusals of loading a
  suite, which every tool does first and which quote the suite's own names;
  the store's other refusals on reading; and any refusal added later.
- **A refusal is provoked through one tool.** A stored document is read
  through `get_run`; the other tools read it through the same `read_run`.
- **Only this fixture's names are looked for**, and a name that is also a
  word digline writes could not be told from it. A name is matched where it
  stands as a name, so the group `till` is not found in "still".
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import anyio
import pytest
from _names import RecordingTable
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult
from tests._helpers import baseline_in, cli, copy_tracked, git

from digline.core import (
    NAMED_CONFIG_KEYS,
    TokenKind,
    project_served,
    redact,
    run_from_json,
    run_to_json,
    split_grouped_name,
)
from digline.report import diff as diff_report
from digline_mcp.server import build_server

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "prompt-first"
SPEC = "suite.py"

Check = Callable[[str], bool]

_DIGEST = re.compile(r"[0-9a-f]{16}")
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+(?:Z|[+-][0-9:]+)")
_RUN_KEY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9-]+-[0-9a-f]{16}")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\S*")
_WORD = re.compile(r"[a-z][a-z_]*")


class Gate:
    """The checks, bound to the table that minted this fixture's tokens and to
    the labels `run_labels` gives the runs the answers name."""

    def __init__(
        self, table: RecordingTable, *, labels: frozenset[str] = frozenset()
    ) -> None:
        self.table = table
        self.labels = labels

    def form(self, pattern: re.Pattern[str], *, empty: bool = False) -> Check:
        return lambda text: (empty and text == "") or bool(pattern.fullmatch(text))

    def word(self, *, empty: bool = False) -> Check:
        """(a): a word of digline's, which is no name the table minted."""
        return lambda text: (
            (empty and text == "")
            or (bool(_WORD.fullmatch(text)) and text not in self.table.texts())
        )

    def label(self, text: str) -> bool:
        """(a): a run's label, one of those `run_labels` gives for the two runs
        an answer names. Read from the function and not written here as forms,
        because it has three resolutions and a list of them can hold fewer."""
        return text in self.labels

    def token(self, text: str) -> bool:
        """(c): a token this table minted."""
        return text in self.table.rows

    def config_key(self, text: str) -> bool:
        """(a) or (c): a configuration key is digline's word where the run
        recorded it as one, and a token this table minted otherwise. (ADR 0034
        §17.2; #323)"""
        return text in NAMED_CONFIG_KEYS or self.token(text)

    def case(self, text: str) -> bool:
        """(c): a case's id, or nothing where a line is about the run, as an
        aggregate's is."""
        return text == "" or self.token(text)

    def check(self, text: str) -> bool:
        """(c): a check's name, `family[group=…]` included, each part a token
        this table minted."""
        family, group = split_grouped_name(text)
        return self.token(family) and (group is None or self.token(group))

    def prose(self, text: str) -> bool:
        """(p): no text the table minted appears in it."""
        return not any(name in text for name in self.table.texts())

    @staticmethod
    def anything(_: str) -> bool:
        return True

    @staticmethod
    def empty(text: str) -> bool:
        return text == ""


def strings(gate: Gate) -> dict[str, tuple[str, Check]]:
    """Every path a string may sit at in an answer, with its class and check.
    One map for every tool: a path means the same thing in each."""
    runkey, time, digest = (
        gate.form(_RUN_KEY),
        gate.form(_TIME),
        gate.form(_DIGEST),
    )
    return {
        # (a) forms digline writes
        "$.config_hash": ("a", digest),
        "$.created_at": ("a", time),
        "$.promoted_at": ("a", gate.form(_TIME, empty=True)),
        "$.rejudged_from": ("a", gate.form(_RUN_KEY, empty=True)),
        "$.digline_version": ("a", gate.form(_VERSION)),
        "$.runs[].digline_version": ("a", gate.form(_VERSION)),
        "$.key": ("a", runkey),
        "$.baseline_key": ("a", runkey),
        "$.run_key": ("a", runkey),
        "$.runs[].key": ("a", runkey),
        "$.runs.left.key": ("a", runkey),
        "$.runs.right.key": ("a", runkey),
        "$.reference.key": ("a", runkey),
        "$.runs[].created_at": ("a", time),
        "$.runs.left.created_at": ("a", time),
        "$.runs.right.created_at": ("a", time),
        "$.first": ("a", time),
        "$.last": ("a", time),
        "$.on_record_not_read[]": ("a", time),
        "$.reference.created_at": ("a", time),
        "$.reference.promoted_at": ("a", time),
        "$.spans[].first_seen": ("a", time),
        "$.spans[].last_seen": ("a", time),
        "$.runs.left.label": ("a", gate.label),
        "$.runs.right.label": ("a", gate.label),
        "$.results[].verdicts[].assertion_id": ("a", digest),
        "$.aggregate[].assertion_id": ("a", digest),
        "$.runs[].aggregate[].assertion_id": ("a", digest),
        "$.shape[].assertion_id": ("a", digest),
        "$.facts[].assertion_id": ("a", digest),
        "$.facts[].shape.assertion_id": ("a", digest),
        # (a) digline's words
        "$.results[].verdicts[].status": ("a", gate.word()),
        "$.aggregate[].status": ("a", gate.word()),
        "$.runs[].aggregate[].status": ("a", gate.word()),
        "$.deltas[].outcome": ("a", gate.word()),
        "$.deltas[].scope": ("a", gate.word()),
        "$.checks[].favours": ("a", gate.word()),
        "$.checks[].outcome": ("a", gate.word()),
        "$.checks[].scope": ("a", gate.word()),
        "$.target_config_deltas[].outcome": ("a", gate.word()),
        "$.facts[].about": ("a", gate.word()),
        "$.facts[].kind": ("a", gate.word()),
        "$.facts[].noise_source": ("a", gate.word(empty=True)),
        "$.facts[].outcome": ("a", gate.word()),
        "$.facts[].scope": ("a", gate.word()),
        "$.scope": ("a", gate.word()),
        "$.spans[].side": ("a", gate.word()),
        "$.spans[].absence": ("a", gate.word()),
        "$.reference.target.absence": ("a", gate.word()),
        "$.reference.judge.absence": ("a", gate.word()),
        # A provider is read from a configuration key, and a projection's keys
        # are tokens: under `project` the reading says `projected` and names
        # no provider. Held empty, so a provider read in clear is red.
        "$.spans[].provider": ("a", gate.empty),
        "$.reference.target.provider": ("a", gate.empty),
        "$.reference.judge.provider": ("a", gate.empty),
        # (b) the committing party's own strings (ADR 0054 §9)
        "$.tenant": ("b", gate.anything),
        "$.suite": ("b", gate.anything),
        "$.environment": ("b", gate.anything),
        "$.git_commit": ("b", gate.anything),
        "$.runs[].environment": ("b", gate.anything),
        "$.runs[].git_commit": ("b", gate.anything),
        "$.runs.left.environment": ("b", gate.anything),
        "$.runs.right.environment": ("b", gate.anything),
        "$.spans[].environments[]": ("b", gate.anything),
        # (c) tokens this table minted
        "$.results[].case_id": ("c", gate.token),
        "$.results[].verdicts[].assertion": ("c", gate.check),
        "$.results[].calibration.check": ("c", gate.token),
        "$.aggregate[].assertion": ("c", gate.check),
        "$.runs[].aggregate[].assertion": ("c", gate.check),
        "$.target_config.values{}": ("a|c", gate.config_key),
        "$.deltas[].assertion": ("c", gate.check),
        "$.deltas[].case_id": ("c", gate.case),
        "$.shape[].assertion": ("c", gate.check),
        "$.checks[].assertion": ("c", gate.check),
        "$.checks[].case_id": ("c", gate.case),
        "$.facts[].assertion": ("c", gate.check),
        "$.facts[].case_id": ("c", gate.case),
        "$.facts[].name": ("c", gate.check),
        "$.facts[].before": ("c", gate.token),
        "$.facts[].shape.assertion": ("c", gate.check),
        "$.target_config_deltas[].field": ("a|c", gate.config_key),
        "$.target_config_deltas[].before": ("c", gate.token),
        "$.target_config_deltas[].after": ("c", gate.token),
        # (p) prose composed from projected values
        "$.note": ("p", gate.prose),
        "$.sentence": ("p", gate.prose),
        "$.notes[]": ("p", gate.prose),
        "$.runs.left.note": ("p", gate.prose),
        "$.runs.right.note": ("p", gate.prose),
        "!refusal": ("p", gate.prose),
        # A refusal's fields. `role` is digline's word for the document a
        # refusal could not read. (ADR 0054 §8; #742)
        "!refusal.role": ("a", gate.word()),
    }


#: The maps whose keys are data rather than field names, and the check on a
#: key. A map not listed here has its keys read as field names, so a data key
#: in it shows up as a path nobody classified.
KEYED: dict[str, str] = {"$.target_config.values": "$.target_config.values{}"}


def labels_in(answers: dict[str, list[tuple[str, str]]]) -> frozenset[str]:
    """The labels `run_labels` gives each pair of runs an answer names, from
    the instants and keys the answer carries for them."""
    labels: set[str] = set()
    for found in answers.values():
        at = dict(found)
        sides = [
            f"$.runs.{side}.{field}"
            for side in ("left", "right")
            for field in ("created_at", "key")
        ]
        if all(path in at for path in sides):
            left_at, left_key, right_at, right_key = (at[path] for path in sides)
            labels.update(
                diff_report.run_labels(
                    left_at, right_at, left_key=left_key, right_key=right_key
                )
            )
    return frozenset(labels)


def walk(value: Any, path: str = "$") -> list[tuple[str, str]]:
    """Every string in `value`, value or data key, with its path."""
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in cast(dict[str, Any], value).items():
            if path in KEYED:
                found.append((KEYED[path], key))
                found.extend(walk(item, KEYED[path]))
            else:
                found.extend(walk(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for item in cast(list[Any], value):
            found.extend(walk(item, f"{path}[]"))
    elif isinstance(value, str):
        found.append((path, value))
    return found


#: What the copy adds to the example: an aggregate split by group, so that a
#: run's aggregate names, `family[group=…]` among them, are in the answers.
#: Without one, `list_runs` names nothing and a list in clear passed this gate.
_WIDENED = (
    (
        "from digline.core import JudgeReply, Levenshtein, LlmRubric, Repeated",
        "from digline.core import Accuracy, JudgeReply, Levenshtein, LlmRubric, "
        "Repeated",
    ),
    (
        'Case(id=c["id"], vars=c["vars"], expected=c["expected"])',
        'Case(id=c["id"], vars=c["vars"], expected=c["expected"], '
        'label="positive", group="till" if "price" in c["id"] else "shelf")',
    ),
    (
        "    samples=3,\n    min_agreement=",
        '    run_assertions=[Accuracy(over="levenshtein", threshold=0.5, '
        "tolerance=0.05, by_group=True)],\n    samples=3,\n    min_agreement=",
    ),
)


#: Tracked files of the example the fixture leaves out: its lock and its
#: rendered report, which no tool reads.
_NOT_COPIED = frozenset({"uv.lock", "report.html"})


def build_repository(tmp: Path, *, example: Path = EXAMPLE) -> tuple[Path, str, str]:
    repo = tmp / "prompt-first"
    copy_tracked(example, repo, leave_out=_NOT_COPIED)
    suite = repo / SPEC
    source = suite.read_text(encoding="utf-8")
    for before, after in _WIDENED:
        assert source.count(before) == 1, before
        source = source.replace(before, after)
    suite.write_text(source, encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "initial")
    keys: list[str] = []
    for _ in range(2):
        done = cli(repo, "run", "--suite", SPEC)
        assert done.stdout.strip(), done.stderr
        keys.append(done.stdout.strip().splitlines()[-1])
        if len(keys) == 1:
            # The widened suite is another configuration than the committed
            # baseline's, so the first run becomes the reference.
            promoted = cli(
                repo,
                "promote",
                "--replacing",
                baseline_in(repo),
                "--suite",
                SPEC,
                "--run",
                keys[0],
            )
            assert promoted.returncode == 0, promoted.stderr
    return repo, keys[0], keys[1]


def drive(
    repo: Path, first: str, second: str, *, table: RecordingTable | None
) -> dict[str, list[tuple[str, str]]]:
    """Every tool the server registers, called once over `repo`, and the strings
    of each answer. `run` is called twice, as an agent must: its refusal is an
    answer too."""
    calls: dict[str, dict[str, Any]] = {
        "list_runs": {"suite": SPEC},
        "get_run": {"suite": SPEC},
        "get_baseline": {"suite": SPEC},
        "log": {"suite": SPEC},
        "compare": {"suite": SPEC},
        "diff": {"suite": SPEC, "run1": first, "run2": second},
        "explain": {"suite": SPEC},
        "run": {"suite": SPEC},
    }
    names = "clear" if table is None else "project"
    answers: dict[str, list[tuple[str, str]]] = {}

    async def go() -> None:
        server = build_server(str(repo), None, None, names=names, table=table)
        registered = {tool.name for tool in await server.list_tools()}
        assert registered == set(calls), (
            f"the server registers {sorted(registered - set(calls))} and this "
            f"gate drives none of them, or drives {sorted(set(calls) - registered)} "
            "the server no longer has: drive each tool it registers"
        )
        for name, arguments in calls.items():
            strings: list[tuple[str, str]] = []
            try:
                result = await server.call_tool(name, arguments)
            except ToolError as refused:
                strings.append(("!refusal", str(refused)))
                planned = re.search(r"acknowledge_calls=(\d+)", str(refused))
                assert name == "run" and planned, str(refused)
                result = await server.call_tool(
                    name, {**arguments, "acknowledge_calls": int(planned.group(1))}
                )
            assert isinstance(result, CallToolResult)
            strings.extend(walk(result.structured_content))
            answers[name] = strings

    anyio.run(go)
    return answers


@pytest.fixture(scope="module")
def fixture_repo(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, str]:
    return build_repository(tmp_path_factory.mktemp("names"))


@pytest.fixture(scope="module")
def projected(
    fixture_repo: tuple[Path, str, str],
) -> tuple[dict[str, list[tuple[str, str]]], RecordingTable]:
    table = RecordingTable()
    return drive(*fixture_repo, table=table), table


def test_every_string_of_every_answer_is_classified_and_holds(
    projected: tuple[dict[str, list[tuple[str, str]]], RecordingTable],
) -> None:
    answers, table = projected
    classified = strings(Gate(table, labels=labels_in(answers)))
    unclassified = sorted(
        {
            f"{tool}: {path}"
            for tool, found in answers.items()
            for path, _ in found
            if path not in classified
        }
    )
    assert not unclassified, (
        "under --names project these strings sit at paths the gate does not "
        f"classify: {unclassified}. Classify each, or project what put it "
        "there (ADR 0054 §7)"
    )
    failed = sorted(
        f"{tool}: {path} = {value!r} is not ({classified[path][0]})"
        for tool, found in answers.items()
        for path, value in found
        if not classified[path][1](value)
    )
    assert not failed, "\n".join(failed)


def test_the_table_was_asked_for_the_names_this_fixture_holds(
    projected: tuple[dict[str, list[tuple[str, str]]], RecordingTable],
) -> None:
    """The control: what the prose check looks for is there to look for. A
    table asked for nothing would let every sentence pass."""
    _, table = projected
    assert {"gift-wrap", "llm_rubric", "prompts/system.txt", "anthropic"} <= (
        table.texts()
    )


#: Two run keys of the form digline writes, for answers made up here.
_KEYS = (
    "2026-09-04T09-12-33-100000-00-00-5af8d8dd1e55f5c5",
    "2026-09-04T09-12-33-900000-00-00-5af8d8dd1e55f5c5",
)


def _answer(left: str, right: str) -> list[tuple[str, str]]:
    """The strings of a `diff` answer about two runs, as the walk finds them."""
    return [
        ("$.runs.left.created_at", left),
        ("$.runs.left.key", _KEYS[0]),
        ("$.runs.right.created_at", right),
        ("$.runs.right.key", _KEYS[1]),
    ]


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("2026-09-04T09:12:33+00:00", "2026-09-04T09:13:02+00:00"),
        ("2026-09-04T09:12:33+00:00", "2026-09-04T09:12:51+00:00"),
        ("2026-09-04T09:12:33.1+00:00", "2026-09-04T09:12:33.9+00:00"),
    ],
    ids=["minutes differ", "one minute", "one second"],
)
def test_a_label_is_held_to_what_run_labels_gives(left: str, right: str) -> None:
    """A run's label is checked against `run_labels` on the runs the answer
    names, so the gate accepts each of its resolutions and cannot list fewer.
    A list of forms written here accepted two of the three, and went red
    whenever the minute turned between the fixture's two runs."""
    labels = labels_in({"diff": _answer(left, right)})
    check = strings(Gate(RecordingTable(), labels=labels))["$.runs.left.label"][1]
    expected = diff_report.run_labels(
        left, right, left_key=_KEYS[0], right_key=_KEYS[1]
    )
    assert all(check(label) for label in expected), expected
    assert not check(diff_report.when(left) + "x")


def test_in_clear_the_same_answers_carry_the_names(
    fixture_repo: tuple[Path, str, str],
    projected: tuple[dict[str, list[tuple[str, str]]], RecordingTable],
) -> None:
    """`clear` leaves the names as they are: every name the projection minted
    a token for is in some answer in clear, and no token is."""
    _, table = projected
    answers = drive(*fixture_repo, table=None)
    values = {value for found in answers.values() for _, value in found}
    shown = {name for name in table.texts() if any(name in v for v in values)}
    assert {"gift-wrap", "llm_rubric", "anthropic", "claude-haiku-4-5"} <= shown
    assert not any(value in table.rows for value in values)


def _refusal(
    repo: Path, tool: str, arguments: dict[str, Any], **server: Any
) -> ToolError:
    async def go() -> ToolError:
        built = build_server(str(repo), None, None, names="project", **server)
        try:
            await built.call_tool(tool, arguments)
        except ToolError as refused:
            return refused
        raise AssertionError(f"{tool} {arguments} answered; a refusal was expected")

    return anyio.run(go)


def _provoke(repo: Path, first: str, table: RecordingTable) -> dict[str, ToolError]:
    """The refusals this fixture can provoke under `project`: an unknown run, a
    run diffed with itself, a suite outside the root, a corrupted run document,
    and no baseline."""
    said: dict[str, ToolError] = {}
    said["unknown run"] = _refusal(
        repo,
        "get_run",
        {"suite": SPEC, "run": "2020-01-01T00-00-00-000000-00-00-0000000000000000"},
        table=table,
    )
    said["itself"] = _refusal(
        repo, "diff", {"suite": SPEC, "run1": first, "run2": first}, table=table
    )
    said["outside"] = _refusal(
        repo, "get_run", {"suite": "../elsewhere.py"}, table=table
    )
    stored = next((repo / ".digline").glob("*/runs/*/*.json"))
    kept = stored.read_bytes()
    try:
        stored.write_text('{"schema_version": "x"}', encoding="utf-8")
        said["corrupted"] = _refusal(
            repo, "get_run", {"suite": SPEC, "run": stored.stem}, table=table
        )
    finally:
        stored.write_bytes(kept)
    baselines = next((repo / ".digline").glob("*/baselines"))
    moved = baselines.with_name("baselines-away")
    baselines.rename(moved)
    try:
        said["no baseline"] = _refusal(
            repo, "get_baseline", {"suite": SPEC}, table=table
        )
    finally:
        moved.rename(baselines)
    return said


def test_the_refusals_a_tool_meets_here_name_nothing_the_table_minted(
    fixture_repo: tuple[Path, str, str],
    projected: tuple[dict[str, list[tuple[str, str]]], RecordingTable],
) -> None:
    """The refusals this fixture can provoke, under `project`, checked as
    prose. Each names what it needs to and nothing the table minted, because
    what it quotes is the committing party's own (class b), a key, or the
    request. **A measurement over these, not a rule**: a refusal of the core is
    a sentence, and ADR 0054 §8's fields are not carried by the core's classes.
    The next test holds what is missing. (ADR 0054 §8)"""
    repo, first, _ = fixture_repo
    _, table = projected
    said = {why: str(refused) for why, refused in _provoke(repo, first, table).items()}
    leaked = {
        why: sorted(name for name in table.texts() if name in text)
        for why, text in said.items()
    }
    assert not any(leaked.values()), leaked
    assert all(said.values()), said


def _fields(refused: BaseException) -> list[tuple[str, str]]:
    """The strings a refusal carries in fields, through every wrap, each at
    `!refusal.<field>`: what the gate could classify, as against the sentence."""
    found: list[tuple[str, str]] = []
    error: BaseException | None = refused
    while error is not None:
        for field, value in vars(error).items():
            found.extend(walk(value, f"!refusal.{field}"))
        error = error.__cause__ or error.__context__
    return found


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ADR 0054 §8 wants the names a refusal quotes carried in fields, and "
        "this gate classifies fields, not prose. The five refusals measured "
        "under project (an unknown run, a run diffed with itself, a corrupted "
        "run document, a suite outside the root, no baseline) quote no name "
        "the table minted, and five measurements are not a perimeter. What is "
        "missing is the core's error classes carrying those fields (#548). "
        "The refusals that do name, in their sentence, are NAMED_IN_PROSE."
    ),
)
def test_the_gate_classifies_the_names_of_a_refusal(
    fixture_repo: tuple[Path, str, str],
    projected: tuple[dict[str, list[tuple[str, str]]], RecordingTable],
) -> None:
    """Every refusal a tool meets carries its names in fields, and each field
    sits at a path the gate classifies as something other than prose."""
    repo, first, _ = fixture_repo
    _, table = projected
    classified = strings(Gate(table))
    bare = sorted(
        why
        for why, refused in _provoke(repo, first, table).items()
        if not _fields(refused)
    )
    assert not bare, f"these refusals carry their names in a sentence alone: {bare}"
    unclassified = sorted(
        f"{why}: {path}"
        for why, refused in _provoke(repo, first, table).items()
        for path, _ in _fields(refused)
        if classified.get(path, ("p",))[0] == "p"
    )
    assert not unclassified, unclassified


# -- The refusals, walked as the answers are -----------------------------------
#
# ADR 0054 §8 says a refusal carries the names it quotes in fields and a gate
# classifies the fields, never the prose. Until the core's refusals do, the
# prose is what crosses, and this measures it the only way a sentence can be
# measured mechanically: against the names the projection tokenises in this
# fixture, which are known. A refusal whose sentence holds one of them is red,
# unless `NAMED_IN_PROSE` declares it. The table is the measure of what §8
# still owes, and it may only shrink. (ADR 0054 §8)


def named_in(text: str, names: set[str]) -> frozenset[str]:
    """The names that stand in `text` as names, not as part of a longer word:
    the group `till` stands in "group 'till'" and not in "still". A character
    a name can hold may not touch it on either side, and a full stop after it
    ends a sentence unless a name character follows."""
    return frozenset(
        name
        for name in names
        if re.search(
            rf"(?<![A-Za-z0-9_./-]){re.escape(name)}(?![A-Za-z0-9_/-]|\.[A-Za-z0-9])",
            text,
        )
    )


def test_a_name_is_found_as_a_name_and_not_inside_a_word() -> None:
    """The control for the matcher: a name quoted, at the end of a sentence or
    inside a check's group is found; the same letters inside a word are not."""
    names = {"till", "prompts/system.txt", "opening-hours"}
    assert named_in("case 'opening-hours' is suspended", names) == {"opening-hours"}
    assert named_in("an artifact path is prompts/system.txt.", names) == {
        "prompts/system.txt"
    }
    assert named_in("accuracy[group=till] moved", names) == {"till"}
    assert named_in("it still carries what redaction removes", names) == set()
    assert named_in("opening-hours-2 and prompts/system.txt.bak", names) == set()


@dataclass(frozen=True, slots=True)
class Scene:
    """What a provocation works on: the fixture's repository, its two runs, the
    table that projected it, and a second repository whose last run was made
    under a changed suite."""

    repo: Path
    first: str
    second: str
    table: RecordingTable
    changed: tuple[Path, str, str]


#: A provocation drives one tool into one refusal and returns it, leaving the
#: repository as it found it.
Provoke = Callable[[Scene], ToolError]


@dataclass(frozen=True, slots=True)
class EchoTable:
    """A name table that answers a name with the name itself: what a table
    the owning process got wrong hands the projection."""

    def mint(self, kind: TokenKind, text: str) -> str:
        return text

    def lookup(self, token: str) -> None:
        return None


def _document(base: str, edit: Callable[[dict[str, Any]], object]) -> Provoke:
    """`get_run` on the second run, its stored document replaced by `base`
    (`stored`, or a valid `redacted` or `projected` copy of it) with `edit`
    applied."""

    def provoke(scene: Scene) -> ToolError:
        stored = next((scene.repo / ".digline").glob(f"*/runs/*/{scene.second}.json"))
        kept = stored.read_bytes()
        run = run_from_json(kept.decode("utf-8"))
        if base == "redacted":
            run = redact(run)
        elif base == "projected":
            run = project_served(run, scene.table.mint)
        document: dict[str, Any] = json.loads(run_to_json(run))
        edit(document)
        try:
            stored.write_text(json.dumps(document), encoding="utf-8")
            return _refusal(
                scene.repo,
                "get_run",
                {"suite": SPEC, "run": scene.second},
                table=scene.table,
            )
        finally:
            stored.write_bytes(kept)

    return provoke


def _first_case(**fields: object) -> Callable[[dict[str, Any]], object]:
    return lambda document: document["results"][0].update(fields)


def _first_verdict(**fields: object) -> Callable[[dict[str, Any]], object]:
    return lambda document: document["results"][0]["verdicts"][0].update(fields)


def _band(document: dict[str, Any], **fields: object) -> dict[str, Any]:
    """A calibration band on the first case's first check, inside (0, 1)."""
    verdict = document["results"][0]["verdicts"][0]
    return {
        "check": verdict["assertion"],
        "assertion_id": verdict["assertion_id"],
        "low": 0.1,
        "high": 0.9,
        **fields,
    }


def _with_band(**fields: object) -> Callable[[dict[str, Any]], object]:
    return lambda document: document["results"][0].update(
        calibration=_band(document, **fields)
    )


def _in_turn(
    *edits: Callable[[dict[str, Any]], object],
) -> Callable[[dict[str, Any]], object]:
    """Several edits of one document, applied in order."""

    def edit(document: dict[str, Any]) -> None:
        for each in edits:
            each(document)

    return edit


def _unknown_run(scene: Scene) -> ToolError:
    return _refusal(
        scene.repo,
        "get_run",
        {"suite": SPEC, "run": "2020-01-01T00-00-00-000000-00-00-0000000000000000"},
        table=scene.table,
    )


def _itself(scene: Scene) -> ToolError:
    return _refusal(
        scene.repo,
        "diff",
        {"suite": SPEC, "run1": scene.first, "run2": scene.first},
        table=scene.table,
    )


def _outside(scene: Scene) -> ToolError:
    return _refusal(
        scene.repo, "get_run", {"suite": "../elsewhere.py"}, table=scene.table
    )


def _no_baseline(scene: Scene) -> ToolError:
    baselines = next((scene.repo / ".digline").glob("*/baselines"))
    moved = baselines.with_name("baselines-away")
    baselines.rename(moved)
    try:
        return _refusal(scene.repo, "get_baseline", {"suite": SPEC}, table=scene.table)
    finally:
        moved.rename(baselines)


def _different_suites(scene: Scene) -> ToolError:
    repo, before, after = scene.changed
    return _refusal(
        repo,
        "diff",
        {"suite": SPEC, "run1": before, "run2": after},
        table=RecordingTable(),
    )


def _echoing_table(scene: Scene) -> ToolError:
    return _refusal(
        scene.repo, "get_run", {"suite": SPEC, "run": scene.second}, table=EchoTable()
    )


#: Every refusal this gate walks: the tool driven into it, and words of its
#: sentence that pin the site it comes from, so a provocation that drifts to
#: another refusal is red rather than measuring the wrong one. Measured at
#: `5cae1855`. **What it does not cover** is in the module's docstring.
PROVOCATIONS: dict[str, tuple[Provoke, str]] = {
    # The five the fixture provoked before this gate: none names anything.
    "unknown run": (_unknown_run, "run not found"),
    "a run diffed with itself": (_itself, "a run diffed with itself"),
    "a suite outside the root": (_outside, "which is outside"),
    "a corrupted document": (
        _document("stored", lambda d: d.update(schema_version="x")),
        "'schema_version' is a JSON string, not an integer",
    ),
    "no baseline": (_no_baseline, "has no baseline for tenant"),
    # Family A: a stored document read in clear, before any projection. The
    # validations behind `run_from_dict` raise `ValueError`, quoted whole.
    "a canary that is a calibration case": (
        _document("stored", _in_turn(_with_band(), _first_case(canary=True))),
        "is both a canary and a calibration case",
    ),
    "a suspension with no reason": (
        _document("stored", _first_case(suspended=True, suspended_reason="")),
        "is suspended without a stated reason",
    ),
    "a suspended case with verdicts": (
        _document("stored", _first_case(suspended=True, suspended_reason="paused")),
        "is suspended but carries verdicts",
    ),
    "a suspended case with answers": (
        _document(
            "stored",
            _first_case(suspended=True, suspended_reason="paused", verdicts=[]),
        ),
        "is suspended but carries recorded answers",
    ),
    "a band that binds no verdict": (
        _document("stored", _with_band(assertion_id="0000000000000000")),
        "and none of its verdicts is that check's",
    ),
    "a band outside (0, 1)": (
        _document("stored", _with_band(low=0.9, high=0.1)),
        "declares the band 0.900000–0.100000",
    ),
    "a band with no identity": (
        _document("stored", _with_band(assertion_id="")),
        "carries no assertion_id: a band binds",
    ),
    "a verdict with no identity": (
        _document("stored", _first_verdict(assertion_id="")),
        "carries no assertion_id: compare() pairs on it",
    ),
    "an artifact's flag of the wrong type": (
        _document(
            "stored",
            lambda d: d["artifacts"]["prompts/system.txt"].update(withheld="yes"),
        ),
        "'withheld' is a JSON string, not a boolean",
    ),
    "a redacted verdict with its reason": (
        _document("redacted", _first_verdict(reason="kept")),
        "verdict carries 'reason', but the run declares itself redacted",
    ),
    "a redacted answer with its text": (
        _document(
            "redacted",
            lambda d: d["results"][0]["responses"][0].update(output="kept"),
        ),
        "declares itself withheld but still carries what redaction removes",
    ),
    "a projected case id in clear": (
        _document("projected", _first_case(case_id="opening-hours")),
        "a case id is 'opening-hours', which is not a token",
    ),
    "a projected check name in clear": (
        _document("projected", _first_verdict(assertion="levenshtein")),
        "is 'levenshtein', which is not a token",
    ),
    "a projected group in clear": (
        _document(
            "projected",
            lambda d: d["aggregate"][1].update(
                assertion=d["aggregate"][1]["assertion"].split("[")[0] + "[group=shelf]"
            ),
        ),
        "the group of a verdict in the aggregate is 'shelf'",
    ),
    "a projected artifact path in clear": (
        _document(
            "projected",
            lambda d: d.update(
                artifacts={"prompts/system.txt": next(iter(d["artifacts"].values()))}
            ),
        ),
        "an artifact path is 'prompts/system.txt'",
    ),
    "a projected calibration check in clear": (
        _document("projected", _with_band(check="levenshtein")),
        "the calibration check of a case",
    ),
    "a projected run with metadata": (
        _document("projected", lambda d: d.update(metadata={"opening-hours": 1})),
        "the run carries metadata (opening-hours)",
    ),
    "a projected identity that is a name": (
        _document("projected", _first_verdict(assertion_id="levenshtein")),
        "has an identity that is not a digest",
    ),
    "a projected verdict with metadata in clear": (
        _document(
            "projected",
            _first_verdict(origin="foreign", metadata={"gift-wrap": "x"}),
        ),
        "carries the string metadata 'gift-wrap'",
    ),
    # Family B: `diff` refuses two runs made under different suites, and names
    # the rules that moved. The server projects both runs first.
    "two runs under different suites": (
        _different_suites,
        "were produced under different suites",
    ),
    # Family C: the projection refuses a table that answers a name with itself.
    "a table that answers with the name": (
        _echoing_table,
        "with something that does not have a token's form",
    ),
}

#: The refusals whose sentence names what the projection tokenises:
#: each with the site the name enters the sentence at and the names that
#: leave. **It may only shrink.** A refusal repaired leaves it, and the test
#: below says so; one that starts to name is red until it is declared here,
#: and the count beside it says the table grew. (ADR 0054 §8)
NAMED_IN_PROSE: dict[str, tuple[str, frozenset[str]]] = {
    "a canary that is a calibration case": (
        "core/run.py, CaseResult.__post_init__",
        frozenset({"opening-hours"}),
    ),
    "a suspension with no reason": (
        "core/run.py, CaseResult.__post_init__",
        frozenset({"opening-hours"}),
    ),
    "a suspended case with verdicts": (
        "core/run.py, CaseResult.__post_init__",
        frozenset({"opening-hours"}),
    ),
    "a suspended case with answers": (
        "core/run.py, CaseResult.__post_init__",
        frozenset({"opening-hours"}),
    ),
    "a band that binds no verdict": (
        "core/run.py, _check_band_binds",
        frozenset({"levenshtein", "opening-hours"}),
    ),
    "a band outside (0, 1)": (
        "core/calibration.py, CalibrationBand.bounds",
        frozenset({"levenshtein"}),
    ),
    "a band with no identity": (
        "core/calibration.py, CalibrationBand.__post_init__",
        frozenset({"levenshtein"}),
    ),
    "a verdict with no identity": (
        "core/types.py, Verdict.__post_init__",
        frozenset({"levenshtein"}),
    ),
    "an artifact's flag of the wrong type": (
        "core/run.py, _artifact_from_dict (its `where`)",
        frozenset({"prompts/system.txt"}),
    ),
    "a projected case id in clear": (
        "core/run.py, _check_projected, token",
        frozenset({"opening-hours"}),
    ),
    "a projected check name in clear": (
        "core/run.py, _check_projected, token",
        frozenset({"levenshtein"}),
    ),
    "a projected group in clear": (
        "core/run.py, _check_projected, token",
        frozenset({"shelf"}),
    ),
    "a projected artifact path in clear": (
        "core/run.py, _check_projected, token",
        frozenset({"prompts/system.txt"}),
    ),
    "a projected calibration check in clear": (
        "core/run.py, _check_projected, token",
        frozenset({"levenshtein"}),
    ),
    "a projected run with metadata": (
        "core/run.py, _check_projected, the run's metadata",
        frozenset({"opening-hours"}),
    ),
    "a projected identity that is a name": (
        "core/run.py, _check_projected, identity",
        frozenset({"levenshtein"}),
    ),
    "a projected verdict with metadata in clear": (
        "core/run.py, _check_projected, verdict",
        frozenset({"gift-wrap"}),
    ),
}

#: How many refusals `NAMED_IN_PROSE` declares. Lowered when one is repaired;
#: raising it is what a pull request that adds a refusal naming a name has to
#: show.
#:
#: **What this number does not cover**, so it is not read as the width of
#: ADR 0054 §8. It counts the refusals `PROVOCATIONS` drives, and three kinds
#: cross the boundary and are not driven yet:
#:
#: - the refusals of loading a suite, which every tool does first. They are
#:   inside §8, ruled so on 2026-10-28, and several quote a check's name or a
#:   case id (`run/suite.py`);
#: - the store's other refusals on reading a run or a baseline;
#: - `diff`'s refusal of two runs graded by different judges, which was read
#:   in the code and not provoked.
NAMED_IN_PROSE_COUNT = 17


@pytest.fixture(scope="module")
def changed_suite(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, str]:
    """A repository whose last run was made under a suite with one threshold
    moved: two runs `diff` refuses to compare."""
    repo, _, before = build_repository(tmp_path_factory.mktemp("changed"))
    suite = repo / SPEC
    source = suite.read_text(encoding="utf-8")
    moved = source.replace("threshold=0.5,", "threshold=0.4,")
    assert moved != source, "the control: the suite has a threshold to move"
    suite.write_text(moved, encoding="utf-8")
    git(repo, "commit", "-qam", "move a threshold")
    done = cli(repo, "run", "--suite", SPEC)
    assert done.stdout.strip(), done.stderr
    return repo, before, done.stdout.strip().splitlines()[-1]


@dataclass(frozen=True, slots=True)
class Walked:
    """One provocation's refusal: its sentence, the names that stand in it, and
    the strings it carries in fields."""

    text: str
    names: frozenset[str]
    fields: list[tuple[str, str]]


@pytest.fixture(scope="module")
def walked(
    fixture_repo: tuple[Path, str, str],
    projected: tuple[dict[str, list[tuple[str, str]]], RecordingTable],
    changed_suite: tuple[Path, str, str],
) -> dict[str, Walked]:
    """Each provocation's refusal, walked."""
    repo, first, second = fixture_repo
    _, table = projected
    scene = Scene(repo, first, second, table, changed_suite)
    names = table.texts()
    said: dict[str, Walked] = {}
    for why, (provoke, _) in PROVOCATIONS.items():
        refused = provoke(scene)
        text = str(refused)
        said[why] = Walked(text, named_in(text, names), _fields(refused))
    return said


def test_every_provocation_reaches_the_refusal_it_names(
    walked: dict[str, Walked],
) -> None:
    """A provocation measures one site, so it has to land there."""
    missed = {
        why: seen.text
        for why, seen in walked.items()
        if PROVOCATIONS[why][1] not in seen.text
    }
    assert not missed, missed


def test_no_refusal_names_in_its_sentence_what_the_projection_tokenises(
    walked: dict[str, Walked],
) -> None:
    """A refusal that crosses the boundary under `project` names nothing the
    table was asked to mint, or it is declared in `NAMED_IN_PROSE` with the
    names it lets out. One declared that names nothing any more, or other
    names than declared, is red too, so the table says what is true."""
    undeclared = {
        why: sorted(seen.names)
        for why, seen in walked.items()
        if seen.names and why not in NAMED_IN_PROSE
    }
    assert not undeclared, (
        "these refusals name in their sentence what the projection tokenises, "
        f"and NAMED_IN_PROSE does not declare them: {undeclared}"
    )
    stale = sorted(why for why in NAMED_IN_PROSE if not walked[why].names)
    assert not stale, (
        f"NAMED_IN_PROSE declares {stale}, whose sentences no longer name "
        "anything the projection tokenises: take them out and lower "
        "NAMED_IN_PROSE_COUNT"
    )
    moved = {
        why: (sorted(names), sorted(walked[why].names))
        for why, (_, names) in NAMED_IN_PROSE.items()
        if walked[why].names and walked[why].names != names
    }
    assert not moved, f"declared names, then measured: {moved}"


def test_the_table_of_refusals_that_name_only_shrinks() -> None:
    """Every entry is a provocation this gate walks, and the count is held,
    so an entry added is a number raised in the same diff."""
    assert set(NAMED_IN_PROSE) <= set(PROVOCATIONS), sorted(
        set(NAMED_IN_PROSE) - set(PROVOCATIONS)
    )
    assert len(NAMED_IN_PROSE) == NAMED_IN_PROSE_COUNT, (
        f"NAMED_IN_PROSE holds {len(NAMED_IN_PROSE)} refusals and "
        f"NAMED_IN_PROSE_COUNT says {NAMED_IN_PROSE_COUNT}. Lowered, a refusal "
        "was repaired: lower the count. Raised, a refusal began to name what "
        "the projection tokenises: that is the regression this table exists to "
        "show"
    )


def test_a_field_a_refusal_already_carries_is_classified_and_holds(
    walked: dict[str, Walked],
    projected: tuple[dict[str, list[tuple[str, str]]], RecordingTable],
) -> None:
    """The half of ADR 0054 §8 that exists: where a refusal carries a field,
    the field sits at a path the gate classifies, and holds. `role` is the one
    today (#742)."""
    _, table = projected
    classified = strings(Gate(table))
    found = [
        (why, path, value)
        for why, seen in walked.items()
        for path, value in seen.fields
    ]
    assert any(path == "!refusal.role" for _, path, _ in found), (
        "the control: no refusal walked here carries `role`, so this reads nothing"
    )
    failed = sorted(
        f"{why}: {path} = {value!r}"
        for why, path, value in found
        if classified.get(path, ("p",))[0] == "p" or not classified[path][1](value)
    )
    assert not failed, failed
