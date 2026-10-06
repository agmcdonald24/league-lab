// The league / team pick and the Sleeper username, remembered on this phone (localStorage). A shared link
// (?league=&team=) wins and is then remembered. Storage can be unavailable (private mode): every access is guarded.
import type { UserLeagues } from "./api";

const KEY_LEAGUE = "ll.league";
const KEY_USER = "ll.user"; // the Sleeper username typed on the sign-in screen
const KEY_USER_LEAGUES = "ll.userLeagues"; // the last answer of /api/leagues?username= (the picker renders at once)
const KEY_MFL = "ll.mflLeagues"; // I0-B: the MyFantasyLeague leagues opened on this phone (the switcher lists them)
const keyTeam = (league: string) => `ll.team.${league}`;
const KEY_PLATFORM = "ll.platform"; // ---- II-5: the setup screen's fantasy platform

/** A MyFantasyLeague league remembered on this phone (from GET /api/leagues?mfl=). */
export interface RememberedMfl {
  league_id: string; // "mfl:21861"
  name: string;
  scoring_label: string | null;
  total_rosters: number | null;
  roster_id: number | null;
  team_name: string | null;
}

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
  setTeam: (league: string, team: number | null) => {
    const before = read(keyTeam(league));
    write(keyTeam(league), team === null ? null : String(team));
    if (team !== null && before !== String(team)) remote?.team(league, team); // ---- IK-4: signed in → the server too
  },
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
  // ---- I0-B: MyFantasyLeague leagues (no username lookup there: the league link + the team picked)
  mflLeagues: (): RememberedMfl[] => {
    const raw = read(KEY_MFL);
    if (!raw) return [];
    try {
      const v = JSON.parse(raw) as RememberedMfl[];
      return Array.isArray(v) ? v.filter((x) => x && typeof x.league_id === "string") : [];
    } catch {
      return [];
    }
  },
  rememberMfl: (row: RememberedMfl) => {
    const rest = prefs.mflLeagues().filter((x) => x.league_id !== row.league_id);
    write(KEY_MFL, JSON.stringify([row, ...rest].slice(0, 10)));
    write(KEY_LEAGUE, row.league_id);
    if (row.roster_id !== null) write(keyTeam(row.league_id), String(row.roster_id));
    remote?.leagues([savedFromRemembered(row)]); // ---- IK-4: a league picked on the setup screen → the account too
  },
  // ---- end I0-B
  // ---- IK-3 (Wave I-K): every league opened on demand (MFL, a Sleeper link, ESPN, Yahoo) is remembered in the one list
  // above, keyed by its league key — the prefix says the provider (the switcher's "· ESPN" / "· Yahoo")
  rememberLeague: (row: RememberedMfl) => prefs.rememberMfl(row),
  remembered: (): RememberedMfl[] => prefs.mflLeagues(),
  // ---- end IK-3
  /** Forget the user (the "Not you?" link): the username and their league list; league / team picks stay. */
  forgetUser: () => {
    write(KEY_USER, null);
    write(KEY_USER_LEAGUES, null);
  },
  // ---- II-5 (Wave I-I): the fantasy platform picked on the setup screen (the next visit opens on it)
  platform: (): "sleeper" | "mfl" | "espn" | "yahoo" | null => {
    const v = read(KEY_PLATFORM);
    return v === "sleeper" || v === "mfl" || v === "espn" || v === "yahoo" ? v : null; // ---- IK-3: ESPN / Yahoo too
  },
  setPlatform: (p: "sleeper" | "mfl" | "espn" | "yahoo") => write(KEY_PLATFORM, p),
  // ---- end II-5
};

// ---- IK-4 (Wave I-K): accounts — signed in, the picks also go to the server (lib/account.svelte.ts sets `remote`);
// this browser's copy stays the cache the screens read (synchronously, as before). Signed out, nothing changes.
// What goes by itself: a league picked on the setup screen (`rememberMfl`), a new team pick in a league the account
// already holds (`setTeam`), the Stats views. A username's league list (re-read at every load) does not: those leagues
// go in with the Account page's one tap ("Save the N leagues on this device"), so a league removed from the account
// is not put back by the next load.
// The saved Stats views (II-3's `ll.stats.views`) are read and written here now, so they can follow the account.
const KEY_STATS_VIEWS = "ll.stats.views";
const KEY_STATS_TABLE = "ll.stats.table"; // ---- IM-2

/** A league as the account saves it (PUT /api/account/leagues). */
export interface SavedLeagueIn {
  league: string; // the app's key: a Sleeper id, "mfl:21861", "espn:4242", "yahoo:461.l.4242"
  season?: number | null;
  name?: string | null;
  team_id?: number | null;
  team_name?: string | null;
  scoring_label?: string | null;
  total_rosters?: number | null;
  default?: boolean;
}

export interface PrefsRemote {
  leagues(rows: SavedLeagueIn[]): void;
  team(league: string, team: number): void;
  pref(key: string, value: unknown): void;
}

let remote: PrefsRemote | null = null;
export function setRemote(r: PrefsRemote | null): void {
  remote = r;
}

export interface StatsView {
  name: string;
  qs: string;
}

export function savedFromRemembered(m: RememberedMfl): SavedLeagueIn {
  return { league: m.league_id, name: m.name, team_id: m.roster_id, team_name: m.team_name, scoring_label: m.scoring_label, total_rosters: m.total_rosters };
}

export function savedFromUser(v: UserLeagues): SavedLeagueIn[] {
  return v.leagues
    .filter((l) => l.roster_id !== null)
    .map((l) => ({ league: l.league_id, season: v.season, name: l.name, team_id: l.roster_id, team_name: l.team_name, scoring_label: l.scoring_label, total_rosters: l.total_rosters }));
}

export const accountPrefs = {
  statsViews: (): StatsView[] => {
    try {
      const v = JSON.parse(read(KEY_STATS_VIEWS) ?? "[]") as StatsView[];
      return Array.isArray(v) ? v.filter((x) => x && typeof x.name === "string" && typeof x.qs === "string") : [];
    } catch {
      return [];
    }
  },
  setStatsViews: (views: StatsView[], push = true) => {
    write(KEY_STATS_VIEWS, JSON.stringify(views));
    if (push) remote?.pref("stats.views", views);
  },
  // ---- IM-2 (Wave I-M): the Stats table's view last picked on this device ("key" / "full"; a phone and a desktop keep
  // their own, so it stays on this browser) — a saved view keeps it too (`view=` is in its address)
  statsTable: (): "key" | "full" | null => {
    const v = read(KEY_STATS_TABLE);
    return v === "key" || v === "full" ? v : null;
  },
  setStatsTable: (v: "key" | "full") => write(KEY_STATS_TABLE, v),
  // ---- end IM-2
  /** Every league this browser knows with the team picked in it (the account's "save these leagues"). */
  localLeagues: (): SavedLeagueIn[] => {
    const out: SavedLeagueIn[] = [];
    const seen = new Set<string>();
    const add = (r: SavedLeagueIn) => {
      if (seen.has(r.league)) return;
      seen.add(r.league);
      out.push({ ...r, team_id: prefs.team(r.league) ?? r.team_id ?? null });
    };
    const user = prefs.userLeagues();
    if (user) savedFromUser(user).forEach(add);
    prefs.mflLeagues().forEach((m) => add(savedFromRemembered(m)));
    const current = prefs.league();
    if (current && prefs.team(current) !== null) add({ league: current });
    return out;
  },
  /** The account's leagues into this browser's lists (a new device after sign-in): the switcher lists them, the team
   * picked in each comes back, and the default league opens when this browser had none. Nothing local is dropped. */
  restore: (rows: (SavedLeagueIn & { is_default?: boolean })[]) => {
    const known = prefs.mflLeagues();
    const fromUser = new Set((prefs.userLeagues()?.leagues ?? []).map((l) => l.league_id));
    const add: RememberedMfl[] = [];
    for (const r of rows) {
      if (typeof r.team_id === "number") write(keyTeam(r.league), String(r.team_id));
      if (fromUser.has(r.league) || known.some((k) => k.league_id === r.league)) continue;
      add.push({ league_id: r.league, name: r.name ?? r.league, scoring_label: r.scoring_label ?? null, total_rosters: r.total_rosters ?? null, roster_id: typeof r.team_id === "number" ? r.team_id : null, team_name: r.team_name ?? null });
    }
    if (add.length) write(KEY_MFL, JSON.stringify([...known, ...add].slice(0, 10)));
    const def = rows.find((r) => r.is_default) ?? rows[0];
    if (def && !prefs.league()) write(KEY_LEAGUE, def.league);
  },
};
// ---- end IK-4
