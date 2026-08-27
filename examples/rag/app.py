"""The RAG under test: a retriever and a generator, both stand-ins.

`EMBELLISH` is the switch this example turns to show what the checks catch. With
it off the generator says only what the retrieved passages say. With it on it
adds a sentence nobody retrieved — which is exactly the failure a RAG has, and
exactly what `Faithfulness` is for.
"""

from __future__ import annotations

from corpus import DOCUMENTS

#: Shipped on, so `digline compare` against the committed baseline shows the
#: point straight away. Turn it off and the suite goes green again.
EMBELLISH = True

_KEYWORDS = {
    "hours": ("open", "sunday", "hours", "saturday"),
    "cards": ("card", "join", "member", "cost"),
    "loans": ("borrow", "loan", "renew", "many"),
    "fines": ("fine", "late", "overdue"),
    "rooms": ("room", "study", "book a"),
    "wifi": ("wifi", "internet", "password"),
    "printing": ("print", "photocopy", "colour"),
    "children": ("child", "story", "kids"),
    "donations": ("donate", "donation", "give"),
    "contact": ("contact", "email", "write"),
}

#: What the generator adds when it is embellishing. Plausible, unsupported, and
#: the kind of sentence a reader would never question.
_INVENTED = " The library has been on this square since 1898."


def retrieve(question: str) -> list[str]:
    """The retriever. Keyword matching, so the example needs no index."""
    lowered = question.lower()
    hits = [
        key
        for key, words in _KEYWORDS.items()
        if any(word in lowered for word in words)
    ]
    return [DOCUMENTS[key] for key in hits[:2]] or [DOCUMENTS["contact"]]


def answer(question: str, context: list[str]) -> tuple[str, float]:
    """The generator. Replace with your model; the shape is what matters."""
    said = " ".join(passage.split(".")[0].strip() + "." for passage in context)
    if EMBELLISH:
        said += _INVENTED
    cost = 0.0006 + 0.0000004 * sum(len(passage) for passage in context)
    return said, round(cost, 6)
