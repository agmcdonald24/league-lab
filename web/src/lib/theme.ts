// The design system's values that code needs (docs/DESIGN.md): team accents for all 32 teams, position colors, the
// chart series roles and a few helpers. Colors that only CSS needs live in app.css as tokens (--ll-*); this file holds
// what is chosen per row (a team, a position, a heatmap value).

export interface TeamColors {
  name: string;
  /** the team's main color: a badge's fill (text on it from `onColor`) */
  primary: string;
  /** a color of the team's that reads on the dark surface AND the light one: stripes, the headshot's glow, bars */
  accent: string;
}

// nflverse abbreviations (dim_player.latest_team: LA = the Rams). Primary = the team's first color; accent = the
// first of its colors with OKLCH lightness between ~0.45 and ~0.75 (visible on #0b0e14 and on #f6f7f9).
export const TEAMS: Record<string, TeamColors> = {
  ARI: { name: "Arizona Cardinals", primary: "#97233F", accent: "#C8324F" },
  ATL: { name: "Atlanta Falcons", primary: "#A71930", accent: "#D0283F" },
  BAL: { name: "Baltimore Ravens", primary: "#241773", accent: "#6A55C8" },
  BUF: { name: "Buffalo Bills", primary: "#00338D", accent: "#2F6BD8" },
  CAR: { name: "Carolina Panthers", primary: "#0085CA", accent: "#1C93D2" },
  CHI: { name: "Chicago Bears", primary: "#0B162A", accent: "#C83803" },
  CIN: { name: "Cincinnati Bengals", primary: "#FB4F14", accent: "#F2581F" },
  CLE: { name: "Cleveland Browns", primary: "#311D00", accent: "#FF3C00" },
  DAL: { name: "Dallas Cowboys", primary: "#003594", accent: "#3A6FD0" },
  DEN: { name: "Denver Broncos", primary: "#FB4F14", accent: "#F2581F" },
  DET: { name: "Detroit Lions", primary: "#0076B6", accent: "#1E88C8" },
  GB: { name: "Green Bay Packers", primary: "#203731", accent: "#3E8A5E" },
  HOU: { name: "Houston Texans", primary: "#03202F", accent: "#C8243A" },
  IND: { name: "Indianapolis Colts", primary: "#002C5F", accent: "#2F6AB0" },
  JAX: { name: "Jacksonville Jaguars", primary: "#006778", accent: "#0A8BA0" },
  KC: { name: "Kansas City Chiefs", primary: "#E31837", accent: "#E31837" },
  LA: { name: "Los Angeles Rams", primary: "#003594", accent: "#3A6FD0" },
  LAC: { name: "Los Angeles Chargers", primary: "#0080C6", accent: "#1A8FD0" },
  LV: { name: "Las Vegas Raiders", primary: "#000000", accent: "#8E959A" },
  MIA: { name: "Miami Dolphins", primary: "#008E97", accent: "#0A9AA3" },
  MIN: { name: "Minnesota Vikings", primary: "#4F2683", accent: "#7A4FC0" },
  NE: { name: "New England Patriots", primary: "#002244", accent: "#C60C30" },
  NO: { name: "New Orleans Saints", primary: "#D3BC8D", accent: "#B39A62" },
  NYG: { name: "New York Giants", primary: "#0B2265", accent: "#3758B8" },
  NYJ: { name: "New York Jets", primary: "#125740", accent: "#1F8A62" },
  PHI: { name: "Philadelphia Eagles", primary: "#004C54", accent: "#14808C" },
  PIT: { name: "Pittsburgh Steelers", primary: "#FFB612", accent: "#E0A10E" },
  SEA: { name: "Seattle Seahawks", primary: "#002244", accent: "#4F9E1F" },
  SF: { name: "San Francisco 49ers", primary: "#AA0000", accent: "#D21F1F" },
  TB: { name: "Tampa Bay Buccaneers", primary: "#D50A0A", accent: "#D50A0A" },
  TEN: { name: "Tennessee Titans", primary: "#0C2340", accent: "#4B92DB" },
  WAS: { name: "Washington Commanders", primary: "#5A1414", accent: "#B8342C" },
};

// other spellings (Sleeper, ESPN, old cities) → nflverse
const ALIASES: Record<string, string> = { LAR: "LA", JAC: "JAX", WSH: "WAS", OAK: "LV", SD: "LAC", STL: "LA", ARZ: "ARI", BLT: "BAL", CLV: "CLE", HST: "HOU" };

// IE-0 (Wave I-E): a missing NFL team is not "Free agent" (the review: a rostered team QB read as one)
const NEUTRAL: TeamColors = { name: "No NFL team", primary: "#4b5563", accent: "#7d8699" };

export function teamKey(abbr: string | null | undefined): string | null {
  if (!abbr) return null;
  const a = abbr.trim().toUpperCase();
  return TEAMS[a] ? a : (ALIASES[a] ?? null);
}

/** A team's colors; a neutral gray for no team (a free agent) or an unknown code. */
export function team(abbr: string | null | undefined): TeamColors {
  const k = teamKey(abbr);
  return k ? TEAMS[k] : NEUTRAL;
}

/** The team code to show (LA → LAR reads better to a fan); null stays null. */
export function teamLabel(abbr: string | null | undefined): string | null {
  const k = teamKey(abbr);
  if (!k) return abbr ?? null;
  return k === "LA" ? "LAR" : k;
}

function luminance(hex: string): number {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(h.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Text on a fill: white or near-black, whichever clears contrast. */
export function onColor(hex: string): string {
  const L = luminance(hex);
  return (1.05 / (L + 0.05) >= (L + 0.05) / 0.05) ? "#ffffff" : "#0b0e14";
}

// Positions: tinted chips (the color is the chip's wash and its dot; the text stays ink). The hues are the dataviz
// palette's categorical slots (docs/DESIGN.md § Color), one per position, so a position reads the same everywhere.
export const POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"] as const;
export const POSITION_COLOR: Record<string, string> = {
  QB: "var(--ll-pos-qb)",
  RB: "var(--ll-pos-rb)",
  WR: "var(--ll-pos-wr)",
  TE: "var(--ll-pos-te)",
  K: "var(--ll-pos-k)",
  DEF: "var(--ll-pos-def)",
};
export const positionColor = (p: string | null | undefined) => (p && POSITION_COLOR[p.toUpperCase()]) || "var(--ll-ink-3)";

// Chart roles (CSS variables, so light / dark swap in one place): actual = series 1, expected = the de-emphasis
// ink, over / under = the diverging pair (warm = running hot, cool = due), magnitude = the sequential blue.
export const SERIES = {
  actual: "var(--ll-series-1)",
  expected: "var(--ll-ink-3)",
  hot: "var(--ll-div-hot)",
  due: "var(--ll-div-due)",
  grid: "var(--ll-grid)",
  axis: "var(--ll-axis)",
};

/** A sequential (one-hue) heatmap fill for t in [0, 1]: the surface at 0, the full hue at 1 (both modes). */
export function seqFill(t: number): string {
  const p = Math.round(Math.max(0, Math.min(1, t)) * 100);
  return `color-mix(in oklab, var(--ll-seq-hi) ${p}%, var(--ll-seq-lo))`;
}

/** Ink on a sequential fill: the light ink past the middle of the ramp (the fill is strong), else the normal ink. */
export function seqInk(t: number): string {
  return t > 0.55 ? "var(--ll-seq-ink-strong)" : "var(--ll-ink)";
}

// ---- number formats (one place, so a number reads the same on every screen)
export const fmt = {
  /** 12.3 (one decimal), "—" for unknown (unknown is not zero) */
  pts: (v: number | null | undefined, d = 1) => (v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(d)),
  /** +2.1 / −1.4 (a real minus sign) */
  signed: (v: number | null | undefined, d = 1) =>
    v === null || v === undefined || Number.isNaN(v) ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}`,
  /** 0.234 → 23% */
  pct: (v: number | null | undefined, d = 0) => (v === null || v === undefined || Number.isNaN(v) ? "—" : `${(v * 100).toFixed(d)}%`),
  whole: (v: number | null | undefined) => (v === null || v === undefined || Number.isNaN(v) ? "—" : String(Math.round(v))),
};

/** "Ja'Marr Chase" → ["Ja'Marr", "Chase"]; "Amon-Ra St. Brown" → ["Amon-Ra", "St. Brown"] (the card's two lines). */
export function splitName(name: string): [string, string] {
  const parts = name.trim().split(/\s+/);
  if (parts.length < 2) return ["", name];
  const suffix = /^(jr\.?|sr\.?|ii|iii|iv|v)$/i;
  let lastStart = parts.length - 1;
  if (suffix.test(parts[lastStart]) && lastStart > 1) lastStart--;
  if (lastStart > 1 && /^(st\.?|de|del|la|le|van|von|da|di)$/i.test(parts[lastStart - 1])) lastStart--;
  return [parts.slice(0, lastStart).join(" "), parts.slice(lastStart).join(" ")];
}
