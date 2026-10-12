// Flow group 8 (PROMPT-ORCA.md, "Testes end-to-end"): notifications and unread
// messages in both directions, persistence across logins, effective reading,
// pagination and failure/recovery of the polling channel.
//
// Criteria: CSCW-CA-19, CSCW-CA-29, CSCW-CA-39, CSCW-CA-40, CSCW-CA-41,
// CSCW-CA-42, CSCW-CA-43, CSCW-CA-44.
import { expect, linkActive, openInvestigationAsPatient, test } from "../fixtures/test-fixtures.mjs";
import { ROUTES } from "../fixtures/routes.mjs";
import { t, tx } from "../fixtures/i18n.mjs";
import * as api from "../fixtures/api.mjs";

function messagesMenu(page, count) {
  return page.getByRole("link", { name: t("cscw.menuAria", "pt-BR", { count }) });
}

async function pair(actor) {
  const patient = await actor("patientA");
  const doctor = await actor("doctorA");
  await linkActive(patient, doctor);
  return { patient, doctor };
}

test.describe("Group 8 - notifications and unread counters", () => {
  test("CSCW-CA-39 - doctor sends, patient never opens: notification and unread counter survive a new login", async ({ actor, browserSession }) => {
    const { patient, doctor } = await pair(actor);
    const inv = await api.createInvestigation(doctor.request, { patient_id: patient.patientId, title: "Do médico", initial_message: "msg 1" });
    expect(inv.status).toBe(201);
    expect((await api.postMessage(doctor.request, inv.body.investigation.id, "msg 2")).status).toBe(201);

    expect((await patient.logout()).status).toBe(204);
    expect((await patient.login()).status).toBe(200);
    const summary = (await api.unreadSummary(patient.request)).body;
    expect(summary.messages_unread).toBe(2);
    expect(summary.notifications_unread).toBeGreaterThanOrEqual(2);
    const types = (await api.notifications(patient.request, { unread_only: true })).body.notifications.map((n) => n.notification_type);
    expect(types).toEqual(expect.arrayContaining(["investigation_opened", "investigation_message_added"]));

    const ui = await browserSession("patientA");
    await ui.authenticateWithApi();
    await ui.page.goto(ROUTES.dashboard);
    await expect(messagesMenu(ui.page, 2)).toBeVisible();
  });

  test("CSCW-CA-40 - patient sends, doctor sees the symmetric notification and counter", async ({ actor, browserSession }) => {
    const { patient, doctor } = await pair(actor);
    const inv = await openInvestigationAsPatient(patient, doctor, { initial_message: "p1" });
    expect((await api.postMessage(patient.request, inv.id, "p2")).status).toBe(201);
    expect((await api.postMessage(patient.request, inv.id, "p3")).status).toBe(201);
    const summary = (await api.unreadSummary(doctor.request)).body;
    expect(summary.messages_unread).toBe(3);
    expect(summary.notifications_unread).toBeGreaterThanOrEqual(3);
    expect((await api.unreadSummary(patient.request)).body.messages_unread).toBe(0);

    const ui = await browserSession("doctorA");
    await ui.authenticateWithApi();
    await ui.page.goto(ROUTES.dashboard);
    await expect(messagesMenu(ui.page, 3)).toBeVisible();
  });

  test("CSCW-CA-41 - reading only the notification or opening the listing does not clear the message counter", async ({ actor, browserSession }) => {
    const { patient, doctor } = await pair(actor);
    const inv = await openInvestigationAsPatient(patient, doctor);
    const notes = (await api.notifications(doctor.request, { unread_only: true })).body.notifications;
    for (const n of notes) expect((await api.readNotification(doctor.request, n.id)).status).toBe(200);
    let summary = (await api.unreadSummary(doctor.request)).body;
    expect(summary.notifications_unread).toBe(0);
    expect(summary.messages_unread).toBe(1);

    expect((await api.listInvestigations(doctor.request)).status).toBe(200);
    const ui = await browserSession("doctorA");
    await ui.authenticateWithApi();
    await ui.page.goto(ROUTES.dashboard);
    await expect(ui.page.getByText(inv.title).first()).toBeVisible();
    summary = (await api.unreadSummary(doctor.request)).body;
    expect(summary.messages_unread).toBe(1);
    // Opening the notification bell (UI) also does not mark messages read.
    await ui.page.getByRole("button", { name: t("notifications.title") }).click();
    expect((await api.unreadSummary(doctor.request)).body.messages_unread).toBe(1);
  });

  test("CSCW-CA-42 - messages on pages that were not rendered are not marked as read", async ({ actor, browserSession }) => {
    const { patient, doctor } = await pair(actor);
    const inv = await openInvestigationAsPatient(patient, doctor, { initial_message: "m1" });
    for (let i = 2; i <= 60; i += 1) {
      expect((await api.postMessage(patient.request, inv.id, `m${i}`)).status).toBe(201);
    }
    expect((await api.unreadSummary(doctor.request)).body.messages_unread).toBe(60);
    // Server refuses a marker beyond what exists.
    expect([400, 409]).toContain((await api.readMessages(doctor.request, inv.id, 61)).status);

    const ui = await browserSession("doctorA");
    await ui.authenticateWithApi();
    const read = ui.page.waitForResponse((r) => r.url().endsWith(`/api/investigations/${inv.id}/read`));
    await ui.page.goto(ROUTES.investigation(inv.id));
    // The conversation opens at the first unread page (10 messages) and marks only what it shows.
    const readBody = (await read).request().postDataJSON();
    expect(readBody.up_to_sequence).toBe(10);
    await expect.poll(async () => (await api.unreadSummary(doctor.request)).body.messages_unread).toBe(50);
    await expect(ui.page.getByText("m10", { exact: true })).toBeVisible();
    await expect(ui.page.getByText("m11", { exact: true })).toHaveCount(0);
    await expect(ui.page.getByText("m60", { exact: true })).toHaveCount(0);

    // Reaching the next page displays it and advances the marker by exactly that page.
    const nextRead = ui.page.waitForResponse((r) => r.url().endsWith(`/api/investigations/${inv.id}/read`));
    await ui.page.getByRole("button", { name: tx("pagination.next") }).click();
    await expect(ui.page.getByText("m20", { exact: true })).toBeVisible();
    expect((await nextRead).request().postDataJSON().up_to_sequence).toBe(20);
    await expect.poll(async () => (await api.unreadSummary(doctor.request)).body.messages_unread).toBe(40);

    // Jumping ahead to page 5 shows m41-m50 but cannot mark the unseen m21-m40 as read.
    await ui.page.getByRole("button", { name: t("pagination.page", "pt-BR", { page: 5 }), exact: true }).click();
    await expect(ui.page.getByText("m50", { exact: true })).toBeVisible();
    await ui.page.waitForTimeout(1500);
    expect((await api.unreadSummary(doctor.request)).body.messages_unread).toBe(40);
  });

  test("CSCW-CA-43 - an effectively displayed message advances the marker and updates the counter once", async ({ actor, browserSession }) => {
    const { patient, doctor } = await pair(actor);
    const inv = await openInvestigationAsPatient(patient, doctor, { initial_message: "visível" });
    expect((await api.unreadSummary(doctor.request)).body.messages_unread).toBe(1);

    const ui = await browserSession("doctorA");
    await ui.authenticateWithApi();
    const read = ui.page.waitForResponse((r) => r.url().endsWith(`/api/investigations/${inv.id}/read`));
    await ui.page.goto(ROUTES.investigation(inv.id));
    await expect(ui.page.getByText("visível")).toBeVisible();
    const response = await read;
    expect((await response.json()).last_read_sequence).toBe(1);
    await expect.poll(async () => (await api.unreadSummary(doctor.request)).body.messages_unread).toBe(0);
    expect((await api.getInvestigation(doctor.request, inv.id)).body.unread_count).toBe(0);
    // Provenance de-duplication (single InvestigationMessagesRead per advance)
    // is asserted in tests/integration/test_outbox_and_delivery.py.
  });

  test("CSCW-CA-19 - repeated effective reads advance the marker monotonically without regressions", async ({ actor }) => {
    const { patient, doctor } = await pair(actor);
    const inv = await openInvestigationAsPatient(patient, doctor);
    expect((await api.postMessage(patient.request, inv.id, "segunda")).status).toBe(201);
    const first = await api.readMessages(doctor.request, inv.id, 2);
    expect(first.body.last_read_sequence).toBe(2);
    const repeated = await api.readMessages(doctor.request, inv.id, 2);
    expect(repeated.body.last_read_sequence).toBe(2);
    const backwards = await api.readMessages(doctor.request, inv.id, 1);
    expect(backwards.status).toBe(200);
    expect(backwards.body.last_read_sequence).toBe(2);
    expect((await api.unreadSummary(doctor.request)).body.messages_unread).toBe(0);
  });

  test("CSCW-CA-44 - a failing polling channel recovers notices and counters from persistence", async ({ actor, browserSession }) => {
    const { patient, doctor } = await pair(actor);
    const ui = await browserSession("doctorA");
    await ui.authenticateWithApi();
    // Fault injection: the notification channel is down while messages arrive.
    await ui.context.route("**/api/notifications/**", (route) => route.abort("connectionfailed"));
    await ui.page.goto(ROUTES.dashboard);
    const inv = await openInvestigationAsPatient(patient, doctor);
    expect((await api.postMessage(patient.request, inv.id, "durante a falha")).status).toBe(201);
    await expect(messagesMenu(ui.page, 2)).toHaveCount(0);

    await ui.context.unroute("**/api/notifications/**");
    await ui.page.reload();
    await expect(messagesMenu(ui.page, 2)).toBeVisible();
    expect((await api.unreadSummary(doctor.request)).body.notifications_unread).toBeGreaterThanOrEqual(2);
  });

  test("CSCW-CA-29 (secondary) - failed publication is retried from the durable outbox without duplicating effects", async () => {
    test.skip(true, "Not observable from a browser: the outbox consumer (app/services/notification_outbox.py) is real and wired since Lote 1, but forcing a publish failure requires monkeypatching the Python service directly. The full retry/no-duplicate-effects assertion is covered by tests/integration/test_outbox_and_delivery.py::test_cscw_ca_29_failed_publication_is_retried_from_a_durable_row_without_duplicate_effects (PASS).");
  });

  test("notification listing filters unread and a failed list load is recoverable", async ({ actor, browserSession }) => {
    const { patient, doctor } = await pair(actor);
    await openInvestigationAsPatient(patient, doctor);
    const all = (await api.notifications(doctor.request)).body;
    const unread = (await api.notifications(doctor.request, { unread_only: true })).body;
    expect(all.notifications.length).toBeGreaterThanOrEqual(unread.notifications.length);
    expect(unread.unread_count).toBe(unread.notifications.length);
    await api.readNotification(doctor.request, unread.notifications[0].id);
    expect((await api.notifications(doctor.request, { unread_only: true })).body.unread_count).toBe(unread.unread_count - 1);
    // Unknown / foreign notification ids are 404.
    expect((await api.readNotification(patient.request, unread.notifications[0].id)).status).toBe(404);

    const ui = await browserSession("doctorA");
    await ui.authenticateWithApi();
    await ui.page.goto(ROUTES.dashboard);
    let failNext = true;
    await ui.context.route("**/api/notifications?*", (route) => (failNext ? (failNext = false, route.fulfill({ status: 500, body: "{}" })) : route.continue()));
    const bell = ui.page.getByRole("button", { name: t("notifications.title") });
    await bell.click();
    await bell.click();
    await bell.click();
    await expect(ui.page.getByText(t(`notifications.types.investigation_opened`)).first()).toBeVisible();
  });
});
