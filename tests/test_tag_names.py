"""The pre-tag check, in both directions.

`tools/tag_names.py` refuses a tag whose message names fewer packages than its
run will publish. Every refusal is tested beside the case it must let through:
a check that fails everything passes each "must fail" test, and one that fails
nothing passes each "must pass" test, so only the pair says it discriminates.

Offline by construction — `served()` is the only thing that touches the index,
and nothing here calls it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from tag_names import (  # noqa: E402
    declared_versions,
    missing_from_message,
    names,
    to_publish,
)

#: The shape of the run this check exists for: v0.17.0's message said `digline
#: 0.17.0` and its run published two plugins besides.
V0_17_0 = "digline 0.17.0"
SWEPT = {
    "digline": "0.17.0",
    "digline-anthropic": "0.5.3",
    "digline-openai": "0.5.2",
}


def test_the_real_workspace_is_read() -> None:
    """Against the tree, so a package added to `packages/` is picked up."""
    declared = declared_versions(ROOT)
    assert "digline" in declared
    assert {"digline-anthropic", "digline-openai", "digline-bedrock"} <= set(declared)
    assert all(version and version[0].isdigit() for version in declared.values())


def test_a_version_the_index_serves_is_not_published_again() -> None:
    declared = {"digline": "0.17.0", "digline-anthropic": "0.5.3"}
    served = {"digline": {"0.16.0", "0.17.0"}, "digline-anthropic": {"0.5.3"}}
    assert to_publish(declared, served) == {}


def test_a_version_the_index_lacks_is_published() -> None:
    declared = {"digline": "0.18.0", "digline-anthropic": "0.5.3"}
    served = {"digline": {"0.17.0"}, "digline-anthropic": {"0.5.3"}}
    assert to_publish(declared, served) == {"digline": "0.18.0"}


def test_a_package_the_index_has_never_heard_of_counts() -> None:
    """A first release is the case that most needs naming."""
    assert to_publish({"digline-new": "0.1.0"}, {}) == {"digline-new": "0.1.0"}


def test_the_v0170_message_is_refused() -> None:
    """The control that must fail: the tag as it was actually cut."""
    missing = missing_from_message(V0_17_0, SWEPT)
    assert missing == ["digline-anthropic 0.5.3", "digline-openai 0.5.2"]


def test_the_v0150_style_message_is_accepted() -> None:
    """And the one that must pass: v0.15.0 named its whole family."""
    message = "digline 0.17.0, digline-anthropic 0.5.3, digline-openai 0.5.2"
    assert missing_from_message(message, SWEPT) == []


def test_a_name_without_its_version_does_not_count() -> None:
    """The stale-line case: the package is named, at last release's version.

    This is the one that would otherwise pass a year of bumps.
    """
    message = "digline 0.17.0, digline-anthropic 0.5.2, digline-openai 0.5.2"
    assert missing_from_message(message, SWEPT) == ["digline-anthropic 0.5.3"]


def test_a_version_without_its_name_does_not_count() -> None:
    assert missing_from_message("digline 0.17.0, 0.5.3, 0.5.2", SWEPT) == [
        "digline-anthropic 0.5.3",
        "digline-openai 0.5.2",
    ]


def test_the_separator_and_the_case_are_not_the_point() -> None:
    """A check that argues with punctuation gets bypassed rather than satisfied."""
    for written in (
        "digline-anthropic 0.5.3",
        "digline-anthropic==0.5.3",
        "digline-anthropic @ 0.5.3",
        "digline-anthropic v0.5.3",
        "DIGLINE-ANTHROPIC 0.5.3",
    ):
        assert names(written, "digline-anthropic", "0.5.3"), written


def test_a_longer_version_is_not_a_match() -> None:
    """`0.5.3` must not be read inside `0.5.30`."""
    assert not names("digline-anthropic 0.5.30", "digline-anthropic", "0.5.3")


def test_the_core_name_is_not_read_inside_a_plugin_name() -> None:
    """`digline 0.5.3` is not satisfied by `digline-anthropic 0.5.3`."""
    assert not names("digline-anthropic 0.5.3", "digline", "0.5.3")


def test_nothing_to_publish_names_nothing() -> None:
    assert missing_from_message("anything at all", {}) == []
