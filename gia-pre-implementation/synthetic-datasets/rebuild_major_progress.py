"""Rewrite each synthetic student's major progress from the college's real catalog requirements.

For both colleges, recomputes the progress columns in students.csv (courses and credits required, applied and
remaining, and the major's course list) and the Requirement Area of each enrollment in course_detail.csv, with
the rule in measures/major_requirements.py. College 2 students' Target Program is first changed from a synthetic
pathway to the real program it maps to in college_two/csv/pathway_program_map.csv.

Demo Scenario, Credential Earned and validation.json are left alone: they record how the generator made each
student's courses, not where the student stands now.

Running it twice changes nothing the second time (git diff shows no change).

Usage (from the repo root):
    python gia-pre-implementation/synthetic-datasets/rebuild_major_progress.py
"""

import csv
import io
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit("rebuild_major_progress needs Python 3.10 or newer. Activate the repo's .venv first.")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))  # the repo root, so measures/ imports

from measures import major_requirements as rules  # noqa: E402

# Enrollment areas the rebuild owns. Gateway and current-term labels say something else and are kept.
PROGRAM_CORE = "Program core"
OTHER_COURSE = "Additional coursework"
REBUILT_AREAS = {PROGRAM_CORE, OTHER_COURSE, "Synthetic pathway"}

# Which students.csv column holds each piece of progress, per college.
COLUMNS = {
    "cmc": {
        "major": "Degree Program (Major)",
        "courses_required": "Total Major Courses Required",
        "courses_done": "Major Courses Completed",
        "courses_left": "Major Courses Remaining",
        "remaining_codes": "Courses Remaining (Codes)",
        "units_left": "Units Remaining",
        "units_applied": "Credits Applied to Program",
    },
    "college_two": {
        "major": "Target Program",
        "courses_required": "Total Major Courses Required",
        "courses_done": "Major Courses Completed",
        "courses_left": "Courses Remaining Count",
        "remaining_codes": "Remaining Required Courses",
        "units_left": "Credits Remaining",
        "units_applied": "Credits Applied to Program",
    },
}
SCOPE = {
    "cmc": "2025-26 catalog major requirements; general education not included; not full degree eligibility",
    "college_two": (
        "2026-27 catalog major requirements of the mapped program; general education not included; "
        "courses were generated for a synthetic pathway"
    ),
}


def read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Column names and rows of a UTF-8 CSV with a BOM."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames), list(reader)


def write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    """Write rows back the way the files are stored: BOM, LF line endings, minimal quoting."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(out.getvalue(), encoding="utf-8-sig", newline="")


def number(value: float) -> str:
    """Units the way the files write them: 13.0, 22.5, 1.25."""
    return str(float(value))


def college_two_programs() -> dict[str, str]:
    """Synthetic pathway -> the real program's award_type it maps to."""
    _, rows = read(HERE / "college_two" / "csv" / "pathway_program_map.csv")
    return {row["target_program"]: row["award_type"] for row in rows}


def rebuild(college: str) -> None:
    """Recompute one college's progress columns and enrollment areas."""
    folder = HERE / college / "csv"
    columns = COLUMNS[college]
    majors = rules.cmc_majors() if college == "cmc" else rules.college_two_majors()
    code_of = (lambda code, m=rules.cmc_code_map(): m.get(code, code)) if college == "cmc" else (lambda code: code)
    renamed = college_two_programs() if college == "college_two" else {}

    student_fields, students = read(folder / "students.csv")
    course_fields, enrollments = read(folder / "course_detail.csv")
    passed = rules.passed_courses(enrollments, code_of)

    lists = {}
    for student in students:
        # Keep the dashboard's short major name. Credits are figured on the catalog award it stands for.
        label = renamed.get(student[columns["major"]], student[columns["major"]])
        major = rules.college_two_award(label) if college == "college_two" else label
        if major not in majors:
            sys.exit(f"{college}: no catalog requirements for major {major!r}")
        done = rules.progress(majors[major], passed.get(student["Student GUID"], set()))
        student[columns["courses_required"]] = str(done.courses_required)
        student[columns["courses_done"]] = str(done.courses_done)
        student[columns["courses_left"]] = str(done.courses_left)
        student[columns["remaining_codes"]] = "; ".join(done.remaining_codes)
        student[columns["units_left"]] = number(done.units_left)
        student[columns["units_applied"]] = number(done.units_applied)
        student["program_required_courses"] = "; ".join(done.required_codes)
        student["Requirement Scope"] = SCOPE[college]
        lists[student["Student GUID"]] = set(done.required_codes)

    for row in enrollments:
        if row["Requirement Area"] in REBUILT_AREAS:
            on_list = code_of(row["Course Code"]) in lists.get(row["Student GUID"], set())
            row["Requirement Area"] = PROGRAM_CORE if on_list else OTHER_COURSE

    write(folder / "students.csv", student_fields, students)
    write(folder / "course_detail.csv", course_fields, enrollments)
    near = sum(1 for s in students if 0 < float(s[columns["units_left"]]) <= 9)
    print(f"{college}: {len(students)} students, {near} within 9 credits of their major (synthetic)")


def main() -> None:
    """Rebuild both colleges."""
    for college in ("cmc", "college_two"):
        rebuild(college)


if __name__ == "__main__":
    main()
