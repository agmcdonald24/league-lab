// Wave I-N (IN-5): My Week says what it means, and no screen can go blank. Andrew's morning of 2026-10-06 (League of
// Scrubs roster 2, week 5: QB and TE open — Mahomes, Young and Kelce on a bye): the API's own answers, recorded from the
// week-5 rows of the database through the real routes (api/tests/test_in5.py::test_record_andrews_morning, IN5_RECORD=1)
// into web/fixtures/in5/. team_open_nan.json is the same Team answer with both open rows carrying the id "nan" — what
// the screen got at 09:20, before the PO's hotfix. Phone at 375 and desktop at 1300; GA is stubbed (nothing leaves).
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { SCRUBS, serveFixtures } from "../fixtures";
import { serveDecisions } from "../decisions-fixtures";

const IN5 = join(import.meta.dirname, "..", "..", "fixtures", "in5");
const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", "..", "..", "docs", "handbacks", "in5");
const GOOGLE = /^https:\/\/([a-z0-9-]+\.)*(google-analytics\.com|googletagmanager\.com|google\.com|doubleclick\.net)\//;
const Q = `league=${SCRUBS}&team=2`;
const read = (name: string) => readFileSync(join(IN5, name), "utf8");

type Answer = Record<string, unknown> & { roster?: unknown[]; cards?: { slot: string }[] };

/** /api/my-week and /api/team for roster 2 from web/fixtures/in5 (or a changed copy); the rest from the fixtures. */
async function serve(context: BrowserContext, opts: { week?: Answer; team?: Answer | string } = {}) {
  await serveFixtures(context);
  await serveDecisions(context);
  await context.route(/\/api\/(my-week|team)\?/, async (route) => {
    const u = new URL(route.request().url());
    if (u.searchParams.get("league") !== SCRUBS || u.searchParams.get("team") !== "2") return route.fallback();
    const mine = u.pathname === "/api/my-week" ? (opts.week ?? read("my-week_open.json")) : (opts.team ?? read("team_open.json"));
    return route.fulfill({ status: 200, contentType: "application/json", headers: { "Cache-Control": "no-store" },
      body: typeof mine === "string" ? mine : JSON.stringify(mine) });
  });
}

async function stubGa(context: BrowserContext) {
  await context.route(GOOGLE, async (route) => {
    if (route.request().url().startsWith("https://www.googletagmanager.com/gtag/js")) return route.fulfill({ status: 200, contentType: "text/javascript", body: "" });
    return route.abort();
  });
  await context.addInitScript(() => ((window as unknown as { __llGa: string }).__llGa = "on"));
}

async function gaEvents(page: Page): Promise<{ name: string; p: Record<string, unknown> }[]> {
  return page.evaluate(() => {
    const dl = (window as unknown as { dataLayer?: ArrayLike<unknown>[] }).dataLayer;
    return Array.from(dl ?? [], (a) => Array.from(a))
      .filter((c) => c[0] === "event")
      .map((c) => ({ name: String(c[1]), p: (c[2] ?? {}) as Record<string, unknown> }));
  });
}

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

/** The screen uses the desktop's width: its main column is wider than a phone's. */
async function usesTheWidth(page: Page, isMobile: boolean) {
  if (isMobile) return;
  const w = await page.locator(".ll-under-bar").first().evaluate((el) => el.getBoundingClientRect().width);
  expect(w).toBeGreaterThan(900);
}

const crashes: string[] = [];
test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
  crashes.length = 0;
  page.on("pageerror", (e) => crashes.push(String(e)));
  page.on("console", (m) => m.type() === "error" && /each_key_duplicate/.test(m.text()) && crashes.push(m.text()));
});

test("My Week, two open spots: each is its own roster alert with Waivers at the position, the swap names the coin flip once, News feed", async ({ context, page, isMobile }, info) => {
  await serve(context);
  await page.goto(`/?${Q}`);
  const cards = page.getByTestId("action-card");
  await expect(cards.first()).toBeVisible();
  const texts = await page.getByTestId("action-text").allInnerTexts();
  expect(texts[0]).toBe("Your quarterback spot is open: Mahomes and Young are on a bye. Add a quarterback before Sun 1:00 PM ET.");
  expect(texts[1]).toBe("Your tight end spot is open: Kelce is on a bye. Add a tight end before Sun 1:00 PM ET.");
  expect(texts[2]).toBe("Start Jefferson at FLEX (or Boston: a coin flip) in place of Croskey-Merritt.");
  for (const t of texts) expect(t).not.toMatch(/Start .* out of your lineup|in place of Mahomes|in place of Kelce/);
  await expect(cards.nth(0).getByTestId("action-kind")).toHaveText("⚠︎ Roster alert");
  await expect(cards.nth(1).getByTestId("action-kind")).toHaveText("⚠︎ Roster alert");
  await expect(cards.nth(0).getByTestId("action-reason")).toHaveText(
    "Nobody else on your roster can play quarterback this week. Mahomes is still in your Sleeper lineup: start the player you add in his place.",
  );
  await expect(cards.nth(0).getByTestId("action-submitted")).toHaveText("→ Nothing is claimed from here: add a quarterback in Sleeper.");
  const open = cards.nth(0).getByTestId("action-open");
  await expect(open).toHaveText("Find a quarterback on Waivers ›");
  await expect(open).toHaveAttribute("href", `/waivers?position=QB&${Q}`);
  await expect(page.getByTestId("news-feed-title")).toHaveText("News feed");
  await expect(page.getByText("Change needed")).toHaveCount(0);
  await expect(page.getByText("What changed", { exact: true })).toHaveCount(0);
  // the lineup shows the two open slots as open, nothing else
  await expect(page.getByTestId("lineup")).toBeVisible();
  await noSidewaysScroll(page);
  await usesTheWidth(page, isMobile);
  await page.screenshot({ path: join(SHOTS, `in5-my-week-${info.project.name}.png`), fullPage: true });
  // the next step: Waivers at the position (the screen reads ?position=)
  await open.click();
  await expect(page).toHaveURL(/\/waivers\?position=QB/);
  await expect(page.getByTestId("error-card")).toHaveCount(0);
  expect(crashes).toEqual([]);
});

for (const variant of ["null", "nan"] as const) {
  test(`Team, two open spots (the open rows' id ${variant === "nan" ? '"nan", as at 09:20' : "null, as the API sends it now"}): the screen shows, both open rows say so`, async ({ context, page, isMobile }, info) => {
    await serve(context, { team: read(variant === "nan" ? "team_open_nan.json" : "team_open.json") });
    await page.goto(`/team?${Q}`);
    const roster = page.getByTestId("team-roster");
    await expect(roster).toBeVisible();
    await expect(roster.getByText("QB: nobody can play it this week")).toBeVisible();
    await expect(roster.getByText("TE: nobody can play it this week")).toBeVisible();
    const opens = roster.getByTestId("roster-open-waivers");
    await expect(opens).toHaveCount(2);
    await expect(opens.nth(0)).toHaveAttribute("href", `/waivers?position=QB&${Q}`);
    await expect(opens.nth(1)).toHaveAttribute("href", `/waivers?position=TE&${Q}`);
    await expect(roster.getByText("Justin Jefferson").first()).toBeVisible();
    await expect(page.getByTestId("error-card")).toHaveCount(0);
    await expect(page.locator('[aria-label="Loading"]')).toHaveCount(0);
    await noSidewaysScroll(page);
    await usesTheWidth(page, isMobile);
    if (variant === "nan") {
      await page.screenshot({ path: join(SHOTS, `in5-team-${info.project.name}.png`), fullPage: true });
      await roster.screenshot({ path: join(SHOTS, `in5-team-roster-${info.project.name}.png`) });
    }
    expect(crashes).toEqual([]);
  });
}

test("duplicate-key answers (a call listed twice under one action, the same week twice on Team): both screens still show", async ({ context, page }) => {
  const week = JSON.parse(read("my-week_open.json")) as Answer & { actions: { cards: number[] }[] };
  const swap = week.actions.find((a) => a.cards.length > 0)!;
  const n = swap.cards.length;
  swap.cards = [...swap.cards, ...swap.cards]; // every call (one slot each) twice behind "Why?"
  const team = JSON.parse(read("team_open_nan.json")) as Answer & { weekly: unknown[] };
  team.weekly = [...team.weekly, ...team.weekly]; // every week twice
  await serve(context, { week, team });
  await page.goto(`/?${Q}`);
  await expect(page.getByTestId("action-card").first()).toBeVisible();
  await expect(page.getByTestId("action-call")).toHaveCount(2 * n);
  await expect(page.getByTestId("error-card")).toHaveCount(0);
  await page.goto(`/team?${Q}`);
  await expect(page.getByTestId("team-roster")).toBeVisible();
  await expect(page.getByTestId("error-card")).toHaveCount(0);
  expect(crashes).toEqual([]);
});

test("a render error inside a screen: the error card (the bar stays), Reload, the screen's name to analytics; another tab works", async ({ context, page }, info) => {
  await stubGa(context);
  const team = JSON.parse(read("team_open.json")) as Answer;
  team.roster = [null, ...(team.roster ?? [])]; // a broken row: the screen cannot draw it
  await serve(context, { team });
  await page.goto(`/team?${Q}`);
  const card = page.getByTestId("error-card");
  await expect(card).toBeVisible();
  await expect(card).toHaveAttribute("data-kind", "crashed");
  await expect(card).toHaveAttribute("data-screen", "team");
  await expect(card.getByTestId("error-title")).toHaveText(/This screen hit a problem/);
  await expect(card.getByTestId("error-reload")).toHaveText("Reload");
  await expect(page.getByTestId("top-bar")).toBeVisible(); // the bar stays: the other screens are one tap away
  await expect(page.locator('[aria-label="Loading"]')).toHaveCount(0);
  await expect.poll(async () => (await gaEvents(page)).filter((e) => e.name === "exception").map((e) => e.p.description)).toEqual(["screen: team"]);
  const ev = (await gaEvents(page)).find((e) => e.name === "exception")!;
  expect(ev.p.fatal).toBe(false);
  await page.screenshot({ path: join(SHOTS, `in5-crash-${info.project.name}.png`), fullPage: true });
  // another tab (in the app, no reload): the boundary starts again and the screen shows
  await page.getByTestId("tab-waivers").click();
  await expect(page).toHaveURL(/\/waivers\?/);
  await expect(page.getByTestId("error-card")).toHaveCount(0);
  await expect(page.locator("main, section").first()).toBeVisible();
});
