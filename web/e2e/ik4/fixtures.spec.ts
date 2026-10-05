// Wave I-K (IK-4): accounts, phase 1 — sign in with an emailed link; the leagues saved on one device come back on a
// fresh one (the fifth review § 9's acceptance: "returning on another device restores saved selections"); sign out;
// delete; and, with accounts off on the server (the fixtures' 404, or `enabled: false`), nothing about accounts shows.
// Phone at 375 and desktop at 1300.
// The account API is a small in-test server that keeps its state across browser contexts (one "database", one mailbox):
// its answers copy the shapes recorded from the real API on the clone (web/fixtures/ik4/*.json, written by
// api/tests/test_ik4.py::test_record_web_fixtures with IK4_RECORD=1). Everything else is the shared fixtures.
import { expect, test, type Browser, type BrowserContext, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { DYNASTY, SCRUBS, serveFixtures, TEST_LEAGUE } from "../fixtures";

const DIR = join(import.meta.dirname, "..", "..", "fixtures", "ik4");
const read = <T>(name: string) => JSON.parse(readFileSync(join(DIR, name), "utf8")) as T;
const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out");
const EMAIL = "manager@example.com";

type Row = Record<string, unknown> & { league: string; league_key: string; is_default: boolean; added_at: string };

/** The account API's contract, in memory: one per test (shared by every browser context the test opens). */
class AccountServer {
  enabled = true;
  mailbox = new Map<string, string>(); // email -> the last link's token (the "inbox")
  links = new Map<string, string>(); // token -> email (single use)
  sessions = new Map<string, string>(); // session id -> email
  users = new Map<string, { leagues: Row[]; prefs: { scope: string; key: string; value: unknown; updated_at: string }[] }>();
  calls: string[] = [];
  private n = 0;
  private template = read<{ leagues: Row[] }>("me.json").leagues[0];

  key(league: string, season: number): string {
    if (league.startsWith("mfl:") || league.startsWith("espn:") || league.startsWith("yahoo:")) {
      const [p, ext] = [league.slice(0, league.indexOf(":")), league.slice(league.indexOf(":") + 1)];
      return `${p}:${season}:${ext}`;
    }
    return `sleeper:${season}:${league}`;
  }

  me(email: string) {
    const u = this.users.get(email)!;
    return { ...read<object>("me.json"), email, leagues: u.leagues, default_league: u.leagues.find((l) => l.is_default)?.league ?? null, preferences: u.prefs, watchlist: [] };
  }

  /** Route the account API for one browser context (its own "cookie": the session id held in this closure). */
  async attach(context: BrowserContext): Promise<void> {
    let session: string | null = null;
    await context.route(/\/api\/account(\/|$)/, async (route: Route) => {
      const req = route.request();
      const url = new URL(req.url());
      const p = url.pathname.replace(/^\/api\/account/, "") || "/";
      const m = req.method();
      this.calls.push(`${m} ${url.pathname}`);
      const send = (status: number, body: unknown) => route.fulfill({ status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(body) });
      const email = session ? (this.sessions.get(session) ?? null) : null;
      if (p === "/status") {
        if (!this.enabled) return send(200, read("status_off.json"));
        return send(200, email ? { ...read<object>("status_signed_in.json"), email } : read("status_signed_out.json"));
      }
      if (!this.enabled) return send(404, { error: "Accounts are not on for this server yet.", code: "accounts_off" });
      const body = (req.postDataJSON() ?? {}) as Record<string, unknown>;
      if (p === "/login" && m === "POST") {
        const token = `tok${++this.n}`.padEnd(43, "x");
        this.links.set(token, String(body.email).trim().toLowerCase());
        this.mailbox.set(String(body.email).trim().toLowerCase(), token);
        return send(202, { ok: true, sent: true, minutes: 15 }); // the token is never in the answer
      }
      if (p === "/verify" && m === "POST") {
        const who = this.links.get(String(body.token));
        if (!who) return send(400, { error: "That sign-in link has expired or was already used. Ask for a new one.", code: "link_invalid" });
        this.links.delete(String(body.token));
        if (!this.users.has(who)) this.users.set(who, { leagues: [], prefs: [] });
        session = `s${++this.n}`;
        this.sessions.set(session, who);
        return send(200, { ok: true, email: who });
      }
      if (p === "/logout" && m === "POST") {
        if (session && body.everywhere) for (const [k, v] of this.sessions) if (v === email) this.sessions.delete(k);
        if (session) this.sessions.delete(session);
        session = null;
        return send(200, { ok: true, revoked: 1 });
      }
      if (!email) return send(401, { error: "Sign in with your email to see your account.", code: "signed_out" });
      const u = this.users.get(email)!;
      if (p === "/me" && m === "GET") return send(200, this.me(email));
      if (p === "/leagues" && m === "PUT") {
        for (const l of (body.leagues ?? []) as Record<string, unknown>[]) {
          const k = this.key(String(l.league), Number(l.season ?? 2026));
          const old = u.leagues.find((x) => x.league_key === k);
          const row: Row = { ...this.template, ...(old ?? {}), league: String(l.league), league_key: k, provider: k.split(":")[0], season: Number(k.split(":")[1]), external_id: k.split(":").slice(2).join(":"), is_default: old?.is_default ?? false, added_at: old?.added_at ?? `2026-10-05T12:00:0${u.leagues.length}+00:00` };
          for (const f of ["name", "team_name", "scoring_label", "total_rosters"]) if (l[f] !== undefined && l[f] !== null) row[f] = l[f];
          if ("team_id" in l) row.team_id = l.team_id;
          if (!old) {
            for (const f of ["name", "team_name", "scoring_label", "total_rosters", "team_id"]) if (!(f in l)) row[f] = null;
            u.leagues.push(row);
          } else Object.assign(old, row);
        }
        if (!u.leagues.some((l) => l.is_default) && u.leagues.length) u.leagues[0].is_default = true;
        return send(200, { ok: true, saved: ((body.leagues ?? []) as unknown[]).length });
      }
      if (p === "/default" && m === "PUT") {
        const k = this.key(String(body.league), Number(body.season ?? 2026));
        for (const l of u.leagues) l.is_default = l.league_key === k;
        u.leagues.sort((a, b) => Number(b.is_default) - Number(a.is_default) || a.added_at.localeCompare(b.added_at));
        return send(200, { ok: true });
      }
      if (p.startsWith("/leagues/") && m === "DELETE") {
        u.leagues = u.leagues.filter((l) => l.league_key !== decodeURIComponent(p.slice(9)));
        return send(200, { ok: true });
      }
      if (p === "/preferences" && m === "PUT") {
        u.prefs = [...u.prefs.filter((x) => !(x.scope === (body.scope ?? "global") && x.key === body.key)), { scope: String(body.scope ?? "global"), key: String(body.key), value: body.value, updated_at: "2026-10-05T12:00:00+00:00" }];
        return send(200, { ok: true });
      }
      if (p === "/" && m === "DELETE") {
        this.users.delete(email);
        for (const [k, v] of this.sessions) if (v === email) this.sessions.delete(k);
        session = null;
        return send(200, { ok: true, deleted: true });
      }
      return send(404, { error: `no account route ${m} ${p}` });
    });
  }
}

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

async function device(browser: Browser, like: Page, isMobile: boolean): Promise<{ context: BrowserContext; page: Page }> {
  const vp = like.viewportSize()!;
  const context = await browser.newContext({ viewport: vp, isMobile, hasTouch: isMobile, serviceWorkers: "block", baseURL: test.info().project.use.baseURL });
  return { context, page: await context.newPage() };
}

const store = (page: Page, key: string) => page.evaluate((k) => window.localStorage.getItem(k), key);

/** Ask for a link on this page, then open it (the mailbox is the in-test server's) and tap "Sign in on this device". */
async function signIn(page: Page, server: AccountServer) {
  await page.goto("/account");
  await page.getByTestId("account-email").fill(EMAIL);
  await page.getByTestId("account-send").click();
  await expect(page.getByTestId("link-sent")).toContainText(`A sign-in link is on its way to ${EMAIL}. It works once, for 15 minutes`);
  const token = server.mailbox.get(EMAIL)!;
  expect(token).toBeTruthy();
  await page.goto(`/account#signin=${token}`);
  await expect(page.getByTestId("link-confirm")).toContainText("Sign in to isuckatfantasy on this device?");
  await page.getByTestId("link-go").click();
  await expect(page.getByTestId("account-email-line")).toHaveText(`Signed in as ${EMAIL}.`);
  expect(new URL(page.url()).hash, "the token leaves the address").toBe("");
}

test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test("sign in on a fresh browser restores the saved leagues, the teams, the default and the Stats views", async ({ browser, context, page, isMobile }, info) => {
  const server = new AccountServer();
  await serveFixtures(context);
  await server.attach(context);
  await context.addInitScript(() => {
    if (!window.localStorage.getItem("ll.stats.views")) window.localStorage.setItem("ll.stats.views", JSON.stringify([{ name: "WR · season", qs: "position=WRTE&window=season" }]));
  });

  // device A: a guest picks their leagues (Sleeper username), opens one, then makes an account
  await page.goto("/leagues");
  await page.getByTestId("username").fill("fixture_user");
  await page.getByTestId("username-go").click();
  await expect(page.getByTestId("league-row")).toHaveCount(3);
  await expect(page.getByTestId("account-entry")).toContainText("Want your leagues on another phone or computer? Sign in with your email — no password.");
  await page.locator(`[data-testid="league-row"][data-league="${TEST_LEAGUE}"]`).click();
  await expect(page.getByTestId("myteam-foot")).toBeVisible();
  await page.getByTestId("overflow").click();
  await expect(page.getByTestId("menu-account")).toHaveText("Sign in to save your leagues");
  await page.getByTestId("menu-account").click();
  await expect(page.getByTestId("signin-form")).toContainText("No password: we email you a link.");
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ik4-signin-${info.project.name}.png`), fullPage: true });
  await signIn(page, server);

  // the three leagues on this device are offered, not taken: one tap saves them
  await expect(page.getByTestId("saved-none")).toBeVisible();
  await expect(page.getByTestId("save-local")).toContainText("This device has 3 leagues your account does not have yet.");
  await page.getByTestId("save-local-go").click();
  await expect(page.getByTestId("saved-league")).toHaveCount(3);
  await expect(page.getByTestId("save-local")).toHaveCount(0);
  const row = page.locator(`[data-testid="saved-league"][data-league="${TEST_LEAGUE}"]`);
  await expect(row).toContainText("Sleeper · 2026 · Fixture Falcons");
  await row.getByTestId("saved-make-default").click();
  await expect(page.getByTestId("saved-league").first()).toHaveAttribute("data-league", TEST_LEAGUE);
  await expect(row.getByTestId("saved-default")).toHaveText("Default");
  // the Stats view this browser had went to the account too (the restore merges and pushes)
  await expect.poll(() => server.users.get(EMAIL)?.prefs.find((x) => x.key === "stats.views")?.value).toEqual([{ name: "WR · season", qs: "position=WRTE&window=season" }]);
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ik4-account-${info.project.name}.png`), fullPage: true });

  // device B: a fresh browser — nothing on it — signs in and lands on the default league's week, no setup
  const b = await device(browser, page, isMobile);
  await serveFixtures(b.context);
  await server.attach(b.context);
  await b.page.goto("/account");
  await expect(b.page.getByTestId("signin-form")).toBeVisible();
  expect(await store(b.page, "ll.mflLeagues")).toBeNull();
  await signIn(b.page, server);
  await expect(b.page.getByTestId("saved-league")).toHaveCount(3);
  await expect(b.page.getByTestId("save-local")).toHaveCount(0);
  expect(await store(b.page, "ll.league")).toBe(TEST_LEAGUE);
  expect(await store(b.page, `ll.team.${TEST_LEAGUE}`)).toBe("3");
  expect(await store(b.page, `ll.team.${DYNASTY}`)).toBe("12");
  expect(await store(b.page, `ll.team.${SCRUBS}`)).toBe("2");
  expect(JSON.parse((await store(b.page, "ll.stats.views")) ?? "[]")).toEqual([{ name: "WR · season", qs: "position=WRTE&window=season" }]);
  await b.page.screenshot({ path: join(SHOTS, `ik4-restored-${info.project.name}.png`), fullPage: true });
  const meCalls = () => server.calls.filter((c) => c === "GET /api/account/me").length;
  const before = meCalls();
  await b.page.goto("/");
  await expect(b.page).toHaveURL(new RegExp(`league=${TEST_LEAGUE}&team=3`));
  await expect(b.page.getByTestId("myteam-foot")).toBeVisible();
  const options = await b.page.getByTestId("pick-league").locator("option").allTextContents();
  for (const name of ["Forever Unclean Dynasty", "League of Scrubs", "Test League"]) expect(options).toContain(name);
  await noSidewaysScroll(b.page);
  await b.page.screenshot({ path: join(SHOTS, `ik4-fresh-week-${info.project.name}.png`), fullPage: false });
  // a team picked on B in a saved league goes to the account (A sees it on its next read)
  await expect.poll(meCalls).toBeGreaterThan(before); // this page load's account read (the picks go to the server after it)
  await b.page.getByTestId("pick-team").selectOption("5");
  await expect(b.page).toHaveURL(new RegExp(`league=${TEST_LEAGUE}&team=5`));
  await expect.poll(() => server.users.get(EMAIL)?.leagues.find((l) => l.league === TEST_LEAGUE)?.team_id).toBe(5);
  await b.context.close();
});

test("sign out, sign out everywhere, a used link, delete the account", async ({ context, page }, info) => {
  const server = new AccountServer();
  await serveFixtures(context);
  await server.attach(context);
  await signIn(page, server);
  const used = [...server.mailbox.values()][0];
  await page.getByTestId("signout").click();
  await expect(page.getByTestId("signin-form")).toBeVisible();
  // the same link twice: the words, and the form to ask again
  await page.goto(`/account#signin=${used}`);
  await page.getByTestId("link-go").click();
  await expect(page.getByTestId("account-problem")).toHaveText("That sign-in link has expired or was already used. Ask for a new one.");
  await expect(page.getByTestId("signin-form")).toBeVisible();
  await signIn(page, server);
  await page.getByTestId("signout-all").click();
  await expect(page.getByTestId("signin-form")).toBeVisible();
  await signIn(page, server);
  await page.getByTestId("delete-ask").click();
  await expect(page.getByTestId("delete-confirm")).toContainText("This deletes your email address, your saved leagues and your preferences from isuckatfantasy now.");
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `ik4-delete-${info.project.name}.png`), fullPage: true });
  await page.getByTestId("delete-go").click();
  await expect(page.getByTestId("account-deleted")).toHaveText("Your account is deleted. The leagues on this device stay here.");
  expect(server.users.has(EMAIL)).toBe(false);
  await expect(page.getByTestId("account-privacy")).toContainText("nothing else");
});

test("accounts off: no entry, no menu item, one plain line on /account — guest use as before", async ({ context, page }) => {
  await serveFixtures(context); // no account routes: /api/account/status answers 404 (an older server)
  await page.goto(`/?league=${TEST_LEAGUE}&team=3`);
  await expect(page.getByTestId("myteam-foot")).toBeVisible();
  await page.getByTestId("overflow").click();
  await expect(page.getByTestId("menu-leagues")).toBeVisible();
  await expect(page.getByTestId("menu-account")).toHaveCount(0);
  await page.goto("/leagues");
  await expect(page.getByTestId("setup-steps")).toBeVisible();
  await expect(page.getByTestId("account-entry")).toHaveCount(0);
  await page.goto("/account");
  await expect(page.getByTestId("account-off")).toHaveText("Accounts are not on yet. isuckatfantasy remembers your leagues on this device; pick a league to start.");

  const server = new AccountServer(); // the server's own "off" (no Resend key): enabled false
  server.enabled = false;
  await server.attach(context);
  await page.goto("/leagues");
  await expect(page.getByTestId("setup-steps")).toBeVisible();
  await expect(page.getByTestId("account-entry")).toHaveCount(0);
  expect(server.calls).toEqual(["GET /api/account/status"]);
  // About says what an account would keep
  await page.goto(`/about?league=${TEST_LEAGUE}&team=3`);
  await expect(page.getByTestId("account-notice")).toContainText("An account is optional.");
});
