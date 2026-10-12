// Flow group 4 (PROMPT-ORCA.md, "Testes end-to-end"): revocation by each role
// with open sessions, administrative closing of open investigations, history
// preservation and a fresh acceptance cycle.
//
// Criteria: AUT-CA-14, CSCW-CA-06, CSCW-CA-07, CSCW-CA-08, CSCW-CA-09,
// CSCW-CA-10, CSCW-CA-32.
import { expect, linkActive, openInvestigationAsPatient, test } from "../fixtures/test-fixtures.mjs";
import { ROUTES } from "../fixtures/routes.mjs";
import { t, tx } from "../fixtures/i18n.mjs";
import * as api from "../fixtures/api.mjs";

test.describe("Group 4 - revocation", () => {
  test("CSCW-CA-06 - patient revokes from the UI immediately, without the doctor's confirmation", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    const link = await linkActive(patient, doctor);

    const ui = await browserSession("patientA");
    await ui.authenticateWithApi();
    await ui.page.goto(ROUTES.dashboard);
    await ui.page.getByRole("button", { name: tx("dashboard.revokeLink") }).click();
    const revoked = ui.page.waitForResponse((r) => r.url().includes(`/api/doctor-links/${link.id}/revoke`));
    await ui.page.getByRole("button", { name: tx("dashboard.revokeConfirm") }).click();
    expect((await revoked).status()).toBe(200);
    await expect(ui.page.getByText(t("dashboard.status.revoked")).first()).toBeVisible();

    const seenByDoctor = (await api.listDoctorLinks(doctor.request)).body.links.find((l) => l.id === link.id);
    expect(seenByDoctor?.status ?? "revoked").toBe("revoked");
    expect((await api.patientDetail(doctor.request, patient.patientId)).status).toBe(404);
    const doctorNotes = (await api.notifications(doctor.request)).body.notifications.map((n) => n.notification_type);
    expect(doctorNotes).toContain("association_revoked");
  });

  test("CSCW-CA-07 - doctor revokes immediately, without the patient's confirmation", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    const link = await linkActive(patient, doctor);

    const ui = await browserSession("doctorA");
    await ui.authenticateWithApi();
    await ui.page.goto(ROUTES.patientDetail(patient.patientId));
    await expect(ui.page.getByText(patient.profile.display_name).first()).toBeVisible();
    await ui.page.getByRole("button", { name: tx("dashboard.revokeLink") }).click();
    const revoked = ui.page.waitForResponse((r) => r.url().includes(`/api/doctor-links/${link.id}/revoke`));
    await ui.page.getByRole("button", { name: tx("dashboard.revokeConfirm") }).click();
    expect((await revoked).status()).toBe(200);

    const seenByPatient = (await api.listDoctorLinks(patient.request)).body.links[0];
    expect(seenByPatient.status).toBe("revoked");
    expect((await api.patientDetail(doctor.request, patient.patientId)).status).toBe(404);
    const patientNotes = (await api.notifications(patient.request)).body.notifications.map((n) => n.notification_type);
    expect(patientNotes).toContain("association_revoked");
  });

  test("AUT-CA-14 / CSCW-CA-08 - an already-open doctor session loses access right after revocation", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    const link = await linkActive(patient, doctor);
    const investigation = await openInvestigationAsPatient(patient, doctor);

    const ui = await browserSession("doctorA");
    await ui.authenticateWithApi();
    await ui.page.goto(ROUTES.patientDetail(patient.patientId));
    await expect(ui.page.getByText(patient.profile.display_name).first()).toBeVisible();

    expect((await api.revokeDoctorLink(patient.request, link.id, link.version)).status).toBe(200);

    // Same browser session, next requests: denied.
    expect((await ui.page.request.get(`/api/patients/${patient.patientId}`)).status()).toBe(404);
    expect((await ui.page.request.get(`/api/investigations/${investigation.id}`)).status()).toBe(404);
    await ui.page.reload();
    await expect(ui.page.getByText(patient.profile.display_name)).toHaveCount(0);
    // Old notifications do not restore access.
    const oldNotes = (await api.notifications(doctor.request)).body.notifications;
    const opened = oldNotes.find((n) => n.notification_type === "investigation_opened");
    expect(opened).toBeTruthy();
    expect((await api.readNotification(doctor.request, opened.id)).status).toBe(200);
    expect((await api.getInvestigation(doctor.request, investigation.id)).status).toBe(404);
    expect((await api.listInvestigations(doctor.request)).body.investigations).toHaveLength(0);
    expect((await api.postMessage(doctor.request, investigation.id, "após revogação")).status).toBe(404);
    // There is no realtime channel (polling only); the polled endpoints above are the channel.
  });

  test("CSCW-CA-09 - an investigation open on the revoked link is closed administratively, patient keeps the history", async ({ actor }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    const link = await linkActive(patient, doctor);
    const investigation = await openInvestigationAsPatient(patient, doctor, { initial_message: "histórico preservado" });
    expect((await api.postMessage(doctor.request, investigation.id, "resposta do médico")).status).toBe(201);

    expect((await api.revokeDoctorLink(doctor.request, link.id, link.version)).status).toBe(200);

    const detail = await api.getInvestigation(patient.request, investigation.id);
    expect(detail.status).toBe(200);
    expect(detail.body.investigation.status).toBe("closed");
    expect(detail.body.investigation.closed_reason).toBe("ASSOCIATION_REVOKED");
    expect(detail.body.messages.map((m) => m.content)).toEqual(["histórico preservado", "resposta do médico"]);
    expect((await api.postMessage(patient.request, investigation.id, "depois")).status).toBe(409);
  });

  test("CSCW-CA-10 - a new association requires a fresh acceptance and does not restore old conversations", async ({ actor }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    const link = await linkActive(patient, doctor);
    const old = await openInvestigationAsPatient(patient, doctor);
    expect((await api.revokeDoctorLink(patient.request, link.id, link.version)).status).toBe(200);

    const renewed = await api.createDoctorLink(patient.request, doctor.shortId);
    expect(renewed.status).toBe(201);
    expect(renewed.body.link.status).toBe("pending");
    expect(renewed.body.link.id).not.toBe(link.id);
    expect((await api.patientDetail(doctor.request, patient.patientId)).status).toBe(404);

    expect((await api.decideDoctorLink(doctor.request, renewed.body.link.id, "confirm", renewed.body.link.version)).status).toBe(200);
    expect((await api.patientDetail(doctor.request, patient.patientId)).status).toBe(200);
    // The old conversation stays closed and out of the doctor's list.
    expect((await api.listInvestigations(doctor.request)).body.investigations.map((i) => i.id)).not.toContain(old.id);
    expect((await api.getInvestigation(doctor.request, old.id)).status).toBe(404);
    expect((await api.getInvestigation(patient.request, old.id)).body.investigation.status).toBe("closed");
  });

  test("CSCW-CA-32 - a revoked doctor cannot reach provenance/history through any API", async ({ actor }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    const link = await linkActive(patient, doctor);
    await openInvestigationAsPatient(patient, doctor);
    expect((await api.revokeDoctorLink(patient.request, link.id, link.version)).status).toBe(200);

    // No provenance/history endpoint exists (REVISAO-FINAL.md A12); probe the
    // plausible paths and the clinical routes: all must deny.
    for (const path of [
      `/api/patients/${patient.patientId}/provenance`,
      `/api/patients/${patient.patientId}/history`,
      `/api/provenance?patient_id=${patient.patientId}`,
      `/api/patients/${patient.patientId}`,
      `/api/patients/${patient.patientId}/atypical-days`,
      `/api/patients/${patient.patientId}/report.pdf?start_date=2026-01-01&end_date=2026-01-31`,
    ]) {
      const res = await doctor.request.get(path);
      expect([403, 404, 405], path).toContain(res.status());
      expect(await res.text()).not.toContain(patient.profile.display_name);
    }
  });
});
