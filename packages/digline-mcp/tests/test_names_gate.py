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
projection's gate. And a refusal is checked as prose: `run`'s count, and five
refusals of the core this fixture provokes. ADR 0054 §8 wants a refusal's
names in fields, which the core's classes do not carry, and the last test here
holds that as an `xfail(strict=True)`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import anyio
import pytest
from _names import RecordingTable
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult
from tests._helpers import baseline_in, cli, copy_tracked, git

from digline.core import NAMED_CONFIG_KEYS, split_grouped_name
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
        "missing is the core's error classes carrying those fields (#548)."
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
