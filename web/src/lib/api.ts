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
  const res = await fetch(decisionPaths.evaluate(), {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
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
  return (await res.json()) as TradeEval;
}
