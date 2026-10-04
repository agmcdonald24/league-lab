// Wave I-H (IH-1): the product says when it is stale, and the error states the web app did not have — on fixtures
// (e2e/fixtures.ts answers every /api call; this file overrides /api/status and the failing calls per test).
//   * the stale banner: /api/status `nightly.stale` → one line above My Week's actions ("Yesterday's numbers: the
//     morning update did not run. Injury statuses are still live."), the footer's "Updated …" says the same; none when
//     fresh. Phone at 375 (inside the phone project) and desktop at 1300.
//   * the API down (no answer): a plain card with Try again — at the first screen (the boot) and on My Week — and
//     Try again really asks again; a 500: the card says so and names /api/status; the host's own 502 page = down;
//     our own 502 (Sleeper did not answer) keeps its words.
//   * a 401 after the cookie expired: back to the password screen with "Signed out — sign in again."; a first visit
//     has no such line.
//   * still waiting after 25 s: the card says so, the answer still shows when it arrives (desktop only: 26 s).
import { expect, test, type BrowserContext, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { FIXTURE_PASSWORD, FIXTURES, SCRUBS, serveFixtures } from "../fixtures";

const STALE = "Yesterday's numbers: the morning update did not run. Injury statuses are still live.";
const BASE = JSON.parse(readFileSync(join(FIXTURES, "status.json"), "utf8")) as Record<string, unknown>;
const HOME = `/?league=${SCRUBS}&team=2`;

function statusWith(nightly: Record<string, unknown>) {
  const now = Date.now();
  return { ...BASE, updated_at: new Date(now - 40 * 3600_000).toISOString(), nightly };
}
const stale = () =>
  statusWith({ as_of: new Date(Date.now() - 40 * 3600_000).toISOString(), age_hours: 40, stale: true, limit_hours: 30, words: STALE });
const fresh = () => statusWith({ as_of: new Date(Date.now() - 3 * 3600_000).toISOString(), age_hours: 3, stale: false, limit_hours: 30, words: null });

async function status(context: BrowserContext, body: unknown) {
  await context.route(/\/api\/status$/, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(body) }),
  );
}

test.beforeEach(async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `ih1-${name}-${project}.png`), fullPage: false });

test("stale: one line above the actions, the footer says the same; nothing when fresh", async ({ context, page, isMobile }, info) => {
  await serveFixtures(context);
  await status(context, stale());
  await page.goto(HOME);
  await expect(page.getByTestId("my-week")).toBeVisible();
  const banner = page.getByTestId("stale-banner");
  await expect(banner).toHaveText(`⚠︎${STALE}`);
  await expect(banner).toHaveAttribute("role", "status");
  // above the actions / the cards, under the team's lines
  const b = await banner.boundingBox();
  const team = await page.getByTestId("team-name").boundingBox();
  const lineup = await page.getByText("Your lineup", { exact: false }).first().boundingBox();
  expect(b && team && b.y > team.y).toBeTruthy();
  expect(b && lineup && b.y < lineup.y).toBeTruthy();
  // one line on a desktop; at 375 it wraps inside its box, never sideways
  if (!isMobile) expect(b!.height).toBeLessThan(44);
  await noSidewaysScroll(page);
  await shot(page, "stale-banner", info.project.name);
  // the footer: "Updated 1 day ago · the morning update did not run ›", the sentence on tap
  const foot = page.getByTestId("updated");
  await expect(page.getByTestId("updated-late")).toContainText("the morning update did not run");
  if (isMobile) await foot.locator("summary").tap();
  else await foot.locator("summary").click();
  await expect(page.getByTestId("updated-stale")).toHaveText(STALE);
});

test("fresh: no banner, the footer as before", async ({ context, page }) => {
  await serveFixtures(context);
  await status(context, fresh());
  await page.goto(HOME);
  await expect(page.getByTestId("team-name")).toBeVisible();
  await expect(page.getByTestId("updated")).toBeVisible();
  await expect(page.getByTestId("stale-banner")).toHaveCount(0);
  await expect(page.getByTestId("updated-late")).toHaveCount(0);
});

test("the API down at the first screen: a card with Try again, and Try again asks again", async ({ context, page }, info) => {
  await serveFixtures(context);
  let down = true;
  await context.route(/\/api\/leagues$/, (route: Route) => (down ? route.abort("connectionrefused") : route.fallback()));
  await page.goto(HOME);
  const card = page.getByTestId("error-card");
  await expect(card).toBeVisible();
  await expect(card).toHaveAttribute("data-kind", "down");
  await expect(page.getByTestId("error-title")).toHaveCount(0); // the words say it
  await expect(page.getByTestId("error-words")).toHaveText(/^⚠︎Cannot reach isuckatfantasy right now\. Check your connection, then try again\.$/);
  await expect(page.getByTestId("loading")).toHaveCount(0); // not a spinner
  await noSidewaysScroll(page);
  await shot(page, "api-down", info.project.name);
  down = false;
  await page.getByTestId("error-retry").click();
  await expect(page.getByTestId("team-name")).toBeVisible();
  await expect(page.getByTestId("error-card")).toHaveCount(0);
});

test("My Week: no answer → the card; Try again → the week", async ({ context, page }) => {
  await serveFixtures(context);
  let down = true;
  await context.route(/\/api\/my-week\?/, (route: Route) => (down ? route.abort("connectionrefused") : route.fallback()));
  await page.goto(HOME);
  const card = page.getByTestId("error-card");
  await expect(card).toHaveAttribute("data-kind", "down");
  await expect(page.getByTestId("error-retry")).toBeVisible();
  down = false;
  await page.getByTestId("error-retry").click();
  await expect(page.getByTestId("team-name")).toBeVisible();
});

test("a 500: the card says it broke on our side and names /api/status; the host's own 502 page reads as down", async ({ context, page }, info) => {
  await serveFixtures(context);
  let code = 500;
  await context.route(/\/api\/my-week\?/, (route: Route) =>
    route.fulfill({ status: code, contentType: "text/html", body: `<html><body>${code === 500 ? "Internal Server Error" : "Bad Gateway"}</body></html>` }),
  );
  await page.goto(HOME);
  const card = page.getByTestId("error-card");
  await expect(card).toHaveAttribute("data-kind", "server");
  await expect(page.getByTestId("error-title")).toHaveText(/Something broke on our side/);
  await expect(page.getByTestId("error-words")).toHaveText(
    "Our server hit an error (500). The status page says whether the data is up and when it was last updated.",
  );
  const link = page.getByTestId("error-status-link");
  await expect(link).toHaveText("/api/status");
  await expect(link).toHaveAttribute("href", "/api/status");
  await noSidewaysScroll(page);
  await shot(page, "api-500", info.project.name);
  code = 502;
  await page.getByTestId("error-retry").click();
  await expect(card).toHaveAttribute("data-kind", "down");
  await expect(page.getByTestId("error-words")).toContainText("is not answering right now (error 502)");
  await expect(page.getByTestId("error-status-link")).toHaveCount(0);
});

test("our own 502 still says Sleeper did not answer", async ({ context, page }) => {
  await serveFixtures(context);
  await context.route(/\/api\/my-week\?/, (route: Route) =>
    route.fulfill({ status: 502, contentType: "application/json", body: JSON.stringify({ error: "Sleeper did not answer" }) }),
  );
  await page.goto(HOME);
  await expect(page.getByTestId("error-card")).toHaveAttribute("data-kind", "upstream");
  await expect(page.getByTestId("error-words")).toHaveText("⚠︎Sleeper did not answer. Try again in a minute.");
});

test("signed out mid-session: the password screen says so, and signing in goes back to the screen", async ({ context, page }, info) => {
  const api = await serveFixtures(context, { gate: true });
  await page.goto(HOME);
  await expect(page.getByTestId("login")).toBeVisible();
  await expect(page.getByTestId("signed-out")).toHaveCount(0); // a first visit: no "signed out" line
  await page.locator('input[type="password"]').fill(FIXTURE_PASSWORD);
  await page.getByRole("button", { name: /Open/ }).click();
  await expect(page.getByTestId("team-name")).toBeVisible();
  api.signedIn = false; // the cookie expired
  await page.goto(`/waivers?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("login")).toBeVisible();
  await expect(page.getByTestId("signed-out")).toHaveText("Signed out — sign in again.");
  await noSidewaysScroll(page);
  await shot(page, "signed-out", info.project.name);
  await page.locator('input[type="password"]').fill(FIXTURE_PASSWORD);
  await page.getByRole("button", { name: /Open/ }).click();
  await expect(page.getByTestId("login")).toHaveCount(0);
  await expect(page).toHaveURL(/\/waivers\?/);
});

test("signed out in an open tab: the next screen's 401 says so", async ({ context, page }) => {
  const api = await serveFixtures(context, { gate: true });
  await page.goto(HOME);
  await page.locator('input[type="password"]').fill(FIXTURE_PASSWORD);
  await page.getByRole("button", { name: /Open/ }).click();
  await expect(page.getByTestId("team-name")).toBeVisible();
  api.signedIn = false;
  await page.getByTestId("foot-about").click(); // an in-app move: no reload, the 401 comes from the screen's fetch
  await expect(page.getByTestId("signed-out")).toHaveText("Signed out — sign in again.");
});

test("still waiting after 25 seconds: the card says so, and the answer shows when it comes", async ({ context, page }, info) => {
  test.skip(info.project.name === "phone", "26 s: desktop only");
  test.setTimeout(90_000);
  await serveFixtures(context);
  await context.route(/\/api\/my-week\?/, async (route: Route) => {
    await new Promise((r) => setTimeout(r, 27_000));
    return route.fallback();
  });
  await page.goto(HOME);
  await expect(page.getByTestId("loading")).toBeVisible();
  const card = page.getByTestId("error-card");
  await expect(card).toHaveAttribute("data-kind", "slow", { timeout: 30_000 });
  await expect(page.getByTestId("error-words")).toContainText("taking longer than usual");
  await expect(page.getByTestId("team-name")).toBeVisible({ timeout: 15_000 });
  await expect(card).toHaveCount(0);
});
