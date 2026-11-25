"""Aggregate the synthetic College 2 and CMC files for the institution dashboard."""

import csv
from collections import defaultdict
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from app.core.config import SERVER_ROOT, settings

from .schemas import (
    AttributeRow,
    BlockingCourse,
    CourseBlocker,
    CourseSection,
    DashboardMeta,
    DashboardResponse,
    Institution,
    MajorDetail,
    MajorRow,
    PathwayDetail,
    PathwayTrendRow,
    ProgramCount,
    RateRow,
    RemainingCourse,
    StopOutRow,
    StopOutTile,
    StudentRow,
    SummaryRow,
    TermOption,
    TrendRow,
)

REPO_DATA_ROOT = SERVER_ROOT.parents[1] / "gia-pre-implementation" / "synthetic-datasets"
# DASHBOARD_DATA_DIR lets a deploy (Vercel) bundle the CSVs inside the server folder.
DATA_ROOT = SERVER_ROOT / (settings.DASHBOARD_DATA_DIR or REPO_DATA_ROOT)
UPLOAD_ROOT = (
    Path(settings.DASHBOARD_UPLOAD_DIR) if settings.DASHBOARD_UPLOAD_DIR else DATA_ROOT / "uploads"
)
# The pathway chart's default: every stop-out, not a credit band.
PATHWAY_ALL = "stop_outs"

THRESHOLDS = (0, 3, 6, 9, 12, 15, 24)
STEM_PROGRAMS = {
    "ALTERNATIVE FUEL VEHICLES",
    "BIOLOGY",
    "Building Construction",
    "COMPUTER NETWORK",
    "COMPUTER SCIENCE",
    "Computer Information Systems",
    "REGISTERED NURSING",
    "Welding",
}


# Both colleges' pathways come from pathway_map.csv, so the mapping lives with the data
# rather than in two hardcoded dicts here. College 2 groups four degrees under Professional
# Vocational Technologies and fire science under Public Safety; the rest stand alone.
def _pathway_map(institution: Institution) -> tuple[tuple[str, ...], dict[str, str]]:
    """Return the institution's pathway names in order, and its major -> pathway lookup."""
    rows = [
        row for row in _read_csv(DATA_ROOT / "pathway_map.csv") if row["institution"] == institution
    ]
    names: list[str] = []
    for row in rows:
        if row["pathway"] not in names:
            names.append(row["pathway"])
    return tuple(names), {row["major"]: row["pathway"] for row in rows}


def _majors_of(institution: Institution, pathway: str) -> tuple[str, ...]:
    """The majors inside one pathway, in the order the map lists them."""
    return tuple(
        row["major"]
        for row in _read_csv(DATA_ROOT / "pathway_map.csv")
        if row["institution"] == institution and row["pathway"] == pathway
    )


MAJOR_WORDS = ("BIO", "COMPUTER", "MATH", "CIS")

# Student types this dashboard does not measure at all: they are not working towards a
# credential here, so leaving is not stopping out. Unlike CVC, these are not selectable
# either — they are dropped before the type filter is built.
OUT_OF_SCOPE_TYPES = ("Non-credit (MASP included)",)

SEASON_ORDER = {"Spring": 0, "Summer": 1, "Fall": 2}


def year_key(year: str) -> int:
    """Sort a PDP year like "2024-25" by the year it starts in."""
    start = year.split("-")[0]
    return int(start) if start.isdigit() else 0


def submitted_year_values(institution: Institution) -> list[str]:
    """Every PDP year present in this college's current students file, oldest first."""
    path = institution_folder(institution) / "students.csv"
    if not path.is_file():
        return []
    years = {row.get("pdp_year", "").strip() for row in _read_csv(path)}
    return sorted((year for year in years if year), key=year_key)


def in_scope_students(institution: Institution) -> list[dict]:
    """Students the dashboard will consider at all: out-of-scope types removed."""
    return [
        student
        for student in _students(institution)
        if student["student_type"] not in OUT_OF_SCOPE_TYPES
    ]


def measured_students(institution: Institution) -> list[dict]:
    """The students this dashboard counts by default: in scope, with CVC excluded."""
    return [student for student in in_scope_students(institution) if not student["excluded"]]


def stop_out_count(institution: Institution) -> int | None:
    """The dashboard's own stop-out figure, or None when one year cannot answer it.

    Runs the same rule over the same population as the executive tiles, so the Upload page
    cannot quote a different number.
    """
    if not is_multi_year(institution):
        return None
    # The in-progress term is read off every in-scope student, exactly as build_dashboard does,
    # so this figure cannot drift from the tile it is meant to match.
    current_term = _current_term(in_scope_students(institution))
    return sum(
        _is_stop_out(student, current_term, True) for student in measured_students(institution)
    )


def completed_count(institution: Institution) -> int | None:
    """Students absent from the newest year who had already finished their major.

    They did not come back because there was nothing left to come back for, so they are the
    gap between "did not return" and "stopped out".
    """
    if not is_multi_year(institution):
        return None
    return sum(
        student["absent_from_latest"] and student["credits_remaining"] <= 0
        for student in measured_students(institution)
    )


def measured_year_presence(institution: Institution) -> dict[str, set[str]]:
    """Which students appear in each PDP year, over the population the dashboard measures.

    Applies the dashboard's own exclusions — out-of-scope types and CVC — so the Upload page's
    per-year counts reconcile with the executive tiles instead of quietly disagreeing with them
    by counting raw file rows.
    """
    path = institution_folder(institution) / "students.csv"
    if not path.is_file():
        return {}
    per_year: dict[str, set[str]] = defaultdict(set)
    for row in _read_csv(path):
        year = row.get("pdp_year", "").strip()
        if not year or row.get("student_type", "") in OUT_OF_SCOPE_TYPES:
            continue
        if _is_true(row.get("excluded_from_outreach", "")):
            continue
        per_year[year].add(row["Student GUID"])
    return dict(per_year)


def is_multi_year(institution: Institution) -> bool:
    """True when stop-outs can be read from who disappeared between submitted years.

    Both halves matter. The synthetic file has eight distinct pdp_year values but is a
    snapshot with one row per student, so presence and absence would mark nearly everyone a
    stop-out; only an uploaded set is a real year-by-year submission.
    """
    return has_upload(institution) and len(submitted_year_values(institution)) >= 2


def stop_out_basis(institution: Institution) -> str:
    """Which rule produced this college's stop-out numbers, in words a reader can check."""
    years = submitted_year_values(institution)
    if is_multi_year(institution):
        return f"Absent from {years[-1]}, the most recent year submitted"
    return "Not enrolled, with credits still left on the major"


def term_key(term: str) -> tuple[int, int]:
    """Sort a term like "Fall 2024" by year, then by season within the year."""
    parts = term.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return (0, 0)
    season, year = parts
    return (int(year), SEASON_ORDER.get(season, 0))


def _current_term(students: list[dict]) -> str:
    """The latest term anyone in the file was enrolled in: the term still in progress."""
    terms = [student["last_term"] for student in students if student["last_term"]]
    return max(terms, key=term_key) if terms else ""


def term_label(term: str) -> str:
    """How a term reads on screen: its own calendar year, then the season.

    Every term here sits inside one calendar year, so none of them carry a span. The academic
    year that spans two ("2024-25") is a separate idea, kept in pdp_year. An intersession
    running December into January would be the term that genuinely crosses the boundary, and
    these files contain none.
    """
    parts = term.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return term
    season, year = parts[0], int(parts[1])
    return f"{year % 100:02d} {season}"


def academic_year_of(term: str) -> str:
    """The academic year a term sits in, as "2024-25". Fall starts the year.

    So Fall 2024 and Spring 2025 are the same year, which is what makes a share across them
    meaningless.
    """
    parts = term.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return ""
    season, year = parts[0], int(parts[1])
    start = year if season == "Fall" else year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def _stop_out_tiles(
    stopped: list[dict],
    credit_threshold: int | None,
    term_from: str,
    term_to: str,
    current_term: str,
) -> list[StopOutTile]:
    """The three executive headlines, all about stop-outs under the selected filters.

    Replaces the old tiles, which led with a raw student total and an enrolled count that
    said nothing about who needs calling.
    """
    total = len(stopped)
    matching = [student for student in stopped if _is_near(student, credit_threshold)]
    in_label = _near_label(credit_threshold)

    def share(count: int) -> str:
        """The count as a share of the stop-outs in range, which is what the tile divides by."""
        if not total:
            return "No stop-outs in this range"
        return f"{round(count / total * 1000) / 10}% of stop-outs in range"

    # Which term lost the most students, so staff know when to be ready.
    per_term: dict[str, int] = {}
    for student in stopped:
        per_term[student["last_term"]] = per_term.get(student["last_term"], 0) + 1
    peak = None
    if per_term:
        peak = max(per_term.items(), key=lambda pair: (pair[1], term_key(pair[0])))

    span = (
        f"students, last enrolled in {term_label(term_from)}"
        if term_from == term_to
        else f"students last enrolled between {term_label(term_from)} and {term_label(term_to)}"
    )
    in_progress = (
        f". {term_label(current_term)} is in progress and not counted yet" if current_term else ""
    )
    return [
        StopOutTile(
            id="stop_outs",
            label="Stopped out",
            headline=f"{total:,}",
            note=span + in_progress,
        ),
        # With no credit band selected this tile is every stop-out at 100%, which tells a
        # reader nothing, so it only appears once a band narrows the group.
        *(
            []
            if credit_threshold is None
            else [
                StopOutTile(
                    id="near_stop_outs",
                    label=in_label,
                    headline=f"{len(matching):,}",
                    note=share(len(matching)),
                )
            ]
        ),
        StopOutTile(
            id="peak_term",
            label="Term with the most stop-outs",
            headline=term_label(peak[0]) if peak else "—",
            # A share is only worth printing when the range holds more than one academic year:
            # with one year loaded the peak term is nearly all of it by construction.
            note=(
                f"{peak[1]:,} students left that term"
                + (
                    f", {share(peak[1]).split(' of ')[0]} of the range"
                    if len({academic_year_of(term) for term in per_term}) > 1
                    else f". The range covers one academic year, {academic_year_of(peak[0])}"
                )
            )
            if peak
            else "No stop-outs in this range",
        ),
    ]


def parse_credits(value: str) -> int | None:
    """A credit selection as a threshold, or None for "all stop-outs" with no credit band."""
    if value == PATHWAY_ALL:
        return None
    if value.isdigit() and int(value) in THRESHOLDS:
        return int(value)
    raise ValueError(value)


def build_dashboard(
    institution: Institution,
    credit_threshold: str,
    student_type: str,
    campus_location: str,
    program: str,
    hold: str,
    parent: str,
    term_from: str,
    term_to: str,
    # The pathway chart's own population, independent of the page-level credit threshold.
    pathway_credits: str = PATHWAY_ALL,
    student_term: str = "all",
) -> DashboardResponse:
    """Build stop-out, near-completer, and outreach rows for one institution."""
    students = [
        student
        for student in _students(institution)
        if student["student_type"] not in OUT_OF_SCOPE_TYPES
    ]
    types = sorted({student["student_type"] for student in students})
    locations = sorted({student["campus_location"] for student in students})
    chosen = [student for student in students if _chosen(student, student_type, campus_location)]
    if not _types_known(student_type, set(types)):
        raise ValueError(student_type)
    if campus_location != "all" and campus_location not in locations:
        raise ValueError(campus_location)
    programs = sorted({student["program"] for student in chosen})
    if program != "all" and program not in programs:
        raise ValueError(program)

    # CVC students look like stop-outs and are not. Leave them out unless that type is selected.
    left_out = [student for student in chosen if student_type == "all" and student["excluded"]]
    measured = [student for student in chosen if student not in left_out]
    # Taken from every in-scope student, so a narrow type or campus filter cannot move it.
    current_term = _current_term(students)
    multi_year = is_multi_year(institution)
    stopped_all = [
        student for student in measured if _is_stop_out(student, current_term, multi_year)
    ]
    stopped = list(stopped_all)
    pending = [student for student in measured if _is_pending(student, current_term, multi_year)]

    threshold = parse_credits(credit_threshold)
    # No band selected means the whole outreach population: every stop-out.
    near = (
        stopped_all
        if threshold is None
        else [student for student in measured if _is_near(student, threshold)]
    )

    # The time range is about when a student left, so it filters stop-outs only. Applying it
    # to everyone would empty the near-completer sections: students still enrolled all carry
    # the current term as their last one.
    terms = sorted(
        {student["last_term"] for student in stopped if student["last_term"]}, key=term_key
    )
    term_from = term_from if term_from != "all" else (terms[0] if terms else "")
    term_to = term_to if term_to != "all" else (terms[-1] if terms else "")
    for chosen_term in (term_from, term_to):
        if chosen_term and chosen_term not in terms:
            raise ValueError(chosen_term)
    if term_from and term_to and term_key(term_from) > term_key(term_to):
        term_from, term_to = term_to, term_from
    stopped = [
        student
        for student in stopped
        if not term_from
        or term_key(term_from) <= term_key(student["last_term"]) <= term_key(term_to)
    ]
    terms_in_range = [
        term
        for term in terms
        if not term_from or term_key(term_from) <= term_key(term) <= term_key(term_to)
    ]
    cohorts = sorted({student["cohort"] for student in measured})

    # The pathway chart carries its own population. It used to follow the page-level credit
    # threshold, which sits far above it on screen: a reader could not tell why the lines moved,
    # and at the default most pathways had no near-completers at all and sat flat on zero.
    if pathway_credits == PATHWAY_ALL:
        charted = stopped
    elif pathway_credits.isdigit() and int(pathway_credits) in THRESHOLDS:
        charted = [s for s in stopped if _is_near(s, int(pathway_credits))]
    else:
        raise ValueError(pathway_credits)
    first_program, second_program = _focus_programs(near)
    not_started = threshold == 0
    # Keep the available terms stable while the other Student Services filters change.
    student_terms = sorted(
        {student["last_term"] for student in students if student["last_term"]}, key=term_key
    )
    listed = [
        student
        for student in near
        if (student_term == "all" or student["last_term"] == student_term)
        and _matches(student, program, hold, parent)
    ]
    listed.sort(key=lambda student: (student["credits_remaining"], student["student_id"]))
    return DashboardResponse(
        using_upload=has_upload(institution),
        meta=_meta(
            institution,
            credit_threshold,
            student_type,
            campus_location,
            program,
            hold,
            parent,
        ),
        institution=institution,
        institution_label="College 2" if institution == "college_two" else "Copper Mountain",
        credit_threshold=credit_threshold,
        student_types=types,
        campus_locations=locations,
        programs=programs,
        first_program_label=_label(first_program),
        second_program_label=_label(second_program),
        summary=[
            SummaryRow(id="students", label="Students", value=len(chosen)),
            SummaryRow(id="left_out", label="CVC students excluded", value=len(left_out)),
            SummaryRow(
                id="near",
                label="Haven't started" if not_started else "Near completers",
                value=len(near),
            ),
            SummaryRow(id="stop_outs", label="Stop-outs", value=len(stopped)),
            SummaryRow(
                id="not_enrolled_this_term", label="Not enrolled this term", value=len(pending)
            ),
            SummaryRow(
                id="enrolled",
                label="Currently enrolled",
                value=sum(student["enrolled"] for student in measured),
            ),
        ],
        rates=[
            _rate(
                "stop_out_rate",
                "Stopped out",
                len(stopped),
                len(measured),
            ),
            _rate(
                "near_stop_out_rate",
                "Stop-outs who haven't started"
                if not_started
                else f"Stop-outs: {_near_label(threshold).lower()}",
                sum(_is_near(student, threshold) for student in stopped),
                len(stopped),
            ),
        ],
        trend=[
            TrendRow(
                cohort=cohort,
                first_program=_count(near, cohort, first_program),
                second_program=_count(near, cohort, second_program),
            )
            for cohort in cohorts
        ],
        pathway_trend=_pathway_trend(institution, charted, cohorts),
        majors=_majors(near),
        stop_out_basis=stop_out_basis(institution),
        stop_out_tiles=_stop_out_tiles(stopped, threshold, term_from, term_to, current_term),
        current_term=current_term,
        current_term_label=term_label(current_term),
        terms=[TermOption(value=term, label=term_label(term)) for term in terms],
        term_from=term_from,
        term_to=term_to,
        academic=_academic_rows(institution, measured),
        academic_blocked=_academic_blocked(institution, measured),
        financial=_financial_rows(measured, threshold),
        pathway_majors=_pathway_majors(institution, charted),
        pathway_major_trend=_pathway_major_trend(institution, charted, cohorts),
        pathway_latest=_pathway_latest(institution, measured, current_term),
        pathway_credits=pathway_credits,
        program_counts=_program_counts(near),
        course_blockers=_math_blockers(near),
        # By the term they left, not the year they arrived: the question on this page is when
        # students went, and the term range and peak-term tile above it are both on that axis.
        stop_outs=[
            StopOutRow(
                term=term,
                label=term_label(term),
                stop_outs=sum(student["last_term"] == term for student in stopped),
            )
            for term in terms_in_range
        ],
        attributes=[
            _attribute("Registration hold", near, lambda student: student["hold"]),
            _attribute("Parent", near, lambda student: student["parent"]),
            _attribute("Working", near, lambda student: student["working"]),
        ],
        student_terms=[TermOption(value=term, label=term_label(term)) for term in student_terms],
        students=[_student_row(student) for student in listed[:40]],
        students_matched=len(listed),
        unavailable=[
            "Student name",
            "State-funded special program",
            "Outreach status",
            "Assigned office (program counselors, financial aid, admissions and records)",
        ],
    )


def _students(institution: Institution) -> list[dict]:
    """Join one institution's student, profile, and course-schedule CSVs."""
    folder = institution_folder(institution)
    profiles = {
        row["student_id"]: row for row in _read_csv(folder / "student_institutional_profile.csv")
    }
    schedule = _schedule(folder / "course_schedule.csv")
    history, upcoming = _course_history(folder / "course_detail.csv")
    program_field = "Target Program" if institution == "college_two" else "Degree Program (Major)"
    credits_field = "Credits Remaining" if institution == "college_two" else "Units Remaining"
    remaining_field = (
        "Remaining Required Courses"
        if institution == "college_two"
        else "Courses Remaining (Codes)"
    )
    latest_year = (submitted_year_values(institution) or [""])[-1]
    # Several years means several rows per student. Keep the newest for their attributes, and
    # the set of years for the presence test that decides a stop-out.
    years_present: dict[str, set[str]] = defaultdict(set)
    newest: dict[str, dict[str, str]] = {}
    for row in _read_csv(folder / "students.csv"):
        guid = row["Student GUID"]
        year = row.get("pdp_year", "").strip()
        years_present[guid].add(year)
        held = newest.get(guid)
        if held is None or year_key(year) >= year_key(held.get("pdp_year", "").strip()):
            newest[guid] = row

    joined = []
    for row in newest.values():
        profile = profiles[row["Student GUID"]]
        employment = profile["employment_status"]
        seen = {year for year in years_present[row["Student GUID"]] if year}
        joined.append(
            {
                "years_present": sorted(seen, key=year_key),
                "last_year_present": max(seen, key=year_key) if seen else "",
                # Stop-out by absence: they are missing from the newest year submitted.
                "absent_from_latest": bool(seen) and latest_year not in seen,
                "student_id": row["Student GUID"],
                "cohort": row["Cohort"],
                "program": _label(row[program_field]),
                "student_type": row["student_type"],
                "campus_location": row["campus_location"],
                "excluded": _is_true(row["excluded_from_outreach"]),
                "credits_remaining": float(row[credits_field]),
                "credits_applied": float(row["Credits Applied to Program"]),
                "enrolled": row["Currently Enrolled"] == "Yes",
                # For a stop-out this is the term they left in.
                "last_term": row["Last Enrolled Term"].strip(),
                "hold": _is_true(profile["reg_hold_status"]),
                # Which office owns it: Financial, Academic or Advising.
                "hold_type": profile.get("hold_type", "").strip(),
                "parent": _is_true(profile["is_parent"]),
                "working": employment in {"Full-Time", "Part-Time"},
                "employment": employment,
                "remaining": _remaining(
                    row.get(remaining_field, ""),
                    schedule,
                    history.get(row["Student GUID"], {}),
                    upcoming,
                ),
            }
        )
    return joined


def _schedule(path: Path) -> dict[str, tuple[dict, ...]]:
    """Group course sections by course code."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in _read_csv(path):
        grouped[row["course_code"]].append(
            {
                "section": row["section"],
                "instructor": row["instructor"],
                "meeting_day": row["meeting_day"],
                "meeting_time": row["meeting_time"],
                "location": row["location"],
                "course_title": row["course_title"],
                "terms_offered": row["terms_offered"],
                "offering_pattern": row["offering_pattern"],
            }
        )
    return {
        code: tuple(sorted(sections, key=lambda section: section["section"]))
        for code, sections in grouped.items()
    }


def _course_history(path: Path) -> tuple[dict[str, dict[str, dict]], str]:
    """Finished tries per student and course, and the season after the in-progress term."""
    history: dict[str, dict[str, dict]] = {}
    in_progress_term = ""
    for row in _read_csv(path):
        slot = history.setdefault(row["Student GUID"], {}).setdefault(
            row["Course Code"],
            {"attempts": 0, "failed": 0, "in_progress": False},
        )
        if row["Status"] == "In Progress":
            slot["in_progress"] = True
            in_progress_term = row["Enrollment Term"]
            continue
        slot["attempts"] += 1
        # A D earns credit and still leaves the course unfinished when a C is required.
        if row["Status"] == "Not Passed" or _below_c(row["Grade"]):
            slot["failed"] += 1
    season = in_progress_term.split(" ", 1)[0]
    upcoming = "spring" if season == "Fall" else "fall"
    return history, upcoming


def _below_c(grade: str) -> bool:
    """True when a finished grade is below the C these programs require."""
    try:
        return float(grade) < 2.0
    except ValueError:
        return False


def _next_offering(terms: str, pattern: str, in_progress: bool, upcoming: str) -> str:
    """Whether the next term on the schedule is the one coming up."""
    if in_progress:
        return "In progress this fall" if upcoming == "spring" else "In progress this spring"
    if "alternate" in pattern:
        season = "spring" if "spring" in pattern else "fall"
        return f"Offered every other {season}"
    offered = {part.strip().lower() for part in terms.split(";") if part.strip()}
    if upcoming in offered:
        return f"Coming up in {upcoming}"
    if offered:
        return f"Next in {next(iter(offered))}"
    return "No section on the schedule"


def _remaining(
    codes: str,
    schedule: dict[str, tuple[dict, ...]],
    taken: dict[str, dict],
    upcoming: str,
) -> tuple[dict, ...]:
    """Attach each unfinished course to its tries, its next term, and its sections."""
    courses = []
    for code in [part.strip() for part in codes.split(";") if part.strip()]:
        sections = schedule.get(code, ())
        first = sections[0] if sections else {}
        record = taken.get(code, {"attempts": 0, "failed": 0, "in_progress": False})
        courses.append(
            {
                "course_code": code,
                "course_title": first.get("course_title", ""),
                "terms_offered": first.get("terms_offered", ""),
                "attempts": record["attempts"],
                "failed_attempts": record["failed"],
                "next_offering": _next_offering(
                    first.get("terms_offered", ""),
                    first.get("offering_pattern", ""),
                    record["in_progress"],
                    upcoming,
                ),
                "sections": [
                    {
                        "section": section["section"],
                        "instructor": section["instructor"],
                        "meeting_day": section["meeting_day"],
                        "meeting_time": section["meeting_time"],
                        "location": section["location"],
                    }
                    for section in sections
                ],
            }
        )
    return tuple(sorted(courses, key=lambda course: course["course_code"]))


def institution_folder(institution: str) -> Path:
    """The uploaded set for this college, or the synthetic files when none is saved."""
    override = UPLOAD_ROOT / institution
    if (override / "students.csv").is_file():
        return override
    return DATA_ROOT / institution / "csv"


def has_upload(institution: str) -> bool:
    """True when this college is reading a saved upload instead of the synthetic files."""
    return (UPLOAD_ROOT / institution / "students.csv").is_file()


def clear_read_cache() -> None:
    """Drop cached CSV rows so a new upload is read on the next request."""
    _read_csv_at.cache_clear()


def _read_csv(path: Path) -> tuple[dict[str, str], ...]:
    """Read one CSV, re-reading it whenever the file on disk has changed.

    The rows are cached per version of the file, so editing a synthetic CSV or saving an
    upload is picked up on the next request. Caching on the path alone meant a running
    server kept serving the rows it first read.
    """
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        stamp = 0
    return _read_csv_at(path, stamp)


@lru_cache(maxsize=16)
def _read_csv_at(path: Path, _stamp: int) -> tuple[dict[str, str], ...]:
    """Read one CSV and keep its original text values. Keyed by the file's timestamp."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return tuple(csv.DictReader(handle))


def _types_known(student_type: str, types: set[str]) -> bool:
    """True when the filter is everyone, or every named type exists."""
    if student_type == "all":
        return True
    chosen = [part for part in student_type.split("|") if part]
    return bool(chosen) and all(part in types for part in chosen)


def _chosen(student: dict, student_type: str, campus_location: str) -> bool:
    """Keep students in the selected types and campus. Several types are separated by |."""
    types = None if student_type == "all" else set(student_type.split("|"))
    return (types is None or student["student_type"] in types) and (
        campus_location == "all" or student["campus_location"] == campus_location
    )


def _is_near(student: dict, credit_threshold: int | None) -> bool:
    """Match near completers, or students who have not started the pathway."""
    # None is "no credit band": every student with credits still owed qualifies.
    if credit_threshold is None:
        return student["credits_remaining"] > 0
    if credit_threshold == 0:
        return student["credits_applied"] == 0
    remaining = student["credits_remaining"]
    return 0 < remaining <= credit_threshold


def _left_with_credits(student: dict, multi_year: bool = False) -> bool:
    """Left the college with credits still owed on the major.

    With several PDP years submitted, "left" means absent from the newest year: a student only
    appears in a year they were enrolled in. With one year there is nothing to compare against,
    so the enrollment flag stands in.

    Either way they must still owe credits. Absence alone is equally true of someone who
    finished, and a graduate does not belong on an outreach list.
    """
    if student["credits_remaining"] <= 0:
        return False
    if multi_year:
        return student["absent_from_latest"]
    return not student["enrolled"]


def _is_stop_out(student: dict, current_term: str, multi_year: bool = False) -> bool:
    """A stop-out left with credits remaining, in a term before the one still in progress."""
    return _left_with_credits(student, multi_year) and student["last_term"] != current_term


def _is_pending(student: dict, current_term: str, multi_year: bool = False) -> bool:
    """Left with credits remaining in the current term: not a stop-out until the term ends."""
    return _left_with_credits(student, multi_year) and student["last_term"] == current_term


def _program_counts(students: list[dict]) -> list[ProgramCount]:
    """Every pathway in the credit filter, largest first."""
    counts: dict[str, int] = {}
    for student in students:
        counts[student["program"]] = counts.get(student["program"], 0) + 1
    ranked = sorted(counts, key=lambda program: (-counts[program], program))
    return [ProgramCount(program=_label(program), count=counts[program]) for program in ranked]


def _focus_programs(near: list[dict]) -> tuple[str, str]:
    """Pick the two pathways with the most students in the credit filter."""
    counts: dict[str, int] = {}
    for student in near:
        counts[student["program"]] = counts.get(student["program"], 0) + 1
    ranked = sorted(counts, key=lambda program: (-counts[program], program))
    if not ranked:
        return "", ""
    if len(ranked) == 1:
        return ranked[0], ""
    return ranked[0], ranked[1]


def _pathway_trend(
    institution: Institution, students: list[dict], cohorts: list[str]
) -> list[PathwayTrendRow]:
    """Count credit-filter students in each published pathway by entry cohort."""
    names, pathway_of = _pathway_map(institution)
    rows = []
    for cohort in cohorts:
        counts = {name: 0 for name in names}
        for student in students:
            if student["cohort"] != cohort:
                continue
            # An unmapped major must not 500 the page; the route turns ValueError into a 422.
            name = pathway_of.get(_label(student["program"]))
            if name is None:
                continue
            counts[name] = counts.get(name, 0) + 1
        rows.append(PathwayTrendRow(cohort=cohort, counts=counts))
    return rows


def _pathway_majors(
    institution: Institution, students: list[dict]
) -> dict[str, list[ProgramCount]]:
    """The majors inside each pathway, with how many of these students each holds.

    Keyed on the pathway map, not on the students, so every pathway is present even when the
    count is zero. Dropping empty pathways is what let the chart offer a pathway the drill-down
    then had nothing to show for.
    """
    names, pathway_of = _pathway_map(institution)
    tally: dict[str, dict[str, int]] = {
        name: {major: 0 for major in _majors_of(institution, name)} for name in names
    }
    for student in students:
        major = _label(student["program"])
        pathway = pathway_of.get(major)
        if pathway is None:
            continue
        tally[pathway][major] = tally[pathway].get(major, 0) + 1
    return {
        pathway: [
            ProgramCount(program=major, count=count)
            for major, count in sorted(majors.items(), key=lambda item: (-item[1], item[0]))
        ]
        for pathway, majors in tally.items()
    }


def _pathway_latest(
    institution: Institution, students: list[dict], term: str
) -> list[ProgramCount]:
    """Students in each pathway who were enrolled in the latest term.

    Answers "who is here now", so it reads off every student rather than the chart's population.
    """
    names, pathway_of = _pathway_map(institution)
    counts = {name: 0 for name in names}
    for student in students:
        if not student["enrolled"] or (term and student["last_term"] != term):
            continue
        pathway = pathway_of.get(_label(student["program"]))
        if pathway is not None:
            counts[pathway] += 1
    return [ProgramCount(program=name, count=counts[name]) for name in names]


def _pathway_major_trend(
    institution: Institution, students: list[dict], cohorts: list[str]
) -> dict[str, list[PathwayTrendRow]]:
    """Per pathway, the same cohort trend but with one series per major inside it."""
    names, _pathway_of = _pathway_map(institution)
    out: dict[str, list[PathwayTrendRow]] = {}
    # Every pathway, not only those with students, so each one can be opened.
    for pathway in names:
        majors = _majors_of(institution, str(pathway))
        rows = []
        for cohort in cohorts:
            counts = {major: 0 for major in majors}
            for student in students:
                major = _label(student["program"])
                if student["cohort"] == cohort and major in counts:
                    counts[major] += 1
            rows.append(PathwayTrendRow(cohort=cohort, counts=counts))
        out[str(pathway)] = rows
    return out


DFW_MIN_ENROLMENTS = 15
DFW_HIGH = 0.30


@lru_cache(maxsize=4)
def _course_rates(institution: Institution) -> dict[str, tuple[float, float]]:
    """Withdraw rate and non-pass rate per course, kept apart.

    A course people drop and a course people fail are different problems, so the two are
    reported separately. Only courses with enough enrolments to mean anything are included.
    """
    totals: dict[str, list[int]] = {}
    for row in _read_csv(DATA_ROOT / institution / "csv" / "course_detail.csv"):
        seen, withdrew, failed = totals.setdefault(row["Course Code"], [0, 0, 0])
        totals[row["Course Code"]] = [
            seen + 1,
            withdrew + (row["Status"] == "Withdrawn"),
            failed + (row["Status"] == "Not Passed"),
        ]
    return {
        code: (round(withdrew / seen, 4), round(failed / seen, 4))
        for code, (seen, withdrew, failed) in totals.items()
        if seen >= DFW_MIN_ENROLMENTS
    }


def _blocking_courses(institution: Institution, students: list[dict]) -> list[BlockingCourse]:
    """Courses these students still owe, with what makes each one hard to finish."""
    rates = _course_rates(institution)
    tally: dict[str, dict] = {}
    for student in students:
        seen: set[str] = set()
        for course in student["remaining"]:
            code = course["course_code"]
            if code in seen:
                continue
            seen.add(code)
            row = tally.setdefault(
                code,
                {
                    "course_code": code,
                    "course_title": course["course_title"],
                    "terms_offered": course.get("terms_offered", ""),
                    "students": 0,
                },
            )
            row["students"] += 1
    out = []
    for row in tally.values():
        terms = row["terms_offered"]
        locked = bool(terms) and ";" not in terms
        pair = rates.get(row["course_code"])
        withdraw, fail = pair if pair else (None, None)
        out.append(
            BlockingCourse(
                course_code=row["course_code"],
                course_title=row["course_title"],
                students=row["students"],
                terms_offered=terms,
                season_locked=locked,
                withdraw_rate=withdraw,
                fail_rate=fail,
                # Flagged on the two together: either alone can look mild.
                high_dfw=pair is not None and (withdraw or 0) + (fail or 0) >= DFW_HIGH,
            )
        )
    out.sort(key=lambda row: (-row.students, row.course_code))
    return out[:12]


def _owes_high_dfw(student: dict, rates: dict[str, tuple[float, float]]) -> bool:
    """True when a student still owes a course most students withdraw from or do not pass."""
    return any(
        sum(rates.get(course["course_code"], (0.0, 0.0))) >= DFW_HIGH
        for course in student["remaining"]
    )


def _owes_season_locked(student: dict) -> bool:
    """True when a course this student still owes runs in only one term of the year."""
    return any(
        course["terms_offered"] and ";" not in course["terms_offered"]
        for course in student["remaining"]
    )


def _academic_rows(institution: Institution, students: list[dict]) -> list[AttributeRow]:
    """Each thing holding an academic student back, counted as its own named category.

    "Academic blocker" told a reader nothing on its own, so the categories are named instead:
    a hold this office can release, a course that runs in one term only, or a course most
    students withdraw from or fail.
    """
    rates = _course_rates(institution)
    return [
        _attribute("Academic hold", students, lambda s: s["hold_type"] == "Academic"),
        _attribute("Advising hold", students, lambda s: s["hold_type"] == "Advising"),
        _attribute("Limited course availability", students, _owes_season_locked),
        _attribute("Multiple attempts (DFW)", students, lambda s: _owes_high_dfw(s, rates)),
    ]


def _academic_blocked(institution: Institution, students: list[dict]) -> int:
    """How many students hit at least one academic blocker.

    Counted over students, not summed over the categories: one student can be held by a
    hold and a hard-to-get course at once, and should be called once.
    """
    rates = _course_rates(institution)
    return sum(
        student["hold_type"] in ("Academic", "Advising")
        or _owes_season_locked(student)
        or _owes_high_dfw(student, rates)
        for student in students
    )


def _near_label(credit_threshold: int | None) -> str:
    """How the selected credit filter reads in a row label.

    A row that said "near the end" never told the reader which cut-off was selected, and the
    cut-off is adjustable, so the label names it instead.
    """
    if credit_threshold is None:
        return "Still owing credits"
    if credit_threshold == 0:
        return "No credits earned yet"
    return f"Within {credit_threshold} credits of finishing"


def _financial_rows(students: list[dict], credit_threshold: int | None) -> list[AttributeRow]:
    """What a financial aid office would want counted among its own holds."""
    held = [student for student in students if student["hold_type"] == "Financial"]
    return [
        _attribute("Financial holds", students, lambda s: s["hold_type"] == "Financial"),
        _attribute("Not enrolled, with a financial hold", held, lambda s: not s["enrolled"]),
        _attribute(
            f"{_near_label(credit_threshold)}, with a financial hold",
            held,
            lambda s: _is_near(s, credit_threshold),
        ),
        _attribute("Working, with a financial hold", held, lambda s: s["working"]),
        _attribute("Parenting, with a financial hold", held, lambda s: s["parent"]),
    ]


def build_pathway_detail(
    institution: Institution,
    credit_threshold: str,
    student_type: str,
    campus_location: str,
    pathway: str,
) -> PathwayDetail:
    """One pathway on its own: its majors, and the courses its students still owe.

    The blocking courses cover the whole pathway, which is the question at this depth; the
    per-major view narrows to one major's courses.
    """
    names, pathway_of = _pathway_map(institution)
    if pathway not in names:
        raise ValueError(pathway)
    students = _students(institution)
    in_scope = [s for s in students if s["student_type"] not in OUT_OF_SCOPE_TYPES]
    current_term = _current_term(in_scope)
    chosen = [s for s in students if _chosen(s, student_type, campus_location)]
    measured = [s for s in chosen if not (student_type == "all" and s["excluded"])]
    multi_year = is_multi_year(institution)
    in_pathway = [s for s in measured if pathway_of.get(_label(s["program"])) == pathway]
    # Keyed on the map so a major with nobody in it still shows, rather than looking unoffered.
    tally = {major: 0 for major in _majors_of(institution, pathway)}
    for student in in_pathway:
        major = _label(student["program"])
        tally[major] = tally.get(major, 0) + 1
    return PathwayDetail(
        pathway=pathway,
        majors=[
            ProgramCount(program=major, count=count)
            for major, count in sorted(tally.items(), key=lambda item: (-item[1], item[0]))
        ],
        students=len(in_pathway),
        near=len([s for s in in_pathway if _is_near(s, parse_credits(credit_threshold))]),
        stop_outs=len([s for s in in_pathway if _is_stop_out(s, current_term, multi_year)]),
        blocking_courses=_blocking_courses(institution, in_pathway),
    )


def build_major_detail(
    institution: Institution,
    credit_threshold: str,
    student_type: str,
    campus_location: str,
    major: str,
) -> MajorDetail:
    """Who is in one major, and which remaining courses are hard to finish."""
    _names, pathway_of = _pathway_map(institution)
    if major not in pathway_of:
        raise ValueError(major)
    students = _students(institution)
    in_scope = [s for s in students if s["student_type"] not in OUT_OF_SCOPE_TYPES]
    current_term = _current_term(in_scope)
    chosen = [s for s in students if _chosen(s, student_type, campus_location)]
    measured = [s for s in chosen if not (student_type == "all" and s["excluded"])]
    in_major = [s for s in measured if _label(s["program"]) == major]
    near = [s for s in in_major if _is_near(s, parse_credits(credit_threshold))]
    return MajorDetail(
        major=major,
        pathway=pathway_of[major],
        students=len(in_major),
        near=len(near),
        stop_outs=len(
            [s for s in in_major if _is_stop_out(s, current_term, is_multi_year(institution))]
        ),
        attributes=[
            _attribute("Parenting", in_major, lambda s: s["parent"]),
            _attribute("Working", in_major, lambda s: s["working"]),
            _attribute("Registration hold", in_major, lambda s: s["hold"]),
            _attribute("Not enrolled", in_major, lambda s: not s["enrolled"]),
        ],
        blocking_courses=_blocking_courses(institution, near or in_major),
    )


def _majors(students: list[dict]) -> list[MajorRow]:
    """STEM majors in the credit filter, preferring math, biology, and computing."""
    counts: dict[str, int] = {}
    for student in students:
        if student["program"] not in STEM_PROGRAMS:
            continue
        counts[student["program"]] = counts.get(student["program"], 0) + 1
    named = {
        program: count
        for program, count in counts.items()
        if any(word in program.upper() for word in MAJOR_WORDS)
    }
    chosen = named or counts
    ranked = sorted(chosen, key=lambda program: (-chosen[program], program))
    return [MajorRow(program=program, count=chosen[program]) for program in ranked[:3]]


def _math_blockers(students: list[dict]) -> list[CourseBlocker]:
    """Math courses still unfinished by the most credit-filter students."""
    counts: dict[str, dict] = {}
    for student in students:
        seen: set[str] = set()
        for course in student["remaining"]:
            code = course["course_code"]
            if code in seen or not _is_math(course):
                continue
            seen.add(code)
            row = counts.setdefault(
                code, {"course_code": code, "course_title": course["course_title"], "students": 0}
            )
            row["students"] += 1
    ranked = sorted(counts.values(), key=lambda row: (-row["students"], row["course_code"]))
    return [CourseBlocker(**row) for row in ranked[:3]]


def _is_math(course: dict) -> bool:
    """A math course is a MATH code or a title that says math or calculus."""
    title = course["course_title"].upper()
    code = course["course_code"].upper()
    return code.startswith("MATH") or "MATH" in title or "CALCULUS" in title


def _count(students: list[dict], cohort: str, program: str) -> int:
    """Count credit-filter students in one cohort and focus program."""
    if not program:
        return 0
    return sum(
        student["cohort"] == cohort and student["program"] == program for student in students
    )


def _attribute(label: str, students: list[dict], predicate: Callable[[dict], bool]) -> AttributeRow:
    """Share of credit-filter students with one flag, hiding the rate below 10 students."""
    rated = _rate(label, label, sum(predicate(student) for student in students), len(students))
    return AttributeRow(attribute=label, count=rated.count, n=rated.n, rate=rated.rate)


def _rate(row_id: str, label: str, count: int, denominator: int) -> RateRow:
    """Return a rate, or nulls when fewer than 10 students are in the denominator."""
    suppressed = denominator < 10
    return RateRow(
        id=row_id,
        label=label,
        count=None if suppressed else count,
        n=None if suppressed else denominator,
        rate=None if suppressed else round(count / denominator, 4),
    )


def _matches(student: dict, program: str, hold: str, parent: str) -> bool:
    """Apply the outreach filters without changing the charts."""
    return (
        (program == "all" or student["program"] == program)
        and (hold == "any" or student["hold"] is (hold == "yes"))
        and (parent == "any" or student["parent"] is (parent == "yes"))
    )


def _student_row(student: dict) -> StudentRow:
    """Map one joined record to the outreach table."""
    return StudentRow(
        student_id=student["student_id"],
        program=student["program"],
        student_type=student["student_type"],
        campus_location=student["campus_location"],
        credits_remaining=student["credits_remaining"],
        credits_applied=student["credits_applied"],
        currently_enrolled=student["enrolled"],
        registration_hold=student["hold"],
        hold_type=student["hold_type"],
        parent=student["parent"],
        employment=student["employment"],
        remaining=[
            RemainingCourse(
                course_code=course["course_code"],
                course_title=course["course_title"],
                terms_offered=course["terms_offered"],
                attempts=course["attempts"],
                failed_attempts=course["failed_attempts"],
                next_offering=course["next_offering"],
                sections=[CourseSection(**section) for section in course["sections"]],
            )
            for course in student["remaining"]
        ],
    )


def _is_true(value: str) -> bool:
    """Accept the True and TRUE flags used across the synthetic files."""
    return value.strip().lower() == "true"


def _label(program: str) -> str:
    """Drop the synthetic-pathway suffix from a program name."""
    return program.removesuffix(" (synthetic pathway)")


def _meta(
    institution: Institution,
    credit_threshold: int,
    student_type: str,
    campus_location: str,
    program: str,
    hold: str,
    parent: str,
) -> DashboardMeta:
    """Describe the synthetic source, filters, and measure limits."""
    return DashboardMeta(
        title="Executive summary",
        description=(
            "Stop-outs, near completers, and outreach from the synthetic Copper Mountain "
            "and College 2 files. These are not findings about real students or either college."
        ),
        filters=[
            f"Institution: {institution}",
            f"Credit threshold: {credit_threshold}",
            f"Student type: {student_type}",
            f"Campus: {campus_location}",
            f"Outreach program: {program}",
            f"Outreach hold: {hold}",
            f"Outreach parent: {parent}",
        ],
        definitions={
            "Near completer": (
                "More than zero and no more than the selected credits remain on the "
                "selected pathway. This is not full graduation eligibility."
            ),
            "Haven't started": "No credits are applied to the selected pathway.",
            "Stop-out": (
                "Not currently enrolled, with pathway credits still remaining, and last "
                "enrolled before the term in progress. Students who left this term are "
                "counted separately until it ends."
            ),
            "Left out": (
                "California Virtual Campus students are left out of the rates unless that "
                "student type is selected. Leaving is the end of a one-class visit, not a stop-out."
            ),
            "Working": "Employment status is full-time or part-time on the synthetic profile.",
            "Course schedule": (
                "Unfinished course codes on the student row, joined to course_schedule.csv. "
                "Section, day, time, and location are synthetic."
            ),
        },
    )
