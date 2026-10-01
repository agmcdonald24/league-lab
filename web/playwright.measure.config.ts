import { defineConfig } from "@playwright/test";

// The side-by-side measurement (e2e/measure.spec.ts): the web app (MEASURE_WEB_URL, default :8581) and the
// Streamlit app (MEASURE_ST_URL, default :8577) on the same database. Writes e2e/.out/measure.json and .md.
export default defineConfig({
  testDir: "e2e",
  testMatch: "measure.spec.ts",
  workers: 1,
  timeout: 20 * 60_000,
  reporter: [["list"]],
  use: { browserName: "chromium", trace: "off", actionTimeout: 30_000, navigationTimeout: 60_000 },
});
