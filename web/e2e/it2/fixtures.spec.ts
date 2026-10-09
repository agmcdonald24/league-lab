// Wave I-T (IT-2): "Questionable: about 2 in 3 play" beside the label on a ranked row (the rate of his position where
// the counts allow), and a player Out on this week's own injury report under "Not playing" with the report as the
// source. A hand-built snapshot on e2e/ip2's recorded week (Rankings, Half PPR). 375 and 1300; JPEG q70 (SHOTS_IT2).
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

type Row = Record<string, unknown> & { gsis_id: string; player_name: string; team: string };
const FX = join(import.meta.dirname, "..", "..", "fixtures");
const ip2 = JSON.parse(readFileSync(join(FX, "ip2", "api_ip2.json"), "utf8")) as Record<string, { body: unknown }>;
const SHOTS = process.env.SHOTS_IT2 ?? join(import.meta.dirname, "..", ".out");
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64");
const week = ip2["/api/rankings?league=ref%3Ahalf&limit=50&offset=0&position=WR&view=week"].body as { rows: Row[]; total: number };
const out = week.rows[0];
const q = week.rows[2];
const SHORT = "Questionable: about 7 in 10 play";
const rankings = {
  ...week, total: week.total - 1, not_playing_words: "Not playing this week: not ranked, not tiered.",
  rows: week.rows.slice(1).filter((r) => r.report_status !== "Out").map((r, i) => ({
    ...r, rank: i + 1,
    ...(r.gsis_id === q.gsis_id ? { report_status: "Questionable", availability: { status: "Questionable", code: "QUESTIONABLE",
      why: "Questionable (ankle) · NFL injury report", p_play: 0.7, short: SHORT } } : {}),
  })),
  not_playing: [{ key: out.gsis_id, gsis_id: out.gsis_id, player_name: out.player_name, position: "WR", team: out.team, headshot_url: null,
    status: "Out", code: "OUT", source: "NFL injury report", as_of: null, why: "Out · NFL injury report", out_indefinitely: false,
    group: "out", group_label: "Out", p_play: 0.0, words: "Ruled out this week: he will not play this week, so he is not ranked." }],
};

test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test("Rankings: a questionable row says how often such players play; Out on the week's report is not ranked", async ({ context, page }, info) => {
  await context.route(/^https?:\/\/(?!localhost)/, (route) => route.fulfill({ status: 200, contentType: "image/png", body: PNG }));
  await serveFixtures(context);
  await context.route(/\/api\/rankings\?/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(rankings) }));
  await page.goto("/rankings?league=ref:half");
  const row = page.locator(`[data-testid="rankings-row"][data-key="${q.gsis_id}"]`);
  await expect(row.getByTestId("rankings-rate")).toHaveText(`${SHORT} · Questionable (ankle) · NFL injury report`, { timeout: 30_000 });
  await expect(page.getByTestId("rankings-name").filter({ hasText: out.player_name })).toHaveCount(0);
  await expect(page.getByTestId("rankings-not-playing-row")).toContainText("Out · NFL injury report");
  const [sw, cw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(sw).toBeLessThanOrEqual(cw);
  await row.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(SHOTS, `rankings-questionable-${info.project.name}.jpg`), type: "jpeg", quality: 70, scale: "css" });
});
