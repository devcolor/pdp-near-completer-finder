# Synthetic College 2 and CMC student datasets

One CSV folder per institution: 1,303 students at College 2, 1,000 at Copper Mountain. **Every student, enrollment, hold, schedule
and outcome here is invented.** Course codes, titles and units come from the parsed catalogs in
[`../raw_course_catalogs`](../raw_course_catalogs), so the course metadata is real; nothing
attached to a student is. Nothing in these files is a finding about real students or either
college.

| Institution | CSV folder | Students |
| --- | --- | ---: |
| College 2 | [`college_two/csv`](college_two/csv) | 1,303 |
| Copper Mountain | [`cmc/csv`](cmc/csv) | 1,000 |

## The four files

| File | One row per | What it is for |
| --- | --- | --- |
| `students.csv` | student | Who they are, where they are, how far along |
| `student_institutional_profile.csv` | student | Circumstances: holds, parenting, work, housing, advisor |
| `course_detail.csv` | enrollment | Every course a student took, with grade and status |
| `course_schedule.csv` | section | When and where each course is actually offered |

Join `students.csv` to `course_detail.csv` on `Student GUID`,
`student_institutional_profile.csv` on `student_id`, and `course_schedule.csv` on `course_code`.

Which catalog a course came from is recorded on the rows that use it: `Catalog Source Year` and
`Source Commit` in `course_detail.csv`, `catalog_year` in `course_schedule.csv`. For the catalog
PDF a course was parsed from, see
[`../raw_course_catalogs`](../raw_course_catalogs).

## Credits to graduate, by program and year

`program_credits.csv` in each college folder answers one question per program: how many credits
does it take to finish? CMC has three catalog years, 2023-24 to 2025-26. College 2 has four, up to
2026-27, the catalog its students are held to.

| Column | Holds |
| --- | --- |
| `catalog_year`, `institution`, `program`, `award_type` | Which program, which year |
| `required_credits` | The required core |
| `optional_credits` | Electives on top of the core |
| `total_credits_to_graduate` | The total the catalog states |
| `required_source`, `optional_source`, `total_source` | `catalog`, `derived (total - required)`, or `not stated` |
| `credit_unit` | `semester credits`, or `instructional hours` for non-credit programs |
| `needs_review`, `review_reason` | Rows a person should check before using |

| | CMC | College 2 |
| --- | ---: | ---: |
| Program-years | 160 | 357 |
| Programs per year | 53 / 53 / 54 | 85 / 87 / 89 / 96 |
| Clean rows | 139 | 321 |
| `needs_review` | 21 | 36 |
| Median credits to graduate (clean rows) | 30 | 30 |

**These numbers come from the real catalogs**, not invented: CMC's published PDFs, and College 2's
online catalogs as scraped into
[`../raw_course_catalogs/college_two/program_requirements.csv`](../raw_course_catalogs/college_two#program-requirements).
Only the `derived` optional-credit figures are computed here, by subtracting the required core from
the stated total.

College 2's 2026-27 rows were added with [`college_two/build_program_credits.py`](college_two/build_program_credits.py),
which builds a catalog year's rows from that scrape. Run for 2025-26, it reproduces the existing
rows exactly. To add a year:
`python gia-pre-implementation/synthetic-datasets/college_two/build_program_credits.py 2026-2027`.

Check `needs_review` before you use a row. Three things it catches:

- **Required exceeds the stated total** — 17 CMC and 13 College 2 rows. The parser's sum of required
  courses disagrees with the total the catalog prints. Business Administration 2.0 reads 80.5
  required against a stated 62. One of the two figures is wrong and the catalog does not say which.
- **Non-credit programs count hours, not credits** — 7 College 2 rows. High School Equivalency reads
  576 and ESL 120 because those are instructional hours. `credit_unit` marks them; do not average
  them with credit programs.
- **A figure was not stated**, or the stated total is zero.

Programs are listed per catalog year because requirements change: a student should be held to the
catalog they entered under, which is why every year is kept rather than only the newest.

## College 2 pathways and real programs

College 2 students' `Target Program` is a real program from the 2026-27 catalog, written as its
`award_type` (e.g. `Welding Technology , AS`), so it joins straight to
[`../raw_course_catalogs/college_two/program_requirements.csv`](../raw_course_catalogs/college_two#program-requirements)
and to `program_credits.csv` (on `catalog_year` and `award_type`).

The students' courses were generated for eight synthetic pathways, made before College 2's requirements
were scraped. [`college_two/csv/pathway_program_map.csv`](college_two/csv/pathway_program_map.csv) is the record of
how each pathway was moved to its closest real program: the one with the most of the pathway's
courses on its list. `match` says how well it fits:

| `match` | Pathways | Means |
| --- | --- | --- |
| `good` | Building Construction Technology, Business Administration, Computer Information Systems, Welding Technology | The pathway covers over half the real program |
| `weak` | Child Development, Fire Science Technology, Arts & Humanities, Social & Behavioral Sciences | The pathway covers a third of the real program or less. Fire Science Technology covers 11% |

**The mapping is a stand-in.** The students' courses were made for the pathway, not the real
program, so progress against the real requirements describes the method, not the students. Child
Development students look far from finishing (none within 9 credits). Fire Science looks too close:
the catalog scrape lists 1.25 units for a core the catalog states as 9, and the electives list has
70 courses, so 76 of its 125 students are within 9 credits.

## Who acts on which cohort

[`service_cohort_map.csv`](service_cohort_map.csv) maps each attribute to the service area that
acts on it. Eight rows, three columns: `attribute`, `column`, `service_area`.

| Attribute | Column | Service area |
| --- | --- | --- |
| Parenting | `is_parent` | Student Services |
| Working | `employment_status` | Student Services |
| Housing | `housing_status` | Student Services |
| Student population | `student_type` | Student Services |
| Academic hold | `hold_type = Academic` | Academic Services |
| Advising hold | `hold_type = Advising` | Academic Services |
| Course term availability | `offering_pattern` | Academic Services |
| Financial hold | `hold_type = Financial` | Financial Services |

`Advising` is a third hold type in the data alongside `Academic` and `Financial`; it is filed
under Academic Services because releasing it means booking an advising appointment. Move it if
advising sits under Student Services.

## `pdp_year`: which submission year a row belongs to

PDP data is submitted one academic year at a time, and each year's file lists the students
enrolled **that** year. `pdp_year` on `students.csv` names the year a row belongs to, written
`2024-25` to match `Academic Year` in `course_detail.csv`. It is derived from
`Last Enrolled Term`, with Fall starting the academic year: `Fall 2024` and `Spring 2025` both
fall in `2024-25`.

| | CMC | College 2 |
| --- | ---: | ---: |
| Distinct years | 8 (2019-20 to 2026-27) | 8 (2019-20 to 2026-27) |
| Rows in the newest year | 526 | 769 |

**These files are a snapshot, not a multi-year submission.** Each student appears on exactly one
row, in the year they were last enrolled. So you cannot work out who failed to return by
comparing years here: every student is absent from every year but their own, which would read as
near-total attrition. The Playground's Upload page accepts real year-by-year files and switches
to counting stop-outs by absence only when an uploaded set holds two or more years; otherwise it
uses `Currently Enrolled` with credits remaining.

## Cohort columns

`student_type`, `enrollment_status` and `campus_location` are on `students.csv`;
`course_detail.csv` also carries `student_type` and `campus_location` so enrollment rows can be
grouped without a join.

### `student_type`

| Value | Means | CMC | College 2 |
| --- | --- | ---: | ---: |
| `COLC (regular)` | The ordinary credit student | 570 | 60 |
| `High school dual enrollment (former)` | Came in through dual enrollment, now regular | 120 | 25 |
| `Adult learning` | Adult education and re-entry | 120 | 30 |
| `Non-credit (MASP included)` | Non-credit enrollment, MASP among them | 100 | 20 |
| `CVC (distance learner, other college)` | California Virtual Campus — **not a stop-out**, see below | 50 | 15 |
| `Firefighter` | Fire academy and fire technology | 40 | 300 |
| `Prisoner` | Incarcerated students | — | 550 |

### `enrollment_status`

| Code | Means | Active student? | CMC | College 2 |
| --- | --- | --- | ---: | ---: |
| `ADD` | Added a course | **Yes** | 312 | 354 |
| `NEW` | New registration | **Yes** | 128 | 141 |
| `W` | Withdrew from a course | **Yes** — still enrolled in others | 75 | 73 |
| `D` | Dropped | No | 322 | 285 |
| `C` | Cancelled | No | 163 | 147 |

`ADD`, `NEW` and `W` are the active codes. `W` counts as active because withdrawing from one
course does not end a student's enrollment. The codes agree with `Currently Enrolled` on every
row, so the two never contradict each other.

### `campus_location`

| Value | CMC | College 2 |
| --- | ---: | ---: |
| `CMC Main` | 840 | — |
| `College 2 Main` | — | 363 |
| `College 2 Satellite` | — | 20 |
| `DE (distance ed)` | 160 | 67 |
| `Prison` | — | 550 |

CMC has no `Prison` location and no `Prisoner` students: it does not run a correctional
education site. At College 2 every `Prisoner` is at `Prison`. At both colleges every
`CVC` student is `DE`, and everyone else is at their main campus with about one in eight at a
distance.

## CVC students are not stop-outs

`CVC` is the **California Virtual Campus**. A student enrolled at any other California community
college can take a single class online here. They take courses a la carte — one or two, usually
one term — and then they are gone. They were never working towards a credential here, so leaving
is the normal end of the arrangement, not a student dropping out.

That matters because **they look exactly like stop-outs and are not**. 54 of the 65 read as no
longer enrolled. Counted as stop-outs they would inflate the number while being nobody's to call
back. The data is shaped to match: 1 or 2 course rows each in a single term (against 15 for a
regular student), `Credential Type Sought` of `Not seeking a credential here`, and
`Demo Scenario` of `CVC a la carte (not a stop-out)`.

`excluded_from_outreach` is `TRUE` for all 65. **Filter on it before you build a call list or
report a stop-out rate.** They are flagged rather than deleted so you can measure how much they
would have distorted the figure.

## Course schedule

`course_schedule.csv` replaces the old `course_offerings.csv` and `remaining_requirements.csv`,
which only said whether a course existed, never when it met.

| Column | Example |
| --- | --- |
| `section` | `012`, `W01` for online |
| `course_code`, `course_title` | `ANTH 001`, `INTRODUCTION TO PHYSICAL ANTHROPOLOGY` |
| `instructor` | `R. Tanaka` |
| `meeting_day` | `MW`, `TTh`, `MWF`, `M`–`Th`, `S`, `Async` |
| `meeting_time` | `08:00-09:25`, `18:00-20:50`, `n/a (async)` |
| `location` | `CMC Main`, `College 2 Satellite`, `Prison`, `DE (distance ed)` |
| `catalog_year`, `program`, `terms_offered`, `offering_pattern` | `2025-2026`, `BIOLOGY`, `Fall;Spring`, `fall_only` |

| | CMC | College 2 |
| --- | ---: | ---: |
| Sections | 676 | 870 |
| Courses | 319 | 431 |
| Evening sections (18:00) | 186 | 228 |
| Saturday | 47 | 53 |
| Online, asynchronous | 72 | 121 |

Each course has one to three sections. Sections sit where that college's students are, so College 2
runs more at `Prison` than at `College 2 Main`. Evening, Saturday and asynchronous sections exist
specifically so work and caring conflicts can be tested — that was impossible before, because
no file recorded when anything met.

Instructor names are invented. They are not staff at either college.

## How far along a student is

`students.csv` carries each student's progress on their major: `Total Major Courses Required`,
`Major Courses Completed`, the remaining count, the remaining course codes, credits applied and
remaining, and `program_required_courses` (every course on the major's lists). They are worked out
from `course_detail.csv` and each college's own catalog requirements (CMC 2025-26, College 2 2026-27)
by [`rebuild_major_progress.py`](rebuild_major_progress.py), with the rule in
[`measures/major_requirements.py`](../../measures/major_requirements.py) that the near completers
measure uses too:

- A course counts if it's on the major's list and was passed: 2.0 grade points or more, or `P`.
  A retake that passed counts; each course counts once. CMC's `course_crosswalk.csv` maps old codes
  to current ones. College 2 has no crosswalk, so a course passed under a pre-2025 code doesn't match its
  CCN code (e.g. `HIST C1001`).
- A choice group ("6 units from the electives list", "choose 1") counts only up to what it asks
  for. For alternatives, the closest one counts. The remaining codes list every course that could
  still fill an open group; the remaining count is the fewest courses that would finish the major.
- CMC Computer Science has a plain and a transfer version for the same award; students are held to
  the transfer one, which their courses were made for. CMC's courses file repeats some programs on
  other pages; only the program's own first page is used. For History, the old pathway list came
  from another page (114) than the one the program points to (6), so History students moved the most.

Rerun the script after changing the rule or the data; `measures/tests/test_near_completers.py`
fails if `students.csv` is out of date.

## Cohort, last term and enrollment agree

[`repair_enrollment_terms.py`](repair_enrollment_terms.py) fixes two contradictions the generator
left in `students.csv`. It changes only `Cohort` and `Last Enrolled Term`:

- **Left before the cohort began.** A `Last Enrolled Term` before the cohort's academic year moves
  the cohort, not the term, because `course_detail.csv` backs up the term. The cohort becomes the
  academic year of the student's first course, or of the last term when the student has no courses
  (some College 2 students have none). 18 CMC and 25 College 2 cohorts moved.
- **Enrolled, but last seen in an old term.** A student with `Currently Enrolled = Yes` gets the
  `Reference Term` (the term in progress) as their `Last Enrolled Term`, so it agrees with
  `Currently Enrolled` and `enrollment_status`. 1 CMC and 66 College 2 terms moved.

Rerun it after regenerating `students.csv`; `measures/tests/test_synthetic_terms.py` fails if either
contradiction comes back.

Near completion refers to the major only. General education, residency, substitutions and
prerequisite sequencing are **not** audited, and `All Graduation Requirements Met` stays `Unknown`
for every student. `Demo Scenario`, `Credential Earned` and `validation.json` record how the
generator made each student (`Near completer`, `Core complete` and so on, against the old lists),
not where they stand now, so they can disagree with the progress columns.

## Where the data comes from, and what it does not claim

- **Catalog metadata is real.** Course codes, titles and units are parsed from published
  catalogs. Histories for 2019-20 to 2026-27 use each year's own catalog; newer courses are
  never backfilled into older years.
- **CMC students are held to the 2025-26 catalog.** Majors use the parsed requirement groups in
  [`../raw_course_catalogs/cmc/all_years`](../raw_course_catalogs/cmc), whose output still contains
  ambiguous alternatives. Program selections are unverified.
- **College 2 students' courses were made for synthetic pathways.** Their `Target Program` is now the
  closest real 2026-27 program (see [College 2 pathways and real programs](#college-2-pathways-and-real-programs)),
  and their progress is measured against its real requirements.
- **Awards are simulated.** `Credential Earned` is a recorded outcome for selected scenarios,
  not inferred eligibility. No registrar or degree-audit source is claimed.
- **Dual enrollment coding is unverified.** `MIS Admit Status` stays `Unknown` for CMC; College 2's
  `Special admit` is a mock label, not a validated MIS code.
- **Measures**: retention is enrollment in the next academic year; persistence previously relied
  on an external-enrollment file that has been removed, so treat `Persistence` as a stored flag
  with no supporting rows. Gateway flags use synthetic required/not-required values with
  generated year-one attempts; they are not institutional designations. Numeric grades are grade
  points, and `W` denotes withdrawal.
- **The mixes are chosen for coverage, not realism.** Demographic, program, cohort and outcome
  allocations exist so every group has usable numbers. They are not observed enrollment rates at
  either college, and no causal relationship is implied.
- **Reproducibility**: College 2 seed 202611091524, CMC seed 202611091513, both pinned to catalog
  source commit `56c6354`. Cohort columns and the course schedule were added afterwards and are
  seeded from each student or course id, so they are stable across reruns.

## Known gaps

- **Hold dates are a single snapshot.** `as_of_date` is one date for every student, so you cannot
  show a hold came before a student left. This is the most useful field to fix next.
- **`College 2 Satellite` has 20 students**, enough to chart but small.
- **Course timing is simulated.** `terms_offered` and `offering_pattern` come from a generator,
  not a published schedule — only 36 rows across the CMC catalogs state a season outright. Check
  `timing_source` in the catalog files before relying on it.
- **20 non-starters were added on purpose**, 10 per college, who enrolled and earned nothing,
  because the original data had almost no one at that end of the spectrum.
