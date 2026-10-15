import { expect, test } from "@playwright/test";
import { t, LANGS } from "../fixtures/i18n.mjs";

const credentials = {
  email: process.env.GLICO_E2E_PATIENT_EMAIL,
  password: process.env.GLICO_E2E_PATIENT_PASSWORD,
};

async function loginAndOpen(page, browserContext, request, lang = "pt-BR", viewport = { width: 1440, height: 960 }, account = credentials) {
  expect(account.email).toBeTruthy();
  expect(account.password).toBeTruthy();
  await page.setViewportSize(viewport);
  await page.addInitScript((language) => localStorage.setItem("myglico.language", language), lang);
  const login = await request.post("/api/auth/login", { data: account });
  expect(login.status()).toBe(200);
  await browserContext.addCookies((await request.storageState()).cookies);
  await page.goto("/glico");
  await expect(page.getByRole("heading", { level: 1, name: t("glicoAssistant.title", lang) })).toBeVisible();
}

test("live backend: FAQ, proposal edit/confirm, readings, cancellation and three locales", async ({ page, context, request }) => {
  await loginAndOpen(page, context, request);
  await page.getByRole("button", { name: t("glicoAssistant.chips.more") }).click();
  await page.getByRole("button", { name: t("glicoAssistant.faq.privacy.q") }).click();
  await expect(page.getByText(t("glicoAssistant.faq.privacy.a"))).toBeVisible();

  const message = page.getByLabel(t("glicoAssistant.messageLabel"));
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  const timestamp = `${local.toISOString().slice(0, 10)} ${local.toISOString().slice(11, 16)}`;
  await message.fill(`glicose 110 mg/dL ${timestamp}`);
  await page.getByRole("button", { name: t("glicoAssistant.send"), exact: true }).click();
  const card = page.getByTestId("glico-proposal");
  await expect(card.getByLabel(t("glicoAssistant.valueLabel"))).toHaveValue("110");
  await card.getByLabel(t("glicoAssistant.valueLabel")).fill("118");
  await card.getByRole("button", { name: t("glicoAssistant.saveCorrection") }).click();
  await expect(card.getByLabel(t("glicoAssistant.valueLabel"))).toHaveValue("118");
  await card.getByRole("button", { name: t("glicoAssistant.confirm") }).click();
  await expect(page.getByTestId("glico-receipt")).toBeVisible();
  const panelLink = page.getByRole("link", { name: t("glicoAssistant.viewPatientPanel") });
  await expect(panelLink).toBeVisible();
  await panelLink.click();
  await expect(page.getByText("118 mg/dL").first()).toBeVisible();
  await page.goto("/glico");
  await expect(page.getByRole("heading", { level: 1, name: t("glicoAssistant.title") })).toBeVisible();

  let readingQuery = null;
  page.on("response", async (response) => {
    if (!response.url().includes("/messages") || response.request().method() !== "POST") return;
    try {
      const body = await response.json();
      if (body.answer_key === "glico.query.readings") readingQuery = body;
    } catch { /* Non JSON response is irrelevant to this observer. */ }
  });
  await message.fill("minhas leituras recentes");
  await page.getByRole("button", { name: t("glicoAssistant.send"), exact: true }).click();
  await expect.poll(() => readingQuery?.items?.some((item) => item.glucose_mg_dl === 118)).toBe(true);
  await expect(page.locator('[data-testid="glico-thread"] .glico__list li').filter({ hasText: "118 mg/dL" })).toBeVisible();

  await message.fill("glicose 95 mg/dL");
  await page.getByRole("button", { name: t("glicoAssistant.send"), exact: true }).click();
  await expect(page.getByTestId("glico-proposal")).toBeVisible();
  await page.getByRole("button", { name: t("glicoAssistant.discard") }).click();
  await expect(page.getByText(t("glicoAssistant.cancelled"))).toBeVisible();

  let currentLang = "pt-BR";
  for (const lang of LANGS) {
    await page.getByRole("button", { name: t("languageSwitcher.label", currentLang) }).click();
    const label = lang === "pt-BR" ? /Português/i : lang === "en-US" ? /English/i : /Español/i;
    await page.getByRole("menuitemradio", { name: label }).click();
    await expect(page.getByRole("heading", { level: 1, name: t("glicoAssistant.title", lang) })).toBeVisible();
    currentLang = lang;
  }
});

test("live backend: doctor selects the linked patient before using the conversation", async ({ page, context, request }) => {
  await loginAndOpen(page, context, request, "pt-BR", { width: 1440, height: 960 }, {
    email: process.env.GLICO_E2E_DOCTOR_EMAIL,
    password: process.env.GLICO_E2E_DOCTOR_PASSWORD,
  });
  const composer = page.getByLabel(t("glicoAssistant.messageLabel"));
  await expect(composer).toBeDisabled();
  await page.getByLabel(t("glicoAssistant.selectPatient")).selectOption({ label: "E2E patient" });
  await expect(composer).toBeEnabled();
  await page.getByRole("button", { name: t("glicoAssistant.chips.more") }).click().catch(() => {});
  await page.getByRole("button", { name: t("glicoAssistant.faq.howLog.q") }).click();
  await expect(page.getByText(t("glicoAssistant.faq.howLog.a"))).toBeVisible();
});

test("live backend: media capability and payload errors are real; responsive desktop and mobile", async ({ page, context, request }) => {
  await loginAndOpen(page, context, request, "pt-BR", { width: 1440, height: 960 });
  await expect(page.getByRole("button", { name: t("glicoAssistant.media.photoButton") })).toBeDisabled();
  await expect(page.getByRole("button", { name: t("glicoAssistant.media.audioStart") })).toBeDisabled();
  await expect(page.getByText(t("glicoAssistant.media.disabledPhoto"))).toBeVisible();

  const mediaStatuses = await page.evaluate(async () => {
    const csrfResponse = await fetch("/api/glico/csrf", { credentials: "same-origin" });
    const { token } = await csrfResponse.json();
    const createdResponse = await fetch("/api/glico/conversations", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-MyGlico-CSRF": token },
      body: JSON.stringify({ locale: "pt-BR", client_request_id: crypto.randomUUID() }),
    });
    const conversation = await createdResponse.json();
    const results = {};
    for (const kind of ["image", "audio"]) {
      const response = await fetch(`/api/glico/conversations/${conversation.id}/extract/${kind}`, {
        method: "POST", credentials: "same-origin",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-MyGlico-CSRF": token,
          "X-Glico-Context-Version": String(conversation.context_version),
          "X-Glico-Request-Id": crypto.randomUUID(),
        },
        body: new Uint8Array([1, 2, 3, 4]),
      });
      results[kind] = response.status;
    }
    return { creationStatus: createdResponse.status, ...results };
  });
  expect(mediaStatuses.creationStatus).toBe(201);
  expect(mediaStatuses.image).toBe(503);
  expect(mediaStatuses.audio).toBe(503);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { level: 1, name: t("glicoAssistant.title") })).toBeVisible();
  const dimensions = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: innerWidth }));
  expect(dimensions.width).toBeLessThanOrEqual(dimensions.viewport);
});
