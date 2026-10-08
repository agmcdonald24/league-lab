// Wave I-B (IB-2) on fixtures: Waivers short — the three strongest moves first (the move, the lineup gain, one reason,
// the claim's cost; a drop who starts carries the best claim that keeps him), then one view at a time behind chips
// (Help now · Bye coverage · Stashes · All available), the chip row within two phone screens; the trade calculator's
// decision in view while the roster lists scroll (desktop: the dial's row is sticky; phone: a collapsed bar that opens
// on a tap), "Why?" and "Lineups" collapsed; Trades' partner cards (the package, the dial's label, your gain, one
// reason, Try it). At 375 × 812 (the phone project) and 1300 px (desktop). Fixtures: web/fixtures/save_ib2_fixtures.py.
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { DYNASTY, FIXTURES, SCRUBS, serveFixtures, TEST_LEAGUE } from "../fixtures";
import { serveDecisions } from "../decisions-fixtures";

const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out");
mkdirSync(SHOTS, { recursive: true });
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- the saved API answers, read as JSON
const fx = (name: string): any => JSON.parse(readFileSync(join(FIXTURES, name), "utf8"));
const sg = (x: number) => (Math.abs(x) >= 0.05 ? `${x > 0 ? "+" : "−"}${Math.abs(x).toFixed(1)}` : "+0.0");
const plain = (t: string) => t.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/\*\*/g, "").replace(/ {2}\n/g, "");
const PACKAGES = fx("ia2_packages.json") as Record<string, { partner: number; from: { give: string[]; get: string[]; label: string } }>;
const PHONE_H = 812;

test.beforeEach(async ({ context, page }, info) => {
  await serveFixtures(context);
  await serveDecisions(context);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: PHONE_H });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

async function shot(page: Page, name: string, info: TestInfo) {
  await page.evaluate(() => document.fonts?.ready);
  await page.screenshot({ path: join(SHOTS, `ib2_${name}_${info.project.name}.png`), fullPage: true });
}

/** The top of an element in page coordinates (not the viewport's). */
const pageTop = (page: Page, testid: string) =>
  page.evaluate((t) => {
    const el = document.querySelector(`[data-testid="${t}"]`) as HTMLElement;
    return el.getBoundingClientRect().top + window.scrollY;
  }, testid);

test("waivers: the three strongest moves first, with one reason, the cost, and the alternative before a starter's drop (Scrubs)", async ({ page }, info) => {
  const w = fx(`waivers_${SCRUBS}_2_ALL.json`);
  await page.goto(`/waivers?league=${SCRUBS}&team=2`);
  const cards = page.getByTestId("top-move");
  await expect(cards).toHaveCount(w.top3.length);
  expect(w.top3.length).toBe(3);
  for (let i = 0; i < w.top3.length; i++) {
    const c = w.top3[i];
    const card = cards.nth(i);
    await expect(card.getByTestId("claim-add")).toHaveText(c.move.add.player_name);
    await expect(card.getByTestId("claim-gain")).toHaveText(sg(c.gain));
    await expect(card.getByTestId("claim-reason")).toHaveText(c.reason);
    await expect(card.getByTestId("claim-cost")).toContainText(c.cost);
    // the best waiver alternative: present exactly when the drop starts for you this week or next
    if (c.move.drop_starts) {
      await expect(card.getByTestId("keep-alt")).toContainText(c.move.drop_starts.text);
      await expect(card.getByTestId("keep-alt")).toContainText(c.move.keep_alternative.line);
    } else await expect(card.getByTestId("keep-alt")).toHaveCount(0);
  }
  expect(w.top3.some((c: { move: { drop_starts: unknown } }) => c.move.drop_starts)).toBe(true); // Giants for the Chiefs
  // the page is short: the chip row within the first two phone screens
  const chipsY = await pageTop(page, "views");
  if (info.project.name === "phone") expect(chipsY, "the chips start within two phone screens").toBeLessThan(2 * PHONE_H);
  await noSidewaysScroll(page);
  await shot(page, "waivers_scrubs", info);
});

test("waivers: the chips switch views, one on screen at a time (Help now · Bye coverage · Stashes · All available)", async ({ page }, info) => {
  const w = fx(`waivers_${SCRUBS}_2_ALL.json`);
  await page.goto(`/waivers?league=${SCRUBS}&team=2`);
  const only = async (id: string) => {
    for (const v of ["view-help", "view-bye", "upside", "free-agents"]) await expect(page.getByTestId(v)).toHaveCount(v === id ? 1 : 0);
  };
  // default: Help now
  await expect(page.getByTestId("views-help")).toHaveAttribute("aria-pressed", "true");
  await only("view-help");
  await expect(page.getByTestId("view-help").getByTestId("view-line")).toHaveText(plain(w.views.help.line));
  await expect(page.getByTestId("view-move")).toHaveCount(w.views.help.moves.length);
  await expect(page.getByTestId("view-move").first().getByTestId("claim-add")).toHaveText(w.views.help.moves[0].move.add.player_name);
  // every listed claim that drops a starter carries the alternative line; the others do not
  const withAlt = w.views.help.moves.filter((c: { move: { drop_starts: unknown } }) => c.move.drop_starts).length;
  await expect(page.getByTestId("view-help").getByTestId("keep-alt")).toHaveCount(withAlt);
  // Bye coverage: the next bye the roster cannot cover
  await page.getByTestId("views-bye").click();
  await expect(page).toHaveURL(/view=bye/);
  await only("view-bye");
  await expect(page.getByTestId("view-line")).toHaveText(plain(w.views.bye.line));
  expect(w.views.bye.week).toBe(5);
  await expect(page.getByTestId("view-move")).toHaveCount(w.views.bye.moves.length);
  await expect(page.getByTestId("view-move").first().getByTestId("claim-gain")).toHaveText(sg(w.views.bye.moves[0].week_gain));
  await shot(page, "waivers_bye", info);
  // Stashes: the upside stash
  await page.getByTestId("views-stash").click();
  await only("upside");
  await expect(page.getByTestId("stash")).toHaveCount(Math.min(3, w.upside.stashes.length));
  // All available: the free agents
  await page.getByTestId("views-all").click();
  await only("free-agents");
  await expect(page.getByTestId("fa-row")).toHaveCount(w.free_agents.length);
  // the view survives a position switch (both are the URL)
  await page.getByTestId("fa-pos-WR").click();
  await expect(page).toHaveURL(/view=all/);
  await expect(page).toHaveURL(/position=WR/);
  await only("free-agents");
  // back to the default: the parameter leaves the URL
  await page.getByTestId("views-help").click();
  await expect(page).not.toHaveURL(/view=/);
  await noSidewaysScroll(page);
});

test("waivers on demand (Test League, a roster whose claim drops a starter) and with nothing to claim (dynasty)", async ({ page }) => {
  const t = fx(`waivers_${TEST_LEAGUE}_9_ALL.json`);
  await page.goto(`/waivers?league=${TEST_LEAGUE}&team=9`);
  const cards = page.getByTestId("top-move");
  await expect(cards).toHaveCount(t.top3.length);
  const k = t.top3.findIndex((c: { move: { drop_starts: unknown } }) => c.move.drop_starts);
  expect(k).toBeGreaterThanOrEqual(0);
  await expect(cards.nth(k).getByTestId("keep-alt")).toContainText(t.top3[k].move.keep_alternative.line);
  for (let i = 0; i < t.top3.length; i++) if (i !== k && !t.top3[i].move.drop_starts) await expect(cards.nth(i).getByTestId("keep-alt")).toHaveCount(0);
  const d = fx(`waivers_${DYNASTY}_12_ALL.json`);
  await page.goto(`/waivers?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("top-move")).toHaveCount(0);
  await expect(page.getByTestId("views")).toBeVisible();
  await expect(page.getByTestId("view-line")).toHaveText(plain(d.views.help.line));
  await noSidewaysScroll(page);
});

test("waivers: ?add= (the research pane's Evaluate add / drop) shows the claim for him first", async ({ page }) => {
  const w = fx(`waivers_${SCRUBS}_2_ALL.json`);
  const c = w.views.help.moves[1];
  await page.goto(`/waivers?league=${SCRUBS}&team=2&add=${c.move.add.sleeper_id}`);
  await expect(page.getByTestId("claim-focus")).toBeVisible();
  await expect(page.getByTestId("claim-focused").getByTestId("claim-add")).toHaveText(c.move.add.player_name);
  const [focusY, topY] = await Promise.all([pageTop(page, "claim-focus"), pageTop(page, "top3")]);
  expect(focusY).toBeLessThan(topY);
});

for (const league of [SCRUBS, TEST_LEAGUE]) {
  test(`the calculator keeps the decision in view while the rosters scroll; Why? and Lineups collapsed (${league})`, async ({ page }, info) => {
    // IS-3: Scrubs' package re-chosen on today's fixtures (save_ir2_fixtures.py --scrubs; ia2_packages.json)
    const team = league === SCRUBS ? 2 : 3;
    const pk = PACKAGES[league];
    await page.goto(`/trade-calc?league=${league}&team=${team}&partner=${pk.partner}&give=${pk.from.give.join(",")}&get=${pk.from.get.join(",")}`);
    await expect(page.getByTestId("dial-label")).toHaveText(pk.from.label);
    // the explanation and the lineups wait behind their expanders
    for (const x of ["why", "lineups-x"]) await expect(page.getByTestId(x)).not.toHaveAttribute("open", "");
    await expect(page.getByTestId("trade-details")).toBeHidden();
    await expect(page.getByTestId("lineup-after").first()).toBeHidden();
    // browse the roster lists: scroll to the partner's list
    await page.getByTestId("pick-get").scrollIntoViewIfNeeded();
    await page.evaluate(() => {
      const el = document.querySelector('[data-testid="pick-get"]') as HTMLElement;
      window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 40);
    });
    // the decision is on screen while the partner's list is: the dial's row itself, or — once it has scrolled away — the
    // verdict bar pinned to the top of the screen
    const bar = page.getByTestId("verdict-bar");
    if (info.project.name === "desktop") {
      // desktop: the lists scroll inside their cards; while the dial's row is on screen there is no bar (IR-2 fix: the
      // decision's result card is longer, so at 1300 the dial's row may already have scrolled away here — then the bar
      // below must be pinned, the same rule); open the explanation and the lineups so the page is long, and go to its end
      const dialOn = await page.getByTestId("dial-row").evaluate((el) => {
        const r = el.getBoundingClientRect();
        return r.bottom > 0 && r.top < window.innerHeight;
      });
      if (dialOn) await expect(bar).toHaveCount(0);
      else await expect(bar).toBeInViewport();
      await page.getByTestId("why").locator("summary").first().click();
      await page.getByTestId("lineups-x").locator("summary").first().click();
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    }
    await expect(page.getByTestId("dial-row")).not.toBeInViewport();
    await expect(bar).toBeInViewport();
    expect((await bar.boundingBox())!.y).toBeLessThan(5);
    await expect(bar.getByTestId("dial-chip")).toContainText(pk.from.label);
    await expect(page.getByTestId("verdict-bar-package")).not.toHaveText("");
    if (info.project.name === "phone") {
      await expect(page.getByTestId("pick-get")).toBeInViewport();
      await expect(page.getByTestId("verdict-bar-detail")).toHaveCount(0); // collapsed: a tap opens it
      await page.getByTestId("verdict-bar-toggle").click();
      await expect(page.getByTestId("verdict-bar-toggle")).toHaveAttribute("aria-expanded", "true");
      await page.mouse.wheel(0, 300); // scrolling further down the list, it stays
      await expect(bar).toBeInViewport();
    }
    await expect(page.getByTestId("verdict-bar-detail")).toBeVisible(); // desktop: open
    await noSidewaysScroll(page);
    await shot(page, `calc_sticky_${league}`, info);
    if (info.project.name === "phone") {
      // Why? opens the explanation
      await page.getByTestId("why").locator("summary").first().click();
      await expect(page.getByTestId("trade-details")).toBeVisible();
    }
  });
}
test("Trades: each suggestion is the package, the dial's label, your gain, one reason, and Try it", async ({ page }) => {
  const all = fx(`trades_partners_${SCRUBS}_2_ALL.json`);
  await page.goto(`/trades?league=${SCRUBS}&team=2`);
  const rows = page.getByTestId("partner-row");
  await expect(rows.first()).toBeVisible();
  const p = all.partners[0];
  const r = rows.first();
  await expect(r).toContainText(p.partner_team);
  await expect(r.getByTestId("partner-label")).toContainText(p.interest.label);
  await expect(r.getByTestId("partner-gain")).toHaveText(sg(p.you_gain_horizon));
  await expect(r.getByTestId("partner-reason")).not.toHaveText("");
  // one reason: a sentence, not the paragraph
  expect(((await r.getByTestId("partner-reason").textContent()) ?? "").split(". ").length).toBeLessThanOrEqual(2);
  await r.getByTestId("try-partner").click();
  await expect(page).toHaveURL(/\/trade-calc\?/);
  await expect(page).toHaveURL(new RegExp(`partner=${p.partner}`));
  await noSidewaysScroll(page);
});
