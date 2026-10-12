// Wave J-A (JA-2): the same weeks on Compare and Matchups — JA-1's week control (components/stretch/WeekSlider.svelte,
// URL window / weeks / vs) on Compare ("his early weeks against his recent ones": A, B and the change for the usage and
// production rows; the forecasts say they are forecasts and do not move) and on Matchups (each defense over the
// stretch, its rank, 1 = gives up the most, the change in rank, too few games said; the season's heatmap untouched);
// Stats' side by side opens Compare with the same weeks. Phone at 375, desktop at 1300; screens into JA2_SHOTS.
//
// Recordings: web/fixtures/ja2/api_ja2.json (web/fixtures/save_ja2_fixtures.py) and JA-1's web/fixtures/ja1/api_ja1.json.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures, SCRUBS } from "../fixtures";

const FX = join(import.meta.dirname, "..", "..", "fixtures");
const saved: Record<string, { status: number; body: unknown }> = {
  ...JSON.parse(readFileSync(join(FX, "ja2", "api_ja2.json"), "utf8")),
  ...JSON.parse(readFileSync(join(FX, "ja1", "api_ja1.json"), "utf8")),
};
const keyOf = (path: string, q: URLSearchParams) => `${path}?${new URLSearchParams([...q.entries()].sort(([a], [b]) => a.localeCompare(b))).toString()}`;
const JJ = "00-0036322";
const PW = "00-0038606";
const SHOTS = process.env.JA2_SHOTS ?? "e2e/.out";

async function serve(context: BrowserContext) {
  const api = await serveFixtures(context);
  await context.route(/\/api\/(compare\/weeks|matchups\/defense|players)\?/, (route) => {
    const u = new URL(route.request().url());
    api.calls.push(u.pathname + u.search);
    const hit = saved[keyOf(u.pathname, u.searchParams)];
    if (!hit) return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(hit.body) });
  });
  return api;
}
test.beforeEach(async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});
async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}
const shot = async (page: Page, name: string, isMobile: boolean) => {
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: join(SHOTS, `ja2-${name}-${isMobile ? 375 : 1300}.jpg`), quality: 70, fullPage: false });
};

test("Compare: his early weeks against his recent ones — A, B and the change; the forecasts say they are forecasts", async ({ page, context, isMobile }) => {
  const api = await serve(context);
  await page.goto(`/compare?league=${SCRUBS}&team=2&a=${JJ}&b=${PW}&window=weeks&weeks=3-4&vs=1-2`);
  const card = page.getByTestId("compare-weeks");
  await expect(card).toContainText("His early weeks against his recent ones");
  const share = page.locator('[data-testid="compare-weeks-row"][data-row="target_share"]');
  await expect(share.locator('[data-side="a"]')).toContainText("8.0%");
  await expect(share.locator('[data-side="a"] [data-testid="compare-weeks-chg"]')).toHaveText("−27.7 pts · B 35.7%");
  await expect(page.getByTestId("compare-weeks-note")).toContainText("forecasts");
  await expect(page.getByTestId("compare-forecast-note")).toContainText("forecasts, not history");
  // the forecasts' request carries no weeks
  expect(api.calls.filter((c) => c.startsWith("/api/compare?")).every((c) => !/[?&](window|weeks|vs)=/.test(c))).toBe(true);
  if (isMobile) await expect(page.getByTestId("slider-toggle")).toHaveText(/Weeks 3–4 against weeks 1–2/);
  await card.evaluate((n) => n.scrollIntoView({ block: "start" }));
  await noSidewaysScroll(page);
  await shot(page, "compare-two-stretches", isMobile);
});

test("Matchups: each defense over weeks 3–4, its rank (1 = gives up the most) and the change from weeks 1–2; one game said", async ({ page, context, isMobile }) => {
  const api = await serve(context);
  await page.goto(`/matchups?league=${SCRUBS}&team=2&window=weeks&weeks=3-4&vs=1-2&dpos=WR`);
  const card = page.getByTestId("defense-weeks");
  await expect(card).toContainText("Defenses, weeks 3–4 against weeks 1–2");
  const first = page.getByTestId("defense-weeks-row").first();
  await expect(first).toHaveAttribute("data-defense", "HOU");
  await expect(first.locator('[data-col="rank"]')).toHaveText("#1");
  await expect(first.locator('[data-col="rank-change"]')).toHaveText("same");
  await expect(page.locator('[data-testid="defense-weeks-row"][data-defense="DAL"] [data-col="rank-change"]')).toHaveText("▲ up 15");
  await expect(page.getByTestId("defense-weeks-few").first()).toContainText("1 game: too few to rank");
  // the season's heatmap (and every word a decision reads) comes from the request without weeks
  expect(api.calls.some((c) => c.startsWith("/api/matchups/defense?") && !/[?&]window=/.test(c))).toBe(true);
  await card.evaluate((n) => n.scrollIntoView({ block: "start" }));
  await noSidewaysScroll(page);
  await shot(page, "matchups-change-in-rank", isMobile);
});

test("Stats' side by side opens Compare with the same weeks", async ({ page, context }) => {
  await serve(context);
  const frame = saved[keyOf("/api/players", new URLSearchParams({ league: SCRUBS, limit: "1000", position: "WR,TE", window: "weeks", weeks: "3-4", vs: "1-2" }))].body as { players: { gsis_id: string }[] };
  const [p1, p2] = frame.players;
  await page.goto(`/players?league=${SCRUBS}&team=2&position=WRTE&window=weeks&weeks=3-4&vs=1-2&sel=${p1.gsis_id},${p2.gsis_id}`);
  const link = page.getByTestId("stats-open-compare");
  await expect(link).toBeVisible();
  const href = (await link.getAttribute("href")) ?? "";
  expect(href).toMatch(/[?&]window=weeks/);
  expect(href).toMatch(/[?&]weeks=3-4/);
  expect(href).toMatch(/[?&]vs=1-2/);
});
