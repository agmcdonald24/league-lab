// Wave I-F (IF-4): the decision-quality review § Priority 4 on fixtures — the close call kept in view ("No clear upgrade"),
// What changed, the drawer focused on the decision (the ledger behind expanders), the bench-only expander, the margin's
// comparator, the schedule table, "Updated". Phone at 375 px (inside the phone project) and desktop at 1300.
//
// The answers are the API's own, recorded by api/tests/test_if4.py::test_record_e2e_answers (the review's League of Scrubs
// roster 6 case built from the clone's rows — Williams and Tuten at FLEX, the submitted lineup = the optimizer's —, roster
// 2 with the ESPN fixture overlay: Jefferson Out, his RotoWire news) into web/fixtures/if4/api_if4.json. Re-record:
//   cd api && IF4_RECORD=1 uv run pytest -q tests/test_if4.py -k record
import { expect, test, type Locator, type Page, type Route } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures, SCRUBS, TEST_LEAGUE } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "if4", "api_if4.json");
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};
const WILLIAMS = "00-0037240";

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

async function tap(page: Page, loc: Locator, isMobile: boolean) {
  if (isMobile) await loc.tap();
  else await loc.click();
}

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `if4-${name}-${project}.png`), fullPage: true });

test("the review's close call stays in view: No clear upgrade, Compare, the set line, nothing has changed", async ({ page, isMobile }, info) => {
  await page.goto(`/?league=${SCRUBS}&team=6`);
  const acts = page.getByTestId("week-actions");
  await expect(acts).toBeVisible();
  const line = acts.getByTestId("review-line");
  await expect(line).toHaveCount(1);
  await expect(line.getByTestId("review-kind")).toHaveText("≈ No clear upgrade");
  await expect(line.getByTestId("review-words")).toHaveText(
    "Tuten or Williams at FLEX: a coin flip, 0.3 points apart; your lineup has Williams — no clear upgrade.",
  );
  await expect(line.getByTestId("review-compare")).toHaveAttribute("href", new RegExp(`/compare\\?a=00-0040719&b=${WILLIAMS}`));
  await expect(page.getByTestId("set-line")).toContainText("No clear upgrade elsewhere.");
  await expect(page.getByTestId("week-answer")).toHaveCount(0); // not the blanket "Your lineup is set — nothing to change."
  await expect(acts).not.toContainText("nothing to change");
  await expect(page.getByTestId("what-changed").getByTestId("changed-empty")).toHaveText("Nothing has changed since the morning build.");
  // the lineup: each margin names its comparator; a slot nobody can fill says so (not the whole projection as a gap)
  const lineup = page.getByTestId("lineup");
  if (isMobile) {
    await expect(lineup.getByTestId("margin-line").filter({ hasText: "no eligible reserve" }).first()).toBeVisible();
    await expect(lineup.getByTestId("margin-line").filter({ hasText: "over Lloyd" })).toHaveCount(1);
  } else {
    await expect(lineup.getByTestId("margin-cell").filter({ hasText: "no eligible reserve" }).first()).toBeVisible();
    await expect(lineup.getByTestId("margin-cell").filter({ hasText: "over Lloyd" })).toHaveCount(1);
  }
  // the bench expander: the bench and who can't play only — no starter repeated
  await tap(page, page.getByTestId("lineup-full").locator("summary"), isMobile);
  const bench = page.getByTestId("lineup-full-table");
  await expect(bench).toBeVisible();
  await expect(bench.getByRole("link", { name: "Kirk Cousins" })).toHaveCount(0);
  await expect(bench.getByRole("link", { name: "MarShawn Lloyd" })).toHaveCount(1);
  // "Updated …": the exact time and the feed names behind a tap
  const upd = page.getByTestId("updated");
  await expect(upd.getByTestId("updated-ago")).toHaveText(/ago|just now/);
  await tap(page, upd.locator("summary"), isMobile);
  await expect(upd.getByTestId("updated-exact")).toHaveText(/^Last data load \w{3}, \w{3} \d+, \d+:\d\d [AP]M ET\.$/);
  await noSidewaysScroll(page);
  await shot(page, "team6-week", info.project.name);
});

test("what changed: the overlay's move and the news about him, with the source and the time", async ({ page }, info) => {
  await page.goto(`/?league=${SCRUBS}&team=2`);
  const box = page.getByTestId("what-changed");
  await expect(box).toBeVisible();
  const lines = box.getByTestId("changed-line");
  expect(await lines.count()).toBeGreaterThanOrEqual(2);
  expect(await lines.count()).toBeLessThanOrEqual(5);
  await expect(lines.first()).toHaveAttribute("data-kind", "status");
  await expect(lines.first()).toContainText("Justin Jefferson is out (ankle)");
  await expect(lines.first()).toContainText("Injury report (ESPN)");
  const news = box.locator('[data-testid="changed-line"][data-kind="news"]').first();
  await expect(news).toContainText("Justin Jefferson:");
  await expect(news).toContainText("RotoWire via ESPN");
  await noSidewaysScroll(page);
  await shot(page, "team2-changed", info.project.name);
});

test("the drawer is focused on the decision: role words, the ledger and the schedule behind expanders", async ({ page, isMobile }, info) => {
  await page.goto(`/?league=${SCRUBS}&team=6`);
  await tap(page, page.getByTestId("lineup").getByRole("link", { name: "Jameson Williams" }), isMobile);
  const pane = page.getByTestId("pane");
  await expect(pane).toBeVisible();
  await expect(pane.getByTestId("pane-section-projection")).toBeVisible();
  // the week-by-week paragraph and the next four are not in the open section any more
  await expect(pane.getByTestId("pane-section-projection")).not.toContainText("Week by week");
  await expect(pane.getByTestId("pane-section-projection")).not.toContainText("Next 4:");
  // the role line says which comparison is valid (2 games: not enough to say) — never "no role change detected"
  await expect(pane.getByTestId("pane-section-signals")).toContainText("not enough games to say");
  await expect(pane.getByTestId("pane-section-signals")).not.toContainText("no role change detected");
  for (const id of ["pane-more", "pane-schedule"]) await expect(pane.getByTestId(id)).not.toHaveAttribute("open", /.*/); // II-2: the game log is a section of its own
  await tap(page, pane.getByTestId("pane-more").locator("summary"), isMobile);
  await expect(pane.getByTestId("pane-more-body")).toContainText("Week by week");
  await tap(page, pane.getByTestId("pane-schedule").locator("summary"), isMobile);
  const sched = pane.getByTestId("pane-schedule-table");
  await expect(sched.getByTestId("schedule-row").first()).toContainText("at CAR");
  await expect(sched.getByTestId("schedule-row").first()).toContainText("12th-fewest WR points allowed"); // rank 21 of 32
  await expect(sched.getByTestId("schedule-row").first()).toContainText("10.0");
  await expect(sched.getByTestId("schedule-row").filter({ hasText: "Bye" })).toHaveCount(1);
  await noSidewaysScroll(page);
  await shot(page, "pane", info.project.name);
});

test("Compare bolds what bears on the call, says Typical range, and shows the season once", async ({ page }, info) => {
  // Breece Hall (RB) vs CeeDee Lamb (WR) on the Test League fixture: two games each, so the last 3 are the season
  await page.goto(`/compare?a=00-0038120&b=00-0036358&league=${TEST_LEAGUE}&team=3`);
  await expect(page.getByTestId("compare-answer")).toBeVisible();
  await expect(page.getByTestId("compare-bold-rule")).toHaveText("bold: the better number in points (usage is not compared across positions)");
  const pair = (label: string) => page.getByTestId("pair").filter({ has: page.getByText(label, { exact: true }) });
  for (const label of ["Carries per game", "Targets per game"]) {
    if ((await pair(label).count()) === 0) continue;
    await expect(pair(label).getByTestId("pair-a")).not.toHaveClass(/font-extrabold/);
    await expect(pair(label).getByTestId("pair-b")).not.toHaveClass(/font-extrabold/);
  }
  const proj = pair("Projected points this week");
  expect((await proj.locator(".font-extrabold").count()) <= 1).toBe(true);
  await expect(page.getByTestId("compare-group").filter({ hasText: "Last 3 games" })).toHaveCount(0);
  await expect(page.getByTestId("compare-group").filter({ hasText: "This season (2 games)" })).toHaveCount(1);
  await expect(page.getByTestId("compare")).toContainText("Typical range");
  await expect(page.getByTestId("compare")).not.toContainText("most weeks");
  await noSidewaysScroll(page);
  await shot(page, "compare", info.project.name);
});
