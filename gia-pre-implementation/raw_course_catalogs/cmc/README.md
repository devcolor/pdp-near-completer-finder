# Copper Mountain College course catalogs, 1999–2026

Scraped from the college's public [catalog archive](https://www.cmccd.edu/academic-catalogs/catalog-archives/)
by [`cmc_catalog_scraper.py`](cmc_catalog_scraper.py). Every catalog on that page is a PDF; the
script downloads them, pulls the text out (OCR for the scanned older editions), and writes CSVs.

**This is real published data about a real college** — unlike the synthetic PDP data elsewhere in
this repo. Treat the parsed numbers as a best-effort reading of PDF text, not as the college's
official record. Anything in a `*_review.csv` has not been checked by a person.

## Setup

Needs Python 3.10+ and [Tesseract](https://tesseract-ocr.github.io/) for the scanned catalogs
(`brew install tesseract`).

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install requests beautifulsoup4 pdfplumber pytesseract pillow
```

## Commands

Run these from this folder. Output lands here by default.

```bash
# Everything: download + parse, program requirements, then the cross-year crosswalk
.venv/bin/python cmc_catalog_scraper.py all --from-year 1999

# Or one stage at a time
.venv/bin/python cmc_catalog_scraper.py scrape      --from-year 1999   # courses per catalog
.venv/bin/python cmc_catalog_scraper.py programs    --from-year 1999   # required/elective counts per major
.venv/bin/python cmc_catalog_scraper.py crosswalk                      # match courses across years

# A single catalog, for spot checks
.venv/bin/python cmc_catalog_scraper.py all --only 2025-2026
```

Text extraction is cached under `cache/`, so re-running a parser is fast — only the first run
pays for the downloads and OCR. Useful flags: `--only LABEL...`, `--from-year` / `--to-year`,
`--dump-text` (writes per-page text for debugging a bad parse), `--force` (re-download),
`--ocr off|auto|force`.

## Where everything is

```
cmc/
├── README.md                    this file
├── cmc_catalog_scraper.py       the script that builds everything below
├── catalog_manifest.csv         one row per catalog: pages, OCR pages, courses found, status
│
├── by_year/                     one file per catalog edition
│   ├── courses_2025-2026.csv            courses in that catalog
│   └── programs_2025-2026.csv           programs in that catalog
│
├── all_years/                   the stacked datasets, for analysis
│   ├── courses.csv                      every course from every catalog
│   ├── program_requirements.csv         required/elective course counts per major
│   ├── program_requirement_courses.csv  the courses behind each requirement
│   ├── course_crosswalk.csv             every course tagged with its lineage
│   ├── course_lineages.csv              one row per course followed across years
│   └── dept_aliases.csv                 department renames the matcher inferred
│
├── review/                      rows a person still needs to check
│   ├── program_requirements.csv
│   └── crosswalk.csv
│
├── cache/                       regenerable: downloaded PDFs + extracted page text
└── logs/                        run logs
```

**Start with `catalog_manifest.csv`** — it tells you which catalogs parsed cleanly.
`cache/` can be deleted at any time; it only costs re-downloading and re-OCR to rebuild.

### Term availability (added, mostly simulated)

[`../../add_course_timing.py`](../../add_course_timing.py) adds `terms_offered`,
`offering_pattern`, `timing_source`, `sequence_semester` and `sequence_source` to the course
files, plus `all_years/course_offerings.csv` (one row per course per term) and
`timing_ground_truth.json`.

Catalogs do not publish when courses run, so **`timing_source` is `simulated` for all but 36
rows** (4 athletics courses whose descriptions say "this fall semester pre-season…").
`sequence_semester` is a different, real field: the semester a program's recommended sequence
advises — not a statement that the course only runs then. Re-running `scrape` rewrites the course
files without these columns, so run `add_course_timing.py` again afterwards.

### Course counts per major

`all_years/program_requirements.csv` answers "how many courses does this major need?"

- `min_required_courses` — course slots you must fill from named courses. An "A **or** B" choice
  counts once; a "choose one series (PH 002A & 002B)" choice counts as the whole series.
- `min_elective_courses` — slots filled by choosing from a list ("Select eighteen (18) units from
  the following"). When the catalog gives units rather than a count, this is the *fewest* courses
  that reach those units, using the largest options available.
- `min_total_courses` — the two added together.
- `required_units_min` / `elective_units_min` — the same thing in units.
- `major_units_stated` / `program_units_stated` — the totals the catalog prints itself. **Compare
  these against the parsed units**: a mismatch over 2 units sets `needs_review`.

### Matching courses across years

`all_years/course_lineages.csv` groups the catalog records that look like the same course even when the
department code, number, or title changed. Each lineage gets a `timeline` such as
`CIS 050 Intro to Computers [2011-2012..2015-2016] -> CS 050 Introduction to Computing [2016-2017..2025-2026]`.

Links come from, strongest first: an explicit "formerly known as" note in the catalog, a shared
C-ID, the same code with the same title, a renumber with the same title, then fuzzy title and
description similarity. `match_score` and `match_method` say which, and `needs_review` flags the
weak ones. Tune with `--min-score` (default 0.70) and `--review-below` (default 0.88).

## Known limits

- Course descriptions are parsed from PDF text, so a title can absorb a stray line and a
  description can run short where the PDF's column detection failed.
- The 1999–2011 catalogs are scans. OCR misreads course numbers (`O`/`0`, `l`/`1`); the script
  repairs the obvious cases and sets `ocr_used` so you can filter them out.
- Programs are found by their award heading ("Associate in Science in X"). A program whose
  heading didn't survive extraction is missing entirely — check the count in
  `by_year/programs_*.csv` against the catalog's own program index.
- Elective course counts are a *minimum*, not what a student actually takes.
