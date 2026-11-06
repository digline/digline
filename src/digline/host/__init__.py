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

from digline.host.artifacts import read_artifacts, read_pinned
from digline.host.authorship import to_withhold, written_by_digline
from digline.host.comparing import record_compare
from digline.host.environment import (
    DIRTY_SUFFIX,
    ProcessState,
    git_commit,
    process_state,
    this_process,
    unignored,
    unignored_notes,
    utc_now_iso,
)
from digline.host.errors import UsageError
from digline.host.importing import (
    Declaration,
    ImportAnswer,
    ImportGroup,
    ImportListing,
    Shape,
    answer_id,
    import_elect,
    import_listing,
    imported_since,
    listing_lines,
    written_lines,
)
from digline.host.listing import (
    SuiteRuns,
    left_out,
    left_out_parts,
    one_table,
    suite_runs,
)
from digline.host.loader import (
    SUITE_ATTR,
    TARGET_ATTR,
    Loaded,
    NameTable,
    SourceOnlyLoader,
    load_name_table,
    load_suite,
    load_target,
    refused_exit,
)
from digline.host.measure import (
    Measured,
    Prepared,
    around_target,
    measure,
    prepare,
    refuse_unreadable_baseline,
    seed_observed,
)
from digline.host.promotion import (
    pricing_for,
    promote,
    promote_priced,
    promotion_notes,
    promotion_refusal,
)
from digline.host.reading import (
    Explained,
    Reported,
    explained,
    history,
    instant,
    reported,
)
from digline.host.recording import recorder_status, switch_off, switch_on
from digline.host.refusals import NOT_REFUSALS, REFUSALS
from digline.host.register import entry_for, record
from digline.host.resolve import (
    LATEST,
    NO_BASELINE,
    Resolved,
    need_baseline,
    read_run,
    replacing,
    resolve_key,
)
from digline.host.suggest import (
    PROPOSAL,
    SUITE_RULE,
    Suggested,
    suggest_for,
    suggest_new,
)
from digline.host.toml_suite import SUITE_SUFFIX, load_toml_suite, read_cases
from digline.host.where import (
    STATES,
    State,
    SuiteFound,
    Where,
    record_lines,
    suites_of,
    tenants_under,
    where,
)

__all__ = [
    "DIRTY_SUFFIX",
    "Explained",
    "LATEST",
    "NOT_REFUSALS",
    "NO_BASELINE",
    "REFUSALS",
    "Reported",
    "Resolved",
    "SUITE_ATTR",
    "PROPOSAL",
    "SUITE_RULE",
    "SUITE_SUFFIX",
    "Suggested",
    "TARGET_ATTR",
    "Loaded",
    "NameTable",
    "Measured",
    "Prepared",
    "SourceOnlyLoader",
    "SuiteRuns",
    "UsageError",
    "entry_for",
    "explained",
    "Declaration",
    "ImportAnswer",
    "ImportGroup",
    "ImportListing",
    "Shape",
    "answer_id",
    "around_target",
    "import_elect",
    "import_listing",
    "listing_lines",
    "written_lines",
    "imported_since",
    "record_compare",
    "git_commit",
    "history",
    "left_out",
    "left_out_parts",
    "one_table",
    "instant",
    "load_name_table",
    "load_suite",
    "refused_exit",
    "refuse_unreadable_baseline",
    "to_withhold",
    "written_by_digline",
    "load_target",
    "load_toml_suite",
    "measure",
    "prepare",
    "pricing_for",
    "promote",
    "promote_priced",
    "promotion_notes",
    "promotion_refusal",
    "need_baseline",
    "read_artifacts",
    "read_cases",
    "read_pinned",
    "read_run",
    "record",
    "recorder_status",
    "replacing",
    "reported",
    "resolve_key",
    "seed_observed",
    "suite_runs",
    "suggest_for",
    "suggest_new",
    "switch_off",
    "switch_on",
    "utc_now_iso",
    "unignored",
    "unignored_notes",
    "this_process",
    "process_state",
    "ProcessState",
    "STATES",
    "State",
    "Where",
    "where",
    "SuiteFound",
    "record_lines",
    "suites_of",
    "tenants_under",
]
