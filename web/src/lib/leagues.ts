// The league picker's options: the signed-in Sleeper user's leagues (GET /api/leagues?username=), else the house
// leagues (GET /api/leagues, as before the username sign-in), plus the league in the URL when it is neither (a
// shared link to any Sleeper league works: the API serves it on demand).
import type { League, UserLeagues } from "./api";

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
