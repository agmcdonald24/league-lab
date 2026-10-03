// Wave I-A (IA-2) on fixtures: the trade calculator as its own link (the Decisions row), the interest dial that moves as
// players are ticked (no page reload), the window control (this week · next 4 · rest of season · playoffs) and its
// caption, the lineups shown once, buy low / sell high on Trades (gone from Waivers). At 375 px (the phone project,
// narrowed) and 1300 px. Every number is read from the fixture the screen was served (web/fixtures/*, saved by
// save_ia2_fixtures.py from the API). Screenshots: SHOTS_DIR (default e2e/.out), ia2_<screen>_<project>.png.
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { DYNASTY, FIXTURES, SCRUBS, serveFixtures, TEST_LEAGUE } from "../fixtures";
import { evalKey, serveDecisions, type DecisionCalls } from "../decisions-fixtures";

const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out");
mkdirSync(SHOTS, { recursive: true });
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- fixture JSON, read as written
const fx = (name: string): any => JSON.parse(readFileSync(join(FIXTURES, name), "utf8"));
const plain = (t: string) => t.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/\*\*/g, "").replace(/ {2}\n/g, "");
const PACKAGES = fx("ia2_packages.json") as Record<string, { partner: number; from: { give: string[]; get: string[]; label: string }; to: { give: string[]; get: string[]; label: string } }>;
const TEAM: Record<string, number> = { [DYNASTY]: 12, [SCRUBS]: 2, [TEST_LEAGUE]: 3 };
const calcUrl = (league: string, partner: number, give: string[], get: string[], window?: string) =>
  `/trade-calc?league=${league}&team=${TEAM[league]}&partner=${partner}&give=${give.join(",")}&get=${get.join(",")}${window ? `&window=${window}` : ""}`;

let calls: DecisionCalls;
test.beforeEach(async ({ context, page }, info) => {
  await serveFixtures(context);
  calls = await serveDecisions(context);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

async function shot(page: Page, name: string, info: TestInfo) {
  await page.evaluate(() => document.fonts?.ready);
  await page.screenshot({ path: join(SHOTS, `ia2_${name}_${info.project.name}.png`), fullPage: true });
}

test("the trade calculator is its own link in the Decisions row", async ({ page, isMobile }) => {
  await page.goto(`/trades?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("trades")).toBeVisible();
  const go = page.getByTestId("sub-trade-calc");
  await expect(go).toHaveText("Trade calculator");
  if (isMobile) await go.tap();
  else await go.click();
  await expect(page).toHaveURL(new RegExp(`/trade-calc\\?league=${DYNASTY}&team=12`));
  await expect(page.getByTestId("trade-calc")).toBeVisible();
  await expect(page.getByTestId("tick-both")).toBeVisible();
  await expect(page.getByTestId("window-caption")).toHaveText("The next four weeks: far enough to matter, near enough to trust.");
  // the Trades screen keeps the partners (and links here), not the pickers
  await page.goBack();
  await expect(page.getByTestId("finder")).toBeVisible();
  await expect(page.getByTestId("pick-give")).toHaveCount(0);
  await expect(page.getByTestId("calc-link")).toBeVisible();
});

for (const league of [TEST_LEAGUE, DYNASTY, SCRUBS]) {
  test(`tick a player: the dial moves and its label changes, no reload (${league})`, async ({ page }, info) => {
    const pk = PACKAGES[league];
    const team = TEAM[league];
    const a = fx(evalKey(league, team, pk.partner, pk.from.give, pk.from.get));
    const b = fx(evalKey(league, team, pk.partner, pk.to.give, pk.to.get));
    await page.goto(calcUrl(league, pk.partner, pk.from.give, pk.from.get));
    const dial = page.getByTestId("dial");
    await expect(page.getByTestId("dial-label")).toHaveText(a.interest.label);
    await expect(dial).toHaveAttribute("data-score", String(a.interest.score));
    await expect(page.getByTestId("dial-score")).toHaveText(String(a.interest.score));
    await expect(dial).toContainText(a.interest.caption);
    await expect(page.getByTestId("dial-you")).toContainText(a.span);
    await expect(page.getByTestId("verdict")).toHaveText(plain(a.verdict));
    await page.evaluate(() => ((window as unknown as { __noReload: number }).__noReload = 1));
    // the tick: one more (or one fewer) player, as the saved variant has it
    for (const id of pk.to.get.filter((x) => !pk.from.get.includes(x))) await page.locator(`[data-testid="get-option"][data-id="${id}"] input`).check();
    for (const id of pk.from.get.filter((x) => !pk.to.get.includes(x))) await page.locator(`[data-testid="get-option"][data-id="${id}"] input`).uncheck();
    for (const id of pk.from.give.filter((x) => !pk.to.give.includes(x))) await page.locator(`[data-testid="give-option"][data-id="${id}"] input`).uncheck();
    await expect(page.getByTestId("dial-label")).toHaveText(b.interest.label);
    await expect(dial).toHaveAttribute("data-score", String(b.interest.score));
    expect(a.interest.label).not.toEqual(b.interest.label);
    expect(await page.evaluate(() => (window as unknown as { __noReload?: number }).__noReload)).toBe(1);
    expect(calls.evaluate.at(-1)).toEqual({ league, team, partner: pk.partner, give: pk.to.give, get: pk.to.get });
    await expect(page.getByTestId("verdict")).toHaveText(plain(b.verdict));
    // ticking down in the lists, the dial is off screen: its reading follows in a chip (never both at once)
    await page.getByTestId("dial-row").scrollIntoViewIfNeeded();
    await expect(page.getByTestId("dial-chip")).toHaveCount(0);
    await page.evaluate(() => {
      const el = document.querySelector('[data-testid="dial-row"]') as HTMLElement;
      window.scrollTo(0, el.getBoundingClientRect().bottom + window.scrollY + 40);
    });
    await expect(page.getByTestId("dial-chip")).toContainText(b.interest.label);
    await noSidewaysScroll(page);
    await shot(page, `calc_${league}`, info);
  });
}

test("the window control: the caption, the span and the numbers change (calculator and partner suggestions)", async ({ page }, info) => {
  const pk = PACKAGES[TEST_LEAGUE];
  const team = 3;
  await page.goto(calcUrl(TEST_LEAGUE, pk.partner, pk.from.give, pk.from.get));
  const next4 = fx(evalKey(TEST_LEAGUE, team, pk.partner, pk.from.give, pk.from.get));
  await expect(page.getByTestId("window-caption")).toHaveText(`Weeks 4–7: the next four weeks: far enough to matter, near enough to trust.`);
  for (const w of ["ros", "playoffs", "week"] as const) {
    const ev = fx(evalKey(TEST_LEAGUE, team, pk.partner, pk.from.give, pk.from.get, w));
    await page.getByTestId(`window-${w}`).click();
    await expect(page).toHaveURL(new RegExp(`window=${w}`));
    await expect(page.getByTestId("window-caption")).toContainText(ev.window_why);
    await expect(page.getByTestId("window-caption")).toContainText(ev.span[0].toUpperCase() + ev.span.slice(1));
    await expect(page.getByTestId("dial")).toContainText(`by our numbers over ${ev.span}`);
    await expect(page.getByTestId("dial")).toHaveAttribute("data-score", String(ev.interest.score));
    expect(calls.evaluate.at(-1)?.window).toBe(w);
    if (w === "ros") {
      expect(ev.span).not.toEqual(next4.span);
      await shot(page, "calc_ros", info);
    }
  }
  await page.getByTestId("window-next4").click();
  await expect(page).not.toHaveURL(/window=/);
  await expect(page.getByTestId("dial")).toContainText("by our numbers over weeks 4–7");
  expect(calls.evaluate.at(-1)?.window).toBeUndefined(); // the default is not sent: the body stays the G4 one

  // the partner suggestions: the same control, its own caption and best partner
  await page.goto(`/trades?league=${TEST_LEAGUE}&team=3`);
  await expect(page.getByTestId("window-caption")).toContainText("Weeks 4–7: the next four weeks");
  const po = fx(`trades_partners_${TEST_LEAGUE}_3_ALL_playoffs.json`);
  await page.getByTestId("window-playoffs").click();
  await expect(page).toHaveURL(/window=playoffs/);
  await expect(page.getByTestId("window-caption")).toContainText(`${po.span[0].toUpperCase()}${po.span.slice(1)}: ${po.window_why}`);
  await expect(page.getByTestId("best-partner")).toHaveText(plain(po.words.headline));
  await noSidewaysScroll(page);
});

test("the lineups are shown once: yours, then theirs under an expander", async ({ page }, info) => {
  const pk = PACKAGES[DYNASTY];
  const ev = fx(evalKey(DYNASTY, 12, pk.partner, pk.from.give, pk.from.get));
  await page.goto(calcUrl(DYNASTY, pk.partner, pk.from.give, pk.from.get));
  await expect(page.getByTestId("verdict")).toHaveText(plain(ev.verdict));
  const lineups = page.getByTestId("lineups");
  await expect(lineups.getByTestId("lineup-after").filter({ visible: true })).toHaveCount(1);
  await expect(lineups.getByTestId("lineup-after").first()).toContainText(`Your lineup, week ${ev.week}`);
  await expect(page.getByText(`Your lineup, week ${ev.week}`)).toHaveCount(1);
  // the differences this week / over the window live in the dial's row, not in the lineup headers
  await expect(page.getByTestId("dial-row").getByTestId("fit-tiles")).toBeVisible();
  await page.getByTestId("lineup-theirs").locator("summary").click();
  await expect(lineups.getByTestId("lineup-after").filter({ visible: true })).toHaveCount(2);
  await expect(page.getByTestId("lineup-theirs")).toContainText(`${ev.partner_team}'s lineup`);
  await noSidewaysScroll(page);
  await shot(page, "calc_lineups", info);
});

test("Trades shows buy low / sell high under the partner suggestions; Waivers points there", async ({ page }, info) => {
  for (const [league, team] of [[SCRUBS, 2], [TEST_LEAGUE, 3]] as const) {
    const tl = fx(`trades_lists_${league}_${team}.json`);
    await page.goto(`/trades?league=${league}&team=${team}`);
    const bs = page.getByTestId("buy-sell");
    await expect(bs).toBeVisible();
    await expect(page.getByTestId("buy-line")).toContainText(plain(tl.buy_line).slice(0, 50));
    await expect(page.getByTestId("sell-line")).toContainText(plain(tl.sell_line).slice(0, 50));
    // under the partner finder
    const [finderY, bsY] = await Promise.all([page.getByTestId("finder").boundingBox(), bs.boundingBox()]);
    expect(bsY!.y).toBeGreaterThan(finderY!.y);
    await noSidewaysScroll(page);
    if (league === SCRUBS) await shot(page, "trades_scrubs", info);
    await page.goto(`/waivers?league=${league}&team=${team}`);
    await expect(page.getByTestId("waiver-answer")).toBeVisible();
    await expect(page.getByTestId("buy-sell")).toHaveCount(0);
    await expect(page.getByTestId("buy-sell-moved")).toBeVisible();
  }
});

test("the partner finder says what the sanity bound left out", async ({ page }) => {
  const all = fx(`trades_partners_${SCRUBS}_2_ALL.json`);
  await page.goto(`/trades?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("finder")).toBeVisible();
  if (all.rejected_count) {
    const rej = page.getByTestId("rejected");
    await expect(rej).toContainText(`${all.rejected_count} lopsided`);
    await rej.locator("summary").click();
    await expect(page.getByTestId("rejected-row")).toHaveCount(all.rejected.length);
    await expect(page.getByTestId("rejected-row").first()).toContainText(all.rejected[0].why);
  }
});
