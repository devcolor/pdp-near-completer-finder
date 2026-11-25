"""Check and store a replacement set of the four institution CSVs."""

import csv
import io
from pathlib import Path

from . import data
from .schemas import (
    Institution,
    SubmittedYear,
    UploadFileRequirement,
    UploadRequirements,
)

MAX_BYTES = 15 * 1024 * 1024

# The column every year is read from. Never a folder name, never typed in.
YEAR_COLUMN = "pdp_year"

# The form field, the file name on disk, and what that file is for.
DATASETS = (
    (
        "students",
        "students.csv",
        "Pathways, credits, enrollment, stop-outs, and near completers.",
    ),
    (
        "profile",
        "student_institutional_profile.csv",
        "Holds, parents, and work. Joined on student_id = Student GUID.",
    ),
    (
        "course_schedule",
        "course_schedule.csv",
        "Section, day, time, and location for courses still remaining.",
    ),
    (
        "course_detail",
        "course_detail.csv",
        "Each student's course record. Kept so the four-file set stays complete.",
    ),
)


def requirements(institution: Institution) -> UploadRequirements:
    """The four files for one college, with the columns the synthetic file already has."""
    return UploadRequirements(
        institution=institution,
        using_upload=data.has_upload(institution),
        files=[
            UploadFileRequirement(
                field=field,
                filename=filename,
                purpose=purpose,
                columns=required_columns(institution, filename),
            )
            for field, filename, purpose in DATASETS
        ],
        years=submitted_years(institution),
        stop_out_basis=data.stop_out_basis(institution),
        stop_outs=absent_from_latest(institution),
        completed=data.completed_count(institution),
    )


def absent_from_latest(institution: str) -> int | None:
    """The dashboard's stop-out figure, straight from the dashboard's own rule."""
    return data.stop_out_count(institution)


def _rows_of(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """The header and rows of an uploaded CSV, keeping every value as written."""
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    return list(reader.fieldnames or []), list(reader)


def pdp_years_in(content: bytes) -> list[str]:
    """Every PDP year present in an uploaded file.

    The year is never typed in or taken from a file name: one upload may carry several years,
    so it is always read from the rows themselves.
    """
    _header, rows = _rows_of(content)
    years = {row.get(YEAR_COLUMN, "").strip() for row in rows}
    return sorted(year for year in years if year)


def year_problems(filename: str, content: bytes) -> str | None:
    """Why this file's years cannot be read, or None when every row names one."""
    header, rows = _rows_of(content)
    if YEAR_COLUMN not in header:
        return f"{filename} has no {YEAR_COLUMN} column."
    blank = sum(1 for row in rows if not row.get(YEAR_COLUMN, "").strip())
    if blank:
        return f"{filename} leaves {YEAR_COLUMN} blank on {blank:,} rows."
    return None


def submitted_years(institution: str) -> list[SubmittedYear]:
    """Each PDP year in the current data, oldest first, with who did not come back.

    Counts the same students the dashboard counts, so these figures tie back to the executive
    tiles. Reads whatever the dashboard reads, so it describes the synthetic files until an
    upload replaces them.
    """
    per_year = data.measured_year_presence(institution)
    if not per_year:
        return []
    # On a snapshot every student sits in exactly one year, so "did not return" would come out
    # as the whole previous year. Only a real year-by-year submission can answer it.
    comparable = data.is_multi_year(institution)
    out = []
    previous: set[str] | None = None
    for year in sorted(per_year, key=data.year_key):
        present = per_year[year]
        out.append(
            SubmittedYear(
                year=year,
                students=len(present),
                not_returning=len(previous - present)
                if comparable and previous is not None
                else None,
            )
        )
        previous = present
    return out


def required_columns(institution: str, filename: str) -> list[str]:
    """Column names from the synthetic file. An upload has to include every one."""
    path = data.DATA_ROOT / institution / "csv" / filename
    with path.open(encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle), [])
    return [column for column in header if column]


def column_problems(filename: str, content: bytes, required: list[str]) -> str | None:
    """Why this file cannot replace the current one, or None when its columns are complete."""
    if len(content) > MAX_BYTES:
        return f"{filename} is larger than 15 MB."
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return f"{filename} is not a UTF-8 CSV."
    lines = text.splitlines()
    if not lines or not lines[0].strip():
        return f"{filename} has no header row."
    header = next(csv.reader([lines[0]]))
    missing = [column for column in required if column not in header]
    if missing:
        return f"{filename} is missing {', '.join(missing)}."
    return None


# Files whose rows carry a pdp_year, so a save can add a year without losing the others.
YEAR_KEYED = {"students.csv": "Student GUID", "course_detail.csv": "Student GUID"}


def _write_rows(folder: Path, filename: str, header: list[str], rows: list[dict[str, str]]) -> None:
    """Write one file via a .part file, so a failed save cannot leave a half-written CSV."""
    temporary = folder / f".{filename}.part"
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(folder / filename)


def _merged(
    existing: Path, content: bytes, filename: str
) -> tuple[list[str], list[dict[str, str]]]:
    """This upload's rows, plus the saved rows for years the upload does not mention.

    Re-uploading a year replaces that year and leaves the rest alone, so years accumulate
    across saves instead of the newest file wiping the others.
    """
    header, rows = _rows_of(content)
    incoming_years = {row[YEAR_COLUMN].strip() for row in rows if row.get(YEAR_COLUMN, "").strip()}
    kept: list[dict[str, str]] = []
    if existing.is_file():
        for row in data._read_csv(existing):
            year = row.get(YEAR_COLUMN, "").strip()
            if year and year not in incoming_years:
                kept.append({column: row.get(column, "") for column in header})
    seen: set[tuple[str, str]] = set()
    out = []
    identity = YEAR_KEYED[filename]
    for row in kept + rows:
        key = (row.get(identity, ""), row.get(YEAR_COLUMN, "").strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    out.sort(key=lambda row: (data.year_key(row.get(YEAR_COLUMN, "")), row.get(identity, "")))
    return header, out


def save_datasets(institution: str, files: dict[str, bytes]) -> None:
    """Add this upload's years to the saved set, then drop the cached rows."""
    folder = data.UPLOAD_ROOT / institution
    folder.mkdir(parents=True, exist_ok=True)
    for _field, filename, _purpose in DATASETS:
        if filename in YEAR_KEYED:
            header, rows = _merged(folder / filename, files[filename], filename)
            _write_rows(folder, filename, header, rows)
            continue
        # No pdp_year on these two, so there is no year to merge on: the upload replaces them.
        temporary = folder / f".{filename}.part"
        temporary.write_bytes(files[filename])
        temporary.replace(folder / filename)
    data.clear_read_cache()


def forget_year(institution: str, year: str) -> bool:
    """Drop one year's rows from the saved upload. False when that year is not saved."""
    folder = data.UPLOAD_ROOT / institution
    if not (folder / "students.csv").is_file():
        return False
    found = False
    for filename in YEAR_KEYED:
        path = folder / filename
        if not path.is_file():
            continue
        rows = list(data._read_csv(path))
        header = list(rows[0].keys()) if rows else []
        kept = [row for row in rows if row.get(YEAR_COLUMN, "").strip() != year]
        if len(kept) != len(rows):
            found = True
        _write_rows(folder, filename, header, kept)
    data.clear_read_cache()
    return found


def restore_synthetic(institution: str) -> None:
    """Delete a saved upload so this college reads the synthetic files again."""
    folder = data.UPLOAD_ROOT / institution
    for _field, filename, _purpose in DATASETS:
        Path(folder / filename).unlink(missing_ok=True)
    data.clear_read_cache()
