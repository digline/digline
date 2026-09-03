"""The official image, gated from the repository.

The image itself is built and pushed by `docker-publish.yml`, which is where a
Docker daemon and a registry exist. What can be checked without either is
whether the *files* still agree with each other, and that is the whole of the
drift this pass can produce:

- the versions installed in the image are the versions this workspace declares;
- the tags come from the Dockerfile and are not typed a second time in the
  workflow, or a third time in the image's README;
- nothing reaches the registry before the quickstart has run inside the image
  and returned the exit codes the front page promises.

These run in the `gates` job with everything else. No daemon, no network.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "docker" / "Dockerfile"
IMAGE_README = ROOT / "docker" / "README.md"
WORKFLOW = ROOT / ".github" / "workflows" / "docker-publish.yml"

#: The scope statement, which is the promise the image makes. Compared with the
#: backticks taken out: the words are the contract, the Markdown around them is
#: not.
PROMISE = (
    "The official image runs any suite that depends only on digline and its "
    "plugins — the CI-gate case, HttpTarget against an external app. A suite "
    "with its own dependencies derives the image: "
    "FROM ghcr.io/digline/digline:<version> + install. "
    "No dynamic installs at runtime, ever."
)

#: Which `ARG` in the Dockerfile pins which package of this workspace.
PINS = {
    "DIGLINE_VERSION": "pyproject.toml",
    "DIGLINE_ANTHROPIC_VERSION": "packages/digline-anthropic/pyproject.toml",
    "DIGLINE_OPENAI_VERSION": "packages/digline-openai/pyproject.toml",
    "DIGLINE_BEDROCK_VERSION": "packages/digline-bedrock/pyproject.toml",
}


def dockerfile() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def pinned(arg: str) -> str | None:
    """The default value of a build argument, as the Dockerfile writes it."""
    found = re.search(rf"^ARG {arg}=(.+)$", dockerfile(), re.M)
    return found.group(1).strip() if found else None


def declared(pyproject: str) -> str:
    with (ROOT / pyproject).open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    assert isinstance(version, str)
    return version


def workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# One version number, in one place
# --------------------------------------------------------------------------- #


def test_the_image_pins_the_versions_this_workspace_declares() -> None:
    """The failure this prevents is an image that lags a release silently.

    Nothing at build time notices: `pip install digline==0.4.0` succeeds
    forever, and the gate keeps running the version before the one whose tag
    is on the image.
    """
    for arg, pyproject in PINS.items():
        assert pinned(arg) == declared(pyproject), (
            f"docker/Dockerfile pins {arg}={pinned(arg)} and {pyproject} "
            f"declares {declared(pyproject)}: the image would carry a version "
            "this repository does not"
        )


def test_the_workflow_writes_no_version_of_its_own() -> None:
    """It reads the Dockerfile instead. A number written twice disagrees."""
    version = declared("pyproject.toml")
    assert version not in workflow(), (
        f"docker-publish.yml names {version} literally; the version belongs in "
        "docker/Dockerfile, which the workflow already reads it out of"
    )
    assert "sed -n 's/^ARG DIGLINE_VERSION=//p' docker/Dockerfile" in workflow()


def test_the_image_readme_documents_the_version_it_ships() -> None:
    """Every pinned tag on the page is the version in the Dockerfile.

    `<version>` and `latest` are the two placeholders that mean no version.
    """
    version = declared("pyproject.toml")
    tags = set(
        re.findall(
            r"ghcr\.io/digline/digline:([\w.<>-]+)",
            IMAGE_README.read_text(encoding="utf-8"),
        )
    )
    assert tags - {"<version>", "latest"} == {version}, (
        f"docker/README.md documents the tags {sorted(tags)}, and this "
        f"workspace is at {version}"
    )


# --------------------------------------------------------------------------- #
# The promise, and the order the workflow keeps it in
# --------------------------------------------------------------------------- #


def test_the_image_readme_carries_the_promise_verbatim() -> None:
    """The scope statement defines what the image is for, so it is pinned like
    an interface rather than left to a rewrite that softens it."""
    page = IMAGE_README.read_text(encoding="utf-8").replace("`", "")
    assert " ".join(PROMISE.split()) in " ".join(page.split())


def test_nothing_is_pushed_before_the_quickstart_has_run() -> None:
    """A smoke test that runs after the push tests an image people already have.

    `needs:` is what orders them, and `push: true` living in the other job is
    what keeps the smoke job from being the one that publishes.
    """
    text = workflow()
    smoke, _, publish = text.partition("\n  publish:")
    assert publish, "the workflow has no `publish` job"
    assert re.search(r"^    needs: smoke$", publish, re.M), (
        "the publish job does not declare `needs: smoke`, so a broken image "
        "would reach GHCR while the smoke test was still running"
    )
    assert "push: true" not in smoke, "the smoke job pushes; only publish may"
    assert "packages: write" not in smoke


def test_the_smoke_test_asserts_both_exit_codes() -> None:
    """`0` fine and `1` got worse. A smoke test that only asserts the image
    starts would pass on an image that answers every suite the same way."""
    smoke = workflow().partition("\n  publish:")[0]
    assert "digline run --suite suite.py" in smoke
    assert "digline compare --suite suite.py --run latest" in smoke
    # The break, and the exit code it has to produce.
    assert 'if [ "$status" -ne 1 ]' in smoke


def test_the_smoke_test_checks_the_write_path_on_a_mounted_volume() -> None:
    """Decision 2: `.digline/` lives in the user's repository. In the image
    that is a bind mount, written by a non-root user, and it is the one thing
    about this image that cannot be verified by reading it."""
    smoke = workflow().partition("\n  publish:")[0]
    assert '-v "$work:/work"' in smoke
    assert "$work/.digline/northwind/baselines/support.json" in smoke
    assert '! -user "$(id -u)"' in smoke


# --------------------------------------------------------------------------- #
# The shape of the image itself
# --------------------------------------------------------------------------- #


def test_the_image_runs_as_a_user_that_is_not_root() -> None:
    text = dockerfile()
    assert re.search(r"^USER digline$", text, re.M)
    # After the installs, or it would be a non-root user who cannot install.
    assert text.index("RUN pip install") < text.index("USER digline")


def test_the_entrypoint_is_the_cli_in_the_mounted_repository() -> None:
    """`digline` at `/work`: every argument after the image name is the command
    line the reader would have typed locally."""
    text = dockerfile()
    assert 'ENTRYPOINT ["digline"]' in text
    assert re.search(r"^WORKDIR /work$", text, re.M)
