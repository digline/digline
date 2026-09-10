"""The query engine under test: an index over four local pages, and one call.

Real LlamaIndex all the way down — `VectorStoreIndex`, `VectorIndexRetriever`,
`RetrieverQueryEngine`, the compact response synthesizer and a prompt template
read from a file. What is *not* real is the embedding: `HashEmbedding` below is
a local stand-in, so an example about a framework can be run by somebody with
no account. See `README.md` §2 for what that costs you.

`answer()` returns the engine's **text**. Retrieval runs on every call rather
than being frozen into the cases, which is the difference between this example
and `examples/rag`: there the passages are frozen and the generator is under
test, here the whole pipeline is, retrieval included.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

from llama_index.core import Document, PromptTemplate, VectorStoreIndex
from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.llms import LLM
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.retrievers import VectorIndexRetriever

HERE = Path(__file__).parent

#: The handbook, keyed by the id the answer is asked to cite.
PAGES: dict[str, str] = {
    f"handbook/{path.stem}": path.read_text(encoding="utf-8")
    for path in sorted((HERE / "handbook").glob("*.md"))
}

QA_TEMPLATE = (HERE / "prompts" / "qa_template.txt").read_text(encoding="utf-8")

#: How many buckets the stand-in embedding hashes into. Large enough that two
#: words of this handbook rarely collide, small enough to stay readable.
DIMENSIONS = 1024

#: A stem shorter than this is ignored. The rule looks arbitrary and is not:
#: in a handbook about bike hire the short words *are* the furniture — bike,
#: dock, ride, hire, pass — and every page is full of them, so a question
#: matches whichever page repeats them most. That is not a hypothetical: with
#: four-letter words counted, *"a brake failed, where do I leave it?"*
#: retrieved the hire page, which says nothing about brakes. A real embedding
#: model has no such problem, having read the rest of the language first.
SHORTEST = 5

#: Stems are truncated to this many characters before hashing — a poor man's
#: stemmer. Without it `refund`, `refunded` and `refunds` are three unrelated
#: axes, and a question asking about one does not reach the page stating
#: another.
STEM = 6


def _stems(text: str) -> list[str]:
    return [word[:STEM] for word in re.findall(rf"[a-z]{{{SHORTEST},}}", text.lower())]


def _vector(text: str) -> list[float]:
    """A bag of hashed word stems, normalised to length one.

    Cosine similarity over this is real retrieval — nearer questions really do
    reach nearer pages — and it is a pure function of the text, so a run is
    reproducible on a machine that has never seen a model.
    """
    axes = [0.0] * DIMENSIONS
    for stem in _stems(text):
        digest = hashlib.blake2b(stem.encode(), digest_size=8).digest()
        axes[int.from_bytes(digest, "big") % DIMENSIONS] += 1.0
    # A zero vector would divide by zero and, worse, score identically against
    # everything; `or 1.0` leaves it zero, which is below any cutoff.
    norm = math.sqrt(sum(axis * axis for axis in axes)) or 1.0
    return [axis / norm for axis in axes]


class HashEmbedding(BaseEmbedding):
    """A local, deterministic stand-in for an embedding model.

    LlamaIndex ships `MockEmbedding`, and it cannot be used here: it returns
    the same constant vector for every text, so every page is equidistant from
    every question and the retriever's ranking is whatever order the store
    happens to hold. That is not retrieval, and a suite built on it would be
    measuring nothing.
    """

    @classmethod
    def class_name(cls) -> str:
        return "HashEmbedding"

    def _get_query_embedding(self, query: str) -> list[float]:
        return _vector(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return _vector(text)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return _vector(query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return _vector(text)


def documents() -> list[Document]:
    """The handbook as LlamaIndex documents, each carrying the id to cite.

    Built by hand rather than with `SimpleDirectoryReader`, for one reason that
    only shows up later: the reader puts the **absolute** `file_path` in the
    node metadata, it reaches the prompt, and from there it reaches the
    committed baseline. A baseline that differs between two machines compares
    nothing.

    `source` is excluded from the embedding and not from the prompt: the page
    id is what the answer must cite, and it is noise in a similarity score.
    """
    return [
        Document(
            text=text,
            metadata={"source": source},
            excluded_embed_metadata_keys=["source"],
        )
        for source, text in PAGES.items()
    ]


def build_engine(llm: LLM) -> BaseQueryEngine:
    """The pipeline: index, retriever, prompt, synthesizer.

    `RetrieverQueryEngine.from_args` rather than `index.as_query_engine`. The
    two do the same thing and only this one is typed — `as_query_engine` is
    `reportUnknownMemberType` under pyright strict, which this example's own
    gate runs. It is also the more honest shape: the retriever and its `top_k`
    are the decisions a RAG lives or dies by, and here they are named.
    """
    index = VectorStoreIndex.from_documents(documents(), embed_model=HashEmbedding())
    return RetrieverQueryEngine.from_args(
        VectorIndexRetriever(index=index, similarity_top_k=1),
        llm=llm,
        text_qa_template=PromptTemplate(QA_TEMPLATE),
    )


def answer(question: str, llm: LLM) -> str:
    """The whole engine, invoked in process. No server, no HTTP."""
    return str(build_engine(llm).query(question))


def page(source: str) -> str:
    """One handbook page, for the case that declares which one should answer it."""
    return PAGES[source]
