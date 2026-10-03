// Wave I-E (IE-2): the review's trade explained through the starting lineup, the setup order, the contrast.
// Dad's league (MFL 70587), team 8 "Big Mac Attack" ↔ team 12 "Madeyes Revenge", Tuten for Rice (the review's reduced
// scenario: Watson and Nabers only change slot numbers). Phone (375) and desktop (1300).
//
// The answers are the API's own, recorded from a live API on the MFL fixtures into web/fixtures/mfl/api_70587_ie2.json
// and replayed here (no API, no database). Re-record (the POST's body is part of the key):
//   (api on :8749 with LEAGUE_LAB_MFL_FIXTURES / _SLEEPER_FIXTURES / _PLAYER_IDS_CSV set, the gate off)
//   IE2_RECORD=http://127.0.0.1:8749 FIXTURES_PORT=8617 npm run e2e:fixtures -- e2e/ie2
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "mfl", "api_70587_ie2.json");
const RECORD = process.env.IE2_RECORD ?? "";
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = !RECORD && existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};
const MINE = /mfl|70587|scoring-check/i;
const SHOTS = process.env.SHOTS_DIR ?? "e2e/.out";
const CALC = "/trade-calc?league=mfl%3A70587&team=8&partner=12&give=12490&get=10229";

const keyOf = (u: URL, body: string | null) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return u.pathname + (q.length ? `?${new URLSearchParams(q).toString()}` : "") + (body ? ` ${body}` : "");
};

async function answer(route: Route) {
  const req = route.request();
  const u = new URL(req.url());
  const body = req.method() === "POST" ? req.postData() : null;
  const key = keyOf(u, body);
  if (!MINE.test(decodeURIComponent(key))) return route.fallback();
  if (RECORD) {
    const r = await fetch(RECORD + u.pathname + u.search, body ? { method: "POST", body, headers: { "Content-Type": "application/json" } } : undefined);
    const text = await r.text();
    let parsed: unknown = text;
    try {
      parsed = JSON.parse(text);
    } catch {
      /* keep the text */
    }
    saved[key] = { status: r.status, body: parsed };
    return route.fulfill({ status: r.status, contentType: "application/json", body: text });
  }
  const s = saved[key];
  if (!s) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: `no fixture for ${key}` }) });
  return route.fulfill({ status: s.status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(s.body) });
}

test.afterAll(() => {
  if (RECORD) writeFileSync(FILE, JSON.stringify(saved, null, 1) + "\n");
});

test.beforeEach(async ({ context }) => {
  await serveFixtures(context);
  await context.route(/\/api\//, answer);
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const top = async (page: Page, testid: string) => (await page.getByTestId(testid).first().boundingBox())?.y ?? Number.NaN;

test("the trade result: assets → effect → starters in / out → backup → their side → alternatives, then the arithmetic", async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(CALC);
  const story = page.getByTestId("trade-story");
  await expect(story).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("trade-assets")).toContainText("Bhayshul Tuten");
  await expect(page.getByTestId("trade-assets")).toContainText("Rashee Rice");
  await expect(page.getByTestId("trade-effect")).toHaveText("Your starting lineup: about 3.4 more points this week, about 10 more in total over weeks 4–7.");
  await expect(page.getByTestId("starter-in")).toHaveCount(1);
  await expect(page.getByTestId("starter-in")).toContainText("Rashee Rice at WR/TE");
  await expect(page.getByTestId("starter-out")).toHaveCount(1);
  await expect(page.getByTestId("starter-out")).toContainText("Ladd McConkey");
  await expect(page.getByTestId("starter-out")).toContainText("to the bench");
  await expect(story).not.toContainText("Nabers"); // only moved WR/TE 2 → 3: not a change
  await expect(story).not.toContainText("Watson");
  await expect(page.getByTestId("trade-total")).toContainText("115.4 → 118.8 (+3.4 projected points)");
  await expect(page.getByTestId("trade-backup")).toHaveText("Backup coverage: you lose Tuten, a backup RB (1 RB left on your bench).");
  await expect(page.getByTestId("trade-their-side")).toContainText("Madeyes Revenge's starting lineup: about 2.0 fewer points this week");
  await expect(page.getByTestId("trade-hold")).toContainText("Standing pat keeps your starting lineup at 115.4");
  // the order on the page (top to bottom) and the arithmetic below it
  const order = ["trade-assets", "trade-effect", "trade-starters", "trade-backup", "trade-their-side", "trade-hold", "why", "lineups-x"];
  const ys = [];
  for (const t of order) ys.push(await top(page, t));
  console.log(`IE-2 ${info.project.name}: result order y = ${ys.map((y) => Math.round(y)).join(" < ")}`);
  for (let i = 1; i < ys.length; i++) expect(ys[i], `${order[i]} below ${order[i - 1]}`).toBeGreaterThan(ys[i - 1]);
  await expect(page.getByTestId("why").locator("summary")).toHaveText(/How we calculated this/);
  // the lineup detail: Nabers and Watson show no change of their own; McConkey's row carries the -6.9
  await page.getByTestId("lineups-x").locator("summary").first().click();
  const mine = page.getByTestId("lineup-after").first();
  await expect(mine.locator("li", { hasText: "Malik Nabers" })).not.toContainText("+");
  await expect(mine.locator("li", { hasText: "Christian Watson" })).not.toContainText("+");
  await expect(mine.getByTestId("lineup-out")).toContainText("Ladd McConkey");
  await expect(mine.getByTestId("lineup-out")).toContainText("−6.9"); // s1: a true minus
  await expect(mine.getByTestId("lineup-reshuffled")).toContainText("Nabers WR/TE 2 → WR/TE 3");
  await noSidewaysScroll(page);
  await story.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(SHOTS, `ie2_trade_result_${info.project.name}.png`), fullPage: false });
});

test("setup: league and team picker first, the scoring one status line (collapsed)", async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  await expect(page.getByTestId("leagues")).toBeVisible();
  await page.getByTestId("mfl-link").fill("70587");
  await page.getByTestId("mfl-go").click();
  const card = page.getByTestId("mfl-card");
  await expect(card).toContainText("Make Football Great Again");
  await expect(page.getByTestId("mfl-team")).toHaveCount(12);
  const status = page.getByTestId("scoring-status");
  await expect(status).toHaveText(/^›?\s*(Custom MFL scoring — some pieces are estimated|MFL scoring, read exactly)$/);
  await expect(page.getByTestId("card-scoring")).toBeHidden(); // collapsed until asked
  const teamsY = await top(page, "mfl-team");
  const statusY = await top(page, "scoring-status");
  expect(teamsY).toBeLessThan(statusY);
  if (info.project.name === "desktop") expect(teamsY, "the team picker on the first desktop screen").toBeLessThan(900);
  await status.click();
  await expect(page.getByTestId("card-scoring")).toBeVisible();
  await expect(page.getByTestId("card-check")).toBeVisible();
  console.log(`IE-2 ${info.project.name}: team picker y=${Math.round(teamsY)}, scoring status y=${Math.round(statusY)}: ${(await status.textContent())?.trim()}`);
  await noSidewaysScroll(page);
  await card.screenshot({ path: join(SHOTS, `ie2_setup_${info.project.name}.png`) });
});

test("contrast: supporting text (ink-3) ≥ 4.5:1 on every surface, light and dark", async ({ page }) => {
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto("/");
    const r = await page.evaluate(() => {
      const css = getComputedStyle(document.documentElement);
      const hex = (n: string) => {
        const h = css.getPropertyValue(n).trim(); // the build may shorten #ffffff to #fff
        return h.length === 4 ? `#${h[1]}${h[1]}${h[2]}${h[2]}${h[3]}${h[3]}` : h;
      };
      const lum = (h: string) => {
        const v = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
      };
      const ratio = (a: string, b: string) => {
        const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
        return (x + 0.05) / (y + 0.05);
      };
      const out: Record<string, number> = {};
      for (const ink of ["--ll-ink-2", "--ll-ink-3"])
        for (const bg of ["--ll-page", "--ll-surface", "--ll-raised", "--ll-sunken"]) out[`${ink} on ${bg}`] = Math.round(ratio(hex(ink), hex(bg)) * 100) / 100;
      return out;
    });
    console.log(`IE-2 contrast (${scheme}): ${JSON.stringify(r)}`);
    for (const [k, v] of Object.entries(r)) expect(v, `${scheme}: ${k}`).toBeGreaterThanOrEqual(4.5);
  }
});
