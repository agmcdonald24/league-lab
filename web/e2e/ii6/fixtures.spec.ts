// Wave I-J (II-6): the presentation list. Phone at 375 px (inside the phone project) and desktop at 1300.
import { expect, test, type Locator, type Page, type Route, type TestInfo } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { serveDecisions } from "../decisions-fixtures";
import { SCRUBS, serveFixtures } from "../fixtures";

const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out");
mkdirSync(SHOTS, { recursive: true });
const II4 = join(import.meta.dirname, "..", "..", "fixtures", "ii4", "api_ii4.json");
type Saved = { status: number; body: unknown };
const ii4: Record<string, Saved> = existsSync(II4) ? (JSON.parse(readFileSync(II4, "utf8")) as Record<string, Saved>) : {};
const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return u.pathname + (q.length ? `?${new URLSearchParams(q).toString()}` : "");
};
async function answerIi4(route: Route) {
  const s = ii4[keyOf(new URL(route.request().url()))];
  if (!s) return route.fallback();
  return route.fulfill({ status: s.status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(s.body) });
}

test.beforeEach(async ({ context, page }, info) => {
  await serveFixtures(context);
  await serveDecisions(context);
  await context.route(/\/api\//, answerIi4);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function tap(page: Page, loc: Locator, isMobile: boolean) {
  if (isMobile) await loc.tap();
  else await loc.click();
}
async function noSidewaysScroll(page: Page) {
  const [sw, iw] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}
async function shot(page: Page, name: string, info: TestInfo, fullPage = false) {
  await page.evaluate(() => document.fonts?.ready);
  await page.screenshot({ path: join(SHOTS, `ii6-${name}-${info.project.name}.png`), fullPage });
}
const pane = (page: Page) => page.getByTestId("pane");

type Box = { x: number; y: number; width: number; height: number };
const overlaps = (a: Box, b: Box) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

/** Each top card: the whole name shows (no ellipsis), and neither the name nor the position badge sits under the gain. */
async function topCardsReadable(page: Page) {
  const cards = page.getByTestId("top-move");
  const n = await cards.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) {
    const c = cards.nth(i);
    const name = c.getByTestId("claim-add");
    const cut = await name.evaluate((el) => el.scrollWidth > el.clientWidth + 1);
    expect(cut, `card ${i + 1}: the name is cut`).toBe(false);
    const gain = (await c.getByTestId("claim-gain-box").boundingBox())!;
    const nb = (await name.boundingBox())!;
    const meta = (await c.getByTestId("claim-meta").boundingBox())!;
    expect(overlaps(nb, gain), `card ${i + 1}: the name runs under the gain`).toBe(false);
    expect(overlaps(meta, gain), `card ${i + 1}: the position badge runs under the gain`).toBe(false);
    const card = (await c.boundingBox())!;
    expect(gain.x + gain.width).toBeLessThanOrEqual(card.x + card.width + 0.5);
  }
}

test("Waivers' top three: the name wins over the gain label — drawer open and closed", async ({ page, isMobile }, info) => {
  await page.goto(`/waivers?league=${SCRUBS}&team=2`);
  const top = page.getByTestId("top3");
  await expect(top).toBeVisible();
  await expect(page.getByTestId("top-move")).toHaveCount(3);
  await topCardsReadable(page);
  await noSidewaysScroll(page);
  await shot(page, "waivers-top-closed", info);
  await tap(page, page.getByTestId("top-move").nth(2).getByTestId("claim-add"), isMobile);
  await expect(pane(page)).toBeVisible();
  if (!isMobile) {
    await topCardsReadable(page);
    await noSidewaysScroll(page);
  }
  await shot(page, "waivers-top-drawer", info);
});
