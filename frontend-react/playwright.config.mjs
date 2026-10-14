import { randomBytes } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, devices } from "@playwright/test";
import {
  BACKEND_PORT,
  FRONTEND_PORT,
  backendUrl,
  frontendUrl,
  testDatabaseFile,
  testDatabaseUrl,
} from "./e2e/fixtures/env.mjs";

const configDir = path.dirname(fileURLToPath(import.meta.url));

// Ephemeral key material for the isolated test backend. Generated per run when
// the environment does not provide values, so no key ever lands in the repo.
// app/core/crypto.py expects HEX format (bytes.fromhex). Written back to
// process.env so test workers (spawned with the runner's env after this config
// is loaded) and e2e/scripts/seed_atypical_days.py use the very same keys and
// database as the backend under test instead of generating new ones.
process.env.MYGLICO_ENCRYPTION_KEY_V1 ||= randomBytes(32).toString("hex");
process.env.MYGLICO_LOOKUP_HMAC_KEY ||= randomBytes(32).toString("hex");
process.env.MYGLICO_E2E_DATABASE_URL ||= testDatabaseUrl;
process.env.MYGLICO_E2E_DATABASE_FILE ||= testDatabaseFile;

const encryptionKeyV1 = process.env.MYGLICO_ENCRYPTION_KEY_V1;
const lookupHmacKey = process.env.MYGLICO_LOOKUP_HMAC_KEY;
const databaseUrl = process.env.MYGLICO_E2E_DATABASE_URL;
const databaseFile = process.env.MYGLICO_E2E_DATABASE_FILE;

const artifactsDir = path.join(configDir, "e2e", ".artifacts");

const backendEnv = {
  MYGLICO_APP_ENV: "e2e",
  MYGLICO_DEBUG: "false",
  MYGLICO_GLICO_ENABLED: process.env.MYGLICO_E2E_GLICO_ENABLED ?? "true",
  MYGLICO_DATABASE_URL: databaseUrl,
  MYGLICO_ENCRYPTION_KEY_V1: encryptionKeyV1,
  MYGLICO_LOOKUP_HMAC_KEY: lookupHmacKey,
  MYGLICO_E2E_DATABASE_FILE: databaseFile,
  MYGLICO_E2E_BACKEND_PORT: String(BACKEND_PORT),
};

export default defineConfig({
  testDir: path.join(configDir, "e2e", "specs"),
  testIgnore: ["**/13-glico-live-backend.spec.mjs"],
  outputDir: path.join(artifactsDir, "test-results"),
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [
    ["list"],
    ["html", { outputFolder: path.join(artifactsDir, "html-report"), open: "never" }],
  ],
  use: {
    baseURL: frontendUrl,
    // The app picks its language from navigator.language; pin pt-BR so text
    // assertions do not depend on the host OS locale (REVISAO-FINAL.md, A16:
    // /entrar/ failed because Chromium opened in en-US). The i18n group
    // switches language explicitly.
    locale: "pt-BR",
    timezoneId: "America/Sao_Paulo",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Both servers are started by Playwright against the isolated test database;
  // reuse is disabled on purpose so a dev server bound to the dev database can
  // never serve E2E assertions.
  webServer: [
    {
      command: `node ${JSON.stringify(path.join(configDir, "e2e", "scripts", "start-backend.mjs"))}`,
      cwd: path.resolve(configDir, ".."),
      // Health-checked directly AND through the Vite proxy below, so tests
      // never start while /api would still answer 500.
      url: `${backendUrl}/health`,
      env: backendEnv,
      timeout: 180_000,
      reuseExistingServer: false,
    },
    {
      command: `npx vite --port ${FRONTEND_PORT} --strictPort`,
      cwd: configDir,
      url: `${frontendUrl}/health`,
      env: { VITE_API_TARGET: backendUrl },
      // /health is proxied to the backend: this URL only answers 200 when the
      // proxy really reaches uvicorn.
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
});
