# Key definitions and assumptions

This section explains what each number on the dashboard means, which period of time it covers,
and who it leaves out. The goal is simple: anyone reading a figure should know exactly what it
counts.

> **All data here is synthetic.** These figures show how the method works. They are not findings
> about real students or real colleges.

## The two colleges

The dashboard and measures run on two colleges, each modeled on real California
community college course catalogs.

| | CMC | College 2 |
| --- | --- | --- |
| Students | 1,000 | 1,303 |
| Catalog used for requirements | 2025-26 | 2026-27 |
| Years of course history | 2019-20 to 2026-27 | 2019-20 to 2026-27 |

## What the dashboard measures

### Stop-out

A stop-out is a student who left the college while they still had credits to finish in their
major.

Three things must all be true:

1. **They left.** They aren't enrolled now. When a college sends two or more years of data, the
   dashboard checks instead whether the student is missing from the most recent year.
2. **They still owe credits.** A student who leaves with nothing left to finish has most likely
   graduated, so the count leaves them out.
3. **The term they left in has ended.** Students who last attended the current term are counted
   separately, as described next.

### Not enrolled this term

These students meet every part of the stop-out definition except one: their last term is the one
happening now. That term isn't over yet, so it's too early to say whether they've left. The dashboard
shows them on their own line and doesn't call them stop-outs.

### Near completer

A near completer is a student who is 9 credits or fewer away from finishing their major.

- **The cutoff can change.** Staff can choose 3, 6, 9, 12, 15 or 24 credits.
- **They don't have to have left.** Students who are still enrolled count too. That way advisors
  can reach them before they stop out, not after.
- **The default view shows every stop-out.** When the page first opens, no cutoff is applied.
  Choosing a cutoff narrows the list to near completers.
- **Zero credits has its own meaning.** Choosing 0 shows students who haven't started their major
  at all.

### Credits left in the major

This is the number of credits a student still needs to finish their major's requirements. The dashboard
works it out for each student, one at a time, from the courses they've taken.

- **A course counts when it's required for the major and the student passed it.** Passing means a
  C (2.0) or better.
- **Retakes count once.** If any attempt was a C or higher, the course counts.
- **Elective groups have a cap.** If a major asks for 6 credits from a list and the student passed
  9, only 6 count.
- **This covers the major only.** General education, residency rules and course substitutions are
  not checked. This is a planning estimate, not a degree audit.

### Student circumstances

The dashboard also shows what might be getting in a student's way. Each one points to the office best placed
to help.

| Circumstance | What it means | Office that can act |
| --- | --- | --- |
| Parent | The student is raising a child | Student Services |
| Working | The student works full time or part time | Student Services |
| Financial hold | A financial issue is blocking registration | Financial Services |
| Academic or advising hold | An academic or advising issue is blocking registration | Academic Services |

A student can fall into more than one group, so the percentages won't add up to 100%.

## Time periods

| Term | What it means |
| --- | --- |
| **Current term** | The most recent term anyone in the data attended. Its stop-outs aren't counted until it ends |
| **Last term attended** | The term a stop-out left in. The dashboard's date range filters on this |
| **Starting year** | The academic year a student first enrolled |
| **Academic year** | Runs Fall through Summer. Fall 2024 and Spring 2025 are both in 2024-25 |
| **Catalog year** | The catalog that sets the requirements. Each college uses one catalog for every student |

The date range applies to stop-outs only. Students who are still enrolled all share the current
term, so filtering them by date would hide every near completer.

## Who the counts leave out, and why

| Who | Left out of | Why |
| --- | --- | --- |
| **Online visiting students** from other colleges (California Virtual Campus) | Stop-outs, near completers and outreach lists | They take one or two classes here while enrolled somewhere else. Leaving is the expected end, not a stop-out. Counting them would add 54 false stop-outs. The data flags them rather than deleting them, so the dashboard can show how many it set aside |
| **Non-credit students** | The whole dashboard | They aren't working toward a degree or certificate, so leaving isn't stopping out |
| **Students who already earned their credential** | Near completers | They have nothing left to finish |
| **Students who owe no credits** | Stop-outs | They most likely graduated |
| **Students whose major has no readable requirements** | Near completers | Without the requirements, the dashboard can't work out credits left |
| **Any group under 10 students** | Shared measure results | The measures hide small groups to protect students. This helps, but it isn't a full privacy guarantee: a hidden number can sometimes be worked out from the others |

## Assumptions

- **One catalog per college.** Every student is held to the same catalog. In practice, students
  usually follow the catalog from the year they started. A real rollout should do the same.
- **Matching students to programs took judgment.** CMC offers two versions of Computer Science for
  the same award; the data holds students to the transfer version, which matches their courses.
  Each College 2 student follows the closest real program.
- **College 2's course codes changed in 2025, and nothing links old codes to new ones yet.** Some
  College 2 students may show more credits left than they really have.
- **Hold dates are a single snapshot.** Every hold has the same date, so the data can't show whether
  a hold came before a student left. It can show that holds and stop-outs appear together. It can't
  show that one caused the other.
- **The student mix was chosen so every group has enough people to measure.** It doesn't reflect
  real enrollment at either college.
- **Graduation records are simulated.** They show how each synthetic student was created, not
  whether they're actually eligible to graduate.

## For the data team

The dashboard and the near-completer measure use the same rules, so their numbers match. The code
is the final word:

- [`data.py`](../../playground/server_application/app/institution_dashboard/data.py): stop-outs,
  current term, filters and exclusions
- [`major_requirements.py`](../../measures/major_requirements.py): credits left in the major
- [`measures/README.md`](../../measures/README.md): the measure format, small-group hiding and the
  other success measures
- [Synthetic datasets README](../../gia-pre-implementation/synthetic-datasets/README.md): field
  names, how the data was made and known gaps

| Plain term | Field |
| --- | --- |
| Enrolled now | `Currently Enrolled` |
| Credits left | `Units Remaining` (CMC), `Credits Remaining` (College 2) |
| Last term attended | `Last Enrolled Term` |
| Online visiting student | `excluded_from_outreach` |
| Parent | `is_parent` |
| Working | `employment_status` is `Full-Time` or `Part-Time` |
| Hold, and its type | `reg_hold_status`, `hold_type` |
