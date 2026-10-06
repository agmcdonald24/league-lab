// ---- IM-5 (Wave I-M): DFS — the answers' shapes (api/league_lab_api/dfs.py) and the three calls. No league, no team.
import { ApiError, get, Unauthorized } from "../../lib/api";

export type Site = "dk" | "fd";
export const SITES: { key: Site; label: string }[] = [
  { key: "dk", label: "DraftKings" },
  { key: "fd", label: "FanDuel" },
];

export interface ProjRow {
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

export const postLineups = (body: { contest: string; players: SlatePlayer[]; locks: string[]; excludes: string[]; mode: string; n: number }) =>
  post<Lineups>("/api/dfs/lineups", JSON.stringify(body), "application/json");

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
