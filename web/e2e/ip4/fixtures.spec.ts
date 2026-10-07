// Wave I-P (IP-4): the player card — the head (his picture on his team's colour, this week's projection as the one
// headline number with its range, his value), the ratings (percentiles with a stated minimum sample; a dash and the
// reason under it; the overall = the plain mean of the ratings shown), the points-against-the-projection chart (tap,
// keyboard, "Show the numbers"), the role chart (toggles), and every section the card had. A WR, an RB, a QB, a rookie
// with two games, a kicker (no ratings: the card still stands) and a defense (hand-built from the kicker's card: the
// API has no defense card — see docs/handbacks/IP-4.md); the pane. Phone at 375, desktop at 1300, dark and light;
// screenshots (JPEG, rule 12) into docs/handbacks/ip4/ (SHOTS_IP4) when set, else e2e/.out.
//
// Two modes, as e2e/in3. Default: the answers come from web/fixtures/ip4/api_ip4.json (recorded from the fixture API,
// trimmed to what the screens read), the rest from serveFixtures. IP4_LIVE=http://localhost:8964 (the fixture API
// serving web/dist): the same walk against the real server, recording those answers.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const LIVE = process.env.IP4_LIVE ?? "";
const DIR = join(import.meta.dirname, "..", "..", "fixtures", "ip4");
const RECORDED = join(DIR, "api_ip4.json");
const SHOTS = process.env.SHOTS_IP4 ?? join(import.meta.dirname, "..", ".out");
type Recorded = Record<string, { status: number; body: unknown }>;
type Rating = { key: string; rating: number | null; words: string };
type Ratings = { ratings: Rating[]; overall: number | null };

const REF = "ref:half";
const P = {
  wr: { id: "00-0039075", name: "Nacua", pos: "WR" }, // Puka Nacua: two games played of four
  rb: { id: "00-0038120", name: "Hall", pos: "RB" }, // Breece Hall (Out this week: the status chip)
  qb: { id: "00-0034796", name: "Jackson", pos: "QB" }, // Lamar Jackson
  rookie: { id: "00-0041069", name: "Young", pos: "WR" }, // Colbie Young, a 2026 rookie with two games
  k: { id: "00-0037692", name: "Aubrey", pos: "K" }, // Brandon Aubrey
};

if (LIVE) test.use({ baseURL: LIVE });

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return `${u.pathname}?${new URLSearchParams(q).toString()}`;
};
const NOT_RECORDED = new Set(["/api/session", "/api/login", "/api/ratelimit", "/api/status", "/api/leagues", "/api/account/status"]); // serveFixtures has these
const recorded: Recorded = existsSync(RECORDED) ? (JSON.parse(readFileSync(RECORDED, "utf8")) as Recorded) : {};

// what the screens read of a game row and of the players list (rule 12: recordings trimmed to the fields used)
const GAME_FIELDS = ["season", "season_type", "week", "opponent", "is_home", "played", "points", "expected_points", "target_share", "carry_share", "offense_snap_pct"];
function trim(path: string, body: unknown): unknown {
  if (/^\/api\/player\/[^/]+\/games$/.test(path)) {
    const b = body as { games: Record<string, unknown>[] };
    return { ...b, games: b.games.map((g) => Object.fromEntries(GAME_FIELDS.map((f) => [f, g[f] ?? null]))) };
  }
  if (path === "/api/players") {
    const b = body as { players?: unknown[] };
    return b.players ? { ...b, players: b.players.slice(0, 6), catalogue: undefined, presets: undefined, howto: undefined } : b;
  }
  return body;
}

async function api(context: BrowserContext): Promise<string[]> {
  const calls: string[] = [];
  await context.route(/^https?:\/\/(?!localhost)/, (route) => route.abort()); // headshots, GA: never fetched by a test
  if (LIVE) {
    await context.route(/\/api\//, async (route) => {
      const u = new URL(route.request().url());
      calls.push(u.pathname + u.search);
      try {
        const res = await route.fetch();
        if (route.request().method() === "GET" && !NOT_RECORDED.has(u.pathname)) recorded[keyOf(u)] = { status: res.status(), body: trim(u.pathname, await res.json()) };
        await route.fulfill({ response: res });
      } catch {
        /* the page closed with the request in flight */
      }
    });
    return calls;
  }
  await serveFixtures(context);
  await context.route(/\/api\//, async (route) => {
    const u = new URL(route.request().url());
    calls.push(u.pathname + u.search);
    const hit = recorded[keyOf(u)];
    if (!hit) return route.fallback();
    return route.fulfill({ status: hit.status, contentType: "application/json", body: JSON.stringify(hit.body) });
  });
  return calls;
}

async function noSideways(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "no sideways page scroll").toBeLessThanOrEqual(iw + 1);
}

async function shot(page: Page, name: string, full = false) {
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: join(SHOTS, `${name}.jpg`), type: "jpeg", quality: 70, fullPage: full });
}

test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test.afterAll(() => {
  if (!LIVE) return;
  mkdirSync(DIR, { recursive: true });
  writeFileSync(RECORDED, JSON.stringify(recorded));
});

/** the ratings route's answer as the page read it (recorded), for the numbers the test checks */
function ratingsOf(id: string): Ratings | null {
  const hit = recorded[`/api/player/${id}/ratings?`]; // fix round: asked without a league (NFL-wide)
  return (hit?.body as Ratings) ?? null;
}

async function openCard(page: Page, id: string) {
  await page.goto(`/player/${id}?league=${REF}`);
  await expect(page.getByTestId("player-header")).toBeVisible({ timeout: 30_000 });
}

for (const [kind, p] of Object.entries(P).filter(([k]) => k !== "k")) {
  test(`the card: ${kind} — head, ratings, the charts, every section`, async ({ context, page, isMobile }, info) => {
    await api(context);
    await openCard(page, p.id);
    const head = page.getByTestId("player-header");
    await expect(head.getByTestId("card-name")).toContainText(p.name.toUpperCase(), { ignoreCase: true });
    await expect(head.getByTestId("card-number")).toHaveText(/^\d+\.\d$|^—$/);
    await expect(head).toContainText("Half PPR points");
    await expect(head.getByTestId("headshot")).toBeVisible(); // the silhouette here: no outside host in a test

    // the ratings: 6–8 rows; a number 0–99 or a dash with the reason; the overall is the mean of the ones shown
    const card = page.getByTestId("card-ratings");
    await expect(card).toBeVisible();
    await expect(card.getByTestId("rating").first()).toBeVisible({ timeout: 30_000 });
    const n = await card.getByTestId("rating").count();
    expect(n).toBeGreaterThanOrEqual(6);
    expect(n).toBeLessThanOrEqual(8);
    await expect(card.getByTestId("ratings-label")).toContainText("Not a projection");
    const values = await card.getByTestId("rating-value").allTextContents();
    const shown = values.filter((v) => /^\d+$/.test(v.trim())).map(Number);
    for (const v of shown) expect(v).toBeLessThanOrEqual(99);
    const overall = (await card.getByTestId("ratings-overall").textContent()) ?? "";
    if (shown.length >= 3) expect(Number(overall.match(/\d+/)![0])).toBe(Math.round(shown.reduce((a, b) => a + b, 0) / shown.length));
    else expect(overall).toContain("—");
    if (values.some((v) => v.trim() === "—")) await expect(card.getByTestId("rating-reason").or(card.getByTestId("ratings-words")).first()).toBeVisible();
    // the screenshot before anything is opened (what a visitor sees first)
    await expect(page.getByTestId("card-points-chart")).toBeVisible({ timeout: 30_000 });
    const scheme = info.project.name === "desktop" ? (kind === "qb" ? "light" : "dark") : kind === "rb" ? "light" : "dark";
    if (scheme === "light") {
      await page.emulateMedia({ colorScheme: "light" });
    } else await page.emulateMedia({ colorScheme: "dark" });
    const pick: Record<string, string[]> = { desktop: ["wr", "qb"], phone: ["wr", "rb", "rookie"] };
    if ((pick[info.project.name] ?? []).includes(kind)) await shot(page, `ip4-${kind}-${isMobile ? 375 : 1300}-${scheme}`);
    // a row opens its definition and sample
    await card.getByTestId("rating").first().getByRole("button").click();
    await expect(card.getByTestId("rating-detail")).toBeVisible();
    await card.getByTestId("ratings-how").locator("summary").click();
    await expect(card.getByTestId("ratings-how")).toContainText("not a forecast");

    // the first chart: bars against the projection; tap / keyboard read a week; the numbers behind a summary
    const chart = page.getByTestId("card-points-chart");
    await expect(chart).toBeVisible();
    const readout = chart.getByTestId("chart-readout");
    await expect(readout).toContainText(/^Week \d+/);
    const slider = chart.getByRole("slider");
    await slider.focus();
    const before = await readout.textContent();
    await page.keyboard.press("Home");
    const first = await readout.textContent();
    await page.keyboard.press("End");
    expect(await readout.textContent()).toMatch(/^Week \d+/);
    expect(first).toMatch(/^Week \d+/);
    expect(before).toMatch(/^Week \d+/);
    const box = (await slider.locator("svg").boundingBox())!;
    if (isMobile) await page.touchscreen.tap(box.x + 40, box.y + box.height / 2);
    else await page.mouse.click(box.x + 40, box.y + box.height / 2);
    expect(await readout.textContent()).toBe(first);
    await chart.getByTestId("chart-numbers").locator("summary").click();
    await expect(chart.getByTestId("chart-numbers").locator("tbody tr").first()).toBeVisible();

    // the role chart: a toggle takes a line off
    const role = page.getByTestId("card-role");
    await expect(role).toBeVisible();
    const toggle = role.locator("[data-testid^=role-toggle-]").first();
    const pressed = await toggle.getAttribute("aria-pressed");
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-pressed", pressed === "true" ? "false" : "true");

    // the game log's chart (expected against actual) is reachable by keyboard too
    const log = page.getByTestId("game-log");
    await log.getByRole("slider").focus();
    await page.keyboard.press("End");
    await expect(log.getByTestId("chart-readout")).toContainText("Week");
    // the head's number is the Projection tile's own (one rounding on the card)
    const num = ((await head.getByTestId("card-number").textContent()) ?? "").trim();
    if (num !== "—") await expect(page.getByTestId("section-projection").getByTestId("metrics").locator("button").first()).toContainText(num);

    // fix round: the first chart sits directly under the ratings, above the sections (a phone and the page alike)
    const order = await page.locator("[data-testid=card-ratings], [data-testid=card-points], [data-testid=section-projection]").evaluateAll((els) => els.map((e) => e.getAttribute("data-testid")));
    expect(order).toEqual(["card-ratings", "card-points", "section-projection"]);
    if (isMobile) {
      const pts = (await page.getByTestId("card-points").boundingBox())!;
      const rat = (await card.boundingBox())!;
      expect(pts.y).toBeGreaterThan(rat.y + rat.height - 1);
      expect(pts.y - (rat.y + rat.height)).toBeLessThan(24);
    }

    // every section the card had is still there
    for (const s of ["projection", "availability", "value", "usage", "signals"]) await expect(page.getByTestId(`section-${s}`)).toBeVisible();
    await expect(page.getByTestId("game-log")).toBeVisible();
    await expect(page.getByTestId("player")).not.toContainText(/No league/);
    await noSideways(page);
    // at 1300 the card uses the width: the ratings and the chart side by side, the sections in columns
    if (!isMobile) {
      const r = (await card.boundingBox())!;
      const c = (await page.getByTestId("card-points").boundingBox())!;
      expect(c.x).toBeGreaterThan(r.x + r.width - 1);
      expect(Math.abs(c.y - r.y)).toBeLessThan(4);
    }
  });
}

test("the rookie with two games: dashes with the reason, never a low number", async ({ context, page }) => {
  await api(context);
  await openCard(page, P.rookie.id);
  const card = page.getByTestId("card-ratings");
  await expect(card.getByTestId("rating").first()).toBeVisible({ timeout: 30_000 });
  const rec = ratingsOf(P.rookie.id);
  const dashes = (await card.getByTestId("rating-value").allTextContents()).filter((v) => v.trim() === "—").length;
  if (rec) expect(dashes).toBe(rec.ratings.filter((r) => r.rating === null).length);
  expect(dashes).toBeGreaterThan(0);
  // not in the ranked group at all (2 targets): one line says why, for every row
  await expect(card.getByTestId("ratings-words")).toContainText(/so far; ratings start at 15\+ targets/);
  await expect(card.getByTestId("ratings-overall")).toContainText("no average yet");
});

test("a kicker: no ratings, the card still stands", async ({ context, page, isMobile }) => {
  await api(context);
  await openCard(page, P.k.id);
  await expect(page.getByTestId("card-number")).toBeVisible();
  await expect(page.getByTestId("card-ratings")).toHaveCount(0);
  await expect(page.getByTestId("section-projection")).toBeVisible();
  await expect(page.getByTestId("card-points-chart")).toBeVisible({ timeout: 30_000 });
  await noSideways(page);
  if (!isMobile) {
    await page.emulateMedia({ colorScheme: "dark" });
    await shot(page, `ip4-k-1300-dark`);
  }
});

// fix round: a defense has a card — search "Denver", pick the defense: the drawer and the full page are the card, not an
// error (its projection and range, its game, its points by week in the scoring; no ratings)
test("a defense: search Denver, pick it, its card (not an error)", async ({ context, page, isMobile }) => {
  await api(context);
  await page.goto(`/players?league=${REF}`);
  if (isMobile) await page.getByTestId("search-open").click();
  await expect(page.getByTestId("search")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("search").fill("Denver");
  const hit = page.getByTestId("search-hit").filter({ hasText: "Denver Broncos" });
  await expect(hit).toHaveCount(1, { timeout: 30_000 });
  await hit.click();
  const pane = page.getByTestId("pane");
  await expect(pane.getByTestId("pane-card")).toContainText("Broncos", { ignoreCase: true, timeout: 30_000 });
  await expect(pane.getByTestId("card-unit-mark")).toHaveText("DEN");
  await expect(pane.getByTestId("pane-ratings")).toHaveCount(0);
  await expect(pane.getByTestId("pane-points").getByTestId("card-points-chart")).toBeVisible({ timeout: 30_000 });
  await expect(pane.locator(".ll-error")).toHaveCount(0);
  await pane.getByTestId("pane-full").click();
  await expect(page).toHaveURL(/\/player\/DEN\?/);
  await expect(page.getByTestId("player-header")).toContainText("Broncos", { ignoreCase: true, timeout: 30_000 });
  await expect(page.getByTestId("card-number")).toHaveText(/^\d+\.\d$/);
  await expect(page.getByTestId("section-projection")).toBeVisible();
  await expect(page.getByTestId("card-points-chart").getByTestId("chart-readout")).toContainText(/^Week \d+/);
  await expect(page.getByTestId("game-log")).toHaveCount(0); // a unit has no player game log; its points are the chart
  await expect(page.locator(".ll-error")).toHaveCount(0);
  await noSideways(page);
  if (isMobile) {
    await page.emulateMedia({ colorScheme: "dark" });
    await shot(page, "ip4-def-375-dark");
  }
});

test("the pane: the head, the ratings and the first chart, then the sections", async ({ context, page, isMobile }, info) => {
  const calls = await api(context);
  await page.goto(`/players?league=${REF}&pane=${P.wr.id}&from=search`);
  const pane = page.getByTestId("pane");
  await expect(pane.getByTestId("pane-card")).toBeVisible({ timeout: 30_000 });
  await expect(pane.getByTestId("pane-card")).toContainText("NACUA", { ignoreCase: true });
  await expect(pane.getByTestId("pane-ratings").getByTestId("rating").first()).toBeVisible({ timeout: 30_000 });
  await expect(pane.getByTestId("pane-points").getByTestId("card-points-chart")).toBeVisible({ timeout: 30_000 });
  await expect(pane.getByTestId("pane-section-projection")).toBeVisible();
  await expect(pane.getByTestId("pane-actions")).toBeVisible();
  // fix round: in the drawer too, the first chart sits directly under the ratings, above the sections
  const order = await pane.locator("[data-testid=pane-ratings], [data-testid=pane-points], [data-testid=pane-section-projection]").evaluateAll((els) => els.map((e) => e.getAttribute("data-testid")));
  expect(order).toEqual(["pane-ratings", "pane-points", "pane-section-projection"]);
  // the ratings are asked without a league (the limiter never marks it seen: L2)
  expect(calls.some((c) => /\/ratings\?league=/.test(c))).toBe(false);
  await noSideways(page);
  if (!isMobile) {
    await page.emulateMedia({ colorScheme: "light" });
    mkdirSync(SHOTS, { recursive: true });
    await pane.screenshot({ path: join(SHOTS, "ip4-pane-1300-light.jpg"), type: "jpeg", quality: 70 }); // the pane alone (the screen under it is a trimmed recording)
  }
  void info;
});

test("the role chart carries the record's sentence when it is graded (IP-3's summary()[\"role\"]), nothing when absent", async ({ context, page }) => {
  await api(context);
  await openCard(page, P.wr.id);
  await expect(page.getByTestId("card-role-chart")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("card-role-record")).toHaveCount(0); // no record on this copy: nothing shown
  const words = "A hand-built sentence: after a role change, the share held over the next two games (n = 812).";
  await context.route(/\/api\/context\/record/, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ corner: { graded: false, n: 0, words: null }, role: { graded: true, n: 812, words } }) }),
  );
  await openCard(page, P.qb.id);
  await expect(page.getByTestId("card-role-record")).toHaveText(words, { timeout: 30_000 });
});

