"""What a target and a judge declare about themselves, and the rules on it.

`ProviderTarget` and `JudgeBase` both answer `config` — the parameters that
decided how the model answered (ADR 0005 §1) — so the two small rules that
answer has to follow live here rather than twice.

`declared_config` is the third, and it is a different kind of rule: the two
above shape a configuration written in this repository and reviewed with it,
while an `HttpTarget` reads one out of an answer written by an application
nobody here reviews. There the contract has to be *enforced* rather than
followed, which is why the closed key table lives beside them (ADR 0005 §8).

Nothing in this module calls anything. It is string and dictionary work, kept
beside the bases that use it because getting any of these wrong is a boundary
mistake rather than a formatting one.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast
from urllib.parse import urlsplit

from digline.core import ConfigValue

__all__ = ["CONTRACT_FIELDS", "declared_config", "endpoint_host", "sent"]


def sent(**values: ConfigValue) -> dict[str, ConfigValue]:
    """Only what was actually sent: an unset parameter is **absent**.

    Not `None`. "We did not send it, so the provider's own default applied" and
    "we sent nothing for it" are different facts, and only absence states the
    first one honestly — which is what lets a comparison report `new` the day a
    suite starts pinning a temperature it used to leave alone.
    """
    return {key: value for key, value in values.items() if value is not None}


def endpoint_host(base_url: str | None) -> str | None:
    """Host and port of a custom endpoint. `None` for the provider's own.

    Never the scheme, never the path, and — the reason this is a function rather
    than the string itself — **never the userinfo**. `https://user:secret@gw/v1`
    is a URL somebody will write one day, and ADR 0004 §5 makes a credential the
    one category of payload that no `Disclosure` can release. Reaching into the
    parse for the host is what makes that structural instead of hopeful.

    What survives is still the client's topology, which is why it is the one
    field redaction keeps back (ADR 0005 §2).
    """
    if base_url is None:
        return None
    parsed = urlsplit(base_url if "//" in base_url else f"//{base_url}")
    if not parsed.hostname:
        return None
    return f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname


#: The keys a configuration may hold: the closed table of ADR 0005 §1.
#:
#: Enforced here and nowhere else, because this is the one place the values are
#: written by somebody outside this repository. A plugin declares what it
#: actually sends and is reviewed; an application behind HTTP is not, and ADR
#: 0005 §1 keeps what is outside the contract out of the record — an open
#: mapping of unknown keys is exactly where an account identifier or a
#: customer's own tuning would end up, in the box where nobody can check it.
CONTRACT_FIELDS = frozenset(
    {
        "provider",
        "model",
        "max_tokens",
        "temperature",
        "top_p",
        "top_k",
        "seed",
        "region",
        "base_url",
        "response_format",
        "json_mode",
    }
)


def declared_config(found: object, *, where: str) -> dict[str, ConfigValue]:
    """A configuration an application reported, checked before it is believed.

    `where` names the path it was read from, so every refusal below points at
    the field in the answer rather than at this function.

    The rules are ADR 0005's, applied at the one boundary that needs them
    enforced rather than reviewed: the closed key table, scalars only, `null`
    read as *not sent*, `base_url` reduced to its host, and a configuration that
    cannot say who answered refused outright.
    """
    if not isinstance(found, Mapping):
        raise ValueError(
            f"{where!r} holds a {type(found).__name__}, not an object: a "
            "configuration is a flat object of scalars, so that a comparison "
            "can render it field by field"
        )
    entries = cast("Mapping[str, object]", found)

    unknown = sorted(set(entries) - CONTRACT_FIELDS)
    if unknown:
        raise ValueError(
            f"{where!r} declares {', '.join(unknown)}, which is not part of "
            f"the configuration contract (ADR 0005 §1). Allowed: "
            f"{', '.join(sorted(CONTRACT_FIELDS))}. What is outside the "
            "contract stays outside the record — put it in a file and declare "
            "it in `Suite.artifacts`, where it is diffed instead of guessed at"
        )

    checked: dict[str, ConfigValue] = {}
    for key, value in entries.items():
        if value is not None and not isinstance(value, str | int | float | bool):
            raise ValueError(
                f"{where!r} records {key!r} as a {type(value).__name__}, which "
                "is not a scalar: a configuration is diffed field by field and "
                "rendered by value, and a nested one has no such sentence"
            )
        checked[key] = value

    for key in ("provider", "model"):
        value = checked.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"{where!r} gives no {key}: a configuration that cannot say "
                "who answered, and as what, names no system. Report it as a "
                "non-empty string, or leave the whole object out"
            )

    # `null` is *not sent*, exactly as `sent()` reads an unset parameter above:
    # the provider's own default applied, and only absence says so honestly.
    declared: dict[str, ConfigValue] = {
        key: value for key, value in checked.items() if value is not None
    }
    # Never the scheme, never the path, never the userinfo — and reduced here
    # rather than trusted, because an application reporting its own endpoint is
    # far likelier to send the whole URL than a plugin is (ADR 0004 §5).
    if "base_url" in declared:
        host = endpoint_host(str(declared["base_url"]))
        if host is None:
            del declared["base_url"]
        else:
            declared["base_url"] = host
    return declared
