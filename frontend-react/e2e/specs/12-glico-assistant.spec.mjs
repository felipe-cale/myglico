import { expect, linkActive, test } from "../fixtures/test-fixtures.mjs";
import { LANGS, t } from "../fixtures/i18n.mjs";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const GLICO = "/glico";
const here = path.dirname(fileURLToPath(import.meta.url));

// 1x1 transparent PNG: a real, decodable image for the upload path.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64"
);

async function openAssistant(ui, { lang, viewport } = {}) {
  if (lang) await ui.page.addInitScript((value) => window.localStorage.setItem("myglico.language", value), lang);
  if (viewport) await ui.page.setViewportSize(viewport);
  await ui.authenticateWithApi();
  await ui.page.goto(GLICO);
  await expect(ui.page.getByRole("heading", { level: 1, name: t("glicoAssistant.title", lang || "pt-BR") })).toBeVisible();
}

const MAIN_CHIPS = ["readings", "atypical"];

async function chip(ui, key) {
  // Everyday shortcuts are always visible; the others sit behind "More options".
  if (!MAIN_CHIPS.includes(key)) {
    const more = ui.page.getByRole("button", { name: t("glicoAssistant.chips.more") });
    if ((await more.getAttribute("aria-expanded")) !== "true") await more.click();
  }
  await ui.page.getByRole("button", { name: t(`glicoAssistant.chips.${key}`) }).click();
}

async function sendPickedPhoto(ui) {
  await ui.page.getByRole("button", { name: t("glicoAssistant.media.sendPhoto") }).click();
}

async function expectNoHorizontalOverflow(page) {
  const dims = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, view: window.innerWidth }));
  expect(dims.doc, `content exceeds ${dims.view}px viewport`).toBeLessThanOrEqual(dims.view);
}

// Network-level stubs are used ONLY where the backend cannot yet produce the state (photo/audio capabilities are
// off in F1 until the media worker is provisioned). The UI and the browser are real.
async function stubMediaCapabilities(page) {
  await page.route("**/api/glico/capabilities*", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({ response, json: { ...body, photo: true, audio: true } });
  });
}

test.describe("Glico assistant - language model", () => {
  test("shows the privacy note, sends short history and renders the model's reply as plain text", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await ui.page.route("**/api/glico/capabilities*", async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      await route.fulfill({ response, json: { ...body, language_model: true } });
    });
    const bodies = [];
    await ui.page.route("**/api/glico/conversations/*/messages", async (route) => {
      bodies.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, json: { type: "message", text: "Oi! <b>Como</b> posso ajudar?" } });
    });
    await openAssistant(ui);
    await ui.page.getByRole("button", { name: t("glicoAssistant.notesTitle") }).click();
    await expect(ui.page.getByTestId("glico-llm-note")).toHaveText(t("glicoAssistant.llmNote"));
    await ui.page.keyboard.press("Escape");
    const field = ui.page.getByLabel(t("glicoAssistant.messageLabel"));
    await field.fill("oi");
    await ui.page.getByRole("button", { name: t("glicoAssistant.send"), exact: true }).click();
    await expect(ui.page.getByText("Oi! <b>Como</b> posso ajudar?")).toBeVisible();
    await field.fill("e agora?");
    await ui.page.getByRole("button", { name: t("glicoAssistant.send"), exact: true }).click();
    await expect.poll(() => bodies.length).toBe(2);
    expect(bodies[0].history).toBeUndefined();
    expect(bodies[1].history).toEqual([
      { role: "user", text: "oi" },
      { role: "assistant", text: "Oi! <b>Como</b> posso ajudar?" }
    ]);
  });
});

test.describe("Glico assistant - locales", () => {
  test("every glicoAssistant key exists in pt-BR, en-US and es", async () => {
    const dir = path.resolve(here, "..", "..", "src", "locales");
    const flatten = (node, prefix = "") =>
      Object.entries(node).flatMap(([key, value]) =>
        typeof value === "object" ? flatten(value, `${prefix}${key}.`) : [`${prefix}${key}`]
      );
    const keys = Object.fromEntries(
      LANGS.map((lang) => [lang, flatten(JSON.parse(fs.readFileSync(path.join(dir, `${lang}.json`), "utf-8")).glicoAssistant).sort()])
    );
    expect(keys["en-US"]).toEqual(keys["pt-BR"]);
    expect(keys.es).toEqual(keys["pt-BR"]);
    expect(keys["pt-BR"].length).toBeGreaterThan(50);
  });
});

test.describe("Glico assistant - patient", () => {
  test("navigates from the shell, proposes, edits, confirms and shows a receipt", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await ui.authenticateWithApi();
    await ui.page.goto("/dashboard");
    await ui.page.getByRole("link", { name: t("appShell.nav.assistant") }).first().click();
    await expect(ui.page).toHaveURL(/\/glico$/);

    const message = ui.page.getByLabel(t("glicoAssistant.messageLabel"));
    await expect(message).toBeEnabled();
    await message.fill("glicose 110 mg/dL");
    await ui.page.getByRole("button", { name: t("glicoAssistant.send"), exact: true }).click();

    const card = ui.page.getByTestId("glico-proposal");
    await expect(card).toBeVisible();
    await expect(card.getByLabel(t("glicoAssistant.valueLabel"))).toHaveValue("110");
    const confirm = card.getByRole("button", { name: t("glicoAssistant.confirm") });
    // No date/time was typed: the reading defaults to now, says so, and is ready for review.
    await expect(card.getByLabel(t("glicoAssistant.measuredAtLabel"))).not.toHaveValue("");
    await expect(card.getByText(t("glicoAssistant.measuredAtAssumed"))).toBeVisible();
    await expect(confirm).toBeEnabled();

    await card.getByLabel(t("glicoAssistant.valueLabel")).fill("118");
    await card.getByRole("button", { name: t("glicoAssistant.saveCorrection") }).click();
    await expect(card.getByLabel(t("glicoAssistant.valueLabel"))).toHaveValue("118");
    await expect(confirm).toBeEnabled();

    await confirm.click();
    await expect(ui.page.getByTestId("glico-receipt")).toBeVisible();
    await expect(ui.page.getByTestId("glico-proposal")).toHaveCount(0);
  });

  test("discarding a proposal removes the card", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await openAssistant(ui);
    await ui.page.getByLabel(t("glicoAssistant.messageLabel")).fill("glicose 95 mg/dL");
    await ui.page.getByRole("button", { name: t("glicoAssistant.send"), exact: true }).click();
    await expect(ui.page.getByTestId("glico-proposal")).toBeVisible();
    await ui.page.getByRole("button", { name: t("glicoAssistant.discard") }).click();
    await expect(ui.page.getByTestId("glico-proposal")).toHaveCount(0);
    await expect(ui.page.getByText(t("glicoAssistant.cancelled"))).toBeVisible();
  });

  test("text without a reading gets localized help with a navigation link", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await openAssistant(ui);
    await ui.page.getByLabel(t("glicoAssistant.messageLabel")).fill("oi, tudo bem?");
    await ui.page.getByRole("button", { name: t("glicoAssistant.send"), exact: true }).click();
    await expect(ui.page.getByText(t("glicoAssistant.helpManual"))).toBeVisible();
    await ui.page.getByRole("link", { name: t("glicoAssistant.goDashboard") }).first().click();
    await expect(ui.page).toHaveURL(/\/dashboard$/);
  });

  for (const lang of LANGS) {
    test(`FAQ answers deterministically in ${lang}`, async ({ actor, browserSession }) => {
      await actor("patientA");
      const ui = await browserSession("patientA", { locale: lang });
      await openAssistant(ui, { lang });
      await ui.page.getByRole("button", { name: t("glicoAssistant.chips.more", lang) }).click();
      await ui.page.getByRole("button", { name: t("glicoAssistant.faq.howLog.q", lang) }).click();
      await expect(ui.page.getByText(t("glicoAssistant.faq.howLog.a", lang))).toBeVisible();
      await ui.page.getByRole("button", { name: t("glicoAssistant.notesTitle", lang) }).click();
      await expect(ui.page.getByText(t("glicoAssistant.notClinicalAdvice", lang))).toBeVisible();
      await ui.page.keyboard.press("Escape");
    });
  }

  test("remains usable without overflow at 390, 768 and 1440px in all locales", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await openAssistant(ui);
    let currentLang = "pt-BR";
    for (const lang of LANGS) {
      if (lang !== currentLang) {
        await ui.page.getByRole("button", { name: t("languageSwitcher.label", currentLang) }).click();
        const languageName = lang === "en-US" ? /English/i : /Español/i;
        await ui.page.getByRole("menuitemradio", { name: languageName }).click();
        currentLang = lang;
      }
      for (const width of [390, 768, 1440]) {
        await ui.page.setViewportSize({ width, height: 900 });
        await expect(ui.page.getByRole("heading", { level: 1, name: t("glicoAssistant.title", lang) })).toBeVisible();
        await expect(ui.page.locator("#glico-message")).toBeEnabled();
        await expectNoHorizontalOverflow(ui.page);
      }
    }
  });

  test("opens a collaboration proposal for review and does not confirm it automatically", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    let posted;
    await ui.page.route("**/api/glico/conversations/*/collaboration-proposals", async (route) => {
      posted = route.request().postDataJSON();
      await route.fulfill({ status: 201, json: { proposal: {
        id: "22222222-2222-4222-8222-222222222222", kind: "investigation_open", version: 1,
        context_version: 1, state: "READY", expires_at: new Date(Date.now() + 600000).toISOString(),
        fields: { title: posted.title, content: posted.content }, missing_fields: [], warnings: [], origin: "glico_collaboration"
      } } });
    });
    await openAssistant(ui);
    await chip(ui, "open");
    await expect(ui.page.getByText(t("glicoAssistant.collab.openPrompt"))).toBeVisible();
    await ui.page.getByLabel(t("glicoAssistant.messageLabel")).fill("Reading question");
    await ui.page.getByRole("button", { name: t("glicoAssistant.send"), exact: true }).click();
    const card = ui.page.getByTestId("glico-proposal");
    await expect(card).toBeVisible();
    await expect(card.getByRole("heading", { name: t("glicoAssistant.investigation.openTitle") })).toBeVisible();
    await expect(card.getByRole("button", { name: t("glicoAssistant.confirm") })).toBeEnabled();
    expect(posted).toMatchObject({ kind: "investigation_open", title: "Reading question", content: "Reading question" });
  });

  test("voice dictation reports unsupported browsers in the selected locale", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await ui.page.addInitScript(() => {
      delete window.SpeechRecognition;
      delete window.webkitSpeechRecognition;
    });
    await openAssistant(ui);
    await chip(ui, "open");
    await ui.page.getByRole("button", { name: t("glicoAssistant.investigation.dictate") }).click();
    await expect(ui.page.getByTestId("glico-error")).toHaveText(t("glicoAssistant.errors.dictationUnavailable"));
  });

  test("renders accessible readings and a contextual patient PDF link for the selected period", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await ui.page.route("**/api/glico/conversations/*/messages", async (route) => {
      const text = route.request().postDataJSON().text;
      if (text.includes("leituras")) {
        await route.fulfill({ json: { answer_key: "glico.query.readings", items: [{ glucose_mg_dl: 123, measured_at: "2025-06-12T08:30:00Z", context_label: "fasting" }] } });
      } else {
        await route.fulfill({ json: { answer_key: "glico.query.pdf" } });
      }
    });
    await openAssistant(ui);
    await ui.page.getByLabel(t("glicoAssistant.messageLabel")).fill("minhas leituras recentes");
    await ui.page.getByRole("button", { name: t("glicoAssistant.send"), exact: true }).click();
    const list = ui.page.locator('[data-testid="glico-thread"] .glico__list');
    await expect(list.getByRole("heading", { name: t("glicoAssistant.query.readingsTitle") })).toBeVisible();
    await expect(list.locator("li")).toContainText("123 mg/dL");
    await expect(list.locator("time")).toHaveAttribute("datetime", "2025-06-12T08:30:00Z");

    await chip(ui, "period");
    await ui.page.getByLabel(t("glicoAssistant.period.startLabel")).fill("2025-06-01");
    await ui.page.getByLabel(t("glicoAssistant.period.endLabel")).fill("2025-06-30");
    await ui.page.getByRole("button", { name: t("glicoAssistant.period.apply") }).click();
    await expect(ui.page.getByLabel(t("glicoAssistant.period.startLabel"))).toHaveValue("2025-06-01");
    await ui.page.getByLabel(t("glicoAssistant.messageLabel")).fill("gerar relatório pdf");
    await ui.page.getByRole("button", { name: t("glicoAssistant.send"), exact: true }).click();
    const download = ui.page.getByRole("link", { name: t("glicoAssistant.query.pdfDownload") });
    await expect(download).toBeVisible();
    await expect(download).toHaveAttribute("href", /\/api\/patients\/[^/]+\/report\.pdf\?start_date=2025-06-01&end_date=2025-06-30&lang=pt-BR/);
  });

  test("logout clears the Glico draft and returning to the route does not restore it", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await openAssistant(ui);
    const composer = ui.page.locator("#glico-message");
    await composer.fill("private unsubmitted draft");
    await ui.page.getByRole("button", { name: t("auth.logout") }).first().click();
    await expect(ui.page).toHaveURL(/\/$|\/login$/);
    await ui.page.goto(GLICO);
    await expect(ui.page.locator("#glico-message")).toHaveCount(0);
    await expect(ui.page.getByText("private unsubmitted draft")).toHaveCount(0);
  });

  test("photo and audio are disabled with an explanation when the backend flags them off", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await openAssistant(ui);
    await expect(ui.page.getByRole("button", { name: t("glicoAssistant.media.photoButton") })).toBeDisabled();
    await expect(ui.page.getByRole("button", { name: t("glicoAssistant.media.audioStart") })).toBeDisabled();
    await expect(ui.page.getByText(t("glicoAssistant.media.disabledPhoto"))).toBeVisible();
  });

  test("fits a 390px mobile viewport and keeps 44px touch targets", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await openAssistant(ui, { viewport: { width: 390, height: 844 } });
    await ui.page.getByLabel(t("glicoAssistant.messageLabel")).fill("glicose 110 mg/dL");
    await ui.page.getByRole("button", { name: t("glicoAssistant.send"), exact: true }).click();
    await expect(ui.page.getByTestId("glico-proposal")).toBeVisible();
    await expectNoHorizontalOverflow(ui.page);
    for (const name of [t("glicoAssistant.confirm"), t("glicoAssistant.discard")]) {
      const box = await ui.page.getByRole("button", { name }).boundingBox();
      expect(box.height).toBeGreaterThanOrEqual(44);
    }
  });

  test("keyboard: composer, FAQ and actions are reachable and labelled", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await openAssistant(ui);
    await expect(ui.page.getByRole("region", { name: t("glicoAssistant.chatLabel") })).toBeVisible();
    await ui.page.getByLabel(t("glicoAssistant.messageLabel")).focus();
    await expect(ui.page.getByLabel(t("glicoAssistant.messageLabel"))).toBeFocused();
    await ui.page.getByRole("button", { name: t("glicoAssistant.chips.more") }).click();
    await ui.page.getByRole("button", { name: t("glicoAssistant.faq.privacy.q") }).focus();
    await ui.page.keyboard.press("Enter");
    await expect(ui.page.getByText(t("glicoAssistant.faq.privacy.a"))).toBeVisible();
  });
});

test.describe("Glico assistant - media states (UI against stubbed extract endpoints)", () => {
  const cases = [
    { status: 413, detail: "payload_too_large", key: "errors.tooLarge" },
    { status: 415, detail: "unsupported_media_type", key: "errors.unsupported" },
    { status: 422, detail: "ambiguous_reading", key: "errors.ambiguous" },
    { status: 503, detail: "capability_unavailable", key: "errors.unavailable" },
    { status: 504, detail: "processing_timeout", key: "errors.timeout" },
    { status: 429, detail: "quota_exceeded", key: "errors.limitRetry", headers: { "Retry-After": "30" }, vars: { wait: "30 s" } }
  ];
  for (const item of cases) {
    test(`photo upload ${item.status} shows a localized message`, async ({ actor, browserSession }) => {
      await actor("patientA");
      const ui = await browserSession("patientA");
      await stubMediaCapabilities(ui.page);
      let received;
      await ui.page.route("**/api/glico/conversations/*/extract/image", async (route) => {
        received = route.request().headers();
        await route.fulfill({ status: item.status, headers: item.headers || {}, json: { detail: item.detail } });
      });
      await openAssistant(ui);
      await ui.page.getByTestId("glico-photo-input").setInputFiles({ name: "visor.png", mimeType: "image/png", buffer: PNG });
      await sendPickedPhoto(ui);
      await expect(ui.page.getByTestId("glico-error")).toHaveText(t(`glicoAssistant.${item.key}`, "pt-BR", item.vars));
      expect(received["content-type"]).toBe("application/octet-stream");
      expect(received["x-glico-context-version"]).toBeTruthy();
      expect(received["x-glico-request-id"]).toBeTruthy();
      expect(received["x-myglico-csrf"]).toBeTruthy();
    });
  }

  test("photo rejected client-side when the type is unsupported or the file is too large", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await stubMediaCapabilities(ui.page);
    let calls = 0;
    await ui.page.route("**/api/glico/conversations/*/extract/image", (route) => { calls += 1; return route.abort(); });
    await openAssistant(ui);
    await ui.page.getByTestId("glico-photo-input").setInputFiles({ name: "x.gif", mimeType: "image/gif", buffer: PNG });
    await expect(ui.page.getByTestId("glico-error")).toHaveText(t("glicoAssistant.errors.unsupported"));
    // not a decodable image and over the limit: it cannot be shrunk, so sending is refused locally
    await ui.page.getByTestId("glico-photo-input").setInputFiles({ name: "big.png", mimeType: "image/png", buffer: Buffer.alloc(3 * 1024 * 1024 + 1) });
    await sendPickedPhoto(ui);
    await expect(ui.page.getByTestId("glico-error")).toHaveText(t("glicoAssistant.errors.tooLarge"));
    expect(calls).toBe(0);
  });

  test("an in-flight photo upload can be cancelled and nothing is kept", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await stubMediaCapabilities(ui.page);
    await ui.page.route("**/api/glico/conversations/*/extract/image", () => {});
    await openAssistant(ui);
    await ui.page.getByTestId("glico-photo-input").setInputFiles({ name: "visor.png", mimeType: "image/png", buffer: PNG });
    await sendPickedPhoto(ui);
    await expect(ui.page.getByText(t("glicoAssistant.media.processingPhoto"))).toBeVisible();
    await ui.page.getByRole("button", { name: t("glicoAssistant.media.cancel") }).click();
    await expect(ui.page.getByText(t("glicoAssistant.media.discarded"))).toBeVisible();
    await expect(ui.page.getByText(t("glicoAssistant.media.processingPhoto"))).toHaveCount(0);
  });

  test("a photo proposal opens the review card and is never confirmed automatically", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await stubMediaCapabilities(ui.page);
    let confirmCalls = 0;
    await ui.page.route("**/api/glico/proposals/*/confirm", (route) => { confirmCalls += 1; return route.continue(); });
    await ui.page.route("**/api/glico/conversations/*/extract/image", (route) =>
      route.fulfill({
        json: {
          type: "proposal",
          proposal: {
            id: "11111111-1111-4111-8111-111111111111", kind: "glucose_single", version: 1, context_version: 1, state: "READY",
            expires_at: new Date(Date.now() + 600000).toISOString(),
            fields: { glucose_mg_dl: 132, measured_at: new Date().toISOString() }, missing_fields: [], warnings: [], origin: "glico_photo"
          }
        }
      })
    );
    await openAssistant(ui);
    await ui.page.getByTestId("glico-photo-input").setInputFiles({ name: "visor.png", mimeType: "image/png", buffer: PNG });
    await sendPickedPhoto(ui);
    const card = ui.page.getByTestId("glico-proposal");
    await expect(card.getByLabel(t("glicoAssistant.valueLabel"))).toHaveValue("132");
    expect(confirmCalls).toBe(0);
  });

  test("microphone denied shows a localized error and never uploads", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await stubMediaCapabilities(ui.page);
    await ui.page.addInitScript(() => {
      Object.defineProperty(navigator, "mediaDevices", {
        configurable: true,
        value: { getUserMedia: () => Promise.reject(Object.assign(new Error("denied"), { name: "NotAllowedError" })) }
      });
    });
    let uploads = 0;
    await ui.page.route("**/api/glico/conversations/*/extract/audio", (route) => { uploads += 1; return route.abort(); });
    await openAssistant(ui);
    await ui.page.getByRole("button", { name: t("glicoAssistant.media.audioStart") }).click();
    await expect(ui.page.getByTestId("glico-error")).toHaveText(t("glicoAssistant.errors.micDenied"));
    expect(uploads).toBe(0);
  });
});

test.describe("Glico assistant - doctor", () => {
  test("must pick a linked patient explicitly before chatting; cannot confirm glucose", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const ui = await browserSession("doctorA");
    await openAssistant(ui);

    const message = ui.page.getByLabel(t("glicoAssistant.messageLabel"));
    await expect(message).toBeDisabled();
    await expect(ui.page.getByText(t("glicoAssistant.selectPatientRequired"))).toBeVisible();

    await ui.page.getByRole("button", { name: t("glicoAssistant.selectPatient") }).click();
    await ui.page.getByRole("option", { name: patient.profile?.display_name || "Paciente A (E2E)" }).click();
    await expect(message).toBeEnabled();

    await message.fill("glicose 110 mg/dL");
    await ui.page.getByRole("button", { name: t("glicoAssistant.send"), exact: true }).click();
    await expect(ui.page.getByTestId("glico-error")).toHaveText(t("glicoAssistant.errors.notAllowed"));
    await expect(ui.page.getByTestId("glico-proposal")).toHaveCount(0);
  });

  test("one-tap report shortcuts set the period and hand over the PDF link for the chosen patient", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const ui = await browserSession("doctorA");
    await openAssistant(ui);
    await ui.page.getByRole("button", { name: t("glicoAssistant.selectPatient") }).click();
    await ui.page.getByRole("option", { name: patient.profile?.display_name || "Paciente A (E2E)" }).click();

    // A doctor only gets four shortcuts and cannot log readings (no photo or audio capture).
    await expect(ui.page.getByRole("list", { name: t("glicoAssistant.chips.title") }).getByRole("button")).toHaveCount(4);
    await expect(ui.page.getByRole("button", { name: t("glicoAssistant.media.sendPhoto") })).toHaveCount(0);

    const links = ui.page.getByRole("link", { name: t("glicoAssistant.query.pdfDownload") });
    for (const [index, months] of [1, 3].entries()) {
      await ui.page.getByRole("button", { name: t(months === 1 ? "glicoAssistant.chips.reportMonths_one" : "glicoAssistant.chips.reportMonths_other", "pt-BR", { count: months }) }).click();
      await expect(links).toHaveCount(index + 1);
      const download = links.last();
      const href = await download.getAttribute("href");
      const params = new URL(href, "http://x").searchParams;
      const start = new Date(params.get("start_date"));
      const end = new Date(params.get("end_date"));
      const spanDays = (end - start) / 86400000;
      expect(spanDays).toBeGreaterThanOrEqual(months * 28);
      expect(spanDays).toBeLessThanOrEqual(months * 31 + 1);
    }
  });

  test("doctor without links sees an empty-state hint and the unrelated patient is never offered", async ({ actor, browserSession }) => {
    await actor("patientB");
    await actor("doctorB");
    const ui = await browserSession("doctorB");
    await openAssistant(ui);
    const picker = ui.page.getByRole("button", { name: t("glicoAssistant.selectPatient") });
    await expect(picker).toHaveText(t("glicoAssistant.selectPatientPlaceholder"));
    await picker.click();
    await expect(ui.page.getByRole("option")).toHaveCount(0);
    await expect(ui.page.getByText(t("glicoAssistant.noPatients"))).toBeVisible();
  });

  test("fits a 390px mobile viewport", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const ui = await browserSession("doctorA");
    await openAssistant(ui, { viewport: { width: 390, height: 844 } });
    await expectNoHorizontalOverflow(ui.page);
  });
});

test.describe("Glico assistant - usage limit message", () => {
  test("a long wait is shown as hours and minutes, not raw seconds", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await stubMediaCapabilities(ui.page);
    await ui.page.route("**/api/glico/conversations/*/extract/audio", (route) => route.fulfill({
      status: 429, headers: { "Retry-After": "35794" }, json: { detail: "quota_exceeded" } }));
    await openAssistant(ui);
    await ui.page.getByTestId("glico-photo-input").setInputFiles({ name: "v.png", mimeType: "image/png", buffer: PNG });
    await ui.page.route("**/api/glico/conversations/*/extract/image", (route) => route.fulfill({
      status: 429, headers: { "Retry-After": "35794" }, json: { detail: "quota_exceeded" } }));
    await sendPickedPhoto(ui);
    await expect(ui.page.getByTestId("glico-error")).toHaveText(t("glicoAssistant.errors.limitRetry", "pt-BR", { wait: "9 h 57 min" }));
  });
});

test.describe("Glico assistant - conversation order", () => {
  test("each proposal and receipt stays where it happened while new messages keep arriving below", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await openAssistant(ui);
    const field = ui.page.getByLabel(t("glicoAssistant.messageLabel"));
    const send = ui.page.getByRole("button", { name: t("glicoAssistant.send"), exact: true });
    const thread = ui.page.getByTestId("glico-thread");

    await field.fill("52 mg/dL");
    await send.click();
    await expect(ui.page.getByTestId("glico-proposal")).toHaveCount(1);
    await field.fill("94 mg/dL");
    await send.click();
    await expect(thread.getByText(t("glicoAssistant.proposalReplaced"))).toHaveCount(1);
    await expect(ui.page.getByTestId("glico-proposal")).toHaveCount(1);

    const order = await thread.locator("article").evaluateAll((nodes) => nodes.map((node) => {
      if (node.querySelector('[data-testid="glico-proposal"]')) return "card";
      if (/replaced|substitu|reemplaz/i.test(node.textContent)) return "old-card";
      return node.classList.contains("glico__message--user") ? "user" : "glico";
    }));
    // user, glico text, (old card), user, glico text, live card
    expect(order).toEqual(["user", "glico", "old-card", "user", "glico", "card"]);

    await ui.page.getByTestId("glico-proposal").getByRole("button", { name: t("glicoAssistant.confirm") }).click();
    await expect(ui.page.getByTestId("glico-receipt")).toHaveCount(1);
    await expect(ui.page.getByTestId("glico-proposal")).toHaveCount(0);
    await field.fill("minhas leituras recentes");
    await send.click();
    const after = await thread.locator("article").evaluateAll((nodes) => nodes.map((node) => (
      node.querySelector('[data-testid="glico-receipt"]') ? "receipt" : node.classList.contains("glico__message--user") ? "user" : "glico")));
    // the receipt stays above the newer exchange instead of sinking to the bottom
    expect(after.indexOf("receipt")).toBeLessThan(after.lastIndexOf("user"));
  });
});


test.describe("Glico assistant - camera photos", () => {
  test("a multi-megabyte camera photo is shrunk in the browser before it is uploaded", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await stubMediaCapabilities(ui.page);
    let uploaded = null;
    await ui.page.route("**/api/glico/conversations/*/extract/image", async (route) => {
      uploaded = route.request().postDataBuffer();
      await route.fulfill({ status: 200, json: { type: "clarification", answer_key: "glico.reading.ambiguous_image" } });
    });
    await openAssistant(ui);
    const original = await ui.page.evaluate(async () => {
      const canvas = document.createElement("canvas");
      canvas.width = 3264;
      canvas.height = 2448;
      const ctx = canvas.getContext("2d");
      const image = ctx.createImageData(canvas.width, canvas.height);
      for (let i = 0; i < image.data.length; i += 4) {
        image.data[i] = Math.random() * 255; image.data[i + 1] = Math.random() * 255; image.data[i + 2] = Math.random() * 255; image.data[i + 3] = 255;
      }
      ctx.putImageData(image, 0, 0);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 1));
      const file = new File([blob], "camera.jpg", { type: "image/jpeg" });
      const transfer = new DataTransfer();
      transfer.items.add(file);
      const input = document.querySelector('[data-testid="glico-photo-input"]');
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return file.size;
    });
    expect(original).toBeGreaterThan(3 * 1024 * 1024);
    await sendPickedPhoto(ui);
    await expect.poll(() => uploaded?.length ?? 0).toBeGreaterThan(0);
    expect(uploaded.length).toBeLessThan(3 * 1024 * 1024);
    expect(uploaded.length).toBeLessThan(original / 2);
  });
});

test.describe("Glico assistant - low confidence audio", () => {
  test("a flagged proposal shows the check-the-value note in the user's language", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await ui.page.route("**/api/glico/conversations/*/messages", async (route) => {
      await route.fulfill({ status: 200, json: { type: "proposal", proposal: {
        id: "33333333-3333-4333-8333-333333333333", kind: "glucose_single", version: 1, context_version: 1, state: "READY",
        expires_at: new Date(Date.now() + 600000).toISOString(),
        fields: { glucose_mg_dl: 84, original_value: 84, original_unit: "mg/dL", measured_at: new Date().toISOString(), timezone: "UTC", context_label: null, notes: null },
        missing_fields: [], warnings: ["low_confidence"], origin: "glico_audio" } } });
    });
    await openAssistant(ui);
    await ui.page.getByLabel(t("glicoAssistant.messageLabel")).fill("84");
    await ui.page.getByRole("button", { name: t("glicoAssistant.send"), exact: true }).click();
    await expect(ui.page.getByTestId("glico-proposal").getByText(t("glicoAssistant.lowConfidenceAudio"))).toBeVisible();
  });
});

test.describe("Glico assistant - unexpected failure", () => {
  test("an unexpected server error leaves the chat for the friendly error screen, and retry returns to the chat", async ({ actor, browserSession }) => {
    await actor("patientA");
    const ui = await browserSession("patientA");
    await ui.page.route("**/api/glico/conversations/*/messages", (route) => route.fulfill({ status: 500, json: { detail: "boom" } }));
    await openAssistant(ui);
    await ui.page.getByLabel(t("glicoAssistant.messageLabel")).fill("quanto foi minha ultima medicao");
    await ui.page.getByRole("button", { name: t("glicoAssistant.send"), exact: true }).click();
    await expect(ui.page).toHaveURL(/\/erro\?origem=glico$/);
    await expect(ui.page.getByRole("heading", { level: 1, name: t("errorPage.title") })).toBeVisible();
    await expect(ui.page.getByText(t("errorPage.bodyGlico"))).toBeVisible();
    await ui.page.getByRole("button", { name: t("errorPage.retry") }).click();
    await expect(ui.page).toHaveURL(/\/glico$/);
  });

  test("the error screen is available at /erro in all three languages", async ({ page }) => {
    for (const lang of LANGS) {
      await page.addInitScript((value) => window.localStorage.setItem("myglico.language", value), lang);
      await page.goto("/erro");
      await expect(page.getByRole("heading", { level: 1, name: t("errorPage.title", lang) })).toBeVisible();
      await expect(page.getByRole("button", { name: t("errorPage.retry", lang) })).toBeVisible();
      await expect(page.getByRole("link", { name: t("errorPage.home", lang) })).toBeVisible();
    }
  });
});
