// Two Streamlit behaviours the side-by-side relies on, checked N times each (node e2e/streamlit-probe.mjs):
//  1. Back: Home → (sidebar) Player, then the browser's Back — does My Week come back?  (MEASURE_ST_URL, default :8577)
//  2. With the beta password on (an instance started with LEAGUE_LAB_APP_PASSWORD, PROBE_GATED_URL + PROBE_GATED_PASSWORD):
//     after signing in, does a player name in a card open a tab that asks for the password again?
// Prints JSON. Chromium via PLAYWRIGHT_BROWSERS_PATH.
import { chromium, devices } from "@playwright/test";

const ST = process.env.MEASURE_ST_URL ?? "http://localhost:8577";
const GATED = process.env.PROBE_GATED_URL;
const PW = process.env.PROBE_GATED_PASSWORD ?? "";
const N = Number(process.env.PROBE_N ?? 10);
const WEEK = "/?league=1321941740235550720&team=12";
const CARD = /apart, (a coin flip|a lean|clear)/;
const IPHONE = { ...devices["iPhone 13"] };
delete IPHONE.defaultBrowserType;
const profiles = { phone: { ...IPHONE, viewport: { width: 390, height: 844 } }, desktop: { viewport: { width: 1300, height: 900 } } };

const b = await chromium.launch();
const out = {};
for (const [name, opts] of Object.entries(profiles)) {
  const mobile = name === "phone";
  let backOk = 0;
  const entries = [];
  for (let i = 0; i < N; i++) {
    const ctx = await b.newContext(opts);
    const page = await ctx.newPage();
    await page.goto(ST + WEEK);
    await page.getByText(CARD).first().waitFor({ timeout: 120000 });
    await page.locator('[data-testid="stStatusWidget"]').waitFor({ state: "detached", timeout: 60000 }).catch(() => {});
    if (mobile) {
      await page.locator('[data-testid="stExpandSidebarButton"]').tap();
      await page.waitForTimeout(400);
    }
    const h0 = await page.evaluate(() => history.length);
    const link = page.locator('[data-testid="stSidebarNavLink"]').filter({ hasText: /^Player$/ }).first();
    await (mobile ? link.tap() : link.click());
    await page.getByText("Pick a player above").first().waitFor({ timeout: 60000 });
    await page.locator('[data-testid="stStatusWidget"]').waitFor({ state: "detached", timeout: 60000 }).catch(() => {});
    entries.push((await page.evaluate(() => history.length)) - h0);
    await page.goBack();
    const ok = await page.getByText(CARD).first().waitFor({ timeout: 8000 }).then(() => true).catch(() => false);
    if (ok) backOk++;
    await ctx.close();
  }
  out[name] = { back_returns_to_my_week: `${backOk} of ${N}`, history_entries_per_hop: entries };
  console.error(name, JSON.stringify(out[name]));
}
if (GATED) {
  const ctx = await b.newContext(profiles.desktop);
  const page = await ctx.newPage();
  await page.goto(GATED + WEEK);
  const box = page.locator('input[type="password"]').first();
  await box.fill(PW);
  await box.press("Enter");
  await page.getByText(CARD).first().waitFor({ timeout: 120000 });
  const popupP = ctx.waitForEvent("page", { timeout: 15000 });
  await page.locator('[data-testid="stMarkdownContainer"] a[href^="Player?"]').first().click();
  const popup = await popupP;
  await popup.waitForLoadState();
  const asked = await popup.getByText("Enter the password from your invite").first().waitFor({ timeout: 60000 }).then(() => true).catch(() => false);
  out.gate = { new_tab_asks_for_password_again: asked, url: popup.url().replace(GATED, "") };
  await ctx.close();
}
await b.close();
console.log(JSON.stringify(out, null, 2));
