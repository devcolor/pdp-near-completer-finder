"""Near completers: the share of students who are a few credits from finishing their major.

Reads the synthetic_student table that load_synthetic.py builds for CMC or College 2. Credits left are the major's
catalog requirements the student hasn't passed (see major_requirements.py), not total degree units.
"""
from __future__ import annotations

from .sql_counts import cohort_values_sql, count_in_sql
from ..models import Cohort, Counts, ExclusionReason, Group, GroupDimension

THRESHOLD = 9  # credits left, at most, to count; run_measure(..., threshold=) changes it
SUPPORTED_OPEN_DIMENSIONS = frozenset({GroupDimension.MAJOR})


def note(threshold: float = THRESHOLD) -> str:
    """The row's definition, naming the threshold it was run with."""
    return (
        f"Students with more than 0 and at most {threshold:g} credits left on their major's requirements, out of "
        "students whose major has readable catalog requirements. Credits left are the major's required and "
        "choice-group units not yet passed (a C / 2.0 or better, or P); choice groups count only up to what they "
        "ask for, and general education is not included. Catalogs: CMC 2025-26, College 2 2026-27. Students who earned "
        "a credential, and CVC students taking a class from another college, are outside the measure. "
        "Synthetic data: not a finding about real students."
    )


NOTE = note()


def student_sql(threshold: float = THRESHOLD) -> str:
    """One row per student, in the shape count_in_sql expects."""
    # The threshold is written into the query, so only a plain positive number is accepted.
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not threshold > 0:
        raise ValueError("threshold must be a number above 0")
    out_of_scope = "s.excluded_from_outreach = 1 OR s.credential_earned = 1"
    answered = f"NOT ({out_of_scope}) AND s.units_left IS NOT NULL"
    return f"""
SELECT s.student_id AS student_id,
       s.cohort AS cohort,
       CASE WHEN {out_of_scope} THEN 0 ELSE 1 END AS in_scope,
       CASE WHEN {answered} THEN 1 ELSE 0 END AS has_answer,
       CASE WHEN {answered} AND s.units_left > 0 AND s.units_left <= {float(threshold)} THEN 1 ELSE 0 END AS achieved,
       '{ExclusionReason.NO_REQUIREMENTS.value}' AS exclusion_reason,
       s.race AS race,
       s.ethnicity AS ethnicity,
       s.gender AS gender,
       s.first_gen AS first_gen,
       s.age_band AS age_band,
       s.pell AS pell,
       s.enrollment_type AS enrollment_type,
       s.enrollment_intensity AS enrollment_intensity,
       s.cohort_term AS cohort_term,
       s.major AS major
FROM synthetic_student s
"""


def open_values(connection, dimension: GroupDimension, cohorts: list[Cohort]) -> list[str]:
    """The majors students in the requested cohorts are on."""
    if dimension != GroupDimension.MAJOR:
        raise ValueError(f"near_completers has no values to find for {dimension.value}")
    cursor = connection.cursor()
    cursor.execute(
        f"WITH cohort_numbers(cohort, cohort_no) AS (VALUES {cohort_values_sql(cohorts)}) "
        "SELECT DISTINCT s.major FROM synthetic_student s JOIN cohort_numbers c ON c.cohort = s.cohort "
        "WHERE s.major IS NOT NULL ORDER BY s.major"
    )
    return [row[0] for row in cursor.fetchall()]


def count(connection, cohorts: list[Cohort], groups: list[Group], threshold: float = THRESHOLD) -> dict[tuple[Cohort, Group], Counts]:
    """Count near completers for every cohort and group."""
    return count_in_sql(connection, student_sql(threshold), cohorts, groups)
