"""A workspace package cannot claim to work with a core that lacks its API.

The trap, in full, because it is the kind that only shows up in somebody else's
environment: a plugin imports a name that arrived in digline 0.5.0 while its own
`pyproject.toml` still says `digline>=0.2.0`. Everything passes here — the
workspace has one core and it is the newest one — the wheel builds, the wheel
uploads, and then a user with digline 0.4.0 installed runs `pip install
digline-anthropic`, the resolver honours the floor it was given, and the plugin
fails on its first import.

Nothing else catches it. `publish.yml` installs each plugin wheel with the core
wheel built beside it, which is the newest core by construction. The tests here
run against the source. The floor is a promise about versions that are *not*
present, so the only thing that can check it is a rule about what the sources
reach for.

That rule: **every name a package imports out of `digline` has to be listed in
`INTRODUCED` below, and the package's floor has to be at least the highest of
them.**

Written about provider plugins, because for four releases that is all
`packages/` held. `digline-mcp` is the first workspace package that is not
one — no `digline.providers` entry point, and it reaches for the store, the
driver, the report, the wire and the host. The trap is identical either way,
so the checks are unchanged and only the vocabulary widened.

A name that is not listed fails this file rather than passing quietly,
which is the point — the moment a plugin reaches for a new part of the core,
somebody has to say which version it appeared in, and that is exactly the
moment the floor needs deciding.

**Do not reach the name through `getattr`, and this paragraph exists because it
was considered.** When `read_pinned` arrived in 0.19.0 both plugins imported it,
this file demanded floors of `>=0.19.0`, and that obliged a release of each —
three packages on one tag instead of one. The cheap way out was to fetch the
name dynamically: `getattr(host, "read_pinned", None)`, no import, floors
untouched, this gate silent.

It was refused, and the reason is not style. **That is precisely the
"works by accident" shape this gate was built to catch**, and writing code whose
purpose is to be invisible to a check built to catch it is the worst remedy on
the table — worse than the honest cost, and worse than not shipping the feature,
because it leaves the floor *saying something false* while the tests agree with
it. A floor is a promise to a user resolving a version we will never see; a
dynamic lookup converts that promise into an `AttributeError` at their runtime
and moves the failure from our CI to their machine. If the floor is too expensive
to raise, the answer is to not use the name, or to ship the feature later — never
to reach it in a way the gate cannot see.

The general rule, since the next temptation will wear different clothes: a check
you are routing around is a check you are disagreeing with, and the disagreement
belongs in this docstring where somebody can argue back, not in a call that
evades it.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"

#: When each name became part of digline's public surface, as the release that
#: first carried it. Verified against the history — `git log -S` on the
#: definition, then `git describe --contains` on the commit — rather than
#: remembered.
#:
#: A name here can be *too low* only by mistake, and the mistake is invisible
#: while every floor is above it. So the table is checked into the record: 0.1.0
#: is the first release, and anything claiming it should be a name that has
#: been there from the start.
INTRODUCED: dict[str, str] = {
    # 0.35.0, the number the cut is expected to give the core release that
    # carries #548 — not yet a release. digline-mcp's `--names project` loads
    # its table with `load_name_table`, holds one answer to one table with
    # `one_table`, and names a suite's checks and cases as a projection does;
    # its floor is owed at the cut, in RELEASING.md's table. (ADR 0054)
    "NameTable": "0.35.0",
    "load_name_table": "0.35.0",
    "one_table": "0.35.0",
    "project_check_name": "0.35.0",
    "project_declared": "0.35.0",
    # 0.25.0 and 0.25.2 — the minter's type and the served projection, each in
    # `digline.core.__all__` from that tag (`git show` of each tag's
    # `core/__init__.py`), imported by digline-mcp under `--names project`.
    "Minter": "0.25.0",
    "project_served": "0.25.2",
    # 0.25.0 — in `digline.core.__all__` from that tag and not in 0.24.0's.
    # digline-mcp catches it where a table answers a name wrongly while a
    # refusal is rendered for an agent. (ADR 0054 §8)
    "ProjectionRefusedError": "0.25.0",
    # 0.34.0, the number the cut is expected to give the core release that
    # carries #523 — not yet a release. Whether git would commit a tenant's
    # run directory or its name table, and the sentence for each. digline-mcp
    # logs them after its `run` tool writes, and pytest-digline prints them
    # after `--digline-run` writes; both floors are owed at the cut already,
    # in RELEASING.md's table, and these ride with them.
    "unignored": "0.34.0",
    "unignored_notes": "0.34.0",
    # 0.34.0 as well, for #621: pytest-digline refuses with it before
    # `--digline-run` spends, on a floor already owed at that cut.
    "refuse_unreadable_baseline": "0.34.0",
    # 0.31.0 — what every front end that runs a suite says about it before the
    # first call, composed once (#396, ADR 0024 §6.4). digline-mcp's floor
    # reached it in digline-mcp 0.5.0, and pytest-digline's in pytest-digline
    # 0.2.4.
    "suite_notes": "0.31.0",
    # 0.29.0 — a refusal is classified by frame as well as by type, and the
    # MCP server renders it without a message digline did not write (#445,
    # ADR 0043 §3). digline-mcp's floor reached it in digline-mcp 0.4.5.
    "to_withhold": "0.29.0",
    "refusal_text": "0.29.0",
    # 0.28.0 — a `SystemExit` from code digline runs is refused with its
    # location, and the MCP server answers it instead of ending (#414, ADR 0041
    # §4.3). digline-mcp's floor reached it in digline-mcp 0.4.4.
    "refused_exit": "0.28.0",
    # 0.25.2 — the list a program that shows runs reads (#276, `44e64ee`,
    # `v0.25.2~9^2`). digline-mcp's `list_runs` reads through it since #314.
    "suite_runs": "0.25.2",
    # 0.20.0 — the core classifies its own refusals, and a front end catches
    # the classification rather than a list of its own (friction 59). Assumed
    # number: `--replacing` makes the release a minor (ADR 0031); whoever cuts
    # it owns the number, and this moves with digline-mcp's floor.
    "REFUSALS": "0.20.0",
    # 0.6.0 — the exit code a comparison means, exported with `digline.wire`
    # (`3100818`, `v0.6.0~2^2~10`). pytest-digline carries it on each suite it
    # opens, so a session digline did not say green does not end green.
    # `EXIT_USAGE` came in the same commit, and digline-mcp's parser exits
    # with it on a refused command line (ADR 0008 §1).
    "EXIT_OK": "0.6.0",
    "EXIT_USAGE": "0.6.0",
    "exit_code": "0.6.0",
    # 0.1.0 — one localized string by key (`ae4a2af`, `v0.1.0~7`). The key the
    # session line uses, `fact.session_not_green`, is new in the core release
    # that carries ADR 0049 §7: a widened table the import cannot see, which is
    # why pytest-digline's floor is owed at the cut, in RELEASING.md's table.
    "phrase": "0.1.0",
    # 0.7.0 — every verdict in `error` in a run, case checks then aggregates
    # (`7df7b7f`, `v0.7.0~2^2~3`). digline-mcp's `run` tool counts them for
    # `errored_checks` (#654).
    "errored_verdicts": "0.7.0",
    # 0.6.0 — an aggregate's name read back into its parts (`6ed18ef`,
    # `v0.6.0~2^2~27`). pytest-digline reads it to tell a slice whose group no
    # case declares from the remainder (#574).
    "split_grouped_name": "0.6.0",
    # 0.6.0 — the loader's default attribute and the TOML suffix, exported
    # with the TOML suite form (`c63fd66`, `v0.6.0~2^2~14`). pytest-digline
    # reads them to tell when two specs name one suite, before loading either.
    "SUITE_ATTR": "0.6.0",
    "SUITE_SUFFIX": "0.6.0",
    # 0.20.0 — `key_of` shipped with `--replacing` (ADR 0031, `0faa931`,
    # `v0.20.0~6^2~3`). A plugin reaches for it now because the key rule moved
    # off the store: `FileResultStore.key_for` was a passthrough to this, and
    # naming a run's key is the document's business, not a backend's. No floor
    # moves — digline-mcp already requires `>=0.20.0` for `REFUSALS`.
    "key_of": "0.20.0",
    # 0.19.2 — the store's two refusals gained types, so a boundary can tell a
    # refusal from a bug (the standing-code pass of 2026-09-23). Ruled as a
    # patch because nothing a legitimate user relies on changes; conditional on
    # no later fix from that pass moving a format version, which would make the
    # core a minor and move this with it.
    "PathRefusedError": "0.19.2",
    "SuiteMismatchError": "0.19.2",
    "DocumentRefusedError": "0.19.2",
    "RunNotFoundError": "0.19.2",
    # 0.1.0 — the first published surface.
    "ModelPrice": "0.1.0",
    "Pricing": "0.1.0",
    "ProviderTarget": "0.1.0",
    "Usage": "0.1.0",
    "UnknownModelError": "0.1.0",
    "PromptTemplate": "0.1.0",
    "render_value": "0.1.0",
    # 0.1.3 — a plugin became a target *and* a judge (ADR 0004).
    "JudgeBase": "0.1.3",
    "ScoreJudge": "0.1.3",
    "ClaimCountJudge": "0.1.3",
    "loads_lenient": "0.1.3",
    # 0.2.0 — the configuration of the system under test (ADR 0005).
    "ConfigValue": "0.2.0",
    "CONTRACT_FIELDS": "0.2.0",
    "declared_config": "0.2.0",
    "endpoint_host": "0.2.0",
    "sent": "0.2.0",
    # 0.5.0 — providers as entry points (ADR 0007 §3).
    "Provider": "0.5.0",
    "ProviderNotFound": "0.5.0",
    "installed": "0.5.0",
    "resolve": "0.5.0",
    "split_coordinate": "0.5.0",
    # 0.1.0 — the parts of the core a package other than a provider reaches for.
    # Undated until `digline-mcp` arrived, because until then nothing outside
    # `packages/` imported them and nothing inside it did.
    "Run": "0.1.0",
    "Suite": "0.1.0",
    "compare": "0.1.0",
    "execute": "0.1.0",
    "headline": "0.1.0",
    "FileResultStore": "0.1.0",
    "ResultStore": "0.1.0",
    "ConfigMismatchError": "0.1.0",
    "ErroredRunError": "0.1.0",
    "TenantMismatchError": "0.1.0",
    # 0.4.0 — the preflight count (ADR 0006 §8).
    "CallPlan": "0.4.0",
    "planned_calls": "0.4.0",
    # 0.6.0 — the two-run report (ADR 0008).
    "diff": "0.6.0",
    "DifferentSuitesError": "0.6.0",
    "DifferentJudgesError": "0.6.0",
    # 0.6.0 — the machine surface, promoted out of the CLI (ADR 0011 §6).
    "compare_json": "0.6.0",
    "diff_json": "0.6.0",
    "run_json": "0.6.0",
    "runs_json": "0.6.0",
    "run_document": "0.6.0",
    # 0.6.0 — the host layer (ADR 0011 §7). **These names are older than the
    # date beside them**, and the date is still right: the table exists to
    # answer "would a user with digline X get an ImportError", and until 0.6.0
    # these lived in `digline.cli`. A move is exactly the failure this file
    # guards, so a name that moved is dated to the release that moved it.
    "UsageError": "0.6.0",
    "load_suite": "0.6.0",
    "load_target": "0.6.0",
    "git_commit": "0.6.0",
    "utc_now_iso": "0.6.0",
    "read_artifacts": "0.6.0",
    # 0.19.0 — the pins beside the artifacts. Both front ends read them, because
    #  refuses a pinning suite handed no pin set rather than recording a
    # control that cannot fire (ADR 0029 §4).
    "read_pinned": "0.19.0",
    "resolve_key": "0.6.0",
    "Resolved": "0.6.0",
    "need_baseline": "0.6.0",
    "read_run": "0.6.0",
    # Older still — the class dates to 0.5.0 and the TOML loader — but it left
    # `digline.cli` on the same move, so it answers the ImportError question
    # with the same number as the functions above it.
    "Loaded": "0.6.0",
    # 0.8.0 — `_complete` returns a record (ADR 0004 §6), and the record carries
    # the observed identity (ADR 0005 §9). Every provider plugin reaches for all
    # three, which is why the trio's floors move together.
    "Completion": "0.8.0",
    "CompletionResult": "0.8.0",
    "ObservedIdentity": "0.8.0",
    "as_completion": "0.8.0",
    "finish_of": "0.8.0",
    "Finish": "0.8.0",
    # 0.9.0 — the per-delta sentence, promoted out of `render._detail` so a
    # third front end can print the report's own line instead of composing a
    # fourth one (ADR 0013 §6).
    "check_line": "0.9.0",
    # 0.1.0 — the comparison's own types, and the verdict inside them. Undated
    # until `pytest-digline` arrived, for the reason the host names were:
    # nothing outside `src/` imported them. Verified against the history, like
    # every line here — all three land in `v0.1.0~7`.
    "AssertionDelta": "0.1.0",
    # 0.10.1 — the sanitiser both front ends share. The plugin prints a judge's
    # `reason`, which quotes what a model answered, so it needs the same rule the
    # CLI applies at its own sink (the 0.10.0 release delta-pass).
    "visible": "0.10.1",
    "Comparison": "0.1.0",
    "Verdict": "0.1.0",
    # 0.2.0 — the named configuration delta a row prints beside a drop
    # (ADR 0005 §5).
    "config_changes": "0.2.0",
    # 0.11.0 — the host composition both front ends sit on, so journalling is
    # wired once rather than once per front end (ADR 0017 §11). Undated until
    # now for the reason the other host names were: nothing outside `src/`
    # imported them. `digline-mcp` 0.1.2 does, which is what dates them.
    "prepare": "0.11.0",
    "measure": "0.11.0",
    # 0.1.0 — the canonical form a recorded value is written in. Undated until
    # `digline-bedrock` used it to write a non-object tool input as JSON rather
    # than drop it; `git describe --contains` on its definition lands in
    # `v0.1.0~7`.
    "canonical": "0.1.0",
    # 0.13.0 — the trajectory a provider plugin hands over (ADR 0018 §1,
    # amended 2026-09-15), and the declared zero each plugin's `free()` now
    # delegates to (ADR 0022 §2). Dated to a release that did not exist yet
    # when the trio's floors named it, which is what kept the plugins off the
    # index until 0.13.0 was. A names gate sees these two and not the field
    # `Completion.tool_calls` beside them, so the floors say that by hand.
    "ToolCall": "0.13.0",
    "free": "0.13.0",
    # 0.7.0 — the reading's machine shape (ADR 0012 §3). Undated until the MCP
    # `explain` tool imported it (ADR 0020 §8); `git describe --contains` on the
    # commit that defined it lands in v0.7.0.
    "explain_json": "0.7.0",
    # 0.13.0 — the reading across runs (ADR 0020), and the host composition both
    # front ends share for it and for `explain`. Dated to a release that did not
    # exist yet when the MCP tools first imported them, which is what kept the
    # MCP half off `main` until it did — the shape ADR 0017 §11 gave `prepare`
    # and `measure`.
    "explained": "0.13.0",
    "history": "0.13.0",
    "instant": "0.13.0",
    "log_json": "0.13.0",
    # 0.14.0 — the calibration case (ADR 0024 §4). Dated to a release that does
    # not exist yet, the shape `ToolCall` and `free` had: `pytest-digline` reads
    # a lost scale off the run with the report's own function and prints the
    # report's own sentence for it, so it stays off the index until 0.14.0 is.
    "ScaleLost": "0.14.0",
    "scale_lost": "0.14.0",
    "calibration_fact": "0.14.0",
    # 0.15.1 — the escape rule moved off the serialised JSON and onto the value,
    # so that both front ends inherit it instead of one remembering it.
    # `digline-mcp` reaches for it directly from 0.1.4, because a refusal's
    # *message* is not a rendered document: `digline.wire` never saw it, and it
    # left for a client with its control bytes intact.
    "json_visible": "0.15.1",
}

#: Where a dated name may live. Was `core` and `targets` alone, which was true
#: for as long as every workspace package was a provider plugin: a provider
#: needs a `ProviderTarget` and a `JudgeBase` and nothing else. `digline-mcp` is
#: a workspace package and not a provider — it registers no entry point in
#: `digline.providers` — and it reaches for the store, the driver, the report,
#: the wire and the host. The rule is unchanged: a dated name that no longer
#: exists anywhere fails, because the floor would then be computed against a
#: version claim nobody can meet.
SURFACE = (
    "digline.core",
    "digline.targets",
    "digline.store",
    "digline.run",
    "digline.report",
    "digline.wire",
    "digline.host",
)


#: When each method or attribute a shipped plugin calls on something digline
#: gives it became part of digline, keyed by `(module, class, attribute)`: the
#: class in the receiver's MRO that defines it, in the module that defines it
#: today. A module's own attribute has the class `""`. (#702)
#:
#: **What it is for.** `RELEASING.md` reads a public name in three levels, and
#: a method or an attribute a shipped plugin calls is the **second**: a release
#: that removes or renames it breaks the plugin, whether or not `docs/api.md`
#: lists it. Its date is what lets the delta-pass tell a name a release added
#: from one a plugin already relied on. `INTRODUCED`, above, dates the names a
#: plugin imports and is keyed by the bare name; a method is in no `__all__`,
#: and one name is two entries when two classes define it, so it has a table of
#: its own.
#:
#: **Where the dates come from.** `tools/plugin_call_dates.py`, from git's
#: release tags: the first `v*` tag from which the class, in today's module,
#: defines the attribute in its own body at every later tag. It found no gap
#: and no entry it could not date. A class that moved is dated to the move, the
#: rule `INTRODUCED` applies: one entry is. The control: `ToolCall.tool`,
#: `ScaleLost`, `Completion.text` and `CallPlan` come out at the releases
#: `INTRODUCED` gives their classes, 0.13.0, 0.14.0, 0.8.0 and 0.4.0, and two
#: dates were read again with `git log -S` and `git describe --contains`:
#: `Run.usage` at 0.16.0 and `Suite.declared` at 0.32.0. Its limit: presence is
#: by name, so an attribute that once had the same name and another meaning is
#: read as the same one.
#:
#: **Not in it, and not a gap.** `tools/plugin_calls.py` leaves six receivers
#: unresolved, each a reply of the Anthropic SDK in `digline_anthropic/
#: client.py`, which pyright types `Any`. What a plugin reads on an SDK's reply
#: is not a name of digline's, so it is not dated here.
CALLED: dict[tuple[str, str, str], str] = {
    ("digline.core.aggregate", "RunAssertion", "name"): "0.1.0",
    ("digline.core.calibration", "ScaleLost", "case_id"): "0.14.0",
    ("digline.core.calibration", "ScaleLost", "check"): "0.14.0",
    ("digline.core.compare", "AssertionDelta", "assertion"): "0.1.0",
    ("digline.core.compare", "AssertionDelta", "baseline"): "0.1.0",
    ("digline.core.compare", "AssertionDelta", "calibration"): "0.14.0",
    ("digline.core.compare", "AssertionDelta", "canary"): "0.10.0",
    ("digline.core.compare", "AssertionDelta", "case_id"): "0.1.0",
    ("digline.core.compare", "AssertionDelta", "current"): "0.1.0",
    ("digline.core.compare", "AssertionDelta", "denominator_moved"): "0.15.1",
    ("digline.core.compare", "AssertionDelta", "outcome"): "0.1.0",
    ("digline.core.compare", "AssertionDelta", "scope"): "0.1.0",
    ("digline.core.compare", "Comparison", "config_changes"): "0.2.0",
    ("digline.core.compare", "Comparison", "deltas"): "0.1.0",
    ("digline.core.protocols", "Assertion", "name"): "0.1.0",
    ("digline.core.run", "Run", "config_hash"): "0.1.0",
    ("digline.core.run", "Run", "created_at"): "0.1.0",
    ("digline.core.run", "Run", "usage"): "0.16.0",
    ("digline.core.types", "Verdict", "reason"): "0.1.0",
    ("digline.core.types", "Verdict", "status"): "0.1.0",
    ("digline.host.listing", "SuiteRuns", "baseline_key"): "0.25.2",
    ("digline.host.listing", "SuiteRuns", "baseline_refused"): "0.25.2",
    ("digline.host.listing", "SuiteRuns", "listing"): "0.25.2",
    ("digline.host.listing", "SuiteRuns", "misfiled"): "0.28.0",
    ("digline.host.listing", "SuiteRuns", "skipped"): "0.26.0",
    ("digline.host.listing", "SuiteRuns", "unreadable_count"): "0.26.0",
    ("digline.host.listing", "SuiteRuns", "note"): "0.25.2",
    ("digline.host.listing", "SuiteRuns", "refused"): "0.25.2",
    ("digline.host.listing", "SuiteRuns", "runs"): "0.25.2",
    ("digline.host.loader", "Loaded", "modules_unchecked"): "0.32.0",
    ("digline.host.loader", "NameTable", "mint"): "0.35.0",
    # In `digline.cli` from 0.5.0; dated to the move, as INTRODUCED dates
    # the host names.
    ("digline.host.loader", "Loaded", "suite"): "0.6.0",
    ("digline.host.measure", "Measured", "plan"): "0.11.0",
    ("digline.host.measure", "Measured", "ref"): "0.11.0",
    ("digline.host.measure", "Measured", "run"): "0.11.0",
    ("digline.host.measure", "Prepared", "plan"): "0.11.0",
    ("digline.host.reading", "Explained", "baseline"): "0.13.0",
    ("digline.host.reading", "Explained", "exit_code"): "0.13.0",
    # Named `scope` until `OUTPUT_VERSION` 5, when the facts this name held
    # became `facts`. The attribute is as old as its date and its meaning is
    # not: a floor read from this table would let digline-mcp read the facts
    # where it means the document, which is why RELEASING.md owes its floor.
    ("digline.host.reading", "Explained", "reading"): "0.13.0",
    ("digline.host.reading", "Explained", "run"): "0.13.0",
    ("digline.host.resolve", "Resolved", "key"): "0.6.0",
    ("digline.host.resolve", "Resolved", "note"): "0.6.0",
    ("digline.report.diff", "", "sentence"): "0.6.0",
    ("digline.report.render", "Headline", "reasons_available"): "0.1.0",
    ("digline.report.render", "Headline", "sentence"): "0.1.0",
    ("digline.run.suite", "CallPlan", "judged"): "0.14.0",
    ("digline.run.suite", "CallPlan", "repeats"): "0.4.0",
    ("digline.run.suite", "CallPlan", "sentence"): "0.4.0",
    ("digline.run.suite", "CallPlan", "target_calls"): "0.4.0",
    ("digline.run.suite", "Case", "group"): "0.6.0",
    ("digline.run.suite", "Case", "id"): "0.1.0",
    ("digline.run.suite", "Case", "suspended"): "0.1.0",
    ("digline.run.suite", "Suite", "assertions"): "0.1.0",
    ("digline.run.suite", "Suite", "cases"): "0.1.0",
    ("digline.run.suite", "Suite", "declared"): "0.32.0",
    ("digline.run.suite", "Suite", "disclosure"): "0.1.0",
    ("digline.run.suite", "Suite", "environment"): "0.1.0",
    ("digline.run.suite", "Suite", "name"): "0.1.0",
    ("digline.run.suite", "Suite", "run_assertions"): "0.1.0",
    ("digline.run.suite", "Suite", "tenant"): "0.1.0",
    ("digline.store.protocol", "ResultStore", "write_run"): "0.1.0",
    ("digline.targets.completion", "Completion", "text"): "0.8.0",
    ("digline.targets.completion", "Completion", "unpriced"): "0.35.0",
    ("digline.targets.completion", "Completion", "usage"): "0.8.0",
    ("digline.targets.completion", "ToolCall", "tool"): "0.13.0",
    ("digline.targets.judge", "JudgeBase", "config"): "0.2.0",
    ("digline.targets.judge", "JudgeBase", "prefill"): "0.6.0",
    ("digline.targets.pricing", "ModelPrice", "cache_read_per_mtok"): "0.1.0",
    ("digline.targets.pricing", "ModelPrice", "cache_write_per_mtok"): "0.1.0",
    ("digline.targets.pricing", "ModelPrice", "input_per_mtok"): "0.1.0",
    ("digline.targets.pricing", "ModelPrice", "output_per_mtok"): "0.1.0",
    ("digline.targets.pricing", "Pricing", "cost"): "0.1.0",
    ("digline.targets.pricing", "Pricing", "declared"): "0.13.0",
    ("digline.targets.pricing", "Pricing", "per_model"): "0.1.0",
    ("digline.targets.pricing", "Pricing", "why_unpriced"): "0.35.0",
    ("digline.targets.provider", "ProviderTarget", "config"): "0.2.0",
    ("digline.targets.provider", "ProviderTarget", "prefill"): "0.10.0",
}

#: The entries the history does not date, each with the reason, never a guess
#: at a version: "undated" is a value. None today.
UNDATED: dict[tuple[str, str, str], str] = {}

#: The entries on `main` and in no release tag, each with what brought it.
#: `UNDATED` is *the history does not answer*; this is *it is in no tag yet*,
#: and the cut answers it: each entry moves into `CALLED` with the number of
#: the release that carries it (RELEASING.md, *Before the tag: moving the
#: number*). `test_plugin_calls.py` holds that every entry here is in no tag,
#: so a name the cut forgot to move fails there rather than staying here.
UNRELEASED: dict[tuple[str, str, str], str] = {
    ("digline.host.reading", "Explained", "facts"): "OUTPUT_VERSION 5",
}


def plugins() -> list[Path]:
    found = sorted(p for p in PACKAGES.iterdir() if (p / "pyproject.toml").is_file())
    assert found, "no plugin found; this file would prove nothing"
    return found


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def floor(plugin: Path) -> str:
    """The `digline>=X` a plugin's metadata declares."""
    with (plugin / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    for dependency in project["dependencies"]:
        text = str(dependency).replace(" ", "")
        if text.startswith("digline>="):
            return text.removeprefix("digline>=").split(",")[0]
    pytest.fail(f"{plugin.name} declares no `digline>=` floor at all")


def imported_from_digline(plugin: Path) -> set[str]:
    """Every name the plugin's sources take out of `digline`."""
    names: set[str] = set()
    for source in sorted((plugin / "src").rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "digline."
            ):
                names.update(alias.name for alias in node.names)
    return names


@pytest.mark.parametrize("plugin", plugins(), ids=lambda p: p.name)
def test_every_core_name_a_plugin_imports_is_dated(plugin: Path) -> None:
    """The half that keeps the table honest.

    An undated name cannot be checked against a floor, so it fails here with
    the one question that needs answering."""
    undated = sorted(imported_from_digline(plugin) - set(INTRODUCED))
    assert not undated, (
        f"{plugin.name} imports {undated} from digline, and "
        "tests/test_plugin_floors.py does not say which release introduced "
        "them. Add each one to INTRODUCED with the version it first shipped "
        "in — `git log -S'<name>' --reverse -- src/` then "
        "`git describe --tags --contains <commit>` — and then check that this "
        "plugin's `digline>=` floor is at least that high."
    )


@pytest.mark.parametrize("plugin", plugins(), ids=lambda p: p.name)
def test_the_floor_covers_every_core_name_the_plugin_uses(plugin: Path) -> None:
    """The trap itself. A floor below the newest name the sources import is a
    published promise that the package cannot keep."""
    declared = floor(plugin)
    # A name new in a core that is not released yet cannot be met by a floor,
    # because a floor may not name a release that does not exist. The row
    # owed at the cut is the promise instead. It counts only beside the marker
    # in the plugin's own pyproject, and the cut deletes the row, after which
    # this reads the real floor again.
    #
    # **A temporary relaxation, and weaker than what it replaces.** A row is a
    # promise somebody has to keep at the cut, and a floor is the fact a
    # resolver reads. Between the pull request that writes the row and the cut
    # that deletes it, this gate holds the promise, not the fact. It regains
    # its strength only at the cut. (#414)
    owed = owed_floor(plugin)
    if owed is not None and version_tuple(owed) > version_tuple(declared):
        declared = owed
    used = imported_from_digline(plugin) & set(INTRODUCED)
    needed = max(used, key=lambda name: version_tuple(INTRODUCED[name]))
    assert version_tuple(declared) >= version_tuple(INTRODUCED[needed]), (
        f"{plugin.name} declares `digline>={declared}` and imports "
        f"`{needed}`, which arrived in digline {INTRODUCED[needed]}. A user "
        f"who has digline {declared} installed would get this plugin and an "
        f"ImportError: raise the floor to >={INTRODUCED[needed]}."
    )


@pytest.mark.parametrize("plugin", plugins(), ids=lambda p: p.name)
def test_a_dated_name_still_exists_in_the_public_surface(plugin: Path) -> None:
    """The table names the public surface, so a name removed from digline has to
    be removed from here too — otherwise the floor is computed against a version
    claim nobody can meet."""
    import importlib

    modules = [importlib.import_module(name) for name in SURFACE]
    for name in imported_from_digline(plugin) & set(INTRODUCED):
        assert any(hasattr(module, name) for module in modules), (
            f"{name} is dated in INTRODUCED but exists in none of "
            f"{', '.join(SURFACE)}. Either it moved — date it to the release "
            "that moved it, the way the host names are — or it is gone and the "
            "entry has to go with it."
        )


def imports_from_digline(plugin: Path) -> set[tuple[str, str]]:
    """Every `(module, name)` the plugin's sources take out of `digline`."""
    pairs: set[tuple[str, str]] = set()
    for source in sorted((plugin / "src").rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "digline."
            ):
                pairs.update((node.module or "", alias.name) for alias in node.names)
    return pairs


@pytest.mark.parametrize("plugin", plugins(), ids=lambda p: p.name)
def test_every_dated_name_is_in_the_all_of_the_module_it_comes_from(
    plugin: Path,
) -> None:
    """A name a plugin imports is public, whether or not `docs/api.md` lists
    it, and `RELEASING.md` says so (*Choosing the version*, the second level,
    2026-10-25): renaming it moves the minor, because the plugin's cap protects
    its users only through a minor. That rule is applied by review. What this
    holds is the list it reads: every dated name a plugin imports is in the
    `__all__` of the module it is imported from.

    `test_a_dated_name_still_exists_in_the_public_surface` above cannot see
    this. It asks `hasattr`, and a name taken out of an `__all__` with its
    definition left in place still answers it.
    """
    import importlib

    missing = sorted(
        f"{module}.{name}"
        for module, name in imports_from_digline(plugin)
        if name in INTRODUCED
        and name not in getattr(importlib.import_module(module), "__all__", ())
    )
    assert not missing, (
        f"{plugin.name} imports these, they are dated in INTRODUCED, and they "
        f"are in no `__all__` of the module they come from: {missing}. A name a "
        "plugin imports is public surface (RELEASING.md, Choosing the version): "
        "put it back in `__all__`, or move the plugin off it first."
    )


@pytest.mark.parametrize("entry", sorted(CALLED), ids=lambda e: f"{e[0]}:{e[1]}.{e[2]}")
def test_a_dated_call_is_still_an_attribute_of_its_class(
    entry: tuple[str, str, str],
) -> None:
    """A method or attribute dated in `CALLED` still exists where the table
    says, so a date is never kept for something a release took away: that
    removal is the break a plugin meets. Read through the MRO, fields with no
    default included, since `hasattr` does not see a dataclass field that has
    none. (#702)"""
    import importlib

    module_name, class_name, attr = entry
    module = importlib.import_module(module_name)
    if not class_name:
        assert hasattr(module, attr), f"{module_name} no longer has `{attr}`"
        return
    cls = getattr(module, class_name, None)
    assert isinstance(cls, type), f"{module_name} no longer has `{class_name}`"
    assert any(
        attr in vars(klass) or attr in getattr(klass, "__annotations__", {})
        for klass in cls.__mro__
    ), (
        f"`{class_name}.{attr}` is dated in CALLED and {module_name}.{class_name} "
        "no longer has it. A shipped plugin calls it (tools/plugin_calls.py): "
        "removing it is a break at the second level of RELEASING.md's public "
        "name, so put it back, or move the plugin off it first."
    )


def test_the_import_reader_finds_the_module_of_each_name() -> None:
    """The control for the test above: a plugin's imports are read with their
    module, so the check is made against the right `__all__`."""
    pairs = imports_from_digline(PACKAGES / "digline-mcp")
    assert ("digline.host", "unignored_notes") in pairs
    assert ("digline.wire", "explain_json") in pairs


#: Where `RELEASING.md` lists the floors owed to the next cut, between these two
#: sentences. Both are required: a reworded heading must fail here, not leave
#: the check below reading an empty section and passing.
OWED_OPENS = "raise the floors owed to this release."
OWED_CLOSES = "**An empty table is the normal state.**"
OWED_MARKER = "Owed at the cut"


def owed_section() -> str:
    text = (ROOT / "RELEASING.md").read_text(encoding="utf-8")
    start, end = text.find(OWED_OPENS), text.find(OWED_CLOSES)
    assert 0 <= start < end, (
        "RELEASING.md no longer has the step that lists the floors owed at the "
        f"cut, opening with {OWED_OPENS!r} and closing with {OWED_CLOSES!r}."
    )
    return text[start:end]


def owed_rows() -> list[list[str]]:
    """The rows of the table owed at the cut, each as its four cells.

    Split on the pipes that end a cell and not on `\\|`, which Markdown reads
    as a pipe inside one: a row whose *Owed because* says `Usage \\| None`
    was five cells to a plain split, and `owed_floor` passed over it as no
    row at all."""
    rows: list[list[str]] = []
    for line in owed_section().splitlines():
        if not line.startswith("|"):
            continue
        cells = [
            cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))
        ]
        assert len(cells) == 4, f"a row of the owed table is not four cells: {line}"
        rows.append(cells)
    return rows


def owed_floor(plugin: Path) -> str | None:
    """The *Raise to* of `plugin`'s row in the table owed at the cut, when its
    pyproject carries the marker, or `None`."""
    pyproject = (plugin / "pyproject.toml").read_text(encoding="utf-8")
    if OWED_MARKER not in pyproject:
        return None
    for cells in owed_rows():
        if cells[0] == f"`{plugin.name}`":
            return cells[2].strip("`")
    return None


@pytest.mark.parametrize("plugin", plugins(), ids=lambda p: p.name)
def test_a_floor_owed_at_the_cut_is_where_the_cut_reads(plugin: Path) -> None:
    """The half this file cannot compute. A plugin that passes a new argument to
    a name it already imported needs a newer core than its imports say, and a
    floor may not name a release that does not exist yet, so the floor is
    written by hand at the cut. A note beside the floor is read by nobody
    cutting a release, so the note has to be in the step the cut walks through.
    (#314)"""
    pyproject = (plugin / "pyproject.toml").read_text(encoding="utf-8")
    if OWED_MARKER not in pyproject:
        return
    assert f"| `{plugin.name}` |" in owed_section(), (
        f"{plugin.name}'s pyproject.toml says its floor is {OWED_MARKER!r}, and "
        "RELEASING.md's table of floors owed to this release has no row for "
        "it. Add the row, or the release will ship this package on a floor "
        "that cannot run it."
    )


#: The header of the table owed at the cut. Read whole, so a column added,
#: removed or renamed fails here instead of moving every cell one place.
OWED_HEADER = ["Package", "Owed because", "Raise to", "Then"]

#: The other table `RELEASING.md` keeps for the next cut, declared out of the
#: rule below rather than passed over. **Its rows name a number and not a
#: floor**: what a package's next version must reflect, read by whoever
#: chooses the number. One of the packages it names is digline itself, which
#: has no plugin `pyproject.toml` to carry a marker. A floor that a row there
#: implies is written in the table owed at the cut, which is where the rule
#: reads it. Its header is pinned, so a floor column added to it fails here
#: and the scope is decided again.
OUT_OF_SCOPE = {
    "**And the number each package owes: read *Owed to the next version*.**": (
        "| Package | What it carries | What the number must reflect |"
    ),
}


def test_the_owed_table_has_the_shape_the_rule_reads() -> None:
    """The control for the rule below: the header is the one it was written
    for, and every row splits into its four cells."""
    rows = owed_rows()
    assert rows[0] == OWED_HEADER, rows[0]
    assert rows[1] == ["---"] * 4, rows[1]


def test_every_floor_owed_at_the_cut_has_a_keeper() -> None:
    """The other direction from the test above: a row in the table owed at the
    cut names a plugin whose `pyproject.toml` carries the marker.

    Without it, the test above returns at its first line, `owed_floor` answers
    `None`, and the row is held by nothing but the file that holds it: a debt
    no machine reads. Measured 2026-10-27: digline-anthropic, digline-bedrock
    and digline-openai each had a row, from #739 and #569, and none of them
    the marker."""
    names = {plugin.name for plugin in plugins()}
    unkept: list[str] = []
    for cells in owed_rows()[2:]:
        package = cells[0].strip("`")
        assert package in names, (
            f"the table owed at the cut names {package!r}, which is not a "
            f"plugin of this workspace: {sorted(names)}"
        )
        pyproject = (PACKAGES / package / "pyproject.toml").read_text(encoding="utf-8")
        if OWED_MARKER not in pyproject:
            unkept.append(package)
    assert not unkept, (
        f"RELEASING.md owes a floor for {unkept} at the cut, and their "
        f"pyproject.toml carries no {OWED_MARKER!r}, so nothing here reads the "
        "row. Write the marker beside the `digline>=` floor, saying what it is "
        "raised to and why."
    )


def test_the_table_out_of_scope_keeps_its_shape() -> None:
    """Declared out of the rule above, and pinned so the declaration is
    decided again if the table starts to name a floor."""
    text = (ROOT / "RELEASING.md").read_text(encoding="utf-8")
    for opens, header in OUT_OF_SCOPE.items():
        start = text.find(opens)
        assert start >= 0, f"RELEASING.md no longer has {opens!r}"
        assert header in text[start:], (
            f"the table after {opens!r} no longer has the header {header!r}: "
            "decide again whether its rows name a floor"
        )
