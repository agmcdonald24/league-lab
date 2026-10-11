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

// ---- IU-6 (Wave I-U): in a blog post (mdDoc only) a link may go to any https site — no user / password / port in it —
// and says it is the writer's, not ours: rel="noopener noreferrer nofollow ugc", a new tab. `md`'s sentences (provider
// text) keep IM-3's rule above. http:, javascript:, data:, "//host" and everything else stay the label as text.
export const POST_LINK_REL = "noopener noreferrer nofollow ugc";
export function anyHttps(raw: string): boolean {
  if (!/^https:\/\/[a-z0-9.-]+([/?#]|$)/i.test(raw)) return false; // the host spelled plainly: no "\", "@", ":" before the path
  try {
    const u = new URL(raw);
    return u.protocol === "https:" && !u.username && !u.password && !u.port && u.hostname.includes(".");
  } catch {
    return false;
  }
}

function inline(text: string, ctx: LinkContext, more?: (html: string) => string, post = false): string {
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
    if (post && anyHttps(raw)) return `${tag(`<a href="${escapeHtml(raw)}" rel="${POST_LINK_REL}" target="_blank" class="ll-link">`)}${label}</a>`; // IU-6
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
// ---- IO-3 (Wave I-O): + a picture uploaded from the blog editor, /blog/img/db/<uuid> (api blog_store.py)
const BLOG_IMG = /^\/blog\/img\/([a-z0-9][a-z0-9_-]{0,79}\.(png|jpe?g|webp)|db\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/;

function inlineDoc(text: string, ctx: LinkContext): string {
  // code spans and pictures are held aside (their own escaped HTML) while `inline` escapes and marks up the rest
  const held: string[] = [];
  const hold = (html: string) => `\uE000${held.push(html) - 1}\uE000`;
  let rest = text.replace(/\uE002\d*\uE002?/g, "").replace(/`([^`\n]+)`/g, (_m, c: string) => hold(`<code>${escapeHtml(c)}</code>`));
  // pictures: ![alt](/blog/img/name.png) — our own folder only, else the words
  rest = rest.replace(/!\[([^\]]*)\]\(([^)\s]*)\)/g, (_m, alt: string, src: string) =>
    hold(BLOG_IMG.test(src) ? `<img src="${src}" alt="${escapeHtml(alt)}" loading="lazy" decoding="async" class="ll-md-img">` : escapeHtml(alt)),
  );
  // escapes, then links / bold / hard breaks, then italic — all before the links' tags come back (none inside an href)
  const out = inline(rest, ctx, (h) => h.replace(/(^|[\s(])\*([^*\s][^*]*?)\*(?=[\s).,;:!?]|$)/g, "$1<em>$2</em>"), true);
  return out.replace(/\uE000(\d+)\uE000/g, (_m, i: string) => held[Number(i)]);
}

// ---- IU-6 (Wave I-U): embeds from a closed list — a YouTube video or a post on X, written as the link alone on its
// line. Matched on the raw line by strict patterns (the host spelled exactly, the id's own alphabet and length), and
// built from the captured ids alone (escaped all the same). YouTube: a placeholder with a Play button and the video's
// link — nothing is asked of YouTube until the reader taps; then PostBody makes the iframe to
// https://www.youtube-nocookie.com/embed/<id> (sandboxed, lazy, its own referrer policy, a title). X: a plain link card
// from the URL (the handle and the post's number) — no script from X, ever. Any other link alone on a line is a
// paragraph as before.
const YT_ID = /^[A-Za-z0-9_-]{11}$/;
const YT = [
  /^https:\/\/(?:www\.|m\.)?youtube\.com\/watch\?v=([A-Za-z0-9_-]{11})(?:&[A-Za-z0-9_.=-]*)*$/,
  /^https:\/\/(?:www\.)?youtube\.com\/shorts\/([A-Za-z0-9_-]{11})(?:\?[A-Za-z0-9_.=&-]*)?$/,
  /^https:\/\/youtu\.be\/([A-Za-z0-9_-]{11})(?:\?[A-Za-z0-9_.=&-]*)?$/,
];
const X_POST = /^https:\/\/(?:www\.|mobile\.)?(?:x|twitter)\.com\/([A-Za-z0-9_]{1,15})\/status\/(\d{1,20})(?:\?[A-Za-z0-9_.=&-]*)?$/;

export function youtubeId(line: string): string | null {
  for (const re of YT) {
    const m = re.exec(line);
    if (m && YT_ID.test(m[1])) return m[1];
  }
  return null;
}
export function xPost(line: string): { handle: string; id: string } | null {
  const m = X_POST.exec(line);
  return m ? { handle: m[1], id: m[2] } : null;
}
export function isYoutubeId(id: string | null | undefined): id is string {
  return typeof id === "string" && YT_ID.test(id);
}
/** The YouTube block from a checked id: a Play button (nothing asked of YouTube before the tap) and the video's link. */
function youtubeBlock(yt: string): string {
  const id = escapeHtml(yt);
  return (
    `<figure class="ll-embed ll-embed-yt" data-yt="${id}">` +
    `<button type="button" class="ll-embed-play" data-yt-play="${id}" aria-label="Play the YouTube video"><span class="ll-embed-k">▶ Play the video</span><span class="ll-embed-s">From YouTube: it loads when you tap.</span></button>` +
    `<figcaption><a href="https://www.youtube.com/watch?v=${id}" rel="${POST_LINK_REL}" target="_blank" class="ll-link">Watch on YouTube</a></figcaption></figure>`
  );
}

/** ---- IY-1 (Wave I-Y): the X block — our own markup only: the post's words and "Name (@handle) · date" when a pasted
 * embed code had them (plain text, escaped here), else the card; then **Show the post** (PostBody makes X's frame on the
 * tap: nothing from X before it) and **Open on X**. The handle and the id come from strict patterns. */
function xBlock(handle: string, id: string, said?: { words: string; name: string; date: string }): string {
  const h = escapeHtml(handle);
  const n = escapeHtml(id);
  const by = said ? [said.name ? `${escapeHtml(said.name)} (@${h})` : `@${h}`, said.date ? escapeHtml(said.date) : ""].filter(Boolean).join(" · ") : "";
  const body = said
    ? `<blockquote class="ll-embed-quote" data-x-body>${said.words ? `<p class="ll-embed-words">${escapeHtml(said.words).replace(/\n/g, "<br>")}</p>` : ""}<footer class="ll-embed-by">${by}</footer></blockquote>`
    : `<div class="ll-embed-card" data-x-body><span class="ll-embed-k">A post on X</span><span class="ll-embed-h">@${h}</span></div>`;
  return (
    `<figure class="ll-embed ll-embed-x" data-x-post="${n}">${body}` +
    `<div class="ll-embed-actions"><button type="button" class="ll-embed-show" data-x-show="${n}">Show the post</button>` +
    `<a href="https://x.com/${h}/status/${n}" rel="${POST_LINK_REL}" target="_blank" class="ll-link">Open on X</a></div></figure>`
  );
}

/** The embed's HTML for a line that is one link alone, else null (the line stays a paragraph). */
export function embed(line: string): string | null {
  const yt = youtubeId(line);
  if (yt) return youtubeBlock(yt);
  const x = xPost(line);
  if (x) return xBlock(x.handle, x.id);
  return null;
}

// ---- IY-1 (Wave I-Y): the embed code X and YouTube hand a writer, pasted into a post, is READ — never passed through.
// X: <blockquote class="twitter-tweet">…</blockquote>, with or without X's <script …widgets.js></script> after it, on
// one line or several. From it, by strict patterns only: the handle and the post's number from its status link (the
// last link inside; x.com or twitter.com); as plain text (tags dropped, entities decoded — escaped again on output):
// the post's words (the first <p>), the author's name (before "(@handle)") and the date (the status link's words).
// YouTube: <iframe … src="https://www.youtube.com/embed/<id>…"></iframe> (or youtube-nocookie.com) → the YouTube block
// from the id; nothing else is read from it. A blockquote whose status link does not match, any other HTML, a second
// script, an attribute: the text it was, escaped like any text.
const X_PASTE = /<blockquote\b[^>]{0,400}\bclass\s*=\s*["']twitter-tweet\b[^"']{0,200}["'][^>]{0,400}>([\s\S]{0,20000}?)<\/blockquote\s*>(?:\s*<script\b[^>]{0,200}\bsrc\s*=\s*["']https:\/\/platform\.(?:twitter|x)\.com\/widgets\.js["'][^>]{0,200}>\s*<\/script\s*>)?/gi;
const YT_PASTE = /<iframe\b[^>]{0,800}?\bsrc\s*=\s*["']https:\/\/www\.youtube(?:-nocookie)?\.com\/embed\/([A-Za-z0-9_-]{11})(?:\?[^"'<>\s]{0,400})?["'][^>]{0,800}>\s*<\/iframe\s*>/gi;
const X_STATUS = /^https:\/\/(?:www\.|mobile\.)?(?:x|twitter)\.com\/([A-Za-z0-9_]{1,15})\/status\/(\d{5,25})(?:[?#][^"'<>\s]*)?$/;
const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", mdash: "—", ndash: "–", hellip: "…", rsquo: "’", lsquo: "‘", rdquo: "”", ldquo: "“" };

/** HTML → plain text: line breaks kept, every tag dropped, entities decoded (escapeHtml runs again on output). */
export function plainText(html: string): string {
  return html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]*>/g, "")
    .replace(/[<>]/g, "")
    .replace(/&(#x[0-9a-f]{1,6}|#\d{1,7}|[a-z]{2,8});/gi, (m, e: string) => {
      if (e[0] === "#") {
        const cp = e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
        return cp > 31 && cp <= 0x10ffff && !(cp >= 0xd800 && cp <= 0xdfff) && cp !== 127 ? String.fromCodePoint(cp) : "";
      }
      return ENTITIES[e.toLowerCase()] ?? m;
    })
    // eslint-disable-next-line no-control-regex -- the control characters (all but the line break) are the point
    .replace(/[\u0000-\u0009\u000b-\u001f\u007f\uE000-\uF8FF]/g, "")
    .replace(/[ \t]+/g, " ")
    .replace(/ *\n */g, "\n")
    .trim();
}

/** A pasted X blockquote's inner HTML → the post it names, or null (no status link of the strict shape: it stays text). */
export function xPaste(inner: string): { handle: string; id: string; words: string; name: string; date: string } | null {
  const links = [...inner.matchAll(/<a\b[^>]*?\bhref\s*=\s*["']([^"'<>]{0,500})["'][^>]*>([\s\S]{0,500}?)<\/a\s*>/gi)];
  for (let k = links.length - 1; k >= 0; k--) {
    const m = X_STATUS.exec(links[k][1].replace(/&amp;/gi, "&"));
    if (!m) continue;
    // PO (Wave I-Y): the media pointer X leaves at the end of a post's words (one or more trailing https://t.co/… links)
    // is dropped: the frame shows the media, and the bare short link reads as noise in our block
    const words = plainText(/<p\b[^>]*>([\s\S]*?)<\/p\s*>/i.exec(inner)?.[1] ?? "").slice(0, 1000)
      .replace(/(?:\s*https:\/\/t\.co\/[A-Za-z0-9]{1,20})+\s*$/, "");
    const after = inner.slice(inner.search(/<\/p\s*>/i) >= 0 ? inner.search(/<\/p\s*>/i) : 0, links[k].index);
    const who = plainText(after).replace(/^[\s—–-]+/, "");
    const named = /^(.{1,80}?)\s*\(@[A-Za-z0-9_]{1,15}\)$/.exec(who);
    return { handle: m[1], id: m[2], words, name: named ? named[1].trim().slice(0, 60) : "", date: plainText(links[k][2]).slice(0, 40) };
  }
  return null;
}

/** The pasted embed codes in a document (outside code fences) lifted out: each becomes a line of its own holding
 * \uE002<n>\uE002, and `blocks[n]` its HTML. A blockquote that is not a post on X stays exactly as written. */
function liftPastes(text: string, blocks: string[]): string {
  const lift = (seg: string) =>
    seg
      .replace(X_PASTE, (all: string, inner: string) => {
        const x = xPaste(inner);
        if (!x) return all;
        return `\n\n\uE002${blocks.push(xBlock(x.handle, x.id, x)) - 1}\uE002\n\n`;
      })
      .replace(YT_PASTE, (all: string, id: string) => (isYoutubeId(id) ? `\n\n\uE002${blocks.push(youtubeBlock(id)) - 1}\uE002\n\n` : all));
  const out: string[] = [];
  let seg: string[] = [];
  let fenced = false;
  for (const l of text.split("\n")) {
    if (isFence(l)) {
      if (!fenced) {
        out.push(lift(seg.join("\n")));
        seg = [];
      }
      out.push(l);
      fenced = !fenced;
    } else if (fenced) out.push(l);
    else seg.push(l);
  }
  out.push(lift(seg.join("\n")));
  return out.join("\n");
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
export function mdDoc(text: string | null | undefined, ctx: LinkContext = {}, lifted?: string[]): string {
  if (!text) return "";
  // U+E000: the placeholders' mark (a private-use character); IY-1: U+E002 marks a lifted embed code (top level only)
  const blocks = lifted ?? [];
  let src = text.replace(/\r\n?/g, "\n");
  if (!lifted) src = liftPastes(src.replace(/[\uE000\uE002]/g, ""), blocks);
  const lines = src.replace(/\uE000/g, "").split("\n");
  const out: string[] = [];
  let i = 0;
  const para: string[] = [];
  const flush = () => {
    const held = para.length === 1 ? /^\uE002(\d+)\uE002$/.exec(para[0].trim()) : null; // IY-1: a pasted embed code
    const alone = held ? (blocks[Number(held[1])] ?? "") : para.length === 1 ? embed(para[0].trim()) : null; // IU-6: a YouTube / X link alone on its line
    if (alone) out.push(alone);
    else if (para.length) out.push(`<p>${inlineDoc(para.join("\n"), ctx).replace(/\n/g, " ")}</p>`);
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
      out.push(`<blockquote>${mdDoc(body.join("\n"), ctx, blocks)}</blockquote>`);
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
