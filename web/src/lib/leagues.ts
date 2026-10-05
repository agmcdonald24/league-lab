// The league picker's options: the signed-in Sleeper user's leagues (GET /api/leagues?username=), else the house
// leagues (GET /api/leagues, as before the username sign-in), plus the league in the URL when it is neither (a
// shared link to any Sleeper league works: the API serves it on demand).
import type { League, Roster, UserLeagues } from "./api";
import { prefs } from "./prefs";

export interface LeagueOption {
  league_id: string;
  name: string;
  scoring_label: string | null;
  total_rosters: number | null;
  roster_id: number | null; // the user's own team there (null: none, or not known)
  team_name: string | null;
  mine: boolean; // from the user's own list (so "no team" is known, not just unknown)
}

export function leagueOptions(
  mine: UserLeagues | null,
  house: League[],
  current: string | null,
  names: Record<string, string> = {},
): LeagueOption[] {
  const out: LeagueOption[] = mine
    ? mine.leagues.map((l) => ({
        league_id: l.league_id,
        name: l.name,
        scoring_label: l.scoring_label,
        total_rosters: l.total_rosters,
        roster_id: l.roster_id,
        team_name: l.team_name,
        mine: true,
      }))
    : house.map((l) => ({
        league_id: l.league_id,
        name: l.league_name,
        scoring_label: l.scoring_label,
        total_rosters: null,
        roster_id: null,
        team_name: null,
        mine: false,
      }));
  // I0-B: the MyFantasyLeague leagues opened on this phone ("MFL" after the name in the switcher)
  for (const m of prefs.mflLeagues()) {
    if (out.some((o) => o.league_id === m.league_id)) continue;
    // ---- II-5: a Sleeper league opened by its link is remembered here too: "· MFL" only on an MFL league
    // ---- IK-3: "· ESPN" / "· Yahoo" by the key's prefix (suffixOf)
    out.push({ league_id: m.league_id, name: `${m.name}${suffixOf(m.league_id)}`, scoring_label: m.scoring_label, total_rosters: m.total_rosters, roster_id: m.roster_id, team_name: m.team_name, mine: true });
  }
  if (current && !out.some((o) => o.league_id === current)) {
    out.push({ league_id: current, name: names[current] ?? "This league", scoring_label: null, total_rosters: null, roster_id: null, team_name: null, mine: false });
  }
  return out;
}

/** "12 teams · half PPR …" for a league row. */
export function leagueLine(l: { total_rosters: number | null; scoring_label: string | null }): string {
  const label = l.scoring_label ?? "";
  // the house labels already start with the size ("10-team redraft · …"): do not say it twice
  if (l.total_rosters && !/^\d+-team/.test(label)) return [`${l.total_rosters} teams`, label].filter(Boolean).join(" · ");
  return label;
}

// ---- I0-B (Wave I-0): MyFantasyLeague. GET /api/leagues?mfl=<league link or id> → the league card and its teams (MFL
// has no username lookup without a login: the user picks their team; an F=0004 in the link preselects it).
export interface MflLeague {
  platform: "mfl";
  league: { league_id: string; name: string; season: number; total_rosters: number | null; scoring_label: string | null; url: string | null };
  teams: Roster[];
  roster_id: number | null; // the team the pasted link names (F=0004), else null
  unmapped: { mfl_id: string; name: string | null; position: string | null }[];
  players: number;
  mapped: number;
  scoring_note: string;
}

export const mflPath = (text: string) => `/api/leagues?mfl=${encodeURIComponent(text.trim())}`;
export const isMfl = (league: string | null | undefined) => !!league && league.toLowerCase().startsWith("mfl:");
// ---- IK-3 (Wave I-K): the switcher's suffix by the key's prefix — "· MFL", "· ESPN", "· Yahoo"; a Sleeper league none
export const suffixOf = (league: string | null | undefined): string => {
  const s = (league ?? "").toLowerCase();
  return s.startsWith("mfl:") ? " · MFL" : s.startsWith("espn:") ? " · ESPN" : s.startsWith("yahoo:") ? " · Yahoo" : "";
};

// ---- I0-C (Wave I-0): one MFL box for a link, an id or the league's name. GET /api/leagues?mfl_search=<text>: a link or
// an id answers as ?mfl= does (an MflLeague); a name answers this season's matches (at most 25) to pick from.
export interface MflSearch {
  platform: "mfl";
  query: string;
  season: number;
  matches: { league_id: string; name: string; year: number; home_url: string }[];
  total: number;
  note: string;
}

export const mflSearchPath = (text: string) => `/api/leagues?mfl_search=${encodeURIComponent(text.trim())}`;
export const isMflSearch = (v: MflLeague | MflSearch): v is MflSearch => "matches" in v;

// ---- IC-3 (Wave I-C): the Leagues card tells the truth. `card` rides on `/api/leagues?mfl=` and on each
// `/api/leagues?username=` row: the lineup League Lab solves and the scoring it prices, read back in the league's own
// words, what is not priced; the scoring check (IC-1's GET /api/league/scoring-check?league=) loads after the card.
export interface LeagueCard {
  lineup: { text: string; slots: string[]; unread: string[]; unread_text?: string; bench: number };
  scoring: {
    text: string;
    pieces: string[];
    not_priced: string[];
    not_priced_text?: string;
    approximated: string[];
    source: "spec" | "settings";
  };
  check_path: string;
}

export interface CheckMiss {
  player: string;
  position?: string | null;
  theirs: number;
  ours: number;
  gap: number;
  likely_rule?: string | null;
}

export interface ScoringCheck {
  league: string;
  week: number;
  n: number;
  within_0_1?: number;
  within_1: number;
  misses: CheckMiss[];
  suspect_rules?: unknown[];
  words?: string;
}

// declaration merging: the MFL answer and the Sleeper rows carry the card (older answers have none)
export interface MflLeague {
  card?: LeagueCard;
}
export type WithCard = { card?: LeagueCard | null };

const pts = (v: number) => (Math.round(v * 10) / 10).toString().replace("-", "−");

/** "Week 2 check: we match your league's points for 141 of 146 players within 1 point." */
export function checkLine(c: ScoringCheck): string {
  if (!c.n) return `Week ${c.week}: no scored players to check yet.`;
  const all = c.within_1 === c.n;
  return `Week ${c.week} check: we match your league's points for ${all ? `all ${c.n}` : `${c.within_1} of ${c.n}`} players within 1 point.`;
}

/** MFL writes names "Last, First" ("Patriots, New England"): said the usual way round. */
export const firstLast = (name: string) => name.replace(/^([^,]+), (.+)$/, "$2 $1");

/** "Saquon Barkley: league 23, ours 13 — sacks (one more or fewer than our stat line)" (the check's rule family
 * prefix, "count:" / "distance:", is the check's own key, not words). */
export function missLine(m: CheckMiss): string {
  const rule = (m.likely_rule ?? "").replace(/^[a-z_]+:/, "").trim();
  return `${firstLast(m.player)}: league ${pts(m.theirs)}, ours ${pts(m.ours)}${rule ? ` \u2014 ${rule}` : ""}`;
}

/** The misses worth naming (more than 1 point apart), biggest first. */
export function bigMisses(c: ScoringCheck, n = 3): CheckMiss[] {
  return [...c.misses].filter((m) => Math.abs(m.gap) > 1).sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap)).slice(0, n);
}
// ---- end IC-3
