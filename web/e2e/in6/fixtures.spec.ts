// Wave I-N (IN-6): the League screen's first two blocks — "Power rankings" (every team by its best lineup's expected
// points per week over the rest of the season, record / points for / against / schedule left beside it, my team marked,
// no movement arrows) and "Rest of season" (simulated seasons: projected record, playoff odds, top seed, a bye in a
// league with byes; what it assumes; no title odds), every column's definition one tap away; a league with no readable
// outlook keeps the rankings and says why. Phone at 375 (no sideways page scroll; the tables scroll inside themselves,
// the team column fixed) and desktop at 1300 (the blocks use the width: bars).
//
// The outlook answers are the API's own, recorded from the fixture API on this sandbox's database (web/fixtures/in6/;
// the schedule after week 5 is the SYNTHETIC round robin of api/tests/fixtures/make_in6_schedule.py, not the leagues'
// real one): `curl /api/league/outlook?league=<id>&team=<n>` with the timings dropped. The League answers are the
// decisions fixtures (web/fixtures/league_*.json).
import { expect, test, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveDecisions } from "../decisions-fixtures";
import { DYNASTY, SCRUBS, serveFixtures, TEST_LEAGUE } from "../fixtures";

const IN6 = join(import.meta.dirname, "..", "..", "fixtures", "in6");
const SHOTS = process.env.SHOTS_IN6 ?? join(import.meta.dirname, "..", ".out");
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const read = (name: string): any => JSON.parse(readFileSync(join(IN6, name), "utf8"));
const FILES: Record<string, string> = { [`${SCRUBS}_2`]: "outlook_scrubs_2.json", [`${DYNASTY}_12`]: "outlook_dynasty_12.json", [`${TEST_LEAGUE}_3`]: "outlook_test_3.json" };

test.beforeEach(async ({ context, page }, info) => {
  await serveFixtures(context);
  await serveDecisions(context);
  await context.route(/\/api\/league\/outlook\?/, async (route: Route) => {
    const q = new URL(route.request().url()).searchParams;
    const f = FILES[`${q.get("league")}_${q.get("team")}`];
    if (!f) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: "no fixture" }) });
    return route.fulfill({ status: 200, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: readFileSync(join(IN6, f), "utf8") });
  });
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (page: Page, name: string, project: string) =>
  page.getByTestId("outlook").screenshot({ path: join(SHOTS, `in6-${name}-${project}.png`) });

const pct = (p: number) => (p < 0.005 ? "<1%" : p > 0.995 ? ">99%" : `${Math.round(p * 100)}%`);

for (const scheme of ["dark", "light"] as const) {
  test(`power rankings and the rest of the season, League of Scrubs team 2 (${scheme})`, async ({ page }, info) => {
    const o = read("outlook_scrubs_2.json");
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto(`/league?league=${SCRUBS}&team=2`);
    const power = page.getByTestId("power");
    await expect(power).toBeVisible();
    // the first two blocks: above the standings
    const top = async (id: string) => (await page.getByTestId(id).boundingBox())!.y;
    expect(await top("power")).toBeLessThan(await top("season"));
    expect(await top("season")).toBeLessThan(await top("standings"));
    // every team, ranked by points per week; mine marked; the metric said once; no arrows
    await expect(page.getByTestId("power-row")).toHaveCount(o.power.rows.length);
    await expect(page.getByTestId("power-row").first()).toContainText(o.power.rows[0].team_name);
    await expect(page.getByTestId("power-row").first()).toContainText(o.power.rows[0].per_week.toFixed(1));
    const mine = o.power.rows.find((r: { roster_id: number }) => r.roster_id === 2);
    await expect(page.locator('[data-testid="power-row"][data-yours="1"]')).toContainText(`${mine.team_name} (you)`);
    await expect(page.getByTestId("power-words")).toHaveText(o.power.words);
    await expect(page.getByTestId("no-arrows")).toContainText("No movement arrows");
    const gap = o.power.rows.find((r: { gap_words: string | null }) => r.gap_words);
    if (gap) await expect(page.getByTestId("gap").first()).toBeVisible();
    // a definition one tap away, and the same tap closes it
    await page.getByTestId("def-power").click();
    await expect(page.getByTestId("power").getByTestId("league-def")).toHaveText(o.definitions.power);
    await page.getByTestId("def-power").click();
    await expect(page.getByTestId("power").getByTestId("league-def")).toHaveCount(0);
    await page.getByTestId("def-record").click();
    await expect(page.getByTestId("power").getByTestId("league-def")).toHaveText(o.definitions.record);
    await page.getByTestId("def-record").click();
    // the rest of the season: odds per team, sorted, the assumptions, no title odds
    const season = page.getByTestId("season");
    await expect(page.getByTestId("season-row")).toHaveCount(o.outlook.rows.length);
    await expect(page.getByTestId("season-row").first().getByTestId("playoff-odds")).toHaveText(pct(o.outlook.rows[0].playoff));
    await expect(page.getByTestId("season-words")).toContainText(`${o.outlook.playoff_teams} teams make the playoffs`);
    await expect(page.getByTestId("season-assumes")).toContainText("rosters as they are today");
    await expect(page.getByTestId("season-assumes")).toContainText("the further out the week, the wider its range");
    await expect(page.getByTestId("season-honest")).toContainText("not a graded forecast");
    await expect(season).toContainText("No title odds");
    await expect(season).not.toContainText("Bye");                          // four spots: no byes
    await page.getByTestId("def-playoff_odds").click();
    await expect(season.getByTestId("league-def")).toHaveText(o.definitions.playoff_odds);
    await noSidewaysScroll(page);
    if (info.project.name === "phone") {
      // the team column stays while the numbers scroll inside the table
      const box = page.getByTestId("power-scroll");
      const before = await page.getByTestId("power-row").first().locator("th").boundingBox();
      await box.evaluate((el) => (el.scrollLeft = 400));
      const after = await page.getByTestId("power-row").first().locator("th").boundingBox();
      expect(Math.abs(after!.x - before!.x)).toBeLessThan(2);
      expect(await box.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
    } else {
      // the width is used: the blocks span the page and draw bars
      const w = (await power.boundingBox())!.width;
      expect(w).toBeGreaterThan(1000);
      await expect(page.getByTestId("power-row").first().locator("td").first().locator("span.wide\\:block")).toBeVisible();
    }
    await shot(page, `scrubs-${scheme}`, info.project.name);
  });
}

test("a league with byes: the bye column; a league without an outlook keeps the rankings and says why", async ({ page }, info) => {
  const d = read("outlook_dynasty_12.json");
  await page.goto(`/league?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("season-row")).toHaveCount(d.outlook.rows.length);
  await expect(page.getByTestId("def-bye")).toBeVisible();
  await expect(page.getByTestId("season-words")).toContainText("6 teams make the playoffs");
  await expect(page.locator('[data-testid="season-row"][data-yours="1"]')).toHaveCount(1);
  await noSidewaysScroll(page);
  await shot(page, "dynasty", info.project.name);

  const t = read("outlook_test_3.json");
  await page.goto(`/league?league=${TEST_LEAGUE}&team=3`);
  await expect(page.getByTestId("power-row")).toHaveCount(t.power.rows.length);
  await expect(page.getByTestId("no-outlook")).toHaveText(`No outlook for the rest of the season: ${t.outlook.reason}.`);
  await expect(page.getByTestId("season-row")).toHaveCount(0);
  await noSidewaysScroll(page);
  await shot(page, "no-outlook", info.project.name);
});
