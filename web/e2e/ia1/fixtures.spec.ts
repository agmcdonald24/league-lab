// Wave I-A (IA-1) on fixtures: "say it like a person would". My Week (short names and headshots in the slot list, the
// plain lineup header, a card's reason sentence over its small print), Trends (below / above expectation, the work a
// game per row, the reason), Matchups (receivers only under a real section title), Compare ("Choose a player"). The
// answers are web/fixtures/*.json (brought to the new shapes by web/fixtures/save_ia1_fixtures.py). The phone runs at
// 375 × 812 (the brief's width), the desktop at 1300 × 900. Screenshots: SHOTS_DIR (default e2e/.out).
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { DYNASTY, serveFixtures, TEST_LEAGUE } from "../fixtures";

const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out");
mkdirSync(SHOTS, { recursive: true });
const fixture = (name: string) => JSON.parse(readFileSync(join(import.meta.dirname, "..", "..", "fixtures", name), "utf8"));
const dyn = (path: string) => `${path}?league=${DYNASTY}&team=12`;

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

test.beforeEach(async ({ context, page, isMobile }) => {
  await serveFixtures(context);
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test("My Week: short names and a headshot on every lineup row, the plain header, a card that says why", async ({ page, isMobile }, info) => {
  const d = fixture(`my-week_${DYNASTY}_12.json`);
  await page.goto(dyn("/"));
  await expect(page.getByTestId("team-name")).toHaveText(d.team_name);

  // the header: "Your lineup" and one line under it
  await expect(page.getByTestId("lineup-head")).toHaveText("Your lineup");
  await expect(page.getByTestId("lineup-caption")).toHaveText("Starters, the bench, who can't play — tap a name for his card.");
  await expect(page.getByTestId("lineup-full").locator("summary")).toHaveText(/The bench and who can't play/);
  await expect(page.getByText(/Your full lineup: every slot/)).toHaveCount(0);

  // every row: a headshot (a silhouette when the picture does not load); the name short on a phone, whole on a desktop
  const lineup = page.getByTestId("lineup");
  const rows = lineup.locator("tbody tr");
  await expect(rows).toHaveCount(d.lineup.length);
  await expect(lineup.getByTestId("headshot")).toHaveCount(d.lineup.filter((r: { player_name: string | null }) => r.player_name).length);
  const shown = await lineup.locator("tbody").innerText();
  const first = d.lineup.find((r: { position: string }) => r.position !== "DEF");
  const [fn, ...rest] = (first.player_name as string).split(" ");
  const short = `${fn[0]}. ${rest.join(" ")}`;
  if (isMobile) {
    expect(shown).toContain(short);
    expect(shown).not.toContain(first.player_name);
    await expect(lineup.getByTestId("short-name").first()).toBeVisible();
  } else {
    expect(shown).toContain(first.player_name);
    await expect(lineup.getByTestId("short-name").first()).toBeHidden();
  }

  // the cards: the call, the reason in a sentence, then the small print with the odds and the numbers
  const cards = page.getByTestId("decision-card");
  await expect(cards).toHaveCount(d.cards.length);
  for (let i = 0; i < d.cards.length; i++) {
    const why = cards.nth(i).getByTestId("card-why");
    await expect(why).toBeVisible();
    await expect(why).toHaveText(d.cards[i].why.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1"));
    await expect(cards.nth(i).getByTestId("card-small-print")).toContainText(/outscores|apart/);
  }
  await expect(cards.first().getByTestId("card-why")).toContainText("Too close to call");
  // the reason reads in the body size, the odds in the small print under it
  const sizes = await cards.first().evaluate((el) => {
    const px = (s: string) => parseFloat(getComputedStyle(el.querySelector(`[data-testid="${s}"]`)!).fontSize);
    return { why: px("card-why"), small: px("card-small-print") };
  });
  expect(sizes.why).toBeGreaterThan(sizes.small);

  await expect(page.getByTestId("to-research")).toHaveText(/Who's above or below expectation/);
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ia1_week_dyn12_${info.project.name}.png`), fullPage: true });
  await page.getByTestId("lineup-full").locator("summary").click();
  await expect(page.getByTestId("lineup-full-table").getByTestId("headshot").first()).toBeVisible();
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ia1_week_dyn12_full_${info.project.name}.png`), fullPage: true });
});

test("My Week: the Test League's cards say why (a role, a matchup, a close call)", async ({ page }, info) => {
  const d = fixture(`my-week_${TEST_LEAGUE}_3.json`);
  await page.goto(`/?league=${TEST_LEAGUE}&team=3`);
  const why = page.getByTestId("decision-card").getByTestId("card-why");
  await expect(why).toHaveCount(3);
  await expect(why.nth(0)).toContainText("Too close to call");
  await expect(why.nth(1)).toContainText("of his team's carries");
  await expect(why.nth(2)).toContainText(/who give up the .* points to tight ends/);
  expect(d.cards.every((c: { why: string }) => c.why)).toBe(true);
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ia1_week_test_${info.project.name}.png`), fullPage: false });
});

test("Trends: below and above expectation, the work per game on every row, the reason in a sentence", async ({ page, isMobile }, info) => {
  const t = fixture(`trends_${DYNASTY}.json`);
  await page.goto(dyn("/trends"));
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Below and above expectation");
  await expect(page.getByTestId("answer")).toContainText("Below expectation:");
  await expect(page.getByTestId("answer")).toContainText("Above expectation:");
  await expect(page.getByTestId("view-due")).toHaveText("Below");
  await expect(page.getByTestId("view-hot")).toHaveText("Above");
  await expect(page.getByTestId("card-due")).toContainText("Below");
  await expect(page.getByText(/running hot|Due to pick up/i)).toHaveCount(0);

  await expect(page.getByTestId("trend-stats-head")).toHaveText(/Tgt\/g\s*Car\/g\s*Snaps\s*Exp\s*Pts/);
  const rows = page.getByTestId("trends-list").locator("li");
  await expect(rows).toHaveCount(30);
  // the first row is the biggest gap either way: its numbers as the API sent them
  const top = [...t.players].filter((p) => p.gap !== null).sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap))[0];
  const one = (v: number | null) => (v === null ? "—" : v.toFixed(1));
  const row = rows.first();
  await expect(row.getByTestId("player-row")).toContainText(top.player_name);
  await expect(row.getByTestId("headshot")).toBeVisible();
  await expect(row.getByTestId("stat-targets")).toHaveText(`${one(top.targets_pg_l3)} (${one(top.targets_pg)})`);
  await expect(row.getByTestId("stat-carries")).toHaveText(`${one(top.carries_pg_l3)} (${one(top.carries_pg)})`);
  await expect(row.getByTestId("stat-snaps")).toHaveText(`${Math.round(top.snap_pct_l3 * 100)}%`);
  await expect(row.getByTestId("stat-expected")).toHaveText(top.xppg.toFixed(1));
  await expect(row.getByTestId("stat-actual")).toHaveText(top.ppg.toFixed(1));
  await expect(row.getByTestId("gap")).toBeVisible(); // the bar stays
  await expect(row.getByTestId("trend-why")).toHaveText(top.why);
  expect(top.why).toMatch(/^Getting the .* of an? \d+\.\d-point player, scoring \d+\.\d: .+\.$/);
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ia1_trends_${info.project.name}.png`), fullPage: true });
  if (!isMobile) await expect(page.getByTestId("trends-detail")).toContainText(/expectation/);
});

test("Matchups: the cornerbacks your receivers face — a real title, receivers only, a headshot on each", async ({ page }, info) => {
  const cb = fixture(`matchups_cb_${DYNASTY}_12.json`);
  await page.goto(dyn("/matchups"));
  const title = page.getByTestId("cb-title");
  await expect(title).toHaveText("The cornerbacks your receivers face");
  expect(await title.evaluate((el) => parseInt(getComputedStyle(el).fontWeight, 10))).toBeGreaterThanOrEqual(700);
  const section = page.getByTestId("cb-section");
  const wrs = cb.matchups.filter((m: { position: string; is_starter: boolean }) => m.position === "WR" && m.is_starter);
  await expect(section.locator(":scope > [data-testid=cb-card]")).toHaveCount(wrs.length);
  for (const te of cb.matchups.filter((m: { position: string }) => m.position === "TE")) await expect(section).not.toContainText(te.player_name);
  await expect(section).not.toContainText("tight end");
  await expect(section.locator(":scope > [data-testid=cb-card]").first().getByTestId("headshot")).toBeVisible();
  await expect(page.getByTestId("howto")).not.toContainText("Tight ends mostly draw");
  await noSidewaysScroll(page);
  await section.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(SHOTS, `ia1_matchups_${info.project.name}.png`), fullPage: false });
});

test("Compare: both pickers say Choose a player", async ({ page }) => {
  await page.goto(dyn("/compare"));
  await expect(page.getByTestId("compare-search-a")).toHaveAttribute("placeholder", "Choose a player");
  await expect(page.getByTestId("compare-search-b")).toHaveAttribute("placeholder", "Choose a player");
  await expect(page.getByPlaceholder("Find a player")).toHaveCount(0);
  await noSidewaysScroll(page);
});
