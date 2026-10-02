// The decision screens (plan G4) on fixtures: Waivers, Trade Finder, Team Hub, League, every one at 390 × 844 (phone)
// and 1300 × 900 (desktop) — the projects of playwright.fixtures.config.ts — in light AND dark, for the house leagues
// (dynasty roster 12, Scrubs roster 2) and the fictional Test League (team 3). Every number checked is read from the
// fixture the screen was served (web/fixtures/*.json, make_decision_fixtures.py), so "numbers equal the fixtures".
// Screenshots: SHOTS_DIR (default e2e/.out), g4_<screen>_<league>_<project>_<scheme>.png.
// The file is named fixtures.spec.ts so `npm run e2e:fixtures` (testMatch "fixtures.spec.ts") runs it with F2's.
import { expect, test, type Browser, type BrowserContext, type Page, type TestInfo } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { DYNASTY, FIXTURES, SCRUBS, serveFixtures, TEST_LEAGUE } from "../fixtures";
import { serveDecisions, type DecisionCalls } from "../decisions-fixtures";

const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out");
mkdirSync(SHOTS, { recursive: true });
const SCHEMES = ["light", "dark"] as const;
type Scheme = (typeof SCHEMES)[number];

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- fixture JSON, read as written
const fx = (name: string): any => JSON.parse(readFileSync(join(FIXTURES, name), "utf8"));
const f1 = (x: number) => x.toFixed(1);
const sg = (x: number) => (Math.abs(x) >= 0.05 ? `${x > 0 ? "+" : "−"}${Math.abs(x).toFixed(1)}` : "+0.0");
const ord = (n: number) => `${n}${n % 100 >= 10 && n % 100 <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;

async function open(browser: Browser, info: TestInfo, scheme: Scheme): Promise<{ context: BrowserContext; page: Page; calls: DecisionCalls }> {
  const context = await browser.newContext({ ...info.project.use, colorScheme: scheme, serviceWorkers: "block" });
  await serveFixtures(context);
  const calls = await serveDecisions(context);
  const page = await context.newPage();
  return { context, page, calls };
}

/** Nothing scrolls sideways: the page is no wider than the screen, and no element inside the screen's <main> sticks out
 * past its right edge (html / body clip overflow, so the page width alone would not show a grid track that grew). */
async function noSidewaysScroll(page: Page) {
  const { sw, iw, out } = await page.evaluate(() => {
    const iw = window.innerWidth;
    const out: string[] = [];
    const main = document.querySelector("main");
    for (const el of main ? Array.from(main.querySelectorAll<HTMLElement>("*")) : []) {
      let clipped = false;
      for (let a = el.parentElement; a && a !== main; a = a.parentElement) {
        const o = getComputedStyle(a).overflowX;
        if (o !== "visible") {
          clipped = true;
          break;
        }
      }
      const r = el.getBoundingClientRect();
      if (!clipped && r.width > 0 && r.right > iw + 1) out.push(`${el.tagName}.${el.className}`.slice(0, 80));
    }
    return { sw: document.documentElement.scrollWidth, iw, out };
  });
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
  expect(out.slice(0, 5), "elements past the screen's right edge").toEqual([]);
}

async function shot(page: Page, name: string, info: TestInfo, scheme: Scheme) {
  await page.evaluate(() => document.fonts?.ready);
  await page.screenshot({ path: join(SHOTS, `g4_${name}_${info.project.name}_${scheme}.png`), fullPage: true });
}

async function isDark(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const [r, g, b] = getComputedStyle(document.body).backgroundColor.match(/\d+/g)!.map(Number);
    return r + g + b < 120;
  });
}

for (const scheme of SCHEMES) {
  test.describe(`${scheme}`, () => {
    test(`waivers: the answer first, the moves as cards, free agents by position (${scheme})`, async ({ browser }, info) => {
      const { context, page } = await open(browser, info, scheme);
      // League of Scrubs, roster 2: real claims
      const w = fx(`waivers_${SCRUBS}_2_ALL.json`);
      const moves = w.moves.filter((m: { list_kind: string }) => m.list_kind !== "nothing");
      const top = moves.find((m: { list_kind: string }) => m.list_kind === "start_now");
      await page.goto(`/waivers?league=${SCRUBS}&team=2`);
      await expect(page.getByTestId("waiver-answer")).toHaveText(top.headline);
      expect(await isDark(page)).toBe(scheme === "dark");
      const tiles = page.getByTestId("waiver-tiles").getByTestId("stat-value");
      await expect(tiles.nth(0)).toHaveText(sg(top.weekly_gain));
      await expect(tiles.nth(1)).toHaveText(sg(top.horizon_gain));
      await expect(tiles.nth(2)).toHaveText(f1(w.lineup_value));
      const cards = page.getByTestId("waiver-move");
      const titled = moves.filter((m: { card_title: string | null }) => m.card_title);
      await expect(cards).toHaveCount(Math.min(3, titled.length));
      // the top card's sentence is the screen's answer (not repeated); the others carry their own
      await expect(cards.first().getByTestId("move-headline")).toHaveCount(0);
      if (titled.length > 1) await expect(cards.nth(1).getByTestId("move-headline")).toHaveText(titled[1].headline);
      await expect(cards.first().getByTestId("move-add")).toHaveText(titled[0].add_name);
      await expect(cards.first().getByTestId("move-drop")).toContainText(titled[0].drop_name);
      // the free agents: the fixture's list, in its order, with this week's projection
      const rows = page.getByTestId("fa-row");
      await expect(rows).toHaveCount(w.free_agents.length);
      await expect(rows.first()).toContainText(w.free_agents[0].player_name);
      await expect(rows.first().getByTestId("row-value")).toHaveText(f1(w.free_agents[0].proj_points));
      await expect(page.getByTestId("headshot").first()).toBeVisible();
      await noSidewaysScroll(page);
      await shot(page, "waivers_scrubs", info, scheme);
      // position switch: WR (URL rewritten in place)
      const wr = fx(`waivers_${SCRUBS}_2_WR.json`);
      await page.getByTestId("fa-pos-WR").click();
      await expect(page).toHaveURL(/position=WR/);
      await expect(rows).toHaveCount(wr.free_agents.length);
      await expect(rows.first()).toContainText(wr.free_agents[0].player_name);
      if (info.project.name === "desktop") {
        // list + detail: the picked free agent on the right
        await expect(page.getByTestId("fa-detail")).toContainText(wr.free_agents[0].player_name);
        await expect(page.getByTestId("fa-proj")).toHaveText(f1(wr.free_agents[0].proj_points));
        await rows.nth(1).click({ position: { x: 300, y: 20 } });
        await expect(page.getByTestId("fa-detail")).toContainText(wr.free_agents[1].player_name);
      } else {
        await expect(page.getByTestId("fa-detail")).toBeHidden();
      }
      // dynasty roster 12: nothing beats what he has (the mart's 'nothing' row)
      await page.goto(`/waivers?league=${DYNASTY}&team=12`);
      await expect(page.getByTestId("waiver-answer")).toContainText("Nothing beats what you have.");
      await expect(page.getByTestId("waiver-move")).toHaveCount(0);
      await expect(page.getByTestId("fa-row")).toHaveCount(fx(`waivers_${DYNASTY}_12_ALL.json`).free_agents.length);
      await noSidewaysScroll(page);
      await shot(page, "waivers_dynasty", info, scheme);
      // the Test League (no database behind it): the same screen
      const t = fx(`waivers_${TEST_LEAGUE}_3_ALL.json`);
      await page.goto(`/waivers?league=${TEST_LEAGUE}&team=3`);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Best claims for Fixture Falcons");
      await expect(page.getByTestId("waiver-answer")).toHaveText(t.moves.find((m: { list_kind: string }) => m.list_kind === "start_now").headline);
      await context.close();
    });

    test(`team hub: value and rank, strength by slot vs the league, the next weeks, the roster (${scheme})`, async ({ browser }, info) => {
      const { context, page } = await open(browser, info, scheme);
      for (const [league, team, label] of [
        [DYNASTY, 12, "dynasty"],
        [SCRUBS, 2, "scrubs"],
        [TEST_LEAGUE, 3, "test"],
      ] as const) {
        const t = fx(`team_${league}_${team}.json`);
        const lv = t.rankings.find((r: { measure: string }) => r.measure === "lineup_value");
        await page.goto(`/team?league=${league}&team=${team}`);
        await expect(page.getByTestId("team-answer")).toHaveText(
          `Week ${t.value.week}: your best lineup projects ${f1(t.value.lineup_value)}, ${ord(lv.league_rank)} of ${lv.n_rosters} in the league.`,
        );
        await expect(page.getByRole("heading", { level: 1 })).toHaveText(t.team_name);
        const tiles = page.getByTestId("team-tiles").getByTestId("stat-value");
        await expect(tiles.nth(0)).toHaveText(f1(t.value.lineup_value));
        await expect(tiles.nth(1)).toHaveText(f1(t.value.horizon_value));
        await expect(tiles.nth(2)).toHaveText(f1(t.value.bench_value));
        await expect(page.getByTestId("slot-bar")).toHaveCount(t.slots.length);
        await expect(page.getByTestId("slot-bar").first().getByTestId("bar-value")).toHaveText(
          `${f1(t.slots[0].top_value)} · ${ord(t.slots[0].league_rank_top_value)}`,
        );
        await expect(page.getByTestId("week-bar")).toHaveCount(t.weeks.length);
        await expect(page.getByTestId("league-bar")).toHaveCount(t.league.length);
        await expect(page.locator('[data-testid="league-bar"][data-yours="1"]')).toHaveCount(1);
        const starters = t.roster.filter((r: { role: string }) => r.role === "starter");
        await expect(page.getByTestId("roster-starter")).toHaveCount(starters.length);
        await expect(page.getByTestId("roster-starter").first().getByTestId("row-value")).toHaveText(f1(starters[0].player_value));
        await noSidewaysScroll(page);
        await shot(page, `team_${label}`, info, scheme);
      }
      await context.close();
    });

    test(`league: luck first, standings, who has been lucky, moves, the draft (${scheme})`, async ({ browser }, info) => {
      const { context, page } = await open(browser, info, scheme);
      const l = fx(`league_${DYNASTY}.json`);
      await page.goto(`/league?league=${DYNASTY}&team=12`);
      const me = l.all_play.find((r: { roster_id: number }) => r.roster_id === 12);
      const unluckier = l.all_play.filter((r: { luck_wins: number }) => r.luck_wins < me.luck_wins).length + 1;
      await expect(page.getByTestId("league-answer")).toContainText(
        me.luck_wins < 0 ? `You've been ${unluckier === 1 ? "the unluckiest" : `the ${ord(unluckier)}-unluckiest`} team by schedule (${sg(me.luck_wins)} wins)` : "luckiest",
      );
      await expect(page.getByTestId("standing-row")).toHaveCount(l.standings.length);
      await expect(page.getByTestId("standing-row").first()).toContainText(l.standings[0].team_name);
      await expect(page.locator('[data-testid="standing-row"][data-yours="1"]')).toContainText(`${me.wins}-${me.losses}`);
      await expect(page.getByTestId("luck-bar")).toHaveCount(l.all_play.length);
      const luckiest = [...l.all_play].sort((a, b) => b.luck_wins - a.luck_wins)[0];
      await expect(page.getByTestId("luck-bar").first()).toContainText(luckiest.team_name);
      await expect(page.getByTestId("luck-bar").first().getByTestId("bar-value")).toHaveText(`${sg(luckiest.luck_wins)} wins`);
      await expect(page.getByTestId("move").first()).toContainText(l.transactions[0].player_name);
      await expect(page.locator('[data-testid="pick"]:visible')).toHaveCount(l.standings.length * 2);
      await expect(page.getByTestId("pick").first()).toContainText(l.draft[0].player_name);
      await noSidewaysScroll(page);
      await shot(page, "league_dynasty", info, scheme);
      // the Test League: no draft from Sleeper, the line says so
      await page.goto(`/league?league=${TEST_LEAGUE}&team=3`);
      await expect(page.getByTestId("no-draft")).toBeVisible();
      await expect(page.getByTestId("standing-row")).toHaveCount(fx(`league_${TEST_LEAGUE}.json`).standings.length);
      await noSidewaysScroll(page);
      await shot(page, "league_test", info, scheme);
      await context.close();
    });

    test(`trades: the best partner, try it, evaluate a package, the partner finder (${scheme})`, async ({ browser }, info) => {
      const { context, page, calls } = await open(browser, info, scheme);
      const best = fx(`trades_partners_${DYNASTY}_12_ALL.json`).partners[0];
      const key = (p: { roster_id: number; give: { sleeper_id: string }[]; get: { sleeper_id: string }[] }) =>
        `trades_evaluate_${DYNASTY}_12_${p.roster_id}_${p.give.map((x) => x.sleeper_id).sort().join("-")}_${p.get.map((x) => x.sleeper_id).sort().join("-")}.json`;
      const ev = fx(key(best));
      await page.goto(`/trades?league=${DYNASTY}&team=12`);
      await expect(page.getByTestId("best-partner")).toContainText(`Best partner: ${best.team_name}.`);
      await expect(page.getByTestId("best-partner")).toContainText(`you ${sg(best.my_week)} this week and ${sg(best.my_horizon)} over ${ev.span}`);
      await expect(page.getByTestId("tick-both")).toBeVisible();
      await page.getByTestId("try-best").click();
      await expect(page).toHaveURL(new RegExp(`partner=${best.roster_id}`));
      await expect(page.getByTestId("verdict")).toHaveText(ev.verdict);
      expect(calls.evaluate.at(-1)).toEqual({
        league: DYNASTY,
        team: 12,
        partner: best.roster_id,
        give: best.give.map((x: { sleeper_id: string }) => x.sleeper_id),
        get: best.get.map((x: { sleeper_id: string }) => x.sleeper_id),
      });
      const fit = page.getByTestId("fit-tiles").getByTestId("stat-value");
      await expect(fit.nth(0)).toHaveText(sg(ev.fit.mine.week));
      await expect(fit.nth(1)).toHaveText(sg(ev.fit.mine.horizon));
      await expect(fit.nth(2)).toHaveText(sg(ev.fit.theirs.week));
      await expect(page.getByTestId("market").getByTestId("bar-value").first()).toHaveText(String(ev.market.give));
      await expect(page.getByTestId("ros").getByTestId("bar-value").nth(1)).toHaveText(String(ev.ros.get));
      await expect(page.getByTestId("lineup-after")).toHaveCount(2);
      await noSidewaysScroll(page);
      await shot(page, "trades_dynasty", info, scheme);
      // a copied link opens the same trade
      const url = page.url();
      const p2 = await context.newPage();
      await p2.goto(url);
      await expect(p2.getByTestId("verdict")).toHaveText(ev.verdict);
      await p2.close();
      // build one by hand: the second fixture's partner, tick your best player and their second-best
      const other = fx(`trades_evaluate_${DYNASTY}_12_6_11563_6813.json`);
      await page.getByTestId("partner").selectOption(String(other.partner));
      await expect(page).toHaveURL(new RegExp(`partner=${other.partner}`));
      for (const id of new Set([...ev.give.map((x: { sleeper_id: string }) => x.sleeper_id)])) {
        if (!other.give.some((x: { sleeper_id: string }) => x.sleeper_id === id)) await page.locator(`[data-testid="give-option"][data-id="${id}"] input`).uncheck();
      }
      for (const x of other.give) await page.locator(`[data-testid="give-option"][data-id="${x.sleeper_id}"] input`).check();
      for (const x of other.get) await page.locator(`[data-testid="get-option"][data-id="${x.sleeper_id}"] input`).check();
      await expect(page.getByTestId("verdict")).toHaveText(other.verdict);
      // the partner finder: who has a RB for me
      const rb = fx(`trades_partners_${DYNASTY}_12_RB.json`);
      await page.getByTestId("want-RB").click();
      await expect(page).toHaveURL(/want=RB/);
      await expect(page.getByTestId("partner-row")).toHaveCount(Math.min(12, rb.partners.length));
      await expect(page.getByTestId("partner-row").first()).toContainText(rb.partners[0].team_name);
      await noSidewaysScroll(page);
      // the Test League: the best partner's trade evaluates on its fixture
      const tb = fx(`trades_partners_${TEST_LEAGUE}_3_ALL.json`).partners[0];
      const tev = fx(
        `trades_evaluate_${TEST_LEAGUE}_3_${tb.roster_id}_${tb.give.map((x: { sleeper_id: string }) => x.sleeper_id).sort().join("-")}_${tb.get.map((x: { sleeper_id: string }) => x.sleeper_id).sort().join("-")}.json`,
      );
      await page.goto(`/trades?league=${TEST_LEAGUE}&team=3`);
      await page.getByTestId("try-best").click();
      await expect(page.getByTestId("verdict")).toHaveText(tev.verdict);
      await shot(page, "trades_test", info, scheme);
      await context.close();
    });
  });
}

test("the Decisions tab reaches the four screens (one tap, same tab)", async ({ browser, isMobile }, info) => {
  const { context, page } = await open(browser, info, "dark");
  await page.goto(`/?league=${DYNASTY}&team=12`);
  const go = async (testid: string) => (isMobile ? page.getByTestId(testid).first().tap() : page.getByTestId(testid).first().click());
  await go("tab-decisions");
  await expect(page).toHaveURL(new RegExp(`/waivers\\?league=${DYNASTY}&team=12`));
  await expect(page.getByTestId("waivers")).toBeVisible();
  for (const [sub, screen] of [
    ["sub-trades", "trades"],
    ["sub-team", "team"],
    ["sub-league", "league"],
  ] as const) {
    await go(sub);
    await expect(page.getByTestId(screen)).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/${screen}\\?league=${DYNASTY}&team=12`));
  }
  expect(context.pages()).toHaveLength(1);
  await context.close();
});
