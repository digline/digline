"""The offline driver. Depends on `digline.core`; the core does not know it.

`execute()` returns a `Run` and nothing else — the store, the comparison and the
promotion are composition on top, not responsibilities of the driver.
"""

from digline.run.driver import (
    HasArtifacts,
    Mapper,
    Preflight,
    Response,
    Target,
    default_mapper,
    execute,
)
from digline.run.suite import Case, Suite

__all__ = [
    "Case",
    "HasArtifacts",
    "Mapper",
    "Preflight",
    "Response",
    "Suite",
    "Target",
    "default_mapper",
    "execute",
]
