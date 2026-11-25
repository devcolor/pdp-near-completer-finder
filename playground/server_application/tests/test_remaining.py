"""Courses still owed carry the tries that did not clear them."""

from app.institution_dashboard import data


def test_a_failed_course_still_owed_counts_the_try() -> None:
    """A remaining course counts a fail that has to be taken again."""
    data.clear_read_cache()
    courses = [course for student in data._students("cmc") for course in student["remaining"]]
    failed = [course for course in courses if course["failed_attempts"] > 0]
    assert failed
    assert all(course["attempts"] >= course["failed_attempts"] for course in failed)
    assert any(course["next_offering"].startswith("Coming up") for course in courses)
    assert any(course["next_offering"].startswith("Next in") for course in courses)


def test_several_student_types_can_be_included_together() -> None:
    """The type filter takes every checked type, not only one."""
    data.clear_read_cache()
    one = data.build_dashboard(
        "cmc", "15", "COLC (regular)", "all", "all", "any", "any", "all", "all"
    )
    both = data.build_dashboard(
        "cmc", "15", "COLC (regular)|Adult learning", "all", "all", "any", "any", "all", "all"
    )
    everyone = data.build_dashboard("cmc", "15", "all", "all", "all", "any", "any", "all", "all")

    def total(body: data.DashboardResponse) -> int:
        """The student total on a dashboard."""
        return next(row.value for row in body.summary if row.id == "students")

    assert total(one) < total(both) < total(everyone)
    # The CVC type name itself contains a comma, so types are not split on commas.
    with_cvc = data.build_dashboard(
        "cmc",
        "15",
        "COLC (regular)|CVC (distance learner, other college)",
        "all",
        "all",
        "any",
        "any",
        "all",
        "all",
    )
    assert total(one) < total(with_cvc)
