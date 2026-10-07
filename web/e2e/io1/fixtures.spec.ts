// Wave I-O (IO-1, and its fix round): the context record on DFS. "Worth a look" is off the screen — graded on 2025 and
// 2026 weeks 1–4 it was not distinguishable from chance — and ONE quiet line under the board's intro (and a published
// slate's) says so with the record's numbers; without the record the line is not shown at all. The corner chip is
// information: never coloured, its quarter's words, its grade in the title and the row's detail. Outdoor games carry
// the forecast at kickoff (wind 20 mph in Green Bay) on a dashed chip — not in the projection. The board's answers were
// recorded from the fixture API on :8861 against league_lab_im1 (web/fixtures/io1/); the published slate is IN-4's
// recording (web/fixtures/in4/) with the record's line set the way the API sets it (the same `context_for`).
// Phone at 375 and desktop at 1300; screenshots into docs/handbacks/io1/.
import { expect, test, type BrowserContext, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const IO1 = join(import.meta.dirname, "..", "..", "fixtures", "io1");
const IN4 = join(import.meta.dirname, "..", "..", "fixtures", "in4");
const SHOTS = process.env.SHOTS_IO1 ?? join(import.meta.dirname, "..", "..", "..", "docs", "handbacks", "io1");
const read = (name: string) => readFileSync(join(IO1, name), "utf8");
const NEVER = /\b(lock|locks|guaranteed|free money|no league)\b/i;
const board = () => JSON.parse(read("projections_dk.json"));
const LINE = board().context_meta.worth_line as string;

async function dfsApi(context: BrowserContext, projections: string, slate: string | null = null) {
  await context.route(/\/api\/(dfs|context)\//, async (route: Route) => {
    const url = new URL(route.request().url());
    const send = (status: number, body: string) => route.fulfill({ status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body });
    if (url.pathname === "/api/dfs/projections") return send(200, projections);
    if (url.pathname === "/api/dfs/slates")
      return slate ? send(200, readFileSync(join(IN4, "slates_dk.json"), "utf8")) : send(200, JSON.stringify({ season: 2026, week: 4, slates: [], not_offered: [], unreadable: [] }));
    if (url.pathname === "/api/dfs/slate/2026-w05-dk-main" && slate) return send(200, slate);
    if (url.pathname === "/api/context/record") return send(200, read("context_record.json"));
    return send(404, JSON.stringify({ error: "not recorded" }));
  });
}

async function noSideways(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw).toBeLessThanOrEqual(iw);
}

async function size(page: Page, name: string) {
  if (name === "phone") await page.setViewportSize({ width: 375, height: 812 });
}

test("DFS with the record: one line instead of the list, the corner as information, the weather", async ({ page, context }, info) => {
  expect(LINE).toMatch(/^We tried a "Worth a look" list and graded it on 2025 and 2026 weeks 1–4: it listed a receiver 37 times \(in 29 games\)/);
  await serveFixtures(context);
  await dfsApi(context, read("projections_dk.json"));
  await size(page, info.project.name);
  await page.goto("/dfs");
  await expect(page.getByTestId("dfs-proj-row").first()).toBeVisible();
  // no list: one quiet line under the board's intro, the record's numbers as the API gave them
  await expect(page.getByTestId("dfs-worth")).toHaveCount(0);
  await expect(page.getByTestId("dfs-worth-line")).toHaveCount(1);
  await expect(page.getByTestId("dfs-projections").getByTestId("dfs-worth-line")).toHaveText(LINE);
  // receivers: the weather chip (dashed: not in the projection); the corner chip never coloured, its grade in the title
  await page.getByTestId("dfs-proj-pos-WR").click();
  const wx = page.locator("[data-testid=dfs-chip][data-signal=weather]").first();
  await expect(wx).toBeVisible();
  await expect(wx).toHaveAttribute("data-outside", "yes");
  await expect(wx).toHaveText(/^(Wind \d+ mph|Rain \(\d\.\d\d in\)|Snow|\d+°F)/);
  const corners = page.locator("[data-testid=dfs-chip][data-signal=corner]");
  await expect(corners.first()).toBeVisible();
  for (const c of await corners.all()) await expect(c).not.toHaveClass(/text-good|text-bad|border-good|border-bad/);
  const graded = page.locator("[data-testid=dfs-chip][data-signal=corner][data-graded=none]").first();
  await expect(graded).toHaveAttribute("title", /Graded: no measurable effect/);
  await expect(page.locator("[data-testid=dfs-chip][data-signal=corner]", { hasText: "Shutdown corner" }).first()).toBeVisible();
  const row = page.getByTestId("dfs-proj-row").filter({ has: page.locator("[data-signal=corner][data-graded=none]") }).first();
  await row.getByTestId("dfs-proj-open").click();
  await expect(row.getByTestId("dfs-signal-graded").first()).toContainText("Graded: no measurable effect");
  // what the projection holds: the corner's grade and the weather's thresholds; no "Worth a look" rule any more
  await page.getByTestId("dfs-holds").locator("summary").click();
  await expect(page.getByTestId("dfs-corner-record")).toContainText("no measurable effect either way");
  await expect(page.getByTestId("dfs-weather-honest")).toContainText("Not in the projection; outdoor games carry the forecast at kickoff");
  await expect(page.getByTestId("dfs-holds")).not.toContainText("Worth a look:");
  expect((await page.getByTestId("dfs").innerText()).match(NEVER)).toBeNull();
  await noSideways(page);
  await page.getByTestId("dfs-worth-line").scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(SHOTS, `io1-dfs-line-${info.project.name}.png`), fullPage: false });
  await row.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(SHOTS, `io1-dfs-corner-${info.project.name}.png`), fullPage: false });
});

test("A published slate with the record: the same line, no list", async ({ page, context }, info) => {
  const slate = JSON.parse(readFileSync(join(IN4, "slate_published_dk.json"), "utf8"));
  slate.context_meta = { ...(slate.context_meta ?? {}), worth_line: LINE };
  await serveFixtures(context);
  await dfsApi(context, read("projections_dk.json"), JSON.stringify(slate));
  await size(page, info.project.name);
  await page.goto("/dfs");
  await expect(page.getByTestId("dfs-slate-head")).toContainText("DraftKings classic · week 5");
  await expect(page.getByTestId("dfs-worth")).toHaveCount(0);
  await expect(page.getByTestId("dfs-worth-line")).toHaveCount(1);
  await expect(page.getByTestId("dfs-worth-line")).toHaveText(LINE);
  await noSideways(page);
  await page.screenshot({ path: join(SHOTS, `io1-dfs-slate-${info.project.name}.png`), fullPage: false });
});

test("DFS without the record: no line at all, no grade, no weather", async ({ page, context }, info) => {
  const b = board();
  b.context_meta.worth_line = null;
  b.context_meta.corner_record = null;
  b.context_meta.forecast = false;
  for (const p of b.players) {
    p.context = (p.context ?? []).filter((s: { signal: string }) => s.signal !== "weather").map((s: Record<string, unknown>) => {
      delete s.graded;
      delete s.graded_effect;
      return s;
    });
  }
  await serveFixtures(context);
  await dfsApi(context, JSON.stringify(b));
  await size(page, info.project.name);
  await page.goto("/dfs");
  await expect(page.getByTestId("dfs-proj-row").first()).toBeVisible();
  await expect(page.getByTestId("dfs-worth")).toHaveCount(0);
  await expect(page.getByTestId("dfs-worth-line")).toHaveCount(0);
  await expect(page.getByTestId("dfs")).not.toContainText("Worth a look");
  await page.getByTestId("dfs-proj-pos-WR").click();
  await expect(page.locator("[data-testid=dfs-chip][data-signal=weather]")).toHaveCount(0);
  await expect(page.locator("[data-testid=dfs-chip][data-graded=none]")).toHaveCount(0);
  await page.getByTestId("dfs-holds").locator("summary").click();
  await expect(page.getByTestId("dfs-weather-honest")).toContainText("no forecast for this week's games yet");
  await noSideways(page);
});
