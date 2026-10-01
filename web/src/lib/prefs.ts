// The league / team pick, remembered on this phone (localStorage). A shared link (?league=&team=) wins
// and is then remembered. Storage can be unavailable (private mode): every access is guarded.

const KEY_LEAGUE = "ll.league";
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
};
