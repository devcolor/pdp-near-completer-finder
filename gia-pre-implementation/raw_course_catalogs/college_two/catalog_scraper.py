"""Scrape College 2 course catalogs with Firecrawl and write one CSV per catalog year.

Three catalog formats, by year:
  - PDF catalogs (2006-07 to 2020-21): Firecrawl turns each PDF into markdown; we parse course headings.
  - eLumen site (2021-22 to 2024-25): the home page lists every course; each course page has its units.
  - Acalog site (2025-26, 2026-27): the course description listing shows code, title and credits.

Writes the same layout as ../cmc: by_year/courses_<catalog>.csv, courses_all_years.csv and
catalog_manifest.csv. Raw Firecrawl responses are cached under cache/ (git-ignored), so re-running
only re-parses (no credits spent).
Needs FIRECRAWL_API_KEY in the environment or the repo-root .env. Python 3.10 or newer.

Usage (from the repo root):
    python gia-pre-implementation/raw_course_catalogs/college_two/catalog_scraper.py              # every year
    python gia-pre-implementation/raw_course_catalogs/college_two/catalog_scraper.py 2024-2025    # one year
"""

import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit("scrape_catalogs needs Python 3.10 or newer. Activate the repo's .venv first.")

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
BY_YEAR_DIR = HERE / "by_year"
RAW_DIR = HERE / "cache"
API = "https://api.firecrawl.dev/v2"
MAX_TRIES = 3

PDF_BASE = "https://college2.example.edu/catalog/"
PDF_CATALOGS = {
    "2006-2007": "06-07/06-07catalog.pdf",
    "2007-2008": "07-08/07-08catalog.pdf",
    "2008-2009": "08-09/08-09catalog.pdf",
    "2009-2010": "09-10/09-10catalog.pdf",
    "2010-2011": "10-11/10-11catalog.pdf",
    "2011-2012": "11-12/11-12catalog.pdf",
    "2012-2013": "12-13/12-13catalog.pdf",
    "2013-2014": "13-14/13-14catalog.pdf",
    "2014-2015": "14-15/2014-2015catalog_2.pdf",
    "2015-2016": "15-16/2015-2016catalog.pdf",
    "2016-2017": "16-17/2016-2017catalog.pdf",
    "2017-2018": "17-18/2017-2018catalog.pdf",
    "2018-2019": "18-19/2018-2019catalog.pdf",
    "2019-2020": "19-20/2019-2020%20Catalog.pdf",
    "2020-2021": "20-21/2020-2021%20Catalog.pdf",
}
ELUMEN_CATALOGS = {
    "2021-2022": "https://college2.example.edu/catalog/2021-2022/",
    "2022-2023": "https://college2.example.edu/catalog/2022-2023/",
    "2023-2024": "https://college2.example.edu/catalog/2023-2024/",
    "2024-2025": "https://college2.example.edu/catalog/2024-2025/",
}
# Acalog course description listing: (host, catoid, navoid). 100 courses per page.
ACALOG_CATALOGS = {
    "2025-2026": ("https://college2.example.edu", 1, (46, 47)),
    "2026-2027": ("https://college2.example.edu", 2, (94,)),
}

# Same names and order as the CMC CSVs, minus the CMC columns this scraper doesn't extract.
CSV_FIELDS = ["catalog", "start_year", "end_year", "course_code", "dept", "number", "title",
              "units_min", "units_max", "units_raw", "source", "source_url"]
MANIFEST_FIELDS = ["catalog", "start_year", "end_year", "url", "source", "courses_parsed",
                   "courses_without_units", "status"]

# Course code: 2-5 letter subject, then a number such as 080, 101, 216A or the CCN style C1000.
CODE = r"([A-Z]{2,5})\s?((?:C\d{4}|\d{3,4})[A-Z]{0,2})"
UNITS = re.compile(r"(\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*(\d+(?:\.\d+)?))?\s*units?\b", re.IGNORECASE)


def read_setting(name: str) -> str | None:
    """Return a setting from the environment, falling back to the repo-root .env."""
    if os.environ.get(name):
        return os.environ[name]
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip().strip("'\"")
    return None


def firecrawl(method: str, path: str, body: dict | None = None) -> dict:
    """Call the Firecrawl API, retrying up to MAX_TRIES times, and return the JSON body."""
    key = read_setting("FIRECRAWL_API_KEY")
    if not key:
        sys.exit("FIRECRAWL_API_KEY not set. Add it to the repo-root .env file.")
    data = json.dumps(body).encode() if body is not None else None
    last_error = ""
    for attempt in range(1, MAX_TRIES + 1):
        request = urllib.request.Request(
            API + path, data=data, method=method,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                result = json.load(response)
            if result.get("success", True):
                return result
            last_error = str(result.get("error"))
        except urllib.error.HTTPError as error:
            last_error = f"{error.code}: {error.read().decode()[:300]}"
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = str(error)
        print(f"  attempt {attempt} failed for {path}: {last_error}")
        time.sleep(5 * attempt)
    raise RuntimeError(f"Firecrawl {path} failed after {MAX_TRIES} tries: {last_error}")


def cached_scrape(year: str, url: str, **options) -> dict:
    """Scrape one URL, reusing the cached response under output/raw/<year>/ if there is one."""
    name = hashlib.sha1((url + json.dumps(options, sort_keys=True)).encode()).hexdigest()[:16]
    path = RAW_DIR / year / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    result = firecrawl("POST", "/scrape", {"url": url, **options})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"url": url, "options": options, "response": result}))
    return {"url": url, "options": options, "response": result}


def cached_batch_scrape(year: str, urls: list[str], name: str = "batch_course_pages",
                        **options) -> dict[str, str]:
    """Batch-scrape many URLs to markdown, caching the combined result. Returns {url: markdown}."""
    path = RAW_DIR / year / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    job = firecrawl("POST", "/batch/scrape", {"urls": urls, **options})
    status_path = f"/batch/scrape/{job['id']}"
    while True:
        status = firecrawl("GET", status_path)
        if status["status"] in ("completed", "failed", "cancelled"):
            break
        print(f"  {year}: {status.get('completed', 0)}/{status.get('total', len(urls))} pages")
        time.sleep(10)
    pages = list(status.get("data", []))
    # Large batches come back in several pieces; "next" points at the next piece.
    next_url = status.get("next")
    while next_url:
        more = firecrawl("GET", next_url.replace(API, ""))
        pages += more.get("data", [])
        next_url = more.get("next")
    content_key = options.get("formats", ["markdown"])[0]  # e.g. "markdown" or "html"
    by_url = {p.get("metadata", {}).get("sourceURL", ""): p.get(content_key, "") for p in pages}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(by_url))
    return by_url


def parse_units(text: str) -> tuple[str, str, str]:
    """Return (units_min, units_max, as_printed) from the first 'N units' or 'N-M units' in text."""
    match = UNITS.search(text)
    if not match:
        return "", "", ""
    low, high = match.group(1), match.group(2) or match.group(1)
    return low, high, match.group(0)


def clean_title(title: str) -> str:
    """Strip markup, course-length notes and trailing units from a course title."""
    # Collapse spaces first: "<em>Course</em> length" becomes "Course  length" once tags are gone.
    title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", title))
    title = re.split(r"Course\s*length|\d+(?:\.\d+)?\s*(?:-|–)?\s*\d*(?:\.\d+)?\s*units?\b",
                     title, flags=re.IGNORECASE)[0]
    title = re.sub(r"[*_#♦◇®]|[-]", " ", title)  # markup, symbols, PDF icon glyphs
    return re.sub(r"\s+", " ", title).strip(" .:-")


def row(year: str, subject: str, number: str, title: str, units: tuple[str, str, str],
        source: str, url: str) -> dict:
    """Build one CSV row. Units are written like the CMC CSVs: '4.0', '0.25'."""
    start, end = year.split("-")
    return {
        "catalog": year, "start_year": start, "end_year": end,
        "course_code": f"{subject} {number}", "dept": subject, "number": number, "title": title,
        "units_min": str(float(units[0])) if units[0] else "",
        "units_max": str(float(units[1])) if units[1] else "",
        "units_raw": units[2], "source": source, "source_url": url,
    }


def parse_pdf_markdown(year: str, markdown: str, url: str) -> list[dict]:
    """Find course entries in a PDF catalog's markdown: a code-and-title line, then its units."""
    heading = re.compile(rf"^(?:#+\s*|\*\*)?[\s*:_]*{CODE}\b[\s.:\-–]+(.+)$")
    lines = markdown.splitlines()
    courses: dict[str, dict] = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        is_marked = stripped.startswith(("#", "**"))
        match = heading.match(stripped)
        if not match:
            continue
        subject, number, rest = match.groups()
        title = clean_title(rest)
        letters = [c for c in title if c.isalpha()]
        # Unmarked lines must look like a course heading: mostly upper case, so prose doesn't match.
        if not letters or (not is_marked and sum(c.isupper() for c in letters) / len(letters) < 0.8):
            continue
        # Units sit on the heading line or within the next few lines, before the next heading.
        window = [stripped]
        for following in lines[i + 1:i + 7]:
            if heading.match(following.strip()):
                break
            window.append(following)
        units = parse_units(" ".join(window))
        # Non-credit courses print "Non-credit" instead of units; keep them so they can be filtered.
        if not units[0] and re.search(r"non-?\s?credit", " ".join(window), re.IGNORECASE):
            units = ("0", "0", "Non-credit")
        # A "Course length" line marks a real description even when the PDF text lost its units;
        # keep those with blank units rather than dropping the course.
        is_description = bool(re.search(r"Course\s*length", " ".join(window), re.IGNORECASE))
        code = f"{subject} {number}"
        if (units[0] or is_description) and code not in courses:
            courses[code] = row(year, subject, number, title, units, "pdf", url)
    return list(courses.values())


def scrape_pdf(year: str) -> list[dict]:
    """Scrape and parse one PDF catalog."""
    url = PDF_BASE + PDF_CATALOGS[year]
    result = cached_scrape(year, url, formats=["markdown"], timeout=300000)
    markdown = result["response"]["data"]["markdown"]
    return parse_pdf_markdown(year, markdown, url)


def format_number(value: str) -> str:
    """Drop a trailing '.0' so eLumen's '4.0' matches the other sources' '4'."""
    return value[:-2] if value.endswith(".0") else value


def split_code(code: str) -> tuple[str, str]:
    """Split an eLumen code like 'ACC101' or 'ENGLC1000' into ('ACC', '101') or ('ENGL', 'C1000')."""
    # A CCN number is C plus 4 digits, so "ACC101" stays ACC + 101 rather than AC + C101.
    match = re.match(r"^([A-Z]+?)(C\d{4}[A-Z]*|\d.*)$", code.upper())
    return (match.group(1), match.group(2)) if match else (code.upper(), "")


def scrape_elumen(year: str) -> list[dict]:
    """List every course from the eLumen home page, then batch-scrape course pages for units."""
    home = cached_scrape(year, ELUMEN_CATALOGS[year], formats=["rawHtml"], waitFor=6000)
    html = home["response"]["data"]["rawHtml"]
    # Each nav link reads "<a href=".../course/acc101"> ... ACC101 - Principles of Accounting I".
    links = re.findall(r'href="([^"]+/course/[^"]+)"[^>]*>(.*?)</a>', html, flags=re.DOTALL)
    titles = {}
    for href, inner in links:
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
        match = re.match(r"^([A-Z0-9]+)\s*-\s*(.+)$", text)
        if match:
            titles[href] = match.groups()
    pages = cached_batch_scrape(year, sorted(titles), formats=["markdown"],
                                onlyMainContent=True, waitFor=4000)
    rows = []
    for href, (code, title) in sorted(titles.items()):
        markdown = pages.get(href, "")
        low = re.search(r"Minimum Credit Units\s+(\d+(?:\.\d+)?)", markdown)
        high = re.search(r"Maximum Credit Units\s+(\d+(?:\.\d+)?)", markdown)
        units_min = format_number(low.group(1)) if low else ""
        units_max = format_number(high.group(1)) if high else units_min
        if units_max == "0":
            printed = "Non-credit"
        elif units_min != units_max:
            printed = f"{units_min}-{units_max} units"
        else:
            printed = f"{units_min} units" if units_min else ""
        subject, number = split_code(code)
        rows.append(row(year, subject, number, title.strip(), (units_min, units_max, printed),
                        "elumen", href))
    return rows


def acalog_page_url(host: str, catoid: int, navoid: int, page: int) -> str:
    """Return the URL of one page of an Acalog course description listing."""
    return (f"{host}/content.php?catoid={catoid}&navoid={navoid}&filter%5Bitem_type%5D=3"
            f"&filter%5Bonly_active%5D=1&filter%5B3%5D=1&filter%5Bcpage%5D={page}")


def scrape_acalog(year: str) -> list[dict]:
    """Page through an Acalog course listing and read code, title and credits."""
    host, catoid, navoids = ACALOG_CATALOGS[year]
    entry = re.compile(rf"\[{CODE}\s*-\s*([^\]]+?)\]\(([^)\s]+preview_course[^)\s]*)[^)]*\)"
                       r"(?:<br>)?\s*Credits:\s*([\d.\-– to]+)")
    for navoid in navoids:
        rows, page = [], 1
        while page <= 30:
            url = acalog_page_url(host, catoid, navoid, page)
            markdown = cached_scrape(year, url, formats=["markdown"])["response"]["data"]["markdown"]
            found = entry.findall(markdown)
            if not found:
                break
            for subject, number, title, link, credits in found:
                # Non-credit courses (ABE, GED, NBE) show an empty "Credits:".
                units = parse_units(credits.strip() + " units") if credits.strip() else ("0", "0", "Non-credit")
                rows.append(row(year, subject, number, title.strip(), units, "acalog", link))
            page += 1
        if rows:
            return rows
    return []


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    """Write rows as UTF-8 with a BOM, like the CMC CSVs, so Excel reads accents correctly."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    """Read a CSV written by write_csv, or return [] if it doesn't exist."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def catalog_source(year: str) -> tuple[str, str]:
    """Return (source, url) for a catalog year."""
    if year in PDF_CATALOGS:
        return "pdf", PDF_BASE + PDF_CATALOGS[year]
    if year in ELUMEN_CATALOGS:
        return "elumen", ELUMEN_CATALOGS[year]
    host, catoid, navoids = ACALOG_CATALOGS[year]
    return "acalog", acalog_page_url(host, catoid, navoids[0], 1)


def run_year(year: str) -> list[dict]:
    """Scrape, parse and write one catalog year to by_year/; return its rows."""
    if year in PDF_CATALOGS:
        rows = scrape_pdf(year)
    elif year in ELUMEN_CATALOGS:
        rows = scrape_elumen(year)
    else:
        rows = scrape_acalog(year)
    rows.sort(key=lambda r: (r["dept"], r["number"]))
    write_csv(BY_YEAR_DIR / f"courses_{year}.csv", CSV_FIELDS, rows)
    return rows


def write_combined(all_years: list[str], failed: set[str]) -> None:
    """Rebuild courses_all_years.csv and catalog_manifest.csv from every by_year file."""
    combined, manifest = [], []
    for year in all_years:
        rows = read_csv(BY_YEAR_DIR / f"courses_{year}.csv")
        combined += rows
        source, url = catalog_source(year)
        start, end = year.split("-")
        status = "failed" if year in failed else ("ok" if rows else "not_scraped")
        manifest.append({
            "catalog": year, "start_year": start, "end_year": end, "url": url, "source": source,
            "courses_parsed": len(rows),
            "courses_without_units": sum(1 for r in rows if not r["units_min"]),
            "status": status,
        })
    write_csv(HERE / "courses_all_years.csv", CSV_FIELDS, combined)
    write_csv(HERE / "catalog_manifest.csv", MANIFEST_FIELDS, manifest)


def main() -> None:
    """Run the requested years (default: all), a few at a time, then rebuild the combined files."""
    all_years = sorted({**PDF_CATALOGS, **ELUMEN_CATALOGS, **ACALOG_CATALOGS})
    years = sys.argv[1:] or all_years
    unknown = set(years) - set(all_years)
    if unknown:
        sys.exit(f"Unknown years: {sorted(unknown)}. Known: {all_years}")
    failed = set()
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {year: pool.submit(run_year, year) for year in years}
        for year, future in futures.items():
            try:
                rows = future.result()
                missing = sum(1 for r in rows if not r["units_min"])
                print(f"{year}: {len(rows)} courses ({missing} without units)")
            except Exception as error:  # Report and keep going so one bad year doesn't stop the rest.
                failed.add(year)
                print(f"{year}: FAILED: {error}")
    write_combined(all_years, failed)


if __name__ == "__main__":
    main()
