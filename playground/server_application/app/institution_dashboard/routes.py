"""HTTP API for the CMC and College 2 institution dashboard."""

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from .data import (
    PATHWAY_ALL,
    build_dashboard,
    build_major_detail,
    build_pathway_detail,
    parse_credits,
)
from .schemas import (
    DashboardResponse,
    FlagFilter,
    Institution,
    MajorDetail,
    PathwayDetail,
    UploadRequirements,
)
from .uploads import (
    DATASETS,
    column_problems,
    forget_year,
    requirements,
    restore_synthetic,
    save_datasets,
    year_problems,
)

router = APIRouter()


def _checked_credits(value: str) -> str:
    """Reject a credit selection with its own message, not the generic filter one."""
    try:
        parse_credits(value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Unsupported credit threshold.") from error
    return value


@router.get("/dashboard")
async def dashboard(
    institution: Annotated[Institution, Query()] = "cmc",
    credit_threshold: Annotated[str, Query()] = PATHWAY_ALL,
    student_type: Annotated[str, Query()] = "all",
    campus_location: Annotated[str, Query()] = "all",
    program: Annotated[str, Query()] = "all",
    hold: Annotated[FlagFilter, Query()] = "any",
    parent: Annotated[FlagFilter, Query()] = "any",
    term_from: Annotated[str, Query()] = "all",
    term_to: Annotated[str, Query()] = "all",
    pathway_credits: Annotated[str, Query()] = PATHWAY_ALL,
    student_term: Annotated[str, Query()] = "all",
) -> DashboardResponse:
    """Return synthetic stop-out, near-completer, and outreach rows."""
    try:
        return build_dashboard(
            institution,
            _checked_credits(credit_threshold),
            student_type,
            campus_location,
            program,
            hold,
            parent,
            term_from,
            term_to,
            pathway_credits,
            student_term=student_term,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=422, detail="Unknown filter for this institution."
        ) from error


@router.get("/dashboard/major")
async def dashboard_major(
    major: Annotated[str, Query()],
    institution: Annotated[Institution, Query()] = "cmc",
    credit_threshold: Annotated[str, Query()] = PATHWAY_ALL,
    student_type: Annotated[str, Query()] = "all",
    campus_location: Annotated[str, Query()] = "all",
) -> MajorDetail:
    """Return one major's student mix and the courses holding them up."""
    try:
        return build_major_detail(
            institution, _checked_credits(credit_threshold), student_type, campus_location, major
        )
    except ValueError as error:
        raise HTTPException(
            status_code=422, detail="Unknown filter for this institution."
        ) from error


@router.get("/dashboard/pathway")
async def dashboard_pathway(
    pathway: Annotated[str, Query()],
    institution: Annotated[Institution, Query()] = "cmc",
    credit_threshold: Annotated[str, Query()] = PATHWAY_ALL,
    student_type: Annotated[str, Query()] = "all",
    campus_location: Annotated[str, Query()] = "all",
) -> PathwayDetail:
    """One pathway's majors and the courses holding its students up."""
    try:
        return build_pathway_detail(
            institution, _checked_credits(credit_threshold), student_type, campus_location, pathway
        )
    except ValueError as error:
        raise HTTPException(
            status_code=422, detail="Unknown filter for this institution."
        ) from error


@router.get("/uploads/requirements")
async def upload_requirements(
    institution: Annotated[Institution, Query()] = "cmc",
) -> UploadRequirements:
    """The four files for one college and the columns each one has to include."""
    return requirements(institution)


@router.post("/uploads")
async def upload_datasets(
    institution: Annotated[Institution, Query()],
    students: Annotated[UploadFile, File()],
    profile: Annotated[UploadFile, File()],
    course_schedule: Annotated[UploadFile, File()],
    course_detail: Annotated[UploadFile, File()],
) -> dict[str, bool]:
    """Replace one college's four files when every required column is present."""
    incoming = {
        "students.csv": students,
        "student_institutional_profile.csv": profile,
        "course_schedule.csv": course_schedule,
        "course_detail.csv": course_detail,
    }
    contents: dict[str, bytes] = {}
    problems: list[str] = []
    expected = {item.filename: item.columns for item in requirements(institution).files}
    for _field, filename, _purpose in DATASETS:
        content = await incoming[filename].read()
        contents[filename] = content
        problem = column_problems(filename, content, expected[filename])
        if problem:
            problems.append(problem)
        elif filename == "students.csv":
            year_problem = year_problems(filename, content)
            if year_problem:
                problems.append(year_problem)
    if problems:
        raise HTTPException(status_code=422, detail=" ".join(problems))
    save_datasets(institution, contents)
    return {"saved": True}


@router.delete("/uploads")
async def delete_upload(
    institution: Annotated[Institution, Query()],
    year: Annotated[str | None, Query()] = None,
) -> dict[str, bool]:
    """Drop one submitted year, or the whole upload when no year is named."""
    if year:
        if not forget_year(institution, year):
            raise HTTPException(status_code=422, detail="That year is not in the saved upload.")
        return {"restored": False}
    restore_synthetic(institution)
    return {"restored": True}
