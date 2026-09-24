"""Third-party text on a machine surface, and the two ranges JSON leaves raw.

A tool name, a model id, a finish reason: provider-supplied strings that reach a
program through `digline.wire`. They are not trusted text — the endpoint a suite
points at may be a gateway, a proxy, or a compatible server nobody here reviews —
and a terminal is very often what reads the program's output next.

It lives in `core` because **every** front end needs it and a front end may not
import another one. `report.visible()` is the same rule for a sentence and sits
one layer up for the same reason; this one is lower still because `digline.wire`
is where the machine surface is rendered, and `wire` may not import `report`
either. Putting it here is what makes a third front end inherit the rule without
knowing it exists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

__all__ = [
    "NEVER_LANGUAGE",
    "json_visible",
    "recordable",
    "without_lone_surrogates",
]

#: DEL and C1 as their JSON `\\u00XX` spelling — the two ranges a JSON encoder
#: leaves raw. C0 is not here: every encoder in play already escapes it.
_UNESCAPED_BY_JSON = {code: f"\\u{code:04x}" for code in (0x7F, *range(0x80, 0xA0))}


def _spelling(code: int) -> str:
    """A code point as the escape a reader can see.

    Two widths because one of these ranges is astral: `\\uXXXX` cannot spell
    U+E0041, and a five-digit `\\u` is not a spelling anything recognises. The
    eight-digit `\\U` form is what Python and C both write.
    """
    return f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}"


#: Characters that are **never language**, and the whole of what this widening
#: covers. Each is a formatting instruction to a renderer, not a letter in any
#: script, and none of them can appear in prose anybody wrote on purpose.
#:
#: - **U+202A–U+202E**, the bidi embeddings and overrides. Deprecated by Unicode
#:   itself in favour of the isolates, and the overrides are what reverse the
#:   display order of a path so a reader sees a name that is not there.
#: - **U+FFF9–U+FFFB**, the interlinear annotation characters, which exist to
#:   hide one run of text behind another in plain text.
#: - **U+E0000–U+E007F**, the tag block: a copy of ASCII that renders as
#:   nothing at all, so a sentence written in it is invisible in every surface
#:   digline has and exactly recoverable by whatever parses the text.
#:
#: **What is deliberately absent is the rest of `Cf`, and that is the whole
#: design.** U+200E/U+200F (LRM, RLM) and U+061C (ALM) set direction in ordinary
#: Arabic and Hebrew prose; U+200C/U+200D (ZWNJ, ZWJ) carry meaning in Indic
#: scripts and hold emoji sequences together; U+2066–U+2069 are the isolates
#: Unicode recommends *instead of* the overrides above. Neutralising the
#: category would corrupt a report rendered in a language this project intends
#: to serve, which is the argument `report.escape()` has always made about bidi
#: marks and which survives here unchanged — it was only ever wrong about the
#: overrides, not about the marks.
NEVER_LANGUAGE = {
    code: _spelling(code)
    for code in (
        *range(0x202A, 0x202F),
        *range(0xFFF9, 0xFFFC),
        *range(0xE0000, 0xE0080),
    )
}

#: The surrogate range, as the escape spelling of each code point. Every
#: surrogate in a Python `str` is unpaired by construction — a well-formed pair
#: is one character by the time it is a `str` — so the whole block is the rule.
_SURROGATES = {code: f"\\u{code:04x}" for code in range(0xD800, 0xE000)}


def json_visible(text: str) -> str:
    """`text` with DEL and the C1 block written as their JSON escapes.

    **The two ranges, and why only these two.** A JSON encoder escapes C0 —
    `\\x1b` becomes `\\u001b` — and stops there. DEL (U+007F) and the C1 block
    (U+0080–U+009F) go out raw, and U+009B *is* CSI: on a terminal it opens the
    same sequence ESC `[` does, so `\\u009b2K\\u009b31m` erases the line being
    printed and recolours what follows. A document that reads *"Nothing got
    worse."* can therefore be written by the thing being measured.

    **Applied to the value, not to the serialised document.** That is the part
    worth understanding, because it is a deliberate loss. Escaping the finished
    JSON text would leave the parsed value identical — `\\u009b` and the raw
    byte are the same character to a parser — and that is what `digline.cli`
    did alone until 0.15.0. It cannot work for every front end: `digline-mcp`
    hands dictionaries to an SDK that serialises them itself, so digline never
    sees those bytes. The only place both front ends share is the value, so the
    value is where the rule goes, and a consumer now reads six characters where
    it used to read one.

    That trade is made on purpose and stated where consumers read it
    (`OUTPUT_VERSION` 2): a control byte inside a provider-supplied tool name is
    not data anybody needs verbatim, and the same fact must not read differently
    at two front ends — which is the whole reason `digline.wire` exists.

    Language is untouched. This neutralises two control ranges and the
    characters that are never language (`NEVER_LANGUAGE`) — not accents,
    arrows, em dashes or bidi *marks*: those are legitimate text in the
    languages a report is written for, and `report.escape()` states the same
    exemption.

    **The third range, and why it was not here before.** 0.10.1 closed DEL and
    C1 against a terminal. That is a defence of one reader, and the reader this
    function was written for is the other one: `digline.wire` renders for a
    program, and since 0.15.0 that program is very often an agent holding
    tools. A tag character is invisible to every surface digline has and is an
    exact encoding of ASCII, so a `case_id` can carry a sentence addressed to
    that agent past a human who reviewed the document and saw nothing. The
    payload does not cross a boundary and no file is read — what moves is an
    instruction, into the context of the one reader that acts on instructions.
    """
    return text.translate(_UNESCAPED_BY_JSON).translate(NEVER_LANGUAGE)


def without_lone_surrogates(text: str) -> str:
    """`text` with every surrogate written as its escape spelling.

    **What this is for.** A run document is written with `ensure_ascii=False`,
    which is what keeps a committed baseline readable: a judge's reason in
    Italian stays Italian, and a reviewer reads prose rather than `\\u00e8`. The
    cost of that is real and was found by the delta-pass over 0.15.0 — a single
    unpaired surrogate anywhere in provider text makes the whole file
    un-encodable, so `digline run` ends at exit 64 with **no run file** after
    every call has been paid for, and `--resume` replays and dies at the same
    byte forever.

    **Why not `ensure_ascii=True`.** It fixes the crash and costs the baseline:
    every accent and arrow in every recorded reason becomes an escape, in the one
    artifact a human reviews in a pull request. The readability of that file is
    the premise of the whole escaping argument — a reader who cannot read it
    cannot review it — so trading it permanently against a rare malformed byte is
    the wrong side of the trade. This neutralises the byte instead and leaves
    every other character alone.

    Shown, not stripped, like `visible()` and `json_visible()` before it: a value
    that carried a broken code point is a value somebody should look at, and the
    six characters say exactly which one it was.
    """
    return text.translate(_SURROGATES)


def recordable[T](document: T) -> T:
    """`document` with every string in it safe to write as UTF-8.

    Applied where a run document is serialised rather than where each field is
    built, for the reason every other rule here is applied at a sink: a field
    added later inherits it instead of needing somebody to remember. Walks keys
    as well as values — a `Score.metadata` key is suite-supplied text like any
    other.
    """
    if isinstance(document, str):
        return without_lone_surrogates(document)  # pyright: ignore[reportReturnType]
    if isinstance(document, dict):
        items = cast("Mapping[object, object]", document)
        walked = {recordable(key): recordable(value) for key, value in items.items()}
        return cast("T", walked)
    if isinstance(document, list | tuple):
        members = cast("Sequence[object]", document)
        walked_list = [recordable(item) for item in members]
        return cast(
            "T", tuple(walked_list) if isinstance(document, tuple) else walked_list
        )
    return document
