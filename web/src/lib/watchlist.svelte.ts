// ---- IL-5 (Wave I-L): the watchlist — the players a signed-in person saved (IK-4's `accounts.watchlist`).
// * Watch / Watching on the drawer (components/PlayerPane.svelte) saves a player for the account, whatever league is on
//   screen (`league: null`: a player, not a league's row); un-watching removes every row of that player.
// * /watchlist (routes/Watchlist.svelte) reads GET /api/account/watchlist?league=&team=: each player as the drawer's
//   card has him in the league on screen (name, position, NFL team, his status today, this week's projection, free
//   agent / rostered by whom).
// * GA: `watchlist_add` / `watchlist_remove` with the player's id and where the tap was (ids only, no PII).
import { account, AccountError, GateClosed } from "./account.svelte";
import { trackWatchlist } from "./analytics";

export interface WatchOwner {
  kind: "yours" | "free_agent" | "rostered" | "not_in_pool";
  team_id: number | null;
  team_name: string | null;
  words: string;
}

export interface WatchRow {
  player_key: string;
  player_name: string | null;
  position: string | null;
  team: string | null;
  status: string | null; // the injury designation after the availability overlay; null = none
  proj_points: number | null;
  week: number | null;
  owner: WatchOwner | null;
  read: boolean;
  words: string | null; // why a row could not be read
}

export interface WatchAnswer {
  league: string | null;
  league_name: string | null;
  week: number | null;
  count: number;
  shown: number;
  players: WatchRow[];
}

const qs = (pairs: [string, string | number | null | undefined][]): string => {
  const s = pairs
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join("&");
  return s ? `?${s}` : "";
};

export const watchlistPath = (league: string | null, team: number | null): string =>
  `/api/account/watchlist${qs([["league", league], ["team", team]])}`;

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

/** Signed in with accounts on: the drawer offers Watch. */
export function canWatch(): boolean {
  return !!(account.status?.enabled && account.status.signed_in && account.me);
}

export function isWatched(key: string | null | undefined): boolean {
  return !!key && !!account.me?.watchlist.some((w) => w.player_key === key);
}

/** Save a player (optimistic: the button turns at once; a refusal puts it back and throws). */
export async function watch(key: string, origin: string | null): Promise<void> {
  const me = account.me;
  if (!me || isWatched(key)) return;
  const row = { league_key: null, league: null, player_key: key, added_at: null };
  me.watchlist = [...me.watchlist, row];
  try {
    await call("PUT", "/api/account/watchlist", { player_key: key, league: null });
    trackWatchlist("add", key, origin);
  } catch (e) {
    me.watchlist = me.watchlist.filter((w) => w !== row);
    throw e;
  }
}

/** Remove a player: every row of him (one saved with a league and one without are the same player). */
export async function unwatch(key: string, origin: string | null): Promise<void> {
  const me = account.me;
  if (!me) return;
  const mine = me.watchlist.filter((w) => w.player_key === key);
  if (!mine.length) return;
  me.watchlist = me.watchlist.filter((w) => w.player_key !== key);
  try {
    for (const w of mine) {
      await call("DELETE", `/api/account/watchlist${qs([["player_key", key], ["league", w.league]])}`);
    }
    trackWatchlist("remove", key, origin);
  } catch (e) {
    me.watchlist = [...me.watchlist, ...mine];
    throw e;
  }
}

export const loadWatchlist = (league: string | null, team: number | null) => call<WatchAnswer>("GET", watchlistPath(league, team));
