// Flow group 9 (PROMPT-ORCA.md, "Testes end-to-end"): atypical-days popup,
// count consistency, non-consecutive days, filter composition/clearing,
// midnight/timezone, accessibility and loading/empty/error states.
//
// Criteria: CSCW-CA-23, CSCW-CA-24, CSCW-CA-25, CSCW-CA-26, CSCW-CA-27.
import { expect, seedAtypicalDays, test } from "../fixtures/test-fixtures.mjs";
import { ROUTES } from "../fixtures/routes.mjs";
import { escapeRegex, t, tx } from "../fixtures/i18n.mjs";
import * as api from "../fixtures/api.mjs";

const RANGE = { start_date: "2026-06-01", end_date: "2026-07-31" };
// Window used only by the global-run scenario (see CSCW-CA-23 (A1)).
const GLOBAL_RUN_RANGE = { start_date: "2025-02-03", end_date: "2025-03-31" };
const dayOf = (row) => row.indicator_date || row.date || row.metric_date;

// The popup trigger is the interactive "Dias atípicos" stat card of the
// patient detail; its accessible name is "<label>: <count>. <action hint>".
function popupTrigger(page) {
  const label = escapeRegex(t("patientDetail.stats.anomalyDays.label"));
  const action = escapeRegex(t("patientDetail.stats.anomalyDays.action"));
  return page.getByRole("button", { name: new RegExp(`^\\s*${label}: .*\\. ${action}\\s*$`, "i") });
}

// The trigger only exists once the session and the patient detail have loaded.
// Waiting on those real responses (instead of only on the button) makes a
// failed load report which request failed and where the page ended up.
async function openDetail(browserSession, key, patientId, search = "") {
  const ui = await browserSession(key);
  await ui.authenticateWithApi();
  const responseTo = (pathname) => ui.page
    .waitForResponse((r) => r.request().method() === "GET" && new URL(r.url()).pathname === pathname, { timeout: 20_000 })
    .catch((error) => error);
  const sessionResponse = responseTo("/api/auth/session");
  const detailResponse = responseTo(`/api/patients/${patientId}`);
  await ui.page.goto(ROUTES.patientDetailQuery(patientId, search));
  for (const [label, pending] of [["/api/auth/session", sessionResponse], [`/api/patients/${patientId}`, detailResponse]]) {
    const response = await pending;
    if (response instanceof Error) throw new Error(`GET ${label} never answered (page at ${ui.page.url()}): ${response.message}`);
    expect(response.status(), `GET ${label} (page at ${ui.page.url()})`).toBe(200);
  }
  await expect(popupTrigger(ui.page)).toBeVisible();
  return ui;
}

// The period date form sits behind the "Alterar período" disclosure of the period bar.
async function expandPeriodForm(page) {
  const toggle = page.getByRole("button", { name: tx("patientDetail.filter.toggle") });
  await expect(toggle).toBeVisible();
  if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
}

// The manual entry form is collapsed to its header row until it is opened.
async function openManualEntry(page) {
  const toggle = page.locator("#new-reading").getByRole("button", { name: tx("manualEntry.toggle") });
  await toggle.click();
  await expect(page.locator("#new-reading").getByRole("button", { name: tx("manualEntry.toggleClose") })).toHaveAttribute("aria-expanded", "true");
}

async function openPopup(page) {
  await popupTrigger(page).click();
  const dialog = page.getByRole("dialog", { name: t("cscw.popupTitle") });
  await expect(dialog).toBeVisible();
  return dialog;
}

test.describe("Group 9 - atypical-days popup and filters", () => {
  test("CSCW-CA-23 - the popup lists exactly the days counted for the patient (patient-scoped run)", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const seeded = seedAtypicalDays(patient.patientId);
    const detail = (await api.patientDetail(patient.request, patient.patientId, RANGE)).body;
    expect(detail.summary.anomaly_days).toBe(seeded.flagged.length);

    const ui = await openDetail(browserSession, "patientA", patient.patientId, `?start_date=${RANGE.start_date}&end_date=${RANGE.end_date}`);
    const dialog = await openPopup(ui.page);
    await expect(dialog.getByRole("checkbox")).toHaveCount(seeded.flagged.length);
  });

  test("CSCW-CA-23 (A1) - UCI-style global analysis run: popup is not empty", async ({ actor }) => {
    const patient = await actor("patientA");
    // The global run is bounded to a window no other test seeds, so it only
    // covers this test's data instead of every patient left in the shared E2E
    // database (P2-03: unbounded, it took >60 s after a few repetitions).
    const seeded = seedAtypicalDays(patient.patientId, { globalRun: true, start: GLOBAL_RUN_RANGE.start_date });
    expect(seeded.run_patient_id).toBeNull();
    const days = (await api.atypicalDays(patient.request, patient.patientId, GLOBAL_RUN_RANGE)).body.days;
    expect(days.map((d) => d.indicator_id).sort()).toEqual(seeded.flagged.map((f) => f.indicator_id).sort());
  });

  test("CSCW-CA-23 (N1) - card count stays consistent with the popup after another patient's analysis runs", async ({ actor }) => {
    const patientA = await actor("patientA");
    const patientB = await actor("patientB");
    const seededA = seedAtypicalDays(patientA.patientId);
    seedAtypicalDays(patientB.patientId);
    const popupCount = (await api.atypicalDays(patientA.request, patientA.patientId, RANGE)).body.days.length;
    const card = (await api.patientDetail(patientA.request, patientA.patientId, RANGE)).body.summary.anomaly_days;
    expect(popupCount).toBe(seededA.flagged.length);
    expect(card).toBe(popupCount);
  });

  test("CSCW-CA-24 - selecting non-consecutive days filters only those days, never the in-between range", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const seeded = seedAtypicalDays(patient.patientId, { spikes: [10, 25] });
    expect(seeded.flagged.length).toBeGreaterThanOrEqual(2);
    const [first, last] = [seeded.flagged[0].date, seeded.flagged.at(-1).date];

    const ui = await openDetail(browserSession, "patientA", patient.patientId, `?start_date=${RANGE.start_date}&end_date=${RANGE.end_date}`);
    const dialog = await openPopup(ui.page);
    const boxes = dialog.getByRole("checkbox");
    await boxes.first().check();
    await boxes.last().check();
    const detailRequest = ui.page.waitForRequest((r) => r.url().includes(`/api/patients/${patient.patientId}?`) && r.url().includes("dates="));
    await dialog.getByRole("button", { name: tx("cscw.popupApply") }).click();
    const url = new URL((await detailRequest).url());
    expect(url.searchParams.get("dates").split(",").sort()).toEqual([first, last].sort());
    await expect(ui.page).toHaveURL(/dates=/);

    const filtered = (await api.patientDetail(patient.request, patient.patientId, { dates: `${first},${last}` })).body;
    const shownDays = [...new Set(filtered.daily_indicators.map(dayOf))].sort();
    expect(shownDays).toEqual([first, last].sort());
    const eventDays = [...new Set(filtered.glucose_events.map((e) => e.occurred_at.slice(0, 10)))].sort();
    expect(eventDays).toEqual([first, last].sort());
  });

  test("CSCW-CA-25 - clearing the day selection keeps the period filter (composition and single state)", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    seedAtypicalDays(patient.patientId);
    const ui = await openDetail(browserSession, "patientA", patient.patientId, `?start_date=${RANGE.start_date}&end_date=${RANGE.end_date}`);
    // The API clamps the requested period to the available data; that normalized period is the active filter to preserve.
    await expect(ui.page).toHaveURL(/start_date=2026-06-01/);
    const activePeriod = new URL(ui.page.url()).searchParams;
    const activeStart = activePeriod.get("start_date");
    const activeEnd = activePeriod.get("end_date");
    let dialog = await openPopup(ui.page);
    await dialog.getByRole("checkbox").first().check();
    // Chip for the selected day is visible inside the popup.
    await expect(dialog.getByRole("button", { name: /×|remover|remove/i }).first()).toBeVisible();
    await dialog.getByRole("button", { name: tx("cscw.popupApply") }).click();
    await expect(ui.page).toHaveURL(/dates=/);
    await expect.poll(() => new URL(ui.page.url()).searchParams.get("start_date")).toBe(activeStart);
    await expect.poll(() => new URL(ui.page.url()).searchParams.get("end_date")).toBe(activeEnd);

    dialog = await openPopup(ui.page);
    await dialog.getByRole("button", { name: tx("cscw.popupClearDays") }).click();
    await expect(ui.page).not.toHaveURL(/dates=/);
    await expect.poll(() => new URL(ui.page.url()).searchParams.get("start_date")).toBe(activeStart);
    await expect.poll(() => new URL(ui.page.url()).searchParams.get("end_date")).toBe(activeEnd);
    await expandPeriodForm(ui.page);
    await expect(ui.page.locator('input[type="date"]').first()).toHaveValue(activeStart);
  });

  test("CSCW-CA-23/25 (N2, N3) - popup follows the active period shorter than the history; a day outside it widens the period with a notice", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const seeded = seedAtypicalDays(patient.patientId);
    const flaggedDates = seeded.flagged.map((item) => item.date).sort();
    expect(flaggedDates.length).toBeGreaterThanOrEqual(2);
    const outsideDay = flaggedDates.at(-1);
    const dayBefore = new Date(`${outsideDay}T00:00:00Z`);
    dayBefore.setUTCDate(dayBefore.getUTCDate() - 1);
    const shortRange = { start_date: RANGE.start_date, end_date: dayBefore.toISOString().slice(0, 10) };

    // The active period deliberately excludes the last atypical day of the history.
    const scoped = (await api.patientDetail(patient.request, patient.patientId, shortRange)).body;
    const cardCount = scoped.summary.anomaly_days;
    expect(cardCount).toBeGreaterThan(0);
    expect(cardCount).toBeLessThan(flaggedDates.length);

    const ui = await openDetail(browserSession, "patientA", patient.patientId, `?start_date=${shortRange.start_date}&end_date=${shortRange.end_date}`);
    const dialog = await openPopup(ui.page);
    // N2: same scope as the card, and the scope is stated.
    await expect(dialog.getByRole("checkbox")).toHaveCount(cardCount);
    await expect(dialog.getByTestId("atypical-scope")).toContainText(String(cardCount));
    await expect(dialog.locator('input[type="date"]').first()).toHaveValue(shortRange.start_date);
    await expect(dialog.locator('input[type="date"]').last()).toHaveValue(shortRange.end_date);
    await dialog.getByRole("button", { name: tx("cscw.popupShowAll") }).click();
    await expect(dialog.getByRole("checkbox")).toHaveCount(flaggedDates.length);
    await expect(dialog.getByTestId("atypical-scope")).toHaveText(t("cscw.popupScopeAll", "pt-BR", { count: flaggedDates.length }));

    // N3: picking a day outside the active period widens it explicitly.
    const [y, m, d] = outsideDay.split("-");
    const outsideLabel = `${d}/${m}/${y}`;
    const popupLabel = new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(new Date(`${outsideDay}T00:00:00`));
    const outsideRow = dialog.getByRole("listitem").filter({ hasText: popupLabel });
    await outsideRow.getByRole("checkbox").check();
    await dialog.getByRole("button", { name: tx("cscw.popupApply") }).click();
    await expect(ui.page).toHaveURL(new RegExp(`dates=${outsideDay}`));
    await expect.poll(() => new URL(ui.page.url()).searchParams.get("end_date")).toBe(outsideDay);
    await expect.poll(() => new URL(ui.page.url()).searchParams.get("start_date")).toBe(shortRange.start_date);
    const notice = ui.page.getByTestId("period-adjusted");
    await expect(notice).toBeVisible();
    await expect(notice).toContainText(outsideLabel);
    const summary = ui.page.getByTestId("period-summary");
    await expect(summary).toContainText(outsideLabel);
    await expect(summary).not.toContainText(t("patientDetail.hero.defaultWindow"));
    await expect(summary).not.toContainText("- -");

    // Clearing the days restores the user's original (shorter) period and removes the notice.
    await ui.page.locator(".react-selected-days").getByRole("button", { name: tx("cscw.popupClearDays") }).click();
    await expect(ui.page).not.toHaveURL(/dates=/);
    await expect.poll(() => new URL(ui.page.url()).searchParams.get("end_date")).toBe(shortRange.end_date);
    await expect(ui.page.getByTestId("period-adjusted")).toHaveCount(0);
  });

  test("CSCW-CA-25 (O5, O6) - the original period survives a reload after an automatic widening; the summary tells default from custom periods", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const seeded = seedAtypicalDays(patient.patientId);
    const outsideDay = seeded.flagged.map((item) => item.date).sort().at(-1);
    const dayBefore = new Date(`${outsideDay}T00:00:00Z`);
    dayBefore.setUTCDate(dayBefore.getUTCDate() - 1);
    const shortRange = { start_date: RANGE.start_date, end_date: dayBefore.toISOString().slice(0, 10) };

    // O6: no period filter -> default window text.
    const ui = await openDetail(browserSession, "patientA", patient.patientId);
    const summary = ui.page.getByTestId("period-summary");
    await expect(summary).toContainText(t("patientDetail.hero.defaultWindow"));

    // O6: explicit custom period -> no default-window text.
    await ui.page.goto(ROUTES.patientDetailQuery(patient.patientId, `?start_date=${shortRange.start_date}&end_date=${shortRange.end_date}`));
    await expect(popupTrigger(ui.page)).toBeVisible();
    const customDays = Math.round((Date.parse(`${shortRange.end_date}T00:00:00Z`) - Date.parse(`${shortRange.start_date}T00:00:00Z`)) / 86400000) + 1;
    await expect(summary).toContainText(t("patientDetail.hero.customWindow", "pt-BR", { count: customDays }));
    await expect(summary).not.toContainText(t("patientDetail.hero.defaultWindow"));

    // Widen the period by picking a day outside it.
    const dialog = await openPopup(ui.page);
    await dialog.getByRole("button", { name: tx("cscw.popupShowAll") }).click();
    const popupLabel = new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(new Date(`${outsideDay}T00:00:00`));
    await dialog.getByRole("listitem").filter({ hasText: popupLabel }).getByRole("checkbox").check();
    await dialog.getByRole("button", { name: tx("cscw.popupApply") }).click();
    await expect.poll(() => new URL(ui.page.url()).searchParams.get("end_date")).toBe(outsideDay);
    await expect(ui.page.getByTestId("period-adjusted")).toBeVisible();

    // O5: after a reload the notice is still there and clearing restores the original period.
    await ui.page.reload();
    await expect(popupTrigger(ui.page)).toBeVisible();
    await expect(ui.page).toHaveURL(new RegExp(`dates=${outsideDay}`));
    await expect(ui.page.getByTestId("period-adjusted")).toBeVisible();
    await ui.page.locator(".react-selected-days").getByRole("button", { name: tx("cscw.popupClearDays") }).click();
    await expect(ui.page).not.toHaveURL(/dates=/);
    await expect.poll(() => new URL(ui.page.url()).searchParams.get("start_date")).toBe(shortRange.start_date);
    await expect.poll(() => new URL(ui.page.url()).searchParams.get("end_date")).toBe(shortRange.end_date);
    await expect(ui.page.getByTestId("period-adjusted")).toHaveCount(0);
    await expect(summary).toContainText(t("patientDetail.hero.customWindow", "pt-BR", { count: customDays }));

    // A further reload without dates keeps the restored period (no stale state).
    await ui.page.reload();
    await expect(popupTrigger(ui.page)).toBeVisible();
    await expect.poll(() => new URL(ui.page.url()).searchParams.get("end_date")).toBe(shortRange.end_date);
    await expect(ui.page.getByTestId("period-adjusted")).toHaveCount(0);
  });

  test("CSCW-CA-26 - the real manual form preserves both sides of local midnight", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const ui = await openDetail(browserSession, "patientA", patient.patientId);
    await openManualEntry(ui.page);
    const form = ui.page.locator(".react-manual-entry-form");
    const dateInput = form.locator('input[type="datetime-local"]');
    const glucoseInput = form.locator('input[type="number"]');
    for (const localTime of ["2026-10-08T00:30", "2026-10-08T23:30"]) {
      await dateInput.fill(localTime);
      await glucoseInput.fill("123");
      await form.getByRole("button", { name: tx("manualEntry.submit") }).click();
      await expect(form.getByRole("status")).toBeVisible();
    }
    const sameDay = (await api.patientDetail(patient.request, patient.patientId, { dates: "2026-10-08" })).body;
    expect(sameDay.glucose_events.filter((event) => event.event_date === "2026-10-08").map((event) => event.event_time))
      .toEqual(expect.arrayContaining(["00:30", "23:30"]));
    expect(sameDay.glucose_events.every((event) => event.event_date === "2026-10-08")).toBe(true);
  });

  test("CSCW-CA-27 - empty, loading and error states are accessible and invent nothing", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const ui = await openDetail(browserSession, "patientA", patient.patientId);
    // Empty: no analytics yet.
    let dialog = await openPopup(ui.page);
    await expect(dialog).toHaveAttribute("aria-modal", "true");
    await expect(dialog.getByText(t("cscw.popupEmpty"))).toBeVisible();
    await expect(dialog.getByRole("checkbox")).toHaveCount(0);
    await ui.page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);

    // Error + retry: the atypical-days call fails once.
    let fail = true;
    await ui.context.route("**/atypical-days*", (route) => (fail ? (fail = false, route.fulfill({ status: 500, body: "{}" })) : route.continue()));
    dialog = await openPopup(ui.page);
    await expect(dialog.getByRole("alert")).toContainText(t("cscw.popupError"));
    await expect(dialog.getByRole("checkbox")).toHaveCount(0);
    await dialog.getByRole("button", { name: tx("cscw.retry") }).click();
    await expect(dialog.getByText(t("cscw.popupEmpty"))).toBeVisible();
    await dialog.getByRole("button", { name: t("cscw.popupCloseAria") }).click();

    // Loading: slow response shows an accessible status.
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    await ui.context.unroute("**/atypical-days*");
    await ui.context.route("**/atypical-days*", async (route) => { await gate; await route.continue(); });
    dialog = await openPopup(ui.page);
    await expect(dialog.getByRole("status")).toContainText(t("cscw.popupLoading"));
    release();
    await expect(dialog.getByText(t("cscw.popupEmpty"))).toBeVisible();
  });

  test("popup period filter narrows the list and keeps the selected-day chips", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const seeded = seedAtypicalDays(patient.patientId, { spikes: [10, 25] });
    const ui = await openDetail(browserSession, "patientA", patient.patientId, `?start_date=${RANGE.start_date}&end_date=${RANGE.end_date}`);
    const dialog = await openPopup(ui.page);
    await expect(dialog.getByRole("checkbox")).toHaveCount(seeded.flagged.length);
    await dialog.getByRole("checkbox").first().check();
    const onlyFirst = seeded.flagged.at(-1).date;
    const range = dialog.locator("form");
    await range.locator("input[type=date]").first().fill(onlyFirst);
    await range.locator("input[type=date]").last().fill(onlyFirst);
    await range.locator("input[type=date]").last().press("Enter");
    await expect(dialog.getByRole("checkbox")).toHaveCount(1);
    await expect(dialog.getByRole("button", { name: /×|remover|remove/i }).first()).toBeVisible();
  });

  test("keyboard accessibility: focus starts in the popup, Esc closes it and focus returns to the trigger", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    seedAtypicalDays(patient.patientId);
    const ui = await openDetail(browserSession, "patientA", patient.patientId);
    const trigger = popupTrigger(ui.page);
    const dialog = await openPopup(ui.page);
    await expect.poll(() => ui.page.evaluate(() => Boolean(document.activeElement?.closest("[role=dialog]")))).toBe(true);
    await expect(dialog.getByRole("button", { name: t("cscw.popupCloseAria") })).toBeVisible();
    await ui.page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });
});
