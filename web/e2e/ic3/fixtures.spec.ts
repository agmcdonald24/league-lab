// Wave I-C (IC-3): dad's league end to end — paste 70587 → the league card reads the lineup and the scoring back in
// the league's own words and shows the scoring check → pick "Knight Train" → My Week → Team / Waivers / Season answer.
// Phone (390) and desktop (1300) like every fixture e2e; the 375-px check runs inside the phone project.
//
// The answers are the API's own, recorded from a live API on the MFL fixtures (api/tests/fixtures/mfl/70587) into
// web/fixtures/mfl/api_70587.json and replayed here (no API, no database). Re-record after the Wave I-C merge:
//   (api on :8743 with LEAGUE_LAB_MFL_FIXTURES / _SLEEPER_FIXTURES / _PLAYER_IDS_CSV set, the gate off)
//   IC3_RECORD=http://localhost:8743 npm run e2e:fixtures -- e2e/ic3
// The strict lineup assertions (8 slots, the team units seated and priced) hold once IC-2's slots are in the API that
// recorded the file; on an older recording the card must say which starters it could not read (it never hides them).
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "mfl", "api_70587.json");
const RECORD = process.env.IC3_RECORD ?? "";
type Saved = { status: number; body: unknown };
// a recording starts empty (no stale answer survives a re-record); a replay reads the file
const saved: Record<string, Saved> = !RECORD && existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};
const MINE = /mfl|70587|scoring-check|username=test_manager/i;
const KEY = "mfl:70587";

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return u.pathname + (q.length ? `?${new URLSearchParams(q).toString()}` : "");
};

async function answer(route: Route) {
  const u = new URL(route.request().url());
  const key = keyOf(u);
  if (!MINE.test(decodeURIComponent(key))) return route.fallback();
  if (RECORD) {
    const r = await fetch(RECORD + u.pathname + u.search);
    const text = await r.text();
    let body: unknown = text;
    try {
      body = JSON.parse(text);
    } catch {
      /* keep the text */
    }
    saved[key] = { status: r.status, body };
    return route.fulfill({ status: r.status, contentType: "application/json", body: text });
  }
  const s = saved[key];
  if (!s) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: `no fixture for ${key}` }) });
  return route.fulfill({ status: s.status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(s.body) });
}

test.afterAll(() => {
  if (RECORD) writeFileSync(FILE, JSON.stringify(saved, null, 1) + "\n");
});

test.beforeEach(async ({ context }) => {
  await serveFixtures(context);
  await context.route(/\/api\//, answer);
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

type Card = { lineup: { text: string; unread: string[] }; scoring: { text: string; source: string } };
const recorded = <T,>(k: string) => (saved[k]?.body ?? null) as T | null;

test("dad's league 70587: the card reads back the lineup and the scoring, then Knight Train's week", async ({ page }, info) => {
  const lg = recorded<{ card: Card; teams: { roster_id: number; team_name: string }[] }>("/api/leagues?mfl_search=70587");
  test.skip(!RECORD && !lg, "no recording yet: run with IC3_RECORD (see the header)");
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });

  await page.goto("/");
  await expect(page.getByTestId("leagues")).toBeVisible();
  await page.getByTestId("mfl-link").fill("70587");
  await page.getByTestId("mfl-go").click();

  const card = page.getByTestId("mfl-card");
  await expect(card).toContainText("Make Football Great Again");
  const rb = page.getByTestId("league-card");
  await expect(rb).toBeVisible();
  const lineupText = (await rb.getByTestId("card-lineup").textContent()) ?? "";
  expect(lineupText).toMatch(/^Your lineup: /);
  if (lineupText.includes("TMQB")) {
    // IC-2's slots: the league's own lineup, in its own words
    expect(lineupText).toBe("Your lineup: TMQB · 2 RB · 3 WR/TE · TMPK · DEF");
    await expect(rb.getByTestId("card-unread")).toHaveCount(0);
  } else {
    // before IC-2: the starters the translation dropped are named on the card, never hidden
    await expect(rb.getByTestId("card-unread")).toContainText("TMQB, WR/TE, TMPK");
  }
  await expect(rb.getByTestId("card-scoring")).toContainText("Scoring:");
  const scoring = (await rb.getByTestId("card-scoring").textContent()) ?? "";
  if (/6 \/ 9 \/ 12/.test(scoring)) expect(scoring).toMatch(/per 10/); // IC-1's spec: TDs by distance, 1 pt per 10 yards
  // the scoring check: a number line once IC-1's route answers, else the plain "not available" line
  const check = rb.getByTestId("card-check");
  await expect(check).toHaveText(/Week \d+ check: we match your league's points for|not available for this league yet/);
  await expect(page.getByTestId("mfl-team")).toHaveCount(12);
  await noSidewaysScroll(page);
  await card.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `ic3-70587-card-${info.project.name}.png`) });

  // pick Knight Train → My Week
  await page.getByTestId("mfl-team").filter({ hasText: "Knight Train" }).click();
  await expect(page.getByTestId("my-week")).toBeVisible();
  await expect(page.getByTestId("lineup")).toBeVisible(); // the week's answer is in (when recording: saved too)
  type Row = { slot: string; role: string; player_name: string | null; position: string | null; value: number | null; flag: string };
  const week = recorded<{ lineup: Row[]; lineup_full: Row[] }>("/api/my-week?league=mfl%3A70587&team=1");
  const starters = (week?.lineup ?? []).filter((r) => r.role === "starter");
  const rows = page.getByTestId("lineup").locator("tbody tr");
  if (week) await expect(rows).toHaveCount(week.lineup.length);
  if (lineupText.includes("TMQB")) {
    // the acceptance: 8 slots in the league's words, the units seated and priced; a seat is empty only when nobody
    // eligible can play (injury / bye), never for want of a slot; no WR or unit is "Can't play" for want of a slot
    expect(starters.map((r) => r.slot)).toEqual(["team QB", "RB1", "RB2", "WR/TE 1", "WR/TE 2", "WR/TE 3", "team K", "DEF"]);
    for (const r of starters) {
      if (r.player_name === null) expect(r.flag, r.slot).toMatch(/^EMPTY/);
      else expect(r.value ?? 0, `${r.slot} ${r.player_name}`).toBeGreaterThan(0);
    }
    expect(starters.find((r) => r.slot === "team QB")?.position).toBe("TMQB");
    expect(starters.find((r) => r.slot === "team K")?.position).toBe("TMPK");
    for (const r of (week?.lineup_full ?? []).filter((x) => x.role === "unplayable"))
      expect(["OUT", "IR", "BYE", "DOUBTFUL", "SUSPENDED", "PUP", "NA"], `${r.player_name} ${r.flag}`).toContain(r.flag.split(" ")[0].toUpperCase());
    await expect(page.getByTestId("lineup")).toContainText("team QB");
  }
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `ic3-70587-week-${info.project.name}.png`), fullPage: true });

  // Team / Waivers / Season answer for the same league and team (no error line)
  for (const [path, id, done] of [["/team", "team", "team-answer"], ["/waivers", "waivers", "waiver-answer"], ["/ros", "ros", "ros-answer"]] as const) {
    await page.goto(`${path}?league=${encodeURIComponent(KEY)}&team=1`);
    const screen = page.getByTestId(id);
    await expect(screen).toBeVisible();
    // the screen's answer is in (or its error line): then no error line
    await expect(screen.getByTestId(done).or(screen.getByTestId("error")).first()).toBeVisible();
    await expect(screen.getByTestId("error")).toHaveCount(0);
    await noSidewaysScroll(page);
  }
});

test("a Sleeper league row carries the same card: lineup, scoring and the check", async ({ page }) => {
  const lg = recorded<unknown>("/api/leagues?username=test_manager");
  test.skip(!RECORD && !lg, "no recording yet: run with IC3_RECORD (see the header)");
  await page.goto("/");
  await page.getByTestId("username").fill("test_manager");
  await page.getByTestId("username-go").click();
  const cards = page.getByTestId("league-card");
  await expect(cards.first()).toBeVisible();
  await expect(cards.first().getByTestId("card-lineup")).toContainText("Your lineup: QB");
  await expect(cards.first().getByTestId("card-scoring")).toContainText("Scoring:");
  await expect(cards.first().getByTestId("card-check")).toHaveText(/Week \d+ check|not available for this league yet/);
  await noSidewaysScroll(page);
});
