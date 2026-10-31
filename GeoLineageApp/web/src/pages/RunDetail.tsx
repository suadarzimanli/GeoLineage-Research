import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { getRun, type CreateRunResult, type RunDetail as RunDetailType } from "../api";
import { FootprintMap } from "../components/FootprintMap";

function safeHttpsUrl(href: string | null | undefined): string | null {
  if (!href) return null;
  try {
    const u = new URL(href);
    if (u.protocol !== "https:") return null;
    return u.toString();
  } catch {
    return null;
  }
}

function downloadText(filename: string, text: string, mime: string) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function downloadJson(filename: string, data: unknown) {
  downloadText(filename, `${JSON.stringify(data, null, 2)}\n`, "application/json");
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function RunDetail() {
  const { id } = useParams();
  const location = useLocation();
  const seeded = location.state as CreateRunResult | null;
  const seedMatches = Boolean(id && seeded?.run?.id === id);
  const [data, setData] = useState<RunDetailType | CreateRunResult | null>(seedMatches ? seeded : null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [copyNote, setCopyNote] = useState<string | null>(null);

  useEffect(() => {
    if (!id) {
      setError("Missing run id");
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    if (seedMatches && seeded) {
      setData(seeded);
    }
    getRun(id)
      .then((fresh) => {
        if (cancelled) return;
        setData({
          ...fresh,
          footprints: fresh.footprints ?? (seedMatches ? seeded?.footprints ?? null : null),
          diff: fresh.diff ?? (seedMatches ? seeded?.diff ?? null : null),
        });
      })
      .catch((err) => {
        if (!cancelled && !seedMatches) {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id, seedMatches, seeded]);

  async function flashCopy(label: string, text: string) {
    const ok = await copyText(text);
    setCopyNote(ok ? `${label} copied` : `Could not copy ${label.toLowerCase()}`);
    window.setTimeout(() => setCopyNote(null), 2000);
  }

  if (loading && !data) return <p className="muted">Loading run…</p>;
  if (error && !data) return <p className="error">{error}</p>;
  if (!data) return <p className="error">Run not found.</p>;

  const run = data.run;
  const footprints = "footprints" in data ? data.footprints : null;
  const receipt = "receipt" in data ? data.receipt : null;
  const diff = "diff" in data ? data.diff : null;
  const outputHref = safeHttpsUrl(run.output_path);
  const idSlice = run.id.slice(0, 8);
  const receiptText = receipt ? `${JSON.stringify(receipt, null, 2)}\n` : "";

  return (
    <div className="stack">
      <div className="page-head">
        <h1>This run</h1>
        <p>
          <span className={`pill ${run.status === "reused" ? "reused" : ""}`}>{run.status}</span>{" "}
          <span className="mono muted">{run.id}</span>
          {loading && <span className="muted"> · refreshing…</span>}
        </p>
      </div>

      <div className="panel stack">
        <div>
          <strong>{run.input_count}</strong> scenes · collection <code>{run.collection}</code>
          {run.reused_from_run_id && (
            <>
              {" "}
              · reused from{" "}
              <Link to={`/runs/${run.reused_from_run_id}`}>{run.reused_from_run_id.slice(0, 8)}…</Link>
            </>
          )}
        </div>
        {outputHref ? (
          <p className="mono muted" style={{ margin: 0 }}>
            Output:{" "}
            <a href={outputHref} target="_blank" rel="noreferrer">
              footprints.geojson
            </a>
            {run.output_checksum ? ` · sha256 ${run.output_checksum.slice(0, 16)}…` : ""}
          </p>
        ) : run.output_path ? (
          <p className="mono muted" style={{ margin: 0 }}>
            Output link skipped (not https).
          </p>
        ) : null}
        {!footprints && run.output_path && (
          <p className="muted" style={{ margin: 0 }}>
            Could not load the footprint file. The map still shows the search box.
          </p>
        )}
        <FootprintMap footprints={footprints} bbox={run.bbox} />
      </div>

      {diff && (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Compared with the previous similar run</h2>
          <p className="muted">
            Added {diff.added.length}, removed {diff.removed.length}, unchanged {diff.unchanged.length}
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Change</th>
                  <th>Scene id</th>
                </tr>
              </thead>
              <tbody>
                {diff.added.map((x) => (
                  <tr key={`a-${x}`}>
                    <td>added</td>
                    <td className="mono">{x}</td>
                  </tr>
                ))}
                {diff.removed.map((x) => (
                  <tr key={`r-${x}`}>
                    <td>removed</td>
                    <td className="mono">{x}</td>
                  </tr>
                ))}
                {!diff.added.length && !diff.removed.length && (
                  <tr>
                    <td colSpan={2} className="muted">
                      Same scene ids as before.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="panel stack">
        <h2 style={{ marginTop: 0 }}>Receipt (JSON)</h2>
        <p className="muted" style={{ margin: 0 }}>
          Retrospective record of one run: search params → input scenes → one transform → output
          file and checksum.
        </p>

        <div className="receipt-guide">
          <p style={{ margin: "0 0 0.5rem" }}>
            <strong>How to use this</strong>
          </p>
          <ul>
            <li>
              Download the receipt to cite how a map or result was produced (catalog, bbox,
              collection, scene ids).
            </li>
            <li>
              Download footprints GeoJSON as the product; compare its hash to{" "}
              <code>output_assets[].checksum</code> (or Copy checksum) to check integrity.
            </li>
            <li>
              <code>search_params</code> and <code>input_assets</code> are the sources;{" "}
              <code>transform_steps</code> is the process; <code>output_assets</code> is what was
              written.
            </li>
            <li>
              <code>reused_from_run_id</code> means this run pointed at an earlier output instead of
              writing new bytes. The scene diff above is separate—it is not inside the receipt file.
            </li>
            <li>
              <code>lineage_dag</code> is a tiny graph of that pipeline for this demo (not a full
              PROV or OpenLineage export).
            </li>
          </ul>
        </div>

        <div className="cta-row receipt-actions">
          <button
            className="btn btn-primary"
            type="button"
            disabled={!receipt}
            onClick={() => receipt && downloadJson(`geolineage-receipt-${idSlice}.json`, receipt)}
          >
            Download receipt
          </button>
          <button
            className="btn btn-ghost"
            type="button"
            disabled={!receipt}
            onClick={() => void flashCopy("Receipt", receiptText)}
          >
            Copy receipt
          </button>
          {footprints && (
            <button
              className="btn btn-ghost"
              type="button"
              onClick={() =>
                downloadText(
                  `geolineage-footprints-${idSlice}.geojson`,
                  `${JSON.stringify(footprints, null, 2)}\n`,
                  "application/geo+json"
                )
              }
            >
              Download footprints
            </button>
          )}
          {run.output_checksum && (
            <button
              className="btn btn-ghost"
              type="button"
              onClick={() => void flashCopy("Checksum", run.output_checksum!)}
            >
              Copy checksum
            </button>
          )}
        </div>
        {copyNote && (
          <p className="muted" style={{ margin: 0 }} role="status">
            {copyNote}
          </p>
        )}

        <pre className="receipt">{receipt ? JSON.stringify(receipt, null, 2) : "No receipt."}</pre>
      </div>

      <div className="cta-row">
        <Link className="btn btn-ghost" to="/history">
          All runs
        </Link>
        <Link className="btn btn-primary" to="/run">
          New run
        </Link>
      </div>
    </div>
  );
}
