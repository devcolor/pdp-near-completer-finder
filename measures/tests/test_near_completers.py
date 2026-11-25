"""Checks the major requirements rule, the near completers measure, and both synthetic student datasets.

Run from the repo root: python -m pytest measures/tests/test_near_completers.py
The data is synthetic: these numbers are not findings about real students or either college.
"""
import sqlite3

import pytest

from measures import major_requirements as rules
from measures.calculations import near_completers
from measures.load_synthetic import CREATE, DATASETS, MAJOR_COLUMN, load
from measures.models import Cohort, ExclusionReason, GroupBy, GroupDimension, Measure, Status
from measures.run_measures import run_measure

COHORT = Cohort.of("2023-24")
LEFT_COLUMN = {"cmc": "Units Remaining", "college_two": "Credits Remaining"}


def group(rule, courses, **need):
    """A requirement group from (code, units) pairs, or a list of blocks for rule='blocks'."""
    options = tuple(tuple(block) for block in courses) if rule == "blocks" else (tuple(courses),)
    return rules.RequirementGroup("G", rule, options, **need)


# The rule: how many units a major still needs.

def test_every_course_group_needs_each_unpassed_course():
    major = [group("all", [("A 1", 3.0), ("A 2", 4.0)])]
    assert rules.progress(major, set()).units_left == 7.0
    assert rules.progress(major, {"A 1"}).units_left == 4.0
    assert rules.progress(major, {"A 1", "A 2"}).units_left == 0.0


def test_choice_group_counts_only_what_it_asks_for():
    # Asks for 6 units; passing 9 still only covers 6, and the extra can't pay for another group.
    major = [group("units", [("E 1", 3.0), ("E 2", 3.0), ("E 3", 3.0)], need_units=6.0), group("all", [("R 1", 3.0)])]
    done = rules.progress(major, {"E 1", "E 2", "E 3"})
    assert (done.units_required, done.units_left, done.units_applied) == (9.0, 3.0, 6.0)


def test_choose_courses_group_needs_the_smallest_open_courses():
    major = [group("courses", [("B 1", 5.0), ("B 2", 4.0), ("B 3", 5.0)], need_courses=1)]
    assert rules.progress(major, set()).units_left == 4.0
    assert rules.progress(major, {"B 3"}).units_left == 0.0


def test_alternative_blocks_take_the_closest_block():
    major = [group("blocks", [[("PH 2A", 4.0), ("PH 2B", 4.0)], [("PH 4A", 4.0), ("PH 4B", 4.0)]])]
    done = rules.progress(major, {"PH 4A"})
    assert (done.units_left, done.courses_left, done.remaining_codes) == (4.0, 1, ("PH 4B",))


@pytest.mark.parametrize("grade, passed", [
    ("2.0", True), ("3.7", True), ("P", True), ("p", True),
    ("1.9", False), ("1.0", False), ("0.0", False), ("F", False), ("W", False), ("I", False), ("", False), (None, False),
])
def test_a_pass_is_2_0_or_better_or_p(grade, passed):
    assert rules.is_pass(grade) is passed


def test_a_retake_that_passed_counts_once():
    rows = [
        {"Student GUID": "s1", "Course Code": "A 1", "Grade": "W"},
        {"Student GUID": "s1", "Course Code": "A 1", "Grade": "1.0"},
        {"Student GUID": "s1", "Course Code": "A 1", "Grade": "3.0"},
        {"Student GUID": "s2", "Course Code": "A 1", "Grade": "1.7"},
    ]
    assert rules.passed_courses(rows) == {"s1": {"A 1"}}


# The measure, on hand-built students.

def fixture_database(students):
    """A synthetic_student table holding (student_id, units_left, excluded, credential) rows, all in 2023-24."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(CREATE)
    connection.execute("INSERT INTO data_provider (source_file, file_sha256, loaded_at) VALUES ('fixture', 'x', '2026-11-10')")
    connection.executemany(
        "INSERT INTO synthetic_student (student_id, cohort, major, excluded_from_outreach, credential_earned, units_left) "
        "VALUES (?, '2023-24', 'BIOLOGY', ?, ?, ?)",
        [(sid, excluded, credential, left) for sid, left, excluded, credential in students],
    )
    return connection


# 0, 5, exactly 9 and 10 credits left; no requirements; a credential earner and a CVC student; 10 far from done.
STUDENTS = [
    ("zero", 0.0, 0, 0),
    ("five", 5.0, 0, 0),
    ("nine", 9.0, 0, 0),
    ("ten", 10.0, 0, 0),
    ("no_major", None, 0, 0),
    ("graduated", 3.0, 0, 1),
    ("cvc", 3.0, 1, 0),
] + [(f"far{n}", 20.0, 0, 0) for n in range(10)]


def everyone(results):
    """The everyone row."""
    return next(r for r in results if r.group.label == "everyone")


def test_near_completers_counts_more_than_0_and_at_most_9_left():
    row = everyone(run_measure(Measure.NEAR_COMPLETERS, [COHORT], database=fixture_database(STUDENTS)))
    # five and nine count. zero is done and ten is one over. 14 students have an answer.
    assert (row.numerator, row.denominator, row.status) == (2, 14, Status.OK)
    assert row.exclusions == {ExclusionReason.NO_REQUIREMENTS: 1}
    assert row.n_out_of_scope == 2
    assert "at most 9 credits" in row.note


def test_threshold_is_a_parameter():
    row = everyone(run_measure(Measure.NEAR_COMPLETERS, [COHORT], database=fixture_database(STUDENTS), threshold=10))
    assert row.numerator == 3
    assert "at most 10 credits" in row.note


@pytest.mark.parametrize("bad", [0, -3, "9; DROP TABLE x", True])
def test_threshold_must_be_a_positive_number(bad):
    with pytest.raises(ValueError):
        near_completers.student_sql(bad)


def test_other_measures_refuse_a_threshold_and_the_major_group():
    with pytest.raises(ValueError):
        run_measure(Measure.RETENTION, [COHORT], database=fixture_database(STUDENTS), threshold=9)
    with pytest.raises(ValueError):
        run_measure(Measure.RETENTION, [COHORT], [GroupBy.of(GroupDimension.MAJOR)], database=fixture_database(STUDENTS))


# Both synthetic datasets: CMC has 1,000 students, College 2 1,303.
STUDENT_COUNTS = {"cmc": 1000, "college_two": 1303}

@pytest.fixture(scope="module", params=["cmc", "college_two"])
def college(request):
    """Each college's loaded database, with its students.csv rows."""
    name = request.param
    students = rules.read_csv(DATASETS / name / "csv" / "students.csv")
    return name, load(name), students


def test_every_student_has_a_major_with_requirements(college):
    name, connection, students = college
    assert len(students) == STUDENT_COUNTS[name]
    assert connection.execute("SELECT COUNT(*) FROM synthetic_student WHERE units_left IS NULL").fetchone()[0] == 0


def test_stored_credits_left_agree_with_the_rule(college):
    # students.csv (which the dashboard reads) must match a fresh calculation, so rerun
    # rebuild_major_progress.py after changing the rule or the data.
    name, connection, students = college
    computed = dict(connection.execute("SELECT student_id, units_left FROM synthetic_student"))
    stale = [s["Student GUID"] for s in students if float(s[LEFT_COLUMN[name]]) != computed[s["Student GUID"]]]
    assert stale == []



def test_students_are_on_real_programs(college):
    name, _, students = college
    if name != "college_two":
        pytest.skip("CMC majors were already real")
    assert not [s for s in students if "synthetic pathway" in s[MAJOR_COLUMN[name]]]


def test_measure_runs_by_major_on_the_dataset(college):
    _, connection, _ = college
    cohorts = [Cohort.of(c) for (c,) in connection.execute("SELECT DISTINCT cohort FROM synthetic_student ORDER BY 1")]
    results = run_measure(Measure.NEAR_COMPLETERS, cohorts, [GroupBy.of(GroupDimension.MAJOR)], database=connection)
    shown = [r for r in results if r.status == Status.OK]
    assert shown, "every row was hidden"
    for row in results:
        assert row.status in (Status.OK, Status.SUPPRESSED)
