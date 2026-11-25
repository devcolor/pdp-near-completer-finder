# Current readiness and next decisions

This section covers where the work stands today, what a campus needs before it can use it, the
risks to plan for and the recommended next builds.

> **All data here is synthetic.** Everything described here runs on synthetic students
> only. Nothing has run on real student records yet.

## Where things stand

| Area | Status | What that means |
| --- | --- | --- |
| **Dashboard** | Built | Executive, student services, academic and financial views, with filters for credits left, dates, programs, holds and parenting |
| **Near-completer and stop-out counts** | Built and tested | The dashboard and the measure use the same rules, and automated tests check that their numbers match |
| **Data upload** | Built | A college can replace its files on the upload page. Files missing a required column are rejected |
| **Year-over-year stop-outs** | Built, not yet tried on real data | Works when a college uploads two or more years. The synthetic set has only one |
| **Program requirements** | Partly ready | Read from real catalogs, but 208 of CMC's 382 programs and 95 of College 2's 497 still need review |
| **Login and access control** | Not built | Anyone with the link can see every view. This must be in place before real data goes in |
| **Saved uploads** | Temporary | On the hosted version, uploaded files are lost whenever the server restarts |
| **Degree audit** | Not built | Credits left covers the major only |
| **Hold dates** | Not available | Every hold has the same date |
| **Transfer records** | Not available | The data can't tell a transfer from a stop-out |

**In short:** the method works and the dashboard is ready to demo. It is not ready for real student
data until login, secure storage and a data agreement are in place.

## What a campus needs before a pilot

A campus is ready to pilot when it can say yes to each of these.

### Data

- [ ] At least two years of PDP submissions, so stop-outs can be found by who didn't come back
- [ ] A current enrollment export, refreshed at least once a term
- [ ] Registration holds with the date each one was placed and its type (drilling down into different hold sub-types as well)
- [ ] Program requirements for each catalog year, checked by someone in the registrar's office
- [ ] A way to link old course codes to new ones, if the college has renumbered/renamed courses

### People

- [ ] A named owner for the outreach list in each office: Student Services, Academic Services and
      Financial Services
- [ ] An advisor who can run a full degree audit before a student is told how close they are
- [ ] A data contact who can prepare the files and answer questions about them

### Approval

- [ ] Sign-off from the college's FERPA or data governance lead
- [ ] An agreed place to host the dashboard, behind the college's own network
- [ ] A plan for how staff record what happened after each outreach contact for outcomes tracking

## Risks

| Risk | Why it matters | How to reduce it |
| --- | --- | --- |
| **Contacting the wrong student** | A student who graduated, transferred or just re-enrolled gets an outreach call | Check the student information system before every contact. Add transfer records when possible |
| **Student data seen by the wrong people** | There is no login today | Build login and role-based access before any real data is uploaded |
| **Uploaded files lost or left on a shared server** | The hosted version stores uploads temporarily | Move uploads to secure, permanent storage the college controls |
| **A link read as a cause** | Staff might assume a hold or a job is why a student left | Train staff on the limits. Label circumstances as "present," not "the reason" |
| **The wrong barrier addressed first** | Circumstances aren't ranked, so outreach may start in the wrong place | Ask the student what matters most. Record the answer so the data improves over time |
| **Overstating how close a student is** | Credits left skips general education and some rules | Require a degree audit before giving a student a number |
| **Numbers that don't match other reports** | Staff lose trust if the dashboard disagrees with the registrar's figures | Agree on definitions up front and reconcile a sample by hand before launch |
| **No one owns the list** | A dashboard nobody acts on changes nothing | Name an owner in each office before the pilot starts |

## What to build next

In priority order:

1. **Login and access control.** Each office should see only the students it serves.
2. **Secure, permanent storage for uploads.** Files should live somewhere the college controls,
   not on a temporary server.
3. **Dated holds.** With real dates, to show whether a hold came before a student left.
4. **Each student's own catalog year.** Hold students to the catalog they're entitled to, not one
   catalog for everyone.
5. **A course code crosswalk for College 2.** Its 2025 renumbering makes some students look further
   from finishing than they are.
6. **Outreach tracking.** Let staff record who was contacted, what the student said was getting in
   the way and whether they came back. Over time, this shows which barriers matter most, something
   the data can't show today.
7. **Transfer records.** Separate students who transferred from students who stopped out.

## Open decisions

- **Which campus pilots first?** It should be the one that checks the most boxes above.
- **Who owns the outreach list in each office?**
- **What should the default credit cutoff be?** The dashboard uses 9 today. A college may prefer
  another number.
- **Where will the dashboard be hosted, and behind whose login?**
- **What data sources come next?** Holds with dates, transfer records and degree audits are the
  three that add the most.
- **How will the college know it worked?** For example: how many contacted students re-enrolled within one
  term, compared with similar students who weren't contacted.
