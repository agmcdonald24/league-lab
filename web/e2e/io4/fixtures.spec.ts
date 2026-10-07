// Wave I-O (IO-4): the fix list — the matchup board's started games and the Stats role-change columns. Phone at 375 and
// desktop at 1300; screenshots into docs/handbacks/io4/ (SHOTS_IO4) and e2e/.out.
//
// Two modes, as e2e/in3. Default: the board's and the Stats frame's answers come from web/fixtures/io4/api_io4.json
// (recorded from the fixture API, its clock pinned to Saturday of week 4: Thursday's game final), the rest from
// serveFixtures. IO4_LIVE=http://localhost:8864 (the fixture API serving web/dist): the same walk against the real
// server, recording those answers.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const LIVE = process.env.IO4_LIVE ?? "";
const DIR = join(import.meta.dirname, "..", "..", "fixtures", "io4");
const RECORDED = join(DIR, "api_io4.json");
const SHOTS = process.env.SHOTS_IO4 ?? join(import.meta.dirname, "..", ".out");
type Recorded = Record<string, { status: number; body: unknown }>;

if (LIVE) test.use({ baseURL: LIVE });

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return `${u.pathname}?${new URLSearchParams(q).toString()}`;
};
const mine = (u: URL) =>
  u.pathname === "/api/matchups/board" ||
  (u.pathname === "/api/matchups/defense" && /^ref:/i.test(u.searchParams.get("league") ?? "")) ||
  (u.pathname === "/api/players" && !!u.searchParams.get("window"));
const recorded: Recorded = existsSync(RECORDED) ? (JSON.parse(readFileSync(RECORDED, "utf8")) as Recorded) : {};

async function api(context: BrowserContext): Promise<void> {
  await context.route(/^https?:\/\/(?!localhost)/, (route) => route.abort()); // headshots, GA: never fetched by a test
  if (LIVE) {
    await context.route(/\/api\//, async (route) => {
      const u = new URL(route.request().url());
      try {
        const res = await route.fetch();
        if (mine(u) && route.request().method() === "GET") recorded[keyOf(u)] = { status: res.status(), body: await res.json() };
        await route.fulfill({ response: res });
      } catch {
        /* the page closed with the request in flight */
      }
    });
    return;
  }
  await serveFixtures(context);
  await context.route(/\/api\//, async (route) => {
    const u = new URL(route.request().url());
    if (!mine(u)) return route.fallback();
    const hit = recorded[keyOf(u)];
    if (!hit) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: `not recorded: ${keyOf(u)}` }) });
    return route.fulfill({ status: hit.status, contentType: "application/json", body: JSON.stringify(hit.body) });
  });
}

async function noSideways(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "no sideways page scroll").toBeLessThanOrEqual(iw + 1);
}

test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test.afterAll(() => {
  if (!LIVE) return;
  mkdirSync(DIR, { recursive: true });
  writeFileSync(RECORDED, JSON.stringify(recorded));
});

test("the board: games that kicked off go below, Still to play by default, Final on their rows", async ({ context, page }, info) => {
  await api(context);
  await page.goto("/matchups?league=ref:half");
  await expect(page.getByTestId("board-row").first()).toBeVisible({ timeout: 30_000 });
  // Saturday of week 4: Thursday's game is final, so the board opens on the games still to play
  await expect(page.getByTestId("board-show")).toBeVisible();
  await expect(page.getByTestId("board-show-to_play")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("board-count")).toContainText(/of \d+ wide receivers still to play/);
  await expect(page.locator("[data-testid=board-row]:not([data-state=to-play])")).toHaveCount(0);
  await noSideways(page);
  if (!info.project.name.includes("phone")) {
    const box = await page.getByTestId("board").boundingBox();
    expect(box!.width).toBeGreaterThan(900);
  }
  await page.screenshot({ path: join(SHOTS, `io4-board-to-play-${info.project.name}.png`) });

  // All games: every receiver, the kicked-off ones last
  await page.getByTestId("board-show-all").click();
  await expect(page).toHaveURL(/bshow=all/);
  await expect(page.getByTestId("board-show-all")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("board-count")).not.toContainText("still to play");

  // the Thursday game picked: its players, each marked Final
  const first = page.getByTestId("board-game").locator("option").nth(1);
  await expect(first).toContainText("Final");
  await page.getByTestId("board-game").selectOption({ index: 1 });
  await expect(page).toHaveURL(/game=/);
  await expect(page.locator("[data-testid=board-row][data-state=final]").first()).toBeVisible();
  await expect(page.locator("[data-testid=board-row]:not([data-state=final])")).toHaveCount(0);
  const badge = page.getByTestId(info.project.name.includes("phone") ? "board-state" : "board-state-wide").first();
  await expect(badge).toHaveText("Final");
  await noSideways(page);
  await page.screenshot({ path: join(SHOTS, `io4-board-final-${info.project.name}.png`) });
});

test("Stats: the role-change columns, sortable, in signed points of share", async ({ context, page }, info) => {
  await api(context);
  await page.goto("/players?league=ref:half&position=WR&view=full&sort=target_share_change&dir=desc");
  await expect(page.getByTestId("players-table-row").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("[data-testid=stats-group-head][data-group='Role change']")).toBeVisible();
  const cell = page.getByTestId("players-table-row").first().locator("td[data-col=target_share_change]");
  await expect(cell).toHaveText(/^\+\d+\.\d pts$/); // the biggest riser first
  await expect(cell).toHaveAttribute("title", /in his last 2 games against .* in his \d+ before them/);
  await page.locator("[data-testid=stats-group-head][data-group='Role change']").scrollIntoViewIfNeeded();
  await noSideways(page);
  await page.screenshot({ path: join(SHOTS, `io4-stats-role-${info.project.name}.png`) });
  // his last 3 games cannot hold 2 games and 2 before them: a dash with the reason, never 0
  await page.goto("/players?league=ref:half&position=WR&view=full&window=last3");
  await expect(page.getByTestId("players-table-row").first()).toBeVisible({ timeout: 30_000 });
  const dash = page.getByTestId("players-table-row").first().locator("td[data-col=target_share_change]");
  await expect(dash).toHaveText("—");
  await expect(dash).toHaveAttribute("title", /Needs his last 2 games played in the window/);
});

// ---- IO-4 fix round (Wave I-O): the corner moves nothing (IO-1's grade). The honesty line as the screen shows it —
// without the record (this database has no ops.context_grade: the projection's inputs alone, never "not graded yet")
// and with it (IO-1's sentence, as context_record.corner_sentence writes it; the answer's projection_words swapped in)
const HEAD =
  "What the projection counts: the points each defense has allowed to the position (this season, the last 4 games and its rank) and the betting lines. Who plays cornerback is not in it: the corner call is a lean from where his targets go, shown for context.";
const RECORD =
  "Graded on 2025 and 2026 weeks 1–4 (Half PPR): receivers with a likely shutdown corner finished 0.4 points below the other receivers against their projection (−1.4 to +0.7; 99 games), those with a likely easy one level with them (−1.1 to +1.2; 79 games) — no measurable effect either way.";

test("the board: the corner is information, the honesty line with and without the record", async ({ context, page }, info) => {
  await api(context);
  await page.goto("/matchups?league=ref:half");
  await expect(page.getByTestId("board-row").first()).toBeVisible({ timeout: 30_000 });
  const honest = page.getByTestId("board-honest");
  await expect(honest).toContainText(HEAD);
  await expect(honest).toContainText("The cornerback is shown beside it and does not move it.");
  await expect(honest).not.toContainText(/not been graded|not graded yet/);
  // no colour from the corner: no red badge; every row's tone is its defense's
  await expect(page.getByTestId("board")).not.toContainText("Shutdown corner");
  for (const row of await page.getByTestId("board-row").all()) {
    const tone = await row.getAttribute("data-tone");
    const def = await row.getByTestId("board-defense-chip").getAttribute("data-tone").catch(() => null);
    if (def !== null) expect(tone).toBe(def);
  }
  await honest.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(SHOTS, `io4-honest-fallback-${info.project.name}.png`) });

  // with the record: the same answers, projection_words = the inputs + IO-1's sentence
  await context.route(/\/api\/matchups\/board\?/, async (route) => {
    const u = new URL(route.request().url());
    const body = (LIVE ? await (await route.fetch()).json() : recorded[keyOf(u)]?.body) as { projection_words: string } | undefined;
    if (!body) return route.fulfill({ status: 404, json: { error: `not recorded: ${keyOf(u)}` } });
    await route.fulfill({ status: 200, json: { ...body, projection_words: `${HEAD} ${RECORD}` } });
  });
  await page.reload();
  await expect(page.getByTestId("board-row").first()).toBeVisible({ timeout: 30_000 });
  await expect(honest).toContainText(`${HEAD} ${RECORD}`);
  await honest.scrollIntoViewIfNeeded();
  await noSideways(page);
  await page.screenshot({ path: join(SHOTS, `io4-honest-record-${info.project.name}.png`) });
});
