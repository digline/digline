"""There is no promote surface, and it is absent rather than refused.

ADR 0013 §3, which is ADR 0011 §1 applied to a second front end. A refusal is a
conversation — it can be argued with, retried, worked around — and an absence is
not. So this is checked structurally, the way `tests/test_layering.py` checks
that nothing below a front end imports `digline.cli`.

A green pytest run is the single most likely place in this product for a
baseline to be promoted by accident, because "the tests pass" is the sentence
people act on without reading.
"""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "pytest_digline"

#: What promoting looks like, whatever it is spelled. `promote_baseline` is the
#: store's method; `write_baseline` and `baseline_path` are the two ways to
#: reach the file underneath it without asking the store to promote.
FORBIDDEN = frozenset({"promote_baseline", "write_baseline", "baseline_path"})

FINE = {"alpha": "Acme, SATISFIED", "beta": "Acme, SATISFIED"}


def sources() -> list[Path]:
    found = sorted(SRC.rglob("*.py"))
    assert found, "no sources found; this file would prove nothing"
    return found


@pytest.mark.parametrize("source", sources(), ids=lambda p: p.name)
def test_no_source_names_anything_that_promotes(source: Path) -> None:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    named = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    offenders = sorted(named & FORBIDDEN)
    assert not offenders, (
        f"{source.name} names {offenders}. A baseline is an approved reference "
        "and the approval is a person's: this plugin gates and never promotes, "
        "and the guarantee is that there is nothing here to call."
    )


def test_no_option_this_plugin_adds_mentions_promoting(
    pytester: pytest.Pytester,
) -> None:
    """The other half: not merely unreachable, unoffered.

    An option named in `--help` is a thing somebody will try, and being told no
    afterwards is the conversation this design refuses to have.
    """
    result = pytester.runpytest_subprocess("--help")
    ours = [line for line in result.stdout.lines if "--digline" in line]
    assert ours, "the plugin's own options are not in --help at all"
    assert not [line for line in ours if "promot" in line.lower()]


def test_a_green_run_leaves_the_baseline_file_untouched(
    pytester: pytest.Pytester,
    baseline: Callable[[dict[str, str], dict[str, str]], Path],
) -> None:
    """The behavioural half of the same guarantee, on the file itself.

    Green is the dangerous case: a plugin that promoted "when everything
    passes" would be doing it on exactly the run nobody reads.
    """
    path = baseline(FINE, FINE)
    stored = pytester.path / ".digline" / "acme" / "baselines" / "support.json"
    before = hashlib.sha256(stored.read_bytes()).hexdigest()

    result = pytester.runpytest_subprocess("--digline-suite", str(path))

    assert result.ret == pytest.ExitCode.OK
    assert hashlib.sha256(stored.read_bytes()).hexdigest() == before
