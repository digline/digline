"""The layer that touches the world: the clock, git, and the user's own files.

**The only layer allowed to read the clock and git.** That sentence used to be
written about `digline.cli`, and it was right about the layer and wrong about
its name — it got away with it because there had only ever been one front end.

There are two things in a command-line tool, and only one of them is a command
line. The **host** is the process that has a filesystem, a clock and a git
repository: it reads the time once and passes it down as a value, asks git what
commit this is, imports the user's `suite.py` without touching the bytecode
cache, and reads the files a suite declares as the thing under test. The
**terminal** is argparse, the help text, the printed tables and the exit codes.
Any front end needs the first; only a terminal needs the second.

So `digline.cli` is one host front end, and `digline-mcp` is another. Neither
imports the other, and `tests/test_layering.py` holds that: nothing under
`src/digline/` outside `cli/` may import `digline.cli`. (ADR 0011 §7)

The clock rule is unchanged and is the reason this layer is drawn where it is.
`created_at` is *passed in* so a run is reproducible; a **duration** is not a
clock — it cannot say what time it is — so `perf_counter` for `latency_ms` in a
target stays allowed.
"""

from digline.host.artifacts import read_artifacts
from digline.host.environment import DIRTY_SUFFIX, git_commit, utc_now_iso
from digline.host.errors import UsageError
from digline.host.loader import (
    SUITE_ATTR,
    TARGET_ATTR,
    Loaded,
    SourceOnlyLoader,
    load_suite,
    load_target,
)
from digline.host.measure import (
    Measured,
    Prepared,
    measure,
    prepare,
    seed_observed,
)
from digline.host.resolve import (
    LATEST,
    Resolved,
    need_baseline,
    read_run,
    resolve_key,
)
from digline.host.toml_suite import SUITE_SUFFIX, load_toml_suite

__all__ = [
    "DIRTY_SUFFIX",
    "LATEST",
    "Resolved",
    "SUITE_ATTR",
    "SUITE_SUFFIX",
    "TARGET_ATTR",
    "Loaded",
    "Measured",
    "Prepared",
    "SourceOnlyLoader",
    "UsageError",
    "git_commit",
    "load_suite",
    "load_target",
    "load_toml_suite",
    "measure",
    "prepare",
    "need_baseline",
    "read_artifacts",
    "read_run",
    "resolve_key",
    "seed_observed",
    "utc_now_iso",
]
