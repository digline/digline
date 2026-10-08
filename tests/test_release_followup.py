"""The five checks that run after a tag, and the five controls beside them.

`.github/release_followup.py` is the answer to a gap that was measured rather
than imagined: post-tag step 3 was last performed for 0.15.0 and was found
undone at 0.15.3, and step 4's Status block was two releases behind on the same
day. Nothing went red, because nothing was looking.

Every check here is tested twice — for the finding, and for the **control**:
the same code asked something that must be false. `Finding.sound` is the
conjunction, and a check whose control does not hold is treated as a failure
rather than as a pass, because a check that would say yes to anything is worse
than no check at all.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Loaded by path because `.github/` is not a package and must not become one:
# the workflows call these scripts by filename. Registered in `sys.modules`
# before it is executed, because `@dataclass` resolves its annotations through
# `sys.modules[cls.__module__]` and a module that is not there raises on the
# first frozen dataclass rather than on anything to do with the test.
_spec = importlib.util.spec_from_file_location(
    "release_followup", ROOT / ".github" / "release_followup.py"
)
assert _spec is not None and _spec.loader is not None
followup = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = followup
_spec.loader.exec_module(followup)


def lock(tmp_path: Path, example: str, version: str | None) -> None:
    """An example's `uv.lock`, with or without a digline entry."""
    path = tmp_path / "examples" / example
    path.mkdir(parents=True, exist_ok=True)
    body = '[[package]]\nname = "attrs"\nversion = "26.1.0"\n\n'
    if version is not None:
        body += f'[[package]]\nname = "digline"\nversion = "{version}"\n'
    (path / "uv.lock").write_text(body, encoding="utf-8")


#: The shape the fixtures build. Not read from the repository: a fixture that
#: tracks the tree cannot fail when the tree changes under it, which is the
#: whole job of the real-tree test at the bottom of this file.
FIXTURE_EXAMPLES = ("classifier", "langchain", "llamaindex", "prompt-first", "rag")


def all_locks(tmp_path: Path, version: str | None) -> Path:
    for example in FIXTURE_EXAMPLES:
        lock(tmp_path, example, version)
    return tmp_path


# --------------------------------------------------------------------------- #
# 1. The example locks
# --------------------------------------------------------------------------- #


def test_locks_that_name_the_release_pass(tmp_path: Path) -> None:
    finding = followup.locks_finding(all_locks(tmp_path, "0.15.3"), "0.15.3")
    assert finding.sound
    assert "all 5 locks name 0.15.3" in finding.said


def test_a_lock_left_at_the_previous_release_is_caught(tmp_path: Path) -> None:
    """The defect itself: 0.15.1 and 0.15.2 both shipped with these at 0.15.0."""
    all_locks(tmp_path, "0.15.3")
    lock(tmp_path, "rag", "0.15.0")
    finding = followup.locks_finding(tmp_path, "0.15.3")
    assert not finding.ok
    assert finding.held, "the control must still hold when the check fails"
    assert "rag 0.15.0" in finding.said
    assert finding.title == "the example locks still name 0.15.0"


def test_locks_naming_different_stale_versions_say_so_in_the_title(
    tmp_path: Path,
) -> None:
    """A title names the step, not the whole finding — but it may not invent a
    single version where the locks disagree."""
    all_locks(tmp_path, "0.15.3")
    lock(tmp_path, "rag", "0.15.0")
    lock(tmp_path, "classifier", "0.14.1")
    assert followup.locks_finding(tmp_path, "0.15.3").title == (
        "the example locks still name several versions"
    )


def test_a_lock_with_no_digline_entry_is_not_read_as_a_match(tmp_path: Path) -> None:
    all_locks(tmp_path, "0.15.3")
    lock(tmp_path, "langchain", None)
    finding = followup.locks_finding(tmp_path, "0.15.3")
    assert not finding.ok
    assert "no digline entry" in finding.said


def test_an_example_with_a_lock_is_read_without_anybody_listing_it(
    tmp_path: Path,
) -> None:
    """The defect this glob exists for, in the direction that caused it.

    `mcp-tools` arrived with a lock and the hand-written tuple did not name it,
    so step 3 read the five it knew, found them all at the new version, and
    reported green over a sixth that was a release behind. A new example has to
    join the check by being committed, not by somebody remembering."""
    all_locks(tmp_path, "0.15.3")
    lock(tmp_path, "mcp-tools", "0.15.0")
    assert "mcp-tools" in followup.pinned_examples(tmp_path)
    finding = followup.locks_finding(tmp_path, "0.15.3")
    assert not finding.ok, "the newcomer's stale lock must fail the step"
    assert finding.held
    assert "mcp-tools 0.15.0" in finding.said


def test_an_example_without_a_lock_is_not_invented(tmp_path: Path) -> None:
    """The other direction: the examples that resolve at install time have no
    lock, and must not be reported as locks with no digline entry."""
    all_locks(tmp_path, "0.15.3")
    (tmp_path / "examples" / "external-app").mkdir(parents=True)
    assert "external-app" not in followup.pinned_examples(tmp_path)
    assert followup.locks_finding(tmp_path, "0.15.3").sound


def test_a_tree_with_no_locks_at_all_does_not_pass(tmp_path: Path) -> None:
    """New with the glob. A named tuple could not find nothing; a pattern can —
    an examples/ that moved, a checkout without it — and `all 0 locks name
    0.15.3` is true of every version there has ever been."""
    (tmp_path / "examples").mkdir()
    finding = followup.locks_finding(tmp_path, "0.15.3")
    assert not finding.held, "nothing read must fail the control"
    assert not finding.sound
    assert "read nothing" in finding.said


def test_the_lock_control_fails_when_the_comparison_is_blind(tmp_path: Path) -> None:
    """The negative half. If every lock somehow read as the impossible version,
    the comparison is not reading the file — and that must not pass."""
    all_locks(tmp_path, followup.IMPOSSIBLE)
    finding = followup.locks_finding(tmp_path, followup.IMPOSSIBLE)
    assert finding.ok, "it matches what it was asked for"
    assert not finding.held, "but the control proves the check is blind"
    assert not finding.sound


# --------------------------------------------------------------------------- #
# 2. The reviewer gate
# --------------------------------------------------------------------------- #

APPROVED: list[dict[str, Any]] = [{"state": "approved", "user": {"login": "someone"}}]
REJECTED: list[dict[str, Any]] = [{"state": "rejected", "user": {"login": "someone"}}]


def test_an_approved_publish_run_passes() -> None:
    finding = followup.approvals_finding(APPROVED, [])
    assert finding.sound
    assert "records an approved" in finding.said


def test_a_gate_that_never_recorded_an_approval_is_caught() -> None:
    """The v0.5.0 failure: the gate fails open and every run looks green."""
    finding = followup.approvals_finding([], [])
    assert not finding.ok
    assert finding.held
    assert finding.title == "the reviewer gate recorded no approval"


def test_a_rejection_is_not_an_approval() -> None:
    assert not followup.approvals_finding(REJECTED, []).ok


def test_the_approvals_control_fails_when_anything_reads_as_approved() -> None:
    """The negative half, and it is a real run in the workflow: the approvals of
    a run with no gated environment. If that reads as approved, this is not
    reading approvals."""
    finding = followup.approvals_finding(APPROVED, APPROVED)
    assert finding.ok
    assert not finding.held
    assert not finding.sound


def test_a_payload_that_is_not_a_list_is_not_an_approval() -> None:
    """An endpoint that moved returns something else, and something else is not
    consent."""
    assert not followup.approvals_finding({"message": "Not Found"}, []).ok


# A re-run erases the record: the endpoint answers for the latest attempt only
# (friction 71, v0.21.0). What an earlier run read is kept and read back.

KEPT: dict[str, Any] = {
    "publish_run": "36311430504",
    "attempt": 1,
    "read_by": "36311781707",
    "approvals": APPROVED,
}


def rerun(kept: object, *, approvals: object = None, attempt: int = 2) -> Any:
    return followup.approvals_finding(
        [] if approvals is None else approvals,
        [],
        attempt=attempt,
        kept=kept,
        publish_run="36311430504",
    )


def test_a_re_run_reads_back_what_attempt_1_recorded() -> None:
    finding = rerun(KEPT)
    assert finding.sound
    assert "on attempt 1" in finding.said
    assert "release-followup run 36311781707" in finding.said


def test_a_re_run_with_nothing_kept_is_unreadable_not_a_gate_that_failed() -> None:
    """v0.21.0 exactly: the gate held, and the only reading is in a log."""
    finding = rerun(None)
    assert not finding.ok
    assert finding.held
    assert "not evidence the gate failed" in finding.said
    assert "did not hold" not in finding.said
    assert finding.title == (
        "the reviewer gate's approval is not readable after a re-run"
    )


def test_a_kept_record_is_not_read_on_attempt_1() -> None:
    """On attempt 1 the endpoint is the reading, and an empty one is the v0.5.0
    failure. A kept record must not paper over it."""
    finding = rerun(KEPT, attempt=1)
    assert not finding.ok
    assert finding.title == "the reviewer gate recorded no approval"


@pytest.mark.parametrize(
    ("label", "kept"),
    [
        ("another publish run", {**KEPT, "publish_run": "1"}),
        ("the same attempt", {**KEPT, "attempt": 2}),
        ("a later attempt", {**KEPT, "attempt": 3}),
        ("an attempt that is a bool", {**KEPT, "attempt": True}),
        ("no reader", {**KEPT, "read_by": ""}),
        ("a rejection", {**KEPT, "approvals": REJECTED}),
        ("approvals that are not a list", {**KEPT, "approvals": {"state": "approved"}}),
        ("not a record", ["approved"]),
    ],
)
def test_a_kept_record_one_field_from_valid_is_not_read(
    label: str, kept: object
) -> None:
    assert not rerun(kept).ok, label


def test_the_endpoint_wins_over_whatever_was_kept() -> None:
    finding = rerun({"garbage": True}, approvals=APPROVED)
    assert finding.sound
    assert finding.said == "the publish run records an approved"


def test_the_control_still_bites_on_a_read_back() -> None:
    finding = followup.approvals_finding(
        [], APPROVED, attempt=2, kept=KEPT, publish_run="36311430504"
    )
    assert finding.ok
    assert not finding.held


def test_a_run_keeps_only_an_approval() -> None:
    assert followup.keep_record([], publish_run="9", attempt=1, read_by="10") is None
    assert (
        followup.keep_record(REJECTED, publish_run="9", attempt=1, read_by="10") is None
    )


def test_what_one_run_keeps_the_next_one_reads() -> None:
    record = followup.keep_record(
        APPROVED, publish_run="36311430504", attempt=1, read_by="36311781707"
    )
    assert rerun(json.loads(json.dumps(record))).sound


def _main_args(tmp_path: Path, *extra: str) -> list[str]:
    all_locks(tmp_path, "0.15.3")
    (tmp_path / "RELEASING.md").write_text(
        BLOCK.format(version="0.15.3"), encoding="utf-8"
    )
    (tmp_path / "control.json").write_text("[]", encoding="utf-8")
    (tmp_path / "digests.json").write_text(json.dumps(digests()), encoding="utf-8")
    return [
        "--version",
        "0.15.3",
        "--root",
        str(tmp_path),
        "--releasing",
        str(tmp_path / "RELEASING.md"),
        "--approvals",
        str(tmp_path / "approvals.json"),
        "--approvals-control",
        str(tmp_path / "control.json"),
        "--digests",
        str(tmp_path / "digests.json"),
        "--action",
        str(action_file(tmp_path, "0.15.3")),
        "--out",
        str(tmp_path / "report.json"),
        *extra,
    ]


def test_main_keeps_the_approval_it_read_and_a_re_run_reads_it(
    tmp_path: Path,
) -> None:
    """The whole path, through the files the workflow passes: attempt 1 keeps,
    attempt 2 finds the endpoint empty and passes on what was kept."""
    kept = tmp_path / "kept.json"
    (tmp_path / "approvals.json").write_text(json.dumps(APPROVED), encoding="utf-8")
    first = _main_args(
        tmp_path,
        *("--publish-run", "36311430504", "--attempt", "1"),
        *("--read-by", "36311781707", "--keep-out", str(kept)),
    )
    assert followup.main(first) == 0
    assert json.loads(kept.read_text(encoding="utf-8"))["read_by"] == "36311781707"

    (tmp_path / "approvals.json").write_text("[]", encoding="utf-8")
    second = _main_args(
        tmp_path,
        *("--publish-run", "36311430504", "--attempt", "2"),
        *("--kept", str(kept)),
    )
    assert followup.main(second) == 0


def test_main_keeps_nothing_when_it_read_no_approval(tmp_path: Path) -> None:
    kept = tmp_path / "kept.json"
    (tmp_path / "approvals.json").write_text("[]", encoding="utf-8")
    args = _main_args(
        tmp_path,
        *("--publish-run", "9", "--attempt", "1"),
        *("--read-by", "10", "--keep-out", str(kept)),
    )
    assert followup.main(args) == 1
    assert not kept.exists()


def test_main_on_a_re_run_with_a_missing_kept_file_is_unreadable(
    tmp_path: Path,
) -> None:
    (tmp_path / "approvals.json").write_text("[]", encoding="utf-8")
    args = _main_args(
        tmp_path,
        *("--publish-run", "9", "--attempt", "2"),
        *("--kept", str(tmp_path / "absent.json")),
    )
    assert followup.main(args) == 1
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert "not readable after a re-run" in json.dumps(report)


# --------------------------------------------------------------------------- #
# 3. The image tags
# --------------------------------------------------------------------------- #

ONE = "sha256:b72573f98dd77ffa8c945c6db2e749f8676d1841b3a1e57000d2dfe93130fefb"
OTHER = "sha256:30f3816455ca21861afe35f395abfe2a272ee988e5d7ccc56039fd7ac952efe6"


def digests(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "0.15.3": ONE,
        "0.15": ONE,
        "latest": ONE,
        "0.15.3-does-not-exist": None,
    }
    base.update(overrides)
    return base


def test_three_tags_on_one_digest_pass() -> None:
    finding = followup.digests_finding(digests(), "0.15.3")
    assert finding.sound
    assert "are one digest" in finding.said


def test_a_latest_left_on_the_previous_release_is_caught() -> None:
    finding = followup.digests_finding(digests(latest=OTHER), "0.15.3")
    assert not finding.ok
    assert "2 different digests" in finding.said


def test_a_registry_that_does_not_answer_is_not_a_defect() -> None:
    """Weather, not a defect. A registry that is down must not read as a release
    that shipped three different images — a red nobody can reproduce is a red
    everybody learns to ignore."""
    finding = followup.digests_finding(digests(latest="error"), "0.15.3")
    assert not finding.ok
    assert "did not answer" in finding.said
    assert "not judged" in finding.said


def test_a_missing_tag_is_told_apart_from_an_unreachable_one() -> None:
    finding = followup.digests_finding(digests(latest=None), "0.15.3")
    assert "has no latest" in finding.said


def test_the_digest_control_fails_when_an_impossible_tag_resolves() -> None:
    """The negative half, asked of the real registry in the workflow: a tag that
    cannot exist must come back not-found. If it resolves, the query answers for
    anything and the positive half means nothing."""
    finding = followup.digests_finding(
        digests(**{"0.15.3-does-not-exist": ONE}), "0.15.3"
    )
    assert finding.ok
    assert not finding.held
    assert not finding.sound


# --------------------------------------------------------------------------- #
# 4. The Status block
# --------------------------------------------------------------------------- #

BLOCK = """### Status: what each path has proven

- **Something.** Seen on v0.15.0: both legs printed `served`.
- **v{version} read the same way.** And the rest of the reading.

### What is not covered, stated rather than assumed
"""


def test_a_status_block_that_names_the_release_passes() -> None:
    finding = followup.status_finding(BLOCK.format(version="0.15.3"), "0.15.3")
    assert finding.sound


def test_a_status_block_two_releases_behind_is_caught() -> None:
    """The defect as found: the block described v0.15.0 and v0.15.1 while the
    tree was at 0.15.3."""
    finding = followup.status_finding(BLOCK.format(version="0.15.1"), "0.15.3")
    assert not finding.ok
    assert finding.held
    assert "0.15.0, v0.15.1" in finding.said
    assert finding.title == "the Status block does not mention v0.15.3"


def test_the_block_ends_at_the_next_heading() -> None:
    """A version named in a *later* section is not this block saying it."""
    text = BLOCK.format(version="0.15.1") + "\nSomething about v0.15.3 down here.\n"
    assert not followup.status_finding(text, "0.15.3").ok


def test_a_missing_block_is_not_read_as_a_pass() -> None:
    assert not followup.status_finding("# Releasing\n\nNothing here.\n", "0.15.3").ok


def test_the_status_control_fails_when_the_block_matches_anything() -> None:
    """Inside the block, not after it — appending below the next heading proves
    nothing, which is what the first cut of this test did."""
    text = BLOCK.format(version="0.15.3").replace(
        "- **Something.**", f"- **v{followup.IMPOSSIBLE}.** - **Something.**"
    )
    finding = followup.status_finding(text, "0.15.3")
    assert finding.ok
    assert not finding.held
    assert not finding.sound


# --------------------------------------------------------------------------- #
# The report, which is what a person actually sees
# --------------------------------------------------------------------------- #


def sound(step: str) -> Any:
    return followup.Finding(step, True, True, "fine", "and fine", f"{step} is undone")


def unsound(step: str) -> Any:
    return followup.Finding(
        step, False, True, "not fine", "and fine", f"{step} is undone"
    )


def test_the_title_names_the_step_that_was_skipped() -> None:
    written = followup.report([sound("a"), unsound("the example locks")], "0.15.3")
    assert written["title"] == (
        "Release follow-up for v0.15.3: the example locks is undone"
    )
    assert written["ok"] is False


def test_several_failures_name_the_first_and_count_the_rest() -> None:
    written = followup.report([unsound("a"), unsound("b"), unsound("c")], "0.15.3")
    assert written["title"].endswith("a is undone, and 2 more")


def test_a_check_that_cannot_fail_takes_precedence_in_the_title() -> None:
    """A broken check is a worse finding than a skipped step, because it makes
    every other answer worthless — so it is the one the title names."""
    blind = followup.Finding("the image tags", True, False, "fine", "blind", "x")
    written = followup.report([unsound("the example locks"), blind], "0.15.3")
    assert written["title"] == (
        "Release follow-up for v0.15.3: a check that cannot fail (the image tags)"
    )


def test_everything_done_says_so() -> None:
    written = followup.report([sound("a"), sound("b")], "0.15.3")
    assert written["ok"] is True
    assert "everything the runbook asks for is done" in written["title"]


def test_the_body_carries_the_whole_reading_rather_than_a_link() -> None:
    written = followup.report([sound("a"), unsound("b")], "0.15.3")
    body = str(written["body"])
    assert "- [x] **a**" in body
    assert "- [ ] **b**" in body
    assert "closes itself on the next push to `main`" in body


# --------------------------------------------------------------------------- #
# 7. The action's default image
# --------------------------------------------------------------------------- #

#: The two lines of `digline-action`'s `action.yml` that name the image: the
#: description's placeholder, which must not be read, and the default.
ACTION_YML = """inputs:
  image:
    description: >-
      Point it at your own derivation — FROM ghcr.io/digline/digline:<version>
    required: false
    default: "ghcr.io/digline/digline:{version}"
"""


def action(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "main": ACTION_YML.format(version="0.30.0"),
        "v1": ACTION_YML.format(version="0.30.0"),
        "v1-does-not-exist": None,
    }
    base.update(overrides)
    return base


def action_file(tmp_path: Path, version: str) -> Path:
    path = tmp_path / "action.json"
    text = ACTION_YML.format(version=version)
    path.write_text(
        json.dumps({"main": text, "v1": text, "v1-does-not-exist": None}),
        encoding="utf-8",
    )
    return path


def test_the_default_is_read_and_the_placeholder_is_not() -> None:
    assert followup.action_default(ACTION_YML.format(version="0.30.0")) == "0.30.0"
    assert followup.action_default("default: ghcr.io/acme/other:0.30.0\n") is None


def test_main_and_v1_on_the_release_pass() -> None:
    finding = followup.action_finding(action(), "0.30.0")
    assert finding.sound
    assert "main and v1 both default to" in finding.said


def test_a_v1_that_was_not_moved_is_caught() -> None:
    """2026-10-08 exactly: `main` had been bumped twice, and `@v1` — the line
    the README tells everyone to write — still resolved to 0.9.0."""
    finding = followup.action_finding(
        action(v1=ACTION_YML.format(version="0.9.0")), "0.30.0"
    )
    assert not finding.ok
    assert "v1 names 0.9.0" in finding.said
    assert "v1 was not moved" in finding.said
    assert finding.title == (
        "digline/digline-action@v1 does not default to digline 0.30.0"
    )


def test_a_main_left_at_the_previous_release_is_caught() -> None:
    finding = followup.action_finding(
        action(
            main=ACTION_YML.format(version="0.29.0"),
            v1=ACTION_YML.format(version="0.29.0"),
        ),
        "0.30.0",
    )
    assert not finding.ok
    assert "main names 0.29.0" in finding.said
    assert "was not moved" not in finding.said


def test_an_action_yml_with_no_default_is_not_a_match() -> None:
    finding = followup.action_finding(action(v1="inputs: {}\n"), "0.30.0")
    assert not finding.ok
    assert "v1 names no digline image" in finding.said


def test_a_missing_ref_is_told_apart_from_an_unreachable_one() -> None:
    missing = followup.action_finding(action(v1=None), "0.30.0")
    assert not missing.ok and missing.answered
    assert "has no action.yml at v1" in missing.said

    unreachable = followup.action_finding(action(v1="error"), "0.30.0")
    assert not unreachable.ok and not unreachable.answered
    assert "not judged" in unreachable.said


def test_the_action_control_fails_when_an_impossible_ref_resolves() -> None:
    finding = followup.action_finding(
        action(**{"v1-does-not-exist": ACTION_YML.format(version="0.30.0")}),
        "0.30.0",
    )
    assert finding.ok
    assert not finding.held
    assert not finding.sound


def test_the_action_is_not_asked_about_a_superseded_release() -> None:
    finding = followup.action_finding(action(), "0.29.0", current=False)
    assert not finding.applicable
    assert finding.sound


def test_main_refuses_to_run_without_the_action(tmp_path: Path) -> None:
    """Required, so that a workflow which stops fetching it fails rather than
    passing over step 7 — the silence this check exists to end."""
    (tmp_path / "approvals.json").write_text(json.dumps(APPROVED), encoding="utf-8")
    argv = _main_args(tmp_path)
    at = argv.index("--action")
    del argv[at : at + 2]
    with pytest.raises(SystemExit):
        followup.main(argv)


def test_main_fails_on_a_v1_that_was_not_moved(tmp_path: Path) -> None:
    (tmp_path / "approvals.json").write_text(json.dumps(APPROVED), encoding="utf-8")
    argv = _main_args(tmp_path)
    old = ACTION_YML.format(version="0.9.0")
    (tmp_path / "action.json").write_text(
        json.dumps(
            {
                "main": ACTION_YML.format(version="0.15.3"),
                "v1": old,
                "v1-does-not-exist": None,
            }
        ),
        encoding="utf-8",
    )
    assert followup.main(argv) == 1
    written = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert "digline-action@v1 does not default to digline 0.15.3" in written["title"]


def test_the_workflow_fetches_the_three_refs_and_passes_them() -> None:
    """The shell is not run here; this holds the shape: the three refs are
    asked, and the file they land in is what `--action` reads."""
    workflow = (ROOT / ".github" / "workflows" / "release-followup.yml").read_text(
        encoding="utf-8"
    )
    assert "for ref in main v1 v1-does-not-exist; do" in workflow
    assert "--action action.json" in workflow


# --------------------------------------------------------------------------- #
# End to end, through `main`
# --------------------------------------------------------------------------- #


def test_main_writes_the_report_and_exits_nonzero_on_a_skipped_step(
    tmp_path: Path,
) -> None:
    all_locks(tmp_path, "0.15.0")
    (tmp_path / "RELEASING.md").write_text(
        BLOCK.format(version="0.15.3"), encoding="utf-8"
    )
    (tmp_path / "approvals.json").write_text(json.dumps(APPROVED), encoding="utf-8")
    (tmp_path / "control.json").write_text("[]", encoding="utf-8")
    (tmp_path / "digests.json").write_text(json.dumps(digests()), encoding="utf-8")
    out = tmp_path / "report.json"

    code = followup.main(
        [
            "--version",
            "0.15.3",
            "--root",
            str(tmp_path),
            "--releasing",
            str(tmp_path / "RELEASING.md"),
            "--approvals",
            str(tmp_path / "approvals.json"),
            "--approvals-control",
            str(tmp_path / "control.json"),
            "--digests",
            str(tmp_path / "digests.json"),
            "--action",
            str(action_file(tmp_path, "0.15.3")),
            "--out",
            str(out),
        ]
    )
    assert code == 1
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["ok"] is False
    assert "the example locks still name 0.15.0" in written["title"]


def test_main_exits_zero_when_the_runbook_was_followed(tmp_path: Path) -> None:
    all_locks(tmp_path, "0.15.3")
    (tmp_path / "RELEASING.md").write_text(
        BLOCK.format(version="0.15.3"), encoding="utf-8"
    )
    (tmp_path / "approvals.json").write_text(json.dumps(APPROVED), encoding="utf-8")
    (tmp_path / "control.json").write_text("[]", encoding="utf-8")
    (tmp_path / "digests.json").write_text(json.dumps(digests()), encoding="utf-8")
    out = tmp_path / "report.json"

    code = followup.main(
        [
            "--version",
            "0.15.3",
            "--root",
            str(tmp_path),
            "--releasing",
            str(tmp_path / "RELEASING.md"),
            "--approvals",
            str(tmp_path / "approvals.json"),
            "--approvals-control",
            str(tmp_path / "control.json"),
            "--digests",
            str(tmp_path / "digests.json"),
            "--action",
            str(action_file(tmp_path, "0.15.3")),
            "--out",
            str(out),
        ]
    )
    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["ok"] is True


def test_this_repository_is_the_shape_the_checks_assume() -> None:
    """The fixtures above are fixtures; this reads the real tree, so a lock that
    stops carrying a digline entry, or an `examples/` that stops holding locks
    at all, fails here rather than silently making a check unfalsifiable.

    **What the set comparison guards, said plainly, because it reads as though
    it guarded more.** It does *not* fail when the tree gains an example: it
    cannot, and it should not — a new example with a lock is found by the glob
    and there is nothing to add it to, which is the whole point of the glob.
    What it guards is `lock_versions` itself. Walk the directory by a different
    route than the function does — `iterdir` and `is_file` against the
    function's `glob` — and a filter reintroduced into the function, or a
    pattern that stops matching what it used to, shows up as a disagreement
    between two readings of one filesystem. That is worth a line; it is just
    not the same line as "a new example fails here", which it used to claim.
    """
    pinned = followup.lock_versions(ROOT)
    # Deliberately not `ROOT.glob("examples/*/uv.lock")`: that is the function's
    # own expression, and comparing it against itself compares nothing.
    walked = {
        directory.name
        for directory in (ROOT / "examples").iterdir()
        if (directory / "uv.lock").is_file()
    }
    assert set(pinned) == walked, (
        "step 3 must read every example that has a lock, and only those — two "
        "walks of one directory disagree, so one of them is filtering"
    )
    assert pinned, "no example carries a uv.lock: step 3 would pass over nothing"
    assert all(version is not None for version in pinned.values()), pinned
    assert followup.status_block((ROOT / "RELEASING.md").read_text(encoding="utf-8")), (
        "RELEASING.md has no Status block for step 4 to update"
    )


# --------------------------------------------------------------------------- #
# The scope: which open issue a run is allowed to touch
# --------------------------------------------------------------------------- #


def test_the_report_carries_the_prefix_that_scopes_its_issue() -> None:
    """One open issue per **release**, not per repository.

    The first cut kept one issue for the whole repository and closed it on any
    green run: a run about 0.15.3 closed an issue naming 0.15.2, marking done a
    step nobody had done. The prefix is emitted here, where the title is built,
    so the workflow matches on a string it was given rather than on one it
    reinvents.
    """
    written = followup.report([unsound("the example locks")], "0.15.3")
    assert written["scope"] == "Release follow-up for v0.15.3:"
    assert str(written["title"]).startswith(str(written["scope"]))


def test_the_scope_is_a_prefix_and_not_a_search() -> None:
    """The case that makes the difference, and it is the real one: the issue
    opened for 0.15.2 has *0.15.3* in its title — "the example locks still name
    0.15.3" — so a substring search for the version would match the wrong issue
    and close it."""
    older = followup.report([unsound("the example locks")], "0.15.2")
    older_title = "Release follow-up for v0.15.2: the example locks still name 0.15.3"
    assert "0.15.3" in older_title
    assert not older_title.startswith(followup.report([sound("a")], "0.15.3")["scope"])
    assert older_title.startswith(str(older["scope"]))


# --------------------------------------------------------------------------- #
# Applicability: which questions a superseded release may be asked
# --------------------------------------------------------------------------- #
#
# Issue #45 is where this came from. Opened about 0.15.2 after 0.15.3 had
# shipped, it failed on the locks and on the image tags — and both were failing
# because the repository had been *repaired*: the locks name 0.15.3 and `latest`
# points at it, which is correct. Two of its three lines could never go green
# without making the current tree wrong, so no run could ever close it, and a
# red label open for ever is the signal people learn to ignore.


def test_the_locks_are_not_asked_about_a_superseded_release(tmp_path: Path) -> None:
    all_locks(tmp_path, "0.15.3")
    finding = followup.locks_finding(tmp_path, "0.15.2", current=False)
    assert not finding.applicable
    assert finding.sound, "nothing to answer is not something wrong"
    assert "not applicable" in finding.said
    assert "0.15.2" in finding.said


def test_the_locks_are_still_asked_about_the_current_release(tmp_path: Path) -> None:
    """The other half: `current=True` is today's behaviour, unchanged."""
    all_locks(tmp_path, "0.15.0")
    finding = followup.locks_finding(tmp_path, "0.15.3", current=True)
    assert finding.applicable
    assert not finding.sound
    assert "do not name 0.15.3" in finding.said


def test_the_image_tags_are_not_asked_about_a_superseded_release() -> None:
    finding = followup.digests_finding(digests(latest=OTHER), "0.15.2", current=False)
    assert not finding.applicable
    assert finding.sound
    assert "`latest` follow the newest release" in finding.said


def test_the_image_tags_are_still_asked_about_the_current_release() -> None:
    finding = followup.digests_finding(digests(latest=OTHER), "0.15.3", current=True)
    assert finding.applicable
    assert not finding.sound


def test_the_record_shaped_checks_keep_their_meaning_for_ever() -> None:
    """The reviewer gate and the Status block take no `current` at all.

    Their subject is a record of what happened at that release — the approvals
    of its publish run, and its paragraph in the block — and a record does not
    stop being true because a later version shipped. That is the line between
    the two categories, and it is why these two have no switch to set.
    """
    assert followup.approvals_finding(APPROVED, []).applicable
    assert followup.status_finding(BLOCK.format(version="0.15.2"), "0.15.2").applicable


def test_a_superseded_release_whose_record_is_complete_is_all_green(
    tmp_path: Path,
) -> None:
    """The state #45 has to be able to reach, or it can never be closed by a run:
    locks and tags not applicable, gate approved, block written."""
    all_locks(tmp_path, "0.15.3")
    findings = [
        followup.locks_finding(tmp_path, "0.15.2", current=False),
        followup.approvals_finding(APPROVED, []),
        followup.digests_finding(digests(latest=OTHER), "0.15.2", current=False),
        followup.status_finding(BLOCK.format(version="0.15.2"), "0.15.2"),
    ]
    written = followup.report(findings, "0.15.2")
    assert written["ok"] is True
    body = str(written["body"])
    assert "- [~] **the example locks**" in body
    assert "- [~] **the image tags**" in body
    assert "- [x] **the Status block**" in body


def test_a_superseded_release_whose_record_is_missing_is_still_red(
    tmp_path: Path,
) -> None:
    """And the negative half of the whole idea: not-applicable must not become a
    way of passing. The block without its paragraph still fails, alone."""
    all_locks(tmp_path, "0.15.3")
    findings = [
        followup.locks_finding(tmp_path, "0.15.2", current=False),
        followup.approvals_finding(APPROVED, []),
        followup.digests_finding(digests(latest=OTHER), "0.15.2", current=False),
        followup.status_finding(BLOCK.format(version="0.15.3"), "0.15.2"),
    ]
    written = followup.report(findings, "0.15.2")
    assert written["ok"] is False
    assert "the Status block does not mention v0.15.2" in str(written["title"])


def test_main_treats_an_older_version_as_superseded(tmp_path: Path) -> None:
    """`--newest` is what decides it, and leaving it out asks about the present
    — so a caller that does not know cannot accidentally excuse a check."""
    all_locks(tmp_path, "0.15.3")
    (tmp_path / "RELEASING.md").write_text(
        BLOCK.format(version="0.15.2"), encoding="utf-8"
    )
    (tmp_path / "approvals.json").write_text(json.dumps(APPROVED), encoding="utf-8")
    (tmp_path / "control.json").write_text("[]", encoding="utf-8")
    (tmp_path / "digests.json").write_text(
        json.dumps({"0.15.2": ONE, "0.15": OTHER, "latest": OTHER}), encoding="utf-8"
    )
    out = tmp_path / "report.json"
    argv = [
        "--version",
        "0.15.2",
        "--root",
        str(tmp_path),
        "--releasing",
        str(tmp_path / "RELEASING.md"),
        "--approvals",
        str(tmp_path / "approvals.json"),
        "--approvals-control",
        str(tmp_path / "control.json"),
        "--digests",
        str(tmp_path / "digests.json"),
        "--action",
        str(action_file(tmp_path, "0.15.3")),
        "--out",
        str(out),
    ]
    assert followup.main([*argv, "--newest", "0.15.3"]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["ok"] is True
    # Without `--newest`, the same inputs are read as the present and fail.
    assert followup.main(argv) == 1


# --------------------------------------------------------------------------- #
# The third word: an absence of an answer is not an answer (#215)
# --------------------------------------------------------------------------- #


def test_an_unread_publish_run_is_not_judged_rather_than_a_gate_that_failed() -> None:
    """#215 exactly: one `gh run list` came back empty, and the empty approvals
    after it read as *"the gate did not hold"* about a gate that had held."""
    finding = followup.approvals_finding(followup.UNREAD, [])
    assert not finding.answered
    assert not finding.ok
    assert finding.held
    assert "not judged" in finding.said
    assert "did not hold" not in finding.said
    assert finding.title == "the reviewer gate could not be read"


def test_an_unread_kept_record_on_a_re_run_is_not_none_was_kept() -> None:
    """Two absences kept apart: a list that answered with nothing is *none was
    kept* (v0.21.0), a list that never answered is *not judged*."""
    none_kept = rerun(None)
    unread = rerun(followup.UNREAD)
    assert none_kept.answered
    assert "none was kept" in none_kept.said
    assert not unread.answered
    assert "not judged" in unread.said


def test_an_approval_read_now_wins_over_an_unread_kept_record() -> None:
    """The endpoint answering is an answer; an unread lookup beside it changes
    nothing."""
    assert rerun(followup.UNREAD, approvals=APPROVED).sound


def test_the_control_still_bites_when_the_reading_is_unread() -> None:
    finding = followup.approvals_finding(followup.UNREAD, APPROVED)
    assert not finding.held


def test_a_run_that_answered_nothing_new_leaves_the_issue_alone() -> None:
    unread = followup.approvals_finding(followup.UNREAD, [])
    written = followup.report([sound("a"), unread], "0.22.0")
    assert written["ok"] is False
    assert written["undecided"] is True
    assert "- [?] **the reviewer gate**" in str(written["body"])


def test_an_undone_step_beside_an_unread_one_is_still_decided() -> None:
    """Something was answered, and it was *no*: that is worth writing down."""
    unread = followup.approvals_finding(followup.UNREAD, [])
    written = followup.report([unsound("the example locks"), unread], "0.22.0")
    assert written["undecided"] is False
    assert written["title"].startswith(
        "Release follow-up for v0.22.0: the example locks is undone"
    )


def test_a_fully_answered_report_is_never_undecided() -> None:
    assert followup.report([sound("a")], "0.22.0")["undecided"] is False
    assert followup.report([unsound("a")], "0.22.0")["undecided"] is False


def test_main_reads_the_unread_word_from_the_file_the_workflow_writes(
    tmp_path: Path,
) -> None:
    all_locks(tmp_path, "0.22.0")
    (tmp_path / "approvals.json").write_text('"unread"', encoding="utf-8")
    (tmp_path / "control.json").write_text("[]", encoding="utf-8")
    releasing = tmp_path / "RELEASING.md"
    releasing.write_text(
        "### Status: what each path has proven\n\n- **v0.22.0 — read.**\n\n## Next\n",
        encoding="utf-8",
    )
    digests = tmp_path / "digests.json"
    digests.write_text(
        '{"0.22.0": "sha256:a", "0.22": "sha256:a", "latest": "sha256:a", '
        '"0.22.0-does-not-exist": null}',
        encoding="utf-8",
    )
    out = tmp_path / "report.json"
    code = followup.main(
        [
            "--version", "0.22.0",
            "--root", str(tmp_path),
            "--releasing", str(releasing),
            "--approvals", str(tmp_path / "approvals.json"),
            "--approvals-control", str(tmp_path / "control.json"),
            "--digests", str(digests),
            "--action", str(action_file(tmp_path, "0.22.0")),
            "--out", str(out),
        ]
    )  # fmt: skip
    written = json.loads(out.read_text(encoding="utf-8"))
    assert code == 1
    assert written["undecided"] is True


def test_the_issue_step_asks_again_before_it_opens_an_issue() -> None:
    """The open issues are a listing too. Read once and empty, they opened a
    duplicate of the issue the listing failed to show; a failed call was an
    empty list. Simulated with a stub `gh` whose listing shows the issue on the
    third read: the step as it stood created a second issue after one read, and
    this one rewrites the first after three. The shell is not run here, so this
    holds the shape the simulation checked: a failed listing stops the step,
    and `gh issue create` is reached only through the loop that lists again."""
    workflow = (ROOT / ".github" / "workflows" / "release-followup.yml").read_text(
        encoding="utf-8"
    )
    step = workflow[
        workflow.index("name: Open, rewrite or close this release's issue") :
    ]
    step = step[: step.index("# Said whichever way this run went")]
    assert "if ! read_issues; then" in step
    assert "> open.json\n" not in step.replace(" \\\n", " ").split("read_issues() {")[0]
    loop = step.index("for try in 1 2 3; do")
    assert (
        step.index('mine="$(find_mine)"\n              [ -n "$mine" ] && break') > loop
    )
    assert step.index("gh issue create") > loop
    assert step.count("gh issue create") == 1
