"""digline — a Python-native evaluation engine for LLM output.

The core (`digline.core`) is pure and callable on its own. Upper layers
depend on it, never the other way round.
"""

# Aliased so `digline.version` does not become a name the package appears
# to export.
from importlib.metadata import version as _distribution_version

#: Read from the installed distribution's metadata rather than written here.
#: Hand-written it fell a whole minor behind `pyproject.toml` without anything
#: noticing — one number in two places disagrees eventually, and this is the
#: copy nobody looks at. No fallback on `PackageNotFoundError`: a made-up
#: version reaching `digline --version` is the bug this line exists to remove,
#: so an uninstalled package fails loudly instead.
__version__ = _distribution_version("digline")
