"""What a target and a judge declare about themselves, and the two rules on it.

`ProviderTarget` and `JudgeBase` both answer `config` — the parameters that
decided how the model answered (ADR 0005 §1) — so the two small rules that
answer has to follow live here rather than twice.

Nothing in this module calls anything. It is string and dictionary work, kept
beside the bases that use it because getting either rule wrong is a boundary
mistake rather than a formatting one.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from digline.core import ConfigValue

__all__ = ["endpoint_host", "sent"]


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
