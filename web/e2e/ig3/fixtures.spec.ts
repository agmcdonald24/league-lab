// Wave I-G (IG-3): the small opens on fixtures — MFL's own roster-freshness line on My Week ("MFL rosters updated
// 4:05 AM ET ›", the exact time on tap), the waiver deadline under the Waivers title (dad's league: first come, first
// served on MFL; League of Scrubs: "Claims run Wednesday 3:00 AM ET (rolling waivers)"), and the MFL grade's
// qualification right under the headline grade on About. Phone at 375 (inside the phone project) and desktop at 1300.
//
// The answers are the API's own, recorded by api/tests/test_ig3.py::test_record_e2e_answers (MFL 70587 team 8 "Big Mac
// Attack" from the MFL fixtures; League of Scrubs roster 6 from the clone) into web/fixtures/ig3/api_ig3.json. Re-record:
//   cd api && IG3_RECORD=1 PYTHONPATH=. uv run pytest -q tests/test_ig3.py -k record
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures, SCRUBS } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "ig3", "api_ig3.json");
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

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `ig3-${name}-${project}.png`), fullPage: true });

async function pickBigMac(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("leagues")).toBeVisible();
  await page.getByTestId("platform-mfl").click(); // ---- II-5 (Wave I-I): the fantasy platform first
  await page.getByTestId("mfl-link").fill("70587");
  await page.getByTestId("mfl-go").click();
  await page.getByTestId("mfl-team").filter({ hasText: "Big Mac Attack" }).click();
  await expect(page.getByTestId("my-week")).toBeVisible();
}

test("dad's league: My Week says when MFL's rosters were read; Waivers says MFL is first come, first served", async ({ page, isMobile }, info) => {
  await pickBigMac(page);
  const mfl = page.getByTestId("mfl-updated");
  await expect(mfl).toBeVisible();
  await expect(mfl.locator("summary")).toHaveText(/^MFL rosters updated \d{1,2}:\d\d (AM|PM) ET\s*›$/);
  await expect(page.getByTestId("mfl-updated-exact")).toBeHidden();
  if (isMobile) await mfl.locator("summary").tap();
  else await mfl.locator("summary").click();
  await expect(page.getByTestId("mfl-updated-exact")).toContainText("Rosters and lineups read from MyFantasyLeague");
  await expect(page.getByTestId("mfl-updated-exact")).toContainText(" ET (");
  await noSidewaysScroll(page);
  await shot(page, "myweek-mfl", info.project.name);

  await page.goto(`/waivers?${Q}`);
  const line = page.getByTestId("waiver-deadline");
  await expect(line).toHaveText(
    /^Free agents are first come, first served on MFL: a claim is yours as soon as MFL takes it(; players lock at their own kickoff — the next game starts \w+ \d{1,2}:\d\d (AM|PM) ET)?\.$/,
  );
  // one line under the title, above the cards
  const head = await page.getByTestId("waiver-lineup").boundingBox();
  const box = await line.boundingBox();
  expect(box && head && box.y > head.y).toBeTruthy();
  await noSidewaysScroll(page);
  await shot(page, "waivers-mfl", info.project.name);
});

test("League of Scrubs: Waivers says when claims run (Wednesday 3:00 AM ET, rolling waivers)", async ({ page }, info) => {
  await page.goto(`/waivers?league=${SCRUBS}&team=6`);
  const line = page.getByTestId("waiver-deadline");
  await expect(line).toHaveText(/^Claims run Wednesday 3:00 AM ET \(rolling waivers\)(; players lock at their own kickoff — the next game starts .+ ET)?\.$/);
  await expect(line.locator("time")).toHaveAttribute("datetime", /^\d{4}-\d\d-\d\dT07:00:00\+00:00$/);
  await noSidewaysScroll(page);
  await page.getByTestId("waivers").screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `ig3-waivers-scrubs-${info.project.name}.png`) });
});

test("About, dad's league: the grades' qualification sits right under the headline grade", async ({ page }, info) => {
  await pickBigMac(page);
  await page.goto(`/about?${Q}`);
  const grades = page.getByTestId("grades");
  await expect(grades.getByTestId("grades-answer")).toBeVisible();
  const q = grades.getByTestId("grades-qualification");
  await expect(q).toContainText("no direct projection record for this MyFantasyLeague league");
  // next to the headline grade: below the answer, above the first grade card
  const a = await grades.getByTestId("grades-answer").boundingBox();
  const b = await q.boundingBox();
  const c = await grades.getByTestId("grade-card").first().boundingBox();
  expect(a && b && c && a.y < b.y && b.y < c.y).toBeTruthy();
  await noSidewaysScroll(page);
  await grades.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `ig3-about-mfl-${info.project.name}.png`) });
});
