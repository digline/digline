"""What the Node recorder wrote, imported with digline alone. (ADR 0062 §4,
as amended 2026-11-06)

`recorders/node/` holds the files an application copies, `digline/`, and the
tests that hold them to the fixtures digline's Python makes. The CI job
`recorder-node` runs those tests, which write a tenant's recordings into a
directory of the runner's, and then this test, which imports them with
digline alone, no plugin installed, and reads `record status` say *not
counted*, since a writer outside Python keeps no counts file.
"""

from __future__ import annotations

import pytest
from tests.test_recorder_java import imported_by_digline_alone

#: Where the CI job's Node run left its recordings, and whether this run must
#: find them: set together by the job, so a run of the job never skips.
RECORDINGS = "DIGLINE_NODE_RECORDINGS"
REQUIRED = "DIGLINE_NODE_REQUIRED"


def test_what_the_node_recorder_wrote_is_imported_by_digline_alone(
    capsys: pytest.CaptureFixture[str],
) -> None:
    imported_by_digline_alone(RECORDINGS, REQUIRED, "recorder-node", capsys)
