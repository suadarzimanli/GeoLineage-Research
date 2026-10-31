import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  adminDeleteRun,
  adminGetStatus,
  adminKeepalive,
  adminListRuns,
  adminLogin,
  adminSetStatus,
  clearAdminToken,
  getAdminToken,
  type AppStatus,
  type RunSummary,
} from "../api";

export function Admin() {
  const [token, setToken] = useState<string | null>(() => getAdminToken());
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingRuns, setLoadingRuns] = useState(false);

  const refreshStatus = useCallback(async () => {
    const data = await adminGetStatus();
    setStatus(data);
  }, []);

  const refreshRuns = useCallback(async () => {
    setLoadingRuns(true);
    setError(null);
    try {
      const [runsData] = await Promise.all([adminListRuns(), refreshStatus()]);
      setRuns(runsData.runs);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      if (msg.toLowerCase().includes("unauthorized")) {
        clearAdminToken();
        setToken(null);
      }
    } finally {
      setLoadingRuns(false);
    }
  }, [refreshStatus]);

  useEffect(() => {
    if (token) void refreshRuns();
  }, [token, refreshRuns]);

  async function onLogin(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session = await adminLogin(username, password);
      setToken(session.token);
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function onLogout() {
    clearAdminToken();
    setToken(null);
    setRuns([]);
    setStatus(null);
  }

  async function onDelete(id: string) {
    if (!window.confirm(`Delete run ${id.slice(0, 8)}…? This cannot be undone.`)) return;
    setBusy(true);
    setError(null);
    try {
      await adminDeleteRun(id);
      setRuns((prev) => prev.filter((r) => r.id !== id));
      await refreshStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onSetStatus(next: "open" | "closed") {
    setBusy(true);
    setError(null);
    try {
      const data = await adminSetStatus(
        next,
        next === "closed" ? "Closed manually by admin" : undefined
      );
      setStatus({ ...data, closed: data.status === "closed", status: data.status });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onKeepalive() {
    setBusy(true);
    setError(null);
    try {
      await adminKeepalive();
      await refreshStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <div>
        <div className="page-head">
          <h1>Admin</h1>
          <p>Sign in to manage stored runs and free-tier controls.</p>
        </div>
        <form className="panel stack" onSubmit={onLogin} style={{ maxWidth: 420 }}>
          <label>
            Username
            <input
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error && <p className="error">{error}</p>}
          <button className="btn btn-primary" type="submit" disabled={busy}>
            {busy ? "Checking…" : "Sign in"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div>
      <div className="page-head">
        <h1>Admin</h1>
        <p>Delete runs, reopen after soft limits, and ping Supabase keepalive.</p>
      </div>

      <div className="panel stack" style={{ marginBottom: "1.25rem" }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Free-tier control</h2>
        <p className="muted" style={{ margin: 0 }}>
          Status: <strong>{status?.status ?? "…"}</strong>
          {status?.closed && status.reason ? ` — ${status.reason}` : ""}
        </p>
        <p className="muted" style={{ margin: 0 }}>
          Runs: {status?.runs_count ?? "—"} / {status?.max_runs ?? "—"} · Requests today:{" "}
          {status?.requests_today ?? "—"} / {status?.max_requests_per_day ?? "—"} · Last DB
          activity:{" "}
          {status?.last_activity_at
            ? new Date(status.last_activity_at).toLocaleString()
            : "—"}
        </p>
        <div className="cta-row">
          <button
            className="btn btn-primary"
            type="button"
            disabled={busy || status?.status === "open"}
            onClick={() => void onSetStatus("open")}
          >
            Reopen app
          </button>
          <button
            className="btn btn-ghost"
            type="button"
            disabled={busy || status?.status === "closed"}
            onClick={() => void onSetStatus("closed")}
          >
            Close app
          </button>
          <button
            className="btn btn-ghost"
            type="button"
            disabled={busy}
            onClick={() => void onKeepalive()}
          >
            Ping keepalive
          </button>
        </div>
      </div>

      <div className="cta-row">
        <button
          className="btn btn-ghost"
          type="button"
          onClick={() => void refreshRuns()}
          disabled={loadingRuns || busy}
        >
          {loadingRuns ? "Refreshing…" : "Refresh"}
        </button>
        <button className="btn btn-ghost" type="button" onClick={onLogout}>
          Sign out
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="panel table-wrap">
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Status</th>
              <th>Scenes</th>
              <th>Collection</th>
              <th>Id</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id}>
                <td>{r.created_at ? new Date(r.created_at).toLocaleString() : "—"}</td>
                <td>{r.status}</td>
                <td>{r.input_count}</td>
                <td className="mono">{r.collection}</td>
                <td className="mono">{r.id.slice(0, 8)}…</td>
                <td>
                  <button
                    className="btn btn-ghost"
                    type="button"
                    disabled={busy}
                    onClick={() => void onDelete(r.id)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {!runs.length && !loadingRuns && (
              <tr>
                <td colSpan={6} className="muted">
                  No runs.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
