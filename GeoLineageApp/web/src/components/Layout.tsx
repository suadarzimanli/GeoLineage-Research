import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { health, type AppStatus } from "../api";

const STATUS_POLL_MS = 60_000;

export function Layout() {
  const [status, setStatus] = useState<AppStatus | null>(null);

  const refreshStatus = useCallback(() => {
    void health()
      .then((s) => setStatus(s))
      .catch(() => {
        /* keep last known status */
      });
  }, []);

  useEffect(() => {
    refreshStatus();
    const id = window.setInterval(refreshStatus, STATUS_POLL_MS);
    const onVis = () => {
      if (document.visibilityState === "visible") refreshStatus();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [refreshStatus]);

  return (
    <div className="shell">
      <header className="topnav">
        <NavLink to="/" className="brand">
          GeoLineage
        </NavLink>
        <nav className="nav-links">
          <NavLink to="/run" className={({ isActive }) => (isActive ? "active" : "")}>
            Run
          </NavLink>
          <NavLink to="/history" className={({ isActive }) => (isActive ? "active" : "")}>
            History
          </NavLink>
          <NavLink to="/about" className={({ isActive }) => (isActive ? "active" : "")}>
            About
          </NavLink>
          <NavLink to="/admin" className={({ isActive }) => (isActive ? "active" : "")}>
            Admin
          </NavLink>
        </nav>
      </header>
      {status?.closed && (
        <div className="status-banner" role="status">
          App is closed near free-tier limits
          {status.reason ? ` — ${status.reason}` : "."} History stays readable; new runs are blocked
          until an admin reopens.
        </div>
      )}
      <Outlet context={{ appStatus: status }} />
    </div>
  );
}
