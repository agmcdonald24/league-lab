// ---- II-5 (Wave I-I): the fantasy platforms — what each one gives League Lab (GET /api/providers, the API's
// `platforms.capabilities`; docs/PROVIDERS.md), the setup flow's lookups and their error words (INTERFACES.md § II-5).
// A screen that would show an empty list for a feature a platform does not give says `gapLine(...)` instead
// ("Transactions: not available for MFL leagues yet"): unavailable is said, never substituted (review § 9).
import { ApiError, get, Unauthorized, type Roster } from "./api";
import { isMfl, type LeagueCard } from "./leagues";

export type ProviderKey = "sleeper" | "mfl" | "espn" | "yahoo";
export type Platform = "sleeper" | "mfl"; // the two the setup flow offers (ESPN / Yahoo: not supported yet)
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
  status: "supported" | "not_supported";
  connect: { kind: "username" | "league_link" | "none"; label: string; example: string | null; where: string };
  features: Record<FeatureKey, ProviderFeature>;
}

export interface Providers {
  providers: Provider[];
  features: FeatureKey[];
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

/** A league key's platform ("mfl:70587" → mfl; Sleeper ids are bare digits). */
export const platformOf = (league: string | null | undefined): Platform => (isMfl(league) ? "mfl" : "sleeper");

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
