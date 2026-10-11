// Wave I-Y (IY-1): embed code pasted into a blog post — X's "Embed post" blockquote (with or without its widgets.js
// script) and YouTube's <iframe> — is READ by lib/md.ts, never passed through. Two parts:
//   1. md.ts and components/blog/xframe.ts as pure functions (this repository has no unit-test runner for web/src: the
//      blog's pure tests live in its e2e specs, as in1 / iu6 do): Andrew's exact paste as stored (one line), the same
//      broken over lines, without the script, twitter.com, YouTube's iframe; forged blockquotes and other HTML; the
//      height messages X's frame sends (the right origin, a wrong one, a string, garbage).
//   2. The post page against the fixture API with the post answered by this test (/api/blog/<slug>): the X block before
//      the tap (no frame, no request to X), after it (a frame with exactly X's address and sandbox, resized by the
//      message the stub frame sends), the YouTube paste behind its Play button, a forged blockquote as text. Every
//      outside host is this test's (pattern web/e2e/ip0): the X frame is a stub page, everything else refused.
// Phone at 375 and desktop at 1300; screenshots in docs/handbacks/iy1/.
import { expect, test, type Route } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const SHOTS = join(import.meta.dirname, "..", "..", "..", "docs", "handbacks", "iy1");
// Andrew's paste, exactly as X gave it and as the post stores it (one line)
const PASTE =
  '<blockquote class="twitter-tweet"><p lang="en" dir="ltr">This is awesome: Here\'s the call #Cardinals GM Monti Ossenfort had with the #Texans when he traded out of No. 3 on draft night. Access to the blockbuster trade while they were on the clock. This content is INCREDIBLE. (via Cardinals Flight Plan on YT) https://t.co/taUindXEfy</p>&mdash; Ari Meirov (@MySportsUpdate) <a href="https://x.com/MySportsUpdate/status/1666992852084092930?ref_src=twsrc%5Etfw">June 9, 2023</a></blockquote> <script async src="https://platform.x.com/widgets.js" charset="utf-8"></script>';
const WORDS =
  "This is awesome: Here's the call #Cardinals GM Monti Ossenfort had with the #Texans when he traded out of No. 3 on draft night. Access to the blockbuster trade while they were on the clock. This content is INCREDIBLE. (via Cardinals Flight Plan on YT) https://t.co/taUindXEfy";
const ID = "1666992852084092930";
const YT = "dQw4w9WgXcQ";
const YT_PASTE = `<iframe width="560" height="315" src="https://www.youtube.com/embed/${YT}?si=Ab_c-12" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>`;
const FORGED = '<blockquote class="twitter-tweet"><p>Forged</p><a href="javascript:window.__iy1=1" onclick="window.__iy1=2">June 1, 2024</a></blockquote>';

/** The HTML holds nothing pasted: no tag or attribute but ours. */
function onlyOurs(html: string) {
  expect(html).not.toMatch(/<script|<iframe|<blockquote class="twitter-tweet"|\son[a-z]+=|javascript:|platform\.x\.com|widgets\.js|<a [^>]*href="(?!https:\/\/(x|www\.youtube)\.com\/)/i);
}

// ============================================================================ part 1: pure
test.describe("md.ts reads pasted embed code", () => {
  test.beforeEach(({ isMobile }) => test.skip(isMobile, "pure functions: once"));

  test("Andrew's paste as stored (one line) becomes our X block: words, name (@handle) · date, Show the post, Open on X", async () => {
    const { mdDoc, xPaste } = await import("../../src/lib/md");
    const inner = /<blockquote[^>]*>([\s\S]*)<\/blockquote>/.exec(PASTE)![1];
    expect(xPaste(inner)).toEqual({ handle: "MySportsUpdate", id: ID, words: WORDS, name: "Ari Meirov", date: "June 9, 2023" });
    const html = mdDoc(`Intro words.\n\n${PASTE}\n\nAfter words.`);
    onlyOurs(html);
    expect(html).toContain(`<figure class="ll-embed ll-embed-x" data-x-post="${ID}">`);
    expect(html).toContain(`<p class="ll-embed-words">This is awesome: Here&#39;s the call #Cardinals GM Monti Ossenfort`);
    expect(html).toContain('<footer class="ll-embed-by">Ari Meirov (@MySportsUpdate) · June 9, 2023</footer>');
    expect(html).toContain(`<button type="button" class="ll-embed-show" data-x-show="${ID}">Show the post</button>`);
    expect(html).toContain(`<a href="https://x.com/MySportsUpdate/status/${ID}" rel="noopener noreferrer nofollow ugc" target="_blank" class="ll-link">Open on X</a>`);
    expect(html).toContain("<p>Intro words.</p>");
    expect(html).toContain("<p>After words.</p>");
    expect(html.match(/ll-embed-x/g)?.length).toBe(1);
    // in the middle of a line: the words around it stay paragraphs, the block stands alone
    const mid = mdDoc(`Look: ${PASTE} wow`);
    expect(mid).toMatch(/<p>Look: ?<\/p>/);
    expect(mid).toMatch(/<p> ?wow<\/p>/);
    expect(mid).toContain('data-x-show="1666992852084092930"');
  });

  test("the same paste broken over lines, without the script, with twitter.com, with Windows line ends", async () => {
    const { mdDoc } = await import("../../src/lib/md");
    const broken = PASTE.replace("</p>", "</p>\n").replace("</blockquote> ", "</blockquote>\n\n").replace('dir="ltr">', 'dir="ltr">\n');
    const noScript = PASTE.replace(/ <script[^]*$/, "");
    const twitter = PASTE.replace("https://x.com/", "https://twitter.com/").replace("platform.x.com", "platform.twitter.com");
    for (const [what, text] of [["broken", broken], ["no script", noScript], ["twitter.com", twitter], ["crlf", broken.replace(/\n/g, "\r\n")]] as const) {
      const html = mdDoc(text);
      onlyOurs(html);
      expect(html, what).toContain(`data-x-show="${ID}"`);
      expect(html, what).toContain("Ari Meirov (@MySportsUpdate) · June 9, 2023");
      expect(html, what).toContain("This is awesome: Here&#39;s the call");
      expect(html.match(/ll-embed-x/g)?.length, what).toBe(1);
      expect(html, what).not.toContain("&lt;"); // nothing of the code left as text
    }
  });

  test("YouTube's iframe code becomes the YouTube block from the id; nothing else is read from it", async () => {
    const { mdDoc } = await import("../../src/lib/md");
    for (const code of [YT_PASTE, YT_PASTE.replace("www.youtube.com", "www.youtube-nocookie.com"), YT_PASTE.replace("?si=Ab_c-12", "")]) {
      const html = mdDoc(`Watch:\n\n${code}`);
      onlyOurs(html);
      expect(html).toContain(`data-yt-play="${YT}"`);
      expect(html).not.toMatch(/title="YouTube video player"|allowfullscreen|accelerometer/);
    }
    for (const bad of [
      YT_PASTE.replace(YT, "dQw4w9WgXc"), // 10 characters
      YT_PASTE.replace(YT, 'dQw4w9WgX"Q'),
      YT_PASTE.replace("https://www.youtube.com/embed/", "https://www.youtube.com.evil.example/embed/"),
      YT_PASTE.replace("https://www.youtube.com/embed/", "https://evil.example/embed/"),
      YT_PASTE.replace("https://", "http://"),
      `<iframe src="javascript:alert(1)//https://www.youtube.com/embed/${YT}"></iframe>`,
    ]) {
      const html = mdDoc(bad);
      expect(html, bad).not.toContain("data-yt-play");
      expect(html, bad).not.toMatch(/<iframe/);
      expect(html, bad).toContain("&lt;iframe"); // text, as before
    }
  });

  test("forged and other HTML: text as written, or nothing but the plain words", async () => {
    const { mdDoc } = await import("../../src/lib/md");
    // no status link of the strict shape → the whole thing stays text
    for (const forged of [
      FORGED,
      PASTE.replace(`status/${ID}`, "status/12345abc"), // an id with letters
      PASTE.replace(`status/${ID}`, "status/1234"), // too short
      PASTE.replace(`status/${ID}`, `status/${"1".repeat(26)}`), // too long
      PASTE.replace("https://x.com/MySportsUpdate", "https://x.com/My-Sports"), // a handle off the pattern
      PASTE.replace("https://x.com/", "https://x.com.evil.example/"),
      PASTE.replace("https://x.com/", "http://x.com/"),
      PASTE.replace('class="twitter-tweet"', 'class="tweet"'),
    ]) {
      const html = mdDoc(forged);
      expect(html, forged).not.toContain("ll-embed-x");
      expect(html, forged).not.toMatch(/<blockquote class="twitter-tweet"|<script|<a [^>]*javascript|<[a-z][^>]*\sonclick=/);
      expect(html, forged).toContain("&lt;blockquote");
    }
    // a valid status link but hostile insides: only the plain words survive, as text
    const hostile =
      '<blockquote class="twitter-tweet" onmouseover="window.__iy1=3"><p lang="en"><a href="javascript:alert(1)" onclick="window.__iy1=4">click</a> <img src=x onerror="window.__iy1=5"><b>bold</b> &lt;script&gt;alert(6)&lt;/script&gt; &#106;avascript &#0; &#xD800;</p>&mdash; Eve <i>"Evil"</i> (@NFL) <a href="https://x.com/NFL/status/123456789" onclick="window.__iy1=7">May 1, 2024</a></blockquote><script src="https://evil.example/x.js"></script><script async src="https://platform.x.com/widgets.js" charset="utf-8"></script>';
    const html = mdDoc(hostile);
    expect(html).toContain('data-x-show="123456789"');
    expect(html).toContain('<p class="ll-embed-words">click bold &lt;script&gt;alert(6)&lt;/script&gt; javascript</p>');
    expect(html).toContain('<footer class="ll-embed-by">Eve &quot;Evil&quot; (@NFL) · May 1, 2024</footer>');
    // the second script (another host) is not X's: it stays text, after the block
    expect(html).toContain("&lt;script src=&quot;https://evil.example/x.js&quot;&gt;&lt;/script&gt;");
    expect(html).not.toMatch(/<script|<img|\son[a-z]+=|<a [^>]*javascript|<b>|<i>/i);
    // a bare widgets.js script alone, and any other HTML: text
    expect(mdDoc('<script async src="https://platform.x.com/widgets.js" charset="utf-8"></script>')).toContain("&lt;script async");
    expect(mdDoc('<div onclick="x"><iframe src="https://evil.example"></iframe></div>')).toContain("&lt;div onclick=&quot;x&quot;&gt;");
    // inside a code fence the paste is code, shown as written
    const fenced = mdDoc("```\n" + PASTE + "\n```");
    expect(fenced).toContain("<pre");
    expect(fenced).not.toContain("ll-embed-x");
    // the bare link still works (IU-6), now with Show the post
    const bare = mdDoc(`https://x.com/MySportsUpdate/status/${ID}`);
    expect(bare).toContain(`data-x-show="${ID}"`);
    expect(bare).toContain('<span class="ll-embed-h">@MySportsUpdate</span>');
    // the lifted block's mark typed by a writer is dropped, never a block
    expect(mdDoc("0")).not.toContain("ll-embed");
  });

  test("X's height messages: the right origin and frame only; an object or a JSON string; clamped; garbage ignored", async () => {
    const { onXMessage, xResizeHeight, xFrameSrc, X_ORIGIN } = await import("../../src/components/blog/xframe");
    const msg = (h: unknown) => ({ "twttr.embed": { method: "twttr.private.resize", params: [{ height: h, width: 550 }] } });
    expect(xResizeHeight(msg(812))).toBe(812);
    expect(xResizeHeight(JSON.stringify(msg(812.4)))).toBe(812);
    expect(xResizeHeight(msg(50))).toBe(200);
    expect(xResizeHeight(msg(99999))).toBe(2000);
    expect(xResizeHeight(msg("640"))).toBe(640);
    for (const junk of [null, undefined, 7, "x", "{", "[]", {}, { "twttr.embed": null }, { "twttr.embed": { method: "other", params: [{ height: 600 }] } }, msg(NaN), msg("640px"), msg(null), msg({}), { "twttr.embed": { method: "twttr.private.resize", params: [] } }, "a".repeat(30_000)])
      expect(xResizeHeight(junk), JSON.stringify(junk)?.slice(0, 40)).toBeNull();
    const win = {};
    const other = {};
    const frame = { contentWindow: win, style: { height: "560px" } };
    expect(onXMessage({ origin: "https://evil.example", source: win, data: msg(900) }, [frame])).toBeNull();
    expect(onXMessage({ origin: "https://platform.x.com", source: win, data: msg(900) }, [frame])).toBeNull();
    expect(onXMessage({ origin: X_ORIGIN, source: other, data: msg(900) }, [frame])).toBeNull();
    expect(onXMessage({ origin: X_ORIGIN, source: null, data: msg(900) }, [frame])).toBeNull();
    expect(onXMessage({ origin: X_ORIGIN, source: win, data: "garbage" }, [frame])).toBeNull();
    expect(frame.style.height).toBe("560px");
    expect(onXMessage({ origin: X_ORIGIN, source: win, data: JSON.stringify(msg(733)) }, [frame])).toBe(frame);
    expect(frame.style.height).toBe("733px");
    expect(xFrameSrc(ID)).toBe(`https://platform.twitter.com/embed/Tweet.html?id=${ID}&dnt=true&theme=light`);
    expect(xFrameSrc(ID, true)).toBe(`https://platform.twitter.com/embed/Tweet.html?id=${ID}&dnt=true&theme=dark`);
    for (const bad of ["", "12a", '1"', "1&x=2", "1".repeat(26)]) expect(xFrameSrc(bad), bad).toBeNull();
  });
});

// ============================================================================ part 2: the post page
const SLUG = "what-s-monti-ossenfort-up-to-now";
const POST = {
  slug: SLUG,
  title: "What's Monti Ossenfort up to now?",
  date: "2026-10-10",
  summary: "The Cardinals' general manager, on the clock.",
  author: "Andrew",
  tags: [],
  minutes: 2,
  image: null,
  markdown: ["The call is worth a look.", "", PASTE, "", "And the video:", "", YT_PASTE, "", "A forged one stays text:", "", FORGED, ""].join("\n"),
};

test.describe("the post page", () => {
  test.beforeEach(async ({ page, isMobile }) => {
    if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
  });

  test("the X block before the tap (nothing from X), X's frame after it, YouTube's paste behind Play, a forged one as text", async ({ context, page, isMobile }) => {
    test.setTimeout(90_000);
    mkdirSync(SHOTS, { recursive: true });
    const w = isMobile ? 375 : 1300;
    await serveFixtures(context);
    const outside: string[] = [];
    // after serveFixtures (the last route registered answers first): the outside world is this test's
    await context.route(/^https?:\/\/(?!localhost[:/]|127\.0\.0\.1[:/])/, (route: Route) => {
      const url = route.request().url();
      outside.push(url);
      if (url.startsWith("https://platform.twitter.com/embed/Tweet.html?"))
        return route.fulfill({
          status: 200,
          contentType: "text/html",
          body: `<!doctype html><title>stub</title><p>X's post would show here.</p><script>parent.postMessage(${JSON.stringify(JSON.stringify({ "twttr.embed": { method: "twttr.private.resize", params: [{ height: 812, width: 550 }] } }))}, "*")</script>`,
        });
      return route.abort();
    });
    await context.route(/\/api\/blog(\?|\/)/, (route: Route) => {
      const u = new URL(route.request().url());
      if (u.pathname === `/api/blog/${SLUG}`) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(POST) });
      if (u.pathname === "/api/blog") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ posts: [{ ...POST, markdown: undefined }] }) });
      return route.fallback();
    });
    await page.goto(`/blog/${SLUG}`);
    await expect(page.getByTestId("post-title")).toHaveText(POST.title, { timeout: 30_000 });
    const body = page.getByTestId("post-body");
    const fig = body.locator("figure.ll-embed-x");
    await expect(fig).toHaveCount(1);
    await expect(fig.locator(".ll-embed-words")).toHaveText(WORDS);
    await expect(fig.locator(".ll-embed-by")).toHaveText("Ari Meirov (@MySportsUpdate) · June 9, 2023");
    await expect(fig.getByRole("link", { name: "Open on X" })).toHaveAttribute("href", `https://x.com/MySportsUpdate/status/${ID}`);
    const show = fig.getByRole("button", { name: "Show the post" });
    await expect(show).toBeVisible();
    await expect(body.locator(`button[data-yt-play="${YT}"]`)).toBeVisible();
    await expect(body.locator("iframe")).toHaveCount(0);
    await expect(page.locator("script[src*='widgets.js'], blockquote.twitter-tweet, iframe")).toHaveCount(0);
    await expect(body).toContainText('<blockquote class="twitter-tweet"><p>Forged</p>'); // as text
    await page.waitForTimeout(1000);
    expect(await page.evaluate(() => (window as unknown as { __iy1?: number }).__iy1)).toBeUndefined();
    expect(outside, "nothing asked of X or YouTube before a tap").toEqual([]);
    const sw = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(sw, "no sideways scroll").toBeLessThanOrEqual(0);
    await fig.scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(SHOTS, `iy1-post-${w}.jpg`), type: "jpeg", quality: 70, fullPage: true });

    // the tap: X's frame in the block's place, exactly this address and sandbox; the stub's height message is obeyed
    await show.click();
    const frame = fig.locator("iframe");
    await expect(frame).toHaveCount(1);
    await expect(frame).toHaveAttribute("src", new RegExp(`^https://platform\\.twitter\\.com/embed/Tweet\\.html\\?id=${ID}&dnt=true&theme=(light|dark)$`));
    await expect(frame).toHaveAttribute("sandbox", "allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox");
    await expect(frame).toHaveAttribute("loading", "lazy");
    await expect(frame).toHaveAttribute("referrerpolicy", "no-referrer");
    await expect(frame).toHaveAttribute("title", "Post on X");
    await expect(fig.locator(".ll-embed-words")).toHaveCount(0);
    await expect(fig.getByRole("button", { name: "Show the post" })).toHaveCount(0);
    await expect(page.frameLocator('iframe[title="Post on X"]').getByText("X's post would show here.")).toBeVisible();
    await expect.poll(() => frame.evaluate((el) => (el as HTMLIFrameElement).style.height), { timeout: 10_000 }).toBe("812px");
    const box = await frame.boundingBox();
    const col = await body.boundingBox();
    expect(Math.abs((box?.width ?? 0) - (col?.width ?? 0)), "as wide as the column").toBeLessThanOrEqual(2);
    expect(outside.every((u) => u.startsWith(`https://platform.twitter.com/embed/Tweet.html?id=${ID}&dnt=true&theme=`)), outside.join(" ")).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: join(SHOTS, `iy1-post-shown-${w}.jpg`), type: "jpeg", quality: 70, fullPage: true });
  });
});
