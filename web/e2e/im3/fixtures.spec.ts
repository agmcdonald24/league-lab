// Wave I-M (IM-3): the open door — the front door for a first visit, browsing without a league (`ref:half`: the reference
// picker, Players · Stats priced in Half PPR, no "rostered by"), the invitation card on My Team / Waivers / Trades, the
// calm 429 line, GA's platform "none". Phone at 375 and desktop at 1300.
//
// Two modes. Default (the fixtures suite): every `ref:` answer comes from web/fixtures/im3/api_im3.json, recorded from
// the fixture API; the rest from serveFixtures. IM3_LIVE=http://localhost:8753 (the fixture API serving web/dist):
// the same walk against the real server, its headers included — every Content-Security-Policy violation fails the
// test (the built app and GA's loader under the CSP) — and the answers are recorded into api_im3.json.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const LIVE = process.env.IM3_LIVE ?? "";
const DIR = join(import.meta.dirname, "..", "..", "fixtures", "im3");
const RECORDED = join(DIR, "api_im3.json");
const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out");
const GOOGLE = /^https:\/\/([a-z0-9-]+\.)*(google-analytics\.com|googletagmanager\.com|google\.com|doubleclick\.net)\//;
type Recorded = Record<string, { status: number; body: unknown }>;

if (LIVE) test.use({ baseURL: LIVE });

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return `${u.pathname}?${new URLSearchParams(q).toString()}`;
};
const isRefCall = (u: URL) => /^ref:/i.test(u.searchParams.get("league") ?? "") || /^\/api\/leagues\/ref:/i.test(decodeURIComponent(u.pathname));

const recorded: Recorded = existsSync(RECORDED) ? (JSON.parse(readFileSync(RECORDED, "utf8")) as Recorded) : {};

/** The API for one test: live (recording the ref: answers), or the recordings + the shared fixtures. */
async function api(context: BrowserContext): Promise<{ calls: string[]; google: string[] }> {
  const calls: string[] = [];
  const google: string[] = []; // GA's requests the page made (a request the CSP blocked never reaches here)
  await context.route(GOOGLE, (route) => {
    google.push(route.request().url());
    return route.request().url().startsWith("https://www.googletagmanager.com/gtag/js") ? route.fulfill({ status: 200, contentType: "text/javascript", body: "" }) : route.abort();
  });
  await context.route(/^https:\/\/static\.www\.nfl\.com\//, (route) => route.abort());
  if (LIVE) {
    // GA on (it is off under automation): gtag.js must load under the server's Content-Security-Policy
    await context.addInitScript(() => ((window as unknown as { __llGa: string }).__llGa = "on"));
    await context.route(/\/api\//, async (route) => {
      const u = new URL(route.request().url());
      calls.push(u.pathname + u.search);
      try {
        const res = await route.fetch();
        if (isRefCall(u) && route.request().method() === "GET") {
          try {
            recorded[keyOf(u)] = { status: res.status(), body: await res.json() };
          } catch {
            /* not JSON */
          }
        }
        await route.fulfill({ response: res });
      } catch {
        /* the page closed with the request in flight */
      }
    });
    return { calls, google };
  }
  await serveFixtures(context);
  await context.route(/\/api\//, async (route) => {
    const u = new URL(route.request().url());
    calls.push(u.pathname + u.search);
    if (!isRefCall(u)) return route.fallback();
    // the exact request, else the same path in the same scoring (a screen that asks with other parameters later)
    const league = u.searchParams.get("league");
    const hit =
      recorded[keyOf(u)] ??
      Object.entries(recorded).find(([k]) => k.startsWith(`${u.pathname}?`) && new URLSearchParams(k.split("?")[1]).get("league") === league)?.[1];
    if (!hit) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: `not recorded: ${keyOf(u)}` }) });
    return route.fulfill({ status: hit.status, contentType: "application/json", body: JSON.stringify(hit.body) });
  });
  return { calls, google };
}

async function cspWatch(page: Page): Promise<string[]> {
  const violations: string[] = [];
  page.on("console", (m) => {
    if (/Content Security Policy|Refused to (load|execute|apply|connect|frame)/i.test(m.text())) violations.push(m.text());
  });
  await page.addInitScript(() =>
    document.addEventListener("securitypolicyviolation", (e) => console.error(`Refused to ${e.violatedDirective}: ${e.blockedURI} (Content Security Policy)`)),
  );
  return violations;
}

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "no sideways page scroll").toBeLessThanOrEqual(iw + 1);
}

test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test.afterAll(() => {
  if (!LIVE) return;
  mkdirSync(DIR, { recursive: true });
  // small recordings: a list of more than 60 rows keeps its first 60 (the screens need a page, not the season)
  const trim = (v: unknown): unknown =>
    Array.isArray(v) ? v.slice(0, 60).map(trim) : v && typeof v === "object" ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, trim(x)])) : v;
  writeFileSync(RECORDED, JSON.stringify(trim(recorded)));
});

test("a first visit: the front door, Browse the lab, Players · Stats in Half PPR with no owners", async ({ context, page }, info) => {
  const { calls, google } = await api(context);
  const csp = await cspWatch(page);
  await page.goto("/");
  // ---- IN-1 (Wave I-N): the front door is the home page now (routes/Home.svelte); the setup screen is /leagues
  const door = page.getByTestId("home");
  await expect(door).toBeVisible();
  await expect(page.getByTestId("home-browse")).toHaveText("Browse players");
  await expect(page.getByTestId("home-open")).toHaveText("Open your league");
  await expect(page.getByTestId("home-record-line")).toBeVisible();
  await expect(page.getByTestId("home-about")).toHaveAttribute("href", "/about?league=ref%3Ahalf");
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `im3-front-door-${info.project.name}.png`), fullPage: true });

  await page.getByTestId("home-browse").click();
  await expect(page).toHaveURL(/\/players\?league=ref(%3A|:)half/);
  await expect(page.getByTestId("ref-picker")).toBeVisible();
  await expect(page.getByTestId("ref-button")).toContainText("Half PPR"); // ---- IN-2: the scoring picker (was a select)
  await expect(page.getByTestId("ref-open")).toHaveText("Open your league");
  await expect(page.getByTestId("players")).toBeVisible();
  await expect(page.getByTestId("players").getByRole("link", { name: /Smith-Njigba|St\. Brown|Chase|Nacua|Jefferson|Lamb/ }).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("players")).not.toContainText(/rostered by/i);
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `im3-browse-stats-${info.project.name}.png`), fullPage: false });
  // a reference key is never a remembered league
  expect(await page.evaluate(() => localStorage.getItem("ll.league"))).toBeNull();
  expect(calls.some((c) => /^\/api\/leagues\/ref/.test(decodeURIComponent(c)))).toBe(false); // no team picker asked for
  // the scoring switch: PPR in the URL, the same screen
  const ppr = page.waitForResponse((r) => r.url().includes("/api/players?") && /league=ref(%3A|:)ppr/.test(r.url()));
  await page.getByTestId("ref-button").click(); // ---- IN-2: the picker's panel (was a select)
  await page.getByTestId("ref-base-ppr").click();
  expect((await ppr).status()).toBe(200);
  await expect(page).toHaveURL(/league=ref(%3A|:)ppr/);
  await page.getByTestId("ref-done").click();
  await expect(page.getByTestId("ref-button")).toContainText("PPR");
  await expect(page.getByTestId("players").getByRole("link", { name: /Smith-Njigba|St\. Brown|Chase|Nacua|Jefferson|Lamb/ }).first()).toBeVisible({ timeout: 30_000 });
  if (LIVE) expect(google.some((u) => u.startsWith("https://www.googletagmanager.com/gtag/js")), "gtag.js loaded under the CSP").toBe(true);
  expect(csp, csp.join("\n")).toEqual([]);
});

// ---- IN-2 (Wave I-N): browsing, My Team and Waivers are not tabs (they are behind "Open your league") and Trades is the
// calculator without a league; their screens, opened by a link, still invite
test("My Team and Waivers invite you to open your league; Trades is the calculator; Players' tabs work", async ({ context, page }, info) => {
  await api(context);
  const csp = await cspWatch(page);
  await page.goto("/trends?league=ref:half");
  await expect(page.getByTestId("ref-picker")).toBeVisible();
  await expect(page.getByTestId("tab-myteam")).toHaveCount(0);
  await expect(page.getByTestId("tab-waivers")).toHaveCount(0);
  await page.getByTestId("tab-trades").click();
  await expect(page.getByTestId("free-trade")).toBeVisible();
  await expect(page.getByTestId("invite-card")).toHaveCount(0);
  for (const tab of ["myteam", "waivers"]) {
    await page.goto(tab === "myteam" ? "/?league=ref:half" : "/waivers?league=ref:half");
    const card = page.getByTestId("invite-card");
    await expect(card).toBeVisible();
    await expect(card).toContainText("Open your league to see your lineup, waivers and trades.");
    await expect(card).toContainText("Half PPR");
    await expect(page.getByTestId("error-card")).toHaveCount(0);
    await noSidewaysScroll(page);
    if (tab === "myteam") await page.screenshot({ path: join(SHOTS, `im3-invite-${info.project.name}.png`), fullPage: false });
  }
  await expect(page.getByTestId("invite-open")).toHaveAttribute("href", "/leagues");
  await page.getByTestId("tab-players").click();
  await expect(page.getByTestId("players")).toBeVisible();
  await expect(page.getByTestId("invite-card")).toHaveCount(0);
  await page.getByTestId("ref-open").click();
  await expect(page).toHaveURL(/\/leagues$/);
  await expect(page.getByTestId("username-form")).toBeVisible(); // IN-1: /leagues is only "open your league" now
  await expect(page.getByTestId("to-home")).toHaveAttribute("href", "/home");
  expect(csp, csp.join("\n")).toEqual([]);
});

test("too many requests: one calm line on the screen, never a blank one", async ({ context, page }) => {
  test.skip(!!LIVE, "fixtures only");
  await api(context);
  await context.route(/\/api\/players\?/, (route) =>
    route.fulfill({
      status: 429,
      contentType: "application/json",
      headers: { "Retry-After": "12" },
      body: JSON.stringify({ error: "Too many requests from this connection. Try again in 12 seconds.", code: "rate_limited", retry_after_s: 12, bucket: "read" }),
    }),
  );
  await page.goto("/players?league=ref:half");
  const card = page.getByTestId("error-card");
  await expect(card).toBeVisible();
  await expect(card).toHaveAttribute("data-kind", "limited");
  await expect(card.getByTestId("error-words")).toContainText("Too many requests from this connection. Try again in 12 seconds.");
});

test("GA counts a reference key as platform none (ids only)", async ({ context, page }) => {
  test.skip(!!LIVE, "fixtures only");
  await api(context);
  await context.route(/\/api\/health$/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, version: "fixture-im3" }) }));
  await context.addInitScript(() => ((window as unknown as { __llGa: string }).__llGa = "on"));
  await page.goto("/players?league=ref:half");
  await expect(page.getByTestId("players")).toBeVisible();
  await expect
    .poll(async () =>
      page.evaluate(() => {
        const dl = (window as unknown as { dataLayer?: ArrayLike<unknown>[] }).dataLayer;
        return Array.from(dl ?? [], (a) => Array.from(a))
          .filter((c) => c[0] === "event" && c[1] === "page_view")
          .map((c) => (c[2] as Record<string, unknown>)?.platform);
      }),
    )
    .toContain("none");
});

// ---- IM-3 fix (the Wave I-M review): provider text in the sentences never becomes a link to another site
test("markdown: a hostile team name stays text; our own links stay links", async () => {
  test.skip(test.info().project.name !== "desktop", "pure code: once is enough");
  const { md, withContext } = await import("../../src/lib/md");
  for (const team of ["[Open](//evil.example)", "[Open](/\\evil.example)", "[Free money](https://evil.example/x)", "[x](https://espn.com.evil.example/)", "[x](https://user@espn.com/)", "[x](javascript:alert(1))"]) {
    const html = md(`**Best partner: ${team}.** Trade with them.`, { league: "1", team: 2 });
    expect(html, team).not.toContain("<a ");
    expect(html).toContain("<strong>Best partner:");
  }
  expect(md("[Amon-Ra St. Brown](/player/00-0036963)", { league: "1", team: 2 })).toContain('<a href="/player/00-0036963?league=1&amp;team=2"');
  expect(md("[ESPN](https://www.espn.com/nfl/player/_/id/4374302)")).toContain('href="https://www.espn.com/nfl/player/_/id/4374302"');
  expect(withContext("//evil.example", { league: "1" })).toBe("//evil.example");
});
