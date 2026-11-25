# Known issues

An honest list of what doesn't work, what only works on your own computer, and what hasn't been
tested. All data in this repo is synthetic. Nothing here is a finding about real students or
colleges.

## Bugs

| Bug | What you'll notice | Code |
| --- | --- | --- |
| An upload keeps one course per student per year | After uploading `course_detail.csv`, attempt counts and "next offered" for courses still owed are wrong. Student counts, stop-outs and near completers are right. | `_merged` in `playground/server_application/app/institution_dashboard/uploads.py` |
| Course drop and fail rates ignore uploads | The "high drop/fail" course flags keep describing the synthetic data after an upload. | `_course_rates` in `institution_dashboard/data.py` |
| A blank credits value gives a misleading error | The dashboard says "Unknown filter for this institution." when a student row has a blank or non-number credits value. | `float()` in `_students`, `data.py` |
| A student with no profile row breaks the page | The dashboard errors for that college if a student in `students.csv` has no row in `student_institutional_profile.csv`. | `profiles[...]` in `_students`, `data.py` |
| "Stop-outs within N credits" also lists enrolled students | Picking a credit band lists every student that close to finishing, enrolled or not. The stop-out tiles are right. | `_is_near` in `build_dashboard`, `data.py` |
| A very large upload can run the API out of memory | The 15 MB per-file limit is checked only after the whole file is read into memory, so a much larger upload can exhaust the server before it is rejected. Uploads and the dashboard also need no sign-in (see "Not tested"). | `await incoming[filename].read()` in `routes.py`; `MAX_BYTES` in `uploads.py` |

## Mock-data quirks

- **Achieving the Dream PDP files (`data/raw/`):** 52 logged issues, such as Race labels cut at 25
  characters, codes that lost leading zeros, mixed "no value" markers, and 2 students in two
  cohorts. Each has a count and a proposed fix in
  [`data/quality/findings.csv`](../data/quality/findings.csv); see the
  [data quality README](../data/quality/README.md) and the normalized model's
  [things to know before you query](../normalized-data-model/README.md#things-to-know-before-you-query).
- **Synthetic College 2 and Copper Mountain files:** hold dates are one snapshot, course timing is
  simulated, College 2's synthetic pathways are matched to real programs with some weak fits, and
  20 non-starters were added on purpose. See
  [Known gaps](../gia-pre-implementation/synthetic-datasets/README.md#known-gaps).

## Only works on your own computer

- **Uploads that last.** On Vercel, uploads are saved to `/tmp` and are lost when the service
  restarts. Run the API locally to keep them.
- **The normalized data model, MCP server, shared measures and gap finder.** None of them are
  deployed; they run from a local clone.

## Not tested

- Any real college data. Every test used synthetic data.
- Uploading on a hosted deployment. Upload testing was done on a local copy.
- Security, privacy, accessibility, and use at the scale of a whole college.
- Quarter-based term calendars. The dashboard expects semester terms.
