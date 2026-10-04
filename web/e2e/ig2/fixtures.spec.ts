// Wave I-G (IG-2): the event store on the screens — My Week's "What changed" cites the stored event (the status line's
// source links to the player's ESPN page, with the report's time; his PlayerWire brief with its publisher and link), and
// About says what is kept. Phone at 375 px (inside the phone project) and desktop at 1300.
//
// The answers are the API's own, recorded by api/tests/test_ig2.py::test_record_e2e_answers (Scrubs roster 2 with the
// ESPN fixture overlay — Jefferson Out — and PlayerWire's fixture briefs, the store on) into web/fixtures/ig2/api_ig2.json.
// Re-record:  cd api && IG2_RECORD=1 PYTHONPATH=. uv run pytest -q tests/test_ig2.py -k record
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures, SCRUBS } from "../fixtures";

const FILE = join(import.meta.dirname, "..", "..", "fixtures", "ig2", "api_ig2.json");
type Saved = { status: number; body: unknown };
const saved: Record<string, Saved> = existsSync(FILE) ? (JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Saved>) : {};

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return u.pathname + (q.length ? `?${new URLSearchParams(q).toString()}` : "");
};

async function answer(route: Route) {
  const s = saved[keyOf(new URL(route.request().url()))];
  if (!s) return route.fallback();
  return route.fulfill({ status: s.status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(s.body) });
}

test.beforeEach(async ({ context, page }, info) => {
  test.skip(!existsSync(FILE), "no recording yet (see the header)");
  await serveFixtures(context);
  await context.route(/\/api\//, answer);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(process.env.SHOTS_DIR ?? "e2e/.out", `ig2-${name}-${project}.png`), fullPage: true });

test("what changed cites the event: his ESPN page on the status line, the brief's publisher and link", async ({ page }, info) => {
  await page.goto(`/?league=${SCRUBS}&team=2`);
  const box = page.getByTestId("what-changed");
  await expect(box).toBeVisible();
  const status = box.locator('[data-testid="changed-line"][data-kind="status"]').first();
  await expect(status).toContainText("Justin Jefferson is out (ankle)");
  const src = status.getByRole("link", { name: /Injury report \(ESPN\)/ });
  await expect(src).toHaveAttribute("href", "https://www.espn.com/nfl/player/_/id/4262921");
  await expect(status.locator("time")).toHaveAttribute("datetime", "2026-10-02T18:35:00Z"); // the report's time, not the check's
  const brief = box.locator('[data-testid="changed-line"][data-kind="news"]').filter({ hasText: "Justin Jefferson:" }).first();
  await expect(brief).toContainText("Jefferson (ankle) ruled out for Sunday");
  const link = brief.getByRole("link", { name: /Minnesota Vikings via PlayerWire/ });
  await expect(link).toHaveAttribute("href", "https://www.vikings.com/news/injury-report-week-5");
  await expect(link).toHaveAttribute("target", "_blank");
  await noSidewaysScroll(page);
  await box.scrollIntoViewIfNeeded();
  await shot(page, "team2-changed", info.project.name);
});

test("About says what the app keeps", async ({ page }, info) => {
  await page.goto(`/about?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("about-events")).toContainText(
    "keeps a record of what it showed: each injury-report change, headline and brief, with its source, link and time",
  );
  await expect(page.getByTestId("about-news-source")).toContainText("keeps only the headline, its date, the source and the link.");
  await noSidewaysScroll(page);
  await page.getByTestId("about-events").scrollIntoViewIfNeeded();
  await shot(page, "about", info.project.name);
});
