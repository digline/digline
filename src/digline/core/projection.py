"""The projection: a run with every name replaced by a token.

Two ways in, for two documents. `project` makes **the committed file**: when
the store lives with the end company, that file is a projection of a promotion
that already happened (ADR 0034 §2). `project_served` makes **what a page
served at the data owner's side shows**, which may be a run nobody promoted
(ADR 0038 §1). Both are produced inside the process that owns the name table
(ADR 0036 §7), which is not digline's: this module is what that process calls,
and it is handed the minting function rather than a table.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

from digline.core.aggregate import grouped_name, split_grouped_name
from digline.core.refused import Quoted
from digline.core.run import CaseResult, Run, SystemConfig, redact
from digline.core.tokens import Minter, TokenKind, is_token
from digline.core.types import NOTHING_EXTRA, ConfigValue, Verdict

__all__ = ["ProjectionRefusedError", "project", "project_served"]


class ProjectionRefusedError(ValueError):
    """Raised when a run cannot be projected, or the minter answered wrong.

    A `ValueError` like the core's other refusals, and listed in
    `host.REFUSALS` so a front end translates it rather than crashing.
    """


def project(run: Run, mint: Minter) -> Run:
    """`run` as the software house may commit it: redacted, then every name
    replaced by the token `mint` returns for it.

    **`project_served` with the two refusals of a reference in front.** What
    it produces, and everything else it refuses, is `project_served`'s, so the
    two cannot drift: for a reference, both return the same document.

    **Refused**, as `ProjectionRefusedError`, before anything else:

    - a run that is already projected, first, so that this sentence and not
      the next one is what a projected document meets;
    - a run that is not a promoted reference. **This is checked from what the
      document says, and nothing more**: `promoted_at` must be set and no
      recorded answer may remain. A `Run` built by hand with a stamp and no
      answers passes. Nothing on the value says that `promote_baseline`
      returned it, and nothing here can.

    **Why these two are this function's and not `project_served`'s.** Their
    reason is ADR 0034 §2's: start from a promotion, and inherit its refusals
    for free, so that a non-reference is not committed. A page that is served
    commits nothing, and that reason does not reach it (ADR 0038 §1). They are
    refused unconditionally here, not by a parameter: a parameter would make the
    committed file's protection a default, and a default is what no test of a
    flag exercises.
    """
    if run.projected:
        raise ProjectionRefusedError(
            "this run is already projected: its names are tokens, and "
            "projecting it again would mint tokens for tokens"
        )
    if not run.promoted_at:
        raise ProjectionRefusedError(
            "this run was not promoted: a projection to commit starts from the "
            "reference promote_baseline returns, which carries the time it was "
            "signed off, and this carries none. A page that shows it uses "
            "project_served"
        )
    if any(case.responses for case in run.results):
        raise ProjectionRefusedError(
            "this run still carries the target's recorded answers, and a "
            "promoted reference carries none: project the run promote_baseline "
            "returned. A page that shows it uses project_served"
        )
    return project_served(run, mint)


def project_served(run: Run, mint: Minter) -> Run:
    """`run` as a page served at the data owner's side may show it: redacted,
    then every name replaced by the token `mint` returns for it. **Promoted or
    not.** (ADR 0038 §1)

    **It carries what a projected reference carries, and no more**, plus what a
    run has that a reference does not (ADR 0038 §2). Recorded answers become
    `RecordedResponse(withheld=True)`, so their **count** crosses, as every
    number crosses a projection today, under ADR 0034 §4's open axis. An
    errored verdict keeps its status and loses its reason, and its string
    metadata goes with redaction. Promotion's refusals are not applied: the
    runs they refuse are the ones a reviewer most needs to see.

    **The order is the definition.** The projection is `redact(run)` first and
    tokenisation after it, never the reverse. Redaction withholds the
    perimeter fields while their keys are still text: `base_url` and
    `fingerprint`, and `resolved_model` wherever `base_url` names an endpoint.
    Tokenise first and the keys are tokens, so nothing recognises them. The
    perimeter fields then cross under tokens, and the widening that withholds
    `resolved_model` never switches on. `Run`'s perimeter check does not catch
    that: on a projected document it cannot fire. It holds because nothing is
    there to find, and only this order puts nothing there. (ADR 0034 §8,
    §7.2's route)

    **No `Disclosure`.** Redaction here is with `NOTHING_EXTRA`. So the owning
    process needs no suite, and nothing a suite disclosed crosses a projection.
    That is a narrowing, and `projected` declares it.

    Where each name goes, by kind, is `rename`'s list: one map, which the
    resolver reads in the other direction. **Through one table**, a served run
    and a projected reference pair case by case, so `compare()` can be run on
    the two projections (ADR 0038 §3, shape B).

    **What tells its document from a projected reference** is what the
    document already says: a reference carries `promoted_at` and no answer, and
    a run nobody promoted carries no `promoted_at`. `read_baseline` refuses a
    projected document that is not a reference, so a served projection cannot
    stand where a reference belongs.

    It returns a `Run`. It writes nothing, commits nothing, and knows neither
    the store nor where the document goes. `run_to_json` serializes it.

    **Refused**, as `ProjectionRefusedError`:

    - a run that is already projected;
    - a token that is not a token: `mint` answered something without a
      token's form, gave one (kind, text) two tokens within this call, or
      gave two (kind, text) one token. **The check on a token is of its form**:
      a minter that echoed a 22-character name of the token alphabet back
      would pass;
    - an identity on the target side, which no kind covers. It is empty
      whenever digline wrote the run;
    - a verdict whose `assertion_id` is not a digest: an assertion that
      overrides `identity` with readable text, which a projection would carry
      in clear. `dataclass_identity` derives one that projects.

    What `Run` refuses of a projected document, it refuses here too, because
    the result is built through it.
    """
    if run.projected:
        raise ProjectionRefusedError(
            "this run is already projected: its names are tokens, and "
            "projecting it again would mint tokens for tokens"
        )
    if run.target_config.identities:
        raise ProjectionRefusedError(
            "the target configuration lists identities, which no token kind "
            "covers: digline records them on the judge side only"
        )
    # First, and for the reason in the docstring: withheld while the keys are
    # still text.
    source = redact(run, NOTHING_EXTRA)
    try:
        return rename(source, _Tokens(mint), projected=True)
    except ValueError as exc:
        # What `Run` refuses of a projected document, named as this function's
        # refusal: most often an identity written by hand as readable text,
        # whose message says to use `dataclass_identity`. A typed refusal, the
        # minter's included, passes through unchanged. (Delta-pass over
        # 0.25.0, F-4)
        if type(exc) is not ValueError:
            raise
        raise ProjectionRefusedError(Quoted.of(exc, "", named=False)) from exc


#: What `rename` is handed: the new text for a name of a kind. `project` hands
#: it a minter's token for the text; `resolve_tokens` hands it a row's text for
#: the token.
type Rename = Callable[[TokenKind, str], str]


def rename(run: Run, name: Rename, *, projected: bool) -> Run:
    """`run` with every name replaced by `name(kind, name)`, and `projected`
    set as given.

    **The one map from place to kind**, in both directions: the projection
    writes a token where this says a kind sits, and the resolver checks a row's
    kind against the same place. Written once so that the two cannot disagree
    about the document's shape.

    - a case's id: `case_id`;
    - a verdict's name, and an aggregate's family: `verdict_name`;
    - the group inside `family[group=…]`: `group`, rebuilt with `grouped_name`;
    - a calibration band's check: `calibration_check`;
    - artifact paths, as keys and in `pinned`: `artifact_path`;
    - configuration keys, in `values` and in `withheld`, and string values:
      the key and value kinds of their side;
    - a judge's `provider/model` label: `judge_identity`.
    """
    return replace(
        run,
        results=tuple(_case(case, name) for case in run.results),
        aggregate=tuple(_aggregate(v, name) for v in run.aggregate),
        artifacts={
            name("artifact_path", path): artifact
            for path, artifact in run.artifacts.items()
        },
        pinned=tuple(name("artifact_path", path) for path in run.pinned),
        target_config=_config(
            run.target_config,
            name,
            "target_config_key",
            "target_config_value",
            projected=projected,
        ),
        judge_config=_config(
            run.judge_config,
            name,
            "judge_config_key",
            "judge_config_value",
            projected=projected,
        ),
        projected=projected,
    )


class _Tokens:
    """`mint`, asked every time and held to one answer per (kind, text).

    Asked every time rather than cached, because a cache would hide the one
    inconsistency this call can see: a minter that answers one (kind, text)
    with two tokens. Two tokens for one name pair as `new` plus `missing`,
    which exits 0. (ADR 0036 §6)
    """

    def __init__(self, mint: Minter) -> None:
        self._mint = mint
        self._by_text: dict[tuple[TokenKind, str], str] = {}
        self._by_token: dict[str, tuple[TokenKind, str]] = {}

    def __call__(self, kind: TokenKind, text: str) -> str:
        # Held as `object`: the minter is the owning process's code, and its
        # annotation is a promise this checks rather than trusts.
        answer = cast(object, self._mint(kind, text))
        if not isinstance(answer, str) or not is_token(answer):
            raise ProjectionRefusedError(
                f"the minter answered {answer!r} for a {kind}, which does not "
                "have a token's form: 22 characters of url-safe base64"
            )
        token = answer
        seen = self._by_text.setdefault((kind, text), token)
        if seen != token:
            raise ProjectionRefusedError(
                f"the minter gave one {kind} two tokens in one projection: the "
                "same name would pair as new and missing"
            )
        owner = self._by_token.setdefault(token, (kind, text))
        if owner != (kind, text):
            raise ProjectionRefusedError(
                f"the minter gave a {kind} a token it had already given "
                f"another {owner[0]} in this projection: two names would read "
                "as one"
            )
        return token


def _verdict(verdict: Verdict, name: str) -> Verdict:
    return replace(verdict, score=replace(verdict.score, name=name))


def _case(case: CaseResult, name: Rename) -> CaseResult:
    return replace(
        case,
        case_id=name("case_id", case.case_id),
        verdicts=tuple(
            _verdict(v, name("verdict_name", v.score.name)) for v in case.verdicts
        ),
        calibration=(
            None
            if case.calibration is None
            else replace(
                case.calibration,
                check=name("calibration_check", case.calibration.check),
            )
        ),
    )


def _aggregate(verdict: Verdict, name: Rename) -> Verdict:
    family, group = split_grouped_name(verdict.score.name)
    renamed = name("verdict_name", family)
    if group is not None:
        renamed = grouped_name(renamed, name("group", group))
    return _verdict(verdict, renamed)


def _config(
    config: SystemConfig,
    name: Rename,
    key: TokenKind,
    value: TokenKind,
    *,
    projected: bool,
) -> SystemConfig:
    def mapped(v: ConfigValue) -> ConfigValue:
        return name(value, v) if isinstance(v, str) else v

    return SystemConfig(
        values={name(key, k): mapped(v) for k, v in config.values.items()},
        withheld=frozenset(name(key, k) for k in config.withheld),
        identities=tuple(name("judge_identity", label) for label in config.identities),
        projected=projected,
    )
