import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import OverviewPage from "./pages/OverviewPage";
import PatientDetailPage from "./pages/PatientDetailPage";
import SemanticPage from "./pages/SemanticPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/patients/:patientId" element={<PatientDetailPage />} />
        <Route path="/semantic" element={<SemanticPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
