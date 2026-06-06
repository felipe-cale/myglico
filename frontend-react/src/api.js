const JSON_HEADERS = {
  Accept: "application/json"
};

async function requestJson(path) {
  const response = await fetch(path, { headers: JSON_HEADERS });
  if (!response.ok) {
    throw new Error(`Falha ao carregar ${path}: ${response.status}`);
  }
  return response.json();
}

export function fetchDashboardSummary() {
  return requestJson("/api/dashboard");
}

export function fetchPatients({ page = 1, pageSize = 12, query = "", signal = "all" }) {
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  if (query) {
    params.set("q", query);
  }
  if (signal && signal !== "all") {
    params.set("signal", signal);
  }
  return requestJson(`/api/patients?${params.toString()}`);
}

export function fetchPatientDetail(patientId, { startDate, endDate } = {}) {
  const params = new URLSearchParams();
  if (startDate) {
    params.set("start_date", startDate);
  }
  if (endDate) {
    params.set("end_date", endDate);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson(`/api/patients/${patientId}${suffix}`);
}

export function patientReportPdfUrl(patientId, { startDate, endDate }) {
  if (!patientId || !startDate || !endDate) {
    return null;
  }

  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate
  });
  return `/api/patients/${encodeURIComponent(patientId)}/report.pdf?${params.toString()}`;
}

export function fetchSemanticQueries() {
  return requestJson("/api/semantic/queries");
}

export function fetchSemanticResult(name) {
  return requestJson(`/api/semantic/query?name=${encodeURIComponent(name)}`);
}
