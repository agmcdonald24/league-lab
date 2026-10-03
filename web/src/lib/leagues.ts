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
    out.push({ league_id: m.league_id, name: `${m.name} · MFL`, scoring_label: m.scoring_label, total_rosters: m.total_rosters, roster_id: m.roster_id, team_name: m.team_name, mine: true });
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
