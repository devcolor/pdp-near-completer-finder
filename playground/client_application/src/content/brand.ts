/** Name, wording and logo used across the site. */

export type Logo = {
  src: string;
  alt: string;
  width: number;
  height: number;
};

type Brand = {
  name: string;
  /** The institution dashboard's name, shown above every one of its tabs. */
  dashboardName: string;
  /** Under the name on the landing page, and the description search engines show. */
  tagline: string;
  /** Footer: "{name} · {summary} made with ♥ by {madeBy}". */
  summary: string;
  /** Footer credit. Set to null to hide it. */
  madeBy: string | null;
  /** Top left of every page. Set to null to show the name instead. */
  logo: Logo | null;
};

export const brand: Brand = {
  name: "CMC and College 2",
  dashboardName: "Stop-Out Outreach & Re-Engagement Dashboard",
  tagline:
    "Stop-outs, near completers, and outreach from the synthetic Copper Mountain and College 2 files.",
  summary: "synthetic institution views for Copper Mountain and College 2",
  madeBy: "dev/color",
  logo: null,
};
