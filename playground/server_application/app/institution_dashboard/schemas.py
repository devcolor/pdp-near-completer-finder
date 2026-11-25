"""Typed response for the CMC and College 2 institution dashboard."""

from typing import Literal

from pydantic import BaseModel, Field

Institution = Literal["college_two", "cmc"]
FlagFilter = Literal["any", "yes", "no"]


class SummaryRow(BaseModel):
    """One headline count for the selected institution and filters."""

    id: str
    label: str
    value: int


class RateRow(BaseModel):
    """A rate with its numerator and denominator. Both are null below 10 students."""

    id: str
    label: str
    count: int | None
    n: int | None
    rate: float | None


class TrendRow(BaseModel):
    """Near completers in two focus programs for one entry cohort."""

    cohort: str
    first_program: int
    second_program: int


class StopOutRow(BaseModel):
    """Stop-outs in one term, counted by the term they were last enrolled in."""

    term: str
    # How the term reads on screen, e.g. "24 Fall".
    label: str
    stop_outs: int


class PathwayTrendRow(BaseModel):
    """Credit-filter students in each academic pathway for one entry cohort."""

    cohort: str
    counts: dict[str, int]


class MajorRow(BaseModel):
    """One STEM major inside the current credit filter."""

    program: str
    count: int


class ProgramCount(BaseModel):
    """Students in one major inside the current credit filter."""

    program: str
    count: int


class CourseBlocker(BaseModel):
    """A math course still unfinished by students in the credit filter."""

    course_code: str
    course_title: str
    students: int


class AttributeRow(BaseModel):
    """A context share among the credit-filter students, hidden below 10 students."""

    attribute: str
    count: int | None
    n: int | None
    rate: float | None


class CourseSection(BaseModel):
    """One scheduled meeting of a course."""

    section: str
    instructor: str
    meeting_day: str
    meeting_time: str
    location: str


class RemainingCourse(BaseModel):
    """One unfinished major course, and how many times the student has tried it."""

    course_code: str
    course_title: str
    terms_offered: str
    attempts: int
    failed_attempts: int
    next_offering: str
    sections: list[CourseSection]


class StudentRow(BaseModel):
    """One outreach row. The files have student IDs, not names."""

    student_id: str
    program: str
    student_type: str
    campus_location: str
    credits_remaining: float
    credits_applied: float
    currently_enrolled: bool
    registration_hold: bool
    hold_type: str
    parent: bool
    employment: str
    remaining: list[RemainingCourse]


class BlockingCourse(BaseModel):
    """A course these students still owe, and what makes it hard to finish."""

    course_code: str
    course_title: str
    students: int
    terms_offered: str
    season_locked: bool
    withdraw_rate: float | None
    fail_rate: float | None
    high_dfw: bool


class PathwayDetail(BaseModel):
    """One pathway on its own: the majors inside it and the courses holding its students up."""

    pathway: str
    majors: list[ProgramCount]
    students: int
    near: int
    stop_outs: int
    blocking_courses: list[BlockingCourse]


class MajorDetail(BaseModel):
    """Who is in one major, and which remaining courses hold them up."""

    major: str
    pathway: str
    students: int
    near: int
    stop_outs: int
    attributes: list[AttributeRow]
    blocking_courses: list[BlockingCourse]


class DashboardMeta(BaseModel):
    """How to read the response. Counts come from the synthetic institution files."""

    title: str
    description: str
    filters: list[str]
    definitions: dict[str, str]
    source: Literal["synthetic"] = "synthetic"


class TermOption(BaseModel):
    """A term the filters can select: the value the API takes, and how it reads on screen."""

    value: str
    label: str


class StopOutTile(BaseModel):
    """One executive headline: a stop-out count, with the filter it was counted under."""

    id: str
    label: str
    # Already formatted, because a tile's headline is not always a number.
    headline: str
    note: str


class DashboardResponse(BaseModel):
    """Stop-outs, near completers, and an outreach list for one institution."""

    meta: DashboardMeta
    institution: Institution
    institution_label: str
    credit_threshold: str
    student_types: list[str]
    campus_locations: list[str]
    programs: list[str]
    first_program_label: str
    second_program_label: str
    summary: list[SummaryRow]
    rates: list[RateRow]
    trend: list[TrendRow]
    pathway_trend: list[PathwayTrendRow]
    majors: list[MajorRow]
    academic: list[AttributeRow]
    academic_blocked: int
    stop_out_basis: str
    stop_out_tiles: list[StopOutTile]
    # The term still in progress; students who left in it are not stop-outs yet.
    current_term: str
    # The same term as it reads on screen, so prose matches the axis and the filters.
    current_term_label: str
    terms: list[TermOption]
    term_from: str
    term_to: str
    financial: list[AttributeRow]
    pathway_latest: list[ProgramCount]
    # Which population the pathway chart is counting: "stop_outs" or a credit threshold.
    pathway_credits: str
    pathway_majors: dict[str, list[ProgramCount]]
    pathway_major_trend: dict[str, list[PathwayTrendRow]]
    program_counts: list[ProgramCount]
    course_blockers: list[CourseBlocker]
    stop_outs: list[StopOutRow]
    attributes: list[AttributeRow]
    student_terms: list[TermOption]
    students: list[StudentRow] = Field(description="The first 40 outreach matches.")
    students_matched: int
    unavailable: list[str]
    using_upload: bool = False


class UploadFileRequirement(BaseModel):
    """One of the four files an upload must include, and the columns it has to have."""

    field: str
    filename: str
    purpose: str
    columns: list[str]


class SubmittedYear(BaseModel):
    """One PDP year present in the data, and who stopped appearing after the year before it."""

    year: str
    students: int
    # None for the earliest year: there is no prior year to have disappeared from.
    not_returning: int | None


class UploadRequirements(BaseModel):
    """What to upload for one college, and whether an upload is already in use."""

    institution: Institution
    using_upload: bool
    files: list[UploadFileRequirement]
    years: list[SubmittedYear]
    stop_out_basis: str
    # The executive summary figure, so the two pages can be tied together.
    stop_outs: int | None
    # Absent but already finished, which is why "did not return" runs higher than stop-outs.
    completed: int | None
