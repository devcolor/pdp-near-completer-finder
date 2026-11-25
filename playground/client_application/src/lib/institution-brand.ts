export type InstitutionId = "cmc" | "college_two";

type BrandTokens = Record<string, string>;

type InstitutionBrand = {
  id: InstitutionId;
  /** Strokes for the pathway chart. The first two follow the brand pair. */
  pathways: string[];
  light: BrandTokens;
  dark: BrandTokens;
};

// Copper Mountain publishes teal and copper (cmccd.edu). Hex sampled 10 Nov 2026: teal #165C64, copper #804834.
// College 2 is anonymized, so it uses a neutral slate theme instead of any real college's colors.
// Copper Mountain hasn't published hex values. Dark-mode values are the same hues, light enough to read.
// Later pathway colors are tints so every line stays distinct.
const BRANDS: Record<InstitutionId, InstitutionBrand> = {
  cmc: {
    id: "cmc",
    pathways: ["#14828C", "#E08A3C", "#3CB8B0", "#C45C28", "#2A6F8F", "#E2B56A", "#D4786A"],
    light: {
      "--brand": "#165C64",
      "--background": "#f3f7f7",
      "--sidebar": "#e7f2f3",
      "--primary": "#165C64",
      "--ring": "#165C64",
      "--accent": "#e5f2f3",
    },
    dark: {
      "--brand": "#3db8c4",
      "--background": "#0e1c1e",
      "--card": "#163033",
      "--popover": "#163033",
      "--sidebar": "#122628",
      "--primary": "#3db8c4",
      "--accent": "#1c3a3e",
      "--border": "#3db8c447",
    },
  },
  college_two: {
    id: "college_two",
    pathways: ["#4A5A70", "#5E8C5A", "#8A6BB0", "#C0703A", "#3A8F86", "#B85C7A", "#7A8494", "#9C8A55"],
    light: {
      "--brand": "#3F4A5A",
      "--background": "#f5f6f7",
      "--sidebar": "#eceef1",
      "--primary": "#3F4A5A",
      "--ring": "#3F4A5A",
      "--accent": "#eef0f2",
    },
    dark: {
      "--brand": "#aab6c6",
      "--background": "#15181c",
      "--card": "#1e2228",
      "--popover": "#1e2228",
      "--sidebar": "#1a1d22",
      "--primary": "#aab6c6",
      "--accent": "#262b32",
      "--border": "#aab6c647",
    },
  },
};

const TOKEN_NAMES = ["--brand", "--background", "--card", "--popover", "--sidebar", "--primary", "--ring", "--accent", "--border"];

/** The brand record for a dashboard institution. Unknown ids use Copper Mountain. */
export function institutionBrand(id: string): InstitutionBrand {
  if (id === "college_two") return BRANDS.college_two;
  return BRANDS.cmc;
}

/** Paint the page with one college's colors. Inline styles beat the theme layer. */
export function applyInstitutionBrand(id: string, dark: boolean) {
  const root = document.documentElement;
  for (const name of TOKEN_NAMES) root.style.removeProperty(name);
  const tokens = dark ? institutionBrand(id).dark : institutionBrand(id).light;
  for (const [name, value] of Object.entries(tokens)) root.style.setProperty(name, value);
}

/** Remove the college colors so another screen can use the plain theme. */
export function clearInstitutionBrand() {
  const root = document.documentElement;
  for (const name of TOKEN_NAMES) root.style.removeProperty(name);
}
