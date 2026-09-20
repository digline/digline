"""The words a reading may not say, shared by every gate that reads prose.

Plain data and one matcher, deliberately not a test module: `explain` was the
first reading held to these lists, and `log` is the second (ADR 0020 §5). A test
module importing another makes collection order matter, so the lists live here
and both gates import them.
"""

from __future__ import annotations

import re

__all__ = ["ADVICE", "EXECUTION", "IDENTITY", "MULTI_RUN", "SPECULATION", "spoken"]

#: Words that turn a reading into counsel. `AGENTS.md` holds the judgment
#: digline does not encode, and a helpful sentence does not look like an
#: architectural violation, which is why this is a gate and not a convention.
#:
#: Inflections are listed rather than matched as prefixes, and "against" is why:
#: a prefix match forbade `explain.check.new` for containing "again", which is
#: a matcher shaping the prose instead of guarding it. Every entry here is a
#: whole word somebody might actually write.
ADVICE = (
    "should",
    "shouldn't",
    "ought",
    "must",
    "try",
    "tries",
    "consider",
    "considering",
    "recommend",
    "recommends",
    "recommended",
    "suggest",
    "suggests",
    "advise",
    "advises",
    "promote",
    "promotes",
    "rerun",
    "re-run",
    "dovresti",
    "dovrebbe",
    "dovrebbero",
    "prova",
    "provare",
    "considera",
    "considerare",
    "consiglia",
    "consigliato",
    "suggerisce",
    "suggerito",
    "puoi",
    "promuovi",
    "promuovere",
    "riesegui",
    "rieseguire",
)

#: Words that claim a measurement over more than one run. A reading is of one
#: run and its reference; "did not repeat" needs a cycle, and the thing that
#: runs cycles is the operator loop — which keeps those layers, and marks the
#: one a model wrote as an opinion rather than as digline's verdict.
MULTI_RUN = (
    "repeat",
    "repeats",
    "repeated",
    "again",
    "recur",
    "recurs",
    "recurred",
    "recurring",
    "drift",
    "drifts",
    "drifted",
    "drifting",
    "wobble",
    "wobbles",
    "flaky",
    "trend",
    "trends",
    "ripete",
    "ripetuto",
    "ricorre",
    "ricorso",
    "deriva",
    "oscilla",
    "instabile",
    "tendenza",
)

#: The canary's word, and only the canary's (ADR 0016 §7). A reading of the
#: record states what was declared; the moment it says *likely* it has started
#: inferring identity from behaviour, which is the deduction ADR 0020 refuses.
SPECULATION = (
    "likely",
    "probably",
    "presumably",
    "probabilmente",
    "presumibilmente",
)

#: Verbs that claim a **model executed**, where the record holds configuration.
#: The run file says what the suite sent and what the provider reported; it
#: never observes the running process, so a sentence built on a sent field may
#: not say it answered. ADR 0020 §3 row 7 states the rule for the one case that
#: looks hardest — an id echoed back is "what was asked for, not what answered".
#:
#: Applied to `explain.*`, `fact.*` and `config.*`. **Not to `log.*`**: there
#: "answered as" rests on ADR 0020's ruling that a *differing* reported id is a
#: sighting, which is doctrine to amend rather than prose to fix.
#:
#: Anchored to the placeholder, because the object is what decides. "Answered
#: under a different configuration" is supportable and stays; so is "ha risposto
#: con una configurazione diversa", which says the same thing in the same
#: strength. What may not be said is the verb taking a configuration **value**:
#: `answered with {name} {after}`, where `{name}` is usually a field this run
#: sent. Both were live when this list was written, and a blunt list would have
#: rewritten four honest sentences to catch two dishonest ones.
EXECUTION = (
    "answered with {",
    "answered as {",
    "graded with {",
    "ha risposto con {",
    "ha risposto come {",
    "ha valutato con {",
    # The same claim with no placeholder to anchor it: a heading over a table
    # of sent parameters, which is where `config.title` hid.
    "what answered",
    "what judged",
    "che cosa ha risposto",
    "che cosa ha giudicato",
)

#: Nouns that name the thing under test rather than the reading. For the
#: doctrine sentences a locale may not quietly strengthen: `log.rolls.none`
#: means *there was almost nothing to compare*, never *the provider held
#: still*, and the Italian said the second for as long as nothing compared the
#: pair. (docs/log.md, "the absences")
IDENTITY = (
    "model",
    "modello",
)


def spoken(words: tuple[str, ...], text: str) -> list[str]:
    """Which of `words` the text uses, matched as words rather than as
    substrings — `\b` on both sides, which is what keeps "against" from
    reading as "again"."""
    lowered = text.lower()
    return [
        word
        for word in words
        if re.search(rf"\b{re.escape(word)}\b", lowered) is not None
    ]
