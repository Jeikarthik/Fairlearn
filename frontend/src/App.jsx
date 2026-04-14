import { useEffect, useMemo, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { createApiClient } from "./api/client";
import DashboardPage from "./pages/DashboardPage";
import AuditStudioPage from "./pages/AuditStudioPage";
import ApiProbePage from "./pages/ApiProbePage";
import NlpProbePage from "./pages/NlpProbePage";
import MonitoringPage from "./pages/MonitoringPage";
import HistoryPage from "./pages/HistoryPage";

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

export default function App() {
  const [apiBase, setApiBase] = useStoredState("fairlens_api_base", DEFAULT_API_BASE);
  const [health, setHealth] = useState({ status: "checking", detail: "Connecting to backend..." });
  const api = useMemo(() => createApiClient(apiBase), [apiBase]);

  useEffect(() => {
    let active = true;
    async function ping() {
      setHealth({ status: "checking", detail: "Connecting to backend..." });
      try {
        const response = await api.health();
        if (!active) {
          return;
        }
        setHealth({
          status: response.status === "ok" ? "online" : "warning",
          detail: response.status === "ok" ? "Backend is reachable." : "Backend responded unexpectedly.",
        });
      } catch (error) {
        if (!active) {
          return;
        }
        setHealth({
          status: "offline",
          detail: error.message || "Backend connection failed.",
        });
      }
    }
    ping();
    return () => {
      active = false;
    };
  }, [api]);

  return (
    <Layout apiBase={apiBase} onApiBaseChange={setApiBase} health={health}>
      <Routes>
        <Route path="/" element={<DashboardPage api={api} health={health} />} />
        <Route path="/audit" element={<AuditStudioPage api={api} />} />
        <Route path="/probe" element={<ApiProbePage api={api} />} />
        <Route path="/language-probe" element={<NlpProbePage api={api} />} />
        <Route path="/monitor" element={<MonitoringPage api={api} />} />
        <Route path="/history" element={<HistoryPage api={api} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
