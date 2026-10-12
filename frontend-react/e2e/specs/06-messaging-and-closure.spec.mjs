// Flow group 6 (PROMPT-ORCA.md, "Testes end-to-end"): message exchange,
// authorship, ordering, AwaitingRole, empty/limit/XSS, closing and post-CLOSED.
//
// Criteria: CSCW-CA-18, CSCW-CA-20, CSCW-CA-21, CSCW-CA-22, CSCW-CA-30,
// CSCW-CA-33 (Não aplicável — single role per account), AUT-CA-15 (secondary).
import { expect, linkActive, openInvestigationAsPatient, seedAtypicalDays, test } from "../fixtures/test-fixtures.mjs";
import { ROUTES } from "../fixtures/routes.mjs";
import { t, tx } from "../fixtures/i18n.mjs";
import * as api from "../fixtures/api.mjs";

async function conversationPage(browserSession, key, investigationId) {
  const ui = await browserSession(key);
  await ui.authenticateWithApi();
  await ui.page.goto(ROUTES.investigation(investigationId));
  return ui;
}

function composer(page) {
  const form = page.locator("form").filter({ has: page.getByRole("button", { name: tx("cscw.send") }) });
  return { form, input: form.locator("input[type=text], textarea").first() };
}

test.describe("Group 6 - messaging and closure", () => {
  test("CSCW-CA-18 - a message sent in the UI is server-authored, ordered and protected", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const inv = await openInvestigationAsPatient(patient, doctor, { initial_message: "m1 paciente" });

    const ui = await conversationPage(browserSession, "doctorA", inv.id);
    await expect(ui.page.getByText("m1 paciente")).toBeVisible();
    const { form, input } = composer(ui.page);
    await input.fill("m2 médico pela UI");
    const sent = ui.page.waitForResponse((r) => r.url().endsWith(`/api/investigations/${inv.id}/messages`));
    await form.getByRole("button", { name: tx("cscw.send") }).click();
    const message = (await (await sent).json()).message;
    expect(message.author_role).toBe("doctor");
    expect(message.author_domain_id).toBe(doctor.doctorId);
    expect(message.sequence).toBe(2);
    await expect(ui.page.getByText("m2 médico pela UI")).toBeVisible();

    // Client cannot forge authorship or sequence.
    const forged = await patient.request.post(`/api/investigations/${inv.id}/messages`, {
      data: { content: "forjada", author_role: "doctor", sequence: 99 },
    });
    expect(forged.status()).toBe(422);
    expect((await api.postMessage(patient.request, inv.id, "m3 paciente")).body.message.sequence).toBe(3);
    const detail = (await api.getInvestigation(patient.request, inv.id)).body;
    expect(detail.messages.map((m) => [m.sequence, m.author_role, m.content])).toEqual([
      [1, "patient", "m1 paciente"], [2, "doctor", "m2 médico pela UI"], [3, "patient", "m3 paciente"],
    ]);
    // Ciphertext-at-rest for messages is asserted in tests/integration/test_crypto_and_secrets.py.
  });

  test("the conversation scrolls to the newest message after sending", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const inv = await openInvestigationAsPatient(patient, doctor, { initial_message: "m1 paciente" });
    for (let sequence = 2; sequence <= 19; sequence += 1) {
      expect((await api.postMessage(patient.request, inv.id, `m${sequence} paciente`)).status).toBe(201);
    }

    const ui = await conversationPage(browserSession, "doctorA", inv.id);
    const { form, input } = composer(ui.page);
    const messageList = ui.page.locator(".react-message-list");
    await input.fill("m20 médico");
    await form.getByRole("button", { name: tx("cscw.send") }).click();

    await expect(ui.page.getByText("m20 médico", { exact: true })).toBeVisible();
    await expect.poll(() => messageList.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
    await expect.poll(() => messageList.evaluate((element) => element.scrollTop + element.clientHeight >= element.scrollHeight - 2)).toBe(true);
  });

  test("CSCW-CA-33 (Não aplicável) - author role always derives from the account's single role", async ({ actor }) => {
    // Product decision 2026-10-07: one role per account; there is no context switch to test.
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const inv = await openInvestigationAsPatient(patient, doctor);
    const viaContextHeader = await doctor.request.post(`/api/investigations/${inv.id}/messages`, {
      data: { content: "com header de contexto" }, headers: { "X-Context": "patient" },
    });
    expect([201, 400, 403]).toContain(viaContextHeader.status());
    if (viaContextHeader.status() === 201) {
      expect((await viaContextHeader.json()).message.author_role).toBe("doctor");
    }
  });

  test("AwaitingRole tracks the last valid author without blocking consecutive messages", async ({ actor }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const inv = await openInvestigationAsPatient(patient, doctor);
    expect(inv.awaiting_role).toBe("doctor");
    expect((await api.postMessage(patient.request, inv.id, "segunda seguida")).status).toBe(201);
    expect((await api.getInvestigation(patient.request, inv.id)).body.investigation.awaiting_role).toBe("doctor");
    expect((await api.postMessage(doctor.request, inv.id, "resposta")).status).toBe(201);
    expect((await api.getInvestigation(patient.request, inv.id)).body.investigation.awaiting_role).toBe("patient");
  });

  test("empty content, over-limit content and script payloads are rejected or rendered safely", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const inv = await openInvestigationAsPatient(patient, doctor);

    expect((await api.postMessage(patient.request, inv.id, "")).status).toBe(422);
    expect((await api.postMessage(patient.request, inv.id, "    ")).status).toBe(400);
    expect((await api.postMessage(patient.request, inv.id, "x".repeat(10_001))).status).toBe(422);
    expect((await api.postMessage(patient.request, inv.id, "x".repeat(10_000))).status).toBe(201);
    const payload = `<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>`;
    expect((await api.postMessage(patient.request, inv.id, payload)).status).toBe(201);

    const ui = await conversationPage(browserSession, "doctorA", inv.id);
    await expect(ui.page.getByText(payload)).toBeVisible();
    expect(await ui.page.evaluate(() => window.__xss)).toBeUndefined();
    expect(await ui.page.locator("img[src=x]").count()).toBe(0);
  });

  test("CSCW-CA-20 - either participant closes (UI and API) with correct authorship and no counterparty approval", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const byDoctor = await openInvestigationAsPatient(patient, doctor, { title: "Encerrada pelo médico" });
    const byPatient = await openInvestigationAsPatient(patient, doctor, { title: "Encerrada pelo paciente" });

    const ui = await conversationPage(browserSession, "doctorA", byDoctor.id);
    const closed = ui.page.waitForResponse((r) => r.url().endsWith(`/api/investigations/${byDoctor.id}/close`));
    await ui.page.getByRole("button", { name: tx("cscw.close") }).click();
    // The UI asks for an optional closing observation before confirming.
    await ui.page.getByRole("button", { name: tx("cscw.confirmClose") }).click();
    expect((await closed).status()).toBe(200);
    await expect(ui.page.getByRole("status").filter({ hasText: t("cscw.closedReason.PARTICIPANT_CLOSED") })).toBeVisible();
    await expect(ui.page.getByRole("button", { name: tx("cscw.send") })).toHaveCount(0);

    const d1 = (await api.getInvestigation(patient.request, byDoctor.id)).body.investigation;
    expect(d1).toMatchObject({ status: "closed", closed_by: doctor.doctorId, closed_reason: "PARTICIPANT_CLOSED", awaiting_role: null });

    const r2 = await api.closeInvestigation(patient.request, byPatient.id, { version: byPatient.version, observation: "Resolvido" });
    expect(r2.status).toBe(200);
    expect(r2.body.investigation).toMatchObject({ status: "closed", closed_by: patient.patientId });
    const last = (await api.getInvestigation(doctor.request, byPatient.id)).body.messages.at(-1);
    expect(last).toMatchObject({ author_role: "patient", content: "Resolvido" });
    const doctorNotes = (await api.notifications(doctor.request)).body.notifications.map((n) => n.notification_type);
    expect(doctorNotes).toContain("investigation_closed");
  });

  test("CSCW-CA-21 - sending after CLOSED is rejected and the history stays intact", async ({ actor }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const inv = await openInvestigationAsPatient(patient, doctor, { initial_message: "antes" });
    expect((await api.closeInvestigation(doctor.request, inv.id, { version: inv.version })).status).toBe(200);
    for (const who of [patient, doctor]) {
      const res = await api.postMessage(who.request, inv.id, "depois");
      expect(res.status).toBe(409);
    }
    const detail = (await api.getInvestigation(patient.request, inv.id)).body;
    expect(detail.messages.map((m) => m.content)).toEqual(["antes"]);
    // Closing again is a no-op (idempotent), not a re-open.
    expect((await api.closeInvestigation(patient.request, inv.id, { version: inv.version })).body.investigation.status).toBe("closed");
  });

  test("CSCW-CA-30 - concurrent close/send and confirm/revoke resolve to valid transitions only", async ({ actor, apiSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const inv = await openInvestigationAsPatient(patient, doctor);

    const results = await Promise.all([
      api.closeInvestigation(doctor.request, inv.id, { version: inv.version }),
      api.postMessage(patient.request, inv.id, "corrida 1"),
      api.postMessage(patient.request, inv.id, "corrida 2"),
    ]);
    for (const r of results) expect([200, 201, 409]).toContain(r.status);
    const detail = (await api.getInvestigation(patient.request, inv.id)).body;
    const sequences = detail.messages.map((m) => m.sequence);
    expect(new Set(sequences).size).toBe(sequences.length);
    expect(sequences).toEqual([...sequences].sort((a, b) => a - b));
    if (detail.investigation.status === "closed") {
      const closedAt = new Date(detail.investigation.closed_at).getTime();
      for (const m of detail.messages) expect(new Date(m.created_at).getTime()).toBeLessThanOrEqual(closedAt);
    }

    // Confirm vs revoke race on a fresh pending link.
    const doctorB = await actor("doctorB");
    const pending = (await api.createDoctorLink(patient.request, doctorB.shortId)).body.link;
    const race = await Promise.all([
      api.decideDoctorLink(doctorB.request, pending.id, "confirm", pending.version),
      api.decideDoctorLink(doctorB.request, pending.id, "reject", pending.version),
      api.decideDoctorLink(doctorB.request, pending.id, "confirm", pending.version),
    ]);
    for (const r of race) expect([200, 409]).toContain(r.status);
    const final = (await api.listDoctorLinks(patient.request)).body.links.find((l) => l.id === pending.id);
    expect(["active", "rejected"]).toContain(final.status);
    expect(final.version).toBe(pending.version + 1);
  });

  test("CSCW-CA-22 - after a recompute the investigation keeps its historical origin and messages", async ({ actor }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const first = seedAtypicalDays(patient.patientId, { days: 40, spikes: [10, 25] });
    const origin = first.flagged[0];
    const inv = await openInvestigationAsPatient(patient, doctor, { atypical_day_event_id: origin.indicator_id, initial_message: "sobre o dia" });

    // Recompute with more history: a new run replaces the classification.
    const second = seedAtypicalDays(patient.patientId, { days: 40, spikes: [], start: "2026-07-11" });
    expect(second.run_id).not.toBe(first.run_id);
    const latestIds = (await api.atypicalDays(patient.request, patient.patientId)).body.days.map((d) => d.indicator_id);
    expect(latestIds).not.toContain(origin.indicator_id);

    const detail = (await api.getInvestigation(patient.request, inv.id)).body;
    expect(detail.investigation.atypical_day_event_id).toBe(origin.indicator_id);
    expect(detail.messages.map((m) => m.content)).toEqual(["sobre o dia"]);
    test.info().annotations.push({
      type: "partial",
      description: "Backend preserves the historical origin; the UI does not indicate 'classificação anterior' (REVISAO-FINAL.md CSCW-CA-22 Parcial).",
    });
  });

  test("CSCW-CA-22 (UI) - the conversation shows that its origin is a previous classification after a recompute", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const first = seedAtypicalDays(patient.patientId, { days: 40, spikes: [10, 25] });
    const origin = first.flagged[0];
    const inv = await openInvestigationAsPatient(patient, doctor, { atypical_day_event_id: origin.indicator_id, initial_message: "sobre o dia" });
    // Correct the readings of the flagged day and reprocess: the new run no longer flags it.
    const second = seedAtypicalDays(patient.patientId, { days: 0, flattenDate: origin.date });
    expect(second.run_id).not.toBe(first.run_id);
    expect(second.flagged.map((item) => item.date)).not.toContain(origin.date);

    const detail = (await api.getInvestigation(patient.request, inv.id)).body;
    expect(detail.investigation.origin?.date).toBe(origin.date);
    expect(detail.investigation.origin?.is_current_classification).toBe(false);

    const [y, m, d] = origin.date.split("-");
    const ui = await conversationPage(browserSession, "patientA", inv.id);
    const originLine = ui.page.getByTestId("investigation-origin");
    await expect(originLine).toContainText(t("cscw.previousClassification"));
    await expect(originLine).toContainText(new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(new Date(Number(y), Number(m) - 1, Number(d))));
    await expect(ui.page.getByText("sobre o dia")).toBeVisible();
  });

  test("CSCW-CA-22 (UI, contract) - origin badge renders from the API `origin` field (response augmented in the browser)", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const first = seedAtypicalDays(patient.patientId, { days: 40, spikes: [10, 25] });
    const origin = first.flagged[0];
    const inv = await openInvestigationAsPatient(patient, doctor, { atypical_day_event_id: origin.indicator_id, initial_message: "sobre o dia" });

    const ui = await browserSession("patientA");
    await ui.authenticateWithApi();
    let currentClassification = false;
    const augment = (summary) => (summary.id === inv.id
      ? { ...summary, origin: { ...(summary.origin ?? { indicator_id: origin.indicator_id, date: origin.date, analysis_run_id: first.run_id }), is_current_classification: currentClassification } }
      : summary);
    await ui.context.route(/\/api\/investigations(\/[^/]+)?(\?.*)?$/, async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      if (body.investigation) body.investigation = augment(body.investigation);
      if (Array.isArray(body.investigations)) body.investigations = body.investigations.map(augment);
      await route.fulfill({ response, json: body });
    });
    const [y, m, d] = origin.date.split("-");
    const dateLabel = new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(new Date(Number(y), Number(m) - 1, Number(d)));

    // Previous classification: badge + explanation in the conversation and in the list.
    await ui.page.goto(ROUTES.investigation(inv.id));
    const originLine = ui.page.getByTestId("investigation-origin");
    await expect(originLine).toContainText(t("cscw.previousClassification"));
    await expect(originLine).toContainText(dateLabel);
    await expect(ui.page.getByText("sobre o dia")).toBeVisible();
    await ui.page.goto("/dashboard#investigations");
    await expect(ui.page.locator(".react-investigation-card").getByTestId("investigation-origin")).toContainText(t("cscw.previousClassification"));

    // Still atypical in the current analysis: dated origin, no "previous" badge.
    currentClassification = true;
    await ui.page.goto(ROUTES.investigation(inv.id));
    await expect(originLine).toHaveText(t("cscw.originAtypicalDated", "pt-BR", { date: dateLabel }));
    await expect(originLine).not.toContainText(t("cscw.previousClassification"));
  });

  test("AUT-CA-15 (secondary) - two linked doctors never share conversations", async ({ actor }) => {
    const patient = await actor("patientA");
    const doctorA = await actor("doctorA");
    const doctorB = await actor("doctorB");
    await linkActive(patient, doctorA);
    await linkActive(patient, doctorB);
    const toA = await openInvestigationAsPatient(patient, doctorA);
    const toB = await openInvestigationAsPatient(patient, doctorB);
    expect((await api.listInvestigations(doctorA.request)).body.investigations.map((i) => i.id)).toEqual([toA.id]);
    expect((await api.listInvestigations(doctorB.request)).body.investigations.map((i) => i.id)).toEqual([toB.id]);
    expect((await api.listInvestigations(patient.request)).body.investigations).toHaveLength(2);
    expect((await api.listInvestigations(doctorA.request, { counterpart_id: patient.patientId })).body.investigations.map((i) => i.id)).toEqual([toA.id]);
  });
});
