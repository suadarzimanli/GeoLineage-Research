// Minimal in-memory stand-in for the Supabase REST + Storage calls the Worker makes, for local
// end-to-end tests:  node test/mock-supabase.mjs  (port 54321), then
//   npx wrangler dev --var SUPABASE_URL:http://127.0.0.1:54321 --var SUPABASE_SERVICE_ROLE_KEY:test
import http from "node:http";
import { randomUUID } from "node:crypto";

const db = { runs: [], lineage_receipts: [], keepalive: [], app_control: [] };
const storage = new Map();
const PORT = Number(process.env.PORT || 54321);

function filterRows(rows, params) {
  let out = rows;
  for (const [k, v] of params) {
    if (["select", "order", "limit"].includes(k)) continue;
    if (v.startsWith("eq.")) out = out.filter((r) => String(r[k]) === decodeURIComponent(v.slice(3)));
    else if (v.startsWith("in.(")) {
      const set = v.slice(4, -1).split(",");
      out = out.filter((r) => set.includes(String(r[k])));
    } else if (v.startsWith("lt.")) out = out.filter((r) => String(r[k]) < decodeURIComponent(v.slice(3)));
  }
  const order = params.get("order");
  if (order) {
    const [col, dir] = order.split(".");
    out = [...out].sort((a, b) => (a[col] < b[col] ? -1 : a[col] > b[col] ? 1 : 0) * (dir === "desc" ? -1 : 1));
  }
  const limit = Number(params.get("limit") || 0);
  return limit ? out.slice(0, limit) : out;
}

function send(res, status, body, headers = {}) {
  res.writeHead(status, { "Content-Type": "application/json", ...headers });
  res.end(body === undefined ? "" : JSON.stringify(body));
}

let clock = 0;
const now = () => new Date(Date.UTC(2026, 0, 1) + ++clock * 1000).toISOString();

http
  .createServer(async (req, res) => {
    const url = new URL(req.url, "http://x");
    let body = "";
    for await (const c of req) body += c;
    const p = url.pathname;

    if (p.startsWith("/storage/v1/object/")) {
      const key = p.replace("/storage/v1/object/public/", "").replace("/storage/v1/object/", "");
      if (req.method === "POST") { storage.set(key, body); return send(res, 200, { Key: key }); }
      if (req.method === "DELETE") { storage.delete(key); return send(res, 200, {}); }
      if (!storage.has(key)) return send(res, 404, { error: "not found" });
      res.writeHead(200, { "Content-Type": "application/geo+json" });
      return res.end(storage.get(key));
    }
    if (p === "/rest/v1/rpc/app_control_bump_request") {
      const row = db.app_control[0];
      row.requests_today += 1;
      return send(res, 200, row);
    }
    const table = p.replace("/rest/v1/", "");
    const rows = db[table];
    if (!rows) return send(res, 404, { error: "no table " + table });
    if (req.method === "HEAD") {
      return send(res, 200, undefined, { "content-range": `0-0/${rows.length}` });
    }
    if (req.method === "GET") return send(res, 200, filterRows(rows, url.searchParams));
    if (req.method === "POST") {
      const obj = JSON.parse(body || "{}");
      const row = { id: table === "app_control" ? 1 : randomUUID(), created_at: now(), ...obj };
      if (table === "runs") row.search_params = obj.search_params ?? {};
      rows.push(row);
      return send(res, 201, [row]);
    }
    if (req.method === "PATCH") {
      const hit = filterRows(rows, url.searchParams);
      for (const r of hit) Object.assign(r, JSON.parse(body || "{}"));
      return send(res, 200, hit);
    }
    if (req.method === "DELETE") {
      const hit = new Set(filterRows(rows, url.searchParams));
      db[table] = rows.filter((r) => !hit.has(r));
      return send(res, 204);
    }
    return send(res, 405, { error: "method" });
  })
  .listen(PORT, () => console.log("mock supabase on", PORT));
