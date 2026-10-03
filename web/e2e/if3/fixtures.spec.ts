// Wave I-F (IF-3): the decision-quality review § Priority 1 on fixtures — Jameson Williams vs Bhayshul Tuten (League of
// Scrubs roster 6, week 4): Carolina's history against receivers next to its corners now (Jaycee Horn and Mike Jackson
// on injured reserve), on Compare and in the pane's matchup section (the Projection section, under "Next:"). Phone at
// 375 px (inside the phone project) and desktop at 1300.
//
// The answers are the API's own, recorded from a live API on the main-database clone (2026-09-26) with the as-of ESPN
// overlay fixture (api/tests/fixtures/espn_if3: Horn and Jackson IR, Sep 30) into web/fixtures/if3/api_if3.json and
// replayed here; team and manager names in the recording are replaced by "Team <roster>" / "Manager <roster>".
// Re-record:
//   (api on :8752: LEAGUE_LAB_ESPN_FIXTURES=api/tests/fixtures/espn_if3, the Sleeper / MFL fixtures, a player-id csv with
//    the two corners' rows, the gate off)
//   IF3_RECORD=http://127.0.0.1:8752 FIXTURES_PORT=8620 npm run e2e:fixtures -- e2e/if3
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { serveFixtures, SCRUBS } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "if3", "api_if3.json");
const RECORD = process.env.IF3_RECORD ?? "";
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = !RECORD && existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};
const WILLIAMS = "00-0037240";
const TUTEN = "00-0040719";
const MINE = new RegExp(`/api/(compare|player/${WILLIAMS}$)`);

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return u.pathname + (q.length ? `?${new URLSearchParams(q).toString()}` : "");
};

// the house league's team and manager names never enter the repository: "Team <roster>" / "Manager <roster>"
function names(v: unknown, out: Map<string, string>): Map<string, string> {
  if (Array.isArray(v)) v.forEach((x) => names(x, out));
  else if (v && typeof v === "object") {
    const o = v as Record<string, unknown>;
    const rid = o.rostered_by_roster_id ?? "?";
    if (typeof o.rostered_by_team === "string" && o.rostered_by_team) out.set(o.rostered_by_team, `Team ${rid}`);
    const h = typeof o.header === "string" ? o.header.match(/ on \*\*([^*]+)\*\* \(([^)]+)\)/) : null;   // the card
    if (h) out.set(h[1], `Team ${rid}`).set(h[2], `Manager ${rid}`);
    for (const x of Object.values(o)) names(x, out);
  } else if (typeof v === "string") {
    for (const m of v.matchAll(/\*\*([^*]+)\*\* \(([^)]+)\)/g)) if (out.has(m[1])) out.set(m[2], out.get(m[1])!.replace("Team", "Manager"));
  }
  return out;
}
function scrub(v: unknown, map: Map<string, string>): unknown {
  if (Array.isArray(v)) return v.map((x) => scrub(x, map));
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v as Record<string, unknown>).map(([k, x]) => [k, scrub(x, map)]));
  if (typeof v === "string") return [...map].reduce((s, [a, b]) => s.split(a).join(b), v);
  return v;
}

async function answer(route: Route) {
  const u = new URL(route.request().url());
  if (!MINE.test(u.pathname)) return route.fallback();
  const key = keyOf(u);
  if (RECORD) {
    const r = await fetch(RECORD + u.pathname + u.search);
    const raw = (await r.json()) as unknown;
    const map = names(raw, names(raw, new Map()));
    const body = scrub(raw, map);
    saved[key] = { status: r.status, body };
    return route.fulfill({ status: r.status, contentType: "application/json", body: JSON.stringify(body) });
  }
  const s = saved[key];
  if (!s) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: `no fixture for ${key}` }) });
  return route.fulfill({ status: s.status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(s.body) });
}

test.afterAll(() => {
  if (RECORD) {
    const map = names(saved, names(saved, new Map()));
    mkdirSync(dirname(FILE), { recursive: true });
    writeFileSync(FILE, JSON.stringify(scrub(saved, map), null, 1) + "\n");
  }
});

test.beforeEach(async ({ context, page }, info) => {
  test.skip(!RECORD && !existsSync(FILE), "no recording yet: run with IF3_RECORD (see the header)");
  await serveFixtures(context);
  await context.route(/\/api\//, answer);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `if3-${name}-${project}.png`), fullPage: true });

test("Compare: Carolina's history with the corners it was earned with, the replacements, the forecast's treatment", async ({ page }, info) => {
  await page.goto(`/compare?league=${SCRUBS}&team=6&a=${WILLIAMS}&b=${TUTEN}`);
  const ev = page.getByTestId("compare-evidence-a");
  await expect(ev).toBeVisible();
  await expect(ev.getByTestId("evidence-flag")).toHaveText("Corners changed");
  const hist = ev.getByTestId("evidence-history");
  await expect(hist).toContainText("Carolina gives up the");
  await expect(hist).toContainText("not adjusted for the offenses it faced");
  await expect(hist).toContainText("Jackson and Horn are on injured reserve (ESPN, Sep 30)");
  await expect(hist).toContainText("Evans");
  await expect(hist).toContainText("unranked");
  const impl = ev.getByTestId("evidence-implication");
  await expect(impl).toContainText("less representative this week (both starting corners changed)");
  await expect(impl).toContainText("does not settle a close call");
  await expect(impl).toContainText("contextual only; not in the forecast");
  await expect(page.getByTestId("compare-corners-changed")).toHaveCount(1);
  // the evidence behind it, one tap away: the missing corners with the source and date, who starts, the forecast's inputs
  await page.getByTestId("compare-evidence-a").getByText("The evidence").click();
  await expect(ev.getByTestId("evidence-missing")).toHaveCount(2);
  await expect(ev.getByTestId("evidence-missing").first()).toContainText("IR · ESPN, Sep 30");
  await expect(ev.getByTestId("evidence-expected")).toContainText("Akayleb Evans (left, for Mike Jackson): unranked (insufficient snaps)");
  await expect(ev.getByTestId("evidence-forecast")).toContainText("none of them says who plays corner");
  // Tuten's side: the history only, no flag
  const b = page.getByTestId("compare-evidence-b");
  await expect(b).toBeVisible();
  await expect(b.getByTestId("evidence-flag")).toHaveCount(0);
  await noSidewaysScroll(page);
  await shot(page, "compare", info.project.name);
});

test("the pane's matchup section: the two sentences under Next:", async ({ page }, info) => {
  await page.goto(`/compare?league=${SCRUBS}&team=6&a=${WILLIAMS}&b=${TUTEN}&pane=${WILLIAMS}&from=compare`);
  const proj = page.getByTestId("pane-section-projection");
  await expect(proj).toBeVisible();
  await expect(proj).toContainText("Corners changed.");
  await expect(proj).toContainText("Jackson and Horn are on injured reserve (ESPN, Sep 30)");
  await expect(proj).toContainText("contextual only; not in the forecast");
  const text = await proj.innerText();
  expect(text.indexOf("Next: week"), "the evidence sits under the Next: line").toBeLessThan(text.indexOf("Corners changed."));
  await noSidewaysScroll(page);
  await proj.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `if3-pane-projection-${info.project.name}.png`) });
});
