// Wave I-K (IK-3): the setup flow for ESPN and Yahoo — Fantasy platform → the league (ESPN: an id or a link; Yahoo:
// Connect with Yahoo → your leagues, or a league link) → the team → My Week; the specific errors (a private ESPN league,
// a wrong link), "Private league?" only when the server reads private leagues, Yahoo "coming soon" when the server has
// no Yahoo keys; the league remembered with "· ESPN" / "· Yahoo" in the switcher. Phone at 375 and desktop at 1300.
// The answers are the API's own, recorded from a fixture API on the SYNTHETIC leagues (IK-1's ESPN 4242 / 5150 and
// IK-2's Yahoo 461.l.4242, built from the documented shapes — not ESPN's or Yahoo's answers) into web/fixtures/ik3/ by
// web/e2e/ik3/record.sh. IK-1's cookie route (POST /api/espn/connect) and IK-2's connect route (/api/yahoo/connect) are
// answered here as their INTERFACES sections document them.
import { expect, test, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const DIR = join(import.meta.dirname, "..", "..", "fixtures", "ik3");
const read = (name: string) => readFileSync(join(DIR, name), "utf8");
const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out");
const ESPN = "espn:4242";
const YAHOO = "yahoo:461.l.4242";

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const YAHOO_PENDING_NOTE =
  "Yahoo leagues are coming soon: Yahoo has not switched on this app's access to fantasy data yet. Nothing is wrong with your league or your Yahoo sign-in. Sleeper and MyFantasyLeague leagues work today.";
// the server's switches for one test: the ESPN private switch, Yahoo's keys, the Yahoo connection
let server = { espnPrivate: false, yahooKeys: true, yahooConnected: false, yahooPending: false };
let asked: string[] = [];
let posted: { path: string; body: unknown }[] = [];

test.beforeEach(async ({ context, page, isMobile }) => {
  server = { espnPrivate: false, yahooKeys: true, yahooConnected: false, yahooPending: false };
  asked = [];
  posted = [];
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
  await serveFixtures(context);
  await context.route(/\/api\//, async (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    const q = url.searchParams;
    const send = (status: number, body: string) =>
      route.fulfill({ status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body });
    // PO 2026-10-05: Yahoo's keys are set but Yahoo has not opened the app's fantasy access — the server's two flags
    if (url.pathname === "/api/providers" && server.yahooPending)
      return send(200, JSON.stringify({ ...JSON.parse(read("providers.json")), yahoo_configured: false, yahoo_pending: true }));
    if (url.pathname === "/api/providers") return send(200, read(server.espnPrivate || !server.yahooKeys ? "providers_private_no_yahoo.json" : "providers.json"));
    if (url.pathname === "/api/espn/connect" && req.method() === "POST") {
      posted.push({ path: url.pathname, body: req.postDataJSON() });
      return send(200, JSON.stringify({ ok: true, connected: true }));
    }
    if (url.pathname === "/api/yahoo/connect") {
      // IK-2's route: off to Yahoo and back to /leagues?platform=yahoo with the ll_yahoo cookie (simulated)
      server.yahooConnected = true;
      return route.fulfill({ status: 302, headers: { Location: "/leagues?platform=yahoo" } });
    }
    if (url.pathname === "/api/yahoo/disconnect" && req.method() === "POST") {
      server.yahooConnected = false;
      return send(200, JSON.stringify({ ok: true }));
    }
    if (url.pathname === "/api/leagues") {
      asked.push(url.search);
      const espn = q.get("espn");
      if (espn !== null) {
        if (espn.includes("5150")) return send(404, read(server.espnPrivate ? "error_espn_private_form.json" : "error_espn_private.json"));
        if (espn.includes("teamId=3")) return send(200, read("espn_link_team.json"));
        if (espn.includes("4242")) return send(200, read("espn_4242.json"));
        if (/^\d+$/.test(espn.trim())) return send(404, read("error_espn_unknown.json"));
        return send(404, read("error_espn_link.json"));
      }
      if (q.get("yahoo_me") !== null) {
        if (server.yahooPending)
          return send(200, JSON.stringify({ ...JSON.parse(read("yahoo_me_not_configured.json")), pending: true, note: YAHOO_PENDING_NOTE }));
        if (!server.yahooKeys) return send(200, read("yahoo_me_not_configured.json"));
        return send(200, read(server.yahooConnected ? "yahoo_me_connected.json" : "yahoo_me_not_connected.json"));
      }
      const y = q.get("yahoo");
      if (y !== null) return y.includes("4242") ? send(200, read("yahoo_461.l.4242.json")) : send(404, read("error_yahoo_link.json"));
    }
    if (url.pathname === "/api/my-week") {
      if (q.get("league") === ESPN && q.get("team") === "1") return send(200, read("my-week_espn_4242_1.json"));
      if (q.get("league") === YAHOO && q.get("team") === "3") return send(200, read("my-week_yahoo_461.l.4242_3.json"));
    }
    return route.fallback();
  });
});

test("ESPN by id: a private league first, a wrong link, then the league → which team is yours → My Week", async ({ page }, info) => {
  await page.goto("/leagues");
  await page.getByTestId("platform-espn").click();
  await expect(page).toHaveURL(/platform=espn/);
  await expect(page.getByTestId("espn-form")).toBeVisible();
  await expect(page.getByTestId("username-form")).toHaveCount(0);
  await expect(page.getByTestId("platform-note")).toContainText("Unofficial: ESPN has no public API for fantasy leagues");
  await expect(page.getByTestId("platform-note")).toContainText("not verified on a live league yet");
  await page.getByTestId("setup-help").locator("summary").click();
  await expect(page.getByTestId("setup-help")).toContainText("fantasy.espn.com/football/league?leagueId=4242 is league 4242");

  // what ESPN gives: eight lines, each "partly", each said unverified
  const caps = page.getByTestId("provider-caps");
  await expect(caps).toContainText("What isuckatfantasy reads from ESPN leagues");
  await caps.locator("summary").click();
  await expect(caps.getByTestId("cap")).toHaveCount(8);
  await expect(caps.locator('[data-status="partial"]')).toHaveCount(8);
  await expect(caps.locator('[data-feature="scoring"]')).toContainText("as built, not verified on a live league yet");

  // a private league: the words and the fix; no cookie form (the server's switch is off)
  await page.getByTestId("espn-link").fill("5150");
  await page.getByTestId("espn-go").click();
  const err = page.getByTestId("espn-error");
  await expect(err).toContainText("ESPN league 5150 is private. ESPN has no sign-in for other apps");
  await expect(err).toHaveAttribute("data-code", "espn_league_private");
  await expect(page.getByTestId("setup-fix")).toContainText("Ask the commissioner to make the league public");
  await expect(page.getByTestId("espn-private")).toHaveCount(0);
  // not an ESPN link
  await page.getByTestId("espn-link").fill("https://example.com/x");
  await page.getByTestId("espn-go").click();
  await expect(err).toHaveText("That is not an ESPN league link or id.");
  await expect(err).toHaveAttribute("data-code", "espn_link_invalid");
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ik3-espn-error-${info.project.name}.png`), fullPage: true });

  // the league: the card, which team is yours, My Week
  await page.getByTestId("espn-link").fill("4242");
  await page.getByTestId("espn-go").click();
  const card = page.getByTestId("provider-card");
  await expect(card).toHaveAttribute("data-platform", "espn");
  await expect(card).toContainText("Synthetic Public League");
  await expect(card).toContainText("ESPN");
  await expect(page.getByTestId("espn-error")).toHaveCount(0);
  await expect(page.locator('[data-testid="setup-steps"] [aria-current="step"]')).toHaveAttribute("data-step", "team");
  await expect(card.getByTestId("team-option")).toHaveCount(10);
  await expect(card.getByTestId("provider-unmapped")).toContainText("2 of");
  expect(asked.at(-1)).toContain("espn=4242");
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ik3-espn-team-${info.project.name}.png`), fullPage: true });
  await card.locator('[data-testid="team-option"][data-roster="1"]').click();
  await expect(page).toHaveURL(/league=espn(%3A|:)4242&team=1/);
  await expect(page.getByTestId("team-name")).toHaveText("Gridiron Gurus");
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ik3-espn-week-${info.project.name}.png`), fullPage: false });

  // remembered on this device by its key; the switcher says ESPN
  const saved = await page.evaluate(() => JSON.parse(window.localStorage.getItem("ll.mflLeagues") ?? "[]"));
  expect(saved[0]).toMatchObject({ league_id: ESPN, roster_id: 1, team_name: "Gridiron Gurus" });
  await expect(page.locator("option", { hasText: "Synthetic Public League · ESPN" })).toHaveCount(1);
  await page.goto("/leagues");
  await expect(page.locator(`[data-testid="league-row"][data-league="${ESPN}"]`)).toContainText("ESPN");
});

test("ESPN: a team link pre-selects the team", async ({ page }) => {
  await page.goto("/leagues?platform=espn");
  await page.getByTestId("espn-link").fill("https://fantasy.espn.com/football/team?leagueId=4242&teamId=3");
  await page.getByTestId("espn-go").click();
  const picked = page.locator('[data-testid="provider-card"] [data-testid="team-option"][data-roster="3"]');
  await expect(picked).toHaveClass(/ring-accent/);
});

test("ESPN private league with the server's switch on: “Private league?” and the cookie words", async ({ page }, info) => {
  server.espnPrivate = true;
  await page.goto("/leagues?platform=espn");
  await page.getByTestId("espn-link").fill("5150");
  await page.getByTestId("espn-go").click();
  await expect(page.getByTestId("setup-fix")).toContainText("Or use “Private league?”");
  const box = page.getByTestId("espn-private");
  await expect(box).toBeVisible();
  await expect(box).toContainText("Your ESPN cookies stay in your browser; isuckatfantasy reads your league with them and never stores them.");
  await expect(page.getByTestId("espn-private-go")).toBeDisabled();
  await page.getByTestId("espn-s2").fill("AEB" + "x".repeat(60));
  await page.getByTestId("espn-swid").fill("{11111111-2222-3333-4444-555555555555}");
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ik3-espn-private-${info.project.name}.png`), fullPage: true });
  await page.getByTestId("espn-private-go").click();
  await expect.poll(() => posted.length).toBe(1);
  expect(posted[0]).toEqual({ path: "/api/espn/connect", body: { espn_s2: "AEB" + "x".repeat(60), swid: "{11111111-2222-3333-4444-555555555555}" } });
  await expect.poll(() => asked.filter((a) => a.includes("espn=5150")).length).toBe(2); // the league asked again with the cookie
});

test("Yahoo: Connect with Yahoo → your leagues → My Week; the switcher says Yahoo", async ({ page }, info) => {
  await page.goto("/leagues");
  await page.getByTestId("platform-yahoo").click();
  await expect(page).toHaveURL(/platform=yahoo/);
  await expect(page.getByTestId("platform-note")).toContainText("Yahoo's official Fantasy Sports API");
  const connect = page.getByTestId("yahoo-connect");
  await expect(connect).toHaveText("Connect with Yahoo");
  await expect(connect).toHaveAttribute("href", "/api/yahoo/connect");
  await expect(page.getByTestId("yahoo-note")).toContainText("Connect with Yahoo to list your leagues here.");
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ik3-yahoo-connect-${info.project.name}.png`), fullPage: true });

  await connect.click(); // → Yahoo → back to /leagues?platform=yahoo, connected
  await expect(page).toHaveURL(/\/leagues\?platform=yahoo/);
  const row = page.locator(`[data-testid="yahoo-league"][data-league="${YAHOO}"]`);
  await expect(row).toContainText("Synthetic Superflex League");
  await expect(row).toContainText("Your team: Synthetic Team 3");
  await expect(page.getByTestId("yahoo-disconnect")).toBeVisible();
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ik3-yahoo-leagues-${info.project.name}.png`), fullPage: true });
  await row.click();
  await expect(page).toHaveURL(/league=yahoo(%3A|:)461\.l\.4242&team=3/);
  await expect(page.getByTestId("team-name")).toHaveText("Synthetic Team 3");
  // PO 2026-10-05: Yahoo's attribution under a Yahoo league's screens, with the link back
  await expect(page.getByTestId("yahoo-attribution")).toHaveText(/Fantasy data provided by\s+Yahoo Fantasy/);
  await expect(page.getByTestId("yahoo-attribution").locator("a")).toHaveAttribute("href", "https://football.fantasysports.yahoo.com/");
  const saved = await page.evaluate(() => JSON.parse(window.localStorage.getItem("ll.mflLeagues") ?? "[]"));
  expect(saved[0]).toMatchObject({ league_id: YAHOO, roster_id: 3 });
  await expect(page.locator("option", { hasText: "Synthetic Superflex League · Yahoo" })).toHaveCount(1);
});

test("Yahoo by a league link: the league, the link's team pre-selected; a wrong link says so", async ({ page }) => {
  server.yahooConnected = true;
  await page.goto("/leagues?platform=yahoo");
  await page.getByTestId("yahoo-link").fill("not a league");
  await page.getByTestId("yahoo-go").click();
  await expect(page.getByTestId("yahoo-error")).toHaveAttribute("data-code", "yahoo_link_invalid");
  await page.getByTestId("yahoo-link").fill("https://football.fantasysports.yahoo.com/f1/4242/3");
  await page.getByTestId("yahoo-go").click();
  const card = page.getByTestId("provider-card");
  await expect(card).toHaveAttribute("data-platform", "yahoo");
  await expect(card.getByTestId("yahoo-attribution")).toContainText("Fantasy data provided by");
  await expect(card.getByTestId("team-option")).toHaveCount(12);
  await expect(card.locator('[data-testid="team-option"][data-roster="3"]')).toHaveClass(/ring-accent/);
  await noSidewaysScroll(page);
});

test("Yahoo: a sign-in that did not complete says so (IK-2's ?yahoo_error=)", async ({ page }) => {
  await page.goto("/leagues?platform=yahoo&yahoo_error=denied");
  await expect(page.getByTestId("yahoo-error-back")).toHaveText("Yahoo sign-in was cancelled: nothing was connected.");
  await expect(page.getByTestId("yahoo-connect")).toBeVisible();
});

test("Yahoo without the server's keys: “coming soon”, nothing to click", async ({ page }, info) => {
  server.yahooKeys = false;
  await page.goto("/leagues?platform=yahoo");
  await expect(page.getByTestId("yahoo-soon")).toHaveText("Connect with Yahoo — coming soon");
  await expect(page.getByTestId("yahoo-soon")).toBeDisabled();
  await expect(page.getByTestId("yahoo-connect")).toHaveCount(0);
  await expect(page.getByTestId("yahoo-form")).toHaveCount(0);
  await expect(page.getByTestId("yahoo-note")).toContainText("Yahoo sign-in is not set up on this server yet");
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ik3-yahoo-soon-${info.project.name}.png`), fullPage: true });
});

test("Yahoo's approval pending: “coming soon” in the server's words — nothing to click, nobody sent round the sign-in", async ({ page }, info) => {
  server.yahooPending = true;
  server.yahooConnected = true; // a manager who connected before the switch: still "coming soon", no league list
  await page.goto("/leagues?platform=yahoo");
  await expect(page.getByTestId("yahoo-soon")).toBeDisabled();
  await expect(page.getByTestId("yahoo-connect")).toHaveCount(0);
  await expect(page.getByTestId("yahoo-form")).toHaveCount(0);
  const note = page.getByTestId("yahoo-note");
  await expect(note).toHaveAttribute("data-pending", "1");
  await expect(note).toContainText("Yahoo has not switched on this app's access to fantasy data yet");
  await expect(note).toContainText("Nothing is wrong with your league or your Yahoo sign-in");
  await expect(page.getByTestId("yahoo-setup")).not.toContainText("expired");
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `po-yahoo-pending-${info.project.name}.png`), fullPage: true });
});

test("four platforms; the choice is remembered and ?platform= opens it", async ({ page }) => {
  await page.goto("/leagues?platform=espn");
  await expect(page.getByTestId("espn-form")).toBeVisible();
  await page.goto("/leagues");
  await expect(page.getByTestId("espn-form")).toBeVisible(); // remembered on this device
  for (const p of ["sleeper", "mfl", "espn", "yahoo"]) await expect(page.getByTestId(`platform-${p}`)).toBeVisible();
  await expect(page.getByTestId("other-platforms")).toHaveCount(0); // II-5's "ESPN or Yahoo?" is now the two choices
});
