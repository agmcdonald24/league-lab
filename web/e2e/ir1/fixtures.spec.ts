// Wave I-R (IR-1): nobody who cannot play is ranked, valued or projected. Hand-built snapshots on the recorded answers
// of e2e/ip2 (Rankings, "Who should I start?", Compare) and e2e/iq4 (the free calculator): the top receiver goes on
// injured reserve. Rankings: he is not in the list, he is under "Not playing" with his status, its source and time and
// the reason; "Who should I start?": "He is out" and no chance for him; the free calculator: no value for him, and the
// trade is not priced. Phone at 375 and desktop at 1300; screenshots (JPEG q70) into docs/handbacks/ir1/ (SHOTS_IR1).
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

type Recorded = Record<string, { status: number; body: unknown }>;
type Row = Record<string, unknown> & { gsis_id: string; player_name: string; rank: number };
const FX = join(import.meta.dirname, "..", "..", "fixtures");
const ip2 = JSON.parse(readFileSync(join(FX, "ip2", "api_ip2.json"), "utf8")) as Recorded;
const iq4 = JSON.parse(readFileSync(join(FX, "iq4", "api_iq4.json"), "utf8")) as Recorded;
const SHOTS = process.env.SHOTS_IR1 ?? join(import.meta.dirname, "..", ".out");
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64");
const WHY = "IR (knee - acl) · Sleeper, Sep 28";

// ---- the snapshot: the week's top receiver on injured reserve
const week = ip2["/api/rankings?league=ref%3Ahalf&limit=50&offset=0&position=WR&view=week"].body as { rows: Row[]; total: number };
const top = week.rows[0];
const out = {
  key: top.gsis_id, gsis_id: top.gsis_id, player_name: top.player_name, position: "WR", team: top.team, headshot_url: null,
  status: "IR", code: "IR", source: "Sleeper", as_of: "2026-09-28T14:00:00Z", why: WHY, out_indefinitely: true,
  words: "On injured reserve: he will not play this week, so he is not ranked.",
};
// and every receiver the recording lists as Out (ESPN's word, today): not ranked either
const ruledOut = week.rows.slice(1).filter((r) => r.report_status === "Out");
const outRows = ruledOut.map((r) => ({
  key: r.gsis_id, gsis_id: r.gsis_id, player_name: r.player_name, position: "WR", team: r.team, headshot_url: null, status: "Out",
  code: "OUT", source: "ESPN", as_of: "2026-10-08T15:00:00Z", why: "Out · ESPN, Oct 8", out_indefinitely: false,
  words: "Ruled out this week: he will not play this week, so he is not ranked.",
}));
const kept = week.rows.slice(1).filter((r) => r.report_status !== "Out");
const rankings = {
  ...week, total: week.total - 1 - ruledOut.length, not_playing: [out, ...outRows],
  not_playing_words: "Not playing this week: not ranked, not tiered.", rows: kept.map((r, i) => ({ ...r, rank: i + 1 })),
};
const START_KEY = "/api/rankings/start?ids=00-0037239%2C00-0039075&league=ref%3Ahalf";
const startRec = ip2[START_KEY].body as { players: Row[]; answer: Record<string, unknown> };
const [A, B] = [startRec.players.find((p) => p.gsis_id === "00-0037239")!, startRec.players.find((p) => p.gsis_id === "00-0039075")!];
const lastA = A.player_name.split(" ").slice(-1)[0];
const lastB = B.player_name.split(" ").slice(-1)[0];
const start = {
  ...startRec,
  players: [{ ...B, p_best: null, pct_best: null, vs: {} }],
  out: [{ ...out, key: A.gsis_id, gsis_id: A.gsis_id, player_name: A.player_name, team: A.team, words: `${lastA} is out — on injured reserve (${WHY}).` }],
  answer: { pick: B.gsis_id, runner_up: null, verdict: "out", p_vs_runner_up: null, words: `${lastA} is out — on injured reserve (${WHY}). Start ${lastB}.` },
  multi_note: null,
};
const CALC_KEY = "/api/trade-calc/free?get=00-0036555&give=00-0033873&league=ref%3Ahalf";
const calcRec = iq4[CALC_KEY].body as { give: { players: Row[] } & Record<string, unknown>; verdict: Record<string, unknown> };
const g0 = calcRec.give.players[0];
const ROS_WORDS = "On injured reserve: no return date, so no rest-of-season value.";
const calc = {
  ...calcRec,
  give: {
    ...calcRec.give, value: null, ros_points: null, low: null, high: null, sd: null, unknown: [g0.player_name],
    players: [{ gsis_id: g0.gsis_id, player_name: g0.player_name, position: g0.position, team: g0.team, value: null, ros_points: null,
      no_projection: true, out: { status: "IR", code: "IR", why: WHY, source: "Sleeper", as_of: "2026-09-28T14:00:00Z" }, why: `${ROS_WORDS} (${WHY})` }],
  },
  verdict: {
    even: null, lean: null, gap: null, low: null, high: null, one_player: null, not_priced: true,
    words: `Not priced: ${g0.player_name} — ${ROS_WORDS} (${WHY}). The calculator does not price a trade on a player who cannot play as if he were healthy — take him out, or try again when his status changes.`,
  },
};

// Compare (research.compare's IR-1 gate): his side has no projection, no rest of season, and his status
const cmpRec = ip2["/api/compare?a=00-0037239&b=00-0039075&league=ref%3Ahalf"].body as Record<string, Record<string, unknown>>;
const compare = {
  ...cmpRec,
  a: { ...cmpRec.a, projection: null, ros: null,
    availability: { status: "IR", code: "IR", why: WHY, source: "Sleeper", cannot_play: true, out_indefinitely: true, ros_words: "On injured reserve: no return date, so no rest-of-season value." } },
  verdict: `${lastA} is out — on injured reserve (${WHY}). Start ${lastB}.`,
};

async function api(context: BrowserContext): Promise<void> {
  await context.route(/^https?:\/\/(?!localhost)/, (route) => route.fulfill({ status: 200, contentType: "image/png", body: PNG }));
  await serveFixtures(context);
  await context.route(/\/api\//, async (route) => {
    const u = new URL(route.request().url());
    const send = (body: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (u.pathname === "/api/rankings" && u.searchParams.get("league") === "ref:half") return send(rankings);
    if (u.pathname === "/api/rankings/start") return send(start);
    if (u.pathname === "/api/trade-calc/free") return send(calc);
    if (u.pathname === "/api/compare") return send(compare);
    return route.fallback();
  });
}

const shot = (page: Page, name: string) => page.screenshot({ path: join(SHOTS, `${name}.jpg`), type: "jpeg", quality: 70, scale: "css", fullPage: true });
const noSideScroll = async (page: Page) => {
  const [sw, cw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(sw).toBeLessThanOrEqual(cw);
};

test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test("Rankings: a player on injured reserve is not ranked, he is under Not playing with why", async ({ context, page }, info) => {
  await api(context);
  await page.goto("/rankings?league=ref:half");
  await expect(page.getByTestId("rankings-row").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("rankings-name").filter({ hasText: top.player_name })).toHaveCount(0);
  await expect(page.getByTestId("rankings-rank").or(page.locator("[data-testid=rankings-row] .wide\\:hidden.tabnum")).first()).toBeAttached();
  const np = page.getByTestId("rankings-not-playing");
  await expect(np).toBeVisible();
  await expect(np).toContainText("Not playing");
  await expect(page.getByTestId("rankings-not-playing-row")).toHaveCount(1 + ruledOut.length);
  await expect(page.getByTestId("rankings-not-playing-row").first()).toContainText(top.player_name);
  await expect(page.getByTestId("rankings-not-playing-status").first()).toHaveText("IR");
  for (const r of ruledOut) await expect(page.getByTestId("rankings-name").filter({ hasText: r.player_name })).toHaveCount(0);
  await expect(np).toContainText(WHY);
  await expect(page.getByTestId("rankings-not-playing-words").first()).toHaveText("On injured reserve: he will not play this week, so he is not ranked.");
  await noSideScroll(page);
  await np.scrollIntoViewIfNeeded();
  await shot(page, `rankings-not-playing-${info.project.name}`);
});

test("Who should I start?: he is out — no chance, no call on him", async ({ context, page }, info) => {
  await api(context);
  await page.goto(`/compare?league=ref:half&a=${A.gsis_id}&b=${B.gsis_id}`);
  const words = page.getByTestId("compare-start-words");
  await expect(words).toBeVisible({ timeout: 30_000 });
  await expect(words).toHaveText(`${lastA} is out — on injured reserve (${WHY}). Start ${lastB}.`);
  await expect(words).toHaveAttribute("data-verdict", "out");
  await expect(page.getByTestId("compare-start-out-player")).toContainText(A.player_name);
  await expect(page.getByTestId("compare-start-out-player")).toContainText(WHY);
  await expect(page.getByTestId("compare-start-pct")).toHaveCount(0);
  await expect(page.getByTestId("compare-start-out-why")).toContainText("no chance and no call");
  await expect(page.getByTestId("compare-out")).toContainText(`${A.player_name}: ${WHY} — On injured reserve: no return date`);
  await noSideScroll(page);
  await shot(page, `start-out-${info.project.name}`);
});

test("the free calculator: no value for a player out indefinitely, and the trade is not priced", async ({ context, page }, info) => {
  await api(context);
  await page.goto(`/trade-calc?league=ref:half&give=${g0.gsis_id}&get=00-0036555`);
  await expect(page.getByTestId("ft-verdict")).toContainText(`Not priced: ${g0.player_name}`, { timeout: 30_000 });
  await expect(page.getByTestId("ft-verdict")).toContainText("as if he were healthy");
  await expect(page.getByTestId("ft-out")).toContainText(ROS_WORDS);
  await expect(page.getByTestId("ft-out")).toContainText(WHY);
  await noSideScroll(page);
  await shot(page, `free-calc-out-${info.project.name}`);
});
