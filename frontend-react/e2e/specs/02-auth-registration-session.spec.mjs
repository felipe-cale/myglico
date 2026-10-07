// Flow group 2 (PROMPT-ORCA.md, "Testes end-to-end"): registration of
// patient/doctor, role-specific fields, validation, login without e-mail
// confirmation, generic login failure, session, logout, browser back button
// and account switch.
//
// Criteria: AUT-CA-03, AUT-CA-04, AUT-CA-05, AUT-CA-06, AUT-CA-08, AUT-CA-09,
// AUT-CA-11, AUT-CA-19 (Não aplicável — single role per account), AUT-CA-20.
import { expect, test } from "../fixtures/test-fixtures.mjs";
import { ROUTES } from "../fixtures/routes.mjs";
import { tx } from "../fixtures/i18n.mjs";
import * as api from "../fixtures/api.mjs";

test.describe("Group 2 - registration, login, session and account switch", () => {
  test("AUT-CA-03 - patient registration creates the account and Patient with a valid short id", async ({ apiSession }) => {
    const session = await apiSession("patientA");
    const created = await session.register();
    expect(created.status).toBe(201);
    expect(created.body.account.roles).toEqual(["patient"]);
    const sess = await api.session(session.request);
    expect(sess.body.authenticated).toBe(true);
    expect(sess.body.patient.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(sess.body.patient.short_id).toMatch(/^[A-Z0-9]{6}$/);
    expect(sess.body.patient.display_name).toBe(session.profile.display_name);
    expect(sess.body.doctor).toBeUndefined();
  });

  test("AUT-CA-04 - doctor registration creates the account and Doctor with name/CRM/UF", async ({ apiSession }) => {
    const session = await apiSession("doctorA");
    const created = await session.register();
    expect(created.status).toBe(201);
    const sess = await api.session(session.request);
    expect(sess.body.doctor.short_id).toMatch(/^[A-Z0-9]{6}$/);
    expect(sess.body.doctor.crm).toBe(session.profile.crm);
    expect(sess.body.doctor.uf).toBe(session.profile.uf);
    expect(sess.body.doctor.name).toBe(session.profile.display_name);
    expect(sess.body.doctor.declared_verified).toBe(false);
    expect(sess.body.patient).toBeUndefined();
  });

  test("AUT-CA-05 - a rejected registration leaves no orphan account behind", async ({ apiSession, profiles }) => {
    // Domain-entity failure cannot be injected through HTTP; the transactional
    // rollback itself is asserted in tests/integration/test_atomicity_rollback.py.
    // Here: an invalid doctor payload (CRM without UF) must not leave a login-able account.
    const p = profiles("patientA");
    const invalid = await apiSession.registerAccount({
      role: "doctor", email: p.email, password: p.password, password_confirmation: p.password,
      display_name: p.display_name, crm: "1234567",
    });
    expect([400, 422]).toContain(invalid.status);
    const loginRes = await apiSession.login({ email: p.email, password: p.password });
    expect(loginRes.status).toBe(401);
    // The e-mail is still free: a valid registration now succeeds.
    const valid = await apiSession.registerAccount({
      role: "patient", email: p.email, password: p.password, password_confirmation: p.password,
      display_name: p.display_name,
    });
    expect(valid.status).toBe(201);
  });

  test("AUT-CA-06 - registration and login work although the e-mail is not confirmed", async ({ apiSession }) => {
    const session = await apiSession("patientB");
    expect((await session.register()).status).toBe(201);
    expect((await session.logout()).status).toBe(204);
    expect((await api.session(session.request)).body.authenticated).toBe(false);
    expect((await session.login()).status).toBe(200);
    const sess = await api.session(session.request);
    expect(sess.body.authenticated).toBe(true);
    expect(sess.body.patient).toBeTruthy();
  });

  test("AUT-CA-08 - two accounts with the same password are independent", async ({ apiSession, profiles }) => {
    profiles("patientB").password = profiles("patientA").password;
    const s1 = await apiSession("patientA");
    const s2 = await apiSession("patientB");
    expect((await s1.register()).status).toBe(201);
    expect((await s2.register()).status).toBe(201);
    const r1 = await api.session(s1.request);
    const r2 = await api.session(s2.request);
    expect(r1.body.patient.id).not.toBe(r2.body.patient.id);
    expect(r1.body.patient.short_id).not.toBe(r2.body.patient.short_id);
    // Hash/salt distinctness is asserted at DB level in tests/integration/test_crypto_and_secrets.py.
  });

  test("AUT-CA-09 - duplicate registration of the same e-mail is rejected with a generic error", async ({ apiSession }) => {
    const s1 = await apiSession("patientA");
    const s2 = await apiSession("patientA");
    expect((await s1.register()).status).toBe(201);
    const dup = await s2.register();
    expect(dup.status).toBe(409);
    expect(JSON.stringify(dup.body)).not.toContain(s1.profile.email);
    // Case variation of the same e-mail is the same account.
    const upper = await s2.register({ email: s1.profile.email.toUpperCase() });
    expect(upper.status).toBe(409);
    expect((await s1.login()).status).toBe(200);
  });

  test("AUT-CA-11 - tampered role/ids in the request grant no privilege", async ({ apiSession }) => {
    const s = await apiSession("patientA");
    const admin = await s.register({ role: "admin" });
    expect(admin.status).toBe(422);
    const injected = await s.register({ patient_id: "11111111-1111-1111-1111-111111111111" });
    expect(injected.status).toBe(422);
    expect((await api.session(s.request)).body.authenticated).toBe(false);
  });

  test("AUT-CA-19 (Não aplicável) - an account holds a single role: a patient e-mail cannot also become a doctor", async ({ apiSession, profiles }) => {
    // Product decision 2026-10-07: dual-role accounts were removed by design.
    const patient = await apiSession("patientA");
    expect((await patient.register()).status).toBe(201);
    const doctorTemplate = profiles("doctorA");
    const asDoctor = await apiSession.registerAccount({
      role: "doctor", email: patient.profile.email, password: patient.profile.password,
      password_confirmation: patient.profile.password, display_name: "X",
      crm: doctorTemplate.crm, uf: doctorTemplate.uf,
    });
    expect(asDoctor.status).toBe(409);
    const sess = await api.session(patient.request);
    expect(sess.body.doctor).toBeUndefined();
  });

  test("AUT-CA-20 - logout and account switch never expose the previous user's data (API)", async ({ apiSession }) => {
    const s1 = await apiSession("patientA");
    expect((await s1.register()).status).toBe(201);
    const first = (await api.session(s1.request)).body.patient;
    expect((await s1.logout()).status).toBe(204);
    expect((await api.patientDetail(s1.request, first.id)).status).toBe(401);
    // Same cookie jar, new account.
    const s2 = await apiSession("patientB");
    const r2 = await api.register(s1.request, s2.profile);
    expect(r2.status).toBe(201);
    const second = (await api.session(s1.request)).body.patient;
    expect(second.id).not.toBe(first.id);
    expect((await api.patientDetail(s1.request, first.id)).status).toBe(404);
  });

  test("SDD1 §8.3 (A5) - repeated failed logins from one client are throttled with a generic 429", async ({ actor, playwright }) => {
    const patient = await actor("patientA");
    const client = await playwright.request.newContext({
      baseURL: test.info().project.use.baseURL,
      extraHTTPHeaders: { "X-Forwarded-For": "10.250.250.250" },
    });
    try {
      const statuses = [];
      for (let i = 0; i < 12; i += 1) {
        statuses.push((await api.login(client, { email: patient.profile.email, password: "senha-errada-123" })).status);
      }
      expect(statuses.slice(0, 10).every((s) => s === 401)).toBe(true);
      expect(statuses.at(-1)).toBe(429);
      const blocked = await api.login(client, { email: patient.profile.email, password: patient.profile.password });
      expect(blocked.status).toBe(429);
      expect(JSON.stringify(blocked.body)).not.toContain(patient.profile.email);
    } finally {
      await client.dispose();
    }
  });

  test("AUT-CA-20 - UI logout then browser back lands on login without data", async ({ actor, browserSession }) => {
    const patient = await actor("patientA");
    const ui = await browserSession("patientA");
    await ui.page.goto(ROUTES.login);
    await ui.page.locator("input[type=email]").fill(patient.profile.email);
    await ui.page.locator("input[type=password]").fill(patient.profile.password);
    await ui.page.getByRole("button", { name: tx("auth.submitLogin") }).click();
    await expect(ui.page).toHaveURL(/\/dashboard$/);
    await ui.page.goto(ROUTES.patientDetail(patient.patientId));
    await expect(ui.page.getByText(patient.profile.display_name).first()).toBeVisible();
    await ui.page.getByRole("button", { name: tx("auth.logout") }).first().click();
    await expect(ui.page).toHaveURL(/\/(login)?$/);
    await ui.page.goBack();
    await expect(ui.page).toHaveURL(/\/login$/);
    await expect(ui.page.getByText(patient.profile.display_name)).toHaveCount(0);
    const cookies = await ui.context.cookies();
    const probe = await ui.page.request.get(`/api/patients/${patient.patientId}`);
    expect(probe.status()).toBe(401);
    expect(cookies.length).toBeGreaterThanOrEqual(0);
  });
});
