"""The half of a provider target that has nothing to do with the provider.

Composing the prompt, timing the call, pricing the tokens and building the
`Response` are the same work for every SDK. A plugin supplies `_complete` and
a price list; everything else is here, so a new provider is thirty lines and
cannot get the `Response` wrong.

`perf_counter` is a **duration**, not a clock: it cannot say what time it is,
so it does not touch the reproducibility rule that makes the CLI pass
`created_at` in. It is what fills `Response.latency_ms`, which some target has
to fill.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter

from digline.core import Output
from digline.run import Case, Response
from digline.targets.pricing import Pricing, Usage
from digline.targets.template import PromptTemplate

__all__ = ["ProviderTarget"]


class ProviderTarget(ABC):
    """A prompt file, a model, and a price list.

    `system` may be given inline or as a file. A file is the usual case in
    practice — the system prompt is the part that moves most — and a file is
    recorded as an artifact, so a run says which one produced it.
    """

    def __init__(
        self,
        prompt_file: str | Path,
        model: str,
        *,
        pricing: Pricing,
        system: str | None = None,
        system_file: str | Path | None = None,
    ) -> None:
        if system is not None and system_file is not None:
            raise ValueError(
                "give `system` or `system_file`, not both: two system prompts "
                "is a question about which one ran"
            )
        self.template = PromptTemplate(prompt_file)
        self.system_template: PromptTemplate | None = None
        if system_file is not None:
            self.system_template = PromptTemplate(system_file)
        elif system is not None:
            self.system_template = PromptTemplate.from_text(system, name="system")
        self.model = model
        self.pricing = pricing

    # -- what the driver and the CLI ask for -------------------------------- #

    def artifacts(self) -> Sequence[Path]:
        """The files that *are* the thing under test, for `Run.artifacts`.

        Only files. An inline system prompt is already in the suite's source,
        and recording it again would record it twice.
        """
        return tuple(
            template.path
            for template in (self.template, self.system_template)
            if template is not None and template.path is not None
        )

    def preflight(self, cases: Sequence[Case]) -> None:
        """Refuse before the first call, not on case thirty-seven.

        Both failures this catches cost money to discover the other way: a
        missing variable stops a run halfway, and an unpriced model runs the
        whole suite and then cannot say what it cost.
        """
        problems: list[str] = []
        if not self.pricing.knows(self.model):
            known = ", ".join(sorted(self.pricing.per_model)) or "none"
            problems.append(
                f"model {self.model!r} has no price (known: {known}); pass "
                "`pricing=` to add it"
            )
        for template in (self.template, self.system_template):
            if template is None:
                continue
            for case in cases:
                if case.suspended is not None:
                    continue
                missing = template.missing_for(case.vars)
                if missing:
                    problems.append(
                        f"case {case.id!r} does not provide "
                        f"{', '.join(sorted(missing))} for {template.name}"
                    )
        if problems:
            raise ValueError(
                f"{type(self).__name__} cannot run this suite:\n  "
                + "\n  ".join(problems)
            )

    # -- the call ------------------------------------------------------------ #

    def __call__(self, case: Case) -> Response:
        prompt = self.template.render(case.vars, case_id=case.id)
        system = (
            None
            if self.system_template is None
            else self.system_template.render(case.vars, case_id=case.id)
        )
        started = perf_counter()
        text, usage = self._complete(prompt, system)
        elapsed_ms = (perf_counter() - started) * 1000.0
        return Response(
            output=self.parse(text),
            input=prompt,
            cost_usd=self.pricing.cost(self.model, usage),
            latency_ms=elapsed_ms,
            metadata={
                "model": self.model,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read_tokens": usage.cache_read_tokens,
                "cache_write_tokens": usage.cache_write_tokens,
            },
        )

    def parse(self, text: str) -> Output:
        """What the assertions will judge. The reply itself, unless you say so.

        A provider returns text. A suite that checks a *shape* — `JsonSchema`,
        or anything reading `output["score"]` — needs that text turned into the
        shape first, and there was nowhere to put that: the base built the
        `Response` and handed back a string, so the suite had to give up on
        `ProviderTarget` or give up on structured assertions. (friction 26)

        Raise on a reply you cannot parse. The driver turns an exception into
        `error`, which is the honest verdict — the model failed to answer in the
        agreed shape, which is neither a pass nor a regression.
        """
        return text

    @abstractmethod
    def _complete(self, prompt: str, system: str | None) -> tuple[str, Usage]:
        """Call the provider. The only thing a plugin has to write."""
