// Flow group 9 (PROMPT-ORCA.md, "Testes end-to-end"): atypical-days popup,
// count consistency, non-consecutive days, filter composition/clearing,
// midnight/timezone, accessibility and loading/empty/error states.
//
// Criteria: CSCW-CA-23, CSCW-CA-24, CSCW-CA-25, CSCW-CA-26, CSCW-CA-27.
import { expect, seedAtypicalDays, test } from "../fixtures/test-fixtures.mjs";
import { ROUTES } from "../fixtures/routes.mjs";
import { t, tx } from "../fixtures/i18n.mjs";
import * as api from "../fixtures/api.mjs";

const RANGE = { start_date: "2026-06-01", end_date: "2026-07-31" };
const dayOf = (row) => row.indicator_date || row.date || row.metric_date;

async function openDetail(browserSession, key, patientId, search = "") {
  const ui = await browserSession(key);
  await ui.authenticateWithApi();
  await ui.page.goto(ROUTES.patientDetailQuery(patientId, search));
  await expect(ui.page.getByRole("button", { name: tx("cscw.popupButton") })).toBeVisible();
  return ui;
}

async function openPopup(page) {
  await page.getByRole("button", { name: tx("cscw.popupButton") }).click();
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
    const seeded = seedAtypicalDays(patient.patientId, { globalRun: true });
    expect(seeded.run_patient_id).toBeNull();
    const days = (await api.atypicalDays(patient.request, patient.patientId, RANGE)).body.days;
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

  test("CSCW-CA-26 - a reading at 23:59 belongs to its own calendar day", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    seedAtypicalDays(patient.patientId, { midnightDay: 5 });
    const day = "2026-06-06";
    const next = "2026-06-07";
    const sameDay = (await api.patientDetail(patient.request, patient.patientId, { dates: day })).body;
    expect(sameDay.glucose_events.some((e) => e.occurred_at.startsWith(`${day}T23:59`))).toBe(true);
    const nextDay = (await api.patientDetail(patient.request, patient.patientId, { dates: next })).body;
    expect(nextDay.glucose_events.some((e) => e.occurred_at.includes("23:59"))).toBe(false);
    expect(nextDay.glucose_events.every((e) => e.occurred_at.startsWith(next))).toBe(true);
    test.info().annotations.push({
      type: "partial",
      description: "Readings are naive local datetimes; there is no per-patient timezone, so the day boundary is the stored wall-clock date (browser runs in America/Sao_Paulo).",
    });
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
    const trigger = ui.page.getByRole("button", { name: tx("cscw.popupButton") });
    const dialog = await openPopup(ui.page);
    await expect.poll(() => ui.page.evaluate(() => Boolean(document.activeElement?.closest("[role=dialog]")))).toBe(true);
    await expect(dialog.getByRole("button", { name: t("cscw.popupCloseAria") })).toBeVisible();
    await ui.page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });
});
