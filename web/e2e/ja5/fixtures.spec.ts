// Wave J-A (JA-5): on a desktop Stats opens on the table too. From 900 px the controls are one row — the positions,
// the weeks as one line ("Season · weeks 1–4 ▾", the full control in place), the situation, and one Filters button that
// names what is in force and opens the rest in place. At 1300 x 900: the first row above 520 px and six rows on the first
// screen with nothing chosen; with a stretch, a comparison and a situation the closed row names all three and five rows
// show. The phone is unchanged (e2e/ix3, e2e/ja1). Screens into JA5_SHOTS.
//
// Recordings: web/fixtures/ja1/api_ja1.json (JA-1) and web/fixtures/ja5/api_ja5.json (weeks 3–4 against 1–2, when trailing).
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures, SCRUBS } from "../fixtures";

const FX = join(import.meta.dirname, "..", "..", "fixtures");
const saved: Record<string, { status: number; body: unknown }> = {
  ...JSON.parse(readFileSync(join(FX, "ja1", "api_ja1.json"), "utf8")),
  ...JSON.parse(readFileSync(join(FX, "ja5", "api_ja5.json"), "utf8")),
};
const keyOf = (q: URLSearchParams) => `/api/players?${new URLSearchParams([...q.entries()].sort(([a], [b]) => a.localeCompare(b))).toString()}`;
const SHOTS = process.env.JA5_SHOTS ?? "e2e/.out";
const url = (extra = "") => `/players?league=${SCRUBS}&team=2&position=WRTE${extra}`;

async function serve(context: BrowserContext) {
  await serveFixtures(context);
  await context.route(/\/api\/players\?/, (route) => {
    const hit = saved[keyOf(new URL(route.request().url()).searchParams)];
    return hit ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(hit.body) }) : route.fallback();
  });
}
const rows = (page: Page) => page.getByTestId("players-table").getByTestId("players-table-row");
const firstTop = (page: Page) => rows(page).first().evaluate((r) => r.getBoundingClientRect().top);
const whole = (page: Page) => rows(page).evaluateAll((rs) => rs.filter((r) => r.getBoundingClientRect().bottom <= window.innerHeight).length);
const shot = async (page: Page, name: string) => {
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: join(SHOTS, `ja5-${name}.jpg`), quality: 70, fullPage: false });
};

test.describe("1300 x 900", () => {
  test.skip(({ isMobile }) => isMobile, "the desktop's first screen");
  test.beforeEach(async ({ page }) => page.setViewportSize({ width: 1300, height: 900 }));

  test("nothing chosen: one control row, the first row above 520 px, six rows on the first screen", async ({ page, context }) => {
    await serve(context);
    await page.goto(url());
    await expect(rows(page).first()).toBeVisible();
    const top = await firstTop(page);
    const n = await whole(page);
    console.log(`JA5 nothing chosen: first row top ${Math.round(top)} px, ${n} whole rows`);
    expect(top).toBeLessThan(520);
    expect(n).toBeGreaterThanOrEqual(6);
    // one row: the positions, the weeks' one line, the situation, Filters — on the same line
    const ys = await Promise.all(["pos-WRTE", "slider-toggle", "stats-sit-pick", "stats-filters-toggle"].map((id) => page.getByTestId(id).evaluate((e) => Math.round(e.getBoundingClientRect().top + e.getBoundingClientRect().height / 2))));
    expect(Math.max(...ys) - Math.min(...ys)).toBeLessThanOrEqual(12);
    await expect(page.getByTestId("slider-toggle")).toHaveText(/Season · weeks 1–4/);
    await expect(page.getByTestId("stats-filters-label")).toHaveText("Filters");
    await expect(page.getByTestId("players-search")).toBeHidden();
    await shot(page, "nothing-chosen-1300");
    // Filters opens the rest in place (a real button), the weeks' line opens the slider in place
    await page.getByTestId("stats-filters-toggle").click();
    await expect(page.getByTestId("stats-filters-toggle")).toHaveAttribute("aria-expanded", "true");
    for (const id of ["players-search", "who-all", "players-team", "mode-game", "stats-min", "stats-minopp", "stats-columns", "role-cards"]) await expect(page.getByTestId(id), id).toBeVisible();
    await shot(page, "filters-open-1300");
    await page.getByTestId("slider-toggle").click();
    await expect(page.getByTestId("slider-a-lo")).toBeVisible();
    await expect(page.getByTestId("slider-quick-season")).toBeVisible();
  });

  test("a stretch, a comparison and a situation in force: the closed row names all three, five rows on the first screen", async ({ page, context }) => {
    await serve(context);
    await page.goto(url("&window=weeks&weeks=3-4&vs=1-2&sit=trailing&who=fa&min=2"));
    await expect(rows(page).first()).toBeVisible();
    await expect(page.getByTestId("slider-toggle")).toHaveText(/Weeks 3–4 against weeks 1–2/);
    await expect(page.getByTestId("stats-sit-pick")).toHaveValue("trailing");
    await expect(page.getByTestId("stats-filters-label")).toHaveText("Filters: When trailing · Free agents · At least 2 games");
    const n = await whole(page);
    console.log(`JA5 everything in force: first row top ${Math.round(await firstTop(page))} px, ${n} whole rows`);
    expect(n).toBeGreaterThanOrEqual(5);
    await shot(page, "everything-closed-1300");
  });
});

test("375: the phone is unchanged — the stack, Filters, the weeks' line when a stretch is in force", async ({ page, context, isMobile }) => {
  test.skip(!isMobile, "the phone");
  await page.setViewportSize({ width: 375, height: 812 });
  await serve(context);
  await page.goto(url("&window=weeks&weeks=3-4&vs=1-2"));
  await expect(rows(page).first()).toBeVisible();
  await expect(page.getByTestId("stats-sit-pick")).toBeHidden();
  await expect(page.getByTestId("slider-toggle")).toHaveText(/Weeks 3–4 against weeks 1–2/);
  await shot(page, "phone-375");
});
