// The decision screens (plan G4) on fixtures: Waivers, Trade Finder, Team Hub, League, every one at 390 × 844 (phone)
// and 1300 × 900 (desktop) — the projects of playwright.fixtures.config.ts — in light AND dark, for the house leagues
// (dynasty roster 12, Scrubs roster 2) and the fictional Test League (team 3). Every number checked is read from the
// fixture the screen was served (web/fixtures/*.json, make_decision_fixtures.py), so "numbers equal the fixtures".
// Screenshots: SHOTS_DIR (default e2e/.out), g4_<screen>_<league>_<project>_<scheme>.png.
// The file is named fixtures.spec.ts so `npm run e2e:fixtures` (testMatch "fixtures.spec.ts") runs it with F2's.
import { expect, test, type Browser, type BrowserContext, type Page, type TestInfo } from "@playwright/test";
import { mkdirSync, readdirSync, readFileSync } from "node:fs";
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

/** A sentence's text as the screen renders it (markdown links → labels, no stars; a "  \n" line break is a <br>, no text). */
const plain = (t: string) => t.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/\*\*/g, "").replace(/ {2}\n/g, "");
type P = { sleeper_id: string };
const ids = (ps: P[]) => ps.map((x) => x.sleeper_id);
const evalFile = (league: string, team: number, partner: number, give: string[], get: string[]) =>
  `trades_evaluate_${league}_${team}_${partner}_${[...give].sort().join("-")}_${[...get].sort().join("-")}.json`;
const bestOf = (league: string, team: number) => {
  const all = fx(`trades_partners_${league}_${team}_ALL.json`);
  return all.partners.find((p: { is_best: boolean }) => p.is_best) ?? all.partners[0];
};

for (const scheme of SCHEMES) {
  test.describe(`${scheme}`, () => {
    test(`waivers: the answer first, the three strongest moves, free agents by position (${scheme})`, async ({ browser }, info) => {
      const { context, page } = await open(browser, info, scheme);
      // League of Scrubs, roster 2: real claims (G2's answer from the marts). IB-2: the answer is the first of the three
      // strongest moves; the four tiles became one lineup line; the free agents are the "All available" view
      const w = fx(`waivers_${SCRUBS}_2_ALL.json`);
      const top = w.top3[0].move;
      await page.goto(`/waivers?league=${SCRUBS}&team=2`);
      await expect(page.getByTestId("waiver-answer")).toHaveText(top.words.headline);
      expect(await isDark(page)).toBe(scheme === "dark");
      await expect(page.getByTestId("waiver-lineup")).toContainText(f1(w.lineup_value));
      const cards = page.getByTestId("top-move");
      await expect(cards).toHaveCount(w.top3.length);
      await expect(cards.first().getByTestId("claim-add")).toHaveText(w.top3[0].move.add.player_name);
      await expect(cards.first().getByTestId("claim-gain")).toHaveText(sg(w.top3[0].gain));
      await expect(cards.first().getByTestId("claim-reason")).toHaveText(w.top3[0].reason);
      await expect(page.getByTestId("waiver-move")).toHaveCount(0); // Wave G's big cards are gone
      await page.getByTestId("views-all").click();
      await expect(page).toHaveURL(/view=all/);
      // the free agents: the fixture's list, in its order, with this week's projection
      const rows = page.getByTestId("fa-row");
      await expect(rows).toHaveCount(w.free_agents.length);
      await expect(rows.first()).toContainText(w.free_agents[0].player_name);
      await expect(rows.first().getByTestId("row-value")).toHaveText(f1(w.free_agents[0].projection));
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
        // list + detail: the picked free agent on the right, as a player card
        const last = (n: string) => n.split(" ").slice(-1)[0];
        await expect(page.getByTestId("fa-detail").getByTestId("card-name")).toContainText(last(wr.free_agents[0].player_name));
        await expect(page.getByTestId("fa-detail").getByTestId("card-number")).toHaveText(f1(wr.free_agents[0].projection));
        await rows.nth(1).click({ position: { x: 300, y: 20 } });
        await expect(page.getByTestId("fa-detail").getByTestId("card-name")).toContainText(last(wr.free_agents[1].player_name));
      } else {
        await expect(page.getByTestId("fa-detail")).toBeHidden();
      }
      // dynasty roster 12: nothing beats what he has (G2's notice, the page's words)
      const d = fx(`waivers_${DYNASTY}_12_ALL.json`);
      await page.goto(`/waivers?league=${DYNASTY}&team=12&view=all`);
      await expect(page.getByTestId("waiver-answer")).toHaveText(plain(d.notice));
      await expect(page.getByTestId("top-move")).toHaveCount(0);
      await expect(page.getByTestId("fa-pos-K")).toHaveCount(0); // a league without kickers has no K tab
      await expect(page.getByTestId("fa-row")).toHaveCount(d.free_agents.length);
      await noSidewaysScroll(page);
      await shot(page, "waivers_dynasty", info, scheme);
      // the Test League (no database behind it: G2's on-demand answer)
      const t = fx(`waivers_${TEST_LEAGUE}_3_ALL.json`);
      await page.goto(`/waivers?league=${TEST_LEAGUE}&team=3&view=all`);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(`Best claims for ${t.team_name}`);
      await expect(page.getByTestId("waiver-answer")).toHaveText(plain(t.notice));
      await expect(page.getByTestId("fa-row")).toHaveCount(t.free_agents.length);
      await noSidewaysScroll(page);
      await shot(page, "waivers_test", info, scheme);
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
        await page.goto(`/team?league=${league}&team=${team}`);
        await expect(page.getByTestId("team-answer")).toHaveText(plain(t.words.lineup[0]));
        await expect(page.getByRole("heading", { level: 1 })).toHaveText(t.team_name);
        const tiles = page.getByTestId("team-tiles").getByTestId("stat-value");
        await expect(tiles.nth(0)).toHaveText(f1(t.value.lineup_value));
        await expect(tiles.nth(1)).toHaveText(f1(t.value.horizon_value));
        await expect(tiles.nth(2)).toHaveText(f1(t.value.bench_value));
        await expect(tiles.nth(3)).toHaveText(`${t.season.wins}-${t.season.losses}`);
        await expect(page.getByTestId("slot-bar")).toHaveCount(t.slot_strength.length);
        const s0 = t.slot_strength[0];
        await expect(page.getByTestId("slot-bar").first().getByTestId("bar-value")).toHaveText(`${f1(s0.top.value)} · ${ord(s0.league.rank)}`);
        await expect(page.getByTestId("week-bar")).toHaveCount(t.weekly.length);
        await expect(page.getByTestId("week-bar").first().getByTestId("bar-value")).toHaveText(
          `${f1(t.weekly[0].lineup_value)} · ${ord(t.weekly[0].league.rank)} of ${t.weekly[0].league.n}`,
        );
        await expect(page.getByTestId("league-bar")).toHaveCount(t.league.length);
        await expect(page.locator('[data-testid="league-bar"][data-yours="1"]')).toHaveCount(1);
        const starters = t.roster.filter((r: { role: string }) => r.role === "starter");
        await expect(page.getByTestId("roster-starter")).toHaveCount(starters.length);
        await expect(page.getByTestId("roster-starter").first().getByTestId("row-value")).toHaveText(f1(starters[0].value));
        await noSidewaysScroll(page);
        await shot(page, `team_${label}`, info, scheme);
      }
      await context.close();
    });

    test(`league: luck first, standings, who has been lucky, weekly ranks, moves, the draft (${scheme})`, async ({ browser }, info) => {
      const { context, page } = await open(browser, info, scheme);
      const l = fx(`league_${DYNASTY}_12.json`);
      await page.goto(`/league?league=${DYNASTY}&team=12`);
      await expect(page.getByTestId("league-answer")).toContainText(plain(l.words.headline));
      const me = l.all_play.find((r: { roster_id: number }) => r.roster_id === 12);
      await expect(page.getByTestId("standing-row")).toHaveCount(l.standings.length);
      await expect(page.getByTestId("standing-row").first()).toContainText(l.standings[0].team_name);
      await expect(page.locator('[data-testid="standing-row"][data-yours="1"]')).toContainText(`${me.wins}-${me.losses}`);
      await expect(page.getByTestId("luck-bar")).toHaveCount(l.all_play.length);
      const luckiest = [...l.all_play].sort((a, b) => b.luck_wins - a.luck_wins)[0];
      await expect(page.getByTestId("luck-bar").first()).toContainText(luckiest.team_name);
      await expect(page.getByTestId("luck-bar").first().getByTestId("bar-value")).toHaveText(`${sg(luckiest.luck_wins)} wins`);
      await expect(page.getByTestId("bench-bar")).toHaveCount(l.profiles.length);
      // weekly scoring rank: every team, best average first; your row marked
      await expect(page.getByTestId("rank-row")).toHaveCount(l.standings.length);
      await expect(page.getByTestId("rank-row").filter({ hasText: "(you)" })).toHaveCount(1);
      await expect(page.getByTestId("move").first()).toContainText(l.transactions[0].player_name);
      await expect(page.locator('[data-testid="pick"]:visible')).toHaveCount(l.standings.length * 2);
      await expect(page.getByTestId("pick").first()).toContainText(l.draft[0].player_name);
      await noSidewaysScroll(page);
      await shot(page, "league_dynasty", info, scheme);
      // the Test League (on demand from Sleeper's weeks): no profiles, no draft: the lines say so
      const t = fx(`league_${TEST_LEAGUE}_3.json`);
      await page.goto(`/league?league=${TEST_LEAGUE}&team=3`);
      await expect(page.getByTestId("league-answer")).toContainText(plain(t.words.headline));
      await expect(page.getByTestId("no-draft")).toBeVisible();
      await expect(page.getByTestId("no-profiles")).toBeVisible();
      await expect(page.getByTestId("standing-row")).toHaveCount(t.standings.length);
      await noSidewaysScroll(page);
      await shot(page, "league_test", info, scheme);
      await context.close();
    });

    test(`trades: the best partner, try it, evaluate a package, the partner finder (${scheme})`, async ({ browser }, info) => {
      const { context, page, calls } = await open(browser, info, scheme);
      const all = fx(`trades_partners_${DYNASTY}_12_ALL.json`);
      const best = bestOf(DYNASTY, 12);
      const ev = fx(evalFile(DYNASTY, 12, best.partner, ids(best.give), ids(best.get)));
      await page.goto(`/trades?league=${DYNASTY}&team=12`);
      await expect(page.getByTestId("best-partner")).toHaveText(plain(all.words.headline));
      // IA-2: "Try this trade" opens the trade calculator (its own screen) with the package in the link
      await page.getByTestId("try-best").click();
      await expect(page).toHaveURL(new RegExp(`/trade-calc\\?.*partner=${best.partner}`));
      await expect(page.getByTestId("verdict")).toHaveText(ev.verdict);
      expect(calls.evaluate.at(-1)).toEqual({ league: DYNASTY, team: 12, partner: best.partner, give: ids(best.give), get: ids(best.get) });
      const fit = page.getByTestId("fit-tiles").getByTestId("stat-value");
      await expect(fit.nth(0)).toHaveText(sg(ev.fit.this_week.mine));
      await expect(fit.nth(1)).toHaveText(sg(ev.fit.next_4.mine));
      await expect(fit.nth(2)).toHaveText(sg(ev.fit.this_week.theirs));
      await expect(fit.nth(3)).toHaveText(sg(ev.fit.next_4.theirs));
      await expect(page.getByTestId("market").getByTestId("bar-value").first()).toHaveText(String(ev.market.give));
      await expect(page.getByTestId("ros").getByTestId("bar-value").nth(1)).toHaveText(String(ev.ros.get));
      await expect(page.getByTestId("roster-size")).toHaveText(plain(ev.size_words));
      await expect(page.getByTestId("lineup-after")).toHaveCount(2);
      await noSidewaysScroll(page);
      await shot(page, "trades_dynasty", info, scheme);
      // a copied link opens the same trade
      const p2 = await context.newPage();
      await p2.goto(page.url());
      await expect(p2.getByTestId("verdict")).toHaveText(ev.verdict);
      await p2.close();
      // build one by hand (the other saved package): pick the partner, tick both sides
      const otherName = readdirSync(FIXTURES).find((f) => f.startsWith(`trades_evaluate_${DYNASTY}_12_`) && f !== evalFile(DYNASTY, 12, best.partner, ids(best.give), ids(best.get)))!;
      const other = fx(otherName);
      await page.getByTestId("partner").selectOption(String(other.partner));
      await expect(page).toHaveURL(new RegExp(`partner=${other.partner}`));
      for (const id of ids(best.give)) {
        if (!ids(other.give).includes(id)) await page.locator(`[data-testid="give-option"][data-id="${id}"] input`).uncheck();
      }
      for (const id of ids(other.give)) await page.locator(`[data-testid="give-option"][data-id="${id}"] input`).check();
      for (const id of ids(other.get)) await page.locator(`[data-testid="get-option"][data-id="${id}"] input`).check();
      await expect(page.getByTestId("verdict")).toHaveText(other.verdict);
      // the partner finder: who has a RB for me (back on the Trades screen)
      const rb = fx(`trades_partners_${DYNASTY}_12_RB.json`);
      await page.goto(`/trades?league=${DYNASTY}&team=12`);
      await page.getByTestId("want-RB").click();
      await expect(page).toHaveURL(/want=RB/);
      await expect(page.getByTestId("partner-row")).toHaveCount(Math.min(12, rb.partners.length));
      await expect(page.getByTestId("partner-row").first()).toContainText(rb.partners[0].partner_team);
      await noSidewaysScroll(page);
      // the Test League (on demand): the best partner's trade
      const tb = bestOf(TEST_LEAGUE, 3);
      const tev = fx(evalFile(TEST_LEAGUE, 3, tb.partner, ids(tb.give), ids(tb.get)));
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
    ["sub-trade-calc", "trade-calc"], // ---- IA-2: the trade calculator, its own link
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
