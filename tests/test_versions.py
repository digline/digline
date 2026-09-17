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
    "src/digline/host/measure.py": {
        "0.11.0": "'the delta-pass over 0.11.0 found it missing' — which "
        "release's delta-pass earned the refusal, told as history. The refusal "
        "is the code below it; the number dates the lesson and does not claim "
        "what digline is at now",
    },
    ".claude/skills/operating-digline/SKILL.md": {
        "0.4.0": "the byte-for-byte mirror of AGENTS.md, gated by test_agents.py",
    },
    "RELEASING.md": {
        "0.14.1": "three sentences told as history once 0.15.0 is the tree's "
        "version: 'Nothing is queued as of 0.14.1' — the site-batch state read "
        "on that release — and the two releases, v0.14.0 and v0.14.1, whose "
        "image wait passed on the runner while the build still could not "
        "resolve the pin. The numbers date the evidence",
        "0.12.0": "'the delta-pass over 0.12.0' — which release the worked "
        "example of a drafted advisory came from, told as history. The number "
        "dates the pass; without it the example cannot say when it happened. "
        "Also, in 'Choosing the version', the worked example of a minor: the "
        "release that moved SCHEMA_VERSION 10 -> 11 and required migrate",
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
        "0.13.0": "the release the index race was measured on, told as history: "
        "its docker-publish was refused `digline==0.13.0` ~30s after the pypi "
        "job had verified that same pin from another runner. The numbers are "
        "the evidence the wait-and-verify was chosen from, and the example "
        "failure messages quote them",
        "0.11.0": "'0.11.0's classifier lock regen' — one of the five incidents "
        "in the index-race record, named so the class can be counted rather "
        "than argued about. History",
        "0.8.0": "three sentences about the release that earned the delta-pass "
        "section — the one whose new surface leaked a resolved model id, whose "
        "finish_raw and ToolsCalled came back clean, and whose follow-on run "
        "lost a propagation race on two legs. History, timings and all, like "
        "the 0.7.1 entries above",
        "0.12.1": "'0.12.1's is the worked example' — the release whose drafted "
        "advisory shows the session posting a GHSA draft, told as history beside "
        "the 0.12.0 entry that dates the pass it came from. Also one of the "
        "three patch examples in 'Choosing the version': it added `escape` to "
        "digline.report and removed nothing",
        "0.10.1": "a patch example in 'Choosing the version': the release that "
        "added `visible` to digline.report and removed nothing. History",
        "0.13.2": "'the two-step form this file carried until 0.13.2' — the "
        "release on which the site check was found passing having built "
        "nothing, and replaced by make preview. History",
        "0.13.3": "a patch example in 'Choosing the version': the release that "
        "added `CheckKind` to digline.core and removed nothing. History since "
        "the 0.14.0 bump",
        "0.14.0": "two incidents in 'The index race': the image build whose "
        "in-build `pip` lost the race with the runner-side wait already green, "
        "which is what added the in-build consumers. History, dated like the "
        "section's other incidents",
    },
    "docs/explain.md": {
        "0.14.0": "'a reference written before 0.14.0' — the release the "
        "`judged` key first reached a document, which is what decides whether "
        "a shape line has a reference to set beside. History",
    },
    "src/digline/wire/run.py": {
        "0.14.0": "'Found in the 0.14.0 delta-pass' — which release's pass "
        "found the MCP run document's gap, told as history in its docstring",
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
        "0.9.0": "'shipped in 0.9.0, and its own 0.1.0' — the release "
        "pytest-digline arrived in, history from the moment 0.10.0 shipped",
        "0.1.3": "digline-mcp's own version, not a digline one — the release "
        "that moved its surface from six tools to eight",
        "0.11.0": "'shipped in 0.11.0' — the release the resumed run landed in",
        "0.12.0": "'since 0.12.0' — the release ToolCalledWith and the recorded "
        "trajectory landed in, on Track D's trajectory item",
        "0.13.0": "'shipped in 0.13.0' — the release log and the register landed in",
    },
    "docs/rejudge.md": {
        "0.10.0": "'Until 0.10.0 the only way to find out was to pay the "
        "target' — the release `rejudge` arrived in, said as history on its own "
        "page",
    },
    "docs/api.md": {
        "0.14.0": "'since 0.14.0 digline reads it in three more places' — the "
        "release KIND stopped being unread, in the Custom assertions section. "
        "History: it dates a change of behaviour, not the current version",
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
        "0.12.0": "the release whose new surface the delta-pass read when it "
        "found the fourth advisory — a fact about a shipped release",
        "0.12.1": "the release that fixed the fourth advisory. Same sentence, "
        "other end of it",
        "0.7.1": "the release the first three published advisories were cut against, "
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
    "examples/langgraph/README.md": {
        "1.2.11": "the langgraph version the example was run against, not a "
        "digline one. Pinned to the example's own pyproject.toml by "
        "tests/test_examples.py, which is where a third-party version belongs — "
        "and named three times on purpose: once as what it was tested against, "
        "once because what a raising tool does was measured on *that* version "
        "and not assumed, and once in the floor the weekly run watches",
        "1.4.0": "langchain, beside it, held by the same test. Two packages "
        "rather than one because `create_agent` moved out of langgraph and into "
        "langchain in v1, so a reader with only one of the two cannot "
        "reproduce the run",
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
        "0.5.0": "the plugin versions, pinned to their own pyproject files by "
        "tests/test_docker.py",
        "0.5.1": "digline-anthropic's version, pinned to its own pyproject by "
        "tests/test_docker.py",
    },
    "src/digline/store/migrate.py": {
        "0.5.0": "'digline-anthropic 0.5.0 or earlier' — the plugin releases "
        'that recorded a call nobody named as a tool named "None", which is '
        "the residue the 12 -> 13 step names and leaves alone. History",
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
        "0.13.0": "four sites reading '(0.13.0 delta-pass)' — the pass over "
        "0.13.0 that found the register reader tracebacking on `Infinity` and "
        "nesting, coercing a wrong-typed field, forgiving a BOM as a tear, and "
        "splitting lines at NEL. Each names the pass beside the refusal that "
        "closes it. History from the moment 0.13.1 shipped",
    },
    # The rest of the 0.13.0 delta-pass, in the same shape: the pass named
    # where each finding is closed, history from the moment 0.13.1 shipped.
    "src/digline/cli/output.py": {
        "0.13.0": "'Until the 0.13.0 delta-pass this docstring said' and "
        "'(from the 0.13.0 delta-pass)' — the pass that found `emit()` "
        "trusting `json.dumps` to escape DEL and C1, named where the standing "
        "rule and the escaping now live",
    },
    "src/digline/cli/view.py": {
        "0.13.0": "'(0.13.0 delta-pass)' — the start-up line the standing "
        "rule's guard caught on its first run, now through `say()`",
    },
    "src/digline/core/assertions.py": {
        "0.13.0": "'(0.13.0 delta-pass)' — the pass that found one undecodable "
        "call erroring `ToolCalledWith` beside a match, named where unreadable "
        "calls are now stepped over",
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
        "0.10.0": "'\"0.10.0\" -> (0, 10, 0)' and the pair beside it — the two "
        "releases between which a string comparison of versions silently "
        "inverts, named in `release_tuple`'s docstring because naming them is "
        "what makes the rule checkable. History from the moment 0.10.1 shipped",
        "0.9.0": '\'"0.10.0" < "0.9.0" is true lexically\' — `release_tuple`\'s '
        "docstring, where the pair is the argument: the two releases between "
        "which a string comparison of versions silently inverts. Naming them "
        "is what makes the rule checkable, and the pair is history the moment "
        "0.10.0 ships (ADR 0014 §4)",
        "1.2.0": "'1.2.0rc1, 1.2.0.post1 and 1.2.0 all read as (1, 2, 0)' — not "
        "a digline version at all. An illustration of what the parser ignores, "
        "chosen far from any real release so nobody reads it as a claim",
        "0.8.1": "'is withheld from 0.8.1' — the release the withholding began "
        "in, which is what tells a reader which stored documents the refusal "
        "above is about. The same sentence as the entry beside it, from the "
        "other end: one names the release that leaked, one the release that "
        "stopped",
        "0.10.1": "'(0.10.1, from the release delta-pass)' — the release in "
        "which an unchecked `kind` stopped reaching `restore_output`, said "
        "beside the refusal that replaced it. History from the moment 0.11.0 "
        "shipped",
        "0.12.1": "four sites — 'Corrected in 0.12.1', '(0.12.1)' twice and "
        "'(0.12.1, from the release delta-pass)' — the release in which `[]` "
        "stopped collapsing into *not reported*, a corrupt trajectory began to "
        "be refused by name, and a perimeter field stopped crossing inside a "
        "comparison. Each named beside the code that closes it. History from "
        "the moment 0.13.0 shipped",
    },
    # The other three sites the 0.10.0 delta-pass left a mark on, in the shape
    # the 0.7.2 pair above established: the release is named beside the code
    # that closes the finding, so a reader knows which stored documents and
    # which terminals the sentence is about.
    "src/digline/report/render.py": {
        "0.10.1": "'(0.10.1, from the release delta-pass)' — the release the "
        "control-character sanitiser arrived in, named beside it so the next "
        "reader does not reinvent it one layer down",
        "0.12.1": "'(0.12.1, from the release delta-pass)' — the release in "
        "which `emit()` stopped putting a control character on a terminal, "
        "named beside the escaping that closed it",
    },
    # The 0.12.1 delta-pass, in the same shape: the release named where each
    # finding is closed, history from the moment 0.13.0 shipped.
    "src/digline/core/compare.py": {
        "0.12.1": "'the 0.12.1 delta-pass' — the release in which "
        "`config_deltas` began redacting both sides, so a perimeter field no "
        "longer walks out of the delta (ADR 0005 §2)",
    },
    "src/digline/report/log.py": {
        "0.12.1": "'the door 0.12.1 closed in `config_deltas`' — the reading "
        "across runs saying which closed door it keeps closed by construction",
    },
    "src/digline/run/replay.py": {
        "0.12.1": "'(0.12.1, from the release delta-pass)' — the release in "
        "which a replay of an honest zero-call run stopped being refused",
    },
    "packages/pytest-digline/src/pytest_digline/plugin.py": {
        "0.10.1": "'(0.10.1)' at three sites — the release in which the "
        "plugin's own terminal output began going through the shared "
        "sanitiser. One finding, three paths out of a document and into a "
        "terminal, each named where it is closed",
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
