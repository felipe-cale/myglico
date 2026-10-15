import { lazy, Suspense } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import AppShell from "./components/AppShell";
import GlobalLoading from "./components/GlobalLoading";
import { useLoadingHold } from "./loadingStore";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import ErrorPage from "./pages/ErrorPage";
import ErrorBoundary from "./components/ErrorBoundary";
import { useAuth, AuthProvider } from "./contexts/AuthContext";

// Authenticated pages (and recharts, through the detail page) load on demand; public pages stay in the entry chunk.
const OverviewPage = lazy(() => import("./pages/OverviewPage"));
const PatientDetailPage = lazy(() => import("./pages/PatientDetailPage"));
const InvestigationPage = lazy(() => import("./pages/InvestigationPage"));
const GlicoAssistantPage = lazy(() => import("./pages/GlicoAssistantPage"));

function PageFallback() {
  useLoadingHold();
  return <div className="react-page" aria-busy="true" />;
}

function ProtectedRoute({ children, role }) {
  const { session, loading } = useAuth();
  if (loading) return <PageFallback />;
  if (!session?.authenticated) return <Navigate to="/login" replace />;
  if (role && session.account?.roles && !session.account.roles.includes(role)) {
     return <Navigate to="/" replace />;
  }
  return children;
}

function PublicRoute({ children }) {
  const { session, loading } = useAuth();
  if (loading) return <PageFallback />;
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
        <Route path="/glico" element={<ProtectedRoute><GlicoAssistantPage /></ProtectedRoute>} />
        <Route path="/dashboard" element={<ProtectedRoute><OverviewPage /></ProtectedRoute>} />
        <Route path="/patients/:patientId" element={<ProtectedRoute><PatientDetailPage /></ProtectedRoute>} />

        <Route path="/erro" element={<ErrorPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

// Reset the boundary on navigation so leaving the error screen works.
function GuardedRoutes() {
  const location = useLocation();
  return (
    <ErrorBoundary key={location.pathname}>
      <MainRoutes />
    </ErrorBoundary>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell>
        <GuardedRoutes />
      </AppShell>
      <GlobalLoading />
    </AuthProvider>
  );
}
