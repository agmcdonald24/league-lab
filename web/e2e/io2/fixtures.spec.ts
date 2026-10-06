// Wave I-O (IO-2): the League page — movement, and a link worth sharing. Phone at 375 and desktop at 1300:
//   * Share on League (a Sleeper league) → the link /league?league=<key> (no team) → opened in a clean browser context
//     (no remembered league, no team): the guest League screen — power rankings and the rest of the season, nobody
//     marked "(you)", one strip "Is this your league? Pick your team" — and picking a team makes it the normal app.
//   * Movement: ▲ ▼ places on the power rankings and "+6 since last week" beside the playoff bar, from the answer's
//     `moved` / `playoff_change` (the API draws them from last week's stored row only).
//   * The power rankings first: while the whole answer is still being simulated the rankings show and the season block
//     says it is playing out the rest of the season.
//   * Title odds: the Title column and the bracket's sentence (Sleeper's settings).
//   * An ESPN league never gets a Share button.
//
// The outlook answers are the API's own, recorded from this worktree's fixture API (web/fixtures/io2/, timings dropped):
// `curl /api/league/outlook?league=<SCRUBS>[&team=2][&part=power]`. The movement in them was computed by the API from a
// week-3 row SEEDED BY HAND into outlook.snapshots for the recording (a shuffled order, every team at 50% playoff
// odds) — it shows how arrows draw, not a real last week. The League answers are the decisions fixtures.
import { expect, test, type BrowserContext, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveDecisions } from "../decisions-fixtures";
import { SCRUBS, serveFixtures } from "../fixtures";

const IO2 = join(import.meta.dirname, "..", "..", "fixtures", "io2");
const SHOTS = process.env.SHOTS_IO2 ?? join(import.meta.dirname, "..", "..", "..", "docs", "handbacks", "io2");
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const read = (name: string): any => JSON.parse(readFileSync(join(IO2, name), "utf8"));

/** The outlook route: the recordings by team (none = the guest's) and part; `delayFull` holds the whole answer back. */
async function serveOutlook(context: BrowserContext, opts: { delayFull?: number } = {}) {
  await context.route(/\/api\/league\/outlook\?/, async (route: Route) => {
    const q = new URL(route.request().url()).searchParams;
    const who = q.get("team") ? `_${q.get("team")}` : "_guest";
    const part = q.get("part") === "power" ? "_power" : "";
    const name = `outlook_scrubs${who}${part}.json`;
    if (q.get("league") !== SCRUBS) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: "no fixture" }) });
    if (!part && opts.delayFull) await new Promise((r) => setTimeout(r, opts.delayFull));
    return route.fulfill({ status: 200, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: readFileSync(join(IO2, name), "utf8") });
  });
}

async function setUp(context: BrowserContext, opts: { delayFull?: number } = {}) {
  await serveFixtures(context);
  await serveDecisions(context);
  await serveOutlook(context, opts);
  // the clipboard, never the share sheet (a headless browser has none; a phone would open it)
  await context.addInitScript(() => Object.defineProperty(navigator, "share", { value: undefined, configurable: true }));
}

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (page: Page, name: string, project: string) => page.screenshot({ path: join(SHOTS, `io2-${name}-${project}.png`), fullPage: false });

test.beforeEach(async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

test("share → the link in a clean context → the guest League screen → pick your team", async ({ browser, context, page }, info) => {
  await setUp(context);
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto(`/league?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("power")).toBeVisible();
  await expect(page.getByTestId("guest-strip")).toHaveCount(0); // a manager with a team: no strip
  await page.getByTestId("league-share").click();
  await expect(page.getByTestId("league-share")).toContainText("Link copied");
  const link = await page.evaluate(() => navigator.clipboard.readText());
  expect(link).toBe(new URL(`/league?league=${SCRUBS}`, page.url()).toString());
  await noSidewaysScroll(page);
  await shot(page, "share", info.project.name);

  // a league-mate opens it: a clean context (nothing remembered, no team)
  const phone = info.project.name === "phone";
  const mate = await browser.newContext(phone ? { viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true } : { viewport: { width: 1300, height: 900 } });
  await setUp(mate);
  const guest = await mate.newPage();
  await guest.goto(link);
  await expect(guest.getByTestId("guest-strip")).toBeVisible();
  await expect(guest.getByTestId("guest-strip")).toContainText("Is this your league?");
  await expect(guest.getByTestId("guest-team")).toContainText("Pick your team");
  const g = read("outlook_scrubs_guest.json");
  await expect(guest.getByTestId("power-row")).toHaveCount(g.power.rows.length);
  await expect(guest.getByTestId("season-row")).toHaveCount(g.outlook.rows.length);
  await expect(guest.locator('[data-testid="power-row"][data-yours="1"]')).toHaveCount(0);
  await expect(guest.getByTestId("power")).not.toContainText("(you)");
  expect(new URL(guest.url()).searchParams.get("team")).toBeNull();
  await noSidewaysScroll(guest);
  if (!phone) expect((await guest.getByTestId("power").boundingBox())!.width).toBeGreaterThan(1000); // the width is used
  await shot(guest, "guest", info.project.name);
  // "then it is the normal app"
  await guest.getByTestId("guest-team").selectOption("2");
  await expect.poll(() => new URL(guest.url()).searchParams.get("team")).toBe("2");
  await expect(guest.getByTestId("guest-strip")).toHaveCount(0);
  await expect(guest.locator('[data-testid="power-row"][data-yours="1"]')).toHaveCount(1);
  await mate.close();
});

test("movement: places moved and the playoff odds' change, from last week's kept ranking", async ({ context, page }, info) => {
  await setUp(context);
  const o = read("outlook_scrubs_2.json");
  await page.goto(`/league?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("season-row")).toHaveCount(o.outlook.rows.length);
  const moved = o.power.rows.filter((r: { moved: number | null }) => r.moved != null);
  expect(moved.length).toBeGreaterThan(0);
  await expect(page.getByTestId("moved")).toHaveCount(moved.length);
  const first = o.power.rows[0];
  const arrow = first.moved > 0 ? `▲ ${first.moved}` : first.moved < 0 ? `▼ ${-first.moved}` : "–";
  await expect(page.getByTestId("power-row").first().getByTestId("moved")).toHaveText(arrow);
  await expect(page.getByTestId("no-arrows")).toHaveText(o.power.movement_note);
  const changed = o.outlook.rows.filter((r: { playoff_change: number | null }) => r.playoff_change != null && Math.abs(r.playoff_change) >= 1);
  await expect(page.getByTestId("odds-change")).toHaveCount(changed.length);
  if (changed.length) await expect(page.getByTestId("odds-change").first()).toContainText("since last week");
  // title odds: the bracket played out (Sleeper's settings: 4 teams, a fixed bracket), said once, context only
  expect(o.outlook.title).toBe(true);
  await expect(page.getByTestId("title-odds")).toHaveCount(o.outlook.rows.length);
  await expect(page.getByTestId("title-words")).toContainText("Title: the 4-team bracket played out in every simulated season");
  await expect(page.getByTestId("title-words")).toContainText("have not been replayed");
  await expect(page.getByTestId("no-title")).toHaveCount(0);
  await noSidewaysScroll(page);
  await page.getByTestId("outlook").screenshot({ path: join(SHOTS, `io2-movement-${info.project.name}.png`) });
});

test("the power rankings first, the rest of the season when it is ready", async ({ context, page }, info) => {
  await setUp(context, { delayFull: 2500 });
  await page.goto(`/league?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("power-row").first()).toBeVisible();
  await expect(page.getByTestId("season-pending")).toBeVisible();
  await expect(page.getByTestId("season-pending")).toContainText("Playing out the rest of the season");
  await noSidewaysScroll(page);
  await page.getByTestId("season").screenshot({ path: join(SHOTS, `io2-power-first-${info.project.name}.png`) });
  await expect(page.getByTestId("season-row").first()).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("season-pending")).toHaveCount(0);
});

test("an ESPN league never gets a Share button", async ({ context, page }) => {
  await setUp(context);
  // the League answer of a Sleeper league served under an ESPN key: the screen renders, the button does not
  await context.route(/\/api\/league\?league=espn/, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: readFileSync(join(IO2, "..", `league_${SCRUBS}_2.json`), "utf8") }),
  );
  await page.goto(`/league?league=espn:5150&team=2`);
  await expect(page.getByTestId("league-answer")).toBeVisible();
  await expect(page.getByTestId("league-share")).toHaveCount(0);
  await page.goto(`/league?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("league-share")).toBeVisible();
});
