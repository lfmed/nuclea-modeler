import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for Núclea Modeler E2E smoke tests.
 *
 * Tests run against a static preview of the production build by default.
 * Set E2E_BASE_URL to point at any other deployment (e.g. the live
 * Databricks Apps URL) — the suite assumes the welcome tour and home
 * page render, no auth required for /.
 */
export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts/,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  timeout: 30_000,
  expect: { timeout: 5_000 },

  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:4173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    locale: "pt-BR",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // Only spin up vite preview when running locally (no E2E_BASE_URL override).
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: "bun run preview --port 4173 --strictPort",
        url: "http://127.0.0.1:4173",
        reuseExistingServer: !process.env.CI,
        timeout: 60_000,
        // Vite preview serves dist; if dist is empty the test will fail
        // with a clear "module not found" instead of hanging.
        stdout: "pipe",
        stderr: "pipe",
      },
});
