// Wave J-B (JB-2): the clean record on the screen. Phone at 375 and desktop at 1300; screenshots into
// docs/handbacks/jb2/ (SHOTS_JB2) or e2e/.out.
//
// Fixtures (web/fixtures/jb2/; this database has no week-5 actuals, so both are shaped like the live record the PO read
// on 14 October):
// * my-week_scrubs_2_lean.json — IX-4's saved My Week (League of Scrubs team 2, week 5, the Boston / Jefferson coin flip
//   at FLEX2) through the route's own steps: Sleeper's numbers from this database's week-5 snapshot (fetched 5 Oct,
//   before the 9 Oct first kickoff) priced by why.market_points, the tally the live record's (13 disagreements, ours right 4, Sleeper right 8),
//   then sleeper_lean.apply.
// * record_scrubs.json — this database's /api/record answer (the history and weeks 1–3 of the lineups are its own) with
//   week 5 scored from the live numbers.
import { expect, test, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveDecisions } from "../decisions-fixtures";
import { SCRUBS, serveFixtures } from "../fixtures";

const FX = join(import.meta.dirname, "..", "..", "fixtures", "jb2");
const SHOTS = process.env.SHOTS_JB2 ?? join(import.meta.dirname, "..", ".out");
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const WEEK: any = JSON.parse(readFileSync(join(FX, "my-week_scrubs_2_lean.json"), "utf8"));
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const REC: any = JSON.parse(readFileSync(join(FX, "record_scrubs.json"), "utf8"));
const LEAN = "Sleeper's numbers lean to Justin Jefferson. This season, on the 13 close calls where we have disagreed, Sleeper was right 8 times, we 4.";

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
  page.screenshot({ path: join(SHOTS, `jb2-${name}-${project === "phone" ? "375" : "1300"}.jpg`), type: "jpeg", quality: 70, fullPage: true });

const serve = (page: Page, re: RegExp, body: unknown, status = 200) =>
  page.route(re, (route: Route) => route.fulfill({ status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(body) }));

test("My Week: the Boston / Jefferson coin flip says Sleeper's numbers lean to Jefferson, with the season's tally", async ({ page }, info) => {
  const a = [...WEEK.actions, ...(WEEK.more_actions ?? [])].find((x: { sleeper_lean?: string }) => x.sleeper_lean);
  expect(a?.sleeper_lean).toBe(LEAN);
  await serve(page, /\/api\/my-week\?/, WEEK);
  await page.goto(`/?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("action-card").first()).toBeVisible();
  const more = page.getByTestId("decisions-more");
  if (await more.count()) await more.locator(":scope > summary").click();
  const lean = page.getByTestId("sleeper-lean");
  await expect(lean).toHaveCount(1);
  await expect(lean).toHaveText(LEAN);
  // no number on the call moved: the action's own words are the saved answer's
  await expect(lean.locator("xpath=..").getByTestId("action-text")).toHaveText(a.action.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1"));
  await noSidewaysScroll(page);
  await shot(page, "myweek-lean", info.project.name);
});

test("My Week: no lean line when the answer carries none (a snapshot after the first kickoff, or Sleeper agrees)", async ({ page }) => {
  const plain = structuredClone(WEEK);
  for (const x of [...plain.actions, ...(plain.more_actions ?? []), ...(plain.review ?? [])]) delete x.sleeper_lean;
  await serve(page, /\/api\/my-week\?/, plain);
  await page.goto(`/?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("action-card").first()).toBeVisible();
  await expect(page.getByTestId("sleeper-lean")).toHaveCount(0);
});

test("About: the record week by week, labelled; the lineups' line; the earlier seasons labelled for what they are", async ({ page }, info) => {
  await serve(page, /\/api\/record\?/, REC);
  await page.goto(`/about?league=${SCRUBS}&team=2`);
  const weeks = page.getByTestId("record-weeks");
  await expect(weeks).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("record-weeks-label")).toHaveText(/^Both numbers frozen before kickoff/);
  const row = page.locator('[data-testid="record-week"][data-week="5"]');
  await expect(row).toContainText("4.3 · 4.1");
  await expect(row).toContainText("13 · 17");
  await expect(row).toContainText("of 26");
  await expect(row).toContainText("9 · 5");
  await page.getByTestId("record-by-position").locator("summary").click();
  await expect(page.getByTestId("record-position").filter({ hasText: "Week 5 · WR" })).toContainText("miss 4.2 ours · 4.0 Sleeper's");
  await expect(page.getByTestId("record-lineups")).toHaveText(
    "In week 5 our recommended lineups scored 1,251.1; managers' own 1,287.3; Sleeper's numbers would have scored 1,323.0.",
  );
  await expect(page.getByTestId("record-history-label")).toHaveText(/^Sleeper's past numbers are served after the games/);
  await expect(page.getByTestId("record-history-row")).toHaveCount(REC.history.by_position.filter((h: { error: unknown }) => h.error).length);
  for (const id of ["record-weeks", "record-history-table"])
    for (const bad of ["beat", "crushed", "unlucky", " due "]) await expect(page.getByTestId(id)).not.toContainText(bad);
  await noSidewaysScroll(page);
  await page.getByTestId("record").scrollIntoViewIfNeeded();
  await shot(page, "about-record", info.project.name);
});

test("About: the record cannot be read — 'not available right now', never 'no record'", async ({ page }) => {
  await serve(page, /\/api\/record\?/, { error: "boom" }, 500);
  await page.goto(`/about?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("record-unavailable")).toHaveText("Our record is not available right now.");
  await expect(page.getByTestId("record")).not.toContainText(/no record/i);
});
