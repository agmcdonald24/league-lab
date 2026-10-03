// ---- U-1 (Wave I-F): one count per screen view — which screen, which league and team number, when; nothing about
// the person (docs/HOSTING.md § "Usage"). POST /api/usage {screen, league, roster_id}: the server adds the time, the
// platform, the release and the day's random session cookie. navigator.sendBeacon where available (it never holds
// up the page, and survives the tab closing), else a keepalive fetch; every failure is ignored.

let last = "";

/** Count a screen view. The same screen, league and team twice in a row (a filter, a sort, the pane) count once. */
export function countView(screen: string, league: string | null, team: number | null): void {
  const key = `${screen}|${league ?? ""}|${team ?? ""}`;
  if (key === last || typeof window === "undefined") return;
  last = key;
  const body = JSON.stringify({ screen, league, roster_id: team });
  try {
    // text/plain: a "simple" beacon every browser sends; the server reads the JSON either way
    if (navigator.sendBeacon?.("/api/usage", new Blob([body], { type: "text/plain;charset=UTF-8" }))) return;
  } catch {
    // fall through to fetch
  }
  try {
    fetch("/api/usage", {
      method: "POST",
      body,
      keepalive: true,
      credentials: "same-origin",
      headers: { "Content-Type": "text/plain;charset=UTF-8" },
    }).catch(() => {});
  } catch {
    // usage is never load-bearing
  }
}
