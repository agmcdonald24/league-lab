// Wave I-O (IO-1): the context record on DFS — "Worth a look" says what the record says (rebuilt for 2025 and 2026
// weeks 1–4: not distinguishable from chance) and why nobody is listed now (the cornerback call no longer counts: graded,
// no measurable effect); the corner chip carries its tier's grade and loses its colour; outdoor games carry the forecast
// at kickoff (wind 20 mph in Green Bay) on a dashed chip — not in the projection. Without the record the screen keeps
// today's words. The answers were recorded from the fixture API on :8861 against league_lab_im1 (web/fixtures/io1/).
// Phone at 375 and desktop at 1300; screenshots into docs/handbacks/io1/.
import { expect, test, type BrowserContext, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const IO1 = join(import.meta.dirname, "..", "..", "fixtures", "io1");
const SHOTS = process.env.SHOTS_IO1 ?? join(import.meta.dirname, "..", "..", "..", "docs", "handbacks", "io1");
const read = (name: string) => readFileSync(join(IO1, name), "utf8");
const NEVER = /\b(lock|locks|guaranteed|free money|no league)\b/i;

async function dfsApi(context: BrowserContext, projections: string) {
  await context.route(/\/api\/(dfs|context)\//, async (route: Route) => {
    const url = new URL(route.request().url());
    const send = (status: number, body: string) => route.fulfill({ status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body });
    if (url.pathname === "/api/dfs/projections") return send(200, projections);
    if (url.pathname === "/api/dfs/slates") return send(200, JSON.stringify({ season: 2026, week: 4, slates: [], not_offered: [], unreadable: [] }));
    if (url.pathname === "/api/context/record") return send(200, read("context_record.json"));
    return send(404, JSON.stringify({ error: "not recorded" }));
  });
}

async function noSideways(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw).toBeLessThanOrEqual(iw);
}

async function size(page: Page, name: string) {
  if (name === "phone") await page.setViewportSize({ width: 375, height: 812 });
}

test("DFS with the record: the grade's words, the graded corner, the weather", async ({ page, context }, info) => {
  await serveFixtures(context);
  await dfsApi(context, read("projections_dk.json"));
  await size(page, info.project.name);
  await page.goto("/dfs");
  await expect(page.getByTestId("dfs-proj-row").first()).toBeVisible();
  // "Worth a look": the record's sentence instead of "no record behind this list yet", and why nobody is listed
  const worth = page.getByTestId("dfs-worth").first();
  await expect(worth.getByTestId("dfs-worth-record")).toContainText("Graded on 2025 and 2026 weeks 1–4 with the cornerback counting");
  await expect(worth.getByTestId("dfs-worth-record")).toContainText("not distinguishable from chance");
  await expect(worth).not.toContainText("no record behind this list");
  await expect(worth.getByTestId("dfs-worth-empty")).toContainText("the cornerback call, made no measurable difference when graded, so it no longer counts");
  // receivers: the weather chip (dashed: not in the projection) and the corner chip with its grade, without colour
  await page.getByTestId("dfs-proj-pos-WR").click();
  const wx = page.locator("[data-testid=dfs-chip][data-signal=weather]").first();
  await expect(wx).toBeVisible();
  await expect(wx).toHaveAttribute("data-outside", "yes");
  await expect(wx).toHaveText(/^(Wind \d+ mph|Rain \(\d\.\d\d in\)|Snow|\d+°F)/);
  const corner = page.locator("[data-testid=dfs-chip][data-signal=corner][data-graded=none]").first();
  await expect(corner).toBeVisible();
  await expect(corner).toHaveAttribute("title", /Graded: no measurable effect/);
  await expect(corner).not.toHaveClass(/text-bad|text-good/);
  const row = page.getByTestId("dfs-proj-row").filter({ has: page.locator("[data-signal=corner][data-graded=none]") }).first();
  await row.getByTestId("dfs-proj-open").click();
  await expect(row.getByTestId("dfs-signal-graded").first()).toContainText("Graded: no measurable effect");
  // what the projection holds: the corner's grade and the weather's thresholds, said once
  await page.getByTestId("dfs-holds").locator("summary").click();
  await expect(page.getByTestId("dfs-corner-record")).toContainText("no measurable effect either way");
  await expect(page.getByTestId("dfs-weather-honest")).toContainText("Not in the projection; outdoor games carry the forecast at kickoff");
  expect((await page.getByTestId("dfs").innerText()).match(NEVER)).toBeNull();
  await noSideways(page);
  await page.screenshot({ path: join(SHOTS, `io1-dfs-record-${info.project.name}.png`), fullPage: false });
  await page.getByTestId("dfs-worth").first().scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(SHOTS, `io1-dfs-worth-${info.project.name}.png`), fullPage: false });
});

test("DFS without the record: today's words, no grade, no weather", async ({ page, context }, info) => {
  const b = JSON.parse(read("projections_dk.json"));
  b.context_meta.worth_record = null;
  b.context_meta.corner_record = null;
  b.context_meta.forecast = false;
  b.context_meta.words = 'Context, not a forecast: these signals sit beside the projection and do not change it. "Worth a look" has no record behind it yet (no backtest).';
  for (const p of b.players) {
    p.context = (p.context ?? []).filter((s: { signal: string }) => s.signal !== "weather").map((s: Record<string, unknown>) => {
      delete s.graded;
      delete s.graded_effect;
      return s;
    });
  }
  await serveFixtures(context);
  await dfsApi(context, JSON.stringify(b));
  await size(page, info.project.name);
  await page.goto("/dfs");
  await expect(page.getByTestId("dfs-proj-row").first()).toBeVisible();
  await expect(page.getByTestId("dfs-worth").first()).toContainText("there is no record behind this list");
  await expect(page.getByTestId("dfs-worth-record")).toHaveCount(0);
  await page.getByTestId("dfs-proj-pos-WR").click();
  await expect(page.locator("[data-testid=dfs-chip][data-signal=weather]")).toHaveCount(0);
  await expect(page.locator("[data-testid=dfs-chip][data-graded=none]")).toHaveCount(0);
  await page.getByTestId("dfs-holds").locator("summary").click();
  await expect(page.getByTestId("dfs-weather-honest")).toContainText("no forecast for this week's games yet");
  await noSideways(page);
});
