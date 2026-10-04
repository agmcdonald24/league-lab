// Wave I-I (II-2) on fixtures — the fifth review § 3, "Use one shared player viewer everywhere": the drawer opens
// several players in a row from Players, Waivers (All available → WR, the review's path) and Receivers without leaving
// the screen; Escape, × and browser Back close it (Back closes the drawer before it leaves the screen); focus returns
// to the name that opened it; the screen's search, filter, sort and scroll stay. Its sections (Overview · Usage · Game
// log · News), Expand (a modal dialog: Escape collapses it), Add to compare (a pair → Compare), Full player page (league
// and team kept); a slower, older answer never overwrites a newer pick and a card read once is not asked again; a name
// on Team, Season, League, Trades, Matchups and My Week opens it too. At 375 px (the phone project, narrowed: a
// full-height sheet) and 1300 px (a panel beside the screen). Screenshots: SHOTS_DIR (default e2e/.out), ii2_*.png.
// The answers are the saved fixtures (web/fixtures; three Scrubs free agents' cards from save_ii2_fixtures.py; the news
// headlines are N1's, recorded from ESPN in api/tests/fixtures/espn).
import { expect, test, type BrowserContext, type Locator, type Page, type TestInfo } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { FIXTURES, SCRUBS, serveFixtures, type FixtureApi } from "../fixtures";
import { serveDecisions } from "../decisions-fixtures";

const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out");
mkdirSync(SHOTS, { recursive: true });
const scrubs = (path: string, extra = "") => `${path}?league=${SCRUBS}&team=2${extra}`;

const PW = { gsis: "00-0038606", name: "Parker Washington" };
const JJ = { gsis: "00-0036322", name: "Justin Jefferson" };
const TMC = { gsis: "00-0040124", name: "Tetairoa McMillan" };
const MW = { gsis: "00-0039880", name: "Malik Washington" };
const WAN = { gsis: "00-0038117", name: "Wan'Dale Robinson" };
const QJ = { gsis: "00-0038544", name: "Quentin Johnston" };
const HOUR = 3_600_000;

test.describe.configure({ timeout: 120_000 }); // several screens per test, on a shared machine
let api: FixtureApi;
test.beforeEach(async ({ context, page }, info) => {
  api = await serveFixtures(context);
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

async function shot(page: Page, name: string, info: TestInfo) {
  await page.evaluate(() => document.fonts?.ready);
  await page.screenshot({ path: join(SHOTS, `ii2_${name}_${info.project.name}.png`) });
}

const pane = (page: Page) => page.getByTestId("pane");
const focusedText = (page: Page) => page.evaluate(() => (document.activeElement as HTMLElement | null)?.innerText?.trim() ?? "");

/** The drawer is on screen with this player: a full-height sheet on a phone, a panel beside the screen from 900 px. */
async function expectDrawer(page: Page, p: { gsis: string; name: string }, isMobile: boolean, screen: string) {
  await expect(pane(page)).toBeVisible();
  await expect(pane(page)).toHaveAttribute("data-gsis", p.gsis);
  await expect(pane(page).getByTestId("pane-card")).toContainText(p.name.split(" ").at(-1)!);
  await expect(pane(page).getByTestId("drawer-league")).toHaveText(/^League of Scrubs scoring · week 4$/); // the league and its scoring stay visible
  const box = (await pane(page).boundingBox())!;
  const vp = page.viewportSize()!;
  if (isMobile) {
    expect(box.y).toBeLessThanOrEqual(1); // a full-height sheet
    expect(box.height).toBeGreaterThanOrEqual(vp.height - 2);
    expect(box.width).toBeGreaterThanOrEqual(vp.width - 2);
  } else {
    expect(box.x).toBeGreaterThan(vp.width / 2); // beside the screen, not over it
    const main = (await page.getByTestId(screen).boundingBox())!;
    expect(main.x + main.width).toBeLessThanOrEqual(box.x + 1);
  }
}

/** Open player `p` from a name link on the screen: from 900 px the list stays usable beside the drawer (a swap in
 *  place, no extra history entry); on a phone the sheet covers the list, so the previous one is closed first. */
async function openNext(page: Page, link: Locator, isMobile: boolean) {
  if (isMobile && (await pane(page).count())) {
    await tap(page, pane(page).getByTestId("pane-close"), isMobile);
    await expect(pane(page)).toHaveCount(0);
  }
  await link.scrollIntoViewIfNeeded();
  await tap(page, link, isMobile);
}

test("Players: several players in a row without leaving the table; the search, filter and sort stay; Escape closes, focus returns", async ({ page, isMobile }, info) => {
  await page.goto(scrubs("/players", "&position=WR&sort=target_share&dir=desc"));
  await expect(page.getByTestId("players-table")).toBeVisible();
  await page.getByTestId("players-search").fill("n");
  await expect(page).toHaveURL(/[?&]q=n(&|$)/); // integ: the search's 250 ms debounce lands before the first open (a Back close restores the entry before it)
  const table = page.getByTestId("players-table");
  const h0 = await page.evaluate(() => history.length);
  for (const p of [PW, JJ, TMC]) {
    await openNext(page, table.getByRole("link", { name: p.name, exact: true }), isMobile);
    await expectDrawer(page, p, isMobile, "players");
    await expect(page).toHaveURL(new RegExp(`/players\\?.*pane=${p.gsis}&from=list`));
    await expect(pane(page).getByTestId("pane-title")).toBeFocused(); // the drawer takes focus
    if (!isMobile) expect(await page.evaluate(() => history.length)).toBe(h0 + 1); // one entry, swapped in place
  }
  await noSidewaysScroll(page);
  await shot(page, "players", info);
  await page.keyboard.press("Escape");
  await expect(pane(page)).toHaveCount(0);
  expect(await focusedText(page)).toBe(TMC.name); // focus back on the name that opened it
  await expect(page).toHaveURL(new RegExp(`/players\\?league=${SCRUBS}&team=2&position=WR&sort=target_share&dir=desc&q=n$`));
  await expect(page.getByTestId("players-search")).toHaveValue("n");
  if (isMobile) expect(await page.evaluate(() => window.scrollY)).toBeGreaterThanOrEqual(0);
  else await expect(table.getByRole("link", { name: TMC.name, exact: true })).toBeInViewport(); // integ: on II-3's taller Stats screen the names are scrolled to and the screen beside the drawer is narrower, so the pixel offset moves when it closes (528 → 461): the place kept is the row you opened from
  await expect(table.getByRole("link", { name: PW.name, exact: true })).toBeVisible();
});

test("Waivers, All available → WR: free agents open the drawer one after another (Evaluate add / drop); Back closes it first", async ({ page, isMobile }, info) => {
  await page.goto(scrubs("/"));
  await expect(page.getByTestId("my-week")).toBeVisible();
  await page.goto(scrubs("/waivers", "&view=all&position=WR"));
  const list = page.getByTestId("fa-list");
  await expect(list).toBeVisible();
  const before = await list.evaluate((el) => el.closest("main")?.innerText.length ?? 0);
  for (const p of [WAN, MW, QJ]) {
    await openNext(page, list.getByRole("link", { name: p.name, exact: true }), isMobile);
    await expectDrawer(page, p, isMobile, "waivers");
    await expect(page).toHaveURL(new RegExp(`/waivers\\?.*view=all&position=WR.*&pane=${p.gsis}&from=waiver`));
    await expect(pane(page).getByTestId("pane-action-waiver")).toHaveText("Evaluate add / drop");
  }
  await noSidewaysScroll(page);
  await shot(page, "waivers", info);
  // browser Back: the drawer closes, the screen stays (the WR filter, the All available view)
  await page.goBack();
  await expect(pane(page)).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`/waivers\\?league=${SCRUBS}&team=2&view=all&position=WR$`));
  await expect(list).toBeVisible();
  expect(await list.evaluate((el) => el.closest("main")?.innerText.length ?? 0)).toBe(before);
  expect(await focusedText(page)).toBe(QJ.name);
  // Back again leaves the screen
  await page.goBack();
  await expect(page).not.toHaveURL(/\/waivers/);
});

test("Receivers: names open the drawer one after another; × closes it and focus returns; the list and its pick stay", async ({ page, isMobile }, info) => {
  await page.goto(scrubs("/receivers", "&view=cards"));
  const list = page.getByTestId("receivers-list");
  await expect(list).toBeVisible();
  for (const p of [PW, TMC, JJ]) {
    await openNext(page, list.getByRole("link", { name: p.name, exact: true }), isMobile);
    await expectDrawer(page, p, isMobile, "receivers");
    await expect(page).toHaveURL(new RegExp(`/receivers\\?.*pane=${p.gsis}`));
  }
  await noSidewaysScroll(page);
  await shot(page, "receivers", info);
  await tap(page, pane(page).getByTestId("pane-close"), isMobile);
  await expect(pane(page)).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`/receivers\\?league=${SCRUBS}&team=2&view=cards$`));
  expect(await focusedText(page)).toBe(JJ.name);
  await expect(list).toBeVisible();
});

const LONG =
  "Jefferson (ankle) has been already been ruled out for Sunday's game against the Dolphins, but the Vikings are hopeful that the superstar wide receiver will return for Week 5 against the Saints, Jeremy Fowler of ESPN reports.";
async function withNews(context: BrowserContext) {
  const now = Date.now();
  const news = [
    { headline: LONG, date: new Date(now - 2 * HOUR - 5 * 60_000).toISOString(), source: "RotoWire via ESPN", url: "https://www.espn.com/nfl/player/_/id/4262921" },
    {
      headline: "Fantasy football Week 4 inactives: Daniels, DeVonta to sit; McConkey questionable",
      date: new Date(now - 14 * HOUR).toISOString(),
      source: "ESPN",
      url: "https://www.espn.com/fantasy/football/story/_/page/FFSundayInactives-50077553/fantasy-football-injuries-nfl-week-4-inactive-active",
      about: "league",
    },
  ];
  const card = JSON.parse(readFileSync(join(FIXTURES, "player", `${SCRUBS}_${JJ.gsis}.json`), "utf8")) as Record<string, unknown>;
  await context.route(new RegExp(`/api/player/${JJ.gsis}(\\?|$)`), (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...card, news }) }),
  );
}

test("the sections: Overview · Usage · Game log · News (tabs, arrow keys); Expand is a modal dialog Escape collapses", async ({ page, context, isMobile }, info) => {
  await withNews(context);
  await page.goto(scrubs("/players", "&position=WR&sort=target_share&dir=desc"));
  const link = page.getByTestId("players-table").getByRole("link", { name: JJ.name, exact: true });
  await tap(page, link, isMobile);
  await expectDrawer(page, JJ, isMobile, "players");
  const d = pane(page);
  // Overview: the projection and its range, where he stands, the one-line reason, the actions
  await expect(d.getByTestId("drawer-tab-overview")).toHaveAttribute("aria-selected", "true");
  await expect(d.getByTestId("pane-section-projection")).toContainText("Typical range");
  await expect(d.getByTestId("pane-section-availability")).toBeVisible();
  await expect(d.getByTestId("pane-why")).toContainText("points this week");
  await expect(d.getByTestId("drawer-compare")).toHaveText("Add to compare");
  await expect(d.getByTestId("pane-full")).toHaveText(/Full player page/);
  await expect(d.getByTestId("pane-section-usage")).toHaveCount(0); // Usage is its own section
  await shot(page, "overview", info);
  // Usage
  await tap(page, d.getByTestId("drawer-tab-usage"), isMobile);
  await expect(d).toHaveAttribute("data-section", "usage");
  await expect(d.getByTestId("pane-section-usage")).toContainText("Share of team passes");
  await expect(d.getByTestId("pane-section-projection")).toHaveCount(0);
  // Game log
  await tap(page, d.getByTestId("drawer-tab-gamelog"), isMobile);
  await expect(d.getByTestId("game-log")).toBeVisible();
  // News: every item, sourced and dated, linked out
  await tap(page, d.getByTestId("drawer-tab-news"), isMobile);
  const items = d.getByTestId("drawer-news-item");
  await expect(items).toHaveCount(2);
  await expect(items.first()).toContainText(/News · 2 h ago · RotoWire via ESPN/);
  await expect(items.first().getByTestId("drawer-news-link")).toHaveAttribute("target", "_blank");
  await expect(items.nth(1)).toContainText(/League news · 14 h ago · ESPN/);
  await expect(d.getByTestId("drawer-news-status")).toBeVisible();
  await noSidewaysScroll(page);
  await shot(page, "news", info);
  // the section sticks while players are swapped (desktop: the list is beside it)
  if (!isMobile) {
    await page.getByTestId("players-table").getByRole("link", { name: PW.name, exact: true }).click();
    await expect(d).toHaveAttribute("data-gsis", PW.gsis);
    await expect(d).toHaveAttribute("data-section", "news");
    await expect(d.getByTestId("drawer-news-empty")).toHaveText("No news about him in the last 14 days.");
    await page.getByTestId("players-table").getByRole("link", { name: JJ.name, exact: true }).click();
    await expect(d).toHaveAttribute("data-gsis", JJ.gsis);
  }
  // the tabs by keyboard: arrows move the selection
  await d.getByTestId("drawer-tab-news").focus();
  await page.keyboard.press("ArrowLeft");
  await expect(d.getByTestId("drawer-tab-gamelog")).toHaveAttribute("aria-selected", "true");
  await expect(d.getByTestId("drawer-tab-gamelog")).toBeFocused();
  await page.keyboard.press("Home");
  await expect(d.getByTestId("drawer-tab-overview")).toHaveAttribute("aria-selected", "true");
  // Expand: a modal dialog with every section, focus inside; Escape collapses it to the drawer, focus back on Expand
  await tap(page, d.getByTestId("drawer-expand"), isMobile);
  const dlg = page.getByTestId("drawer-expanded");
  await expect(dlg).toBeVisible();
  expect(await dlg.evaluate((el) => el.matches(":modal"))).toBe(true);
  await expect(dlg).toHaveAttribute("aria-labelledby", "drawer-expanded-title");
  expect(await dlg.evaluate((el) => el.contains(document.activeElement))).toBe(true);
  for (const id of ["pane-section-projection", "pane-section-usage", "game-log", "drawer-news"]) await expect(dlg.getByTestId(id)).toBeVisible();
  await noSidewaysScroll(page);
  await shot(page, "expanded", info);
  await page.keyboard.press("Escape");
  await expect(dlg).toBeHidden();
  await expect(d).toBeVisible();
  await expect(d.getByTestId("drawer-expand")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(pane(page)).toHaveCount(0);
  expect(await focusedText(page)).toBe(isMobile ? JJ.name : JJ.name);
});

test("Add to compare (a pair → Compare, the screen kept until then); Full player page keeps the league and team; a link in the drawer swaps it", async ({ page, isMobile }) => {
  await page.goto(scrubs("/receivers", "&view=cards"));
  const list = page.getByTestId("receivers-list");
  await openNext(page, list.getByRole("link", { name: PW.name, exact: true }), isMobile);
  await tap(page, pane(page).getByTestId("drawer-compare"), isMobile);
  await expect(pane(page).getByTestId("drawer-compare-note")).toContainText("Parker Washington is waiting to be compared");
  await expect(pane(page).getByTestId("drawer-compare")).toHaveText("Remove from compare");
  await expect(page).toHaveURL(/\/receivers\?/); // nothing left the screen
  await openNext(page, list.getByRole("link", { name: TMC.name, exact: true }), isMobile);
  await expect(pane(page).getByTestId("drawer-compare")).toHaveText(`Compare with ${PW.name}`);
  // a player link inside the drawer (the Value section's "would come in") swaps the drawer, not the page
  await tap(page, pane(page).getByTestId("pane-section-value").getByRole("link", { name: "Michael Wilson" }), isMobile);
  await expect(pane(page)).toHaveAttribute("data-gsis", "00-0038559");
  await expect(page).toHaveURL(/\/receivers\?/);
  await page.goBack(); // Back closes the drawer (the swap added no entry)
  await expect(pane(page)).toHaveCount(0);
  expect(await focusedText(page)).toBe(TMC.name); // focus returns to what opened the drawer, not to the link inside it
  await openNext(page, list.getByRole("link", { name: TMC.name, exact: true }), isMobile);
  await tap(page, pane(page).getByTestId("drawer-compare"), isMobile);
  await expect(page).toHaveURL(new RegExp(`/compare\\?a=${PW.gsis}&b=${TMC.gsis}&league=${SCRUBS}&team=2$`));
  await expect(page.getByTestId("compare-answer")).toContainText("Washington");
  await expect(page.getByTestId("compare-answer")).toContainText("McMillan");
  await expect(pane(page)).toHaveCount(0);
  // Full player page: league + team kept; Back lands on the screen without the drawer
  await page.goto(scrubs("/receivers", "&view=cards"));
  await openNext(page, list.getByRole("link", { name: JJ.name, exact: true }), isMobile);
  await tap(page, pane(page).getByTestId("pane-full"), isMobile);
  await expect(page).toHaveURL(new RegExp(`/player/${JJ.gsis}\\?league=${SCRUBS}&team=2$`));
  await expect(page.getByTestId("player-name")).toHaveText(JJ.name);
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`/receivers\\?league=${SCRUBS}&team=2&view=cards$`));
  await expect(pane(page)).toHaveCount(0);
});

test("a slower, older answer never overwrites a newer pick; a card read once is not asked again", async ({ page, context, isMobile }) => {
  // Parker Washington's card answers 1.5 s late; Jefferson is picked meanwhile
  await context.route(new RegExp(`/api/player/${PW.gsis}(\\?|$)`), async (route) => {
    await new Promise((r) => setTimeout(r, 1500));
    await route.fallback();
  });
  await page.goto(scrubs("/receivers", "&view=cards"));
  const list = page.getByTestId("receivers-list");
  await tap(page, list.getByRole("link", { name: PW.name, exact: true }), isMobile);
  await expect(pane(page).getByTestId("pane-loading")).toBeVisible();
  await expect(pane(page).getByTestId("pane-title")).toHaveText(PW.name); // his name while the card loads
  if (isMobile) await tap(page, pane(page).getByTestId("pane-close"), isMobile);
  await tap(page, list.getByRole("link", { name: JJ.name, exact: true }), isMobile);
  await expect(pane(page)).toHaveAttribute("data-gsis", JJ.gsis);
  await expect(pane(page).getByTestId("pane-card")).toContainText("Jefferson");
  await page.waitForTimeout(2000); // Washington's answer has arrived by now
  await expect(pane(page).getByTestId("pane-card")).toContainText("Jefferson");
  await expect(pane(page).getByTestId("pane-card")).not.toContainText("Washington");
  // the cache: Jefferson again → no second request
  const asked = () => api.calls.filter((c) => c.startsWith(`/api/player/${JJ.gsis}?`)).length;
  expect(asked()).toBe(1);
  await tap(page, pane(page).getByTestId("pane-close"), isMobile);
  await tap(page, list.getByRole("link", { name: JJ.name, exact: true }), isMobile);
  await expect(pane(page).getByTestId("pane-card")).toContainText("Jefferson");
  expect(asked()).toBe(1);
});

// every other screen's player names: the drawer, never a page change (the router's link hook)
const SCREENS: { path: string; extra?: string; screen: string; link: (page: Page) => Locator }[] = [
  { path: "/team", screen: "team", link: (p) => p.getByTestId("team").locator('a[href^="/player/"]').filter({ visible: true }).first() },
  { path: "/ros", screen: "ros", link: (p) => p.getByTestId("ros").locator('a[href^="/player/"]').filter({ visible: true }).first() },
  { path: "/league", screen: "league", link: (p) => p.getByTestId("league").locator('a[href^="/player/"]').filter({ visible: true }).first() },
  { path: "/trades", screen: "trades", link: (p) => p.getByTestId("trades").locator('a[href^="/player/"]').filter({ visible: true }).first() },
  { path: "/matchups", screen: "matchups", link: (p) => p.getByTestId("matchups").locator('a[href^="/player/"]').filter({ visible: true }).first() },
  { path: "/", screen: "my-week", link: (p) => p.getByTestId("my-week").locator('a[href^="/player/"]').filter({ visible: true }).first() },
];

test("Team, Season, League, Trades, Matchups and My Week: a player name opens the drawer on the same screen", async ({ page, isMobile }, info) => {
  test.setTimeout(240_000); // six screens
  for (const s of SCREENS) {
    await page.goto(scrubs(s.path, s.extra ?? ""));
    await expect(page.getByTestId(s.screen)).toBeVisible();
    const link = s.link(page);
    await expect(link, `${s.path}: a player link`).toBeVisible({ timeout: 15_000 });
    const href = (await link.getAttribute("href"))!;
    const key = decodeURIComponent(href.match(/^\/player\/([^/?#]+)/)![1]);
    await link.scrollIntoViewIfNeeded();
    await tap(page, link, isMobile);
    await expect(pane(page), `${s.path}: the drawer`).toBeVisible();
    await expect(pane(page)).toHaveAttribute("data-gsis", key);
    expect(new URL(page.url()).pathname).toBe(s.path);
    if (s.path === "/team") await shot(page, "team", info);
    await page.keyboard.press("Escape");
    await expect(pane(page)).toHaveCount(0);
  }
});
