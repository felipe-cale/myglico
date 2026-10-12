const JSON_HEADERS = {
  Accept: "application/json",
  "Content-Type": "application/json"
};

async function requestJson(path, options = {}) {
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
  return requestJson("/api/auth/logout", { method: "POST" });
}
export function fetchSession() {
  return requestJson("/api/auth/session");
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
export function fetchInvestigationDetail(id, params = {}) {
  const q = new URLSearchParams(params).toString();
  return requestJson(`/api/investigations/${id}${q ? `?${q}` : ""}`);
}
export function createInvestigation(payload) {
  return requestJson("/api/investigations", { method: "POST", body: JSON.stringify(payload) });
}
export function sendInvestigationMessage(id, payload) {
  return requestJson(`/api/investigations/${id}/messages`, { method: "POST", body: JSON.stringify(payload) });
}
export function readInvestigation(id, up_to_sequence) {
  return requestJson(`/api/investigations/${id}/read`, { method: "POST", body: JSON.stringify({ up_to_sequence }) });
}
export function closeInvestigation(id, payload) {
  return requestJson(`/api/investigations/${id}/close`, { method: "POST", body: JSON.stringify(payload) });
}

// === ATYPICAL DAYS ===
export function fetchAtypicalDays(patientId, params = {}) {
  const q = new URLSearchParams(params).toString();
  return requestJson(`/api/patients/${patientId}/atypical-days?${q}`);
}
export function fetchAtypicalDayPrompts(patientId, params = {}) {
  const q = new URLSearchParams(params).toString();
  return requestJson(`/api/patients/${patientId}/atypical-day-prompts${q ? `?${q}` : ""}`);
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
  return requestJson(`/api/notifications?${q}`);
}
export function readNotification(id) {
  return requestJson(`/api/notifications/${id}/read`, { method: "POST" });
}
export function fetchUnreadSummary() {
  return requestJson("/api/notifications/unread-summary");
}

// === LEGACY ===
export function fetchDashboardSummary() {
  return requestJson("/api/dashboard");
}
export function fetchPatients({ page = 1, pageSize = 10, query = "", signal = "all" }) {
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  if (query) params.set("q", query);
  if (signal && signal !== "all") params.set("signal", signal);
  return requestJson(`/api/patients?${params.toString()}`);
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
