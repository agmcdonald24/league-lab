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

// IB-1 (Wave I-B): About the numbers is in the top bar's overflow menu (⋯), not a tab
async function openAbout(page: Page, isMobile: boolean) {
  await tap(page, page.getByTestId("overflow"), isMobile);
  await tap(page, page.getByTestId("menu-about"), isMobile);
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
  await page.getByRole("button", { name: "Open isuckatfantasy" }).click();
  await expect(page.getByText("That is not it.")).toBeVisible();
  await page.getByPlaceholder("Password").fill(FIXTURE_PASSWORD);
  await page.getByRole("button", { name: "Open isuckatfantasy" }).click();

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
  await tap(page, link, isMobile); // IB-1: a lineup name opens the research pane; "Full page" his page
  await expect(page.getByTestId("pane")).toBeVisible();
  await tap(page, page.getByTestId("pane-full"), isMobile);
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
  await tap(page, page.getByTestId("sub-ros"), isMobile); // IB-1: My Team · Season
  await expect(page).toHaveURL(new RegExp(`/ros\\?league=${TEST_LEAGUE}&team=3$`));
  // IB-3: "Value to my lineup" leads with a team picked; "Who scores the most" is the second view
  await expect(page.getByTestId("ros-title")).toHaveText("Value to my lineup");
  await tap(page, page.getByTestId("ros-view-points"), isMobile);
  await expect(page).toHaveURL(new RegExp(`/ros\\?league=${TEST_LEAGUE}&team=3&view=points$`));
  await expect(page.getByTestId("ros-answer")).toContainText(/^#1 overall for the rest of the season: .+ \((QB|RB|WR|TE)\), \d+ points over \d+ games/);
  await expect(page.getByTestId("ros-pos-K")).toBeVisible();
  await expect(page.getByTestId("ros-pos-DEF")).toBeVisible();
  await tap(page, page.getByTestId("ros-pos-WR"), isMobile);
  await expect(page).toHaveURL(new RegExp(`/ros\\?league=${TEST_LEAGUE}&team=3&view=points&position=WR$`));
  await expect(page.getByTestId("ros-answer")).toContainText(
    "#1 WR for the rest of the season: Puka Nacua, 185 points over 12 games (likely 150–219) · playoffs: 30.",
  );
  await expect(page.getByTestId("ros-yours")).toContainText("Yours: #3 Jaxon Smith-Njigba 178");
  // IA-3 (Wave I-A): sortable headers (the sorted one marked), the range, the pieces from 900 px, the expand column
  expect((await page.getByTestId("ros-table").locator("thead th").allTextContents()).map((t) => t.trim())).toEqual(
    ["Rank▲", "Player", "Games", "Points", "Likely", "Playoffs", "Tgt", "Rec", "Rec yd", "TD", "More"],
  );
  await expect(page.getByTestId("ros-table").locator("tbody tr")).toHaveCount(50);
  await noSidewaysScroll(page);
  await shot(page, "ros_test", project, false);

  // 8. about the numbers (the record folded in, Wave G): an unknown league has none, said in plain words
  await openAbout(page, isMobile);
  await expect(page).toHaveURL(new RegExp(`/about\\?league=${TEST_LEAGUE}`));
  await expect(page.getByTestId("model-learned")).toBeVisible();
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
  await tap(page, page.getByTestId("sub-ros"), isMobile); // IB-1: My Team · Season
  await expect(page.getByTestId("ros-answer")).toBeVisible();
  await expect(page.getByTestId("ros-pos-K")).toHaveCount(0); // the dynasty starts no kicker / defense
  await expect(page.getByTestId("ros-pos-DEF")).toHaveCount(0);
  await tap(page, page.getByTestId("ros-view-points"), isMobile); // IB-3: the scoring view (the lineup view leads)
  await tap(page, page.getByTestId("ros-pos-WR"), isMobile);
  await expect(page.getByTestId("ros-yours")).toContainText("Amon-Ra St. Brown");
  await shot(page, "ros_dyn12", project, false);
  await openAbout(page, isMobile);
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
  await tap(page, page.getByTestId("sub-ros"), isMobile); // IB-1: My Team · Season
  await tap(page, page.getByTestId("ros-view-points"), isMobile); // IB-3: the scoring view (the lineup view leads)
  await expect(page.getByTestId("ros-pos-K")).toBeVisible();
  await tap(page, page.getByTestId("ros-pos-K"), isMobile);
  await expect(page.getByTestId("ros-answer")).toContainText("#1 K for the rest of the season:");
  await page.goto(`/record?league=${SCRUBS}&team=2`); // a Wave F link still opens it
  await expect(page.getByTestId("about")).toBeVisible();
  await expect(page.getByTestId("menu-about")).toHaveAttribute("aria-current", "page");
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

// ---- G3 (Wave G): the design system's screens — research (Trends, Matchups, Players, Receivers, Compare), the player
// card's game log, About the numbers — on fixtures, at 390 × 844 and 1300 × 900, light and dark.
const G3_SHOTS = process.env.G3_SHOTS_DIR ?? SHOTS;
mkdirSync(G3_SHOTS, { recursive: true });
const dyn = (path: string, extra = "") => `${path}?league=${DYNASTY}&team=12${extra}`;

test("Trends: the answer first (below / above expectation), the gap bars, filters in the URL, a name opens his card with its chart", async ({ page, isMobile }, info) => {
  await page.goto(dyn("/trends"));
  // G1's rows (fixtures saved from the API); IA-1's words: below / above expectation, the work and the reason in a sentence
  await expect(page.getByTestId("answer")).toContainText("Below expectation: Jameis Winston (getting the throws and runs of a 15.3-point player, scoring 3.6).");
  await expect(page.getByTestId("answer")).toContainText("Above expectation: Jaxon Smith-Njigba (getting the targets of a 20.0-point player, scoring 39.4: 4 touchdowns in 2 games on 6 red-zone targets).");
  await expect(page.getByTestId("card-due")).toContainText("−11.7");
  await expect(page.getByTestId("card-hot")).toContainText("+19.4");
  await expect(page.getByTestId("tab-players")).toHaveAttribute("aria-current", "page");
  await expect(page.getByTestId("sub-trends")).toHaveAttribute("aria-current", "page");
  const rows = page.getByTestId("trends-list").getByTestId("player-row");
  await expect(rows).toHaveCount(30);
  await expect(rows.first().getByTestId("gap")).toHaveText("+19.4");
  await noSidewaysScroll(page);
  if (isMobile) await expect(page.getByTestId("trends-detail")).toBeHidden();
  else {
    await expect(page.getByTestId("trends-detail")).toBeVisible(); // list + detail at 1300
    await expect(page.getByTestId("trends-detail").getByTestId("game-log").getByTestId("line-chart")).toBeVisible();
  }
  await tap(page, page.getByTestId("view-due"), isMobile);
  await expect(page).toHaveURL(/view=due/);
  await expect(rows.first()).toContainText("Jameis Winston");
  await tap(page, page.getByTestId("who-mine"), isMobile);
  await expect(page).toHaveURL(/who=mine/);
  const n = await rows.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) await expect(rows.nth(i)).toHaveAttribute("data-yours", "1");
  await shot(page, "g3_trends_filtered", info.project.name, false);
  // one tap on a name → his card (same tab), the game log: points by week vs expected, a legend for the two
  const name = rows.filter({ hasText: "Emanuel Wilson" }).locator("a").first();
  const who = (await name.textContent())!.trim();
  await tap(page, name, isMobile);
  await expect(page.getByTestId("player-name")).toHaveText(who);
  await expect(page.getByTestId("player-header")).toBeVisible();
  const log = page.getByTestId("game-log");
  await expect(log.getByTestId("legend")).toContainText("Expected points");
  await expect(log.getByTestId("game-log-answer")).toContainText("points a game");
  await expect(log.locator("svg circle").first()).toBeVisible();
  await tap(page, log.getByTestId("game-log-season-2025"), isMobile); // last season: more weeks
  await expect.poll(() => log.locator("svg circle").count()).toBeGreaterThan(3);
  await noSidewaysScroll(page);
});

test("Matchups: your starters' best and toughest, the heatmap with your cells ringed, the cornerbacks your receivers face", async ({ page, isMobile }) => {
  await page.goto(dyn("/matchups"));
  await expect(page.getByTestId("matchups-answer")).toContainText(
    // IB-3: the tone first, the rank in words (1 = toughest for the offense everywhere)
    "Best matchup in your lineup: Jacory Croskey-Merritt (RB) vs IND, who gives up the 2nd-most to RBs: favorable. Toughest: Denzel Boston (WR) vs PIT, who gives up the 2nd-fewest to WRs: difficult.",
  );
  await expect(page.getByTestId("starters").getByTestId("player-row")).toHaveCount(8);
  await expect(page.getByTestId("heatmap").getByTestId("heat-row")).toHaveCount(32);
  await expect(page.getByTestId("heatmap").locator("thead th")).toHaveText(["", "QB", "RB", "WR", "TE"]); // the dynasty starts no kicker
  expect(await page.getByTestId("heat-marked").count()).toBeGreaterThanOrEqual(6);
  await expect(page.getByTestId("heatmap").getByTestId("heat-row").first()).toHaveAttribute("data-row", /IND|LAC|CAR|NO|CIN|DEN|PIT|SF/); // yours first
  const cbs = page.locator('[data-testid="cb-section"] > [data-testid="cb-card"]'); // your starting receivers (the bench is behind an expander)
  await expect(cbs).toHaveCount(3); // IA-1: the tight end is left out, not explained
  await expect(cbs.nth(1)).toContainText("Likely across from him: DJ Turner II (right corner): the 18th-hardest of 74 starting corners to throw on"); // IB-3
  await expect(cbs.nth(1).getByTestId("side-bar")).toContainText("Left 47%");
  await expect(page.getByTestId("cb-section")).not.toContainText("tight ends mostly draw linebackers and safeties");
  await noSidewaysScroll(page);
  void isMobile;
});

// ---- II-3 (Wave I-I): Players is the Stats Explorer now (its own spec: e2e/ii3); here the shared basics on the dynasty
test("Players · Stats: the sorted column's leader, search, position, sort, whose — the table scrolls in its box, not the page", async ({ page, isMobile }) => {
  await page.goto(dyn("/players"));
  await expect(page.getByTestId("players-answer")).toContainText(/Highest fantasy points per game: .+ · \d+ players · Season \(weeks 1–3\)\./);
  const table = page.getByTestId("players-table");
  await expect(table.getByTestId("players-table-row")).toHaveCount(50);
  await noSidewaysScroll(page);
  await tap(page, page.getByTestId("pos-WR"), isMobile);
  await expect(page).toHaveURL(/position=WR/);
  await expect(page.getByTestId("players-answer")).toContainText("Highest target share:");
  await page.getByTestId("sort-points").evaluate((n) => n.scrollIntoView({ block: "center" })); // clear of the phone's tab bar
  await tap(page, page.getByTestId("sort-points"), isMobile);
  await expect(page).toHaveURL(/sort=points&dir=desc/);
  await page.getByTestId("players-search").fill("st. brown");
  await expect(table.getByTestId("players-table-row")).toHaveCount(1);
  await expect(table.getByTestId("players-table-row")).toContainText("Amon-Ra St. Brown");
  await expect(table.getByTestId("players-table-row")).toHaveClass(/ll-mine/); // yours
  await page.getByTestId("players-search").fill("");
  await tap(page, page.getByTestId("who-mine"), isMobile);
  const mine = table.getByTestId("players-table-row");
  await expect(mine.first()).toBeVisible();
  for (const row of await mine.all()) await expect(row).toHaveClass(/ll-mine/);
});

test("Receivers: /receivers lands on the Stats WR / TE preset; the role cards keep their own view (biggest share first, TE switch)", async ({ page, isMobile }) => {
  await page.goto(dyn("/receivers"));
  await expect(page).toHaveURL(/\/players\?.*position=WRTE/);
  await expect(page.getByTestId("players-table")).toBeVisible();
  await expect(page.getByTestId("role-cards")).toBeVisible();
  await page.goto(dyn("/receivers", "&view=cards"));
  await expect(page.getByTestId("receivers-answer")).toContainText("Biggest share of his team's targets: Jaxon Smith-Njigba (44%; the top-12 WRs average 29%).");
  const detail = page.getByTestId("receivers-detail");
  await expect(detail).toBeVisible(); // stacked on a phone (the answer first), on the right at 1300
  await expect(detail.getByTestId("role-bars").getByTestId("bar")).toHaveCount(6); // routes are filled in after the season: not a 0
  await expect(detail.getByTestId("role-bars")).not.toContainText("On the field for pass plays");
  await expect(detail.getByTestId("role-bars")).toContainText("Share of his team's targets");
  await tap(page, page.getByTestId("receivers-list").getByTestId("player-row").nth(1).locator(".ll-label, [data-testid=row-value]").first(), isMobile);
  await expect(page).toHaveURL(/pick=/);
  await tap(page, page.getByTestId("pos-TE"), isMobile);
  await expect(page.getByTestId("receivers-answer")).toContainText("top-12 TEs average");
  await noSidewaysScroll(page);
});
// ---- end II-3

test("Compare: opens on your closest call (same numbers as My Week), paired bars, pick another player", async ({ page, isMobile }) => {
  await page.goto(dyn("/compare"));
  await expect(page).toHaveURL(/a=00-0038797&b=00-0036919/); // My Week's first card: Emanuel Wilson over Kenny Gainwell
  await expect(page.getByTestId("compare-answer")).toContainText("Emanuel Wilson projects 8.7, Kenny Gainwell 8.2 in week 4");
  await expect(page.getByTestId("compare-card-a").getByTestId("card-name")).toHaveText("Wilson"); // shown in capitals (CSS)
  await expect(page.getByTestId("compare-card-b").getByTestId("card-name")).toHaveText("Gainwell");
  expect(await page.getByTestId("compare-group").count()).toBeGreaterThanOrEqual(4);
  await expect(page.getByTestId("compare-group").first().getByTestId("pair").first().getByTestId("pair-a")).toHaveText("8.7");
  await expect(page.getByTestId("compare-next").locator("tbody tr")).toHaveCount(4);
  await noSidewaysScroll(page);
  await page.getByTestId("compare-search-b").fill("kittle");
  await tap(page, page.getByTestId("compare-hits-b").getByRole("button", { name: /George Kittle/ }), isMobile);
  await expect(page).toHaveURL(/b=00-0033288/);
  await expect(page.getByTestId("compare-answer")).toContainText("George Kittle 10.4");
});

test("the Test League (no database): Trends, Matchups and Compare answer on fixtures", async ({ page, isMobile }) => {
  await page.goto(`/trends?league=${TEST_LEAGUE}&team=3`);
  await expect(page.getByTestId("trends-answer")).toBeVisible();
  await tap(page, page.getByTestId("sub-matchups"), isMobile);
  await expect(page).toHaveURL(new RegExp(`/matchups\\?league=${TEST_LEAGUE}&team=3$`));
  await expect(page.getByTestId("heatmap").locator("thead th")).toHaveText(["", "QB", "RB", "WR", "TE", "K"]);
  await expect(page.getByTestId("matchups-answer")).toContainText("Best matchup in your lineup:");
  await tap(page, page.getByTestId("sub-compare"), isMobile);
  await expect(page.getByTestId("compare-answer")).toContainText("projects");
  await noSidewaysScroll(page);
});

test("headshots: a picture when it loads, the silhouette when it does not", async ({ page }) => {
  // one picture served (a tiny PNG); every other headshot is aborted by the fixture server → silhouette
  const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "base64");
  await page.route(/zvo9xatffmqn9lnukpgk/, (r) => r.fulfill({ status: 200, contentType: "image/png", body: png }));
  await page.goto(dyn("/matchups"));
  const nix = page.getByTestId("starters").getByTestId("player-row").first();
  await expect(nix).toContainText("Bo Nix");
  await expect.poll(() => nix.locator("img").evaluate((i: HTMLImageElement) => i.complete && i.naturalWidth)).toBe(1);
  await expect(page.getByTestId("starters").getByTestId("player-row").nth(1).getByTestId("silhouette")).toBeVisible();
});

test("the decisions tabs say what is coming; the bottom bar on a phone, the top bar on a desktop", async ({ page, isMobile }) => {
  await page.goto(dyn("/"));
  await expect(page.getByTestId("decision-card").first()).toBeVisible();
  const bar = (await page.getByTestId("tabs").boundingBox())!;
  if (isMobile) expect(bar.y + bar.height).toBeGreaterThan(page.viewportSize()!.height - 2);
  else expect(bar.y).toBeLessThan(80);
  await tap(page, page.getByTestId("tab-waivers"), isMobile); // IB-1: the four tabs by task
  await expect(page).toHaveURL(/\/waivers\?/);
  await expect(page.getByTestId("waivers")).toBeVisible();
  await tap(page, page.getByTestId("tab-trades"), isMobile);
  for (const s of ["trades", "trade-calc"]) await expect(page.getByTestId(`sub-${s}`)).toBeVisible();
  await tap(page, page.getByTestId("tab-myteam"), isMobile);
  for (const s of ["team", "league"]) await expect(page.getByTestId(`sub-${s}`)).toBeVisible();
  await tap(page, page.getByTestId("tab-players"), isMobile);
  await expect(page).toHaveURL(/\/players\?/); // ---- II-3: the Players tab opens Stats
});

// every screen, light and dark, at this project's size: no sideways scroll, the screen's answer on screen; screenshots
const SCREENS: { name: string; url: string; ready: string }[] = [
  { name: "week", url: dyn("/"), ready: "decision-card" },
  { name: "ros", url: dyn("/ros", "&position=WR&view=points"), ready: "ros-answer" }, // IB-3: the scoring view (lineup: ib3)
  { name: "player", url: `/player/00-0036963?league=${DYNASTY}&team=12`, ready: "game-log-answer" },
  { name: "trends", url: dyn("/trends"), ready: "trends-answer" },
  { name: "matchups", url: dyn("/matchups"), ready: "cb-card" },
  { name: "players", url: dyn("/players"), ready: "players-table" },
  { name: "receivers", url: dyn("/receivers", "&view=cards"), ready: "receivers-detail" }, // ---- II-3: the role cards
  { name: "compare", url: dyn("/compare"), ready: "compare-group" },
  { name: "about", url: dyn("/about"), ready: "record-answer" },
  { name: "leagues", url: "/leagues", ready: "username-form" },
];
for (const scheme of ["light", "dark"] as const) {
  test(`every screen in ${scheme}: no sideways scroll, the answer on screen (screenshots)`, async ({ browser }, info) => {
    test.setTimeout(120_000);
    const ctx = await browser.newContext({ ...info.project.use, colorScheme: scheme });
    await serveFixtures(ctx);
    const page = await ctx.newPage();
    for (const s of SCREENS) {
      await page.goto(s.url);
      await expect(page.getByTestId(s.ready).first()).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await noSidewaysScroll(page);
      const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
      if (scheme === "dark") expect(bg, `${s.name}: dark background`).toBe("rgb(10, 13, 19)");
      else expect(bg, `${s.name}: light background`).toBe("rgb(242, 244, 247)");
      await page.screenshot({ path: join(G3_SHOTS, `g3_${s.name}_${info.project.name}_${scheme}.png`), fullPage: true });
    }
    await ctx.close();
  });
}
