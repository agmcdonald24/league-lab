// Wave I-H (V-2): "Your calls this season" on the Team page — League of Scrubs roster 6 (GoodGameBuddy), weeks 1–2 of
// the sandbox clone: the sentence ("you started …; our lineup would have scored …; the best possible was …"), the
// short table (You · Ours · Best, rebuilt weeks starred, the season row adding up), the calls line, the close calls
// listed, the link to the league's record; with Sleeper's projections as a lineup a fourth column. About's record
// block links back to it. At 375 (phone project) and 1300 (desktop).
//
// `decisions` is the API's own, recorded from a live API on the V-2 clone (league_lab_i0a: `league-lab validate`, then
// `dbt build --select source:ops_decisions mart_decision_record mart_decision_calls`) into
// web/fixtures/v2/record_decisions_<league>_<team>.json and merged here into the record fixture. Re-record:
//   (api on :8712, the gate off)  V2_RECORD=http://localhost:8712 FIXTURES_PORT=8612 npm run e2e:fixtures -- e2e/v2
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { serveDecisions } from "../decisions-fixtures";
import { FIXTURES, SCRUBS, serveFixtures } from "../fixtures";

const TEAM = 6;
const FILE = join(FIXTURES, "v2", `record_decisions_${SCRUBS}_${TEAM}.json`);
const RECORD = process.env.V2_RECORD ?? "";
let decisions: Record<string, unknown> | null = existsSync(FILE) ? JSON.parse(readFileSync(FILE, "utf8")) : null;

interface TeamWeek { week: number; submitted: number; app: number; optimum: number; market: number | null; record_source: string }
interface TeamBlock { weeks: TeamWeek[]; season_totals: { submitted: number; app: number; optimum: number; market: number | null };
                      sentences: { season: string; calls: string | null; market: string | null } }

function answerWith(edit: (d: Record<string, unknown>) => Record<string, unknown> = (d) => d) {
  return async (route: Route) => {
    const u = new URL(route.request().url());
    if (u.searchParams.get("league") !== SCRUBS) return route.fallback();
    if (RECORD && decisions === null) {
      const r = await fetch(`${RECORD}/api/record?league=${SCRUBS}&team=${TEAM}`);
      decisions = ((await r.json()) as { decisions?: Record<string, unknown> }).decisions ?? null;
      writeFileSync(FILE, JSON.stringify(decisions, null, 1) + "\n");
    }
    const base = JSON.parse(readFileSync(join(FIXTURES, `record_${SCRUBS}.json`), "utf8")) as Record<string, unknown>;
    const team = u.searchParams.get("team");
    const d = structuredClone(decisions) as Record<string, unknown>;
    if (team !== String(TEAM)) d.team = null;            // the recording is roster 6's; another team: no block
    return route.fulfill({ status: 200, contentType: "application/json", headers: { "Cache-Control": "no-store" },
                           body: JSON.stringify({ ...base, decisions: edit(d) }) });
  };
}

test.beforeEach(async ({ context }) => {
  test.skip(!RECORD && decisions === null, "no recording yet: run with V2_RECORD (see the header)");
  await serveFixtures(context);
  await serveDecisions(context);                       // /api/team and the other decision screens' fixtures
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (name: string, project: string) => join(process.env.SHOTS_DIR ?? "e2e/.out", `v2-${name}-${project}.png`);
const one = (v: number) => v.toFixed(1);

test("Team: your calls this season, the sentence, the table adding up, the calls", async ({ page, context }, info) => {
  await context.route(/\/api\/record/, answerWith());
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`/team?league=${SCRUBS}&team=${TEAM}`);
  const card = page.getByTestId("team-calls");
  await expect(card).toBeVisible();
  await card.scrollIntoViewIfNeeded();
  const t = (decisions as { team: TeamBlock }).team;
  await expect(card.getByText("Your calls this season")).toBeVisible();
  await expect(page.getByTestId("team-calls-season")).toHaveText(t.sentences.season);
  expect(t.sentences.season).toMatch(/^Weeks 1–2: you started [\d.]+; our lineup would have scored [\d.]+; the best possible was [\d.]+\.$/);
  const rows = page.getByTestId("team-calls-table").locator("tbody tr");
  await expect(rows).toHaveCount(t.weeks.length + 1);
  await expect(rows.first().locator("td").first()).toHaveText("1*");                       // rebuilt: starred
  await expect(rows.first().locator("td").nth(1)).toHaveText(one(t.weeks[0].submitted));
  await expect(page.getByTestId("team-calls-table").locator("th")).toHaveCount(4);          // no Sleeper column yet
  const total = page.getByTestId("team-calls-total").locator("td");
  await expect(total.nth(1)).toHaveText(one(t.season_totals.submitted));
  await expect(total.nth(2)).toHaveText(one(t.season_totals.app));
  await expect(total.nth(3)).toHaveText(one(t.season_totals.optimum));
  expect(Math.abs(t.weeks.reduce((a, w) => a + w.app, 0) - t.season_totals.app)).toBeLessThan(0.011);
  await expect(page.getByTestId("team-calls-calls")).toHaveText(t.sentences.calls ?? "");
  await page.getByTestId("team-calls-list").locator("summary").click();
  await expect(page.getByTestId("team-calls-list").locator("li").first()).toContainText("Week 1:");
  await expect(card).toContainText("Played before this record existed");
  await expect(page.getByTestId("team-calls-league")).toHaveAttribute("href", `/about?league=${SCRUBS}&team=${TEAM}`);
  await noSidewaysScroll(page);
  await card.screenshot({ path: shot("team-calls", info.project.name) });
});

test("Team: with Sleeper's projections as a lineup, a fourth column and its sentence", async ({ page, context }, info) => {
  // the clone holds no Sleeper snapshot yet (raw.sleeper_projections starts with the nightly's): the market numbers
  // here are planted in the test, the layout is what is checked
  await context.route(/\/api\/record/, answerWith((d) => {
    const t = d.team as TeamBlock;
    t.weeks.forEach((w, i) => (w.market = Math.round((w.app + (i ? 3.4 : -1.2)) * 100) / 100));
    t.season_totals.market = Math.round(t.weeks.reduce((a, w) => a + (w.market ?? 0), 0) * 100) / 100;
    t.sentences.market = `Sleeper's projections as a lineup would have scored ${one(t.season_totals.market)} in weeks 1–2.`;
    return d;
  }));
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`/team?league=${SCRUBS}&team=${TEAM}`);
  const card = page.getByTestId("team-calls");
  await card.scrollIntoViewIfNeeded();
  await expect(page.getByTestId("team-calls-table").locator("th")).toHaveCount(5);
  await expect(page.getByTestId("team-calls-table").locator("th").last()).toHaveText("Sleeper");
  await expect(page.getByTestId("team-calls-market")).toContainText("Sleeper's projections as a lineup would have scored");
  await noSidewaysScroll(page);
  await card.screenshot({ path: shot("team-calls-market", info.project.name) });
});

test("Team: a team the record has no calls for shows no block", async ({ page, context }) => {
  await context.route(/\/api\/record/, answerWith());
  await page.goto(`/team?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("team-tiles")).toBeVisible();
  await expect(page.getByTestId("team-calls")).toHaveCount(0);
});

test("About: the record block links to your team's calls", async ({ page, context }, info) => {
  await context.route(/\/api\/record/, answerWith());
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`/about?league=${SCRUBS}&team=${TEAM}`);
  const link = page.getByTestId("decisions-team-link");
  await link.scrollIntoViewIfNeeded();
  await expect(link).toHaveText("Your team's calls this season ›");
  await link.click();
  await expect(page.getByTestId("team-calls")).toBeVisible();
  await noSidewaysScroll(page);
});

// Dad's league (MFL 70587, team 8 "Big Mac Attack"): About shows its lineups' record, weeks 1–3 rebuilt from MFL's own
// weekly results. The rest of the league's answers are IG-3's recording (web/fixtures/ig3/api_ig3.json); `decisions`
// was recorded from the V-2 API (:8712; the clone's MFL rows written by `league-lab validate --mfl mfl:70587` on the
// MFL fixtures) into web/fixtures/v2/record_decisions_mfl70587_8.json.
const MFL_KEY = "mfl:70587";
const IG3 = join(FIXTURES, "ig3", "api_ig3.json");
const MFL_DEC = join(FIXTURES, "v2", "record_decisions_mfl70587_8.json");

test("About: dad's league shows its lineups' record, rebuilt weeks starred", async ({ page, context }, info) => {
  test.skip(!existsSync(IG3) || !existsSync(MFL_DEC), "no IG-3 / V-2 recording");
  const saved = JSON.parse(readFileSync(IG3, "utf8")) as Record<string, { status: number; body: Record<string, unknown> }>;
  const dec = JSON.parse(readFileSync(MFL_DEC, "utf8")) as { weeks: { week: number }[]; sentences: { edge: string } };
  await context.route(/\/api\//, async (route) => {
    const u = new URL(route.request().url());
    const q = [...u.searchParams.entries()].filter(([k]) => k !== "team").sort(([a], [b]) => a.localeCompare(b));
    const key = u.pathname + (q.length ? `?${new URLSearchParams(q).toString()}` : "");
    const s = saved[key] ?? saved[u.pathname + u.search];
    if (u.pathname === "/api/record" && u.searchParams.get("league") === MFL_KEY) {
      const base = saved[`/api/record?league=${encodeURIComponent(MFL_KEY)}`]?.body ?? { league_id: MFL_KEY, available: false };
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...base, decisions: dec }) });
    }
    if (!s) return route.fallback();
    return route.fulfill({ status: s.status, contentType: "application/json", body: JSON.stringify(s.body) });
  });
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/leagues"); // IN-1: "/" without a league is the home page now; the setup screen is /leagues
  await expect(page.getByTestId("leagues")).toBeVisible();
  await page.getByTestId("platform-mfl").click(); // ---- II-5 (Wave I-I): the fantasy platform first
  await page.getByTestId("mfl-link").fill("70587");
  await page.getByTestId("mfl-go").click();
  await page.getByTestId("mfl-team").filter({ hasText: "Big Mac Attack" }).click();
  await expect(page.getByTestId("my-week")).toBeVisible();
  await page.goto(`/about?league=${encodeURIComponent(MFL_KEY)}&team=8`);
  const block = page.getByTestId("record-decisions");
  await block.scrollIntoViewIfNeeded();
  await expect(block).toBeVisible();
  await expect(page.getByTestId("decisions-edge")).toHaveText(dec.sentences.edge);
  expect(dec.sentences.edge).toMatch(/^Weeks 1–3: had every team started our lineup/);
  const rows = page.getByTestId("decisions-table").locator("tbody tr");
  await expect(rows).toHaveCount(dec.weeks.length);
  await expect(rows.first().locator("td").first()).toHaveText("1*");
  await expect(block).toContainText("Points summed over the league's 12 teams each week.");
  await expect(page.getByTestId("decisions-note")).toContainText("played before this record existed");
  await expect(page.getByTestId("decisions-team-link")).toBeVisible();
  await noSidewaysScroll(page);
  await block.screenshot({ path: shot("about-mfl", info.project.name) });
});
