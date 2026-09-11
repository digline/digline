"""One version number, and every place that claims to know it.

`pyproject.toml` is the number the release bumps. Everything else either reads
it or is a record of a version that has already shipped, and the difference
between the two is the whole of this file.

The failure it exists for is small and had already happened: `__version__` in
`digline/__init__.py` said `0.4.0` while `pyproject.toml` said `0.5.0`. Nothing
noticed, because a hand-written copy of a number is only wrong on the days
nobody reads it. That one is now derived from the installed distribution and
cannot drift at all — a claim that *cannot* go stale beats a claim that is
merely gated — and the rest are held here.

The gate has two halves:

- **`LIVE`** names the places that must say the current version, and pins each
  one to `pyproject.toml`. A release that bumps the version and forgets one of
  them fails here.
- **the sweep** reads every version literal in the documented files and demands
  it be either the current version or a registered record. Bump the version and
  every unregistered claim in the repository lights up at once, which is the
  half that keeps this file honest as the repository grows: a new page carrying
  a version number cannot pass without someone deciding which kind it is.

`RECORDED` is therefore an allowance for numbers that are *not* the current
one — "shipped in 0.2.0", a worked example, a third-party pin, or a plan that
names the release it is waiting for. Registering the current version there is
refused, because that would be exactly the way to silence a claim that had gone
stale; and it is what makes a forward reference read itself back, since the day
its version ships the entry becomes illegal and somebody has to say whether the
sentence is now history or now wrong.

The example READMEs are swept too, since the 0.6.0 audit. They had been outside
it, which was backwards: an example is the page most likely to carry a version,
because it is the one telling a reader what to install, and the class with the
worst record for going stale unnoticed. What the sweep found there on its first
run was five third-party pins, now registered — which is the point, since a
number nobody classified is a number nobody is watching.

Three trees are out of the sweep and stay out. `CHANGELOG.md` is dated history
in every line, and `docs/adr/` is immutable once a decision is accepted:
pinning either to the current release would be asking a record to change.
`tests/` is out because a test fixture names versions for a living — the floor
table in `test_plugin_floors.py` is nothing else — and sweeping them would
register more noise than it caught.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Three components, not four: `127.0.0.1` is an address and `0.28.1` is a
#: version, and the lookarounds are what tells them apart.
#:
#: The trailing lookahead is `(?!\.?\d)` and not `(?![\d.])`, which was a hole:
#: a version that **ends a sentence** was defeated by its own full stop, so
#: "shipped in 0.5.0." was invisible to the sweep while "shipped in 0.5.0 ." was
#: not. Three lines were hiding behind it, found while writing the release
#: notes for 0.7.1. The rule it has to keep is only that a fourth component
#: disqualifies — `.1` after `127.0.0` — and a dot followed by a non-digit is
#: punctuation, not a component.
VERSION = re.compile(r"(?<![\d.])\d+\.\d+\.\d+(?!\.?\d)")


def current() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    assert isinstance(version, str)
    return version


#: Every file the sweep reads. Anything not here is unguarded, so a new page
#: that names a version belongs in this list rather than outside it.
def swept() -> list[Path]:
    files = [
        path
        for path in ROOT.glob("*.md")
        # Written history in every line; and the local file is not committed.
        if path.name not in {"CHANGELOG.md", "CLAUDE.local.md"}
    ]
    files += [ROOT / "docker" / "README.md", ROOT / "docker" / "Dockerfile"]
    files += sorted(p for p in (ROOT / "src").rglob("*.py"))
    # `packages/` too, since 0.7.1. It had been outside, and the gap was not
    # theoretical: `digline_mcp` hand-wrote the version it advertises to every
    # MCP client, and nothing here could see it — the same shape as the
    # `__version__` drift at the top of this file, in the one tree the sweep
    # did not read. Both are derived now, so this catches the next one instead
    # of the last one. READMEs included: a package README tells a reader what
    # to install, which is the class with the worst record for going stale.
    # `src` and not the whole tree, for the same reason the root `tests/` is
    # out: a test names versions for a living, and `test_perimeter.py` saying
    # "until 0.1.1 nothing enforced this" is a sentence about history, not a
    # claim that could go stale.
    files += sorted(p for p in (ROOT / "packages").glob("*/src/**/*.py"))
    files += sorted((ROOT / "packages").glob("*/README.md"))
    files += sorted(p for p in (ROOT / "docs").rglob("*.md") if "adr" not in p.parts)
    files += sorted((ROOT / ".claude").rglob("*.md"))
    # The example READMEs. They were outside the sweep until the 0.6.0 audit,
    # which is backwards: an example is the page most likely to name a version,
    # because it is the one telling a reader what to install, and the class with
    # the worst record for going stale unnoticed.
    files += sorted((ROOT / "examples").glob("*/README.md"))
    return [path for path in files if path.is_file()]


#: file → literal → why it is a record and not a claim about this release.
#: A literal equal to the current version must never appear here; the test
#: below refuses it.
RECORDED: dict[str, dict[str, str]] = {
    "AGENTS.md": {
        "0.4.0": "'the one case in 0.4.0' — the state of a shipped release",
    },
    ".claude/skills/operating-digline/SKILL.md": {
        "0.4.0": "the byte-for-byte mirror of AGENTS.md, gated by test_agents.py",
    },
    "RELEASING.md": {
        "0.1.0": "a worked example of the tag format, with invented numbers",
        "0.6.0": "'v0.6.0 was the tag that exercised it' — the release that "
        "first ran the new-package section, said as history rather than plan",
        "0.1.1": "the same worked example",
        "0.1.3": "the same worked example",
        "0.2.0": "'v0.2.0 was tagged after a check that ran ruff' — what happened",
        "0.3.0": "'skipping it is what v0.3.0 cost' — the same",
        "0.4.0": "'a v0.4.0 rebuild sent an hour after the release' — the same",
        "0.5.0": "'it has failed open once, on v0.5.0' — the release the "
        "reviewer gate did not hold on, which is why the approvals endpoint is "
        "worth reading rather than the run's green",
        "0.7.0": "'six of eight legs installed 0.7.0 and passed' — the run that "
        "showed why the index check needs exact pins",
        "0.8.1": "'It shipped as 0.8.1 the same day' — the release the "
        "delta-pass rule was earned on, told as what happened. The rule is the "
        "standing one; this number is the morning it came from",
        "0.7.1": "the release that added the pypi-side index check and taught "
        "this file the two expected reds — five sentences about what happened "
        "on that release morning, timings and all. History, and the reason the "
        "'After the tag' section exists",
        "0.7.2": "'Step 3 no longer exists, since 0.7.2' — the release that "
        "replaced the hand-kept publish roster with one derived from dist/. "
        "What the runbook no longer asks anyone to do, dated",
        "0.8.0": "three sentences about the release that earned the delta-pass "
        "section — the one whose new surface leaked a resolved model id, whose "
        "finish_raw and ToolsCalled came back clean, and whose follow-on run "
        "lost a propagation race on two legs. History, timings and all, like "
        "the 0.7.1 entries above",
    },
    "README.md": {
        "0.5.0": "'since 0.5.0 the suite may be written as data' — when the "
        "declarative format landed. The Status line above it is the live claim "
        "and is pinned in LIVE",
    },
    "ROADMAP.md": {
        "0.1.0": "digline-mcp's own debut version, not a digline one — the "
        "line says the two shipped on the same tag",
        "0.2.0": "'shipped in 0.2.0' — when a decision landed",
        "0.3.0": "'extended in 0.3.0' — the same",
        "0.5.0": "'shipped in 0.5.0', 'real from 0.5.0', and the image's tag "
        "row — what landed in that release",
        "0.6.0": "'what 0.6.0 shipped: digline.wire and OUTPUT_VERSION', and "
        "'an MCP server shipped in 0.6.0' — two lines about what landed then",
        "0.7.0": "'0.7.0 closed the last gap underneath it' — which release "
        "made Track B's exit gate hold, and 'Shipped in 0.7.0' on the item "
        "below it. Both name the release the work landed in; 0.7.1 is a "
        "security patch and closed neither",
        "0.8.0": "three lines about what 0.8.0 landed — the plugin contract "
        "widening on Track A, the observed identity on Track B, and the offline "
        "half of Track D's trajectory item. 0.8.1 is a security patch and "
        "landed none of them",
    },
    "docs/api.md": {
        "0.6.0": "'These moved in 0.6.0.' — the release that promoted "
        "`load_suite` and its neighbours out of `digline.cli` into "
        "`digline.host`, said as history. Hidden from the sweep until the "
        "trailing-period hole in VERSION was closed",
    },
    "SECURITY.md": {
        "0.5.0": "'From 0.5.0 the declarative suite format refuses an api_key "
        "key by name' — when the refusal landed",
        "0.7.2": "'was fixed in 0.7.2' — the symlink escape, named so the "
        "scope paragraph says which side of the line it fell on and when. A "
        "fact about a shipped release, not a claim about this one",
        "0.7.1": "the release the three published advisories were cut against, "
        "and the one whose four fixes the adversarial pass went back over. The "
        "advisory policy has to name a version or it is describing nothing",
        "0.8.0": "the release whose new surface the delta-pass read, in the "
        "worked example of why that rule exists",
        "0.8.1": "what went out before the announcements because that pass "
        "found something. Same sentence, other end of it",
    },
    "examples/external-app/README.md": {
        "0.1.2": "'Needs digline 0.1.2 (HttpTarget)' — the release the feature "
        "arrived in. A floor, so it cannot go stale; the cap in the example's "
        "pyproject.toml is what decides what a reader installs",
    },
    "examples/langchain/README.md": {
        "1.3.18": "the langchain version the example was run against, not a "
        "digline one. Pinned to the example's own lock by "
        "tests/test_examples.py, which is where a third-party version belongs",
        "1.6.1": "langchain-core, beside it, held by the same test",
    },
    "examples/llamaindex/README.md": {
        "0.14.24": "the llama-index-core version the example was run against, "
        "not a digline one. Pinned to the example's own pyproject.toml by "
        "tests/test_examples.py, which is where a third-party version belongs",
    },
    "examples/langchain4j/README.md": {
        "0.3.0": "'Needs digline 0.3.0 (config_path on HttpTarget)' — the same "
        "kind of floor",
    },
    "docker/README.md": {
        "0.4.0": "a deliberate example of building an image for a release "
        "that exists — it named 0.3.1 until that turned out never to have "
        "shipped, which is the same class of claim this file gates",
        "0.28.1": "an httpx pin in an example Dockerfile, not a digline version",
        "2.2.3": "a pandas pin in the same example",
    },
    "docker/Dockerfile": {
        "0.4.0": "the plugin versions, pinned to their own pyproject files by "
        "tests/test_docker.py",
    },
    "src/digline/report/pages.py": {
        "0.4.0": "'0.4.0 rendering compare_page' — the state of a shipped release",
    },
    # Two comments ADR 0009 asked for: each names the release in which the
    # boundary bug it describes was written, which is the whole point of the
    # sentence. Neither is a claim about what digline is at now.
    "src/digline/core/aggregate.py": {
        "0.6.0": "'the rounding arrived here in 0.6.0 as a crash fix' — where "
        "the ruling ADR 0009 wrote down had been made without being written",
    },
    "src/digline/core/diff.py": {
        "0.6.0": "'the unrounded subtraction was written here in 0.6.0' — the "
        "second site of the same defect, and why the record names call sites",
    },
    # The two comments the 0.7.2 security fixes left behind, in the same shape
    # as the pair above: each names the release in which the hole it describes
    # was closed, which is the whole point of the sentence.
    "src/digline/store/file_store.py": {
        "0.7.2": "'until 0.7.2 nothing did' — a checked name proved a segment "
        "safe and never where it led. The release that closed it, said as "
        "history beside the code that closes it",
    },
    "src/digline/targets/http.py": {
        "0.7.2": "'Unguarded until 0.7.2' — the `InvalidURL` that escaped "
        "`preflight`'s handler and reached stderr quoting the credential. "
        "Same shape: the release the handler arrived in",
    },
    # Same shape again, from the other side: the release whose diagnosis the
    # fold was throwing away, named where the fold now keeps it.
    "src/digline/core/sampling.py": {
        "0.8.0": "'since 0.8.0 a mute judge says which ending the provider "
        "declared' — the release the sentence arrived in, said beside the code "
        "that stopped replacing it. History, not a claim about now",
    },
    "src/digline/core/run.py": {
        "0.8.0": "'A run digline 0.8.0 wrote from a compatible endpoint' — the "
        "one release whose redacted documents this refusal actually rejects, "
        "named in the message's own comment so the next reader knows which "
        "files are meant. History from the moment 0.8.1 shipped",
        "0.8.1": "'is withheld from 0.8.1' — the release the withholding began "
        "in, which is what tells a reader which stored documents the refusal "
        "above is about. The same sentence as the entry beside it, from the "
        "other end: one names the release that leaked, one the release that "
        "stopped",
    },
}


#: Where the *current* version is written by hand. Each one is pinned, so a
#: release that bumps `pyproject.toml` and stops there fails here by name
#: rather than somewhere downstream.
LIVE: dict[str, str] = {
    "README.md": r"^## Status\s*\n+`([^`]+)`",
    "docker/Dockerfile": r"^ARG DIGLINE_VERSION=(\S+)$",
    "docker/README.md": r"^\| `([\d.]+)` \| that version of digline",
}


def test_the_live_claims_say_what_pyproject_says() -> None:
    version = current()
    for name, pattern in LIVE.items():
        text = (ROOT / name).read_text(encoding="utf-8")
        found = re.search(pattern, text, re.M)
        assert found is not None, (
            f"{name} no longer has the line this gate reads (pattern "
            f"{pattern!r}). If it moved, move the pattern with it rather than "
            "deleting the entry: the number in that line is written by hand."
        )
        assert found.group(1) == version, (
            f"{name} says {found.group(1)} and pyproject.toml says {version}. "
            "The release bumps pyproject; this one is written by hand and has "
            "fallen behind."
        )


def test_the_minor_tag_follows_the_release() -> None:
    """The image's tag table also promises a `<major>.<minor>` tag, and that
    one is a different shape from the rest — it went stale unnoticed, reading
    `0.4` after 0.5.0 had shipped."""
    version = current()
    minor = ".".join(version.split(".")[:2])
    text = (ROOT / "docker" / "README.md").read_text(encoding="utf-8")
    found = re.search(r"^\| `([\d.]+)` \| the newest patch on that minor", text, re.M)
    assert found is not None, "docker/README.md has no minor-tag row"
    assert found.group(1) == minor, (
        f"docker/README.md documents the minor tag `{found.group(1)}` while "
        f"this workspace is at {version}, whose minor tag is `{minor}`"
    )


def test_no_version_literal_is_left_unaccounted_for() -> None:
    """The sweep. Every number is the current one or a registered record."""
    version = current()
    unaccounted: list[str] = []
    for path in swept():
        name = path.relative_to(ROOT).as_posix()
        allowed = RECORDED.get(name, {})
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for literal in VERSION.findall(line):
                if literal == version or literal in allowed:
                    continue
                unaccounted.append(f"{name}:{line_number}: {literal} — {line.strip()}")

    assert not unaccounted, (
        "these version literals are neither the current release "
        f"({version}) nor registered records:\n  "
        + "\n  ".join(unaccounted)
        + "\n\nEach one is a decision. If the line claims what digline is at "
        "*now*, update it — and add it to LIVE so the next release cannot "
        "forget it. If it records a version that has already shipped, or is "
        "not a digline version at all, add it to RECORDED with the reason. If "
        "the number adds nothing to the sentence, the best fix is to take it "
        "out: a claim that cannot go stale beats a gated one."
    )


def test_a_record_may_not_be_the_current_version() -> None:
    """Otherwise the allowance becomes the way to hide a claim that has gone
    stale: register today's number as "history" and the sweep stops looking."""
    version = current()
    guilty = [
        f"{name}: {why}"
        for name, entries in RECORDED.items()
        for literal, why in entries.items()
        if literal == version
    ]
    assert not guilty, (
        f"RECORDED registers {version}, which is the current release:\n  "
        + "\n  ".join(guilty)
        + "\nA record is a version this release has left behind. If one of "
        "these was a forward reference — a plan naming the release it waits "
        "for — that release is now here, so the sentence is either history or "
        "wrong: read it and say which. Otherwise move the entry to LIVE, or "
        "drop it and let the sweep accept the current version."
    )


def test_every_recorded_file_is_swept_and_every_literal_is_still_there() -> None:
    """An allowance for a line that no longer exists is an allowance nobody
    can see is dead — and the next version literal added to that file inherits
    it."""
    swept_names = {path.relative_to(ROOT).as_posix() for path in swept()}
    stale: list[str] = []
    for name, entries in RECORDED.items():
        if name not in swept_names:
            stale.append(f"{name} is registered but not swept")
            continue
        found = set(VERSION.findall((ROOT / name).read_text(encoding="utf-8")))
        stale += [
            f"{name} no longer contains {literal} ({why})"
            for literal, why in entries.items()
            if literal not in found
        ]
    assert not stale, "RECORDED has entries nothing matches:\n  " + "\n  ".join(stale)


# --------------------------------------------------------------------------- #
# What the number is for
# --------------------------------------------------------------------------- #


def test_dunder_version_is_the_installed_version() -> None:
    """Derived, not written: this is the copy that was already false."""
    from importlib.metadata import version as installed

    import digline

    assert digline.__version__ == installed("digline")


def test_the_cli_prints_the_version_and_exits_zero() -> None:
    """Through the real entry point, because `action="version"` exits inside
    argparse and a test that called `build_parser()` alone would not see the
    exit code the shell does."""
    import digline

    done = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "digline.cli", "--version"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == f"digline {digline.__version__}"


@pytest.mark.parametrize("flag", ["--version", "-h"])
def test_the_top_level_flags_need_no_subcommand(flag: str) -> None:
    """`digline --version` with no command after it: the flag sits on the top
    parser, above `required=True` on the subcommands."""
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "digline.cli", flag],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stderr
