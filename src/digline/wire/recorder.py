"""What `digline record status` says, for a program. (ADR 0058 §10)

Counts, sizes and a tenant's switch. **No recording crosses here**: a recording
is payload, whole, and this module reads none. The host counts them, by suite,
and hands over the numbers. A suite's name and the tenant's are what every
other `--json` already carries.

**`since_last_import` is `null`, on every tenant.** The status of ADR 0058 §10
says how many recordings each suite has gained since the last import, and
there is no import yet: the key is there so the number has a place to arrive,
and `null` says it is not kept, never that nothing arrived.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class TenantRecorder:
    """One tenant's recorder, read from its switch file and its recordings.

    `switch` is `absent` where no file exists, `valid` or `invalid`; the
    values are `None` unless it is `valid`, and they are what the recorder
    will use, a default where the file declared nothing (`declared` names
    what it did). `refusal` is why an invalid file is refused, and
    `production_refusal` why a valid one would still be refused with a tenant
    function, which is production. `size` is the bytes of the readable and
    unreadable recordings alike; `stopped_at_ceiling` is the marker the
    recorder leaves when it stops.
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
                }
                for suite in tenant.suites
            ],
            "since_last_import": None,
        },
    }
