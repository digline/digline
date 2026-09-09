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
CI = ROOT / ".github" / "workflows" / "ci.yml"
SMOKE = ROOT / "docker" / "smoke.sh"

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


def ci() -> str:
    return CI.read_text(encoding="utf-8")


def smoke() -> str:
    return SMOKE.read_text(encoding="utf-8")


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
    text = smoke()
    assert "digline run --suite suite.py" in text
    assert "digline compare --suite suite.py --run latest" in text
    # The break, and the exit code it has to produce.
    assert 'if [ "$status" -ne 1 ]' in text


def test_the_smoke_test_checks_the_write_path_on_a_mounted_volume() -> None:
    """Decision 2: `.digline/` lives in the user's repository. In the image
    that is a bind mount, written by a non-root user, and it is the one thing
    about this image that cannot be verified by reading it."""
    text = smoke()
    assert '-v "$work:/work"' in text
    assert "$work/.digline/northwind/baselines/support.json" in text
    assert '! -user "$(id -u)"' in text


def test_the_smoke_test_is_a_script_both_workflows_run() -> None:
    """One smoke, two callers. `ci.yml` runs it on every change under
    `docker/`, `docker-publish.yml` runs it before the push — and the second is
    the one guarding a release, so it must not be the copy that fell behind.

    What is checked is that neither workflow *inlines* it: a `docker run` of
    the image spelled out in YAML is the copy starting.
    """
    assert SMOKE.is_file(), "docker/smoke.sh is gone"
    # Each workflow's image job, not the whole file: `ci.yml` also runs the
    # examples against PyPI, and those really do call `digline compare`.
    jobs = {
        "docker-publish.yml": workflow().partition("\n  publish:")[0],
        "ci.yml": ci()
        .partition("\n  image:")[2]
        .partition("\n  examples-from-pypi:")[0],
    }
    for name, job in jobs.items():
        assert job, f"{name} has no image job to read"
        assert "docker/smoke.sh digline:smoke" in job, (
            f"{name} does not run docker/smoke.sh; the smoke test belongs in "
            "one file that both workflows call"
        )
        assert "digline compare --suite" not in job, (
            f"{name} spells the quickstart out inline. That is the second copy "
            "of docker/smoke.sh, and copies drift."
        )


def test_the_smoke_script_is_executable() -> None:
    """Both workflows invoke it as a command, not as `bash smoke.sh`."""
    assert SMOKE.stat().st_mode & 0o111, "docker/smoke.sh is not executable"


def test_ci_builds_the_image_without_pushing_it() -> None:
    """The gap this closes: the only build was the one that publishes, so the
    first time a broken Dockerfile was noticed, the version it pins was already
    spent on PyPI.

    The job is gated on the paths that decide what the image *is*. The
    Dockerfile installs digline from the index rather than from this tree, so a
    change under `src/` cannot change the image being built here.
    """
    text = ci()
    job = text.partition("\n  image:")[2].partition("\n  examples-from-pypi:")[0]
    assert job, "ci.yml has no `image` job"
    assert "load: true" in job, "the image is never loaded, so it cannot be run"
    assert "push: true" not in job, "ci.yml must not push; that is the release's job"
    assert "packages: write" not in ci(), (
        "ci.yml grants write access to the registry, which it has no use for"
    )
    assert "docker/smoke.sh" in job


def test_the_image_job_is_gated_on_what_the_image_is_made_of() -> None:
    """A skipped job still reports, which a workflow-level `on: paths:` would
    not — that leaves a required check waiting forever."""
    text = ci()
    assert "needs: image-touched" in text
    assert "if: needs.image-touched.outputs.build == 'true'" in text
    gate = text.partition("\n  image-touched:")[2].partition("\n  image:")[0]
    # The pattern the job actually greps with, not the prose around it: a
    # comment naming `docker/` would otherwise satisfy this while the filter
    # matched something else entirely.
    pattern = re.search(r"grep -qE '([^']+)'", gate)
    assert pattern is not None, (
        "the gate no longer decides with a `grep -qE '<pattern>'`; if it "
        "decides some other way, read that instead of deleting this"
    )
    paths = pattern.group(1)
    assert "docker/" in paths, f"the filter {paths!r} does not name docker/"
    assert "docker-publish" in paths, (
        f"the filter {paths!r} does not cover the publishing workflow, so a "
        "change to the job that builds the release image would not build it"
    )
    assert "ci" in paths, (
        f"the filter {paths!r} does not cover ci.yml, so an edit to this very "
        "job would not run it"
    )


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


def test_the_readme_lists_the_commands_the_image_can_run() -> None:
    """The image's command list, pinned to the parser it describes.

    `docker/README.md` tells a reader that every argument after the image name
    is the command line they would have typed locally, then names them. That
    list was typed by hand and had no relationship to `build_parser()`: `diff`
    shipped in 0.6.0 and the sentence still stopped at six commands, which the
    0.6.0 release audit found by counting rather than by anything failing.

    **`view` is the one exclusion, and it is deliberate.** It serves HTTP on a
    port, and the `docker run` this page documents publishes none — a reader
    who followed the sentence would get a server they cannot reach. Every other
    subcommand reads and writes the mounted repository and nothing else, which
    is exactly what the image is for.
    """
    from digline.cli.main import build_parser

    # Read off the usage line — `{run,compare,diff,...}` — rather than out of
    # `parser._actions`. It is the parser's own public rendering, it is what
    # `digline --help` shows a reader, and it needs no private argparse type.
    usage = build_parser().format_usage()
    choices = re.search(r"\{([a-z,]+)\}", usage)
    assert choices is not None, f"no subcommand list in the usage line: {usage!r}"
    expected = set(choices.group(1).split(",")) - {"view"}

    text = (ROOT / "docker" / "README.md").read_text(encoding="utf-8")
    found = re.search(
        r"the command line you would have typed locally — (.+?)\. The exit code",
        text,
        re.S,
    )
    assert found is not None, (
        "docker/README.md no longer has the sentence this gate reads. If it "
        "moved, move the pattern with it: the list in it is written by hand."
    )
    listed = set(re.findall(r"`([a-z]+)`", found.group(1)))

    assert listed == expected, (
        f"docker/README.md names {sorted(listed)} and the CLI offers "
        f"{sorted(expected)} (every subcommand but `view`, which needs a "
        "published port). Add the missing ones to the sentence, or — if a "
        "command genuinely cannot run in the image — exclude it here with the "
        "reason, the way `view` is excluded."
    )
