// Wave I-N (IN-3): matchups for everyone — the board on /matchups. Browsing (`ref:half`): every receiver's matchup,
// a search, a row that opens the evidence, the words about what the projection counts, no owners and never "No
// league". With a league and a team: "My players" (the screen as before) and "Everyone" (the board, who has him).
// Phone at 375 and desktop at 1300; screenshots into docs/handbacks/in3/ (SHOTS_IN3) and e2e/.out.
//
// Two modes, as e2e/im3. Default: the board's and the reference heatmap's answers come from web/fixtures/in3/api_in3.json
// (recorded from the fixture API), the rest from serveFixtures. IN3_LIVE=http://localhost:8763 (the fixture API serving
// web/dist): the same walk against the real server, recording those answers into api_in3.json.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { SCRUBS, serveFixtures } from "../fixtures";

const LIVE = process.env.IN3_LIVE ?? "";
const DIR = join(import.meta.dirname, "..", "..", "fixtures", "in3");
const RECORDED = join(DIR, "api_in3.json");
const SHOTS = process.env.SHOTS_IN3 ?? join(import.meta.dirname, "..", ".out");
type Recorded = Record<string, { status: number; body: unknown }>;
type BoardBody = { rows: { player_name: string }[]; total: number; offset: number };

if (LIVE) test.use({ baseURL: LIVE });

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return `${u.pathname}?${new URLSearchParams(q).toString()}`;
};
const mine = (u: URL) => u.pathname === "/api/matchups/board" || (u.pathname === "/api/matchups/defense" && /^ref:/i.test(u.searchParams.get("league") ?? ""));
const recorded: Recorded = existsSync(RECORDED) ? (JSON.parse(readFileSync(RECORDED, "utf8")) as Recorded) : {};

async function api(context: BrowserContext): Promise<string[]> {
  const calls: string[] = [];
  await context.route(/^https?:\/\/(?!localhost)/, (route) => route.abort()); // headshots, GA: never fetched by a test
  if (LIVE) {
    await context.route(/\/api\//, async (route) => {
      const u = new URL(route.request().url());
      calls.push(u.pathname + u.search);
      try {
        const res = await route.fetch();
        if (mine(u) && route.request().method() === "GET") recorded[keyOf(u)] = { status: res.status(), body: await res.json() };
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
    let hit = recorded[keyOf(u)];
    const q = u.searchParams.get("q");
    if (!hit && q) {
      // a search that was not recorded: the recorded first page of the same board, filtered by name (as the server does)
      const base = new URL(u.toString());
      base.searchParams.delete("q");
      const all = recorded[keyOf(base)];
      if (all) {
        const body = all.body as BoardBody;
        const rows = body.rows.filter((r) => r.player_name.toLowerCase().includes(q.toLowerCase()));
        hit = { status: 200, body: { ...body, q, rows, total: rows.length } };
      }
    }
    if (!hit) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: `not recorded: ${keyOf(u)}` }) });
    return route.fulfill({ status: hit.status, contentType: "application/json", body: JSON.stringify(hit.body) });
  });
  return calls;
}

async function noSideways(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "no sideways page scroll").toBeLessThanOrEqual(iw + 1);
  const { mw, cw } = await page.evaluate(() => {
    const m = document.querySelector("[data-testid=board]") as HTMLElement;
    return { mw: m.scrollWidth, cw: m.clientWidth };
  });
  expect(mw, "nothing in the board wider than the board").toBeLessThanOrEqual(cw + 1);
}

test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test.afterAll(() => {
  if (!LIVE) return;
  mkdirSync(DIR, { recursive: true });
  writeFileSync(RECORDED, JSON.stringify(recorded));
});

test("browsing: every receiver's matchup, a search, a row opens the evidence", async ({ context, page }, info) => {
  const calls = await api(context);
  await page.goto("/matchups?league=ref:half");
  const board = page.getByTestId("board");
  await expect(board).toBeVisible();
  await expect(page.getByTestId("board-row").first()).toBeVisible({ timeout: 30_000 });
  expect(await page.getByTestId("board-row").count()).toBe(25);
  await expect(page.getByTestId("board-count")).toContainText(/Showing 1–25 of \d+ wide receivers/);
  await expect(page.getByTestId("board-honest-short")).toContainText("Projected points in Half PPR scoring. The defense is in the projection; the corner is not");
  await expect(page.getByTestId("board-honest")).toContainText("Who plays cornerback is not in it");
  await expect(page.getByTestId("matchups-view")).toHaveCount(0); // no switch without a league
  await expect(page.getByTestId("matchups")).not.toContainText(/No league|rostered by|Free agent/i);
  await expect(page.getByTestId("board-corner").first()).toBeVisible();
  await noSideways(page);
  // the desktop uses the width: the board's columns sit side by side
  if (!info.project.name.includes("phone")) {
    const box = await board.boundingBox();
    expect(box!.width).toBeGreaterThan(900);
  }
  await page.screenshot({ path: join(SHOTS, `in3-board-${info.project.name}.png`) });

  // search: the server's q= (two letters at least), the box in the URL
  const asked = page.waitForResponse((r) => r.url().includes("/api/matchups/board?") && /[?&]q=Nacua/.test(r.url()));
  await page.getByTestId("board-search").fill("Nacua");
  expect((await asked).status()).toBe(200);
  await expect(page).toHaveURL(/q=Nacua/);
  await expect(page.getByTestId("board-row")).toHaveCount(1);
  await expect(page.getByTestId("board-name")).toHaveText("Puka Nacua");

  // the row opens the evidence that exists (MatchupEvidence), the corner call and the sentence
  await page.getByTestId("board-row-open").first().click();
  const detail = page.getByTestId("board-detail");
  await expect(detail).toBeVisible();
  await expect(page.getByTestId("board-words")).toContainText("gives up the");
  await expect(page.getByTestId("board-evidence")).toContainText("not in the forecast");
  await expect(page.getByTestId("board-player-link")).toHaveAttribute("href", /\/player\/00-0039075\?league=ref(%3A|:)half/);
  await noSideways(page);
  await detail.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(SHOTS, `in3-evidence-${info.project.name}.png`) });
  expect(calls.filter((c) => c.startsWith("/api/matchups/board")).every((c) => !/team=/.test(c))).toBe(true);
});

test("a league: My players as before, Everyone adds who has him", async ({ context, page }, info) => {
  await api(context);
  await page.goto(`/matchups?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("matchups-view")).toBeVisible();
  await expect(page.getByTestId("matchups-view-mine")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("cb-section")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("board")).toHaveCount(0);
  await page.getByTestId("matchups-view-everyone").click();
  await expect(page).toHaveURL(/view=everyone/);
  await expect(page.getByTestId("board-row").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("board-honest-short")).toContainText("League of Scrubs scoring");
  // who has him: the phone's line under the name; the desktop's row detail
  await page.getByTestId("board-row-open").first().click();
  await expect(page.getByTestId("board-detail")).toContainText(/Who has him: \S/);
  await noSideways(page);
  await page.screenshot({ path: join(SHOTS, `in3-everyone-${info.project.name}.png`) });
  // tone filter: every row says the tone asked
  await page.getByTestId("board-tone-favorable").click();
  await expect(page).toHaveURL(/tone=favorable/);
  await expect(page.locator("[data-testid=board-row]:not([data-tone=favorable])")).toHaveCount(0);
  await expect(page.getByTestId("board-row").first()).toBeVisible();
  await page.getByTestId("matchups-view-mine").click();
  await expect(page.getByTestId("cb-section")).toBeVisible();
});
