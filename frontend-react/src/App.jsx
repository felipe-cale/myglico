import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import AppShell from "./components/AppShell";
import GlobalLoading from "./components/GlobalLoading";
import StateBlock from "./components/StateBlock";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import { useAuth, AuthProvider } from "./contexts/AuthContext";

// Authenticated pages (and recharts, through the detail page) load on demand; public pages stay in the entry chunk.
const OverviewPage = lazy(() => import("./pages/OverviewPage"));
const PatientDetailPage = lazy(() => import("./pages/PatientDetailPage"));
const InvestigationPage = lazy(() => import("./pages/InvestigationPage"));

function PageFallback() {
  const { t } = useTranslation();
  return (
    <div className="react-page" role="status">
      <StateBlock title={t("common.loading")} tone="info" />
    </div>
  );
}

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
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/" element={<PublicRoute><LandingPage /></PublicRoute>} />
        <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
        <Route path="/register" element={<PublicRoute><RegisterPage /></PublicRoute>} />

        <Route path="/investigations/:id" element={<ProtectedRoute><InvestigationPage /></ProtectedRoute>} />
        <Route path="/dashboard" element={<ProtectedRoute><OverviewPage /></ProtectedRoute>} />
        <Route path="/patients/:patientId" element={<ProtectedRoute><PatientDetailPage /></ProtectedRoute>} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell>
        <MainRoutes />
      </AppShell>
      <GlobalLoading />
    </AuthProvider>
  );
}
