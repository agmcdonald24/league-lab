// Wave I-Z (IZ-3): the card says what he means for your roster. The Overview reads forecast (the head and its one-line
// why) → the roster line → at most three reasons → his status (Availability, the news line) → the actions; the sections
// below stay. The full page: the head, then the roster line and the reasons. Phone at 375, desktop at 1300.
//
// Two modes. Default: the fixture API (serveFixtures) with the card's answer for Justin Jefferson in League of Scrubs
// carrying the roster line and the reasons the API gave on league_lab_iq4 (Thursday 8 October 16:00 UTC, week 5).
// IZ3_LIVE=http://localhost:<port> (the API on a database, serving web/dist, providers on local fixtures): the same walk
// against it for a house league (League of Scrubs, team 2) and an on-demand one (MFL 70587, team 1), with screenshots
// (JPEG, rule 12) into docs/handbacks/iz3/ (SHOTS_IZ3) when set, else e2e/.out.
import {
  expect,
  test,
  type BrowserContext,
  type Locator,
  type Page,
  type TestInfo,
} from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { FIXTURES, SCRUBS, serveFixtures } from "../fixtures";

const LIVE = process.env.IZ3_LIVE ?? "";
const SHOTS = process.env.SHOTS_IZ3 ?? join(import.meta.dirname, "..", ".out");
mkdirSync(SHOTS, { recursive: true });
if (LIVE) test.use({ baseURL: LIVE });

const JJ = "00-0036322"; // Justin Jefferson (League of Scrubs team 2's bench this week)
const ROSTER_LINE = {
  kind: "bench",
  words: "On your bench this week; his game has started.",
};
const REASONS = [
  {
    key: "role",
    words:
      "Role: 30% of the targets and carries of his team's WRs and TEs and 43% of their fantasy points (weeks 1–3, 3 games). More under Usage.",
  },
  {
    key: "matchup",
    words:
      "Matchup: week 5 @ NO — NO ranks #21 of 32 vs WR (1 = gives up the most). More in the schedule below.",
  },
  {
    key: "form",
    words:
      "Form: 12.8 points per game this season on work worth 8.9. More under Game log.",
  },
];

async function fixtures(context: BrowserContext) {
  await serveFixtures(context);
  const card = JSON.parse(
    readFileSync(join(FIXTURES, "player", `${SCRUBS}_${JJ}.json`), "utf8"),
  ) as Record<string, unknown>;
  // registered after serveFixtures: this answer wins for his card (Playwright runs the last matching route first)
  await context.route(new RegExp(`/api/player/${JJ}\\?`), (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...card,
        roster_line: ROSTER_LINE,
        reasons: REASONS,
      }),
    }),
  );
}

async function narrow(page: Page, info: TestInfo) {
  if (info.project.name === "phone")
    await page.setViewportSize({ width: 375, height: 812 });
}

/** each testid's element sits below the one before it (document order on the page, whatever the scroll container) */
async function inOrder(scope: Locator, ids: string[]) {
  for (const id of ids)
    await expect(scope.getByTestId(id).first(), id).toBeVisible();
  const order = await scope.evaluate((root, list) => {
    const els = list.map((id) => root.querySelector(`[data-testid="${id}"]`));
    return els
      .slice(1)
      .map((el, i) =>
        els[i]!.compareDocumentPosition(el!) & Node.DOCUMENT_POSITION_FOLLOWING
          ? 1
          : 0,
      );
  }, ids);
  expect(order, ids.join(" → ")).toEqual(ids.slice(1).map(() => 1));
}

async function shot(page: Page, name: string, info: TestInfo) {
  await page.screenshot({
    path: join(SHOTS, `iz3_${name}_${info.project.name}.jpg`),
    type: "jpeg",
    quality: 70,
  });
}

const OVERVIEW = [
  "pane-card",
  "pane-why",
  "pane-roster-line",
  "pane-reasons",
  "pane-section-availability",
  "pane-actions",
];

test("the Overview: forecast → roster line → reasons → status → actions; the full page: head → roster line → reasons", async ({
  page,
  context,
}, info) => {
  test.skip(!!LIVE, "the fixture answer");
  await fixtures(context);
  await narrow(page, info);
  await page.goto(`/players?league=${SCRUBS}&team=2&pane=${JJ}`);
  const pane = page.getByTestId("pane");
  await expect(pane.getByTestId("pane-roster-line")).toHaveText(
    ROSTER_LINE.words,
  );
  await expect(pane.getByTestId("pane-roster-line")).toHaveAttribute(
    "data-kind",
    "bench",
  );
  const items = pane.getByTestId("pane-reason");
  await expect(items).toHaveCount(3);
  await expect(items).toHaveText(REASONS.map((r) => r.words));
  for (const r of REASONS) expect(r.words).toMatch(/ More (under|in) /); // each names where to read more
  await inOrder(pane, OVERVIEW);
  await expect(pane.getByTestId("pane-section-availability")).toHaveCount(1); // status once, not again below
  // the full page
  await page.goto(`/player/${JJ}?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("player-roster-line")).toHaveText(
    ROSTER_LINE.words,
  );
  await expect(page.getByTestId("player-reason")).toHaveCount(3);
  await inOrder(page.locator("body"), [
    "player-header",
    "player-roster-line",
    "player-reasons",
  ]);
});

test("no roster line and no reasons in the answer: nothing drawn (a reference league, an older API)", async ({
  page,
  context,
}, info) => {
  test.skip(!!LIVE, "the fixture answer");
  await serveFixtures(context);
  await narrow(page, info);
  await page.goto(`/players?league=${SCRUBS}&team=2&pane=${JJ}`);
  const pane = page.getByTestId("pane");
  await expect(pane.getByTestId("pane-card")).toBeVisible();
  await expect(pane.getByTestId("pane-roster-line")).toHaveCount(0);
  await expect(pane.getByTestId("pane-reasons")).toHaveCount(0);
  await inOrder(pane, [
    "pane-card",
    "pane-section-availability",
    "pane-actions",
  ]);
});

// ---- live: a house league and an on-demand one, drawer and full page, the screens for the hand-back

for (const c of [
  { name: "house_starter", league: SCRUBS, team: 2, gsis: "00-0037840" }, // Kyren Williams (team 2 starts him)
  { name: "house_fa", league: SCRUBS, team: 2, gsis: "00-0033119" }, // Jacoby Brissett (a free agent who would start)
  { name: "mfl_starter", league: "mfl:70587", team: 1, gsis: "00-0040735" }, // Luther Burden III (MFL 70587 team 1)
  { name: "mfl_other", league: "mfl:70587", team: 1, gsis: "00-0036900" }, // Ja'Marr Chase (another team there)
]) {
  test(`live: ${c.name} — drawer and full page`, async ({
    page,
    context,
  }, info) => {
    test.skip(!LIVE || !c.gsis, "IZ3_LIVE (and the player) not set");
    test.setTimeout(120_000);
    await context.route(/^https?:\/\/(?!localhost)/, (route) => route.abort()); // headshots, GA: never fetched by a test
    await narrow(page, info);
    const lg = encodeURIComponent(c.league);
    await page.goto(`/players?league=${lg}&team=${c.team}&pane=${c.gsis}`);
    const pane = page.getByTestId("pane");
    await expect(pane.getByTestId("pane-roster-line")).toBeVisible({
      timeout: 60_000,
    });
    await expect(pane.getByTestId("pane-reason")).toHaveCount(3);
    await inOrder(pane, OVERVIEW);
    await shot(page, `${c.name}_drawer`, info);
    await page.goto(`/player/${c.gsis}?league=${lg}&team=${c.team}`);
    await expect(page.getByTestId("player-roster-line")).toBeVisible({
      timeout: 60_000,
    });
    await inOrder(page.locator("body"), [
      "player-header",
      "player-roster-line",
      "player-reasons",
    ]);
    await shot(page, `${c.name}_page`, info);
  });
}
