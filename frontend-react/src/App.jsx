import { Routes, Route, Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import AppShell from "./components/AppShell";
import OverviewPage from "./pages/OverviewPage";
import PatientDetailPage from "./pages/PatientDetailPage";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import InvestigationPage from "./pages/InvestigationPage";
import { useAuth, AuthProvider } from "./contexts/AuthContext";

function ProtectedRoute({ children, role }) {
  const { t } = useTranslation();
  const { session, loading } = useAuth();
  if (loading) return <div role="status">{t("common.loading")}</div>;
  if (!session?.authenticated) return <Navigate to="/login" replace />;
  if (role && session.account?.roles && !session.account.roles.includes(role)) {
     return <Navigate to="/" replace />;
  }
  return children;
}

function PublicRoute({ children }) {
  const { t } = useTranslation();
  const { session, loading } = useAuth();
  if (loading) return <div role="status">{t("common.loading")}</div>;
  if (session?.authenticated) return <Navigate to="/dashboard" replace />;
  return children;
}

function MainRoutes() {
  return (
    <Routes>
      <Route path="/" element={<PublicRoute><LandingPage /></PublicRoute>} />
      <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
      <Route path="/register" element={<PublicRoute><RegisterPage /></PublicRoute>} />

      <Route path="/investigations/:id" element={<ProtectedRoute><InvestigationPage /></ProtectedRoute>} />
      <Route path="/dashboard" element={<ProtectedRoute><OverviewPage /></ProtectedRoute>} />
      <Route path="/patients/:patientId" element={<ProtectedRoute><PatientDetailPage /></ProtectedRoute>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell>
        <MainRoutes />
      </AppShell>
    </AuthProvider>
  );
}
