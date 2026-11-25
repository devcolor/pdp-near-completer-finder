# Near completers

**Status:** built as `near_completers` in [`measures/`](../../measures/README.md#near-completers-on-the-cmc-and-college-2-datasets),
on the synthetic CMC and College 2 datasets. The decisions below settle the questions this
spec left **Open**; the rest of the spec is kept as written.

> The data is synthetic. Nothing built on it is a finding about real students or institutions.

## Decisions

| Open question | Decided |
| --- | --- |
| Threshold | **9 credits** by default (steps of 3), a parameter: `run_measure(..., threshold=)` |
| Stopped enrolling | **Not required.** A student still enrolled and close to finishing counts |
| Credits left (step 4) | **A, major requirements only.** The major's required and choice-group units not yet passed. General education isn't counted |
| Data | The synthetic CMC and College 2 datasets, not the PDP mock data, loaded by `measures/load_synthetic.py`. Their courses use real CMC and College 2 codes, so the course-matching gap below doesn't apply |
| Finding the program (step 1) | CMC: `Degree Program (Major)`, matched by name to CMC's requirement files. College 2: `Target Program`, now the real program's `award_type`, moved from the synthetic pathways with `pathway_program_map.csv`. No CIP mapping is needed |
| Ambiguous program | CMC Computer Science has two versions for one award; students are held to the transfer one, which their courses were made for. Any other ambiguous major gets `no_requirements` |
| Catalog year (step 2) | The catalog the datasets hold students to: CMC 2025-26, College 2 2026-27 |
| Course codes (step 3) | CMC's `course_crosswalk.csv` maps old codes to current ones. College 2 still has no crosswalk |
| Grouping | Also by `major` |
| Out of scope | Students who earned a credential (`Credential Earned = Yes`, CMC only) and CVC students (`excluded_from_outreach`) |
| `not_yet_observable` | Not used: every cohort has answers |

The rule is in `measures/major_requirements.py`. `rebuild_major_progress.py` writes the same numbers
into each dataset's `students.csv`, so the dashboard and the measure agree.

A new success measure in [`measures/`](../../measures/README.md): the share of students who are
close to finishing a program's credit requirement. It follows the same `MeasureResult` contract as
the other measures. [The near-completer guide](../examples/near_completers_guide.md) shows how an
advisor would use a measure like this.

## Definition

A **near completer** is a student who is 10 credits or fewer short of their program's credit
requirement and hasn't earned the credential.

**Open:**

- **Threshold.** 10 credits here; the guide uses 15. The threshold should be a parameter, not a
  hard-coded number.
- **Stopped enrolling.** The guide also requires a stop-out: the student didn't persist (see
  [Terms](#terms)) into the latest term. Without it, a student who is still enrolled and on track
  counts too.

## Terms

This spec uses these definitions. Where `measures/` uses the same name for something else, the
difference is noted.

| Term | Means here | How `measures/` uses the name |
| --- | --- | --- |
| **Passing grade** | 2.0 grade points or more (a C or better), or `P` | DFW uses the same 2.0 line. The gateway measures use PDP's flag, which is 1.0 or more |
| **Persistence** | The student enrolled again in the next academic year, or earned a credential by then | `measures/` calls this `retention`. Its `persistence` means enrolled at *another* institution by year 2 |
| **Retention** | The student finished a course and got a grade, so it didn't end in a withdrawal (`W`) or an incomplete (`I`) | No measure does this. `measures/` uses the name for the next-year return above |
| **Credit completion** | Per student: one student's credits earned divided by that student's credits attempted. A cohort's figure is the average of those per-student ratios, not the cohort's total earned divided by its total attempted | `credit_completion` already works this way, for year 1 |

## How it's calculated

1. **Find the student's program** in the CMC or College 2 catalog data.
2. **Look up the program's requirements** for the student's catalog year: total units, required
   courses and choice groups ("choose 6 units from List A").
3. **Match the student's completed courses** to those requirements. A course counts if it's on the
   program's list and was passed.
4. **Work out the credits left:** the program's required credits minus the credits the matched
   courses cover.
5. **Flag near completers:** students with credits left above 0 and at most the threshold (10).

### Step 1: finding the program

Students have a CIP code (`cohort_membership.program_of_study_term_1`, e.g. `240101`) and a
credential sought (`credential_type_sought_year_1`). The catalogs list programs by name and award
(e.g. `Kinesiology`, `AA-T`) with no CIP code.

- **Needed:** a mapping table from program to CIP code and award. Some CIP codes cover several
  programs, such as AA and AS-T in the same subject.
- **Open:** if a CIP code matches more than one program, pick one by a rule (for example the
  credential sought), or exclude the student.

### Step 2: catalog year

**Open:** which catalog's requirements apply. The usual rule is catalog rights: the catalog in
effect when the student started (`cohort`). The mock cohorts are 2021-22 to 2024-25, and both
colleges have catalogs for every one of those years.

### Step 3: matching courses

Course rows are in `course_enrollment` (joined to `course`). A course counts when:

- its code matches a requirement course, after mapping old codes to new ones (for example College 2's
  2025 move to CCN codes like `ENGL C1000`, or CMC's `course_crosswalk.csv`)
- the grade is passing: a C or better, meaning 2.0 grade points or more (`2`, `2.3`, `3.7` and
  so on), or `P` for a pass. Everything else doesn't count: below 2.0, `F`, `W`, `I`, `O`, `OTH`,
  `UNKNOWN` and blank. This is the same 2.0 line the DFW measure uses (`DFW_BELOW` in
  `measures/calculations/dfw.py`). It is not the gateway measures' 1.0: that comes from PDP's own
  gateway flag in the cohort file.
- each course counts once, even if retaken (`attempt_number`). If any attempt passed, the course
  counts.

Choice groups count up to what they ask for. If a group asks for 6 units and the student passed 9,
it counts 6.

### Step 4: credits left

**Open:** which of two definitions to use.

- **A. Major requirements only.** Credits left = the major's required and choice-group units not
  yet met. This needs the course matching in step 3.
- **B. Total program units.** Credits left = the program's stated units (e.g. 60 for an AS-T)
  minus that student's credits earned (`number_of_credits_earned_yr_1` to `_yr_4`). Each student is
  worked out on their own, never from cohort totals. This works on the mock data now, but counts
  every course, including ones that don't apply to the program. The guide warns against this.

One option is to build B first, then A once course matching works.

## The result row

| Contract field | For near completers |
| --- | --- |
| Cohort and group filters | Same cohorts and groups as other measures. Possibly also by college and program |
| Denominator | Students in scope with a known program and credits left |
| Numerator | Of those, students with credits left above 0 and at most the threshold |
| Rate | Numerator / denominator |
| Status | `ok`; `suppressed` when the denominator is under 10; `not_yet_observable` when nobody in the cohort has had enough time (**Open:** what counts as enough, for example 2 years observed) |
| Exclusions | New reasons: `no_program_match` (CIP code matches no program), `ambiguous_program`, `no_requirements` (program has no requirements for that catalog year), plus `unknown_outcome` |
| Out of scope | Students who have already earned the credential (`first_year_to_a_or_c_at_cohort` set), re-admit and continuing students (**Open**) |
| Definition and source | The `note`: the threshold, the credits-left rule, the catalog year rule, and the source files |
| Data-load timestamp | `data_loaded_at`, the same as other measures |

## Inputs

| Input | Where | Status |
| --- | --- | --- |
| CMC programs and requirements | `gia-pre-implementation/raw_course_catalogs/cmc/all_years/program_requirements.csv`, `program_requirement_courses.csv` | Exists. 208 of 382 programs are flagged `needs_review` |
| College 2 programs and requirements | `gia-pre-implementation/raw_course_catalogs/college_two/program_requirements.csv`, `program_requirement_groups.csv`, `program_requirement_courses.csv` | Exists for 2021-22 to 2026-27: 497 programs, 95 flagged `needs_review`. Groups nest, so the groups file is needed |
| Course code crosswalks | CMC `course_crosswalk.csv`; College 2 none yet | College 2 needs one for the CCN codes |
| Program to CIP code mapping | New file | Not started |
| Student courses and credits | `pdp.sqlite`: `course_enrollment`, `course`, `cohort_membership` | Exists |

## Known gap in the mock data

The mock PDP course data uses Texas-style codes (`ENGL 1302`), not CMC or College 2 codes:

- Only 14 of 83,196 course rows match a CMC requirement course.
- 11,099 rows match a College 2 course code, but most likely by chance.

Course matching (step 3) will find almost nothing on this data. Testing it needs fixture students
who took real CMC or College 2 courses.

## How we'll know it works

- **Fixtures:** about 5 hand-built students with known answers: 0 credits left, 5 left, exactly
  10 left, 11 left, and no program match. A test checks that each lands in the right
  numerator, denominator or exclusion.
- **Choice groups:** a student who passed more courses in a group than it asks for gets only the
  group's units.
- **Contract:** `make check` passes, and the measure appears in `run_measures` like the others.
- **Spot-check:** compare 3 College 2 programs from the CSV against the catalog website by hand.

## Out of scope for now

- College 2 catalogs before 2021-22 (PDFs). They aren't needed for the mock cohorts.
- General education patterns (CalGETC, IGETC) as course lists. Definition B covers GE through
  total units.
- Registration holds. `sources/registration_holds/` is a draft and isn't loaded yet.
