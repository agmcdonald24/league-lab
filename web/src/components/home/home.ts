// ---- IN-1 (Wave I-N): the home page's arithmetic and words (routes/Home.svelte). Pure: no fetch, no DOM.
import type { AboutAnswer, BoardRow, MatchupTone, RosPlayer } from "../../lib/api";

export interface TopRow {
  gsis_id: string;
  player_name: string;
  position: string;
  team: string | null;
  headshot_url: string | null;
  week: number | null; // this week's projection
  low: number | null; // this week's low-end / high-end outcome (the board carries them)
  high: number | null;
  ros: number | null; // rest of season (the fallback's context line)
  rosLow: number | null;
  rosHigh: number | null;
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** A row of IN-3's board → the projections module's row (his projection and this week's range). */
export function fromBoard(r: BoardRow): TopRow | null {
  const week = num(r.proj_points);
  if (!r.gsis_id || week === null) return null;
  return {
    gsis_id: r.gsis_id,
    player_name: r.player_name,
    position: r.position,
    team: r.team ?? null,
    headshot_url: r.headshot_url ?? null,
    week,
    low: num(r.p10),
    high: num(r.p90),
    ros: null,
    rosLow: null,
    rosHigh: null,
  };
}

/** The rest-of-season list → this week's top N by this week's projection (`week_points`), with the season's range. */
export function fromRos(players: RosPlayer[], n = 5): TopRow[] {
  return players
    .filter((p) => p.gsis_id && num(p.week_points) !== null)
    .sort((a, b) => (b.week_points ?? 0) - (a.week_points ?? 0))
    .slice(0, n)
    .map((p) => ({
      gsis_id: p.gsis_id as string,
      player_name: p.player_name,
      position: p.position,
      team: p.team,
      headshot_url: p.headshot_url ?? null,
      week: num(p.week_points),
      low: null,
      high: null,
      ros: num(p.ros_points),
      rosLow: num(p.p10),
      rosHigh: num(p.p90),
    }));
}

export function toneOf(r: BoardRow): { tone: MatchupTone | null; words: string | null } {
  return { tone: r.context?.tone ?? null, words: homeWords(r) };
}

const sentence = (w: string) => (/[.!?]$/.test(w) ? w : `${w}.`).replace(/^./, (c) => c.toUpperCase());

/** The home's one line for a matchup (IN-1 fix round, read with the real board): the defense's sentence — what the
 *  tone stands on — plus the corner's only when the call is likely (an unclear call never moves the tone, and two
 *  corners' ranks in a row made five rows a page long). The board's full sentence is one tap away (Matchups). */
export function homeWords(r: BoardRow): string | null {
  const c = r.context;
  if (!c) return null;
  const d = c.defense?.words ?? null;
  const cb = c.cb && c.cb.certainty === "likely" ? c.cb.words : null;
  if (d && cb) return `${sentence(d)} ${sentence(cb)}`;
  if (d) return sentence(d);
  return c.words ?? null;
}

export const TONE_WORDS = { favorable: "Favorable", neutral: "Neutral", difficult: "Difficult" } as const;

/** "Oct 6, 2026" from "2026-10-06" (no time zone shift: the date is a calendar day). */
export function longDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}`;
}

const POS_WORDS: Record<string, string> = { QB: "Quarterbacks", RB: "Running backs", WR: "Wide receivers", TE: "Tight ends" };

export interface GradeRow {
  position: string;
  miss: number | null; // this season's average miss (points per player)
  missBefore: number | null; // the backtest's
  inside: number | null; // this season's share inside the low-end to high-end range
  insideBefore: number | null;
  verdict: "worse" | "better" | "same" | null;
}

/** About's grades → one row per position with a verdict on the miss (worse / better / about the same as before:
 *  more than 10% apart is a change). */
export function gradeRows(g: AboutAnswer["grades"]): GradeRow[] {
  if (!g) return [];
  return g.positions
    .filter((p) => POS_WORDS[p.position])
    .map((p) => {
      const miss = num(p.season?.mae);
      const before = num(p.backtest?.mae);
      const verdict = miss === null || before === null || before <= 0 ? null : miss > before * 1.1 ? "worse" : miss < before * 0.9 ? "better" : "same";
      return { position: p.position, miss, missBefore: before, inside: num(p.season?.coverage_80), insideBefore: num(p.backtest?.coverage_80), verdict };
    });
}

/** The grades in one sentence, the bad news first. */
export function gradeLead(rows: GradeRow[], weeks: string | null): string | null {
  if (!rows.length) return null;
  const span = weeks ? `Through ${weeks} of this season` : "So far this season";
  const worse = rows.filter((r) => r.verdict === "worse").sort((a, b) => (b.miss! / b.missBefore!) - (a.miss! / a.missBefore!));
  if (worse.length) {
    const w = worse[0];
    const others = worse.slice(1).map((r) => POS_WORDS[r.position].toLowerCase());
    return (
      `${span}, ${POS_WORDS[w.position].toLowerCase()} are our weak spot: ${w.miss!.toFixed(1)} points off on average, against ${w.missBefore!.toFixed(1)} in past seasons.` +
      (others.length ? ` ${others.join(" and ").replace(/^./, (c) => c.toUpperCase())} miss more than before too.` : "")
    );
  }
  return `${span}, the projections miss by about as much as in past seasons at every position, or less.`;
}

export const posWords = (p: string) => POS_WORDS[p] ?? p;
