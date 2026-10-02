// The web app, phase 1 (plan F2), on fixtures (e2e/fixtures.ts answers every /api call from web/fixtures/*.json):
// the stranger's path — password → Sleeper username → league picker → My Week → tap a player → his card → Back (same
// scroll) → rest of season → our record — at 390 × 844 (phone) and 1300 × 900 (desktop), for a league the database
// has never seen (the fictional Test League) and for the house leagues. Screenshots: SHOTS_DIR (default e2e/.out).
import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { DYNASTY, FIXTURE_PASSWORD, SCRUBS, serveFixtures, TEST_LEAGUE } from "./fixtures";

const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, ".out");
mkdirSync(SHOTS, { recursive: true });

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

async function tap(page: Page, loc: Locator, isMobile: boolean) {
  if (isMobile) await loc.tap();
  else await loc.click();
}

async function shot(page: Page, name: string, project: string, full = true) {
  await page.screenshot({ path: join(SHOTS, `f2_${name}_${project}.png`), fullPage: full });
}

test.beforeEach(async ({ context }) => {
  await serveFixtures(context); // signed in (no gate) unless a test serves its own
});

test("a stranger: password → username → picker → My Week → player → Back → rest of season → record (Test League, no database)", async ({
  browser,
  isMobile,
}, info) => {
  const context = await browser.newContext({ ...info.project.use, serviceWorkers: "block" });
  const api = await serveFixtures(context, { gate: true });
  const page = await context.newPage();
  const project = info.project.name;
  let popups = 0;
  context.on("page", () => popups++);

  // 1. the beta password stays first
  await page.goto("/");
  await expect(page.getByTestId("login")).toBeVisible();
  await page.getByPlaceholder("Password").fill("not it");
  await page.getByRole("button", { name: "Open League Lab" }).click();
  await expect(page.getByText("That is not it.")).toBeVisible();
  await page.getByPlaceholder("Password").fill(FIXTURE_PASSWORD);
  await page.getByRole("button", { name: "Open League Lab" }).click();

  // 2. no league known on this phone: the username screen
  await expect(page.getByTestId("username-form")).toBeVisible();
  await expect(page.getByText("Your Sleeper username")).toBeVisible();
  await noSidewaysScroll(page);
  await shot(page, "signin", project, false);
  await page.getByTestId("username").fill("nobody_here");
  await page.getByTestId("username-go").click();
  await expect(page.getByTestId("username-error")).toContainText("Sleeper has no user called “nobody_here”");
  await page.getByTestId("username").fill("fixture_user");
  await page.getByTestId("username-go").click();

  // 3. the picker: the user's leagues this season (name, size + scoring, the user's own team)
  const rows = page.getByTestId("league-row");
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(0)).toContainText("Forever Unclean Dynasty");
  const testRow = page.locator(`[data-testid="league-row"][data-league="${TEST_LEAGUE}"]`);
  await expect(testRow).toContainText("Test League");
  await expect(testRow).toContainText("10-team redraft · half PPR"); // size + scoring (the label starts with the size)
  await expect(testRow).toContainText("Your team: Fixture Falcons");
  await noSidewaysScroll(page);
  await shot(page, "picker", project);

  // 4. one tap → My Week for a league the database has never seen, the user's team pre-selected
  await tap(page, testRow, isMobile);
  await expect(page).toHaveURL(new RegExp(`/\\?league=${TEST_LEAGUE}&team=3$`));
  await expect(page.getByTestId("team-name")).toHaveText("Fixture Falcons");
  await expect(page.getByTestId("record-line")).toHaveText("2-1, #3 in the league");
  await expect(page.getByTestId("opponent-line")).toHaveText("Week 4 vs Hail Marys, projects 108 — you project 134");
  await expect(page.getByTestId("decision-card")).toHaveCount(3);
  const first = page.getByTestId("decision-card").first();
  const box = (await first.boundingBox())!;
  expect(box.y + box.height, "the first card ends below the first screen").toBeLessThanOrEqual(page.viewportSize()!.height);
  expect(await page.getByTestId("lineup").locator("thead th").count()).toBeLessThanOrEqual(5);
  await expect(page.getByTestId("pick-team")).toHaveValue("3");
  await noSidewaysScroll(page);
  expect(await page.getByText(/not in the database/i).count()).toBe(0);
  await shot(page, "week_test", project, false);
  await page.getByTestId("lineup-full").locator("summary").click();
  await page.getByTestId("howto").locator("summary").click();
  await noSidewaysScroll(page);
  await shot(page, "week_test_full", project);

  // 5. a name in the lineup: one tap, same tab → the player card in this league
  const link = page.getByTestId("lineup").locator("a", { hasText: "Trey McBride" });
  await link.scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollBy(0, 40));
  const y = await page.evaluate(() => window.scrollY);
  expect(y).toBeGreaterThan(0);
  const h0 = await page.evaluate(() => history.length);
  await tap(page, link, isMobile);
  await expect(page).toHaveURL(new RegExp(`/player/00-0037744\\?league=${TEST_LEAGUE}&team=3$`));
  await expect(page.getByTestId("player-name")).toHaveText("Trey McBride");
  expect(await page.evaluate(() => history.length)).toBe(h0 + 1);
  for (const s of ["projection", "availability", "usage", "signals"]) await expect(page.getByTestId(`section-${s}`)).toBeVisible();
  await expect(page.getByTestId("section-value")).toHaveCount(0); // listed in `missing`: omitted, said in one line
  await expect(page.getByTestId("missing")).toHaveText("Not shown for Test League yet: Value.");
  await expect(page.getByTestId("section-projection")).toContainText(/Rest of season: \d+ points over \d+ games/);
  await expect(page.getByTestId("section-projection").getByRole("link", { name: "Every TE for the rest of the season" })).toBeVisible();
  await noSidewaysScroll(page);
  await shot(page, "player_test", project);

  // 6. Back: My Week at the same scroll position
  await tap(page, page.getByTestId("back"), isMobile);
  await expect(page).toHaveURL(new RegExp(`/\\?league=${TEST_LEAGUE}&team=3$`));
  await expect(page.getByTestId("decision-card").first()).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(y);

  // 7. rest of season: the answer first, then yours, then the list; K / DEF because this league starts them
  await tap(page, page.getByTestId("tab-ros"), isMobile);
  await expect(page).toHaveURL(new RegExp(`/ros\\?league=${TEST_LEAGUE}&team=3$`));
  await expect(page.getByTestId("ros-answer")).toContainText(/^#1 overall for the rest of the season: .+ \((QB|RB|WR|TE)\), \d+ points over \d+ games/);
  await expect(page.getByTestId("ros-pos-K")).toBeVisible();
  await expect(page.getByTestId("ros-pos-DEF")).toBeVisible();
  await tap(page, page.getByTestId("ros-pos-WR"), isMobile);
  await expect(page).toHaveURL(new RegExp(`/ros\\?league=${TEST_LEAGUE}&team=3&position=WR$`));
  await expect(page.getByTestId("ros-answer")).toContainText(
    "#1 WR for the rest of the season: Puka Nacua, 185 points over 12 games (likely 150–219) · playoffs: 30.",
  );
  await expect(page.getByTestId("ros-yours")).toContainText("Yours: #3 Jaxon Smith-Njigba 178");
  expect(await page.getByTestId("ros-table").locator("thead th").allTextContents()).toEqual(["Rank", "Player", "Points", "Games", "Playoffs"]);
  await expect(page.getByTestId("ros-table").locator("tbody tr")).toHaveCount(50);
  await noSidewaysScroll(page);
  await shot(page, "ros_test", project, false);

  // 8. our record: an unknown league has none, said in plain words
  await tap(page, page.getByTestId("tab-record"), isMobile);
  await expect(page).toHaveURL(new RegExp(`/record\\?league=${TEST_LEAGUE}`));
  await expect(page.getByTestId("record-empty")).toContainText("No record for Test League. The record is kept for the leagues the nightly scores.");
  await noSidewaysScroll(page);
  await shot(page, "record_test", project, false);

  // 9. remembered on this phone: a bare visit (the home-screen icon) opens the same league and team
  await page.goto("/");
  await expect(page.getByTestId("team-name")).toHaveText("Fixture Falcons");
  await expect(page).toHaveURL(new RegExp(`/\\?league=${TEST_LEAGUE}&team=3$`));
  expect(popups, "a new tab opened").toBe(0);
  expect(api.calls.some((c) => c.startsWith("/api/leagues?username=fixture_user"))).toBe(true);
  await context.close();
});

test("a house league through the picker: opponent, a card's name, all five sections, rest of season (no K / DEF), the record", async ({
  page,
  isMobile,
}, info) => {
  const project = info.project.name;
  await page.goto("/");
  await page.getByTestId("username").fill("fixture_user");
  await page.getByTestId("username-go").click();
  await tap(page, page.locator(`[data-testid="league-row"][data-league="${DYNASTY}"]`), isMobile);
  await expect(page.getByTestId("team-name")).toHaveText("Shake & Bake");
  await expect(page.getByTestId("record-line")).toHaveText("0-2, #10 in the league");
  await expect(page.getByTestId("opponent-line")).toHaveText("Week 4 vs 2 da Moon wit Love, projects 110.7 — you project 111.2");
  await shot(page, "week_dyn12", project, false);
  const name = page.getByTestId("decision-card").first().locator("a").first();
  const who = (await name.textContent())!.trim();
  await tap(page, name, isMobile);
  await expect(page.getByTestId("player-name")).toHaveText(who);
  for (const s of ["projection", "value", "availability", "usage", "signals"]) await expect(page.getByTestId(`section-${s}`)).toBeVisible();
  await expect(page.getByTestId("missing")).toHaveCount(0);
  await shot(page, "player_dyn12", project);
  await page.goBack();
  await expect(page.getByTestId("team-name")).toHaveText("Shake & Bake");
  await tap(page, page.getByTestId("tab-ros"), isMobile);
  await expect(page.getByTestId("ros-answer")).toBeVisible();
  await expect(page.getByTestId("ros-pos-K")).toHaveCount(0); // the dynasty starts no kicker / defense
  await expect(page.getByTestId("ros-pos-DEF")).toHaveCount(0);
  await tap(page, page.getByTestId("ros-pos-WR"), isMobile);
  await expect(page.getByTestId("ros-yours")).toContainText("Amon-Ra St. Brown");
  await shot(page, "ros_dyn12", project, false);
  await tap(page, page.getByTestId("tab-record"), isMobile);
  await expect(page.getByTestId("record-answer")).toContainText("Through week 3, we called 63 of 107 start/sit calls right; Sleeper's numbers called 58.");
  await expect(page.getByTestId("record-answer")).toContainText("Where we and Sleeper disagreed (19 calls), we were right 12 times and Sleeper 7.");
  await expect(page.getByTestId("record-table").locator("tbody tr")).toHaveCount(3);
  expect(await page.getByTestId("record-table").locator("thead th").count()).toBeLessThanOrEqual(5);
  await noSidewaysScroll(page);
  await shot(page, "record_dyn12", project);
});

test("a shared link wins (no username needed); Scrubs: K and DEF in rest of season; an empty record says so", async ({ page, isMobile }, info) => {
  const project = info.project.name;
  await page.goto(`/?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("team-name")).toHaveText("MacZaddy");
  await expect(page.getByTestId("opponent-line")).toHaveText("Week 4 vs Daejon Loves PR team, projects 115 — you project 117");
  await tap(page, page.getByTestId("tab-ros"), isMobile);
  await expect(page.getByTestId("ros-pos-K")).toBeVisible();
  await tap(page, page.getByTestId("ros-pos-K"), isMobile);
  await expect(page.getByTestId("ros-answer")).toContainText("#1 K for the rest of the season:");
  await tap(page, page.getByTestId("tab-record"), isMobile);
  await expect(page.getByTestId("record-empty")).toContainText("No week on the record yet.");
  await shot(page, "record_scrubs_empty", project, false);
  // the league select's last option opens the sign-in / picker; "‹ My week" comes back to the same team
  await page.getByTestId("pick-league").selectOption("__leagues");
  await expect(page).toHaveURL(/\/leagues$/);
  await expect(page.getByTestId("username-form")).toBeVisible();
  await tap(page, page.getByTestId("to-week"), isMobile);
  await expect(page.getByTestId("team-name")).toHaveText("MacZaddy");
});

test("no team in a league (commissioner only): said in plain words, pick a team, then My Week", async ({ page, isMobile }, info) => {
  await page.goto("/leagues");
  await page.getByTestId("username").fill("fixture_commish");
  await page.getByTestId("username-go").click();
  const row = page.getByTestId("league-row");
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("You have no team in this league");
  await tap(page, row, isMobile);
  await expect(page.getByTestId("no-team")).toContainText("You have no team in Test League");
  await shot(page, "noteam", info.project.name, false);
  await page.getByTestId("pick-team").selectOption("3");
  await expect(page.getByTestId("team-name")).toHaveText("Fixture Falcons");
  await expect(page).toHaveURL(new RegExp(`\\?league=${TEST_LEAGUE}&team=3$`));
});

test("Sleeper down, and Not you? forgets the username", async ({ page }) => {
  await page.goto("/leagues");
  await page.getByTestId("username").fill("sleeper_down");
  await page.getByTestId("username-go").click();
  await expect(page.getByTestId("username-error")).toHaveText("Sleeper did not answer. Try again in a minute.");
  await page.getByTestId("username").fill("fixture_user");
  await page.getByTestId("username-go").click();
  await expect(page.getByTestId("league-row")).toHaveCount(3);
  await page.reload();
  await expect(page.getByTestId("league-row")).toHaveCount(3); // remembered: no typing on the next visit
  await expect(page.getByTestId("username")).toHaveValue("fixture_user");
  await page.getByTestId("not-me").click();
  await expect(page.getByTestId("league-row")).toHaveCount(0);
  await expect(page.getByTestId("username")).toHaveValue("");
});

test("dark mode follows the system", async ({ browser }, info) => {
  const ctx = await browser.newContext({ ...info.project.use, colorScheme: "dark" });
  await serveFixtures(ctx);
  const page = await ctx.newPage();
  await page.goto(`/?league=${TEST_LEAGUE}&team=3`);
  await expect(page.getByTestId("decision-card").first()).toBeVisible();
  // a linked league in neither list (no username here) is named from My Week's answer
  await expect(page.getByTestId("pick-league").locator("option:checked")).toHaveText("Test League");
  expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).not.toBe("rgb(255, 255, 255)");
  await shot(page, "week_test_dark", info.project.name, false);
  await ctx.close();
});

test.describe("with the service worker", () => {
  test.use({ serviceWorkers: "allow" });
  test("installable: manifest, icons, service worker", async ({ page }) => {
  await page.goto(`/?league=${TEST_LEAGUE}&team=3`);
  await expect(page.getByTestId("decision-card").first()).toBeVisible();
  const manifest = await (await page.request.get("/manifest.webmanifest")).json();
  expect(manifest.display).toBe("standalone");
  expect(manifest.icons.map((i: { sizes: string }) => i.sizes)).toEqual(expect.arrayContaining(["192x192", "512x512"]));
  await expect.poll(() => page.evaluate(async () => !!(await navigator.serviceWorker.getRegistration())), { timeout: 10_000 }).toBe(true);
});
});
