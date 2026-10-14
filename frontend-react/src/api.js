import { beginRequest, endRequest } from "./loadingStore";

const JSON_HEADERS = {
  Accept: "application/json",
  "Content-Type": "application/json"
};

export const REQUEST_TIMEOUT_MS = 20000;

// Requests the person triggered show the global loading overlay and can be
// cancelled from it; polling and panels with their own inline loading state
// pass { background: true }. Every request gives up after `timeout` ms with
// error.code === "timeout"; a cancelled one rejects with error.code === "aborted".
async function requestJson(path, { background = false, timeout = REQUEST_TIMEOUT_MS, signal: externalSignal, ...options } = {}) {
  const controller = new AbortController();
  let timedOut = false;
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort();
    else externalSignal.addEventListener("abort", () => controller.abort(), { once: true });
  }
  const timer = timeout > 0 ? setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeout) : null;
  if (!background) beginRequest(controller);
  try {
    return await sendJson(path, { ...options, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted) {
      const stopped = new Error(`Request ${timedOut ? "timed out" : "cancelled"} ${path}`);
      stopped.code = timedOut ? "timeout" : "aborted";
      stopped.cause = error;
      throw stopped;
    }
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
    if (!background) endRequest(controller);
  }
}

async function sendJson(path, options) {
  const headers = { ...JSON_HEADERS, ...options.headers };
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers
  });
  if (!response.ok) {
    if (response.status === 401) throw new Error("Unauthorized");
    const error = new Error(`Request failed ${path}: ${response.status}`);
    error.status = response.status;
    // Machine-readable code (e.g. "context_changed") for callers that map errors to localized copy; never shown raw.
    const body = await response.json().catch(() => null);
    if (typeof body?.detail === "string") error.detail = body.detail;
    const retryAfter = Number(response.headers.get("Retry-After"));
    if (Number.isFinite(retryAfter) && retryAfter > 0) error.retryAfter = retryAfter;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

// === AUTH ===
export function registerAccount(payload) {
  return requestJson("/api/auth/register", { method: "POST", body: JSON.stringify(payload) });
}
export function login(email, password) {
  return requestJson("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
}
export function logout() {
  resetGlicoCsrf();
  return requestJson("/api/auth/logout", { method: "POST" });
}
export function fetchSession() {
  return requestJson("/api/auth/session", { background: true });
}

// === DOCTORS & LINKS ===
export function searchDoctors(params) {
  const criteria = Object.fromEntries(
    Object.entries(params).filter(([, value]) => String(value ?? "").trim())
  );
  const q = new URLSearchParams(criteria).toString();
  return requestJson(`/api/doctors/search?${q}`);
}
export function fetchDoctorLinks(params = {}) {
  const q = new URLSearchParams(params).toString();
  return requestJson(`/api/doctor-links${q ? `?${q}` : ""}`);
}
export function requestDoctorLink(doctor_short_id) {
  return requestJson("/api/doctor-links", { method: "POST", body: JSON.stringify({ doctor_short_id }) });
}
export function confirmDoctorLink(id, version) {
  return requestJson(`/api/doctor-links/${id}/confirm`, { method: "POST", body: JSON.stringify({ version }) });
}
export function rejectDoctorLink(id, version) {
  return requestJson(`/api/doctor-links/${id}/reject`, { method: "POST", body: JSON.stringify({ version }) });
}
export function cancelDoctorLink(id, version) {
  return requestJson(`/api/doctor-links/${id}/cancel`, { method: "POST", body: JSON.stringify({ version }) });
}
export function revokeDoctorLink(id, payload) {
  return requestJson(`/api/doctor-links/${id}/revoke`, { method: "POST", body: JSON.stringify(payload) });
}

// === INVESTIGATIONS ===
export function fetchInvestigations(params = {}) {
  const q = new URLSearchParams(params).toString();
  return requestJson(`/api/investigations?${q}`);
}
export function fetchInvestigationDetail(id, params = {}, { background = false } = {}) {
  const q = new URLSearchParams(params).toString();
  return requestJson(`/api/investigations/${id}${q ? `?${q}` : ""}`, { background });
}
export function createInvestigation(payload) {
  return requestJson("/api/investigations", { method: "POST", body: JSON.stringify(payload) });
}
export function sendInvestigationMessage(id, payload) {
  return requestJson(`/api/investigations/${id}/messages`, { method: "POST", body: JSON.stringify(payload) });
}
export function readInvestigation(id, up_to_sequence) {
  return requestJson(`/api/investigations/${id}/read`, { method: "POST", body: JSON.stringify({ up_to_sequence }), background: true });
}
export function closeInvestigation(id, payload) {
  return requestJson(`/api/investigations/${id}/close`, { method: "POST", body: JSON.stringify(payload) });
}

// === ATYPICAL DAYS ===
export function fetchAtypicalDays(patientId, params = {}) {
  const q = new URLSearchParams(params).toString();
  return requestJson(`/api/patients/${patientId}/atypical-days?${q}`, { background: true });
}
export function fetchAtypicalDayPrompts(patientId, params = {}) {
  const q = new URLSearchParams(params).toString();
  return requestJson(`/api/patients/${patientId}/atypical-day-prompts${q ? `?${q}` : ""}`, { background: true });
}
export function deferAtypicalDayPrompt(indicator_ids) {
  return requestJson("/api/atypical-day-prompts/defer", {
    method: "POST",
    body: JSON.stringify({ indicator_ids: Array.isArray(indicator_ids) ? indicator_ids : [indicator_ids] })
  });
}

// === NOTIFICATIONS ===
export function fetchNotifications(params = {}) {
  const q = new URLSearchParams(params).toString();
  return requestJson(`/api/notifications?${q}`, { background: true });
}
export function readNotification(id) {
  return requestJson(`/api/notifications/${id}/read`, { method: "POST" });
}
export function fetchUnreadSummary() {
  return requestJson("/api/notifications/unread-summary", { background: true });
}

// === LEGACY ===
export function fetchDashboardSummary() {
  return requestJson("/api/dashboard");
}
export function fetchPatients({ page = 1, pageSize = 10, query = "", signal = "all" }, { background = false } = {}) {
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  if (query) params.set("q", query);
  if (signal && signal !== "all") params.set("signal", signal);
  return requestJson(`/api/patients?${params.toString()}`, { background });
}
export function fetchPatientDetail(patientId, {
  startDate, endDate, dates, indicatorPage = 1, indicatorPageSize = 10, eventPage = 1, eventPageSize = 10
} = {}) {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  if (dates?.length) params.set("dates", dates.join(","));
  params.set("indicator_page", String(indicatorPage));
  params.set("indicator_page_size", String(indicatorPageSize));
  params.set("event_page", String(eventPage));
  params.set("event_page_size", String(eventPageSize));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson(`/api/patients/${patientId}${suffix}`);
}
export function createManualGlucoseRecord(patientId, payload) {
  return requestJson(`/api/patients/${encodeURIComponent(patientId)}/glucose-records`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
export function patientReportPdfUrl(patientId, { startDate, endDate, lang }) {
  if (!patientId || !startDate || !endDate) return null;
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
  if (lang) params.set("lang", lang);
  return `/api/patients/${encodeURIComponent(patientId)}/report.pdf?${params.toString()}`;
}

// === GLICO ASSISTANT ===
// Every Glico call is inline (background): the page shows its own busy and error states, and media uploads have their own cancel button.
const GLICO_BACKGROUND = { background: true };
let glicoCsrf = null;

export function resetGlicoCsrf() {
  glicoCsrf = null;
}

export function fetchGlicoCapabilities(locale) {
  const query = new URLSearchParams({ locale });
  return requestJson(`/api/glico/capabilities?${query}`, GLICO_BACKGROUND);
}

async function glicoCsrfToken() {
  if (!glicoCsrf) glicoCsrf = (await requestJson("/api/glico/csrf", GLICO_BACKGROUND)).token;
  return glicoCsrf;
}

// The CSRF token is bound to the session cookie. A rejected token (new login, rotated session) is refetched and the
// request is retried once; csrf_failed is refused before anything executes, so the retry cannot duplicate an effect.
async function glicoMutation(path, payload, { method = "POST", signal } = {}) {
  const send = async () => requestJson(path, {
    ...GLICO_BACKGROUND,
    method,
    signal,
    headers: { "X-MyGlico-CSRF": await glicoCsrfToken() },
    body: JSON.stringify(payload)
  });
  try {
    return await send();
  } catch (error) {
    if (error?.status === 403 && error.detail === "csrf_failed") {
      resetGlicoCsrf();
      return send();
    }
    throw error;
  }
}

export function createGlicoConversation(locale, client_request_id) {
  return glicoMutation("/api/glico/conversations", { locale, client_request_id });
}

export function createGlicoCollaborationProposal(conversationId, payload) {
  return glicoMutation(`/api/glico/conversations/${encodeURIComponent(conversationId)}/collaboration-proposals`, payload);
}

export function fetchGlicoConversation(id) {
  return requestJson(`/api/glico/conversations/${encodeURIComponent(id)}`, GLICO_BACKGROUND);
}

export function updateGlicoContext(id, payload) {
  return glicoMutation(`/api/glico/conversations/${encodeURIComponent(id)}/context`, payload, { method: "PATCH" });
}

export function sendGlicoMessage(id, payload, { signal } = {}) {
  return glicoMutation(`/api/glico/conversations/${encodeURIComponent(id)}/messages`, payload, { signal });
}

export function editGlicoProposal(id, payload) {
  return glicoMutation(`/api/glico/proposals/${encodeURIComponent(id)}`, payload, { method: "PATCH" });
}

export function confirmGlicoProposal(id, payload) {
  return glicoMutation(`/api/glico/proposals/${encodeURIComponent(id)}/confirm`, payload);
}

export function cancelGlicoProposal(id, version) {
  return glicoMutation(`/api/glico/proposals/${encodeURIComponent(id)}/cancel`, { version });
}

// Photo/audio go as one raw application/octet-stream body (never multipart). The gateway reads the context and the
// request id from headers; the media is not echoed back and the caller drops its reference once this settles.
export async function extractGlicoMedia(id, kind, blob, { contextVersion, clientRequestId, signal }) {
  const send = async () => requestJson(`/api/glico/conversations/${encodeURIComponent(id)}/extract/${kind}`, {
    ...GLICO_BACKGROUND,
    timeout: kind === "audio" ? 55000 : 30000,
    method: "POST",
    signal,
    headers: {
      "Content-Type": "application/octet-stream",
      "X-MyGlico-CSRF": await glicoCsrfToken(),
      "X-Glico-Context-Version": String(contextVersion),
      "X-Glico-Request-Id": clientRequestId
    },
    body: blob
  });
  try {
    return await send();
  } catch (error) {
    if (error?.status === 403 && error.detail === "csrf_failed") {
      resetGlicoCsrf();
      return send();
    }
    throw error;
  }
}
