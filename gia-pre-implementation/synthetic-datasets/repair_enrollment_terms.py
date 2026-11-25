"""Repair two contradictions between each synthetic student's cohort, last term and enrollment.

1. A last enrolled term before the cohort's academic year began. The course history backs up the
   last term, so the cohort is what moves: to the academic year of the student's first course, or,
   for a student with no course history, to the academic year of their last term.
2. A student marked Currently Enrolled whose last enrolled term is not the Reference Term (the
   term in progress). The last term becomes the Reference Term, so it agrees with Currently
   Enrolled and enrollment_status.

Only the Cohort, Last Enrolled Term and pdp_year cells of students.csv change; pdp_year moves
only because it is derived from the last term. Running it twice changes nothing the second time
(git diff shows no change).

Usage (from the repo root):
    python gia-pre-implementation/synthetic-datasets/repair_enrollment_terms.py
"""

import sys
from collections import defaultdict
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit("repair_enrollment_terms needs Python 3.10 or newer. Activate the repo's .venv first.")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rebuild_major_progress import read, write  # noqa: E402

SEASON_ORDER = {"Spring": 0, "Summer": 1, "Fall": 2}


def term_key(term: str) -> tuple[int, int]:
    """Sort a term like "Fall 2024" by year, then by season within the year."""
    season, year = term.split()
    return (int(year), SEASON_ORDER[season])


def academic_year(term: str) -> int:
    """The year an academic year starts in: Fall 2024 and Spring 2025 are both 2024-25."""
    season, year = term.split()
    return int(year) if season == "Fall" else int(year) - 1


def cohort_label(start: int) -> str:
    """An academic year the way the Cohort column writes it: 2024 becomes 2024-25."""
    return f"{start}-{(start + 1) % 100:02d}"


def first_terms(college: str) -> dict[str, str]:
    """Each student's earliest Enrollment Term in course_detail.csv."""
    _fields, enrollments = read(HERE / college / "csv" / "course_detail.csv")
    terms: dict[str, list[str]] = defaultdict(list)
    for row in enrollments:
        terms[row["Student GUID"]].append(row["Enrollment Term"])
    return {student: min(found, key=term_key) for student, found in terms.items()}


def repair(college: str) -> tuple[int, int]:
    """Fix both contradictions for one college; return how many cohorts and last terms moved."""
    path = HERE / college / "csv" / "students.csv"
    fields, students = read(path)
    first = first_terms(college)
    cohorts_moved = terms_moved = 0
    for row in students:
        if row["Currently Enrolled"] == "Yes" and row["Last Enrolled Term"] != row["Reference Term"]:
            row["Last Enrolled Term"] = row["Reference Term"]
            terms_moved += 1
            # pdp_year is derived from the last term, so moving one has to restate the other
            # or the two columns start contradicting each other.
            if "pdp_year" in row:
                row["pdp_year"] = cohort_label(academic_year(row["Last Enrolled Term"]))
        last = row["Last Enrolled Term"]
        if academic_year(last) < int(row["Cohort"][:4]):
            start = academic_year(first.get(row["Student GUID"], last))
            row["Cohort"] = cohort_label(start)
            cohorts_moved += 1
    write(path, fields, students)
    return cohorts_moved, terms_moved


def main() -> None:
    """Repair both colleges and report what moved."""
    for college in ("cmc", "college_two"):
        cohorts, terms = repair(college)
        print(f"{college}: {cohorts} cohorts moved, {terms} last terms moved (synthetic)")


if __name__ == "__main__":
    main()
