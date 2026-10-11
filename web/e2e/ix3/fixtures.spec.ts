// Wave I-X (IX-3): Stats — a table that opens on an answer. The first view is Key stats (at most eight columns) on
// every width; the named views (Production, Opportunity, Role changes, Efficiency, Advanced), each with its question;
// the Full table one tap away; the view remembered per position (IM-2's one key carried over once); the situation
// filter (All plays · When trailing · Within a score · When leading: IX-2's groups) with a dash and its reason for a
// column it cannot split; no internal name on screen; "Filter this table"; a card opened from the table and closed
// keeps the position, view, filter, sort and scroll. Phone at 375 and desktop at 1300; screenshots (IX3_SHOTS).
//
// Recordings: web/fixtures/ix3/api_ix3.json (the API on the shared database, 2026 weeks 1–4; re-record with
// web/fixtures/save_ix3_fixtures.py).
import { expect, test, type BrowserContext, type Locator, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures, SCRUBS } from "../fixtures";

const DIR = join(import.meta.dirname, "..", "..", "fixtures", "ix3");
type Row = Record<string, unknown> & { gsis_id: string; player_name: string; position: string; games: number };
type Frame = { players: Row[]; views: Record<string, { key: string; label: string; question: string; columns: string[] }[]>; situation: { columns: string[]; reason: string } | null };
const saved: Record<string, { status: number; body: Frame }> = JSON.parse(readFileSync(join(DIR, "api_ix3.json"), "utf8"));
const keyOf = (q: Record<string, string>) => `/api/players?${new URLSearchParams(Object.entries(q).sort(([a], [b]) => a.localeCompare(b))).toString()}`;
const BASE = { league: SCRUBS, limit: "1000", window: "season" };
const TRAIL = saved[keyOf({ ...BASE, position: "WR,TE", situation: "trailing" })].body;
const WRTE = saved[keyOf({ ...BASE, position: "WR,TE" })].body;
const JJ = { gsis: "00-0036322", name: "Justin Jefferson" }; // a WR with a saved player card, 41st by targets when trailing
const url = (extra = "") => `/players?league=${SCRUBS}&team=2${extra}`;
const SHOTS = process.env.IX3_SHOTS ?? "e2e/.out";
const INTERNAL = /\b(fct|mart|dim|bridge|int|stg)_[a-z_]+|league_lab\.|analytics\.|routes_feed|_proxy\b/;

async function serve(context: BrowserContext) {
  const api = await serveFixtures(context);
  await context.route(/\/api\/players\?/, (route) => {
    const u = new URL(route.request().url());
    api.calls.push(u.pathname + u.search);
    const hit = saved[keyOf(Object.fromEntries(u.searchParams))];
    if (!hit) return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(hit.body) });
  });
  return api;
}

test.beforeEach(async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function tap(page: Page, el: Locator, isMobile: boolean) {
  await el.evaluate((n) => n.scrollIntoView({ block: "center", inline: "nearest" }));
  if (isMobile) await el.tap();
  else await el.click();
}
async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}
const table = (page: Page) => page.getByTestId("players-table");
/** IX-3 round 2: under 900 px the filters fold behind one button — open it before a folded control (no-op on a desktop). */
async function openFilters(page: Page) {
  const t = page.getByTestId("stats-filters-toggle");
  if ((await t.isVisible()) && (await t.getAttribute("aria-expanded")) !== "true") await t.click();
}
const rows = (page: Page) => table(page).getByTestId("players-table-row");
const colHeads = (page: Page) => table(page).locator('thead th[scope=col]:has([data-testid^="sort-"])');

test("a first visit opens on Key stats (at most eight columns) on every width; each named view says its question; the Full table one tap away", async ({ page, context, isMobile }) => {
  await serve(context);
  await page.goto(url("&position=WRTE"));
  await expect(rows(page).first()).toBeVisible();
  await expect(page.getByTestId("stats-table-view-key")).toHaveAttribute("aria-pressed", "true");
  await expect(table(page)).toHaveAttribute("data-view", "key");
  const n = await colHeads(page).count();
  expect(n).toBeLessThanOrEqual(8);
  expect(n).toBe(WRTE.views.wrte.find((v) => v.key === "key")!.columns.length);
  await expect(page.getByTestId("stats-view-question")).toContainText("Key stats:");
  for (const label of ["Production", "Opportunity", "Role changes", "Efficiency", "Advanced", "Full table"]) {
    await expect(page.getByTestId("stats-table-view").getByRole("button", { name: label, exact: true })).toBeVisible();
  }
  // Opportunity: its question, IX-1's on-field share among its columns
  await tap(page, page.getByTestId("stats-table-view-opportunity"), isMobile);
  await expect(page).toHaveURL(/[?&]view=opportunity/);
  await expect(page.getByTestId("stats-view-question")).toContainText("How much of his team's offence comes his way?");
  await expect(page.getByTestId("sort-on_field_target_share")).toHaveCount(1);
  expect(await colHeads(page).count()).toBeLessThanOrEqual(8);
  for (const v of WRTE.views.wrte) expect(v.columns.length, v.key).toBeLessThanOrEqual(8);
  // the Full table, one tap
  await tap(page, page.getByTestId("stats-table-view-full"), isMobile);
  await expect(table(page)).toHaveAttribute("data-view", "full");
  expect(await colHeads(page).count()).toBeGreaterThan(25);
  // the group of snap columns is "Snaps" in a season with no route column (2026)
  const names = await page.getByTestId("stats-group-head").evaluateAll((ths) => ths.map((th) => th.getAttribute("data-group")!));
  expect(names).toContain("Snaps");
  expect(names).not.toContain("Snaps and routes");
  // no internal name anywhere on the screen (the definitions under How to read this included)
  await page.getByTestId("howto").locator("summary, button").first().click();
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(INTERNAL);
  // the table's own box says what it does
  await expect(page.getByTestId("players-search")).toHaveAttribute("placeholder", "Filter this table by name");
  await noSidewaysScroll(page);
});

test("the view is remembered per position; IM-2's one key is carried over once", async ({ page, context, isMobile }) => {
  await serve(context);
  await page.goto(url("&position=RB"));
  await expect(rows(page).first()).toBeVisible();
  await expect(table(page)).toHaveAttribute("data-view", "key");
  await tap(page, page.getByTestId("stats-table-view-full"), isMobile);
  await expect(table(page)).toHaveAttribute("data-view", "full");
  // a full RB table does not force a full WR / TE table
  await tap(page, page.getByTestId("pos-WRTE"), isMobile);
  await expect(page).not.toHaveURL(/[?&]view=/);
  await expect(table(page)).toHaveAttribute("data-view", "key");
  await tap(page, page.getByTestId("stats-table-view-efficiency"), isMobile);
  await expect(page.getByTestId("stats-table-view-efficiency")).toHaveAttribute("aria-pressed", "true");
  await page.goto(url("&position=RB"));
  await expect(table(page)).toHaveAttribute("data-view", "full");
  await page.goto(url("&position=WRTE"));
  await expect(page.getByTestId("stats-table-view-efficiency")).toHaveAttribute("aria-pressed", "true");
  // IM-2's single key (a desktop that picked the Full table once): carried over to every position, then gone
  await page.evaluate(() => {
    localStorage.removeItem("ll.stats.tables");
    localStorage.setItem("ll.stats.table", "full");
  });
  await page.goto(url("&position=WRTE"));
  await expect(table(page)).toHaveAttribute("data-view", "full");
  expect(await page.evaluate(() => localStorage.getItem("ll.stats.table"))).toBeNull();
  expect(JSON.parse((await page.evaluate(() => localStorage.getItem("ll.stats.tables"))) ?? "{}")).toMatchObject({ wrte: "full", rb: "full", qb: "full", all: "full" });
});

test("When trailing: the split columns carry his plays' numbers; a column it cannot split is a dash with the reason; a share on under 20 plays is too few to read", async ({ page, context, isMobile }, info) => {
  const api = await serve(context);
  await page.goto(url("&position=WRTE&sort=targets&dir=desc"));
  await expect(rows(page).first()).toBeVisible();
  await openFilters(page);
  await tap(page, page.getByTestId("sit-trailing"), isMobile);
  await expect(page).toHaveURL(/[?&]sit=trailing/);
  await expect.poll(() => api.calls.some((c) => c.includes("situation=trailing"))).toBe(true);
  await expect(page.getByTestId("stats-situation-note")).toContainText("When trailing");
  await expect(page.getByTestId("stats-situation-note")).toContainText("his team behind by 9 or more");
  // the leader by targets when trailing is the recording's
  const lead = [...TRAIL.players]
    .filter((p) => typeof p.targets_per_game === "number")
    .sort((a, b) => (b.targets_per_game as number) - (a.targets_per_game as number) || a.player_name.localeCompare(b.player_name))[0];
  await expect(rows(page).first()).toContainText(lead.player_name);
  // points cannot be split: a dash with the reason, never the all-plays number
  const pts = rows(page).first().locator('[data-col="points"]');
  await expect(pts).toHaveText("—");
  await expect(pts).toHaveAttribute("title", /Not split by game situation/);
  // a share on fewer than 20 of his team's plays: a dash, "Too few to read"
  const few = TRAIL.players.find((p) => typeof p.situation_plays === "number" && (p.situation_plays as number) > 0 && (p.situation_plays as number) < 20 && (p.targets as number) > 0);
  if (few) {
    await openFilters(page);
    await page.getByTestId("players-search").fill(few.player_name.split(" ").slice(-1)[0].toLowerCase());
    const row = rows(page).filter({ hasText: few.player_name }).first();
    await expect(row.locator('[data-col="target_share"]')).toHaveText("—");
    await expect(row.locator('[data-col="target_share"]')).toHaveAttribute("title", /Too few to read: \d+ plays of his team's when trailing/);
    await page.getByTestId("players-search").fill("");
  }
  await noSidewaysScroll(page);
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: join(SHOTS, `ix3-trailing-${info.project.name === "phone" ? 375 : 1300}.jpg`), quality: 70, fullPage: false });
});

test("a card opened from the table and closed keeps the position, view, filter, sort and scroll", async ({ page, context, isMobile }, info) => {
  await serve(context);
  await page.goto(url("&position=WRTE&view=opportunity&sit=trailing&sort=targets&dir=desc"));
  await expect(rows(page).first()).toBeVisible();
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: join(SHOTS, `ix3-opportunity-${info.project.name === "phone" ? 375 : 1300}.jpg`), quality: 70, fullPage: false });
  const link = table(page).getByRole("link", { name: JJ.name, exact: true });
  await link.evaluate((n) => n.scrollIntoView({ block: "center" }));
  const box = page.getByTestId("stats-scroll");
  const before = await page.evaluate(() => window.scrollY);
  const boxBefore = await box.evaluate((el) => el.scrollTop);
  expect(boxBefore + before, "the table is scrolled to his row").toBeGreaterThan(200);
  const addr = new URL(page.url());
  if (isMobile) await link.tap();
  else await link.click();
  await expect(page.getByTestId("pane")).toHaveAttribute("data-gsis", JJ.gsis);
  await page.getByTestId("pane-close").click();
  await expect(page.getByTestId("pane")).toHaveCount(0);
  const after = new URL(page.url());
  for (const k of ["position", "view", "sit", "sort", "dir"]) expect(after.searchParams.get(k), k).toBe(addr.searchParams.get(k));
  await expect(page.getByTestId("stats-table-view-opportunity")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("sit-trailing")).toHaveAttribute("aria-pressed", "true");
  if (isMobile) await expect(page.getByTestId("stats-filters-label")).toHaveText("Filters: When trailing");
  expect(Math.abs((await page.evaluate(() => window.scrollY)) - before)).toBeLessThanOrEqual(2);
  expect(Math.abs((await box.evaluate((el) => el.scrollTop)) - boxBefore)).toBeLessThanOrEqual(2);
  await expect(link).toBeInViewport();
});

test("screens: 375 and 1300, the first view", async ({ page, context }, info) => {
  await serve(context);
  await page.goto(url("&position=WRTE"));
  await expect(rows(page).first()).toBeVisible();
  await noSidewaysScroll(page);
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: join(SHOTS, `ix3-key-${info.project.name === "phone" ? 375 : 1300}.jpg`), quality: 70, fullPage: false });
  await page.goto(url("&position=WRTE&view=full"));
  await expect(rows(page).first()).toBeVisible();
  await page.screenshot({ path: join(SHOTS, `ix3-full-${info.project.name === "phone" ? 375 : 1300}.jpg`), quality: 70, fullPage: false });
});

// ---- IX-3 round 2: on a phone the first screen is the answer — the title line, the positions, the view tabs (one row)
// and the table's first rows; every other control behind one Filters button that names what is in force
test("a phone opens on the answer: Filters folded (named when in force), the view tabs one row, the table's first rows on the first screen", async ({ page, context, isMobile }, info) => {
  await serve(context);
  await page.goto(url("&position=WRTE"));
  await expect(rows(page).first()).toBeVisible();
  const toggle = page.getByTestId("stats-filters-toggle");
  if (!isMobile) {
    // 1300: nothing changes — no Filters button, every control in place
    await expect(toggle).toBeHidden();
    await expect(page.getByTestId("players-search")).toBeVisible();
    await expect(page.getByTestId("sit-all")).toBeVisible();
    return;
  }
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByTestId("stats-filters-label")).toHaveText("Filters");
  for (const id of ["players-search", "who-all", "players-team", "stats-window-pick", "mode-game", "stats-min", "stats-minopp", "sit-all", "stats-columns", "role-cards"]) await expect(page.getByTestId(id), id).toBeHidden();
  await expect(page.getByTestId("pos-WRTE")).toBeInViewport();
  // the view tabs in one row: every tab on the same line, the page never wider than the screen
  const tops = await page.getByTestId("stats-table-view").locator("button").evaluateAll((bs) => bs.map((b) => Math.round(b.getBoundingClientRect().top)));
  expect(new Set(tops).size).toBe(1);
  await noSidewaysScroll(page);
  // whole rows above the fold: the screen's bottom or, on a phone, the top of the fixed bottom menu
  const seen = await rows(page).evaluateAll((rs) => {
    const bar = [...document.querySelectorAll<HTMLElement>("body *")].find((e) => getComputedStyle(e).position === "fixed" && e.getBoundingClientRect().bottom >= window.innerHeight - 1 && e.getBoundingClientRect().top > window.innerHeight / 2);
    const limit = bar ? bar.getBoundingClientRect().top : window.innerHeight;
    return rs.filter((r) => r.getBoundingClientRect().bottom <= limit).length;
  });
  expect(seen, "table rows on the first screen").toBeGreaterThanOrEqual(3);
  console.log(`IX3R2 rows on the first screen at ${page.viewportSize()?.width}x${page.viewportSize()?.height}: ${seen}`);
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: join(SHOTS, "ix3r2-closed-375.jpg"), quality: 70, fullPage: false });
  // a real button, keyboard reachable: Enter opens it in place
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByTestId("players-search")).toBeVisible();
  await expect(page.getByTestId("sit-all")).toBeVisible();
  await page.screenshot({ path: join(SHOTS, "ix3r2-open-375.jpg"), quality: 70, fullPage: false });
  // a filter in force is named on the closed button
  await page.goto(url("&position=WRTE&sit=trailing&who=fa&window=last5w"));
  await expect(rows(page).first()).toBeVisible().catch(() => undefined);
  await expect(page.getByTestId("stats-filters-label")).toHaveText("Filters: When trailing · Free agents · Last 5 calendar weeks");
  await expect(page.getByTestId("stats-filters-toggle")).toHaveAttribute("aria-expanded", "false");
  await page.screenshot({ path: join(SHOTS, "ix3r2-closed-filtered-375.jpg"), quality: 70, fullPage: false });
  void info;
});
