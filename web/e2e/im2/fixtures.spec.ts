// Wave I-M (IM-2): the Stats tables' screen — Players · Stats as a full table, readable without clicking into anyone.
// Two views one tap apart (Key stats / Full table, in the URL, remembered on this device), the Full table's group
// headers (a <colgroup> + a header cell per group, sticky with the column row), sort (aria-sort), group toggles, every
// player ("Showing 50 of 291 — Show all", rendered in chunks), Download CSV (the API's /api/players.csv, or built in the
// browser when it answers 404), the 375 px phone (Key stats first, the sticky name column ≤ 120 px, the swipe cue, no
// sideways page scroll), the drawer from a name, a dash's reason on a tap, focus never under the sticky column; and the
// same screen on IM-1's answer shape (`group` on the catalogue rows, `full` on the presets) laid over the recording.
// Phone at 375 (inside the phone project) and desktop at 1300; screenshots light and dark (IM2_SHOTS: the folder).
//
// Recordings: web/fixtures/im2/api_im2.json (today's API on the shared database, 2026 weeks 1–4; re-record with
// web/fixtures/save_im2_fixtures.py) and web/fixtures/im2/im1_shape.json (IM-1's shape, by hand).
import { expect, test, type BrowserContext, type Locator, type Page } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures, SCRUBS } from "../fixtures";

const DIR = join(import.meta.dirname, "..", "..", "fixtures", "im2");
type Col = { id: string; label: string; short: string; available: boolean; positions: string[]; group?: string; per_game: boolean; format: string; reason: string | null };
type Row = Record<string, unknown> & { gsis_id: string; player_name: string; position: string; games: number };
type Frame = { players: Row[]; catalogue: Col[]; presets: { key: string; columns: string[]; full?: string[] }[]; total: number };
const saved: Record<string, { status: number; body: Frame }> = JSON.parse(readFileSync(join(DIR, "api_im2.json"), "utf8"));
const SHAPE = JSON.parse(readFileSync(join(DIR, "im1_shape.json"), "utf8")) as {
  groups: Record<string, string>;
  extra_columns: Col[];
  full: Record<string, string[]>;
  columns: Record<string, string[]>;
};
const keyOf = (q: Record<string, string>) => `/api/players?${new URLSearchParams(Object.entries(q).sort(([a], [b]) => a.localeCompare(b))).toString()}`;
const WRTE = saved[keyOf({ league: SCRUBS, limit: "1000", position: "WR,TE", window: "season" })].body;
const ALL = saved[keyOf({ league: SCRUBS, limit: "1000", position: "ALL", window: "season" })].body;
const PW = { gsis: "00-0038606", name: "Parker Washington" }; // a WR with a saved player card (the drawer)
const url = (extra = "") => `/players?league=${SCRUBS}&team=2${extra}`;
const SHOTS = process.env.IM2_SHOTS ?? "e2e/.out";

/** IM-1's answer: a group on every catalogue row, `full` on every preset, one new column the rows do not carry yet. */
function im1(body: Frame): Frame {
  const catalogue = [...body.catalogue.map((c) => ({ ...c, group: SHAPE.groups[c.id] })), ...SHAPE.extra_columns];
  const presets = body.presets.map((p) => ({ ...p, full: SHAPE.full[p.key], columns: SHAPE.columns[p.key] ?? p.columns }));
  return { ...body, catalogue, presets };
}

async function serve(context: BrowserContext, shape: "today" | "im1" = "today") {
  const api = await serveFixtures(context);
  await context.route(/\/api\/players\?/, (route) => {
    const u = new URL(route.request().url());
    const hit = saved[keyOf(Object.fromEntries(u.searchParams))];
    if (!hit) return route.fallback();
    const body = shape === "im1" ? im1(hit.body) : hit.body;
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  return api;
}

test.beforeEach(async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}
async function tap(page: Page, el: Locator, isMobile: boolean) {
  await el.evaluate((n) => n.scrollIntoView({ block: "center", inline: "nearest" }));
  if (isMobile) await el.tap();
  else await el.click();
}
const table = (page: Page) => page.getByTestId("players-table");
const rows = (page: Page) => table(page).getByTestId("players-table-row");
const colHeads = (page: Page) => table(page).locator('thead th[scope=col]:has([data-testid^="sort-"])'); // the sortable column headers
const pctText = (v: unknown) => (typeof v === "number" ? `${(v * 100).toFixed(1)}%` : "—");
const wrteAvailable = WRTE.catalogue.filter((c) => c.available && c.positions.some((p) => p === "WR" || p === "TE"));

test("Full table: every WR / TE column we have (> 25) under group headers; Key stats one tap away; the view in the URL and remembered", async ({ page, context, isMobile }, info) => {
  await serve(context);
  await page.goto(url("&position=WRTE"));
  await expect(rows(page).first()).toBeVisible();
  // the phone opens on Key stats, the desktop on the Full table (the PO's call)
  const opening = isMobile ? "key" : "full";
  await expect(page.getByTestId(`stats-table-view-${opening}`)).toHaveAttribute("aria-pressed", "true");
  await expect(table(page)).toHaveAttribute("data-view", opening);
  if (isMobile) {
    await expect(page.getByTestId("stats-group-row")).toHaveCount(0);
    await tap(page, page.getByTestId("stats-table-view-full"), isMobile);
    await expect(page).toHaveURL(/[?&]view=full/);
  }
  await expect(table(page)).toHaveAttribute("data-view", "full");
  // every available column for WR / TE (today's API: no `full` list, derived here), in groups
  await expect(colHeads(page)).toHaveCount(wrteAvailable.length);
  expect(wrteAvailable.length).toBeGreaterThan(25);
  const groups = page.getByTestId("stats-group-head");
  await expect(groups.first()).toHaveText("Games and points");
  const names = await groups.allTextContents();
  for (const g of ["Receiving", "Air yards", "Red zone", "Next Gen Stats", "Charting", "Snaps and routes", "Rushing"]) expect(names).toContain(g);
  expect(names.indexOf("Receiving")).toBeLessThan(names.indexOf("Rushing")); // a receiver's own stats first
  // a group header spans its columns (scope=colgroup + colspan), one <colgroup> per group
  const spans = await groups.evaluateAll((ths) => ths.map((th) => Number(th.getAttribute("colspan"))));
  expect(spans.reduce((a, b) => a + b, 0)).toBe(wrteAvailable.length);
  await expect(groups.first()).toHaveAttribute("scope", "colgroup");
  await expect(table(page).locator("colgroup[data-group]")).toHaveCount(names.length);
  // a column the app does not have is not in the Full table (routes: after the season); it stays in the picker
  await expect(page.getByTestId("sort-route_participation")).toHaveCount(0);
  await expect(page.getByTestId("sort-adot")).toBeVisible();
  // remembered on this device: a fresh visit without view= opens on the view picked last
  if (isMobile) {
    await page.goto(url("&position=WRTE"));
    await expect(table(page)).toHaveAttribute("data-view", "full");
  } else {
    await tap(page, page.getByTestId("stats-table-view-key"), isMobile);
    await expect(page).toHaveURL(/[?&]view=key/);
    await expect(table(page)).toHaveAttribute("data-view", "key");
    await expect(colHeads(page)).toHaveCount(WRTE.presets.find((p) => p.key === "wrte")!.columns.length);
    await page.goto(url("&position=WRTE"));
    await expect(table(page)).toHaveAttribute("data-view", "key");
  }
  await noSidewaysScroll(page);
  void info;
});

test("sort any column (the sorted column marked, aria-sort), then the group toggles hide and show a group's columns", async ({ page, context, isMobile }) => {
  await serve(context);
  await page.goto(url("&position=WRTE&view=full"));
  await expect(rows(page).first()).toBeVisible();
  const adot = WRTE.players
    .filter((p) => typeof p.adot === "number")
    .sort((a, b) => (b.adot as number) - (a.adot as number) || a.player_name.localeCompare(b.player_name))[0];
  await tap(page, page.getByTestId("sort-adot"), isMobile);
  await expect(page).toHaveURL(/sort=adot&dir=desc/);
  const th = table(page).locator("th", { has: page.getByTestId("sort-adot") });
  await expect(th).toHaveAttribute("aria-sort", "descending");
  await expect(page.getByTestId("sort-adot")).toContainText("▼");
  await expect(rows(page).first()).toContainText(adot.player_name);
  await expect(rows(page).first().locator('[data-col="adot"]')).toHaveText((adot.adot as number).toFixed(1));
  await expect(rows(page).first().locator('[data-col="adot"]')).toHaveClass(/ll-sorted/);
  await tap(page, page.getByTestId("sort-adot"), isMobile);
  await expect(th).toHaveAttribute("aria-sort", "ascending");
  // group toggles: Charting off → its three columns leave, the chip says so (aria-pressed, ✓ / +), back on → they return
  const chip = page.getByTestId("stats-groups").locator('[data-group="Charting"]');
  await expect(chip).toHaveAttribute("aria-pressed", "true");
  await tap(page, chip, isMobile);
  await expect(page).toHaveURL(/hide=Charting/);
  await expect(chip).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByTestId("sort-first_read_target_share")).toHaveCount(0);
  await expect(colHeads(page)).toHaveCount(wrteAvailable.length - 3);
  await expect(page.getByTestId("stats-group-head").filter({ hasText: "Charting" })).toHaveCount(0);
  await tap(page, chip, isMobile);
  await expect(page.getByTestId("sort-first_read_target_share")).toHaveCount(1);
  // the column picker on top: untick one column of the Full table
  await page.getByTestId("stats-columns").locator("summary").click();
  await page.getByTestId("col-catchable_rate").uncheck();
  await expect(page).toHaveURL(/off=catchable_rate/);
  await expect(page.getByTestId("sort-catchable_rate")).toHaveCount(0);
});

test("all the players: Showing 50 of 291 — Show all; per game and totals switch every column that has both", async ({ page, context, isMobile }) => {
  await serve(context);
  await page.goto(url("&position=WRTE&view=full"));
  await expect(rows(page)).toHaveCount(50);
  await expect(page.getByTestId("stats-showing")).toHaveText(`Showing 50 of ${WRTE.total}`);
  await tap(page, page.getByTestId("stats-show-all"), isMobile);
  await expect(page.getByTestId("stats-showing")).toHaveText(`Showing ${WRTE.total} of ${WRTE.total}`);
  // every row is in the table; past 100 only the rows near the box's visible part are in the page (the table says how
  // many: aria-rowcount, each row its aria-rowindex), and the last one comes into view at the bottom of the box
  await expect(table(page)).toHaveAttribute("data-rows", String(WRTE.total));
  await expect(table(page)).toHaveAttribute("aria-rowcount", String(WRTE.total + 2)); // + the two header rows
  const rendered = await rows(page).count();
  expect(rendered).toBeGreaterThan(20);
  expect(rendered).toBeLessThan(WRTE.total);
  const ts = (p: Row) => (typeof p.target_share === "number" ? p.target_share : null);
  const last = [...WRTE.players].sort((a, b) => {
    const av = ts(a);
    const bv = ts(b);
    if (av === null && bv === null) return a.player_name.localeCompare(b.player_name);
    if (av === null) return 1;
    if (bv === null) return -1;
    return bv - av || a.player_name.localeCompare(b.player_name);
  })[WRTE.total - 1];
  await page.getByTestId("stats-scroll").evaluate((el) => el.scrollTo({ top: el.scrollHeight }));
  await expect(rows(page).last()).toContainText(last.player_name);
  await expect(rows(page).last()).toHaveAttribute("aria-rowindex", String(WRTE.total + 2));
  await expect(rows(page).first()).not.toHaveAttribute("aria-rowindex", "3"); // the top rows left the page
  await page.getByTestId("stats-scroll").evaluate((el) => el.scrollTo({ top: 0 }));
  await expect(rows(page).first()).toHaveAttribute("aria-rowindex", "3");
  // per game ↔ totals over the whole table
  await expect(page.getByTestId("sort-receptions")).toHaveText(/REC\/G/i);
  await tap(page, page.getByTestId("mode-total"), isMobile);
  await expect(page.getByTestId("sort-receptions")).toHaveText(/^Rec(?!\/G)/i);
  await expect(page.getByTestId("sort-red_zone_targets")).not.toHaveText(/\/G/);
  await expect(page.getByTestId("sort-target_share")).toHaveText(/Tgt %/i); // a share keeps its own denominator
  // a filter starts again at the first 50
  await page.getByTestId("players-search").fill("wa");
  await expect(page.getByTestId("stats-showing")).toContainText(/^Showing \d+ of \d+$/);
});

test("Download CSV: the API's file when it has the route, else built here from the table (404 today)", async ({ page, context }) => {
  const api = await serve(context);
  await page.goto(url("&position=WR&view=full&who=fa"));
  await expect(rows(page).first()).toBeVisible();
  const link = page.getByTestId("stats-csv");
  await expect(link).toHaveAttribute("href", /^\/api\/players\.csv\?.*position=WR%2CTE.*window=season/);
  await expect(link).toHaveAttribute("href", /cols=games%2Cpoints/);
  await expect(link).toHaveAttribute("href", /who=fa/);
  // today: the route answers 404 → the file is built in the browser
  const [dl] = await Promise.all([page.waitForEvent("download"), link.click()]);
  expect(api.calls.some((c) => c.startsWith("/api/players.csv?"))).toBe(true);
  await expect(link).toHaveAttribute("data-from", "browser");
  expect(dl.suggestedFilename()).toMatch(/^isuckatfantasy-stats-2026-season-wr(-full)?\.csv$/);
  const text = readFileSync((await dl.path())!, "utf8");
  const lines = text.trim().split(/\r\n/);
  const fas = WRTE.players.filter((p) => p.position === "WR" && p.rostered_by_roster_id === null);
  expect(lines.length).toBe(fas.length + 1); // every filtered row, not the first 50
  expect(lines[0]).toMatch(/^Player,Position,NFL team,Games played,Fantasy points per game,/);
  expect(lines[0]).toContain("Target share (%)");
  expect(lines[0]).toContain("Average depth of target");
  // unknown is an empty cell, never 0
  const header = lines[0].split(",");
  const sepAt = header.indexOf("Average separation (yards)");
  const unknown = fas.find((p) => p.separation === null);
  if (unknown && sepAt > 0) {
    const line = lines.find((l) => l.startsWith(`${unknown.player_name},`))!;
    expect(line.split(",")[sepAt]).toBe("");
  }
  // with IM-1's route: its file as it answered
  await context.route(/\/api\/players\.csv\?/, (route) =>
    route.fulfill({ status: 200, headers: { "Content-Type": "text/csv; charset=utf-8", "Content-Disposition": 'attachment; filename="server-file.csv"' }, body: "Player\r\nFrom the server\r\n" }),
  );
  await page.reload();
  await expect(rows(page).first()).toBeVisible();
  const [dl2] = await Promise.all([page.waitForEvent("download"), page.getByTestId("stats-csv").click()]);
  expect(dl2.suggestedFilename()).toBe("server-file.csv");
  expect(readFileSync((await dl2.path())!, "utf8")).toContain("From the server");
  await expect(page.getByTestId("stats-csv")).toHaveAttribute("data-from", "server");
});

test("375 / 1300: the sticky name column (≤ 120 px on a phone) and header rows stay put, the swipe cue, no sideways page scroll; a name opens the drawer", async ({ page, context, isMobile }, info) => {
  await serve(context);
  await page.goto(url("&position=WR&view=full&sort=target_share&dir=desc"));
  await expect(rows(page).first()).toBeVisible();
  const box = page.getByTestId("stats-scroll");
  const nameCell = rows(page).first().locator("th").first();
  const w = (await nameCell.boundingBox())!.width;
  if (isMobile) expect(w).toBeLessThanOrEqual(120.5);
  else expect(w).toBeGreaterThan(150);
  // the phone's short name: "J. Jefferson" on screen, the whole name in the link's text and its accessible name
  const link = rows(page).first().getByRole("link");
  const full = (await link.getAttribute("aria-label"))!;
  expect((await link.textContent())!.trim()).toBe(full);
  // the swipe cue until the first sideways scroll (a phone)
  if (isMobile) await expect(page.getByTestId("stats-swipe")).toBeVisible();
  else await expect(page.getByTestId("stats-swipe")).toBeHidden();
  const before = (await nameCell.boundingBox())!;
  const groupHead = page.getByTestId("stats-group-head").nth(1);
  await box.evaluate((el) => el.scrollBy({ left: 600 }));
  await page.waitForTimeout(150);
  expect(Math.abs((await nameCell.boundingBox())!.x - before.x)).toBeLessThan(2);
  await expect(page.getByTestId("stats-swipe")).toHaveCount(0);
  // down inside the box: the group row and the column row stay at its top, the column row under the group row
  const boxTop = (await box.boundingBox())!.y;
  await box.evaluate((el) => el.scrollBy({ top: 500 }));
  await page.waitForTimeout(150);
  const g = (await groupHead.boundingBox())!;
  const h = (await page.getByTestId("sort-target_share").boundingBox())!;
  expect(Math.abs(g.y - boxTop)).toBeLessThan(3);
  expect(h.y).toBeGreaterThanOrEqual(g.y + g.height - 2);
  await noSidewaysScroll(page);
  // a name opens the drawer (lib/player-drawer.svelte.ts), the table stays
  await box.evaluate((el) => el.scrollTo({ top: 0, left: 0 }));
  await page.getByTestId("players-search").fill("parker wash");
  await expect(rows(page)).toHaveCount(1);
  await tap(page, table(page).getByRole("link", { name: PW.name, exact: true }), isMobile);
  await expect(page.getByTestId("pane")).toHaveAttribute("data-gsis", PW.gsis);
  await expect(page).toHaveURL(new RegExp(`pane=${PW.gsis}&from=list`));
  void info;
});

test("a dash keeps its reason on a tap; a small sample is greyed with its size; focus never lands under the sticky column", async ({ page, context, isMobile }) => {
  await serve(context);
  await page.goto(url("&position=WR&view=full&sort=separation&dir=asc"));
  await expect(rows(page).first()).toBeVisible();
  // sorted ascending, the unknowns come last: find one by search
  const u = WRTE.players.find((p) => p.position === "WR" && p.separation === null && (p.games ?? 0) > 0)!;
  await page.getByTestId("players-search").fill(u.player_name);
  const cell = rows(page).filter({ hasText: u.player_name }).first().locator('td[data-col="separation"]');
  await expect(cell).toHaveText("—");
  await expect(cell).toHaveAttribute("title", /unknown, not zero/);
  await expect(cell).toHaveAttribute("data-why", "");
  await tap(page, cell, isMobile);
  await expect(page.getByTestId("stats-tip")).toContainText("unknown, not zero");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("stats-tip")).toHaveCount(0);
  // a small sample: a rate on under 10 targets reads greyed, the sample in its title
  const s = WRTE.players.find((p) => p.position === "WR" && typeof p.catch_rate === "number" && (p.targets as number) < 10 && (p.targets as number) > 0)!;
  await page.getByTestId("players-search").fill(s.player_name);
  const sc = rows(page).filter({ hasText: s.player_name }).first().locator('td[data-col="catch_rate"]');
  await expect(sc).toHaveText(pctText(s.catch_rate));
  await expect(sc).toHaveClass(/text-ink-3/);
  await expect(sc).toHaveAttribute("title", new RegExp(`Small sample: ${s.targets} targets`));
  // keyboard: a header button scrolled under the sticky column comes back into view beside it
  await page.getByTestId("players-search").fill("");
  const box = page.getByTestId("stats-scroll");
  await box.evaluate((el) => el.scrollTo({ left: el.scrollWidth }));
  await page.getByTestId("sort-points").focus();
  await page.waitForTimeout(150);
  const stick = (await table(page).locator("thead .ll-corner").boundingBox())!;
  const btn = (await page.getByTestId("sort-points").boundingBox())!;
  expect(btn.x).toBeGreaterThanOrEqual(stick.x + stick.width - 1);
  const ring = await page.getByTestId("sort-points").evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(["solid", "auto"]).toContain(ring); // the focus is visible
});

test("IM-1's answer shape: the API's groups and full list win; a new column the rows do not carry yet is a dash with its reason", async ({ page, context, isMobile }) => {
  await serve(context, "im1");
  await page.goto(url("&position=WRTE&view=full"));
  await expect(rows(page).first()).toBeVisible();
  const full = SHAPE.full.wrte;
  await expect(colHeads(page)).toHaveCount(full.length);
  await expect(page.getByTestId("sort-charted_targets")).toHaveCount(0); // not in the answer's full list
  // the answer's group: yards per target is Efficiency there (Receiving in the client's own map)
  const eff = page.getByTestId("stats-group-head").filter({ hasText: "Efficiency" });
  await expect(eff).toHaveCount(1);
  const ids = await colHeads(page).evaluateAll((ths) => ths.map((th) => th.querySelector("button")?.getAttribute("data-testid")?.replace("sort-", "")));
  const effAt = ids.indexOf("yards_per_target");
  expect(ids[effAt + 1]).toBe("yac_per_reception"); // grouped together, catalogue order inside the group
  await expect(page.getByTestId("stats-group-head").filter({ hasText: "Advanced (PFR)" })).toHaveCount(1);
  const drops = rows(page).first().locator('td[data-col="pfr_drops"]');
  await expect(drops).toHaveText("—");
  await expect(drops).toHaveAttribute("title", /PFR has not charted his games yet/);
  // Key stats: the preset's own (richer) default columns
  await tap(page, page.getByTestId("stats-table-view-key"), isMobile);
  await expect(colHeads(page)).toHaveCount(SHAPE.columns.wrte.length);
  await expect(page.getByTestId("sort-adot")).toBeVisible();
  await noSidewaysScroll(page);
});

test("screenshots: 375 and 1300, light and dark (Key stats and Full table)", async ({ page, context, isMobile }, info) => {
  await serve(context);
  mkdirSync(SHOTS, { recursive: true });
  for (const scheme of ["dark", "light"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    for (const view of isMobile ? (["key", "full"] as const) : (["full"] as const)) {
      await page.goto(url(`&position=WRTE&view=${view}&sel=`));
      await expect(rows(page).first()).toBeVisible();
      await page.getByTestId("stats-toolbar").evaluate((n) => n.scrollIntoView({ block: "start" }));
      await page.evaluate(() => window.scrollBy(0, -8));
      await page.waitForTimeout(200);
      await page.screenshot({ path: join(SHOTS, `im2-${view}-${info.project.name === "phone" ? 375 : 1300}-${scheme}.png`), scale: "css" });
    }
  }
});

/** Scroll the table's box down `down` px (null: to the bottom) and across to the end over 2 s, one step a frame; the
 * frames' lengths (ms). */
async function scrollBox(down: number | null) {
  const box = document.querySelector<HTMLElement>('[data-testid="stats-scroll"]')!;
  const frames: number[] = [];
  let last = performance.now();
  const start = last;
  await new Promise<void>((ok) => {
    const step = () => {
      const now = performance.now();
      frames.push(now - last);
      last = now;
      const t = (now - start) / 2000;
      box.scrollTop = Math.min(down ?? Infinity, box.scrollHeight - box.clientHeight) * Math.min(1, t);
      box.scrollLeft = (box.scrollWidth - box.clientWidth) * Math.min(1, t);
      if (t < 1) requestAnimationFrame(step);
      else ok();
    };
    requestAnimationFrame(step);
  });
  frames.shift();
  const sorted = [...frames].sort((a, b) => a - b);
  return { frames: frames.length, p50: sorted[Math.floor(sorted.length / 2)], p95: sorted[Math.floor(sorted.length * 0.95)], max: sorted[sorted.length - 1], over50: frames.filter((f) => f > 50).length };
}

/** Chrome's main-thread totals (ms): script, style, layout, every task. */
async function metrics(cdp: import("@playwright/test").CDPSession): Promise<Record<string, number>> {
  const { metrics: ms } = (await cdp.send("Performance.getMetrics")) as { metrics: { name: string; value: number }[] };
  const pick = (n: string) => (ms.find((x) => x.name === n)?.value ?? 0) * 1000;
  return { scriptMs: pick("ScriptDuration"), styleMs: pick("RecalcStyleDuration"), layoutMs: pick("LayoutDuration"), taskMs: pick("TaskDuration") };
}

test("400 rows x 40 columns: time to show all and to scroll (a phone at 4x CPU slowdown; the desktop as is)", async ({ page, context, isMobile }, info) => {
  test.setTimeout(120_000);
  await serve(context);
  const cdp = await context.newCDPSession(page);
  if (isMobile) await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  await page.goto(url("&view=full")); // every position: 453 players x 46 columns on this recording
  await expect(rows(page)).toHaveCount(50);
  if (process.env.IM2_CSS) await page.addStyleTag({ content: process.env.IM2_CSS }); // TEMP experiment
  const cols = await colHeads(page).count();
  expect(cols).toBeGreaterThanOrEqual(40);
  const n = ALL.total;
  expect(n).toBeGreaterThanOrEqual(400);
  const baseline = await page.evaluate(scrollBox, null); // the first 50 rows top to bottom (~1,300 px/s): this machine's floor
  await page.getByTestId("stats-scroll").evaluate((el) => el.scrollTo({ top: 0, left: 0 }));
  // the longest frame from the tap on
  await page.evaluate(() => {
    const w = window as unknown as { __frames: number[] };
    w.__frames = [];
    let last = performance.now();
    const tick = (now: number) => {
      w.__frames.push(now - last);
      last = now;
      if (w.__frames.length < 2000) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
  // show all: from the tap to every row in the table (the rows near the box in the page) and a frame painted
  const renderMs = await page.evaluate(async (want) => {
    const t0 = performance.now();
    document.querySelector<HTMLButtonElement>('[data-testid="stats-show-all"]')!.click();
    await new Promise<void>((ok) => {
      const tick = () => (document.querySelector('[data-testid="players-table"]')?.getAttribute("data-rows") === String(want) ? ok() : requestAnimationFrame(tick));
      requestAnimationFrame(tick);
    });
    await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
    return performance.now() - t0;
  }, n);
  const renderFrames = await page.evaluate(() => Math.max(...(window as unknown as { __frames: number[] }).__frames.slice(1)));
  // the scroll: 2 s down and across the box, every frame's length
  await cdp.send("Performance.enable");
  const m0 = await metrics(cdp);
  const scroll = await page.evaluate(scrollBox, 3000); // a brisk thumb: 3,000 px down (~58 rows) and across in 2 s
  const m1 = await metrics(cdp);
  const work = Object.fromEntries(Object.keys(m1).map((k) => [k, Math.round(m1[k] - m0[k])])); // main-thread ms in those 2 s
  await page.getByTestId("stats-scroll").evaluate((el) => el.scrollTo({ top: 0, left: 0 }));
  const fling = await page.evaluate(scrollBox, null); // a fling: every row and column in 2 s (~12,000 px/s)
  // a re-sort of every row
  const sortMs = await page.evaluate(async () => {
    const t0 = performance.now();
    document.querySelector<HTMLButtonElement>('[data-testid="sort-targets"]')!.click();
    await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
    return performance.now() - t0;
  });
  const inPage = await rows(page).count();
  const out = { project: info.project.name, cpuSlowdown: isMobile ? 4 : 1, rows: n, columns: cols, cells: n * cols, rowsInPage: inPage, renderMs: Math.round(renderMs), renderLongestFrameMs: Math.round(renderFrames), sortMs: Math.round(sortMs), scroll, scrollWork: work, fling, baseline50Rows: baseline };
  console.log(`IM-2 timing ${JSON.stringify(out)}`);
  mkdirSync(SHOTS, { recursive: true });
  writeFileSync(join(SHOTS, `im2-timing-${info.project.name}.json`), JSON.stringify(out, null, 1) + "\n");
  expect(renderMs).toBeLessThan(isMobile ? 20_000 : 8_000); // loose: the box is shared; the hand-back states the numbers
  expect(existsSync(join(SHOTS, `im2-timing-${info.project.name}.json`))).toBe(true);
});
