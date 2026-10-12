// Wave J-A (JA-4): small faults on game-day screens. Phone at 375 and desktop at 1300; screenshots into
// docs/handbacks/ja4/ (SHOTS_JA4) or e2e/.out.
//
// 1. Waivers' top claims: the claims show first, then one small read of the claim players' news (/api/news/players)
//    draws a line on a claim that has one. No news about a fixture claim player is recorded anywhere, so the line this
//    spec serves says it is a test line — nothing is invented about a real player; the screens show the real state
//    (no news on these claims).
// 2. The trade's section 5: each player's role note — the Folk trade's recorded answer (web/fixtures/iz2) with the
//    notes this branch's API reads on league_lab_iq4 (web/fixtures/ja4/trade_folk_roles.json).
import { expect, test, type BrowserContext, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveDecisions } from "../decisions-fixtures";
import { SCRUBS, serveFixtures } from "../fixtures";

const FX = join(import.meta.dirname, "..", "..", "fixtures");
const SHOTS = process.env.SHOTS_JA4 ?? join(import.meta.dirname, "..", ".out");
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const rec = JSON.parse(readFileSync(join(FX, "iz2", "api_iz2.json"), "utf8")) as Record<string, any>;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const FOLK = JSON.parse(readFileSync(join(FX, "ja4", "trade_folk_roles.json"), "utf8")) as Record<string, any>;
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64");

test.beforeEach(async ({ context, page }, info) => {
  await context.route(/^https?:\/\/(?!localhost)/, (route) => route.fulfill({ status: 200, contentType: "image/png", body: PNG }));
  await serveFixtures(context);
  await serveDecisions(context);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(SHOTS, `ja4-${name}-${project === "phone" ? "375" : "1300"}.jpg`), type: "jpeg", quality: 70, fullPage: true });

test("Waivers: the claims show first; the news read asks for the claim players only; a line lands on its claim", async ({ page }, info) => {
  const asked: string[][] = [];
  let release: () => void = () => {};
  const gate = new Promise<void>((r) => (release = r));
  let line: Record<string, unknown[]> = {};
  await page.route(/\/api\/news\/players\?/, async (route: Route) => {
    const ids = (new URL(route.request().url()).searchParams.get("ids") ?? "").split(",");
    asked.push(ids);
    await gate;                                              // the news answer is held back: the claims must not wait
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ lines: line }) });
  });
  await page.goto(`/waivers?league=${SCRUBS}&team=2`);
  const cards = page.getByTestId("top-move");
  await expect(cards.first()).toBeVisible();                // shown while the news read is still waiting
  await expect.poll(() => asked.length).toBeGreaterThan(0);
  expect(asked[0].length).toBeGreaterThan(0);
  expect(asked[0].length).toBeLessThanOrEqual(4);
  for (const id of asked[0]) expect(id).toMatch(/^\d{2}-\d{7}$/);
  release();
  await expect(page.getByTestId("claim-news")).toHaveCount(0); // no news on these claims (the real state)
  await noSidewaysScroll(page);
  await shot(page, "waivers-claims", info.project.name);

  // a line for the first asked player lands on his claim only (a test line, said to be one)
  line = { [asked[0][0]]: [{ kind: "news", gsis_id: asked[0][0], player_name: null, text: "Test line: no news is recorded for this player", source: "e2e fixture", at: null, url: null, forecast_words: "Context only: not in the projection" }] };
  await page.reload();
  await expect(page.getByTestId("claim-news")).toHaveCount(1);
  await expect(page.getByTestId("claim-news")).toContainText("Test line: no news is recorded for this player");
  await expect(page.getByTestId("claim-news").getByTestId("decision-news-forecast")).toHaveText("Context only: not in the projection");
});

async function evaluate(context: BrowserContext, body: unknown) {
  await context.route(/\/api\/trades\/evaluate/, (route) =>
    route.request().method() === "POST" ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) }) : route.fallback(),
  );
  await context.route(/\/api\/team\?/, (route) => {
    const u = new URL(route.request().url());
    const hit = rec.team[`${u.searchParams.get("league")}|${u.searchParams.get("team")}`];
    return hit ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(hit) }) : route.fallback();
  });
  await context.route(/\/api\/leagues\/[^/]+\/rosters/, (route) => {
    const l = decodeURIComponent(new URL(route.request().url()).pathname.split("/")[3]);
    return rec.rosters[l] ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(rec.rosters[l]) }) : route.fallback();
  });
}

test("the Folk trade: section 5 says each player's role note where the card has one, nothing for a kicker", async ({ context, page }, info) => {
  await evaluate(context, FOLK);
  await page.goto(`/trade-calc?league=${SCRUBS}&team=2&partner=3&give=650&get=421,11792`);
  await expect(page.getByTestId("five-5")).toBeVisible({ timeout: 30_000 });
  for (const [key, n] of Object.entries(FOLK.roles as Record<string, { role: string; left_early: string | null }>)) {
    const row = page.locator(`[data-testid="five-player"][data-key="${key}"]`);
    if (!(await row.count())) continue;                     // a cut player listed elsewhere
    await expect(row.getByTestId("trade-role")).toContainText(`Role: ${n.role}`);
  }
  await expect(page.locator('[data-testid="five-player"][data-key="421"]').getByTestId("trade-role")).toHaveText(`Role: ${FOLK.roles["421"].role}`); // Stafford
  await expect(page.locator('[data-testid="five-player"][data-key="650"]').getByTestId("trade-role")).toHaveCount(0); // Folk, a kicker
  await expect(page.getByTestId("five-5")).not.toContainText("(game started (bench))");
  await noSidewaysScroll(page);
  await page.getByTestId("five-5").scrollIntoViewIfNeeded();
  await shot(page, "trade-section5", info.project.name);
});
