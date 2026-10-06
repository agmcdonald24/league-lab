// Wave I-N (IN-4): DFS without the homework — /dfs with no file opens on the board with its context (chips, the row's
// reasons, "What the projection already holds"); with the matchup signal "Worth a look" lists receivers; a published
// slate opens on its values (no upload) and builds a stacked lineup by its id. The answers were recorded from the
// fixture API (web/fixtures/in4/*.json; the salary file is the SYNTHETIC IM-5 fixture published as 2026-w05-dk.csv).
// projections_dk_matchup.json and slate_published_dk.json carry IN-3's real matchup context, re-recorded from the merged
// tree's fixture API on :8764 (the fix round); projections_dk.json is the board without the matchup module.
// Phone at 375 and desktop at 1300; screenshots into docs/handbacks/in4/.
import { expect, test, type BrowserContext, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const IN4 = join(import.meta.dirname, "..", "..", "fixtures", "in4");
const SHOTS = process.env.SHOTS_IN4 ?? join(import.meta.dirname, "..", "..", "..", "docs", "handbacks", "in4");
const read = (name: string) => readFileSync(join(IN4, name), "utf8");
const NEVER = /\b(lock|locks|guaranteed|free money|beat|no league)\b/i;

async function dfsApi(context: BrowserContext, opts: { projections: string; published: boolean }): Promise<{ calls: string[]; bodies: string[] }> {
  const calls: string[] = [];
  const bodies: string[] = [];
  await context.route(/\/api\/dfs\//, async (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    calls.push(`${req.method()} ${url.pathname}${url.search}`);
    const send = (status: number, body: string) => route.fulfill({ status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body });
    if (url.pathname === "/api/dfs/projections") return send(200, read(opts.projections));
    if (url.pathname === "/api/dfs/slates")
      return opts.published ? send(200, read("slates_dk.json")) : send(200, JSON.stringify({ season: 2026, week: 4, slates: [], not_offered: [], unreadable: [] }));
    if (url.pathname === "/api/dfs/slate/2026-w05-dk-main" && opts.published) return send(200, read("slate_published_dk.json"));
    if (url.pathname === "/api/dfs/lineups") {
      bodies.push(req.postData() ?? "");
      return send(200, read("lineups_published_stack.json"));
    }
    return send(404, JSON.stringify({ error: "No published slate by that name for this week.", code: "not_published" }));
  });
  return { calls, bodies };
}

async function noSideways(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw).toBeLessThanOrEqual(iw);
  const { mw, cw, right } = await page.evaluate(() => {
    const m = document.querySelector("[data-testid=dfs]") as HTMLElement;
    return { mw: m.scrollWidth, cw: m.clientWidth, right: m.getBoundingClientRect().right };
  });
  expect(mw).toBeLessThanOrEqual(cw + 1);
  expect(right).toBeLessThanOrEqual(iw);
}

async function size(page: Page, name: string) {
  if (name === "phone") await page.setViewportSize({ width: 375, height: 812 });
}

test("DFS with no file: the board with its context", async ({ page, context }, info) => {
  await serveFixtures(context);
  const { calls } = await dfsApi(context, { projections: "projections_dk.json", published: false });
  await size(page, info.project.name);
  await page.goto("/dfs");
  await expect(page.getByTestId("dfs-proj-row").first()).toBeVisible();
  expect(calls.some((c) => c.startsWith("GET /api/dfs/slates?site=dk"))).toBe(true);
  // the chips: a role trend and the betting line, read from the answer; the sentence one tap away
  await expect(page.getByTestId("dfs-chip").first()).toBeVisible();
  const withChip = page.getByTestId("dfs-proj-row").filter({ has: page.getByTestId("dfs-chip") }).first();
  await withChip.getByTestId("dfs-proj-open").click();
  await expect(withChip.getByTestId("dfs-proj-detail")).toContainText("In the projection");
  // what the projection holds, said once; without IN-3's module the matchup is "not available here"
  await page.getByTestId("dfs-holds").locator("summary").click();
  await expect(page.getByTestId("dfs-holds")).toContainText("The cornerback (receivers): Not in the projection. Matchup: not available here.");
  await expect(page.getByTestId("dfs-holds")).toContainText("Context, not a forecast");
  await expect(page.getByTestId("dfs-worth-empty")).toContainText("the cornerback call is the signal the projection does not hold");
  await expect(page.getByTestId("dfs-filebox")).toBeVisible();                  // no published slate: the upload stays
  expect((await page.getByTestId("dfs").innerText()).match(NEVER)).toBeNull();
  await noSideways(page);
  await page.screenshot({ path: join(SHOTS, `in4-board-${info.project.name}.png`) });
});

test("DFS with the matchup signal: Worth a look", async ({ page, context }, info) => {
  await serveFixtures(context);
  await dfsApi(context, { projections: "projections_dk_matchup.json", published: false });
  await size(page, info.project.name);
  await page.goto("/dfs");
  const rows = page.getByTestId("dfs-worth").getByTestId("dfs-worth-row");
  await expect(rows.first()).toBeVisible();
  expect(await rows.count()).toBeGreaterThan(0);
  await expect(rows.first().getByTestId("dfs-worth-reasons")).toContainText("(not in the projection)");
  await expect(page.getByTestId("dfs-worth")).toContainText("Context, not a graded forecast");
  // a corner chip is drawn dashed: not in the projection
  await page.getByTestId("dfs-proj-pos-WR").click();
  await expect(page.locator('[data-testid=dfs-chip][data-signal=corner][data-outside=yes]').first()).toBeVisible();
  await expect(page.locator('[data-testid=dfs-chip][data-signal=defense][data-outside=no]').first()).toBeVisible();
  await noSideways(page);
  await page.screenshot({ path: join(SHOTS, `in4-worth-${info.project.name}.png`) });
});

test("DFS with a published slate: values with no upload, then a stacked lineup", async ({ page, context }, info) => {
  await serveFixtures(context);
  const { calls, bodies } = await dfsApi(context, { projections: "projections_dk_matchup.json", published: true });
  await size(page, info.project.name);
  await page.goto("/dfs");
  await expect(page.getByTestId("dfs-slate-head")).toContainText("DraftKings classic · week 5 · 15 games");
  await expect(page.getByTestId("dfs-published")).toContainText("published here so you do not have to add one");
  await expect(page.getByTestId("dfs-answer")).toContainText("597 of 599 players on the published DraftKings file valued");
  await expect(page.getByTestId("dfs-remove")).toHaveCount(0);
  await expect(page.getByTestId("dfs-worth").getByTestId("dfs-worth-row")).toHaveCount(4);   // IN-3's real context, week 5: 4 receivers
  await expect(page.getByTestId("dfs-worth")).toContainText("Ordered by points per $1,000.");
  await expect(page.getByTestId("dfs-undervalued").getByTestId("dfs-value-row")).toHaveCount(8);
  expect(calls.filter((c) => c.startsWith("POST /api/dfs/slate")).length).toBe(0);   // nothing uploaded
  await page.screenshot({ path: join(SHOTS, `in4-published-${info.project.name}.png`) });
  // the upload is the second path, in a quieter place
  await page.getByTestId("dfs-other-file").click();
  await expect(page.getByTestId("dfs-other-box").getByTestId("dfs-filebox")).toBeVisible();
  await page.getByTestId("dfs-other-file").click();
  // a stacked build: QB + 2 pass catchers, a bring-back, at most 67% of the lineups per player
  await page.getByTestId("dfs-stack-2").click();
  await page.getByTestId("dfs-bring-back").check();
  await page.getByTestId("dfs-exposure").fill("67");
  await page.getByTestId("dfs-n").fill("3");
  await page.getByTestId("dfs-build-go").click();
  await expect(page.getByTestId("dfs-lineup")).toHaveCount(3);
  await expect(page.getByTestId("dfs-build-note").first()).toContainText("Stacks: every lineup has the quarterback with at least 2 of his own pass catchers");
  const sent = JSON.parse(bodies[0]);
  expect(sent.slate_id).toBe("2026-w05-dk-main");
  expect(sent.players).toBeUndefined();
  expect(sent.stack).toEqual({ with_qb: 2, bring_back: true, no_def_vs_qb: false });
  expect(sent.max_exposure).toBe(0.67);
  const first = page.getByTestId("dfs-lineup").first();
  const qbTeam = (await first.locator("li").first().innerText()).match(/·\s([A-Z]{2,3})/)?.[1];
  expect(qbTeam).toBeTruthy();
  const teams = await first.locator("li").allInnerTexts();
  expect(teams.filter((t) => /^(WR|TE|FLEX)/.test(t.trim()) && t.includes(`· ${qbTeam}`)).length).toBeGreaterThanOrEqual(2);
  let words = await page.getByTestId("dfs").innerText();
  const names = (JSON.parse(read("slate_published_dk.json")) as { players: { name: string; player_name: string | null }[] }).players.flatMap((p) => [p.name, p.player_name ?? ""]);
  for (const nm of names.filter(Boolean).sort((a, b) => b.length - a.length)) words = words.split(nm).join(" ");
  expect(words.match(NEVER)).toBeNull();
  await noSideways(page);
  await page.getByTestId("dfs-lineups").scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(SHOTS, `in4-lineups-${info.project.name}.png`) });
});
