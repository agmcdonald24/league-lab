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

function inline(text: string, ctx: LinkContext, more?: (html: string) => string): string {
  // ---- IN-1 fix round: a link's opening tag is held aside (U+E001) until the end, so nothing marked up later — bold,
  // italic, a picture or code (mdDoc's U+E000 placeholders) — can land inside its href; a target holding a placeholder
  // is not a link at all. U+E001 in the text itself is dropped (it is the mark).
  const tags: string[] = [];
  const tag = (html: string) => `\uE001${tags.push(html) - 1}\uE001`;
  let out = escapeHtml(text.replace(/\uE001/g, ""));
  // links: [label](href) — label and href are already escaped; only our "/..." paths and https to our hosts stay links
  out = out.replace(/\[([^\]]*)\]\(([^)\s]*)\)/g, (_m, label: string, href: string) => {
    const raw = href.replace(/&amp;/g, "&");
    if (/[\uE000\uE001]/.test(raw)) return label; // a picture or code inside the target: the words, never a link
    if (inAppPath(raw)) return `${tag(`<a href="${escapeHtml(withContext(raw, ctx))}" class="ll-link">`)}${label}</a>`;
    if (trustedHttps(raw)) return `${tag(`<a href="${escapeHtml(raw)}" rel="noopener" target="_blank" class="ll-link">`)}${label}</a>`;
    return label;
  });
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/ {2}\n/g, "<br>");
  if (more) out = more(out);
  return out.replace(/\uE001(\d+)\uE001/g, (_m, i: string) => tags[Number(i)]);
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

// ---- IN-1 (Wave I-N): whole documents — the blog's posts (blog/*.md, docs/BLOG.md). `mdDoc` knows, besides the
// sentences' bold / links / breaks / bullets: headings (# → h2: the page's title is the only h1), *italic*, `code`,
// fenced code blocks, ordered lists, block quotes, tables (wrapped in a box that scrolls sideways by itself), pictures
// from /blog/img/ only, and a horizontal rule. Same rule as `md`: every character is HTML-escaped FIRST, then only
// the tags this file writes are added — raw HTML in a post is shown as text, never run. `md` above is unchanged.
const BLOG_IMG = /^\/blog\/img\/[a-z0-9][a-z0-9_-]{0,79}\.(png|jpe?g|webp)$/;

function inlineDoc(text: string, ctx: LinkContext): string {
  // code spans and pictures are held aside (their own escaped HTML) while `inline` escapes and marks up the rest
  const held: string[] = [];
  const hold = (html: string) => `\uE000${held.push(html) - 1}\uE000`;
  let rest = text.replace(/`([^`\n]+)`/g, (_m, c: string) => hold(`<code>${escapeHtml(c)}</code>`));
  // pictures: ![alt](/blog/img/name.png) — our own folder only, else the words
  rest = rest.replace(/!\[([^\]]*)\]\(([^)\s]*)\)/g, (_m, alt: string, src: string) =>
    hold(BLOG_IMG.test(src) ? `<img src="${src}" alt="${escapeHtml(alt)}" loading="lazy" decoding="async" class="ll-md-img">` : escapeHtml(alt)),
  );
  // escapes, then links / bold / hard breaks, then italic — all before the links' tags come back (none inside an href)
  const out = inline(rest, ctx, (h) => h.replace(/(^|[\s(])\*([^*\s][^*]*?)\*(?=[\s).,;:!?]|$)/g, "$1<em>$2</em>"));
  return out.replace(/\uE000(\d+)\uE000/g, (_m, i: string) => held[Number(i)]);
}

const isRule = (l: string) => /^ {0,3}([-*_])( *\1){2,} *$/.test(l);
const isFence = (l: string) => /^ {0,3}```/.test(l);
const isHeading = (l: string) => /^#{1,6} +\S/.test(l);
const isQuote = (l: string) => /^ {0,3}> ?/.test(l);
const isBullet = (l: string) => /^ {0,3}[-*] +\S/.test(l);
const isOrdered = (l: string) => /^ {0,3}\d{1,3}[.)] +\S/.test(l);
const isTableRow = (l: string) => /^ *\|.*\| *$/.test(l);
const isTableSep = (l: string) => /^ *\|( *:?-+:? *\|)+ *$/.test(l);
const cells = (l: string) =>
  l
    .trim()
    .replace(/^\||\|$/g, "")
    .split(/(?<!\\)\|/)
    .map((c) => c.trim().replace(/\\\|/g, "|"));

/** A whole markdown document → HTML (safe for {@html}: escaped first). The blog's renderer. */
export function mdDoc(text: string | null | undefined, ctx: LinkContext = {}): string {
  if (!text) return "";
  const lines = text.replace(/\uE000/g, "").replace(/\r\n?/g, "\n").split("\n"); // U+E000: the placeholders' mark (a private-use character)
  const out: string[] = [];
  let i = 0;
  const para: string[] = [];
  const flush = () => {
    if (para.length) out.push(`<p>${inlineDoc(para.join("\n"), ctx).replace(/\n/g, " ")}</p>`);
    para.length = 0;
  };
  while (i < lines.length) {
    const l = lines[i];
    if (!l.trim()) {
      flush();
      i++;
    } else if (isFence(l)) {
      flush();
      const lang = l.trim().slice(3).trim().toLowerCase().replace(/[^a-z0-9-]/g, "").slice(0, 20);
      const body: string[] = [];
      i++;
      while (i < lines.length && !isFence(lines[i])) body.push(lines[i++]);
      i++; // the closing fence (or the end)
      out.push(`<pre class="ll-md-code"${lang ? ` data-lang="${lang}"` : ""}><code>${escapeHtml(body.join("\n"))}</code></pre>`);
    } else if (isHeading(l)) {
      flush();
      const level = Math.min(5, Math.max(2, l.match(/^#+/)![0].length + (l.startsWith("# ") ? 1 : 0)));
      out.push(`<h${level}>${inlineDoc(l.replace(/^#+ +/, "").replace(/ +#+ *$/, ""), ctx)}</h${level}>`);
      i++;
    } else if (isRule(l)) {
      flush();
      out.push("<hr>");
      i++;
    } else if (isQuote(l)) {
      flush();
      const body: string[] = [];
      while (i < lines.length && isQuote(lines[i])) body.push(lines[i++].replace(/^ {0,3}> ?/, ""));
      out.push(`<blockquote>${mdDoc(body.join("\n"), ctx)}</blockquote>`);
    } else if (isTableRow(l) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      flush();
      const head = cells(l);
      const align = cells(lines[i + 1]).map((c) => (c.startsWith(":") && c.endsWith(":") ? "center" : c.endsWith(":") ? "right" : ""));
      const at = (k: number) => (align[k] ? ` style="text-align:${align[k]}"` : "");
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && isTableRow(lines[i])) rows.push(cells(lines[i++]));
      const th = head.map((c, k) => `<th scope="col"${at(k)}>${inlineDoc(c, ctx)}</th>`).join("");
      const tb = rows.map((r) => `<tr>${head.map((_h, k) => `<td${at(k)}>${inlineDoc(r[k] ?? "", ctx)}</td>`).join("")}</tr>`).join("");
      out.push(`<div class="ll-md-table" tabindex="0" role="region" aria-label="Table"><table><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table></div>`);
    } else if (isBullet(l) || isOrdered(l)) {
      flush();
      const ordered = isOrdered(l);
      const start = ordered ? Number(l.trim().match(/^\d+/)![0]) : 1;
      const items: string[] = [];
      while (i < lines.length && (ordered ? isOrdered(lines[i]) : isBullet(lines[i]))) {
        let item = lines[i++].replace(ordered ? /^ {0,3}\d{1,3}[.)] +/ : /^ {0,3}[-*] +/, "");
        // a wrapped item: the next indented lines belong to it
        while (i < lines.length && /^ {2,}\S/.test(lines[i]) && !isBullet(lines[i]) && !isOrdered(lines[i])) item += " " + lines[i++].trim();
        items.push(`<li>${inlineDoc(item, ctx)}</li>`);
      }
      out.push(ordered ? `<ol class="ll-md-ol"${start !== 1 ? ` start="${start}"` : ""}>${items.join("")}</ol>` : `<ul class="ll-list">${items.join("")}</ul>`);
    } else {
      para.push(l);
      i++;
    }
  }
  flush();
  return out.join("\n");
}
// ---- end IN-1
