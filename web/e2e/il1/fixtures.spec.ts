// Wave I-L (IL-1): the advanced-data layer on screen — the drawer's Role block (league_lab.roles: his recent role, his
// share of the work against his share of the points, the games without a teammate) and the Stats Explorer's QB preset
// with Next Gen Stats' time to throw. Phone at 375 (inside the phone project) and desktop at 1300.
//
// The answers are the API's own, recorded by api/tests/test_il1.py::test_record_e2e_answers (League of Scrubs roster 2
// on the IL-1 clone, the pinned clock) into web/fixtures/il1/; every other route comes from the shared fixtures.
// Re-record:  cd api && IL1_RECORD=1 PYTHONPATH=. uv run pytest -q tests/test_il1.py -k record
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { FIXTURES, SCRUBS, serveFixtures } from "../fixtures";

const WAN = { gsis: "00-0038117", name: "Wan'Dale Robinson" };
const CARD = readFileSync(join(FIXTURES, "il1", `player_${SCRUBS}_${WAN.gsis}.json`), "utf8");
const QB = readFileSync(join(FIXTURES, "il1", "players_qb_season.json"), "utf8");
type Row = { gsis_id: string; player_name: string; time_to_throw: number | null; games: number | null };
const qbRows = (JSON.parse(QB) as { players: Row[] }).players;

test.beforeEach(async ({ context, page }, info) => {
  await serveFixtures(context);
  // registered after the shared fixtures, so these two answers win
  await context.route(new RegExp(`/api/player/${WAN.gsis}(\\?|$)`), (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: CARD }),
  );
  await context.route(/\/api\/players\?/, (route) => {
    const q = new URL(route.request().url()).searchParams;
    if (q.get("window") === "season" && q.get("position") === "QB") return route.fulfill({ status: 200, contentType: "application/json", body: QB });
    return route.fallback();
  });
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

test("the drawer shows the Role block after the projection, in words", async ({ page }) => {
  await page.goto(`/waivers?league=${SCRUBS}&team=2&pane=${WAN.gsis}&from=list`);
  const d = page.getByTestId("pane");
  await expect(d.getByTestId("pane-title")).toHaveText(WAN.name);
  const role = d.getByTestId("pane-section-role");
  await expect(role).toBeVisible();
  await expect(role).toContainText("Role");
  await expect(role).toContainText("Too early to say: 2 games with a snap so far this season");
  await expect(role).toContainText("Opportunity vs production: in line");
  await expect(role).toContainText("Contingent upside: no games without Carnell Tate to go on");
  await expect(role).toContainText("not a forecast");
  await expect(role).not.toContainText(/regress|unsustainable|due for/i);
  // right after the projection section (and its "why" sentence above it)
  const order = await d.locator('[data-testid^="pane-section-"]').evaluateAll((els) => els.map((e) => e.getAttribute("data-testid")));
  expect(order.indexOf("pane-section-role")).toBe(order.indexOf("pane-section-projection") + 1);
  await noSidewaysScroll(page);
});

test("the full player page shows the Role block too", async ({ page }) => {
  await page.goto(`/player/${WAN.gsis}?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("section-role")).toContainText("Opportunity vs production: in line");
  await noSidewaysScroll(page);
});

test("Players · Stats, QB preset: Time to throw from Next Gen Stats, — for a passer NGS did not qualify", async ({ page }) => {
  await page.goto(`/players?league=${SCRUBS}&team=2&position=QB`);
  const table = page.getByTestId("players-table");
  await expect(table.getByTestId("players-table-row").first()).toBeVisible();
  await expect(page.getByTestId("sort-time_to_throw")).toHaveText(/TTT/i);
  await expect(page.getByTestId("sort-cpoe")).toBeVisible();
  // the header's title carries the definition: how a window adds up
  await expect(page.locator("th", { has: page.getByTestId("sort-time_to_throw") })).toHaveAttribute("title", /never a mean of means/);
  // a qualified passer: his attempt-weighted number, its NGS sample on hover; a passer NGS did not publish: —, the reason
  const rows = table.getByTestId("players-table-row");
  const q = qbRows.find((r) => typeof r.time_to_throw === "number")!;
  const cell = rows.filter({ hasText: q.player_name }).first().locator('td[data-col="time_to_throw"]');
  await expect(cell).toHaveText(q.time_to_throw!.toFixed(2));
  await expect(cell).toHaveAttribute("title", /NGS published \d of his \d games? \(15\+ pass attempts\)/);
  const u = qbRows.find((r) => r.time_to_throw === null && (r.games ?? 0) > 0);
  if (u) {
    await page.getByTestId("players-search").fill(u.player_name);
    const ucell = rows.filter({ hasText: u.player_name }).first().locator('td[data-col="time_to_throw"]');
    await expect(ucell).toHaveText("—");
    await expect(ucell).toHaveAttribute("title", /unknown, not zero/);
  }
  await noSidewaysScroll(page);
});
