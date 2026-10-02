// G1 → G3 (Wave G integration): the ONE place the research screens' shapes meet the research API's real answers.
// The screens (routes/{Trends,Matchups,Players,Receivers,Compare}.svelte) were written against an assumed contract;
// G1's answers (api/league_lab_api/research.py, api/README.md § "Research (G1)") are pinned against the marts, so the
// web side adapts here. Each `to*` takes the raw JSON of one route and returns the shape in lib/api.ts the screen reads.
// Field renames (G1 → screen), all in this league's scoring unless the name ends in _ref:
//   trends    players[].gap_direction → direction; role_alert.kind_label → role_alert.label
//   defense   teams[].points_allowed_per_game_std → points_allowed_pg, rank_std → rank,
//             points_allowed_per_game_l4 → points_allowed_pg_l4, direction (softer/stiffer/steady) → trend (up/down/steady),
//             weeks_used [1, 2, 3] → the last week played (3); starters: G1's `starters` (with team=, added for the heatmap)
//   cb        no shadow_flag (G1 does not flag shadows: README) → null
//   players   ppg → points_per_game
//   receivers games → games_played, points_per_game → ppg, snap_pct → avg_offense_snap_pct, form_week → through_week,
//             yardsticks.*.avg_offense_snap_pct kept; first_read_share_l3 / route_participation_l3 (not sent) → null
//   compare   projection.{proj_points,p10..p90} → the side's own; season → season_stats (totals ÷ games_played → _pg);
//             last3 → form (points_per_game_l3 → ppg_l3); usage.avg_offense_snap_pct → usage.snap_pct;
//             next4[0] (this week) → opponent / opp_rank; week ← the answer's week
import type {
  CbMatchups,
  Compare,
  CompareSide,
  DefenseCell,
  DefenseMatrix,
  Players,
  ReceiverRow,
  Receivers,
  RoleAlert,
  SeasonRow,
  Starter,
  TrendRow,
  Trends,
} from "./api";

type Raw = Record<string, unknown>;
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const per = (total: unknown, games: unknown): number | null => {
  const t = num(total);
  const g = num(games);
  return t === null || !g ? null : t / g;
};
const rows = (v: unknown): Raw[] => (Array.isArray(v) ? (v as Raw[]) : []);

/** Cache by the raw object: a cached answer (Back) is mapped once. */
function memo<T>(fn: (raw: Raw) => T): (raw: unknown) => T {
  const seen = new WeakMap<object, T>();
  return (raw: unknown) => {
    const r = (raw ?? {}) as Raw;
    const hit = seen.get(r);
    if (hit !== undefined) return hit;
    const out = fn(r);
    seen.set(r, out);
    return out;
  };
}

// ---- /api/trends
function roleAlert(a: unknown): RoleAlert | null {
  if (!a || typeof a !== "object") return null;
  const r = a as Raw;
  return { ...(r as unknown as RoleAlert), label: (r.kind_label as string | null) ?? (r.label as string | null) ?? null };
}

export const toTrends = memo<Trends>((r) => ({
  ...(r as unknown as Trends),
  players: rows(r.players).map(
    (p) => ({ ...p, direction: (p.gap_direction ?? p.direction ?? "even") as TrendRow["direction"], role_alert: roleAlert(p.role_alert) }) as unknown as TrendRow,
  ),
}));

// ---- /api/matchups/defense
const TREND: Record<string, DefenseCell["trend"]> = { softer: "up", stiffer: "down", steady: "steady" };

export const toDefense = memo<DefenseMatrix>((r) => {
  const used = r.weeks_used;
  const weeks = Array.isArray(used) ? (used as number[]) : [];
  return {
    ...(r as unknown as DefenseMatrix),
    weeks_used: Array.isArray(used) ? (weeks.length ? Math.max(...weeks) : null) : num(used),
    teams: rows(r.teams).map(
      (t) =>
        ({
          ...t,
          points_allowed_pg: num(t.points_allowed_per_game_std ?? t.points_allowed_pg),
          rank: num(t.rank_std ?? t.rank),
          points_allowed_pg_l4: num(t.points_allowed_per_game_l4 ?? t.points_allowed_pg_l4),
          rank_l4: num(t.rank_l4),
          trend: TREND[String(t.direction ?? t.trend)] ?? null,
        }) as unknown as DefenseCell,
    ),
    starters: rows(r.starters) as unknown as Starter[],
  };
});

// ---- /api/matchups/cb
export const toCb = memo<CbMatchups>((r) => ({
  ...(r as unknown as CbMatchups),
  matchups: rows(r.matchups).map((m) => ({ ...m, shadow_flag: (m.shadow_flag as boolean | undefined) ?? null })) as unknown as CbMatchups["matchups"],
}));

// ---- /api/players
export const toPlayers = memo<Players>((r) => ({
  ...(r as unknown as Players),
  players: rows(r.players).map((p) => ({ ...p, points_per_game: num(p.ppg ?? p.points_per_game) }) as unknown as SeasonRow),
}));

// ---- /api/receivers
export const toReceivers = memo<Receivers>((r) => {
  const rs = rows(r.receivers).map(
    (p) =>
      ({
        ...p,
        games_played: num(p.games ?? p.games_played),
        ppg: num(p.points_per_game ?? p.ppg),
        avg_offense_snap_pct: num(p.snap_pct ?? p.avg_offense_snap_pct),
        first_read_share_l3: num(p.first_read_share_l3),
        route_participation_l3: num(p.route_participation_l3),
      }) as unknown as ReceiverRow,
  );
  const weeks = rs.map((p) => num((p as unknown as Raw).form_week)).filter((w): w is number => w !== null);
  return { ...(r as unknown as Receivers), receivers: rs, through_week: num(r.through_week) ?? (weeks.length ? Math.max(...weeks) : null) };
});

// ---- /api/compare
function side(s: Raw, week: number | null): CompareSide {
  const pj = (s.projection ?? {}) as Raw;
  const se = (s.season ?? {}) as Raw;
  const l3 = (s.last3 ?? {}) as Raw;
  const us = (s.usage ?? {}) as Raw;
  const next4 = rows(s.next4);
  const now = next4.find((w) => w.week === week && !w.bye) ?? null;
  const gp = se.games_played;
  const tds = ["passing_tds", "rushing_tds", "receiving_tds"].map((k) => num(se[k]));
  return {
    ...(s as unknown as CompareSide),
    week,
    proj_points: num(pj.proj_points),
    p10: num(pj.p10),
    p25: num(pj.p25),
    p75: num(pj.p75),
    p90: num(pj.p90),
    opponent: (now?.opponent as string | null) ?? null,
    opp_rank: num(now?.opp_rank),
    injury_status: (s.injury_status as string | null) ?? null,
    season_stats: {
      games_played: num(gp),
      ppg: num(se.ppg),
      xppg: num(se.xppg),
      targets_per_game: num(se.targets_per_game),
      carries_per_game: num(se.carries_per_game),
      receiving_yards_pg: per(se.receiving_yards, gp),
      rushing_yards_pg: per(se.rushing_yards, gp),
      passing_yards_pg: per(se.passing_yards, gp),
      tds_pg: tds.every((t) => t === null) ? null : per(tds.reduce<number>((a, t) => a + (t ?? 0), 0), gp),
    },
    form: {
      games_l3: num(l3.games_l3),
      ppg_l3: num(l3.points_per_game_l3),
      target_share_l3: num(l3.target_share_l3),
      carry_share_l3: num(l3.carry_share_l3),
      snap_pct_l3: num(l3.snap_pct_l3),
    },
    usage: {
      target_share: num(us.target_share),
      carry_share: num(us.carry_share),
      snap_pct: num(us.avg_offense_snap_pct ?? us.snap_pct),
      route_participation: num(us.route_participation),
      first_read_target_share: num(us.first_read_target_share),
      air_yards_share: num(us.air_yards_share),
    },
    ros: (s.ros as CompareSide["ros"]) ?? null,
    next4: next4.map((w) => ({ week: w.week as number, opponent: (w.opponent as string | null) ?? null, is_home: (w.is_home as boolean | null) ?? null, opp_rank: num(w.opp_rank) })),
  };
}

export const toCompare = memo<Compare>((r) => {
  const week = num(r.week);
  return { ...(r as unknown as Compare), a: side((r.a ?? {}) as Raw, week), b: side((r.b ?? {}) as Raw, week) };
});
