// ---- IM-5 (Wave I-M): DFS — the answers' shapes (api/league_lab_api/dfs.py) and the three calls. No league, no team.
import { ApiError, get, Unauthorized } from "../../lib/api";

export type Site = "dk" | "fd";
export const SITES: { key: Site; label: string }[] = [
  { key: "dk", label: "DraftKings" },
  { key: "fd", label: "FanDuel" },
];

// ---- IN-4 (Wave I-N): context beyond the projection (api/league_lab_api/dfs.py context_for; docs/DFS.md § Context)
export type Tone = "favorable" | "neutral" | "difficult" | null;
export interface Signal {
  signal: "defense" | "corner" | "role" | "routes" | "game" | "weather";
  label: string;
  tone: Tone;
  words: string;
  in_projection: boolean;
  projection_words: string;
  trend?: "up" | "down" | null;
  shutdown?: boolean;
  certainty?: string | null;
  implied?: number | null;
  // ---- IO-1 (Wave I-O): the corner's graded effect (the context record), when the grade exists; its quarter (fix round:
  // the corner is information — no tone, never coloured, sorted or filtered on)
  graded?: string | null;
  quarter?: "shutdown" | "solid" | "target" | "unranked" | null;
  graded_effect?: "none" | "measured" | null;
}
export interface ContextMeta {
  matchup: boolean;
  matchup_words: string | null;
  lines: boolean;
  forecast: boolean;
  projection: Record<string, Record<string, boolean>>;
  in_words: string;
  out_words: string;
  words: string;
  worth_rule: string;
  // ---- IO-1 (Wave I-O): the record's sentences (null without the record); fix round: "Worth a look" off, one line
  worth_line?: string | null;
  corner_record?: string | null;
}
export interface WithContext {
  context?: Signal[];
  worth?: boolean;
  worth_reasons?: string[];
}

export interface ProjRow extends WithContext {
  key: string;
  gsis_id: string | null;
  player_name: string;
  position: string;
  team: string | null;
  opponent: string | null;
  proj: number | null;
  p10: number | null;
  p25: number | null;
  p75: number | null;
  p90: number | null;
  status: string | null;
  out: boolean;
  matchup: string | null;
}

export interface Projections {
  site: Site;
  site_name: string;
  season: number;
  week: number;
  players: ProjRow[];
  count: number;
  reference: string | null;
  scoring: string[];
  bonus_at_odds: boolean;
  worth_a_look?: Record<string, string[]>;
  context_meta?: ContextMeta | null;
}

export interface SlatePlayer extends Omit<ProjRow, "player_name"> {
  site_id: string;
  name_id: string | null;
  name: string;
  player_name: string | null;
  our_key: string;
  game: string | null;
  kickoff: string | null;
  salary: number;
  cpt_id: string | null;
  cpt_salary: number | null;
  pts_per_k: number | null;
  ceil_per_k: number | null;
  line_points: number | null;
  value_gap: number | null;
  value_z: number | null;
  value_rank: number | null;
  value_call: "undervalued" | "overpriced" | null;
  status_source: string | null;
  site_avg: number | null;
  reason: string | null;
}

export interface Unmatched {
  key: string;
  name: string;
  position: string;
  team: string;
  salary: number;
  reason: string;
}

export interface Fit {
  slope_per_1000: number;
  intercept: number;
  n: number;
  rmse: number;
  words: string;
}

export interface Slate {
  site: Site;
  site_name: string;
  contest: "dk_classic" | "dk_showdown" | "fd_full";
  contest_label: string;
  cap: number;
  season: number;
  week: number;
  games: string[];
  players: SlatePlayer[];
  unmatched: Unmatched[];
  skipped: { row: number; name: string; reason: string }[];
  matched_by: Record<string, number>;
  counts: { on_file: number; matched: number; unmatched: number; skipped: number };
  fit: Record<string, Fit | null>;
  undervalued: string[];
  overpriced: string[];
  notes: string[];
  scoring: string[];
  bonus_at_odds: boolean;
  worth_a_look?: Record<string, string[]>;
  context_meta?: ContextMeta | null;
  published?: boolean;
  slate_id?: string | null;
  label?: string;
}

export interface LineupSlot {
  slot: string;
  key: string;
  multiplier: number;
  salary: number;
  proj: number;
  upload_id: string;
  name: string | null;
  position: string;
  team: string | null;
  gsis_id: string | null;
  opponent: string | null;
}

export interface Lineup {
  slots: LineupSlot[];
  salary: number;
  salary_left: number;
  proj: number;
  ceiling_sum: number | null;
  low: number | null;
  high: number | null;
  proven: boolean;
  mode: "cash" | "tournament";
}

export interface Lineups {
  contest: string;
  contest_label: string;
  cap: number;
  mode: "cash" | "tournament";
  lineups: Lineup[];
  notes: string[];
  solve_ms: number[];
  left_out: { key: string; name: string | null; status: string | null }[];
  upload_csv: string | null;
  filename: string;
}

export const MAX_BYTES = 1_000_000;
export const MAX_PLAYERS = 800; // ---- IM-5 fix: the lineups route's cap (league_lab.dfs.MAX_PLAYERS)

export const projectionsPath = (site: Site, week?: number | null) => `/api/dfs/projections?site=${site}&limit=1000${week ? `&week=${week}` : ""}`;

export function loadProjections(site: Site): Promise<Projections> {
  return get<Projections>(projectionsPath(site));
}

async function post<T>(path: string, body: BodyInit, type: string): Promise<T> {
  const res = await fetch(path, { method: "POST", credentials: "same-origin", headers: { "Content-Type": type, Accept: "application/json" }, body });
  if (res.status === 401) throw new Unauthorized("sign in");
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = await res.json();
      detail = b.error ?? b.detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

/** The salary file's text → the slate (parsed in one request; the server keeps nothing). */
export const postSlate = (text: string) => post<Slate>("/api/dfs/slate", text, "text/csv");

export interface StackRules {
  with_qb: 0 | 1 | 2;
  bring_back: boolean;
  no_def_vs_qb: boolean;
}
export const postLineups = (body: {
  contest?: string;
  players?: SlatePlayer[];
  slate_id?: string;
  locks: string[];
  excludes: string[];
  mode: string;
  n: number;
  stack?: StackRules | null;
  max_exposure?: number | null;
}) => post<Lineups>("/api/dfs/lineups", JSON.stringify(body), "application/json");

// ---- IN-4: published slates — the site's salary file for this week, on the server (no upload to start)
export interface PublishedRow {
  id: string;
  site: Site;
  site_name: string;
  label: string;
  season: number;
  week: number;
  contest: string;
  contest_label: string;
  on_file: number;
  matched: number | null;
  unmatched: number | null;
}
export interface PublishedList {
  season: number;
  week: number;
  slates: PublishedRow[];
  not_offered: { id: string; reason: string }[];
  unreadable: { file: string; reason: string }[];
}
export const loadPublishedList = (site: Site) => get<PublishedList>(`/api/dfs/slates?site=${site}`);
export const loadPublished = (id: string) => get<Slate>(`/api/dfs/slate/${encodeURIComponent(id)}`);

/** The chip's short words for a signal (the sentence is in its title and the row's detail). */
export function chipWords(s: Signal): string {
  if (s.signal === "role" || s.signal === "routes") return s.trend === "down" ? "Role down" : "Role up";
  // ---- IO-1 fix round: the corner's words from its quarter, never from a tone
  if (s.signal === "corner") return s.quarter === "shutdown" || s.shutdown ? "Shutdown corner" : s.quarter === "target" ? "Soft corner" : s.quarter === "solid" ? "Average corner" : s.quarter === "unranked" ? "Corner unranked" : "Corner unclear";
  if (s.signal === "defense") return s.tone === "favorable" ? "Soft defense" : s.tone === "difficult" ? "Tough defense" : "Defense average";
  if (s.signal === "game") return `Team total ${s.implied?.toFixed(1) ?? "—"}`;
  // ---- IO-1: the forecast's own numbers ("Wind 20 mph", "Rain (0.13 in)") rather than one word
  const m = /:\s*(.+?)\.?$/.exec(s.words ?? "");
  if (m) return m[1].charAt(0).toUpperCase() + m[1].slice(1);
  return "Weather";
}

// the slate stays in this tab (memory + sessionStorage), one per site; never in localStorage, never on the server
const KEY = (site: Site) => `ll.dfs.slate.${site}`;
export function savedSlate(site: Site): Slate | null {
  try {
    const raw = sessionStorage.getItem(KEY(site));
    return raw ? (JSON.parse(raw) as Slate) : null;
  } catch {
    return null;
  }
}
export function saveSlate(site: Site, s: Slate | null): void {
  try {
    if (s === null) sessionStorage.removeItem(KEY(site));
    else sessionStorage.setItem(KEY(site), JSON.stringify(s));
  } catch {
    /* full or blocked: this tab's memory still has it */
  }
}

export const money = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `$${v.toLocaleString("en-US")}`);
export const POS_LABEL: Record<string, string> = { QB: "QB", RB: "RB", WR: "WR", TE: "TE", K: "K", DEF: "DST" };
