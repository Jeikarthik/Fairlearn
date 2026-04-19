import { useEffect, useMemo, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ErrorBoundary from "./components/ErrorBoundary";
import { createApiClient } from "./api/client";
import { AuthProvider, useAuth } from "./context/AuthContext";
import DashboardPage from "./pages/DashboardPage";
import AuditStudioPage from "./pages/AuditStudioPage";
import ApiProbePage from "./pages/ApiProbePage";
import NlpProbePage from "./pages/NlpProbePage";
import MonitoringPage from "./pages/MonitoringPage";
import HistoryPage from "./pages/HistoryPage";
import LoginPage from "./pages/LoginPage";

const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";

function useStoredState(key, initialValue) {
  const [value, setValue] = useState(() => {
    const stored = window.localStorage.getItem(key);
    return stored ?? initialValue;
  });

  useEffect(() => {
    window.localStorage.setItem(key, value);
  }, [key, value]);

  return [value, setValue];
}

function AppRoutes({ apiBase, setApiBase }) {
  const { token, authRequired, logout } = useAuth();
  const [health, setHealth] = useState({ status: "checking", detail: "Connecting to backend..." });

  const api = useMemo(
    () =>
      createApiClient(apiBase, {
        getToken: () => token,
        onUnauthorized: () => logout(),
      }),
    [apiBase, token, logout]
  );

  useEffect(() => {
    let active = true;
    async function ping() {
      setHealth({ status: "checking", detail: "Connecting to backend..." });
      try {
        const response = await api.health();
        if (!active) return;
        setHealth({
          status: response.status === "ok" ? "online" : "warning",
          detail: response.status === "ok" ? "Backend is reachable." : "Backend responded unexpectedly.",
        });
      } catch (error) {
        if (!active) return;
        setHealth({
          status: "offline",
          detail: error.message || "Backend connection failed.",
        });
      }
    }
    ping();
    return () => { active = false; };
  }, [api]);

  // If auth is required and we're not authenticated, show login
  if (authRequired) {
    return <LoginPage />;
  }

  return (
    <Layout apiBase={apiBase} onApiBaseChange={setApiBase} health={health}>
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<ErrorBoundary><DashboardPage api={api} health={health} /></ErrorBoundary>} />
          <Route path="/audit" element={<ErrorBoundary><AuditStudioPage api={api} /></ErrorBoundary>} />
          <Route path="/probe" element={<ErrorBoundary><ApiProbePage api={api} /></ErrorBoundary>} />
          <Route path="/language-probe" element={<ErrorBoundary><NlpProbePage api={api} /></ErrorBoundary>} />
          <Route path="/monitor" element={<ErrorBoundary><MonitoringPage api={api} /></ErrorBoundary>} />
          <Route path="/history" element={<ErrorBoundary><HistoryPage api={api} /></ErrorBoundary>} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </ErrorBoundary>
    </Layout>
  );
}

export default function App() {
  const [apiBase, setApiBase] = useStoredState("fairlens_api_base", DEFAULT_API_BASE);

  return (
    <AuthProvider apiBase={apiBase}>
      <AppRoutes apiBase={apiBase} setApiBase={setApiBase} />
    </AuthProvider>
  );
}
