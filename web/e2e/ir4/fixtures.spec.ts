// Wave I-R (IR-4): what is verified, with every analysis. Browsing (`ref:half`) in 2026 week 5: Rankings (this week and
// rest of season), /ros, the free trade calculator (a quarterback whose starter was set by hand: the softened caveat),
// the player card, About (what changed and when; what each number has been checked against) and the home ("Beta").
// The answers of those routes are web/fixtures/ir4/api_ir4.json, recorded from the app on league_lab_im4 with the clock
// pinned in week 5 (the real provenance lines and the real Seattle caveat); everything else from serveFixtures.
// Outside hosts (headshots): answered here with a 1x1 PNG. Phone at 375 and desktop at 1300; screenshots (JPEG q70)
// into docs/handbacks/ir4/ (SHOTS_IR4) or e2e/.out.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const RECORDED = join(import.meta.dirname, "..", "..", "fixtures", "ir4", "api_ir4.json");
const SHOTS = process.env.SHOTS_IR4 ?? join(import.meta.dirname, "..", ".out");
type Recorded = Record<string, { status: number; body: unknown }>;
const recorded = JSON.parse(readFileSync(RECORDED, "utf8")) as Recorded;
const DARNOLD = "00-0034869";
const HUBBARD = "00-0036555";
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64");
const LINE = /^Model v3\.\d, data published \d+ \w{3}, \d+:\d\d (am|pm) ET · /;

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return `${u.pathname}?${new URLSearchParams(q).toString()}`;
};

async function api(context: BrowserContext): Promise<string[]> {
  const calls: string[] = [];
  await context.route(/^https?:\/\/(?!localhost)/, (route) => route.fulfill({ status: 200, contentType: "image/png", body: PNG }));
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

const shot = (page: Page, name: string) => page.screenshot({ path: join(SHOTS, `${name}.jpg`), type: "jpeg", quality: 70, scale: "css" });
const noSideScroll = async (page: Page) => {
  const [sw, cw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(sw).toBeLessThanOrEqual(cw);
};

test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test("Rankings: one quiet line, this week and rest of season", async ({ context, page }, info) => {
  await api(context);
  await page.goto("/rankings?league=ref:half&position=QB");
  const week = page.getByTestId("rankings-provenance-line");
  await expect(week).toHaveText(LINE);
  await expect(week).toContainText("· week 5 · checked on 2021–2025: next week graded.");
  await page.goto("/rankings?league=ref:half&view=season&position=QB");
  const season = page.getByTestId("rankings-provenance-line");
  await expect(season).toContainText("two to eight weeks ahead graded, weak; the season total's range not graded.");
  await expect(season).toHaveAttribute("data-status", "not_graded");
  await noSideScroll(page);
  await season.scrollIntoViewIfNeeded();
  await shot(page, `rankings-season-${info.project.name}`);
});

test("/ros: the line in the how-to-read box", async ({ context, page }, info) => {
  await api(context);
  await page.goto("/ros?league=ref:half&position=QB");
  const line = page.getByTestId("ros-provenance-line");
  await expect(line).toHaveText(LINE);
  await expect(line).toContainText("weeks 5–17");
  await noSideScroll(page);
  await line.scrollIntoViewIfNeeded();
  await shot(page, `ros-${info.project.name}`);
});

test("the free trade calculator: beta, the line, and the softened caveat of a starter set by hand", async ({ context, page }, info) => {
  await api(context);
  await page.goto(`/trade-calc?league=ref:half&give=${DARNOLD}&get=${HUBBARD}`);
  const line = page.getByTestId("ft-provenance-line");
  await expect(line).toHaveText(/^Beta · Model v3\.\d/);
  await expect(line).toContainText("the trade's range not graded");
  await expect(page.getByTestId("ft-words")).toContainText("(a lean: it assumes Darnold starts).");
  const cav = page.getByTestId("ft-provenance-caveat");
  await expect(cav).toHaveCount(1);
  await expect(cav).toHaveAttribute("data-effect", "soften");
  await expect(cav).toHaveText("Seattle's starter was set by hand (Sam Darnold, not the listed Drew Lock); this depends on Sam Darnold, so read the verdict as a lean that assumes Darnold starts.");
  await noSideScroll(page);
  await cav.scrollIntoViewIfNeeded();
  await shot(page, `free-trade-${info.project.name}`);
});

test("the player card: the line under how to read", async ({ context, page }, info) => {
  await api(context);
  await page.goto(`/player/${DARNOLD}?league=ref:half`);
  const line = page.getByTestId("card-provenance-line");
  await expect(line).toHaveText(LINE);
  await noSideScroll(page);
  await line.scrollIntoViewIfNeeded();
  await shot(page, `card-${info.project.name}`);
});

test("About: what changed and when, what each number has been checked against", async ({ context, page }, info) => {
  await api(context);
  await page.goto("/about?league=ref:half");
  await expect(page.getByTestId("about-versions")).toBeVisible();
  await expect(page.getByTestId("about-versions-list").locator("li")).toHaveCount(8);
  await expect(page.getByTestId("about-versions-list")).toContainText("v3.6");
  await expect(page.getByTestId("about-versions-weeks")).toContainText("weeks 1–3: v2.0; week 4: v3.0");
  await expect(page.getByTestId("model-unknown")).not.toContainText("recipe stays the same");
  await expect(page.getByTestId("model-unknown")).toContainText("What changed and when");
  await expect(page.getByTestId("about-checked-card")).toHaveCount(6);
  await expect(page.getByTestId("about-checked-card").first()).toContainText("Two to eight weeks ahead: graded, weak");
  await expect(page.getByTestId("about-not-graded")).toContainText("a trade of several players or across positions");
  await expect(page.getByTestId("about-useful")).toContainText("Is the trade calculator right? On a close one-for-one");
  await noSideScroll(page);
  await page.getByTestId("about-versions").scrollIntoViewIfNeeded();
  await shot(page, `about-versions-${info.project.name}`);
  await page.getByTestId("about-checked").scrollIntoViewIfNeeded();
  await shot(page, `about-checked-${info.project.name}`);
});

test("the home says beta", async ({ context, page }, info) => {
  await api(context);
  await page.goto("/");
  const beta = page.getByTestId("home-beta");
  await expect(beta).toHaveText("Beta. What each number has been checked against, and what has not, is on About the numbers.");
  await expect(beta.getByRole("link")).toHaveAttribute("href", "/about#checked");
  await noSideScroll(page);
  await shot(page, `home-${info.project.name}`);
});
