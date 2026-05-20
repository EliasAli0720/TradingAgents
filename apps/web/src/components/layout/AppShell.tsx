import { NavLink, Outlet } from "react-router-dom";

const nav = [
  ["Workbench", "/"],
  ["Runs", "/runs"],
  ["Portfolio", "/portfolio"],
  ["Performance", "/performance"],
  ["Trades", "/trades"],
  ["Risk", "/risk"],
  ["Approvals", "/approvals"],
  ["Settings", "/settings"],
] as const;

export function AppShell() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>TradingAgents</h1>
        <nav>
          {nav.map(([label, to]) => (
            <NavLink key={to} to={to}>
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <section className="content-panel">
        <Outlet />
      </section>
    </div>
  );
}
