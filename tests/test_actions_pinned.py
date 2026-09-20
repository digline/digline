"""The gate on the actions the workflows use, and on each way it must fail.

Every refusal is tested next to the case it must let through: a gate that
fails everything passes each "must fail" test, and one that fails nothing
passes each "must pass" test, so only the pair says the gate discriminates.
"""

from __future__ import annotations

from pathlib import Path

from actions import WORKFLOWS, problems, used, workflows

ROOT = Path(__file__).resolve().parents[1]

CHECKOUT = "3d3c42e5aac5ba805825da76410c181273ba90b1"  # actions/checkout v7.0.1
CODEQL = "b96794f015dfd88f77b49b1c93e0fa7110f94c63"  # github/codeql-action v4.38.0
UV = "bec219d24cd3e171d82865faccec33120bb574f4"  # astral-sh/setup-uv v10.1.0
TOKEN = (
    "a0d050558c7a879dddc07b2160b9a07eb0e9ebc7"  # create-github-app-token v3.0.0-beta.6
)

_HEADER = "name: t\non: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"


def _step(ref: str, comment: str = "") -> str:
    """A step that uses an action, as a workflow writes it."""
    return f"      - uses: {ref}{' # ' + comment if comment else ''}\n"


_PINNED = _step(f"actions/checkout@{CHECKOUT}", "v7.0.1")


def _repo(tmp_path: Path, *steps: str) -> Path:
    folder = tmp_path / WORKFLOWS
    folder.mkdir(parents=True)
    (folder / "t.yml").write_text(_HEADER + _PINNED + "".join(steps), encoding="utf-8")
    return tmp_path


def test_this_repository_passes() -> None:
    assert problems(ROOT) == []


def test_this_repository_uses_actions_and_every_one_is_a_commit() -> None:
    refs = used(ROOT)
    assert len(refs) > 20
    assert all("@" in ref and len(ref.split("@")[1]) == 40 for ref in refs), refs


def test_every_workflow_is_read() -> None:
    names = {path.name for path in workflows(ROOT)}
    assert {"ci.yml", "publish.yml", "codeql.yml", "scorecard.yml"} <= names


# What passes.


def test_a_pin_with_its_exact_version_passes(tmp_path: Path) -> None:
    assert problems(_repo(tmp_path)) == []


def test_a_prerelease_after_the_patch_is_a_version(tmp_path: Path) -> None:
    step = _step(f"actions/create-github-app-token@{TOKEN}", "v3.0.0-beta.6")
    assert problems(_repo(tmp_path, step)) == []


def test_a_local_action_is_not_pinned_this_way(tmp_path: Path) -> None:
    assert problems(_repo(tmp_path, _step("./.github/actions/thing"))) == []


def test_a_command_that_merely_says_uses_is_not_an_action(tmp_path: Path) -> None:
    step = "      - run: echo uses: actions/checkout@v7\n"
    assert problems(_repo(tmp_path, step)) == []


# What fails.


def _refusal(tmp_path: Path, step: str) -> str:
    found = problems(_repo(tmp_path, step))
    assert len(found) == 1, found
    return found[0]


def test_a_tag_fails(tmp_path: Path) -> None:
    assert "is used at 'v7'" in _refusal(tmp_path, _step("actions/checkout@v7"))


def test_a_branch_fails(tmp_path: Path) -> None:
    assert "is used at 'main'" in _refusal(tmp_path, _step("actions/checkout@main"))


def test_a_short_sha_fails(tmp_path: Path) -> None:
    step = _step(f"actions/checkout@{CHECKOUT[:7]}")
    assert f"is used at '{CHECKOUT[:7]}'" in _refusal(tmp_path, step)


def test_a_sha_one_character_short_fails(tmp_path: Path) -> None:
    step = _step(f"actions/checkout@{CHECKOUT[:-1]}")
    assert "used at a full 40-character commit" in _refusal(tmp_path, step)


def test_no_version_at_all_fails(tmp_path: Path) -> None:
    assert "is used at nothing" in _refusal(tmp_path, _step("actions/checkout"))


def test_a_pin_with_no_comment_fails(tmp_path: Path) -> None:
    step = _step(f"actions/checkout@{CHECKOUT}")
    assert "the exact version it is at is not written" in _refusal(tmp_path, step)


def test_a_comment_naming_a_major_alone_fails(tmp_path: Path) -> None:
    step = _step(f"github/codeql-action/init@{CODEQL}", "v4")
    assert "a major on its own" in _refusal(tmp_path, step)


def test_a_comment_naming_a_major_and_a_minor_fails(tmp_path: Path) -> None:
    step = _step(f"astral-sh/setup-uv@{UV}", "v10.1")
    assert "the exact version it is at is not written" in _refusal(tmp_path, step)


def test_a_comment_naming_a_branch_fails(tmp_path: Path) -> None:
    step = _step(f"actions/checkout@{CHECKOUT}", "main")
    assert "the exact version it is at is not written" in _refusal(tmp_path, step)


def test_every_workflow_of_the_folder_is_read_and_says_which(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    other = _HEADER + _step("actions/checkout@v7")
    (root / WORKFLOWS / "u.yaml").write_text(other, encoding="utf-8")
    found = problems(root)
    assert len(found) == 1, found
    assert found[0].startswith(".github/workflows/u.yaml:7:"), found
