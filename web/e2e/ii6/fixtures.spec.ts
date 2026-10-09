// Wave I-J (II-6): the presentation list — Wave I-I's "known, left as built". Phone at 375 px (inside the phone project)
// and desktop at 1300. Screenshots: SHOTS_DIR (default e2e/.out), ii6-*.png.
// 1. Waivers' top three: the whole name shows (wraps, never cut) and neither the name nor the position badge runs under
//    the gain label — drawer closed and open (from 900 px the drawer narrows the screen; ClaimCard's container query).
//    Answers: II-4's recording (web/fixtures/ii4, League of Scrubs roster 2).
// 2. Trades: "No compelling trade found" once (the answer at the top); the Finder does not repeat it (Any) and says a
//    position's reason in one line without the best move (a chip). Answers: II-1's recording (web/fixtures/ii1).
// 3. The drawer: what the screen wrote to the URL while it was open (a search typed just before the tap, a filter
//    beside it) stays when ×, Escape or Back closes it; one history entry per screen.
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

// ---- 2. the Trades screen says "No compelling trade found" once
const II1 = join(import.meta.dirname, "..", "..", "fixtures", "ii1", "api_ii1.json");
const ii1: Record<string, Saved> = existsSync(II1) ? (JSON.parse(readFileSync(II1, "utf8")) as Record<string, Saved>) : {};
const SCRUBS_FINDER = `/api/trades/partners?league=${SCRUBS}&team=2`;

test("Trades: 'No compelling trade found' is said once — the answer says it, the Finder does not repeat it (Any, and a position)", async ({ page, context, isMobile }, info) => {
  test.skip(!ii1[SCRUBS_FINDER], "no II-1 recording");
  // the recorded Scrubs roster 2 answer (no credible trade; the rest behind Explore); for a position the same rows stand in
  // for that position's answer (the rendering rule is what is checked here, not the API's filter)
  await context.route(/\/api\/trades\/(partners|lists)/, (route) => {
    const u = new URL(route.request().url());
    if (u.pathname.endsWith("/lists")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ buy_low: [], sell_high: [] }) });
    const s = ii1[SCRUBS_FINDER];
    return route.fulfill({ status: s.status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(s.body) });
  });
  await page.goto(`/trades?league=${SCRUBS}&team=2`);
  const head = page.getByTestId("best-partner");
  await expect(head.getByTestId("no-compelling")).toHaveText("No compelling trade found.");
  await expect(head).toContainText("is worth proposing");
  // IT-1 (re-saved on the calculator's basis): the best move is the answer's own (searched on the same basis)
  const bestMove = (ii1[SCRUBS_FINDER].body as { best_alternative: { words: string } }).best_alternative.words;
  await expect(head).toContainText(`Your best move: ${bestMove}`);
  const explore = page.getByTestId("explore");
  await expect(explore).toBeVisible();
  await expect(page.getByTestId("finder-none")).toHaveCount(0);
  await expect(page.getByTestId("finder-none-why")).toHaveCount(0);
  const main = page.locator("main");
  const count = async (t: string) => (await main.innerText()).split(t).length - 1;
  expect(await count("No compelling trade found")).toBe(1);
  expect(await count("Your best move:")).toBe(1);
  await noSidewaysScroll(page);
  await shot(page, "trades-none", info, true);
  // a position: one line, that position's reason, without the verdict words or the best move again
  await tap(page, page.getByTestId("want-WR"), isMobile);
  await expect(page).toHaveURL(/want=WR/);
  const why = page.getByTestId("finder-none-why");
  // IT-1 (re-saved): the count and the weeks are the saved answer's (the same rows stand in for the WR answer)
  const sb = ii1[SCRUBS_FINDER].body as { partners: unknown[]; span: string };
  const esc = (t: string) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  await expect(why).toHaveText(new RegExp(`^For a WR: none of the ${sb.partners.length} trades? that raises? both starting lineups over ${esc(sb.span)} is worth proposing: .*\\.$`));
  await expect(why).not.toContainText("Your best move");
  expect(await count("No compelling trade found")).toBe(1);
  expect(await count("Your best move:")).toBe(1);
  await shot(page, "trades-none-wr", info, true);
});

// ---- 3. closing the drawer keeps what the screen wrote to the URL while it was open
const PLAYERS = `/players?league=${SCRUBS}&team=2&position=WR&sort=target_share&dir=desc`;
const PW = { gsis: "00-0038606", name: "Parker Washington" };

for (const how of ["×", "Back"] as const) {
  test(`the drawer: a search typed just before the tap stays in the URL when ${how} closes it; Back then leaves the screen`, async ({ page, isMobile }) => {
    await page.goto(`/?league=${SCRUBS}&team=2`);
    await expect(page.getByTestId("my-week")).toBeVisible();
    await page.goto(PLAYERS);
    const table = page.getByTestId("players-table");
    await expect(table).toBeVisible();
    // type, then tap a name at once (in one task, so the race is the same on every machine): the search's 250 ms
    // debounce writes `q` AFTER the drawer's history entry
    await expect(table.getByRole("link", { name: PW.name, exact: true })).toBeVisible();
    await page.evaluate(async (name) => {
      const input = document.querySelector<HTMLInputElement>('[data-testid="players-search"]')!;
      input.value = "n";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      await new Promise((ok) => requestAnimationFrame(ok)); // the list filters (one frame, as a hand would) …
      [...document.querySelectorAll<HTMLAnchorElement>('[data-testid="players-table"] a')].find((a) => a.textContent?.trim() === name)!.click(); // … and the tap lands well inside the 250 ms
    }, PW.name);
    await expect(pane(page)).toHaveAttribute("data-gsis", PW.gsis);
    await expect(page).toHaveURL(/[?&]pane=00-0038606&from=list&q=n$/); // written on the drawer's entry
    if (how === "×") await tap(page, pane(page).getByTestId("pane-close"), isMobile);
    else await page.goBack();
    await expect(pane(page)).toHaveCount(0);
    await expect(page).toHaveURL(new RegExp(`/players\\?league=${SCRUBS}&team=2&position=WR&sort=target_share&dir=desc&q=n$`));
    await expect(page.getByTestId("players-search")).toHaveValue("n");
    // one entry per screen: Back leaves the screen (no second stop on the same screen without the search)
    await page.goBack();
    await expect(page).not.toHaveURL(/\/players/);
    await expect(page.getByTestId("my-week")).toBeVisible();
    // Forward returns to the screen with its search
    await page.goForward();
    await expect(page).toHaveURL(/\/players\?.*q=n$/);
  });
}

test("the drawer (from 900 px): a filter changed beside the open drawer stays when Escape closes it", async ({ page, isMobile }) => {
  test.skip(isMobile, "on a phone the sheet covers the screen: nothing to change beside it");
  await page.goto(PLAYERS);
  const table = page.getByTestId("players-table");
  await tap(page, table.getByRole("link", { name: PW.name, exact: true }), isMobile);
  await expect(pane(page)).toHaveAttribute("data-gsis", PW.gsis);
  await page.getByTestId("players-search").fill("wash");
  await expect(page).toHaveURL(/q=wash$/);
  await pane(page).getByTestId("pane-title").focus();
  await page.keyboard.press("Escape");
  await expect(pane(page)).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`/players\\?league=${SCRUBS}&team=2&position=WR&sort=target_share&dir=desc&q=wash$`));
  await expect(page.getByTestId("players-search")).toHaveValue("wash");
});
