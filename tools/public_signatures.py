"""The required parameters of every public callable, and which ones are new.

From 1.0.0 a minor does not give a public function, method or class a
required parameter it did not have (`RELEASING.md`, *Choosing the version*).
Nothing held that until 1.1.0, which made `digline.host.measure`'s
`marker_root` required: digline-mcp 0.8.1, served by PyPI and admitting the
release, called `measure` without it and raised `TypeError`, and the publish
run stopped the release before PyPI. This reads the surface that promise is
about, so a test can compare it with a tag's.

    uv run python tools/public_signatures.py > now.json
    uv run python tools/public_signatures.py --src <tree>/src > then.json

`--src` puts another tree's `src` first on the path, so the packages read are
that tree's: it is how the fixture of a tag is made, from `git archive`. The
module each package was read from is named on stderr, so a reading of the
wrong tree is seen rather than believed.

**What is read:** every name in the `__all__` of `digline.core`, `digline.run`
and `digline.host`. A function is its signature. A class is its constructor
and every public method it defines or inherits, `self` and `cls` left out.
A parameter is required when it has no default and is not `*args` or
`**kwargs`.

**What it does not see**, said here where the check is: a `Protocol` and its
methods (what is required of an implementer is not what a caller passes), an
`Enum`, a parameter renamed or removed, a positional parameter made
keyword-only, a default that changed, and anything in the other packages'
`__all__`. Only *required parameters added* is compared.
"""

from __future__ import annotations

import enum
import importlib
import inspect
import json
import sys
from collections.abc import Callable
from typing import Any, Protocol

PACKAGES = ("digline.core", "digline.run", "digline.host")


def required(function: Callable[..., Any], *, bound: bool) -> list[str] | None:
    """The required parameters' names, in order, or `None` where Python cannot
    give a signature (a builtin)."""
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return None
    names: list[str] = []
    for index, parameter in enumerate(signature.parameters.values()):
        if bound and index == 0:
            continue
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if parameter.default is parameter.empty:
            names.append(parameter.name)
    return names


def _is_protocol(cls: type) -> bool:
    return bool(getattr(cls, "_is_protocol", False)) or Protocol in cls.__mro__


def _methods(cls: type) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for klass in reversed(cls.__mro__[:-1]):
        for name, member in vars(klass).items():
            if name.startswith("_"):
                continue
            if isinstance(member, staticmethod):
                names = required(member.__func__, bound=False)
            elif isinstance(member, classmethod):
                names = required(member.__func__, bound=True)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            elif inspect.isfunction(member):
                names = required(member, bound=True)
            else:
                continue
            if names is not None:
                found[name] = names
    return found


def signatures() -> dict[str, list[str]]:
    """`{"package.Name": [required, ...], "package.Class.method": [...]}`."""
    found: dict[str, list[str]] = {}
    for package in PACKAGES:
        module = importlib.import_module(package)
        print(f"read: {package} from {module.__file__}", file=sys.stderr)
        for name in getattr(module, "__all__", ()):
            value: object = getattr(module, name, None)
            key = f"{package}.{name}"
            if isinstance(value, type):
                cls: type[object] = value  # pyright: ignore[reportUnknownVariableType]
                if _is_protocol(cls) or issubclass(cls, enum.Enum):
                    continue
                names = required(cls, bound=False)
                if names is not None:
                    found[key] = names
                for method, method_names in _methods(cls).items():
                    found[f"{key}.{method}"] = method_names
            elif callable(value):
                names = required(value, bound=False)
                if names is not None:
                    found[key] = names
    return dict(sorted(found.items()))


def added(then: dict[str, list[str]], now: dict[str, list[str]]) -> list[str]:
    """One line per required parameter a callable has now and did not have
    then, for every callable in both, in name order."""
    lines: list[str] = []
    for key in sorted(set(then) & set(now)):
        for name in now[key]:
            if name not in then[key]:
                lines.append(f"required parameter added  {key}: {name}")
    return lines


def main(argv: list[str]) -> int:
    if argv[:1] == ["--src"] and len(argv) == 2:
        sys.path.insert(0, argv[1])
    elif argv:
        print(__doc__, file=sys.stderr)
        return 2
    json.dump(signatures(), sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
