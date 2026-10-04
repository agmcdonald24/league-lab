// Wave I-B (IB-3): matchup meaning first, "Value to my lineup", the card's default content. On fixtures (e2e/fixtures.ts),
// at 375 px (the phone project, narrowed) and 1300 px: Matchups' tones (the heatmap cells, the starters' chips, the
// cornerback calls with their certainty beside them, no "shutdown" badge), the ROS view toggle (Value to my lineup by
// default, its sentence per row, whose players, the scoring view one tap away), and My Week's cards (the status chip,
// the call, the strength, the reason, Compare, the numbers behind Why?). The numbers are read from the fixture files
// (web/fixtures/save_ib3_fixtures.py saved them from the API's own functions).
import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { DYNASTY, SCRUBS, serveFixtures, TEST_LEAGUE } from "../fixtures";

const FIX = join(import.meta.dirname, "..", "..", "fixtures");
const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out");
mkdirSync(SHOTS, { recursive: true });
const read = (name: string) => JSON.parse(readFileSync(join(FIX, name), "utf8"));

async function tap(page: Page, loc: Locator, isMobile: boolean) {
  if (isMobile) await loc.tap();
  else await loc.click();
}

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

test.beforeEach(async ({ context, page, isMobile }) => {
  await serveFixtures(context);
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test("Matchups: the tone is the signal, the rank small and one way, a corner call says how sure it is", async ({ page }, info) => {
  const def = read(`matchups_defense_${DYNASTY}_12.json`);
  await page.goto(`/matchups?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("matchups-answer")).toContainText(/who gives up the .*: favorable\. Toughest: .* who gives up the .*: difficult\./s);
  // every starter row: a tone chip (a word, not a color alone), the rank under it ("#N toughest vs POS")
  const chips = page.getByTestId("starters").getByTestId("tone-chip");
  await expect(chips).toHaveCount(8);
  for (const t of await chips.all()) {
    await expect(t).toHaveAttribute("data-tone", /favorable|neutral|difficult/);
    await expect(t).toContainText(/Favorable|Neutral|Difficult/);
    await expect(t.getByTestId("rank-small")).toHaveText(/^#\d+ toughest vs (QB|RB|WR|TE)$/);
  }
  // the heatmap's cells carry the API's tone; the legend names the three tones
  const ind = def.teams.find((t: { defense: string; position: string }) => t.defense === "IND" && t.position === "RB");
  expect(ind.tone).toBe("favorable");
  expect(ind.tough_rank).toBe(31);
  const cell = page.locator('[data-row="IND"] td').nth(1);
  await expect(cell).toHaveAttribute("data-tone", "favorable");
  await expect(cell).toContainText("▲");
  await expect(page.getByTestId("heat-legend")).toHaveText(/Favorable\s*.*Neutral\s*.*Difficult/);
  const tones = await page.getByTestId("heatmap").locator("td[data-tone]").evaluateAll((els) => els.map((e) => e.getAttribute("data-tone")));
  expect(new Set(tones)).toEqual(new Set(["favorable", "neutral", "difficult"]));
  // cornerbacks: the tone and the certainty label beside it, the rank in words, no shutdown badge
  const cbs = page.locator('[data-testid="cb-section"] > [data-testid="cb-card"]');
  await expect(cbs.first()).toBeVisible();
  for (const c of await cbs.all()) {
    await expect(c.getByTestId("tone-chip").getByTestId("rank-small")).toHaveText(/^(likely|unclear|no call)$/);
    await expect(c.getByTestId("cb-certainty")).toHaveText(/^(likely|unclear|no call)/i);
  }
  await expect(page.getByTestId("cb-section")).not.toContainText(/shutdown/i);
  await expect(page.getByTestId("cb-section")).toContainText(/the \d+(st|nd|rd|th)-(hardest|easiest) of \d+ starting corners to throw on/);
  await expect(page.getByTestId("howto").locator("summary")).toBeVisible();
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ib3_matchups_${info.project.name}.png`), fullPage: true });
});

test("Rest of season: Value to my lineup leads, a reason per row, whose players, the scoring view one tap away", async ({ page, isMobile }, info) => {
  const d = read(`ros-lineup_${SCRUBS}_2_ALL.json`);
  const mine = read(`ros-lineup_${SCRUBS}_2_ALL_mine.json`);
  await page.goto(`/ros?league=${SCRUBS}&team=2`);
  // II-4: the view is "My roster outlook" (yours only; IB-3's "Value to my lineup" over everyone became two views)
  void d;
  await expect(page.getByTestId("ros-title")).toHaveText("My roster outlook");
  await expect(page.getByTestId("ros-view-outlook")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("ros-lineup-answer")).toContainText(`Your most important player over weeks 4–16: ${mine.players[0].player_name}`);
  await expect(page.getByTestId("ros-lineup-why").first()).toContainText(mine.players[0].lineup_why);
  await expect(page.getByTestId("ros-value").first()).toContainText(`+${Math.round(mine.players[0].lineup_points)}`);
  // yours: the backup QB ranks below every starter, and says why
  await expect(page.getByTestId("ros-row")).toHaveCount(mine.players.length);
  const rows = page.getByTestId("ros-row");
  const names = await rows.evaluateAll((els) => els.map((e) => e.querySelector("td:nth-child(2) a, td:nth-child(2) .min-w-0")?.textContent ?? ""));
  const young = names.findIndex((n) => n.includes("Bryce Young"));
  const starters = names.map((n, i) => [n, i] as const).filter(([n]) => /Travis Kelce|Kyren Williams|Patrick Mahomes/.test(n));
  expect(starters.length).toBe(3);
  for (const [, i] of starters) expect(young).toBeGreaterThan(i);
  await expect(page.getByTestId("ros-lineup-why").nth(young)).toContainText("backup QB"); // one reason row under each row
  // IA-3's pieces stay on this view
  await tap(page, page.getByTestId("ros-row").first().getByTestId("ros-toggle"), isMobile);
  await expect(page.getByTestId("ros-why")).toBeVisible();
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ib3_ros_lineup_${info.project.name}.png`), fullPage: true });
  // the other view: who scores the most (the old screen, unchanged)
  await tap(page, page.getByTestId("ros-view-projections"), isMobile); // II-4
  await expect(page).toHaveURL(/view=projections/);
  await expect(page.getByTestId("ros-title")).toHaveText("Rest-of-season projections");
  await expect(page.getByTestId("ros-answer")).toContainText(/^#1 overall for the rest of the season/);
  await expect(page.getByTestId("ros-lineup-why")).toHaveCount(0);
  await noSidewaysScroll(page);
});

test("My Week: status first, the call, its strength, one reason, Compare; the numbers behind Why?", async ({ page, isMobile }, info) => {
  for (const [league, team] of [
    [SCRUBS, 2],
    [DYNASTY, 12],
    [TEST_LEAGUE, 3],
  ] as const) {
    const d = read(`my-week_${league}_${team}.json`);
    await page.goto(`/?league=${league}&team=${team}`);
    const cards = page.getByTestId("decision-card");
    await expect(cards).toHaveCount(d.cards.length);
    for (let i = 0; i < d.cards.length; i++) {
      const c = d.cards[i];
      const card = cards.nth(i);
      // the status (the API's on the house leagues; derived from the rows on the Test League)
      const want = c.status ?? (c.p_win < 0.55 ? "close" : "change");
      await expect(card).toHaveAttribute("data-status", want);
      await expect(card.getByTestId("card-status")).toHaveText(
        { change: /Change needed/, set: /Already set/, close: /Close call/ }[want as "change" | "set" | "close"],
      );
      // the first thing in the card is the status chip
      const firstText = await card.evaluate((el) => (el.querySelector("[data-testid]") as HTMLElement).dataset.testid);
      expect(firstText).toBe("card-status");
      await expect(card.getByTestId("card-call")).toContainText(c.player_name);
      if (c.alt_name) await expect(card.getByTestId("card-call")).toContainText(c.alt_name);
      await expect(card.getByTestId("card-strength")).toHaveText(/^(Clear|Lean|Coin flip)$/);
      await expect(card.getByTestId("card-why")).toBeVisible();
      // the reason does not repeat whole names (last names; the headline names both)
      const why = (await card.getByTestId("card-why").textContent()) ?? "";
      expect(why.includes(c.player_name) && why.includes(c.alt_name ?? "~")).toBe(false);
      // the small print is behind Why?
      await expect(card.getByTestId("card-small-print").first()).toBeHidden();
      await expect(card.getByTestId("card-compare")).toHaveAttribute("href", new RegExp(`/compare\\?a=${c.gsis_id}&b=${c.alt_gsis_id}&league=${league}&team=${team}`));
    }
    await noSidewaysScroll(page);
    await page.screenshot({ path: join(SHOTS, `ib3_week_${league}_${info.project.name}.png`), fullPage: true });
  }
  // Why? opens the odds and the ranges; Compare lands prefilled with both
  const card = page.getByTestId("decision-card").first();
  await tap(page, card.getByTestId("card-why-more").locator("summary"), isMobile);
  await expect(card.getByTestId("card-small-print").first()).toBeVisible();
  await expect(card.getByTestId("card-small-print").first()).toContainText(/outscores|apart/);
  await tap(page, card.getByTestId("card-compare"), isMobile);
  await expect(page).toHaveURL(/\/compare\?a=.+&b=.+/);
});
