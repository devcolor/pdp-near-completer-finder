# Data provenance and replacement

## Bundled mock data

The PDP-shaped files in [`raw/`](raw/) were provided by Achieving the Dream (ATD) as synthetic
examples. They contain no real student records. Nothing calculated from them is a finding about
real students or institutions.

| File | Rows | Columns | Contents |
| --- | ---: | ---: | --- |
| [`pdp_cohort_data.csv`](raw/pdp_cohort_data.csv) | 10,313 | 85 | Student cohort records |
| [`pdp_course_data.csv`](raw/pdp_course_data.csv) | 100,951 | 35 | Student-course-term records |

The dashboard itself uses a separate synthetic dataset: 1,303 invented students for College 2 and
1,000 for Copper Mountain. Their course catalog information is based on public college catalogs;
the students, enrollments, holds, schedules and outcomes are invented. See the
[dashboard dataset documentation](../gia-pre-implementation/synthetic-datasets/README.md) for
details. Where the dashboard reads these files, and how uploads replace them, is in
[docs/data-flow.md](../docs/data-flow.md).

## Replacing the dashboard data with a real PDP export

The dashboard does not load the two raw PDP files above directly. Its Upload page expects four CSVs
per institution, with the dashboard's required column names:

| File | Contains |
| --- | --- |
| `students.csv` | Student program, credits, enrollment status and cohort |
| `student_institutional_profile.csv` | Holds and student circumstances |
| `course_schedule.csv` | Course sections, times and locations |
| `course_detail.csv` | Student course records |

Map the PDP export fields to these required columns, include `pdp_year` in the year-based files,
and upload them through the dashboard's Upload page. A PDP export needs mapping and definition
checks before it fits this dashboard; the upload does not perform that translation for you. Check
the dashboard's required-column list, confirm local definitions for stop-out and near-completer,
then compare totals and sample records against the source before anyone acts on the results.
Uploads for a year replace that year's student and course rows; profile and schedule files are
replaced as a whole. See the API's [upload requirements and validation](../playground/server_application/app/institution_dashboard/uploads.py)
and [how uploaded files are read](../playground/server_application/app/institution_dashboard/data.py).

## FERPA and student privacy

**Never commit, push, attach, or share real student exports, PDP files, screenshots, or database
dumps in this repository.** FERPA is the US Family Educational Rights and Privacy Act, a federal
student-privacy law. This warning applies to every branch and commit history; deleting a file later
does not remove it from history. Keep real exports outside the repository and use only a machine
and hosted service approved by your college. If real data is committed accidentally, contact your
privacy or compliance office promptly and follow your college's incident process. This is not legal
advice.

## Data-use terms

The repository's [MIT License](../LICENSE) applies to code, not to data. The bundled synthetic data
is provided for demonstration and testing; this repository does not grant a separate data license.
Check with the relevant source before redistributing catalog-derived material or using any data
outside this project.
