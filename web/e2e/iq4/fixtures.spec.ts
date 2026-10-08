// Wave I-Q (IQ-4): the trust guard on three screens. Browsing (`ref:half`) in 2026 week 5, the season's first bye week
// (Kansas City and Carolina have no game): Rankings' "Rest of season" ranks Patrick Mahomes by his remaining games and
// his row says "Bye this week"; the sentence from ros_grade ("Beyond next week there is no betting line yet. Graded on
// 2021–2025, …") is under the list, in /ros's "how to read" box and under the free trade calculator's values; kickers'
// rest of season answers the K / DEF sentence instead of a list. Phone at 375 and desktop at 1300; screenshots (JPEG
// q70) into docs/handbacks/iq4/ (SHOTS_IQ4) or e2e/.out.
//
// Two modes, as e2e/ip2. Default: the rankings', /ros's and the calculator's answers come from
// web/fixtures/iq4/api_iq4.json (recorded from the API on league_lab_iq4 with the clock pinned in week 5 — the real bye
// rows — trimmed to the fields the screens read), the rest from serveFixtures. IQ4_LIVE=http://localhost:8964 (that API
// serving web/dist): the same walk against the real server, recording those answers.
// Outside hosts (headshots): the test answers them itself with a 1x1 PNG (nothing is fetched from outside).
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const LIVE = process.env.IQ4_LIVE ?? "";
const DIR = join(import.meta.dirname, "..", "..", "fixtures", "iq4");
const RECORDED = join(DIR, "api_iq4.json");
const SHOTS = process.env.SHOTS_IQ4 ?? join(import.meta.dirname, "..", ".out");
type Recorded = Record<string, { status: number; body: unknown }>;
const MAHOMES = "00-0033873";
const HUBBARD = "00-0036555";
const SENTENCE = /Beyond next week there is no betting line yet\. Graded on 2021–2025, a quarterback projection two to eight weeks ahead misses by about 7\.4 points per game \(6\.4 for next week\)/;
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64");

if (LIVE) test.use({ baseURL: LIVE });

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return `${u.pathname}?${new URLSearchParams(q).toString()}`;
};
const MINE = ["/api/rankings", "/api/ros", "/api/trade-calc/free"];
const mine = (u: URL) => MINE.includes(u.pathname) && /^ref:/i.test(u.searchParams.get("league") ?? "");
const recorded: Recorded = existsSync(RECORDED) ? (JSON.parse(readFileSync(RECORDED, "utf8")) as Recorded) : {};
// the recording keeps the first 30 rows of a list (the screens' first page and Mahomes among them)
const trim = (u: URL, body: unknown): unknown => {
  if (!body || typeof body !== "object") return body;
  const b = body as Record<string, unknown>;
  if (u.pathname === "/api/rankings" && Array.isArray(b.rows)) return { ...b, rows: (b.rows as unknown[]).slice(0, 30) };
  if (u.pathname === "/api/ros" && Array.isArray(b.players)) return { ...b, players: (b.players as unknown[]).slice(0, 30) };
  return body;
};

async function api(context: BrowserContext): Promise<string[]> {
  const calls: string[] = [];
  await context.route(/^https?:\/\/(?!localhost)/, (route) => route.fulfill({ status: 200, contentType: "image/png", body: PNG }));
  if (LIVE) {
    await context.route(/\/api\//, async (route) => {
      const u = new URL(route.request().url());
      calls.push(u.pathname + u.search);
      try {
        const res = await route.fetch();
        if (mine(u) && route.request().method() === "GET") recorded[keyOf(u)] = { status: res.status(), body: trim(u, await res.json()) };
        await route.fulfill({ response: res });
      } catch {
        /* the page closed with the request in flight */
      }
    });
    return calls;
  }
  await serveFixtures(context);
  await context.route(/\/api\//, async (route) => {
    const u = new URL(route.request().url());
    calls.push(u.pathname + u.search);
    if (!mine(u)) return route.fallback();
    const hit = recorded[keyOf(u)];
    if (!hit) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: `not recorded: ${keyOf(u)}` }) });
    return route.fulfill({ status: hit.status, contentType: "application/json", body: JSON.stringify(hit.body) });
  });
  return calls;
}

const shot = (page: Page, name: string) => page.screenshot({ path: join(SHOTS, `${name}.jpg`), type: "jpeg", quality: 70, scale: "css" });
const noSideScroll = async (page: Page) => {
  const [sw, cw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(sw).toBeLessThanOrEqual(cw);
};

test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test.afterAll(() => {
  if (!LIVE) return;
  mkdirSync(DIR, { recursive: true });
  writeFileSync(RECORDED, JSON.stringify(recorded));
});

test("Rankings, rest of season: a bye-week quarterback ranked by his remaining games, and what we know", async ({ context, page }, info) => {
  await api(context);
  await page.goto("/rankings?league=ref:half&view=season&position=QB");
  const row = page.getByTestId("rankings-row").filter({ hasText: "Patrick Mahomes" });
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(row).toContainText("Bye this week");
  await expect(row).toContainText(/games left/);
  await expect(page.getByTestId("rankings-ros-grade")).toHaveText(SENTENCE);
  await expect(page.getByTestId("rankings-ros-grade")).toContainText("running backs, receivers and tight ends miss by about 0.2 more than next week.");
  await noSideScroll(page);
  await shot(page, `rankings-season-${info.project.name}`);
});

test("Rankings, rest of season: kickers answer the sentence, not a list", async ({ context, page }, info) => {
  await api(context);
  await page.goto("/rankings?league=ref:half&view=season&position=K");
  await expect(page.getByTestId("rankings-notice")).toHaveText(
    "Kickers and defenses: graded on 2021–2025, their order two to eight weeks ahead is no better than chance, so they have no rest-of-season ranking here.",
    { timeout: 30_000 },
  );
  expect(await page.getByTestId("rankings-row").count()).toBe(0);
  await noSideScroll(page);
  await shot(page, `rankings-season-k-${info.project.name}`);
});

test("/ros: the sentence in the how-to-read box, Mahomes in the list", async ({ context, page }, info) => {
  await api(context);
  await page.goto("/ros?league=ref:half&position=QB");
  await expect(page.getByTestId("ros-grade")).toHaveText(SENTENCE, { timeout: 30_000 });
  await expect(page.getByText("Patrick Mahomes").first()).toBeVisible();
  await noSideScroll(page);
  await shot(page, `ros-${info.project.name}`);
});

test("the free trade calculator: a bye-week player valued, and what we know under the values", async ({ context, page }, info) => {
  await api(context);
  await page.goto(`/trade-calc?league=ref:half&give=${MAHOMES}&get=${HUBBARD}`);
  await expect(page.getByTestId("ft-ros-grade")).toHaveText(SENTENCE, { timeout: 30_000 });
  await expect(page.getByText("Patrick Mahomes").first()).toBeVisible();
  await expect(page.getByText(/no rest-of-season projection/)).toHaveCount(0);
  await noSideScroll(page);
  await shot(page, `free-calc-${info.project.name}`);
});
