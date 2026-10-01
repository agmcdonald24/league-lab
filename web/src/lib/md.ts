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
  if (!href.startsWith("/")) return href;
  const [path, query = ""] = href.split("?");
  const qs = new URLSearchParams(query);
  if (ctx.league && !qs.has("league")) qs.set("league", String(ctx.league));
  if (ctx.team != null && ctx.team !== "" && !qs.has("team")) qs.set("team", String(ctx.team));
  const s = qs.toString();
  return s ? `${path}?${s}` : path;
}

function inline(text: string, ctx: LinkContext): string {
  let out = escapeHtml(text);
  // links: [label](href) — label and href are already escaped; only "/..." and "https://..." are kept as links
  out = out.replace(/\[([^\]]*)\]\(([^)\s]*)\)/g, (_m, label: string, href: string) => {
    const raw = href.replace(/&amp;/g, "&");
    if (raw.startsWith("/")) return `<a href="${escapeHtml(withContext(raw, ctx))}" class="ll-link">${label}</a>`;
    if (raw.startsWith("https://")) return `<a href="${escapeHtml(raw)}" rel="noopener" target="_blank" class="ll-link">${label}</a>`;
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
