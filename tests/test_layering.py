"""The core stays pure and isolated.

These are not style checks: they are the two constraints that make
`digline.core` importable from Plumbline as a library, and that stop the
assertion engine from ending up inside a runner, where it can no longer be
invoked — or tested — on its own.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "src" / "digline" / "core"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_the_core_does_not_import_upper_layers() -> None:
    """Allowed direction: cli -> run/online -> store/providers -> core. Never
    the other way round."""
    forbidden = (
        "digline.store",
        "digline.run",
        "digline.online",
        "digline.cli",
    )
    for source in sorted(CORE.glob("*.py")):
        for module in imported_modules(source):
            assert not module.startswith(forbidden), (
                f"{source.name} imports {module}: the core must not depend on "
                "the layers above it"
            )


def test_the_core_does_no_io() -> None:
    """No I/O, network or clock modules. `Judge` is the only route to the
    outside world, and the caller injects it."""
    forbidden = {
        "os",
        "io",
        "pathlib",
        "socket",
        "subprocess",
        "shutil",
        "tempfile",
        "urllib",
        "urllib.request",
        "http",
        "requests",
        "httpx",
        "datetime",
        "time",
    }
    for source in sorted(CORE.glob("*.py")):
        offenders = imported_modules(source) & forbidden
        assert not offenders, (
            f"{source.name} imports {offenders}: the core must stay pure"
        )


def test_the_driver_does_not_know_about_the_store() -> None:
    """`execute()` returns a `Run` and nothing else: it does not write it, does
    not read the baseline, does not compare and does not promote. The full cycle
    is composition above the driver. A driver that knew about the baseline would
    have two reasons to change — and this is the check that keeps it true when
    someone reaches for the convenient shortcut."""
    driver = Path(__file__).resolve().parents[1] / "src" / "digline" / "run"
    for source in sorted(driver.glob("*.py")):
        for module in imported_modules(source):
            assert not module.startswith("digline.store"), (
                f"{source.name} imports {module}: the driver produces a Run, "
                "it does not persist one"
            )


def test_the_report_does_no_io_and_knows_no_store() -> None:
    """`render_html()` returns a string; the caller writes it. And it must not
    read the clock: the report is itself a committable artifact, so a diff has
    to move only when a fact moves."""
    report = Path(__file__).resolve().parents[1] / "src" / "digline" / "report"
    forbidden = {"datetime", "time", "pathlib", "os", "io", "tempfile"}
    for source in sorted(report.glob("*.py")):
        modules = imported_modules(source)
        assert not (modules & forbidden), f"{source.name} does I/O or reads a clock"
        for module in modules:
            assert not module.startswith(("digline.store", "digline.run")), (
                f"{source.name} imports {module}: the report renders a comparison, "
                "it does not produce or persist one"
            )


def test_the_core_imports_on_its_own() -> None:
    """A clean process importing only `digline.core` must not drag in
    `digline.store`: that is the condition for Plumbline to use it as a
    library without inheriting our storage model."""
    code = "import digline.core, sys; print('digline.store' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "False"


SRC = Path(__file__).resolve().parents[1] / "src" / "digline"
PACKAGES = Path(__file__).resolve().parents[1] / "packages"


def test_nothing_shipped_with_digline_imports_a_plugin() -> None:
    """The direction that makes plugins worth having.

    `pip install digline` must not pull somebody's HTTP client along with it, so
    no module under `src/` may import one — not the core, not the targets, not
    the CLI. A plugin depends on digline; digline depends on no plugin, ever.
    """
    plugins = {p.name.replace("-", "_") for p in PACKAGES.glob("*") if p.is_dir()}
    assert plugins, "no plugin to check against; this test would prove nothing"
    for source in sorted(SRC.rglob("*.py")):
        for module in imported_modules(source):
            root = module.split(".")[0]
            assert root not in plugins, (
                f"{source.relative_to(SRC)} imports {module}: digline must not "
                "depend on a package that depends on it"
            )


def test_the_targets_do_not_import_an_sdk() -> None:
    """`digline.targets` is the half of a provider target that has no provider
    in it. The moment it imports one, every user of digline installs it."""
    sdks = {"anthropic", "openai", "google", "cohere", "mistralai", "httpx", "requests"}
    for source in sorted((SRC / "targets").glob("*.py")):
        offenders = imported_modules(source) & sdks
        assert not offenders, f"{source.name} imports {offenders}"


def test_the_core_does_not_import_the_targets() -> None:
    """Targets sit above `digline.run`, which sits above the core. A `Response`
    is produced for a `Case`, so the dependency can only run one way."""
    for source in sorted(CORE.glob("*.py")):
        for module in imported_modules(source):
            assert not module.startswith("digline.targets"), (
                f"{source.name} imports {module}: the core is below the targets"
            )
