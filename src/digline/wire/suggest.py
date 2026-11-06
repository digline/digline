"""What `digline suggest` found, as one value, and that value for a program.
(ADR 0063 §5, §6; ADR 0011 §1, as noted 2026-11-06)

**One value, two readers.** The host reads the suite's recordings, reviewed
answers and runs into a `Suggestion`. Standard error is rendered from it, in
the words of the fifth step of the `proposing-a-suite` skill, and the MCP
server returns `suggest_json` of it. Neither renders a fact the other does
not hold.

**No recorded word, and no rule of the file.** The value holds counts, the
checks by their number, type and name, the setups by their digests and the
shapes of the groups. The rules read from the recordings, a tool's name or a
key, are in the file the command writes, and are not here; neither is a
check's sentence of why, which a program can read off the counts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from digline.wire.contract import OUTPUT_VERSION
from digline.wire.recordings import Shape, shape_json
from digline.wire.text import neutralised

__all__ = [
    "ProposedCheck",
    "SuggestGroup",
    "Suggestion",
    "suggest_json",
]


@dataclass(frozen=True, slots=True)
class ProposedCheck:
    """One check the proposal holds: its number in the file, its TOML type,
    its name, the sentence of why standard error says beside it, and how many
    of its values are placeholders."""

    number: int
    type: str
    name: str
    why: str
    placeholders: int


@dataclass(frozen=True, slots=True)
class SuggestGroup:
    """One group of the recordings not yet examined, by the shape of their
    output: how many answers, from how many recordings, and, for a suite that
    exists and has a capture file to read, how many no person has named."""

    shape: Shape
    answers: int
    recordings: int
    waiting: int | None


@dataclass(frozen=True, slots=True)
class Suggestion:
    """Everything `digline suggest` says, as facts.

    `form` is `"suite.toml"` or `"suite.py"` where the suite exists, `None`
    for one that does not exist yet. `proposal` is the file, as the command
    says it, and `written` whether it was written: over the MCP server it
    never is. `nothing` is true where there was no recording and no reviewed
    answer, so nothing was proposed; `recorder_on` then says whether the
    tenant's recorder was on with no call naming the suite, and
    `recorded_suites` the suites its calls named. `setups` are the setups the
    suite's recordings were made under, per form (`True` for the episodes),
    each by its eight characters, oldest first, the last the one in force.
    """

    tenant: str
    suite: str
    repository: str
    form: str | None
    proposal: str
    written: bool
    nothing: bool = False
    recorder_on: bool = False
    recorded_suites: tuple[str, ...] = ()
    setups: Mapping[bool, tuple[str, ...]] | None = None
    judged: str = ""
    judge_declared: bool = False
    plugins: tuple[str, ...] = ()
    checks: tuple[ProposedCheck, ...] = ()
    already: tuple[str, ...] = ()
    runs: int = 0
    unread: int = 0
    empty: int = 0
    placeholders: int = 0
    suite_file: str | None = None
    adopted: tuple[int, ...] = ()
    calibrated: bool = False
    noes: int = 0
    cases_file: str = ""
    counterexample_by_assistant: bool = False
    assisted: bool = False
    groups: tuple[SuggestGroup, ...] = ()
    unassigned: int = 0


def suggest_json(
    found: Suggestion, *, command: str, with_model: str
) -> dict[str, object]:
    """The proposal's facts for a program, and the command that writes the
    file, `command`, which a person runs. No assistant was asked: what one
    costs is said before its call, and `with_model` is the command that asks
    one. No `exit_code`: a proposal is not a gate."""
    setups = found.setups or {}
    return neutralised(
        {
            "output_version": OUTPUT_VERSION,
            "tenant": found.tenant,
            "suite": found.suite,
            "repository": found.repository,
            "form": found.form,
            "proposal": found.proposal,
            "written": found.written,
            "command": command,
            "nothing": found.nothing,
            "recorder_on": found.recorder_on,
            "recorded_suites": list(found.recorded_suites),
            "setups": {
                "single_calls": list(setups.get(False, ())),
                "episodes": list(setups.get(True, ())),
            },
            "judge": {
                "check": found.judged,
                "declared": found.judge_declared,
                "plugins": list(found.plugins),
            },
            "checks": [
                {
                    "number": check.number,
                    "type": check.type,
                    "name": check.name,
                    "placeholders": check.placeholders,
                }
                for check in found.checks
            ],
            "already": list(found.already),
            "runs": {"read": found.runs, "unread": found.unread, "empty": found.empty},
            "placeholders": found.placeholders,
            "adopted": {"file": found.suite_file, "lines": list(found.adopted)},
            "calibration": {"proposed": not found.calibrated},
            "counterexample": {
                "reviewed_noes": found.noes,
                "cases_file": found.cases_file,
                "constructed": found.noes == 0,
            },
            "groups": [
                {
                    **shape_json(group.shape),
                    "answers": group.answers,
                    "recordings": group.recordings,
                    "waiting": group.waiting,
                }
                for group in found.groups
            ],
            "unassigned": found.unassigned,
            "assistant": {
                "asked": False,
                "sentence": "no assistant over this surface: what one costs is "
                "said before its call, and a tool has no before. Run the command "
                "by hand to ask one",
                "command": with_model,
            },
        }
    )
