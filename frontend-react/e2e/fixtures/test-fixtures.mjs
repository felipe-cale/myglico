// Extended Playwright test with per-profile sessions.
//
// Four profiles (patient A/B, doctor A/B) come from fixtures/profiles.mjs; each
// test gets its own identities, so tests are independent of execution order
// and of the shared E2E database. Credentials are generated at runtime and only
// live in memory for the duration of the run.
//
// Nothing here mocks the backend: every helper performs real HTTP calls
// through Playwright's APIRequestContext or real UI navigation, and
// seedAtypicalDays runs the real analytics pipeline in Python.
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { test as base, expect } from "@playwright/test";

import * as api from "./api.mjs";
import { frontendUrl, repoRoot } from "./env.mjs";
import { createProfileSet } from "./profiles.mjs";

export { expect };

const here = path.dirname(fileURLToPath(import.meta.url));
const seedScript = path.join(here, "..", "scripts", "seed_atypical_days.py");

export const BROWSER_CONTEXT_DEFAULTS = {
  baseURL: frontendUrl,
  locale: "pt-BR",
  timezoneId: "America/Sao_Paulo",
};

// Distinct synthetic client IP per session (see e2e/scripts/start-backend.mjs).
let ipCounter = Math.floor(Math.random() * 50_000);
export function syntheticClientHeaders() {
  ipCounter += 1;
  return { "X-Forwarded-For": `10.${(ipCounter >> 16) & 255}.${(ipCounter >> 8) & 255}.${ipCounter & 255}` };
}

async function newApiSession(playwright, profile) {
  const context = await playwright.request.newContext({ baseURL: frontendUrl, extraHTTPHeaders: syntheticClientHeaders() });
  const session = {
    profile,
    context,
    patientId: null,
    doctorId: null,
    shortId: null,
    get request() {
      return context;
    },
    async register(overrides) {
      const result = await api.register(context, profile, overrides);
      if (result.status === 201) session.remember(result.body);
      return result;
    },
    async login() {
      const result = await api.login(context, { email: profile.email, password: profile.password });
      if (result.status === 200) session.remember(result.body);
      return result;
    },
    async logout() {
      return api.logout(context);
    },
    async whoami() {
      return api.session(context);
    },
    remember(body) {
      if (body?.patient) {
        session.patientId = body.patient.id;
        session.shortId = body.patient.short_id;
      }
      if (body?.doctor) {
        session.doctorId = body.doctor.id;
        session.shortId = body.doctor.short_id;
      }
    },
    async dispose() {
      await context.dispose();
    },
  };
  return session;
}

export const test = base.extend({
  // Per-test identities (see profiles.mjs).
  profiles: async ({}, use, testInfo) => {
    await use(createProfileSet(testInfo.titlePath.at(-1).split(" ")[0].toLowerCase().replace(/[^a-z0-9-]/g, "")));
  },

  // Factory: one isolated API context (own cookie jar) per call, disposed
  // automatically at the end of the test. Also exposes registerAccount /
  // login / logout on an anonymous context for raw-payload scenarios — the
  // missing `apiSession.registerAccount` broke group 2 (REVISAO-FINAL.md, A16).
  apiSession: async ({ playwright, profiles }, use) => {
    const opened = [];
    const factory = async (profileKey) => {
      const session = await newApiSession(playwright, profiles(profileKey));
      opened.push(session);
      return session;
    };
    let raw = null;
    const rawContext = async () => {
      if (!raw) {
        raw = await playwright.request.newContext({ baseURL: frontendUrl, extraHTTPHeaders: syntheticClientHeaders() });
      }
      return raw;
    };
    factory.registerAccount = async (body) => {
      const response = await (await rawContext()).post("/api/auth/register", { data: body });
      return { status: response.status(), body: await response.json().catch(() => null) };
    };
    factory.login = async (credentials) => api.login(await rawContext(), credentials);
    factory.logout = async () => api.logout(await rawContext());
    factory.session = async () => api.session(await rawContext());
    await use(factory);
    for (const session of opened) await session.dispose().catch(() => {});
    if (raw) await raw.dispose().catch(() => {});
  },

  // Factory: registered (or logged-in) API session for a profile.
  actor: async ({ apiSession }, use) => {
    await use(async (profileKey) => {
      const session = await apiSession(profileKey);
      const result = await session.register();
      if (result.status !== 201) {
        throw new Error(`registration of ${profileKey} failed with ${result.status}: ${JSON.stringify(result.body)}`);
      }
      return session;
    });
  },

  // Factory: one isolated browser context per profile (pt-BR, own cookies),
  // plus a helper that seeds its cookies from a real API login.
  browserSession: async ({ browser, playwright, profiles }, use) => {
    const opened = [];
    await use(async (profileKey, contextOptions = {}) => {
      const profile = profiles(profileKey);
      const context = await browser.newContext({
        ...BROWSER_CONTEXT_DEFAULTS,
        extraHTTPHeaders: syntheticClientHeaders(),
        ...contextOptions,
      });
      opened.push(context);
      const page = await context.newPage();
      return {
        profile,
        context,
        page,
        async authenticateWithApi() {
          const apiContext = await playwright.request.newContext({ baseURL: frontendUrl, extraHTTPHeaders: syntheticClientHeaders() });
          try {
            const result = await api.login(apiContext, { email: profile.email, password: profile.password });
            if (result.status !== 200) throw new Error(`API login failed with ${result.status}`);
            await context.addCookies((await apiContext.storageState()).cookies);
          } finally {
            await apiContext.dispose();
          }
        },
      };
    });
    for (const context of opened) await context.close().catch(() => {});
  },
});

// Patient requests, doctor confirms: returns the ACTIVE link (as seen by the doctor).
export async function linkActive(patient, doctor) {
  const requested = await api.createDoctorLink(patient.request, doctor.shortId);
  expect(requested.status, JSON.stringify(requested.body)).toBe(201);
  const link = requested.body.link;
  const confirmed = await api.decideDoctorLink(doctor.request, link.id, "confirm", link.version);
  expect(confirmed.status, JSON.stringify(confirmed.body)).toBe(200);
  expect(confirmed.body.link.status).toBe("active");
  return confirmed.body.link;
}

// Runs e2e/scripts/seed_atypical_days.py against the E2E database.
export function seedAtypicalDays(patientId, { days = 40, spikes = [10, 25], start = "2026-06-01", globalRun = false, midnightDay, flattenDate } = {}) {
  const args = [seedScript, "--patient-id", patientId, "--days", String(days), "--spikes", spikes.join(","), "--start", start];
  if (globalRun) args.push("--global-run");
  if (midnightDay !== undefined) args.push("--midnight-day", String(midnightDay));
  if (flattenDate) args.push("--flatten-date", flattenDate);
  const result = spawnSync(process.env.MYGLICO_E2E_PYTHON || "python", args, {
    cwd: repoRoot,
    encoding: "utf-8",
    env: {
      ...process.env,
      MYGLICO_DATABASE_URL: process.env.MYGLICO_E2E_DATABASE_URL,
      MYGLICO_APP_ENV: "e2e",
      MYGLICO_DEBUG: "false",
    },
  });
  if (result.status !== 0) {
    throw new Error(`seed_atypical_days.py failed (${result.status}): ${result.stderr}`);
  }
  const lastLine = result.stdout.trim().split(/\r?\n/).at(-1);
  return JSON.parse(lastLine);
}

// Patient opens an investigation addressed to `doctor` (link must be ACTIVE).
export async function openInvestigationAsPatient(patient, doctor, extra = {}) {
  const opened = await api.createInvestigation(patient.request, {
    doctor_id: doctor.doctorId,
    title: extra.title || "Questionamento E2E",
    initial_message: extra.initial_message || "Mensagem inicial E2E",
    ...(extra.atypical_day_event_id ? { atypical_day_event_id: extra.atypical_day_event_id } : {}),
  });
  expect(opened.status, JSON.stringify(opened.body)).toBe(201);
  return opened.body.investigation;
}
