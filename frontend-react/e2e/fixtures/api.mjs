// Thin client for the agreed API contract (features/a-desenvolver/CONTRATOS-API.md).
//
// It performs real HTTP calls through Playwright's APIRequestContext — no
// mocking, no interception. Each context keeps its own cookie jar, so a caller
// can hold one context per profile (patient A/B, doctor A/B, dual-role) at the
// same time, exactly like separate browser sessions.
import { LEGACY_API } from "./routes.mjs";

async function json(response) {
  const contentType = response.headers()["content-type"] || "";
  if (!contentType.includes("application/json")) return null;
  return response.json();
}

export async function register(request, profile, overrides = {}) {
  const role = overrides.role || profile.roles[0];
  const body = {
    role,
    email: profile.email,
    password: profile.password,
    password_confirmation: overrides.password_confirmation || profile.password,
    display_name: profile.display_name,
    ...(profile.crm ? { crm: profile.crm } : {}),
    ...(profile.uf ? { uf: profile.uf } : {}),
    privacy_notice_accepted: true,
    ...overrides,
  };
  const response = await request.post("/api/auth/register", { data: body });
  return { status: response.status(), body: await json(response) };
}

export async function login(request, { email, password }) {
  const response = await request.post("/api/auth/login", { data: { email, password } });
  return { status: response.status(), body: await json(response) };
}

export async function logout(request) {
  const response = await request.post("/api/auth/logout");
  return { status: response.status() };
}

export async function session(request) {
  const response = await request.get("/api/auth/session");
  return { status: response.status(), body: await json(response) };
}

export async function searchDoctor(request, query) {
  const response = await request.get("/api/doctors/search", { params: query });
  return { status: response.status(), body: await json(response) };
}

export async function createDoctorLink(request, doctorShortId) {
  const response = await request.post("/api/doctor-links", { data: { doctor_short_id: doctorShortId } });
  return { status: response.status(), body: await json(response) };
}

export async function listDoctorLinks(request) {
  const response = await request.get("/api/doctor-links");
  return { status: response.status(), body: await json(response) };
}

export async function decideDoctorLink(request, linkId, action, version) {
  const response = await request.post(`/api/doctor-links/${linkId}/${action}`, { data: { version } });
  return { status: response.status(), body: await json(response) };
}

export async function revokeDoctorLink(request, linkId, version, reason) {
  const response = await request.post(`/api/doctor-links/${linkId}/revoke`, {
    data: { version, ...(reason ? { reason } : {}) },
  });
  return { status: response.status(), body: await json(response) };
}

export async function atypicalDays(request, patientId, range = {}) {
  const response = await request.get(`/api/patients/${patientId}/atypical-days`, { params: range });
  return { status: response.status(), body: await json(response) };
}

export async function atypicalPrompts(request, patientId) {
  const response = await request.get(`/api/patients/${patientId}/atypical-day-prompts`);
  return { status: response.status(), body: await json(response) };
}

export async function deferAtypicalPrompt(request, indicatorId) {
  const response = await request.post(`/api/atypical-day-prompts/${indicatorId}/defer`);
  return { status: response.status(), body: await json(response) };
}

export async function createInvestigation(request, payload, idempotencyKey) {
  const response = await request.post("/api/investigations", {
    data: payload,
    headers: idempotencyKey ? { "idempotency-key": idempotencyKey } : undefined,
  });
  return { status: response.status(), body: await json(response) };
}

export async function listInvestigations(request, params = {}) {
  const response = await request.get("/api/investigations", { params });
  return { status: response.status(), body: await json(response) };
}

export async function getInvestigation(request, investigationId, params = {}) {
  const response = await request.get(`/api/investigations/${investigationId}`, { params });
  return { status: response.status(), body: await json(response) };
}

export async function postMessage(request, investigationId, content, idempotencyKey) {
  const response = await request.post(`/api/investigations/${investigationId}/messages`, {
    data: { content, ...(idempotencyKey ? { idempotency_key: idempotencyKey } : {}) },
  });
  return { status: response.status(), body: await json(response) };
}

export async function readMessages(request, investigationId, upToSequence) {
  const response = await request.post(`/api/investigations/${investigationId}/read`, {
    data: { up_to_sequence: upToSequence },
  });
  return { status: response.status(), body: await json(response) };
}

export async function closeInvestigation(request, investigationId, { observation, version } = {}) {
  const response = await request.post(`/api/investigations/${investigationId}/close`, {
    data: { ...(observation ? { observation } : {}), version },
  });
  return { status: response.status(), body: await json(response) };
}

export async function notifications(request, params = {}) {
  const response = await request.get("/api/notifications", { params });
  return { status: response.status(), body: await json(response) };
}

export async function readNotification(request, notificationId) {
  const response = await request.post(`/api/notifications/${notificationId}/read`);
  return { status: response.status(), body: await json(response) };
}

export async function unreadSummary(request) {
  const response = await request.get("/api/notifications/unread-summary");
  return { status: response.status(), body: await json(response) };
}

export async function patientDetail(request, patientId, params = {}) {
  const response = await request.get(`/api/patients/${patientId}`, { params });
  return { status: response.status(), body: await json(response) };
}

export async function addGlucoseRecord(request, patientId, record) {
  const response = await request.post(`/api/patients/${patientId}/glucose-records`, { data: record });
  return { status: response.status(), body: await json(response) };
}

export async function reportPdf(request, patientId, params) {
  const response = await request.get(`/api/patients/${patientId}/report.pdf`, { params });
  return {
    status: response.status(),
    contentType: response.headers()["content-type"] || "",
    disposition: response.headers()["content-disposition"] || "",
    body: await response.body(),
  };
}

export async function health(request, path = "/health") {
  const response = await request.get(path);
  return { status: response.status(), body: await json(response) };
}

// Direct, unauthenticated probes used by the guardrail scenarios. They never
// attach a session cookie unless the caller passes an authenticated context.
export async function probe(request, path) {
  const response = await request.get(path);
  return { status: response.status(), contentType: response.headers()["content-type"] || "", body: await response.text() };
}

export const legacy = LEGACY_API;
