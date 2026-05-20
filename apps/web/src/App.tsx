import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import { LoginPage } from "./components/auth/LoginPage";
import { AppShell } from "./components/layout/AppShell";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { PerformancePage } from "./pages/PerformancePage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { RiskPage } from "./pages/RiskPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { RunsPage } from "./pages/RunsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TradesPage } from "./pages/TradesPage";
import { WorkbenchPage } from "./pages/WorkbenchPage";

export function App() {
  const [token, setToken] = useState(() => localStorage.getItem("ta_token"));

  if (!token) {
    return (
      <LoginPage
        onLogin={(nextToken) => {
          localStorage.setItem("ta_token", nextToken);
          setToken(nextToken);
        }}
      />
    );
  }

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<WorkbenchPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunDetailPage />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/performance" element={<PerformancePage />} />
        <Route path="/trades" element={<TradesPage />} />
        <Route path="/risk" element={<RiskPage />} />
        <Route path="/approvals" element={<ApprovalsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
