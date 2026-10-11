// Wave I-Z (IZ-1): About's record says one sentence about us against Sleeper on past weeks (GET /api/record `history`,
// built from the table by the API), the caveat beside it; nothing while the table has no rows; "not available right
// now" when it cannot be read. The record's answers are the fixtures' (serveFixtures); the `history` block is added here
// in the API's three states — constructed test words, not a measurement (the sandbox has no Sleeper numbers).
// Phone at 390 and desktop at 1300; screenshots into docs/handbacks/iz1/ (SHOTS_IZ1) or e2e/.out.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { FIXTURES, SCRUBS, serveFixtures } from "../fixtures";

const SHOTS = process.env.SHOTS_IZ1 ?? join(import.meta.dirname, "..", ".out");
const SENTENCE =
  "Against Sleeper's free projections on 58 past weeks (2023, 2024, 2025, 2026), on the weekly miss and the order of players: ahead at RB and WR; level at QB; behind at TE. On the close start / sit calls the two disagreed on, ours was right 53% of 4,210 times.";
const CAVEAT =
  "Ours: our model as it runs today, re-run on each past season with only the seasons before it (2026: our projections as published before kickoff). Sleeper's numbers for past weeks are the ones its site serves now, written after the games, so this favours Sleeper; the record above, from week 5 of 2026, compares numbers saved before kickoff.";
const STATES = {
  graded: { available: true, status: "graded", sentence: SENTENCE, caveat: CAVEAT },
  none: { available: false, status: "none", sentence: null, caveat: null },
  unavailable: { available: false, status: "unavailable", sentence: "The comparison with Sleeper on past weeks is not available right now.", caveat: null },
} as const;

async function withHistory(context: BrowserContext, state: keyof typeof STATES) {
  await serveFixtures(context);
  await context.route(/\/api\/record\?/, async (route) => {
    const league = new URL(route.request().url()).searchParams.get("league");
    const body = JSON.parse(readFileSync(join(FIXTURES, `record_${league}.json`), "utf8")) as Record<string, unknown>;
    await route.fulfill({ json: { ...body, history: STATES[state] } });
  });
}

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw).toBeLessThanOrEqual(iw);
}

test("About: the history's one sentence and its caveat, only when the table has rows", async ({ page, context }, info) => {
  await withHistory(context, "graded");
  await page.goto(`/about?league=${SCRUBS}&team=2`);
  const s = page.getByTestId("record-history");
  await expect(s).toHaveText(SENTENCE);
  await expect(page.getByTestId("record-history-caveat")).toHaveText(CAVEAT);
  await noSidewaysScroll(page);
  mkdirSync(SHOTS, { recursive: true });
  await s.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(SHOTS, `iz1-about-history-constructed-${info.project.name}.png`) });
  await page.getByTestId("record").screenshot({ path: join(SHOTS, `iz1-about-record-constructed-${info.project.name}.png`) });
});

test("About: no rows says nothing; a table that cannot be read says so", async ({ page, context }) => {
  await withHistory(context, "none");
  await page.goto(`/about?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("record")).toBeVisible();
  await expect(page.getByTestId("record-answer").or(page.getByTestId("record-empty"))).toBeVisible();
  await expect(page.getByTestId("record-history")).toHaveCount(0);
  await context.unrouteAll({ behavior: "ignoreErrors" });
  await withHistory(context, "unavailable");
  await page.goto(`/about?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("record-history")).toHaveText("The comparison with Sleeper on past weeks is not available right now.");
  await expect(page.getByTestId("record-history-caveat")).toHaveCount(0);
});
