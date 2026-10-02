import { defineConfig } from "@playwright/test";

// The side-by-side measurement (e2e/measure.spec.ts): the web app (MEASURE_WEB_URL, default :8581) and the
// Streamlit app (MEASURE_ST_URL, default :8577) on the same database. Writes e2e/.out/measure.json and .md.
// With MEASURE_FIXTURES=1 (npm run measure:fixtures): the web app alone on fixtures (e2e/measure-fixtures.spec.ts,
// plan F2: first content ≤ 500 ms), served by `vite preview` on :8584 (started here). Writes measure_fixtures.*.
const fixtures = !!process.env.MEASURE_FIXTURES;
const port = Number(process.env.FIXTURES_PORT ?? 8584);

export default defineConfig({
  testDir: "e2e",
  testMatch: fixtures ? "measure-fixtures.spec.ts" : "measure.spec.ts",
  workers: 1,
  timeout: 20 * 60_000,
  reporter: [["list"]],
  use: { browserName: "chromium", trace: "off", actionTimeout: 30_000, navigationTimeout: 60_000 },
  webServer: fixtures
    ? { command: `npx vite preview --port ${port} --strictPort`, url: `http://localhost:${port}/`, reuseExistingServer: true, timeout: 60_000 }
    : undefined,
});
