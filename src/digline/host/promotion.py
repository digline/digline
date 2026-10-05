"""Promotion for anything that drives digline: the hash is computed, not passed.

`ResultStore.promote_baseline` checks a run against `expected_config_hash`,
the configuration in force — condition 2 in ADR 0002 §8. A caller
outside digline could not compute that hash from the names `docs/api.md`
documented: it is `suite.config_hash(pricing=...)` over the digest of the
target the run was measured with, and a Python suite that declares no target
contributes nothing (ADR 0022 §4). The value within easy reach was
`run.config_hash`, which compares the run with itself and passes every time.
That is a vacuous green, and fixed decision 3 refuses it.

So the public route is `promote`, which takes what the suite was loaded as and
computes the hash itself. Everything a caller could get wrong is inside it, and
the only thing it still takes is what only the caller knows: which target was
measured. (#256)
"""

from __future__ import annotations

from digline.core import Run
from digline.host.errors import UsageError
from digline.host.loader import TARGET_ATTR, Loaded, load_target
from digline.host.resolve import LATEST
from digline.host.resolve import replacing as expected_baseline_of
from digline.run import Suite, price_digest_of
from digline.store import ResultStore, RunRef

__all__ = ["pricing_for", "promote", "promote_priced"]


def pricing_for(loaded: Loaded, target: str | None, suite_spec: str) -> str:
    """The declared-price digest of the target a command is about.

    `target` is the `--target` spec, or `None` for the suite's own. A `suite.py`
    with no `target` at all, and no spec, contributes nothing: it is promoted as
    it always was, because there is no price there to have declared. A TOML
    suite refuses a spec, as `load_target` says. (ADR 0022 §5)

    `suite_spec` names the suite in `load_target`'s refusals and nothing else.
    """
    if (
        target is None
        and loaded.module is not None
        and not hasattr(loaded.module, TARGET_ATTR)
    ):
        return ""
    return price_digest_of(load_target(target, loaded, suite_spec))


def promote(
    store: ResultStore,
    loaded: Loaded,
    key: str,
    *,
    target: str | None,
    replacing: str,
    promoted_at: str,
) -> Run:
    """Promote the run `key` to be the baseline of the loaded suite.

    - `key` is a run key. `latest` is refused: resolve it with `resolve_key`
      first, which hands back what its scan stepped over for the caller to show.
    - `target` is the spec of the target the run was measured with, or `None`
      for the suite's own. **It is a parameter because only the caller knows
      which target was measured**: a suite with several would otherwise sign a
      run of one system as the reference for another (ADR 0022 §5).
    - `replacing` is the reference this promotion replaces, as `compare` printed
      it: a key, or `none` where the suite has no baseline yet (ADR 0031 §1).
    - `promoted_at` is the signature's time, read by the caller: `utc_now_iso()`.

    Returns the reference written, which is what `promote_baseline` returns and
    what a projection starts from (ADR 0034 §2). Every refusal is in `REFUSALS`.
    """
    suite = loaded.suite
    pricing = pricing_for(loaded, target, f"suite {suite.name!r}")
    return promote_priced(
        store,
        suite,
        pricing,
        key,
        replacing=replacing,
        promoted_at=promoted_at,
    )


def promote_priced(
    store: ResultStore,
    suite: Suite,
    pricing: str,
    key: str,
    *,
    replacing: str,
    promoted_at: str,
) -> Run:
    """`promote`, for a caller that computed `pricing_for` once already.

    `digline view` does, at launch: resolving the target again on every request
    would import the user's target module once per promotion. Internal, and not
    in `docs/api.md` — a caller outside digline has no launch to compute it at.
    """
    if key == LATEST:
        raise UsageError(
            f"promote takes a run key, not {LATEST!r}: resolve it with "
            "`resolve_key` first, which also says what its scan stepped over"
        )
    return store.promote_baseline(
        RunRef(tenant=suite.tenant, suite=suite.name, key=key),
        suite.config_hash(pricing=pricing),
        # What the caller compared against, as they typed it — never read from
        # the store here, which would make the check compare the baseline with
        # itself. (ADR 0031 §1) The helper is imported under another name
        # because the parameter `replacing` would hide it in this function.
        expected_baseline=expected_baseline_of(replacing),
        promoted_at=promoted_at,
    )
