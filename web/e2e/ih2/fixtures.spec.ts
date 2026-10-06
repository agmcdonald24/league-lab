// Wave I-H (IH-2): the small opens on fixtures — the Team page says when MFL's roster was read ("MFL rosters updated
// 4:05 AM ET ›", the exact time on tap, under the roster), the dynasty's Waivers says which days daily claims run
// ("Claims run every day except Saturday at 5:00 AM ET (FAAB blind bids)"), and My Week's "What changed" shows a
// Questionable starter once ("Questionable: Flowers (hamstring) — your lineup is unchanged"). Phone at 375 (inside the
// phone project) and desktop at 1300.
//
// The answers are the API's own, recorded by api/tests/test_ih2.py::test_record_e2e_answers (MFL 70587 team 8 "Big Mac
// Attack" from the MFL fixtures; the dynasty roster 12 and League of Scrubs roster 3 — with the ESPN fixtures' overlay —
// from the clone) into web/fixtures/ih2/api_ih2.json. Re-record:
//   cd api && IH2_RECORD=1 PYTHONPATH=. uv run pytest -q tests/test_ih2.py -k record
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { DYNASTY, SCRUBS, serveFixtures } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "ih2", "api_ih2.json");
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};
const KEY = "mfl:70587";
const Q = `league=${encodeURIComponent(KEY)}&team=8`;

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

const shot = (name: string, project: string) => join(process.env.SHOTS_DIR ?? "e2e/.out", `ih2-${name}-${project}.png`);

async function pickBigMac(page: Page) {
  await page.goto("/leagues"); // IN-1: "/" without a league is the home page now; the setup screen is /leagues
  await expect(page.getByTestId("leagues")).toBeVisible();
  await page.getByTestId("platform-mfl").click(); // ---- II-5 (Wave I-I): the fantasy platform first
  await page.getByTestId("mfl-link").fill("70587");
  await page.getByTestId("mfl-go").click();
  await page.getByTestId("mfl-team").filter({ hasText: "Big Mac Attack" }).click();
}

test("dad's league: the Team page says when MFL's roster was read, under the roster", async ({ page, isMobile }, info) => {
  await pickBigMac(page);
  await page.goto(`/team?${Q}`);
  const team = page.getByTestId("team");
  await expect(team.getByTestId("team-answer")).toBeVisible();
  const line = team.getByTestId("team-mfl-updated");
  await expect(line).toBeVisible();
  await expect(line.locator("summary")).toHaveText(/^MFL rosters updated \d{1,2}:\d\d (AM|PM) ET\s*›$/);
  await expect(team.getByTestId("team-mfl-updated-exact")).toBeHidden();
  if (isMobile) await line.locator("summary").tap();
  else await line.locator("summary").click();
  await expect(team.getByTestId("team-mfl-updated-exact")).toContainText("This roster was read from MyFantasyLeague");
  await expect(team.getByTestId("team-mfl-updated-exact")).toContainText(" ET (");
  // right under the roster card
  const roster = await team.getByTestId("team-roster").boundingBox();
  const box = await line.boundingBox();
  expect(roster && box && box.y >= roster.y + roster.height - 1).toBeTruthy();
  await noSidewaysScroll(page);
  await page.screenshot({ path: shot("team-mfl", info.project.name), fullPage: true });
});

test("a Sleeper league's Team page has no MFL line", async ({ page }) => {
  await page.goto(`/team?league=${SCRUBS}&team=6`);
  await expect(page.getByTestId("team-answer")).toBeVisible();
  await expect(page.getByTestId("team-mfl-updated")).toHaveCount(0);
});

test("the dynasty: Waivers says which days daily claims run", async ({ page }, info) => {
  await page.goto(`/waivers?league=${DYNASTY}&team=12`);
  const line = page.getByTestId("waiver-deadline");
  await expect(line).toHaveText(/^Claims run every day except Saturday at 5:00 AM ET \(FAAB blind bids\)(; players lock at their own kickoff — the next game starts .+ ET)?\.$/);
  await expect(line.locator("time")).toHaveAttribute("datetime", /^\d{4}-\d\d-\d\dT09:00:00\+00:00$/);
  await noSidewaysScroll(page);
  await page.getByTestId("waivers").screenshot({ path: shot("waivers-dynasty", info.project.name) });
});

test("League of Scrubs roster 3: What changed shows the Questionable starter once", async ({ page }, info) => {
  await page.goto(`/?league=${SCRUBS}&team=3`);
  const wc = page.getByTestId("what-changed");
  await expect(wc).toBeVisible();
  const q = wc.getByTestId("changed-line").filter({ hasText: "Questionable:" });
  await expect(q).toHaveCount(1);
  await expect(q).toContainText("Questionable: Flowers (hamstring) — your lineup is unchanged");
  await expect(q).toHaveAttribute("data-kind", "status");
  await expect(q).toContainText("Injury report (ESPN)");
  await noSidewaysScroll(page);
  await wc.screenshot({ path: shot("what-changed", info.project.name) });
});
