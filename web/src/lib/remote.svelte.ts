// One API answer for a screen: the cached answer at once (Back renders synchronously), else a fetch; the error in
// plain words (the Wave F pages' wording). A newer path wins over a late answer for an older one.
import { ApiError, get, peek, Unauthorized } from "./api";
import { restoreScroll } from "./router.svelte";

export function errorWords(e: unknown): string {
  if (e instanceof ApiError && e.status === 404) return /league/i.test(e.message) ? "League Lab cannot find this league on Sleeper. Pick another above." : e.message;
  if (e instanceof ApiError && e.status === 502) return "Sleeper did not answer. Try again in a minute.";
  if (e instanceof ApiError && e.status === 503) return "The numbers are not ready yet. Try again in a few minutes.";
  return e instanceof Error ? e.message : String(e);
}

export class Remote<T> {
  data = $state<T | null>(null);
  error = $state<string | null>(null);
  loading = $state(false);
  #path: string | null = null;
  #map: (raw: unknown) => T;

  /** `map`: the API's answer → the screen's shape (lib/shapes.ts); default as is. */
  constructor(map?: (raw: unknown) => T) {
    this.#map = map ?? ((raw) => raw as T);
  }

  /** Load `path` (null clears). `keep`: hold the previous answer on screen while the new one loads (no flash). */
  load(path: string | null, onauth: () => void, keep = false): void {
    this.#path = path;
    this.error = null;
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
    get<unknown>(path)
      .then((d) => {
        if (this.#path !== path) return;
        this.data = this.#map(d);
        this.loading = false;
        restoreScroll();
      })
      .catch((e) => {
        if (this.#path !== path) return;
        this.loading = false;
        if (e instanceof Unauthorized) onauth();
        else this.error = errorWords(e);
      });
  }
}
