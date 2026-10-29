"""A run that is missing from the scan, and what `log` may say about it (#287).

A scan sees what is there, not what was. A missing run folded away in silence.
Its neighbours joined into one span, a roll it carried disappeared, and a first
sighting moved to the next run read. The reading therefore asserted things
that did not happen.

What the fold can see is what #286 found for `latest`: the two committed
artifacts that record a run's `created_at`, the baseline and the register.
Every case below that names the missing run in one of them was red before the
fold read them. The last two are the other half:
- a store where every run named is read says nothing;
- a missing run that neither artifact names **still folds away**, which is the
  limit this repair does not lift.
"""

from __future__ import annotations

import json

from tests.test_log import T1, T2, T3, T4, a_run, config, read, target_spans
from tests.test_resolve_latest import entry_naming

from digline.core import Run
from digline.report import IdentityLog, log_text
from digline.wire import log_json

A, B = "snapshot-a", "snapshot-b"


def run_at(created_at: str, answered: str) -> tuple[str, Run]:
    return a_run(created_at, target=config(resolved=answered))


def said(log: IdentityLog) -> str:
    return "\n".join(log_text(log, locale="en"))


def test_a_roll_there_and_back_no_longer_reads_as_no_change() -> None:
    """A, B, A with the B run missing and named by the register. Before: one A
    span from T1 to T4, no roll, and nothing said."""
    gone = run_at(T2, B)
    log = read(run_at(T1, A), run_at(T4, A), register=(entry_naming(gone[1]),))

    (span,) = target_spans(log)
    assert (span.reported, span.first_seen, span.last_seen) == (A, T1, T4)
    assert span.unread_on_record == 1
    assert log.on_record_not_read == (T2,)
    assert "1 run(s) on record inside it were not read" in said(log)


def test_a_roll_window_says_a_run_on_record_inside_it_was_not_read() -> None:
    """A, B, B with the first B missing and promoted. Before: `silent_between`
    was 0, and nothing marked the window as holding a run."""
    gone = run_at(T2, B)
    log = read(run_at(T1, A), run_at(T3, B), baseline=gone)

    (roll,) = log.rolls
    assert (roll.last_before, roll.first_after) == (T1, T3)
    assert roll.silent_between == 0
    assert roll.unread_on_record == 1
    assert "1 run(s) on record between them were not read" in said(log)


def test_a_missing_first_sighting_is_counted_before_the_first_run_read() -> None:
    """A, B, B with the A run missing: no roll, and B's span reads as the first
    sighting there was. Only the count before the first run read says
    otherwise."""
    gone = run_at(T1, A)
    log = read(run_at(T2, B), run_at(T3, B), register=(entry_naming(gone[1]),))

    assert log.rolls == ()
    assert log.on_record_not_read == (T1,)
    assert "1 before the first run read, 0 after the last" in said(log)


def test_a_missing_last_sighting_is_counted_after_the_last_run_read() -> None:
    gone = run_at(T3, B)
    log = read(run_at(T1, A), run_at(T2, A), baseline=gone)

    assert log.rolls == ()
    assert log.on_record_not_read == (T3,)
    assert "0 before the first run read, 1 after the last" in said(log)


def test_the_keys_cross_to_a_program() -> None:
    gone = run_at(T2, B)
    log = read(run_at(T1, A), run_at(T4, A), register=(entry_naming(gone[1]),))

    document = json.loads(json.dumps(log_json(log)))
    assert document["on_record_not_read"] == [T2]
    target = [s for s in document["spans"] if s["side"] == "target"]
    assert [s["unread_on_record"] for s in target] == [1]


def test_nothing_is_said_where_every_run_on_record_was_read() -> None:
    """The baseline and the register both name runs, and every one of them is
    read. A reading that annotated every span would pass the controls above and
    tell nobody anything."""
    first, second = run_at(T1, A), run_at(T2, B)
    log = read(
        first,
        second,
        run_at(T3, B),
        baseline=second,
        register=(entry_naming(first[1]), entry_naming(second[1])),
    )

    assert log.on_record_not_read == ()
    assert all(span.unread_on_record == 0 for span in log.spans)
    assert all(roll.unread_on_record == 0 for roll in log.rolls)
    assert "on record" not in said(log)


def test_a_run_on_record_outside_the_window_is_not_counted() -> None:
    """The evidence is read through the window, like the runs. A register line
    naming a run before `--since` is outside the reading, not a gap in it."""
    gone = run_at(T1, A)
    log = read(
        run_at(T3, A),
        run_at(T4, A),
        since=T2[:10],
        register=(entry_naming(gone[1]),),
    )

    assert log.on_record_not_read == ()


def test_a_missing_run_nothing_records_still_folds_away() -> None:
    """The limit, pinned. No baseline and no register line names the B run, so
    the reading has no trace of it: one A span from T1 to T4, no roll, and
    nothing to say. `identity_log`'s docstring says why. Lifting this needs a
    record of what existed, which neither artifact is."""
    log = read(run_at(T1, A), run_at(T4, A))

    (span,) = target_spans(log)
    assert (span.first_seen, span.last_seen, span.runs) == (T1, T4, 2)
    assert log.rolls == ()
    assert log.on_record_not_read == ()
    assert span.unread_on_record == 0
