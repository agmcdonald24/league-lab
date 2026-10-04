// Wave I-F (U-1): usage tracking — one POST /api/usage per screen view (the route name, the league, the team number;
// nothing else), sent with navigator.sendBeacon after the screen is on screen, never twice for the same screen, never
// before sign-in; a failing count never shows; the notice on About. Test League (fixtures), phone 375 and desktop 1300.
import { expect, test, type BrowserContext } from "@playwright/test";
import { FIXTURE_PASSWORD, serveFixtures, TEST_LEAGUE } from "../fixtures";

type Count = { screen: string; league: string | null; roster_id: number | null; type: string };

/** Answer the counts before the fixture server does (it would 404 them) and keep what was sent. */
async function counts(context: BrowserContext, status = 204): Promise<Count[]> {
  const got: Count[] = [];
  await context.route(/\/api\/usage$/, async (route) => {
    const req = route.request();
    const type = `${req.resourceType()} ${(req.headers()["content-type"] ?? "").toLowerCase()}`;
    got.push({ ...(JSON.parse(req.postData() ?? "{}") as Omit<Count, "type">), type });
    await route.fulfill({ status, body: "" });
  });
  return got;
}

const Q = `league=${TEST_LEAGUE}&team=3`;

test("one count per screen view: screen, league, team — and nothing else", async ({ context, page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await serveFixtures(context);
  const got = await counts(context);
  await page.goto(`/?${Q}`);
  await expect(page.getByTestId("myteam-foot")).toBeVisible();
  await expect.poll(() => got.length).toBe(1);
  expect(got[0]).toEqual({ screen: "week", league: TEST_LEAGUE, roster_id: 3, type: "ping text/plain;charset=utf-8" }); // a beacon

  // in-app navigation (no reload): the new screen counts once, Back to My Week is a new view
  await page.getByTestId("foot-about").click();
  await expect(page.getByTestId("usage-notice")).toHaveText(
    "isuckatfantasy counts screen views — which screen, which league and team, when — and nothing about you. " +
      // ---- INF-1 (Wave I-I): the notice names Google Analytics and what it is sent
      "It also uses Google Analytics: the same screen views and a few taps (a player opened, Compare, a trade evaluated, " +
      "the link to edit your lineup), with the league and team numbers and the app's version — never your username, " +
      "team name or password. Google sets a cookie to tell visits apart and sees your browser and rough location, as on " +
      "any site that uses it.",
  );
  await expect.poll(() => got.map((c) => c.screen)).toEqual(["week", "about"]);
  await page.goBack();
  await expect(page.getByTestId("myteam-foot")).toBeVisible();
  await expect.poll(() => got.map((c) => c.screen)).toEqual(["week", "about", "week"]);
  await page.waitForTimeout(300); // nothing else arrives (the URL rewrite of the league / team is not a view)
  expect(got).toHaveLength(3);
});

test("not before sign-in; a failing count never shows", async ({ context, page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await serveFixtures(context, { gate: true });
  const got = await counts(context, 500);
  await page.goto(`/?${Q}`);
  await expect(page.getByTestId("login")).toBeVisible();
  await page.waitForTimeout(300);
  expect(got).toEqual([]);
  await page.getByPlaceholder("Password").fill(FIXTURE_PASSWORD);
  await page.getByRole("button", { name: "Open isuckatfantasy" }).click();
  await expect(page.getByTestId("myteam-foot")).toBeVisible();
  await expect.poll(() => got.length).toBe(1);
  await expect(page.locator(".ll-error")).toHaveCount(0);
});
