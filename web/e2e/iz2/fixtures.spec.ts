// Wave I-Z (IZ-2): a trade answers five questions in order (the review of 10 October § "The trade decision that could
// distinguish the product", Pass 2). Phone at 375 (the lineup panel without sideways scroll) and desktop at 1300;
// screenshots into docs/handbacks/iz2/ (SHOTS_IZ2) or e2e/.out.
//
// Recorded answers (web/fixtures/iz2/api_iz2.json): POST /api/trades/evaluate from this branch's API on league_lab_iq4
// at the PO's Saturday clock (2026-10-10T16:00Z) — the review's known trade (League of Scrubs, team 2 gives Folk to team 3
// for Stafford + Reichard) and a trade the calculator calls worth proposing. Everything else from the fixture API.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveDecisions } from "../decisions-fixtures";
import { SCRUBS, serveFixtures } from "../fixtures";

const RECORDED = join(import.meta.dirname, "..", "..", "fixtures", "iz2", "api_iz2.json");
const SHOTS = process.env.SHOTS_IZ2 ?? join(import.meta.dirname, "..", ".out");
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const rec = JSON.parse(readFileSync(RECORDED, "utf8")) as Record<string, any>;
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64");

// the trade's answer and both rosters as this branch's API answered them (the fixture API's rosters are older)
async function evaluate(context: BrowserContext, body: unknown) {
  await context.route(/\/api\/trades\/evaluate/, (route) =>
    route.request().method() === "POST" ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) }) : route.fallback(),
  );
  await context.route(/\/api\/team\?/, (route) => {
    const u = new URL(route.request().url());
    const hit = rec.team[`${u.searchParams.get("league")}|${u.searchParams.get("team")}`];
    return hit ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(hit) }) : route.fallback();
  });
  await context.route(/\/api\/leagues\/[^/]+\/rosters/, (route) => {
    const l = decodeURIComponent(new URL(route.request().url()).pathname.split("/")[3]);
    return rec.rosters[l] ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(rec.rosters[l]) }) : route.fallback();
  });
}

test.beforeEach(async ({ context, page }, info) => {
  await context.route(/^https?:\/\/(?!localhost)/, (route) => route.fulfill({ status: 200, contentType: "image/png", body: PNG }));
  await serveFixtures(context);
  await serveDecisions(context);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSideways(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(SHOTS, `iz2-${name}-${project === "phone" ? "375" : "1300"}.jpg`), type: "jpeg", quality: 70, fullPage: true });

const sgn = (x: number) => (Math.abs(x) >= 0.05 ? `${x > 0 ? "+" : "−"}${Math.abs(x).toFixed(1)}` : "+0.0");

const top = async (page: Page, testid: string) => (await page.getByTestId(testid).first().boundingBox())?.y ?? Number.NaN;
const f1 = (x: number) => x.toFixed(1);

test("the Folk trade: five questions in order, the lineup panel, keep / claim / trade on one basis", async ({ context, page }, info) => {
  const ev = rec.folk;
  const d = ev.decision;
  await evaluate(context, ev);
  await page.goto(`/trade-calc?league=${SCRUBS}&team=2&partner=3&give=650&get=421,11792`);
  await expect(page.getByTestId("trade-five")).toBeVisible({ timeout: 30_000 });
  // the conclusion, then the package, then the five questions in the review's order
  const order = ["verdict", "three-apart", "trade-assets", "five-1", "five-2", "five-3", "five-4", "five-5", "why", "lineups-x"];
  const ys = [];
  for (const t of order) ys.push(await top(page, t));
  for (let i = 1; i < ys.length; i++) expect(ys[i], `${order[i]} below ${order[i - 1]}`).toBeGreaterThan(ys[i - 1]);
  // three things kept apart, by name, each with its unit; the market price's source and date
  await expect(page.getByTestId("apart-lineup")).toContainText(`Lineup points (your best lineup each week): you ${sgn(d.mine.gain_window)} over ${d.span}`);
  await expect(page.getByTestId("apart-market")).toContainText(`Market price (season value above replacement, in season points): you give ${ev.market.give}, you get ${ev.market.get}`);
  await expect(page.getByTestId("apart-market")).toContainText(/From League Lab's rest-of-season projections, data published \d+ \w{3}, \d+:\d\d (am|pm) ET\./);
  await expect(page.getByTestId("five-plausibility")).toHaveText("Implausible");
  await expect(page.getByTestId("trade-result")).not.toContainText(/\bfree\b(?! (agent|pool))/i); // a low lineup value is never "free"
  // 1. your starters: the panel's rows are the decision's changes, the displaced player named, before → after
  await expect(page.getByTestId("trade-effect")).toHaveText(d.effect_words);
  const mine = page.getByTestId("panel-mine").getByTestId("panel-row");
  await expect(mine).toHaveCount(d.changes.mine.length);
  for (const [i, c] of d.changes.mine.entries()) {
    if (c.out_player) await expect(mine.nth(i).getByTestId("panel-out")).toContainText(c.out_player.player_name);
    if (c.in_player) await expect(mine.nth(i).getByTestId("panel-in")).toContainText(c.in_player.player_name);
  }
  await expect(page.getByTestId("panel-mine").getByTestId("panel-total")).toContainText(`${f1(d.mine.before.this_week)} → ${f1(d.mine.after.this_week)} (${sgn(d.mine.gain_week)} projected points)`);
  await expect(page.getByTestId("trade-strip").getByTestId("strip-mine").locator("td")).toHaveText(d.strip.mine.map(sgn));
  // 2. what they get: their panel, why they might say no in words — never a chance that they accept
  await expect(page.getByTestId("trade-their-side")).toHaveText(d.their_effect_words);
  await expect(page.getByTestId("panel-theirs").getByTestId("panel-row")).toHaveCount(d.changes.theirs.length);
  await expect(page.getByTestId("five-refuse-lead")).toContainText(ev.card.why_refuse[0]);
  await expect(page.getByTestId("five-2")).not.toContainText(/%|probab|chance (that|of) (they|him)/i);
  // 3. the cost beyond the package; 4. keep / claim / trade, one basis, one row
  await expect(page.getByTestId("trade-cut")).toHaveText(ev.cut.map((c: { words: string }) => c.words).join(" "));
  const alt = d.alternative.mine;
  await expect(page.getByTestId("way-keep")).toContainText(f1(d.mine.before.window));
  await expect(page.getByTestId("way-trade")).toContainText(f1(d.mine.after.window));
  await expect(page.getByTestId("way-claim")).toContainText(f1(d.mine.before.window + alt.gain_window));
  await expect(page.getByTestId("way-claim")).toHaveAttribute("data-best", "true");
  await expect(page.getByTestId("three-ways-claim")).toContainText(`add ${alt.player.player_name}`);
  await expect(page.getByTestId("three-ways-claim")).toContainText("it can be lost to a team ahead of you");
  await expect(page.getByTestId("trade-alternative")).toContainText(d.alternative.words);
  // 5. what could change the answer: every player in the trade, the checks for their positions
  await expect(page.getByTestId("five-player")).toHaveCount(ev.give.length + ev.get.length + (ev.cut ?? []).length);
  await expect(page.getByTestId("five-check-list")).toContainText("Kickers two to eight weeks ahead: no better than chance");
  await expect(page.getByTestId("trade-news")).toHaveCount(0); // IZ-4 fills it
  // the phone: the panel fits
  await noSideways(page);
  const box = await page.getByTestId("panel-mine").boundingBox();
  expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  await shot(page, "folk", info.project.name);
});

test("a trade the calculator calls worth proposing: the trade is the best of the three", async ({ context, page }, info) => {
  const ev = rec.lloyd;
  const d = ev.decision;
  await evaluate(context, ev);
  await page.goto(`/trade-calc?league=${SCRUBS}&team=2&partner=6&give=650&get=11581`);
  await expect(page.getByTestId("trade-five")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("recommendation")).toContainText("Worth proposing");
  await expect(page.getByTestId("five-plausibility")).toHaveText(ev.card.plausibility.label);
  await expect(page.getByTestId("way-trade")).toHaveAttribute("data-best", "true");
  await expect(page.getByTestId("way-trade")).toContainText(f1(d.mine.after.window));
  await expect(page.getByTestId("panel-mine").getByTestId("panel-row")).toHaveCount(d.changes.mine.length);
  await noSideways(page);
  await shot(page, "worth-proposing", info.project.name);
});

test("no claim beats standing pat: the claim's box says so", async ({ context, page }) => {
  const ev = rec.dyn;
  await evaluate(context, ev);
  await page.goto(`/trade-calc?league=1321941740235550720&team=12&partner=10&give=11559&get=7594,13287`);
  await expect(page.getByTestId("trade-five")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("way-claim")).toContainText("no claim found");
  await expect(page.getByTestId("three-ways-claim")).toHaveCount(0);
  await expect(page.getByTestId("way-trade")).toHaveAttribute("data-best", "true");
});

test("the free calculator: what applies without a league, and what a league would add", async ({ context, page }, info) => {
  await context.route(/\/api\/trade-calc\/free\?/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(rec.free) }));
  await page.goto("/trade-calc?league=ref:half&give=00-0034869&get=00-0036555");
  await expect(page.getByTestId("ft-five")).toBeVisible({ timeout: 30_000 });
  for (const i of [1, 2, 3, 4]) await expect(page.getByTestId(`ft-five-${i}`)).toContainText("A league would add");
  await expect(page.getByTestId("ft-five-5")).toContainText("Nobody in this trade is out or without a projection.");
  await expect(page.getByTestId("ft-five")).toContainText("Lineup points and whether an offer is plausible need the two rosters.");
  await noSideways(page);
  await shot(page, "free", info.project.name);
});
