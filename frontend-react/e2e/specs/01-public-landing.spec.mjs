// Flow group 1 (PROMPT-ORCA.md, "Testes end-to-end"): public landing page,
// absence of clinical calls/data, private routes and direct API/PDF access
// without a session.
//
// Criteria: AUT-CA-01, AUT-CA-02, CSCW-CA-35, AUT-CA-23 (public responses).
// Status: executable. Text assertions use the app's own pt-BR strings
// (fixtures/i18n.mjs) and the browser locale is pinned to pt-BR in
// playwright.config.mjs.
import { expect, test } from "../fixtures/test-fixtures.mjs";
import { t, tx } from "../fixtures/i18n.mjs";
import * as api from "../fixtures/api.mjs";
import { LEGACY_API, ROUTES } from "../fixtures/routes.mjs";

test.describe("Group 1 - public landing and guardrails", () => {
  test(
    "AUT-CA-01 - visitor sees the explanation plus Entrar/Criar conta and no clinical data is loaded",
    async ({ page }) => {
      const clinicalRequests = [];
      page.on("request", (req) => {
        const url = req.url();
        if (url.includes("/api/")) {
          if (
            url.includes("/api/patients") ||
            url.includes("/api/dashboard") ||
            url.includes("/api/investigations") ||
            url.includes("/api/doctor-links") ||
            url.includes("/api/notifications") ||
            url.includes("/api/atypical-day-prompts")
          ) {
            clinicalRequests.push(url);
          }
        }
      });

      await page.goto(ROUTES.landing, { waitUntil: "domcontentloaded" });

      // CTAs should be visible (Entrar/Criar conta)
      const loginLink = page.getByRole("link", { name: tx("auth.login") });
      const registerLink = page.getByRole("link", { name: tx("auth.register") });
      await expect(loginLink.first()).toBeVisible({ timeout: 15000 });
      await expect(registerLink.first()).toBeVisible({ timeout: 15000 });

      // No clinical API calls on public landing
      expect(clinicalRequests.length).toBe(0);

      // No patient identifiers in DOM
      const bodyText = await page.locator("body").innerText();
      expect(bodyText).not.toMatch(/\b[A-Z0-9]{6}\b/); // short id pattern
      expect(bodyText).not.toMatch(/@.*\.com|@e2e\.myglico\.invalid/);
    }
  );

  test(
    "AUT-CA-02 - legacy patient API/JSON/PDF routes deny anonymous access",
    async ({ request }) => {
      const id = "11111111-1111-1111-1111-111111111111";
      const pdf = await request.get(LEGACY_API.patientReportPdf(id), {
        params: { start_date: "2026-01-01", end_date: "2026-01-02" },
      });
      expect(pdf.status()).toBeGreaterThanOrEqual(400);
      expect(pdf.status()).toBeLessThan(500);
      const patients = await request.get(LEGACY_API.patients);
      expect(patients.status()).toBeGreaterThanOrEqual(400);
      expect(patients.status()).toBeLessThan(500);
      const patient = await request.get(LEGACY_API.patient(id));
      expect(patient.status()).toBeGreaterThanOrEqual(400);
      expect(patient.status()).toBeLessThan(500);
      const dash = await request.get(LEGACY_API.dashboard);
      expect(dash.status()).toBeGreaterThanOrEqual(400);
      expect(dash.status()).toBeLessThan(500);
      const glucose = await request.post(LEGACY_API.patientGlucoseRecords(id), {
        data: { measured_at: "2026-01-01T10:00:00", glucose_mg_dl: 100 },
      });
      expect(glucose.status()).toBeGreaterThanOrEqual(400);
      expect(glucose.status()).toBeLessThan(500);
    }
  );

  test(
    "CSCW-CA-35 - landing regression: stays informative with login/register and without public patients",
    async ({ page }) => {
      await page.goto(ROUTES.landing, { waitUntil: "networkidle" });
      await expect(page.getByRole("heading", { name: t("landing.hero.title") })).toBeVisible();
      await expect(page.getByRole("link", { name: tx("auth.login") }).first()).toBeVisible();
      await expect(page.getByRole("link", { name: tx("auth.register") }).first()).toBeVisible();
      // No clinical UI elements on landing: no patient table/list, no SHORTID/CRM labels.
      await expect(page.getByRole("table")).toHaveCount(0);
      const text = await page.locator("body").innerText();
      expect(text).not.toMatch(/SHORTID|CRM/);
      expect(text).not.toMatch(/@[\w.-]+\.(com|invalid)/);
    }
  );

  test(
    "private routes redirect anonymous visitors to the login flow",
    async ({ page }) => {
      const id = "11111111-1111-1111-1111-111111111111";
      for (const route of [ROUTES.dashboard, ROUTES.investigation(id), ROUTES.patientDetail(id)]) {
        await page.goto(route);
        await expect(page).toHaveURL(/\/login$/);
      }
    }
  );

  test(
    "AUT-CA-23 - public responses/bundle expose no credentials, keys or clinical content",
    async ({ page, request }) => {
      await page.goto(ROUTES.landing, { waitUntil: "networkidle" });
      const html = await page.content();
      const forbidden = /MYGLICO_ENCRYPTION_KEY|MYGLICO_LOOKUP_HMAC|password_hash|cryptography|MasterKey/i;
      expect(html).not.toMatch(forbidden);
      const scriptUrls = await page.evaluate(() => {
        return Array.from(document.querySelectorAll("script[src]")).map((s) => s.src);
      });
      for (const u of scriptUrls.slice(0, 2)) {
        const resp = await request.get(u);
        const text = await resp.text();
        expect(text).not.toMatch(forbidden);
      }
      const resps = await Promise.all([
        request.get(LEGACY_API.dashboard),
        request.get(LEGACY_API.patients),
      ]);
      for (const r of resps) {
        expect(r.status()).toBeGreaterThanOrEqual(400);
      }
    }
  );
});
