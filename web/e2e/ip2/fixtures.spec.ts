// Wave I-P (IP-2): rankings for everyone and "Who should I start?". Browsing (`ref:half`): the Rankings tab, the week's
// receivers ranked with tiers drawn as lines, the range bar, the defense's matchup chip (never a corner), a search;
// pick two rows → Compare opens on the answer in words ("… outscores … in N of 100 such weeks"). With a league: Rankings
// is a sub-tab under Players and the rows say who has him. Phone at 375 and desktop at 1300; screenshots (JPEG) into
// docs/handbacks/ip2/ (SHOTS_IP2) or e2e/.out.
//
// Two modes, as e2e/in3. Default: the rankings', the start answer's and Compare's (browsing) answers come from
// web/fixtures/ip2/api_ip2.json (recorded from the fixture API, trimmed to the fields the screens read), the rest from
// serveFixtures. IP2_LIVE=http://localhost:8962 (the fixture API serving web/dist): the same walk against the real
// server, recording those answers.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { SCRUBS, serveFixtures } from "../fixtures";

const LIVE = process.env.IP2_LIVE ?? "";
const DIR = join(import.meta.dirname, "..", "..", "fixtures", "ip2");
const RECORDED = join(DIR, "api_ip2.json");
const SHOTS = process.env.SHOTS_IP2 ?? join(import.meta.dirname, "..", ".out");
type Recorded = Record<string, { status: number; body: unknown }>;
type Row = Record<string, unknown> & { player_name: string };
type RankBody = { rows: Row[]; total: number; q: string | null };

if (LIVE) test.use({ baseURL: LIVE });

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return `${u.pathname}?${new URLSearchParams(q).toString()}`;
};
const mine = (u: URL) =>
  u.pathname === "/api/rankings" || u.pathname === "/api/rankings/start" || (u.pathname === "/api/compare" && /^ref:/i.test(u.searchParams.get("league") ?? ""));
// the fields the rankings screen reads (the recording keeps nothing else)
const ROW_FIELDS = ["key", "gsis_id", "player_name", "position", "team", "rank", "tier", "proj_points", "p10", "p90", "opponent", "is_home", "kickoff_at", "game_state",
  "report_status", "matchup", "rostered_by_roster_id", "rostered_by_team", "ros_games", "ros_points_per_game", "starter_unclear"];
const trim = (u: URL, body: unknown): unknown => {
  if (u.pathname !== "/api/rankings" || !body || typeof body !== "object") return body;
  const b = body as RankBody;
  return { ...b, rows: (b.rows ?? []).map((r) => Object.fromEntries(ROW_FIELDS.filter((k) => k in r).map((k) => [k, r[k]]))) };
};
const recorded: Recorded = existsSync(RECORDED) ? (JSON.parse(readFileSync(RECORDED, "utf8")) as Recorded) : {};
// ---- fix round: the flagged quarterbacks (a fake starters.unclear with IP-1's interface: Seattle lists Drew Lock, Sam
// Darnold took the dropbacks; Chicago the same), recorded from the API with the fake in place (fixture mode only)
const UNCLEAR = join(DIR, "api_ip2_unclear.json");
const unclear: Recorded = existsSync(UNCLEAR) ? (JSON.parse(readFileSync(UNCLEAR, "utf8")) as Recorded) : {};
const LOCK = "00-0035704";

async function api(context: BrowserContext): Promise<string[]> {
  const calls: string[] = [];
  await context.route(/^https?:\/\/(?!localhost)/, (route) => route.abort()); // headshots, GA: never fetched by a test
  if (LIVE) {
    await context.route(/\/api\//, async (route) => {
      const u = new URL(route.request().url());
      calls.push(u.pathname + u.search);
      try {
        const res = await route.fetch();
        if (mine(u) && route.request().method() === "GET") recorded[keyOf(u)] = { status: res.status(), body: trim(u, await res.json()) };
        await route.fulfill({ response: res });
      } catch {
        /* the page closed with the request in flight */
      }
    });
    return calls;
  }
  await serveFixtures(context);
  await context.route(/\/api\//, async (route) => {
    const u = new URL(route.request().url());
    calls.push(u.pathname + u.search);
    if (!mine(u)) return route.fallback();
    let hit = recorded[keyOf(u)];
    const q = u.searchParams.get("q");
    if (!hit && q && u.pathname === "/api/rankings") {
      // a search that was not recorded: the recorded first page of the same list, filtered by name (as the server does)
      const base = new URL(u.toString());
      base.searchParams.delete("q");
      const all = recorded[keyOf(base)];
      if (all) {
        const body = all.body as RankBody;
        const rows = body.rows.filter((r) => r.player_name.toLowerCase().includes(q.toLowerCase()));
        hit = { status: 200, body: { ...body, q, rows, total: rows.length } };
      }
    }
    if (!hit) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: `not recorded: ${keyOf(u)}` }) });
    return route.fulfill({ status: hit.status, contentType: "application/json", body: JSON.stringify(hit.body) });
  });
  return calls;
}

async function noSideways(page: Page, testid: string) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "no sideways page scroll").toBeLessThanOrEqual(iw + 1);
  const { mw, cw } = await page.evaluate((t) => {
    const m = document.querySelector(`[data-testid=${t}]`) as HTMLElement;
    return { mw: m.scrollWidth, cw: m.clientWidth };
  }, testid);
  expect(mw, "nothing wider than the screen's own box").toBeLessThanOrEqual(cw + 1);
}

const shot = (page: Page, name: string) => page.screenshot({ path: join(SHOTS, `${name}.jpg`), type: "jpeg", quality: 70, scale: "css" }); // rule 12: small JPEGs

test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test.afterAll(() => {
  if (!LIVE) return;
  mkdirSync(DIR, { recursive: true });
  writeFileSync(RECORDED, JSON.stringify(recorded));
});

test("browsing: the Rankings tab, tiers as lines, the range bar, the defense's chip, a search", async ({ context, page }, info) => {
  const calls = await api(context);
  await page.goto("/rankings?league=ref:half");
  // the tab while browsing: Home · Rankings · Players · Trades · DFS, Rankings lit
  await expect(page.getByTestId("tab-rankings")).toBeVisible();
  await expect(page.getByTestId("tab-rankings")).toHaveAttribute("aria-current", "page");
  await expect(page.getByTestId("tabs").locator("a")).toHaveText(["Home", "Rankings", "Players", "Trades", "DFS"]);
  const list = page.getByTestId("rankings");
  await expect(page.getByTestId("rankings-row").first()).toBeVisible({ timeout: 30_000 });
  expect(await page.getByTestId("rankings-row").count()).toBe(50);
  await expect(page.getByTestId("rankings-answer")).toContainText(/\d+ wide receivers ranked by week 4's projection in Half PPR scoring, in \d+ tiers/);
  await expect(page.getByTestId("rankings-tier-words")).toContainText("fewer than 55 weeks in 100");
  await expect(page.getByTestId("tier-break").first()).toHaveText(/Tier 1/);
  expect(await page.getByTestId("tier-break").count()).toBeGreaterThan(1);
  await expect(page.getByTestId("rankings-bar").first()).toHaveAttribute("aria-label", /range \d+–\d+, projected/);
  await expect(page.getByTestId("rankings-count")).toContainText(/Showing 1–50 of \d+ wide receivers/);
  await expect(page.getByTestId("rankings-honest")).toContainText("who plays cornerback is not");
  // the chip is the defense's tone; no corner anywhere, never "No league", nobody owns anyone
  await expect(list).not.toContainText(/No league/);
  await expect(page.getByTestId("rankings-rows")).not.toContainText(/corner|shutdown|Who has him|Free agent/i);
  await noSideways(page, "rankings");
  if (!info.project.name.includes("phone")) {
    const box = await page.getByTestId("rankings-rows").boundingBox();
    expect(box!.width, "the list uses the width").toBeGreaterThan(1000);
  }
  await shot(page, `ip2-rankings-${info.project.name}`);

  // a search: the server's q= (two letters at least), the rank stays the position's
  const asked = page.waitForResponse((r) => r.url().includes("/api/rankings?") && /[?&]q=Nacua/.test(r.url()));
  await page.getByTestId("rankings-search").fill("Nacua");
  expect((await asked).status()).toBe(200);
  await expect(page).toHaveURL(/q=Nacua/);
  await expect(page.getByTestId("rankings-row")).toHaveCount(1);
  await expect(page.getByTestId("rankings-name")).toHaveText("Puka Nacua");
  expect(calls.filter((c) => c.startsWith("/api/rankings?")).every((c) => !/team=/.test(c))).toBe(true);

  // the rest of the season: the rank, the projection and the range, no tier lines, the line that says why
  await page.getByTestId("rankings-search").fill("");
  await page.getByTestId("rankings-view-season").click();
  await expect(page).toHaveURL(/view=season/);
  await expect(page.getByTestId("rankings-head")).toContainText("Rest-of-season rankings");
  await expect(page.getByTestId("rankings-row").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("tier-break")).toHaveCount(0);
  await expect(page.getByTestId("rankings-tier-words")).toHaveText("No tiers for the rest of the season: the season ranges have not been graded yet.");
  await expect(page.getByTestId("rankings-answer")).not.toContainText("tier");
});

test("pick two → Compare answers who to start, as unsure as it is", async ({ context, page }, info) => {
  await api(context);
  await page.goto("/rankings?league=ref:half");
  await expect(page.getByTestId("rankings-row").first()).toBeVisible({ timeout: 30_000 });
  const picks = page.getByTestId("rankings-pick");
  await picks.nth(0).click();
  await expect(page.getByTestId("rankings-picks")).toContainText("pick one more");
  await expect(page.getByTestId("rankings-compare")).toHaveCount(0);
  await picks.nth(2).click();
  await expect(page).toHaveURL(/pick=00-\d{7}%2C00-\d{7}|pick=00-\d{7},00-\d{7}/);
  await expect(page.getByTestId("rankings-compare")).toContainText("Who should I start? Compare 2");
  await page.getByTestId("rankings-compare").click();
  await expect(page).toHaveURL(/\/compare\?.*a=00-\d{7}.*b=00-\d{7}/);
  const words = page.getByTestId("compare-start-words");
  await expect(words).toBeVisible({ timeout: 30_000 });
  await expect(words).toHaveText(/^(Start|Lean|A coin flip)[^:]*: .* in \d{1,2} of 100 such weeks — (a clear call, not a sure one|close; either is fine|either is fine)\.$/);
  await expect(page.getByTestId("compare-start-player")).toHaveCount(2);
  await expect(page.getByTestId("compare-start-floor")).toContainText("Read anything under 65 as a lean, not a verdict");
  // the answer is the first thing under the title: above the two pickers
  const answerBox = await page.getByTestId("compare-start").boundingBox();
  const pickersBox = await page.getByTestId("compare-pickers").boundingBox();
  expect(answerBox!.y).toBeLessThan(pickersBox!.y);
  await expect(page.getByTestId("compare")).not.toContainText(/No league|This league scoring/);
  await noSideways(page, "compare");
  await shot(page, `ip2-start-${info.project.name}`);
  // shareable: the same URL opened afresh gives the same sentence
  const said = await words.innerText();
  await page.goto(page.url());
  await expect(page.getByTestId("compare-start-words")).toHaveText(said, { timeout: 30_000 });
});

test("a league: Rankings under Players, who has him, the league's own scoring", async ({ context, page }, info) => {
  await api(context);
  await page.goto(`/rankings?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("tab-rankings")).toHaveCount(0);
  await expect(page.getByTestId("tab-players")).toHaveAttribute("aria-current", "page");
  await expect(page.getByTestId("rankings-row").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("rankings-answer")).toContainText("League of Scrubs scoring");
  await expect(page.getByTestId("rankings")).toContainText(/Who has him|Yours|Free agent/);
  await noSideways(page, "rankings");
  await shot(page, `ip2-league-${info.project.name}`);
});

test("a starter unclear: the chip, the dashed edge, no tier; Who should I start? gives no call", async ({ context, page }, info) => {
  test.skip(!!LIVE, "the fake starters.unclear is in the recording only");
  await api(context);
  await context.route(/\/api\/(rankings|compare)/, async (route) => {
    const hit = unclear[keyOf(new URL(route.request().url()))];
    if (!hit) return route.fallback();
    return route.fulfill({ status: hit.status, contentType: "application/json", body: JSON.stringify(hit.body) });
  });
  await page.goto("/rankings?league=ref:half&position=QB");
  const lock = page.locator(`[data-testid=rankings-row][data-key="${LOCK}"]`);
  await expect(lock).toBeVisible({ timeout: 30_000 });
  await expect(lock).toHaveAttribute("data-unclear", "1");
  await expect(lock).toHaveAttribute("data-tier", "");
  await expect(lock.getByTestId(info.project.name.includes("phone") ? "rankings-unclear-chip-phone" : "rankings-unclear-chip")).toHaveText("Starter unclear");
  await expect(lock.getByTestId("rankings-unclear-words")).toContainText("Seattle lists Drew Lock as the starter");
  await expect(lock.getByTestId("rankings-unclear-words")).toContainText("No tier.");
  // he keeps his place by projection: the rows around him are ranked one either side
  const ranks = await page.getByTestId("rankings-row").evaluateAll((els) => els.map((e) => e.getAttribute("data-key")));
  const i = ranks.indexOf(LOCK);
  expect(i).toBeGreaterThan(0);
  await expect(page.getByTestId("rankings-honest")).toContainText("Starter unclear (the dashed edge)");
  await noSideways(page, "rankings");
  await lock.scrollIntoViewIfNeeded();
  await shot(page, `ip2-unclear-${info.project.name}`);
  // pick him and a clear quarterback: the sentence first, no call, no chances
  await lock.getByTestId("rankings-pick").click();
  await page.locator("[data-testid=rankings-row]:not([data-unclear])").first().getByTestId("rankings-pick").click();
  await page.getByTestId("rankings-compare").click();
  const words = page.getByTestId("compare-start-words");
  await expect(words).toBeVisible({ timeout: 30_000 });
  await expect(words).toHaveAttribute("data-verdict", "no call");
  await expect(words).toHaveText(/^Seattle lists Drew Lock as the starter.* Starter unclear — no call\.$/);
  await expect(page.getByTestId("compare-start-pct")).toHaveCount(0);
  await expect(page.getByTestId("compare-start-nocall").first()).toBeVisible();
  await expect(page.getByTestId("compare-start-nocall-why")).toContainText("No chances are given");
  await noSideways(page, "compare");
});
