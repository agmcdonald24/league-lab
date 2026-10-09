// Wave I-I (II-0, the fifth review § 1): the calculation audit on the screen.
//   * Team → "Strength by slot vs the league": one bar per starting slot (RB1 and RB2 apart, each FLEX), the player you
//     start there and his projected points against the league's average starter at the same slot (the tick) and its
//     best; the numbers on the screen are the answer's, and the best is never below a member; the group totals and the
//     usable-depth line under the bars.
//   * Trades → the partner cards: a week that loses is said ("loses 0.5 this week"), never "Nothing changes this week"
//     beside the strip's own −0.5.
// Phone at 375 (inside the phone project) and desktop at 1300.
//
// The answers are the API's own, recorded by api/tests/test_ii0.py::test_record_e2e_answers (League of Scrubs roster 2,
// MacZaddy, on the II-0 clone, week 4) into web/fixtures/ii0/api_ii0.json. Re-record:
//   cd api && II0_RECORD=1 PYTHONPATH=. uv run pytest -q tests/test_ii0.py -k record
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures, SCRUBS } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "ii0", "api_ii0.json");
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};
const SHOTS = process.env.SHOTS_DIR ?? "e2e/.out";

type League = { avg: number | null; best: number | null; rank: number | null; n: number };
type Slot = { slot: string; slot_type: string; value: number | null; empty: boolean; player: { player_name: string } | null; league: League };
type Sb = { slots: Slot[]; groups: { slot_type: string; slots: number; total: number }[]; depth: { words: string | null } };
type Partner = { partner_team: string; strip: { mine: (number | null)[] }; story: { words: string; this_week: { kind: string } } };
const body = <T,>(k: string) => saved[k]?.body as T;
const team = () => body<{ strength_by_slot: Sb }>(`/api/team?league=${SCRUBS}&team=2`);
const partners = () => body<{ partners: Partner[] }>(`/api/trades/partners?league=${SCRUBS}&team=2`);

const f1 = (x: number) => x.toFixed(1);
const ord = (n: number) => `${n}${n % 100 >= 10 && n % 100 <= 20 ? "th" : (({ 1: "st", 2: "nd", 3: "rd" }) as Record<number, string>)[n % 10] ?? "th"}`;

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return u.pathname + (q.length ? `?${new URLSearchParams(q).toString()}` : "");
};

async function answer(route: Route) {
  const u = new URL(route.request().url());
  const s = saved[keyOf(u)];
  if (!s) return route.fallback();
  return route.fulfill({ status: s.status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(s.body) });
}

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

test.beforeEach(async ({ context, page }, info) => {
  test.skip(!existsSync(FILE), "no recording yet (see the header)");
  await serveFixtures(context);
  await context.route(/\/api\//, answer);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

test("Team: strength by slot, each slot apart, the bar and the league on one metric", async ({ page }, info) => {
  await page.goto(`/team?league=${SCRUBS}&team=2`);
  const card = page.getByTestId("team-slots");
  await expect(card).toBeVisible();
  const sb = team().strength_by_slot;
  const bars = card.getByTestId("slot-bar");
  await expect(bars).toHaveCount(sb.slots.length);
  for (const s of ["RB1", "RB2", "WR1", "WR2", "FLEX1", "FLEX2"]) await expect(card.locator(`[data-slot="${s}"]`)).toHaveCount(1);
  for (const [i, s] of sb.slots.entries()) {
    const bar = bars.nth(i);
    if (s.value != null && s.league.rank) await expect(bar.getByTestId("bar-value")).toHaveText(`${f1(s.value)} · ${ord(s.league.rank)} of ${s.league.n}`);
    if (s.league.avg != null) await expect(bar.getByTestId("slot-league")).toContainText(`League average ${f1(s.league.avg)}, best ${f1(s.league.best!)}`);
    if (s.value != null) expect(s.league.best!).toBeGreaterThanOrEqual(s.value); // the best is never below a member
    if (s.player) await expect(bar).toContainText(s.player.player_name);
  }
  // the secondary lines: each position with more than one slot added up, and usable depth
  const groups = card.getByTestId("slot-groups");
  for (const g of sb.groups.filter((x) => x.slots > 1)) await expect(groups).toContainText(f1(g.total));
  if (sb.depth.words) await expect(card.getByTestId("slot-depth")).toHaveText(sb.depth.words);
  await noSidewaysScroll(page);
  await page.evaluate(() => document.fonts?.ready);
  await card.screenshot({ path: join(SHOTS, `ii0-team-slots-${info.project.name}.png`) });
});

test("Trades: a partner card whose week loses says so", async ({ page }, info) => {
  await page.goto(`/trades?league=${SCRUBS}&team=2`);
  // IT-1 (re-saved on the calculator's basis): the screen shows the credible cards, then — behind "Explore
  // alternatives", opened here — the rest (12 at most), each with the decision's story
  const all = partners().partners as (Partner & { tier?: string })[];
  const credRows = all.filter((p) => p.tier === "credible");
  const explore = all.filter((p) => p.tier !== "credible").slice(0, 12);
  await expect(page.getByTestId("best-partner")).toBeVisible();
  if (explore.length) await page.getByTestId("explore").locator("summary").first().click();
  const cards = page.getByTestId("partner-row");
  await expect(cards.first()).toBeVisible();
  const rows = [...credRows, ...explore];
  const losing = rows.filter((p) => (p.strip.mine[0] ?? 0) <= -0.05);
  expect(losing.length).toBeGreaterThan(0); // the recording's week 4: every top package costs a little now
  const reasons = await page.getByTestId("partner-reason").allTextContents();
  expect(reasons.length).toBe(rows.length); // the cards in the answer's order
  for (const [i, p] of rows.entries()) {
    if ((p.strip.mine[0] ?? 0) > -0.05) continue;
    expect(reasons[i]).not.toContain("Nothing changes this week");
    // IT-1 (re-saved): a card whose incoming player cannot play this week says that first (the screen's one reason)
    const out = (p as Partner & { get?: { player_name: string; cannot_play?: string | null }[] }).get?.find((x) => x.cannot_play);
    if (out) {
      expect(reasons[i]).toContain(`${out.player_name} cannot play this week`);
      continue;
    }
    expect(reasons[i]).toBe(p.story.words); // the strip's own numbers (trades.week_story)
  }
  await noSidewaysScroll(page);
  await cards.first().screenshot({ path: join(SHOTS, `ii0-partner-${info.project.name}.png`) });
});
