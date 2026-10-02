// First content on fixtures (plan F2 acceptance: ≤ 500 ms): navigation start → the first decision card in the DOM
// (the same MutationObserver stamp as measure.spec.ts), My Week from a shared link, cold (a new browser profile) and
// warm (a second visit in the same profile), median of MEASURE_LOADS, phone (iPhone 13 UA, 390 × 844) and desktop
// (1300 × 900). The API is the fixture files (e2e/fixtures.ts), so this measures the app alone: the shell, the inline
// first fetch, the bundle, the render. The built app is served by `vite preview` (the measure config starts it).
//   npm run build && npm run measure:fixtures        → e2e/.out/measure_fixtures.json and .md
import { devices, expect, test, type Browser } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { cpus, loadavg } from "node:os";
import { join } from "node:path";
import { DYNASTY, serveFixtures, TEST_LEAGUE } from "./fixtures";

const BASE = process.env.MEASURE_FIXTURES_URL ?? `http://localhost:${process.env.FIXTURES_PORT ?? 8584}`;
const LOADS = Number(process.env.MEASURE_LOADS ?? 5);
const LIMIT_MS = 500;
const OUT = join(import.meta.dirname, ".out");
mkdirSync(OUT, { recursive: true });

const STAMP = `(() => {
  const check = () => {
    if (window.__ll_first) return;
    if (document.querySelector('[data-testid="decision-card"]')) window.__ll_first = performance.now();
  };
  new MutationObserver(check).observe(document, { childList: true, subtree: true });
})();`;

const { defaultBrowserType: _ignored, ...IPHONE } = devices["iPhone 13"];
void _ignored;
const PROFILES = [
  { name: "phone", options: { ...IPHONE, viewport: { width: 390, height: 844 }, serviceWorkers: "block" as const } },
  { name: "desktop", options: { viewport: { width: 1300, height: 900 }, serviceWorkers: "block" as const } },
];
const PAGES = [
  { name: "Test League (any league)", url: `/?league=${TEST_LEAGUE}&team=3` },
  { name: "dynasty roster 12", url: `/?league=${DYNASTY}&team=12` },
];

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
};

async function loads(browser: Browser, options: (typeof PROFILES)[number]["options"], url: string) {
  const cold: number[] = [];
  const warm: number[] = [];
  for (let i = 0; i < LOADS; i++) {
    const ctx = await browser.newContext(options);
    await serveFixtures(ctx);
    for (const bucket of [cold, warm]) {
      const page = await ctx.newPage();
      await page.addInitScript(STAMP);
      await page.goto(BASE + url, { waitUntil: "commit" });
      await page.getByTestId("decision-card").first().waitFor();
      await page.waitForFunction(() => (window as unknown as { __ll_first?: number }).__ll_first);
      bucket.push(Math.round(await page.evaluate(() => (window as unknown as { __ll_first: number }).__ll_first)));
      await page.close();
    }
    await ctx.close();
  }
  return { cold_median_ms: median(cold), cold_runs_ms: cold, warm_median_ms: median(warm), warm_runs_ms: warm };
}

test("first content on fixtures ≤ 500 ms", async ({ browser }) => {
  test.setTimeout(10 * 60_000);
  const results: Record<string, unknown> = { when: new Date().toISOString(), base: BASE, loads: LOADS, cpus: cpus().length, loadavg_start: loadavg() };
  const lines = ["| Page | Phone: first visit / repeat (median ms) | Desktop: first visit / repeat (median ms) |", "|---|---|---|"];
  // one warm-up load (vite preview's first answers, the browser's first start)
  {
    const ctx = await browser.newContext(PROFILES[1].options);
    await serveFixtures(ctx);
    const page = await ctx.newPage();
    await page.goto(BASE + PAGES[0].url);
    await page.getByTestId("decision-card").first().waitFor();
    await ctx.close();
  }
  for (const pg of PAGES) {
    const row: Record<string, unknown> = {};
    for (const p of PROFILES) row[p.name] = await loads(browser, p.options, pg.url);
    results[pg.name] = row;
    const cell = (x: { cold_median_ms: number; warm_median_ms: number }) => `${x.cold_median_ms} / ${x.warm_median_ms}`;
    lines.push(`| My Week, ${pg.name} | ${cell(row.phone as never)} | ${cell(row.desktop as never)} |`);
  }
  results.loadavg_end = loadavg();
  writeFileSync(join(OUT, "measure_fixtures.json"), JSON.stringify(results, null, 2));
  writeFileSync(join(OUT, "measure_fixtures.md"), lines.join("\n") + "\n");
  console.log(lines.join("\n"));
  for (const pg of PAGES)
    for (const p of PROFILES) {
      const r = (results[pg.name] as Record<string, { cold_median_ms: number }>)[p.name];
      expect(r.cold_median_ms, `${pg.name}, ${p.name}: first content`).toBeLessThanOrEqual(LIMIT_MS);
    }
});
