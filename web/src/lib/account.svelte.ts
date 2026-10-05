// Accounts, phase 1 (Wave I-K, IK-4; docs/ACCOUNTS.md § "Built, phase 1"): sign in with an emailed link; the leagues,
// the team in each, the default league and the saved Stats views follow the account to any device.
// * GET /api/account/status says whether the server has accounts on (`enabled`) and who is signed in. Off, or any
//   failure (an older server, the fixtures): nothing about accounts shows anywhere — guest use is exactly as before.
// * The link the email holds is `/account#signin=<token>`: the fragment never reaches a server; the Account page posts
//   it (POST /api/account/verify) after one tap, and the server answers with the `ll_session` cookie (HttpOnly).
// * Signed in, lib/prefs.ts hands the picks to the server too (`setRemote`): this browser's copy stays the cache the
//   screens read, the server's is the one another device restores from. A failed push is quiet (the local copy holds).
import { accountPrefs, setRemote, type SavedLeagueIn, type StatsView } from "./prefs";

export interface AccountStatus {
  enabled: boolean;
  reason: string | null; // off | no_secret | no_mailer | not_ready
  signed_in: boolean;
  email: string | null;
  mailer: string | null;
  session_days: number;
}

export interface SavedLeague {
  league: string; // the app's key
  league_key: string; // provider:season:external_id
  provider: "sleeper" | "mfl" | "espn" | "yahoo";
  season: number;
  external_id: string;
  name: string | null;
  team_id: number | string | null;
  team_name: string | null;
  scoring_label: string | null;
  total_rosters: number | null;
  is_default: boolean;
  last_sync_at: string | null;
  sync_status: string | null;
  added_at: string | null;
}

export interface Me {
  email: string;
  created_at: string | null;
  default_league: string | null;
  leagues: SavedLeague[];
  preferences: { scope: string; key: string; value: unknown; updated_at: string | null }[];
  watchlist: { league_key: string | null; league: string | null; player_key: string; added_at: string | null }[];
  // ---- IL-5: the Yahoo / ESPN connections the account keeps (never a token)
  connections?: { provider: "yahoo" | "espn"; external_user_id: string; connected_at: string | null; status: string; last_sync_at: string | null }[];
}

/** The beta password's 401 (no `code`): the app's password screen, as for any other call. */
export class GateClosed extends Error {}

/** An account answer that is not OK: the API's words and its `code` (signed_out, rate_limited, link_invalid, …). */
export class AccountError extends Error {
  constructor(
    public status: number,
    public code: string | null,
    message: string,
  ) {
    super(message);
  }
}

const OFF: AccountStatus = { enabled: false, reason: "unreachable", signed_in: false, email: null, mailer: null, session_days: 90 };

export const account = $state<{ status: AccountStatus | null; me: Me | null }>({ status: null, me: null });

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data: { code?: string; error?: string; detail?: string } | null = null;
  try {
    data = await res.json();
  } catch {
    /* not JSON */
  }
  if (res.status === 401 && !data?.code) throw new GateClosed("sign in");
  if (!res.ok) throw new AccountError(res.status, data?.code ?? null, data?.error ?? data?.detail ?? res.statusText);
  return data as T;
}

let statusAsked: Promise<AccountStatus> | null = null;

/** Is the feature on, who is signed in (asked once per page load; `force` asks again). Never throws. */
export function loadStatus(force = false): Promise<AccountStatus> {
  if (statusAsked && !force) return statusAsked;
  statusAsked = call<AccountStatus>("GET", "/api/account/status")
    .then((s) => (s && typeof s.enabled === "boolean" ? s : OFF))
    .catch(() => OFF)
    .then(async (s) => {
      account.status = s;
      if (s.enabled && s.signed_in) await loadMe().catch(() => {});
      else {
        account.me = null;
        setRemote(null);
      }
      return s;
    });
  return statusAsked;
}

export async function loadMe(): Promise<Me | null> {
  try {
    const me = await call<Me>("GET", "/api/account/me");
    account.me = me;
    attach();
    return me;
  } catch (e) {
    if (e instanceof AccountError && e.code === "signed_out") {
      account.me = null;
      if (account.status) account.status = { ...account.status, signed_in: false, email: null };
      setRemote(null);
      return null;
    }
    throw e;
  }
}

export const requestLink = (email: string) => call<{ ok: boolean; sent: boolean; minutes: number }>("POST", "/api/account/login", { email });

/** The link's token → a session on this device; the account's leagues and views come into this browser. */
export async function verifyLink(token: string): Promise<Me | null> {
  await call("POST", "/api/account/verify", { token });
  statusAsked = null;
  await loadStatus(true);
  if (account.me) restore(account.me);
  return account.me;
}

/** The account's picks into this browser (the switcher, the team per league, the default league, Stats views). */
export function restore(me: Me): void {
  accountPrefs.restore(me.leagues.map((l) => ({ ...l, team_id: typeof l.team_id === "number" ? l.team_id : null })));
  const server = statsViewsOf(me);
  const local = accountPrefs.statsViews();
  const merged = [...server, ...local.filter((v) => !server.some((s) => s.name === v.name))].slice(-8);
  accountPrefs.setStatsViews(merged, false);
  if (merged.length !== server.length) void pushPref("stats.views", merged);
}

function statsViewsOf(me: Me): StatsView[] {
  const p = me.preferences.find((x) => x.scope === "global" && x.key === "stats.views");
  return Array.isArray(p?.value) ? (p.value as StatsView[]).filter((v) => v && typeof v.name === "string" && typeof v.qs === "string") : [];
}

/** The leagues on this browser that the account does not have yet ("Save these N leagues"). */
export function unsaved(me: Me | null): SavedLeagueIn[] {
  if (!me) return [];
  return accountPrefs.localLeagues().filter((l) => !me.leagues.some((s) => s.league === l.league));
}

export async function saveLeagues(rows: SavedLeagueIn[]): Promise<void> {
  if (!rows.length) return;
  await call("PUT", "/api/account/leagues", { leagues: rows });
  await loadMe();
}

export async function setDefault(league: string, season: number): Promise<void> {
  await call("PUT", "/api/account/default", { league, season });
  await loadMe();
}

export async function removeLeague(leagueKey: string): Promise<void> {
  await call("DELETE", `/api/account/leagues/${encodeURIComponent(leagueKey)}`);
  await loadMe();
}

export async function signOut(everywhere = false): Promise<void> {
  await call("POST", "/api/account/logout", { everywhere });
  account.me = null;
  setRemote(null);
  if (account.status) account.status = { ...account.status, signed_in: false, email: null };
}

export async function deleteAccount(): Promise<void> {
  await call("DELETE", "/api/account");
  account.me = null;
  setRemote(null);
  if (account.status) account.status = { ...account.status, signed_in: false, email: null };
}

function pushPref(key: string, value: unknown): Promise<void> {
  return call("PUT", "/api/account/preferences", { scope: "global", key, value })
    .then(() => {})
    .catch(() => {});
}

/** Signed in: lib/prefs.ts's picks go to the server too (quietly; the local copy stays the cache). */
function attach(): void {
  setRemote({
    leagues: (rows) => {
      const fresh = rows.filter((r) => r.team_id !== null && r.team_id !== undefined);
      if (fresh.length) void call("PUT", "/api/account/leagues", { leagues: fresh }).then(() => loadMe()).catch(() => {});
    },
    team: (league, team) => {
      const saved = account.me?.leagues.find((l) => l.league === league);
      if (!saved || saved.team_id === team) return; // only a league the account holds; a shared link's league stays local
      void call("PUT", "/api/account/leagues", { leagues: [{ league, season: saved.season, team_id: team }] })
        .then(() => loadMe())
        .catch(() => {});
    },
    pref: (key, value) => void pushPref(key, value),
  });
}

/** The sign-in token in this page's address (`#signin=<token>`), if any. */
export function linkToken(): string | null {
  const m = location.hash.match(/(?:^#|&)signin=([A-Za-z0-9_-]{20,100})/);
  return m ? m[1] : null;
}

/** Take the token out of the address (Back and a shared screenshot never show it). */
export function dropLinkToken(): void {
  if (location.hash) history.replaceState(history.state, "", location.pathname + location.search);
}

export const PROVIDER_LABEL: Record<SavedLeague["provider"], string> = { sleeper: "Sleeper", mfl: "MFL", espn: "ESPN", yahoo: "Yahoo" };
