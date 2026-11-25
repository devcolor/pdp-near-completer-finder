# Limits on interpretation and use

This section is about what a user cannot infer from the dashboard. It covers the questions the data can't
answer, the known gaps and the points where a person needs to check the work before anyone
acts on it.

> **All data here is synthetic.** These figures show how the method works. They are not findings
> about real students or real colleges.

For what each number means, see [Key definitions and assumptions](4-key-definitions-and-assumptions.md).

## Questions the dashboard can't answer

| Question | Why not |
| --- | --- |
| **Why did a student leave?** | The dashboard shows what was true when a student left, such as a hold or a job. It can't show what made them leave. Hold dates are one snapshot, so the data can't even show whether a hold came first |
| **Who will stop out next?** | Nothing here is predictive. It counts who has already left and who is close to finishing |
| **Is this student ready to graduate?** | Credits left covers the major only. General education, residency and substitutions aren't checked, so it can't confirm a student is eligible to graduate |
| **Did a student transfer, or stop out?** | The data has no record of where students go next. A student who moved to a university looks the same as one who stopped out |
| **How do real students at these colleges compare?** | The students are synthetic. The mix of groups was chosen so every group has enough people to measure, not to match real enrollment |
| **Which college is doing better?** | The two colleges use different catalogs, different program lists and different data. Their numbers aren't built to be compared side by side |
| **Are some groups of students treated unfairly?** | Any gap between groups reflects how the synthetic data was made, not how a college serves its students |
| **When will a course be offered?** | Most course timing was generated, not taken from a published schedule. Only 36 rows in CMC's catalogs state a season outright |

## Known gaps

### In the data

- **Hold dates are one snapshot.** Every hold carries the same date. This is the most useful gap to
  fix next, since it would show whether holds come before students leave.
- **College 2 has no link between old and new course codes.** Its course codes changed in 2025. A
  course passed under an old code doesn't count toward the new one, so some College 2 students show
  more credits left than they really have.
- **Many program requirements still need review.** The catalog reader flagged 208 of CMC's 382
  programs and 95 of College 2's 497 for review.
- **Persistence has nothing behind it.** The synthetic data stores a persistence flag, but the
  records that would support it were removed. Treat it as unverified.
- **Graduation records are simulated.** They show how each student was created, which can disagree
  with their actual progress.
- **Gateway course flags and dual enrollment codes are mock values.** They aren't official college
  designations.
- **Some groups are small.** College 2's Satellite campus has 20 students: enough to chart, too few
  to draw conclusions from.
- **The data adds 20 students on purpose who enrolled and earned nothing**, 10 per college. They make
  sure the "haven't started" view has someone in it.

### In the method

- **One catalog per college.** Every student is held to the same catalog, not the one from the
  year they started.
- **Year-over-year data isn't in the synthetic set.** Each student appears once, in their last
  year. Counting stop-outs by who disappeared between years only works when a college uploads two
  or more real years.
- **Circumstances aren't ranked.** A student can have several at once, and the dashboard gives each
  the same weight. If a stop-out had a registration hold and is also a parent, outreach staff can't
  tell which one, if either, led them to leave. The data has no way to say which barrier matters
  most.
- **Hiding small groups isn't a full privacy guarantee.** A hidden number can sometimes be worked
  out by subtracting the groups that are shown.

## Where a person needs to review

These are the areas where staff should check the work before acting.

### Before contacting a student

- **Confirm they've really left.** Check the student information system for a current enrollment,
  a late registration or a recent withdrawal the data hasn't caught yet.
- **Confirm they haven't finished elsewhere.** A student may have transferred or earned a
  credential at another school.
- **Check the hold is still active.** Holds change daily, and the data is a snapshot.
- **Check the student's circumstances with care.** Parent and work status come from what the
  student reported. Don't open a conversation by assuming either.
- **Ask which barrier matters most.** When a student has more than one circumstance, the dashboard
  can't say which one to address first. Let the student tell you, then bring in the office that
  can help.

### Before telling a student how close they are

- **Run a real degree audit.** Credits left is a planning estimate for the major only. An advisor
  should confirm general education, residency and substitutions before giving a student a number.
- **Check the student's catalog year.** The student may be entitled to an older catalog with
  different requirements.
- **Check the program match.** Programs flagged for review, and every College 2 student with
  courses from before 2025, need a closer look.

### Before sharing a figure

- **Say the data is synthetic** whenever a figure from this work is shown, until it runs on real
  data.
- **Check small groups.** Make sure no shared table lets someone work out a hidden group.
- **Name the cutoff and date range.** A near-completer count means little without the credit
  cutoff and the terms it covers.
- **Don't present a link as a cause.** "Many stop-outs had a hold" is supported. "Holds caused
  stop-outs" is not.

### When something looks off

- **Students the data can't place**, such as an unclear program or a major with no readable
  requirements, should go to a person, not drop off the list quietly.
- **Online visiting students** are set aside automatically. If one is actually working toward a
  degree here, staff should correct the record.
