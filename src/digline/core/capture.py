"""The id a captured case is given, from its input. (ADR 0023 §6, ADR 0002 §5)

Pure, so the import and anything that reads its file compute the same id from
the same input.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from digline.core.types import canonical

__all__ = ["CAPTURE_ID_PREFIX", "capture_id"]

#: What every captured case's id begins with, so a reader of a cases file can
#: tell a case a person elected from one a developer named.
CAPTURE_ID_PREFIX = "cap-"


def capture_id(vars: Mapping[str, object]) -> str:  # noqa: A002 — `Case.vars`
    """`"cap-" + sha256(canonical(vars))[:16]`, the recipe of ADR 0023 §6.

    From the input and nothing else: the same input elected on two branches
    gets one id, and the order its keys were written in does not move it,
    because `canonical` sorts them. The application's own identifiers, a
    date and a sequence number are not in it, for the reasons §6 gives.
    """
    payload = json.dumps(
        canonical(vars), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return CAPTURE_ID_PREFIX + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
