"""A refusal, rendered for a program that is not inside the perimeter.

The command line, `pytest-digline` and a library caller read `str()` of a
refusal, the whole sentence, because their reader is the person who ran the
command. An MCP client is a model's context. It gets the same refusal with
every field but one: the message of an exception digline did not write, which
is payload like a verdict's `reason` (decision 9). Where it is left out, the
sentence says so, and says where to read it. (ADR 0043 §3)

Who wrote the message is not decided here. It is read from frames, which is
the filesystem, so `digline.host.to_withhold` decides and hands over the
fields, and this renders them.
"""

from __future__ import annotations

from digline.core import Minter, Quoted

__all__ = ["WITHHELD", "refusal_text"]

#: What the agent reads in place of the message. The command that prints the
#: traceback follows it, where there is one, and running it is the agent's own
#: act: *the user's code can read the user's data* and *digline ships it* are
#: two statements (ADR 0042).
WITHHELD = (
    "Its message was not written by digline and may quote a case's data, so it "
    "is not shown here. The same command on the command line shows it."
)


def refusal_text(
    refusal: BaseException, withheld: Quoted | None, *, mint: Minter | None = None
) -> str:
    """The refusal's sentence for an agent: whole when `withheld` is `None`,
    and without the quoted message otherwise. Given `mint`, each name the
    sentence quotes is its token, as an answer under `project` names it.
    (ADR 0054 §8)"""
    if withheld is not None:
        return withheld.rendered(withheld=WITHHELD, mint=mint)
    said = refusal.args[0] if len(refusal.args) == 1 else None
    if mint is not None and isinstance(said, Quoted):
        return said.rendered(withheld=None, mint=mint)
    return str(refusal)
