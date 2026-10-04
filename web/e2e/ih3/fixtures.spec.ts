// Wave I-H (IH-3): the week's win probability on My Week — one line under the opponent line ("This week is a coin
// flip: 53%, 120 to 117 expected."), one per game of a double header (dad's league, week 4: Knight Train plays Big Mac
// Attack and Klaby Crew), nothing when the answer has no `win` (an answer from before Wave I-H, or no range for the
// league); the League screen's odds per game. Information only: the line never names a player to start. Phone at 375
// (inside the phone project) and desktop at 1300. The expected words and numbers are read from the recording (a
// re-recording after kickoffs moves them: locked lineups, games in).
//
// The answers are the API's own, recorded by api/tests/test_ih3.py::test_record_e2e_answers (League of Scrubs roster 6
// from the main database, the week-4 opponent from the Sleeper fixtures; MFL 70587 team 1 from the MFL fixtures) into
// web/fixtures/ih3/api_ih3.json. Re-record:
//   cd api && IH3_RECORD=1 PYTHONPATH=. uv run pytest -q tests/test_ih3.py -k record
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures, SCRUBS } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "ih3", "api_ih3.json");
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};

type Win = { line: string; opponent_roster_id: number; also?: Win[] };
type Side = { roster_id: number; team_name: string; percent?: number; expected?: number };
type Game = { matchup_id: number; a: Side; b: Side; p: number | null };
const body = <T,>(k: string) => saved[k]?.body as T;
const myWeekScrubs6 = () => body<{ win: Win; opponent: { team_name: string } }>(`/api/my-week?league=${SCRUBS}&team=6`);
const myWeekKnight = () => body<{ win: Win; opponent: { team_name: string; roster_id: number; also: { team_name: string; roster_id: number }[] } }>(
  "/api/my-week?league=mfl%3A70587&team=1",
);
const odds = (league: string) => body<{ games: Game[] }>(`/api/league/week-odds?league=${encodeURIComponent(league)}`);
const sideText = (s: Side) => `${s.percent}% · ${Math.round(s.expected ?? 0)} expected`;

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
  page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `ih3-${name}-${project}.png`), fullPage: false });

const LINE = /^(This week is a coin flip|You're a (slight|clear) (favorite|underdog) this week): \d{1,2}%, \d+ to \d+ expected\.( \d+ of your \d+ have played, \d+ of theirs\.)?$/;

test("League of Scrubs roster 6: one line under the opponent line, the percentage and both expected totals", async ({ page }, info) => {
  await page.goto(`/?league=${SCRUBS}&team=6`);
  await expect(page.getByTestId("my-week")).toBeVisible();
  const line = page.getByTestId("win-line");
  await expect(line).toHaveCount(1);
  await expect(line).toHaveText(LINE);
  await expect(line).toHaveText(myWeekScrubs6().win.line);         // the recording's own line (53%, 120 to 117 at 12:58 ET)
  await expect(line).toHaveAttribute("title", "assuming the players' weeks are independent except teammates and opponents");
  // right under the opponent line, above the league line
  const opp = await page.getByTestId("opponent-line").boundingBox();
  const box = await line.boundingBox();
  const lg = await page.getByTestId("league-line").boundingBox();
  expect(opp && box && box.y > opp.y).toBeTruthy();
  if (lg) expect(box && box.y < lg.y).toBeTruthy();
  // information, never an instruction
  expect((await line.textContent())?.toLowerCase()).not.toMatch(/\b(start|sit|bench|ceiling|chase)\b/);
  await noSidewaysScroll(page);
  await shot(page, "myweek-scrubs6", info.project.name);
});

test("dad's league, a double header: two lines, each naming its opponent", async ({ page }, info) => {
  await page.goto("/");
  await expect(page.getByTestId("leagues")).toBeVisible();
  await page.getByTestId("mfl-link").fill("70587");
  await page.getByTestId("mfl-go").click();
  await page.getByTestId("mfl-team").filter({ hasText: "Knight Train" }).click();
  await expect(page.getByTestId("my-week")).toBeVisible();
  const lines = page.getByTestId("win-line");
  await expect(lines).toHaveCount(2);
  const d = myWeekKnight();
  const name = (rid: number) => [d.opponent, ...d.opponent.also].find((o) => o.roster_id === rid)?.team_name;
  expect(name(d.win.opponent_roster_id)).toBe("Big Mac Attack");
  await expect(lines.nth(0)).toHaveText(`Big Mac Attack: ${d.win.line}`);
  await expect(lines.nth(1)).toHaveText(`Klaby Crew: ${d.win.also![0].line}`);
  for (const t of await lines.allTextContents()) expect(t.replace(/^[^:]+: /, "")).toMatch(LINE);
  await expect(lines.nth(0)).toHaveAttribute("data-side", "underdog");
  await noSidewaysScroll(page);
  await shot(page, "myweek-double-header", info.project.name);
});

test("an answer without `win` shows no line", async ({ page }) => {
  await page.goto(`/?league=${SCRUBS}&team=2`);          // the base fixture (recorded before Wave I-H)
  await expect(page.getByTestId("my-week")).toBeVisible();
  await expect(page.getByTestId("opponent-line")).toBeVisible();
  await expect(page.getByTestId("win-line")).toHaveCount(0);
});

test("League screen, a house league: this week's games with both teams' chance, asked after the screen shows", async ({ page }, info) => {
  await page.goto(`/league?league=${SCRUBS}&team=6`);
  const card = page.getByTestId("league-odds");
  await expect(card).toBeVisible();
  const games = card.getByTestId("league-game");
  await expect(games).toHaveCount(5);
  const mine = card.locator('[data-testid="league-game"][data-mine="1"]');
  await expect(mine).toHaveCount(1);
  const g6 = odds(SCRUBS).games.find((g) => g.a.roster_id === 6 || g.b.roster_id === 6)!;
  await expect(mine.getByTestId("game-odds")).toHaveText([sideText(g6.a), sideText(g6.b)]);
  // the same number My Week shows for roster 6
  const six = g6.a.roster_id === 6 ? g6.a : g6.b;
  expect(myWeekScrubs6().win.line).toContain(`${six.percent}%`);
  for (const t of await card.getByTestId("game-odds").allTextContents()) expect(t).toMatch(/^\d{1,2}% · \d+ expected$/);
  await expect(card.getByTestId("odds-note")).toContainText("independent except teammates and opponents");
  await noSidewaysScroll(page);
  await card.scrollIntoViewIfNeeded();
  await shot(page, "league-scrubs", info.project.name);
});

test("League screen, dad's league: the odds sit in the week's matchups card, both games of the double header", async ({ page }, info) => {
  await page.goto(`/league?league=${encodeURIComponent("mfl:70587")}&team=1`);
  const card = page.getByTestId("league-matchups");
  await expect(card).toBeVisible();
  await expect(card.getByTestId("game-odds").first()).toBeVisible();
  await expect(page.getByTestId("league-odds")).toHaveCount(0);          // no second card
  const mine = card.locator('[data-testid="league-game"][data-mine="1"]');
  await expect(mine).toHaveCount(2);
  await expect(mine.nth(0).getByTestId("game-odds")).toHaveCount(2);
  const got = (await mine.nth(0).getByTestId("game-odds").allTextContents()).sort();
  const gBig = odds("mfl:70587").games.find((g) => [g.a.roster_id, g.b.roster_id].includes(1) && [g.a.roster_id, g.b.roster_id].includes(8))!;
  expect(got).toEqual([sideText(gBig.a), sideText(gBig.b)].sort());          // vs Big Mac Attack
  const kt = gBig.a.roster_id === 1 ? gBig.a : gBig.b;
  expect(myWeekKnight().win.line).toContain(`${kt.percent}%`);               // as My Week says
  await expect(page.getByTestId("league-results").getByTestId("game-odds")).toHaveCount(0);   // last week's results: none
  await noSidewaysScroll(page);
  await card.scrollIntoViewIfNeeded();
  await shot(page, "league-mfl", info.project.name);
});
