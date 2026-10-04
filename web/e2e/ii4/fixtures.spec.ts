// Wave I-I (II-4): the copy standard, the three Season views, news as a decision-impact feed, the presentation (the
// product and analytics review § 5–8). Phone at 375 px (inside the phone project) and desktop at 1300.
//
// The answers are the API's own, recorded by api/tests/test_ii4.py::test_record_e2e_answers (League of Scrubs roster 2,
// MacZaddy — the review's team — with the ESPN fixture overlay: Jefferson Out since the build, his RotoWire news; the
// three Season views; Waivers) into web/fixtures/ii4/api_ii4.json. Re-record:
//   cd api && II4_RECORD=1 PYTHONPATH=. uv run pytest -q tests/test_ii4.py -k record_e2e
import { expect, test, type Locator, type Page, type Route } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { serveDecisions } from "../decisions-fixtures";
import { DYNASTY, serveFixtures, SCRUBS } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "ii4", "api_ii4.json");
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};
type Row = { player_name: string; lineup_kind?: string; lineup_points?: number; acquire?: { kind: string; path: string } | null };
type Ros = { players: Row[]; season_view?: { counterfactual: string } };
const body = <T,>(k: string) => saved[k]?.body as T;

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return u.pathname + (q.length ? `?${new URLSearchParams(q).toString()}` : "");
};

async function answer(route: Route) {
  const u = new URL(route.request().url());
  let k = keyOf(u);
  // the projections view asks the plain rest-of-season path (lib/ros.ts seasonPath): the recorded projections answer
  if (u.pathname === "/api/ros" && !u.searchParams.get("view") && u.searchParams.get("league") === SCRUBS) {
    const pos = u.searchParams.get("position") ?? "ALL";
    k = `/api/ros?league=${SCRUBS}&limit=50&position=${pos}&team=2&view=projections`;
  }
  const s = saved[k];
  if (!s) return route.fallback();
  return route.fulfill({ status: s.status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(s.body) });
}

test.beforeEach(async ({ context, page }, info) => {
  test.skip(!existsSync(FILE), "no recording yet (see the header)");
  await serveFixtures(context);
  await serveDecisions(context); // Team / League / Waivers' saved answers (e2e/decisions-fixtures.ts)
  await context.route(/\/api\//, answer);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const [sw, iw] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

async function tap(page: Page, loc: Locator, isMobile: boolean) {
  if (isMobile) await loc.tap();
  else await loc.click();
}

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `ii4-${name}-${project}.png`), fullPage: true });

test("Season: three named views, each with its counterfactual; upgrades before acquisition cost lead to Waivers or a trade", async ({ page, isMobile }, info) => {
  const outlook = body<Ros>(`/api/ros?league=${SCRUBS}&limit=50&position=ALL&team=2&view=outlook`);
  const upgrades = body<Ros>(`/api/ros?league=${SCRUBS}&limit=50&position=ALL&team=2&view=upgrades`);
  await page.goto(`/ros?league=${SCRUBS}&team=2`);
  // 1. My roster outlook (the default): your players only, what your lineup loses without each one
  await expect(page.getByTestId("ros-title")).toHaveText("My roster outlook");
  await expect(page.getByTestId("ros-view-outlook")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("ros-view-outlook")).toHaveText(isMobile ? "My roster" : "My roster outlook");
  await expect(page.getByTestId("ros-counterfactual")).toContainText("Your players only. Each number is what your best lineup loses over the weeks left without him");
  await expect(page.getByTestId("ros-counterfactual")).toContainText("his injury cover is shown apart and is not added in");
  await expect(page.getByTestId("ros-row")).toHaveCount(outlook.players.length);
  await expect(page.getByTestId("ros-who")).toHaveCount(0); // yours only: no "whose" chips
  await expect(page.getByTestId("ros-lineup-answer")).toContainText(`Your most important player over weeks 4–16: ${outlook.players[0].player_name}`);
  await noSidewaysScroll(page);
  await shot(page, "outlook", info.project.name);
  // 2. Potential upgrades: before acquisition cost, the costs left out said, each row's next step
  await tap(page, page.getByTestId("ros-view-upgrades"), isMobile);
  await expect(page).toHaveURL(/view=upgrades/);
  await expect(page.getByTestId("ros-title")).toHaveText("Potential upgrades");
  await expect(page.getByTestId("ros-counterfactual")).toContainText("Before acquisition cost");
  await expect(page.getByTestId("ros-counterfactual")).toContainText("This is not his trade value.");
  await expect(page.getByTestId("ros-costs")).toHaveText("Not included: the drop a free agent needs, the players a trade sends, a waiver claim that might be lost.");
  await expect(page.getByTestId("ros-lineup-answer")).toContainText(`The biggest potential upgrade over weeks 4–16, before acquisition cost: ${upgrades.players[0].player_name}`);
  const first = page.getByTestId("ros-acquire").first();
  await expect(first).toHaveAttribute("data-kind", upgrades.players[0].acquire!.kind);
  await expect(first).toHaveAttribute("href", new RegExp(upgrades.players[0].acquire!.path.replace(/[?]/g, "\\?")));
  await expect(page.getByTestId("ros-row").filter({ hasText: "yours" })).toHaveCount(0);
  // free agents only: the add / drop path
  await tap(page, page.getByTestId("ros-who-fa"), isMobile);
  await expect(page).toHaveURL(/who=fa/);
  await expect(page.getByTestId("ros-acquire").first()).toHaveAttribute("data-kind", "add_drop");
  await expect(page.getByTestId("ros-acquire").first()).toHaveAttribute("href", /\/waivers\?add=/);
  await noSidewaysScroll(page);
  await shot(page, "upgrades", info.project.name);
  // 3. Rest-of-season projections: no roster, no lineup, no cost; per game from 640 px
  await tap(page, page.getByTestId("ros-view-projections"), isMobile);
  await expect(page.getByTestId("ros-title")).toHaveText("Rest-of-season projections");
  await expect(page.getByTestId("ros-counterfactual")).toContainText("no roster, no lineup and no cost considered");
  await expect(page.getByTestId("ros-lineup-why")).toHaveCount(0);
  if (!isMobile) await expect(page.getByTestId("ros-per-game").first()).toHaveText(/^\d+\.\d$/);
  await noSidewaysScroll(page);
  await shot(page, "projections", info.project.name);
});

test("My Week: decisions, then What changed as decision items (status, forecast, why here, next step), then the lineup's status; three clocks", async ({ page }, info) => {
  await page.goto(`/?league=${SCRUBS}&team=2`);
  const box = page.getByTestId("what-changed");
  await expect(box).toBeVisible();
  // the order: the actions first, What changed second, the lineup's status (the set line / where to change) after
  const order = await page.evaluate(() =>
    ["week-actions", "what-changed", "where-to-change"].map((id) => document.querySelector(`[data-testid="${id}"]`)?.getBoundingClientRect().top ?? -1),
  );
  expect(order[1]).toBeGreaterThan(order[0]);
  expect(order[2]).toBeGreaterThan(order[1]);
  const lines = box.getByTestId("changed-line");
  const st = lines.first();
  await expect(st).toHaveAttribute("data-kind", "status");
  await expect(st).toHaveAttribute("data-decision", "changed");
  await expect(st).toHaveAttribute("data-forecast", "included");
  await expect(st.getByTestId("changed-decision")).toContainText("Recommendation changed");
  await expect(st).toContainText("Justin Jefferson is out (ankle)");
  await expect(st.getByTestId("changed-forecast")).toHaveText("Included in the current projection: the injury report's status is applied to this week");
  await expect(st.getByTestId("changed-why")).toHaveText("In the lineup you submitted, and he cannot play this week");
  await expect(st.getByTestId("changed-next")).toHaveText("Compare your options for the slot ›");
  // the RotoWire item on the same ankle: reflected by the recorded status, not counted twice, no action
  const nw = box.locator('[data-testid="changed-line"][data-kind="news"]').first();
  await expect(nw).toHaveAttribute("data-decision", "none");
  await expect(nw).toHaveAttribute("data-forecast", "included");
  await expect(nw.getByTestId("changed-decision")).toHaveText("No action currently indicated");
  await expect(nw).toContainText("Justin Jefferson:");
  await expect(nw.getByTestId("changed-next")).toHaveText("Inspect Jefferson ›");
  // a long item behind More (the source detail one tap away)
  await expect(nw.getByTestId("changed-more")).toHaveCount(1);
  // the clocks: data built · injuries checked · news — stamps, no stale warning
  const foot = page.getByTestId("updated");
  await expect(foot.locator("summary")).toContainText("Data built");
  await expect(foot.getByTestId("clock-injuries")).toContainText(/Injuries checked .*\d:\d\d [AP]M ET/);
  await expect(foot.getByTestId("clock-news")).toContainText("News");
  await expect(page.getByTestId("stale-warning")).toHaveCount(0);
  await expect(page.getByTestId("stale-banner")).toHaveCount(0);
  await noSidewaysScroll(page);
  await box.scrollIntoViewIfNeeded();
  await shot(page, "home-feed", info.project.name);
});

test("Waivers: each top claim says when it helps; the claims competing for one roster spot are named", async ({ page }, info) => {
  await page.goto(`/waivers?league=${SCRUBS}&team=2`);
  const top = page.getByTestId("top3");
  await expect(top).toBeVisible();
  const hz = top.getByTestId("top-move-horizon");
  await expect(hz).toHaveCount(3);
  await expect(hz.nth(0)).toHaveText("Helps this week (+8.3)");
  await expect(hz.nth(2)).toHaveText("Covers a bye in week 7");
  await expect(hz.nth(2)).toHaveAttribute("data-horizon", "bye");
  // the intro is honest about the horizon (the review: not "each with what it adds this week")
  await expect(page.getByTestId("waiver-answer")).toContainText("The three strongest claims below: 2 help this week, 1 covers a bye (week 7). Each card's total is its gain over weeks 4–7.");
  await expect(page.getByTestId("waiver-answer")).not.toContainText("each with what it adds this week");
  await expect(top.getByTestId("top-compete")).toContainText("compete for the same roster spot (each drops Jacory Croskey-Merritt): claim one of them.");
  await noSidewaysScroll(page);
  await shot(page, "waivers-top", info.project.name);
});

test("Team, League: depth defined, hindsight labelled, no promise that luck evens out", async ({ page }) => {
  await page.goto(`/team?league=${DYNASTY}&team=12`); // the saved Team answers are the dynasty's
  await expect(page.getByTestId("team-tiles")).toContainText("Depth (bench lineup)");
  await expect(page.getByTestId("team-tiles")).toContainText("best legal lineup from the bench");
  await noSidewaysScroll(page);
  await page.goto(`/league?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("luck")).toContainText("Past luck says nothing about the weeks left");
  await expect(page.locator("body")).not.toContainText("It evens out over a season");
  await expect(page.getByTestId("bench")).toContainText("Points left on the bench (hindsight)");
  await noSidewaysScroll(page);
});
