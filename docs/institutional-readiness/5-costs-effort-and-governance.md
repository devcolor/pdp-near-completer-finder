# Costs, effort and governance

This section covers the staff a pilot needs, how much AI the work uses and what it costs alongside the
governance steps a college should complete before real student data goes in.

> **All data here is synthetic.** Every figure below is a planning estimate, not a measured cost.
> A college should replace each one with its own numbers once a pilot starts.

## Sizing assumptions

The estimates assume two small colleges of about 2,000 to 3,000 students each, about 5,000 in all.

At the rates the synthetic data shows, a college that size has a few hundred stop-outs and several
hundred near completers. The synthetic data inflates both on purpose, so a real college will likely
see fewer. To stay on the safe side, the estimates plan for **an outreach list of up to 500
students a term at each college, about 1,000 in all.**

## Staff roles

A one-term pilot at one campus needs the roles below. One person can hold more than one role.

| Role | What they do | Estimated effort |
| --- | --- | --- |
| **Project lead** | Owns the pilot, clears blockers and reports results to leadership | About 2 hours a week |
| **Data contact** (institutional research) | Prepares and uploads the files each term and answers questions about them | 20 to 30 hours to set up, then 2 to 4 hours each term |
| **Catalog reviewer** (registrar's office) | Checks the program requirements flagged for review | About 15 minutes a program: roughly 52 hours for CMC's 208 and 24 hours for College 2's 95 |
| **Developer or IT staff** | Adds login, secure storage and hosting on the college's systems | 40 to 80 hours once, then 2 to 4 hours a month |
| **Outreach owner** (one per office) | Works the outreach list for Student Services, Academic Services or Financial Services | 10 to 15 minutes per student: about 85 to 125 hours a term for 500 students, or 6 to 8 hours a week over a 15-week term |
| **Advisor** | Runs a full degree audit before a student hears how close they are | About 45 minutes per student who responds. If 1 in 4 respond, that is about 95 hours a term for 500 students |
| **Data governance lead** | Reviews the data use, access and storage plan and signs off | 5 to 10 hours before launch, then a quarterly review |

The largest cost is outreach time, and it grows with the number of students contacted. At both
colleges together, outreach comes to 170 to 250 hours a term. A college that can't staff that
should start with the students closest to finishing and widen the list later. The catalog review
is the largest one-time cost, and it doesn't change with the number of students.

## AI usage and cost

### Where AI is used today

| Use | Uses AI? | Touches student data? |
| --- | --- | --- |
| **The dashboard** | No. Every number comes from fixed rules in code, not from an AI model | Yes, but no AI sees it |
| **Building and maintaining the code** | Yes. The team used Claude Code to write and test it | No. The work ran on synthetic data |
| **Data definitions assistant** (the PDP MCP server and Metadata Advisor skill) | Yes. Staff can ask an AI assistant what a column means or how to break down a measure | No. These tools return definitions only, never student records |

The dashboard has a setting for an AI chat key, but no feature uses it yet. **Running the
dashboard costs nothing in AI fees today.**

### Prices used for the estimates

Claude API prices per million tokens, as of November 2026. A token is about three quarters of a
word.

| Model | Input | Output | Best for |
| --- | --- | --- | --- |
| Claude Opus 5.5 | $4.00 | $20.00 | Complex reasoning and writing |
| Claude Sonnet 5.5 | $2.00 | $10.00 | Everyday drafting and questions |
| Claude Haiku 5.5 | $0.10 | $0.50 | Short, simple, high-volume tasks |

### Estimates for possible AI features

These features don't exist yet. The estimates show the scale of cost if a college adds them.

| Feature | Assumed size of each use | Volume | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 |
| --- | --- | --- | --- | --- | --- |
| **Draft an outreach message** for staff to edit | 2,000 tokens in, 400 out | 1,000 students a term | $0.40 a term | $8 a term | $16 a term |
| **Answer a staff question** about definitions or data | 10,000 tokens in, 1,000 out | 200 questions a month across both colleges | $0.30 a month | $6 a month | $12 a month |
| **Summarize outreach notes** into common barriers | 100,000 tokens in (1,000 notes), 2,000 out | Once a term | About $0.01 a term | $0.22 a term | $0.44 a term |
| **Total for both colleges** | | A 4-month term | **About $1.60 a term** | **About $32 a term** | **About $65 a term** |

**AI fees are small next to staff time.** Even with the most expensive model, both colleges
together spend about $65 a term on AI, against 170 to 250 hours of outreach work. Doubling the
list doubles the AI fees and still keeps them under $150 a term. The bigger costs are staff time,
the catalog review and the governance work needed before any student data reaches an AI tool.

Coding assistants for maintenance are billed per seat or by usage, depending on the plan. A
college should set a monthly budget and check usage reports each month.

## Governance checklist

A college should complete every item before real student data goes into the dashboard.

### FERPA and data use

- [ ] Confirm each user is a school official with a legitimate educational interest in the
      students they see
- [ ] Sign a data use agreement that names the data, the purpose and who can see it
- [ ] Limit the files to the fields the dashboard needs, and leave out anything it doesn't use
- [ ] Decide how long uploaded files are kept and how they are deleted

### Access and security

- [ ] Put the dashboard behind the college's own login
- [ ] Give each office access only to the students it serves
- [ ] Store uploaded files in secure, permanent storage the college controls
- [ ] Keep a log of who viewed or exported student lists
- [ ] Decide who can download an outreach list, and where downloaded lists may be saved

### AI tools

- [ ] Keep student records out of AI tools unless a signed agreement with the AI vendor covers
      student data
- [ ] Check what the vendor stores, for how long and whether it trains on the data
- [ ] Have a person review every AI-drafted message before it reaches a student

### Reporting

- [ ] Hide any group under 10 students in shared reports, and check that no table lets someone
      work out a hidden group
- [ ] State the credit cutoff and date range next to every figure
- [ ] Label synthetic figures as synthetic wherever they appear

### Student contact

- [ ] Agree on how staff contact students and how a student can opt out
- [ ] Train outreach staff on the limits in [Limits on interpretation and use](4-limits-on-interpretation-and-use.md)
- [ ] Record each contact and its outcome so the college can measure whether outreach works

### Ongoing review

- [ ] Name who responds if student data is exposed, and how fast
- [ ] Review access, storage and this checklist once a year
