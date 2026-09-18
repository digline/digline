"""Neutralising third-party text in a rendered document, once, for every front end.

`digline.cli` escaped DEL and C1 in `output.emit()`, on the serialised JSON, and
that worked for exactly as long as there was one front end. `digline-mcp` hands
dictionaries to an SDK that serialises them itself, so nothing digline owns ever
sees those bytes, and a tool name carrying U+009B reached an MCP client raw — the
fourth time this family has bitten, and the first at a door built after the rule
was written.

So the rule moves to the one place both front ends already share. A document
rendered here is neutralised before it is returned, and a front end inherits it
without knowing it exists — which is the only version of this that survives a
third one. What it costs a consumer is stated at `OUTPUT_VERSION` 2.
(from the release delta-pass over 0.15.0)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from digline.core import json_visible

__all__ = ["neutralised"]


def _walk(value: object) -> object:
    """The recursion, over the shapes a rendered document is made of.

    `str` before `Sequence`, because a string is one and would otherwise be taken
    apart character by character. `Mapping` covers keys as well as values: a
    `Score.metadata` key is suite-supplied and a config key can carry a
    provider's own field name.
    """
    if isinstance(value, str):
        return json_visible(value)
    if isinstance(value, Mapping):
        items = cast("Mapping[object, object]", value)
        return {_walk(key): _walk(item) for key, item in items.items()}
    if isinstance(value, list | tuple):
        members = cast("Sequence[object]", value)
        walked = [_walk(item) for item in members]
        return tuple(walked) if isinstance(value, tuple) else walked
    return value


def neutralised[T](document: T) -> T:
    """`document` with DEL and C1 written as JSON escapes in every string in it.

    Idempotent, which is what makes it safe to apply at more than one level: once
    a `\\u009b` has been written as six ASCII characters there is nothing left
    for a second pass to find. So a builder that calls another builder does not
    have to know whether the inner one already did it, and `output.emit()` can
    stay as a second belt without double-escaping anything.

    The cast is the honest shape of this: the walk rebuilds containers, so it
    cannot be expressed as returning the same type it was handed without saying
    so once, here, rather than at each of the seven call sites.
    """
    return cast("T", _walk(document))
