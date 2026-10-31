import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listRuns, type RunSummary } from "../api";

export function History() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listRuns()
      .then((r) => setRuns(r.runs))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="page-head">
        <h1>History</h1>
        <p>Past runs stored in the cloud. Open one to see the map, receipt, and diff.</p>
      </div>

      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">{error}</p>}

      {!loading && !error && (
        <div className="panel table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Status</th>
                <th>Scenes</th>
                <th>Collection</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>{r.created_at ? new Date(r.created_at).toLocaleString() : "—"}</td>
                  <td>
                    <span className={`pill ${r.status === "reused" ? "reused" : ""}`}>
                      {r.status}
                    </span>
                  </td>
                  <td>{r.input_count}</td>
                  <td className="mono">{r.collection}</td>
                  <td>
                    <Link to={`/runs/${r.id}`}>Open</Link>
                  </td>
                </tr>
              ))}
              {!runs.length && (
                <tr>
                  <td colSpan={5} className="muted">
                    Nothing here yet. <Link to="/run">Run a search</Link>.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
