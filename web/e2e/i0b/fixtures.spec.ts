// Wave I-0 (I0-B): a MyFantasyLeague league on fixtures — the Leagues screen's second way in (paste the league link →
// the league card → pick the team → the same My Week), the "MFL" mark in the league switcher, a league MFL will not
// share. The MFL answers are the API's own (web/fixtures/mfl/*.json, saved from api/tests/fixtures/mfl through the API);
// every other /api call is e2e/fixtures.ts's.
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const MFL = join(import.meta.dirname, "..", "..", "fixtures", "mfl");
const read = (name: string) => readFileSync(join(MFL, name), "utf8");

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

test.beforeEach(async ({ context }) => {
  await serveFixtures(context);
  // registered after serveFixtures: asked first; anything that is not an MFL call falls through to it
  await context.route(/\/api\//, async (route) => {
    const url = new URL(route.request().url());
    const q = url.searchParams;
    const send = (status: number, body: string) =>
      route.fulfill({ status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body });
    // I0-C: the box now asks ?mfl_search= (a link answers exactly as ?mfl= does)
    if (url.pathname === "/api/leagues" && (q.has("mfl") || q.has("mfl_search"))) {
      return (q.get("mfl") ?? q.get("mfl_search"))!.includes("21861") ? send(200, read("league_21861.json")) : send(404, read("private.json"));
    }
    if (url.pathname === "/api/leagues/mfl%3A21861/rosters" || url.pathname === "/api/leagues/mfl:21861/rosters")
      return send(200, read("rosters_21861.json"));
    if (url.pathname === "/api/my-week" && q.get("league") === "mfl:21861" && q.get("team") === "4")
      return send(200, read("my-week_21861_4.json"));
    return route.fallback();
  });
});

test("MyFantasyLeague: paste the league link → pick the team → My Week; the switcher says MFL", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("leagues")).toBeVisible();
  await page.getByTestId("platform-mfl").click(); // ---- II-5 (Wave I-I): the fantasy platform first
  await expect(page.getByText("Find your MyFantasyLeague league")).toBeVisible(); // I0-C: the box also takes a name; II-5: the label

  // a league MFL will not share: the sentence, no card
  await page.getByTestId("mfl-link").fill("https://www45.myfantasyleague.com/2026/home/99999999");
  await page.getByTestId("mfl-go").click();
  await expect(page.getByTestId("mfl-error")).toContainText("Ask the commissioner to allow API access");
  await expect(page.getByTestId("mfl-card")).toHaveCount(0);

  // the public league 21861
  await page.getByTestId("mfl-link").fill("https://www45.myfantasyleague.com/2026/home/21861");
  await page.getByTestId("mfl-go").click();
  const card = page.getByTestId("mfl-card");
  await expect(card).toBeVisible();
  await expect(card).toContainText("Addicts 1 Redraft $300 No Trade");
  await expect(card).toContainText("12-team redraft · full PPR");
  await expect(page.getByTestId("mfl-note")).toContainText("Lineup read as QB, 2 RB, 2 WR, TE, 2 FLEX, K, DEF");
  await expect(page.getByTestId("mfl-team")).toHaveCount(12);
  await noSidewaysScroll(page);

  await page.getByTestId("mfl-team").filter({ hasText: "Matt and Doug's Team" }).click();
  await expect(page).toHaveURL(/league=mfl(%3A|:)21861/);
  await expect(page).toHaveURL(/team=4/);
  await expect(page.getByText("Matthew Stafford").first()).toBeVisible();
  await expect(page.locator("strong", { hasText: "Mahafaha" }).first()).toBeVisible(); // this week's opponent (MFL's schedule)
  await noSidewaysScroll(page);

  // remembered on this phone like a Sleeper league; the switcher marks it MFL
  const saved = await page.evaluate(() => JSON.parse(window.localStorage.getItem("ll.mflLeagues") ?? "[]"));
  expect(saved[0]).toMatchObject({ league_id: "mfl:21861", roster_id: 4, team_name: "Matt and Doug's Team" });
  await expect(page.locator("option", { hasText: "Addicts 1 Redraft $300 No Trade · MFL" })).toHaveCount(1);
});
