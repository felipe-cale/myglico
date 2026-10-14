import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const e2eDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.dirname(e2eDir);
const baseURL = "http://localhost:8102";

export default defineConfig({
  testDir: path.join(e2eDir, "specs"),
  testMatch: "13-glico-live-backend.spec.mjs",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: "list",
  use: { ...devices["Desktop Chrome"], baseURL, locale: "pt-BR", timezoneId: "America/Sao_Paulo" },
  webServer: {
    command: "npx vite --host 127.0.0.1 --port 8102 --strictPort",
    cwd: frontendDir,
    url: `${baseURL}/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: { VITE_API_TARGET: "http://127.0.0.1:8012" },
  },
});
