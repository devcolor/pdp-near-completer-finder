"""Scrape College 2 program requirements with Firecrawl, for the 2021-22 to 2026-27 catalogs.

Two web catalog formats, by year:
  - eLumen (2021-22 to 2024-25): the home page links every program; each program page lists
    its total units and nested requirement groups ("Complete the following number of credits: 6").
  - Acalog (2025-26, 2026-27): the programs page links every program; each program page lists
    "### <group> - Total N Credits" headings with the courses under them.

Writes program_requirements.csv (one row per program per catalog) and
program_requirement_courses.csv (one row per course per requirement group), with column names
taken from ../cmc where they mean the same thing. Firecrawl responses are cached under cache/
(git-ignored), so a re-run only re-parses. The older PDF catalogs aren't parsed; the mock PDP
cohorts start in 2021-22.
Needs FIRECRAWL_API_KEY in the environment or the repo-root .env. Python 3.10 or newer.

Usage (from the repo root):
    python gia-pre-implementation/raw_course_catalogs/college_two/program_scraper.py              # every year
    python gia-pre-implementation/raw_course_catalogs/college_two/program_scraper.py 2024-2025    # one year
"""

import re
import sys
from html import unescape
from html.parser import HTMLParser

from catalog_scraper import (ACALOG_CATALOGS, ELUMEN_CATALOGS, HERE, cached_batch_scrape,
                                 cached_scrape, read_csv, split_code, write_csv)

# Acalog "Programs" navigation page for each catalog: (host, catoid, navoid).
ACALOG_PROGRAM_PAGES = {
    "2025-2026": (ACALOG_CATALOGS["2025-2026"][0], 1, 47),
    "2026-2027": (ACALOG_CATALOGS["2026-2027"][0], 2, 95),
}
YEARS = sorted({**ELUMEN_CATALOGS, **ACALOG_PROGRAM_PAGES})


def elumen_program_urls(year: str) -> dict[str, str]:
    """Return {program page URL: program name} from the cached eLumen home page."""
    home = cached_scrape(year, ELUMEN_CATALOGS[year], formats=["rawHtml"], waitFor=6000)
    html = home["response"]["data"]["rawHtml"]
    programs = {}
    for href, inner in re.findall(r'href="([^"]+/program/[^"]+)"[^>]*>(.*?)</a>', html, flags=re.DOTALL):
        programs[href] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
    return programs


def acalog_program_urls(year: str) -> dict[str, str]:
    """Return {program page URL: program name} from an Acalog programs page."""
    host, catoid, navoid = ACALOG_PROGRAM_PAGES[year]
    url = f"{host}/content.php?catoid={catoid}&navoid={navoid}"
    markdown = cached_scrape(year, url, formats=["markdown"])["response"]["data"]["markdown"]
    programs = {}
    for name, link in re.findall(r"\[([^\]]+)\]\(([^)\s]+preview_program\.php\?catoid=\d+&poid=\d+)", markdown):
        # Drop "&returnto=" so each program has one URL.
        programs[link] = name.strip()
    return programs


def program_pages(year: str) -> tuple[str, dict[str, str], dict[str, str]]:
    """Fetch (or read from the cache) every program page for a year: (source, names, markdown)."""
    if year in ELUMEN_CATALOGS:
        names = elumen_program_urls(year)
        # Cleaned HTML, not markdown: the nested "rule-list" divs say which group holds which.
        pages = cached_batch_scrape(year, sorted(names), name="batch_program_pages_html",
                                    formats=["html"], onlyMainContent=True, waitFor=4000)
        return "elumen", names, pages
    names = acalog_program_urls(year)
    pages = cached_batch_scrape(year, sorted(names), name="batch_program_pages", formats=["markdown"])
    # A few pages come back from a batch without their content; fetch those one at a time.
    for url in names:
        if "## Program Requirements" not in pages.get(url, ""):
            pages[url] = cached_scrape(year, url, formats=["markdown"])["response"]["data"].get("markdown", "")
    return "acalog", names, pages


PROGRAM_FIELDS = ["catalog", "start_year", "end_year", "program_id", "program", "award_type",
                  "award_level", "is_transfer_degree", "program_units_stated", "program_units_min",
                  "program_units_max", "major_units_min", "major_units_max", "ge_units_stated",
                  "required_groups", "choice_groups", "courses_listed", "needs_review",
                  "review_reason", "source", "source_url"]
GROUP_FIELDS = ["catalog", "program_id", "group_id", "parent_group_id", "group_name", "rule",
                "choose_units_min", "choose_units_max", "stated_total", "courses_listed"]
COURSE_FIELDS = ["catalog", "start_year", "program_id", "program", "award_level", "group_id",
                 "group_name", "requirement_kind", "choose_units", "course_code", "dept", "number",
                 "title", "units_min", "units_max", "source_url"]

RANGE = r"(\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*(\d+(?:\.\d+)?))?"
# A course item such as "BIO210 - Human Anatomy" (eLumen) or "POLS C1000 - American Government" (Acalog).
COURSE_ITEM = re.compile(r"^([A-Z]{2,5})\s?((?:C\d{4}|\d{2,4})[A-Z]{0,2})\s*-\s*(.+)$")


class Group:
    """One requirement group: its rule, its courses and the groups inside it."""

    def __init__(self, name: str = "", parent: "Group | None" = None):
        self.name, self.parent = name, parent
        self.stated_total = ""  # as printed, e.g. "55 - 60"
        self.rule, self.choose = "", ("", "")
        self.items: list[tuple[str, str]] = []  # (text, units as printed)
        self.children: list[Group] = []


def number_range(text: str) -> tuple[str, str]:
    """Return (min, max) from text like '3', '18-19' or '34 - 39'; blanks if there's no number."""
    match = re.search(RANGE, text or "")
    if not match:
        return "", ""
    return str(float(match.group(1))), str(float(match.group(2) or match.group(1)))


def set_rule(group: Group, text: str) -> None:
    """Read an eLumen rule line ('Complete all of the following', ...) into the group."""
    text = re.sub(r"\s+", " ", text).strip()
    if text.startswith("Complete all"):
        group.rule = "all"
    elif text.startswith("Complete at least one"):
        group.rule = "one_of"
    elif text.startswith("Complete the following number of credits"):
        group.rule, group.choose = "credits", number_range(text.split(":", 1)[1])


class ElumenRules(HTMLParser):
    """Build a Group tree from the nested 'rule-list' divs on an eLumen program page."""

    def __init__(self):
        super().__init__()
        self.root: Group | None = None
        self.current: Group | None = None
        self.divs: list[str] = []  # class of each open div, to know which div closes
        self.capture, self.text = "", ""
        self.item_name = self.item_units = ""

    def handle_starttag(self, tag, attrs):
        """Open a group, an item, or start capturing a header, rule, name or units."""
        css = dict(attrs).get("class") or ""
        if tag == "div":
            self.divs.append(css)
            if "accordionheader-x-nested" in css:
                self.root = self.current = Group()
            elif "rule-list" in css and self.current is not None:
                child = Group(parent=self.current)
                self.current.children.append(child)
                self.current = child
        elif self.current is not None and tag == "strong":
            self.capture, self.text = "strong", ""
        elif self.current is not None and tag == "span" and css in ("rule-name", "rule-credits"):
            self.capture, self.text = css, ""

    def handle_data(self, data):
        """Collect text for whatever is being captured."""
        if self.capture:
            self.text += data

    def handle_endtag(self, tag):
        """Close a group or item, and file captured text where it belongs."""
        if tag in ("strong", "span") and self.capture:
            text = re.sub(r"\s+", " ", unescape(self.text)).strip()
            if self.capture == "strong":
                if text.startswith("Complete"):
                    set_rule(self.current, text)
                elif not self.current.name:
                    match = re.match(r"^(.*?)\s*\(Total\s*(.*?)\)\s*$", text)
                    self.current.name = match.group(1) if match else text
                    self.current.stated_total = match.group(2) if match else ""
            elif self.capture == "rule-name":
                self.item_name = text
            else:
                self.item_units = text
            self.capture = ""
        elif tag == "div" and self.divs:
            css = self.divs.pop()
            if "new-rule" in css and self.current is not None:
                self.current.items.append((self.item_name, self.item_units))
                self.item_name = self.item_units = ""
            elif "rule-list" in css and self.current is not None and self.current.parent is not None:
                group, self.current = self.current, self.current.parent
                # A nameless rule-list only wraps one course: move its items up to the real group.
                if not group.name and not group.rule and not group.children:
                    self.current.children.remove(group)
                    self.current.items += group.items
            elif "accordionheader-x-nested" in css:
                self.current = None


def parse_elumen_tables(html: str) -> Group | None:
    """Read the older eLumen layout (2021-22): one flat table per group, 'List A ... 6.0 Credits'."""
    start = html.find("Program Requirements</h4>")
    if start < 0:
        return None
    root = Group("Program Requirements")
    root.rule = "all"
    block = html[start:].split('class="table table-total"', 1)[0]
    for table in re.findall(r"<table[^>]*>(.*?)</table>", block, re.DOTALL):
        header = re.search(r'<th scope="col">(.*?)</th>\s*<th class="table-x-total" scope="col">(.*?)</th>',
                           table, re.DOTALL)
        if not header:
            continue
        name = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", header.group(1)))).strip()
        total = re.sub(r"\s*Credits?\s*", "", header.group(2)).strip()
        rows = re.findall(r'<th scope="row" class="[^"]*u-margin-left1x[^"]*">(.*?)</th>\s*'
                          r'<td class="table-x-total">(.*?)</td>', table, re.DOTALL)
        if not rows:
            # A header with credits and no courses is a note, such as the GE pattern.
            root.items.append((name, total))
            continue
        group = Group(name, root)
        group.stated_total = total
        group.rule, group.choose = "credits", number_range(total)
        for text, units in rows:
            text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", text))).strip()
            group.items.append((text, re.sub(r"<[^>]+>", "", units).strip()))
        root.children.append(group)
    return root


def parse_elumen(html: str) -> tuple[str, str, Group | None]:
    """Return (title, program units as printed, requirement tree) for an eLumen program page."""
    title = re.findall(r'<h1 class="u-text-bold">(.*?)</h1>', html, re.DOTALL)
    units = (re.search(r"Units:</h4>\s*<div[^>]*>\s*<p>\s*([^<]+?)\s*Units?", html)
             or re.search(r"Credits:</h[45]>\s*<div[^>]*>\s*<p>\s*([^<]+?)\s*credits", html))
    if "accordion-program-builder-rules-title" in html:
        parser = ElumenRules()
        parser.feed(html)
        root = parser.root
    else:
        root = parse_elumen_tables(html)
    return (re.sub(r"\s+", " ", unescape(title[0])).strip() if title else "",
            units.group(1) if units else "", root)


def parse_acalog(markdown: str) -> tuple[str, Group | None]:
    """Return (program units as printed, requirement tree) for an Acalog program page."""
    units = re.search(r"\nCredits:\s*" + RANGE, markdown)
    start = markdown.find("## Program Requirements")
    if start < 0:
        return (units.group(0).split(":", 1)[1].strip() if units else ""), None
    block = markdown[start:].split("[Close]", 1)[0]
    root = Group("Program Requirements")
    root.rule = "all"
    section = current = root
    for piece in re.split(r"<br>|\n", block)[1:]:
        piece = piece.strip().strip("|").strip()
        heading = re.match(r"^(#{3,4})\s+(.+)$", piece)
        item = re.match(r"^-\s*\[([^\]]+)\]\([^)]*\)\s*(?:Credits:\s*(.+))?$", piece)
        if heading:
            name = heading.group(2).strip()
            parent = root if heading.group(1) == "###" else section
            current = Group(parent=parent)
            parent.children.append(current)
            if heading.group(1) == "###":
                section = current
            total = re.search(r"(?:Total\s*|minimum of\s*)" + RANGE, name, re.IGNORECASE)
            current.name = re.split(r"\s+-\s+Total|\s+-\s+Choose", name)[0].strip()
            current.stated_total = total.group(0).split(None, 1)[-1] if total else ""
            low, high = number_range(current.stated_total)
            current.rule, current.choose = ("credits", (low, high)) if low else ("all", ("", ""))
        elif item:
            current.items.append((unescape(item.group(1)).strip(), (item.group(2) or "").strip()))
    return (units.group(0).split(":", 1)[1].strip() if units else ""), root


def award_level(title: str, page: str) -> str:
    """Return the award from a program title, e.g. 'AA-T', 'AS', 'Certificate of Achievement'."""
    transfer = "AA-T or AS-T" in page or "for Transfer" in title
    if re.search(r"non-?\s?credit|High School Equivalency|Certificate of Completion", title, re.IGNORECASE):
        return "Noncredit Certificate"
    if "CalGETC General Education Courses" in title:
        return "GE pattern"
    for pattern, level in [(r"Certificate of Career Preparation", "Certificate of Career Preparation"),
                           (r"Certificate of Achievement", "Certificate of Achievement"),
                           (r"\bAA-T\b", "AA-T"), (r"\bAS-T\b", "AS-T"),
                           (r"Certificate\b", "Certificate")]:
        if re.search(pattern, title):
            return level
    if re.search(r"Associate (?:in|of) Arts|, AA\b", title):
        return "AA-T" if transfer else "AA"
    if re.search(r"Associate (?:in|of) Science|Associates? Degree|, AS\b|\bADN\b", title):
        return "AS-T" if transfer else "AS"
    return ""


def award_from_page(page: str) -> str:
    """Guess the award from the page text when the title doesn't say, e.g. 'Kinesiology'."""
    text = re.sub(r"<[^>]+>", " ", page)
    # Every transfer page says "required for all AA-T or AS-T degrees", so drop that before looking.
    transfer = "AA-T or AS-T" in text
    text = text.replace("AA-T or AS-T", "").replace("\u201cAA-T\u201d or \u201cAS-T\u201d", "")
    science = re.search(r"\bAS-?T\b|Associate (?:in|of) Science|A\.S\. Degree", text)
    if transfer:
        return "AS-T" if science else "AA-T"
    if science:
        return "AS"
    if re.search(r"Associate (?:in|of) Arts|A\.A\. Degree", text):
        return "AA"
    return ""


def program_name(title: str) -> str:
    """Strip the award words from a title: 'Associate in Arts in Kinesiology' -> 'Kinesiology'."""
    name = re.sub(r"\s*,?\s*(?:Non[- ]?Credit\s+)?(?:Certificate of (?:Career Preparation|Achievement|"
                  r"Completion)|Certificate|Associate of (?:Arts|Science)|Associates? Degree)\b.*$",
                  "", title, flags=re.IGNORECASE)
    name = re.sub(r"^(?:Associate (?:in|of) (?:Arts|Science) in|AA-T in|AS-T)\s+", "", name)
    name = re.sub(r"\s*(?:,\s*(?:AA-T|AS-T|AA|AS)\b.*|\s+for Transfer)$", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip(" ,-") or title


def item_units(text: str) -> tuple[str, str]:
    """Return a course or text item's (min, max) units."""
    return number_range(text)


def group_units(group: Group) -> tuple[float, float]:
    """The (min, max) units a group asks for: its 'credits' rule, else everything in it."""
    if group.rule == "credits" and group.choose[0]:
        return float(group.choose[0]), float(group.choose[1])
    low = high = 0.0
    for text, units in group.items:
        if COURSE_ITEM.match(text):
            a, b = item_units(units)
            low, high = low + float(a or 0), high + float(b or 0)
    for child in group.children:
        a, b = group_units(child)
        low, high = low + a, high + b
    if group.rule == "one_of" and group.children:
        units = [group_units(child) for child in group.children]
        return min(u[0] for u in units), max(u[1] for u in units)
    return low, high


def flatten(group: Group, prefix: str = "G") -> list[tuple[str, str, Group]]:
    """Walk the tree depth-first: (group_id, parent_group_id, group), with ids like G1, G1.2."""
    found = []
    for index, child in enumerate(group.children, 1):
        group_id = f"{prefix}{index}" if prefix == "G" else f"{prefix}.{index}"
        found.append((group_id, prefix if prefix != "G" else "", child))
        found += flatten(child, group_id)
    return found


def requirement_kind(group: Group) -> str:
    """'required' if every course listed is needed, else 'choice'."""
    if group.rule == "all":
        return "required"
    if group.rule == "credits" and group.choose[0]:
        listed = sum(float(item_units(units)[0] or 0) for text, units in group.items if COURSE_ITEM.match(text))
        listed += sum(group_units(child)[0] for child in group.children)
        return "required" if listed <= float(group.choose[0]) else "choice"
    return "choice"


def review_reasons(level: str, program_units: tuple[str, str], groups: list, courses: int) -> list[str]:
    """Why a program's rows need a human look, or [] if they check out."""
    reasons = []
    if not level:
        reasons.append("award level not recognized")
    if not courses:
        reasons.append("no courses listed")
    if not program_units[0]:
        reasons.append("no program units stated")
    for group_id, _, group in groups:
        if group.rule == "credits" and group.choose[0] == "0.0":
            reasons.append(f"{group_id} asks for 0 units")
        elif group.rule == "credits" and group.choose[0]:
            listed = sum(float(item_units(u)[1] or 0) for t, u in group.items if COURSE_ITEM.match(t))
            listed += sum(group_units(child)[1] for child in group.children)
            if listed < float(group.choose[0]):
                reasons.append(f"{group_id} lists fewer units than it asks for")
    return reasons


def program_rows(year: str, source: str, url: str, title: str, page: str,
                 printed_units: str, root: Group | None) -> tuple[dict, list[dict], list[dict]]:
    """Turn one parsed program page into its program row, group rows and course rows."""
    start, end = year.split("-")
    program_id = (url.rstrip("/").rsplit("/", 1)[-1] if source == "elumen"
                  else "poid-" + re.search(r"poid=(\d+)", url).group(1))
    level = award_level(title, page)
    guessed = not level and bool(award_from_page(page))
    level = level or award_from_page(page)
    groups = flatten(root) if root else []
    # Short certificates list their courses on the root itself, with no group around them.
    root_has_courses = bool(root) and any(COURSE_ITEM.match(t.replace("\xa0", " ")) for t, _ in root.items)
    if root_has_courses:
        groups = [("G0", "", root)] + [(g, p or "G0", group) for g, p, group in groups]
    program = {"catalog": year, "program_id": program_id, "program": program_name(title)}
    group_rows, course_rows, ge_units = [], [], []
    for group_id, parent_id, group in groups:
        kind = requirement_kind(group)
        codes = 0
        for text, units in group.items:
            low, high = item_units(units)
            match = COURSE_ITEM.match(text.replace("\xa0", " "))
            if not match:
                if low and re.search(r"General Education|GE\b|CalGETC|IGETC|CSU", text):
                    ge_units.append(units)
                    course_rows.append({**program, "start_year": start, "award_level": level,
                                        "group_id": group_id, "group_name": group.name,
                                        "requirement_kind": "ge", "choose_units": "", "course_code": "",
                                        "dept": "", "number": "", "title": text, "units_min": low,
                                        "units_max": high, "source_url": url})
                continue
            codes += 1
            dept, number = split_code(match.group(1) + match.group(2))
            course_rows.append({**program, "start_year": start, "award_level": level,
                                "group_id": group_id, "group_name": group.name,
                                "requirement_kind": kind,
                                "choose_units": group.choose[0] if kind == "choice" else "",
                                "course_code": f"{dept} {number}", "dept": dept, "number": number,
                                "title": match.group(3).strip(), "units_min": low, "units_max": high,
                                "source_url": url})
        group_rows.append({"catalog": year, "program_id": program_id, "group_id": group_id,
                           "parent_group_id": parent_id, "group_name": group.name, "rule": group.rule,
                           "choose_units_min": group.choose[0], "choose_units_max": group.choose[1],
                           "stated_total": group.stated_total, "courses_listed": codes})
    # GE items sit on the root (eLumen) or in a CalGETC group (Acalog).
    if root and not root_has_courses:
        for text, units in root.items:
            if not COURSE_ITEM.match(text) and item_units(units)[0]:
                ge_units.append(units)
    top = [group for group_id, parent_id, group in groups if not parent_id
           and not re.search(r"CalGETC|IGETC|General Education", group.name or "")]
    major = [group_units(group) for group in top]
    program_units = number_range(printed_units) if printed_units else number_range(root.stated_total if root else "")
    courses = sum(1 for row in course_rows if row["course_code"])
    reasons = review_reasons(level, program_units, groups, courses)
    if guessed:
        reasons.append("award level taken from page text")
    row = {**program, "start_year": start, "end_year": end, "award_type": title, "award_level": level,
           "is_transfer_degree": "yes" if level in ("AA-T", "AS-T") else "",
           "program_units_stated": printed_units, "program_units_min": program_units[0],
           "program_units_max": program_units[1],
           "major_units_min": str(sum(m[0] for m in major)) if major else "",
           "major_units_max": str(sum(m[1] for m in major)) if major else "",
           "ge_units_stated": "; ".join(dict.fromkeys(ge_units)),
           "required_groups": sum(1 for _, _, g in groups if requirement_kind(g) == "required"),
           "choice_groups": sum(1 for _, _, g in groups if requirement_kind(g) == "choice"),
           "courses_listed": courses, "needs_review": "yes" if reasons else "",
           "review_reason": "; ".join(reasons), "source": source, "source_url": url}
    return row, group_rows, course_rows


def run_year(year: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Fetch (or read cached) and parse every program page for one catalog year."""
    source, names, pages = program_pages(year)
    programs, groups, courses = [], [], []
    for url, name in sorted(names.items()):
        page = pages.get(url, "")
        if source == "elumen":
            title, printed_units, root = parse_elumen(page)
            title = title or name
        else:
            title = name
            printed_units, root = parse_acalog(page)
        program, group_rows, course_rows = program_rows(year, source, url, unescape(title), page,
                                                        printed_units, root)
        if not page:
            program["needs_review"], program["review_reason"] = "yes", "page did not load"
        programs.append(program)
        groups += group_rows
        courses += course_rows
    return programs, groups, courses


def main() -> None:
    """Parse the requested years (default: all) and rewrite the three combined CSVs."""
    years = sys.argv[1:] or YEARS
    unknown = set(years) - set(YEARS)
    if unknown:
        sys.exit(f"Unknown years: {sorted(unknown)}. Known: {YEARS}")
    files = {"program_requirements.csv": PROGRAM_FIELDS,
             "program_requirement_groups.csv": GROUP_FIELDS,
             "program_requirement_courses.csv": COURSE_FIELDS}
    # Keep the rows of years not being re-run, so one year can be refreshed on its own.
    kept = {name: [r for r in read_csv(HERE / name) if r["catalog"] not in years] for name in files}
    for year in years:
        programs, groups, courses = run_year(year)
        kept["program_requirements.csv"] += programs
        kept["program_requirement_groups.csv"] += groups
        kept["program_requirement_courses.csv"] += courses
        flagged = sum(1 for p in programs if p["needs_review"])
        print(f"{year}: {len(programs)} programs, {len(courses)} course rows, {flagged} need review")
    for name, fields in files.items():
        rows = sorted(kept[name], key=lambda r: (r["catalog"], r["program_id"], r.get("group_id", "")))
        write_csv(HERE / name, fields, rows)


if __name__ == "__main__":
    main()
