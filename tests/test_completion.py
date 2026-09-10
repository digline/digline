"""The record `_complete` returns, and the identity it carries (ADR 0004 §6).

Two guarantees are load-bearing here and neither is visible from a plugin's own
tests. The **pair still works**, permanently, which is what makes third-party
plugins unaffected by construction; and an unrecognised finish reason becomes
`other` and never `stop`, which is fixed decision 3 arriving through the door a
provider opens when it adds a word next quarter.
"""

from __future__ import annotations

import pytest

from digline.core import Finish
from digline.targets import Completion, ObservedIdentity, Usage, as_completion

USAGE = Usage(input_tokens=10, output_tokens=4)
TABLE: dict[str, Finish] = {"end_turn": "stop", "max_tokens": "length"}


def a_reply(**kwargs: object) -> Completion:
    return Completion(text="Rome.", usage=USAGE, **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# The pair is still a return, and always will be
# --------------------------------------------------------------------------- #


def test_a_plugin_that_returns_the_pair_still_works() -> None:
    """The whole compatibility claim of ADR 0004 §6, in one assertion. A plugin
    written before the record keeps working, unchanged and unrecompiled."""
    read = as_completion(("Rome.", USAGE))
    assert read.text == "Rome."
    assert read.usage == USAGE


def test_the_pair_says_nothing_about_tools_rather_than_saying_none() -> None:
    """The reading that matters: a plugin returning a pair has not reported that
    the model called no tools, it has not reported at all. `ToolsCalled` errors
    on the first and judges the second."""
    assert as_completion(("Rome.", USAGE)).tools is None
    assert a_reply(tools=()).tools == ()


def test_a_record_is_passed_through_unchanged() -> None:
    record = a_reply(finish="stop")
    assert as_completion(record) is record


# --------------------------------------------------------------------------- #
# The vocabulary
# --------------------------------------------------------------------------- #


def test_a_known_word_is_translated_and_kept() -> None:
    from digline.targets import finish_of

    assert finish_of("max_tokens", TABLE) == ("length", "max_tokens")


def test_an_unknown_word_is_other_and_never_stop() -> None:
    """A provider that adds a stop reason must not turn a truncated run green on
    upgrade. `other` plus the word is the honest answer; `stop` would be the
    vacuously green assertion of fixed decision 3."""
    from digline.targets import finish_of

    finish, raw = finish_of("brand_new_reason", TABLE)
    assert finish == "other"
    assert raw == "brand_new_reason"


@pytest.mark.parametrize("said", [None, ""])
def test_a_provider_that_said_nothing_stays_nothing(said: str | None) -> None:
    """So every consumer falls back to what it did before the record existed."""
    from digline.targets import finish_of

    assert finish_of(said, TABLE) == (None, None)


# --------------------------------------------------------------------------- #
# What reaches the mapper
# --------------------------------------------------------------------------- #


def test_only_what_was_reported_reaches_the_metadata() -> None:
    """A key present means the provider said something. That is what lets
    `ToolsCalled` tell *called nothing* from *nobody asked*."""
    assert dict(as_completion(("Rome.", USAGE)).as_metadata()) == {}
    assert dict(
        a_reply(tools=(), finish="stop", finish_raw="end_turn").as_metadata()
    ) == {
        "finish": "stop",
        "finish_raw": "end_turn",
        "tools": [],
    }


def test_the_observed_identity_reaches_the_metadata_under_its_recorded_names() -> None:
    """The same names the run records (ADR 0005 §9), so a reader meets one
    spelling in the response bag and in the configuration delta."""
    found = dict(a_reply(model="gpt-x-2026-01-01", fingerprint="fp_1").as_metadata())
    assert found == {"resolved_model": "gpt-x-2026-01-01", "fingerprint": "fp_1"}


# --------------------------------------------------------------------------- #
# The identity, and the rotation split
# --------------------------------------------------------------------------- #


def test_nothing_observed_is_nothing_recorded() -> None:
    """Bedrock Converse, every run: its reply carries no model id at all, and
    the record says so rather than echoing the request back."""
    seen = ObservedIdentity("anthropic.claude-x")
    seen.see(a_reply(finish="stop"))
    assert seen.values == {"resolved_model": None, "fingerprint": None}


def test_the_first_observation_is_the_runs() -> None:
    seen = ObservedIdentity("claude-sonnet-5")
    for _ in range(3):
        seen.see(a_reply(model="claude-sonnet-5-20260115"))
    assert seen.values["resolved_model"] == "claude-sonnet-5-20260115"


def test_a_model_that_rolled_part_way_through_raises() -> None:
    """ADR 0005 §8's rule arriving on the side §8 assumed was safe. The caller
    lets it out and the driver errors that one case; the run is still written."""
    seen = ObservedIdentity("claude-sonnet-5")
    seen.see(a_reply(model="claude-sonnet-5-20260115"))
    with pytest.raises(ValueError, match="part way through the run") as caught:
        seen.see(a_reply(model="claude-sonnet-5-20260301"))
    # The alias is named too: it is what the two observations were hiding behind.
    assert "claude-sonnet-5'" in str(caught.value)


def test_a_fingerprint_that_rolled_goes_absent_and_does_not_raise() -> None:
    """OpenAI documents `system_fingerprint` as changing whenever they change
    the backend, so raising would paint runs red for an event with no bearing on
    which model answered. Absent reads as *the provider did not say*."""
    seen = ObservedIdentity("gpt-5-mini")
    seen.see(a_reply(fingerprint="fp_1"))
    seen.see(a_reply(fingerprint="fp_2"))
    assert seen.values["fingerprint"] is None


def test_a_rotated_fingerprint_does_not_take_the_model_with_it() -> None:
    """Two fields measuring different things get different rules, and one going
    absent must not silence the other."""
    seen = ObservedIdentity("gpt-5-mini")
    seen.see(a_reply(model="gpt-5-mini-2026-01-01", fingerprint="fp_1"))
    seen.see(a_reply(model="gpt-5-mini-2026-01-01", fingerprint="fp_2"))
    assert seen.values == {
        "resolved_model": "gpt-5-mini-2026-01-01",
        "fingerprint": None,
    }
