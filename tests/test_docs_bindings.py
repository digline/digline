"""The identity rule the documentation replay compares run keys by."""

from __future__ import annotations

from tests._docs import Bindings

A = "2026-08-26T16-06-38-334462-00-00-282b0c02d6511fb4"
B = "2026-08-26T16-06-48-447223-00-00-282b0c02d6511fb4"
X = "2026-09-16T15-21-13-989814-00-00-282b0c02d6511fb4"
Y = "2026-09-16T15-21-14-001122-00-00-282b0c02d6511fb4"


def test_a_key_binds_to_the_run_printed_beside_it_and_stays_bound() -> None:
    bindings = Bindings()
    assert bindings.match(f"baseline set to {A}", f"baseline set to {X}")
    assert bindings.match(A, X)


def test_one_key_on_the_page_cannot_stand_for_two_runs() -> None:
    bindings = Bindings()
    assert bindings.match(A, X)
    assert not bindings.match(A, Y)


def test_two_keys_on_the_page_cannot_stand_for_one_run() -> None:
    bindings = Bindings()
    assert bindings.match(A, X)
    assert not bindings.match(B, X)


def test_a_line_that_fails_binds_nothing() -> None:
    bindings = Bindings()
    assert not bindings.match(f"{A} set", f"{X} unset")
    assert bindings.match(f"{A} unset", f"{Y} unset")


def test_the_shape_around_the_keys_is_still_compared() -> None:
    assert not Bindings().match(f"* {A}", f"  {X}")


def test_labels_number_tokens_by_first_appearance_on_the_page() -> None:
    bindings = Bindings()
    bindings.seen(f"{A} then {B}")
    bindings.seen(A)
    assert bindings.label(f"{B} {A}") == "<KEY 2> <KEY 1>"
