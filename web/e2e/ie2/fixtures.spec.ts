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
  // IR-2 fix: every sentence and number below is the saved answer's `decision` (re-saved; the screen reads only it)
  type Ch = { slot_word: string; in: string | null; out: string | null; in_how: string; out_why: string; out_value: number | null; words: string; in_player: { player_name: string } | null; out_player: { player_name: string } | null };
  const ev = Object.entries(saved).find(([k]) => k.includes("/api/trades/evaluate"))![1].body as {
    decision: { effect_words: string; their_effect_words: string; changes: { mine: Ch[] }; depth: { mine: { words: string } };
      mine: { before: { this_week: number }; after: { this_week: number }; gain_week: number }; alternative: { words: string } };
  };
  const d = ev.decision;
  const sgn = (x: number) => (Math.abs(x) >= 0.05 ? `${x > 0 ? "+" : "\u2212"}${Math.abs(x).toFixed(1)}` : "+0.0");
  await expect(page.getByTestId("trade-effect")).toHaveText(d.effect_words);
  // the starters, slot by slot: Rice takes a WR/TE slot from the player who goes to the bench (one change, one slot)
  await expect(page.getByTestId("starter-change")).toHaveText(d.changes.mine.map((c) => `${c.words}.`));
  const rice = d.changes.mine.find((c) => c.in_player?.player_name === "Rashee Rice")!;
  expect(rice.slot_word).toBe("WR/TE");
  expect(rice.out_why).toBe("bench");
  await expect(page.getByTestId("trade-starters")).not.toContainText("Nabers"); // a renumbered WR/TE is not a change
  await expect(page.getByTestId("trade-starters")).not.toContainText("Watson");
  await expect(page.getByTestId("trade-total")).toContainText(`${d.mine.before.this_week.toFixed(1)} → ${d.mine.after.this_week.toFixed(1)} (${sgn(d.mine.gain_week)} projected points)`);
  await expect(page.getByTestId("trade-backup")).toHaveText(`Backup coverage: ${d.depth.mine.words}.`);
  await expect(page.getByTestId("trade-their-side")).toContainText(d.their_effect_words);
  await expect(page.getByTestId("trade-alternative")).toContainText(d.alternative.words); // was trade-hold (IR-2: one alternative line)
  // the order on the page (top to bottom) and the arithmetic below it
  const order = ["trade-assets", "trade-effect", "trade-alternative", "trade-starters", "trade-backup", "trade-their-side", "why", "lineups-x"];
  const ys = [];
  for (const t of order) ys.push(await top(page, t));
  console.log(`IE-2 ${info.project.name}: result order y = ${ys.map((y) => Math.round(y)).join(" < ")}`);
  for (let i = 1; i < ys.length; i++) expect(ys[i], `${order[i]} below ${order[i - 1]}`).toBeGreaterThan(ys[i - 1]);
  await expect(page.getByTestId("why").locator("summary")).toHaveText(/How we calculated this/);
  // the lineup detail: Nabers and Watson show no change of their own; the benched starter's row carries his points
  await page.getByTestId("lineups-x").locator("summary").first().click();
  const mine = page.getByTestId("lineup-after").first();
  await expect(mine.locator("li", { hasText: "Malik Nabers" })).not.toContainText("+");
  await expect(mine.locator("li", { hasText: "Christian Watson" })).not.toContainText("+");
  await expect(mine.getByTestId("lineup-out")).toContainText(rice.out_player!.player_name);
  await expect(mine.getByTestId("lineup-out")).toContainText(sgn(-(rice.out_value ?? 0))); // s1: a true minus
  await noSidewaysScroll(page);
  await story.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(SHOTS, `ie2_trade_result_${info.project.name}.png`), fullPage: false });
});

test("setup: league and team picker first, the scoring one status line (collapsed)", async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/leagues"); // IN-1: "/" without a league is the home page now; the setup screen is /leagues
  await expect(page.getByTestId("leagues")).toBeVisible();
  await page.getByTestId("platform-mfl").click(); // ---- II-5 (Wave I-I): the fantasy platform first
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
