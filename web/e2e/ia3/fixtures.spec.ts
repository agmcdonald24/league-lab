// Wave I-A (IA-3): the rankings — more to see, and "why this number". On fixtures (e2e/fixtures.ts), at 375 px (the
// phone project, narrowed) and 1300 px: the honesty line on top, headshots, the tap-to-expand row with the pieces and
// "why this number" (phone: name + points; desktop: the piece columns), the sort, the market line, and the player
// card's "why this number" list. The numbers are read from the fixture files (web/fixtures/save_ia3_fixtures.py
// saved them from the API); the market is null in every fixture (no market mart in the clone), so the market lines
// are added to one answer here, by hand, in the API's words (why.market_words).
import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { SCRUBS, serveFixtures } from "../fixtures";

const FIX = join(import.meta.dirname, "..", "..", "fixtures");
const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out");
mkdirSync(SHOTS, { recursive: true });
const read = (name: string) => JSON.parse(readFileSync(join(FIX, name), "utf8"));

interface Row {
  gsis_id: string | null;
  player_name: string;
  ros_points: number | null;
  per_game?: Record<string, number | null>;
  why?: { sentence: string; pieces: { words: string }[] } | null;
  market_words?: string | null;
  market_points?: number | null;
  bye_weeks?: number[];
}
const WR: { players: Row[] } = read(`ros_${SCRUBS}_WR.json`);
const KELCE = "00-0030506"; // a TE in Scrubs' lineup fixture (his card has "why this number")
const CARD = read(`player/${SCRUBS}_${KELCE}.json`);

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

test("rest of season: the honesty line, headshots, the pieces, the expand row and the sort (Scrubs WR)", async ({ page, isMobile }, info) => {
  await page.goto(`/ros?league=${SCRUBS}&team=2&position=WR&view=points`); // IB-3: the scoring view
  await expect(page.getByTestId("ros-answer")).toBeVisible();
  const honesty = page.getByTestId("ros-honesty");
  await expect(honesty).toContainText("How to read the rankings.");
  await expect(honesty).toContainText("from his work, not his name");
  await expect(honesty).toContainText("quarterbacks lead the list by design");
  await expect(honesty).toContainText("Sleeper's own number is there to compare");

  const rows = page.getByTestId("ros-row");
  await expect(rows).toHaveCount(WR.players.length);
  const first = rows.first();
  await expect(first.getByTestId("headshot")).toBeVisible();
  await expect(first).toContainText(WR.players[0].player_name);
  await expect(first.getByTestId("ros-bye")).toHaveText(`bye ${WR.players[0].bye_weeks!.join(", ")} ·`);

  // the piece columns: from 900 px only; a phone shows the name and the points
  const tgt = first.getByTestId("ros-pg-targets");
  if (isMobile) await expect(tgt).toBeHidden();
  else await expect(tgt).toHaveText(WR.players[0].per_game!.targets!.toFixed(1));

  // the expand row: the pieces a game, why this number, what the model leans on
  await tap(page, first.getByTestId("ros-toggle"), isMobile);
  const ex = page.getByTestId("ros-expand");
  await expect(ex).toHaveCount(1);
  await expect(ex.getByTestId("ros-pieces")).toContainText("targets");
  await expect(ex.getByTestId("ros-pieces")).toContainText(WR.players[0].per_game!.targets!.toFixed(1));
  await expect(ex.getByTestId("ros-why")).toContainText(WR.players[0].why!.sentence);
  await expect(ex.getByTestId("ros-why").locator("li")).toHaveCount(WR.players[0].why!.pieces.length);
  await expect(ex.getByTestId("ros-leans")).toContainText("For WRs the model leans most on");
  await expect(ex.getByTestId("ros-market")).toHaveCount(0); // no market number in the fixture: no line, never a 0
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ia3_ros_expand_${info.project.name}.png`), fullPage: false });
  await tap(page, first.getByTestId("ros-toggle"), isMobile);
  await expect(page.getByTestId("ros-expand")).toHaveCount(0);

  // the sort: Points twice = fewest first; on a desktop, targets per game
  await tap(page, page.getByTestId("ros-sort-ros_points"), isMobile);
  await tap(page, page.getByTestId("ros-sort-ros_points"), isMobile);
  const fewest = [...WR.players].sort((a, b) => (a.ros_points ?? 0) - (b.ros_points ?? 0))[0];
  await expect(rows.first()).toContainText(fewest.player_name);
  await expect(page.getByTestId("ros-table").locator("th[aria-sort=ascending]")).toContainText("Points");
  if (!isMobile) {
    await page.getByTestId("ros-sort-pg:targets").click();
    const most = [...WR.players].sort((a, b) => (b.per_game?.targets ?? -1) - (a.per_game?.targets ?? -1))[0];
    await expect(rows.first()).toContainText(most.player_name);
    await expect(rows.first().getByTestId("ros-pg-targets")).toHaveText(most.per_game!.targets!.toFixed(1));
  }
  await tap(page, page.getByTestId("ros-sort-rank"), isMobile);
  await expect(rows.first()).toContainText(WR.players[0].player_name);
});

test("rest of season: the market line in the expanded row (added by hand: Sleeper's number for this week)", async ({ context, page, isMobile }) => {
  const words = "Sleeper has him at 24.0. We're well under the market: our number follows his recent usage. Treat it with care.";
  await context.route(/\/api\/ros\?/, async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("league") !== SCRUBS || url.searchParams.get("position") !== "WR") return route.fallback();
    const body = structuredClone(WR) as { players: Row[] };
    body.players[0].market_points = 24.0;
    body.players[0].market_words = words;
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...read(`ros_${SCRUBS}_WR.json`), players: body.players }) });
  });
  await page.goto(`/ros?league=${SCRUBS}&team=2&position=WR&view=points`); // IB-3: the scoring view
  await tap(page, page.getByTestId("ros-row").first().getByTestId("ros-toggle"), isMobile);
  await expect(page.getByTestId("ros-market")).toHaveText(`Week 4: ${words}`);
});

test("player card: why this number, the market line, what the model leans on (Scrubs, Travis Kelce)", async ({ page }, info) => {
  await page.goto(`/player/${KELCE}?league=${SCRUBS}&team=2`);
  const why = page.getByTestId("player-why");
  await expect(why).toBeVisible();
  await expect(page.getByTestId("section-projection").getByTestId("player-why")).toHaveCount(1); // inside the Projection section
  await expect(page.getByTestId("player-why-sentence")).toHaveText(CARD.why.sentence);
  await expect(page.getByTestId("player-why-pieces").locator("li")).toHaveCount(CARD.why.pieces.length);
  await expect(page.getByTestId("player-why-pieces")).toContainText("catches × 0.5");
  await expect(page.getByTestId("player-market-none")).toHaveText("Sleeper's number for this week is not in yet.");
  await expect(page.getByTestId("player-leans")).toContainText("For TEs the model leans most on");
  await noSidewaysScroll(page);
  await why.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(SHOTS, `ia3_player_why_${info.project.name}.png`), fullPage: false });
});

test("player card: the market line with the gap in words (added by hand)", async ({ context, page }) => {
  const market = { market_points: 16.2, ours: CARD.proj_points, ratio: 0.63, week: 4, far: true, why: null,
    words: "Sleeper has him at 16.2. We're well under the market: our number follows his recent usage. Treat it with care." };
  await context.route(/\/api\/player\/00-0030506\?/, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...CARD, market }) }),
  );
  await page.goto(`/player/${KELCE}?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("player-market")).toHaveText(market.words);
  await expect(page.getByTestId("player-market-none")).toHaveCount(0);
});
