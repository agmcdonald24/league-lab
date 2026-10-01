import { defineConfig, devices } from "@playwright/test";

// The web app's checks (e2e/app.spec.ts) against a running API that serves web/dist:
//   (cd ../api && uv run uvicorn league_lab_api.main:app --port 8581) && npm run build && npm run e2e
// Chromium only (the sandbox's browsers: PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers). Screenshots: SHOTS_DIR (default e2e/.out).
export default defineConfig({
  testDir: "e2e",
  testMatch: "app.spec.ts",
  workers: 1,
  timeout: 60_000,
  reporter: [["list"]],
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8581", trace: "off" },
  projects: [
    { name: "phone", use: { ...devices["iPhone 13"], browserName: "chromium", viewport: { width: 390, height: 844 } } },
    { name: "desktop", use: { browserName: "chromium", viewport: { width: 1300, height: 900 } } },
  ],
});
