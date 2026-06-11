"""Exhaustive lifecycle test: every (from, to) pair is either allowed or raises."""

from itertools import product

import pytest

from app.lifecycle.state_machine import (
    ALLOWED_TRANSITIONS,
    IllegalTransitionError,
    InvoiceStatus,
    assert_transition,
)

S = InvoiceStatus

EXPECTED: set[tuple[InvoiceStatus, InvoiceStatus]] = {
    (S.DRAFT, S.VALIDATED),
    (S.VALIDATED, S.DRAFT),
    (S.VALIDATED, S.QUEUED),
    (S.QUEUED, S.SENT),
    (S.QUEUED, S.ERROR),
    (S.SENT, S.ACCEPTED),
    (S.SENT, S.REJECTED),
    (S.SENT, S.ERROR),
    (S.REJECTED, S.DRAFT),
    (S.REJECTED, S.QUEUED),
    (S.ERROR, S.DRAFT),
    (S.ERROR, S.QUEUED),
}


def test_transition_table_matches_specification_exactly() -> None:
    actual = {(frm, to) for frm, targets in ALLOWED_TRANSITIONS.items() for to in targets}
    assert actual == EXPECTED


@pytest.mark.parametrize("frm,to", list(product(S, S)))
def test_every_pair_exhaustively(frm: InvoiceStatus, to: InvoiceStatus) -> None:
    if (frm, to) in EXPECTED:
        assert_transition(frm, to)  # must not raise
    else:
        with pytest.raises(IllegalTransitionError) as excinfo:
            assert_transition(frm, to)
        assert excinfo.value.from_status is frm
        assert excinfo.value.to_status is to


def test_accepted_is_terminal() -> None:
    assert ALLOWED_TRANSITIONS[S.ACCEPTED] == frozenset()


def test_every_status_has_a_transition_entry() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(S)
