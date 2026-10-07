"""A store that implements `ResultStore` and nothing else, held in memory.

It exists so that something other than `FileResultStore` is passed where a
signature says `ResultStore`. Until it did, every caller was handed the one
implementation there is, and a signature could go back to `FileResultStore`
with nothing going red. Passed here, a signature that reverts becomes a type
error in `tests/test_protocol_store.py`, which pyright's strict run covers.

**It holds only what it is passed to.** A site that no test calls with it is
not held by it, however many sites were retyped. `tests/test_protocol_store.py`
says site by site which is which.

**Hollow in two places, and a green through it says nothing about either:**

- It holds `Run` values, so a scan never reports `Listing.skipped` or
  `unreadable`. The foreign-schema paths — `Listing.advice()`, and the
  *"run `digline migrate`"* `UsageError` in `resolve_key` — cannot be reached
  through it. They are tested against the file store.
- **It neither promotes nor deletes.** `promote_baseline` raises. Condition 8
  asks what a store holds now, beside its own write, and the protocol forbids
  asserting it through a fake (`ResultStore.promote_baseline`); a fake that
  promoted would be a second copy of the conditions, which is the drift
  `refusals_for` exists to prevent. `delete_run` raises for the same reason:
  its refusal about the baseline asks what the store holds now, and is tested
  against a store that really writes (ADR 0044 §7).

It is not a second backend, and it is not evidence that the six methods are
enough: nothing here has to survive a process ending.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from digline.core import Run, key_of
from digline.store import Listing, Removal, RunNotFoundError, RunRef


@dataclass
class MemoryStore:
    """The six methods of `ResultStore`, over two dictionaries."""

    runs: dict[RunRef, Run] = field(default_factory=dict[RunRef, Run])
    baselines: dict[tuple[str, str], Run] = field(
        default_factory=dict[tuple[str, str], Run]
    )

    def write_run(self, run: Run) -> RunRef:
        # The protocol's invariant: the key is the document's.
        ref = RunRef(
            tenant=run.tenant,
            suite=run.suite,
            key=key_of(run.created_at, run.config_hash),
        )
        self.runs[ref] = run
        return ref

    def scan_runs(self, tenant: str, suite: str) -> Listing:
        return Listing(
            runs=tuple(
                ref for ref in self.runs if (ref.tenant, ref.suite) == (tenant, suite)
            )
        )

    def read_run(self, ref: RunRef) -> Run:
        try:
            return self.runs[ref]
        except KeyError:
            raise RunNotFoundError(f"no run {ref.key!r} in this memory") from None

    def read_baseline(self, tenant: str, suite: str) -> Run | None:
        return self.baselines.get((tenant, suite))

    def promote_baseline(
        self,
        ref: RunRef,
        expected_config_hash: str,
        *,
        expected_baseline: str | None,
        promoted_at: str,
    ) -> Run:
        raise NotImplementedError(
            "MemoryStore does not promote: condition 8 is not asserted through a "
            "fake. Test promotion against a store that really writes."
        )

    def delete_run(self, ref: RunRef) -> Removal:
        raise NotImplementedError(
            "MemoryStore does not delete: the refusal about the baseline is not "
            "asserted through a fake. Test the delete against a store that "
            "really writes."
        )
