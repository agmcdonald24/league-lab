// Wave I-B (IB-1) on fixtures: navigation by task — four tabs (My Team · Waivers · Trades · Players) and their
// sub-tabs reach every screen; About the numbers from the overflow menu (⋯) and the foot of My Team; the player's page
// keeps the tab bar; the research pane opens from a My Week lineup row (with "Compare with my starter", which lands on
// Compare prefilled), from the search field, from Players' list; Back closes it. At 375 px (the phone project,
// narrowed) and 1300 px. Screenshots: SHOTS_DIR (default e2e/.out), ib1_<screen>_<project>.png.
import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { DYNASTY, serveFixtures, TEST_LEAGUE } from "../fixtures";
import { serveDecisions } from "../decisions-fixtures";

const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out");
mkdirSync(SHOTS, { recursive: true });
const dyn = (path: string) => `${path}?league=${DYNASTY}&team=12`;
const tst = (path: string) => `${path}?league=${TEST_LEAGUE}&team=3`;

test.beforeEach(async ({ context, page }, info) => {
  await serveFixtures(context);
  await serveDecisions(context);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function tap(page: Page, loc: Locator, isMobile: boolean) {
  if (isMobile) await loc.tap();
  else await loc.click();
}

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

async function shot(page: Page, name: string, info: TestInfo, full = false) {
  await page.evaluate(() => document.fonts?.ready);
  await page.screenshot({ path: join(SHOTS, `ib1_${name}_${info.project.name}.png`), fullPage: full });
}

const TABS: { tab: string; label: string; first: string; subs: [string, string, string][] }[] = [
  {
    tab: "myteam",
    label: "My Team",
    first: "my-week",
    subs: [
      ["week", "This week", "my-week"],
      ["ros", "Season", "ros"],
      ["team", "Team", "team"],
      ["league", "League", "league"],
    ],
  },
  { tab: "waivers", label: "Waivers", first: "waivers", subs: [] },
  {
    tab: "trades",
    label: "Trades",
    first: "trades",
    subs: [
      ["trades", "Partners", "trades"],
      ["trade-calc", "Calculator", "trade-calc"],
    ],
  },
  {
    tab: "players",
    label: "Players",
    first: "players", // ---- II-3: Stats · Trends · Matchups · Compare (Receivers is the Stats WR / TE preset)
    subs: [
      ["players", "Stats", "players"],
      ["trends", "Trends", "trends"],
      ["matchups", "Matchups", "matchups"],
      ["compare", "Compare", "compare"],
    ],
  },
];

test("four tabs and their sub-tabs reach every screen (one tap each, same tab, the paths kept)", async ({ page, context, isMobile }, info) => {
  await page.goto(dyn("/"));
  await expect(page.getByTestId("my-week")).toBeVisible();
  const tabs = page.getByTestId("tabs").locator("a");
  await expect(tabs).toHaveCount(4);
  await expect(tabs).toHaveText(TABS.map((t) => t.label));
  const bar = (await page.getByTestId("tabs").boundingBox())!;
  if (isMobile) expect(bar.y + bar.height).toBeGreaterThan(page.viewportSize()!.height - 2); // the bottom bar
  else expect(bar.y).toBeLessThan(80);
  await shot(page, "week", info);
  for (const t of TABS) {
    await tap(page, page.getByTestId(`tab-${t.tab}`), isMobile);
    await expect(page.getByTestId(t.first)).toBeVisible();
    await expect(page.getByTestId(`tab-${t.tab}`)).toHaveAttribute("aria-current", "page");
    if (!t.subs.length) await expect(page.getByTestId("subtabs")).toHaveCount(0);
    else await expect(page.getByTestId("subtabs").locator("a")).toHaveText(t.subs.map((s) => s[1]));
    for (const [sub, , screen] of t.subs) {
      await tap(page, page.getByTestId(`sub-${sub}`), isMobile);
      await expect(page.getByTestId(screen)).toBeVisible();
      await expect(page).toHaveURL(new RegExp(`/${sub === "week" ? "" : sub}\\?league=${DYNASTY}&team=12`));
      await expect(page.getByTestId(`sub-${sub}`)).toHaveAttribute("aria-current", "page");
      await expect(page.getByTestId(`tab-${t.tab}`)).toHaveAttribute("aria-current", "page");
      await noSidewaysScroll(page);
    }
  }
  await shot(page, "players", info);
  expect(context.pages()).toHaveLength(1);
});

test("About the numbers: from the overflow menu (⋯) and from the foot of My Team", async ({ page, isMobile }, info) => {
  await page.goto(dyn("/ros"));
  await expect(page.getByTestId("ros")).toBeVisible();
  await expect(page.getByTestId("menu-about")).toBeHidden();
  await tap(page, page.getByTestId("overflow"), isMobile);
  await expect(page.getByTestId("menu-about")).toBeVisible();
  await shot(page, "overflow", info);
  await tap(page, page.getByTestId("menu-about"), isMobile);
  await expect(page).toHaveURL(new RegExp(`/about\\?league=${DYNASTY}&team=12`));
  await expect(page.getByTestId("about")).toBeVisible();
  await expect(page.getByTestId("menu-about")).toHaveAttribute("aria-current", "page");
  await expect(page.getByTestId("menu-about")).toBeHidden(); // the menu closes on the way
  await page.goBack();
  await expect(page.getByTestId("ros")).toBeVisible();
  await tap(page, page.getByTestId("foot-about"), isMobile);
  await expect(page.getByTestId("about")).toBeVisible();
});

test("the player's page keeps the tab bar and the search field; Back goes where you came from", async ({ page, isMobile }, info) => {
  await page.goto(dyn("/matchups"));
  await expect(page.getByTestId("matchups")).toBeVisible();
  await page.goto(`/player/00-0036963?league=${DYNASTY}&team=12`); // a shared link: opened here
  await expect(page.getByTestId("player-name")).toHaveText("Amon-Ra St. Brown");
  await expect(page.getByTestId("top-bar")).toBeVisible();
  await expect(page.getByTestId("tabs")).toBeVisible();
  await expect(page.getByTestId("tabs").locator("a")).toHaveCount(4);
  await expect(page.getByTestId("back")).toHaveText(/My week/);
  await noSidewaysScroll(page);
  await shot(page, "player", info);
  // from a screen: the tab you came from stays lit, Back returns there
  await tap(page, page.getByTestId("tab-players"), isMobile);
  await tap(page, page.getByTestId("sub-players"), isMobile);
  await expect(page.getByTestId("players-table")).toBeVisible();
  await page.getByTestId("players-search").fill("st. brown");
  await expect(page.getByTestId("players-table").getByTestId("players-table-row")).toHaveCount(1);
  // Players' list: a name opens the pane; "Full page" his page, in the frame
  await tap(page, page.getByTestId("players-table").getByRole("link", { name: "Amon-Ra St. Brown" }), isMobile);
  await expect(page.getByTestId("pane")).toBeVisible();
  await expect(page.getByTestId("pane-card")).toContainText("St. Brown");
  await expect(page.getByTestId("pane-action-compare")).toHaveCount(0); // from a list: no action but the full page
  await tap(page, page.getByTestId("pane-full"), isMobile);
  await expect(page).toHaveURL(new RegExp(`/player/00-0036963\\?league=${DYNASTY}&team=12$`));
  await expect(page.getByTestId("tab-players")).toHaveAttribute("aria-current", "page");
  await expect(page.getByTestId("pane")).toHaveCount(0);
  await expect(page.getByTestId("back")).toHaveText(/Back/);
  await tap(page, page.getByTestId("back"), isMobile);
  await expect(page).toHaveURL(/\/players\?/);
  await expect(page.getByTestId("pane")).toHaveCount(0); // Back lands on the list, not on the pane
});

test("the pane from a My Week lineup row: Compare with my starter → Compare prefilled", async ({ page, isMobile }, info) => {
  await page.goto(tst("/"));
  await expect(page.getByTestId("decision-card").first()).toBeVisible();
  // a bench player (the bench and who can't play): compared with the weakest starter he could replace
  await tap(page, page.getByTestId("lineup-full").locator("summary"), isMobile);
  const hall = page.getByTestId("lineup-full-table").getByRole("link", { name: "Breece Hall" });
  await hall.scrollIntoViewIfNeeded();
  const y0 = await page.evaluate(() => window.scrollY);
  const h0 = await page.evaluate(() => history.length);
  await tap(page, hall, isMobile);
  const pane = page.getByTestId("pane");
  await expect(pane).toBeVisible();
  await expect(page).toHaveURL(/pane=00-0038120&from=lineup/);
  // the screen did not jump: the phone's sheet covers it where it was; from 900 px the list narrows beside the pane and
  // the browser keeps the tapped row in view
  if (isMobile) expect(await page.evaluate(() => window.scrollY)).toBe(y0);
  await expect(hall).toBeInViewport();
  expect(await page.evaluate(() => history.length)).toBe(h0 + 1);
  await expect(pane.getByTestId("pane-card")).toContainText("Breece Hall");
  await expect(pane.getByTestId("pane-section-projection")).toBeVisible();
  await expect(pane.getByTestId("pane-action-compare")).toHaveText("Compare with my starter");
  await expect(pane.getByTestId("pane-compare-with")).toHaveText("With CeeDee Lamb.");
  await expect(pane.getByTestId("pane-full")).toBeVisible();
  const box = (await pane.boundingBox())!;
  const vp = page.viewportSize()!;
  if (isMobile) {
    expect(box.y + box.height).toBeGreaterThan(vp.height - 2); // a sheet from the bottom
    expect(box.width).toBeGreaterThan(vp.width - 2);
  } else {
    expect(box.x).toBeGreaterThan(vp.width / 2); // beside the screen, on the right
    const main = (await page.getByTestId("my-week").boundingBox())!;
    expect(main.x + main.width).toBeLessThanOrEqual(box.x + 1); // not over it
  }
  await noSidewaysScroll(page);
  await shot(page, "pane_lineup", info);
  await tap(page, pane.getByTestId("pane-action-compare"), isMobile);
  await expect(page).toHaveURL(new RegExp(`/compare\\?a=00-0038120&b=00-0036358&league=${TEST_LEAGUE}&team=3$`));
  await expect(page.getByTestId("compare-answer")).toContainText("Breece Hall");
  await expect(page.getByTestId("compare-answer")).toContainText("CeeDee Lamb");
  await expect(page.getByTestId("pane")).toHaveCount(0);
  await shot(page, "compare_prefilled", info);
  // a starter: compared with the best bench player who can fill his slot
  await page.goto(tst("/"));
  await tap(page, page.getByTestId("lineup").getByRole("link", { name: "Trey McBride" }), isMobile);
  await expect(page.getByTestId("pane-action-compare")).toHaveText("Compare with my best bench option");
  await expect(page.getByTestId("pane-compare-with")).toHaveText("With Dalton Kincaid, the next best for TE.");
  // Back closes the pane (the phone's swipe); the screen stays
  await page.goBack();
  await expect(page.getByTestId("pane")).toHaveCount(0);
  await expect(page.getByTestId("my-week")).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/\\?league=${TEST_LEAGUE}&team=3$`));
});

test("the search field opens the pane; × closes it; another name swaps it in place", async ({ page, isMobile }, info) => {
  await page.goto(dyn("/team"));
  await expect(page.getByTestId("team")).toBeVisible();
  if (isMobile) {
    await expect(page.getByTestId("search")).toBeHidden(); // a magnifier on a phone
    await tap(page, page.getByTestId("search-open"), isMobile);
  }
  await expect(page.getByTestId("search")).toBeVisible();
  await page.getByTestId("search").fill("st brown");
  await expect(page.getByTestId("search-hit")).toHaveCount(1);
  await shot(page, "search", info);
  await tap(page, page.getByTestId("search-hit").first(), isMobile);
  await expect(page.getByTestId("pane")).toBeVisible();
  await expect(page.getByTestId("pane")).toHaveAttribute("data-from", "search");
  await expect(page.getByTestId("pane-card")).toContainText("St. Brown");
  // IF-4 (the decision-quality review: the drawer focused on the decision): the game log is behind its expander
  await tap(page, page.getByTestId("pane").getByTestId("pane-gamelog").locator("summary").first(), isMobile);
  await expect(page.getByTestId("pane").getByTestId("game-log")).toBeVisible();
  await expect(page.getByTestId("search-results")).toHaveCount(0);
  await noSidewaysScroll(page);
  await shot(page, "pane_search", info);
  await tap(page, page.getByTestId("pane-close"), isMobile);
  await expect(page.getByTestId("pane")).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`/team\\?league=${DYNASTY}&team=12$`));
});
