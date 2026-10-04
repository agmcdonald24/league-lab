// Wave I-G (V-1): the decision record on About — "Our lineups against the ones started" under the record against
// Sleeper's projections: the edge sentence, three tiles (what our lineups would have added, the best lineup in
// hindsight, how the coin flips landed), the week table (rebuilt weeks starred), the calls / news lines, the note and
// "How to read". League of Scrubs, weeks 1–2 of the sandbox clone. At 375 (phone project) and 1300 (desktop).
//
// `decisions` is the API's own, recorded from a live API on the V-1 clone (league_lab_i0a: `league-lab validate`, then
// `dbt build --select mart_decision_record mart_decision_calls`) into web/fixtures/v1/record_decisions_<league>.json
// and merged here into the record fixture (web/fixtures/record_<league>.json). Re-record:
//   (api on :8705, the gate off)  V1_RECORD=http://localhost:8705 FIXTURES_PORT=8605 npm run e2e:fixtures -- e2e/v1
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { FIXTURES, SCRUBS, serveFixtures } from "../fixtures";

const FILE = join(FIXTURES, "v1", `record_decisions_${SCRUBS}.json`);
const RECORD = process.env.V1_RECORD ?? "";
let decisions: unknown = existsSync(FILE) ? JSON.parse(readFileSync(FILE, "utf8")) : null;

async function answer(route: Route) {
  const u = new URL(route.request().url());
  if (u.searchParams.get("league") !== SCRUBS) return route.fallback();
  if (RECORD && decisions === null) {
    const r = await fetch(`${RECORD}/api/record?league=${SCRUBS}`);
    decisions = ((await r.json()) as { decisions?: unknown }).decisions ?? null;
    writeFileSync(FILE, JSON.stringify(decisions, null, 1) + "\n");
  }
  const base = JSON.parse(readFileSync(join(FIXTURES, `record_${SCRUBS}.json`), "utf8")) as Record<string, unknown>;
  return route.fulfill({ status: 200, contentType: "application/json", headers: { "Cache-Control": "no-store" },
                         body: JSON.stringify({ ...base, decisions }) });
}

test.beforeEach(async ({ context }) => {
  test.skip(!RECORD && decisions === null, "no recording yet: run with V1_RECORD (see the header)");
  await serveFixtures(context);
  await context.route(/\/api\/record/, answer);
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (name: string, project: string) => join(process.env.SHOTS_DIR ?? "e2e/.out", `v1-${name}-${project}.png`);

test("About: our lineups against the ones started, weeks 1–2 graded and the season adding up", async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`/about?league=${SCRUBS}&team=2`);
  const block = page.getByTestId("record-decisions");
  await expect(block).toBeVisible();
  await block.scrollIntoViewIfNeeded();
  await expect(block.getByRole("heading", { name: "Our lineups against the ones started" })).toBeVisible();
  await expect(page.getByTestId("decisions-edge")).toContainText("Weeks 1–2: had every team started our lineup");

  // the tiles say the season's numbers, the table one row a week with the rebuilt weeks starred
  const d = decisions as { season_totals: { edge: number; regret: number }; weeks: { week: number; edge: number }[];
                           calls: { coin_flips: { n: number } } };
  const fmt = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}`;
  await expect(page.getByTestId("decisions-tile-edge").getByTestId("stat-value")).toHaveText(fmt(d.season_totals.edge));
  await expect(page.getByTestId("decisions-tile-regret").getByTestId("stat-value")).toHaveText(`+${d.season_totals.regret.toFixed(1)}`);
  await expect(page.getByTestId("decisions-tile-flips")).toContainText(`${d.calls.coin_flips.n} calls`);
  const rows = page.getByTestId("decisions-table").locator("tbody tr");
  await expect(rows).toHaveCount(d.weeks.length);
  await expect(rows.first().locator("td").first()).toHaveText("1*");
  await expect(rows.first().locator("td").last()).toHaveText(fmt(d.weeks[0].edge));
  // the weeks add up to the season (the tile) to the tenth
  const sum = d.weeks.reduce((a, w) => a + w.edge, 0);
  expect(Math.abs(sum - d.season_totals.edge)).toBeLessThan(0.011);

  await expect(page.getByTestId("decisions-calls")).toContainText("The coin flips landed");
  await expect(page.getByTestId("decisions-note")).toContainText("played before this record existed");
  await page.getByTestId("decisions-howto").locator("summary").click();
  await expect(page.getByTestId("decisions-howto")).toContainText("ours minus started");
  await noSidewaysScroll(page);
  await block.screenshot({ path: shot("about-decisions", info.project.name) });
});
