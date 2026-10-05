// Wave I-I (II-5): one setup flow — Fantasy platform → the identifier → the league → the team → My Week (review § 9).
// Sleeper by username (fixture_user / fixture_commish: the shared fixtures), Sleeper by a league link, MFL by a league
// id; the specific error words (the API's `code` / `fix`); what each platform gives (GET /api/providers); the League
// screen saying MFL moves are not read. Phone at 375 and desktop at 1300.
// The answers are the API's own, recorded from a fixture API (api/tests/fixtures/{sleeper,mfl}) into web/fixtures/ii5/:
//   curl localhost:8726/api/providers > web/fixtures/ii5/providers.json   (and the rest: see the STATUS hand-back)
import { expect, test, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures, TEST_LEAGUE } from "../fixtures";

const DIR = join(import.meta.dirname, "..", "..", "fixtures");
const read = (name: string) => readFileSync(join(DIR, "ii5", name), "utf8");
const IC4 = JSON.parse(readFileSync(join(DIR, "mfl", "api_70587_ic4.json"), "utf8")) as Record<string, { status: number; body: unknown }>;
const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out");

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

let asked: string[] = [];

test.beforeEach(async ({ context, page, isMobile }) => {
  asked = [];
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
  await serveFixtures(context);
  await context.route(/\/api\//, async (route: Route) => {
    const url = new URL(route.request().url());
    const q = url.searchParams;
    const send = (status: number, body: string) =>
      route.fulfill({ status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body });
    if (url.pathname === "/api/providers") return send(200, read("providers.json"));
    if (url.pathname === "/api/leagues") {
      asked.push(url.search);
      if (q.get("username") === "nobody_here") return send(404, read("error_user_unknown.json"));
      const sl = q.get("sleeper");
      if (sl !== null) return sl.includes(TEST_LEAGUE) ? send(200, read(`sleeper_${TEST_LEAGUE}.json`)) : send(404, read("error_sleeper_league_unknown.json"));
      const m = q.get("mfl_search") ?? q.get("mfl");
      if (m !== null) {
        if (m.includes("70587")) return send(200, read("mfl_70587.json"));
        if (m.includes("99999999")) return send(404, read("error_mfl_private.json"));
        return send(404, read("error_mfl_link.json"));
      }
    }
    if (url.pathname === "/api/my-week" && q.get("league") === "mfl:70587" && q.get("team") === "8") return send(200, read("my-week_mfl70587_8.json"));
    // the League screen of dad's league (IC-4's recording)
    const key = url.pathname + url.search;
    if (key.includes("70587") && IC4[key]) return send(IC4[key].status, JSON.stringify(IC4[key].body));
    return route.fallback();
  });
});

test("Sleeper: platform → username (a wrong one first) → leagues → My Week", async ({ page }, info) => {
  await page.goto("/leagues");
  await expect(page.getByTestId("setup-steps")).toBeVisible();
  await expect(page.locator('[data-testid="setup-steps"] [aria-current="step"]')).toHaveAttribute("data-step", "league");
  await expect(page.getByTestId("platform-sleeper").locator("input")).toBeChecked();
  await expect(page.getByTestId("username-form")).toBeVisible();
  await expect(page.getByTestId("mfl-form")).toHaveCount(0);
  await expect(page.getByTestId("setup-guest")).toHaveText("No account needed: isuckatfantasy remembers your leagues on this device.");

  // where to find it, with an example
  await page.getByTestId("setup-help").locator("summary").click();
  await expect(page.getByTestId("setup-help")).toContainText("sleeper.com/leagues/1389709692405551104/team");
  await expect(page.getByTestId("setup-help")).toContainText("not your team's name");

  // what Sleeper gives: eight lines, nothing missing
  const caps = page.getByTestId("provider-caps");
  await expect(caps).toContainText("What isuckatfantasy reads from Sleeper leagues");
  await expect(caps).not.toContainText("not available yet");
  await caps.locator("summary").click();
  await expect(caps.getByTestId("cap")).toHaveCount(8);
  await expect(caps.locator('[data-feature="team_assets"]')).toHaveAttribute("data-status", "partial");

  // a username that does not exist: the specific words and the fix
  await page.getByTestId("username").fill("nobody_here");
  await page.getByTestId("username-go").click();
  const err = page.getByTestId("username-error");
  await expect(err).toHaveText("That Sleeper username does not exist: “nobody_here”.");
  await expect(err).toHaveAttribute("data-code", "sleeper_user_unknown");
  await expect(page.getByTestId("setup-fix")).toContainText("the name you sign in to Sleeper with");
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ii5-sleeper-error-${info.project.name}.png`), fullPage: true });

  // the right one: the leagues, the team pre-selected, then My Week
  await page.getByTestId("username").fill("fixture_user");
  await page.getByTestId("username-go").click();
  await expect(page.getByTestId("username-error")).toHaveCount(0);
  await expect(page.getByTestId("league-row")).toHaveCount(3);
  const row = page.locator(`[data-testid="league-row"][data-league="${TEST_LEAGUE}"]`);
  await expect(row).toContainText("Your team: Fixture Falcons");
  await noSidewaysScroll(page);
  await row.click();
  await expect(page).toHaveURL(new RegExp(`league=${TEST_LEAGUE}&team=3`));
  await expect(page.getByTestId("team-name")).toHaveText("Fixture Falcons");
});

test("Sleeper by a league link: the league, which team is yours, My Week (and a wrong id says so)", async ({ page }, info) => {
  await page.goto("/leagues");
  await page.getByTestId("username").fill("1234567890123456");
  await page.getByTestId("username-go").click();
  await expect(page.getByTestId("username-error")).toHaveText("Sleeper has no football league 1234567890123456.");
  await expect(page.getByTestId("username-error")).toHaveAttribute("data-code", "sleeper_league_unknown");

  await page.getByTestId("username").fill(`https://sleeper.com/leagues/${TEST_LEAGUE}/team`);
  await page.getByTestId("username-go").click();
  const card = page.getByTestId("sleeper-card");
  await expect(card).toContainText("Test League");
  await expect(page.locator('[data-testid="setup-steps"] [aria-current="step"]')).toHaveAttribute("data-step", "team");
  await expect(card.getByTestId("team-option")).toHaveCount(10);
  expect(asked.at(-1)).toContain("sleeper=");
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ii5-sleeper-link-${info.project.name}.png`), fullPage: true });
  await card.locator('[data-testid="team-option"][data-roster="3"]').click();
  await expect(page).toHaveURL(new RegExp(`league=${TEST_LEAGUE}&team=3`));
  await expect(page.getByTestId("team-name")).toHaveText("Fixture Falcons");
});

test("a league with no team of yours: pick the team on the setup screen", async ({ page }) => {
  await page.goto("/leagues");
  await page.getByTestId("username").fill("fixture_commish");
  await page.getByTestId("username-go").click();
  const row = page.getByTestId("league-row");
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("You have no team in this league: pick the team to see below.");
  await page.getByTestId("team-pick-open").locator("summary").click();
  const opts = page.getByTestId("team-pick-open").getByTestId("team-option");
  await expect(opts).toHaveCount(10);
  await opts.and(page.locator('[data-roster="3"]')).click();
  await expect(page).toHaveURL(new RegExp(`league=${TEST_LEAGUE}&team=3`));
  await expect(page.getByTestId("team-name")).toHaveText("Fixture Falcons");
});

test("MFL: platform → league id (a private one first) → team → My Week; transactions said unavailable", async ({ page }, info) => {
  await page.goto("/leagues");
  await page.getByTestId("platform-mfl").click();
  await expect(page).toHaveURL(/platform=mfl/);
  await expect(page.getByTestId("username-form")).toHaveCount(0);
  await expect(page.getByTestId("mfl-form")).toBeVisible();

  await page.getByTestId("setup-help").locator("summary").click();
  await expect(page.getByTestId("setup-help")).toContainText("www45.myfantasyleague.com/2026/home/70587 is league 70587");

  const caps = page.getByTestId("provider-caps");
  await expect(caps).toContainText("What isuckatfantasy reads from MFL leagues — 1 not available yet");
  await caps.locator("summary").click();
  await expect(caps.locator('[data-feature="transactions"]')).toContainText("Transactions: not available for MFL leagues yet.");
  await expect(caps.locator('[data-feature="transactions"]')).toHaveAttribute("data-status", "no");

  // a league MFL will not share
  await page.getByTestId("mfl-link").fill("99999999");
  await page.getByTestId("mfl-go").click();
  const err = page.getByTestId("mfl-error");
  await expect(err).toContainText("MFL league 99999999 is private or does not exist. Ask the commissioner to allow API access");
  await expect(err).toHaveAttribute("data-code", "mfl_league_private");
  await expect(page.getByTestId("setup-fix")).toContainText("the number after /home/");
  // not a league link at all
  await page.getByTestId("mfl-link").fill("https://example.com/x");
  await page.getByTestId("mfl-go").click();
  await expect(err).toHaveText("That is not a MyFantasyLeague league link or id.");
  await expect(err).toHaveAttribute("data-code", "mfl_link_invalid");
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ii5-mfl-error-${info.project.name}.png`), fullPage: true });

  // dad's league: the card, which team is yours, My Week
  await page.getByTestId("mfl-link").fill("70587");
  await page.getByTestId("mfl-go").click();
  await expect(page.getByTestId("mfl-card")).toBeVisible();
  await expect(page.getByTestId("mfl-error")).toHaveCount(0);
  await expect(page.locator('[data-testid="setup-steps"] [aria-current="step"]')).toHaveAttribute("data-step", "team");
  await expect(page.getByTestId("mfl-team")).toHaveCount(12);
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ii5-mfl-team-${info.project.name}.png`), fullPage: true });
  await page.locator('[data-testid="mfl-team"][data-roster="8"]').click();
  await expect(page).toHaveURL(/league=mfl%3A70587&team=8|league=mfl:70587&team=8/);
  await expect(page.getByTestId("team-name")).toHaveText("Big Mac Attack");
});

test("the platform is remembered, ?platform= opens it, ESPN and Yahoo are choices of their own", async ({ page }) => {
  await page.goto("/leagues?platform=mfl");
  await expect(page.getByTestId("mfl-form")).toBeVisible();
  await page.goto("/leagues");
  await expect(page.getByTestId("mfl-form")).toBeVisible(); // remembered on this device
  await page.getByTestId("platform-sleeper").click();
  await expect(page.getByTestId("username-form")).toBeVisible();
  // ---- IK-3 (Wave I-K): II-5's "ESPN or Yahoo? Not supported yet" expander became the ESPN and Yahoo choices (e2e/ik3)
  await expect(page.getByTestId("other-platforms")).toHaveCount(0);
  await expect(page.getByTestId("platform-espn")).toBeVisible();
  await expect(page.getByTestId("platform-yahoo")).toBeVisible();
});

test("League: an MFL league's moves are said not read, never 'No completed moves'", async ({ page }) => {
  await page.goto("/league?league=mfl%3A70587&team=1");
  await expect(page.getByTestId("moves")).toBeVisible();
  await expect(page.getByTestId("moves-unavailable")).toHaveText("Transactions: not available for MFL leagues yet.");
  await expect(page.getByTestId("moves")).not.toContainText("No completed moves");
});
