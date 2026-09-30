import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: "http://127.0.0.1:13000", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node tests/upstream.mjs",
      url: "http://127.0.0.1:18001",
      reuseExistingServer: false,
    },
    {
      command: "npm run start -- --port 13000",
      url: "http://127.0.0.1:13000",
      reuseExistingServer: false,
      timeout: 120000,
      env: { TAXGUIDE_API_URL: "http://127.0.0.1:18001" },
    },
  ],
});
