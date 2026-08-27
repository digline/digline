"""The prompt as a file, substituted deterministically.

Two decisions that look small and are not.

**No `str.format`.** A real prompt contains JSON — a tool schema, an example
reply, a few braces in prose — and `format` raises on every one of them. So the
substitution is a regex over `{identifier}` and nothing else: `{"role": "user"}`
is left exactly as written, and the set of variables a template declares is
knowable without executing it.

**Values render deterministically.** The same `vars` must produce the same
prompt, on this machine and on the next one, or two runs differ for a reason
nobody recorded. Numbers and booleans go through `str()`; mappings and sequences
go through JSON with sorted keys and no spaces; anything else is refused by
name, because an object's `str()` may carry a memory address and a prompt that
changes per process is a prompt nobody can reproduce.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

__all__ = ["PromptTemplate", "render_value"]

#: `{name}` where name is a Python identifier. Everything else — `{}`, `{"a":1}`,
#: `{{`, `{ spaced }` — is text and stays text.
_SLOT = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def render_value(value: object, *, where: str) -> str:
    """One `case.vars` value as prompt text, the same way every time."""
    # Read once, before any narrowing: after `isinstance` the static type is a
    # generic whose parameters are unknown, and the name is only for the error.
    kind = type(value).__name__
    if isinstance(value, str):
        return value
    if isinstance(value, bool | int | float) or value is None:
        return str(value)
    if isinstance(value, Mapping | Sequence):
        try:
            return json.dumps(
                cast(object, value),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        except TypeError as exc:
            raise ValueError(
                f"{where} holds a {kind} that is not JSON serialisable: {exc}"
            ) from exc
    raise ValueError(
        f"{where} holds a {kind}, which has no deterministic "
        "text form. Pass a string, a number, a boolean, or something JSON "
        "serialisable: an object's str() may carry a memory address, and a "
        "prompt that differs per process is a prompt nobody can reproduce"
    )


class PromptTemplate:
    """A prompt file, its digest, and the variables it asks for.

    Read at construction, so a path that does not exist fails when the suite is
    imported rather than on the first case.
    """

    __slots__ = ("name", "path", "sha", "text", "variables")

    def __init__(self, path: str | Path) -> None:
        self.path: Path | None = Path(path)
        data = self.path.read_bytes()
        self.text: str = data.decode("utf-8")
        self.sha: str = hashlib.sha256(data).hexdigest()
        self.name: str = str(path)
        self.variables: frozenset[str] = frozenset(_SLOT.findall(self.text))

    @classmethod
    def from_text(cls, text: str, *, name: str = "<inline>") -> PromptTemplate:
        """A template given in the suite rather than in a file.

        It has no path, so it is not an artifact: there is nothing to record
        that the suite's own source does not already carry.
        """
        template = cls.__new__(cls)
        template.path = None
        template.text = text
        template.sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        template.name = name
        template.variables = frozenset(_SLOT.findall(text))
        return template

    def missing_for(self, provided: Mapping[str, object]) -> frozenset[str]:
        return frozenset(self.variables - set(provided))

    def render(self, provided: Mapping[str, object], *, case_id: str = "") -> str:
        where = f"case {case_id!r}" if case_id else "vars"
        missing = self.missing_for(provided)
        if missing:
            raise ValueError(
                f"{where} does not provide {', '.join(sorted(missing))}, which "
                f"{self.name} asks for"
            )
        return _SLOT.sub(
            lambda m: render_value(
                provided[m.group(1)], where=f"{where}, variable {m.group(1)!r}"
            ),
            self.text,
        )

    def __repr__(self) -> str:  # pragma: no cover — diagnostics only
        return f"PromptTemplate({self.name!r}, sha={self.sha[:12]})"
