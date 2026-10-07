// Starts the backend for the Playwright suite against a dedicated, disposable
// SQLite file. Never touches the dev/production database:
//   1. deletes the previous E2E SQLite file (if any);
//   2. runs `alembic upgrade head` so the schema is rebuilt from scratch;
//   3. serves the API on 127.0.0.1:$MYGLICO_E2E_BACKEND_PORT (default 8101)
//      for playwright.config.mjs to health-check.
// Environment (database URL + ephemeral keys) is injected by Playwright's
// webServer entry; nothing here reads or writes secrets to versioned files.
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const dbFile = process.env.MYGLICO_E2E_DATABASE_FILE;

if (!process.env.MYGLICO_DATABASE_URL) {
  console.error("[e2e] MYGLICO_DATABASE_URL is not set; refusing to start.");
  process.exit(1);
}
if (!dbFile) {
  console.error("[e2e] MYGLICO_E2E_DATABASE_FILE is not set; refusing to start.");
  process.exit(1);
}
if (process.env.MYGLICO_E2E_RESET_DB !== "0") {
  for (const candidate of [dbFile, `${dbFile}-wal`, `${dbFile}-shm`]) {
    fs.rmSync(candidate, { force: true });
  }
  console.log(`[e2e] reset test database file: ${dbFile}`);
}

const python = process.env.MYGLICO_E2E_PYTHON || "python";
const port = process.env.MYGLICO_E2E_BACKEND_PORT || "8101";

// No shell: the child is python itself, so Playwright's teardown (which kills
// this process tree) never leaves an orphan uvicorn holding the port.
const alembic = spawnSync(python, ["-m", "alembic", "upgrade", "head"], {
  cwd: repoRoot,
  stdio: "inherit",
  env: process.env,
});
if (alembic.status !== 0) {
  console.error("[e2e] alembic upgrade head failed; aborting backend start.");
  process.exit(alembic.status ?? 1);
}

// --proxy-headers: every request reaches uvicorn through the Vite proxy from
// 127.0.0.1, so without it all simulated users share one client IP and the
// per-IP rate limits (login/search/link request, REVISAO-FINAL.md A5) throttle
// the whole suite. Each test context sends its own X-Forwarded-For, like
// distinct users behind a reverse proxy. Only the disposable E2E backend
// trusts the header, and only from the local Vite proxy (127.0.0.1); the dedicated rate-limit scenario reuses one IP.
const server = spawn(python, [
  "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port,
  "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1",
], {
  cwd: repoRoot,
  stdio: "inherit",
  env: process.env,
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.kill(signal));
}
process.on("exit", () => {
  if (server.exitCode === null) server.kill();
});
server.on("exit", (code) => process.exit(code ?? 0));
