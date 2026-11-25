"""How far each student is from finishing their major, from the college's own catalog requirements.

The near completers measure, the synthetic dataset rebuild and the dashboard all use this one rule, so their
numbers agree. Standard library only.

A major is a list of requirement groups. Each group is one of:
- all: every course on the list
- units: courses adding up to some units, e.g. "6 units from the electives list"
- courses: some number of courses from the list, e.g. "choose 1"
- blocks: one of several alternative sets, e.g. "PH 002A and PH 002B, or PH 004A and PH 004B"

General education groups (CalGETC and the like) are left out: this counts the major only.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .calculations.dfw import DFW_BELOW

REPO = Path(__file__).resolve().parent.parent
CATALOGS = REPO / "gia-pre-implementation" / "raw_course_catalogs"
CMC_FOLDER = CATALOGS / "cmc" / "all_years"
COLLEGE_TWO_FOLDER = CATALOGS / "college_two"

# The catalog each college's synthetic students are held to.
CMC_CATALOG = "2025-2026"
COLLEGE_TWO_CATALOG = "2026-2027"

# CMC lists Computer Science twice for the same award. The synthetic students follow the transfer version
# (MATH 001A, 001B and 004), so that one is used. Any other major listed twice is an error.
CMC_EMPHASIS = {"COMPUTER SCIENCE": "for transfer"}

PASS_CODES = {"P"}


@dataclass(frozen=True)
class RequirementGroup:
    """One requirement group of a major. options holds one course list, or one per alternative block."""

    group_id: str
    rule: str  # all, units, courses or blocks
    options: tuple[tuple[tuple[str, float], ...], ...]  # (course code, units) lists
    need_units: float | None = None
    need_courses: int | None = None


@dataclass(frozen=True)
class Progress:
    """Where one student stands on their major."""

    units_required: float  # units the major takes, with nothing passed
    units_left: float
    courses_required: int  # fewest courses that finish the major, with nothing passed
    courses_left: int  # fewest courses still needed
    remaining_codes: tuple[str, ...]  # courses that could still count, sorted
    required_codes: tuple[str, ...]  # every course on the major's lists, sorted

    @property
    def units_applied(self) -> float:
        """Units of passed courses that count toward the major."""
        return round(self.units_required - self.units_left, 2)

    @property
    def courses_done(self) -> int:
        """Courses required minus courses still needed."""
        return self.courses_required - self.courses_left


def is_pass(grade: str | None) -> bool:
    """A C or better (2.0 grade points or more), or P. W, I, F, blank and anything else don't count."""
    text = (grade or "").strip().upper()
    if text in PASS_CODES:
        return True
    try:
        return float(text) >= DFW_BELOW
    except ValueError:
        return False


def progress(groups: list[RequirementGroup], passed: set[str]) -> Progress:
    """Units and courses left on a major, given the course codes the student passed."""
    nothing: set[str] = set()
    remaining: set[str] = set()
    units_required = units_left = 0.0
    courses_required = courses_left = 0
    for group in groups:
        units_required += group_units_left(group, nothing)
        courses_required += group_courses_left(group, nothing)
        left = group_units_left(group, passed)
        units_left += left
        courses_left += group_courses_left(group, passed)
        if left > 0:
            remaining.update(group_remaining_codes(group, passed))
    codes = {code for group in groups for option in group.options for code, _ in option}
    return Progress(
        units_required=round(units_required, 2),
        units_left=round(units_left, 2),
        courses_required=courses_required,
        courses_left=courses_left,
        remaining_codes=tuple(sorted(remaining)),
        required_codes=tuple(sorted(codes)),
    )


def group_units_left(group: RequirementGroup, passed: set[str]) -> float:
    """Units the group still needs. A choice group counts passed courses only up to what it asks for."""
    courses = group.options[0]
    if group.rule == "blocks":
        return min(sum(units for code, units in block if code not in passed) for block in group.options)
    if group.rule == "units":
        done = sum(units for code, units in courses if code in passed)
        return max(0.0, group.need_units - done)
    if group.rule == "courses":
        still = group.need_courses - sum(1 for code, _ in courses if code in passed)
        open_units = sorted(units for code, units in courses if code not in passed)
        return sum(open_units[:max(still, 0)])
    return sum(units for code, units in courses if code not in passed)


def group_courses_left(group: RequirementGroup, passed: set[str]) -> int:
    """Fewest courses that would finish the group."""
    courses = group.options[0]
    if group.rule == "blocks":
        return min(sum(1 for code, _ in block if code not in passed) for block in group.options)
    if group.rule == "units":
        left = group_units_left(group, passed)
        count = 0
        # Largest courses first gives the fewest courses.
        for units in sorted((u for code, u in courses if code not in passed), reverse=True):
            if left <= 0:
                break
            left -= units
            count += 1
        return count
    if group.rule == "courses":
        return max(0, group.need_courses - sum(1 for code, _ in courses if code in passed))
    return sum(1 for code, _ in courses if code not in passed)


def group_remaining_codes(group: RequirementGroup, passed: set[str]) -> list[str]:
    """Unpassed courses that could finish the group: the closest block, or every open choice."""
    if group.rule == "blocks":
        best = min(group.options, key=lambda block: sum(units for code, units in block if code not in passed))
        return [code for code, _ in best if code not in passed]
    return [code for code, _ in group.options[0] if code not in passed]


def read_csv(path: Path) -> list[dict[str, str]]:
    """Rows of a UTF-8 CSV, with or without a BOM."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def as_float(text: str | None) -> float | None:
    """'3.0' -> 3.0, blank -> None."""
    return float(text) if text and text.strip() else None


def build_group(group_id: str, rows: list[dict[str, str]], code_of) -> RequirementGroup:
    """One group from its course rows. code_of maps a catalog code to the code students are matched on."""
    courses = {code_of(row["course_code"]): float(row["units_min"]) for row in rows}
    blocks = sorted({row.get("alternative_block") or "" for row in rows} - {""})
    need_units = next((as_float(row["choose_units"]) for row in rows if as_float(row["choose_units"])), None)
    need_courses = next((as_float(row.get("choose_courses")) for row in rows if as_float(row.get("choose_courses"))), None)
    if blocks:
        options = tuple(
            tuple((code_of(r["course_code"]), float(r["units_min"])) for r in rows if r["alternative_block"] == block)
            for block in blocks
        )
        return RequirementGroup(group_id, "blocks", options)
    if need_units:
        return RequirementGroup(group_id, "units", (tuple(courses.items()),), need_units=need_units)
    if need_courses:
        return RequirementGroup(group_id, "courses", (tuple(courses.items()),), need_courses=int(need_courses))
    return RequirementGroup(group_id, "all", (tuple(courses.items()),))


def grouped(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Course rows by group_id, in file order."""
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        groups.setdefault(row["group_id"], []).append(row)
    return groups


def cmc_code_map(folder: Path = CMC_FOLDER) -> dict[str, str]:
    """Every CMC course code to its current (canonical) code, from course_crosswalk.csv.

    A code that belonged to more than one course over the years is left as it is.
    """
    seen: dict[str, set[str]] = {}
    for row in read_csv(folder / "course_crosswalk.csv"):
        seen.setdefault(row["course_code"], set()).add(row["canonical_code"])
    return {code: next(iter(canonical)) for code, canonical in seen.items() if len(canonical) == 1}


def cmc_majors(folder: Path = CMC_FOLDER, catalog: str = CMC_CATALOG) -> dict[str, list[RequirementGroup]]:
    """CMC majors by name as students.csv writes it (e.g. BIOLOGY), from the catalog's requirement files.

    The courses file repeats some programs on other pages, so only the courses on the program's own first
    source page are used.
    """
    code_map = cmc_code_map(folder)
    programs: dict[str, list[dict[str, str]]] = {}
    for row in read_csv(folder / "program_requirements.csv"):
        if row["catalog"] == catalog:
            programs.setdefault(row["program"].upper(), []).append(row)
    courses = [row for row in read_csv(folder / "program_requirement_courses.csv") if row["catalog"] == catalog]

    majors = {}
    for name, rows in programs.items():
        program = pick_cmc_program(name, rows)
        if program is None:
            continue  # listed more than once with no pinned emphasis: students on it get no_requirements
        page = program["source_pages"].split(",")[0].strip()
        own = [
            row for row in courses
            if row["program"].upper() == name and row["award_type"] == program["award_type"] and row["source_page"] == page
        ]
        if own and all_have_units(own):
            majors[name] = [
                build_group(gid, group_rows, lambda code: code_map.get(code, code))
                for gid, group_rows in grouped(own).items()
            ]
    return majors


def all_have_units(rows: list[dict[str, str]]) -> bool:
    """A major can only be measured if every course on it states its units."""
    return all(as_float(row["units_min"]) is not None for row in rows)


def pick_cmc_program(name: str, rows: list[dict[str, str]]) -> dict[str, str] | None:
    """The one program row for a major: the only one, or the emphasis pinned in CMC_EMPHASIS. None if unclear."""
    if len(rows) == 1:
        return rows[0]
    wanted = CMC_EMPHASIS.get(name)
    chosen = [row for row in rows if wanted and row["emphasis"] == wanted]
    return chosen[0] if len(chosen) == 1 else None


# pathway_map.csv writes the short name. The catalog award is what the requirements are filed under.
COLLEGE_TWO_MAJOR_AWARD = {
    "Administration of Justice": "Administration of Justice, AS-T",
    "Automotive Technology": "Automotive Technology, AS",
    "Building Construction Technology": "Building Construction Technology , AS",
    "Business Administration": "Business Administration 2.0, AS-T",
    "Child & Adolescent Development": "Child Development , AS",
    "Communication Studies": "Communication Studies 2.0, AA-T",
    "Computer Information Systems": "Computer Information Systems , AS",
    "Early Childhood Education": "Early Childhood Education, AS-T",
    "English": "English, AA-T",
    "Fire Science Technology": "Fire Science Technology, AS",
    "History": "History, AA-T",
    "Kinesiology": "Kinesiology, AA-T",
    "Law, Public Policy & Society": "Criminal Justice , AS",
    "Psychology": "Psychology, AA-T",
    "Public Health": "Biological Sciences , AS (Emphasis Health Science)",
    "Sociology": "Sociology, AA-T",
    "Welding Technology": "Welding Technology , AS",
}


def college_two_award(name: str) -> str:
    """The catalog award for a dashboard major name, or the name when it is already an award."""
    return COLLEGE_TWO_MAJOR_AWARD.get(name, name)


def college_two_majors(folder: Path = COLLEGE_TWO_FOLDER, catalog: str = COLLEGE_TWO_CATALOG) -> dict[str, list[RequirementGroup]]:
    """College 2 majors by award_type (e.g. 'Welding Technology , AS'), from the scraped requirement files."""
    programs = [row for row in read_csv(folder / "program_requirements.csv") if row["catalog"] == catalog]
    nested = {
        row["program_id"] for row in read_csv(folder / "program_requirement_groups.csv")
        if row["catalog"] == catalog and row["parent_group_id"]
    }
    courses: dict[str, list[dict[str, str]]] = {}
    for row in read_csv(folder / "program_requirement_courses.csv"):
        if row["catalog"] == catalog and row["requirement_kind"] != "ge":
            courses.setdefault(row["program_id"], []).append(row)

    majors = {}
    names = [row["award_type"] for row in programs]
    for program in programs:
        name = program["award_type"]
        # Nested groups and a title used twice can't be read with this rule, so those programs are left out.
        if program["program_id"] in nested or names.count(name) > 1 or program["program_id"] not in courses:
            continue
        rows = courses[program["program_id"]]
        if not all_have_units(rows):
            continue
        majors[name] = [build_group(gid, group_rows, lambda code: code) for gid, group_rows in grouped(rows).items()]
    return majors


def passed_courses(enrollments: list[dict[str, str]], code_of=lambda code: code) -> dict[str, set[str]]:
    """Student GUID -> codes of the courses they passed. A retake that passed counts; each course counts once."""
    passed: dict[str, set[str]] = {}
    for row in enrollments:
        if is_pass(row["Grade"]):
            passed.setdefault(row["Student GUID"], set()).add(code_of(row["Course Code"]))
    return passed
