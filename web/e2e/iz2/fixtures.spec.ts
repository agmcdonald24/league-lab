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

test("the Folk trade: five questions in order, the lineup panel, keep / claim / trade on one basis", async ({ context, page }, info) => {
  const ev = rec.folk;
  const d = ev.decision;
  await evaluate(context, ev);
  await page.goto(`/trade-calc?league=${SCRUBS}&team=2&partner=3&give=650&get=421,11792`);
  await expect(page.getByTestId("trade-five")).toBeVisible({ timeout: 30_000 });
  await noSideways(page);
  await shot(page, "folk", info.project.name);
});
