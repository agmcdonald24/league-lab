// Wave I-Q (IQ-2), Wave I-W (IW-1): who starts, decided by the data (sq1.0; no hand list). Browsing (`ref:half`), week
// 5: the quarterback the data rule starts against the listing (Seattle → Sam Darnold) carries the chip "Who starts" and
// one sentence ("Seattle: we project Sam Darnold to start — …; the schedule lists Drew Lock."), keeps his tier and is
// never "Starter unclear"; Drew Lock's row says the same; Chicago (round 3, S7: a listing neither the depth chart nor
// the last game names is dropped) → Caleb Williams, the sentence on his row and on Case Keenum's ("the depth chart lists
// him first; the schedule still lists Case Keenum; Tyson Bagent took the snaps in week 4"); "Who should I start?" gives
// Darnold a call and his chance like anyone else.
// Recorded again on IW-1's copy (league_lab_iq4, the data rule in force). Phone at 375, desktop at 1300;
// screenshots (JPEG q70) into docs/handbacks/iq2/ (SHOTS_IQ2) or e2e/.out.
//
// Two modes, as e2e/ip2. Default: the rankings', the start answer's and Compare's answers come from
// web/fixtures/iq2/api_iq2.json (recorded from the fixture API at week 5 on IQ-2's database, trimmed to the fields the
// screens read), the rest from serveFixtures. IQ2_LIVE=http://localhost:8925 (the fixture API serving web/dist with
// LEAGUE_LAB_NOW=2026-10-07T23:00:00Z): the same walk against the real server, recording those answers. No outside
// host is reached in either mode (headshots and analytics are aborted).
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const LIVE = process.env.IQ2_LIVE ?? "";
const DIR = join(import.meta.dirname, "..", "..", "fixtures", "iq2");
const RECORDED = join(DIR, "api_iq2.json");
const SHOTS = process.env.SHOTS_IQ2 ?? join(import.meta.dirname, "..", ".out");
type Recorded = Record<string, { status: number; body: unknown }>;
type RankBody = { rows: Record<string, unknown>[] };
const DARNOLD = "00-0034869";
const WILLIAMS = "00-0039918", KEENUM = "00-0028986";   // ---- IW-1 round 3: Chicago
const LOCK = "00-0035704";

if (LIVE) test.use({ baseURL: LIVE });

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return `${u.pathname}?${new URLSearchParams(q).toString()}`;
};
const mine = (u: URL) =>
  u.pathname === "/api/rankings" || u.pathname === "/api/rankings/start" || (u.pathname === "/api/compare" && /^ref:/i.test(u.searchParams.get("league") ?? ""));
const ROW_FIELDS = ["key", "gsis_id", "player_name", "position", "team", "rank", "tier", "tier_p", "proj_points", "p10", "p25", "p50", "p75", "p90",
  "opponent", "is_home", "kickoff_at", "game_state", "report_status", "matchup", "ros_games", "ros_points_per_game", "bye_weeks", "starter_unclear", "starter_corrected"];
const trim = (u: URL, body: unknown): unknown => {
  if (u.pathname !== "/api/rankings" || !body || typeof body !== "object") return body;
  const b = body as RankBody;
  return { ...b, rows: (b.rows ?? []).map((r) => Object.fromEntries(ROW_FIELDS.filter((k) => k in r).map((k) => [k, r[k]]))) };
};
const recorded: Recorded = existsSync(RECORDED) ? (JSON.parse(readFileSync(RECORDED, "utf8")) as Recorded) : {};

async function api(context: BrowserContext): Promise<void> {
  await context.route(/^https?:\/\/(?!localhost)/, (route) => route.abort()); // headshots, GA: never fetched by a test
  if (LIVE) {
    await context.route(/\/api\//, async (route) => {
      const u = new URL(route.request().url());
      try {
        const res = await route.fetch();
        if (mine(u) && route.request().method() === "GET") recorded[keyOf(u)] = { status: res.status(), body: trim(u, await res.json()) };
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

async function noSideways(page: Page, testid: string) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "no sideways page scroll").toBeLessThanOrEqual(iw + 1);
  const { mw, cw } = await page.evaluate((t) => {
    const m = document.querySelector(`[data-testid=${t}]`) as HTMLElement;
    return { mw: m.scrollWidth, cw: m.clientWidth };
  }, testid);
  expect(mw, "nothing wider than the screen's own box").toBeLessThanOrEqual(cw + 1);
}

const shot = (page: Page, name: string) => page.screenshot({ path: join(SHOTS, `${name}.jpg`), type: "jpeg", quality: 70, scale: "css" });

test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test.afterAll(() => {
  if (!LIVE) return;
  mkdirSync(DIR, { recursive: true });
  writeFileSync(RECORDED, JSON.stringify(recorded));
});

test("a corrected starter: the chip, one sentence, his tier; Lock's row says the same; never unclear", async ({ context, page }, info) => {
  await api(context);
  await page.goto("/rankings?league=ref:half&position=QB");
  const row = page.locator(`[data-testid=rankings-row][data-key="${DARNOLD}"]`);
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("rankings-answer")).toContainText(/quarterbacks ranked by week 5's projection in Half PPR scoring/);
  await expect(row).toHaveAttribute("data-corrected", "1");
  await expect(row).not.toHaveAttribute("data-unclear", "1");
  await expect(row).not.toHaveAttribute("data-tier", "");              // a tier like anyone else
  const phone = info.project.name.includes("phone");
  await expect(row.getByTestId(phone ? "rankings-corrected-chip-phone" : "rankings-corrected-chip")).toHaveText("Who starts");
  await expect(row.getByTestId(phone ? "rankings-corrected-chip" : "rankings-corrected-chip-phone")).toBeHidden();
  const words = row.getByTestId("rankings-corrected-words");
  await expect(words).toContainText(
    "Seattle: we project Sam Darnold to start — he led the team's dropbacks in week 4; the schedule lists Drew Lock.");
  await expect(words).not.toContainText(/by hand|corrected/i);
  await expect(words).not.toContainText(/No tier|wrong|unclear/i);
  const lock = page.locator(`[data-testid=rankings-row][data-key="${LOCK}"]`);
  await expect(lock).toHaveAttribute("data-corrected", "1");
  await expect(lock.getByTestId("rankings-corrected-words")).toContainText("the schedule lists Drew Lock");
  // Chicago (IW-1 round 3, S7): Caleb Williams, Questionable (available), first on the depth chart; the listing (Keenum)
  // is named by neither the depth chart nor week 4's snaps (Bagent): the same sentence on Williams' row and Keenum's
  const CHI_WORDS = "Chicago: we project Caleb Williams to start — the depth chart lists him first; the schedule still lists Case Keenum; Tyson Bagent took the snaps in week 4.";
  for (const g of [WILLIAMS, KEENUM]) {
    await expect(page.locator(`[data-testid=rankings-row][data-key="${g}"]`).getByTestId("rankings-corrected-words")).toContainText(CHI_WORDS);
  }
  for (const g of [DARNOLD, LOCK, WILLIAMS, KEENUM]) {
    await expect(page.locator(`[data-testid=rankings-row][data-key="${g}"][data-unclear]`)).toHaveCount(0);
  }
  // the projection reads the corrected starter: Darnold above Lock
  const keys = await page.getByTestId("rankings-row").evaluateAll((els) => els.map((e) => e.getAttribute("data-key")));
  expect(keys.indexOf(DARNOLD)).toBeLessThan(keys.indexOf(LOCK));
  await noSideways(page, "rankings");
  if (!phone) {
    const box = await page.getByTestId("rankings-rows").boundingBox();
    expect(box!.width, "the list uses the width").toBeGreaterThan(1000);
  }
  await row.scrollIntoViewIfNeeded();
  await shot(page, `iq2-rankings-${info.project.name}`);
});

test("Who should I start? with a corrected quarterback: a call and his chance, and the sentence", async ({ context, page }, info) => {
  await api(context);
  await page.goto("/rankings?league=ref:half&position=QB");
  const row = page.locator(`[data-testid=rankings-row][data-key="${DARNOLD}"]`);
  await expect(row).toBeVisible({ timeout: 30_000 });
  await row.getByTestId("rankings-pick").click();
  await page.locator("[data-testid=rankings-row]:not([data-unclear]):not([data-corrected])").first().getByTestId("rankings-pick").click();
  await page.getByTestId("rankings-compare").click();
  const words = page.getByTestId("compare-start-words");
  await expect(words).toBeVisible({ timeout: 30_000 });
  await expect(words).not.toHaveAttribute("data-verdict", "no call");
  await expect(page.getByTestId("compare-start-pct")).toHaveCount(2);
  await expect(page.getByTestId("compare-start-nocall")).toHaveCount(0);
  await expect(page.getByTestId("compare-start-corrected")).toHaveText(
    "Seattle: we project Sam Darnold to start — he led the team's dropbacks in week 4; the schedule lists Drew Lock.");
  await noSideways(page, "compare");
  await shot(page, `iq2-start-${info.project.name}`);
});
