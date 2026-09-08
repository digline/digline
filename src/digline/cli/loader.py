"""Loading a suite and a target, which are Python objects rather than data.

A `Judge` is an object, a `Target` is a function, a `Disclosure` is declared in
code by construction (ADR 0002). None of that is expressible in YAML without
reinventing a language, and a configuration language grown one escape at a time
ends up unable to express its own delimiters.

So the CLI **imports** the suite; it does not interpret it. And it never goes
looking: a file found by convention is a file that runs by accident.

Two constraints on *how* it loads a suite given as a file path, both learned the
hard way and both non-negotiable:

- **The suite's directory goes on `sys.path`.** A suite imports the application
  under test; that is the normal case. Only for a file path — a
  `package.module:attr` spec is already importable and the path is left alone.
- **It is compiled from source, never through the bytecode cache.** Writing
  `__pycache__` dirties the user's repository; reading it can run a stale suite.
- **So is everything that resolves in that directory**, through a finder scoped
  to it alone — because the application under test is what changes between two
  runs, and a stale copy of it hides the very regression the tool exists to
  find.

See ADR 0002 §9 for all three.
"""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from importlib.machinery import (
    EXTENSION_SUFFIXES,
    SOURCE_SUFFIXES,
    ExtensionFileLoader,
    FileFinder,
    SourceFileLoader,
)
from pathlib import Path
from types import CodeType, ModuleType
from typing import TYPE_CHECKING

from digline.cli.errors import UsageError
from digline.cli.toml_suite import SUITE_SUFFIX, load_toml_suite
from digline.run import Suite, Target

if TYPE_CHECKING:
    from _typeshed import ReadableBuffer

__all__ = [
    "SUITE_ATTR",
    "TARGET_ATTR",
    "Loaded",
    "SourceOnlyLoader",
    "UsageError",
    "load_suite",
    "load_target",
]

SUITE_ATTR = "suite"
TARGET_ATTR = "target"


class SourceOnlyLoader(SourceFileLoader):
    """A loader that always compiles from source, ignoring `__pycache__`.

    Used **only** for the directory holding the suite, which is where the
    application under test lives. Everything else — the standard library, site
    packages, the rest of the user's environment — keeps the normal machinery,
    because bytecode caching there is a performance win with no correctness
    cost: those modules do not change between two runs of an evaluation.
    """

    def get_code(self, fullname: str) -> CodeType:
        path = self.get_filename(fullname)
        return self.source_to_code(self.get_data(path), path)  # type: ignore[return-value]

    def set_data(self, path: str, data: ReadableBuffer, *, _mode: int = 0o666) -> None:
        """Never write bytecode: the artifact is what dirties the user's tree."""
        return None


def _finder(directory: str) -> FileFinder:
    # Deliberately without `BYTECODE_SUFFIXES`: in this directory a lone `.pyc`
    # must not be importable at all.
    return FileFinder(
        directory,
        (SourceOnlyLoader, SOURCE_SUFFIXES),
        (ExtensionFileLoader, EXTENSION_SUFFIXES),
    )


_scoped: set[str] = set()


def _scope_to_source(directory: str) -> None:
    """Make imports resolving in `directory` read from disk, always.

    The reason, found by running the tool and reading the wrong answer: the
    suite itself is compiled from source, but everything it *imports* went
    through the normal machinery — so a helper module edited within the same
    second and to the same length was served from a stale `.pyc`, and a
    comparison reported that nothing had got worse when something had.

    Of every defect met in this project this is the only kind that can hide a
    regression, which is why it is worth a finder rather than a warning.

    The scope is one directory on purpose. A loader for every module would slow
    every import to protect files that do not change during an evaluation, and
    would reach far outside anything this tool has a right to alter.
    """
    real = os.path.realpath(directory)
    if real in _scoped:
        return
    _scoped.add(real)

    def hook(path: str) -> FileFinder:
        if os.path.realpath(path) != real:
            # Not ours: let the next hook — the normal one — answer.
            raise ImportError(f"not the suite directory: {path}")
        return _finder(path)

    sys.path_hooks.insert(0, hook)
    # The cache is consulted before the hooks, so the entry has to be replaced
    # too — otherwise a finder built earlier would keep serving this directory.
    sys.path_importer_cache[directory] = _finder(directory)


def _split(spec: str) -> tuple[str, str | None]:
    """`"pkg.mod:name"` or `"file.py:name"` into module part and attribute.

    Only a trailing `:name` counts, and only when `name` is an identifier, so a
    Windows path like `C:\\suites\\qa.py` is not mistaken for one.
    """
    head, sep, tail = spec.rpartition(":")
    if sep and tail.isidentifier():
        return head, tail
    return spec, None


def _import(module_part: str, spec: str) -> ModuleType:
    if module_part.endswith(".py") or "/" in module_part or "\\" in module_part:
        path = Path(module_part).resolve()
        if not path.is_file():
            raise UsageError(f"no such file: {path} (from {spec!r})")

        # Compiled from source rather than imported through the normal
        # machinery, which reads and writes `__pycache__`. Two reasons, both
        # found by running this against a real repository:
        #
        # 1. Writing bytecode leaves artifacts in the user's repository, and a
        #    repository with new untracked files is a *dirty* one — our own
        #    import would have made every run report itself unreproducible.
        # 2. Reading bytecode can run a stale suite. Python's freshness check is
        #    (mtime, size) with one-second granularity, so a file edited within
        #    the same second and to the same length runs from cache. For a tool
        #    whose premise is reproducibility, "what is on disk" is the only
        #    acceptable answer.
        name = f"_digline_suite_{path.stem}"
        try:
            code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            raise UsageError(f"{path} does not parse: {exc}") from exc

        # The suite's own directory goes on the path before it runs.
        #
        # A suite imports the application it evaluates — that is what a suite
        # *is*, not an exceptional case — so `from brief import judge` has to
        # resolve the way it would under `python suite.py` or under pytest from
        # its rootdir. Without this the first real suite fails on its first line
        # with ModuleNotFoundError, and the tool looks broken because it is.
        #
        # Guarded against duplicates: several suites in one directory, or one
        # loaded twice, must not make `sys.path` grow.
        directory = str(path.parent)
        if directory not in sys.path:
            sys.path.insert(0, directory)
        # …and what resolves there is read from disk, never from bytecode.
        _scope_to_source(directory)

        module = ModuleType(name)
        module.__file__ = str(path)
        # Registered before execution so a module using dataclasses that refer
        # to their own names resolves normally.
        sys.modules[name] = module
        exec(code, module.__dict__)  # noqa: S102 — the user's own suite, by request
        return module

    try:
        return importlib.import_module(module_part)
    except ImportError as exc:
        raise UsageError(f"cannot import module {module_part!r}: {exc}") from exc


def _pick(module: ModuleType, attr: str, spec: str, kind: str) -> object:
    value = getattr(module, attr, None)
    if value is None:
        available = ", ".join(sorted(n for n in vars(module) if not n.startswith("_")))
        raise UsageError(
            f"{spec!r} has no attribute {attr!r} to use as the {kind}. "
            f"Define it, or name it explicitly as '{spec}:<attribute>'. "
            f"Module defines: {available or '(nothing public)'}"
        )
    return value


@dataclass(frozen=True, slots=True)
class Loaded:
    """A suite, and whatever the form it came in still owes the caller.

    A Python suite carries its **module**, because that is where `--target`
    looks. A TOML suite carries its **target**, because it declared one as data
    and there is no module to look in. Exactly one of the two is set, and which
    one is the whole difference between the forms at this layer.
    """

    suite: Suite
    module: ModuleType | None = None
    target: Target | None = None

    @property
    def is_data(self) -> bool:
        return self.module is None


def load_suite(spec: str) -> tuple[Suite, Loaded]:
    """The `Suite`, and how it was loaded.

    The extension chooses the format and nothing else does (ADR 0007 §6): a
    `.toml` is read as data, everything else is imported as it always was. No
    new flag — the CLI already dispatches on the shape of what it is given, and
    one more suffix is the smallest addition to a surface people have learned.
    """
    if spec.endswith(SUITE_SUFFIX):
        path = Path(spec)
        if not path.is_file():
            raise UsageError(f"no such file: {path.resolve()} (from {spec!r})")
        suite, target = load_toml_suite(path)
        return suite, Loaded(suite=suite, target=target)

    module_part, attr = _split(spec)
    module = _import(module_part, spec)
    value = _pick(module, attr or SUITE_ATTR, spec, "suite")
    if not isinstance(value, Suite):
        raise UsageError(f"{spec!r} gave a {type(value).__name__}, not a Suite")
    return value, Loaded(suite=value, module=module)


def load_target(spec: str | None, loaded: Loaded, suite_spec: str) -> Target:
    """The target: declared in the file when the suite is data, imported when
    it is code.

    `--target` has no meaning for a TOML suite and is refused rather than
    ignored. A flag pointing at a Python attribute would be the escape hatch
    ADR 0007 §5 refuses, entered through the command line — and a suite that is
    data has to stay data all the way to what it calls.
    """
    if loaded.target is not None:
        if spec is not None:
            raise UsageError(
                f"--target does not apply to {suite_spec}: a suite that is data "
                "declares its target in [target], and pointing this flag at a "
                "Python attribute would put code back into a suite that is "
                "meant not to have any. Drop the flag, or write a suite.py."
            )
        return loaded.target

    assert loaded.module is not None  # noqa: S101 — one of the two is always set
    if spec is None:
        value = _pick(loaded.module, TARGET_ATTR, suite_spec, "target")
    else:
        module_part, attr = _split(spec)
        module = _import(module_part, spec)
        value = _pick(module, attr or TARGET_ATTR, spec, "target")
    if not callable(value):
        raise UsageError(f"the target is a {type(value).__name__}, not callable")
    return value  # type: ignore[return-value]
