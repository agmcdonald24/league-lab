// Wave I-G (IG-1): unknown is not zero, and team units have a season value. (1) League of Scrubs roster 6
// "GoodGameBuddy": Josh Jacobs has no projection row — the bench shows a dash titled "no projection" and the words, never
// "0.00" (the API sends null). (2) Dad's league, MFL 70587 team 8: "Houston Texans QB + Tuten for Rice" counts the team
// QB's season value (IF-2: "Not counted (no season projection): Houston Texans QB."), and the Finder's "left out" rule is
// the value gap (season value above replacement), not the raw rest-of-season totals. Phone at 375 px and desktop.
//
// The answers are the API's own, recorded from a live API on the fixtures (MFL / Sleeper / ESPN / the player-ids CSV) and
// the clone `league_lab_i0b` into web/fixtures/ig1/api_ig1.json, and replayed here. Re-record:
//   (api on :8703 — scratchpad waveIG/ig1/api_ig1.sh — the gate off)
//   IG1_RECORD=http://127.0.0.1:8703 FIXTURES_PORT=8603 npx playwright test --config playwright.fixtures.config.ts e2e/ig1
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { serveFixtures, SCRUBS } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "ig1", "api_ig1.json");
const RECORD = process.env.IG1_RECORD ?? "";
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = !RECORD && existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};

// ---- IR-2 fix: the calculator's saved answer (its `decision` is what the screen reads); the sign as `s1` prints it
type Ev = { decision: { alternative: { words: string }; strip: { mine: number[]; theirs: number[] } }; values: { season_value: { words: string } } };
const savedEval = (has: string): Ev =>
  Object.entries(saved).find(([k]) => k.startsWith("/api/trades/evaluate") && k.includes(has))![1].body as Ev;
const MINE = /\/api\/(my-week|trades\/(partners|evaluate)|team\?|player\/00-0035700\?)|mfl/i;
const MFL = "mfl:70587";

const keyOf = (u: URL, body: string | null) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return u.pathname + (q.length ? `?${new URLSearchParams(q).toString()}` : "") + (body ? ` ${body}` : "");
};

async function answer(route: Route) {
  const req = route.request();
  const u = new URL(req.url());
  const body = req.method() === "POST" ? req.postData() : null;
  const key = keyOf(u, body);
  if (!MINE.test(decodeURIComponent(u.pathname + u.search))) return route.fallback();
  if (RECORD) {
    const r = await fetch(RECORD + u.pathname + u.search, body ? { method: "POST", body, headers: { "content-type": "application/json" } } : {});
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
  if (!s) return route.fallback();
  return route.fulfill({ status: s.status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(s.body) });
}

test.afterAll(() => {
  if (RECORD) {
    mkdirSync(dirname(FILE), { recursive: true });
    writeFileSync(FILE, JSON.stringify(saved, null, 1) + "\n");
  }
});

test.beforeEach(async ({ context, page }, info) => {
  if (RECORD) test.setTimeout(240_000);
  test.skip(!RECORD && !existsSync(FILE), "no recording yet: run with IG1_RECORD (see the header)");
  await serveFixtures(context);
  await context.route(/\/api\//, answer);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `ig1-${name}-${project}.png`), fullPage: true });

test("a bench player with no projection shows a dash and the words, never 0.00", async ({ page }, info) => {
  await page.goto(`/?league=${SCRUBS}&team=6`);
  await expect(page.getByTestId("lineup")).toBeVisible({ timeout: 60_000 });
  await page.getByTestId("lineup-full").locator("summary").first().click();
  const table = page.getByTestId("lineup-full-table");
  const row = table.locator("tr", { hasText: "Jacobs" });
  await expect(row).toHaveCount(1);
  const proj = row.getByTestId("lineup-proj");
  await expect(proj).toContainText("—");
  await expect(proj).not.toContainText("0.0"); // IU-3: one decimal
  await expect(proj).toHaveAttribute("title", /no projection/i);
  await expect(row.getByTestId("lineup-flag")).toHaveText("no projection"); // the console's flag, mirrored (parity)
  await expect(row.getByTestId("no-projection")).toHaveCount(0); // said once
  // every other row keeps its number; no row shows a bare 0.00 for a player
  await expect(table.getByTestId("lineup-proj").filter({ hasText: /^0\.0+$/ })).toHaveCount(0); // IU-3: one decimal
  await expect(page.getByTestId("unvalued-words")).toHaveCount(0); // the bench is not in the total: nothing to say
  await noSidewaysScroll(page);
  await shot(page, "scrubs6-bench", info.project.name);
  // his card in the research pane: a dash, and the label says why
  await row.getByTestId("lineup-name").click();
  const card = page.getByTestId("pane-card");
  await expect(card).toContainText("—", { timeout: 60_000 });
  await expect(card).toContainText("no projection");
  await expect(card).not.toContainText("0.0");
});

test("the team QB is counted in the season value, and the Finder leaves out trades on the value gap", async ({ page }, info) => {
  await page.goto(`/trade-calc?league=${encodeURIComponent(MFL)}&team=8&partner=12&give=${encodeURIComponent("mfl:0682")},12490&get=10229`);
  await expect(page.getByTestId("trade-alternative")).toBeVisible({ timeout: 90_000 });
  await page.getByTestId("why").locator("summary").first().click();
  const sv = page.getByTestId("season-value-words");
  // IR-2 fix: the season value line is the saved answer's (re-saved: the team QB still counted, no "Not counted")
  await expect(sv).toContainText(savedEval('"mfl:0682","12490"').values.season_value.words);
  await expect(sv).not.toContainText("Not counted");
  await expect(page.getByTestId("sanity")).toHaveCount(0);
  await noSidewaysScroll(page);
  await shot(page, "team8-calc", info.project.name);

  await page.goto(`/trades?league=${encodeURIComponent(MFL)}&team=8`);
  // IT-1 (re-saved on the calculator's basis): the answer's own first line (today: no trade worth proposing — the
  // Chicago Bears QB package is behind Explore), then the trades left out on the value gap
  const fa = Object.entries(saved).find(([k]) => k.includes("/api/trades/partners") && k.includes("team=8"))![1].body as {
    verdict: { kind: string; headline: string | null }; partners: { partner_team: string; tier?: string }[]; rejected_count: number };
  const cred = fa.partners.find((r) => r.tier === "credible");
  await expect(page.getByTestId("best-partner")).toContainText(cred ? `Best partner: ${cred.partner_team}` : fa.verdict.headline!, { timeout: 90_000 });
  expect(fa.rejected_count).toBeGreaterThan(0);
  const left = page.getByTestId("rejected");
  await left.locator("summary").first().click();
  await expect(page.getByTestId("rejected-rule")).toContainText("season value above replacement");
  await expect(page.getByTestId("rejected-list")).toContainText("season value above replacement for");
  await expect(page.getByTestId("rejected-list")).not.toContainText("rest-of-season points");
  await noSidewaysScroll(page);
  await shot(page, "team8-finder", info.project.name);
});
