// The read-only API (api/league_lab_api/main.py). Same origin: the API serves this app.
// Answers are kept in memory for five minutes, so Back and a second tap render at once.
import { trackTradeEvaluate } from "./analytics"; // ---- INF-1: Google Analytics

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
  // ---- IA-1: the slot list's headshot and team (the player card unit's small size on every row)
  headshot_url?: string | null;
  team?: string | null;
  // ---- end IA-1
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
  why?: string | null; // ---- IA-1: the reason sentence (also the card's second block)
  // ---- IB-0: the call's status (Change needed / Already set / Close call; null when Sleeper's lineup is unknown),
  // its strength, and who of the two Sleeper starts right now
  status?: "change" | "set" | "close" | null;
  strength?: "clear" | "lean" | "coin flip" | null;
  in_sleeper_lineup?: { player: boolean; alt: boolean } | null;
  // ---- end IB-0
  blocks: Block[];
}

// ---- IB-0: one availability truth - the roster context's summary that Waivers and Team carry (My Week: `availability`)
export interface RosterContextSummary {
  league_id: string;
  roster_id: number;
  week: number;
  lineup_value: number | null;
  changed: boolean;
  changes: string[];
  checked_at: string | null;
  as_of_build: string | null;
}
// ---- end IB-0

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
  changes?: string[]; // ---- IB-0: his lineup through the same overlay (who moved and why)
  also?: Opponent[]; // ---- I-C: a double header's other opponent(s) (MFL leagues can play twice in a week)
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

export type SectionKey = "usage" | "projection" | "availability" | "value" | "signals" | "role"; // ---- IL-1: + role

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

// ---- V-1 (Wave I-G): the decision record (GET /api/record `decisions`; INTERFACES.md § V-1): per scored week the
// league's sums over its teams — what they started, what our lineups (recorded before the first kickoff) would have
// scored, the best lineups in hindsight — the season (= the sum of the weeks), the close calls graded by the outcome
// (the coin-flip line, the calibration table) and the lineups whose starter's injury report changed after our build
export interface RecordDecisionWeek {
  week: number;
  record_source: "kickoff" | "reconstructed" | "mixed";
  rosters: number;
  submitted: number;
  app: number;
  optimum: number;
  regret: number;
  edge: number;
  news_rosters: number;
}
export interface RecordDecisions {
  available: boolean;
  season?: number;
  why?: string;
  weeks?: RecordDecisionWeek[];
  season_totals?: { weeks: number; roster_weeks: number; submitted: number; app: number; optimum: number; regret: number; edge: number; market?: number | null; market_weeks?: number[] } | null; // V-2: market
  calls?: {
    n: number;
    won: number | null;
    expected: number | null;
    brier: number | null;
    coin_flips: { n: number; won: number | null; expected: number | null };
    table: { bin: number; n: number; p_lo: number; p_hi: number; predicted: number; observed: number }[];
  };
  news?: { roster_weeks: number; edge: number | null; regret: number | null; source?: "events" | "report" | "mixed" }; // V-2: source
  sentences?: { edge: string | null; calls: string | null; news: string | null; market?: string | null }; // V-2: market
  reconstructed_weeks?: number[];
  note?: string | null;
}
export interface RecordAnswer {
  decisions?: RecordDecisions;
}
// ---- end V-1

// ---- V-2 (Wave I-H): the decision record, personal and live (GET /api/record?league=&team= `decisions`; INTERFACES.md
// § V-2): Sleeper's projections as a lineup (`market`), where the news flag came from (`news_source`: the event store
// or the injury report), an MFL league's record (`platform: "mfl"`), and one team's view (`team`)
export interface RecordDecisionWeek {
  market?: number | null;
  news_source?: "events" | "report" | "mixed";
}
export interface RecordTeamCall {
  call_rank: number;
  slot: string | null;
  player_name: string | null;
  alt_player_name: string | null;
  p_win: number | null;
  is_coin_flip: boolean | null;
  starter_points: number | null;
  alt_points: number | null;
  outcome: number | null;
  words: string;
}
export interface RecordTeamWeek {
  week: number;
  record_source: "kickoff" | "reconstructed";
  submitted: number;
  app: number;
  optimum: number;
  market: number | null;
  edge: number;
  regret: number;
  market_edge: number | null;
  n_changed: number | null;
  news: boolean;
  news_source: "events" | "report";
  calls: RecordTeamCall[];
}
export interface RecordTeam {
  roster_id: number;
  team_name: string | null;
  available: boolean;
  why?: string;
  weeks: RecordTeamWeek[];
  season_totals: { weeks: number; submitted: number; app: number; optimum: number; edge: number; regret: number; market: number | null; market_weeks: number[]; market_edge: number | null } | null;
  calls: { n: number; won: number | null; expected: number | null; brier: number | null; coin_flips: { n: number; won: number | null; expected: number | null } } | null;
  news: { weeks: number[]; edge: number | null } | null;
  sentences: { season: string | null; market: string | null; calls: string | null; news: string | null };
}
export interface RecordDecisions {
  platform?: "mfl";
  team?: RecordTeam | null;
}
export const recordTeamPath = (league: string, team: number) =>
  `/api/record?league=${encodeURIComponent(league)}&team=${team}`;
// ---- end V-2

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
  body: unknown; // ---- IE-0: the error's JSON (a trade's `unavailable` assets), when there is one
  constructor(status: number, message: string, body: unknown = null) {
    super(message);
    this.status = status;
    this.body = body;
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
      let body: unknown = null; // ---- IM-3: the error's JSON rides on the ApiError (`code`: needs_league, rate_limited)
      try {
        body = await res.json();
        const b = body as { error?: string; detail?: string };
        detail = b.error ?? b.detail ?? detail;
      } catch {
        /* not JSON */
      }
      throw new ApiError(res.status, detail, body);
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

// ---- G3 (Wave G): the research screens' shapes. G1's answers reach them through lib/shapes.ts (the one mapping layer);
// the fixtures (web/fixtures/*_<league>.json) are G1's saved answers (make_research_fixtures.py)

/** The player fields every research row carries (joined from dim_player). */
export interface PlayerHead {
  gsis_id: string;
  player_name: string;
  position: string;
  team: string | null;
  headshot_url: string | null;
}

export interface Owned {
  rostered_by_roster_id: number | null;
  rostered_by_team: string | null;
}

export interface RoleAlert {
  direction: "up" | "down";
  kind: string;
  direction_label: string | null;
  label: string | null; // app/lib/signals.kind_label: "Filling in", "Bigger role" …
  change_text: string | null;
  cause_text: string | null;
  games_held: number | null;
}

/** GET /api/trends?league=&view=over|under|all&position=&limit= — mart_player_trend_tags + actual vs expected */
export interface TrendRow extends PlayerHead, Owned {
  games: number | null;
  latest_week: number | null;
  tags: string | null;
  momentum: number | null;
  opportunity_trend: string | null;
  n_up: number | null;
  n_down: number | null;
  target_share_l3: number | null;
  target_share_change: number | null;
  snap_share_l3: number | null;
  snap_share_change: number | null;
  carry_share_change: number | null;
  expected_points_l3: number | null;
  expected_points_change: number | null;
  points_l3: number | null;
  points_change: number | null;
  games_with_expected: number | null;
  ppg: number | null; // points per game, this league's scoring
  xppg: number | null; // expected points per game (what his work is usually worth)
  gap: number | null; // ppg − xppg
  direction: "over" | "under" | "even";
  role_alert: RoleAlert | null;
  // ---- IA-1: the work per game (last 3 games and the season), snaps over the last 3, the reason in a sentence
  targets_pg_l3?: number | null;
  targets_pg?: number | null;
  carries_pg_l3?: number | null;
  carries_pg?: number | null;
  snap_pct_l3?: number | null;
  rz_targets?: number | null;
  rz_carries?: number | null;
  tds?: number | null;
  why?: string | null; // "Getting the targets of a 10.5-point player, scoring 3.6: no touchdowns on 4 red-zone targets."
  cause?: string | null;
  // ---- end IA-1
}

export interface Trends {
  league_id: string;
  season: number;
  week: number | null;
  players: TrendRow[];
}

/** GET /api/matchups/defense?league=&team= — mart_defense_vs_position_current per team × position */
export interface DefenseCell {
  defense: string;
  position: string;
  games: number | null;
  points_allowed_pg: number | null;
  rank: number | null; // 1 = gives up the most to the position (the matchup you want)
  points_allowed_pg_l4: number | null;
  rank_l4: number | null;
  trend: "up" | "down" | "steady" | null;
}

export interface Starter extends PlayerHead {
  opponent: string | null;
  is_home: boolean | null;
  slot: string | null;
}

export interface DefenseMatrix {
  league_id: string;
  season: number;
  week: number | null;
  weeks_used: number | null;
  positions: string[];
  teams: DefenseCell[];
  starters?: Starter[]; // with team=: your starters this week and the defense each faces (added to G1 at integration)
}

/** GET /api/matchups/cb?league=&team= — mart_cb_matchups (+ mart_cb_rankings, the projection) for your receivers */
export interface CbMatchup extends PlayerHead, Owned {
  opponent: string | null;
  is_home: boolean | null;
  call_status: string | null; // called | too few targets | tight end | no depth chart yet
  call_strength: string | null; // clear | lean
  alignment_lean: string | null;
  located_targets: number | null;
  left_share: number | null;
  middle_share: number | null;
  right_share: number | null;
  side_share: number | null;
  other_side_share: number | null;
  likely_cover_gsis_id: string | null;
  likely_cover_name: string | null;
  likely_cover_slot: string | null;
  cover_rank: number | null;
  cover_label: string | null; // shutdown | solid | target
  other_cover_name: string | null;
  other_cover_slot: string | null;
  cb_n_ranked: number | null;
  shadow_flag: boolean | null;
  games_vs_cover: number | null;
  targets_vs_cover: number | null;
  receptions_vs_cover: number | null;
  yards_vs_cover: number | null;
  tds_vs_cover: number | null;
  line: string; // app/lib/matchups.cb_line (markdown)
  lean: string | null; // app/lib/matchups.lean_text
  proj_points: number | null;
  p25: number | null;
  p75: number | null;
  is_starter: boolean;
}

export interface CbMatchups {
  league_id: string;
  season: number;
  week: number | null;
  matchups: CbMatchup[];
}

/** GET /api/players?league=&season=&limit= — mart_player_season + points in this league's scoring */
export interface SeasonRow extends PlayerHead, Owned {
  games_played: number | null;
  points: number | null;
  points_per_game: number | null;
  targets: number | null;
  target_share: number | null;
  receptions: number | null;
  receiving_yards: number | null;
  receiving_tds: number | null;
  carries: number | null;
  carry_share: number | null;
  rushing_yards: number | null;
  rushing_tds: number | null;
  attempts: number | null;
  passing_yards: number | null;
  passing_tds: number | null;
  passing_interceptions: number | null;
  avg_offense_snap_pct: number | null;
  adot: number | null;
  first_read_target_share: number | null;
  route_participation: number | null;
}

export interface Players {
  league_id: string;
  season: number;
  total: number;
  players: SeasonRow[];
}

/** GET /api/receivers?league=&season= — mart_player_season usage + mart_player_recent_form, with the yardsticks */
export interface ReceiverRow extends PlayerHead, Owned {
  games_played: number | null;
  ppg: number | null;
  target_share: number | null;
  targets_per_game: number | null;
  air_yards_share: number | null;
  adot: number | null;
  first_read_target_share: number | null;
  route_participation: number | null;
  tprr_proxy: number | null;
  yprr_proxy: number | null;
  avg_offense_snap_pct: number | null;
  target_share_l3: number | null;
  target_share_l5: number | null;
  snap_pct_l3: number | null;
  route_participation_l3: number | null;
  first_read_share_l3: number | null;
}

export type Yardstick = Partial<Record<keyof ReceiverRow | "ppg", number | null>>;

export interface Receivers {
  league_id: string;
  season: number;
  through_week: number | null;
  yardsticks: Record<string, Yardstick>; // WR / TE: the top 12's averages (WORDS.md "yardstick")
  receivers: ReceiverRow[];
}

/** GET /api/compare?league=&a=&b= — the same keys on both sides */
export interface CompareSide extends PlayerHead, Owned {
  week: number | null;
  proj_points: number | null;
  p10: number | null;
  p25: number | null;
  p75: number | null;
  p90: number | null;
  opponent: string | null;
  opp_rank: number | null;
  injury_status: string | null;
  season_stats: {
    games_played: number | null;
    ppg: number | null;
    xppg: number | null;
    targets_per_game: number | null;
    carries_per_game: number | null;
    receiving_yards_pg: number | null;
    rushing_yards_pg: number | null;
    passing_yards_pg: number | null;
    tds_pg: number | null;
  };
  form: { games_l3: number | null; ppg_l3: number | null; target_share_l3: number | null; carry_share_l3: number | null; snap_pct_l3: number | null };
  usage: {
    target_share: number | null;
    carry_share: number | null;
    snap_pct: number | null;
    route_participation: number | null;
    first_read_target_share: number | null;
    air_yards_share: number | null;
  };
  ros: { points: number | null; games: number | null; p10: number | null; p90: number | null; pos_rank: number | null; playoff_points: number | null } | null;
  next4: { week: number; opponent: string | null; is_home: boolean | null; opp_rank: number | null }[];
}

export interface Compare {
  a: CompareSide;
  b: CompareSide;
}

/** GET /api/player/{gsis}/games?league=&season= — fct_player_game, points in this league's scoring */
export interface GameRow {
  season: number;
  week: number;
  opponent: string | null;
  is_home: boolean | null;
  played: boolean | null;
  offense_snap_pct: number | null;
  targets: number | null;
  receptions: number | null;
  receiving_yards: number | null;
  receiving_tds: number | null;
  carries: number | null;
  rushing_yards: number | null;
  rushing_tds: number | null;
  attempts: number | null;
  passing_yards: number | null;
  passing_tds: number | null;
  passing_interceptions: number | null;
  points: number | null;
  expected_points: number | null;
}

export interface Games {
  games: GameRow[];
}

const q = encodeURIComponent;
export const researchPaths = {
  trends: (league: string) => `/api/trends?league=${q(league)}&view=all&limit=200&metrics=none&min_games=2`,
  defense: (league: string, team: number | null) => `/api/matchups/defense?league=${q(league)}${team != null ? `&team=${team}` : ""}`,
  cb: (league: string, team: number) => `/api/matchups/cb?league=${q(league)}&team=${team}`,
  players: (league: string) => `/api/players?league=${q(league)}&sort=points&dir=desc&limit=500`,
  receivers: (league: string) => `/api/receivers?league=${q(league)}&limit=150`,
  compare: (league: string, a: string, b: string) => `/api/compare?league=${q(league)}&a=${q(a)}&b=${q(b)}`,
  games: (gsis: string, league: string, season: number) => `/api/player/${q(gsis)}/games?league=${q(league)}&season=${season}`,
};

/** Wave G: the contract adds the picture to the player card (dim_player.headshot_url; null = a silhouette). */
export interface PlayerCard {
  headshot_url?: string | null;
}

// ---- G4: the decision screens (Wave G, plan G4) on G2's routes: /api/waivers, /api/trades/evaluate,
// /api/trades/partners, /api/team, /api/league. The shapes are G2's (dev/G2 `api/league_lab_api/decisions.py`; the
// fixtures are its saved answers): rows carry the marts' column names, player objects carry headshot_url / team /
// position, and the pages' sentences come as `words`. Fields marked "requested" are asked of G2 (the fixtures add them).

/** A player on a decision screen (G2's `_player`). */
export interface DPlayer {
  sleeper_id: string | null;
  gsis_id: string | null;
  player_name: string | null;
  position: string | null;
  team: string | null;
  headshot_url: string | null;
}

export interface WaiverAdd extends DPlayer {
  projection: number | null;
  value_source: string | null;
  p10: number | null;
  p25: number | null;
  p75: number | null;
  p90: number | null;
  report_status: string | null;
  reason: string | null;
  games_played: number | null;
  is_no_evidence: boolean | null;
  ros_points: number | null;
  ros_rank_pos: number | null;
  season_points_left: number | null;
}

export interface WaiverDrop extends DPlayer {
  projection: number | null;
  is_starter: boolean | null;
  horizon_loss: number | null;
  season_points_left: number | null;
  ros_points: number | null;
  // ---- IB-0: he starts this week by the roster's context (the overlay), and where; never "would not start" then
  starts_this_week?: boolean;
  slot_this_week?: string | null;
  // ---- end IB-0
}

/** One row of mart_waiver_moves (or the on-demand sweep), nested: the free agent, the drop, the gains, the card's words. */
export interface WaiverMove {
  move_rank: number | null;
  add_rank: number | null;
  list_kind: "start_now" | "cover" | "nothing";
  is_best_drop: boolean | null;
  add: WaiverAdd;
  drop: WaiverDrop | null;
  weekly_gain: number;
  horizon_gain: number;
  week_gains: (number | null)[] | null;
  add_horizon_gain: number | null;
  lineup_before: number | null;
  lineup_after: number | null;
  add_slot: string | null;
  fills_empty_slot: boolean | null;
  displaced: (DPlayer & { projection: number | null; slot: string | null }) | null;
  open_roster_spots: number | null;
  words: { headline: string; lines: string[]; why: string | null; source?: string };
}

export interface FreeAgent extends DPlayer {
  projection: number | null;
  p10: number | null;
  p25: number | null;
  p75: number | null;
  p90: number | null;
  injury_status: string | null;
  games_played: number | null;
  ros_points: number | null;
  ros_rank_pos: number | null;
  ppg_std?: number | null;
  expected_per_game?: number | null;
  diff_per_game?: number | null;
  target_share_l3?: number | null;
  snap_pct_l3?: number | null;
}

export interface Waivers {
  league_id: string;
  source: "database" | "sleeper";
  roster_id: number;
  team_name?: string | null;
  position: string;
  week: number | null;
  horizon_last_week?: number | null;
  lineup_value?: number | null;
  weakest: { slot: string; player: DPlayer; value: number | null; margin: number | null; replacement_name: string | null; replacement_value: number | null } | null;
  roster_context?: RosterContextSummary; // ---- IB-0
  moves: WaiverMove[];
  total_moves: number;
  cards: { title: string; add_sleeper_id: string; drop_sleeper_id: string | null; move_rank: number | null; move: WaiverMove }[];
  notice: string | null; // markdown: "Nothing beats what you have." …
  free_agents: FreeAgent[];
  as_of?: string | null;
  inputs_current?: boolean | null;
  on_current_lineup?: boolean | null;
  positions?: string[]; // requested: the positions the league starts (the free-agent tabs)
}

/** A player in a trade (G2's TradeContext.player). */
export interface TradePlayer extends DPlayer {
  sleeper_id: string;
  this_week: number | null;
  cannot_play: string | null;
  market_price: number | null;
  season_points: number | null;
  roster_id: number | null;
  goes_to?: string;
}

export interface LineupState {
  this_week: number;
  horizon: number;
  bench: number | null;
  by_week: number[];
}

export interface TradeSide {
  roster_id: number;
  team_name: string;
  gain_week: number;
  gain_horizon: number;
  cuts: { player: TradePlayer; horizon_loss: number; season_points: number | null }[];
  opened: number;
  limit: number;
}

export interface TradeEval {
  league_id: string;
  source: "database" | "sleeper";
  roster_id: number;
  partner: number;
  partner_team: string;
  week: number;
  weeks: number[];
  span: string; // "weeks 4–7"
  give: TradePlayer[];
  get: TradePlayer[];
  before: { mine: LineupState; theirs: LineupState };
  after: { mine: LineupState; theirs: LineupState };
  fit: { this_week: { mine: number; theirs: number }; next_4: { mine: number; theirs: number }; words: string };
  market: { give: number | null; get: number | null; unknown: string[]; replacement: Record<string, { season_points: number; player_name: string | null }>; words: string; players: TradePlayer[] };
  verdict: string;
  headline: string; // markdown: "**You give …; you get ….** <verdict>"
  ros: { give: number | null; get: number | null; window: string | null; words: string | null } | null;
  ranks?: { words: string | null } | null;
  size_words: string | null;
  sides: { mine: TradeSide; theirs: TradeSide };
  lineups: Record<"mine" | "theirs", { slots: { slot: string; player_name: string | null; gsis_id: string | null; value: number | null; change: number | null }[]; notes: string[]; closest_call: string | null }>;
}

export interface PartnerRow {
  partner: number;
  partner_team: string;
  shape: string;
  kind?: string;
  is_best: boolean;
  give: TradePlayer[];
  get: TradePlayer[];
  you_gain_week: number;
  you_gain_horizon: number;
  they_gain_week: number;
  they_gain_horizon: number;
  price_out: number | null;
  price_in: number | null;
}

export interface Partners {
  league_id: string;
  roster_id: number;
  want: string | null;
  week: number;
  span: string;
  partners: PartnerRow[];
  no_trade_with: string[];
  words: { headline: string | null };
}

/** Team Hub: mart_league_roster_value / _rankings / _slot_strength / _horizon for one roster (+ every roster's values). */
export interface TeamRosterRow extends DPlayer {
  role: "starter" | "bench" | "unplayable" | "empty";
  slot: string | null;
  slot_type: string | null;
  bench_rank: number | null;
  value: number | null;
  value_source: string | null;
  margin: number | null;
  is_locked: boolean | null;
  report_status: string | null;
  reason: string | null;
  acquired: string | null;
  acquired_how: string | null;
}

export interface TeamSlot {
  slot_type: string;
  slots: number;
  empty_slots: number | null;
  top: (DPlayer & { slot: string | null; value: number | null; is_locked: boolean | null }) | null;
  starter_strength: number | null;
  replacement_name: string | null;
  replacement_value: number | null;
  league?: { avg: number | null; best: number | null; rank: number | null; n: number }; // requested
}

export interface TeamRank {
  value: number;
  league_rank: number;
  n_rosters: number;
  horizon: string;
  rank_label: string;
}

export interface Team {
  league_id: string;
  source: "database" | "sleeper";
  roster_id: number;
  team_name: string;
  manager_name: string | null;
  week: number;
  roster_context?: RosterContextSummary; // ---- IB-0
  value: {
    week: number;
    horizon_weeks: number;
    week_label: string;
    horizon_label: string;
    lineup_value: number;
    bench_value: number;
    horizon_value: number;
    empty_slots: string | null;
    n_unvalued: number | null;
    n_locked: number | null;
    n_questionable: number | null;
    weakest_slot: string | null;
    weakest_margin: number | null;
    weakest_player_name: string | null;
    weakest_gsis_id: string | null;
    weakest_position: string | null;
    weakest_value: number | null;
    weakest_replacement_name: string | null;
    weakest_replacement_value: number | null;
    worst_week: number | null;
    worst_week_value: number | null;
  };
  ranks: Partial<Record<"lineup_value" | "horizon_value" | "bench_value", TeamRank>>;
  league: { roster_id: number; team_name: string; is_me: boolean; lineup_value: number; horizon_value: number; bench_value: number; lineup_value_rank: number }[];
  slot_strength: TeamSlot[];
  roster: TeamRosterRow[];
  weekly: { week: number; lineup_value: number | null; bench_value: number | null; league?: { median: number | null; best: number | null; rank: number | null; n: number } }[];
  season: { wins: number; losses: number; standing: number | null; all_play_win_pct?: number | null; luck_wins?: number | null; avg_bench_points_left?: number | null } | null;
  words: { lineup: string[]; horizon: string[] } | null;
}

export interface StandingRow {
  standing: number;
  roster_id: number;
  team_name: string;
  manager_name: string | null;
  wins: number;
  losses: number;
  ties: number | null;
  points_for: number | null;
  points_against: number | null;
}

export interface AllPlayRow {
  roster_id: number;
  team_name: string;
  wins: number;
  losses: number;
  all_play_wins: number;
  all_play_losses: number;
  all_play_win_pct: number | null;
  expected_wins: number | null;
  luck_wins: number | null;
}

export interface TransactionRow {
  created_at: string;
  week: number | null;
  transaction_id: string;
  transaction_type: string; // waiver / free_agent / trade / commissioner
  status: string;
  action: string; // add / drop
  roster_id: number | null;
  team_name: string | null;
  sleeper_player_id: string | null;
  gsis_id: string | null;
  player_name: string | null;
  position: string | null;
  team: string | null;
  headshot_url: string | null;
  waiver_bid: number | null;
}

export interface DraftPick {
  pick_no: number;
  round: number;
  draft_slot: number | null;
  roster_id: number | null;
  team_name: string | null;
  gsis_id: string | null;
  player_name: string | null;
  position: string | null;
  drafted_team: string | null;
  headshot_url?: string | null;
  is_keeper: boolean | null;
  position_rank_by_pick: number | null;
  position_rank_by_points: number | null;
}

export interface LeagueView {
  league_id: string;
  source: "database" | "sleeper";
  season: number;
  weeks_scored: number;
  standings: StandingRow[];
  all_play: AllPlayRow[];
  all_play_week: { week: number; roster_id: number; team_name: string; points: number; result: string | null; week_points_rank: number }[];
  profiles: { roster_id: number; team_name: string; total_bench_points_left: number | null }[] | null; // null: not on demand
  transactions: TransactionRow[];
  transactions_total?: number;
  draft: DraftPick[] | null;
  not_on_demand?: string | null;
  words: { headline: string | null } | null;
}

const encG4 = encodeURIComponent;
export const decisionPaths = {
  waivers: (league: string, team: number, position = "ALL") => `/api/waivers?league=${encG4(league)}&team=${team}&position=${encG4(position)}`,
  team: (league: string, team: number) => `/api/team?league=${encG4(league)}&team=${team}`,
  league: (league: string, team: number | null) => `/api/league?league=${encG4(league)}${team != null ? `&team=${team}` : ""}`,
  // "any position" is no `want` at all (G2 answers 400 to want=ALL)
  partners: (league: string, team: number, want = "ALL") =>
    `/api/trades/partners?league=${encG4(league)}&team=${team}${want === "ALL" ? "" : `&want=${encG4(want)}`}`,
  evaluate: () => "/api/trades/evaluate",
};

/** POST /api/trades/evaluate (not cached: a package is evaluated once per tap). */
export async function postEvaluate(body: { league: string; team: number; partner: number; give: string[]; get: string[] }): Promise<TradeEval> {
  trackTradeEvaluate(body); // ---- INF-1: GA `trade_evaluate` (the partner's number, the package's size; no names)
  const res = await fetch(decisionPaths.evaluate(), {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 401) throw new Unauthorized("sign in");
  if (!res.ok) {
    let detail = res.statusText;
    let body: unknown = null;
    try {
      const b = await res.json();
      body = b;
      detail = b.error ?? b.detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail, body); // ---- IE-0: the body carries `unavailable`
  }
  return (await res.json()) as TradeEval;
}

// ---- H1 (Wave H): the upside stash and buy low / sell high on /api/waivers; GET /api/about ---------------------------
/** One upside stash (mart_waiver_upside; on demand: the NFL-wide alert with its what-if priced in the league's scoring). */
export interface UpsideStash {
  rank: number | null;
  add: DPlayer;
  drop: DPlayer | null;
  base_value: number | null;
  scenario_value: number | null;
  points_gain: number | null;
  holds_weekly_gain: number | null; // null on demand (worked out each night for the house leagues)
  holds_horizon_gain: number | null;
  holds_slot: string | null;
  change_text: string | null;
  cause_text: string | null;
  since_week: number | null;
  games_held: number | null;
  kind: string | null;
  headline: string;
  lines: string[];
}

/** One row of the Trade Finder's buy-low / sell-high lists (roster_value.trade_candidates). */
export interface TradeListRow {
  player: DPlayer;
  roster_id: number | null; // buy low: his owner; sell high: the roster that gains most
  team_name: string | null;
  ppg: number | null;
  xppg: number | null;
  diff_per_game: number | null;
  gain_week: number | null;
  gain_horizon: number | null;
  loss_week: number | null;
  loss_horizon: number | null;
  fit_week: number | null;
  fit_horizon: number | null;
}

// declaration merging: the H1 fields of GET /api/waivers
export interface Waivers {
  upside?: { title: string; stashes: UpsideStash[]; why: string | null; howto: string[]; source?: string };
  trade_lists?: {
    buy_low: TradeListRow[];
    sell_high: TradeListRow[];
    best_buy_by_position?: Record<string, TradeListRow>;
    buy_line?: string;
    sell_line?: string;
    weeks?: string;
    howto?: string[];
    why?: string | null;
  };
}

export interface ImportanceFeature {
  rank: number;
  feature_label: string;
  importance: number | null;
}

export interface GradeNumbers {
  spearman: number | null;
  mae: number | null;
  coverage_80: number | null;
}

/** GET /api/about: the model, what it leans on most (mart_projection_importance), its grades (drift + backtest). */
export interface AboutAnswer {
  league_id: string;
  league_name: string;
  source: "database" | "sleeper";
  why?: string;
  rankings_howto?: string; // ---- IA-3 (PO merge): "How to read the rankings", the same text as /api/ros howto_rankings
  model: { answer: string; sections: { key: string; title: string; text: string }[] };
  importance: {
    model_version: string | null;
    eval_season: number;
    fit_seasons: string | null;
    scored_in: string | null;
    how_measured: string;
    unit: string;
    positions: { position: string; baseline_mae: number | null; top: string; lead: string; features: ImportanceFeature[] }[];
  } | null;
  grades: {
    scored_in: string | null;
    season: number | null;
    weeks: string | null;
    backtest_seasons: string | null;
    answer: string;
    howto: string[];
    positions: {
      position: string;
      season: GradeNumbers & { weeks_scored: number };
      backtest: GradeNumbers;
      by_season: (GradeNumbers & { season: number; weeks: number })[];
    }[];
  } | null;
}

export const aboutPath = (league: string) => `/api/about?league=${encodeURIComponent(league)}`;
// ---- end H1

// ---- IA-2 (Wave I-A): the trade calculator's window and interest dial, the partner finder's sanity bound, buy low /
// sell high on Trades (GET /api/trades/lists; no longer on /api/waivers). Additive: declaration merging + new helpers.
export type TradeWindow = "week" | "next4" | "ros" | "playoffs";

/** The dial: the other manager's interest 0–100 by our numbers over the window, the label, your gain. */
export interface Interest {
  score: number;
  label: EffectLabel; // IE-1: the effect on their starters (was "No deal" | "Maybe" | "Likely" | "Hard to say no")
  their_gain: number;
  you: number | null;
  caption: string; // "by our numbers over weeks 4–7"
}

export interface TradeEval {
  window?: TradeWindow;
  window_label?: string;
  window_why?: string;
  interest?: Interest;
  sanity?: string | null; // why the partner finder would not suggest this package (the market, rest of season), or null
  // fit.next_4 is the window's gain (its name before IA-2; fit.window on the API carries the same numbers)
}

export interface PartnerRow {
  interest?: Interest;
}

export interface Partners {
  window?: TradeWindow;
  window_label?: string;
  window_why?: string;
  weeks?: number[];
  rejected?: { partner_team: string; give: string[]; get: string[]; why: string }[];
  rejected_count?: number;
  sanity?: { ros_gap_share: number; market_share: number; ros_players: number; market_players: number; market_note: string | null;
    rule?: "season_value"; value_players?: number; words?: string }; // ---- IG-1: rule (a) on season value, said in words
}

/** GET /api/trades/lists: buy low / sell high (Wave H's lists, moved from /api/waivers). */
export type TradeLists = NonNullable<Waivers["trade_lists"]> & { league_id: string; roster_id: number; position: string };

export const tradePaths = {
  partners: (league: string, team: number, want = "ALL", window: TradeWindow = "next4") =>
    decisionPaths.partners(league, team, want) + (window === "next4" ? "" : `&window=${window}`),
  lists: (league: string, team: number) => `/api/trades/lists?league=${encodeURIComponent(league)}&team=${team}`,
};

/** POST /api/trades/evaluate over a window (next4, the default, is not sent: the body stays the G4 one). */
export function evaluateIn(body: { league: string; team: number; partner: number; give: string[]; get: string[] }, window: TradeWindow): Promise<TradeEval> {
  return postEvaluate(window === "next4" ? body : ({ ...body, window } as typeof body));
}
// ---- end IA-2

// ---- IA-3 (Wave I-A): the rankings' pieces, "why this number", the market line (GET /api/ros, /api/player, /api/my-week)
/** One piece of a projection: the stat, what it is worth in this league's scoring, said in words. */
export interface WhyPiece {
  stat: string; // "receptions" … or "rest" (bonuses / rounding: what a per-unit price cannot show)
  label: string;
  value: number | null;
  each: number | null; // points per unit in this league's scoring
  points: number;
  words: string; // "5.5 catches × 0.5 = +2.7"
}
/** The stat line × the league's scoring = the points (per game over the window on /api/ros, this week on the card). */
export interface Why {
  per: "game" | "week";
  points: number;
  pieces: WhyPiece[];
  sentence: string; // "8.9 targets → 5.5 catches → 96 yards → 0.48 TDs → 15.4 points per game × 12 games = 185"
  games: number | null;
  total: number | null;
}
export interface Market {
  market_points: number | null; // Sleeper's projection for the week, in this league's scoring
  ours: number | null;
  ratio: number | null;
  week: number | null;
  words: string | null; // "Sleeper has him at 16.2." + the gap in words when ours is under 70% / over 140% of it
  why: string | null; // why there is no market number
  far: boolean;
}
export interface LeansOn {
  features: string[];
  words: string; // About's sentence: "For WRs the model leans most on **…**. Next: *…* · *…*."
  scored_in: string | null;
}
export interface RosPlayer {
  player_key?: string | null; // a defense's Sleeper id (gsis_id null)
  headshot_url?: string | null;
  bye_weeks?: number[];
  ros_points_per_game?: number | null;
  per_game?: Record<string, number | null>; // the table's columns for his position (per game, projected)
  why?: Why | null;
  market_points?: number | null; // this week's
  week_points?: number | null; // this week's projection (ours), the market's comparison
  market_words?: string | null; // "Sleeper has him at 16.2." + the gap in words when far
}
export interface RosList {
  piece_columns?: Record<string, string[]>;
  leans_on?: Record<string, LeansOn>;
  market_week?: number | null;
  market_note?: string;
  howto_rankings?: string;
}
export interface LineupRow {
  market_points?: number | null; // Sleeper's number for the week (null where the market has none)
}
export interface PlayerCard {
  why?: Why | null;
  market?: Market | null;
  leans_on?: LeansOn | null;
}
// ---- end IA-3

// ---- IB-3 (Wave I-B): matchup meaning first (GET /api/matchups/defense, /api/matchups/cb): the tone, one rank
// direction (1 = the toughest for the offense), the rank in words, a cornerback call's certainty
export interface DefenseCell {
  n_ranked?: number | null; // defenses ranked at the position
  tough_rank?: number | null; // 1 = gives up the fewest (the toughest for the offense)
  tough_rank_l4?: number | null;
  tone?: "favorable" | "neutral" | "difficult" | null;
  rank_words?: string | null; // "gives up the 2nd-most points to running backs"
}
export interface DefenseMatrix {
  rank_note?: string;
}
export interface NamedCorner {
  name: string | null;
  slot: string | null; // LCB | RCB | NB
  side: string; // "left corner"
  rank: number | null; // 1 = the hardest to throw on
  label: string | null; // shutdown | solid | target (the mart's)
  words: string; // "the 17th-hardest of 74 starting corners to throw on" / "unranked: too few snaps to rank"
  tone: "favorable" | "neutral" | "difficult" | null;
}
export interface CbMatchup {
  tone?: "favorable" | "neutral" | "difficult" | null;
  certainty?: "likely" | "unclear" | "no call" | null;
  certainty_words?: string | null; // "likely: 47% of his targets go to that side, 29% to the other"
  cover_rank_words?: string | null;
  named_corners?: NamedCorner[];
  history?: string | null; // "11 catches for 137 yards on 11 targets with Turner on the field (2023–25)."
}
// ---- end IB-3

// ---- IB-3 (Wave I-B): "Value to my lineup" (GET /api/ros?view=lineup&team=&who=)
export interface RosPlayer {
  lineup_points?: number | null; // what he adds to (yours: what you lose without him in) your best lineup, the weeks left
  lineup_weeks?: number | null; // the weeks he starts (or would) for you
  lineup_kind?: "mine" | "fa" | "others" | null;
  lineup_why?: string | null; // "Your QB2 only plays in week 7: 16 points over your next-best there."
  lineup_rank?: number | null;
}
export interface RosList {
  view?: "points" | "lineup" | "outlook" | "upgrades" | "projections"; // ---- II-4: the three named Season views
  team?: number;
  who?: string;
  window?: { first: number | null; last: number | null; weeks: number; span: string | null };
  lineup_note?: string;
}
// ---- end IB-3

// ---- IB-2 (Wave I-B): Waivers short — GET /api/waivers' `top3` (the three strongest moves, one reason each), the views
// (Help now · Bye coverage · Stashes · All available; one answer carries them all: the chips switch without a request),
// and on every move whose drop starts this week or next: `drop_starts` + `keep_alternative` (the best claim that keeps
// him, or the line that none does). Additive: declaration merging.
export type WaiverView = "help" | "bye" | "stash" | "all";

/** One claim as the screen shows it: the move, one reason (a fact: the role, the bye, the slot), the claim's cost. */
export interface WaiverCard {
  move: WaiverMove;
  reason: string;
  cost: string;
  gain: number | null; // the lineup gain over the horizon (gain_label: "weeks 4–7")
  gain_label: string;
  this_week: number | null;
  week_gain?: number | null; // Bye coverage: the gain in the bye week (week_gain_label: "week 5")
  week_gain_label?: string;
}

export interface WaiverViews {
  help: { label: string; line: string | null; moves: WaiverCard[] };
  bye: { label: string; line: string | null; week: number | null; on_bye: string[]; empty_slots: string[]; moves: WaiverCard[] };
  stash: { label: string; count: number };
  all: { label: string; count: number };
}

export interface WaiverMove {
  drop_starts?: { weeks: number[]; slot: string | null; text: string } | null;
  keep_alternative?: {
    move: { add: DPlayer; drop: (DPlayer & { player_name: string | null }) | null; weekly_gain: number | null; horizon_gain: number | null } | null;
    line: string;
  } | null;
}

export interface Waivers {
  top3?: WaiverCard[];
  views?: WaiverViews;
  default_view?: WaiverView;
}
// ---- end IB-2

// ---- IC-4 (Wave I-D): the team units and the double header, finished (INTERFACES.md § IC-4). Additive: declaration
// merging. A unit's rest-of-season row (`unit`, the player its weeks are priced from); the Team Hub names a unit with
// its team (`short_name` "Bengals QB", the badge); the League screen's matchups (each game once; both games of a
// double header) and each team-week's games.
export interface RosPlayer {
  unit?: boolean;
  priced_from?: { gsis_id: string | null; player_name: string | null } | null;
  priced_from_words?: string | null; // "Priced from Joe Burrow's line (the team's starting QB each week)"
}
export interface DPlayer {
  unit?: boolean;
  short_name?: string | null;
}
export interface TeamSlot {
  replacement_short?: string | null;
}
export interface MatchupSide {
  roster_id: number;
  team_name: string | null;
  points: number | null; // null before the games
  result: "W" | "L" | "T" | null;
  live?: number | null; // ---- IL-2: this week's score so far (the platform's live points; MFL's live scoring); null before any
}
export interface WeekMatchups {
  week: number;
  played: boolean;
  double_header: boolean;
  games: { matchup_id: number; a: MatchupSide; b: MatchupSide; mine: boolean }[];
}
export interface LeagueView {
  matchups?: WeekMatchups[]; // this week's (not played yet) and the last scored week's
}
// ---- end IC-4

// ---- N1 (Wave I-D): the news line on the card — ESPN's latest headlines for him (api/league_lab_api/news.py): at most
// 3, newest first, none older than 14 days; [] when there is none or the feed is off / out. Only the headline is sent.
export interface NewsItem {
  headline: string;
  date: string; // ISO UTC, ESPN's `published` (PlayerWire: the brief's `published_at`)
  source: string; // "RotoWire via ESPN" | "ESPN" | "<publisher> via PlayerWire"
  url: string; // https, an espn.com page (the story, or his ESPN player page); PlayerWire: the brief's first evidence link
  // ---- N2: PlayerWire's hand-reviewed briefs come first (api/league_lab_api/playerwire.py); ESPN fills the rest
  kind?: "playerwire" | "espn";
  summary?: string | null; // PlayerWire only: the brief's news text
  verification?: "official" | "reported" | "corroborated" | "disputed" | null; // PlayerWire only
  related?: boolean; // PlayerWire only: he is named in the brief, not its subject
}
export interface PlayerCard {
  news?: NewsItem[];
}
// ---- end N1

// ---- IE-0 (Wave I-E): the trade calculator's asset keys (INTERFACES.md § IE-0). A key is opaque ("mfl:0682" like
// "12490"); POST /api/trades/evaluate answers 400 with every asset it cannot analyse named — never a silent drop.
export interface UnavailableAsset {
  key: string;
  side: "give" | "get";
  name: string | null;
  why: string; // "not on Big Mac Attack's roster", "not a player League Lab knows in this league", …
}
/** The `unavailable` list of a 400 from the evaluate call, or [] for any other error. */
export function unavailableOf(e: unknown): UnavailableAsset[] {
  if (!(e instanceof ApiError) || e.status !== 400) return [];
  const b = e.body as { unavailable?: UnavailableAsset[] } | null;
  return Array.isArray(b?.unavailable) ? b.unavailable : [];
}
// ---- end IE-0

// ---- IE-2 (Wave I-E): the trade explained through the starting lineup (POST /api/trades/evaluate, decisions.trade_story):
// who enters your starters and who leaves — by membership, a starter who only changes slot number is in neither list —,
// the required cut, the backup coverage, the other side in the same words, the window named and the comparison with
// standing pat / the best free agent for the same need. `lineups.<side>` gains the starters who left (`out`), the slot
// moves (`reshuffled`, detail only) and the total; a slot row's `change` is the player's own (null: he only moved slot).
export interface StarterMove {
  player: TradePlayer;
  slot: string; // "WR/TE", "team QB" (the league's words, unnumbered)
  value: number; // this week's projected points
  how?: "trade" | "bench";
  why?: "traded" | "cut" | "to the bench";
}
export interface TradeLineupX {
  slots: { slot: string; player_name: string | null; gsis_id: string | null; value: number | null; change: number | null; status?: "new" | "in" | null }[];
  notes: string[];
  closest_call: string | null;
  out?: { slot: string; player_name: string; gsis_id: string | null; value: number; change: number; why: string }[];
  reshuffled?: string[];
  total?: { before: number; after: number; change: number };
}
export interface TradeEval {
  starters_in?: StarterMove[];
  starters_out?: StarterMove[];
  cut?: { player: TradePlayer; season_points: number | null; words: string }[];
  effect_words?: string;
  lineup_words?: string;
  backup_words?: string | null;
  their_change?: { gain_week: number; gain_window: number; starters_in: StarterMove[]; starters_out: StarterMove[]; effect_words: string; lineup_words: string };
  window_words?: string;
  hold_words?: string;
  hold?: { hold: string; waiver: string | null; waiver_gain: number | null };
  how?: { fit: string | null; market: string | null; ros: string | null; size: string | null; ranks: string | null };
}
// ---- end IE-2

// ---- IE-1 (Wave I-E, the casual-user review): My Week's actions (at most three, the most urgent first; INTERFACES.md
// § IE-1), the cards' keys and tiebreaker, Waivers' this-week-first card fields and `home_action`, the dial as the effect
// on their starters, the Finder's cheaper package. Additive: declaration merging.
export type EffectLabel = "Makes their lineup weaker" | "About even" | "Improves their lineup" | "Improves it a lot";
export type ActionKind = "change" | "close" | "move";
export interface ActionPlayer {
  key: string | null;
  name: string;
  link?: string;
}
export interface WeekAction {
  kind: ActionKind;
  urgency: 1 | 2 | 3;
  slots: (string | null)[];
  slot_label: string;
  action: string; // markdown: the action in one sentence (layer 1)
  reason: string; // why, who moves, what could change it (layer 2)
  start: ActionPlayer[];
  sit: ActionPlayer[];
  submitted: boolean | null; // the suggested starters are already in the submitted lineup (null: unknown)
  submitted_words: string | null;
  lock: { kickoff: string; words: string } | null; // "before Sun 1:00 PM ET"
  cards: number[]; // indexes into MyWeek.cards: the analysis behind "Why?" (layer 3)
  gain: number | null;
  href: string | null; // "/waivers" for a claim
  drop?: ActionPlayer | null; // a claim's drop
}
export interface MyWeek {
  actions?: WeekAction[];
  set_line?: string | null;
  next_lock?: { kickoff: string; words: string; players: string[] } | null;
  edit_link?: { label: string; url: string; platform: string } | null;
  nothing_submitted?: string;
  platform_name?: string;
}
export interface DecisionCard {
  key?: string | null;
  alt_key?: string | null;
  tiebreak?: { kind: string; pick: string; side: "me" | "alt" } | null;
  action?: number | null;
}
export interface WaiverCard {
  lead?: string; // "Bears defense instead of Jaguars: about 2 more starter points this week"
  total_words?: string | null; // "+12.4 over weeks 4–7 in total"
  alternative_to?: string | null; // an earlier card that takes the same spot this week
}
export interface Waivers {
  answer?: string | null;
  not_additive?: string;
  home_action?: WeekAction | null;
}
export interface Interest {
  title?: string; // "Effect on their starters"
  need?: string | null; // "fills their empty RB2"
}
export interface PartnerRow {
  optional?: { sleeper_id: string; player_name: string; season_points: number | null; words: string } | null;
  cheaper_than?: { give: string[]; words: string } | null;
}
// ---- end IE-1

// ---- IF-1 (Wave I-F): the drop's cost in pieces, the net gain, one alternative drop and why; "no worthwhile move";
// stashes stay a watchlist (INTERFACES.md § IF-1). Additive: declaration merging.
export interface DropCost {
  lineup_loss: number | null;
  depth_lost: number | null;
  future_starts: number | null;
  future_start_weeks: number | null;
  season_value: number | null;
  season_points: number | null;
  replacement_points: number | null;
  upside: number | null;
  cost: number | null;
  piece: "lineup_loss" | "season_value" | "future_starts" | "depth_lost" | "upside" | null;
  is_incumbent?: boolean | null;
}

export interface WaiverMove {
  drop_cost?: DropCost | null;
  net_weekly_gain?: number | null;
  net_horizon_gain?: number | null;
  is_worthwhile?: boolean | null;
  drop_why?: string | null;
  alternative_drop?: { player: DPlayer; cost: number | null; piece: string | null; net_horizon_gain: number | null; words: string | null } | null;
}

export interface Waivers {
  no_worthwhile_move?: { words: string; best_net_week: number; best_net_horizon: number; add: string | null; drop: string | null } | null;
}

export interface UpsideStash {
  stash_action?: "claim" | "watch";
  watch_words?: string | null;
  drop_cost?: (Partial<DropCost> & { cost: number | null }) | null;
}
// ---- end IF-1

// ---- IF-3 (Wave I-F, the decision-quality review § Priority 1): the matchup evidence object (research.matchup_evidence)
// on /api/compare (`a` / `b`), the player card (`matchup_evidence`) and /api/matchups/cb rows (receivers only). Three
// parts kept apart — the history, what changed in the defense's corners, the implication — plus the forecast's treatment
// ("contextual only; not in the forecast": the projection has no opponent-personnel input) and the two sentences.
export interface EvidencePerson {
  gsis_id: string;
  name: string;
}
export interface MatchupEvidence {
  gsis_id: string;
  player_name: string;
  position: string;
  season: number;
  week: number;
  opponent: string;
  opponent_name: string;
  is_home: boolean | null;
  history: {
    rank_most: number | null; // 1 = gives up the most
    tough_rank: number | null; // 1 = gives up the fewest
    n: number | null;
    words: string | null; // "gives up the 2nd-fewest points to receivers"
    games: number | null;
    period: string | null; // "2026, weeks 1–3"
    points_allowed_pg: number | null;
    scoring: string;
    adjusted: boolean;
    adjusted_words: string;
    adjusted_rank: { rank_most: number | null; n: number | null; words: string | null; scoring: string } | null;
  };
  changed: {
    kind: "changed" | "same" | "unknown" | "not_checked";
    depth_chart_at: string | null;
    regulars: (EvidencePerson & { share: number; coverage_snaps: number; games: number })[];
    listed: (EvidencePerson & { slot: string })[];
    missing: (EvidencePerson & {
      status: string | null;
      code: string | null;
      source: string | null;
      as_of: string | null;
      date_words?: string | null;
      note: string | null;
      reason: "status" | "depth chart";
    })[];
    expected: (EvidencePerson & { slot: string; replaces: string | null; is_new: boolean; rank: number | null; rank_words?: string })[];
    words: string | null;
  };
  implication: { kind: "less_representative" | "stands" | "unknown" | "unchecked"; words: string };
  forecast_treatment: { kind: "contextual"; words: string; detail: string; features: string[] };
  matchup_uncertain: boolean;
  caveat: string | null;
  sentences: string[];
}
export interface CompareSide {
  matchup_evidence?: MatchupEvidence | null;
}
export interface Compare {
  verdict?: string;
}
export interface PlayerCard {
  matchup_evidence?: MatchupEvidence | null;
}
export interface CbMatchup {
  matchup_evidence?: MatchupEvidence | null;
}
// ---- end IF-3

// ---- IF-2 (Wave I-F, the decision-quality review § Priority 3): trades compete with the simpler alternatives — the
// ladder (standing pat, the best legal waiver move, the trade) over the same weeks; each trade's starter points beyond
// the best alternative; the week strip for both sides; the value concepts named and kept apart. Additive.
export interface TradeAlternative {
  kind: "waiver" | "stand_pat";
  player: { sleeper_id: string; gsis_id: string | null; player_name: string; position: string | null } | null;
  drop: { sleeper_id: string; gsis_id: string | null; player_name: string; position: string | null } | null;
  open_spot: boolean;
  gain_week: number;
  gain_window: number; // net of the drop's cost when IF-1's move is the source
  by_week: number[];
  weeks: number[];
  span: string;
  words: string; // "the Atlanta Falcons defense claim gives +12.8 over weeks 4–7 for an open spot"
  source: string;
}
export interface WeekStrip {
  weeks: number[];
  mine: number[]; // your starter points gained per week
  theirs: number[];
}
export interface VersusAlternative {
  beyond_alternative?: number; // your starter points over the window minus the best alternative's
  beats_alternative?: boolean;
  alternative_words?: string;
  other_objective?: { kind: "this_week" | "season_value" | "depth"; words: string } | null;
  strip?: WeekStrip;
}
export interface ValueConcept {
  label: string;
  words: string | null;
  fairness?: boolean;
}
export interface PartnerRow extends VersusAlternative {
  rank?: number;
  demoted?: boolean;
}
export interface Partners {
  best_alternative?: TradeAlternative;
  alternatives?: TradeAlternative[];
  ordering?: { key: string; words: string };
}
export interface TradeEval extends VersusAlternative {
  alternative?: TradeAlternative;
  values?: {
    projected_points: ValueConcept;
    starter_points: ValueConcept & { mine: number; theirs: number };
    depth: ValueConcept & { mine: { before: number | null; after: number | null }; theirs: { before: number | null; after: number | null } };
    season_value: ValueConcept & { give: number | null; get: number | null; unknown: string[] };
    ros_points: ValueConcept & { give: number | null; get: number | null; window: string | null };
  };
}
// ---- end IF-2

// ---- IF-4 (Wave I-F, the decision-quality review § Priority 4): My Week's "Decisions worth reviewing" (a close call the
// submitted lineup already follows: "No clear upgrade") and "What changed" (INTERFACES.md § IF-4). Additive.
export interface ReviewPlayer {
  key: string;
  name: string;
  link: string;
  gsis_id: string | null;
  value: number | null;
}
export interface ReviewLine {
  kind: "no_clear_upgrade";
  slot: string | null;
  slot_label: string;
  start: ReviewPlayer; // the one the submitted lineup starts (ours when unknown)
  other: ReviewPlayer;
  margin: number | null;
  strength: string;
  matchup_uncertain: boolean;
  words: string; // markdown: "Williams or Tuten at FLEX: a coin flip, 0.2 points apart; your lineup has Tuten — no clear upgrade."
  submitted: boolean | null;
  compare: { a: string; b: string } | null;
  cards: number[];
}
export interface ChangedLine {
  kind: "status" | "news";
  gsis_id: string | null;
  player_name?: string | null;
  text: string;
  source: string | null;
  at: string | null;
  url: string | null;
  about?: "player" | "league";
}
export interface MyWeek {
  review?: ReviewLine[];
  changed?: { lines: ChangedLine[]; empty: string };
}
export interface DecisionCard {
  matchup_uncertain?: boolean;
}
export interface NewsItem {
  about?: "player" | "league"; // the item about him first; "league" = an article-level headline (labelled)
}
export interface Status {
  updated_at?: string | null; // the newest load of the data the screens read (ISO UTC)
}
export interface ScheduleRow {
  week: number;
  opponent: string | null; // null = bye
  is_home: boolean | null;
  opp_rank: number | null; // 1 = gives up the most to his position
  proj: number | null; // the rest-of-season board's number for that week (null = none: unknown, not 0)
}
export interface LineupRow {
  margin_vs?: string | null; // the bench player who would come in for him
  margin_words?: string; // "over Lloyd" / "no eligible reserve: the slot would be empty" / "" (no margin)
}
export interface PlayerCard {
  schedule?: ScheduleRow[];
  games_played?: number | null;
}
// ---- end IF-4

// ---- M4 (Wave I-G): how the record's weeks were priced (GET /api/record `pricing`; INTERFACES.md § M4): `flat` = a
// bonus counted only when the projected line reaches it, `ev` = at its odds; `sentence` is About's one line (null when
// every week is flat and so is now — a league without a bonus to price)
export interface RecordPricing {
  now: "flat" | "ev";
  by_week: Record<string, "flat" | "ev" | "mixed">;
  sentence: string | null;
}
export interface RecordAnswer {
  pricing?: RecordPricing;
}
export interface RecordRow {
  pricing?: "flat" | "ev" | "mixed" | null;
}
// ---- end M4

// ---- IG-1 (Wave I-G): unknown is not zero (INTERFACES.md § IG-1). A player with no projection row is sent with
// `value: null` and `no_projection: true` (never 0); My Week says how many starters its total counts at 0.
export interface LineupRow {
  no_projection?: boolean;
}
export interface MyWeek {
  n_unvalued?: number;
  unvalued_words?: string | null;
}
export interface TeamRosterRow {
  no_projection?: boolean;
}
// ---- end IG-1

// ---- IG-3 (Wave I-G): the waiver deadline on Waivers; MFL's roster freshness on My Week; the MFL grade's
// qualification next to the headline grade on About (INTERFACES.md § IG-3)
export interface WaiverDeadline {
  platform: "sleeper" | "mfl";
  kind: string | null; // rolling | reverse_standings | faab | fcfs | blind_bid | blind_bid_fcfs | waiver_order | none
  kind_words: string | null;
  daily: boolean | null;
  runs_at: string | null; // the next time claims run (ISO UTC); null: the platform does not say (MFL)
  runs_words: string | null; // "Wednesday 3:00 AM ET" / "every day at 5:00 AM ET"
  clear_days: number | null;
  lock: { kickoff: string; words: string } | null; // the week's next kickoff not yet played
  words: string; // the one line under the title
  source: string;
}
export interface Waivers {
  deadline?: WaiverDeadline | null;
}
export interface MyWeek {
  roster_updated_at?: string | null; // MFL: when the rosters export was read from MyFantasyLeague (ISO UTC)
  roster_source?: string | null; // "MFL"
}
export interface AboutAnswer {
  grade_note?: string | null; // the qualification shown right under the headline grade (a league we do not score)
}
// ---- end IG-3

// ---- IH-1 (Wave I-H): the stale state (/api/status `nightly`; league_lab/freshness.py) and a retry that really asks
// again (INTERFACES.md § IH-1)
export interface Nightly {
  as_of: string | null; // the newest projections' fit (ISO); null = unknown
  age_hours: number | null;
  stale: boolean | null; // true: older than limit_hours (a missed morning update); null: unknown
  limit_hours: number; // 30
  words: string | null; // the banner's sentence when stale, else null
}
export interface Status {
  nightly?: Nightly;
}
/** Forget a path's cached answer and its request in flight, so the next get() asks the server again (a retry). */
export function forget(path: string): void {
  cache.delete(path);
  inflight.delete(path);
}
// ---- end IH-1

// ---- IH-2 (Wave I-H): the Team page's MFL roster freshness (the same fields as My Week's); which days daily waivers
// run (INTERFACES.md § IH-2)
export interface Team {
  roster_updated_at?: string | null; // MFL: when the rosters export was read from MyFantasyLeague (ISO UTC)
  roster_source?: string | null; // "MFL"
}
export interface WaiverDeadline {
  days?: string[] | null; // the days daily waivers run (Monday first) when they skip a day; null: every day / weekly
  days_mask?: number | null; // Sleeper's raw daily_waivers_days
}
// ---- end IH-2

// ---- IH-3 (Wave I-H): the week's win probability on My Week (INTERFACES.md § IH-3) — information, never a pick: the
// cards decide the lineup on expected points; this line only describes the matchup
export interface WinProbability {
  opponent_roster_id: number | null;
  p: number | null; // calibrated P(my starters outscore theirs); null: no range for this league yet / live scores unread
  percent: number | null; // whole percent, 1–99
  words: string | null; // "a coin flip" | "a slight favorite" | "a clear favorite" | "a slight underdog" | "a clear underdog"
  side: "favorite" | "underdog" | "even" | null;
  line: string | null; // "You're a slight favorite this week: 58%, 121 to 117 expected."
  note: string | null; // why there is no number ("no range for this league yet")
  assumptions?: string; // "assuming the players' weeks are independent except teammates and opponents"
  early: boolean;
  mine?: number | null; // expected totals: the lineups' projections, actual points where the game is in
  theirs?: number | null;
  n_played?: number;
  n_starters?: number;
  opp_n_played?: number;
  opp_n_starters?: number;
  played_words?: string | null; // "2 of your 9 have played, 3 of theirs"
  also?: WinProbability[]; // a double header's other game(s)
}
export interface MyWeek {
  win?: WinProbability | null;
}
/** /api/league/week-odds: this week's games with both teams' chance (asked after the League screen shows) */
export interface WeekOddsSide {
  roster_id: number;
  team_name: string | null;
  percent?: number; // whole percent; the two sides add to 100
  expected?: number; // the best lineup's projection (actual points where the game is in)
  n_played?: number;
}
export interface WeekOddsGame {
  matchup_id: number;
  a: WeekOddsSide;
  b: WeekOddsSide;
  p: number | null; // a's chance
  words: string | null; // "a coin flip" | "a slight favorite" | "a clear favorite" (the favourite's side)
  favorite?: number | null;
  note: string | null;
}
export interface WeekOdds {
  league_id: string;
  season: number;
  week: number | null;
  games: WeekOddsGame[];
  assumptions: string;
  note: string | null;
}
export const weekOddsPath = (league: string) => `/api/league/week-odds?league=${encodeURIComponent(league)}`;
// ---- end IH-3

// ---- II-0 (Wave I-I): strength by slot, one metric over one population (GET /api/team `strength_by_slot`; INTERFACES.md
// § II-0) and the partner row's story (the words from the row's own numbers)
export interface SlotLeague {
  avg: number | null;
  best: number | null;
  worst: number | null;
  rank: number | null; // 1 = best
  n: number;
  n_empty?: number;
}
export interface StrengthSlot {
  slot: string; // "RB1", "RB2", "FLEX1", "QB"
  slot_type: string;
  slot_order: number | null;
  player: (DPlayer & { unit?: boolean; short_name?: string | null }) | null; // null: an empty slot
  value: number | null; // projected points; 0 for an empty slot; null = no projection (unknown, not 0)
  empty: boolean;
  unvalued: boolean;
  is_locked: boolean;
  league: SlotLeague;
}
export interface StrengthBySlot {
  metric: "projected_points";
  metric_words: string;
  week: number | null;
  n_rosters: number;
  population: string;
  slots: StrengthSlot[];
  groups: { slot_type: string; slots: number; total: number | null; n_unvalued: number; league: SlotLeague }[];
  depth: { usable: number | null; raw_bench: number; league: SlotLeague; words: string | null };
  words: string;
}
export interface Team {
  strength_by_slot?: StrengthBySlot | null;
}
export interface WeekStory {
  this_week: { week: number | null; change: number | null; kind: "gain" | "loss" | "none" | "unknown" };
  window: { change: number | null; kind: "gain" | "loss" | "none" | "unknown" };
  by_week: { week: number; change: number | null }[];
  words: string;
}
export interface PartnerRow {
  story?: WeekStory | null;
}
// ---- end II-0

// ---- II-1 (Wave I-I, the product and analytics handoff § 2): the trade card and the Finder's threshold (INTERFACES.md
// § II-1). Every Finder row and the calculator's answer carry `card`; the Finder carries `verdict` ("No compelling trade
// found" with the reason when no trade passes) and each row's `tier` (credible / explore). No probability anywhere.
export interface CardAlternative extends TradeAlternative {
  covered_window: number | null; // the claim's gain once empty slots are filled from the free pool (the card's frame)
  covered_week: number | null;
  covered_by_week: number[] | null;
  availability: "guaranteed" | "claim";
  availability_words: string;
}
export interface CardEffect {
  this_week: number;
  window: number;
  by_week: number[];
  raw_window: number | null; // the same gain with an empty slot left empty (the old number)
  words: string;
}
export interface TradeCard {
  give: TradePlayer[];
  get: TradePlayer[];
  partner: number;
  drops: { mine: { player: TradePlayer; words: string }[]; theirs: { player: TradePlayer; words: string }[] };
  your_effect: CardEffect;
  their_effect: CardEffect;
  depth_cost: { mine: string | null; theirs: string | null; roster_spots: number; season_value: { give: number | null; get: number | null }; horizon: string | null };
  waiver_alternative: { mine: CardAlternative; theirs: CardAlternative; words: string };
  beyond: { mine: number; theirs: number; margin: number };
  why_consider: string[];
  why_refuse: string[];
  plausibility: { key: "plausible" | "roster_fit" | "implausible"; label: string; reasons: string[] };
  guardrails: { rule: string; words: string }[];
  legal: { ok: boolean; notes: string[]; checks: string[] };
  credible: boolean;
}
export interface PartnerRow {
  card?: TradeCard;
  tier?: "credible" | "explore";
}
export interface Partners {
  verdict?: { kind: "compelling" | "none"; headline: string | null; reason: string | null };
  credible_count?: number;
  explore_count?: number;
  margin?: number;
}
export interface TradeEval {
  card?: TradeCard;
}
// ---- end II-1

// ---- II-3: the Stats Explorer (GET /api/players?window=…; api/league_lab_api/stats.py). Unknown is null (never 0).
export type StatsStatus = "present" | "derived" | "planned" | "unavailable";
export interface StatsColumn {
  id: string;
  label: string; // "Target share"
  short: string; // "Tgt %"
  kind: "games" | "count" | "share" | "rate";
  format: "int" | "pct" | "dec1" | "dec2" | "pts";
  per_game: boolean; // a count with a `<id>_per_game` twin
  definition: string;
  numerator: string | null;
  denominator: string | null;
  aggregation: string | null;
  source: string;
  status: StatsStatus;
  available: boolean; // for the season asked (routes estimates need participation; first read needs charting)
  reason: string | null; // why a cell is —
  coverage?: string | null;
  positions: string[];
  group?: string; // ---- IM-2 (IM-1's shape): "Receiving", "Air yards", … — absent on older answers (the screen derives it)
}
export interface StatsPreset {
  key: "wrte" | "rb" | "qb";
  label: string;
  positions: string[];
  columns: string[];
  extra: string[];
  sort: string;
  full?: string[]; // ---- IM-2 (IM-1's shape): every column for the position, available, in catalogue order — absent on older answers
}
export interface StatsWindow {
  key: "season" | "last3" | "last5" | "weeks";
  basis: "games" | "weeks";
  n?: number;
  weeks: [number, number] | null;
  through_week: number | null;
  label: string;
  note?: string;
}
export interface StatsRow extends PlayerHead, Owned {
  games: number;
  first_week: number | null;
  last_week: number | null;
  points: number | null;
  points_per_game: number | null;
  [field: string]: unknown;
}
export interface StatsFrame {
  league_id: string;
  season: number;
  positions: string[];
  window: StatsWindow;
  total: number;
  players: StatsRow[];
  catalogue: StatsColumn[];
  presets: StatsPreset[];
  howto: string;
}
export const statsPath = (league: string, o: { position: string; window: string; basis?: string; weeks?: string; season?: number | null }) => {
  const qs = new URLSearchParams({ league, limit: "1000", position: o.position, window: o.window });
  if (o.basis) qs.set("basis", o.basis);
  if (o.weeks) qs.set("weeks", o.weeks);
  if (o.season) qs.set("season", String(o.season));
  return `/api/players?${qs.toString()}`;
};
// ---- IM-2: the same request as a file (GET /api/players.csv, IM-1): the Stats frame's parameters + the screen's
// filters, sort and columns (catalogue ids; `mode` says per game or totals). A 404 → the screen builds the file itself.
export const statsCsvPath = (
  league: string,
  o: { position: string; window: string; basis?: string; weeks?: string; season?: number | null; sort: string; dir: string; cols: string[]; mode: string; who?: string; team?: number | null; nfl?: string; q?: string; min?: number },
) => {
  const qs = new URLSearchParams({ league, limit: "1000", position: o.position, window: o.window, sort: o.sort, dir: o.dir, cols: o.cols.join(",") });
  if (o.mode === "game") qs.set("per_game", "1"); // PO (the merge): IM-1's route says per_game=1
  if (o.basis) qs.set("basis", o.basis);
  if (o.weeks) qs.set("weeks", o.weeks);
  if (o.season) qs.set("season", String(o.season));
  if (o.who && o.who !== "all") qs.set("who", o.who);
  if (o.team !== null && o.team !== undefined) qs.set("team", String(o.team));
  if (o.nfl) qs.set("nfl", o.nfl);
  if (o.q) qs.set("q", o.q);
  if (o.min && o.min > 1) qs.set("min_games", String(o.min));
  return `/api/players.csv?${qs.toString()}`;
};
// ---- end II-3

// ---- II-4 (Wave I-I): Season's three named views (GET /api/ros?view=outlook|upgrades|projections; INTERFACES.md
// § II-4), the news item's five parts on My Week's "What changed" lines, the home's three clocks. Additive.
export interface SeasonView {
  key: "outlook" | "upgrades" | "projections";
  label: string; // "My roster outlook" | "Potential upgrades" | "Rest-of-season projections"
  counterfactual: string; // the view's counterfactual, said once at the top
  costs_included: string[];
  costs_not_included: string[];
}
export interface RosList {
  season_view?: SeasonView;
}
export interface RosPlayer {
  lineup_start_weeks?: number[]; // the weeks he starts for you (outlook) / would (upgrades)
  cover?: { points: number; weeks: number; words: string } | null; // contingent injury cover — never in lineup_points
  acquire?: { kind: "add_drop" | "trade"; words: string; path: string } | null; // upgrades: where the cost is priced
  ros_per_game?: number | null; // projections: points per game over the games left
}
export type DecisionStatus = "changed" | "watch" | "none";
export type ForecastStatus = "included" | "contextual" | "pending";
export interface ChangedLine {
  what_changed?: { text: string; source: string | null; event_at: string | null; published_at: string | null; checked_at: string | null };
  why_here?: string;
  decision_status?: DecisionStatus;
  decision_words?: string;
  forecast_status?: ForecastStatus;
  forecast_words?: string;
  next_step?: { kind: "player" | "compare" | "matchup"; label: string; gsis_id: string | null };
  item_kind?: "development" | "recap";
  priority?: number;
}
export interface Clocks {
  data_built: string | null; // the morning build's newest data load (ISO UTC)
  injuries_checked: string | null; // the injury report's last check
  news: string | null; // the newest news item among What changed's lines
}
export interface MyWeek {
  clocks?: Clocks;
}
export interface NewsItem {
  forecast_status?: ForecastStatus; // the card's items: "contextual" (the projection reads no news)
  forecast_words?: string;
}
// ---- end II-4

// ---- IL-2 (Wave I-L): Waivers' "Recently added in this league" (every team's adds of the decision week and the week
// before, from the moves the League screen lists) and MFL's waiver order / blind-bid balance on the stamp line
export interface RecentAdd {
  week: number | null;
  transaction_type: string; // free_agent | waiver
  roster_id: number | null;
  team_name: string | null;
  player_name: string | null;
  position: string | null;
  gsis_id: string | null;
  waiver_bid: number | null;
  created_at: string | null;
  mine: boolean;
}
export interface RecentAdds {
  weeks: number[];
  rows: RecentAdd[];
  total: number;
  unavailable: string | null; // "Transactions: not available for … leagues yet" / "Recent adds: not read right now"
  source: string | null;
}
export interface Waivers {
  recent_adds?: RecentAdds | null;
}
export interface WaiverDeadline {
  budget_left?: number | null; // MFL blind bids: the team's balance when MFL's league export carries it
  waiver_order?: number | null; // MFL waiver order: the team's place
}
// ---- end IL-2

// ---- IN-3 (Wave I-N): matchups for everyone — GET /api/matchups/board?league=&position=&q=&game=&tone=&sort=&limit=&offset=
// (api/league_lab_api/matchup_board.py). `context` is matchup_board.matchup_context's shape (DFS and the home read it too).
export type MatchupTone = "favorable" | "neutral" | "difficult";
export interface MatchupContext {
  opponent: string;
  home: boolean | null;
  defense: { tone: MatchupTone | null; tough_rank: number | null; n_ranked: number | null; words: string | null };
  cb: {
    tone: MatchupTone | null;
    certainty: "likely" | "unclear" | "no call";
    corner: string | null;
    corner_rank: number | null;
    shutdown: boolean;
    words: string | null;
  } | null;
  tone: MatchupTone | null;
  words: string | null;
}
export interface BoardCorner {
  name: string | null;
  side: string | null;
  rank: number | null;
  label: string | null;
  words: string | null;
  tone: MatchupTone | null;
}
export interface BoardRow {
  gsis_id: string;
  player_name: string;
  position: string;
  team: string | null;
  headshot_url: string | null;
  report_status: string | null;
  opponent: string;
  is_home: boolean | null;
  kickoff_at: string | null;
  game_id: string;
  proj_points: number | null;
  p10: number | null;
  p25: number | null;
  p75: number | null;
  p90: number | null;
  rostered_by_roster_id?: number | null; // absent without a league (`ref:` keys)
  rostered_by_team?: string | null;
  context: MatchupContext;
  cb_detail: { n_ranked: number | null; certainty_words: string | null; history: string | null; named: BoardCorner[] } | null;
  matchup_evidence: MatchupEvidence | null;
}
export interface BoardGame {
  game_id: string;
  home: string;
  away: string;
  kickoff_at: string | null;
}
export interface MatchupBoard {
  league_id: string;
  league_name: string;
  season: number;
  week: number | null;
  position: string;
  q: string | null;
  game: string | null;
  tone: string | null;
  sort: string;
  limit: number;
  offset: number;
  scoring: string;
  projection_words: string;
  tone_words: string;
  position_note: string | null;
  rows: BoardRow[];
  total: number;
  games: BoardGame[];
  counts: Partial<Record<MatchupTone | "none", number>>;
  notice?: string;
}
export interface BoardQuery {
  position: string;
  q: string;
  game: string;
  tone: string;
  sort: string;
  offset: number;
  limit: number;
}
export const boardPath = (league: string, b: BoardQuery) => {
  const p = new URLSearchParams({ league, position: b.position, limit: String(b.limit), offset: String(b.offset) });
  if (b.q.trim().length >= 2) p.set("q", b.q.trim());
  if (b.game) p.set("game", b.game);
  if (b.tone) p.set("tone", b.tone);
  if (b.sort && b.sort !== "projection") p.set("sort", b.sort);
  return `/api/matchups/board?${p.toString()}`;
};
// ---- end IN-3

// ---- IN-2 (Wave I-N): the lab without a league — a player's value on a reference key (the card's `ref_value`, its
// foot line) and the trade calculator without a league (GET /api/trade-calc/free; api/league_lab_api/freetrade.py)
export interface RefPricing {
  fitted: boolean;
  reference: string | null;
  words: string;
}
export interface RefValue {
  value: number | null;
  ros_points: number | null;
  replacement: number;
  replacement_name: string | null;
  position: string;
  value_rank_pos: number;
  pos_rank: number | null;
  from_week: number | null;
  last_week: number | null;
  teams: number;
  superflex: boolean;
  bench: number;
  assumes: string;
  words: string | null;
  pricing: RefPricing;
}
export interface PlayerCard {
  ref_value?: RefValue | null;
  foot?: string | null;
  scoring?: { key: string; label: string; pricing: RefPricing } | null;
}
export interface FreeTradeOutlook {
  week: number | null;
  points: number | null;
  p10: number | null;
  p90: number | null;
  bye: boolean;
  per_game: number | null;
  games: number | null;
}
export interface FreeTradePlayer {
  gsis_id: string;
  player_name: string | null;
  position: string | null;
  team: string | null;
  value: number | null;
  ros_points: number | null;
  ros_p10?: number | null;
  ros_p90?: number | null;
  value_rank_pos?: number;
  pos_rank?: number | null;
  replacement?: number | null;
  outlook?: FreeTradeOutlook;
  no_projection: boolean;
  why?: string;
}
export interface FreeTradeSide {
  players: FreeTradePlayer[];
  n: number;
  value: number | null;
  ros_points: number | null;
  low: number | null;
  high: number | null;
  sd: number | null;
  unknown: string[];
}
export interface FreeTrade {
  league_id: string;
  league_name: string;
  assumes: string;
  value_words: string | null;
  pricing: RefPricing;
  window: { first: number | null; last: number | null; words: string | null };
  give: FreeTradeSide;
  get: FreeTradeSide;
  verdict: {
    even: boolean | null;
    lean: "give" | "get" | null;
    gap: number | null;
    low: number | null;
    high: number | null;
    one_player: { gsis_id: string; player_name: string; value: number; share: number; words: string } | null;
    words: string;
  };
  roster_spots: { you_get_back: number; replacement_points: number | null; replacement_position: string | null; replacement_name: string | null; words: string } | null;
  league_words: string;
  max_side: number;
}
export interface CompareSide {
  ros_value?: number | null; // a reference key only: the value without a league (refleague.compare_values)
}
export const freeTradePath = (league: string, give: string[], getIds: string[]) =>
  `/api/trade-calc/free?league=${encodeURIComponent(league)}&give=${encodeURIComponent(give.join(","))}&get=${encodeURIComponent(getIds.join(","))}`;
// ---- end IN-2

// ---- IN-1 (Wave I-N): the blog (GET /api/blog, /api/blog/{slug}; api/league_lab_api/blog.py) and the home's reads
export interface BlogMeta {
  slug: string;
  title: string;
  date: string; // YYYY-MM-DD
  summary: string;
  author: string;
  tags: string[];
  minutes: number;
  image: string | null; // "/blog/img/<name>" or null
  draft?: boolean; // only with LEAGUE_LAB_BLOG_DRAFTS=on
}
export interface BlogPost extends BlogMeta {
  markdown: string;
}
export const blogPaths = {
  list: (limit = 20) => `/api/blog?limit=${limit}`,
  post: (slug: string) => `/api/blog/${encodeURIComponent(slug)}`,
};
// the home reads IN-3's matchup board (MatchupBoard / BoardRow above) and hides its module when the route fails
export const homePaths = {
  board: (league: string, position: string, sort: string | null, limit: number) =>
    `/api/matchups/board?league=${encodeURIComponent(league)}&position=${position}${sort ? `&sort=${sort}` : ""}&limit=${limit}`,
  ros: (league: string, position: string, limit: number) => `/api/ros?league=${encodeURIComponent(league)}&position=${position}&limit=${limit}`,
};
// ---- end IN-1

// ---- IN-5 (Wave I-N): a starting spot nobody on the roster can fill is its own action (kind "change": a roster alert):
// `open_slot` says which spot and who cannot play; `href` is Waivers at that position, `href_label` the link's words
// ("Find a quarterback on Waivers"). Additive: declaration merging.
export interface OpenSlot {
  slot_type: string; // QB, TE, FLEX …
  slots: string[]; // the lineup's labels of the open spots of that type
  position: string | null; // the Waivers position (null: a flex — every free agent)
  words: string; // "quarterback"
  players: string[]; // the submitted lineup's players it takes over (roster keys)
  named: string[]; // every player of that position who cannot play (roster keys)
}
export interface WeekAction {
  open_slot?: OpenSlot | null;
  href_label?: string | null;
}
// ---- end IN-5

// ---- IN-6 (Wave I-N): the League screen's power rankings and the rest of the season (GET /api/league/outlook;
// api/league_lab_api/outlook.py, docs/METRICS.md § "Power rankings and the season outlook")
export interface PowerRow {
  roster_id: number;
  team_name: string;
  manager_name: string | null;
  rank: number; // by per_week, 1 = the most
  per_week: number; // the best lineup's expected points per week over the rest of the season
  wins: number;
  losses: number;
  ties: number;
  standing: number; // by wins, then points for
  points_for: number | null;
  points_for_rank: number | null;
  points_against: number | null;
  points_against_rank: number | null;
  gap_words: string | null; // "3–1 on the 8th-most points: a soft schedule so far"
  schedule_left: number | null; // the opponents left: their per_week, averaged
  schedule_left_rank: number | null; // 1 = the hardest
  schedule_left_games: number;
  mine: boolean;
}
export interface OutlookRow {
  roster_id: number;
  wins_mean: number; // the final regular-season wins, averaged over the simulated seasons
  wins_p10: number;
  wins_p90: number;
  games_left: number;
  wins_left_mean: number;
  points_for_mean: number;
  playoff: number | null; // null: the league's playoff rules are not known (playoff_reason)
  top_seed: number;
  bye: number | null; // null: no byes (or no playoff rules)
  rank_mean: number;
  status: "clinched" | "eliminated" | null; // proven on wins alone
  mine: boolean;
}
export interface LeagueOutlook {
  league_id: string;
  season: number;
  version: string;
  played_weeks: number;
  roster_id: number | null;
  power: { rows: PowerRow[]; weeks: number[]; span: string; words: string; note: string | null; movement: null; movement_note: string };
  outlook: {
    available: boolean;
    reason: string | null;
    weeks: number[];
    seasons: number;
    playoff_teams: number | null;
    playoff_week_start: number | null;
    byes: number | null;
    tiebreak: string;
    playoff_reason: string | null;
    assumptions: string[];
    rows: OutlookRow[];
  };
  definitions: Record<string, string>;
}
export const outlookPath = (league: string, team: number | null) =>
  `/api/league/outlook?league=${encodeURIComponent(league)}${team != null ? `&team=${team}` : ""}`;
// ---- end IN-6

// ---- IO-4 (Wave I-O): the matchup board's started games (`game_state` per row, `state` per game, `show` = "Still to
// play" / "All games") and where its defense rank comes from (the league's own scoring in a real league). Interfaces
// merge with IN-3's above.
export type GameState = "started" | "final" | null;
export type BoardShow = "to_play" | "all";
export interface BoardRow {
  game_state?: GameState;
}
export interface BoardGame {
  state?: GameState;
}
export interface MatchupBoard {
  show?: BoardShow;
  started_games?: number;
  started_players?: number;
  defense_source?: "league" | "reference";
}
export const boardShowPath = (path: string, show: string) => (show === "all" || show === "to_play" ? `${path}&show=${show}` : path);
// ---- end IO-4
// ---- IO-2 (Wave I-O): the outlook kept each week (movement from last week's stored ranking), the power part first, the
// League link (api/league_lab_api/outlook.py § IO-2, outlook_store.py)
export type PowerRowMoved = PowerRow & { moved?: number | null }; // places up (+) / down (−) since last week's kept ranking
export type OutlookRowMoved = OutlookRow & { playoff_change?: number | null; title?: number | null }; // points of percentage since then; title odds
export interface LeagueOutlookMoved extends Omit<LeagueOutlook, "power" | "outlook"> {
  league_name?: string | null;
  week?: number; // the week the ranking looks ahead from (the one it is kept for)
  shareable?: boolean; // anyone can read this league (Sleeper, MyFantasyLeague): a share link
  power: Omit<LeagueOutlook["power"], "rows" | "movement"> & { rows: PowerRowMoved[]; movement: { week: number; built_at: string } | null; kept?: string | null };
  outlook: Omit<LeagueOutlook["outlook"], "rows"> & {
    rows: OutlookRowMoved[];
    pending?: boolean;
    title?: boolean; // title odds: the bracket played out in every season (Sleeper, the bracket readable)
    title_reason?: string | null;
    bracket?: { rounds: number[][]; reseed: boolean } | null;
  };
}
export const outlookPowerPath = (league: string, team: number | null) => `${outlookPath(league, team)}&part=power`;
// ---- end IO-2
