"""What the five tools of the first verbs change in the CLI's `--json`
before it leaves: the one rendering is `digline.wire`'s, and these are the
differences this surface declares. (ADR 0011 §1, §5, as noted 2026-11-06)

- **Paths relative to the root.** `record_status` says where the switch and
  the recordings are as the repository holds them, not where this machine
  keeps the repository, and so do its refusals, which open with the file.
- **Local indices for cases and answers.** `record_compare` names a case and
  an answer by its number in this answer, `case 1`, `answer 2`, and not by
  the digest the CLI prints. A digest of a text in a small space is the text:
  §5 withholds an artifact's digest for that reason, and an answer of a
  classifier is one word among few. The numbers say what the comparison is
  for, which answers are equal, and verify nothing outside the answer.
- **Under `--names project`, the names as tokens** (ADR 0054 §7): a check by
  `project_check_name`, a setup's key and a model by the configuration's
  kinds, with a key digline names itself in clear as a run's are, and the
  recorder's `redact` as a module's name. A cases file's path and the
  provider plugins installed are withheld: they are names of the repository
  and of this machine, and no kind holds them.
"""

from __future__ import annotations

from pathlib import Path, PurePath
from typing import Any, cast

from digline.core import NAMED_CONFIG_KEYS, Minter, project_check_name

__all__ = [
    "compare_answer",
    "listing_answer",
    "relative",
    "status_answer",
    "suggest_answer",
]


def relative(path: str, root: Path) -> str:
    """`path` as the repository holds it, where it is inside `root`."""
    try:
        return str(PurePath(path).relative_to(root))
    except ValueError:
        return path


def status_answer(
    document: dict[str, Any], *, root: Path, mint: Minter | None
) -> dict[str, Any]:
    """`recorder_status_json`, its two paths relative to the root, and under
    `project` the `redact` function as a module's name."""
    for tenant in cast(list[dict[str, Any]], document["tenants"]):
        switch = cast(dict[str, Any], tenant["switch"])
        recordings = cast(dict[str, Any], tenant["recordings"])
        switch["path"] = relative(str(switch["path"]), root)
        recordings["path"] = relative(str(recordings["path"]), root)
        # The refusals open with the switch file's path, as the recorder
        # names it: said from the repository too.
        for refusal in ("refusal", "production_refusal"):
            if isinstance(switch[refusal], str):
                switch[refusal] = str(switch[refusal]).replace(f"{root}/", "")
        if mint is not None and switch["redact"] is not None:
            switch["redact"] = mint("module_name", str(switch["redact"]))
    return document


def listing_answer(document: dict[str, Any], *, mint: Minter | None) -> dict[str, Any]:
    """`import_listing_json`, and under `project` the check as a token and the
    cases file withheld."""
    if mint is not None:
        declaration = cast(dict[str, Any], document["declaration"])
        if declaration["check"] is not None:
            declaration["check"] = project_check_name(str(declaration["check"]), mint)
        declaration["cases_file"] = None
    return document


def compare_answer(document: dict[str, Any], *, mint: Minter | None) -> dict[str, Any]:
    """`record_compare_json`, each case and each answer by its number in this
    answer, and under `project` a setup's keys and its models as tokens."""
    answers: dict[str, str] = {}
    for number, case in enumerate(cast(list[dict[str, Any]], document["cases"]), 1):
        case["id"] = f"case {number}"
        for setup in cast(list[dict[str, Any]], case["setups"]):
            if mint is not None:
                setup["models"] = [
                    mint("target_config_value", str(model))
                    for model in cast(list[object], setup["models"])
                ]
            for answer in cast(list[dict[str, Any]], setup["answers"]):
                digest = str(answer.pop("digest"))
                answers.setdefault(digest, f"answer {len(answers) + 1}")
                answer["answer"] = answers[digest]
    document["case"] = None
    keys = cast(dict[str, Any] | None, document["setup_keys"])
    if mint is not None and keys is not None:
        # As a run's configuration is projected: digline's own keys cross in
        # clear, and any other is a token. (ADR 0034 §17.2)
        for key in cast(list[dict[str, Any]], keys["keys"]):
            if key["key"] not in NAMED_CONFIG_KEYS:
                key["key"] = mint("target_config_key", str(key["key"]))
    return document


def suggest_answer(
    document: dict[str, Any], *, root: Path, mint: Minter | None
) -> dict[str, Any]:
    """`suggest_json`, the proposal's path relative to the root, and under
    `project` every check's name as a token, the cases file and the plugins
    installed withheld."""
    document["proposal"] = relative(str(document["proposal"]), root)
    if mint is None:
        return document
    judge = cast(dict[str, Any], document["judge"])
    if judge["check"]:
        judge["check"] = project_check_name(str(judge["check"]), mint)
    judge["plugins"] = []
    for check in cast(list[dict[str, Any]], document["checks"]):
        check["name"] = project_check_name(str(check["name"]), mint)
    document["already"] = [
        project_check_name(str(name), mint)
        for name in cast(list[object], document["already"])
    ]
    cast(dict[str, Any], document["counterexample"])["cases_file"] = None
    return document
