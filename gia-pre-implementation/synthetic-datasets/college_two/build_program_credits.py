"""Build rows of college_two/csv/program_credits.csv from the scraped College 2 program requirements.

Each row says how many credits a program takes to finish in one catalog year: the required core
(the major's units), the stated total, and the difference as optional credits. The figures come
from raw_course_catalogs/college_two/program_requirements.csv.

Rewrites the rows for the years given and keeps every other year as it is. Run it for a year that
is already in the file to check that it reproduces those rows (git diff shows no change).

Usage (from the repo root):
    python gia-pre-implementation/synthetic-datasets/college_two/build_program_credits.py 2026-2027
"""

import csv
import re
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit("build_program_credits needs Python 3.10 or newer. Activate the repo's .venv first.")

HERE = Path(__file__).resolve().parent
CREDITS = HERE / "csv" / "program_credits.csv"
REQUIREMENTS = HERE.parents[1] / "raw_course_catalogs" / "college_two" / "program_requirements.csv"
NONCREDIT_NOTE = "non-credit program: the catalog counts instructional hours, not credits"


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    """Return (column names, rows) of a UTF-8 CSV, with or without a BOM."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames), list(reader)


def as_number(value: str) -> float | None:
    """'60.0' -> 60.0; blank -> None."""
    return float(value) if value else None


def plain(value: float) -> str:
    """Write 18.0 as '18' and 0.5 as '0.5', the way review reasons print numbers."""
    return f"{value:g}"


def program_name(award_type: str, known: dict[str, str]) -> str:
    """The program part of a title: 'Welding Technology , AS' -> 'Welding Technology'."""
    if award_type in known:
        return known[award_type]
    name = re.split(r",\s*(?:AA-T|AS-T|AA|AS|Certificate|Non[- ]?Credit)\b"
                    r"|\s+Certificate of (?:Career Preparation|Achievement|Completion)\b", award_type)[0]
    return name.strip(" ,")


def is_hours(program: dict) -> bool:
    """Noncredit programs that state a figure count instructional hours, not credits."""
    noncredit = program["award_level"] == "Noncredit Certificate"
    figures = [as_number(program["program_units_min"]), as_number(program["major_units_min"])]
    return noncredit and any(figure for figure in figures if figure)


def credit_row(program: dict, known: dict[str, str]) -> dict:
    """One program_credits row for one scraped program."""
    required = as_number(program["major_units_min"])
    total = as_number(program["program_units_min"])
    hours = is_hours(program)
    reasons = [NONCREDIT_NOTE] if hours else []
    if required is not None and total is not None and required > total:
        reasons.append(f"required ({plain(required)}) exceeds stated total ({plain(total)})")
    if total == 0:
        reasons.append("stated total is zero")
    if required is None or total is None:
        reasons.append("a figure was not stated in the catalog")
    both = required is not None and total is not None
    return {
        "catalog_year": program["catalog"],
        "institution": "college_two",
        "program": program_name(program["award_type"], known),
        "award_type": program["award_type"],
        "required_credits": "" if required is None else str(required),
        # Rounded to 1 place like the existing rows, so 30 - 29.75 is written 0.2.
        "optional_credits": str(round(max(total - required, 0.0), 1)) if both else "",
        "total_credits_to_graduate": "" if total is None else str(total),
        "required_source": "catalog" if required is not None else "not stated",
        "optional_source": "derived (total - required)" if both else "not stated",
        "total_source": "catalog" if total is not None else "not stated",
        "needs_review": "yes" if reasons else "",
        "review_reason": "; ".join(reasons),
        "credit_unit": "instructional hours" if hours else "semester credits",
    }


def main() -> None:
    """Rebuild the requested catalog years in program_credits.csv."""
    years = sys.argv[1:]
    if not years:
        sys.exit("Name the catalog years to build, e.g. 2026-2027.")
    fields, rows = read_csv(CREDITS)
    _, programs = read_csv(REQUIREMENTS)
    available = {p["catalog"] for p in programs}
    missing = set(years) - available
    if missing:
        sys.exit(f"No scraped requirements for {sorted(missing)}. Scraped: {sorted(available)}")
    # Keep the program names already chosen for a title in earlier years.
    known = {row["award_type"]: row["program"] for row in rows}
    kept = [row for row in rows if row["catalog_year"] not in years]
    built = [credit_row(p, known) for p in programs if p["catalog"] in years]
    built.sort(key=lambda row: (row["catalog_year"], row["program"], row["award_type"]))
    with CREDITS.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(kept + built, key=lambda row: row["catalog_year"]))
    for year in years:
        year_rows = [row for row in built if row["catalog_year"] == year]
        flagged = sum(1 for row in year_rows if row["needs_review"])
        print(f"{year}: {len(year_rows)} programs, {flagged} need review")


if __name__ == "__main__":
    main()
