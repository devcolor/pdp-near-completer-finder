#!/usr/bin/env python3
"""
cmc_catalog_scraper.py
======================
Download every Copper Mountain College catalog listed on the archive page,
parse the course descriptions out of each PDF, and build:

  1. one CSV of courses per catalog edition (plus one combined CSV), and
  2. a crosswalk CSV that tries to recognise the "same" course across editions
     even when its catalog number, department code or title changed.

Archive page: https://www.cmccd.edu/academic-catalogs/catalog-archives/

Sub-commands
------------
  scrape     download PDFs, extract text (OCR for scanned pages), parse courses
  crosswalk  read the combined CSV from `scrape` and build the crosswalk
  all        scrape, then crosswalk

Quick start
-----------
  pip install requests beautifulsoup4 pdfplumber
  pip install pytesseract pillow        # optional, scanned catalogs (also install Tesseract)
  python cmc_catalog_scraper.py all --out-dir cmc_catalog_data

See `python cmc_catalog_scraper.py scrape --help` for options.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import json
import logging
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urljoin, urlparse

log = logging.getLogger("cmc")

ARCHIVE_URL = "https://www.cmccd.edu/academic-catalogs/catalog-archives/"
DEFAULT_OUT_DIR = Path(__file__).resolve().parent

# Output layout: one file per catalog in by_year/, the stacked datasets in all_years/,
# the rows a person still needs to check in review/, and regenerable files in cache/ and logs/.
BY_YEAR = "by_year"
ALL_YEARS = "all_years"
REVIEW = "review"
USER_AGENT = "Mozilla/5.0 (compatible; cmc-catalog-research/1.0; personal research script)"

COURSE_COLUMNS = [
    "catalog", "start_year", "end_year", "course_code", "dept", "number", "title",
    "units_min", "units_max", "units_raw", "lecture_hours", "lab_hours",
    "description", "prerequisite", "corequisite", "advisory", "transfer",
    "c_id", "cal_getc", "cmc_ge", "formerly_known_as",
    "source_pages", "ocr_used", "duplicate_count", "source_url",
]

# --------------------------------------------------------------------------
# Catalog discovery
# --------------------------------------------------------------------------
YEAR_RE = re.compile(r"((?:19|20)\d{2})\s*[-\u2013\u2014_]\s*((?:19|20)?\d{2})")


@dataclass
class Edition:
    label: str            # e.g. "2013-2015"
    start_year: int
    end_year: int
    url: str = ""
    path: Optional[Path] = None
    pages: int = 0
    ocr_pages: int = 0
    courses: int = 0
    status: str = ""


def parse_year_label(text: str):
    """'2025-2026' / '2007-09' / 'Catalogue-2020-2021.pdf' -> (2025, 2026, '2025-2026')."""
    m = YEAR_RE.search(text or "")
    if not m:
        return None
    start = int(m.group(1))
    end_raw = m.group(2)
    end = int(end_raw) if len(end_raw) == 4 else int(str(start)[:2] + end_raw)
    if end < start:
        end += 100
    return start, end, f"{start}-{end}"


def parse_archive_html(html: str, base_url: str = ARCHIVE_URL) -> list[Edition]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, Edition] = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if not urlparse(href).path.lower().endswith(".pdf"):
            continue
        parsed = (parse_year_label(a.get_text(" ", strip=True))
                  or parse_year_label(unquote(Path(urlparse(href).path).name)))
        if not parsed:
            continue
        start, end, label = parsed
        found.setdefault(label, Edition(label, start, end, href))
    return sorted(found.values(), key=lambda e: (e.start_year, e.end_year))


def make_session():
    import requests

    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def discover_editions(session) -> list[Edition]:
    r = session.get(ARCHIVE_URL, timeout=30)
    r.raise_for_status()
    editions = parse_archive_html(r.text, ARCHIVE_URL)
    if not editions:
        raise RuntimeError("No catalog PDF links found on the archive page; the page layout may have changed.")
    return editions


def download(session, url: str, dest: Path, force: bool = False, delay: float = 1.0, retries: int = 4) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0 and not force:
        return False
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            with session.get(url, stream=True, timeout=(15, 180)) as r:
                r.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(1 << 16):
                        fh.write(chunk)
            with open(tmp, "rb") as fh:
                if fh.read(5) != b"%PDF-":
                    raise ValueError("response is not a PDF")
            tmp.replace(dest)
            time.sleep(delay)
            return True
        except Exception as ex:  # noqa: BLE001
            last_err = ex
            log.warning("download attempt %d/%d failed for %s: %s", attempt, retries, url, ex)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"could not download {url}: {last_err}")


# --------------------------------------------------------------------------
# Text extraction (text layer first, OCR for scanned pages)
# --------------------------------------------------------------------------
_OCR_WARNED = False


def _two_column_text(page) -> Optional[str]:
    """If the page is laid out in two columns, read left column then right column."""
    words = page.extract_words()
    n = len(words)
    if n < 80:
        return None
    mid = page.width / 2
    crossing = sum(1 for w in words if w["x0"] < mid - 4 and w["x1"] > mid + 4)
    left = sum(1 for w in words if w["x1"] <= mid + 4)
    right = sum(1 for w in words if w["x0"] >= mid - 4)
    if crossing / n < 0.03 and left / n > 0.25 and right / n > 0.25:
        left_txt = page.crop((0, 0, mid, page.height)).extract_text() or ""
        right_txt = page.crop((mid, 0, page.width, page.height)).extract_text() or ""
        return left_txt + "\n" + right_txt
    return None


def _ocr_page(page, dpi: int, lang: str) -> Optional[str]:
    global _OCR_WARNED
    try:
        import pytesseract
    except ImportError:
        if not _OCR_WARNED:
            log.warning("pytesseract is not installed, so scanned pages will be empty. "
                        "Install: pip install pytesseract pillow  (and the Tesseract application).")
            _OCR_WARNED = True
        return None
    img = page.to_image(resolution=dpi).original
    return pytesseract.image_to_string(img, lang=lang, config="--psm 3")


def pdf_parts(pdf_path: Path) -> list[Path]:
    """Expand an Adobe PDF Portfolio into the PDFs inside it; an ordinary PDF passes through."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return [pdf_path]
    try:
        reader = PdfReader(str(pdf_path))
        if len(reader.pages) > 2:      # a real catalog, not just a portfolio cover sheet
            return [pdf_path]
        attachments = reader.attachments
    except Exception as ex:  # noqa: BLE001
        log.debug("could not inspect %s for attachments: %s", pdf_path.name, ex)
        return [pdf_path]
    if not attachments:
        return [pdf_path]
    dest = pdf_path.parent / f"{pdf_path.stem}_parts"
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for name in sorted(attachments):
        if not name.lower().endswith(".pdf"):
            continue
        target = dest / re.sub(r"[^A-Za-z0-9._-]+", "_", name)
        if not target.exists() or target.stat().st_size == 0:
            target.write_bytes(attachments[name][0])
        out.append(target)
    if out:
        log.info("  %s is a PDF Portfolio; reading %d embedded files", pdf_path.name, len(out))
    return out or [pdf_path]


def extract_pages(pdf_path: Path, cache_json: Path, ocr_mode: str = "auto", min_chars: int = 80,
                  dpi: int = 300, lang: str = "eng", columns: bool = True) -> list[dict]:
    """Return [{'n': 1, 'text': '...', 'ocr': False}, ...]. Results are cached and resumable."""
    import pdfplumber

    cached = None
    if cache_json.exists():
        try:
            cached = json.loads(cache_json.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cached = None

    parts = pdf_parts(pdf_path)
    counts = []
    for part in parts:
        with pdfplumber.open(str(part)) as pdf:
            counts.append(len(pdf.pages))
    total = sum(counts)
    pages: list[dict] = cached["pages"] if cached and cached.get("n") == total else []
    if len(pages) == total:
        return pages

    offset = 0
    for part, count in zip(parts, counts):
        if len(pages) >= offset + count:      # this part is already cached
            offset += count
            continue
        with pdfplumber.open(str(part)) as pdf:
            for i in range(max(0, len(pages) - offset), count):
                page = pdf.pages[i]
                text, used_ocr = "", False
                if ocr_mode != "force":
                    try:
                        text = (_two_column_text(page) if columns else None) or page.extract_text() or ""
                    except Exception as ex:  # noqa: BLE001
                        log.debug("text extraction failed on page %d: %s", offset + i + 1, ex)
                sparse = len(re.sub(r"\s", "", text)) < min_chars
                if ocr_mode == "force" or (ocr_mode == "auto" and sparse):
                    ocr_text = _ocr_page(page, dpi, lang)
                    if ocr_text is not None:
                        text, used_ocr = ocr_text, True
                pages.append({"n": offset + i + 1, "text": text, "ocr": used_ocr})
                page.flush_cache()
                done = len(pages)
                if used_ocr and done % 10 == 0:
                    log.info("  OCR progress %d/%d pages", done, total)
                if done % 10 == 0:
                    cache_json.write_text(json.dumps({"n": total, "pages": pages}), encoding="utf-8")
        offset += count
    cache_json.write_text(json.dumps({"n": total, "pages": pages}), encoding="utf-8")
    return pages


# --------------------------------------------------------------------------
# Course parsing
# --------------------------------------------------------------------------
_REPL = {"\ufb01": "fi", "\ufb02": "fl", "\ufb00": "ff", "\u00ad": "", "\u2010": "-", "\u2011": "-",
         "\u2013": "-", "\u2014": "-", "\u00a0": " "}
NOISE_RES = [re.compile(p, re.I) for p in (
    r"^\s*\d{1,3}\s*$",
    r"^\s*page\s+\d+\s*$",
    r"^.{0,40}copper mountain college.{0,40}catalog.{0,40}$",
    r"^\s*joshua tree, ca\b.{0,60}$",
    r"^\s*www\.cmccd\.edu\s*$",
    r"^\s*course descriptions\s*$",
    r"^\s*copper mountain college\s*$",
)]
BAD_DEPTS = {"THE", "AND", "FOR", "PAGE", "FALL", "UNIT", "UNITS", "TOTAL", "NOTE", "SEE", "CSU", "UC", "ACT",
             "SAT", "OR", "NOT", "WITH", "FROM", "MAY", "ALL", "ANY", "ONE", "TWO", "PART", "LEVEL", "SPRING",
             "SUMMER", "WINTER", "YEAR", "DAY", "JUNE", "JULY", "AUG", "SEP", "SEPT", "OCT", "NOV", "DEC",
             "JAN", "FEB", "MAR", "APR", "ROOM", "BLDG", "EXT"}

NUM = r"[A-Z]?\d{1,4}[A-Z]{0,2}"
HEADER_RE = re.compile(rf"^\s*(?P<dept>[A-Z]{{2,6}})\s+(?P<num>{NUM})(?![\w-])\s*(?P<rest>.*)$")
_UNITS = r"(?P<u>\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?)"
# The second alternative repeats the number pattern, so it stays unnamed (group 2) to avoid
# redefining the group name 'u'. Callers read `.group("u") or .group(2)`.
_UNITS_UNNAMED = r"(\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?)"
# Case-insensitive: editions vary between '3 Units', '3 units' and '4 UNITS'.
UNITS_INLINE_RE = re.compile(rf"\(?{_UNITS}\s*(?:semester\s+)?units?\)?\b|\bunits?\s*:\s*{_UNITS_UNNAMED}", re.I)
UNITS_LINE_RE = re.compile(rf"^\(?(?:{_UNITS}\s*(?:semester\s+)?units?\b|units?\s*:\s*(?P<u2>\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?))", re.I)
FIELD_START_RE = re.compile(r"^(Pre-?requisites?|Co-?requisites?|Advisory|Total\s+(Lecture|Lab)|Lecture\s+Hours|Lab\s+Hours|Transfer)\b", re.I)
TITLE_START_OK = re.compile(r"^[A-Z0-9(]")
MAX_BODY_LINES = 60   # a course description never runs longer than this many lines
# The 2011-2020 editions print a hyphenated code alone on its line, e.g. 'ANTH-001', 'DE-300A'.
CODE_ONLY_RE = re.compile(rf"^\s*(?P<dept>[A-Z]{{2,6}})\s*[-–]\s*(?P<num>{NUM})\s*$")

LABELS = [
    ("prerequisite", re.compile(r"^Pre-?requisites?\s*:\s*(.*)$", re.I)),
    ("corequisite", re.compile(r"^Co-?requisites?\s*:\s*(.*)$", re.I)),
    ("advisory", re.compile(r"^(?:Advisor(?:y|ies)|Recommended\s+Preparation)\s*:\s*(.*)$", re.I)),
    ("transfer", re.compile(r"^Transfer(?:\s*/\s*Applicability)?\s*:\s*(.*)$", re.I)),
    ("c_id", re.compile(r"^C-?ID\s*:?\s*(.*)$")),
    ("cal_getc", re.compile(r"^Cal-?GETC\s*:?\s*(.*)$", re.I)),
    ("cmc_ge", re.compile(r"^CMC\s+GE\s*:?\s*(.*)$", re.I)),
]
TRANSFER_BARE_RE = re.compile(
    r"^(?:(?:CSU|UC|Program Applicable|Degree Applicable|Non-?Degree Applicable|Not Transferable)\s*[,;/&]?\s*)+$", re.I)
HOURS_LINE_RE = re.compile(r"^(?:Total\s+)?(?:Lecture|Lab|Laboratory)\s+Hours?\b", re.I)
HOURS_RE = re.compile(r"(Lecture|Lab|Laboratory)\s+Hours?\s*:?\s*(\d+(?:\.\d+)?)", re.I)
CODE_IN_TEXT = r"[A-Z]{2,6}\s?[A-Z]?\d{1,4}[A-Z]{0,2}"
FORMER_RE = re.compile(rf"[Ff]ormerly(?:\s+(?:known\s+as|listed\s+as|numbered))?\s*:?\s*({CODE_IN_TEXT}(?:\s*(?:,|and|/|or)\s*{CODE_IN_TEXT})*)")


def clean_page_lines(text: str) -> list[str]:
    for k, v in _REPL.items():
        text = text.replace(k, v)
    out = []
    for raw in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        # Some editions print a sideways "COURSES" tab in the margin, which lands in the text as
        # stray single letters: a lone letter on its own line, or glued to the front of a line.
        if re.fullmatch(r"[a-zA-Z]", line):
            continue
        line = re.sub(r"^[a-z] (?=[A-Z(])", "", line)
        if not line or any(rx.match(line) for rx in NOISE_RES):
            continue
        out.append(line)
    return out


def fix_ocr_num(num: str) -> str:
    """Repair common OCR confusions inside a course number (O->0, l/I->1) when surrounded by digits."""
    chars = list(num)
    for i, ch in enumerate(chars):
        prev_d = i > 0 and chars[i - 1].isdigit()
        next_d = i + 1 < len(chars) and chars[i + 1].isdigit()
        if ch in "Oo" and (prev_d or next_d):
            chars[i] = "0"
        elif ch in "lI" and prev_d and next_d:
            chars[i] = "1"
    return "".join(chars)


def try_header(lines: list[str], i: int):
    line = lines[i]
    m = HEADER_RE.match(line)
    if not m:
        return None
    dept, num, rest = m.group("dept"), m.group("num"), m.group("rest").strip()
    if dept in BAD_DEPTS or re.search(r"\.{3,}|(?:\.\s){3,}", line):
        return None
    if i > 0 and lines[i - 1].rstrip().lower().endswith((",", ";", ":", " and", " or", " with", " of", " to", "/")):
        return None
    if rest and not TITLE_START_OK.match(rest):
        return None
    parts: list[str] = []
    units = None
    end = i
    um = UNITS_INLINE_RE.search(rest) if rest else None
    if um:
        parts = [rest[:um.start()].strip(" -:,(")]
        units = um.group("u") or um.group(2)
    else:
        if rest:
            parts = [rest]
        found = False
        for k in range(i + 1, min(i + 5, len(lines))):
            ln = lines[k].strip()
            um = UNITS_LINE_RE.match(ln)
            if um:
                units = um.group("u") or um.group("u2")
                end, found = k, True
                break
            if (HEADER_RE.match(ln) or FIELD_START_RE.match(ln) or len(ln) > 90
                    or not TITLE_START_OK.match(ln)):
                return None
            parts.append(ln)
            if len(parts) > 3:
                return None
        if not found:
            return None
    title = re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip(" .:-")
    if len(re.findall(r"[A-Za-z]", title)) < 3 or len(title) > 120:
        return None
    return {"dept": dept, "num": num, "title": title, "units": units, "end": end, "line": i}


def try_header_code_only(lines: list[str], i: int):
    """2011-2020 catalogs put the code on its own line: 'ANTH-001' / TITLE / '3 Units'."""
    m = CODE_ONLY_RE.match(lines[i])
    if not m or m.group("dept") in BAD_DEPTS:
        return None
    parts: list[str] = []
    for k in range(i + 1, min(i + 6, len(lines))):
        ln = lines[k].strip()
        um = UNITS_LINE_RE.match(ln)
        if um:
            title = re.sub(r"\s+", " ", " ".join(parts)).strip(" .:-")
            if len(re.findall(r"[A-Za-z]", title)) < 3 or len(title) > 120:
                return None
            return {"dept": m.group("dept"), "num": m.group("num"), "title": title,
                    "units": um.group("u") or um.group("u2"), "end": k, "line": i}
        # Anything that isn't a plausible title line means this was not a course header.
        if (CODE_ONLY_RE.match(ln) or HEADER_RE.match(ln) or FIELD_START_RE.match(ln)
                or len(ln) > 90 or not TITLE_START_OK.match(ln)):
            return None
        parts.append(ln)
    return None


def _strip_trailing_headings(lines: list[str]) -> list[str]:
    while lines and lines[-1].isupper() and len(lines[-1].split()) <= 8 and not lines[-1].endswith("."):
        lines = lines[:-1]
    return lines


def parse_body(lines: list[str]) -> dict:
    fields: dict[str, list[str]] = {k: [] for k in
                                    ("description", "prerequisite", "corequisite", "advisory",
                                     "transfer", "c_id", "cal_getc", "cmc_ge")}
    lecture = lab = None
    cur = "description"
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if HOURS_LINE_RE.match(s):
            for kind, val in HOURS_RE.findall(s):
                if kind.lower() == "lecture":
                    lecture = val
                else:
                    lab = val
            continue
        matched = False
        for name, rx in LABELS:
            m = rx.match(s)
            if m:
                cur, matched = name, True
                if m.group(1).strip():
                    fields[name].append(m.group(1).strip())
                break
        if matched:
            continue
        if TRANSFER_BARE_RE.match(s):
            fields["transfer"].append(s)
            cur = "description" if cur == "transfer" else cur
            continue
        fields[cur].append(s)
    for k in fields:
        fields[k] = _strip_trailing_headings(fields[k])
    out = {k: re.sub(r"\s+", " ", " ".join(v)).strip() for k, v in fields.items()}
    out["lecture_hours"], out["lab_hours"] = lecture, lab
    return out


def _norm_code(dept: str, num: str) -> str:
    return f"{dept.upper()} {num.upper()}"


def _units_range(raw: Optional[str]):
    if not raw:
        return None, None
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", raw)]
    if not nums:
        return None, None
    return min(nums), max(nums)


def parse_courses(pages: list[dict], edition: Edition) -> list[dict]:
    flat: list[tuple[int, bool, str]] = []
    for p in pages:
        for ln in clean_page_lines(p.get("text", "")):
            flat.append((p["n"], bool(p.get("ocr")), ln))
    texts = [t for _, _, t in flat]

    headers = []
    i = 0
    while i < len(texts):
        h = try_header(texts, i) or try_header_code_only(texts, i)
        if h:
            headers.append(h)
            i = h["end"] + 1
        else:
            i += 1

    rows: dict[str, dict] = {}
    for idx, h in enumerate(headers):
        stop = headers[idx + 1]["line"] if idx + 1 < len(headers) else len(texts)
        # The last course on a page run would otherwise swallow the index and appendices that follow it.
        stop = min(stop, h["end"] + 1 + MAX_BODY_LINES)
        page_no, is_ocr, _ = flat[h["line"]]
        num = fix_ocr_num(h["num"]) if is_ocr else h["num"]
        code = _norm_code(h["dept"], num)
        body = parse_body(texts[h["end"] + 1:stop])
        blob = " ".join(texts[h["line"]:stop])
        former = []
        for m in FORMER_RE.finditer(blob):
            former += [re.sub(r"\s+", " ", c).strip() for c in re.findall(CODE_IN_TEXT, m.group(1))]
        umin, umax = _units_range(h["units"])
        pages_set = sorted({flat[j][0] for j in range(h["line"], max(h["line"] + 1, stop))})
        row = {
            "catalog": edition.label, "start_year": edition.start_year, "end_year": edition.end_year,
            "course_code": code, "dept": h["dept"], "number": num, "title": h["title"],
            "units_min": umin, "units_max": umax, "units_raw": h["units"] or "",
            "lecture_hours": body["lecture_hours"], "lab_hours": body["lab_hours"],
            "description": body["description"], "prerequisite": body["prerequisite"],
            "corequisite": body["corequisite"], "advisory": body["advisory"], "transfer": body["transfer"],
            "c_id": body["c_id"], "cal_getc": body["cal_getc"], "cmc_ge": body["cmc_ge"],
            "formerly_known_as": "; ".join(dict.fromkeys(former)),
            "source_pages": ",".join(map(str, pages_set[:6])), "ocr_used": is_ocr,
            "duplicate_count": 1, "source_url": edition.url,
        }
        prev = rows.get(code)
        if prev is None:
            rows[code] = row
        else:  # same code seen twice in one catalog (addendum, index, etc.): keep the richest copy
            dup = prev["duplicate_count"] + 1
            keep = row if len(row["description"]) > len(prev["description"]) else prev
            keep["duplicate_count"] = dup
            rows[code] = keep
    return sorted(rows.values(), key=lambda r: (r["dept"], r["number"]))


def write_csv(path: Path, rows: list[dict], columns: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# --------------------------------------------------------------------------
# scrape command
# --------------------------------------------------------------------------
def select_editions(args, session) -> list[Edition]:
    editions: list[Edition] = []
    cache_pdf = Path(args.out_dir) / "cache" / "pdfs"
    if args.local_dir:
        for pdf in sorted(Path(args.local_dir).glob("*.pdf")):
            parsed = parse_year_label(pdf.name)
            if parsed:
                s, e, label = parsed
                editions.append(Edition(label, s, e, "", pdf))
            else:
                log.warning("skipping %s (no year range in file name)", pdf.name)
    else:
        editions = discover_editions(session)
        for ed in editions:
            ed.path = cache_pdf / f"{ed.label}.pdf"
    for spec in args.extra_pdf or []:
        label_part, _, path_part = spec.partition("=")
        parsed = parse_year_label(label_part)
        if not parsed or not path_part or not Path(path_part).exists():
            log.error("--extra-pdf expects LABEL=PATH with an existing file, got %r", spec)
            continue
        s, e, label = parsed
        editions.append(Edition(label, s, e, "", Path(path_part)))
    this_year = dt.date.today().year
    editions = [e for e in editions if args.from_year <= e.start_year <= (args.to_year or this_year + 1)]
    if args.only:
        wanted = {parse_year_label(x)[2] if parse_year_label(x) else x for x in args.only}
        editions = [e for e in editions if e.label in wanted]
    return sorted(editions, key=lambda e: (e.start_year, e.end_year))


def ensure_pages(ed: Edition, out: Path, args, session) -> list[dict]:
    """Download the edition's PDF if needed and return its extracted page text (cached)."""
    if ed.url and session is not None:
        if download(session, ed.url, ed.path, force=args.force, delay=args.delay):
            log.info("downloaded %s", ed.path.name)
    cache_json = out / "cache" / "text" / f"{ed.label}.json"
    cache_json.parent.mkdir(parents=True, exist_ok=True)
    pages = extract_pages(ed.path, cache_json, ocr_mode=args.ocr, min_chars=args.min_chars,
                          dpi=args.ocr_dpi, lang=args.ocr_lang, columns=not args.no_columns)
    ed.pages, ed.ocr_pages = len(pages), sum(1 for p in pages if p["ocr"])
    return pages


def cmd_scrape(args) -> Path:
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    session = None if args.local_dir else make_session()
    editions = select_editions(args, session)
    if not editions:
        raise SystemExit("No catalog editions selected.")
    log.info("Processing %d catalogs: %s", len(editions), ", ".join(e.label for e in editions))

    all_rows: list[dict] = []
    for ed in editions:
        log.info("=== %s ===", ed.label)
        try:
            pages = ensure_pages(ed, out, args, session)
            if args.dump_text:
                d = out / "cache" / "text_pages" / ed.label
                d.mkdir(parents=True, exist_ok=True)
                for p in pages:
                    (d / f"page_{p['n']:04d}.txt").write_text(p["text"], encoding="utf-8")
            rows = parse_courses(pages, ed)
            ed.courses, ed.status = len(rows), "ok" if rows else "no courses parsed (see --dump-text)"
            write_csv(out / BY_YEAR / f"courses_{ed.label}.csv", rows, COURSE_COLUMNS)
            all_rows += rows
            log.info("%s: %d pages (%d OCR), %d courses", ed.label, ed.pages, ed.ocr_pages, ed.courses)
        except Exception as ex:  # noqa: BLE001
            ed.status = f"error: {ex}"
            log.exception("failed on %s", ed.label)

    combined = out / ALL_YEARS / "courses.csv"
    write_csv(combined, all_rows, COURSE_COLUMNS)
    write_csv(out / "catalog_manifest.csv",
              [{"catalog": e.label, "start_year": e.start_year, "end_year": e.end_year, "url": e.url,
                "pdf": os.path.relpath(e.path, out) if e.path else "",  # relative, so no local path is committed "pages": e.pages, "ocr_pages": e.ocr_pages,
                "courses_parsed": e.courses, "status": e.status} for e in editions],
              ["catalog", "start_year", "end_year", "url", "pdf", "pages", "ocr_pages", "courses_parsed", "status"])
    log.info("Wrote %s (%d rows), %s", combined, len(all_rows), out / BY_YEAR)
    bad = [e.label for e in editions if e.courses == 0]
    if bad:
        log.warning("0 courses parsed for: %s. Check catalog_manifest.csv; rerun with --dump-text and "
                    "inspect cache/text_pages/<catalog>/ to tune the parser.", ", ".join(bad))
    return combined


# --------------------------------------------------------------------------
# Program requirements: how many required and elective courses each major needs
# --------------------------------------------------------------------------
PROGRAM_COLUMNS = [
    "catalog", "start_year", "end_year", "program", "award_type", "award_level", "emphasis",
    "is_transfer_degree", "min_required_courses", "min_elective_courses", "min_total_courses",
    "required_units_min", "required_units_max", "elective_units_min",
    "major_units_stated", "program_units_stated", "ge_units_stated",
    "required_groups", "choice_groups", "elective_groups",
    "needs_review", "review_reason", "source_pages", "ocr_used", "source_url",
]
PROGRAM_COURSE_COLUMNS = [
    "catalog", "start_year", "program", "award_type", "section", "group_id", "requirement_kind",
    "choose_courses", "choose_units", "alternative_block", "course_code", "dept", "number",
    "title", "units_raw", "units_min", "units_max", "source_page",
]

PROG_AWARDS = [
    (re.compile(r"^Associate\s+(?:in|of)\s+Arts\b", re.I), "Associate in Arts", "AA"),
    (re.compile(r"^Associate\s+(?:in|of)\s+Science\b", re.I), "Associate in Science", "AS"),
    (re.compile(r"^Certificate\s+of\s+Achievement\b", re.I), "Certificate of Achievement", "Certificate"),
    (re.compile(r"^Certificate\s+of\s+Completion\b", re.I), "Certificate of Completion", "Certificate"),
    (re.compile(r"^Skills?\s+Certificate\b", re.I), "Skills Certificate", "Certificate"),
]
TABLE_HEAD_RE = re.compile(r"^Dept\.?\s*/?\s*No\.?\s+Title\s+Units", re.I)
PROG_SECTIONS = [
    ("required", re.compile(r"^(?:Required\s+Courses?|Core\s+Courses?|Major\s+Requirements?|Required)\s*:?\s*$", re.I)),
    ("restricted_elective", re.compile(r"^Restricted\s+Electives?\b", re.I)),
    ("elective", re.compile(r"^(?:Recommended\s+)?Electives?\s*:?\s*$", re.I)),
]
# "Physics Requirement:", "List A:" - a labelled sub-block inside the table.
PROG_SUBSECTION_RE = re.compile(r"^(?:[A-Z][A-Za-z/&'. -]{1,40}\s+Requirements?|List\s+[A-C]|Group\s+[A-C1-3])\s*:?\s*$")
PROG_TABLE_END_RE = re.compile(
    r"^(?:Advisors?\s*:|Students?\s+must\s+complete|Program\s+Learning\s+Outcomes|Upon\s+successful\s+completion"
    r"|Recommended\s+Sequence|Suggested\s+Sequence)", re.I)
OR_LINE_RE = re.compile(r"^(?:or|OR|-?\s*or\s*-)$", re.I)
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
             "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
             "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
             "twenty": 20, "twentyone": 21, "twentytwo": 22, "twentyfour": 24, "thirty": 30}
SELECT_RE = re.compile(
    r"\b(?:Select|Choose|Complete|Take)\s+(?:at\s+least\s+|a\s+minimum\s+of\s+|any\s+)?"
    r"(?P<word>[A-Za-z]+|\d+(?:\.\d+)?)\s*(?:\(\s*(?P<paren>\d+(?:\.\d+)?)\s*\)\s*)?"
    r"(?P<what>courses?|units?|series)", re.I)
PAREN_UNITS_RE = re.compile(r"\(\s*(\d+(?:\.\d+)?)\s*(?:semester\s+)?units?\s*\)", re.I)
# A line that is only course codes joined by commas / "or" - the option list for a choice.
CODE_LIST_RE = re.compile(rf"^(?:{CODE_IN_TEXT})(?:\s*(?:,|;|/|,?\s*or|,?\s*and)\s*(?:{CODE_IN_TEXT}))+$", re.I)
DOT_LEADER_RE = re.compile(r"\.{2,}\s*(?P<units>\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?)?\s*$")
TRAILING_UNITS_RE = re.compile(r"\s(?P<units>\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?)$")
PROG_CODE_RE = re.compile(rf"^(?P<dept>[A-Z]{{2,6}})\s+(?P<num>{NUM})(?![\w-])\s*(?P<rest>.*)$")

TOTAL_KINDS = [
    ("program_units_stated", re.compile(r"^(?:MINIMUM\s+(?:TRANSFERABLE|CERTIFICATE|DEGREE|PROGRAM)\s+UNITS"
                                        r"|TOTAL\s+(?:PROGRAM\s+|DEGREE\s+|CERTIFICATE\s+)?UNITS)", re.I)),
    ("ge_units_stated", re.compile(r"General\s+Education|Cal-?GETC|IGETC|CSU\s+GE", re.I)),
    ("major_units_stated", re.compile(r"^(?:Total\s+Units\s+for\s+the\s+Major|Total\s+Major\s+Units"
                                      r"|Required\s+Courses?|Total\s+Units\s+in\s+the\s+Major|Major\s+Units)", re.I)),
    ("elective_units_stated", re.compile(r"^(?:Restricted\s+)?Electives?\b", re.I)),
]


def undouble(text: str) -> str:
    """Collapse doubled glyphs some catalog headings render as: 'AAUUTTOO' -> 'AUTO'."""
    out = []
    for word in text.split():
        core = re.sub(r"[^A-Za-z]", "", word)
        if len(core) >= 4 and len(core) % 2 == 0 and all(core[i] == core[i + 1] for i in range(0, len(core), 2)):
            out.append(core[::2])
        else:
            out.append(word)
    return " ".join(out)


def match_award(line: str):
    """'Certificate of Achievement in X' -> ('Certificate of Achievement', 'Certificate', 'X')."""
    for rx, award, level in PROG_AWARDS:
        m = rx.match(line)
        if not m:
            continue
        rest = re.sub(r"^(?:in|for)\b\s*", "", line[m.end():].strip(), flags=re.I).strip(" :-")
        return award, level, rest
    return None


def _prog_name_from(lines: list[str], i: int, rest: str):
    """Collect a program name that may continue onto the lines below the award heading."""
    parts = [undouble(rest)] if rest else []
    emphasis = ""
    for k in range(i + 1, min(i + 5, len(lines))):
        ln = undouble(lines[k].strip())
        if re.match(r"^(?:with\s+emphasis|for\s+transfer|\(?A[AS]-?T\)?$)", ln, re.I):
            emphasis = (emphasis + " " + ln).strip()
            continue
        if PROG_TABLE_END_RE.match(ln) or TABLE_HEAD_RE.match(ln) or match_award(ln):
            break
        letters = re.sub(r"[^A-Za-z]", "", ln)
        # Name continuation lines are short and in capitals.
        if not letters or len(ln) > 60 or not letters.isupper():
            break
        parts.append(ln)
        if not ln.endswith((":", "-", "&")):
            break
    return re.sub(r"\s+", " ", " ".join(parts)).strip(" :-&"), emphasis


def _split_units(rest: str):
    """Split 'Title ......4' or 'Title 4' into (title, units_raw)."""
    m = DOT_LEADER_RE.search(rest)
    if m:
        return rest[:m.start()].strip(" .-:"), (m.group("units") or "").replace(" ", "")
    m = TRAILING_UNITS_RE.search(rest)
    if m and len(rest[:m.start()].strip()) > 3:
        return rest[:m.start()].strip(" .-:"), m.group("units").replace(" ", "")
    return rest.strip(" .-:"), ""


def _select_spec(line: str):
    """'Select three (3) courses ... (9 units)' -> {'courses': 3, 'units': 9.0}."""
    m = SELECT_RE.search(line)
    if not m:
        return None
    word = (m.group("paren") or m.group("word") or "").lower()
    if re.fullmatch(r"\d+(?:\.\d+)?", word):
        n = float(word)
    else:
        n = NUM_WORDS.get(re.sub(r"[^a-z]", "", word))
    what = m.group("what").lower()
    spec = {"courses": None, "units": None, "by_block": False}
    if what.startswith("unit"):
        spec["units"] = n
    elif what.startswith("series"):
        # "Choose one series (PH 002A & 002B) OR (PH 004A & 004B)" picks a block of courses, not one course.
        spec["by_block"] = True
    else:
        spec["courses"] = n
    pm = PAREN_UNITS_RE.search(line)
    if pm and spec["units"] is None:
        spec["units"] = float(pm.group(1))
    return spec if (spec["courses"] or spec["units"] or spec["by_block"]) else None


@dataclass
class ReqGroup:
    """One requirement slot: a mandatory course, an 'A or B' choice, or 'pick N from a list'."""
    kind: str                 # required | choice | elective
    section: str
    choose_courses: Optional[float] = None
    choose_units: Optional[float] = None
    by_block: bool = False    # pick one whole alternative block (a course series), not one course
    blocks: list = field(default_factory=lambda: [[]])   # alternatives; each block is a list of courses

    def add(self, course: dict):
        self.blocks[-1].append(course)

    def new_block(self):
        if self.blocks[-1]:
            self.blocks.append([])

    @property
    def options(self) -> list:
        return [c for b in self.blocks for c in b]


def _block_units(block: list):
    lo = sum(c["units_min"] or 0 for c in block)
    hi = sum((c["units_max"] if c["units_max"] is not None else c["units_min"]) or 0 for c in block)
    return lo, hi


def group_minimums(g: ReqGroup):
    """Return (min_courses, min_units, max_units) needed to satisfy this group."""
    blocks = [b for b in g.blocks if b]
    if g.kind in ("choice", "elective") and not g.by_block:
        opts = sorted(g.options, key=lambda c: -((c["units_max"] or c["units_min"]) or 0))
        if g.choose_courses:
            n = int(math.ceil(g.choose_courses))
            take = opts[:n]
            lo = sum(c["units_min"] or 0 for c in take) or (g.choose_units or 0)
            return n, float(lo), float(lo)
        if g.choose_units:
            biggest = (opts[0]["units_max"] or opts[0]["units_min"]) if opts else None
            n = int(math.ceil(g.choose_units / biggest)) if biggest else None
            return n, float(g.choose_units), float(g.choose_units)
        return (1 if blocks else 0), 0.0, 0.0
    if not blocks:
        return 0, 0.0, 0.0
    sized = [(len(b), *_block_units(b)) for b in blocks]
    best = min(sized, key=lambda s: (s[0], s[1]))
    return best[0], float(best[1]), float(max(s[2] for s in sized))


def parse_program_table(lines: list[tuple[int, bool, str]]):
    """Turn one program's requirement table into requirement groups plus the totals it states."""
    groups: list[ReqGroup] = []
    totals: dict[str, str] = {}
    section = "required"
    cur: Optional[ReqGroup] = None
    alternation = False

    for page, _ocr, raw in lines:
        ln = undouble(raw.strip())
        if not ln:
            continue
        if PROG_TABLE_END_RE.match(ln):
            break
        if TABLE_HEAD_RE.match(ln):
            continue
        if OR_LINE_RE.match(ln):
            alternation = True
            continue

        tm = DOT_LEADER_RE.search(ln)
        label = ln[:tm.start()].strip() if tm else ""
        # A stated total such as 'Total Units for the Major ......19'.
        if tm and tm.group("units") and label and not PROG_CODE_RE.match(label) and not CODE_LIST_RE.match(label):
            for key, rx in TOTAL_KINDS:
                if rx.search(label):
                    totals.setdefault(key, tm.group("units").replace(" ", ""))
                    break
            cur = None
            continue

        sec_hit = next((name for name, rx in PROG_SECTIONS if rx.match(ln)), None)
        spec = _select_spec(ln)
        if sec_hit and not spec:
            section, cur = sec_hit, None
            continue
        if spec:
            # 'Select 18 units from the following' - the lines below it are the options.
            if sec_hit:
                section = sec_hit
            kind = "elective" if section in ("restricted_elective", "elective") or sec_hit else "choice"
            cur = ReqGroup(kind, section, spec["courses"], spec["units"], spec["by_block"])
            groups.append(cur)
            alternation = False
            continue
        if PROG_SUBSECTION_RE.match(ln):
            cur = None
            continue

        codes_part = ln[:tm.start()].strip() if tm else ln
        units_raw = (tm.group("units") or "") if tm else ""
        if CODE_LIST_RE.match(codes_part):
            # 'GEOG 002, PHIL 012, or SOC 014 ....3' - every option on one line.
            umin, umax = _units_range(units_raw)
            if cur is None or cur.kind == "required":
                cur = ReqGroup("choice", section, 1.0, umin)
                groups.append(cur)
            for code in re.findall(CODE_IN_TEXT, codes_part):
                m = PROG_CODE_RE.match(re.sub(r"([A-Z])\s*(\d)", r"\1 \2", code.strip(), count=1))
                if m:
                    cur.add({"dept": m.group("dept"), "number": m.group("num"), "title": "",
                             "units_raw": units_raw, "units_min": umin, "units_max": umax, "page": page})
            alternation = False
            continue

        m = PROG_CODE_RE.match(ln)
        if not m:
            continue
        title, u_raw = _split_units(m.group("rest"))
        umin, umax = _units_range(u_raw)
        course = {"dept": m.group("dept"), "number": m.group("num"), "title": title,
                  "units_raw": u_raw, "units_min": umin, "units_max": umax, "page": page}
        if alternation and cur is not None:
            cur.new_block()
            cur.add(course)
        elif cur is not None and cur.kind in ("choice", "elective"):
            cur.add(course)
        else:
            cur = ReqGroup("required" if section == "required" else "elective", section)
            groups.append(cur)
            cur.add(course)
        alternation = False
    return groups, totals


def parse_programs(pages: list[dict], edition: Edition, units_lookup: dict):
    """Find each program in one catalog and count the courses it requires."""
    flat: list[tuple[int, bool, str]] = []
    for p in pages:
        for ln in clean_page_lines(p.get("text", "")):
            flat.append((p["n"], bool(p.get("ocr")), ln))
    texts = [t for _, _, t in flat]

    heads = [(i, hit) for i, t in enumerate(texts) if (hit := match_award(undouble(t)))]
    programs, course_rows = [], []
    for h_i, (i, (award, level, rest)) in enumerate(heads):
        stop = heads[h_i + 1][0] if h_i + 1 < len(heads) else len(texts)
        block = flat[i:stop]
        # Only a block with a real requirement table is a program; the rest is prose or the index.
        if not any(TABLE_HEAD_RE.match(undouble(t)) or any(rx.match(undouble(t)) for _n, rx in PROG_SECTIONS)
                   for _p, _o, t in block):
            continue
        name, emphasis = _prog_name_from(texts, i, rest)
        if len(re.sub(r"[^A-Za-z]", "", name)) < 3:
            continue
        start = next((k for k, (_p, _o, t) in enumerate(block) if TABLE_HEAD_RE.match(undouble(t))), None)
        if start is None:
            start = next((k for k, (_p, _o, t) in enumerate(block)
                          if any(rx.match(undouble(t)) for _n, rx in PROG_SECTIONS)), 0)
        groups, totals = parse_program_table(block[start:])
        if not groups:
            continue

        # Option lists often print only course codes, so fill units and titles from the scrape step.
        for g in groups:
            for c in g.options:
                key = (edition.label, f"{c['dept']} {c['number']}")
                if c["units_min"] is None and key in units_lookup:
                    c["units_min"], c["units_max"] = units_lookup[key]
                if not c["title"]:
                    c["title"] = units_lookup.get(("title",) + key, "")

        req_n = req_lo = req_hi = ele_n = ele_lo = 0.0
        n_req = n_choice = n_ele = 0
        unknown_elective = False
        for gid, g in enumerate(groups, 1):
            n, lo, hi = group_minimums(g)
            if g.kind == "required":
                req_n, req_lo, req_hi, n_req = req_n + (n or 0), req_lo + lo, req_hi + hi, n_req + 1
            elif g.kind == "choice":
                req_n, req_lo, req_hi, n_choice = req_n + (n or 0), req_lo + lo, req_hi + hi, n_choice + 1
            else:
                unknown_elective = unknown_elective or n is None
                ele_n, ele_lo, n_ele = ele_n + (n or 0), ele_lo + lo, n_ele + 1
            for b_i, blk in enumerate(g.blocks, 1):
                for c in blk:
                    course_rows.append({
                        "catalog": edition.label, "start_year": edition.start_year, "program": name,
                        "award_type": award, "section": g.section, "group_id": f"G{gid:03d}",
                        "requirement_kind": g.kind,
                        "choose_courses": g.choose_courses or "", "choose_units": g.choose_units or "",
                        "alternative_block": b_i if len([b for b in g.blocks if b]) > 1 else "",
                        "course_code": f"{c['dept']} {c['number']}", "dept": c["dept"], "number": c["number"],
                        "title": c["title"], "units_raw": c["units_raw"],
                        "units_min": c["units_min"] if c["units_min"] is not None else "",
                        "units_max": c["units_max"] if c["units_max"] is not None else "",
                        "source_page": c["page"],
                    })

        reasons = []
        if unknown_elective:
            reasons.append("an elective block states units but lists no courses, so its course count is unknown")
        stated = totals.get("major_units_stated") or totals.get("program_units_stated")
        if not stated:
            reasons.append("no stated total units to check against")
        else:
            s_lo, _ = _units_range(stated)
            if s_lo and abs((req_lo + ele_lo) - s_lo) > 2:
                reasons.append(f"parsed {req_lo + ele_lo:g} units vs stated {stated}")
        if any(o for _p, o, _t in block):
            reasons.append("involves OCR text")
        head_text = " ".join([emphasis] + [t for _p, _o, t in block[:40]])
        programs.append({
            "catalog": edition.label, "start_year": edition.start_year, "end_year": edition.end_year,
            "program": name, "award_type": award, "award_level": level, "emphasis": emphasis,
            "is_transfer_degree": "yes" if re.search(r"for transfer|TRANSFERABLE UNITS", head_text, re.I) else "",
            "min_required_courses": int(req_n), "min_elective_courses": int(ele_n),
            "min_total_courses": int(req_n + ele_n),
            "required_units_min": f"{req_lo:g}" if req_lo else "",
            "required_units_max": f"{req_hi:g}" if req_hi else "",
            "elective_units_min": f"{ele_lo:g}" if ele_lo else "",
            "major_units_stated": totals.get("major_units_stated", ""),
            "program_units_stated": totals.get("program_units_stated", ""),
            "ge_units_stated": totals.get("ge_units_stated", ""),
            "required_groups": n_req, "choice_groups": n_choice, "elective_groups": n_ele,
            "needs_review": "yes" if reasons else "", "review_reason": "; ".join(reasons),
            "source_pages": ",".join(map(str, sorted({p for p, _o, _t in block})[:6])),
            "ocr_used": any(o for _p, o, _t in block), "source_url": edition.url,
        })

    # A catalog can print the same program twice (summary page and full page): keep the fuller one.
    best: dict[tuple, dict] = {}
    for p in programs:
        key = (p["program"], p["award_type"], p["emphasis"])
        if key not in best or p["min_total_courses"] > best[key]["min_total_courses"]:
            best[key] = p
    kept = sorted(best.values(), key=lambda p: (p["program"], p["award_type"]))
    keep_pages = {(p["program"], p["award_type"], p["source_pages"]) for p in kept}
    course_rows = [c for c in course_rows
                   if any(c["program"] == k[0] and c["award_type"] == k[1] for k in keep_pages)]
    return kept, course_rows


def load_units_lookup(path: Path) -> dict:
    """Course units and titles from the scrape step, used to fill gaps in program option lists."""
    lookup: dict = {}
    if not path.exists():
        return lookup
    csv.field_size_limit(2 ** 31 - 1)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            try:
                umin = float(r["units_min"]) if r.get("units_min") else None
                umax = float(r["units_max"]) if r.get("units_max") else None
            except ValueError:
                umin = umax = None
            lookup[(r["catalog"], r["course_code"])] = (umin, umax)
            lookup[("title", r["catalog"], r["course_code"])] = r.get("title", "")
    return lookup


def cmd_programs(args) -> None:
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    session = None if args.local_dir else make_session()
    editions = select_editions(args, session)
    if not editions:
        raise SystemExit("No catalog editions selected.")
    units_lookup = load_units_lookup(out / ALL_YEARS / "courses.csv")
    log.info("Reading program requirements from %d catalogs", len(editions))

    all_progs, all_courses = [], []
    for ed in editions:
        log.info("=== %s ===", ed.label)
        try:
            pages = ensure_pages(ed, out, args, session)
            progs, courses = parse_programs(pages, ed, units_lookup)
            write_csv(out / BY_YEAR / f"programs_{ed.label}.csv", progs, PROGRAM_COLUMNS)
            all_progs += progs
            all_courses += courses
            log.info("%s: %d programs, %d requirement rows", ed.label, len(progs), len(courses))
        except Exception:  # noqa: BLE001
            log.exception("failed on %s", ed.label)

    write_csv(out / ALL_YEARS / "program_requirements.csv", all_progs, PROGRAM_COLUMNS)
    write_csv(out / ALL_YEARS / "program_requirement_courses.csv", all_courses, PROGRAM_COURSE_COLUMNS)
    write_csv(out / REVIEW / "program_requirements.csv", [p for p in all_progs if p["needs_review"]], PROGRAM_COLUMNS)
    log.info("Wrote all_years/program_requirements.csv (%d programs), "
             "all_years/program_requirement_courses.csv (%d rows), %d flagged for review",
             len(all_progs), len(all_courses), sum(1 for p in all_progs if p["needs_review"]))


# --------------------------------------------------------------------------
# Crosswalk: decide which courses are "the same" across editions
# --------------------------------------------------------------------------
STOPWORDS = set("OF TO THE AND FOR IN A AN ON WITH BY OR".split())
ABBR = {"INTRO": "INTRODUCTION", "INTRODUCTORY": "INTRODUCTION", "LAB": "LABORATORY", "DEV": "DEVELOPMENT",
        "ADMIN": "ADMINISTRATION", "MGMT": "MANAGEMENT", "AMER": "AMERICAN", "ECON": "ECONOMICS"}
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}
GENERIC_TITLES = {"INDEPENDENT STUDY", "SPECIAL TOPICS", "SELECTED TOPICS", "WORK EXPERIENCE", "DIRECTED STUDIES",
                  "COOPERATIVE WORK EXPERIENCE", "INTERNSHIP", "DIRECTED STUDY", "TOPICS IN"}
DESC_STOP = set("the and for with this that are from their will can may have has course courses student students "
                "includes include including topics emphasis introduction study studies basic principles".split())


def norm_title_tokens(title: str) -> list[str]:
    t = title.upper().replace("&", " AND ")
    t = re.sub(r"\bU\.\s?S\.?(?=\s|$)", "UNITED STATES", t)
    t = re.sub(r"[^A-Z0-9 ]", " ", t)
    return [ABBR.get(x, x) for x in t.split()]


def split_seq(tokens: list[str]):
    """Split a trailing sequence marker (I, II, 1, 2, A, B...) from the title tokens."""
    if len(tokens) >= 2:
        last = tokens[-1]
        base = tokens[:-1]
        if base and base[-1] == "PART":
            base = base[:-1]
        if last in ROMAN:
            return base, ROMAN[last]
        if re.fullmatch(r"[1-5]", last):
            return base, int(last)
        if re.fullmatch(r"[A-D]", last):
            return base, ord(last) - 64
    return tokens, None


def num_norm(num: str) -> str:
    return re.sub(r"^([A-Z]?)0+(?=\d)", r"\1", num.upper())


@dataclass
class Rec:
    idx: int
    ed_idx: int
    row: dict
    dept: str
    number: str
    nn: str
    base: list
    seq: Optional[int]
    has_lab: bool
    units: Optional[float]
    cids: set
    formerly: set
    ocr: bool
    vec: Optional[dict] = None
    lineage: int = -1
    score: float = 0.0
    method: str = "new_course"
    prev_code: str = ""
    notes: list = field(default_factory=list)

    @property
    def code_key(self):
        return (self.dept, self.nn)


def _cids(text: str) -> set:
    return {re.sub(r"\s+", " ", m).strip() for m in re.findall(r"[A-Z]{2,6}\s?\d{2,3}[A-Z]?", text or "")}


def build_recs(rows: list[dict], ed_order: dict) -> list[Rec]:
    recs = []
    for i, r in enumerate(rows):
        toks = norm_title_tokens(r["title"])
        base, seq = split_seq(toks)
        try:
            units = float(r["units_max"]) if r.get("units_max") not in ("", None) else None
        except ValueError:
            units = None
        former = {re.sub(r"\s+", " ", c).strip() for c in (r.get("formerly_known_as") or "").split(";") if c.strip()}
        recs.append(Rec(i, ed_order[r["catalog"]], r, r["dept"], r["number"], num_norm(r["number"]), base, seq,
                        "LABORATORY" in toks, units, _cids(r.get("c_id", "")), former,
                        str(r.get("ocr_used")).lower() == "true"))
    return recs


class DescModel:
    def __init__(self, recs: list[Rec]):
        docs = []
        for r in recs:
            toks = [w for w in re.findall(r"[a-z]{3,}", (r.row.get("description") or "").lower()) if w not in DESC_STOP]
            docs.append(toks)
        df = Counter(w for d in docs for w in set(d))
        n = max(len(docs), 1)
        idf = {w: math.log((1 + n) / (1 + c)) + 1 for w, c in df.items()}
        for r, d in zip(recs, docs):
            if len(d) < 8:
                r.vec = None
                continue
            tf = Counter(d)
            vec = {w: c * idf[w] for w, c in tf.items()}
            norm = math.sqrt(sum(v * v for v in vec.values()))
            r.vec = {w: v / norm for w, v in vec.items()}

    @staticmethod
    def cosine(a: Optional[dict], b: Optional[dict]) -> Optional[float]:
        if not a or not b:
            return None
        if len(a) > len(b):
            a, b = b, a
        return sum(v * b.get(w, 0.0) for w, v in a.items())


def title_similarity(a: list[str], b: list[str]) -> float:
    A = [t for t in a if t not in STOPWORDS]
    B = [t for t in b if t not in STOPWORDS]
    if not A or not B:
        return 0.0
    sa, sb = set(A), set(B)
    jac = len(sa & sb) / len(sa | sb)
    return 0.5 * jac + 0.5 * difflib.SequenceMatcher(None, " ".join(A), " ".join(B)).ratio()


def score_pair(old: Rec, new: Rec, aliases: dict):
    """Return (score 0-1, method, notes)."""
    if old.seq and new.seq and old.seq != new.seq:
        return 0.0, "sequence_mismatch", []
    ts = title_similarity(old.base, new.base)
    ds = DescModel.cosine(old.vec, new.vec)
    same_code = old.code_key == new.code_key
    dept_rel = old.dept == new.dept or aliases.get(old.dept) == new.dept
    same_num = old.nn == new.nn
    cid_eq = bool(old.cids & new.cids)
    former_hit = (f"{old.dept} {old.number}" in new.formerly or f"{old.dept} {old.nn}" in new.formerly
                  or any(re.sub(r"\s+", "", f) == f"{old.dept}{old.number}" for f in new.formerly))
    base_score = ts if ds is None else 0.55 * ts + 0.45 * ds
    bonus = 0.0
    if same_code:
        bonus += 0.12
    elif dept_rel and same_num:
        bonus += 0.08
    if old.units is not None and new.units is not None:
        bonus += 0.04 if old.units == new.units else (-0.08 if abs(old.units - new.units) > 1 else 0.0)
    if cid_eq:
        bonus += 0.20
    score = min(1.0, base_score + bonus)
    if old.has_lab != new.has_lab:
        score -= 0.25
    exact_title = ts >= 0.98
    if exact_title and dept_rel:
        score = max(score, 0.86)
    elif exact_title and ds is not None and ds >= 0.5:
        score = max(score, 0.80)
    if " ".join(new.base) in GENERIC_TITLES and not (dept_rel and same_num):
        score *= 0.5
    method = ("same_code_same_title" if same_code and ts >= 0.9 else
              "same_code_title_changed" if same_code else
              "renumbered_same_title" if ts >= 0.9 else "fuzzy_title_and_description")
    notes = []
    if cid_eq:
        method = "c_id_match" if not same_code else method
        notes.append("same C-ID")
    if former_hit:
        score, method = max(score, 0.97), "formerly_known_as"
        notes.append("catalog says 'formerly known as' the old code")
    return max(0.0, min(1.0, score)), method, notes


@dataclass
class Lineage:
    id: int
    recs: list = field(default_factory=list)

    @property
    def last(self):
        return self.recs[-1]


def build_lineages(recs: list[Rec], n_editions: int, aliases: dict, min_score: float, max_gap: int):
    for r in recs:
        r.lineage, r.score, r.method, r.prev_code, r.notes = -1, 0.0, "new_course", "", []
    by_ed = defaultdict(list)
    for r in recs:
        by_ed[r.ed_idx].append(r)

    lineages: list[Lineage] = []
    idx_code, idx_cid, idx_tok = defaultdict(set), defaultdict(set), defaultdict(set)
    tok_df = Counter(t for r in recs for t in set(r.base) if t not in STOPWORDS)

    def index(lin: Lineage, r: Rec):
        idx_code[r.code_key].add(lin.id)
        idx_code[(r.dept, r.number.upper())].add(lin.id)
        for c in r.cids:
            idx_cid[c].add(lin.id)
        for t in set(r.base):
            if t not in STOPWORDS:
                idx_tok[t].add(lin.id)

    for ed in range(n_editions):
        cur = by_ed.get(ed, [])
        pairs = []
        for r in cur:
            cands = set(idx_code.get(r.code_key, ()))
            for c in r.cids:
                cands |= idx_cid.get(c, set())
            for f in r.formerly:
                m = re.match(r"([A-Z]{2,6})\s?(.+)", f)
                if m:
                    cands |= idx_code.get((m.group(1), num_norm(m.group(2))), set())
                    cands |= idx_code.get((m.group(1), m.group(2).upper()), set())
            for a, b in aliases.items():
                if b == r.dept:
                    cands |= idx_code.get((a, r.nn), set())
            rare = sorted((t for t in set(r.base) if t not in STOPWORDS), key=lambda t: tok_df[t])[:4]
            for t in rare:
                if len(idx_tok[t]) <= 400:
                    cands |= idx_tok[t]
            for lid in cands:
                lin = lineages[lid]
                if ed - lin.last.ed_idx > max_gap or lin.last.ed_idx == ed:
                    continue
                best = (0.0, "", [])
                for k, old in enumerate(reversed(lin.recs[-2:])):
                    s, m, n = score_pair(old, r, aliases)
                    s -= 0.02 * k
                    if s > best[0]:
                        best = (s, m, n)
                if best[0] >= min_score:
                    pairs.append((best[0], lid, r.idx, best[1], best[2]))
        pairs.sort(key=lambda p: (-p[0], p[1], p[2]))
        used_lin, used_rec = set(), set()
        for s, lid, ridx, m, n in pairs:
            if lid in used_lin or ridx in used_rec:
                continue
            used_lin.add(lid)
            used_rec.add(ridx)
            r = recs[ridx]
            lin = lineages[lid]
            r.lineage, r.score, r.method, r.notes = lid, round(s, 3), m, n
            r.prev_code = lin.last.row["course_code"]
            lin.recs.append(r)
            index(lin, r)
        for r in cur:
            if r.lineage == -1:
                lin = Lineage(len(lineages), [r])
                lineages.append(lin)
                r.lineage = lin.id
                for lid in idx_code.get(r.code_key, ()):
                    if lid != lin.id and lineages[lid].last.ed_idx < ed:
                        r.notes.append(f"code previously used by '{lineages[lid].last.row['title']}'")
                        break
                index(lin, r)
    return lineages


def learn_aliases(lineages: list[Lineage]) -> dict:
    moves, totals = Counter(), Counter()
    for lin in lineages:
        for a, b in zip(lin.recs, lin.recs[1:]):
            if b.score >= 0.9:
                totals[a.dept] += 1
                if a.dept != b.dept:
                    moves[(a.dept, b.dept)] += 1
    aliases = {}
    for (old, new), c in moves.most_common():
        if old not in aliases and c >= 3 and c / max(totals[old], 1) >= 0.5:
            aliases[old] = new
    return aliases


def cmd_crosswalk(args) -> None:
    out = Path(args.out_dir)
    src = Path(args.input) if args.input else out / ALL_YEARS / "courses.csv"
    with open(src, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"{src} has no rows. Run the scrape step first.")
    editions = sorted({(int(r["start_year"]), int(r["end_year"]), r["catalog"]) for r in rows})
    ed_order = {label: i for i, (_, _, label) in enumerate(editions)}
    recs = build_recs(rows, ed_order)
    DescModel(recs)
    log.info("Matching %d course records across %d catalogs", len(recs), len(editions))

    lineages = build_lineages(recs, len(editions), {}, args.min_score, args.max_gap)
    aliases = learn_aliases(lineages)
    if aliases:
        log.info("Learned department renames: %s", ", ".join(f"{a}->{b}" for a, b in aliases.items()))
        lineages = build_lineages(recs, len(editions), aliases, args.min_score, args.max_gap)

    # canonical identity = most recent record in each lineage
    ordered = sorted(lineages, key=lambda l: (l.last.dept, l.last.nn, l.last.row["title"]))
    new_id = {l.id: f"L{n:05d}" for n, l in enumerate(ordered, 1)}
    latest_label = editions[-1][2]

    xw_rows = []
    for lin in ordered:
        canon = lin.last.row
        for r in lin.recs:
            reasons = []
            if r.method == "new_course" and r.notes:
                reasons += r.notes
            if r.method != "new_course":
                if r.score < args.review_below:
                    reasons.append(f"score {r.score:.2f} below {args.review_below}")
                if r.method in ("same_code_title_changed", "fuzzy_title_and_description"):
                    reasons.append(f"method: {r.method}")
                if r.ocr or lin.recs[lin.recs.index(r) - 1].ocr:
                    if r.method not in ("same_code_same_title", "formerly_known_as"):
                        reasons.append("involves OCR text")
            xw_rows.append({
                "lineage_id": new_id[lin.id], "canonical_code": canon["course_code"], "canonical_title": canon["title"],
                "catalog": r.row["catalog"], "start_year": r.row["start_year"],
                "course_code": r.row["course_code"], "title": r.row["title"], "units": r.row["units_raw"],
                "match_method": r.method, "match_score": f"{r.score:.3f}" if r.method != "new_course" else "",
                "matched_to_previous_code": r.prev_code,
                "needs_review": "yes" if reasons else "", "review_reason": "; ".join(reasons),
            })
    xw_rows.sort(key=lambda x: (x["canonical_code"], x["lineage_id"], int(x["start_year"])))
    xw_cols = ["lineage_id", "canonical_code", "canonical_title", "catalog", "start_year", "course_code", "title",
               "units", "match_method", "match_score", "matched_to_previous_code", "needs_review", "review_reason"]
    write_csv(out / ALL_YEARS / "course_crosswalk.csv", xw_rows, xw_cols)
    write_csv(out / REVIEW / "crosswalk.csv", [x for x in xw_rows if x["needs_review"]], xw_cols)

    by_lin = defaultdict(list)
    for x in xw_rows:
        by_lin[x["lineage_id"]].append(x)
    summary = []
    for lid, items in by_lin.items():
        items.sort(key=lambda x: int(x["start_year"]))
        codes = list(dict.fromkeys(i["course_code"] for i in items))
        titles = list(dict.fromkeys(i["title"] for i in items))
        timeline, run = [], None
        for i in items:
            if run and run["code"] == i["course_code"] and run["title"] == i["title"]:
                run["end"] = i["catalog"]
            else:
                run = {"code": i["course_code"], "title": i["title"], "start": i["catalog"], "end": i["catalog"]}
                timeline.append(run)
        summary.append({
            "lineage_id": lid, "canonical_code": items[-1]["canonical_code"], "canonical_title": items[-1]["canonical_title"],
            "first_catalog": items[0]["catalog"], "last_catalog": items[-1]["catalog"], "catalogs_present": len(items),
            "in_latest_catalog": "yes" if items[-1]["catalog"] == latest_label else "",
            "distinct_codes": len(codes), "distinct_titles": len(titles),
            "all_codes": " | ".join(codes), "all_titles": " | ".join(titles),
            "timeline": " -> ".join(f"{t['code']} {t['title']} [{t['start']}..{t['end']}]" for t in timeline),
            "needs_review": "yes" if any(i["needs_review"] for i in items) else "",
        })
    summary.sort(key=lambda s: (s["canonical_code"], s["lineage_id"]))
    write_csv(out / ALL_YEARS / "course_lineages.csv", summary,
              ["lineage_id", "canonical_code", "canonical_title", "first_catalog", "last_catalog", "catalogs_present",
               "in_latest_catalog", "distinct_codes", "distinct_titles", "all_codes", "all_titles", "timeline", "needs_review"])
    write_csv(out / ALL_YEARS / "dept_aliases.csv",
              [{"old_dept": a, "new_dept": b} for a, b in aliases.items()], ["old_dept", "new_dept"])
    multi = sum(1 for s in summary if s["distinct_codes"] > 1 or s["distinct_titles"] > 1)
    log.info("Wrote all_years/course_crosswalk.csv (%d rows), all_years/course_lineages.csv "
             "(%d lineages, %d with a code/title change), review/crosswalk.csv (%d rows to check)",
             len(xw_rows), len(summary), multi,
             sum(1 for x in xw_rows if x["needs_review"]))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scrape CMC catalogs and build a cross-year course crosswalk.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                        help=f"output folder (default: the script's own folder, {DEFAULT_OUT_DIR})")
        sp.add_argument("-v", "--verbose", action="store_true")

    def scrape_opts(sp):
        sp.add_argument("--from-year", type=int, default=1999, help="first catalog start year (default 1999)")
        sp.add_argument("--to-year", type=int, default=None, help="last catalog start year (default: this year)")
        sp.add_argument("--only", nargs="+", metavar="LABEL", help="only these catalogs, e.g. 2020-2021 1999-2001")
        sp.add_argument("--extra-pdf", nargs="+", metavar="LABEL=PATH",
                        help="add local PDFs not on the archive page, e.g. 2026-2027=Catalog-2026-27.pdf")
        sp.add_argument("--local-dir", help="use PDFs already in this folder instead of downloading "
                                            "(file names must contain a year range, e.g. Catalogue-2020-2021.pdf)")
        sp.add_argument("--force", action="store_true", help="re-download PDFs even if cached")
        sp.add_argument("--delay", type=float, default=1.0, help="seconds to wait between downloads (default 1)")
        sp.add_argument("--ocr", choices=["auto", "off", "force"], default="auto",
                        help="auto = OCR only pages with no text layer (default)")
        sp.add_argument("--ocr-dpi", type=int, default=300)
        sp.add_argument("--ocr-lang", default="eng")
        sp.add_argument("--min-chars", type=int, default=80, help="pages with fewer text characters count as scanned")
        sp.add_argument("--no-columns", action="store_true", help="disable two-column page detection")
        sp.add_argument("--dump-text", action="store_true", help="save extracted text per page for debugging")

    def xw_opts(sp):
        sp.add_argument("--input", help="combined courses CSV (default: <out-dir>/courses_all_years.csv)")
        sp.add_argument("--min-score", type=float, default=0.70, help="minimum score to link two courses (default 0.70)")
        sp.add_argument("--review-below", type=float, default=0.88, help="flag links scoring below this (default 0.88)")
        sp.add_argument("--max-gap", type=int, default=4, help="max catalogs a course may be absent and still match (default 4)")

    for name, helptext in (("scrape", "download + parse catalogs"),
                           ("programs", "per-major required and elective course counts"),
                           ("crosswalk", "build the cross-year crosswalk"),
                           ("all", "scrape, then programs, then crosswalk")):
        sp = sub.add_parser(name, help=helptext)
        common(sp)
        if name in ("scrape", "programs", "all"):
            scrape_opts(sp)
        if name in ("crosswalk", "all"):
            xw_opts(sp)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    if args.cmd in ("scrape", "all"):
        cmd_scrape(args)
    if args.cmd in ("programs", "all"):
        cmd_programs(args)
    if args.cmd in ("crosswalk", "all"):
        cmd_crosswalk(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
