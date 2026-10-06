// One API answer for a screen: the cached answer at once (Back renders synchronously), else a fetch; the error in
// plain words (the Wave F pages' wording). A newer path wins over a late answer for an older one.
import { ApiError, forget, get, peek, Unauthorized } from "./api";
import { restoreScroll } from "./router.svelte";
import { APP_NAME } from "./brand";

// ---- IH-1 (Wave I-H): what went wrong, as a kind a card can act on (components/ErrorCard.svelte), and the words.
//   down     — the server did not answer at all (no network, the process down, the host's own 502 / 503 / 504 page)
//   slow     — no answer after SLOW_MS (the request keeps going: the answer shows if it arrives; Try again asks anew)
//   server   — a 500: something broke on our side (the card names /api/status, which says whether the data is up)
//   upstream — our 502: Sleeper or MyFantasyLeague did not answer
//   notready — our 503 "the numbers are not ready yet" (the nightly is restoring the copy); busy — our 503 "busy"
//   notfound — a 404 (the screen's own words); other — anything else (the API's own sentence)
// A 401 is never a failure: it goes back to the password screen (App.svelte, "Signed out — sign in again").
// ---- IM-3: limited — our 429 (the rate limiter: "Too many requests from this connection. Try again in N seconds.");
//            needsleague — a decision screen asked without a league (`ref:` keys): "Open your league to see this."
export type FailureKind = "down" | "slow" | "server" | "upstream" | "notready" | "busy" | "notfound" | "other" | "limited" | "needsleague";
export interface Failure {
  kind: FailureKind;
  words: string;
  status: number | null;
}
export const SLOW_MS = 25_000;
export const STATUS_PATH = "/api/status";
const OURS_502 = /did not answer/i; // main.py's handler: "Sleeper did not answer" / "MyFantasyLeague did not answer"
const OURS_503 = /not ready|busy/i; // main.py's handlers: "the numbers are not ready yet" / "busy, try again in a minute"

export function failureOf(e: unknown): Failure {
  if (e instanceof ApiError) {
    const s = e.status;
    const code = (e.body as { code?: string } | null)?.code; // ---- IM-3
    if (s === 429 || code === "rate_limited")
      return { kind: "limited", status: s, words: /^Too many requests/.test(e.message) ? e.message : "Too many requests from this connection. Try again in a minute." };
    if (code === "needs_league") return { kind: "needsleague", status: s, words: e.message || "Open your league to see this." };
    if (s === 404)
      return { kind: "notfound", status: s, words: /league/i.test(e.message) ? `${APP_NAME} cannot find this league on Sleeper. Pick another above.` : e.message };
    if (s === 502 && OURS_502.test(e.message))
      return { kind: "upstream", status: s, words: `${/MyFantasyLeague/i.test(e.message) ? "MyFantasyLeague" : "Sleeper"} did not answer. Try again in a minute.` };
    if (s === 503 && /busy/i.test(e.message)) return { kind: "busy", status: s, words: "Busy right now. Try again in a minute." };
    if (s === 503 && OURS_503.test(e.message)) return { kind: "notready", status: s, words: "The numbers are not ready yet. Try again in a few minutes." };
    if (s === 502 || s === 503 || s === 504)
      return { kind: "down", status: s, words: `${APP_NAME} is not answering right now (error ${s}). It is usually back within a few minutes.` };
    if (s >= 500)
      return { kind: "server", status: s, words: `Our server hit an error (${s}). The status page says whether the data is up and when it was last updated.` };
    return { kind: "other", status: s, words: e.message };
  }
  // fetch() rejects with a TypeError when nothing answered: "Failed to fetch" (Chrome), "Load failed" (Safari),
  // "NetworkError when attempting to fetch resource." (Firefox)
  if (e instanceof TypeError) return { kind: "down", status: null, words: `Cannot reach ${APP_NAME} right now. Check your connection, then try again.` };
  return { kind: "other", status: null, words: e instanceof Error ? e.message : String(e) };
}

export const SLOW_WORDS = `${APP_NAME} is taking longer than usual to answer.`;
// ---- end IH-1

export function errorWords(e: unknown): string {
  return failureOf(e).words; // ---- IH-1: one wording for every screen (the card and the screens' own lines)
}

export class Remote<T> {
  data = $state<T | null>(null);
  error = $state<string | null>(null);
  loading = $state(false);
  failure = $state<Failure | null>(null); // ---- IH-1: the error as a kind (null: none); `slow` while still waiting
  #path: string | null = null;
  #onauth: () => void = () => {};
  #slow: ReturnType<typeof setTimeout> | null = null;
  #map: (raw: unknown) => T;

  /** `map`: the API's answer → the screen's shape (lib/shapes.ts); default as is. */
  constructor(map?: (raw: unknown) => T) {
    this.#map = map ?? ((raw) => raw as T);
  }

  /** Load `path` (null clears). `keep`: hold the previous answer on screen while the new one loads (no flash). */
  load(path: string | null, onauth: () => void, keep = false): void {
    this.#path = path;
    this.#onauth = onauth;
    this.error = null;
    this.failure = null;
    this.#clearSlow();
    if (path === null) {
      this.data = null;
      return;
    }
    const hit = peek<unknown>(path);
    if (hit !== undefined) {
      this.data = this.#map(hit);
      this.loading = false;
      restoreScroll();
      return;
    }
    if (!keep) this.data = null;
    this.loading = true;
    // ---- IH-1: not a spinner forever — after SLOW_MS the card says so and offers Try again; the request keeps going
    this.#slow = setTimeout(() => {
      // an answer kept on screen while the next loads (keep) is not "waiting": only an empty screen says so
      if (this.#path === path && this.loading && this.data === null) this.failure = { kind: "slow", status: null, words: SLOW_WORDS };
    }, SLOW_MS);
    get<unknown>(path)
      .then((d) => {
        if (this.#path !== path) return;
        this.#clearSlow();
        this.data = this.#map(d);
        this.loading = false;
        this.failure = null;
        restoreScroll();
      })
      .catch((e) => {
        if (this.#path !== path) return;
        this.#clearSlow();
        this.loading = false;
        if (e instanceof Unauthorized) onauth();
        else {
          this.failure = failureOf(e); // ---- IH-1
          this.error = this.failure.words;
        }
      });
  }

  /** ---- IH-1: ask again (the card's Try again): the answer in flight, if any, is let go. */
  retry(): void {
    if (this.#path === null) return;
    forget(this.#path);
    this.load(this.#path, this.#onauth, true);
  }

  #clearSlow(): void {
    if (this.#slow !== null) clearTimeout(this.#slow);
    this.#slow = null;
  }
}
