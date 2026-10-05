"""The refusal digline writes in words, as a type of its own, and what it quotes."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Quoted", "RefusedError"]


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


# `eq=False`: two refusals are never compared, and `cause` is an exception,
# which compares by identity anyway. `slots=True` is the house style for values.
@dataclass(frozen=True, slots=True, eq=False)
class Quoted:
    """A refusal digline wrote that quotes another exception, kept in fields.

    Digline no longer interpolates another exception's text into its own
    sentence. A site that wraps hands this to the refusal as its one argument,
    `UsageError(Quoted.of(exc, ...))`. So `str()` of the refusal is still the
    whole sentence, for the person who ran the command. A front end that must
    not ship the message renders the same refusal without it. (ADR 0043 §2)

    `before`, `after` and `reproduce` are digline's words. `kind`, `exit_code`
    and `locations` are code. **`message` is whoever raised `cause`'s**, and
    who that is is read from `cause`'s innermost frame, never from its type
    (§1). That reading needs the filesystem, so it is done in `digline.host`
    and not here. `builtin` marks the sites where the frame cannot say. A
    builtin digline calls has no frame of its own, so the innermost frame is
    digline's whatever the builtin quoted. Such a site is declared by name, and
    its message is never digline's (§6).
    """

    before: str
    kind: str
    message: str
    cause: BaseException = field(repr=False)
    after: str = ""
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
    def of(
        cls,
        exc: BaseException,
        before: str,
        after: str = "",
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
        if isinstance(exc, SystemExit):
            code = exc.code
            if isinstance(code, int):
                exit_code, said = code, ""
            else:
                # `sys.exit()` asks for nothing, and quotes nothing either.
                said = "" if code is None else repr(code)
        else:
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

    def __str__(self) -> str:
        """The whole sentence, message included."""
        return self.rendered(withheld=None)

    def rendered(self, *, withheld: str | None) -> str:
        """The sentence with the message, or, given `withheld`, without it and
        with those words after the location instead: what a front end says
        about what it left out. The type, the locations and the command stay
        either way."""
        hidden = withheld is not None and bool(self.message)
        if self.kind == "SystemExit":
            if self.exit_code is not None:
                code = repr(self.exit_code)
            else:
                code = "…" if hidden else (self.message or "None")
            described = f"SystemExit({code})"
        elif self.message and not hidden:
            described = f"{self.kind}: {self.message}" if self.named else self.message
        else:
            described = self.kind
        text = f"{self.before}{described}{_at(self.locations)}{self.after}"
        if hidden:
            text += f"{'' if text.endswith('.') else '.'} {withheld}"
        if self.reproduce is not None:
            text += f" For the full traceback, run: {self.reproduce}"
        return text


def _at(locations: tuple[str, ...]) -> str:
    if not locations:
        return ""
    at = f" at {locations[0]}"
    if len(locations) > 1:
        at += f", reached from {locations[-1]}"
    return at
