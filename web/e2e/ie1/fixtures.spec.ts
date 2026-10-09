// Wave I-E (IE-1): the casual-user review on fixtures — My Week as a weekly action list (the review's roster, MFL 70587
// team 8 "Big Mac Attack", and League of Scrubs roster 2), Waivers' cards this week first, the dial as the effect on
// their starters, the Finder's cheaper package first. Phone at 375 px (inside the phone project) and desktop at 1300.
//
// The answers are the API's own, recorded from a live API on the fixtures (MFL 70587, the Sleeper fixtures, the ESPN
// overlay: McConkey Questionable, Jefferson Out) into web/fixtures/ie1/api_ie1.json and replayed here. Re-record:
//   (api on :8748 with LEAGUE_LAB_MFL_FIXTURES / _SLEEPER_FIXTURES / _ESPN_FIXTURES / _PLAYER_IDS_CSV set, the gate off)
//   IE1_RECORD=http://127.0.0.1:8748 FIXTURES_PORT=8616 npm run e2e:fixtures -- e2e/ie1
import { expect, test, type Locator, type Page, type Route } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { serveFixtures, SCRUBS } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "ie1", "api_ie1.json");
const RECORD = process.env.IE1_RECORD ?? "";
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = !RECORD && existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};
const MINE = /\/api\/(my-week|waivers|trades|team|rosters|leagues\?mfl)|mfl/i;
const MFL = "mfl:70587";
const EFFECT = ["Makes their lineup weaker", "About even", "Improves their lineup", "Improves it a lot"];

const keyOf = (u: URL, body: string | null) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return u.pathname + (q.length ? `?${new URLSearchParams(q).toString()}` : "") + (body ? ` ${body}` : "");
};

async function answer(route: Route) {
  const req = route.request();
  const u = new URL(req.url());
  const body = req.method() === "POST" ? req.postData() : null;
  const key = keyOf(u, body);
  if (!MINE.test(decodeURIComponent(u.pathname + u.search))) return route.fallback();
  if (RECORD) {
    const r = await fetch(RECORD + u.pathname + u.search, body ? { method: "POST", body, headers: { "content-type": "application/json" } } : {});
    const text = await r.text();
    let parsed: unknown = text;
    try {
      parsed = JSON.parse(text);
    } catch {
      /* keep the text */
    }
    saved[key] = { status: r.status, body: parsed };
    return route.fulfill({ status: r.status, contentType: "application/json", body: text });
  }
  const s = saved[key];
  if (!s) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: `no fixture for ${key}` }) });
  return route.fulfill({ status: s.status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(s.body) });
}

test.afterAll(() => {
  if (RECORD) {
    mkdirSync(dirname(FILE), { recursive: true });
    writeFileSync(FILE, JSON.stringify(saved, null, 1) + "\n");
  }
});

test.beforeEach(async ({ context, page }, info) => {
  test.skip(!RECORD && !existsSync(FILE), "no recording yet: run with IE1_RECORD (see the header)");
  await serveFixtures(context);
  await context.route(/\/api\//, answer);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

async function tap(page: Page, loc: Locator, isMobile: boolean) {
  if (isMobile) await loc.tap();
  else await loc.click();
}

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `ie1-${name}-${project}.png`), fullPage: true });

test("the review's roster: one receiver decision, already in the MFL lineup, where to change it, nothing submitted", async ({ page, isMobile }, info) => {
  await page.goto(`/?league=${encodeURIComponent(MFL)}&team=8`);
  const acts = page.getByTestId("week-actions");
  await expect(acts).toBeVisible();
  const cards = acts.getByTestId("action-card");
  await expect(cards.first()).toBeVisible();
  expect(await cards.count()).toBeLessThanOrEqual(3);
  const first = cards.first();
  await expect(first).toHaveAttribute("data-kind", "close");
  await expect(first.getByTestId("action-kind")).toContainText("Close call");
  await expect(first.getByTestId("action-text")).toHaveText("Keep Addison and Nabers ahead of McConkey for now.");
  await expect(first.getByTestId("action-reason")).toContainText("McConkey's questionable status breaks the tie. Check his status again before kickoff.");
  await expect(first.getByTestId("action-submitted")).toHaveText("✓ Already in your MFL lineup — nothing to change.");
  await expect(first.getByTestId("action-lock")).toHaveText("before Sun 4:05 PM ET");
  await expect(first.getByTestId("action-slot")).toHaveText("WR/TE 2 · WR/TE 3");
  // the analysis is one tap away (layer 3): the two calls behind the one decision
  await expect(first.getByTestId("action-call").first()).toBeHidden();
  await tap(page, first.getByTestId("action-why").locator("summary"), isMobile);
  await expect(first.getByTestId("action-call")).toHaveCount(2);
  await expect(first.getByTestId("action-call").first()).toContainText(/McConkey|Nabers/);
  // the rest is one line, the claim from Waivers is the third kind of action (after the lineup calls), with its link
  await expect(page.getByTestId("set-line")).toContainText("The rest of your lineup is set — nothing to change.");
  const move = acts.locator('[data-testid="action-card"][data-kind="move"]');
  await expect(move).toHaveCount(1);
  await expect(move.getByTestId("action-text")).toHaveText("Claim Dalton Schultz: about 3 more starter points this week.");
  await expect(move.getByTestId("action-open")).toHaveAttribute("href", /\/waivers\?league=mfl%3A70587&team=8|\/waivers\?league=mfl:70587&team=8/);
  await expect(move.getByTestId("action-submitted")).toContainText("Nothing is claimed from here");
  const link = page.getByTestId("edit-link");
  await expect(link).toHaveText("Open MFL to edit your lineup ↗");
  await expect(link).toHaveAttribute("href", "https://www44.myfantasyleague.com/2026/options?L=70587&O=02");
  await expect(link).toHaveAttribute("target", "_blank");
  await expect(page.getByTestId("nothing-submitted")).toHaveText("isuckatfantasy never changes your lineup or claims; it tells you what to do in your league's app.");
  // the action list comes before the lineup table on a phone (the first screen answers "what do I do?")
  const a = await acts.boundingBox();
  const t = await page.getByTestId("lineup-head").boundingBox();
  if (isMobile && a && t) expect(a.y).toBeLessThan(t.y);
  await noSidewaysScroll(page);
  await shot(page, "team8-week", info.project.name);
});

test("Scrubs roster 2: the change before the first kickoff, and the Sleeper link", async ({ page }, info) => {
  await page.goto(`/?league=${SCRUBS}&team=2`);
  const first = page.getByTestId("action-card").first();
  await expect(first).toBeVisible();
  await expect(first).toHaveAttribute("data-kind", "change");
  await expect(first).toHaveAttribute("data-submitted", "false");
  await expect(first.getByTestId("action-kind")).toContainText("Roster alert"); // IN-5: was "Change needed"
  await expect(first.getByTestId("action-text")).toHaveText("Start Wilson at FLEX (or Croskey-Merritt: a coin flip) in place of Jefferson.");
  await expect(first.getByTestId("action-reason")).toContainText("Jefferson is out");
  await expect(first.getByTestId("action-submitted")).toHaveText("→ Not in your Sleeper lineup yet: make the change in Sleeper.");
  await expect(first.getByTestId("action-lock")).toHaveText("before Sun 9:30 AM ET");
  await expect(page.getByTestId("edit-link")).toHaveAttribute("href", `https://sleeper.com/leagues/${SCRUBS}`);
  await expect(page.getByTestId("edit-link")).toHaveText("Open Sleeper to edit your lineup ↗");
  await expect(page.getByTestId("set-line")).toContainText("The rest of your lineup is set");
  expect(await page.getByTestId("action-card").count()).toBeLessThanOrEqual(3);
  await noSidewaysScroll(page);
  await shot(page, "scrubs2-week", info.project.name);
});

test("Waivers: this week's gain is the number, the four-week total is second and cumulative, no triple copy", async ({ page }, info) => {
  await page.goto(`/waivers?league=${encodeURIComponent(MFL)}&team=8`);
  await expect(page.getByTestId("waiver-answer")).toHaveText("The three strongest claims below: each helps this week. Each card's total is its gain over weeks 4–7."); // integ: II-4's intro
  const top = page.getByTestId("top-move");
  await expect(top).toHaveCount(3);
  // PO (I-E): the three are ordered by this week's gain — Schultz (+3.0) first; the Falcons' bye cover (+1.2 this week,
  // +12.8 over the four weeks, cumulative) last; Vele is labelled the alternative to Schultz for the same spot
  const f = top.first();
  await expect(f.getByTestId("claim-gain")).toHaveText("+3.0");
  await expect(f).toContainText("this week");
  await expect(f.getByTestId("claim-lead")).toHaveText("Dalton Schultz instead of Ladd McConkey: about 3 more starter points this week.");
  await expect(f.getByTestId("claim-total")).toHaveText("+8.1 over weeks 4–7 in total.");
  await expect(top.nth(1).getByTestId("claim-alternative")).toHaveText("Instead of Dalton Schultz:");
  const falcons = top.nth(2);
  await expect(falcons.getByTestId("claim-gain")).toHaveText("+1.2");
  await expect(falcons.getByTestId("claim-lead")).toHaveText("Falcons defense instead of Jaguars: about 1 more starter point this week.");
  await expect(falcons.getByTestId("claim-total")).toHaveText("+12.8 over weeks 4–7 in total.");
  await expect(page.getByTestId("not-additive")).toContainText("Each claim is weighed on its own");
  // Help now starts after the three: its first row is none of them, and not the answer either
  const row = page.getByTestId("view-move").first();
  await expect(row).toBeVisible();
  const rowLead = (await row.getByTestId("claim-lead").textContent()) ?? "";
  const answerText = (await page.getByTestId("waiver-answer").textContent()) ?? "";
  expect(rowLead).not.toEqual(answerText);
  for (let i = 0; i < 3; i++) expect(rowLead).not.toEqual((await top.nth(i).getByTestId("claim-lead").textContent()) ?? "");
  await noSidewaysScroll(page);
  await shot(page, "team8-waivers", info.project.name);
});

test("the dial is the effect on their starters: outcome words, no 0–100, no interest", async ({ page }, info) => {
  await page.goto(`/trade-calc?league=${encodeURIComponent(MFL)}&team=8&partner=12&give=12490&get=10229`);
  const dial = page.getByTestId("dial");
  await expect(dial).toBeVisible();
  await expect(dial.getByTestId("dial-title")).toHaveText("Effect on their starters");
  const label = (await dial.getByTestId("dial-label").textContent()) ?? "";
  expect(EFFECT).toContain(label.trim());
  await expect(dial.getByTestId("dial-score")).toHaveCount(0);
  await expect(dial).not.toContainText("/ 100");
  await expect(dial).not.toContainText(/interest|say no|Likely/i);
  await expect(dial.locator("svg")).toHaveAttribute("aria-label", /^Effect on their starters: /);
  await noSidewaysScroll(page);
  await shot(page, "team8-dial", info.project.name);
});

test("the Finder leads with the cheaper package and names the extra player as optional", async ({ page }, info) => {
  // IT-1 (re-saved on the calculator's basis): the cheaper package and its optional extra are read from the saved
  // answer (today: Millertime, Kelce for Coker, + RJ Harvey optional); not worth proposing, so behind Explore
  type Row = { partner_team: string; tier?: string; cheaper_than?: { words: string } | null; optional?: { words: string } | null };
  const ans = Object.entries(saved).find(([k]) => k.includes("/api/trades/partners") && k.includes("team=12"))![1].body as { partners: Row[] };
  const lead = ans.partners.find((r) => r.cheaper_than)!;
  const extra = ans.partners.find((r) => r.optional && r.partner_team === lead.partner_team)!;
  await page.goto(`/trades?league=${encodeURIComponent(MFL)}&team=12`);
  await expect(page.getByTestId("best-partner")).toBeVisible();
  if (lead.tier !== "credible") await page.getByTestId("explore").locator("summary").first().click();
  const rows = page.getByTestId("partner-row").filter({ hasText: lead.partner_team });
  await expect(rows.first()).toBeVisible();
  await expect(rows.filter({ has: page.getByTestId("partner-cheaper") }).first().getByTestId("partner-cheaper")).toHaveText(lead.cheaper_than!.words);
  await expect(page.getByTestId("partner-optional").first()).toContainText(extra.optional!.words);
  expect(extra.optional!.words).toContain("does not change your gain");
  await expect(rows.first().getByTestId("partner-label")).toContainText("Their starters");
  for (const t of await page.getByTestId("partner-label").allTextContents()) expect(EFFECT.some((e) => t.includes(e)), t).toBe(true);
  await noSidewaysScroll(page);
  await shot(page, "team12-finder", info.project.name);
});
