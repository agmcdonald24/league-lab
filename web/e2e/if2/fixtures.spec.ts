// Wave I-F (IF-2): trades compete with the simpler alternatives — the decision-quality review § Priority 3 on its own
// roster, MFL 70587 team 8 "Big Mac Attack" (the ESPN fixture overlay on). The Finder's first card is the headline, it
// says what the trade adds beyond the best waiver move (the Atlanta Falcons defense for the open spot, +12.8 over weeks
// 4–7 on the fixture), a trade below it is marked, and every card carries the week strip for both sides; the calculator
// says the same against the claim and labels the raw rest-of-season totals "not a fairness test". Phone at 375 px.
//
// The answers are the API's own, recorded from a live API on the fixtures into web/fixtures/if2/api_if2.json and
// replayed here. Re-record:
//   (api on :8751 with LEAGUE_LAB_MFL_FIXTURES / _SLEEPER_FIXTURES / _ESPN_FIXTURES / _PLAYER_IDS_CSV set, the gate off)
//   IF2_RECORD=http://127.0.0.1:8751 FIXTURES_PORT=8619 npm run e2e:fixtures -- e2e/if2
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { serveFixtures } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "if2", "api_if2.json");
const RECORD = process.env.IF2_RECORD ?? "";
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = !RECORD && existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};
const MINE = /\/api\/(trades|rosters|leagues\?mfl)|mfl/i;
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
  if (!s) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: `no fixture for ${key}` }) });
  return route.fulfill({ status: s.status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(s.body) });
}

test.afterAll(() => {
  if (RECORD) {
    mkdirSync(dirname(FILE), { recursive: true });
    writeFileSync(FILE, JSON.stringify(saved, null, 1) + "\n");
  }
});

test.beforeEach(async ({ context, page }, info) => {
  test.skip(!RECORD && !existsSync(FILE), "no recording yet: run with IF2_RECORD (see the header)");
  await serveFixtures(context);
  await context.route(/\/api\//, answer);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `if2-${name}-${project}.png`), fullPage: true });

test("the Finder's first card is the headline, measured against the best waiver move, with the week strip", async ({ page }, info) => {
  await page.goto(`/trades?league=${encodeURIComponent(MFL)}&team=8`);
  const head = page.getByTestId("best-partner");
  await expect(head).toContainText("Best partner: Madeyes Revenge");
  await expect(head).toContainText("Chicago Bears QB");
  await expect(page.getByTestId("best-alternative")).toHaveText(/^\+14\.6 over weeks 4–7: 1\.8 more than your best waiver move \(the Atlanta Falcons defense claim gives \+12\.8/);
  await expect(page.getByTestId("finder-ordering")).toContainText("Ranked by gain beyond your best waiver move over weeks 4–7");
  const cards = page.getByTestId("partner-row");
  await expect(cards.first()).toBeVisible();
  // the first card is the headline's trade
  await expect(cards.first()).toContainText("Madeyes Revenge");
  await expect(cards.first()).toContainText("Chicago Bears QB");
  await expect(cards.first()).toContainText("Rashee Rice");
  await expect(cards.first().getByTestId("partner-demoted")).toHaveCount(0);
  // the next one is below the claim: marked and worded
  const second = cards.nth(1);
  await expect(second.getByTestId("partner-demoted")).toHaveText("Below your best waiver move.");
  await expect(second.getByTestId("partner-alternative")).toContainText("the trade does not beat it on starter points");
  // the strip: both sides, four weeks
  const strip = cards.first().getByTestId("partner-strip");
  await expect(strip).toBeVisible();
  await expect(strip.getByTestId("strip-mine").locator("td")).toHaveCount(4);
  await expect(strip.getByTestId("strip-theirs").locator("td")).toHaveCount(4);
  await expect(strip.getByTestId("strip-mine").locator("td").first()).toHaveText("+5.1");
  await noSidewaysScroll(page);
  await shot(page, "team8-finder", info.project.name);
});

test("the calculator: the review's headline trade against the claim, the strip, the raw totals not a fairness test", async ({ page }, info) => {
  await page.goto(`/trade-calc?league=${encodeURIComponent(MFL)}&team=8&partner=12&give=${encodeURIComponent("mfl:0682")}&get=10229,${encodeURIComponent("mfl:0677")}`);
  const alt = page.getByTestId("trade-alternative");
  await expect(alt).toContainText("Against your best waiver move:");
  await expect(alt).toContainText("+7.9 over weeks 4–7; the Atlanta Falcons defense claim gives +12.8 over weeks 4–7 for an open spot: the trade does not beat it on starter points.");
  const strip = page.getByTestId("trade-strip");
  await expect(strip.getByTestId("strip-mine").locator("td")).toHaveText(["+1.7", "+0.0", "+2.3", "+3.8"]);
  await expect(strip.getByTestId("strip-theirs").locator("td").first()).toHaveText("−2.0");
  await noSidewaysScroll(page);
  await shot(page, "team8-calc", info.project.name);
  await page.getByTestId("why").locator("summary").first().click();
  await expect(page.getByTestId("ros")).toContainText("Rest-of-season projected points");
  await expect(page.getByTestId("ros")).toContainText("not a fairness test");
  await expect(page.getByTestId("season-value-words")).toContainText("Season value above replacement: you give");
  await expect(page.getByTestId("sanity")).toHaveCount(0);
});
