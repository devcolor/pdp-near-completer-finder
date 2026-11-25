#!/usr/bin/env python3
"""
add_course_timing.py
====================
Course catalogs say what courses exist, not when they run. This script adds term
availability ("seasonality") to both the raw catalog extracts and the synthetic student
datasets, so analyses can ask whether a student's remaining requirement was even offered
in the term after they left.

Every row carries `timing_source`:

  catalog    read out of the published catalog - a program's recommended course sequence
             ("First Semester", "Second Semester", ...) or an explicit season note in the
             course description ("this fall semester pre-season ...").
  simulated  generated here, because the catalog does not publish it. Deterministic:
             the pattern for a course is seeded from its code, so reruns agree.

Only about 4% of CMC course rows have real catalog timing (228 rows, mostly Vocational
Nursing). Everything else is simulated, and labelled as such. The true source for the rest
is the term schedule of classes, which is a separate publication.

Usage
-----
  python3 add_course_timing.py                 # both institutions, raw + synthetic
  python3 add_course_timing.py --only cmc
  python3 add_course_timing.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw_course_catalogs"
SYN = ROOT / "synthetic-datasets"

csv.field_size_limit(2 ** 31 - 1)

# How often a course runs in both terms, by how heavily enrolled it is. Recorded in
# timing_ground_truth.json so a model can be scored against the parameters that made it.
GROUND_TRUTH = {
    "p_both_by_volume": {"high": 0.92, "mid": 0.70, "low": 0.35},
    "p_fall_given_single_season": 0.72,
    "p_alternate_year_given_single_season": 0.12,
    "volume_terciles": "course enrollment counts from the synthetic course_detail.csv",
    "seed": "md5(institution + course_code), so a course's pattern is stable across reruns",
    "note": "Simulated rows only. Rows with timing_source=catalog are read from the catalog.",
}

SEM_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
             "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
SEM_RE = re.compile(r"^\s*(?:(first|second|third|fourth|fifth|sixth)|(\d))(?:st|nd|rd|th)?\s+semester\b"
                    r"|^\s*semester\s+(one|two|three|four|five|six|\d)\b", re.I)
CODE_RE = re.compile(r"^([A-Z]{2,6})\s*-?\s*([A-Z]?\d{1,4}[A-Z]{0,2})\b")
SEASON_NOTE_RE = re.compile(r"\bthis\s+(?:is\s+a\s+)?(fall|spring)\s+semester\b", re.I)


def norm_code(dept: str, num: str) -> str:
    """'MATH-001A' and 'MATH 1A' both become 'MATH 001A' so catalogs and datasets join."""
    num = num.upper()
    m = re.match(r"^([A-Z]?)(\d+)([A-Z]*)$", num)
    if m:
        num = f"{m.group(1)}{int(m.group(2)):03d}{m.group(3)}"
    return f"{dept.upper()} {num}"


def rand01(institution: str, code: str, salt: str = "") -> float:
    """A stable pseudo-random number in [0,1) for one course, so reruns agree."""
    h = hashlib.md5(f"{institution}|{code}|{salt}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# --------------------------------------------------------------------------
# Real timing, read out of the catalogs
# --------------------------------------------------------------------------
def catalog_sequence_positions(inst_dir: Path) -> dict:
    """Course -> semester position, from 'First Semester / Second Semester' sequence tables."""
    out: dict[str, int] = {}
    for cache in sorted((inst_dir / "cache" / "text").glob("*.json")):
        pages = json.loads(cache.read_text(encoding="utf-8")).get("pages", [])
        for page in pages:
            current = None
            for raw in (page.get("text") or "").splitlines():
                line = re.sub(r"\s+", " ", raw).strip()
                m = SEM_RE.match(line)
                if m:
                    val = next(g for g in m.groups() if g).lower()
                    current = SEM_WORDS.get(val, int(val) if val.isdigit() else None)
                    continue
                if current:
                    cm = CODE_RE.match(line)
                    if cm:
                        out.setdefault(norm_code(cm.group(1), cm.group(2)), current)
    return out


def catalog_season_notes(rows: list[dict]) -> dict:
    """Course -> 'Fall'/'Spring' where the description states the season outright."""
    out: dict[str, str] = {}
    for r in rows:
        m = SEASON_NOTE_RE.search(r.get("description") or "")
        if m:
            out.setdefault(r["course_code"], m.group(1).capitalize())
    return out


# --------------------------------------------------------------------------
# Simulated timing for everything the catalog does not state
# --------------------------------------------------------------------------
def enrollment_volume(institution: str) -> dict:
    """Course -> 'high'/'mid'/'low' from how often it appears in the synthetic enrollments."""
    detail = read_csv(SYN / institution / "csv" / "course_detail.csv")
    counts = Counter(norm_code(*m.groups()) for r in detail
                     if (m := CODE_RE.match(r.get("Course Code", "") or "")))
    if not counts:
        return {}
    ordered = sorted(counts.values())
    lo = ordered[len(ordered) // 3]
    hi = ordered[2 * len(ordered) // 3]
    return {c: ("high" if n > hi else "low" if n <= lo else "mid") for c, n in counts.items()}


def simulate_pattern(institution: str, code: str, volume: str) -> tuple[str, str]:
    """Return (terms_offered, offering_pattern) for a course the catalog says nothing about."""
    p_both = GROUND_TRUTH["p_both_by_volume"][volume]
    if rand01(institution, code, "both") < p_both:
        return "Fall;Spring", "every_term"
    season = "Fall" if rand01(institution, code, "season") < GROUND_TRUTH["p_fall_given_single_season"] else "Spring"
    if rand01(institution, code, "alt") < GROUND_TRUTH["p_alternate_year_given_single_season"]:
        return season, f"{season.lower()}_alternate_years"
    return season, f"{season.lower()}_only"


def build_timing(institution: str, courses: list[dict], inst_dir: Path) -> dict:
    """Decide one offering pattern per course, preferring real catalog timing over simulation."""
    seq = catalog_sequence_positions(inst_dir)
    notes = catalog_season_notes(courses)
    volume = enrollment_volume(institution)
    timing: dict[str, dict] = {}
    for code in sorted({r["course_code"] for r in courses}):
        if code in notes:
            # The description states the season outright: "this fall semester pre-season ...".
            season = notes[code]
            timing[code] = {"terms_offered": season, "offering_pattern": f"{season.lower()}_only",
                            "sequence_semester": seq.get(code, ""),
                            "sequence_source": "catalog" if code in seq else "",
                            "timing_source": "catalog"}
            continue
        # A recommended sequence position says when a program advises taking the course, NOT
        # that it is the only term it runs. Keep it as its own real field and still simulate
        # availability, or we would turn a recommendation into a constraint.
        terms, pattern = simulate_pattern(institution, code, volume.get(code, "mid"))
        timing[code] = {"terms_offered": terms, "offering_pattern": pattern,
                        "sequence_semester": seq.get(code, ""),
                        "sequence_source": "catalog" if code in seq else "",
                        "timing_source": "simulated"}
    return timing


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------
TIMING_COLS = ["terms_offered", "offering_pattern", "timing_source", "sequence_semester", "sequence_source"]
BLANK_TIMING = {"terms_offered": "", "offering_pattern": "", "timing_source": "unknown",
                "sequence_semester": "", "sequence_source": ""}


def augment_course_files(inst_dir: Path, timing: dict, dry: bool) -> list[str]:
    """Add the timing columns to every raw courses CSV, keeping the existing columns."""
    targets = [p for p in [inst_dir / "all_years" / "courses.csv", inst_dir / "courses_all_years.csv"]
               if p.exists()] + sorted((inst_dir / "by_year").glob("courses_*.csv"))
    touched = []
    for path in targets:
        rows = read_csv(path)
        if not rows:
            continue
        cols = [c for c in rows[0] if c] + [c for c in TIMING_COLS if c not in rows[0]]
        for r in rows:
            r.update(timing.get(r["course_code"], BLANK_TIMING))
        if not dry:
            write_csv(path, rows, cols)
        touched.append(str(path.relative_to(RAW)))
    return touched


def write_offerings(inst_dir: Path, courses: list[dict], timing: dict, dry: bool) -> Path:
    """One row per course per term: the long-form calendar that student data joins to."""
    catalogs = sorted({r["catalog"] for r in courses})
    by_catalog = defaultdict(set)
    for r in courses:
        by_catalog[r["catalog"]].add(r["course_code"])
    rows = []
    for cat in catalogs:
        start = int(cat.split("-")[0])
        for code in sorted(by_catalog[cat]):
            t = timing[code]
            for term in ("Fall", "Spring"):
                offered = term in t["terms_offered"].split(";")
                if offered and t["offering_pattern"].endswith("alternate_years"):
                    offered = start % 2 == 0
                rows.append({"catalog": cat, "academic_year_start": start, "course_code": code,
                             "term": term, "offered": str(offered).upper(),
                             "offering_pattern": t["offering_pattern"],
                             "timing_source": t["timing_source"],
                             "sequence_semester": t["sequence_semester"],
                             "sequence_source": t["sequence_source"]})
    dest = (inst_dir / "all_years" / "course_offerings.csv") if (inst_dir / "all_years").exists() \
        else (inst_dir / "course_offerings.csv")
    if not dry:
        write_csv(dest, rows, ["catalog", "academic_year_start", "course_code", "term", "offered",
                               "offering_pattern", "timing_source", "sequence_semester", "sequence_source"])
    return dest


def update_synthetic(institution: str, timing: dict, dry: bool) -> list[str]:
    """Copy the calendar next to the synthetic data and flag season-locked remaining requirements."""
    out_dir = SYN / institution / "csv"
    if not out_dir.exists():
        return []
    touched = []
    rows = [{"course_code": c, "terms_offered": t["terms_offered"],
             "offering_pattern": t["offering_pattern"], "fall_offered": str("Fall" in t["terms_offered"]).upper(),
             "spring_offered": str("Spring" in t["terms_offered"]).upper(),
             "season_locked": str(";" not in t["terms_offered"]).upper(),
             "timing_source": t["timing_source"], "sequence_semester": t["sequence_semester"],
             "sequence_source": t["sequence_source"]}
            for c, t in sorted(timing.items())]
    if not dry:
        write_csv(out_dir / "course_offerings.csv", rows,
                  ["course_code", "terms_offered", "offering_pattern", "fall_offered", "spring_offered",
                   "season_locked", "timing_source", "sequence_semester", "sequence_source"])
    touched.append(str((out_dir / "course_offerings.csv").relative_to(SYN)))

    rr_path = out_dir / "remaining_requirements.csv"
    rr = read_csv(rr_path)
    if rr:
        cols = [c for c in rr[0] if c] + [c for c in ("Terms Offered", "Season Locked", "Timing Source")
                                          if c not in rr[0]]
        for r in rr:
            m = CODE_RE.match(r.get("Course Code", "") or "")
            t = timing.get(norm_code(*m.groups())) if m else None
            r["Terms Offered"] = t["terms_offered"] if t else ""
            r["Season Locked"] = str(";" not in t["terms_offered"]).upper() if t else ""
            r["Timing Source"] = t["timing_source"] if t else "unknown"
        if not dry:
            write_csv(rr_path, rr, cols)
        touched.append(str(rr_path.relative_to(SYN)))
    return touched


def run(institution: str, dry: bool) -> None:
    inst_dir = RAW / institution
    courses = read_csv(inst_dir / "all_years" / "courses.csv") or read_csv(inst_dir / "courses_all_years.csv")
    if not courses:
        print(f"  {institution}: no raw courses file found, skipping")
        return
    timing = build_timing(institution, courses, inst_dir)
    src = Counter(t["timing_source"] for t in timing.values())
    pat = Counter(t["offering_pattern"] for t in timing.values())
    print(f"=== {institution.upper()} ===")
    print(f"  distinct courses: {len(timing)}   catalog-sourced: {src['catalog']}   simulated: {src['simulated']}")
    for p, c in pat.most_common():
        print(f"     {p:28} {c:5}")
    touched = augment_course_files(inst_dir, timing, dry)
    dest = write_offerings(inst_dir, courses, timing, dry)
    syn = update_synthetic(institution, timing, dry)
    print(f"  raw files updated: {len(touched)}  (+ {dest.name})")
    for s in syn:
        print(f"  synthetic updated: {s}")
    if not dry:
        (inst_dir / "timing_ground_truth.json").write_text(
            json.dumps({"institution": institution, **GROUND_TRUTH,
                        "counts": {"catalog": src["catalog"], "simulated": src["simulated"]},
                        "patterns": dict(pat)}, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Add term availability to the raw and synthetic course data.")
    ap.add_argument("--only", nargs="+", choices=["cmc", "college_two"], help="limit to these institutions")
    ap.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = ap.parse_args()
    for inst in (args.only or ["cmc", "college_two"]):
        run(inst, args.dry_run)
    if args.dry_run:
        print("\n(dry run - nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
