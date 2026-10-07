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
 *  tone stands on (IO-4 fix round: the corner's sentence no more; the board shows the corner, one tap away). */
export function homeWords(r: BoardRow): string | null {
  const c = r.context;
  if (!c) return null;
  // ---- IO-4 fix round (Wave I-O): the defense's sentence only, never the corner's (graded: no measurable effect)
  const d = c.defense?.words ?? null;
  return d ? sentence(d) : null;
  // ---- end IO-4
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

// ---- IP-1 (Wave I-P, fix round): the grades say what the sample can carry. Three weeks are about 110 quarterback-games, and
// the same model's first three weeks have ranged from 5.6 to 6.4 points at QB in past seasons, so a 10% gap after three
// weeks is no finding: under MIN_WEEKS the lead says "too few weeks to call that a difference" and the tile is
// "unclear", never "weak spot". From MIN_WEEKS on, a miss is "worse" only above every past season of the same model
// (About's by_season) and more than 10% above its backtest; "better" the mirror. docs/WORDS.md § "How the projections
// have done, honestly"; docs/METRICS.md § "v3.4: the quarterback weak spot".
export const MIN_WEEKS = 6;

export interface GradeRow {
  position: string;
  miss: number | null; // this season's average miss (points per player)
  missBefore: number | null; // the backtest of the model that made the weeks shown (mart_projection_drift, IP-1)
  inside: number | null; // this season's share inside the low-end to high-end range
  insideBefore: number | null;
  weeks: number; // complete weeks behind the miss
  pastLow: number | null; // the same model's lowest and highest season miss in the backtest (About's by_season)
  pastHigh: number | null;
  verdict: "worse" | "better" | "same" | "unclear" | null;
}

/** About's grades → one row per position with a verdict on the miss: "unclear" while fewer than MIN_WEEKS weeks are in and
 *  the gap is more than 10%; then "worse" / "better" only outside every past season and more than 10% from the backtest. */
export function gradeRows(g: AboutAnswer["grades"]): GradeRow[] {
  if (!g) return [];
  return g.positions
    .filter((p) => POS_WORDS[p.position])
    .map((p) => {
      const miss = num(p.season?.mae);
      const before = num(p.backtest?.mae);
      const weeks = num(p.season?.weeks_scored) ?? 0;
      const past = (p.by_season ?? []).map((s) => num(s.mae)).filter((v): v is number => v !== null);
      const pastLow = past.length ? Math.min(...past) : null;
      const pastHigh = past.length ? Math.max(...past) : null;
      let verdict: GradeRow["verdict"] = null;
      if (miss !== null && before !== null && before > 0) {
        const gap = miss > before * 1.1 ? "worse" : miss < before * 0.9 ? "better" : "same";
        if (gap === "same") verdict = "same";
        else if (weeks < MIN_WEEKS) verdict = "unclear";
        else if (gap === "worse") verdict = pastHigh === null || miss > pastHigh ? "worse" : "same";
        else verdict = pastLow === null || miss < pastLow ? "better" : "same";
      }
      return { position: p.position, miss, missBefore: before, inside: num(p.season?.coverage_80), insideBefore: num(p.backtest?.coverage_80),
               weeks, pastLow, pastHigh, verdict };
    });
}

/** "weeks 1–3" → "week 3" (the newest complete week); null when the span says nothing. */
export function throughWeek(weeks: string | null): string | null {
  const m = weeks ? /(\d+)\D*$/.exec(weeks) : null;
  return m ? `week ${m[1]}` : null;
}

/** The grades in one sentence: the position where the projections miss most against the same model's past seasons,
 *  its miss and that model's, and whether the weeks in can call it a difference. */
export function gradeLead(rows: GradeRow[], weeks: string | null): string | null {
  if (!rows.length) return null;
  const through = throughWeek(weeks);
  const span = through ? `Through ${through}` : "So far this season";
  const behind = rows.filter((r) => r.verdict === "worse" || r.verdict === "unclear")
    .sort((a, b) => (b.miss! / b.missBefore!) - (a.miss! / a.missBefore!));
  if (behind.length) {
    const w = behind[0];
    const head = `${span}, ${POS_WORDS[w.position].toLowerCase()} are where our projections miss most against past seasons: ` +
      `${w.miss!.toFixed(1)} points per game, against ${w.missBefore!.toFixed(1)} for the same model in past seasons`;
    if (w.verdict === "unclear") return `${head} — too few weeks to call that a difference.`;
    const others = behind.slice(1).filter((r) => r.verdict === "worse").map((r) => POS_WORDS[r.position].toLowerCase());
    return (
      `${head}, more than in any of them${w.pastLow !== null && w.pastHigh !== null ? ` (${w.pastLow.toFixed(1)} to ${w.pastHigh.toFixed(1)})` : ""}.` +
      (others.length ? ` ${others.join(" and ").replace(/^./, (c) => c.toUpperCase())} miss more than in past seasons too.` : "")
    );
  }
  return `${span}, the projections miss by about as much as in past seasons at every position, or less.`;
}
// ---- end IP-1

export const posWords = (p: string) => POS_WORDS[p] ?? p;
