"""`pytest-digline`: the comparison, as rows in pytest's own report.

The plugin lives in `pytest_digline.plugin`, which is what the `pytest11` entry
point names. Nothing is exported here: a pytest plugin is not a library, and a
name importable from the package root is a surface somebody would write against.
"""

from importlib.metadata import version as _distribution_version

# Read from the installed distribution rather than written here, for the reason
# `digline.__version__` is: a hand-written copy is neither derived nor gated,
# and `tests/test_versions.py` sweeps these sources for exactly that.
__version__ = _distribution_version("pytest-digline")

__all__ = ["__version__"]
