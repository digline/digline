"""The names a shipped plugin reaches for in digline, read by type (#702).

A method or attribute a plugin calls on something digline gives it is public
surface, as much as a name it imports (`RELEASING.md`, *a public name is read
in three levels*: the second is a name a shipped plugin calls): a release that
moves it breaks the plugin. `INTRODUCED` in `tests/test_plugin_floors.py`
dates the names a plugin imports. This lists the others.

A match on the attribute's name alone is an upper bound and not the list: it
took `list.append` for `Journal.append`, and the `.text`, `.content` and
`.model` of an SDK's reply for a digline object's (104 pairs, measured at
`fc63625d`). So this reads the receiver's **type**, from pyright:

1. each plugin's sources are copied, and every receiver whose attribute some
   class in `digline` defines is wrapped in `reveal_type(...)`, where it is
   read and not where it is assigned;
2. pyright, run over the copy with this environment, says what type each
   receiver has;
3. the attribute is counted when, in the MRO of the receiver's class, the
   class that defines it is in a `digline` module. So a plugin's own class
   that inherits `config` from `ProviderTarget` counts `config`, and an SDK's
   `.model` does not.

Beside the attributes it lists the names a plugin imports out of `digline`, at
the import and at each use of the name: `refuse_unreadable_baseline` is the
control, imported and called once each in pytest-digline. Those are already
dated by `INTRODUCED`.

    uv run python tools/plugin_calls.py

prints one line per (plugin, kind, name) with how many places, then one line
per **unresolved** receiver and their count. It exits 0: what it prints is a
list to read, not a verdict.

**An unresolved receiver is not measured, never not present.** pyright typed
it `Any` or `Unknown`, so whether its attribute is digline's is unknown, and
it is counted neither way. A count of unresolved receivers is part of the
result, as much as the list: the list is the floor of what the plugins reach
for, and the unresolved receivers are where it may be higher. Measured on the
tree that added this, they are six, each a reply of the Anthropic SDK.

**What else it does not see.** A class pyright names that is neither
digline's nor the plugin's own is read as a third party's and not counted. A
short type name two `digline` classes share is counted when either defines
the attribute. An attribute that is assigned and never read is not wrapped.
A name bound by a `digline` import and later rebound in the same module is
still read as the import's.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
import pkgutil
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"

_SITE = re.compile(r'expected "__site_(\d+)" but received "(.*)"', re.S)


@dataclass(frozen=True)
class Site:
    plugin: str
    path: str
    line: int
    receiver: str
    attr: str


def _digline_classes() -> dict[str, list[type]]:
    """Every class defined in a `digline` module, by its short name."""
    import digline

    found: dict[str, list[type]] = {}
    for info in pkgutil.walk_packages(digline.__path__, "digline."):
        if info.name.endswith(".__main__"):
            continue  # it runs the command line on import
        module = importlib.import_module(info.name)
        for value in vars(module).values():
            if inspect.isclass(value) and value.__module__ == info.name:
                found.setdefault(value.__name__, []).append(value)
    return found


def _members(cls: type) -> set[str]:
    names: set[str] = set()
    for klass in cls.__mro__:
        names |= set(vars(klass))
        names |= set(getattr(klass, "__annotations__", {}))
    return names


def _defined_in_digline(cls: type, attr: str) -> bool:
    """Whether the class in `cls`'s MRO that defines `attr` is digline's."""
    for klass in cls.__mro__:
        if attr in vars(klass) or attr in getattr(klass, "__annotations__", {}):
            module = klass.__module__
            return module == "digline" or module.startswith("digline.")
    return False


def _plugin_sources(plugin: Path) -> list[Path]:
    return sorted((plugin / "src").rglob("*.py"))


def _wrap(
    source: bytes, candidates: set[str], first: int
) -> tuple[bytes, list[tuple[int, int, str, str]]]:
    """`source` with each candidate receiver wrapped, and the sites wrapped:
    `(site number, line, receiver text, attribute)`."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))

    def offset(lineno: int, col: int) -> int:
        return starts[lineno - 1] + col

    inserts: list[tuple[int, int, bytes]] = []
    sites: list[tuple[int, int, str, str]] = []
    number = first
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or node.attr not in candidates:
            continue
        if not isinstance(node.ctx, ast.Load):
            # Wrapped, `self.x = ...` would no longer declare `x` on the class,
            # and every later read of `x` would come back unknown.
            continue
        receiver = node.value
        assert receiver.end_lineno is not None and receiver.end_col_offset is not None
        start = offset(receiver.lineno, receiver.col_offset)
        end = offset(receiver.end_lineno, receiver.end_col_offset)
        span = end - start
        # At one offset, the opening of the wider receiver goes leftmost and the
        # closing of the narrower one does: so applied from the end, the
        # narrower opening is inserted first and the wider closing first.
        inserts.append((start, -span, b"reveal_type("))
        inserts.append((end, span, f', expected_text="__site_{number}")'.encode()))
        sites.append((number, node.lineno, ast.unparse(receiver), node.attr))
        number += 1
    out = bytearray(source)
    for at, _, text in sorted(inserts, key=lambda i: (i[0], i[1]), reverse=True):
        out[at:at] = text
    return bytes(out), sites


def _imported_names(source: str) -> Counter[str]:
    """Each name a module imports out of `digline`, at the import and at each
    use of the name it binds."""
    tree = ast.parse(source)
    bound: dict[str, str] = {}
    places: Counter[str] = Counter()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.level == 0
            and (node.module == "digline" or node.module.startswith("digline."))
        ):
            for alias in node.names:
                bound[alias.asname or alias.name] = alias.name
                places[alias.name] += 1
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in bound:
            places[bound[node.id]] += 1
    return places


def _counts(
    type_text: str, attr: str, classes: dict[str, list[type]], local: dict[str, type]
) -> bool | None:
    """Whether `attr` on a receiver of the type pyright printed is digline's,
    or None when a part of the type is unknown to pyright.

    A class that is neither digline's nor the plugin's own (an SDK's reply,
    pytest's `TestReport`, `list`) does not count, whatever its attributes are
    called: that is the narrowing this tool exists for."""
    counted = False
    for part in (p.strip() for p in type_text.split(" | ")):
        if part in {"Any", "Unknown"} or part.startswith(("Any", "Unknown")):
            return None
        module = re.fullmatch(r'Module\("(.*)"\)', part)
        if module:
            name = module.group(1)
            if name == "digline" or name.startswith("digline."):
                counted |= hasattr(importlib.import_module(name), attr)
            continue
        match = re.fullmatch(r"type\[(.*)\]", part)
        if match:
            part = match.group(1)
        part = part.removeprefix("Self@")
        part = re.sub(r"\[.*\]$", "", part)
        for cls in [local[part]] if part in local else classes.get(part, []):
            counted |= _defined_in_digline(cls, attr)
    return counted


def _module_classes(plugin: Path) -> dict[str, type]:
    """The classes a plugin's own modules define, by short name."""
    found: dict[str, type] = {}
    for path in _plugin_sources(plugin):
        relative = path.relative_to(plugin / "src").with_suffix("")
        name = ".".join(relative.parts).removesuffix(".__init__")
        try:
            module = importlib.import_module(name)
        except Exception as error:  # noqa: BLE001 - named, not dropped
            print(f"{plugin.name}: {name} not imported: {error!r}", file=sys.stderr)
            continue
        for value in vars(module).values():
            if inspect.isclass(value) and value.__module__ == name:
                found[value.__name__] = value
    return found


def scan(packages: Path = PACKAGES) -> tuple[Counter[tuple[str, str, str]], list[str]]:
    """`{(plugin, kind, name): places}` and the receivers left unresolved."""
    classes = _digline_classes()
    candidates: set[str] = set()
    for group in classes.values():
        for cls in group:
            candidates |= _members(cls)
    candidates -= {n for n in candidates if n.startswith("__")}

    found: Counter[tuple[str, str, str]] = Counter()
    unresolved: list[str] = []
    plugins = sorted(p for p in packages.iterdir() if (p / "src").is_dir())
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch)
        sites: dict[int, Site] = {}
        for plugin in plugins:
            for path in _plugin_sources(plugin):
                source = path.read_bytes()
                for name, places in _imported_names(source.decode()).items():
                    found[(plugin.name, "import", name)] += places
                wrapped, wrapped_sites = _wrap(source, candidates, len(sites))
                target = copy / plugin.name / path.relative_to(plugin / "src")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(wrapped)
                for number, line, receiver, attr in wrapped_sites:
                    sites[number] = Site(
                        plugin.name, str(path.relative_to(ROOT)), line, receiver, attr
                    )
        config = {
            "executionEnvironments": [
                {"root": plugin.name, "extraPaths": [str(ROOT / "src")]}
                for plugin in plugins
            ],
            "pythonVersion": f"{sys.version_info.major}.{sys.version_info.minor}",
        }
        (copy / "pyrightconfig.json").write_text(json.dumps(config))
        pyright = shutil.which("pyright", path=str(Path(sys.executable).parent))
        assert pyright is not None, "pyright is not installed beside this interpreter"
        done = subprocess.run(
            [
                pyright,
                "--outputjson",
                "--pythonpath",
                sys.executable,
                "-p",
                str(copy / "pyrightconfig.json"),
            ],
            capture_output=True,
            text=True,
            cwd=copy,
        )
        report = json.loads(done.stdout)

    received: dict[int, str] = {}
    for diagnostic in report["generalDiagnostics"]:
        match = _SITE.search(diagnostic["message"])
        if match:
            received[int(match.group(1))] = match.group(2)

    local_by_plugin = {plugin.name: _module_classes(plugin) for plugin in plugins}
    for number, site in sorted(sites.items()):
        type_text = received.get(number)
        where = f"{site.path}:{site.line}: {site.receiver}.{site.attr}"
        if type_text is None:
            unresolved.append(f"{where}: no type read")
            continue
        counted = _counts(type_text, site.attr, classes, local_by_plugin[site.plugin])
        if counted is None:
            unresolved.append(f"{where}: {type_text}")
        elif counted:
            found[(site.plugin, "attribute", site.attr)] += 1
    return found, unresolved


def main(argv: list[str]) -> int:
    if argv:
        print("usage: plugin_calls.py", file=sys.stderr)
        return 64
    found, unresolved = scan()
    for (plugin, kind, name), places in sorted(found.items()):
        print(f"{plugin}  {kind}  {name}  {places}")
    for line in sorted(unresolved):
        print(f"unresolved  {line}")
    print(f"{len(unresolved)} unresolved: not measured, never not present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
