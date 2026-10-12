// Flow group 10 (PROMPT-ORCA.md, "Testes end-to-end"): essential flows in the
// three languages and the clinical PDF in all three `lang` values with
// locale-correct dates/numbers and authorization validated on every request.
//
// Criteria: AUT-CA-12 (PDF authorization), AUT-CA-01/CSCW-CA-35 (localised
// landing copy), AUT-CA-23 (no secrets in delivered assets).
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, linkActive, seedAtypicalDays, test } from "../fixtures/test-fixtures.mjs";
import { ROUTES } from "../fixtures/routes.mjs";
import { LANGS, escapeRegex, t, tx } from "../fixtures/i18n.mjs";
import * as api from "../fixtures/api.mjs";

const pdfTextScript = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "scripts", "pdf_text.py");
const RANGE = { start_date: "2026-06-01", end_date: "2026-07-10" };
// Expected rendering of 2026-06-01 and of a decimal in each locale.
const DATE_BY_LANG = { "pt-BR": "01/06/2026", "en-US": "06/01/2026", es: "01/06/2026" };
const RAW_KEY = /\b(cscw|dashboard|auth|overview|patientDetail|notifications)\.[a-zA-Z]+/;

function pdfText(file) {
  const result = spawnSync(process.env.MYGLICO_E2E_PYTHON || "python", [pdfTextScript, file], { encoding: "utf-8" });
  if (result.status !== 0) throw new Error(result.stderr);
  return result.stdout;
}

async function switchLanguage(page, lang) {
  const anyLabel = new RegExp(LANGS.map((l) => escapeRegex(t("languageSwitcher.label", l))).join("|"));
  await page.getByRole("button", { name: anyLabel }).first().click();
  const labels = { "pt-BR": "Português", "en-US": "English", es: "Español" };
  await page.getByRole("menuitemradio", { name: new RegExp(labels[lang]) }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", lang);
}

test.describe("Group 10 - three languages and the clinical PDF", () => {
  for (const lang of LANGS) {
    test(`essential flows render in ${lang} (landing, register, login, links, investigations)`, async ({ actor, browserSession }) => {
      const patient = await actor("patientA");
      const doctor = await actor("doctorA");
      await linkActive(patient, doctor);
      const ui = await browserSession("patientA");
      const page = ui.page;

      await page.goto(ROUTES.landing);
      await switchLanguage(page, lang);
      await expect(page.getByRole("heading", { name: t("landing.hero.title", lang) })).toBeVisible();
      await page.getByRole("link", { name: tx("auth.register", lang) }).first().click();
      await expect(page.getByRole("button", { name: tx("auth.submitRegister", lang) })).toBeVisible();
      expect(await page.locator("body").innerText()).not.toMatch(RAW_KEY);

      await page.goto(ROUTES.login);
      await expect(page.getByRole("button", { name: tx("auth.submitLogin", lang) })).toBeVisible();
      await page.locator("input[type=email]").fill(patient.profile.email);
      await page.locator("input[type=password]").fill(patient.profile.password);
      await page.getByRole("button", { name: tx("auth.submitLogin", lang) }).click();
      await expect(page).toHaveURL(/\/dashboard$/);
      await expect(page.getByText(t("dashboard.myDoctors", lang)).first()).toBeVisible();
      await expect(page.locator(".react-nav").getByText(t("cscw.investigations", lang))).toBeVisible();
      await expect(page.getByText(t("dashboard.status.active", lang)).first()).toBeVisible();
      const body = await page.locator("body").innerText();
      expect(body).not.toMatch(RAW_KEY);
      if (lang !== "pt-BR") {
        expect(body).not.toContain(t("dashboard.myDoctors", "pt-BR"));
        expect(body).not.toContain("Carregando");
      }
    });

    test(`clinical PDF downloads in lang=${lang} with locale-correct dates and numbers`, async ({ actor }, testInfo) => {
      const patient = await actor("patientA");
      const doctor = await actor("doctorA");
      await linkActive(patient, doctor);
      seedAtypicalDays(patient.patientId, { days: 40 });

      for (const who of [patient, doctor]) {
        const pdf = await api.reportPdf(who.request, patient.patientId, { ...RANGE, lang });
        expect(pdf.status).toBe(200);
        expect(pdf.contentType).toContain("application/pdf");
        expect(pdf.disposition).toMatch(/^attachment; filename=".+\.pdf"$/);
        expect(pdf.body.subarray(0, 5).toString()).toBe("%PDF-");
        const file = testInfo.outputPath(`report-${lang}-${who === patient ? "patient" : "doctor"}.pdf`);
        fs.writeFileSync(file, pdf.body);
        const text = pdfText(file);
        const titles = { "pt-BR": "Relatório glicêmico", "en-US": "Glucose report", es: "Informe glucémico" };
        expect(text).toContain(titles[lang]);
        for (const other of LANGS.filter((l) => l !== lang)) expect(text).not.toContain(titles[other]);
        expect(text).toContain(DATE_BY_LANG[lang]);
        // Decimal separator: comma for pt-BR/es, dot for en-US.
        const decimals = text.match(/\b\d{2,3}[.,]\d\b/g) || [];
        expect(decimals.length).toBeGreaterThan(0);
        const sep = lang === "en-US" ? "." : ",";
        expect(decimals.filter((d) => d.includes(sep)).length).toBeGreaterThan(decimals.length / 2);
      }
    });
  }

  test("AUT-CA-12 - the PDF endpoint denies anonymous and cross-patient access", async ({ actor, playwright }) => {
    const patientA = await actor("patientA");
    const patientB = await actor("patientB");
    const doctorB = await actor("doctorB");
    seedAtypicalDays(patientB.patientId, { days: 15, spikes: [] });
    const anon = await playwright.request.newContext({ baseURL: test.info().project.use.baseURL });
    try {
      const anonymous = await api.reportPdf(anon, patientB.patientId, { ...RANGE, lang: "pt-BR" });
      expect(anonymous.status).toBe(401);
    } finally {
      await anon.dispose();
    }
    for (const lang of LANGS) {
      for (const intruder of [patientA, doctorB]) {
        const res = await api.reportPdf(intruder.request, patientB.patientId, { ...RANGE, lang });
        expect(res.status).toBe(404);
        expect(res.contentType).not.toContain("pdf");
        expect(res.body.toString()).not.toContain(patientB.profile.display_name);
      }
    }
    expect((await api.reportPdf(patientB.request, patientB.patientId, { ...RANGE, lang: "es" })).status).toBe(200);
  });

  test("AUT-CA-01/CSCW-CA-35 - landing copy is complete in all three languages", async ({ page }) => {
    const clinical = [];
    page.on("request", (req) => {
      if (/\/api\/(patients|dashboard|investigations|doctor-links|notifications)/.test(req.url())) clinical.push(req.url());
    });
    await page.goto(ROUTES.landing);
    for (const lang of LANGS) {
      await switchLanguage(page, lang);
      await expect(page.getByRole("heading", { name: t("landing.hero.title", lang) })).toBeVisible();
      await expect(page.getByText(t("landing.hero.body", lang))).toBeVisible();
      await expect(page.getByRole("link", { name: tx("auth.login", lang) }).first()).toBeVisible();
      await expect(page.getByRole("link", { name: tx("auth.register", lang) }).first()).toBeVisible();
      expect(await page.locator("body").innerText()).not.toMatch(RAW_KEY);
    }
    expect(t("landing.hero.title", "pt-BR")).not.toBe(t("landing.hero.title", "en-US"));
    expect(clinical).toEqual([]);
  });

  test("AUT-CA-23 - delivered scripts carry no credentials or keys in any language", async ({ page, request }) => {
    const keys = [process.env.MYGLICO_ENCRYPTION_KEY_V1, process.env.MYGLICO_LOOKUP_HMAC_KEY].filter(Boolean);
    const scripts = new Set();
    page.on("response", (res) => {
      if (/\.(m?js|jsx|css|json)(\?|$)/.test(res.url()) || res.request().resourceType() === "script") scripts.add(res.url());
    });
    await page.goto(ROUTES.landing);
    for (const lang of LANGS) await switchLanguage(page, lang);
    await page.goto(ROUTES.login);
    await page.goto(ROUTES.register);
    expect(scripts.size).toBeGreaterThan(0);
    const forbidden = /MYGLICO_(ENCRYPTION|LOOKUP)|password_hash|qwerty|BEGIN (RSA|PRIVATE)|@email\.com/i;
    for (const url of scripts) {
      const text = await (await request.get(url)).text();
      expect(text, url).not.toMatch(forbidden);
      for (const key of keys) expect(text, url).not.toContain(key);
    }
  });
});
