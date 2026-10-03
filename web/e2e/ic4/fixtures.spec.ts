// Wave I-D (IC-4): the team units and the double header, finished — dad's league (MFL 70587), Knight Train (team 1):
// rest of season with the units' rows (the team's badge where a face goes, "Priced from Joe Burrow's line"), the Team
// Hub naming a unit by its team ("Bengals QB" + the badge), the League screen listing week 4's double header (12 games,
// two of them Knight Train's). At 375 (phone project) and 1300 (desktop).
//
// The answers are the API's own, recorded from a live API on the MFL fixtures (api/tests/fixtures/mfl/70587, the ESPN
// fixture overlay on) into web/fixtures/mfl/api_70587_ic4.json and replayed here (no API, no database). Re-record:
//   (api on :8745 with LEAGUE_LAB_MFL_FIXTURES / _SLEEPER_FIXTURES / _ESPN_FIXTURES / _PLAYER_IDS_CSV set, the gate off)
//   IC4_RECORD=http://localhost:8745 FIXTURES_PORT=8613 npm run e2e:fixtures -- e2e/ic4
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "mfl", "api_70587_ic4.json");
const RECORD = process.env.IC4_RECORD ?? "";
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};
const MINE = /mfl|70587/i;
const KEY = "mfl:70587";
const Q = `league=${encodeURIComponent(KEY)}&team=1`;

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return u.pathname + (q.length ? `?${new URLSearchParams(q).toString()}` : "");
};

async function answer(route: Route) {
  const u = new URL(route.request().url());
  const key = keyOf(u);
  if (!MINE.test(decodeURIComponent(key))) return route.fallback();
  if (RECORD) {
    const r = await fetch(RECORD + u.pathname + u.search);
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

test.beforeEach(async ({ context }, info) => {
  test.skip(!RECORD && !Object.keys(saved).length, "no recording yet: run with IC4_RECORD (see the header)");
  await serveFixtures(context);
  await context.route(/\/api\//, answer);
  void info;
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

async function pickKnightTrain(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("leagues")).toBeVisible();
  await page.getByTestId("mfl-link").fill("70587");
  await page.getByTestId("mfl-go").click();
  await page.getByTestId("mfl-team").filter({ hasText: "Knight Train" }).click();
  await expect(page.getByTestId("my-week")).toBeVisible();
  await expect(page.getByTestId("lineup")).toBeVisible();
}

const shot = (name: string, project: string) => join(process.env.SHOTS_DIR ?? "e2e/.out", `ic4-${name}-${project}.png`);

test("rest of season: the team units' rows with their team's badge, priced from the starter's line", async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await pickKnightTrain(page);
  await page.goto(`/ros?${Q}&view=points`);
  const ros = page.getByTestId("ros");
  await expect(ros.getByTestId("ros-answer")).toBeVisible();
  // the units are ranked with everyone (the team QBs score like quarterbacks): some in the top 50, with a badge
  await expect(ros.getByTestId("ros-unit-badge").first()).toBeVisible();
  // their own chip: Team QB
  await ros.getByTestId("ros-pos").getByText("Team QB", { exact: true }).click();
  await expect(page).toHaveURL(/position=TMQB/);
  const rows = ros.getByTestId("ros-row");
  await expect(rows).toHaveCount(32);
  await expect(ros.getByTestId("ros-unit-badge")).toHaveCount(32);
  const cin = rows.filter({ hasText: "Cincinnati Bengals QB" });
  await expect(cin).toContainText("yours");
  await expect(cin.getByTestId("team-badge")).toHaveText("CIN");
  await cin.getByTestId("ros-toggle").click();
  await expect(ros.getByTestId("ros-priced-from")).toHaveText("Priced from Joe Burrow's line (the team's starting QB each week).");
  await expect(ros.getByTestId("ros-why")).toBeVisible(); // the starter's pieces, QB rules
  await noSidewaysScroll(page);
  await page.screenshot({ path: shot("ros-team-qb", info.project.name), fullPage: true });
  // Value to my lineup: the units counted against the waiver wire's units
  await page.goto(`/ros?${Q}&position=TMQB`);
  await expect(ros.getByTestId("ros-lineup-answer")).toBeVisible();
  await expect(ros.getByTestId("ros-lineup-why").first()).toBeVisible();
  await expect(ros.getByTestId("ros-lineup-why").filter({ hasText: "TMQB" })).toHaveCount(0);
  await noSidewaysScroll(page);
});

test("Team Hub: the unit is named with its team", async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await pickKnightTrain(page);
  await page.goto(`/team?${Q}`);
  const team = page.getByTestId("team");
  await expect(team.getByTestId("team-answer")).toBeVisible();
  const unit = team.getByTestId("slot-unit");
  await expect(unit).toHaveCount(2); // team QB, team K
  await expect(unit.first()).toContainText("Bengals QB");
  await expect(unit.first().getByTestId("team-badge")).toHaveText("CIN");
  await expect(unit.nth(1)).toContainText("Chargers K");
  await expect(team.getByTestId("team-slots")).not.toContainText("Cincinnati Bengals QB");
  await noSidewaysScroll(page);
  await team.getByTestId("team-slots").screenshot({ path: shot("team-slots", info.project.name) });
});

test("League: week 4's double header lists both of Knight Train's games", async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await pickKnightTrain(page);
  await page.goto(`/league?${Q}`);
  const lg = page.getByTestId("league");
  const m = lg.getByTestId("league-matchups");
  await expect(m).toBeVisible();
  await expect(m.getByTestId("double-header")).toBeVisible();
  await expect(m.getByTestId("league-game")).toHaveCount(12);
  const mine = m.locator('[data-mine="1"]');
  await expect(mine).toHaveCount(2);
  await expect(mine.nth(0)).toContainText("Big Mac Attack");
  await expect(mine.nth(1)).toContainText("Klaby Crew");
  const res = lg.getByTestId("league-results");
  await expect(res.getByTestId("league-game")).toHaveCount(6);
  await expect(res.locator('[data-mine="1"]')).toContainText("Rock33");
  await noSidewaysScroll(page);
  await m.screenshot({ path: shot("league-matchups", info.project.name) });
});
