import { defineConfig, devices } from "@playwright/test";

// The web app on fixtures (e2e/fixtures.spec.ts; plan F2): no API, no database, no Sleeper — every /api call is
// answered from web/fixtures/*.json by route interception (e2e/fixtures.ts). The built app (web/dist) is served by
// `vite preview` on :8584 (started here). Phone (iPhone 13 UA, 390 × 844, touch) and desktop (1300 × 900).
//   npm run build && npm run e2e:fixtures            (screenshots: SHOTS_DIR, default e2e/.out)
export default defineConfig({
  testDir: "e2e",
  testMatch: "fixtures.spec.ts",
  workers: 1,
  timeout: 60_000,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:8584", trace: "off", serviceWorkers: "block" },
  webServer: { command: "npx vite preview --port 8584 --strictPort", url: "http://localhost:8584/", reuseExistingServer: true, timeout: 60_000 },
  projects: [
    { name: "phone", use: { ...devices["iPhone 13"], browserName: "chromium", viewport: { width: 390, height: 844 }, serviceWorkers: "block" } },
    { name: "desktop", use: { browserName: "chromium", viewport: { width: 1300, height: 900 }, serviceWorkers: "block" } },
  ],
});
