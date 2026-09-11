"""What a plugin's `_complete` returns, and how a provider's word becomes ours.

`Completion` is the record ADR 0004 §6 widened `_complete` into. It replaces
the `(text, Usage)` pair — which was decided when the only question asked of a
provider was *what did it say and what did it cost*, and which left `_no_text`
inferring a cause from a token count while all three providers were returning
the answer as a field.

Nothing here imports an SDK. Translating a provider's vocabulary into ours is
each plugin's job, because only the plugin knows whose words it is reading;
what lives here is the record they fill and the one rule none of them may get
wrong — an unrecognised word is `other`, never `stop`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from digline.core import Finish
from digline.targets.pricing import Usage

__all__ = [
    "WHY_SILENT",
    "Completion",
    "CompletionResult",
    "ObservedIdentity",
    "as_completion",
    "finish_of",
    "no_text_reason",
    "said_something",
]


@dataclass(frozen=True, slots=True)
class Completion:
    """One call to a provider: what it said, what it cost, and how it went.

    A record and not a longer tuple, and not because seven is more than two: a
    tuple's meaning is positional, and every plugin author would have had to
    count. Everything after `usage` defaults, so a provider that can say none of
    it writes `Completion(text, usage)` and is done — which is not hypothetical,
    it is `digline-bedrock` on two of the five.

    The two identity fields are **passengers**. What they are for is ADR 0005
    §9; they ride here because they arrive in the same reply, and widening
    `_complete` twice for two facts from one call would be two plugin releases
    for one journey.
    """

    text: str
    usage: Usage
    #: How the turn ended, in the one vocabulary (`digline.core.Finish`).
    #: `None` where the provider said nothing — the ordinary case on a
    #: compatible endpoint, and the reason every consumer has a fallback.
    finish: Finish | None = None
    #: The provider's own word, verbatim. Kept because the normalisation above
    #: is lossy exactly where a regulated reader cares: `refusal`,
    #: `content_filtered` and `guardrail_intervened` all become `filtered`, and
    #: `max_tokens` and `model_context_window_exceeded` both become `length` —
    #: your cap and the model's window being two different things to go and fix.
    #: Recorded, never interpreted, never asserted on.
    finish_raw: str | None = None
    #: The tools the model called, in the order it called them. Names only: the
    #: three providers disagree about what an argument *is*, and nothing reads
    #: them yet. (ADR 0004 §6, "the names, not the arguments")
    #:
    #: **`None` and `()` are different facts**, on the same rule `sent()` reads
    #: an unset parameter by: `()` says the model called nothing, `None` says
    #: nobody reported. A plain-function target and a provider that says nothing
    #: about tools must not be read as models that called none, so `ToolsCalled`
    #: errors on `None` and judges `()`.
    tools: tuple[str, ...] | None = None
    #: What the provider said answered, where it says so. `None` on Bedrock
    #: Converse, whose reply carries no model id at all — and it stays `None`
    #: rather than echoing the request back, which would manufacture the one
    #: fact it exists to obtain. (ADR 0005 §9)
    model: str | None = None
    #: The backend build, where a provider names one. OpenAI's
    #: `system_fingerprint` and nobody else's.
    fingerprint: str | None = None

    def as_metadata(self) -> Mapping[str, object]:
        """What a `Response` carries to the mapper, and so to an assertion.

        Only what was actually reported: a key here means the provider said
        something, which is what lets `ToolsCalled` tell *called nothing* from
        *nobody asked*. `Response.metadata` is not persisted, so this bag costs
        nothing in any document — what reaches a run file is what an assertion
        measured out of it.
        """
        found: dict[str, object] = {}
        if self.finish is not None:
            found["finish"] = self.finish
        if self.finish_raw is not None:
            found["finish_raw"] = self.finish_raw
        if self.tools is not None:
            found["tools"] = list(self.tools)
        if self.model is not None:
            found["resolved_model"] = self.model
        if self.fingerprint is not None:
            found["fingerprint"] = self.fingerprint
        return found


#: What a plugin may return. The pair is **permanently** admissible, not
#: deprecated: a plugin written against ADR 0004 as it stood keeps working, and
#: a provider with nothing to report beyond text and tokens keeps a return that
#: is honest for it. Third-party plugins are unaffected by construction, which
#: is the sentence ADR 0005 §6 used for the same shape.
type CompletionResult = Completion | tuple[str, Usage]


def as_completion(result: CompletionResult) -> Completion:
    """Read what a plugin returned, in either admissible form.

    The pair becomes a `Completion` with every widened field at its default —
    which is the correct reading of it: a plugin that returns a pair has not
    said the model called no tools, it has said nothing about tools at all.
    """
    if isinstance(result, Completion):
        return result
    text, usage = result
    return Completion(text=text, usage=usage)


def finish_of(
    word: str | None, table: Mapping[str, Finish]
) -> tuple[Finish | None, str | None]:
    """A provider's word as `(finish, finish_raw)`.

    Shared so that the one rule no plugin may get wrong is written once: a word
    the table does not know maps to **`other`, and keeps the word**. It must not
    map to `stop`. A provider that adds a stop reason next quarter would
    otherwise turn a truncated run green on upgrade, which is fixed decision 3's
    vacuously green assertion arriving through a different door.

    Said nothing stays nothing: `None` in, `(None, None)` out, and every
    consumer falls back to what it did before this record existed.
    """
    if not word:
        return None, None
    return table.get(word, "other"), word


#: Why a reply that said nothing said nothing, per ending, in the vocabulary
#: every plugin translates into (ADR 0004 §6). One sentence per outcome, because
#: they need different actions: raising `max_tokens` fixes the first and nothing
#: at all about the others.
#:
#: Written for either side of ADR 0004 — the target under test and the judge
#: grading one both go mute the same way — so the sentences say "text" rather
#: than naming a shape. `JudgeBase` passes its own table for the one entry where
#: the two really do differ: a judge was asked for a JSON object, and saying so
#: is the difference between a cause and a category.
WHY_SILENT: Mapping[Finish, str] = {
    "length": "it was truncated before the first character — raise max_tokens",
    "tool_use": "it answered with a tool call instead of text",
    "filtered": "the reply was refused or filtered, not written",
    "stop": "it ended normally and said nothing, which is a prompt or a model "
    "that will not answer in the shape asked for",
    "other": "the provider ended the turn for a reason of its own",
}


def said_something(text: str, prefill: str | None = None) -> bool:
    """Whether the *model* contributed anything, past what we wrote for it.

    A plugin may open the assistant turn for the model — Anthropic prefills `{`
    so the reply is a JSON object whether or not the model felt like opening
    one — and prepends that prefill back before returning, which is right for
    parsing and wrong for this question: a model that produced nothing comes
    back as `"{"`, and `"{"` is not empty. Without this, the provider most
    likely to be prefilling would be the one provider the check never fired for.

    One implementation and two callers, like `ObservedIdentity` above: the
    target path and the judge path ask the same question of the same field, and
    a second copy of it would be the one that fell behind.
    """
    body = text
    if prefill and body.startswith(prefill):
        body = body[len(prefill) :]
    return bool(body.strip())


def no_text_reason(
    reply: Completion,
    *,
    subject: str,
    max_tokens: int | None = None,
    why: Mapping[Finish, str] = WHY_SILENT,
) -> str:
    """Why a reply that said nothing said nothing, as a sentence.

    Since ADR 0004 §6 the cause is **read** rather than inferred, and this is
    the one case where the two disagree most: a model that answered with a tool
    call and a model cut off at the cap look identical to a token count when the
    cap was also reached, and they need opposite fixes.

    The inference below is kept as the fallback, and it is not a courtesy: a
    provider on a compatible endpoint that reports no finish reason is the
    ordinary case, and this is the sentence that serves it. The numbers are what
    this layer holds when the provider says nothing, so they are what it may
    claim — and a caller that cannot name a cap (`max_tokens=None`) does not get
    a sentence about one, because a cap nobody sent is not a cap the reply hit.
    """
    counted = (
        f"{reply.usage.output_tokens}"
        if max_tokens is None
        else f"{reply.usage.output_tokens} of {max_tokens}"
    )
    if reply.finish is not None:
        # The provider's own word beside ours: `finish` decides the sentence,
        # `finish_raw` is what an operator will search the provider's docs for.
        said = reply.finish if reply.finish_raw is None else reply.finish_raw
        return (
            f"{subject} returned no text: the provider reported {said!r} "
            f"({counted} output tokens), so {why[reply.finish]}"
        )
    if max_tokens is None:
        return (
            f"{subject} returned no text ({counted} output tokens) and the "
            "provider reported no reason — a non-text reply or a refusal"
        )
    if reply.usage.output_tokens >= max_tokens:
        return (
            f"{subject} returned no text: output hit the max_tokens cap "
            f"({counted}) — likely truncated before the first character"
        )
    return (
        f"{subject} returned no text with output well under the cap "
        f"({counted}) — a non-text reply or a refusal"
    )


class ObservedIdentity:
    """What the provider said answered, held to one answer for the run.

    Mutable and deliberately so: it accumulates across calls, which is the whole
    point — a `ProviderTarget` and a `JudgeBase` both learn their identity by
    being used, and `execute()` reads it after the last case for exactly that
    reason (ADR 0005 §8, §9).

    One implementation and two users, because the rule is one rule. It is ADR
    0005 §9's split, and the split is not a softening of §8 — it is §8's own
    question asked of each field: *does a change here mean a different system
    was measured?*

    **`resolved_model` raises.** A model that rolled under an alias part way
    through is the system changing mid-measurement, which is what §8 refuses to
    average away; the caller lets it out, and the driver errors that one case
    while the run is still written.

    **`fingerprint` goes absent.** OpenAI documents `system_fingerprint` as
    changing whenever they change the backend configuration, so raising on it
    would paint runs red for an event with no bearing on which model answered —
    the false red that teaches a team to stop reading the colour. Absent instead
    reads, under the observed-absence rule, as *the provider did not say*.
    """

    __slots__ = ("_asked_as", "_fingerprint", "_model", "_rotated")

    def __init__(self, asked_as: str) -> None:
        #: The alias the caller sent, quoted in the message so a reader knows
        #: which declaration the two observations were hiding behind.
        self._asked_as = asked_as
        self._model: str | None = None
        self._fingerprint: str | None = None
        self._rotated = False

    def see(self, reply: Completion) -> None:
        """Take in one reply. Raises when the model id contradicts the run."""
        if reply.model is not None:
            if self._model is None:
                self._model = reply.model
            elif self._model != reply.model:
                raise ValueError(
                    f"the provider answered as {self._model!r} and then as "
                    f"{reply.model!r} part way through the run, both under "
                    f"model={self._asked_as!r}. One run measures one system, so "
                    "there is no single identity to record: pin the model id "
                    "instead of the alias, or evaluate each one as its own run"
                )
        if reply.fingerprint is not None:
            if self._fingerprint is None:
                self._fingerprint = reply.fingerprint
            elif self._fingerprint != reply.fingerprint:
                self._rotated = True

    @property
    def values(self) -> dict[str, str | None]:
        """The two fields, for `sent()` to drop the absent ones.

        `None` here is *the provider did not say* rather than *we did not send
        it* — a different fact behind the same absence, which is why ADR 0005 §9
        spends a section on it and why `sent()` has a sibling name in the plugin
        docs rather than a flag.
        """
        return {
            "resolved_model": self._model,
            "fingerprint": None if self._rotated else self._fingerprint,
        }
