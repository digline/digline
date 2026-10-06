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
import json
import os
import shlex
import sys
from collections.abc import Callable
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

from digline.core import Quoted
from digline.host.authorship import (
    frames_outside,
    raised_inside_digline,
)
from digline.host.errors import UsageError
from digline.host.toml_suite import SUITE_SUFFIX, load_toml_suite
from digline.report.render import visible
from digline.run import Suite, Target, check_target

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
    "refused_exit",
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
        # `compile` is a builtin, so the innermost frame is this one and the
        # frame rule would call the message digline's. It is not: "keyword
        # argument repeated: <name>" quotes a name written in a case, when the
        # cases are written inline. So the site is declared by name, and the
        # line and column are read off the exception. (ADR 0043 §6, amended)
        except SyntaxError as exc:
            raise UsageError(
                Quoted.of(
                    exc,
                    f"{path} does not parse{_line_and_column(exc)}: ",
                    builtin=True,
                )
            ) from exc
        # Named here, at the read, and not by a rule in `main()` that would also
        # catch a decode error inside digline itself. (ADR 0041 §4.2)
        except UnicodeDecodeError as exc:
            raise UsageError(
                f"{path} is not UTF-8 at byte {exc.start}: a suite is read as "
                "UTF-8 source"
            ) from None

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
        # An import the suite cannot satisfy is a refusal with a reader, as it
        # already is for the dotted form below. Unwrapped it was classified as
        # nobody's refusal, so the MCP server passed it on as the bare "Error
        # executing tool <name>" and put the module's name on stderr, where no
        # client reads it — the common case under `uvx`, where a plugin the
        # suite imports is not installed.
        #
        # **And any other exception the suite raises while it loads**, which
        # until ADR 0041 stayed "the unexpected exception it is" (27bc37e) and
        # so exited 1, "worse", from a suite that never got as far as running.
        # By who raised it: anything raised inside digline passes through, a
        # refusal as the refusal it is, an `OSError` as the environment, and
        # anything else to exit 70, because the sentence digline did not write
        # is its own defect; and anything else is the suite's, **a refusal type
        # or an `OSError` included**, refused with the location 27bc37e was
        # protecting and the command that prints the traceback. An `OSError`
        # passed through whatever its frame until #451; its frame is now read
        # past the standard library, so a read the suite asked for is the
        # suite's and one digline asked for is digline's. (ADR 0041 §4.1,
        # ADR 0043 §1)
        try:
            exec(code, module.__dict__)  # noqa: S102 — the user's own suite, by request
        except ImportError as exc:
            raise _could_not_import(
                exc,
                lambda what: f"{path} could not import {what}",
                f". {_INSTALLED_THERE}",
            ) from exc
        # A `SystemExit` beside the rest: not an `Exception`, but the suite's
        # code asking to end digline's process, which is not the suite's to
        # end. Refused by the same rule, with the code it asked for.
        # (ADR 0041 §4.3)
        except (Exception, SystemExit) as exc:
            if raised_inside_digline(exc):
                raise
            reproduce = (
                f"cd {shlex.quote(str(path.parent))} && python -c "
                + shlex.quote(f"import runpy; runpy.run_path({json.dumps(path.name)})")
            )
            raise _raised_while_loading(str(path), exc, reproduce) from exc
        return module

    try:
        return importlib.import_module(module_part)
    except ImportError as exc:
        raise _could_not_import(
            exc, lambda _what: f"cannot import module {module_part!r}"
        ) from exc
    except (Exception, SystemExit) as exc:
        if raised_inside_digline(exc):
            raise
        reproduce = "python -c " + shlex.quote(f"import {module_part}")
        raise _raised_while_loading(repr(module_part), exc, reproduce) from exc


_INSTALLED_THERE = (
    "A suite runs in the environment of the tool that loads it, so what it "
    "imports — a provider plugin, the application under test and its SDK — has "
    "to be installed there."
)


def _could_not_import(
    exc: ImportError, subject: Callable[[str], str], after: str = ""
) -> UsageError:
    """A failed import, with the module's name when the import system named it.

    The common case is the `uvx` one 27bc37e was written for: a plugin is not
    installed, and the module's name is the whole diagnosis. When the message
    is exactly the one the import system writes from the exception's own
    attributes, digline writes it again from those attributes, and that text is
    digline's. Any other message is quoted, because whoever raised it chose
    its words. A suite that imitates the template on purpose gets its text
    through: that is a deliberate act, stated here rather than discovered.
    (ADR 0043 §5)

    `subject` says what could not be imported, given the module's name or
    "a module" when there is none digline can vouch for. A function rather
    than a string, because the file form names the module and the dotted
    form has already named it.
    """
    written = _import_system_said(exc)
    if written is not None:
        return UsageError(f"{subject(repr(exc.name))}: {written}{after}")
    # Nor is `name` read when the message is not the import system's: it is an
    # attribute whoever raised it set, like the message.
    return UsageError(Quoted.of(exc, f"{subject('a module')}: ", after))


def _import_system_said(exc: ImportError) -> str | None:
    """The import system's own sentence, rebuilt from `name`, `name_from` and
    `path`, when `str(exc)` is exactly that; `None` otherwise."""
    name = exc.name
    if name is None:
        return None
    candidates = [f"No module named {name!r}"]
    # `name_from` is set by `from x import y` since Python 3.12, which is the
    # floor this package declares.
    name_from: object = getattr(exc, "name_from", None)
    if isinstance(name_from, str):
        where = exc.path if exc.path is not None else "unknown location"
        candidates.append(f"cannot import name {name_from!r} from {name!r} ({where})")
    said = str(exc)
    return said if said in candidates else None


def _line_and_column(exc: SyntaxError) -> str:
    if exc.lineno is None:
        return ""
    if exc.offset is None:
        return f" at line {exc.lineno}"
    return f" at line {exc.lineno}, column {exc.offset}"


def _raised_while_loading(where: str, exc: BaseException, reproduce: str) -> UsageError:
    """The refusal of a suite whose own code raised while it loaded, with the
    location in place of the traceback.

    27bc37e left this exception unexpected, because a sentence without the
    traceback would hide where the suite failed. The location answers that, and
    so does the command that prints the full traceback. **The refusal is the
    same on every front end, and its rendering is not:** the message is
    `Quoted`'s, the command line prints it, and the MCP server does not. It is
    passed through `visible`, because an exception's message is not digline's
    to vouch for. (ADR 0041 §4, ADR 0043 §3)

    A `SystemExit` is refused here too, and says so: the suite asked digline to
    stop, and digline did, but the code it asked for is not the suite's to
    choose. (ADR 0041 §4.3)
    """
    stopped = (
        " digline stopped, as asked, but the code it runs does not choose its "
        "exit code."
        if isinstance(exc, SystemExit)
        else ""
    )
    return UsageError(
        Quoted.of(
            exc,
            f"{visible(where)} raised ",
            ", while it was being loaded. That is the suite's own code, or code "
            f"it called, run before anything was measured.{stopped}",
            locations=tuple(visible(at) for at in frames_outside(exc)),
            reproduce=visible(reproduce),
            message=visible(_message(exc)),
        )
    )


def _message(exc: BaseException) -> str:
    """What `Quoted.of` would read, so it can be passed through `visible`."""
    if isinstance(exc, SystemExit):
        code = exc.code
        return "" if code is None or isinstance(code, int) else repr(code)
    return str(exc)


def refused_exit(exc: SystemExit) -> UsageError | None:
    """The refusal for a `SystemExit` raised by code digline runs, or `None`
    when digline raised it.

    For the front ends, around everything after the suite has loaded: a
    target, a mapper, a check, a judge, a `preflight` or a property digline
    reads. The request to stop is honoured, because the command stops. The code
    is not, because the person or pipeline that invoked digline owns the
    process, and to them the exit code is digline's contract. A run in progress
    keeps its journal. The driver does not call this: a library caller owns its
    own process, and gets the `SystemExit`. (ADR 0041 §4.3)
    """
    if raised_inside_digline(exc):
        return None
    return UsageError(
        Quoted.of(
            exc,
            "code digline ran raised ",
            ". digline stopped, as asked, but the code it runs does not choose "
            "its exit code. A run in progress keeps its journal: `digline run "
            "--resume` continues it.",
            locations=tuple(visible(at) for at in frames_outside(exc)),
            message=visible(_message(exc)),
        )
    )


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


def load_suite(spec: str, *, root: Path | None = None) -> tuple[Suite, Loaded]:
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
        # `root` is the perimeter a data suite may read inside (ADR 0007 §6).
        # It reaches only the TOML form: a `.py` suite is code and can already
        # open anything, so a boundary there would be decoration. That is
        # true of reading. Crossing is ruled in ADR 0042: the declared
        # artifacts of every format are held to the perimeter in
        # `read_artifacts`, and refused at the exits under `.digline` or `.git`.
        suite, target = load_toml_suite(path, root=root)
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
        check_target(loaded.target)
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
    # Here as well as in `execute()`, so a command that loads the target and
    # never runs it refuses the same shapes. (#423)
    check_target(value)
    return value  # type: ignore[return-value]
