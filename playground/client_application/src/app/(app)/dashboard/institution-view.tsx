"use client";

import { useTheme } from "next-themes";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { cn } from "cn";
import { Bar, BarChart, XAxis, YAxis } from "recharts";

import { ChevronDown, Funnel, FunnelX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { brand } from "@/content/brand";
import { PageIntro } from "@/components/page-intro";
import { StatTile } from "@/components/stat-tile";
import { BarList } from "@/components/sandbox/bar-list";
import { PartStripes, usePartStripesId } from "@/components/sandbox/part-stripes";
import { PartLegend } from "@/components/sandbox/part-swatch";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { apiRequest } from "@/lib/api-client";
import { applyInstitutionBrand, clearInstitutionBrand, institutionBrand } from "@/lib/institution-brand";
import { type ChartSeries, monochromeChartConfig, partFill, stripedPartFill, stripesFor } from "@/lib/charts";

type View = "executive" | "student-services" | "academic" | "financial";

type RateRow = { id: string; label: string; count: number | null; n: number | null; rate: number | null };
type SummaryRow = { id: string; label: string; value: number };
type Section = { section: string; meeting_day: string; meeting_time: string; location: string };
type RemainingCourse = {
  course_code: string;
  attempts: number;
  failed_attempts: number;
  next_offering: string;
  sections: Section[];
};
type Student = {
  student_id: string;
  program: string;
  student_type: string;
  campus_location: string;
  credits_remaining: number;
  credits_applied: number;
  currently_enrolled: boolean;
  registration_hold: boolean;
  hold_type: string;
  parent: boolean;
  employment: string;
  remaining: RemainingCourse[];
};
type DashboardBody = {
  meta: { description: string };
  credit_threshold: string;
  student_types: string[];
  campus_locations: string[];
  programs: string[];
  first_program_label: string;
  second_program_label: string;
  summary: SummaryRow[];
  rates: RateRow[];
  trend: { cohort: string; first_program: number; second_program: number }[];
  pathway_trend: { cohort: string; counts: Record<string, number> }[];
  majors: { program: string; count: number }[];
  academic: { attribute: string; count: number | null; n: number | null; rate: number | null }[];
  academic_blocked: number;
  stop_out_tiles: { id: string; label: string; headline: string; note: string }[];
  current_term: string;
  current_term_label: string;
  stop_out_basis: string;
  terms: { value: string; label: string }[];
  term_from: string;
  term_to: string;
  financial: { attribute: string; count: number | null; n: number | null; rate: number | null }[];
  pathway_latest: { program: string; count: number }[];
  pathway_credits: string;
  pathway_majors: Record<string, { program: string; count: number }[]>;
  pathway_major_trend: Record<string, { cohort: string; counts: Record<string, number> }[]>;
  program_counts: { program: string; count: number }[];
  course_blockers: { course_code: string; course_title: string; students: number }[];
  stop_outs: { term: string; label: string; stop_outs: number }[];
  attributes: { attribute: string; count: number | null; n: number | null; rate: number | null }[];
  student_terms: { value: string; label: string }[];
  students: Student[];
  students_matched: number;
  unavailable: string[];
  using_upload?: boolean;
};

const THRESHOLDS = [0, 3, 6, 9, 12, 15, 24];
/** The credit selections, worded the same wherever they appear. "stop_outs" means no band. */
const CREDIT_OPTIONS: [string, string][] = [
  ["stop_outs", "All stop-outs"],
  ...THRESHOLDS.map(
    (value) =>
      [
        String(value),
        value === 0 ? "Stop-outs who never started" : `Stop-outs within ${value} credits`,
      ] as [string, string],
  ),
];
const DEFAULT_FILTERS = {
  institution: "cmc",
  credit_threshold: "stop_outs",
  student_type: "all",
  campus_location: "all",
  program: "all",
  hold: "any",
  parent: "any",
  student_term: "all",
  pathway: "all",
  major: "all",
  term_from: "all",
  term_to: "all",
  pathway_credits: "stop_outs",
};

type Filters = typeof DEFAULT_FILTERS;

/** This page writes its own filters, so nothing else needs to subscribe. */
function ignoreSavedFilterChanges() {
  return () => {};
}

/** The query string for this page, or the filters saved for this tab. */
function savedFilterSearch(view: View): string {
  return window.location.search || window.sessionStorage.getItem(`dashboard-filters:${view}`) || "";
}

/** No saved filters during server render, so the first paint matches on the client. */
function noSavedFilters() {
  return "";
}

/** Fill any missing filter from the defaults. */
function filtersFromSearch(search: string): Filters {
  const params = new URLSearchParams(search);
  return {
    institution: params.get("institution") || DEFAULT_FILTERS.institution,
    credit_threshold: params.get("credit_threshold") || DEFAULT_FILTERS.credit_threshold,
    student_type: params.get("student_type") || DEFAULT_FILTERS.student_type,
    campus_location: params.get("campus_location") || DEFAULT_FILTERS.campus_location,
    program: params.get("program") || DEFAULT_FILTERS.program,
    hold: params.get("hold") || DEFAULT_FILTERS.hold,
    parent: params.get("parent") || DEFAULT_FILTERS.parent,
    student_term: params.get("student_term") || DEFAULT_FILTERS.student_term,
    pathway: params.get("pathway") || DEFAULT_FILTERS.pathway,
    major: params.get("major") || DEFAULT_FILTERS.major,
    term_from: params.get("term_from") || DEFAULT_FILTERS.term_from,
    term_to: params.get("term_to") || DEFAULT_FILTERS.term_to,
    pathway_credits: params.get("pathway_credits") || DEFAULT_FILTERS.pathway_credits,
  };
}
const INTRO: Record<View, { title: string; lead: string }> = {
  executive: {
    title: "Executive summary",
    lead: "",
  },
  "student-services": {
    title: "Student support",
    lead: "Holds, parents, work, and course times. These counts are synthetic.",
  },
  academic: {
    title: "Pathways and courses",
    lead: "Who is closest to finishing, and when remaining courses meet. These counts are synthetic.",
  },
  financial: {
    title: "Financial holds",
    lead: "Students a financial hold is stopping from enrolling, and how close they were. These counts are synthetic.",
  },
};

/** One institution view. Each page keeps its own filters in this tab. */
export function InstitutionView({ view }: { view: View }) {
  const { resolvedTheme } = useTheme();
  const [body, setBody] = useState<DashboardBody | null>(null);
  const [error, setError] = useState<string | null>(null);
  const saved = useSyncExternalStore(ignoreSavedFilterChanges, () => savedFilterSearch(view), noSavedFilters);
  const [edited, setEdited] = useState<Filters | null>(null);
  const filters = useMemo(() => edited ?? filtersFromSearch(saved), [edited, saved]);

  useEffect(() => {
    const dark = resolvedTheme ? resolvedTheme === "dark" : document.documentElement.classList.contains("dark");
    applyInstitutionBrand(filters.institution, dark);
    return () => clearInstitutionBrand();
  }, [filters.institution, resolvedTheme]);

  useEffect(() => {
    const search = new URLSearchParams(filters);
    window.sessionStorage.setItem(`dashboard-filters:${view}`, search.toString());
    const path = view === "executive" ? "/dashboard" : `/dashboard/${view}`;
    window.history.replaceState(null, "", `${path}?${search.toString()}`);
    let cancelled = false;
    apiRequest<DashboardBody>(`/dashboard?${search.toString()}`)
      .then((next) => {
        if (!cancelled) {
          setBody(next);
          setError(null);
        }
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message);
      });
    return () => {
      cancelled = true;
    };
  }, [filters, view]);

  function update(name: string, value: string) {
    setEdited((current) => {
      const next = { ...(current ?? filters), [name]: value };
      if (name === "institution") {
        next.student_type = "all";
        next.campus_location = "all";
        next.program = "all";
        next.hold = "any";
        next.parent = "any";
        next.student_term = "all";
        next.pathway = "all";
        next.major = "all";
        next.term_from = "all";
        next.term_to = "all";
        next.pathway_credits = "stop_outs";
      }
      // A pathway's majors do not survive a change of pathway.
      if (name === "pathway") next.major = "all";
      return next;
    });
  }

  // Memoised: the detail panels take this as an effect dependency, so a fresh object every
  // render would refetch in a loop.
  const detailScope = useMemo(
    () => ({
      institution: filters.institution,
      credit_threshold: filters.credit_threshold,
      student_type: filters.student_type,
      campus_location: filters.campus_location,
    }),
    [filters.institution, filters.credit_threshold, filters.student_type, filters.campus_location],
  );

  const notStarted = filters.credit_threshold === "0";
  const allStopOuts = filters.credit_threshold === "stop_outs";
  const nearLabel = allStopOuts ? "All stop-outs" : notStarted ? "Haven't started" : "Near completers";

  /** Keep this college's on-screen accent in the PDF, then clear the print override. */
  function exportSummary() {
    const dark = resolvedTheme ? resolvedTheme === "dark" : document.documentElement.classList.contains("dark");
    const tokens = dark ? institutionBrand(filters.institution).dark : institutionBrand(filters.institution).light;
    const root = document.documentElement;
    // The print sheet forces a white page. The accent has to be marked important or the bars print in the other college's color.
    root.style.setProperty("--brand", tokens["--brand"], "important");
    root.style.setProperty("--primary", tokens["--primary"], "important");
    window.addEventListener("afterprint", () => applyInstitutionBrand(filters.institution, dark), { once: true });
    window.setTimeout(() => window.print(), 50);
  }

  return (
    <div className="flex flex-col gap-8 px-6 py-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <PageIntro title={`${brand.dashboardName}*`} size="sm">
          <p className="text-xs">
            {"* "}
            {body?.meta.description ?? "Based on synthetic data. These counts are not findings about real students or either college."}
          </p>
        </PageIntro>
        {view === "executive" && (
          <button type="button" className="no-print h-10 rounded-md border px-4 text-sm font-medium print:hidden" onClick={exportSummary}>
            Export PDF
          </button>
        )}
      </div>
      {body?.using_upload && <p className="text-sm text-muted-foreground">Showing uploaded files for this college.</p>}

      {/* The dashboard is named once above; this is the tab within it. */}
      <div className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold">{INTRO[view].title}</h2>
        {INTRO[view].lead ? <p className="text-sm text-muted-foreground">{INTRO[view].lead}</p> : null}
      </div>

      <form className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Filter label="Institution" value={filters.institution} onChange={(value) => update("institution", value)} options={[["cmc", "Copper Mountain"], ["college_two", "College 2"]]} />
        <Filter label="Counting" value={filters.credit_threshold} onChange={(value) => update("credit_threshold", value)} options={CREDIT_OPTIONS} />
        <Filter label="Campus" value={filters.campus_location} onChange={(value) => update("campus_location", value)} options={[["all", "All campuses"], ...(body?.campus_locations ?? []).map((value) => [value, value] as [string, string])]} />
        {view === "executive" && (
          <TermRange
            terms={body?.terms ?? []}
            from={filters.term_from}
            to={filters.term_to}
            onChange={update}
          />
        )}
        <TypeChecks types={body?.student_types ?? []} value={filters.student_type} onChange={(value) => update("student_type", value)} />
      </form>

      {error && <p className="text-sm text-destructive">{error}</p>}
      {!body && !error && <p className="text-sm text-muted-foreground">Loading the synthetic files…</p>}
      {body && view === "executive" && (
        <Executive
          body={body}
          nearLabel={nearLabel}
          filters={filters}
          scope={detailScope}
          onChange={update}
          pathwayColors={institutionBrand(filters.institution).pathways}
        />
      )}
      {body && view === "student-services" && <StudentServices body={body} nearLabel={nearLabel} filters={filters} onChange={update} />}
      {body && view === "financial" && <FinancialAid body={body} filters={filters} onChange={update} />}
      {body && view === "academic" && <Academic body={body} nearLabel={nearLabel} filters={filters} onChange={update} />}
    </div>
  );
}

/** Student type as a collapsed multi-select: the list only takes space while it is open. */
function TypeChecks({ types, value, onChange }: { types: string[]; value: string; onChange: (value: string) => void }) {
  const selected = value === "all" ? new Set(types) : new Set(value.split("|").filter(Boolean));
  const allOn = types.length === 0 || selected.size === types.length;

  function toggle(type: string, checked: boolean) {
    const next = new Set(value === "all" ? types : selected);
    if (checked) next.add(type);
    else next.delete(type);
    const picked = types.filter((item) => next.has(item));
    onChange(picked.length === 0 || picked.length === types.length ? "all" : picked.join("|"));
  }

  // The trigger has to say what is selected, because the list is hidden until opened.
  const summary = allOn
    ? "All types"
    : selected.size === 1
      ? [...selected][0]
      : `${selected.size} of ${types.length} types`;

  return (
    <div className="flex flex-col gap-1 text-sm font-medium">
      <span id="student-type-label">Student type</span>
      <Popover>
        <PopoverTrigger
          className="flex h-10 items-center justify-between gap-2 rounded-md border bg-background px-3 text-left font-normal"
          aria-labelledby="student-type-label"
        >
          <span className="truncate">{summary}</span>
          <ChevronDown aria-hidden className="size-4 shrink-0 opacity-60" />
        </PopoverTrigger>
        <PopoverContent align="start" className="max-h-80 w-72 overflow-y-auto">
          <label className="flex items-center gap-2 rounded-sm px-1 py-1.5 font-normal hover:bg-accent">
            <Checkbox checked={allOn} onCheckedChange={() => onChange("all")} />
            All types
          </label>
          <div className="my-0.5 border-t" />
          {types.map((type) => (
            <label key={type} className="flex items-center gap-2 rounded-sm px-1 py-1.5 font-normal hover:bg-accent">
              <Checkbox checked={selected.has(type)} onCheckedChange={(checked) => toggle(type, checked === true)} />
              {type}
            </label>
          ))}
        </PopoverContent>
      </Popover>
    </div>
  );
}

/** A range picker over the terms: click a start, then an end. One control, not two selects. */
function TermRange({ terms, from, to, onChange }: {
  terms: { value: string; label: string }[];
  from: string;
  to: string;
  onChange: (name: string, value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  // The first click of a new range, waiting for its second. Null means the range is settled.
  const [pending, setPending] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  const order = terms.map((term) => term.value);
  const at = (value: string) => order.indexOf(value);
  const labelOf = (value: string) => terms.find((term) => term.value === value)?.label ?? value;
  const everything = from === "all" && to === "all";
  const summary = everything
    ? "All terms"
    : `${from === "all" ? "Earliest" : labelOf(from)} – ${to === "all" ? "Latest" : labelOf(to)}`;

  // While picking, shade from the first click to whatever the pointer is over.
  const [lowIndex, highIndex] = pending
    ? [at(pending), at(preview ?? pending)].sort((a, b) => a - b)
    : [from === "all" ? 0 : at(from), to === "all" ? order.length - 1 : at(to)];

  function pick(value: string) {
    if (pending === null) {
      setPending(value);
      onChange("term_from", value);
      onChange("term_to", value);
      return;
    }
    const [first, second] = at(pending) <= at(value) ? [pending, value] : [value, pending];
    onChange("term_from", first);
    onChange("term_to", second);
    setPending(null);
    setPreview(null);
    setOpen(false);   // the range is complete, so the picker gets out of the way
  }

  return (
    <div className="flex min-w-0 flex-col gap-1 text-sm font-medium">
      <span id="term-range-label">Last term enrolled</span>
      <Popover
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) { setPending(null); setPreview(null); }
        }}
      >
        <PopoverTrigger
          className="flex h-10 items-center justify-between gap-2 rounded-md border bg-background px-3 text-left font-normal"
          aria-labelledby="term-range-label"
        >
          <span className="truncate">{summary}</span>
          <ChevronDown aria-hidden className="size-4 shrink-0 opacity-60" />
        </PopoverTrigger>
        <PopoverContent align="start" className="w-72">
          <p className="px-1 text-xs text-muted-foreground">
            {pending ? "Now pick the end of the range." : "Pick the start of the range."}
          </p>
          <ul className="grid grid-cols-2 gap-1" onMouseLeave={() => setPreview(null)}>
            {terms.map((term, index) => {
              const inRange = index >= lowIndex && index <= highIndex;
              const isEdge = index === lowIndex || index === highIndex;
              return (
                <li key={term.value}>
                  <button
                    type="button"
                    onClick={() => pick(term.value)}
                    onMouseEnter={() => pending && setPreview(term.value)}
                    aria-pressed={inRange}
                    className={cn(
                      "w-full rounded-sm px-2 py-1.5 text-left text-sm font-normal tabular-nums",
                      !inRange && "hover:bg-accent",
                      inRange && !isEdge && "bg-accent",
                      isEdge && !everything && "bg-foreground text-background",
                      isEdge && everything && "bg-accent",
                    )}
                  >
                    {term.label}
                  </button>
                </li>
              );
            })}
          </ul>
          <button
            type="button"
            className="mt-1 w-full rounded-sm border px-2 py-1.5 text-sm font-normal hover:bg-accent"
            onClick={() => {
              onChange("term_from", "all");
              onChange("term_to", "all");
              setPending(null);
              setOpen(false);
            }}
          >
            All terms
          </button>
        </PopoverContent>
      </Popover>
    </div>
  );
}

function Filter({ label, value, options, onChange }: { label: string; value: string; options: [string, string][]; onChange: (value: string) => void }) {
  return (
    <label className="flex flex-col gap-1 text-sm font-medium">
      {label}
      <select className="h-10 rounded-md border bg-background px-3" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>{optionLabel}</option>
        ))}
      </select>
    </label>
  );
}

/** How the selected credit band reads in a sentence. */
function creditLineFor(selection: string) {
  if (selection === "stop_outs") return "with credits still owed on their major";
  if (selection === "0") return "with no credits applied to their major";
  return `within ${selection} credits of finishing their major`;
}

function countOf(body: DashboardBody, id: string) {
  return body.summary.find((row) => row.id === id)?.value ?? 0;
}

function Executive({ body, nearLabel, filters, scope, onChange, pathwayColors }: {
  body: DashboardBody;
  nearLabel: string;
  filters: { pathway: string; major: string; pathway_credits: string };
  scope: DetailScope;
  onChange: (name: string, value: string) => void;
  pathwayColors: string[];
}) {
  const creditLine = creditLineFor(body.credit_threshold);
  return (
    <>
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {body.stop_out_tiles.map((tile) => (
          <article key={tile.id} className="rounded-xl border border-l-4 p-4" style={{ borderLeftColor: "var(--brand)" }}>
            <p className="text-sm text-muted-foreground">{tile.label}</p>
            <p className="text-3xl font-semibold">{tile.headline}</p>
            <p className="text-sm text-muted-foreground">{tile.note}</p>
          </article>
        ))}
      </section>
      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">Stop-outs</h2>
        <p className="text-sm text-muted-foreground">By the term each student was last enrolled in, so the bars show when students went. California Virtual Campus students are left out unless that type is selected.</p>
        <p className="text-3xl font-semibold">{countOf(body, "stop_outs").toLocaleString()}</p>
        {body.current_term ? (
          <p className="text-sm text-muted-foreground">
            Not enrolled this term: <span className="font-semibold text-foreground">{countOf(body, "not_enrolled_this_term").toLocaleString()}</span>. {body.current_term_label} is still in progress, so they are counted as stop-outs once it ends.
          </p>
        ) : null}
        <CohortChart rows={body.stop_outs} series={[{ key: "stop_outs", label: "Stop-outs" }]} />
      </section>
      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">{nearLabel}</h2>
        <p className="text-sm text-muted-foreground">Every major, {creditLine}.</p>
        <p className="text-3xl font-semibold">{countOf(body, "near").toLocaleString()}</p>
        <ProgramBars rows={body.program_counts} />
      </section>
      <section className="flex flex-col gap-3">
        <PathwayDrilldown body={body} filters={filters} scope={scope} onChange={onChange} colors={pathwayColors} />
      </section>
      {filters.major !== "all" && (
        <section className="flex flex-col gap-3">
          <MajorDetailPanel major={filters.major} scope={scope} />
        </section>
      )}
      <WhoIsCounted body={body} />
    </>
  );
}

/** What "student" means on this page, and who the counts leave out. */
function WhoIsCounted({ body }: { body: DashboardBody }) {
  const total = body.summary.find((row) => row.id === "students")?.value ?? 0;
  const excluded = body.summary.find((row) => row.id === "left_out")?.value ?? 0;
  return (
    <section className="flex flex-col gap-2 border-t pt-4 text-sm text-muted-foreground">
      <h2 className="font-medium text-foreground">How these students are counted</h2>
      <p>
        A <strong className="font-medium text-foreground">student</strong> is one person in this
        college&rsquo;s synthetic file, counted once. A{" "}
        <strong className="font-medium text-foreground">stop-out</strong> is counted by:{" "}
        {body.stop_out_basis.toLowerCase()}. With several PDP years loaded a student is counted as
        having left when they stop appearing, because a student only appears in a year they were
        enrolled in; with a single year there is nothing to compare against, so their enrollment
        flag is used instead.
      </p>
      <p>
        <strong className="font-medium text-foreground">Counted:</strong> firefighters, adult
        learners, former dual enrollment, regular (COLC) students, and &mdash; at College 2
        &mdash; incarcerated students. {total.toLocaleString()} students in all.
      </p>
      <p>
        <strong className="font-medium text-foreground">Left out of every figure:</strong>{" "}
        non-credit students (MASP included). They are not working towards a credential here, so
        finishing with us is not something they can stop short of. They cannot be filtered back
        in.
      </p>
      <p>
        <strong className="font-medium text-foreground">Left out unless you ask for them:</strong>{" "}
        California Virtual Campus (CVC) students &mdash; {excluded.toLocaleString()} of{" "}
        {total.toLocaleString()}. They are enrolled at another California college and take one or
        two classes with us a la carte, so leaving is the normal end of that arrangement.
        Selecting CVC under Student type puts them back in.
      </p>
      <p>
        The time range filters stop-outs by the last term they were enrolled, so it tells you{" "}
        <em>when</em> they left. It ends at the last finished term:{" "}
        {body.current_term_label || "the current term"} is still in progress, so students who left in it
        are shown apart, as not enrolled this term. Credit counts cover the major only: general education, residency
        and substitutions are not audited. All figures are synthetic.
      </p>
    </section>
  );
}

function titleCase(value: string) {
  return value.toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/** One colored line per academic pathway, across entry cohorts. */
/** The filters a detail request must repeat, so it describes the same students as the page. */
type DetailScope = {
  institution: string;
  credit_threshold: string;
  student_type: string;
  campus_location: string;
};

type BlockingCourse = {
  course_code: string;
  course_title: string;
  students: number;
  terms_offered: string;
  season_locked: boolean;
  withdraw_rate: number | null;
  fail_rate: number | null;
  high_dfw: boolean;
};

type MajorDetailBody = {
  major: string;
  pathway: string;
  students: number;
  near: number;
  stop_outs: number;
  attributes: { attribute: string; count: number | null; n: number | null; rate: number | null }[];
  blocking_courses: BlockingCourse[];
};

type PathwayDetailBody = {
  pathway: string;
  majors: { program: string; count: number }[];
  students: number;
  near: number;
  stop_outs: number;
  blocking_courses: BlockingCourse[];
};

/** One pathway on its own: the majors inside it, and the courses holding the whole pathway up. */
function PathwayDetailPanel({ pathway, scope, onPickMajor }: { pathway: string; scope: DetailScope; onPickMajor: (major: string) => void }) {
  const [detail, setDetail] = useState<PathwayDetailBody | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const search = new URLSearchParams({ pathway, ...scope });
    apiRequest<PathwayDetailBody>(`/dashboard/pathway?${search.toString()}`)
      .then((next) => { if (!cancelled) { setDetail(next); setError(null); } })
      .catch((reason: Error) => { if (!cancelled) setError(reason.message); });
    return () => { cancelled = true; };
  }, [pathway, scope]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  // Until the response for *this* pathway arrives, the previous one would be wrong.
  if (!detail || detail.pathway !== pathway) {
    return <p className="text-sm text-muted-foreground">Loading this pathway…</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <ul className="grid gap-4 sm:grid-cols-3">
        <li><StatTile value={detail.students.toLocaleString()} label="Students in this pathway" /></li>
        <li><StatTile value={detail.stop_outs.toLocaleString()} label="Stopped out" /></li>
        <li><StatTile value={detail.near.toLocaleString()} label="Within the credit filter" /></li>
      </ul>
      <div className="flex flex-col gap-3">
        <h3 className="text-base font-semibold">Majors in this pathway</h3>
        <p className="text-sm text-muted-foreground">Pick one to see that major on its own.</p>
        <ul className="flex flex-col">
          {detail.majors.map((major) => (
            <li key={major.program} className="flex items-baseline justify-between gap-3 border-b py-1.5 last:border-b-0">
              <button
                type="button"
                className="text-left text-sm underline-offset-4 hover:underline disabled:no-underline disabled:opacity-60"
                onClick={() => onPickMajor(major.program)}
                disabled={major.count === 0}
              >
                {titleCase(major.program)}
              </button>
              <span className="text-sm tabular-nums">{major.count.toLocaleString()}</span>
            </li>
          ))}
        </ul>
      </div>
      <BlockingCourses courses={detail.blocking_courses} scope="this pathway" />
    </div>
  );
}

/** One major: who is in it, and which remaining courses are hard to finish. */
function MajorDetailPanel({ major, scope }: { major: string; scope: DetailScope }) {
  const [detail, setDetail] = useState<MajorDetailBody | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const search = new URLSearchParams({ major, ...scope });
    apiRequest<MajorDetailBody>(`/dashboard/major?${search.toString()}`)
      .then((next) => { if (!cancelled) { setDetail(next); setError(null); } })
      .catch((reason: Error) => { if (!cancelled) setError(reason.message); });
    return () => { cancelled = true; };
  }, [major, scope]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  // Until the response for *this* major arrives, the old one would be wrong.
  if (!detail || detail.major !== major) {
    return <p className="text-sm text-muted-foreground">Loading this major…</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <li><StatTile value={detail.students.toLocaleString()} label="Students in this major" /></li>
        <li><StatTile value={detail.near.toLocaleString()} label="Within the credit filter" /></li>
        <li><StatTile value={detail.stop_outs.toLocaleString()} label="Stopped out" /></li>
        {detail.attributes.map((row) => (
          <li key={row.attribute}>
            <StatTile
              value={row.rate === null ? "—" : `${Math.round(row.rate * 100)}`}
              unit={row.rate === null ? null : "%"}
              label={row.attribute}
              detail={row.count === null ? "Fewer than 10 students" : `${row.count} of ${row.n}`}
            />
          </li>
        ))}
      </ul>
      <BlockingCourses courses={detail.blocking_courses} scope="this major" />
    </div>
  );
}

/** The courses a group of students still owe, with what makes each hard to finish. */
function BlockingCourses({ courses, scope }: { courses: BlockingCourse[]; scope: string }) {
  return (
      <div className="flex flex-col gap-3">
        <h3 className="flex items-center gap-2 text-base font-semibold">
          <span aria-hidden className="h-4 w-1 rounded-full bg-foreground" />
          Courses these students still owe
        </h3>
        <p className="text-sm text-muted-foreground">
          A course runs in one term only, or a high share of students withdraw or do not pass
          it. Dropping a course and failing it are different problems, so they are counted
          separately. Both use courses with at least 15 enrolments; <span className="font-medium">high</span> marks
          30% or more of students between them.
        </p>
        {courses.length === 0 ? (
          <p className="text-sm text-muted-foreground">No remaining courses for {scope}.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="py-1 pr-4 font-medium">Course</th>
                <th scope="col" className="py-1 pr-6 text-right font-medium whitespace-nowrap">Students</th>
                <th scope="col" className="py-1 pr-6 text-right font-medium whitespace-nowrap">Withdrew</th>
                <th scope="col" className="py-1 pr-6 text-right font-medium whitespace-nowrap">Did not pass</th>
                <th scope="col" className="py-1 font-medium whitespace-nowrap">Offered</th>
              </tr>
            </thead>
            <tbody>
              {courses.map((course) => (
                <tr key={course.course_code} className="border-t">
                  <td className="py-1.5 pr-4">
                    <span className="font-medium">{course.course_code}</span>{" "}
                    <span className="text-muted-foreground">{titleCase(course.course_title)}</span>
                  </td>
                  <td className="py-1.5 pr-6 text-right tabular-nums">{course.students}</td>
                  <td className="py-1.5 pr-6 text-right tabular-nums">
                    {course.withdraw_rate === null ? "—" : `${Math.round(course.withdraw_rate * 100)}%`}
                  </td>
                  <td className="py-1.5 pr-6 text-right tabular-nums whitespace-nowrap">
                    {course.fail_rate === null ? "—" : `${Math.round(course.fail_rate * 100)}%`}
                    {course.high_dfw && (
                      <span className="ml-1.5 rounded-sm border px-1 text-xs font-medium">high</span>
                    )}
                  </td>
                  <td className="py-1.5 whitespace-nowrap">
                    {course.terms_offered ? course.terms_offered.split(";").join(" and ") : "—"}
                    {course.season_locked && (
                      <span className="ml-1.5 rounded-sm border px-1 text-xs font-medium">one term only</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
  );
}

/** Pathways, then the majors inside one, then one major on its own.
 *
 * The chart never goes away. Each step narrows it - every pathway, then the majors in one,
 * then the single major - and the sections underneath change to match.
 */
function PathwayDrilldown({ body, filters, scope, onChange, colors }: {
  body: DashboardBody;
  filters: { pathway: string; major: string; pathway_credits: string };
  scope: DetailScope;
  onChange: (name: string, value: string) => void;
  colors: string[];
}) {
  const pathway = filters.pathway === "all" ? null : filters.pathway;
  const major = filters.major === "all" ? null : filters.major;
  const depth = major ? 2 : pathway ? 1 : 0;

  let rows = body.pathway_trend;
  if (pathway) rows = body.pathway_major_trend[pathway] ?? [];
  if (major) {
    // Keep only the chosen major's series, so the chart narrows instead of vanishing.
    rows = rows.map((row) => ({
      cohort: row.cohort,
      counts: { [major]: row.counts[major] ?? 0 },
    }));
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {depth > 0 ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => { onChange("pathway", "all"); onChange("major", "all"); }}
          >
            <FunnelX aria-hidden />
            Reset to all pathways
          </Button>
        ) : (
          <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <Funnel aria-hidden className="size-4" />
            Pick a pathway to narrow this
          </span>
        )}
        <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 text-sm">
          <button
            type="button"
            className={depth === 0 ? "font-semibold" : "underline underline-offset-4"}
            onClick={() => { onChange("pathway", "all"); onChange("major", "all"); }}
          >
            All pathways
          </button>
          {pathway && (
            <>
              <span aria-hidden className="text-muted-foreground">›</span>
              <button
                type="button"
                className={depth === 1 ? "font-semibold" : "underline underline-offset-4"}
                onClick={() => onChange("major", "all")}
              >
                {pathway}
              </button>
            </>
          )}
          {major && (
            <>
              <span aria-hidden className="text-muted-foreground">›</span>
              <span className="font-semibold">{titleCase(major)}</span>
            </>
          )}
        </nav>
      </div>
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <p className="max-w-xl text-sm text-muted-foreground">
          {depth === 2
            ? "This major on its own. Its numbers are below."
            : depth === 1
              ? "Majors in this pathway, by the year students started. Pick one to narrow further."
              : "Stop-outs by the year they started. Pick a pathway to see the majors inside it. These counts are synthetic."}
        </p>
        {/* This chart has its own population. The page-level credit threshold sits far above
            it, so having that drive these lines gave no clue why they moved. */}
        <Filter
          label="Counting"
          value={filters.pathway_credits}
          onChange={(value) => onChange("pathway_credits", value)}
          options={CREDIT_OPTIONS}
        />
      </div>
      <div className="rounded-xl border p-4">
        {rows.length ? (
          <PathwayLines
            rows={rows}
            colors={colors}
            onSelect={depth === 2 ? undefined : (name) => onChange(depth === 0 ? "pathway" : "major", name)}
            selectLabel={depth === 0 ? "Open pathway" : "Open major"}
          />
        ) : (
          <p className="text-sm text-muted-foreground">No students here for this filter.</p>
        )}
      </div>
      {depth === 0 && (
        <div className="flex flex-col gap-3">
          <h3 className="text-base font-semibold">Pathways</h3>
          <p className="text-sm text-muted-foreground">
            Students enrolled in {body.current_term_label || "the latest term"}. Pick one to see
            the majors inside it and the courses holding its students up.
          </p>
          <ul className="flex flex-col">
            {body.pathway_latest.map((row, index) => (
              <li key={row.program} className="flex items-baseline justify-between gap-3 border-b py-1.5 last:border-b-0">
                <button
                  type="button"
                  className="flex items-center gap-2 text-left text-sm underline-offset-4 hover:underline"
                  onClick={() => onChange("pathway", row.program)}
                >
                  <span aria-hidden className="inline-block h-0.5 w-4 shrink-0" style={{ backgroundColor: colors[index % colors.length] }} />
                  {row.program}
                </button>
                <span className="text-sm tabular-nums">{row.count.toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {depth === 1 && pathway && (
        <PathwayDetailPanel pathway={pathway} scope={scope} onPickMajor={(name) => onChange("major", name)} />
      )}
    </>
  );
}

function PathwayLines({
  rows,
  colors,
  onSelect,
  selectLabel,
}: {
  rows: { cohort: string; counts: Record<string, number> }[];
  colors: string[];
  /** Given a series name when the reader picks one. Omit to render a plain chart. */
  onSelect?: (name: string) => void;
  selectLabel?: string;
}) {
  // Which point the pointer is on, as "series|cohort". Held in state rather than a
  // group-hover class: Tailwind does not reliably emit utilities used only inside the svg.
  const [hovered, setHovered] = useState<string | null>(null);
  // "series|cohort"; the cohort half is empty when the legend itself is hovered.
  const hoveredName = hovered ? hovered.split("|")[0] : null;
  if (!rows.length) return <p className="text-sm text-muted-foreground">No students in this filter.</p>;
  const names = Object.keys(rows[0].counts);
  const width = 640;
  const height = 220;
  const gutter = 34;          // room for the value axis
  const floor = height - 30;  // room for the cohort labels
  const peak = Math.max(1, ...rows.flatMap((row) => Object.values(row.counts)));
  /** Round the top of the axis up to something a reader can divide in their head. */
  const step = peak <= 5 ? 1 : peak <= 10 ? 2 : peak <= 30 ? 5 : peak <= 60 ? 10 : 25;
  const top = Math.ceil(peak / step) * step;
  const ticks = Array.from({ length: top / step + 1 }, (_, i) => i * step);
  const xAt = (index: number) =>
    rows.length === 1 ? (gutter + width) / 2 : (index / (rows.length - 1)) * (width - gutter - 30) + gutter;
  const yAt = (value: number) => floor - (value / top) * (floor - 14);
  /** Nudge a hover label inward so a long series name stays inside the viewBox. */
  const labelX = (x: number, name: string) => {
    const half = name.length * 2.6 + 8;
    return Math.min(Math.max(x, gutter + half), width - 30 - half);
  };
  const line = (name: string) => rows.map((row, index) => `${xAt(index)},${yAt(row.counts[name] ?? 0)}`).join(" ");
  /** One lookup for chart, legend and heading, so their colors cannot drift apart. */
  const colorOf = (index: number) => colors[index % colors.length];
  return (
    <div className="flex flex-col gap-3">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label="Students by entry cohort">
        {ticks.map((value) => (
          <g key={value}>
            <line
              x1={gutter} x2={width - 30} y1={yAt(value)} y2={yAt(value)}
              stroke="currentColor" strokeWidth="1" opacity={value === 0 ? 0.28 : 0.1}
            />
            <text x={gutter - 6} y={yAt(value) + 3.5} textAnchor="end" fontSize="10" fill="currentColor" opacity="0.65">
              {value}
            </text>
          </g>
        ))}
        {names.map((name, index) => (
          <g key={name}>
            {onSelect && (
              // A 2.5px line is a poor click target, so a transparent one sits underneath.
              <polyline
                fill="none" stroke="transparent" strokeWidth="14" points={line(name)}
                className="cursor-pointer" onClick={() => onSelect(name)}
              />
            )}
            <polyline
              fill="none" stroke={colorOf(index)} points={line(name)} pointerEvents="none"
              strokeWidth={hoveredName === name ? 4 : 2.5}
              opacity={hoveredName !== null && hoveredName !== name ? 0.3 : 1}
            />
            {rows.map((row, i) => {
              const value = row.counts[name] ?? 0;
              const key = `${name}|${row.cohort}`;
              return (
                // A hit target per point, so hovering pops up the number the line is at.
                <g key={row.cohort}>
                  <circle
                    cx={xAt(i)} cy={yAt(value)} r="9" fill="transparent"
                    className={onSelect ? "cursor-pointer" : undefined}
                    onClick={onSelect ? () => onSelect(name) : undefined}
                    onMouseEnter={() => setHovered(key)}
                    onMouseLeave={() => setHovered((at) => (at === key ? null : at))}
                  >
                    <title>{`${name} — ${row.cohort}: ${value}`}</title>
                  </circle>
                  {hovered === key && (
                    <>
                      <circle cx={xAt(i)} cy={yAt(value)} r="3.5" fill={colorOf(index)} pointerEvents="none" />
                      {/* Clamped so a long name like "Professional Vocational Technologies"
                          cannot run off either edge of the viewBox. */}
                      <text
                        x={labelX(xAt(i), name)} y={yAt(value) - 22} textAnchor="middle" fontSize="12" fontWeight="700"
                        fill="currentColor" stroke="var(--card)" strokeWidth="3.5" paintOrder="stroke"
                        pointerEvents="none"
                      >
                        {value}
                      </text>
                      <text
                        x={labelX(xAt(i), name)} y={yAt(value) - 9} textAnchor="middle" fontSize="10"
                        fill={colorOf(index)} stroke="var(--card)" strokeWidth="3" paintOrder="stroke"
                        pointerEvents="none"
                      >
                        {name}
                      </text>
                    </>
                  )}
                </g>
              );
            })}
          </g>
        ))}
        {rows.map((row, index) => (
          <text key={row.cohort} x={xAt(index)} y={height - 8} textAnchor="middle" fontSize="11" fill="currentColor">{row.cohort}</text>
        ))}
      </svg>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {names.map((name, index) => {
          // Hovering a point in the chart marks which key it belongs to, so the reader does not
          // have to match a colour by eye.
          const lit = hoveredName === name;
          const dimmed = hoveredName !== null && !lit;
          const swatch = (
            <span
              aria-hidden
              className={cn("inline-block w-4 rounded-full transition-all", lit ? "h-1" : "h-0.5")}
              style={{ backgroundColor: colorOf(index) }}
            />
          );
          return (
            <li
              key={name}
              className={cn(
                "flex items-center gap-1.5 rounded-sm px-1 transition-opacity",
                lit && "bg-accent font-semibold text-foreground",
                dimmed && "opacity-40",
              )}
            >
              {onSelect ? (
                // The svg is role="img", so its interior is hidden from screen readers.
                // The legend is the accessible way in; clicking a line is a mouse shortcut.
                <button
                  type="button"
                  onClick={() => onSelect(name)}
                  onMouseEnter={() => setHovered(`${name}|`)}
                  onMouseLeave={() => setHovered((at) => (at === `${name}|` ? null : at))}
                  title={selectLabel ? `${selectLabel}: ${name}` : name}
                  className="flex items-center gap-1.5 rounded-sm underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                >
                  {swatch}
                  {name}
                </button>
              ) : (
                <>
                  {swatch}
                  {name}
                </>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Show the outreach summary and filter the student list. */
function StudentServices({ body, nearLabel, filters, onChange }: { body: DashboardBody; nearLabel: string; filters: Pick<Filters, "program" | "hold" | "parent" | "student_term">; onChange: (name: string, value: string) => void }) {
  return (
    <>
      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">Who needs support</h2>
        <p className="text-sm text-muted-foreground">Registration holds, parents, and work among the students in this credit filter.</p>
        <BarList
          items={body.attributes.map((row) => ({
            label: row.attribute,
            value: row.rate === null ? null : row.rate * 100,
            display: row.count === null ? "—" : `${row.count} of ${row.n}`,
          }))}
        />
      </section>
      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">Students</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Filter label="Program" value={filters.program} onChange={(value) => onChange("program", value)} options={[["all", "All programs"], ...body.programs.map((value) => [value, value] as [string, string])]} />
          <Filter label="Registration hold" value={filters.hold} onChange={(value) => onChange("hold", value)} options={[["any", "any"], ["yes", "yes"], ["no", "no"]]} />
          <Filter label="Parent" value={filters.parent} onChange={(value) => onChange("parent", value)} options={[["any", "any"], ["yes", "yes"], ["no", "no"]]} />
          <StudentTermFilter terms={body.student_terms} value={filters.student_term} onChange={(value) => onChange("student_term", value)} />
        </div>
        <p className="text-sm text-muted-foreground">Showing {body.students.length.toLocaleString()} of {body.students_matched.toLocaleString()} {nearLabel.toLowerCase()}. The files identify students by ID.</p>
        <StudentTable body={body} columns={["student_id", "student_type", "campus_location", "credits_remaining", "currently_enrolled", "registration_hold", "parent", "employment", "remaining"]} />
        <h3 className="text-base font-semibold">Not in these datasets</h3>
        <ul className="list-disc pl-5 text-sm text-muted-foreground">
          {body.unavailable.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </section>
    </>
  );
}

/** Filter the student list by the student's last recorded enrollment term. */
function StudentTermFilter({ terms, value, onChange }: {
  terms: DashboardBody["student_terms"];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Filter
      label="Last term enrolled"
      value={value}
      onChange={onChange}
      options={[["all", "All terms"], ...terms.map(({ value, label }): [string, string] => [value, label])]}
    />
  );
}

/** Financial aid's own view: the holds this office can clear, and who they are holding up. */
function FinancialAid({ body, filters, onChange }: {
  body: DashboardBody;
  filters: Pick<Filters, "program" | "student_term">;
  onChange: (name: string, value: string) => void;
}) {
  const held = body.financial[0];
  return (
    <>
      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">Students held by a financial hold</h2>
        <p className="text-sm text-muted-foreground">
          A financial hold is the one blocker this office can lift on its own. Academic and
          advising holds belong to Academic Services.
        </p>
        <p className="text-3xl font-semibold">
          {held?.count === null || held === undefined ? "—" : held.count.toLocaleString()}
        </p>
        <BarList
          max={Math.max(1, ...body.financial.map((row) => row.count ?? 0))}
          items={body.financial.map((row) => ({
            label: row.attribute,
            value: row.count,
            display: row.count === null ? "—" : row.count.toLocaleString(),
            note: row.count === null ? "fewer than 10 students" : undefined,
          }))}
        />
      </section>
      <div className="grid gap-4 sm:grid-cols-2">
        <Filter
          label="Program"
          value={filters.program}
          onChange={(value) => onChange("program", value)}
          options={[["all", "All programs"], ...body.programs.map((value) => [value, value] as [string, string])]}
        />
        <StudentTermFilter terms={body.student_terms} value={filters.student_term} onChange={(value) => onChange("student_term", value)} />
      </div>
      <StudentTable
        body={body}
        columns={["student_id", "program", "hold_type", "credits_remaining", "currently_enrolled", "employment"]}
      />
    </>
  );
}

/** Show academic blockers and the filterable student list. */
function Academic({ body, nearLabel, filters, onChange }: { body: DashboardBody; nearLabel: string; filters: Pick<Filters, "program" | "student_term">; onChange: (name: string, value: string) => void }) {
  const creditLine = creditLineFor(body.credit_threshold);
  return (
    <>
      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">What is holding these students back</h2>
        <p className="text-sm text-muted-foreground">
          Each category below is something this office can act on: release the hold, add a second
          section so a once-a-year course is reachable, or offer support in a course most
          students withdraw from or fail. Financial holds belong to Financial Services.
        </p>
        <p className="text-3xl font-semibold">{body.academic_blocked.toLocaleString()}</p>
        <p className="-mt-2 text-sm text-muted-foreground">
          students hit at least one of these. A student can appear in more than one category, so
          the categories add up to more than this total.
        </p>
        <BarList
          max={Math.max(1, ...body.academic.map((row) => row.count ?? 0))}
          items={body.academic.map((row) => ({
            label: row.attribute,
            value: row.count,
            display: row.count === null ? "—" : row.count.toLocaleString(),
            note: row.count === null ? "fewer than 10 students" : undefined,
          }))}
        />
      </section>
      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">{nearLabel}</h2>
        <p className="text-sm text-muted-foreground">Every major, {creditLine}.</p>
        <p className="text-3xl font-semibold">{countOf(body, "near").toLocaleString()}</p>
        <ProgramBars rows={body.program_counts} />
      </section>
      <div className="grid gap-4 sm:grid-cols-2">
        <Filter label="Program" value={filters.program} onChange={(value) => onChange("program", value)} options={[["all", "All programs"], ...body.programs.map((value) => [value, value] as [string, string])]} />
        <StudentTermFilter terms={body.student_terms} value={filters.student_term} onChange={(value) => onChange("student_term", value)} />
      </div>
      <StudentTable body={body} columns={["student_id", "program", "campus_location", "credits_applied", "credits_remaining", "remaining"]} />
    </>
  );
}

function ProgramBars({ rows }: { rows: { program: string; count: number }[] }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">No students in this filter.</p>;
  const max = Math.max(...rows.map((row) => row.count));
  return (
    <BarList
      max={max}
      items={rows.map((row) => ({
        label: titleCase(row.program),
        value: row.count,
        display: row.count.toLocaleString(),
      }))}
    />
  );
}

function CohortChart({ rows, series }: { rows: Record<string, string | number>[]; series: ChartSeries[] }) {
  const stripesId = usePartStripesId();
  if (!rows.length) return <p className="text-sm text-muted-foreground">No students in this filter.</p>;
  return (
    <div className="flex flex-col gap-3">
      <ChartContainer config={monochromeChartConfig(series)} className="aspect-auto h-44 w-full">
        <BarChart data={rows} margin={{ top: 8, right: 0, bottom: 0, left: 0 }} barGap={2}>
          <defs>
            <PartStripes id={stripesId} />
          </defs>
          <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={8} interval={0} fontSize={10} angle={-30} textAnchor="end" height={48} />
          <YAxis width={30} tickLine={false} axisLine={false} fontSize={10} allowDecimals={false} />
          <ChartTooltip cursor={false} content={<ChartTooltipContent indicator="dot" />} />
          {series.map((item, index) => (
            <Bar
              key={item.key}
              dataKey={item.key}
              fill={index === 0 ? "var(--brand)" : stripesFor(stripedPartFill.fill, stripesId)}
              stroke={index === 0 ? undefined : "var(--brand)"}
              strokeWidth={index === 0 ? 0 : 1.25}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ChartContainer>
      {series.length > 1 && (
        <PartLegend parts={series.map((item, index) => ({ key: item.key, label: item.label, ...(index === 0 ? partFill(0) : stripedPartFill) }))} />
      )}
    </div>
  );
}

function StudentTable({ body, columns }: { body: DashboardBody; columns: (keyof Student)[] }) {
  const labels: Record<string, string> = {
    student_id: "Student ID",
    student_type: "Student type",
    campus_location: "Campus",
    credits_remaining: "Credits left",
    credits_applied: "Credits applied",
    currently_enrolled: "Enrolled",
    registration_hold: "Hold",
    parent: "Parent",
    employment: "Work",
    program: "Program",
    remaining: "Remaining courses",
  };
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr>{columns.map((column) => <th key={column} className="py-2 pr-3 font-medium">{labels[column]}</th>)}</tr>
        </thead>
        <tbody>
          {body.students.map((student) => (
            <tr key={student.student_id} className="border-t align-top">
              {columns.map((column) => <td key={column} className="py-2 pr-3">{cell(student, column)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RemainingCourses({ courses }: { courses: RemainingCourse[] }) {
  if (courses.length === 0) return "—";
  return (
    <ul className="flex flex-col gap-3">
      {courses.map((course) => (
        <li key={course.course_code}>
          <span className="font-medium">{course.course_code}</span>
          <span className="block text-muted-foreground">{attemptText(course)}</span>
          <span className="block">{course.next_offering}</span>
          {course.sections.length === 0 ? (
            <span className="block text-muted-foreground">No section</span>
          ) : (
            <ul>
              {course.sections.map((section) => (
                <li key={section.section}>
                  {section.meeting_day} {section.meeting_time} {section.location}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  );
}

function attemptText(course: RemainingCourse) {
  if (course.attempts === 0) {
    return course.next_offering.startsWith("In progress") ? "First try" : "Not attempted";
  }
  if (course.failed_attempts === 0) return `Attempted ${course.attempts}`;
  if (course.failed_attempts === 1) return `Attempted ${course.attempts}, did not pass`;
  return `Attempted ${course.attempts}, did not pass ${course.failed_attempts} times`;
}

function cell(student: Student, key: keyof Student) {
  if (key === "remaining") return <RemainingCourses courses={student.remaining} />;
  const value = student[key];
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}
