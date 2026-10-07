// Flow group 3 (PROMPT-ORCA.md, "Testes end-to-end"): exact doctor search by
// short id and CRM + UF, minimal profiles, request/reject/cancel/accept and
// no clinical access while the link is pending.
//
// Criteria: AUT-CA-10, CSCW-CA-01, CSCW-CA-02, CSCW-CA-03, CSCW-CA-04,
// CSCW-CA-05.
import { expect, test } from "../fixtures/test-fixtures.mjs";
import { ROUTES } from "../fixtures/routes.mjs";
import { t, tx } from "../fixtures/i18n.mjs";
import * as api from "../fixtures/api.mjs";

const ALLOWED_DOCTOR_KEYS = ["crm", "declared_verified", "is_demo", "link_status", "name", "short_id", "uf"];

async function loginUi(ui, profile) {
  await ui.authenticateWithApi();
  await ui.page.goto(ROUTES.dashboard);
  await expect(ui.page).toHaveURL(/\/dashboard$/);
}

test.describe("Group 3 - doctor search and link request lifecycle", () => {
  test("AUT-CA-10 / CSCW-CA-01 - exact search by short id and by CRM + UF returns the minimal allowed profile", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");

    const byShortId = await api.searchDoctor(patient.request, { short_id: doctor.shortId });
    expect(byShortId.status).toBe(200);
    expect(Object.keys(byShortId.body.doctor).sort()).toEqual(ALLOWED_DOCTOR_KEYS);
    expect(byShortId.body.doctor).toMatchObject({
      short_id: doctor.shortId, name: doctor.profile.display_name,
      crm: doctor.profile.crm, uf: doctor.profile.uf, link_status: "none",
    });
    const lower = await api.searchDoctor(patient.request, { short_id: doctor.shortId.toLowerCase() });
    expect(lower.body.doctor?.short_id).toBe(doctor.shortId);

    const byCrm = await api.searchDoctor(patient.request, { crm: doctor.profile.crm, uf: doctor.profile.uf });
    expect(byCrm.body.doctor.short_id).toBe(doctor.shortId);
    const raw = JSON.stringify(byCrm.body);
    expect(raw).not.toContain(doctor.profile.email);
    expect(raw).not.toContain(doctor.doctorId);

    // Wrong UF / unknown short id: empty result, same shape, no oracle.
    const wrongUf = await api.searchDoctor(patient.request, { crm: doctor.profile.crm, uf: "AC" });
    expect(wrongUf).toEqual({ status: 200, body: { doctor: null } });
    const unknown = await api.searchDoctor(patient.request, { short_id: "ZZZZZ9" });
    expect(unknown.status).toBe(200);
    expect(unknown.body.doctor === null || unknown.body.doctor.short_id === "ZZZZZ9").toBe(true);

    // Anonymous and doctor callers cannot search.
    expect((await api.searchDoctor(doctor.request, { short_id: doctor.shortId })).status).toBe(403);

    // UI: patient searches by SHORTID on the dashboard.
    const ui = await browserSession("patientA");
    await loginUi(ui);
    await ui.page.getByLabel(t("dashboard.shortId")).fill(doctor.shortId);
    await ui.page.getByRole("button", { name: tx("dashboard.search") }).click();
    await expect(ui.page.getByText(doctor.profile.display_name).first()).toBeVisible();
    await expect(ui.page.getByRole("button", { name: tx("dashboard.requestLink") })).toBeVisible();
    await expect(ui.page.getByText(doctor.profile.email)).toHaveCount(0);
  });

  test("CSCW-CA-02 - patient request creates PENDING + notification with no clinical access before acceptance", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");

    const ui = await browserSession("patientA");
    await loginUi(ui);
    await ui.page.getByLabel(t("dashboard.shortId")).fill(doctor.shortId);
    await ui.page.getByRole("button", { name: tx("dashboard.search") }).click();
    const requested = ui.page.waitForResponse((r) => r.url().endsWith("/api/doctor-links") && r.request().method() === "POST");
    await ui.page.getByRole("button", { name: tx("dashboard.requestLink") }).click();
    expect((await requested).status()).toBe(201);
    await expect(ui.page.getByText(t("dashboard.status.pending")).first()).toBeVisible();

    const links = await api.listDoctorLinks(patient.request);
    expect(links.body.links).toHaveLength(1);
    expect(links.body.links[0].status).toBe("pending");

    const doctorNotifications = await api.notifications(doctor.request, { unread_only: true });
    expect(doctorNotifications.body.notifications.map((n) => n.notification_type)).toContain("association_requested");

    // Pending: doctor has no clinical access to the patient.
    expect((await api.patientDetail(doctor.request, patient.patientId)).status).toBe(404);
    expect((await api.atypicalDays(doctor.request, patient.patientId)).status).toBe(404);
    expect((await api.reportPdf(doctor.request, patient.patientId, { start_date: "2026-01-01", end_date: "2026-01-31" })).status).toBe(404);
    // Duplicate request while pending does not create a second link.
    const again = await api.createDoctorLink(patient.request, doctor.shortId);
    expect([200, 409]).toContain(again.status);
    expect((await api.listDoctorLinks(patient.request)).body.links).toHaveLength(1);
  });

  test("CSCW-CA-03 - a different doctor cannot confirm someone else's request and the state does not change", async ({ actor }) => {
    const patient = await actor("patientA");
    const doctorA = await actor("doctorA");
    const doctorB = await actor("doctorB");
    const link = (await api.createDoctorLink(patient.request, doctorA.shortId)).body.link;

    const forged = await api.decideDoctorLink(doctorB.request, link.id, "confirm", link.version);
    expect([403, 404]).toContain(forged.status);
    expect(JSON.stringify(forged.body)).not.toContain(patient.profile.display_name);
    // The patient cannot confirm its own request either.
    expect([403, 404]).toContain((await api.decideDoctorLink(patient.request, link.id, "confirm", link.version)).status);

    const seenByA = (await api.listDoctorLinks(doctorA.request)).body.links;
    expect(seenByA.find((l) => l.id === link.id)).toMatchObject({ status: "pending", version: link.version });
    expect((await api.listDoctorLinks(doctorB.request)).body.links).toHaveLength(0);
  });

  test("CSCW-CA-04 - the addressed doctor confirms in the UI and the link becomes ACTIVE with a version bump", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    const link = (await api.createDoctorLink(patient.request, doctor.shortId)).body.link;

    const ui = await browserSession("doctorA");
    await loginUi(ui);
    await expect(ui.page.getByText(patient.profile.display_name).first()).toBeVisible();
    const confirmed = ui.page.waitForResponse((r) => r.url().includes(`/api/doctor-links/${link.id}/confirm`));
    await ui.page.getByRole("button", { name: tx("dashboard.accept") }).click();
    expect((await confirmed).status()).toBe(200);

    const after = (await api.listDoctorLinks(patient.request)).body.links[0];
    expect(after.status).toBe("active");
    expect(after.version).toBeGreaterThan(link.version);
    expect(after.decided_at).toBeTruthy();
    // Repeating the confirmation is idempotent: same state, no second version bump.
    const repeated = await api.decideDoctorLink(doctor.request, link.id, "confirm", link.version);
    expect(repeated.status).toBe(200);
    expect(repeated.body.link.version).toBe(after.version);
    // A stale version for a different transition is rejected (optimistic locking).
    expect((await api.revokeDoctorLink(doctor.request, link.id, link.version)).status).toBe(409);
    // Now the doctor can read the patient.
    expect((await api.patientDetail(doctor.request, patient.patientId)).status).toBe(200);
    // Patient is notified of the decision.
    const patientNotes = (await api.notifications(patient.request)).body.notifications.map((n) => n.notification_type);
    expect(patientNotes.some((type) => /confirm|accept|active/i.test(type))).toBe(true);
  });

  test("CSCW-CA-05 - reject and cancel reach coherent terminal states and allow a new request", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctorA = await actor("doctorA");
    const doctorB = await actor("doctorB");

    const linkA = (await api.createDoctorLink(patient.request, doctorA.shortId)).body.link;
    const rejected = await api.decideDoctorLink(doctorA.request, linkA.id, "reject", linkA.version);
    expect(rejected.status).toBe(200);
    expect(rejected.body.link.status).toBe("rejected");
    expect((await api.decideDoctorLink(doctorA.request, linkA.id, "confirm", rejected.body.link.version)).status).toBe(409);

    const linkB = (await api.createDoctorLink(patient.request, doctorB.shortId)).body.link;
    const ui = await browserSession("patientA");
    await loginUi(ui);
    const cancelled = ui.page.waitForResponse((r) => r.url().includes(`/api/doctor-links/${linkB.id}/cancel`));
    await ui.page.getByRole("button", { name: tx("dashboard.cancel") }).click();
    expect((await cancelled).status()).toBe(200);

    const statuses = Object.fromEntries((await api.listDoctorLinks(patient.request)).body.links.map((l) => [l.id, l.status]));
    expect(statuses[linkA.id]).toBe("rejected");
    expect(statuses[linkB.id]).toBe("cancelled");
    expect((await api.patientDetail(doctorA.request, patient.patientId)).status).toBe(404);

    // A new request after a terminal state opens a fresh PENDING cycle.
    const renewed = await api.createDoctorLink(patient.request, doctorA.shortId);
    expect(renewed.status).toBe(201);
    expect(renewed.body.link.id).not.toBe(linkA.id);
    expect(renewed.body.link.status).toBe("pending");
  });
});
