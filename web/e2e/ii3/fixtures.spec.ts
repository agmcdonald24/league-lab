// Wave I-I (II-3): the Stats Explorer (the fifth review § 4) — Players · Stats with the WR / TE, RB and QB presets, the
// windows (season / last 3 games played / last 3 calendar weeks / a week range), totals or per game, whose players,
// the column picker (a column the app does not have is offered disabled, with the reason), — for unknown, the sticky
// player column, saved views, 2–4 players side by side, and /receivers → the WR / TE preset. Phone at 375 (inside the
// phone project) and desktop at 1300.
//
// The answers are the API's own, recorded by api/tests/test_ii3.py::test_record_e2e_answers (League of Scrubs roster 2
// on the II-3 clone) into web/fixtures/ii3/api_ii3.json; e2e/fixtures.ts serves them for /api/players?window=…, every
// other route from the shared fixtures. Re-record:
//   cd api && II3_RECORD=1 PYTHONPATH=. uv run pytest -q tests/test_ii3.py -k record
import { expect, test, type Locator, type Page } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures, SCRUBS } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "ii3", "api_ii3.json");
type Row = Record<string, unknown> & { gsis_id: string; player_name: string; position: string; games: number; rostered_by_roster_id: number | null };
type Frame = { players: Row[]; window: { label: string } };
const saved: Record<string, { status: number; body: unknown }> = existsSync(FILE) ? JSON.parse(readFileSync(FILE, "utf8")) : {};
const frame = (q: Record<string, string>) => {
  const qs = new URLSearchParams(Object.entries({ league: SCRUBS, limit: "1000", ...q }).sort(([a], [b]) => a.localeCompare(b)));
  return saved[`/api/players?${qs.toString()}`]?.body as Frame;
};
const KYREN = "00-0037840";
const scrubs = (extra = "") => `/players?league=${SCRUBS}&team=2${extra}`;

test.beforeEach(async ({ context, page }, info) => {
  test.skip(!existsSync(FILE), "no recording yet (see the header)");
  await serveFixtures(context);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}
const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `ii3-${name}-${project}.png`), fullPage: false });
async function tap(page: Page, el: Locator, isMobile: boolean) {
  // the phone's tab bar sits over the bottom of the screen: bring the control to the middle first
  await el.evaluate((n) => n.scrollIntoView({ block: "center", inline: "nearest" }));
  if (isMobile) await el.tap();
  else await el.click();
}
const pct = (v: unknown) => (typeof v === "number" ? `${(v * 100).toFixed(1)}%` : "—");

test("the question on one screen: available WRs by target share, with their receiving yards per game", async ({ page, isMobile }, info) => {
  const f = frame({ position: "WR,TE", window: "season" });
  const want = f.players
    .filter((p) => p.position === "WR" && p.rostered_by_roster_id === null)
    .sort((a, b) => ((b.target_share as number) ?? -1) - ((a.target_share as number) ?? -1) || a.player_name.localeCompare(b.player_name))[0];
  await page.goto(scrubs("&position=WR&who=fa"));
  const table = page.getByTestId("players-table");
  await expect(table.getByTestId("players-table-row").first()).toBeVisible();
  // the WR / TE preset: target share sorted, receiving yards per game a column beside it
  await expect(page.getByTestId("sort-target_share")).toBeVisible();
  await expect(page.getByTestId("sort-receiving_yards")).toHaveText(/REC YDS\/G/i);
  await expect(page.getByTestId("players-answer")).toContainText(`Highest target share: ${want.player_name}, ${pct(want.target_share)}`);
  await expect(page.getByTestId("players-answer")).toContainText(`${(want.receiving_yards_per_game as number).toFixed(1)} receiving yards per game`);
  const first = table.getByTestId("players-table-row").first();
  await expect(first).toContainText(want.player_name);
  await expect(first.locator('[data-col="target_share"]')).toHaveText(pct(want.target_share));
  await expect(first.locator('[data-col="receiving_yards"]')).toHaveText((want.receiving_yards_per_game as number).toFixed(1));
  await expect(first.locator('[data-col="target_share"]')).toHaveAttribute("title", /of \d+ team targets in his \d+ games?/);
  // sorted ascending over the whole set, then back
  await tap(page, page.getByTestId("sort-target_share"), isMobile);
  await expect(page).toHaveURL(/sort=target_share&dir=asc/);
  await noSidewaysScroll(page);
  await shot(page, "question", info.project.name);
});

test("Kyren Williams: the table's carry share is the card's", async ({ page }) => {
  const card = saved[`/api/player/${KYREN}?league=${SCRUBS}`]?.body as { sections: { usage: { blocks: { kind: string; metrics?: { label: string; value: string }[] }[] } } };
  const onCard = card.sections.usage.blocks.flatMap((b) => b.metrics ?? []).find((m) => m.label === "Carry share")!.value;
  await page.goto(scrubs("&position=RB&q=kyren"));
  const row = page.getByTestId("players-table").getByTestId("players-table-row").filter({ hasText: "Kyren Williams" });
  await expect(row.locator('[data-col="carry_share"]')).toHaveText(onCard);
  const t = frame({ position: "RB", window: "season" }).players.find((p) => p.gsis_id === KYREN)!;
  await expect(row.locator('[data-col="carry_share"]')).toHaveAttribute("title", `${t.carries} of ${t.team_carries} team carries in his ${t.games} games`);
});

test("windows: last 3 games played vs last 3 calendar weeks vs a week range; totals or per game", async ({ page, isMobile }) => {
  await page.goto(scrubs("&position=WRTE"));
  await expect(page.getByTestId("stats-window-label")).toContainText("Season (weeks 1–3)");
  await page.getByTestId("stats-window-pick").selectOption("last3");
  await expect(page).toHaveURL(/window=last3/);
  await expect(page.getByTestId("stats-window-label")).toContainText("Last 3 games played");
  await expect(page.getByTestId("stats-window-label")).toContainText("the G column says how many");
  await page.getByTestId("stats-window-pick").selectOption("last3w");
  await expect(page.getByTestId("stats-window-label")).toContainText(/Last 3 calendar weeks \(weeks 1–3\)/);
  await page.goto(scrubs("&position=RB&window=weeks&weeks=1-2"));
  await expect(page.getByTestId("stats-window-label")).toContainText("Weeks 1–2 (calendar weeks)");
  const games = await page.getByTestId("players-table").locator('[data-col="games"]').allTextContents();
  expect(games.length).toBeGreaterThan(0);
  expect(games.every((g) => Number(g) <= 2)).toBe(true);
  // minimum opportunities (targets + carries in the window): fewer rows, every one over the bar
  const rb = frame({ position: "RB", window: "weeks", weeks: "1-2" }).players;
  const over = rb.filter((p) => ((p.targets as number) ?? 0) + ((p.carries as number) ?? 0) >= 20).length;
  await page.getByTestId("stats-minopp").selectOption("20");
  await expect(page).toHaveURL(/minopp=20/);
  await expect(page.getByTestId("players-answer")).toContainText(`· ${over} players ·`);
  // totals ↔ per game: counts switch, shares keep their own denominators
  await expect(page.getByTestId("sort-carries")).toHaveText(/CAR\/G/i);
  await tap(page, page.getByTestId("mode-total"), isMobile);
  await expect(page).toHaveURL(/mode=total/);
  await expect(page.getByTestId("sort-carries")).toHaveText(/^CAR\s*/i);
  await expect(page.getByTestId("sort-carry_share")).toHaveText(/CAR %/i);
});

test("the column picker: definitions, verified extras, routes unavailable in-season with the reason; — never 0", async ({ page }, info) => {
  await page.goto(scrubs("&position=WRTE"));
  await page.getByTestId("stats-columns").locator("summary").click();
  await expect(page.getByTestId("col-routes")).toBeDisabled();
  await expect(page.getByTestId("col-why-routes")).toContainText("Not available");
  await expect(page.getByTestId("col-route_participation")).toBeDisabled(); // 2026: participation comes after the season
  await expect(page.getByTestId("col-why-route_participation")).toContainText("after the season");
  // a verified extra joins the table; a cell it cannot work out is — with the reason, never 0
  await page.getByTestId("col-first_read_target_share").check();
  await expect(page).toHaveURL(/cols=/);
  const cells = page.getByTestId("players-table").locator('[data-col="first_read_target_share"]');
  await expect(cells.first()).toBeVisible();
  const dash = cells.filter({ hasText: "—" });
  if ((await dash.count()) > 0) await expect(dash.first()).toHaveAttribute("title", /charting/i);
  await expect(page.getByTestId("players-table").locator("thead")).toContainText(/1st-read %/i);
  await shot(page, "columns", info.project.name);
});

test("sticky player column and header on a phone; 2–4 side by side; saved views; /receivers lands on the WR / TE preset", async ({ page, isMobile }, info) => {
  await page.goto(`/receivers?league=${SCRUBS}&team=2`);
  await expect(page).toHaveURL(/\/players\?.*position=WRTE/);
  await expect(page.getByTestId("sub-players")).toHaveAttribute("aria-current", "page");
  const box = page.getByTestId("stats-scroll");
  const firstCell = page.getByTestId("players-table").getByTestId("players-table-row").first().locator("td").first();
  const before = (await firstCell.boundingBox())!;
  await box.evaluate((el) => el.scrollBy({ left: 400 }));
  await page.waitForTimeout(100);
  const after = (await firstCell.boundingBox())!;
  expect(Math.abs(after.x - before.x)).toBeLessThan(2); // the player column stays put while the numbers scroll
  await noSidewaysScroll(page);
  // two to four players side by side, then on to Compare
  const picks = page.getByTestId("stats-select");
  for (const i of [0, 1, 2]) await tap(page, picks.nth(i), isMobile);
  await expect(page.getByTestId("stats-compare")).toContainText("Side by side (3 of 4)");
  await expect(page.getByTestId("stats-open-compare")).toHaveAttribute("href", /\/compare\?a=.+&b=.+/);
  await shot(page, "side-by-side", info.project.name);
  // a saved view comes back after a reload (this browser only)
  await page.getByTestId("stats-columns").locator("summary").click();
  await page.getByTestId("stats-view-name").fill("My WR check");
  await page.getByTestId("stats-view-save").click();
  await page.reload();
  await page.getByTestId("stats-columns").locator("summary").click();
  await expect(page.getByTestId("stats-view")).toHaveText(["My WR check"]);
});
