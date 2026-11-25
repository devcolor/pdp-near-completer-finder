"""Loads one college's synthetic student dataset (CMC or College 2) into SQLite for the near completers measure.

Each college is its own database, the way each institution runs the measures on its own data. The data files
are only read. One table, synthetic_student, holds a row per student: their cohort, group values, major and
the units left on it, worked out from course_detail.csv with the rule in major_requirements.py.

Usage (from the repo root): python -m measures.load_synthetic cmc
"""
from __future__ import annotations

import hashlib
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import major_requirements as rules

DATASETS = rules.REPO / "gia-pre-implementation" / "synthetic-datasets"
OUTPUT = Path(__file__).parent / "output"
COLLEGES = ("cmc", "college_two")

# students.csv column for each group value. College 2 has no ethnicity column, so it loads as blank (UNKNOWN).
GROUP_COLUMNS = {
    "race": "Race",
    "ethnicity": "Ethnicity",
    "gender": "Gender",
    "first_gen": "First Gen",
    "pell": "Pell Status First Year",
    "age_band": "Student Age",
    "enrollment_type": "Enrollment Type",
    "enrollment_intensity": "Enrollment Intensity First Term",
    "cohort_term": "Cohort Term",
}
MAJOR_COLUMN = {"cmc": "Degree Program (Major)", "college_two": "Target Program"}

CREATE = f"""
CREATE TABLE data_provider (provider_id INTEGER PRIMARY KEY, source_file TEXT, file_sha256 TEXT, loaded_at TEXT);
CREATE TABLE synthetic_student (
    student_id TEXT PRIMARY KEY,
    cohort TEXT,
    major TEXT,
    excluded_from_outreach INTEGER,
    credential_earned INTEGER,
    units_left REAL,
    {", ".join(f"{name} TEXT" for name in GROUP_COLUMNS)}
);
"""


def is_true(value: str | None) -> bool:
    """The synthetic files write flags as True, TRUE or Yes."""
    return (value or "").strip().lower() in {"true", "yes"}


def sha256(path: Path) -> str:
    """The file's SHA-256, so a result can say exactly which data it came from."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(college: str, database: str | Path = ":memory:") -> sqlite3.Connection:
    """Build the college's database and return an open connection to it."""
    if college not in COLLEGES:
        raise ValueError(f"college must be one of {COLLEGES}")
    folder = DATASETS / college / "csv"
    majors = rules.cmc_majors() if college == "cmc" else rules.college_two_majors()
    code_map = rules.cmc_code_map() if college == "cmc" else {}
    students = rules.read_csv(folder / "students.csv")
    passed = rules.passed_courses(rules.read_csv(folder / "course_detail.csv"), lambda code: code_map.get(code, code))

    connection = sqlite3.connect(database)
    connection.executescript(CREATE)
    loaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for name in ("students.csv", "course_detail.csv"):
        path = folder / name
        connection.execute(
            "INSERT INTO data_provider (source_file, file_sha256, loaded_at) VALUES (?, ?, ?)",
            (path.relative_to(rules.REPO).as_posix(), sha256(path), loaded_at),
        )
    connection.executemany(
        f"INSERT INTO synthetic_student VALUES ({', '.join('?' * (6 + len(GROUP_COLUMNS)))})",
        [student_row(college, student, majors, passed) for student in students],
    )
    connection.commit()
    return connection


def student_row(college: str, student: dict[str, str], majors: dict, passed: dict[str, set[str]]) -> tuple:
    """One synthetic_student row. units_left is blank when the major has no readable requirements."""
    major = student[MAJOR_COLUMN[college]]
    lookup = rules.college_two_award(major) if college == "college_two" else major
    groups = majors.get(lookup)
    units_left = rules.progress(groups, passed.get(student["Student GUID"], set())).units_left if groups else None
    return (
        student["Student GUID"],
        student["Cohort"],
        major,
        int(is_true(student["excluded_from_outreach"])),
        int(is_true(student.get("Credential Earned"))),
        units_left,
        *(student.get(column) or None for column in GROUP_COLUMNS.values()),
    )


def main() -> None:
    """Write measures/output/synthetic_<college>.sqlite for the colleges named, or both."""
    OUTPUT.mkdir(exist_ok=True)
    for college in sys.argv[1:] or COLLEGES:
        path = OUTPUT / f"synthetic_{college}.sqlite"
        path.unlink(missing_ok=True)
        load(college, path).close()
        print(f"{college}: wrote {path}")


if __name__ == "__main__":
    main()
