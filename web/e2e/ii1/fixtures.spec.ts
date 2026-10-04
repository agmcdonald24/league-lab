// Wave I-I (II-1): credible trades — the product and analytics handoff § 2. The Finder promotes a trade only when it beats
// BOTH teams' own best alternative (empty slots filled from the free pool for both sides) and is a plausible offer; the
// rest go behind "Explore alternatives"; "No compelling trade found" is a first-class answer with its reason. Each card
// shows the plausibility label (a plausible offer / a roster-fit idea / implausible), both lineup effects, both waiver
// alternatives, why they might consider it and reasons they might refuse — never a probability. Phone 375, desktop 1300.
//
// The answers are the API's own, recorded from a fixture API (II-1's clone league_lab_i0b for League of Scrubs, the MFL
// fixtures for 70587) into web/fixtures/ii1/api_ii1.json and replayed here. Re-record:
//   (api on :8722 — scratchpad/ii1/api_ii1.sh: LEAGUE_LAB_MFL_FIXTURES / _SLEEPER_FIXTURES / _ESPN_FIXTURES / _PLAYER_IDS_CSV)
//   II1_RECORD=http://127.0.0.1:8722 FIXTURES_PORT=8622 npx playwright test --config playwright.fixtures.config.ts e2e/ii1
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { serveFixtures } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "ii1", "api_ii1.json");
const RECORD = process.env.II1_RECORD ?? "";
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = !RECORD && existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};
const MINE = /\/api\/(trades|rosters|leagues\?mfl)|mfl|1389709692405551104/i;
const MFL = "mfl:70587";
const SCRUBS = "1389709692405551104";

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
  test.skip(!RECORD && !existsSync(FILE), "no recording yet: run with II1_RECORD (see the header)");
  await serveFixtures(context);
  await context.route(/\/api\//, answer);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `ii1-${name}-${project}.png`), fullPage: true });

test("Scrubs roster 2: No compelling trade found, the reason, and the trades behind Explore alternatives", async ({ page }, info) => {
  await page.goto(`/trades?league=${SCRUBS}&team=2`);
  const head = page.getByTestId("best-partner");
  await expect(head.getByTestId("no-compelling")).toHaveText("No compelling trade found.");
  await expect(head).toContainText("is worth proposing");
  await expect(head).toContainText("Your best move:");
  await expect(page.getByTestId("try-best")).toHaveCount(0);
  await expect(page.getByTestId("finder-none")).toContainText("No compelling trade found");
  const explore = page.getByTestId("explore");
  await expect(explore).toContainText("Explore alternatives");
  await explore.locator("summary").first().click();
  await expect(page.getByTestId("explore-why")).toBeVisible();
  const cards = explore.getByTestId("partner-row");
  await expect(cards.first()).toBeVisible();
  // a compact trade card on every explored trade: the label and both sides' effects; no probability anywhere
  const card = cards.first().getByTestId("trade-card");
  await expect(card.getByTestId("card-plausibility")).toHaveText(/^(Plausible offer|A roster-fit idea|Implausible)$/);
  await expect(card.getByTestId("card-your-effect")).toContainText("Your starters:");
  await expect(card.getByTestId("card-their-effect")).toContainText("starters:");
  await expect(page.locator("main")).not.toContainText(/probab|% chance|likely to accept/i);
  await noSidewaysScroll(page);
  await shot(page, "scrubs2-finder", info.project.name);
});

test("MFL 70587 team 8: the credible trade leads, with its full card", async ({ page }, info) => {
  await page.goto(`/trades?league=${encodeURIComponent(MFL)}&team=8`);
  const head = page.getByTestId("best-partner");
  await expect(head).toContainText("Best partner:");
  const finder = page.getByTestId("finder");
  const first = finder.getByTestId("partner-row").first();
  const card = first.getByTestId("trade-card");
  await expect(card.getByTestId("card-credible")).toHaveText("Beats both teams' alternatives");
  await expect(card.getByTestId("card-alternatives")).toContainText("Yours:");
  await expect(card.getByTestId("card-alternatives")).toContainText("Theirs:");
  await expect(card.getByTestId("card-alternatives")).toContainText(/claim|first come/);
  await expect(card.getByTestId("card-consider")).toContainText("Why they might consider it");
  // the rest are behind Explore alternatives
  await expect(page.getByTestId("explore")).toContainText("Explore alternatives");
  await noSidewaysScroll(page);
  await shot(page, "mfl8-finder", info.project.name);
});

test("the calculator: a kicker for a starter is labelled implausible, from the slots and the free pool", async ({ page }, info) => {
  // Scrubs: MacZaddy's kicker (Chase McLaughlin) for Run Bijan Run's starting QB (Matthew Stafford)
  await page.goto(`/trade-calc?league=${SCRUBS}&team=2&partner=3&give=6650&get=421`);
  const card = page.getByTestId("calc-trade-card");
  await expect(card.getByTestId("card-plausibility")).toHaveText("Implausible");
  await expect(card.getByTestId("card-refuse")).toContainText("A K for a starter (Matthew Stafford)");
  await expect(card.getByTestId("card-credible")).toHaveCount(0);
  await noSidewaysScroll(page);
  await shot(page, "scrubs2-calc-k-for-qb", info.project.name);
});
