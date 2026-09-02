"""The pipeline under test: two runnable steps over seven local documents.

Step one is ordinary Python — keyword retrieval over the handbook, so the
example needs no index and no embeddings. Step two is the LLM call: the passage
and the request go into a prompt, and one JSON object comes back.

`answer()` returns the model's **text**, not a parsed object. That is on
purpose: what breaks when you upgrade langchain or the model is the shape of
that text — a code fence appears around the JSON, a field is renamed, the parser
starts handing back content blocks instead of a string. A chain that parses
before it returns turns all of that into an exception, and an exception is a
worse thing to compare than a string.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda

HERE = Path(__file__).parent

#: The handbook, keyed by the id the model is asked to cite.
DOCUMENTS: dict[str, str] = {
    f"handbook/{path.stem}": path.read_text(encoding="utf-8")
    for path in sorted((HERE / "documents").glob("*.md"))
}

SYSTEM = (HERE / "prompts" / "extract.txt").read_text(encoding="utf-8")
REQUEST = (HERE / "prompts" / "request.txt").read_text(encoding="utf-8")

#: What each page answers. Keyword matching, because a vector store would make
#: this example about a vector store.
_KEYWORDS = {
    "handbook/accounts": ("password", "account", "sign in", "log in", "locked"),
    "handbook/payments": ("payment", "card", "charged", "pay ", "refund"),
    "handbook/returns": ("return", "send back", "unworn", "30 days"),
    "handbook/shipping": ("deliver", "shipping", "island", "arrive", "warehouse"),
    "handbook/sizing": ("size", "sizing", "chart", "measure", "larger"),
    "handbook/warranty": ("warranty", "zip", "faulty", "repair", "stitching"),
}

#: Where a request that matches no page goes. The prompt then tells the model to
#: say the handbook does not cover it and hand over to a person, which is what
#: `needs_human` is for.
FALLBACK = "handbook/contact"


def select(request: str) -> str:
    """Step one. The page with the most keywords in common with the request."""
    lowered = request.lower()
    hits = {
        source: sum(word in lowered for word in words)
        for source, words in _KEYWORDS.items()
    }
    # `sorted` before `max` so a tie is broken by name rather than by whatever
    # order the dict happens to have: retrieval that is not reproducible makes
    # every comparison below it meaningless.
    best = max(sorted(hits), key=lambda source: hits[source])
    return best if hits[best] else FALLBACK


def passage(request: str) -> str:
    """The text step one selected. The suite freezes it into `Case.context`, so
    the judge reads the same passage the chain was given."""
    return DOCUMENTS[select(request)]


def _retrieve(payload: Mapping[str, str]) -> dict[str, str]:
    request = payload["request"]
    source = select(request)
    return {"request": request, "source": source, "passage": DOCUMENTS[source]}


def build_chain(model: BaseChatModel) -> Runnable[dict[str, str], str]:
    """`{"request": ...}` in, the model's JSON text out.

    The system prompt is passed as a `SystemMessage` rather than as a
    `("system", ...)` tuple: a tuple is a template, and this one contains the
    literal braces of the JSON shape it asks for, which a template would read as
    variables and refuse to fill.
    """
    prompt = ChatPromptTemplate.from_messages(
        [SystemMessage(content=SYSTEM), ("human", REQUEST)]
    )
    return RunnableLambda(_retrieve) | prompt | model | StrOutputParser()


def answer(request: str, model: BaseChatModel) -> str:
    """The whole pipeline, invoked in process. No server, no HTTP."""
    return build_chain(model).invoke({"request": request})
