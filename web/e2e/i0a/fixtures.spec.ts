// Wave I-0 (I0-A) on fixtures: My Week with the availability overlay — the "Injuries checked" stamp in place of the
// stale-news warning, the sentences of who moved and why under the lineup header, the OUT / IR chips with their reason.
// The two answers are the API's own (Scrubs roster 2, the database clone, ESPN's feed fixture with Justin Jefferson
// ruled Out), saved with the stamp pinned to 2026-10-02 18:40 UTC (2:40 PM ET). Phone 390 × 844 and desktop 1300 × 900.
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { SCRUBS, serveFixtures } from "../fixtures";

const read = (name: string) => readFileSync(join(import.meta.dirname, name), "utf8");
const week = read(`my-week_${SCRUBS}_2.json`);

test.use({ timezoneId: "America/New_York" });

test.beforeEach(async ({ context }) => {
  await serveFixtures(context);
  // registered after the fixture server, so these two answer first
  await context.route(/\/api\/my-week\?/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: week }));
  await context.route(/\/api\/status$/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: read("status.json") }));
});

test("My Week: injuries checked, who moved and why, the OUT chip (Scrubs roster 2, Jefferson ruled out)", async ({ page }) => {
  const d = JSON.parse(week);
  await page.goto(`/?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("team-name")).toHaveText("MacZaddy");
  await expect(page.getByTestId("injuries-checked")).toHaveText(/^Injuries checked (Fri )?2:40 PM$/);
  await expect(page.getByTestId("stale-warning")).toHaveCount(0);
  const changes = page.getByTestId("availability-changes");
  await expect(changes.locator("li")).toHaveCount(d.availability.changes.length);
  await expect(changes).toContainText("Justin Jefferson is out (ankle) — Michael Wilson starts at FLEX2");
  const lineup = page.getByTestId("lineup");
  await expect(lineup).toContainText("Michael Wilson");
  await expect(lineup).not.toContainText("Justin Jefferson");
  await page.getByTestId("lineup-full").locator("summary, button").first().click();
  const row = page.getByTestId("lineup-full-table").locator("tr", { hasText: "Justin Jefferson" });
  await expect(row).toContainText("Can't play");
  await expect(row.getByTestId("avail-chip")).toHaveText("OUT");
  await expect(row.getByTestId("avail-reason")).toHaveText("Out (ankle) · ESPN, Oct 2 2:35 PM ET");
  await expect(page.getByTestId("lineup-full-table").getByTestId("avail-chip")).toHaveCount(
    d.lineup_full.filter((r: { flag: string }) => ["OUT", "DOUBTFUL", "IR"].includes(r.flag)).length,
  );
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw).toBeLessThanOrEqual(iw);
});
