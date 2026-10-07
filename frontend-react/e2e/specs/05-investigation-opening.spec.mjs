// Flow group 5 (PROMPT-ORCA.md, "Testes end-to-end"): opening an investigation
// by each role, with and without an atypical-day event, recipient selection,
// no active doctor, foreign events and cross-patient isolation.
//
// Criteria: CSCW-CA-13, CSCW-CA-14, CSCW-CA-15, CSCW-CA-16, CSCW-CA-17,
// AUT-CA-12, AUT-CA-13, AUT-CA-15.
import { expect, linkActive, openInvestigationAsPatient, seedAtypicalDays, test } from "../fixtures/test-fixtures.mjs";
import { ROUTES } from "../fixtures/routes.mjs";
import { t, tx } from "../fixtures/i18n.mjs";
import * as api from "../fixtures/api.mjs";

const RANGE = { start_date: "2026-06-01", end_date: "2026-07-31" };

test.describe("Group 5 - investigation opening and isolation", () => {
  test("CSCW-CA-13 - patient opens from an atypical-day invitation in the UI; origin, doctor and first message persist", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const seeded = seedAtypicalDays(patient.patientId);
    expect(seeded.flagged.length).toBeGreaterThan(0);
    const target = seeded.flagged[0];

    const ui = await browserSession("patientA");
    await ui.authenticateWithApi();
    await ui.page.goto(`${ROUTES.dashboard}?atypical_day_event_id=${target.indicator_id}`);
    await ui.page.getByLabel(t("cscw.association")).selectOption({ label: doctor.profile.display_name });
    await ui.page.getByLabel(t("cscw.subject")).fill("Dia atípico E2E");
    await ui.page.getByLabel(t("cscw.message")).fill("Primeira mensagem sobre o dia atípico");
    const created = ui.page.waitForResponse((r) => r.url().endsWith("/api/investigations") && r.request().method() === "POST");
    await ui.page.locator("form").filter({ has: ui.page.getByLabel(t("cscw.subject")) }).getByRole("button", { name: tx("cscw.send") }).click();
    const response = await created;
    expect(response.status()).toBe(201);
    const investigation = (await response.json()).investigation;
    await expect(ui.page).toHaveURL(new RegExp(`/investigations/${investigation.id}$`));
    await expect(ui.page.getByText("Primeira mensagem sobre o dia atípico")).toBeVisible();

    expect(investigation.atypical_day_event_id).toBe(target.indicator_id);
    expect(investigation.doctor_id).toBe(doctor.doctorId);
    expect(investigation.opened_by_role).toBe("patient");
    expect(investigation.awaiting_role).toBe("doctor");
    const days = (await api.atypicalDays(patient.request, patient.patientId, RANGE)).body.days;
    expect(days.find((d) => d.indicator_id === target.indicator_id)?.has_investigation).toBe(true);
    const doctorNotes = (await api.notifications(doctor.request)).body.notifications.map((n) => n.notification_type);
    expect(doctorNotes).toContain("investigation_opened");
  });

  test("CSCW-CA-14 - patient opens without an atypical day: origin is null and no artificial event is created", async ({ actor }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const investigation = await openInvestigationAsPatient(patient, doctor);
    expect(investigation.atypical_day_event_id).toBeNull();
    expect((await api.atypicalDays(patient.request, patient.patientId)).body.days).toEqual([]);
    expect((await api.atypicalPrompts(patient.request, patient.patientId)).body.prompts).toEqual([]);
  });

  test("CSCW-CA-15 - doctor opens with or without an event, only for ACTIVE links", async ({ actor }) => {
    const patient = await actor("patientA");
    const other = await actor("patientB");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const seeded = seedAtypicalDays(patient.patientId);

    const plain = await api.createInvestigation(doctor.request, { patient_id: patient.patientId, title: "Sem evento", initial_message: "Olá" });
    expect(plain.status).toBe(201);
    expect(plain.body.investigation.opened_by_role).toBe("doctor");
    expect(plain.body.investigation.awaiting_role).toBe("patient");
    const withEvent = await api.createInvestigation(doctor.request, {
      patient_id: patient.patientId, atypical_day_event_id: seeded.flagged[0].indicator_id, title: "Com evento", initial_message: "Vi o dia",
    });
    expect(withEvent.status).toBe(201);
    expect(withEvent.body.investigation.atypical_day_event_id).toBe(seeded.flagged[0].indicator_id);

    // Unlinked patient, and a doctor trying to impersonate the patient role.
    expect((await api.createInvestigation(doctor.request, { patient_id: other.patientId, title: "x", initial_message: "x" })).status).toBe(404);
    expect((await api.createInvestigation(doctor.request, { doctor_id: doctor.doctorId, title: "x", initial_message: "x" })).status).toBe(400);
    // Patient without any ACTIVE doctor cannot open.
    expect((await api.createInvestigation(other.request, { doctor_id: doctor.doctorId, title: "x", initial_message: "x" })).status).toBe(404);
  });

  test("CSCW-CA-16 - an event belonging to another patient is refused without data leakage", async ({ actor }) => {
    const patientA = await actor("patientA");
    const patientB = await actor("patientB");
    const doctor = await actor("doctorA");
    await linkActive(patientA, doctor);
    const seededB = seedAtypicalDays(patientB.patientId);
    const foreign = seededB.flagged[0].indicator_id;

    const res = await api.createInvestigation(patientA.request, {
      doctor_id: doctor.doctorId, atypical_day_event_id: foreign, title: "x", initial_message: "x",
    });
    expect(res.status).toBe(404);
    const raw = JSON.stringify(res.body);
    expect(raw).not.toContain(seededB.flagged[0].date);
    expect(raw).not.toContain(patientB.patientId);
    // A non-atypical / unknown event id is refused the same way.
    const unknown = await api.createInvestigation(patientA.request, {
      doctor_id: doctor.doctorId, atypical_day_event_id: "00000000-0000-0000-0000-000000000000", title: "x", initial_message: "x",
    });
    expect(unknown.status).toBe(404);
    expect(unknown.body).toEqual(res.body);
    expect((await api.listInvestigations(patientA.request)).body.investigations).toHaveLength(0);
  });

  test("CSCW-CA-17 - with several doctors the recipient choice is explicit in the UI and conversations stay isolated", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctorA = await actor("doctorA");
    const doctorB = await actor("doctorB");
    await linkActive(patient, doctorA);
    await linkActive(patient, doctorB);

    const ui = await browserSession("patientA");
    await ui.authenticateWithApi();
    await ui.page.goto(ROUTES.dashboard);
    await ui.page.getByRole("button", { name: tx("cscw.new") }).click();
    const select = ui.page.getByLabel(t("cscw.association"));
    // No implicit default: placeholder first, both doctors offered.
    await expect(select).toHaveValue("");
    await expect(select.locator("option")).toHaveCount(3);
    await expect(select.locator("option").first()).toHaveText(t("cscw.selectAssociation"));
    const optionTexts = await select.locator("option").allInnerTexts();
    expect(optionTexts).toEqual(expect.arrayContaining([doctorA.profile.display_name, doctorB.profile.display_name]));
    await select.selectOption({ label: doctorB.profile.display_name });
    await ui.page.getByLabel(t("cscw.subject")).fill("Só para o médico B");
    await ui.page.getByLabel(t("cscw.message")).fill("Conteúdo restrito ao B");
    const created = ui.page.waitForResponse((r) => r.url().endsWith("/api/investigations") && r.request().method() === "POST");
    await ui.page.locator("form").filter({ has: ui.page.getByLabel(t("cscw.subject")) }).getByRole("button", { name: tx("cscw.send") }).click();
    const investigation = (await (await created).json()).investigation;
    expect(investigation.doctor_id).toBe(doctorB.doctorId);

    expect((await api.listInvestigations(doctorB.request)).body.investigations.map((i) => i.id)).toEqual([investigation.id]);
    expect((await api.listInvestigations(doctorA.request)).body.investigations).toHaveLength(0);
    expect((await api.getInvestigation(doctorA.request, investigation.id)).status).toBe(404);
  });

  test("AUT-CA-15 - a conversation directed to one doctor is not visible to the other linked doctor", async ({ actor }) => {
    const patient = await actor("patientA");
    const doctorA = await actor("doctorA");
    const doctorB = await actor("doctorB");
    await linkActive(patient, doctorA);
    await linkActive(patient, doctorB);
    const toA = await openInvestigationAsPatient(patient, doctorA, { initial_message: "segredo para A" });

    const probe = await api.getInvestigation(doctorB.request, toA.id);
    expect(probe.status).toBe(404);
    expect(JSON.stringify(probe.body)).not.toContain("segredo para A");
    expect((await api.postMessage(doctorB.request, toA.id, "intrusão")).status).toBe(404);
    expect((await api.readMessages(doctorB.request, toA.id, 1)).status).toBe(404);
    expect((await api.closeInvestigation(doctorB.request, toA.id, { version: 1 })).status).toBe(404);
    expect((await api.unreadSummary(doctorB.request)).body.messages_unread).toBe(0);
    expect((await api.unreadSummary(doctorA.request)).body.messages_unread).toBe(1);
  });

  test("AUT-CA-12 - patient A cannot read patient B's resources by changing URL/IDs", async ({ actor, browserSession }) => {
    const patientA = await actor("patientA");
    const patientB = await actor("patientB");
    const doctor = await actor("doctorA");
    await linkActive(patientB, doctor);
    const invB = await openInvestigationAsPatient(patientB, doctor, { initial_message: "dados do B" });
    expect((await api.addGlucoseRecord(patientB.request, patientB.patientId, { measured_at: "2026-06-01T08:00:00", glucose_mg_dl: 123 })).status).toBe(201);

    const id = patientB.patientId;
    const probes = [
      await api.patientDetail(patientA.request, id),
      await api.atypicalDays(patientA.request, id),
      await api.atypicalPrompts(patientA.request, id),
      await api.reportPdf(patientA.request, id, { start_date: "2026-06-01", end_date: "2026-06-30" }),
      await api.addGlucoseRecord(patientA.request, id, { measured_at: "2026-06-02T08:00:00", glucose_mg_dl: 99 }),
      await api.getInvestigation(patientA.request, invB.id),
      await api.postMessage(patientA.request, invB.id, "x"),
    ];
    for (const probe of probes) {
      expect([403, 404]).toContain(probe.status);
      expect(String(probe.body ? JSON.stringify(probe.body) : "")).not.toContain("dados do B");
    }
    // UI: typing B's URL shows no B data.
    const ui = await browserSession("patientA");
    await ui.authenticateWithApi();
    await ui.page.goto(ROUTES.patientDetail(id));
    await expect(ui.page.getByText(patientB.profile.display_name)).toHaveCount(0);
    await ui.page.goto(ROUTES.investigation(invB.id));
    await expect(ui.page.getByText("dados do B")).toHaveCount(0);
  });

  test("AUT-CA-13 - a doctor without an active link cannot read the patient", async ({ actor }) => {
    const patient = await actor("patientA");
    const doctorA = await actor("doctorA");
    const doctorB = await actor("doctorB");
    await linkActive(patient, doctorA);
    seedAtypicalDays(patient.patientId);

    expect((await api.patientDetail(doctorA.request, patient.patientId, RANGE)).status).toBe(200);
    for (const probe of [
      await api.patientDetail(doctorB.request, patient.patientId, RANGE),
      await api.atypicalDays(doctorB.request, patient.patientId, RANGE),
      await api.reportPdf(doctorB.request, patient.patientId, RANGE),
      await api.addGlucoseRecord(doctorB.request, patient.patientId, { measured_at: "2026-06-02T08:00:00", glucose_mg_dl: 99 }),
    ]) {
      expect(probe.status).toBe(404);
    }
    const listAll = await doctorB.request.get("/api/patients");
    expect([200, 403]).toContain(listAll.status());
    if (listAll.status() === 200) expect(await listAll.text()).not.toContain(patient.patientId);
  });
});
