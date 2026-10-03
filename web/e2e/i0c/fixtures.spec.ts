// Wave I-0 (I0-C): find a MyFantasyLeague league by its name — the one MFL box takes a link, an id or the name; a name
// lists this season's matches; tapping one opens the league card and the team picker (I0-B's flow), then My Week.
// The answers are the API's own (web/fixtures/mfl/search_*.json saved through the API from
// api/tests/fixtures/mfl/leagueSearch_addicts.json; league_21861 / rosters / my-week are I0-B's).
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const MFL = join(import.meta.dirname, "..", "..", "fixtures", "mfl");
const read = (name: string) => readFileSync(join(MFL, name), "utf8");
const LINK = /myfantasyleague\.com|^\d{1,8}$|^mfl:/i;

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

let asked: string[] = [];

test.beforeEach(async ({ context }) => {
  asked = [];
  await serveFixtures(context);
  await context.route(/\/api\//, async (route) => {
    const url = new URL(route.request().url());
    const q = url.searchParams;
    const send = (status: number, body: string) =>
      route.fulfill({ status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body });
    if (url.pathname === "/api/leagues" && (q.has("mfl_search") || q.has("mfl"))) {
      asked.push(url.search);
      const t = (q.get("mfl_search") ?? q.get("mfl") ?? "").trim();
      if (q.has("mfl") || LINK.test(t)) return t.includes("21861") ? send(200, read("league_21861.json")) : send(404, read("private.json"));
      if (t.length < 3) return send(200, read("search_short.json"));
      return t.toLowerCase().includes("addicts") ? send(200, read("search_addicts.json")) : send(200, read("search_none.json"));
    }
    if (url.pathname === "/api/leagues/mfl%3A21861/rosters" || url.pathname === "/api/leagues/mfl:21861/rosters")
      return send(200, read("rosters_21861.json"));
    if (url.pathname === "/api/my-week" && q.get("league") === "mfl:21861" && q.get("team") === "4")
      return send(200, read("my-week_21861_4.json"));
    return route.fallback();
  });
});

test("MyFantasyLeague by name: type the name → pick the league → pick the team → My Week", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("leagues")).toBeVisible();
  await expect(page.getByTestId("mfl-help")).toContainText(
    "Paste your league link, or type your league's name as it appears in the MFL app.",
  );

  // a name nothing matches: the sentence, no list
  await page.getByTestId("mfl-link").fill("Zebra Llama Club");
  await page.getByTestId("mfl-go").click();
  await expect(page.getByTestId("mfl-search-note")).toContainText("No MyFantasyLeague league this season");
  await expect(page.getByTestId("mfl-match")).toHaveCount(0);

  // the name: this season's matches (25 shown of 30), each "MFL · 2026"
  await page.getByTestId("mfl-link").fill("addicts");
  await page.getByTestId("mfl-go").click();
  await expect(page.getByTestId("mfl-match")).toHaveCount(25);
  await expect(page.getByTestId("mfl-search-note")).toContainText("first 25 of 30");
  const pick = page.getByTestId("mfl-match").filter({ hasText: "Addicts 1 Redraft $300 No Trade" });
  await expect(pick).toContainText("MFL · 2026");
  await expect(page.getByTestId("mfl-card")).toHaveCount(0);
  await noSidewaysScroll(page);
  expect(asked.at(-1)).toContain("mfl_search=addicts");

  // tap it: the league card and the team picker (the pasted-link flow)
  await pick.click();
  const card = page.getByTestId("mfl-card");
  await expect(card).toBeVisible();
  await expect(card).toContainText("Addicts 1 Redraft $300 No Trade");
  await expect(page.getByTestId("mfl-team")).toHaveCount(12);
  expect(asked.at(-1)).toMatch(/[?&]mfl=mfl(%3A|:)21861/);

  // "Not this league" goes back to the list
  await page.getByTestId("mfl-back").click();
  await expect(page.getByTestId("mfl-match")).toHaveCount(25);
  await pick.click();
  await expect(page.getByTestId("mfl-team")).toHaveCount(12);
  await noSidewaysScroll(page);

  await page.getByTestId("mfl-team").filter({ hasText: "Matt and Doug's Team" }).click();
  await expect(page).toHaveURL(/league=mfl(%3A|:)21861/);
  await expect(page).toHaveURL(/team=4/);
  await expect(page.getByText("Matthew Stafford").first()).toBeVisible();

  // remembered on this phone, as a pasted link is
  const saved = await page.evaluate(() => JSON.parse(window.localStorage.getItem("ll.mflLeagues") ?? "[]"));
  expect(saved[0]).toMatchObject({ league_id: "mfl:21861", roster_id: 4, team_name: "Matt and Doug's Team" });
  await expect(page.locator("option", { hasText: "Addicts 1 Redraft $300 No Trade · MFL" })).toHaveCount(1);
});

test("MyFantasyLeague box: an id or a link still goes straight to the league card; two letters ask for more", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("mfl-link").fill("ad");
  await page.getByTestId("mfl-go").click();
  await expect(page.getByTestId("mfl-search-note")).toContainText("at least 3 letters");

  await page.getByTestId("mfl-link").fill("21861"); // a bare id: no browser "enter a URL" refusal (the box is text)
  await page.getByTestId("mfl-go").click();
  await expect(page.getByTestId("mfl-card")).toContainText("Addicts 1 Redraft $300 No Trade");
  await expect(page.getByTestId("mfl-match")).toHaveCount(0);
  await expect(page.getByTestId("mfl-back")).toHaveCount(0);
  expect(asked.at(-1)).toContain("mfl_search=21861");
});
