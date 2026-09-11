"""Whether the document in hand was written by a digline newer than this one.

A fact rather than a message, and it lives here for ADR 0011 §6's reason: the
CLI prints it on stderr, a program reads it as a field, and both come from one
function so the two surfaces cannot disagree about what *behind* means.

It is never an exit code. The exit codes are a contract about the suite
(`AGENTS.md` §6), and a tooling mismatch is not a verdict on a suite.
(ADR 0014 §4)
"""

from __future__ import annotations

from collections.abc import Iterable

from digline import __version__
from digline.core import release_tuple

__all__ = ["ahead_note", "writer_ahead"]


def writer_ahead(written_by: str, installed: str = __version__) -> bool:
    """Whether `written_by` is a later release than `installed`.

    Not the schema check wearing another hat. If the schema moved, the reader
    already refused and named the file; this covers the case that refusal cannot
    see — **same schema, newer writer** — where the document parses and fields
    written under rules this version does not have are read by the rules it has.

    An unrecorded version is never *ahead*: `release_tuple("")` is `()`, which
    compares less than every real release.
    """
    return release_tuple(written_by) > release_tuple(installed)


def ahead_note(written_by: Iterable[str], installed: str = __version__) -> str:
    """One line about the newest document that is ahead, or nothing to say.

    Takes an iterable because the commands that read two documents — a run and
    its baseline, two runs of a diff — would otherwise print the same warning
    twice about one installation. The newest one ahead is the one that matters:
    it is the release the reader has to reach.

    Empty when nothing is ahead, which is the ordinary case and is therefore
    silent. A store full of older documents is what every migrated store looks
    like, and a warning that fired on the ordinary case would be one the reader
    learns to skip — taking the rare one with it.
    """
    ahead = [version for version in written_by if writer_ahead(version, installed)]
    if not ahead:
        return ""
    newest = max(ahead, key=release_tuple)
    return (
        f"written by digline {newest}, running {installed}: a newer digline "
        "wrote this document, and what that version added is being read here by "
        "older rules. Upgrade digline — a newer document is never rewritten "
        "backwards."
    )
