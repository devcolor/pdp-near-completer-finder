# How data gets into the dashboard

Where the dashboard reads its data, how uploads replace it, and how to change the synthetic data
safely. All data in this repo is synthetic. For where the data comes from and how to replace it
with a real PDP export, see [data/README.md](../data/README.md).

## Two data sets, used by different parts

| Data | Where | Used by |
| --- | --- | --- |
| Achieving the Dream mock PDP files (cohort and course) | `data/raw/` | The normalized data model, gap finder, MCP server and data-quality checks. **Not the dashboard.** |
| Synthetic College 2 and Copper Mountain students | `gia-pre-implementation/synthetic-datasets/<college>/csv/` | The dashboard. `<college>` is `cmc` or `college_two`. |

Both are synthetic. The College 2 and Copper Mountain files use real course codes, titles and
program requirements from each college's public catalog; everything about a student is invented.
Their columns, how they were generated and their known gaps are in the
[synthetic data README](../gia-pre-implementation/synthetic-datasets/README.md).

## How data gets into the dashboard

The dashboard has no database for its data. The API reads CSV files and the web app asks the API.

```
CSV files ──read by──> API (playground/server_application) ──JSON──> web app (playground/client_application)
```

1. **Where the API looks.** For each college it reads `<data root>/<college>/csv/`. The data root
   is `DASHBOARD_DATA_DIR` if set, otherwise `gia-pre-implementation/synthetic-datasets/`. The
   code is in `playground/server_application/app/institution_dashboard/data.py`.
2. **What it reads.** Four files per college, plus one shared map at the data root:

   | File | One row per | Used for |
   | --- | --- | --- |
   | `students.csv` | student | Stop-outs, near completers, credits remaining, every filter |
   | `student_institutional_profile.csv` | student | Holds, parenting, work, housing |
   | `course_detail.csv` | enrollment | Courses taken, attempts, course drop and fail rates |
   | `course_schedule.csv` | course section | When a course still owed is offered next |
   | `pathway_map.csv` (data root) | major | Which pathway each major belongs to |

   Joins: `students.Student GUID` = `student_institutional_profile.student_id` =
   `course_detail.Student GUID`; courses still owed join `course_schedule` on `course_code`.
3. **Uploads replace the synthetic files.** The Upload page sends the four files to
   `POST /api/v1/uploads`, which checks their columns and saves them to `<upload dir>/<college>/`.
   The upload dir is `DASHBOARD_UPLOAD_DIR` if set, otherwise `<data root>/uploads/`. When that
   folder has a `students.csv`, the API reads it instead of the synthetic files.
   - Uploading a year (`pdp_year`) replaces that year's rows and keeps the others, so years add up
     across uploads. The profile and schedule files are replaced whole.
   - `DELETE /api/v1/uploads` removes a college's upload and goes back to the synthetic files.
   - Course drop and fail rates always come from the synthetic `course_detail.csv`, even after an
     upload.
4. **Changes show up without a restart.** The API caches each file per version, so an edited CSV
   or a new upload is read on the next request.
5. **On Vercel**, the API's build copies `synthetic-datasets/` into the server folder and
   `DASHBOARD_DATA_DIR=synthetic-datasets` points at it. Uploads go to `/tmp` and are lost when the
   service restarts. See [deploy.md](deploy.md).

## Changing the synthetic data

Edit the CSVs in `gia-pre-implementation/synthetic-datasets/<college>/csv/`, then rerun the two
scripts that keep them consistent. The tests fail if either is out of date.

```bash
python gia-pre-implementation/synthetic-datasets/repair_enrollment_terms.py   # cohort and last term agree
python gia-pre-implementation/synthetic-datasets/rebuild_major_progress.py   # credits remaining match the catalog
```

Never edit the files in `data/raw/`: their checksums are checked by `scripts/check.py`.
