// The read-only API (api/league_lab_api/main.py). Same origin: the API serves this app.
// Answers are kept in memory for five minutes, so Back and a second tap render at once.

export interface Metric {
  label: string;
  value: string | null;
  delta: string | null;
  trend?: "up" | "down" | "off" | null;
  help: string | null;
}

export interface Block {
  kind: string; // markdown | caption | unavailable | metrics | info | warning
  text?: string;
  metrics?: Metric[];
}

export interface League {
  league_id: string;
  league_name: string;
  season: number;
  scoring_label: string | null;
  is_reference_league: boolean;
}

/** GET /api/leagues?username= (Wave F contract): the user's leagues this season. */
export interface SleeperUser {
  user_id: string;
  username: string;
  display_name: string | null;
  avatar: string | null;
}

export interface UserLeague {
  league_id: string;
  name: string;
  season: number;
  total_rosters: number | null;
  scoring_label: string | null;
  roster_id: number | null; // the user's own team in that league; null = no team (a commissioner-only league)
  team_name: string | null;
  status: string | null;
  in_database: boolean;
}

export interface UserLeagues {
  user: SleeperUser;
  season: number;
  leagues: UserLeague[];
}

export interface Roster {
  roster_id: number;
  team_name: string;
  manager_name: string | null;
}

export interface LineupRow {
  role: "starter" | "bench" | "unplayable";
  slot: string;
  player_name: string | null;
  gsis_id: string | null;
  position: string | null;
  value: number | null;
  margin: number | null;
  flag: string;
}

export interface DecisionCard {
  slot: string;
  slot_label: string;
  gsis_id: string | null;
  player_name: string;
  value: number | null;
  alt_gsis_id: string | null;
  alt_name: string | null;
  alt_value: number | null;
  margin: number | null;
  verdict: string;
  how: string;
  blocks: Block[];
}

export interface Mover {
  gsis_id: string | null;
  player_name: string;
  position: string;
  tags: string | null;
  momentum: number | null;
}

/** The week's opponent (Wave F contract); today's database path still sends the team name as a string. */
export interface Opponent {
  roster_id: number | null;
  team_name: string;
  manager: string | null;
  lineup_value: number | null;
}

export interface MyWeek {
  league_id: string;
  league_name: string;
  season: number;
  scoring_label: string | null;
  roster_id: number;
  team_name: string;
  manager_name: string | null;
  week: number | null;
  record: { wins: number; losses: number; standing: number } | null;
  opponent: Opponent | string | null;
  source?: "database" | "sleeper";
  summary: string;
  league_line: string;
  lineup_value?: number | null;
  cards: DecisionCard[];
  notice: string | null;
  lineup: LineupRow[];
  lineup_full: LineupRow[];
  howto: string | null;
  movers: Mover[];
}

export interface Section {
  title: string;
  blocks: Block[];
}

export interface PlayerCard {
  gsis_id: string;
  player_name: string;
  position: string;
  team: string | null;
  header: string;
  league_id: string;
  league_name: string;
  season: number;
  week: number | null;
  rostered_by_roster_id: number | null;
  is_free_agent: boolean;
  injury_status: string | null;
  locked: boolean;
  proj_points: number | null;
  sections: Partial<Record<SectionKey, Section>>;
  howto: string;
  /** Wave F: rest of season (numbers; the sentence is in the Projection section, or `line` when the API sends it) */
  ros?: Ros | null;
  /** Wave F: sections the API could not build for this league (omitted, said in one line) */
  missing?: string[];
}

export type SectionKey = "usage" | "projection" | "availability" | "value" | "signals";

export interface Ros {
  points: number | null;
  games: number | null;
  p10: number | null;
  p90: number | null;
  pos_rank: number | null;
  playoff_points: number | null;
  from_week: number | null;
  last_week: number | null;
  line?: string | null; // requested of F3: ros.card_line(), the Streamlit card's sentence
}

/** GET /api/ros?league=&position=&limit= (Wave F contract) */
export interface RosPlayer {
  gsis_id: string | null;
  player_name: string;
  position: string;
  team: string | null;
  ros_points: number | null;
  ros_games: number | null;
  playoff_points: number | null;
  p10: number | null;
  p90: number | null;
  pos_rank: number | null;
  rank?: number | null; // the overall rank on position=ALL, if the API sends it (else the list order)
  rostered_by_roster_id: number | null;
  rostered_by_team: string | null;
}

export interface RosList {
  league_id: string;
  from_week: number | null;
  lines_note?: string | null;   // the betting-line caveat (QA, Wave F)
  last_week: number | null;
  players: RosPlayer[];
  positions?: string[]; // requested of F3: the positions this league starts (K / DEF only when it has them)
}

/** One row of analytics.mart_projection_record (GET /api/record) */
export interface RecordRow {
  scope?: string;
  week: number | null;
  position: string;
  status: string | null;
  n_both?: number | null;
  n_players?: number | null;
  ours_spearman?: number | null;
  sleeper_spearman?: number | null;
  ours_mae?: number | null;
  sleeper_mae?: number | null;
  pairs_listed?: number | null;
  pairs_n?: number | null;
  pairs_ours_right?: number | null;
  pairs_sleeper_right?: number | null;
  pairs_both_right?: number | null;
  pairs_disagree?: number | null;
  pairs_ours_right_disagree?: number | null;
  league_name?: string | null;
}

export interface RecordAnswer {
  available?: boolean;
  why?: string;
  league_id?: string;
  from_week?: number | null;
  weeks?: RecordRow[];
  summary?: RecordRow | null;
}

export interface Hit {
  gsis_id: string;
  player_name: string;
  position: string;
  nfl_team: string | null;
  rostered_by_team: string | null;
  is_free_agent: boolean;
  label: string;
}

export interface Status {
  freshness: string;
  warning: string | null;
}

export class Unauthorized extends Error {}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

declare global {
  interface Window {
    // started by the inline script in index.html before this bundle loads (the first screen's data)
    __llPrefetch?: { url: string; res: Promise<Response> };
  }
}

function takePrefetch(path: string): Promise<Response> | undefined {
  const pre = typeof window !== "undefined" ? window.__llPrefetch : undefined;
  if (!pre || pre.url !== path) return undefined;
  window.__llPrefetch = undefined;
  return pre.res;
}

const TTL_MS = 5 * 60_000;
const cache = new Map<string, { at: number; data: unknown }>();
const inflight = new Map<string, Promise<unknown>>();

/** The cached answer for a path, if fresh (lets a page render synchronously on Back). */
export function peek<T>(path: string): T | undefined {
  const hit = cache.get(path);
  return hit && Date.now() - hit.at < TTL_MS ? (hit.data as T) : undefined;
}

export async function get<T>(path: string): Promise<T> {
  const hit = peek<T>(path);
  if (hit !== undefined) return hit;
  const running = inflight.get(path);
  if (running) return running as Promise<T>;
  const p = (async () => {
    const res = await (takePrefetch(path) ?? fetch(path, { credentials: "same-origin", headers: { Accept: "application/json" } }));
    if (res.status === 401) throw new Unauthorized("sign in");
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.error ?? body.detail ?? detail;
      } catch {
        /* not JSON */
      }
      throw new ApiError(res.status, detail);
    }
    const data = (await res.json()) as T;
    cache.set(path, { at: Date.now(), data });
    return data;
  })();
  inflight.set(path, p);
  try {
    return await p;
  } finally {
    inflight.delete(path);
  }
}

export function clearCache(): void {
  cache.clear();
}

export async function session(): Promise<{ gate: boolean; signed_in: boolean }> {
  const res = await fetch("/api/session", { credentials: "same-origin" });
  return res.json();
}

export async function login(password: string): Promise<boolean> {
  const res = await fetch("/api/login", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  return res.ok;
}

export const paths = {
  leagues: () => "/api/leagues",
  rosters: (league: string) => `/api/leagues/${encodeURIComponent(league)}/rosters`,
  myWeek: (league: string, team: number) => `/api/my-week?league=${encodeURIComponent(league)}&team=${team}`,
  player: (gsis: string, league: string, team: number | null) =>
    `/api/player/${encodeURIComponent(gsis)}?league=${encodeURIComponent(league)}${team != null ? `&team=${team}` : ""}`,
  search: (league: string, q: string) => `/api/search?league=${encodeURIComponent(league)}&q=${encodeURIComponent(q)}`,
  status: () => "/api/status",
  userLeagues: (username: string) => `/api/leagues?username=${encodeURIComponent(username)}`,
  ros: (league: string, position: string, limit = 50) =>
    `/api/ros?league=${encodeURIComponent(league)}&position=${encodeURIComponent(position)}&limit=${limit}`,
  record: (league: string) => `/api/record?league=${encodeURIComponent(league)}`,
};
