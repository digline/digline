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

import re
from collections.abc import Mapping
from typing import cast
from urllib.parse import urlsplit

from digline.core import ConfigValue

#: What may appear in a hostname: letters, digits, dot, dash, underscore, and
#: the `[`, `]`, `:` and `%` an IPv6 literal with a zone id needs. Deliberately
#: a shape test and not a resolver — the question is "is this a host at all",
#: which a string with a space in it answers on its own.
_HOST = re.compile(r"^[A-Za-z0-9._\-\[\]:%]+$")

__all__ = [
    "CONTRACT_FIELDS",
    "declared_config",
    "endpoint_host",
    "expected_config",
    "refuse_config_mismatch",
    "sent",
]


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
    try:
        parsed = urlsplit(base_url if "//" in base_url else f"//{base_url}")
        hostname, port = parsed.hostname, parsed.port
    except ValueError:
        # A netloc `urlsplit` cannot take apart — a non-numeric port is the
        # common one. There is no host to report, and reporting the string
        # instead is the mistake this whole function exists to refuse.
        return None
    if not hostname or not _HOST.match(hostname):
        # `urlsplit` is happy to call anything before the first `/` a host, so
        # `endpoint_host("not a url at all sk-SECRET")` used to answer with the
        # whole lowercased string — a "host" containing a space, recorded in
        # every run and printed in every message about the endpoint. A value
        # that is not a host has none, and `None` is what that is called.
        return None
    return f"{hostname}:{port}" if port else hostname


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
#: Deliberately **not** `resolved_model` or `fingerprint`. A plugin records them
#: because it read them out of its own SDK's reply; this table governs the one
#: boundary where the values arrive over HTTP from an application nobody here
#: reviews, and ADR 0005 §9 leaves that widening until there is an application
#: with one to report. Nothing checks a plugin's keys against this set.


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


def expected_config(found: object, *, where: str) -> dict[str, ConfigValue]:
    """The configuration a **suite** declares it expects, checked as it is read.

    The other side of `declared_config`, and the reason ADR 0030 §4 is a repair
    rather than a workaround: over HTTP the measured party writes every field it
    reports, so the only way a reviewed value can reach the record is for a
    reviewer to have written one. This is that value, and it is checked here so
    that a declaration which could never match is refused when it is written
    instead of on every case of every run.

    A **partial** declaration: the keys named here are the keys checked, and
    ADR 0030 §5.2 rules that none of them is mandatory. What is refused is an
    empty one — a gate that checks nothing passes everything, and a check that
    cannot fail is the bug fixed decision 3 names.
    """
    if not isinstance(found, Mapping):
        raise ValueError(
            f"{where} is a {type(found).__name__}, not a table: a declared "
            "configuration is the same flat object of scalars an application "
            "reports, so that the two can be compared field by field"
        )
    entries = cast("Mapping[str, object]", found)
    if not entries:
        raise ValueError(
            f"{where} declares nothing. An empty declaration accepts every "
            "configuration an application could report, which is the state a "
            "suite is in when it omits the key — so it is refused rather than "
            "read as a review that happened. Name the fields you expect, or "
            "leave the key out"
        )

    unknown = sorted(set(entries) - CONTRACT_FIELDS)
    if unknown:
        raise ValueError(
            f"{where} declares {', '.join(unknown)}, which is not part of the "
            f"configuration contract (ADR 0005 §1). Allowed: "
            f"{', '.join(sorted(CONTRACT_FIELDS))}. An application cannot "
            "report a field outside the contract, so an expectation of one "
            "could never be met"
        )

    checked: dict[str, ConfigValue] = {}
    for key, value in entries.items():
        # `None` is refused here and read as *not sent* in a reported
        # configuration, which is the asymmetry this pair of functions is for:
        # absence is an honest thing for an application to report and an empty
        # thing for a suite to declare. "I expect nothing for this" is what
        # leaving the key out already says.
        if value is None or not isinstance(value, str | int | float | bool):
            named = "nothing" if value is None else type(value).__name__
            raise ValueError(
                f"{where} declares {key!r} as {named}, which is not a scalar "
                "value to compare against: an expectation is met by equality "
                "with what the application reported, so it has to be the value "
                "you expect"
            )
        if isinstance(value, str) and not value:
            raise ValueError(
                f"{where} declares {key!r} as an empty string: an application "
                "that reported one would be refused by the contract, so this "
                "expectation could never be met"
            )
        checked[key] = value
    return checked


def refuse_config_mismatch(
    reported: Mapping[str, ConfigValue],
    expected: Mapping[str, ConfigValue],
    *,
    spoken: str,
) -> None:
    """Refuse a reported configuration that contradicts the suite's declaration.

    ADR 0030 §4. `spoken` names the endpoint, because the refusal is about what
    an endpoint said and a reader needs to know which one.

    **An expected key the application never reports is a mismatch too.** §8
    reads a missing key as *not sent, the provider's own default applied*, which
    is an honest reading of an application's silence and a dishonest one here:
    the suite asked a question and got none of an answer. Absence is not
    agreement (ADR 0030 §7).
    """
    moved = sorted(key for key in expected if reported.get(key) != expected[key])
    if not moved:
        return
    said: list[str] = []
    for key in moved:
        if key in reported:
            said.append(
                f"{key}: declared {expected[key]!r}, reported {reported[key]!r}"
            )
        else:
            said.append(f"{key}: declared {expected[key]!r}, not reported at all")
    differences = ", ".join(said)
    raise ValueError(
        f"{spoken} answered under a configuration the suite did not declare "
        f"({differences}). `expect_config` is what makes the configuration in "
        "the record a value a reviewer wrote rather than one the application "
        "chose, so a value it did not declare is refused rather than recorded "
        "(ADR 0030 §4). Two things this can be, and they are fixed at "
        "different ends: the application moved, or the declaration is stale — "
        "point the target at the system you meant to measure, or update "
        "`expect_config` to the one that answered"
    )
