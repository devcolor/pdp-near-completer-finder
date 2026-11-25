"use client";

import { useEffect, useState } from "react";

import { PageIntro } from "@/components/page-intro";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { ApiError, apiRequest } from "@/lib/api-client";
import { cn } from "cn";

type RequirementFile = {
  field: string;
  filename: string;
  purpose: string;
  columns: string[];
};

type SubmittedYear = {
  year: string;
  students: number;
  /** Null when no prior year is loaded to have disappeared from. */
  not_returning: number | null;
};

type Requirements = {
  institution: string;
  using_upload: boolean;
  files: RequirementFile[];
  years: SubmittedYear[];
  stop_out_basis: string;
  /** Null until two years make the question answerable. */
  stop_outs: number | null;
  completed: number | null;
};

/** The column every submitted year is read from, highlighted wherever it is listed. */
const YEAR_COLUMN = "pdp_year";

/** Split a combined upload error into one message per file, matched on the filename. */
function errorsByFile(message: string, filenames: string[]): Record<string, string> {
  const pattern = new RegExp(`(?=(?:${filenames.map((name) => name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")}))`);
  const found: Record<string, string> = {};
  for (const part of message.split(pattern)) {
    const text = part.trim();
    const filename = filenames.find((name) => text.startsWith(name));
    if (filename) found[filename] = text;
  }
  return found;
}

/** Replace one college's four CSVs after each file has the columns the synthetic file has. */
export function UploadView() {
  const [institution, setInstitution] = useState("cmc");
  const [requirements, setRequirements] = useState<Requirements | null>(null);
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [fileErrors, setFileErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiRequest<Requirements>(`/uploads/requirements?institution=${institution}`)
      .then((next) => {
        if (!cancelled) setRequirements(next);
      })
      .catch((reason: Error) => {
        if (!cancelled) setToast(reason.message);
      });
    return () => {
      cancelled = true;
    };
  }, [institution]);

  function chooseInstitution(value: string) {
    setInstitution(value);
    setFiles({});
    setMessage(null);
    setToast(null);
    setFileErrors({});
  }

  function showFileErrors(next: Record<string, string>, summary: string) {
    setFileErrors(next);
    setToast(summary);
    setMessage(null);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!requirements) return;
    const missing = requirements.files.filter((file) => !files[file.field]);
    if (missing.length) {
      const next: Record<string, string> = {};
      for (const file of missing) next[file.filename] = `Choose ${file.filename}.`;
      showFileErrors(next, `Choose ${missing.map((file) => file.filename).join(", ")}.`);
      return;
    }
    const body = new FormData();
    for (const file of requirements.files) {
      const chosen = files[file.field];
      if (chosen) body.append(file.field, chosen, file.filename);
    }
    setBusy(true);
    setToast(null);
    setFileErrors({});
    setMessage(null);
    try {
      await apiRequest(`/uploads?institution=${institution}`, { method: "POST", formData: body, timeoutMs: 60_000 });
      setMessage("Saved. The dashboard is now reading these files.");
      setRequirements(await apiRequest<Requirements>(`/uploads/requirements?institution=${institution}`));
    } catch (reason) {
      const summary = reason instanceof ApiError ? reason.message : "The upload failed.";
      const next = errorsByFile(summary, requirements.files.map((file) => file.filename));
      showFileErrors(next, summary);
    } finally {
      setBusy(false);
    }
  }

  async function forgetYear(year: string) {
    setBusy(true);
    setToast(null);
    setMessage(null);
    try {
      await apiRequest(`/uploads?institution=${institution}&year=${encodeURIComponent(year)}`, { method: "DELETE" });
      setMessage(`Removed ${year}.`);
      setRequirements(await apiRequest<Requirements>(`/uploads/requirements?institution=${institution}`));
    } catch (reason) {
      setToast(reason instanceof ApiError ? reason.message : `Could not remove ${year}.`);
    } finally {
      setBusy(false);
    }
  }

  async function restore() {
    setBusy(true);
    setToast(null);
    setFileErrors({});
    setMessage(null);
    try {
      await apiRequest(`/uploads?institution=${institution}`, { method: "DELETE" });
      setFiles({});
      setMessage("Restored the synthetic files.");
      setRequirements(await apiRequest<Requirements>(`/uploads/requirements?institution=${institution}`));
    } catch (reason) {
      setToast(reason instanceof ApiError ? reason.message : "Could not restore the synthetic files.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="px-6 py-8">
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="flex flex-col gap-8">
      <PageIntro title="Upload" size="sm">
        <p>Replace the four files for one college. A file missing any current column is rejected, and the dashboard keeps the files it already has.</p>
      </PageIntro>
      <form className="flex flex-col gap-6" onSubmit={save}>
        <label className="flex max-w-xs flex-col gap-1 text-sm font-medium">
          Institution
          <select className="h-10 rounded-md border bg-background px-3" value={institution} onChange={(event) => chooseInstitution(event.target.value)}>
            <option value="cmc">Copper Mountain</option>
            <option value="college_two">College 2</option>
          </select>
        </label>
        {requirements?.using_upload && <p className="text-sm text-muted-foreground">This college is reading an uploaded set.</p>}
        {requirements?.files.map((file) => (
          <fieldset key={file.filename} className={cn("flex flex-col gap-2 rounded-xl border p-4", fileErrors[file.filename] && "border-destructive")}>
            <legend className="px-1 text-sm font-semibold">{file.filename}</legend>
            <p className="text-sm text-muted-foreground">{file.purpose}</p>
            <p className="text-xs font-medium">Required columns</p>
            <ul className="flex flex-wrap gap-1.5">
              {file.columns.map((column) => (
                <li
                  key={column}
                  // Inline, not a utility class: a Tailwind colour utility is only generated
                  // when the class is already in the scanned source.
                  className={cn(
                    "rounded-md px-2 py-0.5 text-xs",
                    column === YEAR_COLUMN ? "border font-semibold" : "bg-muted text-muted-foreground",
                  )}
                  style={
                    column === YEAR_COLUMN
                      ? { color: "var(--flag)", borderColor: "var(--flag-border)", backgroundColor: "var(--flag-surface)" }
                      : undefined
                  }
                >
                  {column}
                </li>
              ))}
              {file.columns.includes(YEAR_COLUMN) && (
                <li className="w-full pt-1 text-xs" style={{ color: "var(--flag)" }}>
                  The submitted year is read from {YEAR_COLUMN}. One file may hold several years.
                </li>
              )}
            </ul>
            <div className="flex flex-wrap items-center gap-3 pt-1">
              <label className={cn(buttonVariants({ variant: "outline" }), "cursor-pointer")}>
                Choose file
                <input
                  key={`${institution}-${file.field}`}
                  className="sr-only"
                  type="file"
                  accept=".csv,text/csv"
                  aria-label={file.filename}
                  onChange={(event) => {
                    setFiles((current) => ({ ...current, [file.field]: event.target.files?.[0] ?? null }));
                    setFileErrors((current) => {
                      if (!current[file.filename]) return current;
                      const next = { ...current };
                      delete next[file.filename];
                      return next;
                    });
                  }}
                />
              </label>
              <span className="text-sm text-muted-foreground">{files[file.field]?.name ?? "No file chosen"}</span>
            </div>
            {fileErrors[file.filename] && <p className="text-sm text-destructive">{fileErrors[file.filename]}</p>}
          </fieldset>
        ))}
        {message && <p className="text-sm">{message}</p>}
        <div className="flex flex-wrap gap-3">
          <button className="h-10 rounded-md bg-foreground px-4 text-sm font-medium text-background disabled:opacity-50" type="submit" disabled={busy || !requirements}>
            Check and save
          </button>
          {requirements?.using_upload && (
            <button className="h-10 rounded-md border px-4 text-sm font-medium disabled:opacity-50" type="button" onClick={restore} disabled={busy}>
              Restore synthetic files
            </button>
          )}
        </div>
      </form>
      </div>
      <YearsPanel
        years={requirements?.years ?? []}
        stopOuts={requirements?.stop_outs ?? null}
        completed={requirements?.completed ?? null}
        basis={requirements?.stop_out_basis ?? ""}
        usingUpload={requirements?.using_upload ?? false}
        busy={busy}
        onForget={forgetYear}
      />
      </div>
      {toast && (
        <div className="fixed right-4 bottom-4 z-50 w-[min(24rem,calc(100vw-2rem))]">
          <Alert variant="destructive">
            <AlertTitle>Upload failed</AlertTitle>
            <AlertDescription className="max-h-40 overflow-y-auto">{toast}</AlertDescription>
          </Alert>
        </div>
      )}
    </div>
  );
}

/** Which PDP years the dashboard currently holds, and who did not come back in each. */
function YearsPanel({
  years,
  stopOuts,
  completed,
  basis,
  usingUpload,
  busy,
  onForget,
}: {
  years: SubmittedYear[];
  stopOuts: number | null;
  completed: number | null;
  basis: string;
  usingUpload: boolean;
  busy: boolean;
  onForget: (year: string) => void;
}) {
  // Two years of real submissions answer "who did not come back"; a snapshot cannot.
  const submission = stopOuts !== null;
  return (
    <aside className="flex h-fit flex-col gap-3 rounded-xl border p-4 lg:sticky lg:top-6">
      <h2 className="text-base font-semibold">Years submitted</h2>
      {submission ? (
        <p className="text-sm text-muted-foreground">
          A student appears in a year only if they were enrolled that year, so a student missing
          from the newest year did not come back.
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">
          These counts are <strong className="font-medium text-foreground">not enrollment</strong>.
          The current files hold one row per student, filed under the year they were last
          enrolled, so a year shows how many students <em>last appeared</em> then. Attrition
          cannot be read from that, which is why no year reports who did not return.
        </p>
      )}
      {years.length === 0 ? (
        <p className="text-sm text-muted-foreground">No years loaded yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {years.map((year, index) => (
            <li key={year.year} className="flex items-baseline justify-between gap-2 border-b pb-2 last:border-b-0">
              <div className="flex flex-col">
                <span className="text-base font-medium tabular-nums" style={{ color: "var(--flag)" }}>{year.year}</span>
                <span className="text-sm text-muted-foreground">
                  {year.students.toLocaleString()} {submission ? "students" : "last appeared here"}
                  {year.not_returning !== null && ` · ${year.not_returning.toLocaleString()} did not return`}
                  {submission && index === 0 && " · baseline, nothing earlier to compare"}
                </span>
              </div>
              {usingUpload && (
                <button
                  type="button"
                  className="shrink-0 text-sm underline underline-offset-4 disabled:opacity-50"
                  onClick={() => onForget(year.year)}
                  disabled={busy}
                >
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {stopOuts !== null && (
        <p className="border-t pt-3 text-sm">
          <span className="font-semibold">{stopOuts.toLocaleString()}</span>{" "}
          <span className="text-muted-foreground">
            are missing from {years[years.length - 1]?.year} <em>and</em> still owe credits. This
            is the figure the Executive summary shows as{" "}
            <span className="font-medium text-foreground">Stopped out</span>.
            {completed !== null && completed > 0 && (
              <>
                {" "}
                A further <span className="font-medium text-foreground">{completed.toLocaleString()}</span>{" "}
                did not return because they had already finished their award, so they are counted
                above but are not stop-outs.
              </>
            )}
          </span>
        </p>
      )}
      {basis && (
        <p className="border-t pt-3 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">Counting stop-outs by:</span> {basis}.
          {years.length < 2 && " Load a second year to count them by absence instead."}
        </p>
      )}
      <p className="text-sm text-muted-foreground">
        Counts here cover the students the dashboard measures, so they tie back to it: non-credit
        students are left out and CVC students are excluded unless selected.
      </p>
      {!usingUpload && years.length > 0 && (
        <p className="text-sm text-muted-foreground">
          These are the synthetic files, a one-row-per-student snapshot rather than a year-by-year
          submission, so &ldquo;did not return&rdquo; cannot be worked out from them.
        </p>
      )}
      {usingUpload && (
        <p className="text-sm text-muted-foreground">
          Saving adds the years in your file. Re-uploading a year replaces just that year. The
          profile and schedule files carry no year, so each upload replaces those outright.
        </p>
      )}
    </aside>
  );
}
