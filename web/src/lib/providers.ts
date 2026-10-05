// ---- II-5 (Wave I-I): the fantasy platforms — what each one gives League Lab (GET /api/providers, the API's
// `platforms.capabilities`; docs/PROVIDERS.md), the setup flow's lookups and their error words (INTERFACES.md § II-5).
// A screen that would show an empty list for a feature a platform does not give says `gapLine(...)` instead
// ("Transactions: not available for MFL leagues yet"): unavailable is said, never substituted (review § 9).
import { ApiError, get, Unauthorized, type Roster } from "./api";
import { isMfl, type LeagueCard } from "./leagues";

export type ProviderKey = "sleeper" | "mfl" | "espn" | "yahoo";
export type Platform = "sleeper" | "mfl" | "espn" | "yahoo"; // ---- IK-3: the setup flow offers all four (was sleeper | mfl)
export type FeatureKey = "scoring" | "roster_slots" | "matchups" | "players" | "waivers" | "transactions" | "team_assets" | "news";

export interface ProviderFeature {
  label: string;
  status: "yes" | "partial" | "no";
  words: string;
  unavailable: string | null; // "Transactions: not available for MFL leagues yet" when status is "no"
}

export interface Provider {
  provider: ProviderKey;
  name: string; // "MyFantasyLeague"
  short: string; // "MFL"
  status: "supported" | "not_supported" | "unverified" | "off"; // IK-3: "unverified" = as built, not checked on a live league yet; IL-5: "off" = the server's kill switch
  connect: { kind: "username" | "league_link" | "oauth" | "none"; label: string; example: string | null; where: string };
  features: Record<FeatureKey, ProviderFeature>;
  note?: string; // IK-3: ESPN's "Unofficial: …", Yahoo's "Through Yahoo's official … API"
  off?: string; // IL-5: "ESPN leagues: not available right now" (status "off")
}

export interface Providers {
  providers: Provider[];
  features: FeatureKey[];
  espn_private?: boolean; // ---- IK-3: the server reads private ESPN leagues with the user's own cookies (IK-1's switch)
  yahoo_configured?: boolean; // ---- IK-3: Yahoo's app keys are set: "Connect with Yahoo" works (else "coming soon")
  yahoo_pending?: boolean; // PO 2026-10-05: the keys are set but Yahoo has not opened the app's fantasy access yet
}

export const providersPath = "/api/providers";
export const sleeperLeaguePath = (text: string) => `/api/leagues?sleeper=${encodeURIComponent(text.trim())}`;

/** GET /api/leagues?sleeper=<league link or id>: the MFL answer's shape for a Sleeper league (no username needed). */
export interface SleeperLeague {
  platform: "sleeper";
  league: { league_id: string; name: string; season: number; total_rosters: number | null; scoring_label: string | null; url: string; platform: "sleeper" };
  teams: Roster[];
  roster_id: null;
  card: LeagueCard | null;
  capabilities: Provider;
}

/** A league key's platform ("mfl:70587" → mfl, "espn:4242" → espn, "yahoo:461.l.4242" → yahoo; Sleeper ids are bare). */
export const platformOf = (league: string | null | undefined): Platform => {
  const s = (league ?? "").trim().toLowerCase(); // ---- IK-3: four prefixes (was mfl | sleeper)
  if (isMfl(s)) return "mfl";
  if (s.startsWith("espn:")) return "espn";
  if (s.startsWith("yahoo:")) return "yahoo";
  return "sleeper";
};

/** A Sleeper league link or id typed in the username box (sleeper.com/leagues/<id>…, or the long number alone). */
export const looksLikeSleeperLeague = (text: string) => /sleeper\.(com|app)\/leagues\/\d{10,}/i.test(text) || /^\d{15,24}$/.test(text.trim());

/** The sentence for a feature this league's platform does not give, else null (also null while unknown). */
export async function gapLine(league: string | null | undefined, feature: FeatureKey): Promise<string | null> {
  if (!league) return null;
  try {
    const v = await get<Providers>(providersPath);
    return v.providers.find((p) => p.provider === platformOf(league))?.features[feature]?.unavailable ?? null;
  } catch {
    return null; // the line is a nicety: a failed read leaves the screen as it was
  }
}

/** A setup lookup: like `get`, but a failure keeps the API's error body (`code`, `fix`) for the specific words. Not
 * cached: a corrected username is asked again. */
export async function setupGet<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: "same-origin", headers: { Accept: "application/json" } });
  if (res.status === 401) throw new Unauthorized("sign in");
  if (!res.ok) {
    let body: { error?: string; detail?: string; code?: string; fix?: string } | null = null;
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, body?.error ?? body?.detail ?? res.statusText, body);
  }
  return (await res.json()) as T;
}

/** The setup error's key and words from an ApiError's body (null: an older answer without them). */
export function setupError(err: unknown): { code: string; words: string; fix: string | null } | null {
  if (!(err instanceof ApiError) || !err.body || typeof err.body !== "object") return null;
  const b = err.body as { code?: unknown; error?: unknown; fix?: unknown };
  if (typeof b.code !== "string" || typeof b.error !== "string") return null;
  return { code: b.code, words: b.error, fix: typeof b.fix === "string" ? b.fix : null };
}
// ---- end II-5

// ---- IK-3 (Wave I-K): ESPN (`espn:<id>`) and Yahoo (`yahoo:<game>.l.<id>`) in the setup flow. GET /api/leagues?espn=<id or
// link> / ?yahoo=<link, key or id> answer the MFL answer's shape; ?yahoo_me=1 lists the signed-in user's Yahoo leagues
// (IK-2's `ll_yahoo` cookie; always 200 — `configured` / `connected` say what to show). INTERFACES.md § IK-3.
export const espnLeaguePath = (text: string) => `/api/leagues?espn=${encodeURIComponent(text.trim())}`;
export const yahooLeaguePath = (text: string) => `/api/leagues?yahoo=${encodeURIComponent(text.trim())}`;
export const yahooMePath = "/api/leagues?yahoo_me=1";
export const yahooConnectPath = "/api/yahoo/connect"; // IK-2: redirects to Yahoo, back to /leagues?platform=yahoo
export const yahooDisconnectPath = "/api/yahoo/disconnect"; // IK-2: POST, clears the cookie
export const espnConnectPath = "/api/espn/connect"; // IK-1: POST {espn_s2, swid} → the sealed `ll_espn` cookie
export const PLATFORMS: { key: Platform; name: string }[] = [
  { key: "sleeper", name: "Sleeper" },
  { key: "mfl", name: "MyFantasyLeague" },
  { key: "espn", name: "ESPN" },
  { key: "yahoo", name: "Yahoo" },
];
export const isPlatform = (v: string | null | undefined): v is Platform => v === "sleeper" || v === "mfl" || v === "espn" || v === "yahoo";

/** The words after a league's name: "Sleeper" / "MFL" / "ESPN" / "Yahoo". */
export const providerShort = (league: string | null | undefined): string =>
  ({ sleeper: "Sleeper", mfl: "MFL", espn: "ESPN", yahoo: "Yahoo" })[platformOf(league)];

/** An ESPN or Yahoo league's card and team picker (the MFL answer's shape). */
export interface ProviderLeague {
  platform: "espn" | "yahoo";
  league: { league_id: string; name: string; season: number; total_rosters: number | null; scoring_label: string | null; url: string | null; platform: "espn" | "yahoo" };
  teams: Roster[];
  roster_id: number | null; // the team the link names (ESPN teamId=, Yahoo …/f1/<id>/<team>), else null
  unmapped: { espn_id?: string; yahoo_id?: string; name: string | null; position: string | null }[];
  players: number;
  mapped: number;
  scoring_note: string;
  card?: LeagueCard | null;
  capabilities: Provider;
  espn_private?: boolean;
  yahoo_configured?: boolean;
}

/** GET /api/leagues?yahoo_me=1. */
export interface YahooMe {
  platform: "yahoo";
  configured: boolean;
  pending?: boolean; // PO 2026-10-05: "coming soon" because Yahoo's approval of the app is pending (the note says so)
  connected: boolean;
  season: number;
  leagues: {
    league_id: string;
    name: string;
    season: number | null;
    total_rosters: number | null;
    scoring_label: string | null;
    roster_id: number | null;
    team_name: string | null;
    url: string | null;
    card: LeagueCard | null;
  }[];
  note: string | null;
}

/** POST a small JSON body (the ESPN cookie form, Yahoo's disconnect); the API's error words when it refuses. */
export async function setupPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (res.status === 401) throw new Unauthorized("sign in");
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* not JSON */
  }
  if (!res.ok) {
    const b = (data ?? {}) as { error?: string; detail?: string };
    throw new ApiError(res.status, b.error ?? b.detail ?? res.statusText, data);
  }
  return data as T;
}
// ---- end IK-3
