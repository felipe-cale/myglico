import { expect, linkActive, openInvestigationAsPatient, test } from "../fixtures/test-fixtures.mjs";
import { ROUTES } from "../fixtures/routes.mjs";
import { t } from "../fixtures/i18n.mjs";

async function expectNoHorizontalOverflow(page) {
  const dimensions = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
  }));
  expect(dimensions.documentWidth, `mobile content exceeds ${dimensions.viewportWidth}px viewport`).toBeLessThanOrEqual(
    dimensions.viewportWidth,
  );
}

test.describe("Responsive layout", () => {
  test("CSCW-CA-20 - conversation fits a 390px mobile viewport", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);
    const investigation = await openInvestigationAsPatient(patient, doctor);

    const ui = await browserSession("patientA");
    await ui.authenticateWithApi();
    await ui.page.setViewportSize({ width: 390, height: 844 });
    await ui.page.goto(ROUTES.investigation(investigation.id));

    await expect(ui.page.getByRole("heading", { name: t("cscw.messagesTitle") })).toBeVisible();
    await expectNoHorizontalOverflow(ui.page);
  });

  test("CSCW-CA-01 - doctor search controls fit a 390px mobile viewport", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const doctor = await actor("doctorA");
    await linkActive(patient, doctor);

    const ui = await browserSession("patientA");
    await ui.authenticateWithApi();
    await ui.page.setViewportSize({ width: 390, height: 844 });
    await ui.page.goto(ROUTES.dashboard);
    await ui.page.getByRole("button", { name: t("dashboard.addDoctor") }).click();

    await expect(ui.page.getByLabel(t("dashboard.shortId"))).toBeVisible();
    await expect(ui.page.getByRole("button", { name: t("dashboard.search") })).toBeVisible();
    await expectNoHorizontalOverflow(ui.page);
  });
});
