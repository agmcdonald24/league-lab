// Wave I-X (IX-4): My Week — one matchup number, the lineup it is, three decisions (the review of 10 October § 1, § 4's
// Big Mac Attack paragraph, § 5's news sentence). Phone at 375 (no sideways page scroll) and desktop at 1300.
//
// The answers are the API's own, recorded from this branch's API on league_lab_iq4 (web/fixtures/ix4/; `curl
// /api/my-week?league=<id>&team=<n>` with the on-demand timings dropped) at three clocks: Thursday 8 October 12:00 UTC
// (week 5 before its first kickoff: "before"), Saturday 10 October 16:00 UTC (Thursday's game has kicked off: "live",
// no points in yet) and Monday 5 October 12:00 UTC (week 4 with every Sunday game in: "played"). The rest of the screen
// (leagues, status, waivers) is the fixture API's (e2e/fixtures.ts, e2e/decisions-fixtures.ts).
import { expect, test, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveDecisions } from "../decisions-fixtures";
import { SCRUBS, serveFixtures } from "../fixtures";

const IX4 = join(import.meta.dirname, "..", "..", "fixtures", "ix4");
const SHOTS = process.env.SHOTS_IX4 ?? join(import.meta.dirname, "..", ".out");
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const read = (name: string): any => JSON.parse(readFileSync(join(IX4, name), "utf8"));
const MFL = "mfl:70587";

async function serveWeek(page: Page, file: string) {
  await page.route(/\/api\/my-week\?/, (route: Route) =>
    route.fulfill({ status: 200, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: readFileSync(join(IX4, file), "utf8") }),
  );
}

test.beforeEach(async ({ context, page }, info) => {
  await serveFixtures(context);
  await serveDecisions(context);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(SHOTS, `ix4-${name}-${project === "phone" ? "375" : "1300"}.png`), fullPage: true });

const strip = (md: string) => md.replace(/\*\*/g, "").replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");

// the head: one summary (the line, what it is, the chance), the league rank as detail with no total; no other total
async function oneSummary(page: Page, d: { matchup: { line: string; basis: string | null; chance: string | null; state: string }; lineup_value: number }) {
  const m = d.matchup;
  await expect(page.getByTestId("matchup")).toHaveCount(1);
  await expect(page.getByTestId("matchup")).toHaveAttribute("data-state", m.state);
  await expect(page.getByTestId("matchup-line")).toHaveText(strip(m.line));
  if (m.basis) await expect(page.getByTestId("matchup-basis")).toHaveText(m.basis);
  if (m.chance) await expect(page.getByTestId("matchup-chance")).toHaveText(m.chance);
  await expect(page.getByTestId("opponent-line")).toHaveCount(0);
  await expect(page.getByTestId("win-line")).toHaveCount(0);
  const head = await page.locator("main section").first().innerText();
  expect(head).not.toContain(d.lineup_value.toFixed(2));      // "125.07" nowhere in the head: the total is said once
  expect(head).not.toContain("best lineup projects");
}

// the table: the recommendation, its total, the provider's lineup compared where known
async function recommended(page: Page, d: { recommended: { rows: { now_words?: string | null }[]; total: number | null; words: string | null } }) {
  const r = d.recommended;
  await expect(page.getByTestId("lineup-head")).toHaveText("Recommended lineup");
  if (r.words) await expect(page.getByTestId("lineup-vs-provider")).toContainText(r.words);
  else await expect(page.getByTestId("lineup-vs-provider")).toHaveCount(0);
  await expect(page.getByTestId("lineup").locator("tbody tr")).toHaveCount(r.rows.length);
  await expect(page.getByTestId("lineup-now")).toHaveCount(r.rows.filter((x) => x.now_words).length);
  if (r.total !== null) await expect(page.getByTestId("lineup-total")).toHaveText(r.total.toFixed(1));
  await expect(page.getByText(/the call above keeps/)).toHaveCount(0);
}

// three decisions at most, the rest behind More; no news card without news
async function threeFirst(page: Page, d: { actions: unknown[]; more_actions: unknown[]; review: unknown[]; changed: { lines: unknown[] } }) {
  const acts = page.getByTestId("week-actions");
  const shown = acts.locator(':scope > [data-testid="action-card"], :scope > [data-testid="review-line"]');
  const all = d.actions.length + d.more_actions.length + d.review.length;
  expect(await shown.count()).toBeLessThanOrEqual(3);
  if (all > 3) await expect(page.getByTestId("decisions-more")).toBeVisible();
  if (!d.changed.lines.length) await expect(page.getByTestId("what-changed")).toHaveCount(0);
  await expect(page.getByText("Nothing has changed since the morning build.")).toHaveCount(0);
}

test("League of Scrubs team 2 before week 5's first kickoff: each side's best lineup, labelled, and the chance", async ({ page }, info) => {
  const d = read("my-week_scrubs_2_before.json");
  expect(d.matchup.state).toBe("before");
  await serveWeek(page, "my-week_scrubs_2_before.json");
  await page.goto(`/?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("team-name")).toHaveText("MacZaddy");
  await oneSummary(page, d);
  await expect(page.getByTestId("matchup-line")).toContainText(": you project ");
  await expect(page.getByTestId("matchup-basis")).toHaveText("Each side's best lineup by our projections.");
  await recommended(page, d);
  await threeFirst(page, d);
  await noSidewaysScroll(page);
  await shot(page, "scrubs2-before", info.project.name);
});

test("League of Scrubs team 2 during week 5: the live line is the one summary", async ({ page }, info) => {
  const d = read("my-week_scrubs_2_live.json");
  expect(d.matchup.state).toBe("live");
  await serveWeek(page, "my-week_scrubs_2_live.json");
  await page.goto(`/?league=${SCRUBS}&team=2`);
  await oneSummary(page, d);
  await expect(page.getByTestId("matchup-line")).toContainText(" expected.");
  await expect(page.getByTestId("matchup-basis")).toContainText("Points scored so far plus projections for players still to play");
  await recommended(page, d);
  await threeFirst(page, d);
  // More opens on the rest, keyboard-reachable
  const more = page.getByTestId("decisions-more");
  if (await more.count()) {
    await more.locator(":scope > summary").focus();
    await page.keyboard.press("Enter");
    await expect(more.locator('[data-testid="action-card"], [data-testid="review-line"]').first()).toBeVisible();
  }
  await noSidewaysScroll(page);
  await shot(page, "scrubs2-live", info.project.name);
});

test("a week with games already played: points in plus projections, how many have played", async ({ page }, info) => {
  const d = read("my-week_scrubs_2_played.json");
  expect(d.win.n_played).toBeGreaterThan(0);
  await serveWeek(page, "my-week_scrubs_2_played.json");
  await page.goto(`/?league=${SCRUBS}&team=2`);
  await oneSummary(page, d);
  await expect(page.getByTestId("matchup-basis")).toContainText(`${d.win.n_played} of your ${d.win.n_starters}`);
  await recommended(page, d);
  await noSidewaysScroll(page);
  await shot(page, "scrubs2-played", info.project.name);
});

test("MFL Big Mac Attack: the Chicago team-QB call says check who starts first, on the call and on its row", async ({ page }, info) => {
  const d = read("my-week_mfl70587_8_live.json");
  await serveWeek(page, "my-week_mfl70587_8_live.json");
  await page.goto(`/?league=${encodeURIComponent(MFL)}&team=8`);
  await expect(page.getByTestId("team-name")).toHaveText("Big Mac Attack");
  await oneSummary(page, d);
  await expect(page.getByTestId("league-line")).toHaveCount(0);           // no rank on demand, and never the total
  const call = page.locator('[data-testid="action-card"]').filter({ hasText: "check who starts first" });
  await expect(call).toHaveCount(1);
  await expect(call.getByTestId("action-text")).toHaveText("Chicago Bears QB or Houston Texans QB at team QB: check who starts first.");
  await expect(call.getByTestId("action-reason")).toContainText("Chicago");
  await expect(call.getByTestId("action-kind")).toContainText("Close call");
  await expect(page.getByTestId("lineup-check")).toHaveText("? Check who starts for Chicago before kickoff");
  await recommended(page, d);
  await expect(page.getByTestId("lineup-now").first()).toContainText("In MFL now: Houston Texans QB");
  await threeFirst(page, d);
  await noSidewaysScroll(page);
  await shot(page, "mfl8-live", info.project.name);
});
