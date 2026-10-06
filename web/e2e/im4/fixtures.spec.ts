// Wave I-M (IM-4): passkeys — against the REAL account API (the fixture API on http://localhost:8754, accounts on:
// `LEAGUE_LAB_ACCOUNTS=on`, a throwaway `LEAGUE_LAB_API_SECRET`; docs/ACCOUNTS.md § "Passkeys") with Chromium's
// virtual authenticator through CDP (`WebAuthn.enable`, `WebAuthn.addVirtualAuthenticator` with a resident key and
// user verification). No in-test account server: the challenge, the signature and the counter are checked by the API.
//   1. a guest with two leagues taps "Create an account with a passkey": the account is made, the leagues are saved;
//   2. sign out, "Sign in with a passkey": back in;
//   3. another device (a fresh browser holding the same passkey, as iCloud Keychain / Google Password Manager sync it):
//      "Sign in with a passkey" brings the leagues back with nothing typed;
//   4. "Add another passkey" (a second authenticator), the list shows both, remove the first: it no longer opens the
//      account; the last one cannot be removed ("Your only way in"); the account is deleted at the end.
// Phone at 375 and desktop at 1300. When nothing answers on :8754 the spec starts the API itself from ../api (the
// worktree's .env names the database; it needs scripts/hosted_accounts.sql applied); when the API answers but has no
// passkeys (its database lacks the IM-4 tables) the tests are skipped with that reason.
import { expect, test, type Browser, type BrowserContext, type CDPSession, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { join } from "node:path";

const API = process.env.IM4_API ?? "http://localhost:8754";
const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out");
const SCRUBS = "1389709692405551104";
const MFL = "mfl:70587";

let server: ChildProcess | null = null;
let skipWhy: string | null = null;

async function status(): Promise<Record<string, unknown> | null> {
  try {
    const r = await fetch(`${API}/api/account/status`, { signal: AbortSignal.timeout(5000) });
    return r.ok ? ((await r.json()) as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

test.beforeAll(async () => {
  test.setTimeout(240_000);
  let s = await status();
  if (!s && API === "http://localhost:8754") {
    const api = join(import.meta.dirname, "..", "..", "..", "api");
    const env: NodeJS.ProcessEnv = {
      ...process.env,
      LEAGUE_LAB_ACCOUNTS: "on",
      LEAGUE_LAB_CLIENT_IP: "x-forwarded-for", // each "device" below sends its own address: its own per-client limits
      LEAGUE_LAB_API_SECRET: randomBytes(24).toString("hex"), // throwaway, this run only
      LEAGUE_LAB_NOW: "2026-10-03T16:00:00Z",
      LEAGUE_LAB_SLEEPER_FIXTURES: join(api, "tests", "fixtures", "sleeper"),
      LEAGUE_LAB_MFL_FIXTURES: join(api, "tests", "fixtures", "mfl"),
      LEAGUE_LAB_MFL_YEAR: "2026",
      LEAGUE_LAB_PLAYER_IDS_CSV: join(api, "tests", "fixtures", "ff", "db_playerids.csv"),
      OMP_NUM_THREADS: "1",
      PYTHONPATH: ".",
    };
    delete env.LEAGUE_LAB_APP_PASSWORD;
    server = spawn("uv", ["run", "uvicorn", "league_lab_api.main:app", "--port", "8754"], { cwd: api, env, stdio: "ignore", detached: false });
    for (let i = 0; i < 70 && !s; i++) {
      await new Promise((r) => setTimeout(r, 3000));
      s = await status();
    }
  }
  if (!s) skipWhy = `no account API on ${API}`;
  else if (!(s.methods as string[] | undefined)?.includes("passkey")) skipWhy = `the API on ${API} has no passkeys (why: ${JSON.stringify(s.why)})`;
  else if (s.passkey_here !== true) skipWhy = `passkeys do not work on ${API} (LEAGUE_LAB_ACCOUNTS must be "on" for localhost)`;
});

test.afterAll(() => {
  server?.kill();
  server = null;
});

test.beforeEach(async ({ page, isMobile }) => {
  test.skip(skipWhy !== null, skipWhy ?? "");
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

/** A browser on its own "device": a context with its own storage, its own address (the API's per-address limits). */
async function device(browser: Browser, like: Page, isMobile: boolean, ua: string | undefined): Promise<{ context: BrowserContext; page: Page }> {
  const ip = `198.51.100.${1 + Math.floor(Math.random() * 250)}`;
  const context = await browser.newContext({
    viewport: like.viewportSize()!,
    isMobile,
    hasTouch: isMobile,
    userAgent: ua,
    serviceWorkers: "block",
    extraHTTPHeaders: { "x-forwarded-for": ip },
  });
  return { context, page: await context.newPage() };
}

/** Chromium's virtual authenticator on this page: a platform authenticator with a resident key and user verification. */
async function authenticator(page: Page): Promise<{ cdp: CDPSession; id: string }> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("WebAuthn.enable", { enableUI: false });
  const { authenticatorId } = await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: { protocol: "ctap2", transport: "internal", hasResidentKey: true, hasUserVerification: true, isUserVerified: true, automaticPresenceSimulation: true },
  });
  return { cdp, id: authenticatorId };
}

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const store = (page: Page, key: string) => page.evaluate((k) => window.localStorage.getItem(k), key);

test("a passkey account: create, sign out, sign in, another device, add and remove a passkey", async ({ browser, page, isMobile }, info) => {
  test.setTimeout(180_000);
  const ua = await page.evaluate(() => navigator.userAgent);
  const shot = (p: Page, name: string) => p.screenshot({ path: join(SHOTS, `im4-${name}-${info.project.name}.png`), fullPage: true });

  // ---- device A: a guest with two leagues (opened by link) and the Scrubs team picked
  const a = await device(browser, page, isMobile, ua);
  await a.context.addInitScript(
    ([scrubs, mfl]) => {
      if (window.localStorage.getItem("ll.mflLeagues")) return;
      window.localStorage.setItem(
        "ll.mflLeagues",
        JSON.stringify([
          { league_id: scrubs, name: "League of Scrubs", scoring_label: "12-team redraft · half PPR", total_rosters: 12, roster_id: 2, team_name: "MacZaddy" },
          { league_id: mfl, name: "MFL 70587", scoring_label: null, total_rosters: 12, roster_id: 1, team_name: null },
        ]),
      );
      window.localStorage.setItem("ll.league", scrubs);
      window.localStorage.setItem(`ll.team.${scrubs}`, "2");
    },
    [SCRUBS, MFL],
  );
  const keyA = await authenticator(a.page);
  await a.page.goto(`${API}/account`);
  await expect(a.page.getByTestId("passkey-start")).toContainText("An account keeps your leagues");
  await expect(a.page.getByTestId("passkey-create")).toHaveText("Create an account with a passkey");
  await expect(a.page.getByTestId("signin-form")).toContainText("Or use your email"); // the fixture API has a (stub) mailer too
  await noSidewaysScroll(a.page);
  await shot(a.page, "signed-out");

  await a.page.getByTestId("passkey-create").click();
  await expect(a.page.getByTestId("account-email-line")).toHaveText("Signed in with a passkey.");
  await expect(a.page.getByTestId("account-notice-line")).toHaveText("Your account is made and this device's leagues are saved to it.");
  await expect(a.page.getByTestId("saved-league")).toHaveCount(2);
  await expect(a.page.locator(`[data-testid="saved-league"][data-league="${SCRUBS}"]`).getByTestId("saved-default")).toHaveText("Default");
  await expect(a.page.getByTestId("passkey-row")).toHaveCount(1);
  await expect(a.page.getByTestId("passkey-only")).toHaveText("Your only way in");
  await expect(a.page.getByTestId("passkey-recovery")).toContainText("If you lose every device that holds your passkeys, this account cannot be recovered");
  await noSidewaysScroll(a.page);
  await shot(a.page, "account");
  const creds = (await keyA.cdp.send("WebAuthn.getCredentials", { authenticatorId: keyA.id })).credentials;
  expect(creds).toHaveLength(1);
  expect(creds[0].isResidentCredential).toBe(true);
  expect(creds[0].rpId).toBe("localhost");

  // ---- sign out, then back in with the passkey (nothing typed)
  await a.page.getByTestId("signout").click();
  await expect(a.page.getByTestId("passkey-signin")).toBeVisible();
  await a.page.getByTestId("passkey-signin").click();
  await expect(a.page.getByTestId("account-email-line")).toHaveText("Signed in with a passkey.");
  await expect(a.page.getByTestId("saved-league")).toHaveCount(2);
  const counted = (await keyA.cdp.send("WebAuthn.getCredentials", { authenticatorId: keyA.id })).credentials[0];
  expect(counted.signCount).toBeGreaterThan(0);

  // ---- device B: a fresh browser holding the same (synced) passkey — the leagues come back
  const b = await device(browser, page, isMobile, ua);
  const keyB1 = await authenticator(b.page);
  await keyB1.cdp.send("WebAuthn.addCredential", { authenticatorId: keyB1.id, credential: counted });
  await b.page.goto(`${API}/account`);
  expect(await store(b.page, "ll.mflLeagues")).toBeNull();
  await b.page.getByTestId("passkey-signin").click();
  await expect(b.page.getByTestId("account-email-line")).toHaveText("Signed in with a passkey.");
  await expect(b.page.getByTestId("saved-league")).toHaveCount(2);
  await expect(b.page.getByTestId("save-local")).toHaveCount(0);
  expect(await store(b.page, "ll.league")).toBe(SCRUBS); // the default league opens on this device
  expect(await store(b.page, `ll.team.${SCRUBS}`)).toBe("2");
  expect(JSON.parse((await store(b.page, "ll.mflLeagues")) ?? "[]").map((l: { league_id: string }) => l.league_id).sort()).toEqual([SCRUBS, MFL].sort());

  // ---- device B adds its own passkey (another authenticator: a second device or ecosystem), then removes the first
  await keyB1.cdp.send("WebAuthn.removeVirtualAuthenticator", { authenticatorId: keyB1.id });
  const keyB2 = await authenticator(b.page);
  await b.page.getByTestId("passkey-add").click();
  await expect(b.page.getByTestId("account-notice-line")).toHaveText("Passkey added.");
  await expect(b.page.getByTestId("passkey-row")).toHaveCount(2);
  await expect(b.page.getByTestId("passkey-only")).toHaveCount(0);
  await expect(b.page.getByTestId("passkey-add")).toHaveText("Add another passkey");
  await noSidewaysScroll(b.page);
  await shot(b.page, "two-passkeys");
  expect((await keyB2.cdp.send("WebAuthn.getCredentials", { authenticatorId: keyB2.id })).credentials).toHaveLength(1);
  await b.page.getByTestId("passkey-row").first().getByTestId("passkey-remove").click();
  await expect(b.page.getByTestId("passkey-remove-note")).toContainText("it no longer opens this account");
  await b.page.getByTestId("passkey-remove-go").click();
  await expect(b.page.getByTestId("passkey-row")).toHaveCount(1);
  await expect(b.page.getByTestId("passkey-only")).toHaveText("Your only way in");

  // ---- device A's passkey opens nothing now: the words say so
  await a.page.getByTestId("signout").click();
  await a.page.getByTestId("passkey-signin").click();
  await expect(a.page.getByTestId("account-problem")).toHaveText(
    "That passkey is not saved to any isuckatfantasy account (it may have been removed). Sign in another way, or create a new account.",
  );
  await expect(a.page.getByTestId("passkey-start")).toBeVisible();
  await noSidewaysScroll(a.page);
  await shot(a.page, "removed-passkey");

  // ---- clean up: device B deletes the account (its passkeys go with it)
  await b.page.getByTestId("delete-ask").click();
  await expect(b.page.getByTestId("delete-confirm")).toContainText("Your watchlist, your passkeys and any Yahoo or ESPN connection go too.");
  await b.page.getByTestId("delete-go").click();
  await expect(b.page.getByTestId("account-deleted")).toBeVisible();
  await a.context.close();
  await b.context.close();
});

test("a browser without passkeys says why and offers the email link instead", async ({ browser, page, isMobile }, info) => {
  const ua = await page.evaluate(() => navigator.userAgent);
  const c = await device(browser, page, isMobile, ua);
  await c.context.addInitScript(() => {
    // an app's built-in browser: no WebAuthn at all
    Object.defineProperty(window, "PublicKeyCredential", { value: undefined, configurable: true });
  });
  await c.page.goto(`${API}/account`);
  await expect(c.page.getByTestId("passkey-unsupported")).toContainText("This browser cannot use passkeys (an app's built-in browser often cannot).");
  await expect(c.page.getByTestId("passkey-create")).toHaveCount(0);
  await expect(c.page.getByTestId("signin-form")).toBeVisible();
  await noSidewaysScroll(c.page);
  await c.page.screenshot({ path: join(SHOTS, `im4-unsupported-${info.project.name}.png`), fullPage: true });
  await c.context.close();
});
