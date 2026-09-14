import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  use: {
    baseURL: process.env.OPENATLAS_TEST_URL || "http://127.0.0.1:8000",
    screenshot: "only-on-failure",
  },
  workers: 1,
});
