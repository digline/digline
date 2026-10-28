"""The command line, driven in a real subprocess against a real git repository.

In-process tests would not prove the two things this layer exists for: that the
clock and git are read *here* and nowhere else, and that a pipeline can act on
the exit code.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from tests._helpers import baseline_in, cli, run_key, suite_source, write_suite

from digline.cli import (
    EXIT_OK,
    EXIT_UNJUDGED,
    EXIT_USAGE,
    EXIT_WORSE,
    OUTPUT_VERSION,
    build_parser,
    exit_code,
    main,
)
from digline.core.run import SCHEMA_VERSION
from digline.report import Headline

ROOT = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------- #
# exit codes
# --------------------------------------------------------------------------- #


def head(*, worse: bool, unjudged: int) -> Headline:
    return Headline(
        worse=worse,
        unjudged=unjudged,
        suspended=0,
        config_changed=False,
        counts={},
        reasons_available=True,
        sentence="",
        # By the rule `headline()` follows: `unjudged` is a cause exactly when
        # the count is above zero. (ADR 0053)
        unjudged_causes=("unjudged",) if unjudged else (),
    )


def test_a_regression_outranks_an_unjudged_case() -> None:
    """Both need attention, but a regression is a statement about behaviour and
    an unjudged case is one about the harness. If the harness won, a real
    regression would hide behind a flaky provider."""
    assert exit_code(head(worse=True, unjudged=3)) == EXIT_WORSE
    assert exit_code(head(worse=True, unjudged=0)) == EXIT_WORSE
    assert exit_code(head(worse=False, unjudged=3)) == EXIT_UNJUDGED
    assert exit_code(head(worse=False, unjudged=0)) == EXIT_OK


def test_a_suspension_alone_never_fails() -> None:
    quiet = Headline(
        worse=False,
        unjudged=0,
        suspended=7,
        config_changed=True,
        counts={},
        reasons_available=True,
        sentence="",
        unjudged_causes=(),
    )
    assert exit_code(quiet) == EXIT_OK


def test_the_exit_code_reads_the_causes_and_not_the_flags() -> None:
    """`unjudged_causes` is what `exit_code` reads behind a regression; the
    flags beside it are derived from it in `headline()` and are not read. A
    headline built by hand with the two disagreeing shows which one is: from
    `headline()` they always agree, so nothing else can. (ADR 0053)"""
    flags_only = Headline(
        worse=False,
        unjudged=3,
        suspended=0,
        config_changed=False,
        counts={},
        reasons_available=True,
        sentence="",
        unjudged_causes=(),
        scale_lost=True,
        pinned_drifted=True,
        pinned_lost=True,
        nothing_judged=True,
    )
    assert exit_code(flags_only) == EXIT_OK
    tuple_only = replace(
        flags_only,
        unjudged=0,
        scale_lost=False,
        pinned_drifted=False,
        pinned_lost=False,
        nothing_judged=False,
        unjudged_causes=("pinned_drifted",),
    )
    assert exit_code(tuple_only) == EXIT_UNJUDGED
    assert exit_code(replace(tuple_only, worse=True)) == EXIT_WORSE


# --------------------------------------------------------------------------- #
# the cycle, through the process boundary
# --------------------------------------------------------------------------- #


def test_run_prints_a_key_that_promote_accepts(repo: Path) -> None:
    key = run_key(repo)
    assert key and ":" not in key

    promoted = cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )
    assert promoted.returncode == EXIT_OK, promoted.stderr
    assert (repo / ".digline" / "acme-bank" / "baselines" / "qa.json").is_file()

    compared = cli(
        repo, "compare", "--suite", "suite_qa.py", "--run", key, "--locale", "en"
    )
    assert compared.returncode == EXIT_OK
    assert "Nothing got worse" in compared.stdout


def test_every_command_that_acts_on_a_perimeter_names_it(repo: Path) -> None:
    """Friction 64. A suite copied between customers keeps the other customer's
    `tenant=` line, and `run`, `compare`, `list` and `promote` then acted on the
    wrong perimeter with exit 0 while **not one line of terminal output named a
    tenant** — the only place it appeared was the HTML report's header.

    Checked on the line each command is actually read by, not on a line of its
    own: a tenant on a line nobody reads is what the header already was. And by
    the whole line, so a tenant that turned up somewhere incidental — the way
    `register`'s commit path carries it as a path segment — does not pass for a
    statement of it."""
    ran = cli(repo, "run", "--suite", "suite_qa.py")
    assert ran.returncode == EXIT_OK, ran.stderr
    key = ran.stdout.strip()
    # stdout stays the key alone — `KEY=$(digline run …)` is the idiom — so the
    # tenant leads the announcement read before anything is paid for.
    assert "\n" not in key and "tenant" not in key
    announced = [ln for ln in ran.stderr.splitlines() if "call" in ln][0]
    assert announced.startswith("digline: tenant 'acme-bank' · ")

    promoted = cli(
        repo, "promote", "--replacing", "none", "--suite", "suite_qa.py", "--run", key
    )
    assert promoted.returncode == EXIT_OK, promoted.stderr
    assert promoted.stdout == f"tenant 'acme-bank' · qa baseline set to {key}\n"

    compared = cli(repo, "compare", "--suite", "suite_qa.py", "--run", key)
    assert compared.stdout.splitlines()[1] == (
        f"tenant 'acme-bank', against baseline {key}"
    )

    listed = cli(repo, "list", "--suite", "suite_qa.py")
    assert listed.stdout.splitlines()[0] == "tenant 'acme-bank' · qa"


def test_compare_exits_worse_when_the_suite_regresses(repo: Path) -> None:
    baseline_key = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        baseline_key,
    )

    write_suite(repo, fr_score="0.2")  # the judge now scores one case badly
    key = run_key(repo)
    compared = cli(
        repo, "compare", "--suite", "suite_qa.py", "--run", key, "--locale", "it"
    )
    assert compared.returncode == EXIT_WORSE
    assert "peggiorato" in compared.stdout


def test_compare_exits_unjudged_when_a_case_cannot_run(repo: Path) -> None:
    baseline_key = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        baseline_key,
    )

    write_suite(repo, extra=', Case(id="flaky")')
    key = run_key(repo)
    compared = cli(
        repo, "compare", "--suite", "suite_qa.py", "--run", key, "--locale", "en"
    )
    assert compared.returncode == EXIT_UNJUDGED
    # With the denominator it is a count of: the suite grew to three cases.
    assert "2 of 3 cases judged, 1 could not be." in compared.stdout


def test_the_exit_code_field_is_the_process_exit_code(repo: Path) -> None:
    """The field and the number a shell sees are the same number.

    Two surfaces return this object — `compare --json` and the MCP `compare`
    tool — and only one of them can exit a process. If the field were computed
    anywhere but `exit_code()` the two could disagree, and the disagreement
    would show up as a pipeline that gated correctly and an agent that did not.
    So it is checked against the thing it claims to be, over all three outcomes.
    (ADR 0011 §4)
    """
    baseline_key = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        baseline_key,
    )

    def field_and_status(*, expected: int) -> None:
        key = run_key(repo)
        done = cli(
            repo,
            "compare",
            "--suite",
            "suite_qa.py",
            "--run",
            key,
            "--locale",
            "en",
            "--json",
        )
        assert done.returncode == expected, done.stdout
        assert json.loads(done.stdout)["exit_code"] == done.returncode

    field_and_status(expected=EXIT_OK)
    write_suite(repo, fr_score="0.2")  # the judge now scores one case badly
    field_and_status(expected=EXIT_WORSE)
    write_suite(repo, extra=', Case(id="flaky")')
    field_and_status(expected=EXIT_UNJUDGED)


def test_the_diff_json_has_no_exit_code(repo: Path) -> None:
    """`diff` gains nothing of the kind, and the absence is the same point as
    the absent `worse`: a verdict exists only against an approved reference, and
    neither side of a diff was approved by anybody. (ADR 0008 §1, ADR 0011 §4)"""
    first = run_key(repo)
    second = run_key(repo)
    done = cli(
        repo,
        "diff",
        "--suite",
        "suite_qa.py",
        first,
        second,
        "--locale",
        "en",
        "--json",
        "full",
    )
    assert done.returncode == EXIT_OK
    payload = json.dumps(json.loads(done.stdout))
    assert "exit_code" not in payload
    assert "worse" not in payload


def test_compare_json_emits_the_headline_not_the_document(repo: Path) -> None:
    key = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )
    done = cli(
        repo,
        "compare",
        "--suite",
        "suite_qa.py",
        "--run",
        key,
        "--locale",
        "en",
        "--json",
    )
    payload = json.loads(done.stdout)
    assert set(payload) == COMPARE_KEYS
    assert payload["output_version"] == OUTPUT_VERSION
    assert "<html" not in done.stdout


#: The whole of what `digline compare --json` prints, under `OUTPUT_VERSION` 2.
#:
#: A golden set, compared by equality, and the point is that it is tedious to
#: change: a key the command starts to print fails here until it is added, so an
#: addition is deliberate and seen in review, not forbidden. An added key needs
#: no bump, because a consumer that ignores it parses what it parsed before. A
#: renamed or removed key, a value of another type, or a number whose meaning
#: changes is a bump: the rule is in `digline.wire.contract`, above `_BASE`.
#: `SCHEMA_VERSION` does not cover it — that one is about documents on disk.
#:
#: *Corrected 2026-10-12.* Until then this comment said that adding a key here
#: without a bump was the mistake it guarded, while the set already held keys
#: added without one, each recorded in `contract.py` as needing none.
COMPARE_KEYS = {
    "output_version",
    "worse",
    "unjudged",
    "suspended",
    "config_changed",
    # Joined the contract with ADR 0003: same rules, different prompt is a thing
    # a pipeline has to be able to ask about.
    "artifacts_changed",
    # Joined with ADR 0029, same rule again. `pinned_drifted` is a **new cause of
    # exit 2**, so a consumer that only reads `exit_code` already sees it and one
    # that wants to know which of the three causes fired now can.
    "pinned_drifted",
    # And this one is on the contract precisely *because* it moves no number: a
    # pin nobody could check is not a failure and must not be silent, so the
    # count has to reach a pipeline that wants to make its own policy out of it.
    # A consumer that ignores it reads exactly the numbers it read before.
    "pinned_unchecked",
    # Joined with ADR 0049 §4, same rule: the fourth cause of exit 2, a run in
    # which none of the cases that count was judged. A consumer that reads only
    # `exit_code` already sees it; this says which cause fired.
    "nothing_judged",
    # Joined with ADR 0051, same rule: two counts that move no number and a
    # fifth cause of exit 2. A consumer that reads only `exit_code` already
    # sees the third; the counts say which half of it is present.
    "pinned_unreferenced",
    "pinned_withdrawn",
    "pinned_lost",
    # Joined with ADR 0053, same rule: the causes of exit 2 that hold, by the
    # names of the keys above. A consumer reading `exit_code` sees no new
    # number; one reading this sees a drift beside a regression that exits 1.
    "unjudged_causes",
    # Joined with #642, same rule: a sixth cause of exit 2, the checks the
    # comparison could not pair. A consumer reading `exit_code` already sees
    # it; this says how many.
    "unpaired",
    # A count from the judged run, or null where it records none. (ADR 0052)
    "modules_unchecked",
    # Joined with ADR 0005, and deliberately without a bump: the rule is that
    # *added* keys leave a consumer working, and these two answer a question
    # nothing else on this list can — same rules, same prompt, different model.
    "target_config_changed",
    "judge_config_changed",
    # Joined with ADR 0006, same rule: a consumer that never looks at it is
    # unaffected, and one that wants to tell "nothing moved" from "what moved
    # was noise" has the count without parsing a sentence.
    "within_noise",
    # Joined with ADR 0018 §8, same rule a fifth time. It answers a question
    # none of the others can — not "did anything move" but "how firmly did the
    # ones that did not move stay put" — and it changes no exit code, so a
    # consumer that ignores it reads exactly the numbers it read before.
    "on_the_line",
    # Joined with ADR 0011 §4, same rule. It is the number AGENTS.md §6 calls
    # the contract, and it is here because the MCP server returns this same
    # object and has no process to exit — a caller left to derive it from
    # `worse` and `unjudged` would have to know that a regression outranks an
    # unjudged case, which is precisely what `exit_code()` exists to hold in one
    # place. `test_the_exit_code_field_is_the_process_exit_code` pins the two
    # together.
    "exit_code",
    # Joined with ADR 0031 §2, same rule, and changes no exit code. The key of
    # the reference this comparison was made against, which is what
    # `promote --replacing` has to name: a consumer that promotes after a green
    # comparison has it without reading `list`.
    "baseline_key",
    # Joined with ADR 0015 §8, same rule again. A pipeline that never looks at
    # it is unaffected; one that does learns the thing no other key on this list
    # can say — that the answers under these numbers were replayed from a
    # stored run rather than measured, so what moved is the judging.
    "rejudged",
    # Joined with ADR 0016 §8, and it is the first addition that can change the
    # **exit code** of a run: a canary that moved exits 1 with no regression
    # anywhere. Only for a suite that declares a canary, which none did before
    # this release, so no existing consumer sees a number it did not see before.
    "canary_moved",
    # Joined with ADR 0020 §3, row 7, same rule a sixth time. The endpoint
    # returned the requested id as the model that answered, so the identity the
    # record seems to confirm is not identified. It moves no exit code, and it is
    # never true behind a named endpoint, where the answering model is withheld.
    "target_echoed",
    # Joined with ADR 0024 §4.7, the same rule a seventh time, and the second
    # addition that can change the exit code: a calibration case outside its
    # band exits 2. Only for a suite that declares one, which none could before
    # this release.
    "scale_lost",
    # Joined by the delta-pass over 0.15.1, the same rule an eighth time, and
    # the first addition that makes a number *already on this list* smaller: a
    # delta whose two sides counted different cases is in none of `counts` now,
    # so `improved` or `regressed` is one lower in the run where that happened,
    # and `worse` is false where the arithmetic pointed down. The key set is
    # what this golden set guards and it is untouched; the semantic change is
    # written in `wire/contract.py`, beside the version it did not move.
    "denominator_moved",
    # ADR 0027 §7: how many checks the run recorded as gaps between what the
    # suite asked and what came back. An added key, the same rule again; it
    # moves no exit code of its own, because every gap is already an errored
    # verdict and exits 2 as one.
    "unreconciled",
    # F-10, the second 0.17.0 delta-pass: the same count for the **reference**.
    # An added key, the same rule again, and this one moves no exit code at all
    # — the run being compared may itself reconcile perfectly, and failing it
    # for the state of a document promoted weeks ago would fail the wrong run.
    # A pipeline that wants to refuse a comparison standing on a reference
    # nobody can state now has a number to refuse on.
    "reference_unreconciled",
    # ADR 0027 §6, amended 2026-09-28: how many checks the run refused because
    # their verdict was named otherwise than their assertion. An added key, the
    # same rule again; it moves no exit code of its own, because each refusal is
    # already an errored verdict and exits 2 as one.
    "misnamed",
    "counts",
    "reasons_available",
    "sentence",
    # #433: what resolving the run stepped over, the line `--run latest` prints
    # on stderr, and empty for a key typed by hand. An added key, the same rule
    # again; it moves no exit code, and it is here because MCP's `compare`
    # returns this object and has no stderr.
    "note",
    # #448: the run held against `baseline_key`, derived from the run that was
    # read, so `--run latest` says which run it picked. An added key, the same
    # rule again, and it moves no exit code.
    "run_key",
}


def test_the_json_output_declares_its_own_contract_version(repo: Path) -> None:
    """Storage and output are two contracts with two lifetimes, so they carry
    two numbers. A run file must stay *readable* years later, which is why
    `SCHEMA_VERSION` has migrations; a pipeline only needs to know what it is
    being handed today."""
    key = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )

    compared = json.loads(
        cli(repo, "compare", "--suite", "suite_qa.py", "--run", key, "--json").stdout
    )
    ran = json.loads(cli(repo, "run", "--suite", "suite_qa.py", "--json").stdout)
    assert compared["output_version"] == ran["output_version"] == OUTPUT_VERSION
    # The two numbers are independent, and nothing may quietly tie them.
    assert OUTPUT_VERSION != SCHEMA_VERSION


def test_json_full_adds_the_deltas_and_nothing_else(repo: Path) -> None:
    key = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )
    full = json.loads(
        cli(
            repo, "compare", "--suite", "suite_qa.py", "--run", key, "--json", "full"
        ).stdout
    )
    assert set(full) == COMPARE_KEYS | {
        "deltas",
        "target_config_deltas",
        "judge_config_deltas",
        # ADR 0028 §8: the rules that moved, beside the two configuration lists
        # and under `full` for their reason.
        "suite_deltas",
        # ADR 0024 §6.3: the shape reading's counts, beside the deltas they are
        # read from, under `full` only.
        "shape",
    }


def regressed_repo(repo: Path) -> str:
    """A promoted baseline, then a run where `capital-fr` scores badly."""
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        run_key(repo),
    )
    write_suite(repo, fr_score="0.2")
    return run_key(repo)


def test_compare_names_the_checks_that_got_worse(repo: Path) -> None:
    """ "1 check got worse" without saying which sends the reader to open an HTML
    file to learn a fact that fits on one line."""
    key = regressed_repo(repo)
    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode == EXIT_WORSE

    lines = [ln for ln in done.stdout.splitlines() if " · " in ln]
    assert len(lines) == 1
    case, assertion, detail = lines[0].split(" · ")
    assert case == "capital-fr"
    assert assertion == "llm_rubric"
    assert "1.000000" in detail and "0.200000" in detail


def test_the_terminal_detail_is_the_one_in_the_report(repo: Path) -> None:
    """End to end through two commands: if the two ever stop sharing the
    string, this says so."""
    key = regressed_repo(repo)
    terminal = cli(
        repo, "compare", "--suite", "suite_qa.py", "--run", key, "--locale", "it"
    ).stdout
    document = cli(
        repo, "report", "--suite", "suite_qa.py", "--run", key, "--locale", "it"
    ).stdout

    detail = next(ln for ln in terminal.splitlines() if " · " in ln).split(" · ")[2]
    assert detail in document


def test_a_clean_comparison_prints_only_the_sentence(repo: Path) -> None:
    key = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )
    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode == EXIT_OK
    assert " · " not in done.stdout


def test_compare_json_full_adds_the_deltas(repo: Path) -> None:
    key = regressed_repo(repo)

    plain = json.loads(
        cli(repo, "compare", "--suite", "suite_qa.py", "--run", key, "--json").stdout
    )
    assert "deltas" not in plain  # unchanged, as promised

    full = json.loads(
        cli(
            repo, "compare", "--suite", "suite_qa.py", "--run", key, "--json", "full"
        ).stdout
    )
    assert full["sentence"] == plain["sentence"]
    worse = [d for d in full["deltas"] if d["outcome"] == "regressed"]
    assert len(worse) == 1
    assert worse[0]["case_id"] == "capital-fr"
    assert worse[0]["before"] == 1.0
    assert worse[0]["after"] == 0.2
    assert worse[0]["scope"] == "case"


def test_every_delta_says_what_it_is_about(repo: Path) -> None:
    """A run-scoped delta carries `case_id == ""`, and without `scope` the only
    way to tell an aggregate from a case was to read that empty string as a
    convention — which is also what a malformed `case_id` would look like."""
    key = regressed_repo(repo)
    full = json.loads(
        cli(
            repo, "compare", "--suite", "suite_qa.py", "--run", key, "--json", "full"
        ).stdout
    )
    assert all(d["scope"] in ("case", "run") for d in full["deltas"])
    assert all(d["case_id"] != "" for d in full["deltas"] if d["scope"] == "case")


def test_json_full_does_not_carry_the_judge_words(repo: Path) -> None:
    """A reason is payload, and the stdout of a CI job is where logs go and
    stay. A pipeline that needs it can read the run file from inside the
    perimeter."""
    key = regressed_repo(repo)
    out = cli(
        repo, "compare", "--suite", "suite_qa.py", "--run", key, "--json", "full"
    ).stdout
    assert "judged:" not in out
    assert all("reason" not in d for d in json.loads(out)["deltas"])


def test_report_writes_a_document_and_keeps_the_exit_code(repo: Path) -> None:
    baseline_key = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        baseline_key,
    )
    write_suite(repo, fr_score="0.2")
    key = run_key(repo)

    out = repo / "report.html"
    done = cli(
        repo,
        "report",
        "--suite",
        "suite_qa.py",
        "--run",
        key,
        "--locale",
        "it",
        "--out",
        str(out),
    )
    assert done.returncode == EXIT_WORSE
    document = out.read_text(encoding="utf-8")
    assert document.startswith("<!DOCTYPE html>")
    assert "È peggiorato? Sì" in document


def test_an_out_that_cannot_be_written_is_named_as_the_out(repo: Path) -> None:
    """#672: `--out` into a directory that does not exist printed
    *"FileNotFoundError: [Errno 2] …"*, a class name and a crash's shape. It is
    a verdict about an argument, and says so: the option, the path, the
    errno's text, exit 64, nothing on standard output."""
    key = run_key(repo)
    missing = repo / "missing" / "dir" / "r.html"
    done = cli(
        repo,
        "report",
        "--suite",
        "suite_qa.py",
        "--run",
        key,
        "--locale",
        "en",
        "--out",
        str(missing),
    )
    assert done.returncode == 64
    assert done.stdout == ""
    assert f"--out {missing}" in done.stderr
    assert "No such file or directory" in done.stderr
    assert "FileNotFoundError" not in done.stderr


def test_report_redacted_removes_the_judge_words(repo: Path) -> None:
    key = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )

    complete = cli(
        repo, "report", "--suite", "suite_qa.py", "--run", key, "--locale", "en"
    ).stdout
    hidden = cli(
        repo,
        "report",
        "--suite",
        "suite_qa.py",
        "--run",
        key,
        "--locale",
        "en",
        "--redacted",
    ).stdout

    assert "judged:" in complete
    assert "judged:" not in hidden
    assert "produced from redacted data" in hidden


# --------------------------------------------------------------------------- #
# list
# --------------------------------------------------------------------------- #


def test_list_shows_runs_newest_first_and_marks_the_baseline(repo: Path) -> None:
    """Without this a developer coming back the next day had no way to name
    yesterday's run: `--run KEY` is mandatory everywhere and only `run` prints
    a key."""
    first = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        first,
    )
    write_suite(repo, fr_score="0.5")
    second = run_key(repo)
    assert second != first

    done = cli(repo, "list", "--suite", "suite_qa.py")
    assert done.returncode == EXIT_OK, done.stderr
    body = [line for line in done.stdout.splitlines() if line.strip()]

    # The perimeter first, above the table: a listing that named no tenant is
    # how a copied suite's runs read as one history (friction 64).
    title, header, rows = body[0], body[1], body[2:4]
    assert title == "tenant 'acme-bank' · qa"
    assert "KEY" in header and "CASES" in header
    # Newest first. Checked by membership, not by column index: a marked row
    # starts with "*" and an unmarked one with a space, so `split()` shifts.
    assert second in rows[0] and first not in rows[0]
    assert first in rows[1] and second not in rows[1]
    # The promoted one, and only it, is marked.
    assert rows[1].startswith("*")
    assert not rows[0].startswith("*")
    assert "* = current baseline" in done.stdout


def test_list_reports_the_recorded_facts(repo: Path) -> None:
    key = run_key(repo)
    done = cli(repo, "list", "--suite", "suite_qa.py")
    row = next(line for line in done.stdout.splitlines() if key in line)
    assert "staging" in row  # environment
    assert row.rstrip().endswith("2")  # two cases
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert sha[:7] in row


def test_list_marks_nothing_when_there_is_no_baseline(repo: Path) -> None:
    run_key(repo)
    done = cli(repo, "list", "--suite", "suite_qa.py")
    assert "* = current baseline" not in done.stdout
    # Nor the other marker: a store with no replay in it says nothing about
    # replays, the same way it says nothing about a baseline it does not have.
    assert "~ = rejudged" not in done.stdout


def test_list_marks_a_rejudged_run_rather_than_showing_it_as_a_measurement(
    repo: Path,
) -> None:
    """A replay used to be indistinguishable from a real run in this listing.

    `rejudge` writes a run like any other and `list` printed it like any other:
    same columns, a fresh key at the top because it is the newest thing in the
    store, and nothing saying the answers were replayed. Only `rejudged_from`
    inside the document said so, three commands away. That is a listing showing
    something as what it is not, on the surface somebody reads first — and
    `--run latest` resolves to exactly that row.
    """
    source = repo / "suite_qa.py"
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            'disclosure=Disclosure(run_metadata=frozenset({"model"})),',
            'disclosure=Disclosure(run_metadata=frozenset({"model"})),\n'
            "    record_responses=True,",
        ),
        encoding="utf-8",
    )
    measured = run_key(repo)
    rejudged = cli(
        repo, "rejudge", "--suite", "suite_qa.py", "--run", measured
    ).stdout.strip()
    assert rejudged and rejudged != measured

    done = cli(repo, "list", "--suite", "suite_qa.py")
    assert done.returncode == EXIT_OK, done.stderr
    rows = done.stdout.splitlines()
    replay_row = next(line for line in rows if rejudged in line)
    measured_row = next(line for line in rows if measured in line)

    assert replay_row.startswith("~"), (
        "the rejudged run is listed as an ordinary run: this row is a replay of "
        f"{measured} and the listing does not say so"
    )
    assert not measured_row.startswith("~")
    assert "~ = rejudged" in done.stdout
    # The marker rides the column the baseline already uses, so the row is no
    # wider than it was. Guarded here because widening it is how the marker
    # would stop being seen.
    assert len(replay_row.rstrip()) == len(measured_row.rstrip())


def test_list_on_an_empty_store_says_so(repo: Path) -> None:
    done = cli(repo, "list", "--suite", "suite_qa.py")
    assert done.returncode == EXIT_OK
    assert "no runs for suite 'qa'" in done.stdout


def test_list_needs_no_locale(repo: Path) -> None:
    """Terminal output for the developer, not a document for a recipient."""
    run_key(repo)
    assert cli(repo, "list", "--suite", "suite_qa.py").returncode == EXIT_OK


def test_list_shows_a_dirty_commit_as_such(repo: Path) -> None:
    (repo / "scratch.txt").write_text("uncommitted", encoding="utf-8")
    key = run_key(repo)
    done = cli(repo, "list", "--suite", "suite_qa.py")
    row = next(line for line in done.stdout.splitlines() if key in line)
    assert "-dirty" in row


# --------------------------------------------------------------------------- #
# git and the clock live here
# --------------------------------------------------------------------------- #


def test_a_clean_tree_records_the_commit(repo: Path) -> None:
    key = run_key(repo)
    stored = json.loads(
        (repo / ".digline" / "acme-bank" / "runs" / "qa" / f"{key}.json").read_text(
            encoding="utf-8"
        )
    )
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert stored["git_commit"] == sha
    assert not stored["git_commit"].endswith("-dirty")


def test_a_dirty_tree_is_marked_and_warned_about_in_the_report(repo: Path) -> None:
    """Such a run cannot be reproduced from the repository, and a reader
    deciding whether to act on it must be told before the numbers."""
    (repo / "untracked_change.txt").write_text("uncommitted", encoding="utf-8")

    key = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )
    stored = json.loads(
        (repo / ".digline" / "acme-bank" / "runs" / "qa" / f"{key}.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["git_commit"].endswith("-dirty")

    document = cli(
        repo, "report", "--suite", "suite_qa.py", "--run", key, "--locale", "en"
    ).stdout
    assert "-dirty" in document
    assert "cannot be reproduced from the repository" in document


def test_outside_a_repository_there_is_no_commit_and_no_error(
    tmp_path: Path,
) -> None:
    """A run produced from a notebook or a container legitimately has none, and
    refusing to work there would break the tool where people try things first."""
    write_suite(tmp_path)
    key = run_key(tmp_path)
    stored = json.loads(
        (tmp_path / ".digline" / "acme-bank" / "runs" / "qa" / f"{key}.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["git_commit"] is None


def test_the_created_at_comes_from_the_clock(repo: Path) -> None:
    first = run_key(repo)
    stored = json.loads(
        (repo / ".digline" / "acme-bank" / "runs" / "qa" / f"{first}.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["created_at"].startswith("20")
    assert stored["created_at"].endswith("+00:00")


# --------------------------------------------------------------------------- #
# loading, and what the CLI refuses
# --------------------------------------------------------------------------- #


def test_a_missing_suite_attribute_names_what_is_missing(repo: Path) -> None:
    (repo / "empty.py").write_text("x = 1\n", encoding="utf-8")
    done = cli(repo, "run", "--suite", "empty.py")
    assert done.returncode == EXIT_USAGE
    assert "has no attribute 'suite'" in done.stderr
    assert "Module defines: x" in done.stderr


def test_a_missing_target_attribute_names_what_is_missing(repo: Path) -> None:
    source = suite_source()
    (repo / "no_target.py").write_text(
        source.replace("def target(case):", "def _hidden(case):"), encoding="utf-8"
    )
    done = cli(repo, "run", "--suite", "no_target.py")
    assert done.returncode == EXIT_USAGE
    assert "no attribute 'target'" in done.stderr


def test_an_explicit_attribute_after_a_colon_is_used(repo: Path) -> None:
    done = cli(repo, "run", "--suite", "suite_qa.py:suite")
    assert done.returncode == EXIT_OK, done.stderr


def test_a_nonexistent_file_says_so(repo: Path) -> None:
    done = cli(repo, "run", "--suite", "nowhere.py")
    assert done.returncode == EXIT_USAGE
    assert "no such file" in done.stderr


def test_tenant_and_env_verify_and_never_override(repo: Path) -> None:
    ok = cli(
        repo,
        "run",
        "--suite",
        "suite_qa.py",
        "--tenant",
        "acme-bank",
        "--env",
        "staging",
    )
    assert ok.returncode == EXIT_OK, ok.stderr

    wrong = cli(repo, "run", "--suite", "suite_qa.py", "--tenant", "globex")
    assert wrong.returncode == EXIT_USAGE
    assert "The suite decides" in wrong.stderr
    # And nothing was filed under the wrong perimeter.
    assert not (repo / ".digline" / "globex").exists()


def test_compare_does_not_demand_a_locale(repo: Path) -> None:
    """Terminal output for a developer, same category as `list`: English unless
    asked otherwise. The sentence matches the report's anyway, because both come
    from `headline()` — there is no need to make the user restate it."""
    key = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )

    plain = cli(repo, "compare", "--suite", "suite_qa.py", "--run", key)
    assert plain.returncode == EXIT_OK, plain.stderr
    assert "Nothing got worse" in plain.stdout

    italian = cli(
        repo, "compare", "--suite", "suite_qa.py", "--run", key, "--locale", "it"
    )
    assert "Nulla è peggiorato" in italian.stdout


def test_report_does_demand_a_locale(repo: Path) -> None:
    """A document has a recipient, and their language is not settled by
    omission."""
    key = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )
    done = cli(repo, "report", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode != EXIT_OK
    assert "--locale" in done.stderr


# --------------------------------------------------------------------------- #
# The first run, before there is anything to compare it with (friction 3)
# --------------------------------------------------------------------------- #


def test_report_renders_a_run_that_has_no_baseline(repo: Path) -> None:
    """The dead end this closes: `report` refused a run with no baseline and
    said "run it, look at the result, then promote" — while being the only way
    to look. A command that names looking as the prerequisite for looking is
    the friction, not the documentation."""
    key = run_key(repo)
    done = cli(repo, "report", "--suite", "suite_qa.py", "--run", key, "--locale", "en")
    assert done.returncode == EXIT_OK, done.stderr
    assert done.stdout.startswith("<!DOCTYPE html>")
    assert "No reference to compare against" in done.stdout


def test_a_run_with_no_baseline_is_never_reported_as_worse(repo: Path) -> None:
    """`EXIT_WORSE` is a relation, and there is nothing here to be worse than.

    The suite this runs is the one that scores badly on `capital-fr`, which
    against a baseline would exit 1. Without one it exits 0: a low score is not
    a regression, it is a measurement.
    """
    write_suite(repo, fr_score="0.2")
    key = run_key(repo)
    done = cli(repo, "report", "--suite", "suite_qa.py", "--run", key, "--locale", "en")
    assert done.returncode == EXIT_OK, done.stderr
    assert done.returncode != EXIT_WORSE


def test_a_case_that_could_not_be_judged_still_exits_two(repo: Path) -> None:
    """The half of the contract that survives without a reference: a case the
    suite could not judge is a fact about the harness, and a document that
    reports one must not exit as though everything went fine."""
    write_suite(repo, extra=', Case(id="flaky")')
    key = run_key(repo)
    done = cli(repo, "report", "--suite", "suite_qa.py", "--run", key, "--locale", "en")
    assert done.returncode == EXIT_UNJUDGED, done.stderr
    # Three verdicts on one case: the section counts checks and the
    # tally counts cases, and each says which.
    assert "What could not be judged (3)" in done.stdout
    assert "<li>cases not judged <b>1</b></li>" in done.stdout


def test_the_document_becomes_comparative_once_a_baseline_exists(repo: Path) -> None:
    """No flag decides this. The same command answers the question it can
    answer, and says so when it cannot — the way `--redacted` is not what makes
    a report redacted."""
    key = run_key(repo)
    before = cli(
        repo, "report", "--suite", "suite_qa.py", "--run", key, "--locale", "en"
    ).stdout
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )
    after = cli(
        repo, "report", "--suite", "suite_qa.py", "--run", key, "--locale", "en"
    ).stdout

    assert "No reference to compare against" in before
    assert "Did it get worse?" not in before
    assert "No reference to compare against" not in after
    assert "Did it get worse?" in after


def test_compare_still_refuses_without_a_baseline(repo: Path) -> None:
    """A comparison needs a reference; a document does not. `report` stopped
    refusing and `compare` did not, which is the whole distinction."""
    key = run_key(repo)
    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode != EXIT_OK
    assert "has no baseline" in done.stderr


def test_a_baseless_report_can_still_be_redacted(repo: Path) -> None:
    key = run_key(repo)
    done = cli(
        repo,
        "report",
        "--suite",
        "suite_qa.py",
        "--run",
        key,
        "--locale",
        "en",
        "--redacted",
    )
    assert done.returncode == EXIT_OK, done.stderr
    assert "judged: " not in done.stdout


# --------------------------------------------------------------------------- #
# --run latest
# --------------------------------------------------------------------------- #


def test_latest_resolves_to_the_most_recent_run(repo: Path) -> None:
    """The friction of minute three: copying by hand the key `run` just printed."""
    first = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        first,
    )
    write_suite(repo, fr_score="0.2")
    second = run_key(repo)
    assert second != first

    compared = cli(repo, "compare", "--suite", "suite_qa.py", "--run", "latest")
    assert compared.returncode == EXIT_WORSE  # the second run is the worse one
    assert "1 check got worse" in compared.stdout


def test_latest_works_for_promote_and_reports_the_real_key(repo: Path) -> None:
    key = run_key(repo)
    done = cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        "latest",
    )
    assert done.returncode == EXIT_OK, done.stderr
    # Never the literal "latest": what was promoted must be nameable afterwards.
    assert key in done.stdout
    assert "latest" not in done.stdout


def test_latest_works_for_report(repo: Path) -> None:
    key = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )
    done = cli(
        repo, "report", "--suite", "suite_qa.py", "--run", "latest", "--locale", "en"
    )
    assert done.returncode == EXIT_OK, done.stderr
    assert done.stdout.startswith("<!DOCTYPE html>")


def test_latest_on_an_empty_store_says_so(repo: Path) -> None:
    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", "latest")
    assert done.returncode == EXIT_USAGE
    assert "no runs stored" in done.stderr
    assert "Run it first" in done.stderr


def test_run_is_still_mandatory(repo: Path) -> None:
    """`latest` is a value the caller types, not a default that guesses."""
    run_key(repo)
    done = cli(repo, "compare", "--suite", "suite_qa.py")
    assert done.returncode != EXIT_OK
    assert "--run" in done.stderr


# --------------------------------------------------------------------------- #
# A suite imports the application it evaluates
# --------------------------------------------------------------------------- #


def test_a_suite_can_import_a_module_beside_it(tmp_path: Path) -> None:
    """A suite imports the application under test — that is what a suite *is*.
    Without its directory on the path, the first real suite fails on its first
    line with ModuleNotFoundError and the tool looks broken because it is."""
    (tmp_path / "brief.py").write_text(
        "def judge_score(case_id):\n    return 0.9\n", encoding="utf-8"
    )
    (tmp_path / "suite_app.py").write_text(
        "from brief import judge_score\n"
        "from digline.core import Contains, JudgeReply, LlmRubric\n"
        "from digline.run import Case, Response, Suite\n"
        "\n"
        "suite = Suite(\n"
        "    tenant='acme', environment='dev', name='qa',\n"
        "    assertions=[\n"
        "        Contains(needle='Rome'),\n"
        "        LlmRubric(\n"
        "            rubric='ok?',\n"
        "            judge=lambda p: JudgeReply(score=judge_score('x'), reason='r'),\n"
        "            threshold=0.7,\n"
        "            tolerance=0.05,\n"
        "        ),\n"
        "    ],\n"
        "    cases=[Case(id='one')],\n"
        ")\n"
        "\n"
        "def target(case):\n"
        "    return Response(output='Rome', cost_usd=0.01)\n",
        encoding="utf-8",
    )

    done = cli(tmp_path, "run", "--suite", "suite_app.py")
    assert done.returncode == EXIT_OK, done.stderr
    assert done.stdout.strip()


def test_a_suite_whose_import_is_missing_is_a_usage_error(tmp_path: Path) -> None:
    """A missing import names the module and exits as a refusal, as the dotted
    form always has — not as a traceback. Under `uvx` it is the first thing a
    suite that imports a plugin meets."""
    (tmp_path / "suite_plugin.py").write_text(
        "import digline_plugin_that_is_not_installed\n", encoding="utf-8"
    )
    done = cli(tmp_path, "run", "--suite", "suite_plugin.py")
    assert done.returncode == EXIT_USAGE, done.stderr
    assert "digline_plugin_that_is_not_installed" in done.stderr
    assert "Traceback" not in done.stderr, done.stderr


APP_SUITE = """\
import brief
from digline.core import JudgeReply, LlmRubric
from digline.run import Case, Response, Suite

suite = Suite(
    tenant="acme", environment="dev", name="qa",
    assertions=[
        LlmRubric(
            rubric="ok?",
            judge=lambda p: JudgeReply(score=brief.SCORE, reason="r"),
            threshold=0.7,
            tolerance=0.05,
        )
    ],
    cases=[Case(id="one")],
)


def target(case):
    return Response(output="Rome", cost_usd=0.01)
"""


def test_the_application_beside_the_suite_is_never_read_from_stale_bytecode(
    repo: Path,
) -> None:
    """The defect this finder exists for, reproduced exactly.

    `brief.py` is edited to the same length, and its mtime is forced back so the
    pre-existing `.pyc` looks fresh — the same condition an edit within one
    second produces, made deterministic. Without the source-only finder the run
    scores 0.95 again and the comparison reports that nothing got worse, which
    is the only kind of defect that can hide a regression.
    """
    brief = repo / "brief.py"
    brief.write_text("SCORE = 0.95\n", encoding="utf-8")
    (repo / "suite_app.py").write_text(APP_SUITE, encoding="utf-8")

    # Someone already ran the application the ordinary way, so a cache exists.
    subprocess.run(
        [sys.executable, "-c", "import brief"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    assert (repo / "__pycache__").is_dir()
    stamp = brief.stat().st_mtime

    first = cli(repo, "run", "--suite", "suite_app.py")
    assert first.returncode == EXIT_OK, first.stderr
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_app.py",
        "--run",
        "latest",
    )

    # Same length, and the timestamp put back: to Python's freshness check
    # (mtime, size) the stale cache is indistinguishable from a current one.
    brief.write_text("SCORE = 0.20\n", encoding="utf-8")
    os.utime(brief, (stamp, stamp))

    second = cli(repo, "run", "--suite", "suite_app.py")
    assert second.returncode == EXIT_OK, second.stderr
    compared = cli(repo, "compare", "--suite", "suite_app.py", "--run", "latest")
    assert compared.returncode == EXIT_WORSE, compared.stdout
    assert "1 check got worse" in compared.stdout


def test_running_leaves_no_bytecode_behind(repo: Path) -> None:
    """New untracked files make a repository dirty, and digline would then
    report every run of its own making as unreproducible."""
    (repo / "brief.py").write_text("SCORE = 0.95\n", encoding="utf-8")
    (repo / "suite_app.py").write_text(APP_SUITE, encoding="utf-8")

    done = cli(repo, "run", "--suite", "suite_app.py")
    assert done.returncode == EXIT_OK, done.stderr
    assert not list(repo.rglob("__pycache__"))
    assert not list(repo.rglob("*.pyc"))


def test_only_the_suite_directory_gets_the_source_only_loader(
    tmp_path: Path,
) -> None:
    """Scoped on purpose: a loader for every module would slow every import to
    protect files that do not change during an evaluation."""
    from digline.host.loader import SourceOnlyLoader
    from digline.host.loader import load_suite as _load_suite

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "faraway.py").write_text("VALUE = 1\n", encoding="utf-8")

    beside = tmp_path / "beside"
    beside.mkdir()
    (beside / "nearby.py").write_text("VALUE = 2\n", encoding="utf-8")
    (beside / "suite_two.py").write_text(
        "import faraway\n"
        "import nearby\n"
        "from digline.core import Contains\n"
        "from digline.run import Case, Suite\n"
        "\n"
        "suite = Suite(\n"
        "    tenant='acme', environment='dev', name='qa',\n"
        "    assertions=[Contains(needle='x')],\n"
        "    cases=[Case(id='one')],\n"
        ")\n",
        encoding="utf-8",
    )

    before = list(sys.path)
    sys.path.insert(0, str(elsewhere))
    try:
        _load_suite(str(beside / "suite_two.py"))
        # Beside the suite: read from disk, always.
        assert isinstance(sys.modules["nearby"].__loader__, SourceOnlyLoader)
        # Anywhere else: the normal machinery, cache and all.
        assert not isinstance(sys.modules["faraway"].__loader__, SourceOnlyLoader)
    finally:
        sys.path[:] = before
        for name in ("nearby", "faraway"):
            sys.modules.pop(name, None)


def test_a_suite_given_as_a_module_path_leaves_sys_path_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a file path needs the treatment: `package.module:attr` is already
    importable, and widening the path for it would be reaching into the
    caller's environment for no reason."""
    from digline.host.loader import UsageError as _UsageError
    from digline.host.loader import load_suite as _load_suite

    before = list(sys.path)
    with pytest.raises(_UsageError):
        _load_suite("a_module_that_does_not_exist:suite")
    assert sys.path == before


def test_loading_twice_does_not_grow_sys_path(tmp_path: Path) -> None:
    """Several suites in one directory, or one loaded twice, must not make
    `sys.path` accumulate copies of the same entry."""
    from digline.host.loader import load_suite as _load_suite

    write_suite(tmp_path)
    path = str(tmp_path.resolve())
    # Measured as a delta, not against global uniqueness: pytest's own sys.path
    # already carries a duplicate, and asserting on it would be testing pytest.
    before = list(sys.path)
    try:
        for _ in range(3):
            _load_suite(str(tmp_path / "suite_qa.py"))

        assert sys.path.count(path) == 1
        assert len(sys.path) == len(before) + 1
        assert sys.path[0] == path  # inserted at the front, like `python file.py`
    finally:
        sys.path[:] = before


def test_comparing_without_a_baseline_explains_the_next_step(repo: Path) -> None:
    key = run_key(repo)
    done = cli(
        repo, "compare", "--suite", "suite_qa.py", "--run", key, "--locale", "en"
    )
    assert done.returncode == EXIT_USAGE
    assert "has no baseline" in done.stderr
    assert "promote" in done.stderr


def test_promoting_a_run_that_could_not_judge_is_refused(repo: Path) -> None:
    write_suite(repo, extra=', Case(id="flaky")')
    key = run_key(repo)
    done = cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )
    assert done.returncode == EXIT_USAGE
    assert "flaky" in done.stderr


# --------------------------------------------------------------------------- #
# --meta
# --------------------------------------------------------------------------- #


def test_meta_is_recorded_and_stays_payload_unless_disclosed(repo: Path) -> None:
    # The value carries a decimal point on purpose. An earlier version asserted
    # that the bare digits "1499" were absent from the report, and failed about
    # one run in a hundred: `created_at` carries microseconds, so a timestamp
    # like `…:01.149917+00:00` contains them. A flaky test is worse than no
    # test — it teaches the reader to rerun instead of to look.
    key = run_key(
        repo, "--meta", "model=claude-opus-5", "--meta", "account_balance=1499.55"
    )
    stored = json.loads(
        (repo / ".digline" / "acme-bank" / "runs" / "qa" / f"{key}.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["metadata"] == {
        "model": "claude-opus-5",
        "account_balance": "1499.55",
    }

    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )
    hidden = cli(
        repo,
        "report",
        "--suite",
        "suite_qa.py",
        "--run",
        key,
        "--locale",
        "en",
        "--redacted",
    ).stdout
    # The suite discloses `model` and nothing else.
    assert "account_balance" not in hidden
    assert "1499.55" not in hidden


def test_malformed_meta_is_refused(repo: Path) -> None:
    done = cli(repo, "run", "--suite", "suite_qa.py", "--meta", "nonsense")
    assert done.returncode == EXIT_USAGE
    assert "key=value" in done.stderr


# --------------------------------------------------------------------------- #
# Old schemas do not block a scan (friction 19)
# --------------------------------------------------------------------------- #


def runs_dir(root: Path) -> Path:
    return root / ".digline" / "acme-bank" / "runs" / "qa"


def downgrade(path: Path, to_version: int) -> None:
    """Turn a current document back into an older one, by removing exactly what
    that version added. The inverse of the migration, so the fixture and the
    code under test cannot both be wrong in the same direction."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if to_version <= 5:
        raw.pop("aggregate", None)
    if to_version <= 4:
        for case in raw["results"]:
            case.pop("suspended", None)
            case.pop("suspended_reason", None)
    raw["schema_version"] = to_version
    path.write_text(json.dumps(raw, sort_keys=True, indent=2), encoding="utf-8")


def mixed_store(repo: Path) -> tuple[str, Path, Path]:
    """Three runs at three schemas: one current, one at 5, one at 4."""
    current = run_key(repo)
    older = run_key(repo)
    oldest = run_key(repo)
    assert len({current, older, oldest}) == 3, "keys must differ to file three runs"

    older_path = runs_dir(repo) / f"{older}.json"
    oldest_path = runs_dir(repo) / f"{oldest}.json"
    downgrade(older_path, 5)
    downgrade(oldest_path, 4)
    return current, older_path, oldest_path


def test_list_survives_a_store_with_three_schemas(repo: Path) -> None:
    """The scan is a survey. It steps over what it cannot read, and says so."""
    current, _older, _oldest = mixed_store(repo)
    done = cli(repo, "list", "--suite", "suite_qa.py")

    assert done.returncode == EXIT_OK, done.stderr
    assert current in done.stdout
    assert "ignored:" in done.stdout
    assert "schema 5" in done.stdout and "schema 4" in done.stdout
    assert "migrate" in done.stdout


def test_latest_resolves_over_the_readable_runs(repo: Path) -> None:
    """This is the failure that started the entry: `--run latest` died on
    yesterday's files, refusing a run nobody had asked for."""
    current, _older, _oldest = mixed_store(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        current,
    )

    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", "latest")
    assert done.returncode == EXIT_OK, done.stderr
    assert "ignored:" in done.stderr  # noted, and kept off stdout


def test_naming_an_old_run_explicitly_is_still_refused(repo: Path) -> None:
    """A scan steps over what it does not recognise; an explicitly named key
    does not. The caller asked for that file and must be told."""
    _current, older_path, _oldest = mixed_store(repo)
    done = cli(repo, "compare", "--suite", "suite_qa.py", "--run", older_path.stem)
    assert done.returncode != EXIT_OK
    assert "schema_version 5 is not supported" in done.stderr


def test_migrate_brings_them_all_forward_and_the_scan_stops_ignoring(
    repo: Path,
) -> None:
    current, older_path, oldest_path = mixed_store(repo)

    before = cli(repo, "list", "--suite", "suite_qa.py")
    assert "ignored:" in before.stdout
    assert older_path.stem not in before.stdout  # skipped, so not a row

    migrated = cli(repo, "migrate", "--suite", "suite_qa.py")
    assert migrated.returncode == EXIT_OK, migrated.stderr
    assert "from schema 5" in migrated.stdout
    assert "from schema 4" in migrated.stdout
    assert "0 refused" in migrated.stdout

    after = cli(repo, "list", "--suite", "suite_qa.py")
    assert after.returncode == EXIT_OK
    assert "ignored:" not in after.stdout
    # All three readable now, so all three are rows — named, not counted.
    for key in (current, older_path.stem, oldest_path.stem):
        assert key in after.stdout


def test_a_dry_run_writes_nothing(repo: Path) -> None:
    _current, older_path, _oldest = mixed_store(repo)
    before = older_path.read_text(encoding="utf-8")

    done = cli(repo, "migrate", "--suite", "suite_qa.py", "--dry-run")
    assert done.returncode == EXIT_OK
    assert "would migrate" in done.stdout
    assert older_path.read_text(encoding="utf-8") == before


def test_a_non_additive_bump_is_refused_with_what_is_missing(repo: Path) -> None:
    """Schema 3 predates `environment`. There is no value to invent, and
    inventing one would place a run in a perimeter it may not belong to."""
    key = run_key(repo)
    path = runs_dir(repo) / f"{key}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("environment")
    raw["schema_version"] = 3
    path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")

    done = cli(repo, "migrate", "--suite", "suite_qa.py")
    assert done.returncode == EXIT_USAGE
    assert "environment" in done.stderr
    assert "1 refused" in done.stdout
    # Refused, therefore untouched: still readable as the old document it was.
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 3


def test_one_refusal_does_not_block_the_others(repo: Path) -> None:
    _current, older_path, oldest_path = mixed_store(repo)
    broken = runs_dir(repo) / "not-a-run.json"
    broken.write_text("{ this is not json", encoding="utf-8")

    done = cli(repo, "migrate", "--suite", "suite_qa.py")
    assert done.returncode == EXIT_USAGE
    assert "1 refused" in done.stdout
    for path in (older_path, oldest_path):
        # The current version, not a literal: every additive bump would
        # otherwise fail this test for a reason that has nothing to do with it.
        version = json.loads(path.read_text(encoding="utf-8"))["schema_version"]
        assert version == SCHEMA_VERSION


def test_the_baseline_is_migrated_too(repo: Path) -> None:
    """A baseline left behind would be unreadable the moment anything compared
    against it, which is every command that matters."""
    key = run_key(repo)
    cli(
        repo,
        "promote",
        "--replacing",
        baseline_in(repo),
        "--suite",
        "suite_qa.py",
        "--run",
        key,
    )
    baseline = repo / ".digline" / "acme-bank" / "baselines" / "qa.json"
    downgrade(baseline, 5)

    assert cli(repo, "compare", "--suite", "suite_qa.py", "--run", key).returncode != 0
    assert cli(repo, "migrate", "--suite", "suite_qa.py").returncode == EXIT_OK
    assert cli(repo, "compare", "--suite", "suite_qa.py", "--run", key).returncode == 0


def test_the_help_is_written_for_whoever_typed_it() -> None:
    """`--help` used to print the module's docstring.

    An architecture note — "the last layer, and the only one that touches the
    world" — rewrapped by argparse into a paragraph, and announcing four
    commands while listing seven. Whoever types `-h` wants to know what to type;
    whoever opens the file wants to know why the layer exists. Two audiences,
    two texts, and the reasons stay in the docstring and in `docs/adr/`.
    """
    # Through `sys.modules`: `digline.cli` re-exports the `main` *function*,
    # which shadows the `main` submodule on the package.
    import digline.cli.main  # noqa: F401  # pyright: ignore[reportUnusedImport]

    module = sys.modules["digline.cli.main"]
    helped = build_parser().format_help()

    assert "the last layer" not in helped
    assert "Four commands" not in helped
    assert module.__doc__ is not None
    # Not a paraphrase of the docstring either: nothing of it is reused.
    assert module.__doc__.strip().splitlines()[0] not in helped

    # What it does, and where to go next.
    assert "not got worse" in helped
    assert "digline <command> -h" in helped


def test_the_help_says_a_non_zero_exit_is_a_verdict() -> None:
    """The reader of `--help` is the one writing a wrapper, and a wrapper that
    reads `1` as a crash reads a verdict as an error. The meaning of each code
    is on the API page, given as a URL because the wheel ships no `docs/`.
    Joined on whitespace, since argparse rewraps the epilog to the terminal."""
    helped = " ".join(build_parser().format_help().split())

    assert "Exit codes 0, 1 and 2 are verdicts, and each means digline ran" in helped
    assert "https://digline.dev/product/api/" in helped


def test_the_help_and_the_package_summary_say_the_same_thing() -> None:
    """A PyPI page and a terminal describing one tool two ways is one of them
    being out of date, and no way to tell which."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    summary = pyproject["project"]["description"]
    assert "baseline" in summary and "repo" in summary
    assert "worse" in build_parser().format_help()


# --------------------------------------------------------------------------- #
# `digline explain` — the scope follows the store, and the exit code gates
# (ADR 0012 §1, §6)
# --------------------------------------------------------------------------- #


def test_explaining_without_a_baseline_reads_the_run_alone(repo: Path) -> None:
    """Not a refusal, and this is the pattern `report` settled in 0.6.0: making
    a reader name the scope means making them know, before they type, which of
    two documents they are entitled to."""
    key = run_key(repo)
    done = cli(repo, "explain", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode == EXIT_OK, done.stderr
    assert "What ran" in done.stdout
    assert "How it was set up" in done.stdout
    assert "What it found" in done.stdout
    # No comparative claim anywhere: there is nothing here to be worse than.
    assert "reference" not in done.stdout.lower()
    assert "got worse" not in done.stdout


def test_explaining_with_a_baseline_compares_without_being_asked(repo: Path) -> None:
    key = run_key(repo)
    assert (
        cli(
            repo,
            "promote",
            "--replacing",
            baseline_in(repo),
            "--suite",
            "suite_qa.py",
            "--run",
            key,
        ).returncode
        == 0
    )
    done = cli(repo, "explain", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode == EXIT_OK, done.stderr
    assert "What moved" in done.stdout
    assert "What differed underneath" in done.stdout


def test_explaining_a_run_that_got_worse_exits_one(repo: Path) -> None:
    """It gates like `report` and not like `diff`: with a baseline it holds a
    run against the same approved reference `compare` gates on, and a command
    that described a regression at length while exiting 0 would teach a reader
    that the exit code is decoration."""
    good = run_key(repo)
    assert (
        cli(
            repo,
            "promote",
            "--replacing",
            baseline_in(repo),
            "--suite",
            "suite_qa.py",
            "--run",
            good,
        ).returncode
        == 0
    )
    write_suite(repo, fr_score="0.1")
    worse = run_key(repo)
    done = cli(repo, "explain", "--suite", "suite_qa.py", "--run", worse)
    assert done.returncode == EXIT_WORSE, done.stdout
    assert "got worse" in done.stdout


def test_a_reading_with_no_reference_never_exits_worse(repo: Path) -> None:
    """The one test to read first if ADR 0012 §6 ever looks like it stopped
    being true. "Worse" is a relation, and a run read alone has nothing to be
    worse than — however badly it scored."""
    write_suite(repo, fr_score="0.1")
    key = run_key(repo)
    done = cli(repo, "explain", "--suite", "suite_qa.py", "--run", key)
    assert done.returncode != EXIT_WORSE
    assert done.returncode == EXIT_OK, done.stderr


def test_a_reading_emits_the_fact_list_and_no_prose(repo: Path) -> None:
    key = run_key(repo)
    done = cli(repo, "explain", "--suite", "suite_qa.py", "--run", key, "--json")
    assert done.returncode == EXIT_OK, done.stderr
    payload = json.loads(done.stdout)
    assert payload["output_version"] == OUTPUT_VERSION
    assert payload["reading"] == "run"
    assert payload["exit_code"] == EXIT_OK
    assert payload["facts"], "an empty list would make this test prove nothing"
    assert {fact["about"] for fact in payload["facts"]} <= {"check", "setting", "run"}
    # The prose is a render of this, so none of it travels: a consumer with the
    # typed facts in hand must never be invited to parse English.
    assert "sentence" not in payload
    assert "What ran" not in done.stdout


def test_the_reading_is_available_in_italian(repo: Path) -> None:
    key = run_key(repo)
    done = cli(
        repo, "explain", "--suite", "suite_qa.py", "--run", key, "--locale", "it"
    )
    assert done.returncode == EXIT_OK, done.stderr
    assert "Che cosa è stato eseguito" in done.stdout


def test_the_reading_takes_no_out_flag(repo: Path) -> None:
    """ADR 0012 §7, asserted as an absence. A reading written to a file has a
    recipient who did not choose English, and `--locale` would have to become
    mandatory as it is on `report`. The flag's absence is what keeps the
    document/terminal split honest rather than bent."""
    key = run_key(repo)
    done = cli(
        repo, "explain", "--suite", "suite_qa.py", "--run", key, "--out", "x.txt"
    )
    assert done.returncode != EXIT_OK
    assert "--out" in done.stderr


# --------------------------------------------------------------------------- #
# A command the parser refuses exits 64 (ADR 0008 §1)
# --------------------------------------------------------------------------- #
#
# ADR 0008 §1: "a bad flag, an unreadable run, a refused pair (§3) exit
# `EXIT_USAGE` (64)". The parser exited argparse's own 2 instead, which is
# `EXIT_UNJUDGED`: a pipeline that mistyped a flag read *the run could not be
# judged*. The tests below run every subcommand through each refusal the parser
# makes, in process, so what is measured is the parser each subcommand really
# has and not a reading of argparse's documentation.

#: For each subcommand, the arguments that parse: every required option with a
#: value it accepts. Nothing here is read, because the parser refuses before a
#: command runs, and these arguments only make sure the refusal under test is
#: the one that fires.
PARSES: dict[str, tuple[str, ...]] = {
    "run": ("--suite", "s.py"),
    "rejudge": ("--suite", "s.py", "--run", "k"),
    "compare": ("--suite", "s.py", "--run", "k"),
    "diff": ("--suite", "s.py", "k1", "k2"),
    "list": ("--suite", "s.py"),
    "migrate": ("--suite", "s.py"),
    "promote": ("--suite", "s.py", "--run", "k", "--replacing", "none"),
    "delete": ("--suite", "s.py", "--run", "k"),
    "register": ("--suite", "s.py", "--run", "k", "--disposition", "accepted"),
    "view": ("--suite", "s.py"),
    "explain": ("--suite", "s.py", "--run", "k"),
    "log": ("--suite", "s.py"),
    "report": ("--suite", "s.py", "--run", "k", "--locale", "en"),
}

#: The subcommands that take a choice, and the option that carries it. The
#: others have none, so a wrong choice cannot be asked of them.
CHOICE: dict[str, str] = {
    "compare": "--locale",
    "diff": "--locale",
    "register": "--disposition",
    "explain": "--locale",
    "log": "--locale",
    "report": "--locale",
}


def refused(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> tuple[str | int | None, str]:
    """The exit code `main` stopped with, and what it printed on stderr."""
    with pytest.raises(SystemExit) as stopped:
        main(argv)
    return stopped.value.code, capsys.readouterr().err


def test_the_table_names_every_subcommand_the_parser_has() -> None:
    """Read off the parser's own usage line, so a subcommand added later is
    refused here until it is in the table and goes through every case below."""
    usage = build_parser().format_usage()
    match = re.search(r"\{([a-z,]+)\}", usage)
    assert match is not None, usage
    assert set(match.group(1).split(",")) == set(PARSES)
    assert set(CHOICE) <= set(PARSES)


@pytest.mark.parametrize("command", sorted(PARSES))
def test_an_unknown_flag_exits_64(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, err = refused([command, *PARSES[command], "--no-such-flag"], capsys)
    assert "unrecognized arguments: --no-such-flag" in err, err
    assert code == EXIT_USAGE, (
        f"`digline {command}` with an unknown flag exited {code}: a pipeline that "
        "mistyped a flag would read it as a verdict (ADR 0008 §1)"
    )


@pytest.mark.parametrize("command", sorted(PARSES))
def test_a_missing_value_exits_64(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, err = refused([command, *PARSES[command], "--suite"], capsys)
    assert "argument --suite: expected one argument" in err, err
    assert code == EXIT_USAGE, (
        f"`digline {command} --suite` with no value exited {code}, not 64 (ADR 0008 §1)"
    )


@pytest.mark.parametrize("command", sorted(PARSES))
def test_a_missing_required_flag_exits_64(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    given = PARSES[command]
    # `--suite` and its value, found by name: a reordered table must not make
    # this drop some other option and still pass.
    at = given.index("--suite")
    without_suite = [*given[:at], *given[at + 2 :]]
    code, err = refused([command, *without_suite], capsys)
    assert "the following arguments are required: --suite" in err, err
    assert code == EXIT_USAGE, (
        f"`digline {command}` without --suite exited {code}, not 64 (ADR 0008 §1)"
    )


@pytest.mark.parametrize("command", sorted(CHOICE))
def test_an_invalid_choice_exits_64(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, err = refused([command, *PARSES[command], CHOICE[command], "xx"], capsys)
    assert f"argument {CHOICE[command]}: invalid choice: 'xx'" in err, err
    assert code == EXIT_USAGE, (
        f"`digline {command} {CHOICE[command]} xx` exited {code}, not 64 (ADR 0008 §1)"
    )


def test_an_unknown_subcommand_exits_64(capsys: pytest.CaptureFixture[str]) -> None:
    code, err = refused(["nosuchcommand"], capsys)
    assert "invalid choice: 'nosuchcommand'" in err, err
    assert code == EXIT_USAGE, f"an unknown subcommand exited {code}, not 64"


@pytest.mark.parametrize(
    "argv",
    [["--help"], ["--version"], ["compare", "--help"], ["report", "--help"]],
    ids=["root --help", "root --version", "compare --help", "report --help"],
)
def test_help_and_version_still_exit_0(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Why the refusal is `error()` and not every `SystemExit`: `--help` and
    `--version` end the process through the same exit, and they are answers,
    not refusals."""
    code, _err = refused(argv, capsys)
    assert code == 0, f"`digline {' '.join(argv)}` exited {code}, not 0"


# --------------------------------------------------------------------------- #
# An option given different values is refused (#567)
# --------------------------------------------------------------------------- #
#
# argparse keeps the last value of a repeated option and drops the others
# without a word: `compare --suite a.py --suite b.py` compared `b.py` alone and
# exited with its code. The rule: an option given different values is refused,
# and the same value given twice passes, because it drops nothing. The rule is
# the parser's, not a list of flags, so the options below are read off the
# parser itself, and an option added tomorrow is in them without anybody adding
# it here.

#: The class argparse gives `action="append"`, read off a parser rather than
#: named, because the name is private to argparse. An option declared with it
#: is repeatable by choice, and the rule leaves it alone.
APPEND = type(argparse.ArgumentParser().add_argument("--x", action="append"))


def subparsers() -> dict[str, argparse.ArgumentParser]:
    """Each subcommand's own parser, as `build_parser()` builds it."""
    root = build_parser()
    for action in root._actions:  # pyright: ignore[reportPrivateUsage]
        choices: object = action.choices
        if isinstance(choices, dict):
            return cast(dict[str, argparse.ArgumentParser], choices)
    raise AssertionError("the parser has no subcommands")


def value_options() -> list[tuple[str, argparse.Action]]:
    """Every option that takes a value, in every subcommand, except the ones
    declared repeatable. A flag (`nargs=0`) takes none."""
    return [
        (command, action)
        for command, parser in sorted(subparsers().items())
        for action in parser._actions  # pyright: ignore[reportPrivateUsage]
        if action.option_strings and action.nargs != 0 and type(action) is not APPEND
    ]


def two_values(action: argparse.Action) -> tuple[str, str]:
    """Two different values the option accepts."""
    if action.choices is not None:
        first, second, *_ = list(action.choices)
        return str(first), str(second)
    if action.type is int:
        return "1", "2"
    return "first.py", "second.py"


def stored(action: argparse.Action, value: str) -> object:
    """The value as the namespace holds it, after `type=`."""
    return int(value) if action.type is int else value


def without(given: tuple[str, ...], option: str) -> list[str]:
    """`given` with `option` and its value taken out, found by name."""
    if option not in given:
        return list(given)
    at = given.index(option)
    return [*given[:at], *given[at + 2 :]]


def parsed(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> tuple[str | int | None, str, argparse.Namespace | None]:
    """What the parser alone does with `argv`: the exit code it stopped with
    and its stderr, or `None` and the namespace it accepted. Nothing runs, so a
    command line the rule does not refuse is never executed here."""
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as stopped:
        return stopped.code, capsys.readouterr().err, None
    return None, capsys.readouterr().err, args


VALUE_OPTIONS = value_options()


def test_the_rule_reaches_options_in_every_subcommand() -> None:
    """The parametrization below is not empty, and it is not one subcommand: a
    reading of the parser that found nothing would pass every test it drives."""
    assert {command for command, _ in VALUE_OPTIONS} == set(PARSES)
    assert len(VALUE_OPTIONS) > len(PARSES)


@pytest.mark.parametrize(
    ("command", "action"),
    VALUE_OPTIONS,
    ids=[f"{command} {action.option_strings[-1]}" for command, action in VALUE_OPTIONS],
)
def test_an_option_given_two_values_is_refused_and_both_are_named(
    command: str, action: argparse.Action, capsys: pytest.CaptureFixture[str]
) -> None:
    option = action.option_strings[-1]
    first, second = two_values(action)
    argv = [command, *without(PARSES[command], option), option, first, option, second]
    code, err, args = parsed(argv, capsys)
    given = f"{option} {first!r} and {option} {second!r}"
    assert code == EXIT_USAGE, (
        f"`digline {command}` refused {given} with exit {code}, not 64"
        if args is None
        else f"`digline {command}` accepted {given} and kept "
        f"{getattr(args, action.dest)!r}: the other value was dropped without a "
        "word (#567)"
    )
    named = f"{stored(action, first)!r}, {stored(action, second)!r}"
    assert f"argument {option}: given different values ({named})" in err, err


def named_case(
    argv: list[str],
    option: str,
    values: tuple[str, str],
    dest: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One of the three cases #567 measured: refused with 64, both values named
    in the order given."""
    code, err, args = parsed(argv, capsys)
    given = f"{option} {values[0]!r} and {option} {values[1]!r}"
    assert code == EXIT_USAGE, (
        f"{given} were refused with exit {code}, not 64"
        if args is None
        else f"{given} were accepted and {getattr(args, dest)!r} was kept: the "
        "other was dropped without a word (#567)"
    )
    named = f"{values[0]!r}, {values[1]!r}"
    assert f"argument {option}: given different values ({named})" in err, err


def test_two_suites_on_compare_are_refused_by_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The case #567 measured: `billing` was compared, `support` was never
    loaded, and nothing said so."""
    values = ("both.py:support", "both.py:billing")
    argv = ["compare", "--suite", values[0], "--suite", values[1], "--run", "latest"]
    named_case(argv, "--suite", values, "suite", capsys)


def test_two_runs_on_compare_are_refused_by_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Measured beside #567: the last `--run` was the run compared."""
    values = ("k1", "k2")
    argv = ["compare", "--suite", "s.py", "--run", values[0], "--run", values[1]]
    named_case(argv, "--run", values, "run", capsys)


def test_two_targets_on_run_are_refused_by_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Measured beside #567: the last `--target` was the target called."""
    values = ("a.py:target", "b.py:target")
    argv = ["run", "--suite", "s.py", "--target", values[0], "--target", values[1]]
    named_case(argv, "--target", values, "target", capsys)


def test_an_option_that_stores_nothing_is_refused_when_declared() -> None:
    """`_Once` replaces `store`, and keeps the check `store` made: an option
    declared with `nargs=0` stores nothing, which is a flag declared wrong."""
    with pytest.raises(ValueError, match="cannot take zero of them"):
        build_parser().add_argument("--nothing", nargs=0)


def test_a_const_without_an_optional_value_is_refused_when_declared() -> None:
    """The other check `store` made: a `const` is what an option given with no
    value stores, so declaring one where the value is not optional is a
    declaration that cannot mean anything."""
    with pytest.raises(ValueError, match="so it needs `nargs='\\?'`"):
        build_parser().add_argument("--fixed", const="x")


def test_meta_stays_repeatable_and_keeps_every_value() -> None:
    """`--meta` is `append` by choice: each one is a different key, and the rule
    is about an option that takes one value."""
    args = build_parser().parse_args(
        ["run", "--suite", "s.py", "--meta", "a=1", "--meta", "b=2"]
    )
    assert args.meta == ["a=1", "b=2"]


def test_a_flag_given_twice_is_still_accepted() -> None:
    """A flag takes no value, so giving it twice drops nothing."""
    args = build_parser().parse_args(
        ["run", "--suite", "s.py", "--keep-errors", "--keep-errors"]
    )
    assert args.keep_errors is True


@pytest.mark.parametrize(
    ("command", "action"),
    VALUE_OPTIONS,
    ids=[f"{command} {action.option_strings[-1]}" for command, action in VALUE_OPTIONS],
)
def test_an_option_given_the_same_value_twice_is_accepted(
    command: str, action: argparse.Action, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same value twice drops nothing, so it passes, and the value reaches
    the reader as one value."""
    option = action.option_strings[-1]
    value, _ = two_values(action)
    argv = [command, *without(PARSES[command], option), option, value, option, value]
    code, err, args = parsed(argv, capsys)
    assert args is not None, (
        f"`digline {command}` refused {option} {value!r} given twice (exit {code}): "
        f"{err}"
    )
    assert getattr(args, action.dest) == stored(action, value)


def test_json_given_twice_without_a_value_is_accepted() -> None:
    """`--json` takes an optional value: given twice without one, both are its
    `const`, and nothing is dropped."""
    args = build_parser().parse_args(
        ["compare", "--suite", "s.py", "--run", "k", "--json", "--json"]
    )
    assert args.json == "headline"


def test_the_same_port_written_two_ways_is_one_value() -> None:
    """Compared as stored, after `type=int`: `80` and `080` are one port."""
    args = build_parser().parse_args(
        ["view", "--suite", "s.py", "--port", "80", "--port", "080"]
    )
    assert args.port == 80


@pytest.mark.parametrize("command", sorted(PARSES))
def test_no_reserved_name_reaches_the_namespace(command: str) -> None:
    """What the rule keeps while it parses is gone once it has parsed. A name
    left behind would reach a `--json` or a `repr` one day, and nobody would
    know where it came from. Every option of the subcommand is given twice with
    one value, so the bookkeeping runs for all of them."""
    options = [action for name, action in VALUE_OPTIONS if name == command]
    base: tuple[str, ...] = PARSES[command]
    for action in options:
        base = tuple(without(base, action.option_strings[-1]))
    argv = [command, *base]
    for action in options:
        option = action.option_strings[-1]
        value, _ = two_values(action)
        argv += [option, value, option, value]
    args = build_parser().parse_args(argv)
    dests = {
        action.dest
        for action in subparsers()[command]._actions  # pyright: ignore[reportPrivateUsage]
    }
    extra = set(vars(args)) - dests - {"command", "func"}
    assert not extra, f"`digline {command}` left {sorted(extra)} in the namespace"


@pytest.mark.parametrize(
    ("command", "action"),
    VALUE_OPTIONS,
    ids=[f"{command} {action.option_strings[-1]}" for command, action in VALUE_OPTIONS],
)
def test_an_option_given_once_is_read_as_before(
    command: str, action: argparse.Action
) -> None:
    """The control: the normal road. Each option given once parses, and its
    value reaches the reader as one value, not as a list."""
    option = action.option_strings[-1]
    value, _ = two_values(action)
    args = build_parser().parse_args(
        [command, *without(PARSES[command], option), option, value]
    )
    expected: object = int(value) if action.type is int else value
    assert getattr(args, action.dest) == expected
