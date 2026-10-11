// ---- IZ-2 (Wave I-Z, the review of 10 October § "The trade decision that could distinguish the product"): a trade
// answers five questions in order. Everything here ORDERS and WORDS what the calculator's answer already holds
// (`decision`, `lineups`, `card`, `cut`, `market`, `provenance`, `caveats`): nothing is re-priced. The one sum —
// the claim's total = standing pat + the claim's gain on the same basis — is the API's own `alternative.beyond`
// read the other way (trade − claim = beyond), pinned in api/tests/test_iz2.py.
import type { CardAlternative, DecisionChange, TeamRosterRow, TradeAlternative, TradeEval, TradePlayer } from "./api";

/** The panel's row: one starting slot that changes — who leaves it, who takes it, the points difference. */
export interface PanelRow {
  slot: string;
  out: string | null; // the displaced player (null: the slot was empty)
  outWhy: string | null; // "traded", "to the bench", …
  in: string | null;
  inHow: string | null; // "from the trade", "from the bench", …
  change: number | null; // in − out, this week's projection
}

const IN_HOW: Record<string, string> = { trade: "from the trade", bench: "from the bench", "free agent": "a free agent for the week", slot: "moves over" };
const OUT_WHY: Record<string, string> = { traded: "traded", cut: "cut", bench: "to the bench", "free agent no longer needed": "the free agent no longer needed", slot: "moves to another slot" };

type Change = DecisionChange & { in_player?: { player_name: string | null } | null; out_player?: { player_name: string | null } | null };

/** The slots that change in one side's starting lineup this week (the decision's `changes`, in the lineup's order). */
export function panelRows(changes: DecisionChange[] | undefined): PanelRow[] {
  return (changes ?? []).map((c0) => {
    const c = c0 as Change;
    const change = c.in_value != null && c.out_value != null ? c.in_value - c.out_value : c.in_value != null ? c.in_value : c.out_value != null ? -c.out_value : null;
    return {
      slot: c.slot_word || c.slot,
      out: c.out_player?.player_name ?? null,
      outWhy: c.out_why ? (OUT_WHY[c.out_why] ?? c.out_why) : null,
      in: c.in_player?.player_name ?? null,
      inHow: c.in_how ? (IN_HOW[c.in_how] ?? c.in_how) : null,
      change,
    };
  });
}

/** Keep / claim / trade on one basis: your starters' total over the window for each (the claim's: standing pat plus the
 * claim's gain on the same basis). `claim` is null when the answer names no claim. */
export interface ThreeWays {
  keep: number;
  claim: number | null;
  trade: number;
  claimGain: number | null;
  tradeGain: number;
  claimName: string | null; // "add Washington Commanders defense, drop Jacory Croskey-Merritt"
  assumption: string; // a free agent may be gone by waivers
  best: "keep" | "claim" | "trade";
}

type Alt = Partial<CardAlternative> & Partial<TradeAlternative>;

export function threeWays(r: TradeEval): ThreeWays | null {
  const d = r.decision;
  if (!d) return null;
  const alt = ((d.alternative as unknown as { mine?: Alt }).mine ?? null) as Alt | null;
  const keep = d.mine.before.window;
  const trade = d.mine.after.window;
  const hasClaim = !!alt && alt.kind === "waiver" && !!alt.player && alt.gain_window != null;
  const claimGain = hasClaim ? alt!.gain_window! : null;
  const claim = claimGain == null ? null : keep + claimGain;
  const pname = (p: { player_name: string; position: string | null } | null | undefined) =>
    p ? (p.position === "DEF" && !/defense$/i.test(p.player_name) ? `${p.player_name} defense` : p.player_name) : "";
  const claimName = hasClaim ? `add ${pname(alt!.player)}${alt!.drop ? `, drop ${alt!.drop.player_name}` : alt!.open_spot ? " for your open roster spot" : ""}` : null;
  const assumption = alt?.availability_words
    ? `${alt.availability_words[0].toUpperCase()}${alt.availability_words.slice(1)}.`
    : "A free agent may be gone by the time your claim runs: another team can add him first.";
  const tradeGain = d.mine.gain_window;
  const best = claimGain != null && claimGain > tradeGain && claimGain > 0 ? "claim" : tradeGain > 0 ? "trade" : "keep";
  return { keep, claim, trade, claimGain, tradeGain, claimName, assumption, best };
}

/** A player in the trade (given, received or cut) with what could change the answer about him: his injury report and
 * the reason he sits (the rosters' own notes), or why he cannot play. */
export interface Involved {
  key: string;
  name: string;
  side: "give" | "get" | "cut";
  words: string | null;
}

export function involved(r: TradeEval, mine: TeamRosterRow[], theirs: TeamRosterRow[]): Involved[] {
  const rowOf = (rows: TeamRosterRow[], k: string) => rows.find((x) => x.sleeper_id === k);
  const note = (p: TradePlayer, rows: TeamRosterRow[]): string | null => {
    const row = rowOf(rows, p.sleeper_id) as (TeamRosterRow & { availability?: { why: string; sits: boolean } | null }) | undefined;
    const bits = [p.cannot_play, row?.availability?.sits ? row.availability.why : null, row?.report_status && !/^(active|healthy)$/i.test(row.report_status) ? `listed ${row.report_status}` : null];
    const w = [...new Set(bits.filter((b): b is string => !!b))];
    return w.length ? w.join("; ") : null;
  };
  const out: Involved[] = [];
  for (const p of r.give) out.push({ key: p.sleeper_id, name: p.player_name ?? p.sleeper_id, side: "give", words: note(p, mine) });
  for (const p of r.get) out.push({ key: p.sleeper_id, name: p.player_name ?? p.sleeper_id, side: "get", words: note(p, theirs) });
  for (const c of r.cut ?? []) out.push({ key: c.player.sleeper_id, name: c.player.player_name ?? c.player.sleeper_id, side: "cut", words: note(c.player, mine) });
  return out;
}

/** "data published 11 Oct, 1:10 am ET" → "11 Oct, 1:10 am ET" (the trust line's own stamp), or null. */
export function publishedWords(provenanceWords: string | null | undefined): string | null {
  const m = /data published ([^·]+?)\s*(?:·|$)/.exec(provenanceWords ?? "");
  return m ? m[1].trim() : null;
}

/** The weekly effect under a panel: "week 5 −0.4 · week 6 +0.1 …" pairs. */
export function weekly(weeks: number[] | undefined, gains: number[] | undefined): { week: number; gain: number }[] {
  return (weeks ?? []).map((w, i) => ({ week: w, gain: gains?.[i] ?? 0 }));
}
