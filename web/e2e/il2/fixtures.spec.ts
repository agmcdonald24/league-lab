// Wave I-L (IL-2): MyFantasyLeague complete on dad's league (mfl:70587, team 1). League's "Latest moves" lists MFL's
// moves (one card per move; the trade both ways; never "not available"); this week's matchups card carries each team's
// score so far from MFL's live scoring ("8.0 so far": Thursday's game of week 4) beside the odds; My Week's win line
// counts the starter whose game is over; Waivers lists "Recently added in this league" and the first-come stamp line.
// Phone at 375 (inside the phone project) and desktop at 1300.
//
// The answers are the API's own, recorded by api/tests/test_il2.py::test_record_e2e_answers (the MFL fixtures:
// MFL's own recordings, except the transactions — a synthetic fixture from MFL's documented shape) into
// web/fixtures/il2/api_il2.json. Re-record:
//   cd api && IL2_RECORD=1 PYTHONPATH=. uv run pytest -q tests/test_il2.py -k record
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "il2", "api_il2.json");
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};
const KEY = "mfl%3A70587";

type Tx = { transaction_id: string; transaction_type: string; team_name: string; player_name: string; action: string; week: number };
type Side = { roster_id: number; team_name: string; live?: number | null };
type Win = { line: string; n_played: number; also?: Win[] };
const body = <T,>(k: string) => saved[k]?.body as T;
const league = () => body<{ transactions: Tx[]; matchups: { played: boolean; week: number; games: { a: Side; b: Side }[] }[] }>(`/api/league?league=${KEY}&team=1`);
const myWeek = () => body<{ win: Win }>(`/api/my-week?league=${KEY}&team=1`);
const waivers = () => body<{ recent_adds: { rows: { player_name: string; team_name: string; week: number }[] }; deadline: { words: string } }>(`/api/waivers?league=${KEY}&position=ALL&team=1`);

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return u.pathname + (q.length ? `?${new URLSearchParams(q).toString()}` : "");
};

async function answer(route: Route) {
  const u = new URL(route.request().url());
  const s = saved[keyOf(u)];
  if (!s) return route.fallback();
  return route.fulfill({ status: s.status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(s.body) });
}

test.beforeEach(async ({ context, page }, info) => {
  test.skip(!existsSync(FILE), "no recording yet (see the header)");
  await serveFixtures(context);
  await context.route(/\/api\//, answer);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `il2-${name}-${project}.png`), fullPage: false });

test("League shows MFL's moves: one card per move, newest first, the trade both ways", async ({ page }, info) => {
  await page.goto(`/league?league=${KEY}&team=1`);
  const card = page.getByTestId("moves");
  await expect(card).toBeVisible();
  await expect(card.getByTestId("moves-unavailable")).toHaveCount(0);
  const moves = card.getByTestId("move");
  const ids = [...new Set(league().transactions.map((t) => t.transaction_id))];
  await expect(moves).toHaveCount(ids.length);
  expect(ids.length).toBe(5);
  await expect(moves.nth(0)).toContainText("Big Mac Attack");
  await expect(moves.nth(0)).toContainText("Week 4");
  await expect(moves.nth(0)).toContainText("Dalton Schultz");
  const trade = moves.filter({ hasText: "A.J. Brown" });
  await expect(trade).toHaveCount(1);
  await expect(trade).toContainText("DK Metcalf");
  await expect(trade).toContainText("Millertime · trade");          // the card names one side, the other in brackets
  await expect(trade).toContainText("(Big Mac Attack)");
  const mine = moves.filter({ hasText: "Knight Train" });
  await expect(mine).toContainText("Ja'Kobi Lane");
  await expect(mine).toContainText("Mack Hollins");
  await noSidewaysScroll(page);
  await card.scrollIntoViewIfNeeded();
  await shot(page, "league-moves", info.project.name);
});

test("this week's matchups carry MFL's live score beside the odds; My Week counts the game that is over", async ({ page }, info) => {
  await page.goto(`/league?league=${KEY}&team=1`);
  const card = page.getByTestId("league-matchups");
  await expect(card).toBeVisible();
  const this4 = league().matchups.find((m) => !m.played)!;
  const lives = this4.games.flatMap((g) => [g.a, g.b]).filter((s) => s.live != null).length;
  await expect(card.getByTestId("game-live")).toHaveCount(lives);
  const mine = card.locator('[data-testid="league-game"][data-mine="1"]');
  await expect(mine).toHaveCount(2);                                    // the double header
  await expect(mine.nth(0).getByTestId("game-live")).toHaveText("8.0 so far");
  await expect(mine.nth(1).getByTestId("game-live")).toHaveText("8.0 so far");
  await expect(page.getByTestId("league-results").getByTestId("game-live")).toHaveCount(0);   // last week: final scores only
  await noSidewaysScroll(page);
  await card.scrollIntoViewIfNeeded();
  await shot(page, "league-live", info.project.name);

  await page.goto(`/?league=${KEY}&team=1`);
  await expect(page.getByTestId("my-week")).toBeVisible();
  const lines = page.getByTestId("win-line");
  await expect(lines).toHaveCount(2);
  const w = myWeek().win;
  expect(w.n_played).toBe(1);
  await expect(lines.nth(0)).toContainText(w.line);
  await expect(lines.nth(0)).toContainText("1 of your");
  await noSidewaysScroll(page);
  await shot(page, "myweek-live", info.project.name);
});

test("Waivers: recently added in this league, and the first-come stamp line", async ({ page }, info) => {
  await page.goto(`/waivers?league=${KEY}&team=1`);
  await expect(page.getByTestId("waiver-deadline")).toHaveText(waivers().deadline.words);
  await expect(page.getByTestId("waiver-deadline")).toContainText("first come, first served on MFL");
  const card = page.getByTestId("recent-adds");
  await expect(card).toBeVisible();
  const rows = card.getByTestId("recent-add");
  await expect(rows).toHaveCount(waivers().recent_adds.rows.length);
  await expect(rows.nth(0)).toContainText("Ja'Kobi Lane");
  await expect(rows.nth(0)).toContainText("Knight Train (you) · week 3");
  await expect(card.getByTestId("recent-adds-note")).toHaveText("1 add in weeks 3–4 · MyFantasyLeague transactions");
  await noSidewaysScroll(page);
  await card.scrollIntoViewIfNeeded();
  await shot(page, "waivers-recent", info.project.name);
});
