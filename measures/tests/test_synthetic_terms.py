"""The synthetic students' cohort, last term and enrollment flag agree with each other.

Rerun gia-pre-implementation/synthetic-datasets/repair_enrollment_terms.py if these fail.
"""

import csv

import pytest

from measures.load_synthetic import COLLEGES, DATASETS


def academic_year(term: str) -> int:
    """The year an academic year starts in: Fall 2024 and Spring 2025 are both 2024-25."""
    season, year = term.split()
    return int(year) if season == "Fall" else int(year) - 1


def students(college: str) -> list[dict[str, str]]:
    """One college's students.csv rows."""
    with (DATASETS / college / "csv" / "students.csv").open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


@pytest.mark.parametrize("college", COLLEGES)
def test_no_student_leaves_before_their_cohort_starts(college):
    early = [
        row["Student GUID"]
        for row in students(college)
        if academic_year(row["Last Enrolled Term"]) < int(row["Cohort"][:4])
    ]
    assert early == []


@pytest.mark.parametrize("college", COLLEGES)
def test_enrolled_students_were_last_enrolled_this_term(college):
    stale = [
        row["Student GUID"]
        for row in students(college)
        if row["Currently Enrolled"] == "Yes" and row["Last Enrolled Term"] != row["Reference Term"]
    ]
    assert stale == []
