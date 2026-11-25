"""Stop-outs leave out the term still in progress and count it separately."""

import pytest

from app.institution_dashboard import data
from app.institution_dashboard.data import (
    OUT_OF_SCOPE_TYPES,
    _current_term,
    _students,
    build_dashboard,
    term_label,
)


@pytest.fixture(autouse=True)
def no_saved_upload(monkeypatch, tmp_path) -> None:
    """Read the synthetic files, not an upload someone saved on this machine."""
    monkeypatch.setattr(data, "UPLOAD_ROOT", tmp_path)


def dashboard(institution: str):
    """The dashboard at default filters for one synthetic college."""
    return build_dashboard(institution, "6", "all", "all", "all", "any", "any", "all", "all")


def count(body, row_id: str) -> int:
    """One summary row's value."""
    return next(row.value for row in body.summary if row.id == row_id)


def left_with_credits(institution: str) -> int:
    """Students the old rule called stop-outs: not enrolled, with credits left."""
    return sum(
        not student["enrolled"] and student["credits_remaining"] > 0
        for student in _students(institution)
        if student["student_type"] not in OUT_OF_SCOPE_TYPES and not student["excluded"]
    )


@pytest.mark.parametrize("institution", ["cmc", "college_two"])
def test_current_term_is_not_a_stop_out_term(institution: str) -> None:
    body = dashboard(institution)
    in_scope = [s for s in _students(institution) if s["student_type"] not in OUT_OF_SCOPE_TYPES]

    assert body.current_term == _current_term(in_scope)
    assert body.current_term not in [option.value for option in body.terms]
    # Splitting off the current term moves students between the two rows, never loses any.
    assert count(body, "stop_outs") + count(body, "not_enrolled_this_term") == left_with_credits(
        institution
    )
    assert sum(row.stop_outs for row in body.stop_outs) == count(body, "stop_outs")
    assert f"{term_label(body.current_term)} is in progress" in body.stop_out_tiles[0].note


def test_choosing_the_current_term_is_rejected() -> None:
    current = dashboard("college_two").current_term
    with pytest.raises(ValueError):
        build_dashboard("college_two", "6", "all", "all", "all", "any", "any", current, current)
