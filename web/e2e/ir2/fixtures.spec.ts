// Wave I-R (IR-2): one trade verdict — the dependability review's two live failures on the Folk package (League of
// Scrubs, MacZaddy gives Nick Folk to Run Bijan Run for Matthew Stafford + Will Reichard, Next 4):
//   1. the dial, the tiles and the "Worth proposing?" card disagreed (two bases on one page): every primary number is
//      now the answer's `decision` — the card's effects are the tiles' numbers, the recommendation is said once;
//   2. "It takes over their K from Matthew Stafford" (the first incoming starter paired with the first outgoing one) and
//      two depth sentences that disagreed: the dial's line pairs the players of each slot, and the backup line and the
//      card's depth line are one sentence.
// Phone 375 and desktop 1300, no sideways scroll; screenshots (JPEG) to SHOTS_DIR.
//
// The answers are the API's own, recorded from a fixture API on the fixtures' database (pinned clock) into
// web/fixtures/ir2/api_ir2.json and replayed here — the e2e needs no outside host. Re-record:
//   (api on :8962 — docs/STATUS.md § "Wave I-R", IR-2 § Commands)
//   IR2_RECORD=http://127.0.0.1:8962 FIXTURES_PORT=8927 npx playwright test --config playwright.fixtures.config.ts e2e/ir2
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { serveFixtures } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "ir2", "api_ir2.json");
const RECORD = process.env.IR2_RECORD ?? "";
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};
const SCRUBS = "1389709692405551104";
const MINE = /\/api\/(trades|rosters|team\b|teams)|1389709692405551104/i;
const WAIT = RECORD ? 600_000 : 10_000;
test.setTimeout(RECORD ? 1_200_000 : 60_000);

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
  test.skip(!RECORD && !existsSync(FILE), "no recording yet: run with IR2_RECORD (see the header)");
  await serveFixtures(context);
  await context.route(/\/api\//, answer);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `ir2-${name}-${project}.jpg`), fullPage: true, type: "jpeg", quality: 70 });

// the signed one-decimal number a sentence or a tile shows ("+0.5", "-1.3"); "no change" reads as 0
const num = (t: string) => (/no change/.test(t) ? 0 : Number((t.replace(/\u2212/g, "-").match(/[+-]\d+\.\d/) ?? ["NaN"])[0]));

test("Folk for Stafford + Reichard: one basis, the slots paired, one depth sentence", async ({ page }, info) => {
  await page.goto(`/trade-calc?league=${SCRUBS}&team=2&partner=3&give=650&get=421,11792`);
  const result = page.getByTestId("trade-result");
  await expect(result).toBeVisible({ timeout: WAIT });

  // (2) the dial's line pairs the players of each slot of Run Bijan Run's lineup
  const need = page.getByTestId("dial-need");
  await expect(need).toContainText("Folk at their K in place of Reichard");
  await expect(need).toContainText("at their QB in place of Stafford");
  await expect(need).not.toContainText("K from");

  // (1) the tiles, the card and the recommendation read one basis
  const tiles = page.getByTestId("fit-tiles");
  const tileTexts = await tiles.innerText();
  const card = page.getByTestId("calc-trade-card");
  const yourEffect = await card.getByTestId("card-your-effect").innerText();
  const theirEffect = await card.getByTestId("card-their-effect").innerText();
  const tileNums = (tileTexts.replace(/\u2212/g, "-").match(/[+-]\d+\.\d|no change/g) ?? []).map(num);
  // the four tiles' values: you this week, you window, them this week, them window (the captions are totals, unsigned)
  expect(tileNums.length).toBeGreaterThanOrEqual(4);
  const [youWeek, youWin, themWeek, themWin] = tileNums;
  // IT-1: one minus sign — the card's sentences say a negative number as the tiles do ("−0.3", never "-0.3")
  const sgn = (x: number) => `${x > 0 ? "+" : "\u2212"}${Math.abs(x).toFixed(1)}`;
  expect(yourEffect).toContain(youWeek === 0 ? "no change this week" : `${sgn(youWeek)} this week`);
  expect(yourEffect).toContain(youWin === 0 ? "no change over" : `${sgn(youWin)} over weeks`);
  expect(theirEffect).toContain(themWeek === 0 ? "no change this week" : `${sgn(themWeek)} this week`);
  expect(theirEffect).toContain(themWin === 0 ? "no change over" : `${sgn(themWin)} over weeks`);
  for (const t of [yourEffect, theirEffect, await page.getByTestId("verdict").innerText(), await page.getByTestId("recommendation").innerText()])
    expect(t, "a hyphen as a minus sign").not.toMatch(/(^|[\s(])-\d/);
  // IT-1: the tiles say which total they are, the roster-only total other screens show named beside them
  await expect(page.getByTestId("tile-totals")).toContainText("as My Team shows it");
  // the dial's label agrees with their tile (the review's "Improves it" beside a card that says they lose)
  const label = await page.getByTestId("dial-row").innerText();
  if (themWin < -0.05) expect(label).toContain("Makes their lineup weaker");
  if (themWin > 2) expect(label).toMatch(/Improves/);
  await expect(page.getByTestId("basis")).toContainText("Against realistic replacements");
  const rec = (await page.getByTestId("recommendation").innerText()).split(":")[0];
  await expect(page.getByTestId("calc-card")).toContainText(`Worth proposing? ${rec}`);

  // (2) one depth definition: the backup line and the card's depth line are one sentence
  const backup = (await page.getByTestId("trade-backup").innerText()).replace(/^Backup coverage: /, "").replace(/\.$/, "");
  const depth = await card.getByTestId("card-depth").innerText();
  expect(depth.toLowerCase()).toContain(backup.split(";")[0].toLowerCase());
  expect(backup).toContain("who can play in week");

  // the roster-only result is there, labelled as an explanation
  const unfilled = page.getByTestId("unfilled");
  await expect(unfilled).toContainText("If empty slots were left empty");

  await noSidewaysScroll(page);
  await shot(page, "folk", info.project.name);
});
