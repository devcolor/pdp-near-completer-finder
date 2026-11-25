# College 2 course catalogs

Every College 2 catalog from 2006-2007 to 2026-2027, one row per course per catalog year,
plus program requirements for 2021-2022 to 2026-2027 (see [Program requirements](#program-requirements)).
Same layout as [`../cmc`](../cmc):

| File | What it holds |
| --- | --- |
| `by_year/courses_<catalog>.csv` | One catalog year, e.g. `courses_2024-2025.csv` |
| `courses_all_years.csv` | All years together (11,980 rows) |
| `catalog_manifest.csv` | One row per catalog: URL, source, courses parsed, courses without units, status |
| `catalog_scraper.py` | The script that makes them |

### Columns

The same names and order as the CMC CSVs. College 2 doesn't extract the CMC columns for descriptions,
prerequisites, hours or GE, so those are left out, and `source` is added.

| Column | Meaning |
| --- | --- |
| `catalog`, `start_year`, `end_year` | e.g. `2024-2025`, `2024`, `2025` |
| `course_code`, `dept`, `number` | e.g. `ACC 101`, `ACC`, `101`. CCN courses look like `ENGL C1000` |
| `title` | As printed. PDF catalogs print titles in capitals |
| `units_min`, `units_max` | e.g. `4.0`. Equal unless the course has a range, such as `0.5`-`3.0` |
| `units_raw` | The original text, e.g. `4 units`, or `Non-credit` (then units are `0.0`) |
| `source`, `source_url` | `pdf`, `elumen` or `acalog`, and the page it came from |

### Where each year comes from

All links start at the [catalog page](https://college2.example.edu/catalog).

| Catalogs | Source | Parsing |
| --- | --- | --- |
| 2006-2007 to 2020-2021 | PDF catalogs | Firecrawl turns the PDF into text; course headings like `ACC 101 PRINCIPLES OF ACCOUNTING I` and the units after them |
| 2021-2022 to 2024-2025 | eLumen site | The course list on the home page, then each course page for its units |
| 2025-2026, 2026-2027 | Acalog site | The course description listing, which shows credits |

### Re-run it

Add `FIRECRAWL_API_KEY=fc-...` to the repo-root `.env`, activate the repo's `.venv`, then from the repo root:

```bash
python gia-pre-implementation/raw_course_catalogs/college_two/catalog_scraper.py              # every year
python gia-pre-implementation/raw_course_catalogs/college_two/catalog_scraper.py 2024-2025    # one year
```

Each run rewrites the years it scrapes, then rebuilds `courses_all_years.csv` and the manifest. Firecrawl
responses are cached in `cache/<catalog>/` (git-ignored, about 36 MB with the program pages), so a re-run only re-parses and
spends no credits. Delete a year's cache folder to scrape it again. A full scrape from nothing costs
about 4,900 Firecrawl credits.

### Limitations

- **Catalog addenda are not included.** Mid-year changes in the addendum PDFs are missing.
- **Course descriptions only.** From 2012-2013, PDF catalogs list some courses under "Other approved
  courses (inactive)" with no units or description. Those aren't here. This is most of the drop from
  847 courses in 2011-2012 to 563 in 2012-2013 (mostly ADJ, PHE, CRJ and FST).
- **33 PDF courses have blank units** because the PDF-to-text step lost them. The course is still listed.
- **Titles and codes change between years.** Joining years needs a crosswalk that maps old codes
  to new ones (for example the 2025 move to CCN codes like `ENGL C1000`).
- **Parsing PDFs is pattern matching.** Spot-check a year before relying on it.

## Program requirements

What each program asks for, for the 2021-2022 to 2026-2027 catalogs. These are the catalogs the mock
PDP cohorts (2021-22 to 2024-25) start in. Made by `program_scraper.py`.

| File | What it holds |
| --- | --- |
| `program_requirements.csv` | One row per program per catalog (497): award, total units, major units, GE units, review flags |
| `program_requirement_groups.csv` | One row per requirement group (956), such as "List A: select two (6 units)", with its parent group |
| `program_requirement_courses.csv` | One row per course per group (10,135), plus `ge` rows for the GE pattern |

CMC has no groups file. College 2 needs one because its groups nest: "Required Courses (15 units)"
holds 12 units of named courses plus a "Movement Based Courses (3 units)" group, which holds three
1-unit areas. `group_id` shows the nesting (`G1`, `G1.1`, `G1.1.2`), and `parent_group_id` points up.
`G0` is the program itself, for short certificates that list their courses with no group.

### Columns that need explaining

| Column | Meaning |
| --- | --- |
| `program_id` | The eLumen page name or the Acalog `poid-N`. The same program has a different id in each catalog |
| `award_level` | `AA`, `AS`, `AA-T`, `AS-T`, `Certificate of Achievement`, `Certificate of Career Preparation`, `Certificate`, `Noncredit Certificate` |
| `program_units_min`, `_max` | The units the page states for the whole program, e.g. 60 for a degree |
| `major_units_min`, `_max` | Units the top-level groups ask for, not counting GE |
| `ge_units_stated` | The GE pattern's units as printed, e.g. `34 - 39` |
| `rule` (groups) | `all`: every course and group in it; `credits`: courses worth `choose_units_min` units; `one_of`: one of the groups in it |
| `requirement_kind` (courses) | `required` if the group needs every course it lists, `choice` if the student picks, `ge` for a GE pattern line |

### Run it

From the repo root, with the `.venv` active:

```bash
python gia-pre-implementation/raw_course_catalogs/college_two/program_scraper.py              # every year
python gia-pre-implementation/raw_course_catalogs/college_two/program_scraper.py 2024-2025    # one year
```

The pages are cached, so a re-run only re-parses. A scrape from nothing costs about 500 Firecrawl credits.

### Limitations

- **95 of 497 programs have `needs_review = yes`.** `review_reason` says why:
  - The catalog page lists no requirements (27 programs in 2021-22; all the noncredit certificates).
  - The title doesn't name the award, so it was taken from the page text (18).
  - The page has no award at all (18, such as Solar Technician).
  - A group asks for more units than it lists. For example, Acalog's Kinesiology AA-T lists its 3
    movement units outside "Required Courses (15)".
- **Three page layouts.** 2021-22 uses an older eLumen layout of flat tables, so it has no nested
  groups. Rules written as prose ("select one course from any three areas") are kept as the group
  name and aren't enforced.
- **GE patterns are a units line, not a course list.** CalGETC, IGETC and CSU GE show as one `ge` row.
- **No CIP codes.** Matching a program to PDP's `program_of_study_term_1` needs a separate mapping.
