// The few bits of markdown the pages' sentences use (**bold**, [name](/player/<id>), "  \n" line breaks,
// "- " bullets), rendered to HTML. Everything is HTML-escaped FIRST, so the output is safe for {@html}.
// Only same-site paths and https links survive; a player link gets the current league and team appended.

const ESC: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ESC[c]);
}

export interface LinkContext {
  league?: string | null;
  team?: number | string | null;
}

export function withContext(href: string, ctx: LinkContext): string {
  if (!inAppPath(href)) return href; // ---- IM-3 fix: "//host" is not ours
  const [path, query = ""] = href.split("?");
  const qs = new URLSearchParams(query);
  if (ctx.league && !qs.has("league")) qs.set("league", String(ctx.league));
  if (ctx.team != null && ctx.team !== "" && !qs.has("team")) qs.set("team", String(ctx.team));
  const s = qs.toString();
  return s ? `${path}?${s}` : path;
}

// ---- IM-3 fix (the Wave I-M review): provider text (a team or league name) reaches these sentences, so a link is kept
// only when it is ours: an in-app path is "/" followed by neither "/" nor "\" ("//evil.example" and "/\evil.example" are
// other sites to a browser), and an outside link must be https to a host the app links to itself. Anything else is
// the label as plain text.
const LINK_HOSTS = ["isuckatfantasy.io", "espn.com", "sleeper.com", "sleeper.app", "myfantasyleague.com", "yahoo.com", "nfl.com", "draftkings.com", "fanduel.com"];
export function inAppPath(raw: string): boolean {
  return raw.startsWith("/") && !/^\/[/\\]/.test(raw);
}
export function trustedHttps(raw: string): boolean {
  if (!raw.startsWith("https://")) return false;
  try {
    const u = new URL(raw);
    if (u.username || u.password || u.port) return false;
    const h = u.hostname.toLowerCase();
    return LINK_HOSTS.some((d) => h === d || h.endsWith(`.${d}`));
  } catch {
    return false;
  }
}

function inline(text: string, ctx: LinkContext): string {
  let out = escapeHtml(text);
  // links: [label](href) — label and href are already escaped; only our "/..." paths and https to our hosts stay links
  out = out.replace(/\[([^\]]*)\]\(([^)\s]*)\)/g, (_m, label: string, href: string) => {
    const raw = href.replace(/&amp;/g, "&");
    if (inAppPath(raw)) return `<a href="${escapeHtml(withContext(raw, ctx))}" class="ll-link">${label}</a>`;
    if (trustedHttps(raw)) return `<a href="${escapeHtml(raw)}" rel="noopener" target="_blank" class="ll-link">${label}</a>`;
    return label;
  });
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/ {2}\n/g, "<br>");
  return out;
}

/** Markdown → HTML: paragraphs, "- " bullet lists, inline bold / links / hard breaks. */
export function md(text: string | null | undefined, ctx: LinkContext = {}): string {
  if (!text) return "";
  const lines = text.split("\n");
  if (lines.every((l) => l.startsWith("- ") || l.trim() === "")) {
    const items = lines.filter((l) => l.startsWith("- ")).map((l) => `<li>${inline(l.slice(2), ctx)}</li>`);
    return `<ul class="ll-list">${items.join("")}</ul>`;
  }
  return inline(text, ctx).replace(/\n/g, " ");
}

/** The plain text of a markdown sentence (labels instead of links, no stars). */
export function plain(text: string | null | undefined): string {
  if (!text) return "";
  return text.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/\*\*/g, "").replace(/ {2}\n/g, " ");
}
