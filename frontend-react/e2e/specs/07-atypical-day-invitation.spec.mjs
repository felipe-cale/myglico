// Flow group 7 (PROMPT-ORCA.md, "Testes end-to-end"): atypical-day invitation,
// "Ver o dia" / "Agora não", explicit opening, deduplication and historical
// reprocessing.
//
// Criteria: CSCW-CA-36, CSCW-CA-37, CSCW-CA-38, CSCW-CA-45.
import { expect, linkActive, seedAtypicalDays, test } from "../fixtures/test-fixtures.mjs";
import { ROUTES } from "../fixtures/routes.mjs";
import { t, tx } from "../fixtures/i18n.mjs";
import * as api from "../fixtures/api.mjs";

function promptRegion(page) {
  return page.getByRole("region", { name: t("cscw.promptRegion") });
}

// Each invitation batch is a collapsed disclosure; its days and the
// "Agora não" action only render once it is expanded.
function batchToggles(region) {
  return region.locator("button[aria-expanded]");
}

async function expandFirstBatch(region) {
  const toggle = batchToggles(region).first();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
}

test.describe("Group 7 - atypical-day invitation", () => {
  test("CSCW-CA-36 - a newly persisted atypical day invites the patient and never opens a conversation by itself", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const seeded = seedAtypicalDays(patient.patientId);
    expect(seeded.flagged.length).toBeGreaterThan(0);

    const prompts = (await api.atypicalPrompts(patient.request, patient.patientId)).body.prompts;
    expect(prompts).toHaveLength(1);
    expect(prompts[0].indicator_ids.sort()).toEqual(seeded.flagged.map((f) => f.indicator_id).sort());
    expect(prompts[0].dates.sort()).toEqual(seeded.flagged.map((f) => f.date).sort());
    expect(prompts.every((p) => p.status === "created")).toBe(true);
    const notes = (await api.notifications(patient.request)).body.notifications.filter((n) => n.notification_type === "atypical_day_prompt");
    expect(notes.length).toBeGreaterThan(0);
    expect((await api.listInvestigations(patient.request)).body.investigations).toHaveLength(0);
    expect((await api.listInvestigations(doctor.request)).body.investigations).toHaveLength(0);
    // Doctor gets nothing about the invitation.
    expect((await api.notifications(doctor.request)).body.notifications.some((n) => n.notification_type === "atypical_day_prompt")).toBe(false);

    const ui = await browserSession("patientA");
    await ui.authenticateWithApi();
    await ui.page.goto(ROUTES.dashboard);
    const region = promptRegion(ui.page);
    await expect(region).toBeVisible();
    await expandFirstBatch(region);
    await expect(region.getByRole("button", { name: tx("cscw.defer") }).first()).toBeVisible();
    // The historical date (2026-06/07) is shown, not "today".
    await expect(region).toContainText(/2026/);
  });

  test("CSCW-CA-37 - 'Agora não' defers without repeating on refresh and manual opening stays available", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    seedAtypicalDays(patient.patientId);

    const ui = await browserSession("patientA");
    await ui.authenticateWithApi();
    await ui.page.goto(ROUTES.dashboard);
    const region = promptRegion(ui.page);
    const batches = batchToggles(region);
    await expect(batches.first()).toBeVisible();
    const before = await batches.count();
    await expandFirstBatch(region);
    const deferButton = region.getByRole("button", { name: tx("cscw.defer") });
    const deferred = ui.page.waitForResponse((r) => r.url().endsWith("/api/atypical-day-prompts/defer"));
    await deferButton.first().click();
    const response = await deferred;
    expect(response.status()).toBe(200);
    const deferredPrompts = (await response.json()).prompts;
    expect(deferredPrompts.length).toBeGreaterThan(0);
    expect(deferredPrompts.every((p) => p.status === "deferred")).toBe(true);
    const deferredId = deferredPrompts[0].indicator_id;
    await expect(batches).toHaveCount(before - 1);

    // Wait for the prompts to be fetched again so an empty region is a real
    // answer and not just the page before the data arrived.
    const reloadedPrompts = ui.page.waitForResponse((r) => r.request().method() === "GET"
      && new URL(r.url()).pathname === `/api/patients/${patient.patientId}/atypical-day-prompts`);
    await ui.page.reload();
    expect((await reloadedPrompts).status()).toBe(200);
    await expect(ui.page.getByRole("heading").first()).toBeVisible();
    await expect(batches).toHaveCount(before - 1);

    const prompts = (await api.atypicalPrompts(patient.request, patient.patientId)).body.prompts;
    // Since the server-side pagination (ebb0a01) the listing only returns
    // pending ("created") invitations, so a persisted deferral is one that is
    // no longer listed.
    expect(prompts.every((p) => p.status === "created")).toBe(true);
    const stillListed = prompts.flatMap((p) => p.indicator_ids);
    expect(deferredPrompts.filter((p) => stillListed.includes(p.indicator_id))).toEqual([]);
    // Deferring twice is idempotent.
    expect((await api.deferAtypicalPrompt(patient.request, deferredId)).body.prompt.status).toBe("deferred");
    // Manual opening for the deferred day is still possible.
    const opened = await api.createInvestigation(patient.request, {
      doctor_id: doctor.doctorId, atypical_day_event_id: deferredId, title: "Depois", initial_message: "Abrindo depois",
    });
    expect(opened.status).toBe(201);
    // Another patient cannot defer this patient's prompt.
    const other = await actor("patientB");
    const stillCreated = prompts.find((p) => p.status === "created");
    if (stillCreated) {
      expect([403, 404]).toContain((await api.deferAtypicalPrompt(other.request, stillCreated.indicator_ids[0])).status);
    }
  });

  test("CSCW-CA-38 - accepting the invitation with several doctors forces an explicit choice and notifies only the chosen one", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctorA = await actor("doctorA");
    const doctorB = await actor("doctorB");
    await linkActive(patient, doctorA);
    await linkActive(patient, doctorB);
    seedAtypicalDays(patient.patientId);
    const before = {
      a: (await api.notifications(doctorA.request)).body.notifications.length,
      b: (await api.notifications(doctorB.request)).body.notifications.length,
    };

    const ui = await browserSession("patientA");
    await ui.authenticateWithApi();
    await ui.page.goto(ROUTES.dashboard);
    const region = promptRegion(ui.page);
    await expandFirstBatch(region);
    await region.getByRole("button", { name: tx("cscw.openPatient") }).first().click();
    await expect(ui.page).toHaveURL(/atypical_day_event_id=/);
    const eventId = new URL(ui.page.url()).searchParams.get("atypical_day_event_id");
    // Nobody is notified merely by opening the form.
    expect((await api.notifications(doctorA.request)).body.notifications.length).toBe(before.a);

    const select = ui.page.getByLabel(t("cscw.association"));
    await expect(select).toHaveValue("");
    await select.selectOption({ label: doctorB.profile.display_name });
    await ui.page.getByLabel(t("cscw.subject")).fill("Convite aceito");
    await ui.page.getByLabel(t("cscw.message")).fill("Sobre o dia do convite");
    const created = ui.page.waitForResponse((r) => r.url().endsWith("/api/investigations") && r.request().method() === "POST");
    await ui.page.locator("form").filter({ has: ui.page.getByLabel(t("cscw.subject")) }).getByRole("button", { name: tx("cscw.send") }).click();
    const investigation = (await (await created).json()).investigation;
    expect(investigation.atypical_day_event_id).toBe(eventId);
    expect(investigation.doctor_id).toBe(doctorB.doctorId);

    const notesB = (await api.notifications(doctorB.request)).body.notifications;
    expect(notesB.length).toBe(before.b + 1);
    expect(notesB.some((n) => n.notification_type === "investigation_opened" && n.payload.investigation_id === investigation.id)).toBe(true);
    expect((await api.notifications(doctorA.request)).body.notifications.length).toBe(before.a);
  });

  test("CSCW-CA-45 - reprocessing yields one consolidated, deduplicated notice with real historical dates", async ({ actor }) => {
    // The real UCI download is network-bound and slow; it is covered by
    // scripts/import_uci_diabetes.py + tests/integration. Here the same
    // analytics writer is exercised with a multi-day history and reprocessed.
    const patient = await actor("patientA");
    const first = seedAtypicalDays(patient.patientId, { days: 60, spikes: [5, 20, 40] });
    expect(first.flagged.length).toBeGreaterThan(1);
    const notesAfterFirst = (await api.notifications(patient.request)).body.notifications.filter((n) => n.notification_type === "atypical_day_prompt");
    expect(notesAfterFirst).toHaveLength(1);
    const payload = notesAfterFirst[0].payload;
    expect(payload.count).toBe(first.flagged.length);
    expect([...payload.dates].sort()).toEqual(first.flagged.map((f) => f.date).sort());

    // Reprocess the very same history: no new prompts, no new notification.
    const promptsBefore = (await api.atypicalPrompts(patient.request, patient.patientId)).body.prompts;
    seedAtypicalDays(patient.patientId, { days: 0, spikes: [] });
    const promptsAfter = (await api.atypicalPrompts(patient.request, patient.patientId)).body.prompts;
    expect(promptsAfter.length).toBe(promptsBefore.length);
    expect(promptsAfter).toHaveLength(1);
    expect(promptsAfter[0].indicator_ids).toHaveLength(first.flagged.length);
    const notesAfterSecond = (await api.notifications(patient.request)).body.notifications.filter((n) => n.notification_type === "atypical_day_prompt");
    expect(notesAfterSecond).toHaveLength(1);
    for (const promptDate of promptsAfter[0].dates) expect(promptDate.startsWith("2026-0")).toBe(true);
  });
});
