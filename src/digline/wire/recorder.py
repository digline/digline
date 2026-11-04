"""What `digline record status` says, for a program. (ADR 0058 §10)

Counts, sizes and a tenant's switch. **No recording crosses here**: a recording
is payload, whole, and this module reads none. The host counts them, by suite,
and hands over the numbers. A suite's name and the tenant's are what every
other `--json` already carries.

**Since the last import, per suite** (ADR 0058 §10, as amended 2026-11-03).
`imported` is `true` where the suite's draft holds cases elected from
recordings, and `since_last_import` is then how many of the suite's recordings
were written after the newest `examined_through` among them; `false` is
*never imported*, with `since_last_import` the total. Both are `null` where
the status was not asked about that suite (`--suite`): the draft is the
suite's file, and only the suite says where it is. `null` is *not read*,
never *nothing arrived*.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from digline.wire.contract import OUTPUT_VERSION
from digline.wire.text import neutralised

__all__ = ["SuiteRecordings", "TenantRecorder", "recorder_status_json"]

type SwitchState = Literal["absent", "valid", "invalid"]


@dataclass(frozen=True, slots=True)
class SuiteRecordings:
    """One suite's recordings in a tenant: the single calls, the episodes, and
    how many of the calls are marked orphans."""

    suite: str
    calls: int
    episodes: int
    orphans: int
    #: Of `calls`, those made inside an episode, which are part of that
    #: episode's case and not cases of their own.
    inside_episodes: int = 0
    #: Of `episodes`, those the application raised inside, written with what
    #: was seen until then.
    interrupted: int = 0
    #: Per reason, the calls every process said it did not record.
    not_recorded: Mapping[str, int] = field(default_factory=dict[str, int])
    #: Recorded, with something said beside it: `usage not reported`, a
    #: stream that ended `after its episode`.
    noted: Mapping[str, int] = field(default_factory=dict[str, int])
    imported: bool | None = None
    since_last_import: int | None = None


@dataclass(frozen=True, slots=True)
class TenantRecorder:
    """One tenant's recorder, read from its switch file and its recordings.

    `switch` is `absent` where no file exists, `valid` or `invalid`; the
    values are `None` unless it is `valid`, and they are what the recorder
    will use, a default where the file declared nothing (`declared` names
    what it did). `refusal` is why an invalid file is refused, and
    `production_refusal` why a valid one would still be refused with a tenant
    function, which is production. `size` is the bytes of the recordings as
    written, readable and unreadable alike, and the measure the recorder holds
    against the ceiling; the disk holds more, a block per file at the least.
    `stopped_at_ceiling` is the marker the recorder leaves when it stops.
    """

    tenant: str
    switch_path: str
    switch: SwitchState
    on: bool
    sample: float | None
    redact: str | None
    ceiling: int | None
    interval: float | None
    declared: tuple[str, ...]
    refusal: str | None
    production_refusal: str | None
    recordings_path: str
    suites: tuple[SuiteRecordings, ...]
    unreadable: int
    size: int
    stopped_at_ceiling: bool


def recorder_status_json(tenants: Sequence[TenantRecorder]) -> dict[str, object]:
    """Every tenant's recorder. No `exit_code`: the status is not a gate."""
    return neutralised(
        {
            "output_version": OUTPUT_VERSION,
            "tenants": [_tenant_json(tenant) for tenant in tenants],
        }
    )


def _tenant_json(tenant: TenantRecorder) -> dict[str, object]:
    return {
        "tenant": tenant.tenant,
        "switch": {
            "path": tenant.switch_path,
            "state": tenant.switch,
            "on": tenant.on,
            "sample": tenant.sample,
            "redact": tenant.redact,
            "ceiling": tenant.ceiling,
            "interval": tenant.interval,
            "declared": list(tenant.declared),
            "refusal": tenant.refusal,
            "production_refusal": tenant.production_refusal,
        },
        "recordings": {
            "path": tenant.recordings_path,
            "size": tenant.size,
            "stopped_at_ceiling": tenant.stopped_at_ceiling,
            "unreadable": tenant.unreadable,
            "suites": [
                {
                    "suite": suite.suite,
                    "calls": suite.calls,
                    "episodes": suite.episodes,
                    "orphans": suite.orphans,
                    "inside_episodes": suite.inside_episodes,
                    "interrupted": suite.interrupted,
                    "not_recorded": dict(suite.not_recorded),
                    "noted": dict(suite.noted),
                    "imported": suite.imported,
                    "since_last_import": suite.since_last_import,
                }
                for suite in tenant.suites
            ],
        },
    }
