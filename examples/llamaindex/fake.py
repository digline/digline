"""The model, faked, so this runs with no key and no network.

**LlamaIndex ships `MockLLM` and it cannot be the default here.** It has no
`responses=[...]`: with no `max_tokens` it returns the prompt back verbatim,
and with one it returns the word "text" repeated. So the "answer" would be the
assembled prompt — passage and all — and every check on a grounded fact would
pass because the *question* contained it, which is the vacuously green
assertion digline exists to refuse.

It is still worth keeping around: `README.md` §3 swaps it in, and the suite's
`not_contains` goes red on the synthesizer's own template text. The fake we
cannot use is the demonstration of the check that catches it.

So `HandbookLLM` below subclasses LlamaIndex's own `CustomLLM` and answers with
one canned reply per handbook page, quoting it. Keyed on the page the retriever
selected, never on the case: change the corpus or the embedding and the answer
this example sees changes with it, so retrieval stays under test.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from typing import Any

from llama_index.core.base.llms.types import (
    CompletionResponse,
    CompletionResponseGen,
    LLMMetadata,
)
from llama_index.core.llms import CustomLLM

#: One answer per handbook page, staying inside it. A stand-in that invented
#: freely would leave `faithfulness` below measuring nothing.
REPLIES: dict[str, str] = {
    "handbook/docking": (
        "If every point at a dock is taken, use the screen on the dock post to "
        "claim fifteen extra minutes at no charge. The claim is per ride and "
        "begins the moment you press it."
    ),
    "handbook/faults": (
        "Report the fault from the ride screen before you finish, and the "
        "meter stops at the moment you report it. A fault reported after the "
        "bike is docked does not stop the meter."
    ),
    "handbook/hire": (
        "The first thirty minutes of every hire are included in the pass. "
        "After that the meter runs at one pound per additional half hour, "
        "rounded up."
    ),
    "handbook/membership": (
        "A pass may be cancelled within fourteen days of purchase for a full "
        "refund, provided no hire has been started on it. After a hire, the "
        "refund is the unused whole months."
    ),
}

#: How the source reaches the model: the prompt template puts the page id in
#: the passage block, as `source: handbook/hire`.
_SOURCE = re.compile(r"^source: (handbook/\w+)$", re.MULTILINE)


class HandbookLLM(CustomLLM):
    """Deterministic, and it reads the passage it was given.

    Not decorated with `@llm_completion_callback()`, which every LlamaIndex
    example shows: the decorator is untyped, so it costs two errors under
    pyright strict, and all it adds is callback-manager instrumentation nothing
    here listens to.
    """

    @classmethod
    def class_name(cls) -> str:
        return "HandbookLLM"

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(num_output=256, is_chat_model=False)

    def complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        found = _SOURCE.search(prompt)
        if found is None:
            # The retriever handed over nothing, or the template stopped
            # carrying the page id. Both are real failures and both should
            # reach the suite as an answer that cites nothing, rather than as
            # an exception raised by the stand-in.
            return CompletionResponse(text="The handbook does not answer this.")
        source = found.group(1)
        return CompletionResponse(text=f"{REPLIES[source]}\nSource: {source}")

    def stream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponseGen:
        # `Generator`, not `Iterator`: `CompletionResponseGen` is the former,
        # and pyright is right that the two are different promises.
        def once() -> Generator[CompletionResponse, None, None]:
            yield self.complete(prompt, formatted, **kwargs)

        return once()
