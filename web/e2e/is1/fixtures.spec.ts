// Wave I-S (IS-1): a status that rarely plays is not ranked as if it will. A hand-built snapshot on e2e/ip2's recorded
// week (Rankings, Half PPR): the top receiver on injured reserve and the second listed Doubtful. Rankings: neither is
// ranked; "Not playing" has two labelled parts, "Out" and "Unlikely to play", with the doubtful player's reason ("players
// listed doubtful have played about 1 in 100 times"). Phone at 375 and desktop at 1300; screenshots (JPEG q70) into
// docs/handbacks/is1/ (SHOTS_IS1).
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

type Row = Record<string, unknown> & { gsis_id: string; player_name: string; team: string };
const FX = join(import.meta.dirname, "..", "..", "fixtures");
const ip2 = JSON.parse(readFileSync(join(FX, "ip2", "api_ip2.json"), "utf8")) as Record<string, { body: unknown }>;
const SHOTS = process.env.SHOTS_IS1 ?? join(import.meta.dirname, "..", ".out");
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64");
const week = ip2["/api/rankings?league=ref%3Ahalf&limit=50&offset=0&position=WR&view=week"].body as { rows: Row[]; total: number };
const [ir, doubt] = [week.rows[0], week.rows[1]];
const UNLIKELY = "Doubtful: players listed doubtful have played about 1 in 100 times; not ranked this week.";
const np = (r: Row, o: Record<string, unknown>) => ({ key: r.gsis_id, gsis_id: r.gsis_id, player_name: r.player_name, position: "WR",
  team: r.team, headshot_url: null, source: "Sleeper", as_of: "2026-10-07T17:00:00Z", ...o });
const rankings = {
  ...week, total: week.total - 2, not_playing_words: "Not playing this week: not ranked, not tiered.",
  rows: week.rows.slice(2).filter((r) => r.report_status !== "Out").map((r, i) => ({ ...r, rank: i + 1 })),
  not_playing: [
    np(ir, { status: "IR", code: "IR", why: "IR (knee - acl) · Sleeper, Sep 28", out_indefinitely: true, group: "out", group_label: "Out", p_play: null,
      words: "On injured reserve: he will not play this week, so he is not ranked." }),
    np(doubt, { status: "Doubtful", code: "DOUBTFUL", why: "Doubtful (quadriceps) · Sleeper, Oct 7", out_indefinitely: false, group: "unlikely",
      group_label: "Unlikely to play", p_play: 0.01, words: UNLIKELY }),
  ],
};

const shot = (page: Page, name: string) => page.screenshot({ path: join(SHOTS, `${name}.jpg`), type: "jpeg", quality: 70, scale: "css" });

test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test("Rankings: a doubtful player is not ranked; Not playing has Out and Unlikely to play", async ({ context, page }, info) => {
  await context.route(/^https?:\/\/(?!localhost)/, (route) => route.fulfill({ status: 200, contentType: "image/png", body: PNG }));
  await serveFixtures(context);
  await context.route(/\/api\/rankings\?/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(rankings) }));
  await page.goto("/rankings?league=ref:half");
  await expect(page.getByTestId("rankings-row").first()).toBeVisible({ timeout: 30_000 });
  for (const r of [ir, doubt]) await expect(page.getByTestId("rankings-name").filter({ hasText: r.player_name })).toHaveCount(0);
  const group = page.getByTestId("rankings-not-playing");
  await expect(page.getByTestId("rankings-not-playing-part")).toHaveText([/^Out\s*· 1$/, /^Unlikely to play\s*· 1$/]);
  const u = page.locator('[data-testid="rankings-not-playing-row"][data-group="unlikely"]');
  await expect(u).toContainText(doubt.player_name);
  await expect(u.getByTestId("rankings-not-playing-status")).toHaveText("Doubtful");
  await expect(u.getByTestId("rankings-not-playing-words")).toHaveText(UNLIKELY);
  const [sw, cw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(sw).toBeLessThanOrEqual(cw);
  await group.scrollIntoViewIfNeeded();
  await shot(page, `rankings-unlikely-${info.project.name}`);
});
