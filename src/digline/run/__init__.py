"""The offline driver. Depends on `digline.core`; the core does not know it.

`execute()` returns a `Run` and nothing else — the store, the comparison and the
promotion are composition on top, not responsibilities of the driver.
"""

from digline.run.driver import (
    HasArtifacts,
    HasConfig,
    Mapper,
    Preflight,
    Response,
    Target,
    default_mapper,
    execute,
    judge_config,
    judges,
    target_config,
)
from digline.run.replay import Replay, ReplayError, rejudge, replayable_cases
from digline.run.suite import CallPlan, Case, Suite, planned_calls

__all__ = [
    "CallPlan",
    "Case",
    "HasArtifacts",
    "HasConfig",
    "Mapper",
    "Preflight",
    "Replay",
    "ReplayError",
    "Response",
    "Suite",
    "Target",
    "default_mapper",
    "execute",
    "judge_config",
    "judges",
    "planned_calls",
    "rejudge",
    "replayable_cases",
    "target_config",
]
