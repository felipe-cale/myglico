// Frontend routes, reconciled with the real router in src/App.jsx:
//   public: /, /login, /register
//   private: /dashboard (overview + links + investigations + notifications),
//            /patients/:patientId, /investigations/:id
// Any unknown path falls back to "/" — there are no standalone
// /doctors, /notifications or /investigations list pages.
export const ROUTES = {
  landing: "/",
  login: "/login",
  register: "/register",
  dashboard: "/dashboard",
  investigation: (id) => `/investigations/${id}`,
  patientDetail: (patientId) => `/patients/${patientId}`,
  patientDetailQuery: (patientId, search = "") => `/patients/${patientId}${search}`,
};

// Legacy/pre-auth endpoints probed by the guardrail scenarios (AUT-CA-02,
// AUT-CA-12, AUT-CA-13): hiding them in the UI is not enough, the API itself
// must deny anonymous or unauthorized access.
export const LEGACY_API = {
  dashboard: "/api/dashboard",
  patients: "/api/patients",
  patient: (patientId) => `/api/patients/${patientId}`,
  patientReportPdf: (patientId) => `/api/patients/${patientId}/report.pdf`,
  patientGlucoseRecords: (patientId) => `/api/patients/${patientId}/glucose-records`,
};
