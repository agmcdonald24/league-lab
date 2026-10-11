// ---- IM-2 (Wave I-M): the Stats table's columns — the groups, the two views ("Key stats" / "Full table"), how a cell
// reads (the value, the dash's reason, a small sample greyed) and the CSV built in the browser.
//
// IM-1 is adding `group` to every catalogue row and a `full` list to every preset of GET /api/players. Until an answer
// carries them, they are derived here: `GROUPS` names a group for every column of today's catalogue (a column the map
// does not know falls to a group by its id, then to "Other"), and "full" = every catalogue column whose `positions`
// include the position and whose `available` is true. When the answer carries them, the answer wins.
import type { StatsColumn, StatsPreset, StatsRow } from "../../lib/api";
import { fmt } from "../../lib/theme";

export type Mode = "game" | "total";
export type PosGroup = "wrte" | "rb" | "qb" | "all";

/** The group names (IM-1's list, docs/WORDS.md § "The Stats tables"). */
export const GROUP_NAMES = [
  "Games and points",
  "Receiving",
  "Rushing",
  "Passing",
  "Air yards",
  "Red zone",
  "Efficiency",
  "Expected points",
  "Next Gen Stats",
  "Charting",
  "Snaps and routes",
  "Role change", // ---- IO-4
  "Advanced (PFR)",
] as const;

/** The group of every column of today's catalogue (api/league_lab_api/stats.py CATALOGUE, main ab50682). */
export const GROUPS: Record<string, string> = {
  games: "Games and points",
  points: "Games and points",
  expected_points_per_game: "Expected points",
  targets: "Receiving",
  target_share: "Receiving",
  on_field_target_share: "Receiving", // ---- IX-1
  receptions: "Receiving",
  receiving_yards: "Receiving",
  receiving_tds: "Receiving",
  catch_rate: "Receiving",
  yards_per_target: "Receiving",
  yac_per_reception: "Receiving",
  air_yards_share: "Air yards",
  adot: "Air yards",
  red_zone_targets: "Red zone",
  red_zone_target_share: "Red zone",
  red_zone_carries: "Red zone",
  red_zone_carry_share: "Red zone",
  inside_5_carries: "Red zone",
  inside_5_carry_share: "Red zone",
  red_zone_opportunities: "Red zone",
  first_read_target_share: "Charting",
  catchable_rate: "Charting",
  charted_targets: "Charting",
  route_participation: "Snaps and routes",
  tprr_proxy: "Snaps and routes",
  yprr_proxy: "Snaps and routes",
  routes: "Snaps and routes",
  snap_share: "Snaps and routes",
  separation: "Next Gen Stats",
  yac_over_expected: "Next Gen Stats",
  ryoe_per_attempt: "Next Gen Stats",
  time_to_throw: "Next Gen Stats",
  ngs_cpoe: "Next Gen Stats",
  carries: "Rushing",
  carry_share: "Rushing",
  on_field_carry_share: "Rushing", // ---- IX-1
  rb_carry_share: "Rushing",
  rushing_yards: "Rushing",
  rushing_tds: "Rushing",
  yards_per_carry: "Rushing",
  attempts: "Passing",
  completions: "Passing",
  completion_rate: "Passing",
  passing_yards: "Passing",
  yards_per_attempt: "Passing",
  passing_tds: "Passing",
  passing_interceptions: "Passing",
  sacks_suffered: "Passing",
  dropbacks: "Passing",
  scrambles: "Passing",
  cpoe: "Passing",
  pressure_splits: "Passing",
  // ---- IO-4 (Wave I-O): the role change (DFS's role trend: his last 2 games against his games before them)
  target_share_change: "Role change",
  carry_share_change: "Role change",
  snap_share_change: "Role change",
};

// ---- IO-4: a share's change reads in signed points of share ("+5.2 pts"), never as a percent of a percent
export const SHARE_CHANGE = new Set(["target_share_change", "carry_share_change", "snap_share_change"]);
export const sharePts = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v * 100).toFixed(1)} pts`;

// a column neither the answer nor the map names: a group by its id (IM-1's new ids), else "Other" (last)
const BY_ID: [RegExp, string][] = [
  [/^pfr_|drop|broken_tackle|after_contact|pressure|bad_throw|on_target/, "Advanced (PFR)"],
  [/^ngs_|separation|cushion|aggressive|over_expected|time_to|box/, "Next Gen Stats"],
  [/epa|success|first_down|wopr|racr|_rate$|per_touch|per_reception|touchdown_rate/, "Efficiency"],
  [/expected|xfp|over_expected/, "Expected points"],
  [/red_zone|inside_(5|10)/, "Red zone"],
  [/air|adot|deep/, "Air yards"],
  [/snap|route/, "Snaps and routes"],
  [/charted|first_read|catchable/, "Charting"],
  [/pass|attempt|completion|sack|interception|dropback|scramble|cpoe/, "Passing"],
  [/rush|carr|ypc/, "Rushing"],
  [/target|recept|receiving|catch|yac/, "Receiving"],
];
export const OTHER = "Other";

export function groupOf(c: StatsColumn): string {
  if (c.group) return c.group;
  if (GROUPS[c.id]) return GROUPS[c.id];
  return BY_ID.find(([re]) => re.test(c.id))?.[1] ?? OTHER;
}

/** The order the groups read in for a position (the position's own stats first). */
const ORDER: Record<PosGroup, string[]> = {
  wrte: ["Games and points", "Receiving", "Air yards", "Red zone", "Efficiency", "Expected points", "Next Gen Stats", "Charting", "Snaps and routes", "Role change", "Advanced (PFR)", "Rushing", "Passing"],
  rb: ["Games and points", "Rushing", "Receiving", "Red zone", "Efficiency", "Expected points", "Next Gen Stats", "Snaps and routes", "Role change", "Advanced (PFR)", "Air yards", "Charting", "Passing"],
  qb: ["Games and points", "Passing", "Rushing", "Efficiency", "Expected points", "Next Gen Stats", "Advanced (PFR)", "Red zone", "Receiving", "Air yards", "Charting", "Snaps and routes", "Role change"],
  all: [...GROUP_NAMES],
};

/** The position's columns with each group together (a group header spans them), the groups in the position's order,
 * the given order kept inside a group (the catalogue's order). An unknown group goes after the known ones. */
export function arrange(cols: StatsColumn[], pos: PosGroup): StatsColumn[] {
  const order = ORDER[pos];
  const seen: string[] = [];
  for (const c of cols) {
    const g = groupOf(c);
    if (!seen.includes(g)) seen.push(g);
  }
  const rank = (g: string) => {
    const i = order.indexOf(g);
    return i >= 0 ? i : g === OTHER ? 1000 : 500 + seen.indexOf(g);
  };
  return cols
    .map((c, i) => ({ c, i, r: rank(groupOf(c)) }))
    .sort((a, b) => a.r - b.r || a.i - b.i)
    .map((x) => x.c);
}

/** "Full table": the preset's `full` list when the answer has one (IM-1), else every catalogue column that applies to
 * the positions and is available — in the catalogue's order, then grouped. */
export function fullColumns(catalogue: StatsColumn[], preset: StatsPreset | null, positions: string[], pos: PosGroup): StatsColumn[] {
  const byId = new Map(catalogue.map((c) => [c.id, c]));
  const listed = preset?.full;
  const cols = Array.isArray(listed)
    ? listed.map((id) => byId.get(id)).filter((c): c is StatsColumn => !!c && c.available !== false)
    : catalogue.filter((c) => c.available && (positions.length === 0 || c.positions.some((p) => positions.includes(p))));
  return arrange(cols, pos);
}

/** The groups as runs of adjacent columns (the second header row and the <colgroup>s). */
export function runs(cols: StatsColumn[]): { name: string; cols: StatsColumn[] }[] {
  const out: { name: string; cols: StatsColumn[] }[] = [];
  for (const c of cols) {
    const g = groupOf(c);
    const last = out[out.length - 1];
    if (last && last.name === g) last.cols.push(c);
    else out.push({ name: g, cols: [c] });
  }
  return out;
}

// ---- how a cell reads
export const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
export const field = (c: StatsColumn, mode: Mode) => (c.per_game && mode === "game" ? `${c.id}_per_game` : c.id);
export const head = (c: StatsColumn, mode: Mode) => (c.per_game && mode === "game" ? `${c.short}/G` : c.short);
export const title = (c: StatsColumn, mode: Mode) => (c.per_game && mode === "game" ? `${c.label} per game` : c.label);

export function show(c: StatsColumn, p: StatsRow, mode: Mode): string {
  if (c.unsplit) return "—"; // ---- IX-3: never the all-plays number under a situation
  const v = num(p[field(c, mode)]);
  if (v === null) return "—";
  if (SHARE_CHANGE.has(c.id)) return sharePts(v); // ---- IO-4
  if (c.format === "pct") return fmt.pct(v, 1);
  if (c.format === "pts" || c.format === "dec1") return fmt.pts(v, 1);
  if (c.format === "dec2") return fmt.pts(v, 2);
  return c.per_game && mode === "game" ? fmt.pts(v, 1) : fmt.whole(v);
}

/** A rate on a small sample reads greyed, with the sample said (the rate is noisy, not wrong): the field that counts the
 * sample and the size under which it is small. */
export const SMALL: Record<string, [string, number, string]> = {
  catch_rate: ["targets", 10, "targets"],
  yards_per_target: ["targets", 10, "targets"],
  adot: ["targets", 10, "targets"],
  yac_per_reception: ["receptions", 8, "receptions"],
  yards_per_carry: ["carries", 15, "carries"],
  completion_rate: ["attempts", 30, "pass attempts"],
  yards_per_attempt: ["attempts", 30, "pass attempts"],
  cpoe: ["attempts", 30, "pass attempts"],
  catchable_rate: ["charted_targets", 10, "charted targets"],
  separation: ["ngs_targets", 10, "Next Gen Stats targets"],
  yac_over_expected: ["ngs_receptions", 8, "Next Gen Stats receptions"],
  ryoe_per_attempt: ["ngs_rush_attempts", 20, "Next Gen Stats carries"],
  time_to_throw: ["ngs_pass_attempts", 50, "Next Gen Stats pass attempts"],
  ngs_cpoe: ["ngs_pass_attempts", 50, "Next Gen Stats pass attempts"],
};

/** The small sample behind a number, in words ("small sample: 6 targets"), or null. */
export function small(c: StatsColumn, p: StatsRow, mode: Mode): string | null {
  const s = SMALL[c.id];
  if (!s || num(p[field(c, mode)]) === null) return null;
  const n = num(p[s[0]]);
  return n !== null && n < s[1] ? `Small sample: ${fmt.whole(n)} ${s[2]} (under ${s[1]}), so this rate moves a lot.` : null;
}

/** The reason a cell is —, or the sample behind a number ("23 of 57 team carries in his 2 games"). */
export function why(c: StatsColumn, p: StatsRow, mode: Mode): string {
  const v = num(p[field(c, mode)]);
  const g = `${p.games} game${p.games === 1 ? "" : "s"}`;
  const n = (k: string) => num(p[k]);
  // ---- IX-3 (Wave I-X): under a game situation, a column not split by it says so; a split one says its plays
  if (c.unsplit) return c.reason ?? "Not split by game situation.";
  if (c.situation) {
    const where = c.situation.toLowerCase();
    const plays = n("situation_plays");
    if (plays === null || plays === 0) return `His team was not in this situation (${where}) in his games in this window.`;
    if (v === null) return `Too few to read: ${plays} plays of his team's ${where}.`;
    if (c.id === "target_share") return `${n("targets")} of ${n("team_targets")} team targets ${where} (${plays} plays of his team's, his ${g})`;
    if (c.id === "carry_share") return `${n("carries")} of ${n("team_carries")} team carries ${where} (${plays} plays of his team's, his ${g})`;
    return `${title(c, mode)} ${where}: ${plays} plays of his team's in his ${g}`;
  }
  // ---- end IX-3
  if (v === null) return c.reason ?? "not available";
  switch (c.id) {
    case "target_share":
      return `${n("targets")} of ${n("team_targets")} team targets in his ${g}`;
    case "carry_share":
      return `${n("carries")} of ${n("team_carries")} team carries in his ${g}`;
    // ---- IX-1: on the field (2016-2025 counted play by play; 2026 estimated from his snap share)
    case "on_field_target_share":
      return `${n("on_field_targets")} of ${fmt.pts(n("on_field_team_targets"), 1)} team targets on the plays he was on the field in his ${g}${p.on_field_basis === "participation" ? "" : " (estimated from his snap share)"}`;
    case "on_field_carry_share":
      return `${n("on_field_carries")} of ${fmt.pts(n("on_field_team_carries"), 1)} team carries on the plays he was on the field in his ${g}${p.on_field_basis === "participation" ? "" : " (estimated from his snap share)"}`;
    case "rb_carry_share":
      return `${n("carries")} of ${n("team_rb_carries")} running-back carries in his ${g}`;
    case "first_read_target_share":
      return `${n("first_read_targets")} of ${n("team_first_read_targets")} charted first-read targets, ${n("charted_games")} charted games`;
    case "route_participation":
      return `${n("routes_proxy")} of ${n("team_dropbacks_with_participation")} dropbacks on the field (an estimate)`;
    case "snap_share":
      return `mean of ${n("snap_games")} games with snap counts`;
    // ---- IO-4: the two parts of a role change ("27.1% in his last 2 games against 12.0% in his 2 before")
    case "target_share_change":
    case "carry_share_change":
    case "snap_share_change": {
      const base = c.id.replace(/_change$/, "");
      const a = n(`${base}_recent`);
      const b = n(`${base}_before`);
      if (a === null || b === null) return c.reason ?? "not available";
      return `${fmt.pct(a, 1)} in his last ${n("role_games_recent")} games against ${fmt.pct(b, 1)} in his ${n("role_games_before")} before them`;
    }
    // ---- IL-1: Next Gen Stats — the weeks NGS published of his games, and NGS's own denominator (the weight)
    case "time_to_throw":
    case "ngs_cpoe":
      return `NGS published ${n("ngs_pass_weeks")} of his ${g} (15+ pass attempts): ${n("ngs_pass_attempts")} attempts, weighted by attempts`;
    case "ryoe_per_attempt":
      return `NGS published ${n("ngs_rush_weeks")} of his ${g} (10+ carries): ${n("ngs_rush_attempts")} carries, weighted by carries`;
    case "separation":
      return `NGS published ${n("ngs_rec_weeks")} of his ${g} (5+ targets): ${n("ngs_targets")} targets, weighted by targets`;
    case "yac_over_expected":
      return `NGS published ${n("ngs_rec_weeks")} of his ${g} (5+ targets): ${n("ngs_receptions")} receptions, weighted by receptions`;
    // ---- end IL-1
    default: {
      const s = SMALL[c.id];
      if (s && n(s[0]) !== null) return `${fmt.whole(n(s[0]))} ${s[2]} in his ${g}`;
      return c.per_game && mode === "game" ? `${c.label} ${fmt.whole(n(c.id))} in ${g}` : `${c.label}: ${g}`;
    }
  }
}

// ---- the CSV built in the browser (when the API has no /api/players.csv yet): the rows and columns on screen, a
// header row of labels, unknown = an empty cell (never 0), text that a spreadsheet would run as a formula neutralised
const RISKY = /^[=+\-@\t\r]/;
function cell(s: string): string {
  let v = s;
  if (RISKY.test(v) && !/^[-+]?\d/.test(v)) v = `'${v}`;
  return /[",\n\r]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
}

export function csv(rows: StatsRow[], cols: StatsColumn[], mode: Mode, owner?: (p: StatsRow) => string): string {
  const unit = (c: StatsColumn) => (SHARE_CHANGE.has(c.id) ? " (points of share)" : c.format === "pct" ? " (%)" : ""); // IO-4
  const headers = ["Player", "Position", "NFL team", ...cols.map((c) => title(c, mode) + unit(c)), ...(owner ? ["Team in league"] : [])];
  const lines = [headers.map(cell).join(",")];
  for (const p of rows) {
    const vals = cols.map((c) => {
      if (c.unsplit) return ""; // ---- IX-3
      const v = num(p[field(c, mode)]);
      if (v === null) return "";
      return c.format === "pct" ? (v * 100).toFixed(1) : show(c, p, mode);
    });
    lines.push([p.player_name ?? "", p.position ?? "", p.team ?? "", ...vals, ...(owner ? [owner(p)] : [])].map((x) => cell(String(x))).join(","));
  }
  return lines.join("\r\n") + "\r\n";
}

// ---- IX-3 (Wave I-X): the named views — each answers one question (its caption) in at most eight columns per
// position, games included. The answer's `views` (api/league_lab_api/stats.py VIEWS) wins; an older answer without them
// reads this mirror. A column the season does not have drops out; a view left with games alone is not offered.
export type ViewKey = "key" | "production" | "opportunity" | "role" | "efficiency" | "advanced";
export interface ViewDef {
  key: string;
  label: string;
  question: string;
  columns: string[];
}
export const VIEW_KEYS: ViewKey[] = ["key", "production", "opportunity", "role", "efficiency", "advanced"];
export const VIEW_MAX = 8;
const VIEW_WORDS: Record<ViewKey, [string, string]> = {
  key: ["Key stats", "The numbers to read first: what he scores and how much of the offence is his."],
  production: ["Production", "What has he produced?"],
  opportunity: ["Opportunity", "How much of his team's offence comes his way?"],
  role: ["Role changes", "Is his role growing or shrinking?"],
  efficiency: ["Efficiency", "What does he do with each chance?"],
  advanced: ["Advanced", "What do tracking and charting add?"],
};
const VIEWS: Record<PosGroup, Record<ViewKey, string[]>> = {
  wrte: {
    key: ["games", "points", "targets", "target_share", "receptions", "receiving_yards", "receiving_tds", "snap_share"],
    production: ["games", "points", "receptions", "receiving_yards", "receiving_tds", "receiving_first_downs", "yards_per_reception", "yac_per_reception"],
    opportunity: ["games", "targets", "target_share", "on_field_target_share", "air_yards_share", "wopr", "red_zone_targets", "snap_share"],
    role: ["games", "target_share", "target_share_change", "snap_share", "snap_share_change", "route_participation", "first_read_target_share"],
    efficiency: ["games", "catch_rate", "yards_per_target", "epa_per_target", "receiving_success_rate", "first_downs_per_target", "racr", "points_over_expected"],
    advanced: ["games", "separation", "cushion", "yac_over_expected", "adot", "catchable_rate", "drop_rate", "tprr_proxy"],
  },
  rb: {
    key: ["games", "points", "carries", "carry_share", "rushing_yards", "targets", "target_share", "snap_share"],
    production: ["games", "points", "rushing_yards", "rushing_tds", "receptions", "receiving_yards", "receiving_tds", "yards_per_touch"],
    opportunity: ["games", "carries", "carry_share", "on_field_carry_share", "targets", "target_share", "on_field_target_share", "inside_10_carries"],
    role: ["games", "carry_share", "carry_share_change", "target_share", "target_share_change", "snap_share", "snap_share_change", "rb_carry_share"],
    efficiency: ["games", "yards_per_carry", "epa_per_carry", "rushing_success_rate", "first_downs_per_carry", "yards_per_target", "epa_per_target", "points_over_expected"],
    advanced: ["games", "ryoe_per_attempt", "rush_efficiency", "stacked_box_rate", "time_to_los", "yards_before_contact_per_carry", "yards_after_contact_per_carry", "broken_tackle_rate"],
  },
  qb: {
    key: ["games", "points", "attempts", "passing_yards", "passing_tds", "passing_interceptions", "carries", "rushing_yards"],
    production: ["games", "points", "completions", "passing_yards", "passing_tds", "passing_interceptions", "rushing_yards", "rushing_tds"],
    opportunity: ["games", "attempts", "dropbacks", "carries", "scrambles", "red_zone_carries", "rushing_points_share"],
    role: ["games", "snap_share"],
    efficiency: ["games", "completion_rate", "yards_per_attempt", "adjusted_yards_per_attempt", "epa_per_dropback", "passing_success_rate", "cpoe", "sack_rate"],
    advanced: ["games", "time_to_throw", "ngs_cpoe", "aggressiveness", "ngs_pass_intended_air_yards", "pressure_rate", "bad_throw_rate", "times_pressured"],
  },
  all: {
    key: ["games", "points", "ros_value", "targets", "target_share", "carries", "carry_share", "snap_share"],
    production: ["games", "points", "passing_yards", "passing_tds", "rushing_yards", "rushing_tds", "receiving_yards", "receiving_tds"],
    opportunity: ["games", "attempts", "carries", "carry_share", "targets", "target_share", "red_zone_opportunities", "snap_share"],
    role: ["games", "target_share", "target_share_change", "carry_share", "carry_share_change", "snap_share", "snap_share_change"],
    efficiency: ["games", "epa_per_dropback", "epa_per_carry", "epa_per_target", "yards_per_carry", "yards_per_target", "points_over_expected"],
    advanced: ["games", "separation", "yac_over_expected", "ryoe_per_attempt", "time_to_throw", "ngs_cpoe", "broken_tackle_rate", "drop_rate"],
  },
};

/** The position's named views: the answer's when it has them, else the mirror — only the columns this season has. */
export function viewsFor(pos: PosGroup, catalogue: StatsColumn[], answer?: ViewDef[] | null): ViewDef[] {
  const have = new Set(catalogue.filter((c) => c.available !== false).map((c) => c.id));
  const list: ViewDef[] = answer?.length ? answer : VIEW_KEYS.map((k) => ({ key: k, label: VIEW_WORDS[k][0], question: VIEW_WORDS[k][1], columns: VIEWS[pos][k] }));
  return list
    .map((v) => ({ ...v, columns: v.columns.filter((c) => have.has(c)).slice(0, VIEW_MAX) }))
    .filter((v) => v.key === "key" || v.columns.filter((c) => c !== "games").length >= 2);
}
// ---- end IX-3
