"""The refusal digline writes in words, as a type of its own, and what it quotes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from digline.core.tokens import Minter, TokenKind

__all__ = ["NameRef", "Quoted", "RefusedError", "Said"]


class RefusedError(ValueError):
    """Raised on purpose, with a sentence written for whoever made the request:
    a check declared so that it could never fail, a suite that names a check it
    does not have, an endpoint that did not answer at preflight.

    A `ValueError` before it was a class of its own, and still one, so a caller
    that catches `ValueError` catches it. **The type is what says *on purpose*.**
    A deliberate refusal and a bug both start inside digline, so the frame
    cannot tell them apart. A bare `ValueError` that reaches a front end is a
    failure nobody anticipated, and exits 70. (ADR 0041 §4.2)

    Not every deliberate `ValueError` is one. A site raises this when its error
    reaches a front end along the user's road. It stays bare when the same
    `raise` also guards digline's own computation (`Score`, `Verdict`, the `Run`
    family), and when it is raised inside a run-time catch. There the type name
    is written into a committed verdict's reason, and an internal class name has
    no place in it.
    """


@dataclass(frozen=True, slots=True)
class NameRef:
    """A name a refusal quotes, with the kind the projection mints it under.

    In a sentence it reads as its text, as `repr` writes it when `quoted`,
    which is how the sites wrote it before (`{name!r}`). A front end that
    projects reads it as its token instead, minted under `kind`, so a refusal
    that crosses the boundary under `project` names what the answers name: a
    token, never the text. (ADR 0054 §8)
    """

    kind: TokenKind
    text: str
    quoted: bool = True

    def rendered(self, mint: Minter | None) -> str:
        if mint is None:
            said = self.text
        elif self.kind == "verdict_name":
            # Imported here: `projection` builds on the `Run` family, which
            # raises with these. A check's name may carry its group, and the
            # projection mints the two apart. (ADR 0054 §7)
            from digline.core.projection import project_check_name

            said = project_check_name(self.text, mint)
        else:
            said = mint(self.kind, self.text)
        return repr(said) if self.quoted else said


#: Words of a sentence: digline's own text, or a sequence of digline's text and
#: the names it quotes.
type Said = str | Sequence[str | NameRef]


def _parts(said: Said) -> tuple[str | NameRef, ...]:
    return (said,) if isinstance(said, str) else tuple(said)


def _empty(said: Said) -> bool:
    return all(part == "" for part in _parts(said))


def _text(said: Said, mint: Minter | None) -> str:
    return "".join(
        part if isinstance(part, str) else part.rendered(mint) for part in _parts(said)
    )


# `eq=False`: two refusals are never compared, and `cause` is an exception,
# which compares by identity anyway. `slots=True` is the house style for values.
@dataclass(frozen=True, slots=True, eq=False)
class Quoted:
    """A sentence digline wrote, kept in fields: its own words, the names it
    quotes, and what it quotes of another exception, if it quotes one.

    A site hands this to the refusal as its one argument,
    `UsageError(Quoted.of(exc, ...))` or `ValueError(Quoted.said(...))`. So
    `str()` of the refusal is still the whole sentence, for the person who ran
    the command. A front end that must not ship a message renders the same
    refusal without it (ADR 0043 §2), and one that projects renders each name
    as its token (ADR 0054 §8).

    `before`, `after` and `reproduce` are digline's words, with the names they
    quote as `NameRef`s. `kind`, `exit_code` and `locations` are code.
    **`message` is whoever raised `cause`'s**, and who that is is read from
    `cause`'s innermost frame, never from its type (§1). That reading needs the
    filesystem, so it is done in `digline.host` and not here. `builtin` marks
    the sites where the frame cannot say. A builtin digline calls has no frame
    of its own, so the innermost frame is digline's whatever the builtin
    quoted. Such a site is declared by name, and its message is never
    digline's (§6). A sentence that quotes no exception has no `cause`, no
    `kind` and no `message`.

    *The name says half of it since ADR 0054 §8*, which made a sentence that
    quotes nothing one of these too. Renaming a public name waits for a
    major release.
    """

    before: Said
    kind: str
    message: Said
    cause: BaseException | None = field(repr=False)
    after: Said = ""
    exit_code: int | None = None
    #: `file:line`, innermost first: where the raise was, then where the
    #: suite's code was entered, when the two differ.
    locations: tuple[str, ...] = ()
    reproduce: str | None = None
    builtin: bool = False
    #: Whether the whole sentence names the type before the message. A site
    #: that re-raises another refusal as its own says the message alone, as it
    #: always has. Left out, the type is still what stands in its place.
    named: bool = True

    @classmethod
    def said(cls, *parts: str | NameRef) -> Quoted:
        """A sentence of digline's that quotes no exception, its names kept
        apart from its words."""
        return cls(before=parts, kind="", message="", cause=None, named=False)

    @classmethod
    def of(
        cls,
        exc: BaseException,
        before: Said,
        after: Said = "",
        *,
        locations: tuple[str, ...] = (),
        reproduce: str | None = None,
        message: str | None = None,
        builtin: bool = False,
        named: bool = True,
    ) -> Quoted:
        """The fields of `exc`. A `SystemExit` follows ADR 0043 §5: an `int`
        code is the code that was asked for, and anything else is a message.

        `message` replaces `str(exc)` where a site has to clean the text before
        even the command line sees it, such as a credential `HttpTarget` reads
        off its own URL.
        """
        exit_code: int | None = None
        said: Said
        if isinstance(exc, SystemExit):
            code = exc.code
            if isinstance(code, int):
                exit_code, said = code, ""
            else:
                # `sys.exit()` asks for nothing, and quotes nothing either.
                said = "" if code is None else repr(code)
        elif len(exc.args) == 1 and isinstance(exc.args[0], Quoted):
            # A refusal of digline's built from a `Quoted`: its words and its
            # names are taken as they are, so a name it quotes is still a name
            # here, and a front end that projects renders its token.
            said = exc.args[0].parts()
        else:
            # **Anything else is flattened to its text, in silence**: a name
            # in it is no longer a `NameRef`, and a front end that projects
            # ships it in clear. Nothing here can tell. What does is the names
            # gate, `packages/digline-mcp/tests/test_names_gate.py`, which
            # drives the refusals that cross the boundary and is red on a name
            # in a sentence. (ADR 0054 §8)
            said = str(exc)
        return cls(
            before=before,
            kind=type(exc).__name__,
            message=said if message is None else message,
            cause=exc,
            after=after,
            exit_code=exit_code,
            locations=locations,
            reproduce=reproduce,
            builtin=builtin,
            named=named,
        )

    @property
    def names(self) -> tuple[NameRef, ...]:
        """Every name the sentence quotes, in order."""
        return tuple(
            part
            for said in (self.before, self.message, self.after)
            for part in _parts(said)
            if isinstance(part, NameRef)
        )

    def around(self, before: Said, after: Said) -> Quoted:
        """The same sentence with `before` in front of it and `after` behind,
        the names in all three kept."""
        return replace(
            self,
            before=(*_parts(before), *_parts(self.before)),
            after=(*_parts(self.after), *_parts(after)),
        )

    def parts(self) -> tuple[str | NameRef, ...]:
        """The whole sentence, message included, as words and names: what
        `str()` reads, before any name is rendered."""
        said = self._parts(hidden=False)
        if self.reproduce is not None:
            said = (*said, f" For the full traceback, run: {self.reproduce}")
        return said

    def __str__(self) -> str:
        """The whole sentence, message included."""
        return self.rendered(withheld=None)

    def rendered(self, *, withheld: str | None, mint: Minter | None = None) -> str:
        """The sentence with the message, or, given `withheld`, without it and
        with those words after the location instead: what a front end says
        about what it left out. The type, the locations and the command stay
        either way. Given `mint`, each name is its token. (ADR 0054 §8)"""
        hidden = withheld is not None and not _empty(self.message)
        text = _text(self._parts(hidden=hidden), mint)
        if hidden:
            text += f"{'' if text.endswith('.') else '.'} {withheld}"
        if self.reproduce is not None:
            text += f" For the full traceback, run: {self.reproduce}"
        return text

    def _parts(self, *, hidden: bool) -> tuple[str | NameRef, ...]:
        return (*_parts(self.before), *self._described(hidden=hidden), *self._tail())

    def _described(self, *, hidden: bool) -> tuple[str | NameRef, ...]:
        message = _parts(self.message)
        if self.kind == "SystemExit":
            if self.exit_code is not None:
                code = repr(self.exit_code)
            else:
                code = "…" if hidden else (_text(self.message, None) or "None")
            return (f"SystemExit({code})",)
        if not _empty(self.message) and not hidden:
            return (f"{self.kind}: ", *message) if self.named else message
        return (self.kind,)

    def _tail(self) -> tuple[str | NameRef, ...]:
        return (_at(self.locations), *_parts(self.after))


def _at(locations: tuple[str, ...]) -> str:
    if not locations:
        return ""
    at = f" at {locations[0]}"
    if len(locations) > 1:
        at += f", reached from {locations[-1]}"
    return at
