import base from "./playwright.fixtures.config";

// The decision screens' fixture e2e alone (plan G4), on its own preview port so it never reuses another worktree's
// server: E2E_PORT=8594 npx playwright test --config playwright.g4.config.ts (npm run e2e:fixtures runs it with F2's).
const port = Number(process.env.E2E_PORT ?? 8594);
export default {
  ...base,
  testMatch: "**/decisions/fixtures.spec.ts",
  use: { ...base.use, baseURL: `http://localhost:${port}` },
  webServer: { ...base.webServer, command: `npx vite preview --port ${port} --strictPort`, url: `http://localhost:${port}/`, reuseExistingServer: false },
};
