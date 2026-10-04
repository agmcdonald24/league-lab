// Wave I-E (IE-0): the review's P0 #1 — the trade calculator keeps every asset of an MFL package. Dad's league (MFL
// 70587), Big Mac Attack (team 8) and Madeyes Revenge (team 12). The review: the Finder's "Houston Texans QB + Bhayshul
// Tuten for Rashee Rice" (`give=mfl:0682,12490&get=10229`) opened with Tuten alone, the summary said Tuten, the verdict
// flipped, the after-lineup kept Houston. The cause: `parseIds` dropped the colon of a provider key.
// Here: Finder → "Try it" → both assets ticked and named; the review's own link, a reload and manual toggling of the
// team QB change the request and the answer; an asset nobody can analyse is named, never dropped; a unit's row shows its
// team's badge, never "Free agent". At 375 (phone project) and 1300 (desktop).
//
// The answers are the API's own, recorded from a live API on the MFL fixtures (api/tests/fixtures/mfl/70587, the ESPN
// fixture overlay on) into web/fixtures/mfl/api_70587_ie0.json (the evaluate POSTs keyed by their body) and replayed here.
// Re-record:
//   (api on :8747 with LEAGUE_LAB_MFL_FIXTURES / _SLEEPER_FIXTURES / _ESPN_FIXTURES / _PLAYER_IDS_CSV set, the gate off)
//   IE0_RECORD=http://127.0.0.1:8747 FIXTURES_PORT=8615 npm run e2e:fixtures -- e2e/ie0
import { expect, test, type Page, type Request, type Route } from "@playwright/test";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "mfl", "api_70587_ie0.json");
const RECORD = process.env.IE0_RECORD ?? "";
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};
const MINE = /mfl|70587/i;
const KEY = "mfl:70587";
const Q = `league=${encodeURIComponent(KEY)}&team=8`;
const REVIEW = `/trade-calc?${Q}&partner=12&give=mfl%3A0682,12490&get=10229`; // the review's "Trade handoff example"

const keyOf = (u: URL, req: Request) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  const base = u.pathname + (q.length ? `?${new URLSearchParams(q).toString()}` : "");
  if (req.method() !== "POST") return base;
  const b = JSON.parse(req.postData() ?? "{}") as Record<string, unknown>;
  return `POST ${base} ${JSON.stringify(Object.fromEntries(Object.entries(b).sort(([x], [y]) => x.localeCompare(y))))}`;
};

async function answer(route: Route) {
  const req = route.request();
  const u = new URL(req.url());
  const key = keyOf(u, req);
  if (!MINE.test(decodeURIComponent(key))) return route.fallback();
  if (RECORD) {
    const init: RequestInit = req.method() === "POST" ? { method: "POST", headers: { "Content-Type": "application/json" }, body: req.postData() ?? "" } : {};
    const r = await fetch(RECORD + u.pathname + u.search, init);
    const text = await r.text();
    let body: unknown = text;
    try {
      body = JSON.parse(text);
    } catch {
      /* keep the text */
    }
    saved[key] = { status: r.status, body };
    return route.fulfill({ status: r.status, contentType: "application/json", body: text });
  }
  const s = saved[key];
  if (!s) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: `no fixture for ${key}` }) });
  return route.fulfill({ status: s.status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(s.body) });
}

test.afterAll(() => {
  if (RECORD) writeFileSync(FILE, JSON.stringify(saved, null, 1) + "\n");
});

test.beforeEach(async ({ context }) => {
  test.skip(!RECORD && !Object.keys(saved).length, "no recording yet: run with IE0_RECORD (see the header)");
  await serveFixtures(context);
  await context.route(/\/api\//, answer);
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

async function pickBigMac(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("leagues")).toBeVisible();
  await page.getByTestId("platform-mfl").click(); // ---- II-5 (Wave I-I): the fantasy platform first
  await page.getByTestId("mfl-link").fill("70587");
  await page.getByTestId("mfl-go").click();
  await page.getByTestId("mfl-team").filter({ hasText: "Big Mac Attack" }).click();
  await expect(page.getByTestId("my-week")).toBeVisible();
}

/** The evaluate requests the page sends (their give / get), in order. */
function watchEvaluate(page: Page): { give: string[]; get: string[] }[] {
  const sent: { give: string[]; get: string[] }[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().includes("/api/trades/evaluate")) sent.push(JSON.parse(r.postData() ?? "{}"));
  });
  return sent;
}

const shot = (name: string, project: string) => join(process.env.SHOTS_DIR ?? "e2e/.out", `ie0-${name}-${project}.png`);
const give = (page: Page, id: string) => page.locator(`[data-testid="give-option"][data-id="${id}"] input[type="checkbox"]`);

test("the review's link: Houston Texans QB + Tuten for Rice stays a two-for-one, through reload and toggling", async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await pickBigMac(page);
  const sent = watchEvaluate(page);
  await page.goto(REVIEW);
  const calc = page.getByTestId("trade-calc");
  await expect(calc.getByTestId("trade-result")).toBeVisible();
  // both assets ticked, both named, the request carried both
  await expect(give(page, "mfl:0682")).toBeChecked();
  await expect(give(page, "12490")).toBeChecked();
  await expect(calc.getByTestId("picked-give")).toHaveText("Houston Texans QB + Bhayshul Tuten");
  await expect(calc.getByTestId("trade-headline")).toContainText("Houston Texans QB and Bhayshul Tuten");
  expect(sent.at(-1)).toMatchObject({ give: ["mfl:0682", "12490"], get: ["10229"] });
  // the answer describes the same trade: the roster-size line (two for one: a spot opens), Houston out of team QB
  await calc.getByTestId("why").locator("summary, button").first().click();
  await expect(calc.getByTestId("roster-size")).toContainText("you open a spot");
  await calc.getByTestId("lineups-x").locator("summary, button").first().click();
  const mineAfter = calc.getByTestId("lineups").getByTestId("lineup-after").first();
  // IE-2's after-lineup also lists the starters who left ("Houston Texans QB (traded)") under the same slot word
  const teamQb = mineAfter.locator("li").filter({ hasText: /^\s*team QB/ }).first();
  await expect(teamQb).toContainText("Chicago Bears QB");
  await expect(mineAfter).toContainText("Rashee Rice (new)");
  await expect(mineAfter).toContainText("Out of the lineup after the trade: Houston Texans QB (team QB, 30.40, traded)");
  // a unit's row: its team's badge, named for a screen reader; nothing on the page reads "Free agent"
  const hou = page.locator('[data-testid="give-option"][data-id="mfl:0682"]');
  await expect(hou.getByTestId("team-badge")).toHaveText("HOU");
  await expect(hou.getByTestId("team-badge")).toHaveAttribute("aria-label", "Houston Texans");
  await expect(page.locator('[aria-label="Free agent"], [title="Free agent"]')).toHaveCount(0);
  await noSidewaysScroll(page);
  await page.screenshot({ path: shot("review-link", info.project.name), fullPage: true });

  // reload: the same package
  await page.reload();
  await expect(calc.getByTestId("trade-result")).toBeVisible();
  await expect(give(page, "mfl:0682")).toBeChecked();
  await expect(calc.getByTestId("trade-headline")).toContainText("Houston Texans QB and Bhayshul Tuten");

  // untick the team QB: the URL, the request, the summary and the lineup all lose him
  await give(page, "mfl:0682").uncheck();
  await expect(page).toHaveURL(/give=12490(&|$)/);
  await expect(calc.getByTestId("picked-give")).toHaveText("Bhayshul Tuten");
  await expect(calc.getByTestId("trade-headline")).not.toContainText("Houston Texans QB");
  await expect.poll(() => sent.at(-1)?.give).toEqual(["12490"]);
  await expect(calc.getByTestId("trade-headline")).toContainText("Bhayshul Tuten");
  // tick him again: back to the two-for-one
  await give(page, "mfl:0682").check();
  await expect(page).toHaveURL(/give=12490%2Cmfl%3A0682|give=12490,mfl%3A0682/);
  await expect.poll(() => sent.at(-1)?.give).toEqual(["12490", "mfl:0682"]);
  await expect(calc.getByTestId("trade-headline")).toContainText("Houston Texans QB");
  await expect(calc.getByTestId("picked-give")).toHaveText("Bhayshul Tuten + Houston Texans QB");
});

test("Finder → Try it: a package with a team QB opens with every asset ticked and named", async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await pickBigMac(page);
  const sent = watchEvaluate(page);
  await page.goto(`/trades?${Q}`);
  const row = page.getByTestId("partner-row").filter({ hasText: "Chicago Bears QB" }).filter({ hasText: "Tuten" }).first();
  await expect(row).toBeVisible();
  await row.getByTestId("try-partner").click();
  const calc = page.getByTestId("trade-calc");
  await expect(calc.getByTestId("trade-result")).toBeVisible();
  await expect(page).toHaveURL(/give=mfl%3A0671,12490|give=mfl%3A0671%2C12490/);
  await expect(give(page, "mfl:0671")).toBeChecked();
  await expect(give(page, "12490")).toBeChecked();
  await expect(calc.getByTestId("picked-give")).toHaveText("Chicago Bears QB + Bhayshul Tuten");
  await expect(calc.getByTestId("trade-headline")).toContainText("Chicago Bears QB and Bhayshul Tuten");
  expect(sent.at(-1)?.give).toEqual(["mfl:0671", "12490"]);
  // a shared link (a fresh page on the same URL) opens the same trade
  const url = page.url();
  const other = await page.context().newPage();
  await other.goto(url);
  await expect(other.getByTestId("trade-result")).toBeVisible();
  await expect(other.getByTestId("picked-give")).toHaveText("Chicago Bears QB + Bhayshul Tuten");
  await other.close();
  await noSidewaysScroll(page);
});

test("an asset nobody can analyse is named, with no verdict, and can be taken out", async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await pickBigMac(page);
  await page.goto(`/trade-calc?${Q}&partner=12&give=mfl%3A0682,mfl%3A9999&get=10229`);
  const calc = page.getByTestId("trade-calc");
  const un = calc.getByTestId("unavailable");
  await expect(un).toBeVisible();
  await expect(un.getByTestId("unavailable-row")).toHaveCount(1);
  await expect(un).toContainText("Can't analyse mfl:9999 (you give): not a player isuckatfantasy knows in this league.");
  await expect(calc.getByTestId("trade-result")).toHaveCount(0); // no verdict
  await expect(calc.getByTestId("picked-give")).toContainText(/Houston Texans QB \+ mfl:9999\s\(not on this roster\)/);
  await page.screenshot({ path: shot("unavailable", info.project.name), fullPage: true });
  await un.getByTestId("unavailable-remove").click();
  await expect(page).toHaveURL(/give=mfl%3A0682(&|$)/);
  await expect(calc.getByTestId("trade-result")).toBeVisible();
  await expect(calc.getByTestId("trade-headline")).toContainText("You give Houston Texans QB; you get Rashee Rice");
  await noSidewaysScroll(page);
});
