"""What a suite that is data is allowed to read.

ADR 0007 §5 closed the **code** boundary and said so loudly: no `python =`, no
`import =`, no dotted path to a callable. That boundary held. The **read**
boundary was never drawn, and a file with no Python in it could name
`/etc/passwd` as an artifact and have its contents recorded in every run.

The perimeter is the **repository**, not the suite's own directory — a suite in
`eval/` naming `../prompts/system.md` is reading a file its own project owns,
which is the ordinary layout of a repository that keeps its evaluation beside
what it evaluates. So the two tests that matter are the pair: the escape is
refused, and the ordinary layout still works.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from digline.core import Artifact, Contains
from digline.host import UsageError, load_suite, read_artifacts
from digline.run import Case, Suite

CASES = '[{"id": "one", "vars": {"question": "q"}}]'

SUITE = """
[suite]
tenant = "acme"
environment = "staging"
name = "qa"
cases = {cases!r}
{artifacts}

[target]
type = "http"
url = "http://127.0.0.1:8730/answer"
output_path = "data.answer"

  [target.body]
  question = "case.vars.question"

[[assertions]]
type = "contains"
needle = "x"
"""


def write(
    root: Path, *, where: str = ".", cases: str = "cases.json", artifacts: str = ""
) -> Path:
    """A TOML suite in `root/where`, with `cases.json` beside it."""
    directory = root / where
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "cases.json").write_text(CASES, encoding="utf-8")
    path = directory / "suite.toml"
    path.write_text(SUITE.format(cases=cases, artifacts=artifacts), encoding="utf-8")
    return path


def test_an_artifact_outside_the_perimeter_is_refused(tmp_path: Path) -> None:
    """The finding itself: a data file naming a path anywhere on the machine."""
    root = tmp_path / "repo"
    secret = tmp_path / "secret.env"
    secret.write_text("TOKEN=abc123", encoding="utf-8")
    path = write(root, artifacts='artifacts = ["../secret.env"]')

    with pytest.raises(UsageError) as refusal:
        load_suite(str(path), root=root)

    # The field and the resolved path, because `../secret.env` on its own does
    # not tell a reader which boundary it crossed.
    assert "`artifacts`" in str(refusal.value)
    assert str(secret.resolve()) in str(refusal.value)
    assert str(root.resolve()) in str(refusal.value)


def test_an_absolute_artifact_is_refused(tmp_path: Path) -> None:
    """`/etc/hosts` and not a relative climb: the traversal is the obvious
    shape, but a data file may simply state the path it wants."""
    root = tmp_path / "repo"
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    path = write(root, artifacts=f'artifacts = ["{outside}"]')
    with pytest.raises(UsageError, match="`artifacts` names"):
        load_suite(str(path), root=root)


def test_cases_cannot_climb_out_either(tmp_path: Path) -> None:
    """`cases` is read during the load, so it needs the check at the same place
    rather than at the one call that reads artifacts."""
    root = tmp_path / "repo"
    (tmp_path / "elsewhere.json").write_text(CASES, encoding="utf-8")
    path = write(root, cases="../elsewhere.json")
    with pytest.raises(UsageError, match="`cases` names"):
        load_suite(str(path), root=root)


def test_a_target_path_cannot_climb_out_either(tmp_path: Path) -> None:
    """Every path a data suite can write, which is ADR 0007 §6's own phrase: a
    prompt file a `[target]` names reaches the run exactly as an artifact does,
    so a check on `artifacts` alone would have left the door beside it open.

    A provider target and not an `http` one because `HttpTarget` declares no
    `Path` parameter — `prompt_file` is where this format can name a file
    without calling it an artifact.
    """
    pytest.importorskip("digline_anthropic")
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "prompt.md").write_text("Answer: {{question}}", encoding="utf-8")
    (root / "cases.json").write_text(CASES, encoding="utf-8")
    (root / "suite.toml").write_text(
        """
[suite]
tenant = "acme"
environment = "staging"
name = "qa"
cases = "cases.json"

[target]
type = "provider"
provider = "anthropic/claude-haiku-4-5"
prompt_file = "../prompt.md"
max_tokens = 200

[[assertions]]
type = "contains"
needle = "x"
""",
        encoding="utf-8",
    )
    with pytest.raises(UsageError, match="`prompt_file` names"):
        load_suite(str(root / "suite.toml"), root=root)


def test_a_sibling_directory_inside_the_repository_is_fine(tmp_path: Path) -> None:
    """The ruling, stated as a test: the perimeter is the repository.

    A suite in `eval/` reading `../prompts/system.md` is the layout this format
    is for. A boundary drawn at the suite's own directory would have refused it
    and made the fix worse than the finding.
    """
    root = tmp_path / "repo"
    (root / "prompts").mkdir(parents=True)
    (root / "prompts" / "system.md").write_text("You are helpful.", encoding="utf-8")
    path = write(root, where="eval", artifacts='artifacts = ["../prompts/system.md"]')

    suite, _loaded = load_suite(str(path), root=root)
    found = read_artifacts(suite, object(), path.parent, root=root)
    # Keyed from the repository, so the file is named where it actually lives.
    assert set(found) == {"prompts/system.md"}


def test_an_escape_can_never_hide_behind_a_basename(tmp_path: Path) -> None:
    """A `.py` suite may still read outside the repository — it is code, and
    code can already open anything. What it may not do is be recorded as
    something else: `/etc/hosts` used to arrive in the run keyed as `hosts`,
    which is the same name a file in the project would have had.
    """
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "secret.env"
    outside.write_text("TOKEN=abc123", encoding="utf-8")

    suite = Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=[Contains(needle="x")],
        cases=[Case(id="one")],
        artifacts=[outside],
    )
    found = read_artifacts(suite, object(), root, root=root)
    assert set(found) == {"../secret.env"}, "the escape must be visible in the key"


def test_read_artifacts_without_a_root_keeps_the_old_keys(tmp_path: Path) -> None:
    """`root` defaults to `base`, so a caller that has not been updated gets
    exactly what it got before — the published signature did not change under
    anybody."""
    (tmp_path / "prompt.md").write_text("hello", encoding="utf-8")
    suite = Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=[Contains(needle="x")],
        cases=[Case(id="one")],
        artifacts=[Path("prompt.md")],
    )
    assert set(read_artifacts(suite, object(), tmp_path)) == {"prompt.md"}


def test_the_recorded_artifact_is_unchanged_for_the_ordinary_layout(
    tmp_path: Path,
) -> None:
    """The compatibility line: a suite at the root of its project with its
    prompt beside it keys identically before and after. That is every example
    in this repository, and the reason the change is a patch."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "system.txt").write_text("x", encoding="utf-8")
    suite = Suite(
        tenant="acme",
        environment="staging",
        name="qa",
        assertions=[Contains(needle="x")],
        cases=[Case(id="one")],
        artifacts=[Path("prompts/system.txt")],
    )
    both = (
        read_artifacts(suite, object(), tmp_path),
        read_artifacts(suite, object(), tmp_path, root=tmp_path),
    )
    assert set(both[0]) == set(both[1]) == {"prompts/system.txt"}
    assert isinstance(both[1]["prompts/system.txt"], Artifact)
