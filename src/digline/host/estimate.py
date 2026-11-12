"""What a run is likely to cost, read from the suite's newest stored run.

An estimate, never a bound. Nothing before the first call can say what a run
will cost **at most**: a judge reads the target's answer, which does not exist
yet; a token count is bounded by bytes only within one tokenizer; and a target
that is an agent makes a number of calls per case nobody knows in advance. So
the figure is what the newest run of this suite measured, per case, times the
cases this run will call, and it says which run it was read from. Without a
stored run there is no figure, and the sentence says so. The ceiling that
holds is `--max-cost`, read against what the run measures as it goes, and it
is never compared with this. (ADR 0064 §1)
"""

from __future__ import annotations

from dataclasses import dataclass

from digline.core.run import Run, key_of
from digline.run.suite import CallPlan, Suite
from digline.store.protocol import ResultStore

__all__ = ["Estimate", "estimate"]


@dataclass(frozen=True, slots=True)
class Estimate:
    """The figure and the run it was read from, or `key` `None` and `why`
    there is none."""

    key: str | None
    #: Where `key` is `None`: why no figure was read.
    why: str = "this suite has no stored run to read one from"
    usd: float = 0.0
    #: What that run measured, and over how many cases that were not
    #: suspended.
    spent_usd: float = 0.0
    measured_cases: int = 0
    #: The cases this run will call, the figure is scaled to.
    planned_cases: int = 0
    #: Whether that run was made under the configuration this one runs under.
    same_config: bool = True
    #: `False` where that run did not price every call, `None` where it did
    #: not record whether it did.
    every_cost_known: bool | None = True

    def sentence(self) -> str:
        """The line `digline run` prints before the first call."""
        if self.key is None:
            return (
                f"no cost estimate: {self.why}, and nothing before the first "
                "call can say what a run will cost"
            )
        text = (
            f"estimated from run {self.key}: {self.usd:.4f} USD, its "
            f"{self.spent_usd:.4f} USD over {self.measured_cases} "
            f"case{'' if self.measured_cases == 1 else 's'} scaled to "
            f"{self.planned_cases}; an estimate, not a ceiling"
        )
        if not self.same_config:
            text += "; that run was made under another configuration"
        if self.every_cost_known is False:
            text += "; that run did not price every call, so the figure is low"
        elif self.every_cost_known is None:
            text += "; that run did not record whether it priced every call"
        return text


def estimate(
    store: ResultStore, suite: Suite, plan: CallPlan, config_hash: str
) -> Estimate:
    """The estimate for a run of `suite` about to make `plan`, under
    `config_hash`, read from the newest readable run of the suite."""
    listing = store.scan_runs(suite.tenant, suite.name)
    if not listing.runs:
        return Estimate(key=None)
    newest: Run = max(
        (store.read_run(ref) for ref in listing.runs), key=lambda r: r.created_at
    )
    key = key_of(newest.created_at, newest.config_hash)
    measured = sum(1 for case in newest.results if case.suspended is None)
    if measured == 0:
        return Estimate(key=None, why=f"its newest run, {key}, ran no case")
    if newest.usage is None:
        return Estimate(key=None, why=f"its newest run, {key}, recorded no bill")
    lines = (newest.usage.target, newest.usage.judge)
    spent = sum(line.spent_usd for line in lines)
    known = [line.every_cost_known for line in lines if line.calls]
    every_cost_known = False if False in known else None if None in known else True
    planned = plan.cases + plan.calibration + plan.reviewed
    return Estimate(
        key=key,
        usd=spent / measured * planned,
        spent_usd=spent,
        measured_cases=measured,
        planned_cases=planned,
        same_config=newest.config_hash == config_hash,
        every_cost_known=every_cost_known,
    )
