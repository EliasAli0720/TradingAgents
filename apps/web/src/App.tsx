import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import { LoginPage } from "./components/auth/LoginPage";
import { AppShell } from "./components/layout/AppShell";

function Placeholder({ title }: { title: string }) {
  return <h2>{title}</h2>;
}

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
        <Route index element={<Placeholder title="Workbench" />} />
        <Route path="/runs" element={<Placeholder title="Runs" />} />
        <Route path="/portfolio" element={<Placeholder title="Portfolio" />} />
        <Route path="/performance" element={<Placeholder title="Performance" />} />
        <Route path="/trades" element={<Placeholder title="Trades" />} />
        <Route path="/risk" element={<Placeholder title="Risk" />} />
        <Route path="/approvals" element={<Placeholder title="Approvals" />} />
        <Route path="/settings" element={<Placeholder title="Settings" />} />
      </Route>
    </Routes>
  );
}
