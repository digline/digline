"""The two boundaries of an artifact, held to ADR 0042's test plan.

**The read boundary (§2).** A declared file outside the perimeter is never read,
whatever the suite format, and whether the suite or its target declared it.

**The exit boundary (§3).** A file inside the perimeter under `.digline` or
`.git`, or a key that leaves the perimeter, is refused at each of the three
places an artifact's text leaves the `Run` object: `redact()`, `run_document`
and promotion. One predicate, `barred_from_crossing`, decides for all three,
and each exit has its own test here, so that removing the call from any one of
them alone turns its test red.

The keys below are the ones a prefix test would miss: the case-folded forms,
which open the store on a case-insensitive filesystem, and the nested form,
which is another store inside the same perimeter.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Sequence
from pathlib import Path

import pytest
from tests._helpers import baseline_in, cli, git

from digline.core import (
    NOTHING_EXTRA,
    Artifact,
    Contains,
    CrossingRefusedError,
    Disclosure,
    RefusedError,
    Run,
    barred_from_crossing,
    project_served,
    redact,
)
from digline.host import UsageError, read_artifacts
from digline.host.refusals import REFUSALS
from digline.run import Case, Suite
from digline.store import refusals_for
from digline.wire.contract import EXIT_OK, EXIT_USAGE
from digline.wire.run import run_document

#: Keys held back, each with the reason it is in the list.
HELD: dict[str, str] = {
    ".digline/acme/runs/qa/x.json": "the store",
    ".git/config": "the repository's own directory",
    ".DIGLINE/acme/runs/qa/x.json": "the store, case-folded",
    ".Git/config": ".git, case-folded",
    "examples/x/.digline/acme/baselines/qa.json": "a store below the root",
    "vendor/lib/.git": "a submodule's .git file, at the end",
    "..\\secret.env": "a Windows key that leaves the perimeter",
    "../secret.env": "a key recorded before ADR 0042 §2",
    "/etc/hosts": "an absolute key",
}

#: Keys that cross, chosen to sit next to the held ones.
FREE = (
    "prompt.md",
    "prompts/system.md",
    ".github/workflows/ci.yml",
    ".gitignore",
    "digline/notes.md",
    "notes/.digline-old.md",
)

ARTIFACTS_DISCLOSED = Disclosure(artifacts=True)


def _run(*keys: str) -> Run:
    """A complete run recording each key as an artifact with its text."""
    return Run(
        tenant="acme",
        environment="staging",
        suite="qa",
        config_hash="0123456789abcdef",
        created_at="2026-10-05T10:00:00+00:00",
        artifacts={key: Artifact(sha="0" * 64, text="SECRET") for key in keys},
    )


# --------------------------------------------------------------------------- #
# The predicate
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("key", sorted(HELD), ids=lambda k: HELD[k])
def test_the_predicate_holds_back_every_listed_key(key: str) -> None:
    assert barred_from_crossing(key) is not None, key


@pytest.mark.parametrize("key", FREE)
def test_the_predicate_lets_its_neighbours_cross(key: str) -> None:
    """A name that only starts like `.git` or `.digline` is not one: the
    comparison is by whole segment."""
    assert barred_from_crossing(key) is None, key


def test_the_refusal_is_a_refusal_every_front_end_knows() -> None:
    """A `RefusedError` exits 64 on the CLI and reaches an agent as its
    sentence, with neither front end touched (ADR 0041 §4.2, ADR 0011 §10)."""
    assert issubclass(CrossingRefusedError, RefusedError)
    assert CrossingRefusedError in REFUSALS


# --------------------------------------------------------------------------- #
# Exit 1 of 3: redact()
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("key", sorted(HELD), ids=lambda k: HELD[k])
def test_redact_refuses_a_held_artifact_when_artifacts_are_disclosed(key: str) -> None:
    with pytest.raises(CrossingRefusedError) as caught:
        redact(_run("prompt.md", key), ARTIFACTS_DISCLOSED)
    assert key in str(caught.value)
    # The sentence names the held path and only it: the prompt beside it crosses.
    assert "prompt.md" not in str(caught.value)


@pytest.mark.parametrize("key", sorted(HELD), ids=lambda k: HELD[k])
def test_redact_withholds_as_before_when_artifacts_are_not_disclosed(key: str) -> None:
    """Nothing crosses, so there is nothing to refuse (ADR 0042, test plan 5)."""
    redacted = redact(_run(key), Disclosure())
    assert redacted.artifacts[key].withheld


def test_redact_lets_a_free_artifact_cross() -> None:
    redacted = redact(_run(*FREE), ARTIFACTS_DISCLOSED)
    assert all(redacted.artifacts[key].text == "SECRET" for key in FREE)


def test_an_artifact_already_withheld_is_not_refused() -> None:
    """Only its key is left, and every redacted document carries the keys."""
    once = redact(_run(".git/config"), Disclosure())
    assert redact(once, ARTIFACTS_DISCLOSED).artifacts[".git/config"].withheld


# --------------------------------------------------------------------------- #
# Exit 2 of 3: run_document, which does not call redact()
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("key", sorted(HELD), ids=lambda k: HELD[k])
def test_run_document_refuses_a_held_artifact_when_artifacts_are_disclosed(
    key: str,
) -> None:
    with pytest.raises(CrossingRefusedError) as caught:
        run_document(_run(key), ARTIFACTS_DISCLOSED)
    assert key in str(caught.value)


@pytest.mark.parametrize("key", sorted(HELD), ids=lambda k: HELD[k])
def test_run_document_answers_when_artifacts_are_not_disclosed(key: str) -> None:
    document = run_document(_run(key), Disclosure())
    assert "SECRET" not in repr(document)


def test_run_document_lets_a_free_artifact_cross() -> None:
    document = run_document(_run("prompt.md"), ARTIFACTS_DISCLOSED)
    assert "SECRET" in repr(document)


# --------------------------------------------------------------------------- #
# Exit 3 of 3: promotion, condition 9 in refusals_for
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("key", sorted(HELD), ids=lambda k: HELD[k])
def test_refusals_for_carries_the_crossing_with_no_store(key: str) -> None:
    """Whatever the `Disclosure`: a run carries none, because a baseline is the
    complete run (ADR 0042 §3). Answered from the document alone."""
    run = _run("prompt.md", key)
    refusals = refusals_for(run, run.config_hash)
    assert [type(r) for r in refusals] == [CrossingRefusedError]
    assert key in str(refusals[0])


def test_refusals_for_is_silent_on_free_artifacts() -> None:
    run = _run(*FREE)
    assert refusals_for(run, run.config_hash) == ()


def test_the_crossing_comes_before_a_moved_configuration() -> None:
    """First, so a caller raising the first names what must be repaired
    anyway: the artifact is refused until the suite changes, and a moved
    configuration may be the change somebody intended. A choice made in the
    change that implements ADR 0042, which does not place the condition."""
    run = _run(".git/config")
    refusals = refusals_for(run, "another-hash")
    assert [type(r).__name__ for r in refusals] == [
        "CrossingRefusedError",
        "ConfigMismatchError",
    ]


# --------------------------------------------------------------------------- #
# Not an exit: the projection
# --------------------------------------------------------------------------- #


def test_the_projection_is_unaffected() -> None:
    """It begins from `redact(run, NOTHING_EXTRA)`, which withholds every
    artifact, so nothing is left to refuse (ADR 0042, test plan 7)."""
    rows: dict[tuple[str, str], str] = {}

    def mint(kind: str, text: str) -> str:
        return rows.setdefault((kind, text), secrets.token_urlsafe(16))

    served = project_served(_run(".digline/acme/runs/qa/x.json"), mint)
    assert "SECRET" not in repr(served)
    assert redact(_run(".git/config"), NOTHING_EXTRA).redacted


# --------------------------------------------------------------------------- #
# The read boundary, in read_artifacts
# --------------------------------------------------------------------------- #


def _suite(*artifacts: Path) -> Suite:
    return Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=[Contains(needle="x")],
        cases=[Case(id="one")],
        artifacts=list(artifacts),
    )


@pytest.fixture
def perimeter(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "prompt.md").write_text("inside", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("TOKEN=abc123", encoding="utf-8")
    return root


def test_a_file_outside_the_perimeter_is_refused_before_it_is_read(
    perimeter: Path,
) -> None:
    with pytest.raises(UsageError) as caught:
        read_artifacts(
            _suite(Path("../outside.txt")), object(), perimeter, root=perimeter
        )
    message = str(caught.value)
    assert str((perimeter.parent / "outside.txt").resolve()) in message
    assert "artifacts" in message


def test_the_same_file_inside_the_perimeter_is_read(perimeter: Path) -> None:
    found = read_artifacts(
        _suite(Path("prompt.md")), object(), perimeter, root=perimeter
    )
    assert set(found) == {"prompt.md"}


def test_a_link_pointing_outward_is_outside(perimeter: Path) -> None:
    """Resolved first, as ADR 0007 §6 resolves: the link sits inside and the
    file it names does not."""
    (perimeter / "inside.txt").symlink_to(perimeter.parent / "outside.txt")
    with pytest.raises(UsageError):
        read_artifacts(_suite(Path("inside.txt")), object(), perimeter, root=perimeter)


class _TargetNamingAFile:
    """A target answering through `HasArtifacts`, as a `ProviderTarget` does
    for its prompt file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def artifacts(self) -> Sequence[Path]:
        return [self._path]


def test_a_target_answering_an_outside_path_is_refused_the_same_way(
    perimeter: Path,
) -> None:
    target = _TargetNamingAFile(perimeter.parent / "outside.txt")
    with pytest.raises(UsageError):
        read_artifacts(_suite(), target, perimeter, root=perimeter)


def test_the_perimeter_defaults_to_the_suite_directory(perimeter: Path) -> None:
    """`root` defaults to `base`, as the keys always did: the narrowest reading."""
    (perimeter / "eval").mkdir()
    with pytest.raises(UsageError):
        read_artifacts(_suite(Path("../prompt.md")), object(), perimeter / "eval")


# --------------------------------------------------------------------------- #
# End to end, through the command a person runs
# --------------------------------------------------------------------------- #

SUITE = """\
from pathlib import Path

from digline.core import Contains, Disclosure
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme",
    environment="staging",
    name="qa",
    assertions=[Contains(needle="Rome")],
    cases=[Case(id="capital-it")],
    artifacts=[%(artifacts)s],
    disclosure=Disclosure(%(disclosure)s),
)


def target(case):
    return Response(output="Rome", cost_usd=0.01)
"""


def _project(root: Path, *, artifacts: str, disclosure: str) -> None:
    (root / "suite.py").write_text(
        SUITE % {"artifacts": artifacts, "disclosure": disclosure}, encoding="utf-8"
    )
    (root / "prompt.md").write_text("Answer with Rome.\n", encoding="utf-8")


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-q")
    return root


def _run_suite(root: Path) -> str:
    done = cli(root, "run", "--suite", "suite.py")
    assert done.returncode == EXIT_OK, done.stderr
    return done.stdout.strip()


def _report(root: Path, out: Path, *extra: str) -> tuple[int, str]:
    done = cli(
        root,
        "report",
        "--suite",
        "suite.py",
        "--run",
        "latest",
        "--locale",
        "en",
        "--out",
        str(out),
        *extra,
    )
    return done.returncode, done.stderr


def test_run_refuses_a_python_suite_declaring_a_file_outside(
    repository: Path,
) -> None:
    """ADR 0042, test plan 1, through `run`: the `.py` form had no boundary."""
    (repository.parent / "outside.txt").write_text("TOKEN=abc123", encoding="utf-8")
    _project(repository, artifacts='Path("../outside.txt")', disclosure="")
    done = cli(repository, "run", "--suite", "suite.py")
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "outside.txt" in done.stderr
    assert not list((repository / ".digline").rglob("runs/*/*.json"))


def test_report_redacted_refuses_git_config_when_artifacts_are_disclosed(
    repository: Path,
) -> None:
    _project(
        repository,
        artifacts='Path("prompt.md"), Path(".git/config")',
        disclosure="artifacts=True",
    )
    _run_suite(repository)
    out = repository / "redacted.html"
    code, stderr = _report(repository, out, "--redacted")
    assert code == EXIT_USAGE, stderr
    assert ".git/config" in stderr
    assert not out.exists(), "a refused report must write no document"
    # The complete report stays on the developer's disk, where they own it.
    code, stderr = _report(repository, repository / "complete.html")
    assert code == EXIT_OK, stderr


def test_report_redacted_answers_when_artifacts_are_not_disclosed(
    repository: Path,
) -> None:
    _project(repository, artifacts='Path(".git/config")', disclosure="")
    _run_suite(repository)
    code, stderr = _report(repository, repository / "redacted.html", "--redacted")
    assert code == EXIT_OK, stderr


@pytest.mark.parametrize("disclosure", ["", "artifacts=True"])
def test_promote_refuses_git_config_whatever_the_disclosure(
    repository: Path, disclosure: str
) -> None:
    """And the baseline in place is neither written nor replaced."""
    _project(repository, artifacts='Path("prompt.md")', disclosure=disclosure)
    first = _run_suite(repository)
    promoted = cli(
        repository,
        "promote",
        "--suite",
        "suite.py",
        "--run",
        first,
        "--replacing",
        "none",
    )
    assert promoted.returncode == EXIT_OK, promoted.stderr
    (baseline,) = (repository / ".digline").glob("*/baselines/*.json")
    before = baseline.read_bytes()

    _project(
        repository,
        artifacts='Path("prompt.md"), Path(".git/config")',
        disclosure=disclosure,
    )
    second = _run_suite(repository)
    refused = cli(
        repository,
        "promote",
        "--suite",
        "suite.py",
        "--run",
        second,
        "--replacing",
        baseline_in(repository),
    )
    assert refused.returncode == EXIT_USAGE, refused.stderr
    assert ".git/config" in refused.stderr
    assert baseline.read_bytes() == before


def test_the_run_on_disk_still_records_the_file(repository: Path) -> None:
    """The exit boundary refuses the crossing, not the recording: the developer
    keeps the complete run, which is theirs (ADR 0042 §1)."""
    _project(repository, artifacts='Path(".git/config")', disclosure="")
    _run_suite(repository)
    (stored,) = (repository / ".digline").rglob("runs/qa/*.json")
    assert ".git/config" in stored.read_text(encoding="utf-8")


def test_a_case_folded_store_path_is_the_store_on_this_filesystem(
    repository: Path,
) -> None:
    """The measurement §3 rests on, kept where it can be re-run. On a
    case-insensitive filesystem `.DIGLINE/…` opens `.digline/…`; on a
    case-sensitive one it names nothing, and there is nothing to check."""
    store = repository / ".digline" / "acme"
    store.mkdir(parents=True)
    (store / "notes.txt").write_text("held", encoding="utf-8")
    folded = repository / ".DIGLINE" / "acme" / "notes.txt"
    if not folded.is_file():
        pytest.skip("this filesystem is case-sensitive")
    key = os.path.relpath(folded.resolve(), repository.resolve())
    assert barred_from_crossing(key) is not None, key
