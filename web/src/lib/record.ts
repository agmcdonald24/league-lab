// Our record (GET /api/record): the answer's sentences. The words are the Streamlit page's own
// (app/pages/13_Record.py keeps them inline; requested of F3 / the PO: move them to app/lib and send them).
import type { RecordAnswer, RecordRow } from "./api";

export const STARTS =
  "The record starts the first week Sleeper's projections are archived before kickoff: every week we save " +
  "Sleeper's numbers next to ours before the first game, then check after the games whose numbers were closer.";

const n = (v: number | null | undefined): number => (v === null || v === undefined || Number.isNaN(v) ? 0 : Math.trunc(v));
const plural = (k: number, word: string) => `${k} ${word}${k === 1 ? "" : "s"}`;
const span = (ws: number[]) => (ws.length === 1 ? `week ${ws[0]}` : `weeks ${ws[0]}–${ws[ws.length - 1]}`);
const isNum = (v: unknown): v is number => typeof v === "number" && !Number.isNaN(v);

export interface RecordView {
  kind: "unavailable" | "empty" | "starting" | "scored";
  lines: string[]; // markdown, joined with line breaks
  caption: string;
  metrics: { label: string; value: string; delta: string | null; trend: "up" | "down" | "off" | null; help: string }[];
  calls: RecordRow[]; // the week-by-week start/sit rows (position ALL, scored)
  byPosition: RecordRow[]; // week-by-week rows per position (scored)
  leagueName: string;
}

export function recordView(d: RecordAnswer, fallbackName: string): RecordView {
  const weeks = d.weeks ?? [];
  const leagueName = weeks.find((w) => w.league_name)?.league_name ?? d.summary?.league_name ?? fallbackName;
  const base: RecordView = { kind: "empty", lines: [], caption: "", metrics: [], calls: [], byPosition: [], leagueName };
  if (d.available === false) {
    const why = d.why ?? "we keep the record for the leagues we score every morning; yours is not one of them yet";
    return { ...base, kind: "unavailable", lines: [`**No record for ${fallbackName}.** ${why[0].toUpperCase()}${why.slice(1)}.`], caption: "" };
  }
  if (!weeks.length) {
    return {
      ...base,
      lines: [
        `**No week on the record yet.** ${STARTS} Sleeper's numbers are saved by the morning refresh, so the first week it runs ` +
          "before a Thursday kickoff is the first week here. Nothing is filled in after the fact.",
      ],
    };
  }
  const weekNums = (status: string) => [...new Set(weeks.filter((w) => w.status === status && isNum(w.week)).map((w) => w.week as number))].sort((a, b) => a - b);
  const scored = weekNums("scored");
  const inPlay = weekNums("in_play");
  const calls = weeks.filter((w) => w.status === "scored" && w.position === "ALL");
  const byPosition = weeks.filter((w) => w.status === "scored" && w.position !== "ALL");
  if (!scored.length) {
    const first = inPlay[0];
    const a = weeks.find((w) => w.week === first && w.position === "ALL");
    return {
      ...base,
      kind: "starting",
      lines: [
        `**The record starts with week ${first}.** Our projections and Sleeper's were both saved before the week's first kickoff` +
          (a ? `: ${n(a.n_both)} players projected by both, ${n(a.pairs_listed)} start/sit calls across the league.` : "."),
      ],
      caption: `It is scored once the week's last game is in, in ${leagueName} scoring. ${STARTS}`,
    };
  }
  const last = scored[scored.length - 1];
  const a = d.summary ?? null;
  const lines: string[] = [];
  const metrics: RecordView["metrics"] = [];
  if (a && n(a.pairs_n)) {
    const pn = n(a.pairs_n),
      po = n(a.pairs_ours_right),
      ps = n(a.pairs_sleeper_right);
    const pdis = n(a.pairs_disagree),
      pod = n(a.pairs_ours_right_disagree);
    const psd = ps - n(a.pairs_both_right);
    lines.push(`**Through week ${last}, we called ${po} of ${pn} start/sit calls right; Sleeper's numbers called ${ps}.**`);
    lines.push(
      pdis
        ? `Where we and Sleeper disagreed (${plural(pdis, "call")}), we were right ${pod} time${pod === 1 ? "" : "s"} and Sleeper ${psd}.`
        : "We and Sleeper made the same call every time.",
    );
    metrics.push({
      label: "Calls right",
      value: `${po} of ${pn}`,
      delta: po === ps ? "level with Sleeper" : `${po - ps > 0 ? "+" : ""}${po - ps} vs Sleeper`,
      trend: po === ps ? "off" : po > ps ? "up" : "down",
      help: "Start/sit calls (the closest three per team each week) where the player we said to start outscored the other",
    });
  } else {
    lines.push(`**Through week ${last}:** no start/sit call could be graded yet.`);
  }
  if (a && isNum(a.ours_mae) && isNum(a.sleeper_mae)) {
    lines.push(`Our projections missed by **${a.ours_mae.toFixed(2)} points** a player on average; Sleeper's by **${a.sleeper_mae.toFixed(2)}**.`);
    const diff = a.ours_mae - a.sleeper_mae;
    metrics.push({
      label: "Average miss",
      value: `${a.ours_mae.toFixed(2)} pts`,
      delta: Math.abs(diff) < 0.005 ? "level with Sleeper" : `Sleeper's ${a.sleeper_mae.toFixed(2)}`,
      trend: "off",
      help: "How far our projection landed from the real score, in points, averaged over the players both projected",
    });
  }
  const small =
    scored.length < 4
      ? ` ${["One week is", "Two weeks are", "Three weeks are"][scored.length - 1]} a small sample: one odd Sunday moves these numbers a lot.`
      : "";
  const pending = inPlay.length
    ? ` Week ${inPlay[inPlay.length - 1]} is being played: both sides' numbers are saved, and it counts once its last game is in.`
    : "";
  const caption = `The record runs from week ${scored[0]} (${span(scored)} scored), in ${leagueName} scoring: the first week Sleeper's projections were saved before kickoff.${small}${pending}`;
  return { ...base, kind: "scored", lines, caption, metrics, calls, byPosition };
}

export const RECORD_HOWTO = (leagueName: string) =>
  "- **Use it to decide how much to trust us.** If we call more start/sit decisions right than Sleeper's free numbers, " +
  "follow the cards on close calls; if not, treat them as a second opinion.\n" +
  "- **What is compared.** Every week, before the first game kicks off, we save our projections and Sleeper's (the ones " +
  `in the Sleeper app). After the games we check whose numbers were closer. Both are counted in ${leagueName} scoring: ` +
  "Sleeper's stat line (yards, catches, touchdowns) is counted your league's way, not Sleeper's default.\n" +
  "- **Start/sit calls** are the three closest calls per team each week, the ones on the My Week cards (start A over B). " +
  "We said start A; Sleeper's call is whichever of the two it projected higher. The right call is whoever scored more.\n" +
  "- **The average miss** is how far a projection landed from the real score, in points, over every player both " +
  "projected who played (Out and Doubtful players left out). **Order** is the order score: how well the projected " +
  "order matched the real one (1 = perfect, 0 = random).\n" +
  "- **What it is not.** It is not a test on past seasons, and it does not go back " +
  "before the first week Sleeper's numbers were saved before kickoff: earlier weeks are not filled in after the fact. " +
  "It covers players both sides projected, not every name Sleeper lists; a defense is left out (its points are not " +
  "counted from a stat line). A few weeks are a small sample.\n" +
  "- **Same moment for both.** Sleeper's numbers are the last ones saved before the week's first kickoff, the moment " +
  "ours are locked. News after that (a Sunday inactive) is in neither.";
