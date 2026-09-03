"""What a wrong suite file is told.

Half of ADR 0007 is about this, and not incidentally: *"a format whose failure
mode is a silent default is worse than no format."* Two families live here.

**An unknown key is a load error.** A silently dropped `treshold` is a check
running on its default, and for a threshold the default a typo falls back to is
the one that passes — fixed decision 3's vacuously green assertion, arriving in
configuration form. The refusal is mechanical (a wrong keyword to a frozen
dataclass raises); what this module adds is the part that helps: which file,
which entry, which key, and the near miss when there is one.

**A boundary names the way out.** When a TOML asks for what only Python can
give, "unknown type" and "invalid value" are both wrong answers: the reader has
hit a real limit of the format and needs to be told what is on the other side
of it. Every sentence here ends with somewhere to go. A user who is told what
is on the other side of a wall makes a decision; one who is told "invalid"
files a bug.

The messages are data as far as the tests are concerned — `test_toml_errors.py`
reads this module's output, not its source — so the wording can change without
a test rewrite, while the *shape* stays pinned: a locator, a cause, a way out.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Sequence

from digline.cli.errors import UsageError

__all__ = [
    "code_only",
    "computed_body",
    "did_you_mean",
    "listing",
    "unknown_key",
    "unknown_type",
]

#: Where a reader goes to write the Python a data file cannot express. Named in
#: every boundary message; `test_toml_errors.py` checks the file is really
#: there, because a pointer at a page that moved is worse than none.
CUSTOM_DOCS = "docs/api.md"

#: The sentence every boundary ends with. One phrasing, so a reader who meets
#: two boundaries recognises the second as the same kind of thing.
WAY_OUT = f"this suite needs a suite.py. See {CUSTOM_DOCS}."


def did_you_mean(word: str, options: Iterable[str]) -> str:
    """`" Did you mean \\`threshold\\`?"`, or nothing.

    Two passes. A separator swap is tried first and exactly — `llm-rubric` for
    `llm_rubric` is the habit a reader brings from YAML, and it is a certainty
    rather than a guess, so it should not have to clear a similarity bar.
    Everything else goes to `difflib`, which catches the ordinary transposition
    (`treshold`, `tolerence`, `neelde`).
    """
    known = list(options)
    swapped = word.replace("-", "_").replace(" ", "_")
    if swapped != word and swapped in known:
        return f" Did you mean `{swapped}`?"
    close = difflib.get_close_matches(word, known, n=1, cutoff=0.6)
    return f" Did you mean `{close[0]}`?" if close else ""


def listing(names: Iterable[str]) -> str:
    """Names in backticks, sorted, comma separated."""
    return ", ".join(f"`{name}`" for name in sorted(names))


def unknown_key(
    given: Iterable[str],
    allowed: Iterable[str],
    *,
    where: str,
    noun: str,
    owner: str | None = None,
) -> UsageError | None:
    """The refusal for keys nothing accepts, or `None` when they are all known.

    Returns rather than raises so the caller keeps the `raise` at the point a
    reader looks for it.

    A near miss replaces the full list rather than joining it: when the answer
    is one word away, twelve alternatives are noise. With no near miss the list
    is the only help there is, so it is printed in full.
    """
    known = list(allowed)
    unknown = [key for key in given if key not in known]
    if not unknown:
        return None

    subject = f"`{owner}` has no" if owner else "no such"
    if len(unknown) == 1:
        head = f"{where}: {subject} {noun} `{unknown[0]}`."
        if hint := did_you_mean(unknown[0], known):
            return UsageError(head + hint)
        return UsageError(f"{head} Known {noun}s: {listing(known)}")

    lines = [f"{where}: {subject} {noun} {listing(unknown)}."]
    for key in unknown:
        if hint := did_you_mean(key, known):
            lines.append(f"  `{key}`:{hint.replace(' Did you mean', ' did you mean')}")
    if len(lines) == 1:
        lines.append(f"Known {noun}s: {listing(known)}")
    return UsageError("\n".join(lines))


def unknown_type(
    token: str,
    *,
    where: str,
    per_case: Iterable[str],
    per_run: Iterable[str],
) -> UsageError:
    """No check goes by that name.

    The two families are listed apart when there is no near miss: a reader
    looking for `precision` and a reader looking for `contains` are asking
    different questions, and one alphabetical run of nineteen tokens answers
    neither.
    """
    every = [*per_case, *per_run]
    head = f"{where}: there is no check called `{token}`."
    if hint := did_you_mean(token, every):
        return UsageError(head + hint)
    return UsageError(
        f"{head}\n  per case: {listing(per_case)}\n  per run:  {listing(per_run)}"
    )


def code_only(cause: str, *, where: str, kind: str = "assertions") -> UsageError:
    """A boundary: the file is asking for something only Python can give.

    `cause` says what was asked for and why it cannot be data; the tail says
    where to go. Split that way because the second half is the same every time
    and a reader should recognise it as the same answer.
    """
    return UsageError(f"{where}: {cause} — custom {kind} are code, and {WAY_OUT}")


def not_a_coordinate(value: str, *, where: str, key: str) -> UsageError:
    """A judge that is not `provider/model`.

    The shape of what was written decides the sentence. Somebody who wrote
    `digline_anthropic:AnthropicJudge` has not made a typo — they have reached
    for an import, which is the alternative ADR 0007 considered and refused,
    and telling them "not a coordinate" would leave them to try three more
    spellings of the same idea.
    """
    if ":" in value or (value.count(".") and "/" not in value):
        return UsageError(
            f"{where}: `{key}` is {value!r}, which is an import written as a "
            "string. A judge is named by coordinates instead — provider/model, "
            'as in "anthropic/claude-haiku-4-5" — because a data file that '
            "could name a Python object could run any of them, and because the "
            "coordinate is already what a run records as the instrument that "
            f"graded it. A judge with rules of its own has no coordinates: {WAY_OUT}"
        )
    return UsageError(
        f"{where}: `{key}` is {value!r}, which is not a provider/model "
        "coordinate. Write the provider, a slash, and the model — for example "
        '"anthropic/claude-haiku-4-5".'
    )


def object_parameter(key: str, *, where: str, provider: str) -> UsageError:
    """`client` or `pricing` in a `[target]`: injection points, not settings."""
    return UsageError(
        f"{where}: `{key}` is a Python object, not configuration — it is where "
        f"a test injects a stand-in for {provider}, and a data file has "
        f"nothing to put there. Drop it; a suite that needs to inject one is a "
        f"suite.py. See {CUSTOM_DOCS}."
    )


def computed_body(where: str) -> UsageError:
    """`request` in an `[target] type = "http"`.

    Written out rather than built from `code_only`, because the way out here is
    not "write Python" — it is *"write the other key"*, and a message that led
    with suite.py would send somebody to rewrite a suite that has one line
    wrong. The Python answer is still there, last, for the body that genuinely
    has to be computed.
    """
    return UsageError(
        f"{where}: `request` is a function, and the data form is "
        "`[target.body]` — a table shaped like the payload, whose leaves name "
        "case fields:\n\n"
        "  [target.body]\n"
        '  question = "case.vars.question"\n\n'
        "One level of reference and no expressions, so the nesting, the arrays "
        "and the types of a real payload survive. A body that has to be "
        f"*computed* is the one shape this form gives up: {WAY_OUT}"
    )


def missing_parameters(names: Sequence[str], *, where: str, token: str) -> UsageError:
    return UsageError(
        f"{where}: `{token}` needs {listing(names)}, which this entry does not give it."
    )
