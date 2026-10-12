// Wave J-A (JA-1): Stats — the weeks you choose. The week slider (components/stretch/WeekSlider.svelte; URL keys
// window / weeks / vs, lib/stretch.ts): two handles over the played weeks, a single week when they meet, the choice in
// words, quick picks, keyboard; outside the phone's Filters fold when a stretch other than the season is in force.
// One stretch against another (vs=): the value in A, the change from B under it, sort by the change, the presets, the
// headline. A stat week by week (view=byweek&stat=…): the weeks as columns, the stretch's value, a trend mark, a dash
// and its reason for a week without a game. Phone at 375, desktop at 1300; screens into JA1_SHOTS.
//
// Recordings: web/fixtures/ja1/api_ja1.json (web/fixtures/save_ja1_fixtures.py; the first 120 rows of each answer).
import { expect, test, type BrowserContext, type Locator, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures, SCRUBS } from "../fixtures";

const DIR = join(import.meta.dirname, "..", "..", "fixtures", "ja1");
type Row = Record<string, unknown> & { gsis_id: string; player_name: string; games: number };
type Frame = { players: Row[]; vs: { players: Record<string, Row> } | null; byweek: { weeks: number[]; values: Record<string, (number | null)[]>; why: Record<string, (string | null)[]> } | null };
const saved: Record<string, { status: number; body: Frame }> = JSON.parse(readFileSync(join(DIR, "api_ja1.json"), "utf8"));
const keyOf = (q: Record<string, string>) => `/api/players?${new URLSearchParams(Object.entries(q).sort(([a], [b]) => a.localeCompare(b))).toString()}`;
const BASE = { league: SCRUBS, limit: "1000", position: "WR,TE" };
const AB = saved[keyOf({ ...BASE, window: "weeks", weeks: "3-4", vs: "1-2" })].body;
const BW = saved[keyOf({ ...BASE, window: "season", by: "target_share" })].body;
const url = (extra = "") => `/players?league=${SCRUBS}&team=2&position=WRTE${extra}`;
const SHOTS = process.env.JA1_SHOTS ?? "e2e/.out";

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
async function openFilters(page: Page) {
  const t = page.getByTestId("stats-filters-toggle");
  if ((await t.isVisible()) && (await t.getAttribute("aria-expanded")) !== "true") await t.click();
}
async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}
const shot = async (page: Page, name: string, info: { project: { name: string } }) => {
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: join(SHOTS, `ja1-${name}-${info.project.name === "phone" ? 375 : 1300}.jpg`), quality: 70, fullPage: false });
};
const rows = (page: Page) => page.getByTestId("players-table").getByTestId("players-table-row");

test("the slider: season by default (folded on a phone), a quick pick, the handles by keyboard, a single week; the choice in words and in the URL", async ({ page, context, isMobile }, info) => {
  await serve(context);
  await page.goto(url());
  await expect(rows(page).first()).toBeVisible();
  const slider = page.getByTestId("stats-weeks");
  if (isMobile) {
    await expect(slider).toBeHidden(); // the season: inside the Filters fold
    await openFilters(page);
  }
  await expect(page.getByTestId("slider-words")).toHaveText("Season · weeks 1–4");
  await expect(page.getByTestId("slider-quick-season")).toHaveAttribute("aria-pressed", "true");
  await shot(page, "slider-open", info);
  // keyboard: the first handle one step right → weeks 2–4
  await page.getByTestId("slider-a-lo").focus();
  await page.keyboard.press("ArrowRight");
  await expect(page).toHaveURL(/[?&]window=weeks/);
  await expect(page).toHaveURL(/[?&]weeks=2-4/);
  await expect(page.getByTestId("slider-words")).toHaveText("Weeks 2–4 · 3 weeks");
  await expect(page.getByTestId("slider-a-lo")).toHaveAttribute("aria-valuetext", "Week 2");
  // one handle on the other: a single week ("This week" is the newest played)
  await tap(page, page.getByTestId("slider-quick-this"), isMobile);
  await expect(page).toHaveURL(/[?&]weeks=4-4/);
  await expect(page.getByTestId("slider-words")).toHaveText("Week 4 · 1 week");
  // a tap on a week number moves the nearer handle
  await tap(page, page.getByTestId("slider-week-3"), isMobile);
  await expect(page).toHaveURL(/[?&]weeks=3-4/);
  await expect(page.getByTestId("slider-words")).toHaveText("Weeks 3–4 · 2 weeks");
  // a stretch other than the season is never folded away: closed, the slider still shows on a phone
  if (isMobile) {
    await page.getByTestId("stats-filters-toggle").click();
    await expect(page.getByTestId("stats-filters-toggle")).toHaveAttribute("aria-expanded", "false");
    await expect(slider).toBeVisible();
    await expect(rows(page).first()).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    await shot(page, "slider-closed", info);
  }
  // the URL round trip: a fresh visit opens on the same weeks
  await page.goto(url("&window=weeks&weeks=3-4"));
  await expect(page.getByTestId("slider-words")).toHaveText("Weeks 3–4 · 2 weeks");
  await expect(page.getByTestId("stats-window-label")).toHaveCount(1);
  await noSidewaysScroll(page);
});

test("weeks 3–4 against weeks 1–2: the change under each value, sort by the change, the presets, the headline", async ({ page, context, isMobile }, info) => {
  const api = await serve(context);
  await page.goto(url("&window=weeks&weeks=3-4"));
  await expect(rows(page).first()).toBeVisible();
  // JA-2: on a phone a chosen stretch opens closed, one line naming it; a tap opens it in place
  if (isMobile) {
    await expect(page.getByTestId("slider-toggle")).toHaveText(/Weeks 3–4/);
    await expect(page.getByTestId("slider-toggle")).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByTestId("slider-compare")).toBeHidden();
    await tap(page, page.getByTestId("slider-toggle"), isMobile);
    await expect(page.getByTestId("slider-toggle")).toHaveAttribute("aria-expanded", "true");
  } else await expect(page.getByTestId("slider-toggle")).toBeHidden();
  await tap(page, page.getByTestId("slider-compare"), isMobile);
  await expect(page).toHaveURL(/[?&]vs=1-2/); // "the weeks before": the same length, ending where A starts
  await expect.poll(() => api.calls.some((c) => c.includes("vs=1-2"))).toBe(true);
  await expect(page.getByTestId("slider-words")).toContainText("A: Weeks 3–4 · 2 weeks against B: Weeks 1–2 · 2 weeks");
  await expect(page.getByTestId("slider-preset-before")).toHaveAttribute("aria-pressed", "true");
  // the change under the value: a share in points of share
  const first = AB.players.find((p) => typeof p.target_share === "number" && typeof AB.vs!.players[p.gsis_id]?.target_share === "number")!;
  await page.getByTestId("sort-chg-target_share").evaluate((n) => n.scrollIntoView({ block: "center", inline: "nearest" }));
  await tap(page, page.getByTestId("sort-chg-target_share"), isMobile);
  await expect(page).toHaveURL(/[?&]sortby=chg/);
  const rise = [...AB.players]
    .filter((p) => typeof p.target_share === "number" && typeof AB.vs!.players[p.gsis_id]?.target_share === "number")
    .sort((a, b) => ((b.target_share as number) - (AB.vs!.players[b.gsis_id].target_share as number)) - ((a.target_share as number) - (AB.vs!.players[a.gsis_id].target_share as number)) || a.player_name.localeCompare(b.player_name))[0];
  await expect(page.getByTestId("players-answer")).toContainText(`Biggest rise in target share, weeks 3–4 against weeks 1–2: ${rise.player_name}`);
  const chg = (rise.target_share as number) - (AB.vs!.players[rise.gsis_id].target_share as number);
  await expect(rows(page).first().locator('[data-col="target_share"] [data-testid="chg"]')).toHaveText(`${chg >= 0 ? "+" : "−"}${Math.abs(chg * 100).toFixed(1)} pts`);
  void first;
  await shot(page, "a-against-b", info);
  // JA-2: weeks 3–4 end the season, so "the rest of the season" is weeks 1–2 too: one preset, "The weeks before"
  await expect(page.getByTestId("slider-preset-rest")).toHaveCount(0);
  // off again: no second stretch
  await tap(page, page.getByTestId("slider-compare"), isMobile);
  await expect(page).not.toHaveURL(/[?&]vs=/);
  await noSidewaysScroll(page);
});

test("by week: one stat across the weeks, the season's value and a trend mark; a week without a game is a dash with its reason", async ({ page, context, isMobile }, info) => {
  await serve(context);
  await page.goto(url("&view=byweek&stat=target_share"));
  await expect(rows(page).first()).toBeVisible();
  await expect(page.getByTestId("stats-table-view-byweek")).toHaveAttribute("aria-pressed", "true");
  for (const w of BW.byweek!.weeks) await expect(page.getByTestId(`sort-w${w}`)).toHaveCount(1);
  await expect(page.getByTestId("sort-total")).toHaveCount(1);
  await expect(page.getByTestId("sort-trend")).toHaveCount(1);
  // a player who missed a week: a dash there, with the reason
  const missed = BW.players.find((p) => (BW.byweek!.values[p.gsis_id] ?? []).some((v) => v === null));
  if (missed) {
    const i = BW.byweek!.values[missed.gsis_id].findIndex((v) => v === null);
    await openFilters(page);
    await page.getByTestId("players-search").fill(missed.player_name);
    const cell = rows(page).filter({ hasText: missed.player_name.split(" ").slice(-1)[0] }).first().locator(`[data-col="w${BW.byweek!.weeks[i]}"]`);
    await expect(cell).toHaveText("—");
    await expect(cell).toHaveAttribute("title", /bye week|did not play/);
    await page.getByTestId("players-search").fill("");
    if (isMobile) await page.getByTestId("stats-filters-toggle").click();
  }
  // sort by a week
  await tap(page, page.getByTestId(`sort-w${BW.byweek!.weeks[0]}`), isMobile);
  await expect(page).toHaveURL(/[?&]sort=w1/);
  await noSidewaysScroll(page);
  await shot(page, "by-week", info);
});

// ---- JA-2: the compact closed form — with a stretch and a comparison in force, a phone's first screen still shows rows
test("a phone with weeks 3–4 against weeks 1–2: the control is one line and the table's first rows are on the first screen", async ({ page, context, isMobile }) => {
  await serve(context);
  await page.goto(url("&window=weeks&weeks=3-4&vs=1-2"));
  await expect(rows(page).first()).toBeVisible();
  const toggle = page.getByTestId("slider-toggle");
  if (!isMobile) {
    await expect(toggle).toBeHidden();
    await expect(page.getByTestId("slider-a-lo")).toBeVisible();
    return;
  }
  await expect(toggle).toHaveText(/Weeks 3–4 against weeks 1–2/);
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  const seen = await rows(page).evaluateAll((rs) => {
    const bar = [...document.querySelectorAll<HTMLElement>("body *")].find((e) => getComputedStyle(e).position === "fixed" && e.getBoundingClientRect().bottom >= window.innerHeight - 1 && e.getBoundingClientRect().top > window.innerHeight / 2);
    const limit = bar ? bar.getBoundingClientRect().top : window.innerHeight;
    return rs.filter((r) => r.getBoundingClientRect().bottom <= limit).length;
  });
  console.log(`JA2 rows on the first screen at 375x812 with a stretch and a comparison: ${seen}`);
  mkdirSync(process.env.JA2_SHOTS ?? SHOTS, { recursive: true });
  await page.screenshot({ path: join(process.env.JA2_SHOTS ?? SHOTS, "ja2-stats-compact-375.jpg"), quality: 70, fullPage: false });
  expect(seen).toBeGreaterThanOrEqual(3);
  // keyboard: Enter opens it in place
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByTestId("slider-a-lo")).toBeVisible();
});
