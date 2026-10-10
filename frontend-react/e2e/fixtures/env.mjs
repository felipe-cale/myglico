// Shared environment for the Playwright suite: ports, URLs and the isolated
// database file. Imported by both playwright.config.mjs and the test fixtures
// so the two can never drift apart.
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

export const repoRoot = path.resolve(here, "..", "..", "..");

// Dedicated ports (not the dev 8000/8001) so a developer's or another agent's
// dev server can never collide with, or silently serve, the E2E run. Override
// with MYGLICO_E2E_BACKEND_PORT / MYGLICO_E2E_FRONTEND_PORT.
// Backend: 127.0.0.1 instead of "localhost" — Node >= 17 resolves localhost to
// ::1 first while uvicorn binds IPv4 only, which made the Vite proxy answer
// 500 (ECONNREFUSED) for every /api call (REVISAO-FINAL.md, A16).
// Frontend: must stay "localhost" — the session cookie is `Secure`, and both
// browsers and Playwright's APIRequestContext only send Secure cookies over
// plain http to the "localhost" host.
export const BACKEND_PORT = Number(process.env.MYGLICO_E2E_BACKEND_PORT || 8101);
export const FRONTEND_PORT = Number(process.env.MYGLICO_E2E_FRONTEND_PORT || 8100);
export const backendUrl = `http://127.0.0.1:${BACKEND_PORT}`;
export const frontendUrl = `http://localhost:${FRONTEND_PORT}`;

// Isolated SQLite file for the E2E backend. It matches the root .gitignore
// pattern `data/*.db`, so it can never be committed, and it is deleted and
// rebuilt by e2e/scripts/start-backend.mjs on every run.
export const testDatabaseFile = path.join(repoRoot, "data", "e2e-myglico.db");
export const testDatabaseUrl = `sqlite:///${testDatabaseFile.split(path.sep).join("/")}`;
