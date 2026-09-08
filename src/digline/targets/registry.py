"""Provider plugins, found by name.

Fixed decision 6 in `CLAUDE.md` — *"providers as plugins (entry points), not
vendored into the repo"* — becoming real. It was stated from the first commit
and implemented nowhere until a judge could be named in data
(ADR 0007 §3): `judge = "anthropic/claude-haiku-4-5"` has to reach
`AnthropicJudge` without anything under `src/` importing `digline_anthropic`.

**Resolution is by name, never by import.** `tests/test_layering.py` forbids
every module shipped with digline from importing a package that depends on
digline, and this module does not weaken that: it reads what the environment
declares under the `digline.providers` entry point group and knows nothing
about what exists. A provider nobody installed is a message, not a missing
import.

**Nothing is loaded until it is asked for.** Listing the installed names reads
metadata only; `resolve()` is what imports one plugin, and only the one named.
Loading all of them to answer a question about one would mean a suite judging
with Anthropic pays for importing `boto3`, which is the cost this whole
arrangement exists to avoid.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from importlib.metadata import EntryPoint, entry_points
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from digline.core import ClaimJudge, Judge
    from digline.run import Target

__all__ = [
    "GROUP",
    "Provider",
    "ProviderNotFound",
    "clear_cache",
    "installed",
    "resolve",
    "split_coordinate",
]

#: The entry point group a plugin registers under. Part of the plugin contract
#: (ADR 0004) and therefore not a thing to rename lightly: a released plugin
#: declares this string in its own metadata, and changing it here would make
#: every published plugin invisible at once.
GROUP = "digline.providers"

#: What to install for a first-party provider that is not there. A table of two
#: strings each, and deliberately not an import: naming a package is not
#: depending on it, and the layering gate reads imports. A provider outside this
#: table gets the general sentence instead of a wrong `pip install`.
FIRST_PARTY = {
    "anthropic": "digline-anthropic",
    "openai": "digline-openai",
    "bedrock": "digline-bedrock",
}


class ProviderNotFound(LookupError):
    """No installed plugin registers that provider name.

    A `LookupError` and not a `UsageError`: `digline.targets` sits below the
    CLI and has no business knowing that a command line exists. The loader
    catches this and re-raises it as the usage error it is at that layer.
    """


@dataclass(frozen=True, slots=True)
class Provider:
    """What a plugin registers under its name: the three things ADR 0004 §1
    makes every plugin ship.

    Factories rather than instances, because the suite decides the model and
    the set-up. They are the plugin's own classes — `AnthropicTarget` and its
    two judges — and this record exists so that the mapping from a name to them
    is data the plugin declares, rather than a lookup digline performs on a
    module it had to import first.

    **They are called with keywords, and `model` is the one name the contract
    fixes.** A plugin's positional order is its own business: every published
    target happens to take `prompt_file` first, so a caller passing the model
    positionally would fill the wrong parameter and fail somewhere else
    entirely. Everything beyond `model` is whatever that plugin names.
    """

    #: The coordinate's first half, and what a run records as `provider`
    #: (ADR 0005 §4). It is repeated here rather than taken from the entry
    #: point's name so that a plugin declaring one and answering to another
    #: fails loudly, at the moment of resolution, rather than producing runs
    #: filed under a name nobody chose.
    name: str
    target: Callable[..., Target]
    judge: Callable[..., Judge]
    claim_judge: Callable[..., ClaimJudge]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Provider.name must not be empty")


@cache
def _entry_points() -> dict[str, EntryPoint]:
    """Name → entry point, without importing any of them.

    Cached because the metadata of an environment does not change while a
    process runs, and reading it is not free. `clear_cache()` exists for the
    one caller that needs it: a test that installs a fake.
    """
    found: dict[str, EntryPoint] = {}
    for point in entry_points(group=GROUP):
        # First registration wins, and a duplicate is not an error here: two
        # plugins claiming one name is a broken environment, and the sentence
        # that says so belongs where a person can act on it — `resolve()`.
        found.setdefault(point.name, point)
    return found


def installed() -> tuple[str, ...]:
    """The provider names this environment declares, sorted.

    Metadata only: nothing is imported, so this is safe to call in an error
    message about something else.
    """
    return tuple(sorted(_entry_points()))


def clear_cache() -> None:
    """Forget what the environment declared. For a test that installs a fake
    plugin after this module has already answered once."""
    _entry_points.cache_clear()


def resolve(name: str) -> Provider:
    """The plugin registered under `name`, imported now and not before.

    Raises `ProviderNotFound` with the package to install when there is no such
    provider — the most predictable mistake this format has, and one that
    deserves a sentence rather than a `KeyError`.
    """
    point = _entry_points().get(name)
    if point is None:
        raise ProviderNotFound(_missing(name))

    loaded = point.load()
    if not isinstance(loaded, Provider):
        # A plugin that registered the wrong object. Named as the plugin's
        # defect, because it is: the user cannot fix it and should not be
        # invited to try.
        raise ProviderNotFound(
            f"the plugin registered as provider {name!r} ({point.value}) gave "
            f"a {type(loaded).__name__}, not a digline Provider. That is a "
            "defect in the plugin, not in this suite: report it against the "
            "package that ships it"
        )
    if loaded.name != name:
        raise ProviderNotFound(
            f"the plugin registered under the name {name!r} calls itself "
            f"{loaded.name!r}. A run records the provider name, so the two "
            "cannot differ: report it against the package that ships it"
        )
    return loaded


def _missing(name: str) -> str:
    """The sentence a missing provider gets. Its whole job is to end with
    something the reader can type."""
    have = installed()
    listing = ", ".join(have) if have else "none"
    # A near miss before anything else: `anthropi` is a typo, and telling
    # somebody to install a package they already have would be a worse answer
    # than saying so.
    close = difflib.get_close_matches(name, [*have, *FIRST_PARTY], n=1, cutoff=0.6)
    if close and close[0] in have:
        return (
            f"no provider named {name!r} is installed. Did you mean "
            f"{close[0]!r}? Installed providers: {listing}"
        )
    if (package := FIRST_PARTY.get(name)) is not None:
        return (
            f"no provider named {name!r} is installed. It comes from "
            f"{package}: `uv add {package}`, or `pip install {package}`. "
            f"Installed providers: {listing}"
        )
    return (
        f"no provider named {name!r} is installed. Installed providers: "
        f"{listing}. A provider comes from a plugin that registers it under "
        f"the {GROUP!r} entry point; the ones digline publishes are "
        f"{', '.join(sorted(FIRST_PARTY.values()))}"
    )


def split_coordinate(text: str, *, field: str) -> tuple[str, str]:
    """`"anthropic/claude-haiku-4-5"` into provider and model.

    Split on the **first** separator only: a Bedrock inference profile is a
    model identifier with slashes of its own, and a rule that refused it would
    refuse the provider whose identifiers most need naming.

    `field` is where the value came from, so the error can point at the line
    rather than at the value.
    """
    provider, sep, model = text.partition("/")
    if not sep or not provider or not model:
        raise ValueError(
            f"{field} is {text!r}, which is not a provider/model coordinate. "
            "Write the provider, a slash, and the model — for example "
            "'anthropic/claude-haiku-4-5'"
        )
    return provider, model
