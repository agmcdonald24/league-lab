// ---- IY-1 / IY-2 (Wave I-Y): a post on X, shown in X's own frame once X has laid it out (md.ts `xBlock`, PostBody).
// The frame is https://platform.twitter.com/embed/Tweet.html — a page of X's that renders the post with no script on
// ours. It tells its parent its height with a message from https://platform.twitter.com:
//   {"twttr.embed": {"method": "twttr.private.resize", "params": [{"height": <n>, …}]}}   (an object or a JSON string)
// Only that origin, only from one of our X frames, only a number, clamped to 200–2000 px. Until the first one comes the
// frame is out of sight and the card is the block; if none comes, the card stays (IY-2).
export const X_ORIGIN = "https://platform.twitter.com";
export const X_SANDBOX = "allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox";
// ---- IY-2: no tap. The frame is made when the block comes within X_NEAR of the screen, kept out of sight (opacity 0,
// absolutely placed over the card's own box: it takes no room, and Chrome still counts it as on screen, so X renders
// and measures — a frame with visibility: hidden or no height is throttled and X never sends its size), and swapped in
// on its first resize message. No resize within X_GIVE_UP_MS: the frame is removed and the card stays.
export const X_NEAR = "600px 0px";
export const X_GIVE_UP_MS = 10_000;
const X_ID = /^\d{1,25}$/;

export function isXId(id: string | null | undefined): id is string {
  return typeof id === "string" && X_ID.test(id);
}

/** The frame's address for a post id (checked), light or dark like the page. */
export function xFrameSrc(id: string, dark = false): string | null {
  if (!isXId(id)) return null;
  return `${X_ORIGIN}/embed/Tweet.html?id=${id}&dnt=true&theme=${dark ? "dark" : "light"}`;
}

/** The height a resize message asks for, clamped; null for anything else. */
export function xResizeHeight(data: unknown): number | null {
  let d: unknown = data;
  if (typeof d === "string") {
    if (d.length > 20_000) return null;
    try {
      d = JSON.parse(d);
    } catch {
      return null;
    }
  }
  if (!d || typeof d !== "object") return null;
  const e = (d as Record<string, unknown>)["twttr.embed"];
  if (!e || typeof e !== "object") return null;
  const { method, params } = e as { method?: unknown; params?: unknown };
  if (method !== "twttr.private.resize" || !Array.isArray(params) || !params.length) return null;
  const p = params[0];
  const h = p && typeof p === "object" ? (p as { height?: unknown }).height : undefined;
  const n = typeof h === "number" ? h : typeof h === "string" && /^\d{1,6}(\.\d+)?$/.test(h) ? Number(h) : NaN;
  if (!Number.isFinite(n)) return null;
  return Math.min(2000, Math.max(200, Math.round(n)));
}

interface FrameLike {
  contentWindow: unknown;
  style: { height: string };
}
/** A message event → the frame it resized (its height set), or null: wrong origin, not one of `frames`, not a resize. */
export function onXMessage(e: { origin: string; source: unknown; data: unknown }, frames: Iterable<FrameLike>): FrameLike | null {
  if (e.origin !== X_ORIGIN || !e.source) return null;
  const h = xResizeHeight(e.data);
  if (h === null) return null;
  for (const f of frames) {
    if (f.contentWindow && f.contentWindow === e.source) {
      f.style.height = `${h}px`;
      return f;
    }
  }
  return null;
}
