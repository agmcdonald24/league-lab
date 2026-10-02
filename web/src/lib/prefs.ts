// The league / team pick and the Sleeper username, remembered on this phone (localStorage). A shared link
// (?league=&team=) wins and is then remembered. Storage can be unavailable (private mode): every access is guarded.
import type { UserLeagues } from "./api";

const KEY_LEAGUE = "ll.league";
const KEY_USER = "ll.user"; // the Sleeper username typed on the sign-in screen
const KEY_USER_LEAGUES = "ll.userLeagues"; // the last answer of /api/leagues?username= (the picker renders at once)
const keyTeam = (league: string) => `ll.team.${league}`;

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* storage blocked: the URL still carries the pick */
  }
}

export const prefs = {
  league: (): string | null => read(KEY_LEAGUE),
  setLeague: (league: string) => write(KEY_LEAGUE, league),
  team: (league: string): number | null => {
    const v = read(keyTeam(league));
    return v !== null && /^\d+$/.test(v) ? Number(v) : null;
  },
  setTeam: (league: string, team: number | null) => write(keyTeam(league), team === null ? null : String(team)),
  user: (): string | null => read(KEY_USER),
  setUser: (username: string | null) => write(KEY_USER, username),
  userLeagues: (): UserLeagues | null => {
    const raw = read(KEY_USER_LEAGUES);
    if (!raw) return null;
    try {
      const v = JSON.parse(raw) as UserLeagues;
      return v && Array.isArray(v.leagues) ? v : null;
    } catch {
      return null;
    }
  },
  setUserLeagues: (v: UserLeagues | null) => write(KEY_USER_LEAGUES, v === null ? null : JSON.stringify(v)),
  /** Forget the user (the "Not you?" link): the username and their league list; league / team picks stay. */
  forgetUser: () => {
    write(KEY_USER, null);
    write(KEY_USER_LEAGUES, null);
  },
};
