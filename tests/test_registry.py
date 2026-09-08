"""The provider registry: names in, factories out, nothing imported early.

The fakes live in `tests/_providers.py` because an entry point names a module by
import path and `.load()` imports it — see that file's docstring.

The two properties worth a test each are the ones a reader cannot check by
looking at the module, because they are about what a *process* did:

- listing what is installed imports no plugin at all;
- resolving one imports that one and no other.

Both are checked in a clean subprocess, the way `test_layering.py` checks that
the core imports on its own — `sys.modules` in this process has been polluted
by every other test in the file by the time anything asks.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest
from tests._providers import REGISTERED, FakeClaimJudge, FakeJudge, FakeTarget

from digline.targets import ProviderNotFound, installed, resolve
from digline.targets.registry import FIRST_PARTY, GROUP, split_coordinate

ROOT = Path(__file__).resolve().parents[1]


def entry(name: str, attribute: str) -> EntryPoint:
    """An `EntryPoint` pointing back into this module, so `.load()` is the real
    one rather than a stand-in for it."""
    return EntryPoint(name=name, value=f"tests._providers:{attribute}", group=GROUP)


#: Installs a fake environment: `only(fake="REGISTERED")` makes `fake` the one
#: provider there is, registered on `tests._providers.REGISTERED`.
Only = Callable[..., None]


@pytest.fixture
def only(monkeypatch: pytest.MonkeyPatch) -> Only:
    """Replace what the environment declares with exactly what a test says."""

    def install(**points: str) -> None:
        monkeypatch.setattr(
            "digline.targets.registry._entry_points",
            lambda: {name: entry(name, attr) for name, attr in points.items()},
        )

    return install


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


def test_a_registered_provider_resolves_to_its_three_factories(only: Only) -> None:
    only(fake="REGISTERED")
    found = resolve("fake")
    assert found is REGISTERED
    assert found.name == "fake"
    assert found.target is FakeTarget
    assert found.judge is FakeJudge
    assert found.claim_judge is FakeClaimJudge


def test_listing_is_sorted_and_says_what_is_there(only: Only) -> None:
    only(zebra="REGISTERED", fake="REGISTERED")
    assert installed() == ("fake", "zebra")


def test_a_missing_first_party_provider_names_the_package_to_install(
    only: Only,
) -> None:
    """The most predictable mistake this format has. The message has to end
    with something the reader can type."""
    only(openai="REGISTERED")
    with pytest.raises(ProviderNotFound) as caught:
        resolve("anthropic")
    message = str(caught.value)
    assert "digline-anthropic" in message
    assert "pip install digline-anthropic" in message
    # And what they do have, so "is it installed?" is answered in the same line.
    assert "openai" in message


def test_an_unknown_provider_lists_what_is_installed_and_the_group(only: Only) -> None:
    """No `pip install digline-llama` invented for a name nobody publishes."""
    only(anthropic="REGISTERED")
    with pytest.raises(ProviderNotFound) as caught:
        resolve("llama")
    message = str(caught.value)
    assert "digline-llama" not in message
    assert GROUP in message
    assert "anthropic" in message


def test_an_empty_environment_still_answers_in_a_sentence(only: Only) -> None:
    only()
    with pytest.raises(ProviderNotFound, match="none"):
        resolve("anthropic")


def test_a_plugin_that_registered_the_wrong_object_is_named_as_the_defect(
    only: Only,
) -> None:
    only(fake="NOT_A_PROVIDER")
    with pytest.raises(ProviderNotFound, match="defect in the plugin"):
        resolve("fake")


def test_a_plugin_whose_record_disagrees_with_its_name_is_refused(only: Only) -> None:
    """A run records the provider name (ADR 0005 §4), so a plugin registered as
    one thing and calling itself another would file runs under a name nobody
    chose."""
    only(fake="MISNAMED")
    with pytest.raises(ProviderNotFound, match="calls itself 'other'"):
        resolve("fake")


# --------------------------------------------------------------------------- #
# What a process actually imported
# --------------------------------------------------------------------------- #


def in_a_clean_process(code: str) -> str:
    done = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    return done.stdout.strip()


def test_listing_the_installed_providers_imports_none_of_them() -> None:
    """Metadata only. A message about a missing provider must not cost the
    import of every provider that is present."""
    printed = in_a_clean_process(
        "import sys;"
        "from digline.targets import installed;"
        "names = installed();"
        "print(bool(names), [m for m in sys.modules if m.startswith('digline_')])"
    )
    assert printed == "True []", printed


def test_resolving_one_provider_does_not_import_another() -> None:
    """The cost this arrangement exists to avoid: a suite judging with
    Anthropic paying for `boto3`."""
    printed = in_a_clean_process(
        "import sys;"
        "from digline.targets import resolve;"
        "resolve('anthropic');"
        "print(sorted(m for m in sys.modules if m.startswith('digline_')))"
    )
    assert "digline_anthropic" in printed
    assert "digline_bedrock" not in printed
    assert "digline_openai" not in printed


# --------------------------------------------------------------------------- #
# The hint table, and the coordinate
# --------------------------------------------------------------------------- #


def test_the_hint_table_names_every_plugin_in_this_workspace() -> None:
    """`FIRST_PARTY` is what turns "no provider named 'bedrock'" into a command
    somebody can run. A fourth plugin that is not listed here would get the
    general sentence instead, which is a worse message and a silent one."""
    shipped = {path.name for path in (ROOT / "packages").iterdir() if path.is_dir()}
    assert set(FIRST_PARTY.values()) == shipped


@pytest.mark.parametrize(
    ("text", "provider", "model"),
    [
        ("anthropic/claude-haiku-4-5", "anthropic", "claude-haiku-4-5"),
        ("openai/gpt-4o-mini", "openai", "gpt-4o-mini"),
        # A Bedrock inference profile carries slashes of its own, so only the
        # first one separates.
        (
            "bedrock/arn:aws:bedrock:eu-west-1:1:inference-profile/eu.anthropic.x",
            "bedrock",
            "arn:aws:bedrock:eu-west-1:1:inference-profile/eu.anthropic.x",
        ),
    ],
)
def test_a_coordinate_splits_on_the_first_slash(
    text: str, provider: str, model: str
) -> None:
    assert split_coordinate(text, field="judge") == (provider, model)


@pytest.mark.parametrize("text", ["anthropic", "", "/claude", "anthropic/"])
def test_a_value_that_is_not_a_coordinate_says_what_one_looks_like(
    text: str,
) -> None:
    with pytest.raises(ValueError, match="anthropic/claude-haiku-4-5"):
        split_coordinate(text, field="judge")
