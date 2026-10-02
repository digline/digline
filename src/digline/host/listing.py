"""A suite's runs, and the key of its baseline, as a program shows them. (#276)

The list `digline view` opens on, built for a program outside digline: every
readable run with its document, the key the baseline is known by, and what the
read could not show. **In clear, or projected, and the caller says which**: on
a projected page every run in the list is projected, through one minter, or the
call refuses (ADR 0038 §1).

`scan_runs` stays internal. This is the read a program that *shows* runs
needs, and the store's scan is one step of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, cast

from digline.core import (
    DocumentRefusedError,
    Minter,
    ProjectionRefusedError,
    Run,
    TokenKind,
    is_token,
    key_of,
    project_served,
)
from digline.core.run import SCHEMA_VERSION, is_run_key
from digline.report import Locale, phrase
from digline.store import (
    Listing,
    NotAReferenceError,
    PathRefusedError,
    ResultStore,
    RunNotFoundError,
    SuiteMismatchError,
    TenantMismatchError,
)

__all__ = ["SuiteRuns", "left_out", "suite_runs"]

#: How many refused runs the line names before it counts the rest. The line
#: sits above or beside a table it qualifies, and every refused run is still
#: in `SuiteRuns.refused` for a caller that wants them all. (#339)
_NAMED_REFUSALS = 3

#: What the store refuses of one document it was asked to read. A run refused
#: this way is left out of the list and named; the others are still listed.
_DOCUMENT_REFUSALS = (
    DocumentRefusedError,
    PathRefusedError,
    RunNotFoundError,
    SuiteMismatchError,
    TenantMismatchError,
)


@dataclass(frozen=True, slots=True)
class SuiteRuns:
    """What `suite_runs` read, and what it could not.

    `runs` is `runs_page`'s input as it stands: `(key, run)` pairs, in key
    order, which is chronological where digline named the files. A key is the
    stored file's name; see `suite_runs` for what that means on a projected
    list. `baseline_key` is `None` in two situations,
    and `baseline_refused` tells them apart: empty when the suite has no
    baseline yet, a sentence when one is there and could not be read. A page
    must not say *no baseline yet* about a baseline it failed to read.

    `refused` is `(key, what refused it)` for every run the scan found and the
    read did not show. **On a projected listing, what refused it is the
    refusal's type and not its sentence**: a refusal can quote a name, and the
    page it is shown on names none.

    `unnamed` counts what a projected listing left out **without naming it**,
    because the only name it had was a file name that is not a run key: a
    readable run filed under a name other than its `key_of`, or a refused file
    whose name has no run key's form. Always 0 on a listing in clear.
    """

    runs: tuple[tuple[str, Run], ...]
    baseline_key: str | None
    baseline_refused: str
    listing: Listing
    refused: tuple[tuple[str, str], ...]
    unnamed: int

    def note(self) -> str:
        """One line naming what was left out, or empty when nothing was.

        **An empty note does not mean nothing is missing.** It names what the
        scan skipped, what the read refused, and a baseline whose run is not in
        the list. A run removed from the store is said only in that last case,
        for the reason `resolve_key` gives (#286).

        In English, for a terminal and for `--json`. A document shows
        `left_out`, which says the same in its locale. (#339)
        """
        return "; ".join(_parts(self, "en", advise=False))


def left_out(listed: SuiteRuns, *, locale: Locale) -> str:
    """`listed.note()` as a document shows it, in the document's language.

    `locale` is **mandatory, with no default**, as on `render_html`: the line
    sits on a page with a recipient. Only its frame is translated. A refusal's
    sentence, in clear, is the store's and stays as the store wrote it.

    It says one thing `note()` does not: what to do about runs skipped for
    their schema, because a page has no second line to put that on.

    **It is true wherever it is shown**, beside a list or beside one case's
    history: neither line says anything that holds only for a list. (#339)
    """
    return "; ".join(_parts(listed, locale, advise=True))


def _parts(listed: SuiteRuns, locale: Locale, *, advise: bool) -> list[str]:
    parts: list[str] = []
    scan = listed.listing
    skipped = [
        phrase(locale, "left_out.schema", count=count, version=version)
        for version, count in sorted(scan.skipped.items())
    ]
    if scan.unreadable:
        skipped.append(
            phrase(locale, "left_out.unreadable", count=len(scan.unreadable))
        )
    if skipped:
        parts.append(phrase(locale, "left_out.ignored", parts=", ".join(skipped)))
    if advise:
        # `Listing.advice` in the reader's language: the same two directions,
        # on the same comparison with the schema this digline writes.
        if any(version < SCHEMA_VERSION for version in scan.skipped):
            parts.append(phrase(locale, "left_out.migrate"))
        if any(version > SCHEMA_VERSION for version in scan.skipped):
            parts.append(phrase(locale, "left_out.upgrade"))
    if listed.refused:
        named = [f"{key} ({why})" for key, why in listed.refused[:_NAMED_REFUSALS]]
        rest = len(listed.refused) - _NAMED_REFUSALS
        if rest > 0:
            named.append(phrase(locale, "left_out.more", count=rest))
        parts.append(
            phrase(
                locale,
                "left_out.refused",
                count=len(listed.refused),
                keys=", ".join(named),
            )
        )
    if listed.unnamed:
        parts.append(phrase(locale, "left_out.unnamed", count=listed.unnamed))
    if listed.baseline_refused:
        parts.append(
            phrase(locale, "left_out.baseline_refused", why=listed.baseline_refused)
        )
    elif listed.baseline_key is not None and listed.baseline_key not in {
        key for key, _ in listed.runs
    }:
        parts.append(
            phrase(locale, "left_out.baseline_missing", run_key=listed.baseline_key)
        )
    return parts


def suite_runs(
    store: ResultStore, tenant: str, suite: str, *, mint: Minter | None
) -> SuiteRuns:
    """Every readable run of `suite` in `tenant`, and the key of its baseline.

    **It opens every document.** A list that shows aggregates has to read them,
    and the store keeps no index: the cost is every stored run parsed in full,
    which is what `digline view` has always paid for its first screen.

    `mint` is **mandatory, with no default**, for `locale`'s reason: `None`
    lists in clear, a minter lists projected, and a default would answer for a
    caller which of the two a page shows. Projected, every run goes through
    `project_served` and **one wrapper around `mint` for the whole call**, so
    one name has one token across the list and not only within one run. That
    is what lets the page hold a row's aggregates against the baseline's by
    name. digline never opens the table (ADR 0036 §2); it calls what it was
    handed.

    **A run that cannot be projected is left out, never shown in clear.** It is
    named in `refused` by key.

    **A key is the name of the file the run is stored in.** Where digline
    wrote the file, the name is `key_of(created_at, config_hash)`: a time and
    a digest, which `rename` leaves alone, so it names nothing on either side.
    A file somebody named otherwise is another matter, and the two listings
    treat it differently:

    - **In clear**, it is listed and refused under its file name, as the store
      addresses it. That name is what `read_run` needs.
    - **Projected**, a file name is shown only where it names nothing. A
      readable run is listed only if its file name is its `key_of`. A refused
      file is named only if its name has a run key's form. Anything else is
      counted in `unnamed` and named nowhere, so control characters in a file
      name do not reach `note()` either. (Delta-pass over 0.25.2, F-1)

    **That repairs the page, not the split.** The store answers *what is a
    run's key* two ways, the file's name and `key_of`. That is #332, and an ADR
    is owed before it is closed.

    Raised, for the whole call:

    - `PathRefusedError` when `tenant` or `suite` is not one safe name;
    - `ProjectionRefusedError` when the minter answers wrong anywhere in the
      list: an answer without a token's form, one name given two tokens, or
      two names given one. A page built on that would pair rows that are not
      the same and miss rows that are;
    - anything the minter itself raises. A table that cannot be written is the
      owning process's failure, and no page is better than a page minted from
      part of it.

    **One callable is not proved to be one table.** Nothing on a projected
    document says which table minted it (ADR 0036). What this checks is the
    answers it was given.
    """
    listing = store.scan_runs(tenant, suite)
    table = None if mint is None else _OneTable(mint)

    runs: list[tuple[str, Run]] = []
    refused: list[tuple[str, str]] = []
    unnamed = 0
    for ref in listing.runs:
        try:
            run = store.read_run(ref)
            if table is not None:
                run = project_served(run, table)
        except ProjectionRefusedError as exc:
            if table is not None and table.faulted:
                raise
            why = _why(exc, projected=table is not None)
        except _DOCUMENT_REFUSALS as exc:
            why = _why(exc, projected=table is not None)
        else:
            # `rename` leaves `created_at` and `config_hash` alone, so the key
            # is the same before and after the projection.
            if table is not None and ref.key != key_of(run.created_at, run.config_hash):
                unnamed += 1
            else:
                runs.append((ref.key, run))
            continue
        if table is not None and not is_run_key(ref.key):
            unnamed += 1
        else:
            refused.append((ref.key, why))

    baseline_key: str | None = None
    baseline_refused = ""
    try:
        baseline = store.read_baseline(tenant, suite)
    except (*_DOCUMENT_REFUSALS, NotAReferenceError) as exc:
        baseline_refused = _why(exc, projected=table is not None)
    else:
        if baseline is not None:
            baseline_key = key_of(baseline.created_at, baseline.config_hash)

    return SuiteRuns(
        runs=tuple(runs),
        baseline_key=baseline_key,
        baseline_refused=baseline_refused,
        listing=listing,
        refused=tuple(refused),
        unnamed=unnamed,
    )


def _why(exc: Exception, *, projected: bool) -> str:
    """The refusal as a page may show it: its sentence in clear, its type on a
    projected page."""
    return type(exc).__name__ if projected else str(exc)


class _OneTable:
    """`mint`, held to one answer per (kind, text) across the whole list.

    `project_served` holds the minter to that within one run. A list is many
    runs on one page, and a minter that answered a name one way for the first
    row and another way for the second would pass every one of those checks
    while the page compared rows that do not pair. **Every answer passes
    through here first**, so a fault in the minter is caught by this wrapper
    and marked, and the list can tell it from a run that cannot be projected.

    Its sentences name the kind and never the text or the answer: the text is
    a name, and a minter that echoes it back has put a name in its answer.
    """

    def __init__(self, mint: Minter) -> None:
        self._mint = mint
        self._by_text: dict[tuple[TokenKind, str], str] = {}
        self._by_token: dict[str, tuple[TokenKind, str]] = {}
        self.faulted = False

    def __call__(self, kind: TokenKind, text: str) -> str:
        # Held as `object`: the minter is the owning process's code, and its
        # annotation is a promise this checks rather than trusts.
        answer = cast(object, self._mint(kind, text))
        if not isinstance(answer, str) or not is_token(answer):
            self._fault(
                f"the minter answered a {kind} with something that does not have "
                "a token's form: 22 characters of url-safe base64"
            )
        token = answer
        if self._by_text.setdefault((kind, text), token) != token:
            self._fault(
                f"the minter gave one {kind} two tokens in one list: its rows "
                "would not pair"
            )
        owner = self._by_token.setdefault(token, (kind, text))
        if owner != (kind, text):
            self._fault(
                f"the minter gave a {kind} a token it had already given another "
                f"{owner[0]} in this list: two names would read as one"
            )
        return token

    def _fault(self, sentence: str) -> NoReturn:
        self.faulted = True
        raise ProjectionRefusedError(sentence)
