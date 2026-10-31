/**
 * Thin GeoLineage API for Cloudflare Workers Free.
 * - Proxy STAC search (CORS + keep CPU light; network wait does not count as CPU)
 * - Persist runs / receipts / GeoJSON footprints to Supabase
 * - Diff + minimum-recompute (reuse prior output when input ids match)
 */

export interface Env {
  SUPABASE_URL: string;
  SUPABASE_SERVICE_ROLE_KEY: string;
  DEFAULT_CATALOG_URL: string;
  DEFAULT_COLLECTION: string;
  /** Comma-separated browser origins. Empty = permissive (local wrangler). */
  ALLOWED_ORIGINS?: string;
  /** Admin panel credentials — Worker secrets only, never ship in the SPA. */
  ADMIN_USERNAME?: string;
  ADMIN_PASSWORD?: string;
  /** HMAC secret for admin session tokens. */
  ADMIN_SESSION_SECRET?: string;
  /** Soft free-tier caps (wrangler [vars]). */
  MAX_RUNS?: string;
  MAX_REQUESTS_PER_DAY?: string;
  KEEPALIVE_MAX_AGE_HOURS?: string;
}

interface AppControl {
  id: number;
  status: "open" | "closed";
  reason: string | null;
  requests_today: number;
  requests_day: string;
  updated_at?: string;
}

type BBox = [number, number, number, number];

interface SearchBody {
  catalog_url?: string;
  collection?: string;
  bbox: BBox;
  max_items?: number;
  datetime?: string;
}

interface ValidatedSearch {
  catalog_url: string;
  collection: string;
  bbox: BBox;
  max_items: number;
  datetime: string | null;
}

interface StacItem {
  id: string;
  geometry?: GeoJSON.Geometry | null;
  properties?: Record<string, unknown>;
  links?: { rel: string; href: string }[];
}

class HttpError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function normalizeOriginList(raw: string | undefined): string[] | null {
  if (!raw || !raw.trim()) return null;
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function corsHeaders(env: Env, origin: string | null): HeadersInit {
  const allowed = normalizeOriginList(env.ALLOWED_ORIGINS);
  const headers: Record<string, string> = {
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
  if (!allowed) {
    headers["Access-Control-Allow-Origin"] = origin || "*";
    return headers;
  }
  if (origin && allowed.includes(origin)) {
    headers["Access-Control-Allow-Origin"] = origin;
  }
  return headers;
}

function corsAllowed(env: Env, origin: string | null): boolean {
  const allowed = normalizeOriginList(env.ALLOWED_ORIGINS);
  if (!allowed) return true;
  if (!origin) return true; // non-browser / same-origin tools
  return allowed.includes(origin);
}

function json(data: unknown, status: number, env: Env, origin: string | null): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...corsHeaders(env, origin),
    },
  });
}

function clientError(err: unknown): { status: number; message: string } {
  if (err instanceof HttpError) return { status: err.status, message: err.message };
  if (err instanceof SyntaxError) return { status: 400, message: "Invalid JSON body" };
  const raw = err instanceof Error ? err.message : String(err);
  if (raw.startsWith("STAC search failed")) return { status: 502, message: "STAC catalog search failed" };
  if (raw.startsWith("Storage upload failed")) return { status: 502, message: "Storage upload failed" };
  if (raw.includes("aborted") || raw.includes("Timeout") || raw.includes("timeout")) {
    return { status: 504, message: "Upstream request timed out" };
  }
  return { status: 500, message: "Internal server error" };
}

function sha256Hex(bytes: BufferSource): Promise<string> {
  return crypto.subtle.digest("SHA-256", bytes).then((buf) =>
    [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("")
  );
}

function assertBbox(raw: unknown): BBox {
  if (!Array.isArray(raw) || raw.length !== 4) {
    throw new HttpError(400, "bbox [west,south,east,north] required");
  }
  const bbox = raw.map(Number) as BBox;
  if (bbox.some((n) => !Number.isFinite(n))) {
    throw new HttpError(400, "bbox values must be finite numbers");
  }
  const [west, south, east, north] = bbox;
  if (west >= east || south >= north) {
    throw new HttpError(400, "bbox must have west < east and south < north");
  }
  if (west < -180 || east > 180 || south < -90 || north > 90) {
    throw new HttpError(400, "bbox out of geographic range");
  }
  return bbox;
}

function sanitizeCollection(raw: unknown, fallback: string): string {
  const value = (typeof raw === "string" && raw.trim() ? raw.trim() : fallback).slice(0, 128);
  if (!/^[A-Za-z0-9._-]+$/.test(value)) {
    throw new HttpError(400, "collection must be alphanumeric with ._- only");
  }
  return value;
}

function clampMaxItems(raw: unknown): number {
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(n)) return 10;
  return Math.min(50, Math.max(1, Math.floor(n)));
}

function normalizeUrl(url: string): string {
  return url.replace(/\/$/, "");
}

function resolveCatalogUrl(body: SearchBody, env: Env): string {
  const allowed = normalizeUrl(env.DEFAULT_CATALOG_URL);
  if (!body.catalog_url || !String(body.catalog_url).trim()) return allowed;
  const requested = normalizeUrl(String(body.catalog_url).trim());
  if (requested !== allowed) {
    throw new HttpError(400, "catalog_url not allowed");
  }
  return allowed;
}

function sanitizeDatetime(raw: unknown): string | null {
  if (raw == null || raw === "") return null;
  if (typeof raw !== "string" || raw.length > 64) {
    throw new HttpError(400, "datetime must be a short STAC interval string");
  }
  return raw;
}

function validateSearchBody(body: SearchBody, env: Env): ValidatedSearch {
  return {
    catalog_url: resolveCatalogUrl(body, env),
    collection: sanitizeCollection(body.collection, env.DEFAULT_COLLECTION),
    bbox: assertBbox(body.bbox),
    max_items: clampMaxItems(body.max_items),
    datetime: sanitizeDatetime(body.datetime),
  };
}

async function parseJsonBody<T>(req: Request): Promise<T> {
  try {
    return (await req.json()) as T;
  } catch {
    throw new HttpError(400, "Invalid JSON body");
  }
}

async function supabaseFetch(
  env: Env,
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const url = `${normalizeUrl(env.SUPABASE_URL)}/rest/v1/${path}`;
  const headers = new Headers(init.headers);
  headers.set("apikey", env.SUPABASE_SERVICE_ROLE_KEY);
  headers.set("Authorization", `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`);
  headers.set("Content-Type", "application/json");
  if (!headers.has("Prefer")) headers.set("Prefer", "return=representation");
  return fetch(url, { ...init, headers, signal: AbortSignal.timeout(20_000) });
}

async function supabaseStorageUpload(
  env: Env,
  objectPath: string,
  body: ArrayBuffer | string,
  contentType: string
): Promise<void> {
  const url = `${normalizeUrl(env.SUPABASE_URL)}/storage/v1/object/outputs/${objectPath}`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      apikey: env.SUPABASE_SERVICE_ROLE_KEY,
      Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
      "Content-Type": contentType,
      "x-upsert": "true",
    },
    body,
    signal: AbortSignal.timeout(30_000),
  });
  if (!res.ok) {
    throw new Error(`Storage upload failed: ${res.status}`);
  }
}

function publicStorageUrl(env: Env, objectPath: string): string {
  return `${normalizeUrl(env.SUPABASE_URL)}/storage/v1/object/public/outputs/${objectPath}`;
}

function footprintsObjectPath(runId: string): string {
  return `${runId}/footprints.geojson`;
}

function trustedOutputsPrefix(env: Env): string {
  return `${normalizeUrl(env.SUPABASE_URL)}/storage/v1/object/public/outputs/`;
}

/** Only fetch footprints from our public outputs bucket (blocks stored SSRF). */
function resolveFootprintsFetchUrl(
  env: Env,
  runId: string,
  storedPath?: string | null,
  reusedFrom?: string | null
): string | null {
  const prefix = trustedOutputsPrefix(env);
  if (storedPath && storedPath.startsWith(prefix)) return storedPath;
  if (reusedFrom) return publicStorageUrl(env, footprintsObjectPath(reusedFrom));
  return publicStorageUrl(env, footprintsObjectPath(runId));
}

function stripStacItem(raw: unknown): StacItem | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;
  if (typeof item.id !== "string" || !item.id) return null;
  const props = (item.properties && typeof item.properties === "object"
    ? item.properties
    : {}) as Record<string, unknown>;
  const linksRaw = Array.isArray(item.links) ? item.links : [];
  const self = linksRaw.find(
    (l) => l && typeof l === "object" && (l as { rel?: string }).rel === "self"
  ) as { rel: string; href?: string } | undefined;
  return {
    id: item.id.slice(0, 256),
    geometry: (item.geometry as GeoJSON.Geometry | null) ?? null,
    properties: {
      datetime: props.datetime ?? null,
      start_datetime: props.start_datetime ?? null,
    },
    links: self?.href ? [{ rel: "self", href: String(self.href).slice(0, 2048) }] : [],
  };
}

async function searchStac(params: ValidatedSearch): Promise<StacItem[]> {
  const payload: Record<string, unknown> = {
    collections: [params.collection],
    bbox: params.bbox,
    limit: params.max_items,
  };
  if (params.datetime) payload.datetime = params.datetime;

  const res = await fetch(`${params.catalog_url}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/geo+json" },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(25_000),
  });
  if (!res.ok) {
    throw new Error(`STAC search failed: ${res.status}`);
  }

  const data = (await res.json()) as { features?: unknown };
  if (!data || !Array.isArray(data.features)) {
    throw new HttpError(502, "STAC catalog returned invalid response");
  }

  const out: StacItem[] = [];
  for (const f of data.features.slice(0, params.max_items)) {
    const item = stripStacItem(f);
    if (item) out.push(item);
  }
  return out;
}

function footprintsGeoJSON(features: StacItem[]): GeoJSON.FeatureCollection {
  const out: GeoJSON.Feature[] = [];
  for (const item of features) {
    if (!item.geometry) continue;
    const dt = item.properties?.datetime ?? item.properties?.start_datetime ?? null;
    out.push({
      type: "Feature",
      id: item.id,
      geometry: item.geometry,
      properties: {
        id: item.id,
        datetime: dt,
      },
    });
  }
  return { type: "FeatureCollection", features: out };
}

function inputIds(features: StacItem[]): string[] {
  return features.map((f) => f.id).sort();
}

function sameIdSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

async function getReceipt(env: Env, runId: string): Promise<Record<string, unknown> | null> {
  const res = await supabaseFetch(
    env,
    `lineage_receipts?run_id=eq.${encodeURIComponent(runId)}&select=receipt&order=created_at.desc&limit=1`
  );
  if (!res.ok) throw new HttpError(502, "Failed to load receipt");
  const rows = (await res.json()) as { receipt: Record<string, unknown> }[];
  return rows[0]?.receipt ?? null;
}

function receiptIds(receipt: Record<string, unknown> | null): string[] {
  return ((receipt?.input_assets as { id: string }[]) || []).map((a) => a.id).sort();
}

function diffIds(prev: string[], curr: string[]) {
  const p = new Set(prev);
  const c = new Set(curr);
  const added = curr.filter((id) => !p.has(id));
  const removed = prev.filter((id) => !c.has(id));
  const unchanged = curr.filter((id) => p.has(id));
  return { added, removed, unchanged };
}

async function findReusableRun(
  env: Env,
  catalog_url: string,
  collection: string,
  checksum: string,
  ids: string[]
): Promise<{ id: string; output_path: string } | null> {
  const q =
    `runs?select=id,output_path,output_checksum,status` +
    `&catalog_url=eq.${encodeURIComponent(catalog_url)}` +
    `&collection=eq.${encodeURIComponent(collection)}` +
    `&output_checksum=eq.${encodeURIComponent(checksum)}` +
    `&status=in.(complete,reused)` +
    `&order=created_at.desc&limit=5`;
  const res = await supabaseFetch(env, q);
  if (!res.ok) throw new HttpError(502, "Failed to query prior runs");
  const rows = (await res.json()) as {
    id: string;
    output_path?: string | null;
    output_checksum?: string | null;
  }[];

  for (const row of rows) {
    if (!row.output_path) continue;
    const prefix = `${normalizeUrl(env.SUPABASE_URL)}/storage/v1/object/public/outputs/`;
    if (!String(row.output_path).startsWith(prefix)) continue;
    const prevReceipt = await getReceipt(env, row.id);
    if (sameIdSet(receiptIds(prevReceipt), ids)) {
      return { id: row.id, output_path: String(row.output_path) };
    }
  }
  return null;
}

async function previousScopedRunId(
  env: Env,
  catalog_url: string,
  collection: string
): Promise<string | null> {
  const q =
    `runs?select=id` +
    `&catalog_url=eq.${encodeURIComponent(catalog_url)}` +
    `&collection=eq.${encodeURIComponent(collection)}` +
    `&order=created_at.desc&limit=1`;
  const res = await supabaseFetch(env, q);
  if (!res.ok) return null;
  const rows = (await res.json()) as { id: string }[];
  return rows[0]?.id ?? null;
}

async function markRunFailed(env: Env, runId: string): Promise<void> {
  await supabaseFetch(env, `runs?id=eq.${encodeURIComponent(runId)}`, {
    method: "PATCH",
    headers: { Prefer: "return=minimal" },
    body: JSON.stringify({ status: "failed" }),
  });
}

function maxRuns(env: Env): number {
  const n = Number(env.MAX_RUNS || 400);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 400;
}

function maxRequestsPerDay(env: Env): number {
  const n = Number(env.MAX_REQUESTS_PER_DAY || 80_000);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 80_000;
}

function keepaliveMaxAgeHours(env: Env): number {
  const n = Number(env.KEEPALIVE_MAX_AGE_HOURS || 72);
  return Number.isFinite(n) && n > 0 ? n : 72;
}

function utcToday(): string {
  return new Date().toISOString().slice(0, 10);
}

async function getAppControl(env: Env): Promise<AppControl | null> {
  if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_ROLE_KEY) return null;
  try {
    const res = await supabaseFetch(env, "app_control?id=eq.1&select=*");
    if (!res.ok) return null;
    const rows = (await res.json()) as AppControl[];
    return rows[0] ?? null;
  } catch {
    return null;
  }
}

async function ensureAppControl(env: Env): Promise<AppControl | null> {
  let row = await getAppControl(env);
  if (row) return row;
  try {
    const ins = await supabaseFetch(env, "app_control", {
      method: "POST",
      body: JSON.stringify({
        id: 1,
        status: "open",
        reason: null,
        requests_today: 0,
        requests_day: utcToday(),
      }),
    });
    if (!ins.ok) return null;
    const rows = (await ins.json()) as AppControl[];
    return rows[0] ?? null;
  } catch {
    return null;
  }
}

async function patchAppControl(
  env: Env,
  patch: Partial<AppControl>
): Promise<AppControl | null> {
  const res = await supabaseFetch(env, "app_control?id=eq.1", {
    method: "PATCH",
    body: JSON.stringify({ ...patch, updated_at: new Date().toISOString() }),
  });
  if (!res.ok) return null;
  const rows = (await res.json()) as AppControl[];
  return rows[0] ?? null;
}

async function countRuns(env: Env): Promise<number | null> {
  try {
    const url = `${normalizeUrl(env.SUPABASE_URL)}/rest/v1/runs?select=id`;
    const res = await fetch(url, {
      method: "HEAD",
      headers: {
        apikey: env.SUPABASE_SERVICE_ROLE_KEY,
        Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
        Prefer: "count=exact",
      },
      signal: AbortSignal.timeout(15_000),
    });
    const range = res.headers.get("content-range");
    if (!range) return null;
    const total = range.split("/")[1];
    const n = Number(total);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

async function lastActivityAt(env: Env): Promise<string | null> {
  const times: string[] = [];
  try {
    const k = await supabaseFetch(
      env,
      "keepalive?select=created_at&order=created_at.desc&limit=1"
    );
    if (k.ok) {
      const rows = (await k.json()) as { created_at: string }[];
      if (rows[0]?.created_at) times.push(rows[0].created_at);
    }
  } catch {
    /* ignore */
  }
  try {
    const r = await supabaseFetch(
      env,
      "runs?select=created_at&order=created_at.desc&limit=1"
    );
    if (r.ok) {
      const rows = (await r.json()) as { created_at: string }[];
      if (rows[0]?.created_at) times.push(rows[0].created_at);
    }
  } catch {
    /* ignore */
  }
  if (!times.length) return null;
  return times.sort().at(-1) ?? null;
}

async function insertKeepalive(env: Env): Promise<boolean> {
  try {
    const res = await supabaseFetch(env, "keepalive", {
      method: "POST",
      headers: { Prefer: "return=minimal" },
      body: JSON.stringify({ marker: 1 }),
    });
    if (!res.ok) return false;
    const cutoff = new Date(Date.now() - 90 * 24 * 3600_000).toISOString();
    await supabaseFetch(env, `keepalive?created_at=lt.${encodeURIComponent(cutoff)}`, {
      method: "DELETE",
      headers: { Prefer: "return=minimal" },
    }).catch(() => null);
    return true;
  } catch {
    return false;
  }
}

const REQUEST_LIMIT_REASON_PREFIX = "Soft limit: daily Worker request counter reached";

function requestLimitReason(env: Env): string {
  const reqCap = maxRequestsPerDay(env);
  return `${REQUEST_LIMIT_REASON_PREFIX} ${reqCap} (Cloudflare free-tier headroom). Reopens after UTC midnight or Admin override.`;
}

function isRequestLimitReason(reason: string | null | undefined): boolean {
  return Boolean(reason && reason.startsWith(REQUEST_LIMIT_REASON_PREFIX));
}

async function setAppClosed(env: Env, reason: string): Promise<void> {
  await patchAppControl(env, { status: "closed", reason });
}

async function bumpRequestCounter(env: Env): Promise<AppControl | null> {
  try {
    const res = await supabaseFetch(env, "rpc/app_control_bump_request", {
      method: "POST",
      body: "{}",
    });
    if (!res.ok) return null;
    const row = (await res.json()) as AppControl;
    return row && typeof row.id === "number" ? row : null;
  } catch {
    return null;
  }
}

function gateUnavailable(env: Env, origin: string | null): Response {
  return json(
    {
      error: "Free-tier controls unavailable (app_control / bump RPC). Apply supabase/harden_control_rls.sql.",
      closed: true,
    },
    503,
    env,
    origin
  );
}

/** Soft free-tier gate: block new search/runs when closed or near caps. */
async function assertAppOpen(env: Env, origin: string | null): Promise<Response | null> {
  if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_ROLE_KEY) {
    return json(
      { error: "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY on Worker" },
      500,
      env,
      origin
    );
  }

  const control = await ensureAppControl(env);
  if (!control) return gateUnavailable(env, origin);

  if (control.status === "closed") {
    return json(
      {
        error: "App is temporarily closed (free-tier soft limit).",
        closed: true,
        reason: control.reason,
      },
      503,
      env,
      origin
    );
  }

  const current = await bumpRequestCounter(env);
  if (!current) return gateUnavailable(env, origin);

  if (current.status === "closed") {
    return json(
      {
        error: "App is temporarily closed (free-tier soft limit).",
        closed: true,
        reason: current.reason,
      },
      503,
      env,
      origin
    );
  }

  const runs = await countRuns(env);
  const runCap = maxRuns(env);
  if (runs != null && runs >= runCap) {
    const reason = `Soft limit: ${runs} runs stored (cap ${runCap}). Delete runs in Admin, then reopen.`;
    await setAppClosed(env, reason);
    return json({ error: reason, closed: true, reason }, 503, env, origin);
  }

  const reqCap = maxRequestsPerDay(env);
  if (current.requests_today >= reqCap) {
    const reason = requestLimitReason(env);
    await setAppClosed(env, reason);
    return json({ error: reason, closed: true, reason }, 503, env, origin);
  }

  return null;
}

async function buildPublicStatus(env: Env) {
  const control = await ensureAppControl(env);
  return {
    ok: true,
    service: "geolineage-api",
    supabase_configured: Boolean(env.SUPABASE_URL && env.SUPABASE_SERVICE_ROLE_KEY),
    closed: control?.status === "closed",
    reason: control?.reason ?? null,
    status: control?.status ?? "open",
  };
}

async function buildAdminStatus(env: Env) {
  const control = await ensureAppControl(env);
  const runs = await countRuns(env);
  const last = await lastActivityAt(env);
  return {
    ...(await buildPublicStatus(env)),
    runs_count: runs,
    max_runs: maxRuns(env),
    requests_today: control?.requests_today ?? 0,
    max_requests_per_day: maxRequestsPerDay(env),
    last_activity_at: last,
    keepalive_max_age_hours: keepaliveMaxAgeHours(env),
  };
}

async function runScheduledMaintenance(env: Env): Promise<Record<string, unknown>> {
  const result: Record<string, unknown> = { ok: true };
  if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_ROLE_KEY) {
    return { ok: false, error: "supabase not configured" };
  }

  const control = await ensureAppControl(env);
  result.control = control?.status ?? null;

  const today = utcToday();
  if (control && control.requests_day !== today) {
    await patchAppControl(env, { requests_today: 0, requests_day: today });
    if (control.status === "closed" && isRequestLimitReason(control.reason)) {
      await patchAppControl(env, { status: "open", reason: null });
      result.reopened = "request_day_reset";
    }
  }

  const runs = await countRuns(env);
  result.runs_count = runs;
  const runCap = maxRuns(env);
  if (runs != null && runs >= runCap) {
    await setAppClosed(
      env,
      `Soft limit: ${runs} runs stored (cap ${runCap}). Delete runs in Admin, then reopen.`
    );
    result.closed = "run_limit";
  }

  const fresh = await getAppControl(env);
  if (fresh && fresh.requests_today >= maxRequestsPerDay(env) && fresh.status === "open") {
    await setAppClosed(env, requestLimitReason(env));
    result.closed = "request_limit";
  }

  const last = await lastActivityAt(env);
  const maxAgeMs = keepaliveMaxAgeHours(env) * 3600_000;
  const idleMs = last ? Date.now() - Date.parse(last) : Number.POSITIVE_INFINITY;
  result.last_activity_at = last;
  result.idle_hours = Number.isFinite(idleMs) ? Math.round(idleMs / 3600_000) : null;
  if (idleMs >= maxAgeMs) {
    const wrote = await insertKeepalive(env);
    result.keepalive_written = wrote;
  } else {
    result.keepalive_written = false;
  }

  return result;
}

async function handleSearch(req: Request, env: Env, origin: string | null): Promise<Response> {
  const blocked = await assertAppOpen(env, origin);
  if (blocked) return blocked;

  const body = await parseJsonBody<SearchBody>(req);
  const params = validateSearchBody(body, env);
  const features = await searchStac(params);
  return json(
    {
      catalog_url: params.catalog_url,
      collection: params.collection,
      bbox: params.bbox,
      max_items: params.max_items,
      count: features.length,
      features,
    },
    200,
    env,
    origin
  );
}

async function handleCreateRun(req: Request, env: Env, origin: string | null): Promise<Response> {
  if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_ROLE_KEY) {
    return json(
      { error: "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY on Worker" },
      500,
      env,
      origin
    );
  }

  const blocked = await assertAppOpen(env, origin);
  if (blocked) return blocked;

  const body = await parseJsonBody<SearchBody>(req);
  const params = validateSearchBody(body, env);

  const features = await searchStac(params);
  const ids = inputIds(features);
  const footprints = footprintsGeoJSON(features);
  const footprintsText = JSON.stringify(footprints);
  const checksum = await sha256Hex(new TextEncoder().encode(footprintsText));

  const reusable = await findReusableRun(
    env,
    params.catalog_url,
    params.collection,
    checksum,
    ids
  );

  let reused_from_run_id: string | null = reusable?.id ?? null;
  let output_path = reusable?.output_path ?? "";
  let status: "complete" | "reused" = reusable ? "reused" : "complete";

  const prevId = await previousScopedRunId(env, params.catalog_url, params.collection);
  let diff: { added: string[]; removed: string[]; unchanged: string[] } | null = null;
  if (prevId) {
    const prevReceipt = await getReceipt(env, prevId);
    diff = diffIds(receiptIds(prevReceipt), ids);
  }

  const runInsert = await supabaseFetch(env, "runs", {
    method: "POST",
    body: JSON.stringify({
      catalog_url: params.catalog_url,
      collection: params.collection,
      bbox: params.bbox,
      max_items: params.max_items,
      input_count: features.length,
      output_checksum: checksum,
      output_path: output_path || null,
      reused_from_run_id,
      status,
      search_params: {
        bbox: params.bbox,
        collection: params.collection,
        max_items: params.max_items,
        datetime: params.datetime,
      },
    }),
  });
  if (!runInsert.ok) {
    return json({ error: "Failed to create run" }, 500, env, origin);
  }
  const [run] = (await runInsert.json()) as { id: string }[];

  try {
    if (status !== "reused") {
      const objectPath = footprintsObjectPath(run.id);
      await supabaseStorageUpload(env, objectPath, footprintsText, "application/geo+json");
      output_path = publicStorageUrl(env, objectPath);
      const patch = await supabaseFetch(env, `runs?id=eq.${encodeURIComponent(run.id)}`, {
        method: "PATCH",
        headers: { Prefer: "return=minimal" },
        body: JSON.stringify({ output_path }),
      });
      if (!patch.ok) throw new Error("Failed to patch output_path");
    }

    const receipt = {
      run_id: run.id,
      timestamp: new Date().toISOString(),
      catalog_url: params.catalog_url,
      search_params: {
        bbox: params.bbox,
        collection: params.collection,
        max_items: params.max_items,
        datetime: params.datetime,
      },
      input_assets: features.map((f) => ({
        id: f.id,
        href:
          f.links?.find((l) => l.rel === "self")?.href ||
          `${params.catalog_url}/collections/${params.collection}/items/${encodeURIComponent(f.id)}`,
      })),
      transform_steps: [
        {
          name: "footprints_to_geojson",
          parameters: {
            crs: "EPSG:4326",
            ...(reused_from_run_id ? { reused_from_run_id } : {}),
          },
        },
      ],
      output_assets: [
        {
          path: output_path,
          checksum,
          format: "application/geo+json",
        },
      ],
      lineage_dag: {
        nodes: ["input_set", "footprints_to_geojson", "output"],
        edges: [
          { from: "input_set", to: "footprints_to_geojson" },
          { from: "footprints_to_geojson", to: "output" },
        ],
      },
      reused_from_run_id,
    };

    const receiptIns = await supabaseFetch(env, "lineage_receipts", {
      method: "POST",
      body: JSON.stringify({ run_id: run.id, receipt }),
    });
    if (!receiptIns.ok) throw new Error("Failed to insert receipt");

    const runCap = maxRuns(env);
    const runsAfter = await countRuns(env);
    if (runsAfter != null && runsAfter >= runCap) {
      await setAppClosed(
        env,
        `Soft limit: ${runsAfter} runs stored (cap ${runCap}). Delete runs in Admin, then reopen.`
      );
    }

    return json(
      {
        run: {
          id: run.id,
          status,
          catalog_url: params.catalog_url,
          collection: params.collection,
          bbox: params.bbox,
          max_items: params.max_items,
          input_count: features.length,
          output_path,
          output_checksum: checksum,
          reused_from_run_id,
        },
        receipt,
        footprints,
        diff,
      },
      201,
      env,
      origin
    );
  } catch (err) {
    await markRunFailed(env, run.id);
    const { status: st, message } = clientError(err);
    return json({ error: message, run_id: run.id }, st >= 400 ? st : 500, env, origin);
  }
}

async function handleListRuns(env: Env, origin: string | null): Promise<Response> {
  const res = await supabaseFetch(
    env,
    "runs?select=id,created_at,catalog_url,collection,bbox,max_items,input_count,output_path,output_checksum,reused_from_run_id,status&order=created_at.desc&limit=50"
  );
  if (!res.ok) return json({ error: "Failed to list runs" }, 500, env, origin);
  return json({ runs: await res.json() }, 200, env, origin);
}

const ADMIN_TOKEN_TTL_SEC = 8 * 60 * 60;

function b64urlEncode(bytes: ArrayBuffer | Uint8Array): string {
  const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s = "";
  for (let i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlDecode(s: string): Uint8Array {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  const b64 = (s + pad).replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function hmacSign(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  return b64urlEncode(sig);
}

async function timingSafeEqualStr(a: string, b: string): Promise<boolean> {
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  const ha = await crypto.subtle.digest("SHA-256", ab);
  const hb = await crypto.subtle.digest("SHA-256", bb);
  const xa = new Uint8Array(ha);
  const xb = new Uint8Array(hb);
  let diff = xa.length ^ xb.length;
  for (let i = 0; i < xa.length; i++) diff |= xa[i] ^ xb[i];
  return diff === 0 && a.length === b.length;
}

function adminConfigured(env: Env): boolean {
  return Boolean(env.ADMIN_USERNAME && env.ADMIN_PASSWORD && env.ADMIN_SESSION_SECRET);
}

async function mintAdminToken(env: Env): Promise<{ token: string; expires_at: number }> {
  const exp = Math.floor(Date.now() / 1000) + ADMIN_TOKEN_TTL_SEC;
  const payload = b64urlEncode(new TextEncoder().encode(JSON.stringify({ role: "admin", exp })));
  const sig = await hmacSign(env.ADMIN_SESSION_SECRET!, payload);
  return { token: `${payload}.${sig}`, expires_at: exp };
}

async function verifyAdminToken(env: Env, token: string | null): Promise<boolean> {
  if (!adminConfigured(env) || !token) return false;
  const parts = token.split(".");
  if (parts.length !== 2) return false;
  const [payload, sig] = parts;
  const expected = await hmacSign(env.ADMIN_SESSION_SECRET!, payload);
  if (!(await timingSafeEqualStr(sig, expected))) return false;
  try {
    const jsonStr = new TextDecoder().decode(b64urlDecode(payload));
    const data = JSON.parse(jsonStr) as { role?: string; exp?: number };
    if (data.role !== "admin" || typeof data.exp !== "number") return false;
    if (data.exp < Math.floor(Date.now() / 1000)) return false;
    return true;
  } catch {
    return false;
  }
}

function bearerToken(req: Request): string | null {
  const h = req.headers.get("Authorization");
  if (!h || !h.toLowerCase().startsWith("bearer ")) return null;
  return h.slice(7).trim() || null;
}

async function requireAdmin(
  req: Request,
  env: Env,
  origin: string | null
): Promise<Response | null> {
  if (!adminConfigured(env)) {
    return json({ error: "Admin is not configured" }, 503, env, origin);
  }
  if (!(await verifyAdminToken(env, bearerToken(req)))) {
    return json({ error: "Unauthorized" }, 401, env, origin);
  }
  return null;
}

/** Best-effort login throttle (per isolate; resets when the Worker recycles). */
const loginAttempts = new Map<string, { count: number; resetAt: number }>();
const LOGIN_WINDOW_MS = 15 * 60 * 1000;
const LOGIN_MAX_ATTEMPTS = 8;

function clientIp(req: Request): string {
  return (
    req.headers.get("CF-Connecting-IP") ||
    req.headers.get("X-Forwarded-For")?.split(",")[0]?.trim() ||
    "local"
  );
}

function allowLoginAttempt(ip: string): boolean {
  const now = Date.now();
  const row = loginAttempts.get(ip);
  if (!row || now >= row.resetAt) {
    loginAttempts.set(ip, { count: 1, resetAt: now + LOGIN_WINDOW_MS });
    return true;
  }
  if (row.count >= LOGIN_MAX_ATTEMPTS) return false;
  row.count += 1;
  return true;
}

function clearLoginAttempts(ip: string): void {
  loginAttempts.delete(ip);
}

async function handleAdminLogin(req: Request, env: Env, origin: string | null): Promise<Response> {
  if (!adminConfigured(env)) {
    return json({ error: "Admin is not configured" }, 503, env, origin);
  }
  const ip = clientIp(req);
  if (!allowLoginAttempt(ip)) {
    return json({ error: "Too many login attempts. Try again later." }, 429, env, origin);
  }
  const body = await parseJsonBody<{ username?: string; password?: string }>(req);
  const username = String(body.username || "").slice(0, 128);
  const password = String(body.password || "").slice(0, 256);
  const userOk = await timingSafeEqualStr(username, env.ADMIN_USERNAME!);
  const passOk = await timingSafeEqualStr(password, env.ADMIN_PASSWORD!);
  if (!userOk || !passOk) {
    return json({ error: "Invalid credentials" }, 401, env, origin);
  }
  clearLoginAttempts(ip);
  const session = await mintAdminToken(env);
  return json(session, 200, env, origin);
}

async function handleAdminListRuns(env: Env, origin: string | null): Promise<Response> {
  const res = await supabaseFetch(
    env,
    "runs?select=id,created_at,catalog_url,collection,bbox,max_items,input_count,output_path,output_checksum,reused_from_run_id,status&order=created_at.desc&limit=100"
  );
  if (!res.ok) return json({ error: "Failed to list runs" }, 500, env, origin);
  return json({ runs: await res.json() }, 200, env, origin);
}

async function deleteStorageObject(env: Env, objectPath: string): Promise<void> {
  const url = `${normalizeUrl(env.SUPABASE_URL)}/storage/v1/object/outputs/${objectPath}`;
  await fetch(url, {
    method: "DELETE",
    headers: {
      apikey: env.SUPABASE_SERVICE_ROLE_KEY,
      Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
    },
    signal: AbortSignal.timeout(20_000),
  });
}

async function handleAdminStatusGet(env: Env, origin: string | null): Promise<Response> {
  return json(await buildAdminStatus(env), 200, env, origin);
}

async function handleAdminStatusSet(
  req: Request,
  env: Env,
  origin: string | null
): Promise<Response> {
  const body = await parseJsonBody<{ status?: string; reason?: string | null }>(req);
  const status = body.status === "closed" ? "closed" : body.status === "open" ? "open" : null;
  if (!status) {
    return json({ error: 'status must be "open" or "closed"' }, 400, env, origin);
  }
  const reason =
    status === "closed"
      ? String(body.reason || "Closed manually by admin").slice(0, 500)
      : null;
  const row = await patchAppControl(env, { status, reason });
  if (!row) {
    return json(
      { error: "Failed to update app_control (run supabase/keepalive_and_control.sql)" },
      500,
      env,
      origin
    );
  }
  return json({ ok: true, ...row }, 200, env, origin);
}

async function handleAdminKeepalive(env: Env, origin: string | null): Promise<Response> {
  const wrote = await insertKeepalive(env);
  if (!wrote) {
    return json(
      { error: "Keepalive write failed (run supabase/keepalive_and_control.sql)" },
      500,
      env,
      origin
    );
  }
  return json({ ok: true, marker: 1, created_at: new Date().toISOString() }, 200, env, origin);
}

async function handleAdminDeleteRun(
  env: Env,
  id: string,
  origin: string | null
): Promise<Response> {
  const runRes = await supabaseFetch(env, `runs?id=eq.${encodeURIComponent(id)}&select=id,output_path`);
  if (!runRes.ok) return json({ error: "Failed to load run" }, 500, env, origin);
  const rows = (await runRes.json()) as { id: string; output_path?: string | null }[];
  if (!rows[0]) return json({ error: "not found" }, 404, env, origin);

  // Clear FK references so delete is allowed.
  const clear = await supabaseFetch(env, `runs?reused_from_run_id=eq.${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { Prefer: "return=minimal" },
    body: JSON.stringify({ reused_from_run_id: null }),
  });
  if (!clear.ok) return json({ error: "Failed to clear reuse links" }, 500, env, origin);

  const objectPath = footprintsObjectPath(id);
  const ownUrl = publicStorageUrl(env, objectPath);
  const stored = rows[0].output_path;
  // Only delete this run's own object — never a reused path that points at another run.
  const ownsObject =
    !stored ||
    stored === ownUrl ||
    (typeof stored === "string" &&
      stored.startsWith(trustedOutputsPrefix(env)) &&
      stored.endsWith(`/${id}/footprints.geojson`));
  if (ownsObject) {
    try {
      await deleteStorageObject(env, objectPath);
    } catch {
      /* ignore missing object */
    }
  }

  const del = await supabaseFetch(env, `runs?id=eq.${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: { Prefer: "return=minimal" },
  });
  if (!del.ok) return json({ error: "Failed to delete run" }, 500, env, origin);
  return json({ ok: true, id }, 200, env, origin);
}

async function handleGetRun(env: Env, id: string, origin: string | null): Promise<Response> {
  const runRes = await supabaseFetch(env, `runs?id=eq.${encodeURIComponent(id)}&select=*`);
  if (!runRes.ok) return json({ error: "Failed to load run" }, 500, env, origin);
  const runs = (await runRes.json()) as Record<string, unknown>[];
  if (!runs[0]) return json({ error: "not found" }, 404, env, origin);

  const run = runs[0];
  const receipt = await getReceipt(env, id);
  let footprints: unknown = null;

  const urlToFetch = resolveFootprintsFetchUrl(
    env,
    id,
    run.output_path as string | undefined,
    run.reused_from_run_id ? String(run.reused_from_run_id) : null
  );
  if (urlToFetch) {
    try {
      const fr = await fetch(urlToFetch, { signal: AbortSignal.timeout(15_000) });
      if (fr.ok) footprints = await fr.json();
    } catch {
      /* ignore */
    }
  }

  let diff = null;
  const catalog_url = String(run.catalog_url || "");
  const collection = String(run.collection || "");
  const listRes = await supabaseFetch(
    env,
    `runs?select=id` +
      `&catalog_url=eq.${encodeURIComponent(catalog_url)}` +
      `&collection=eq.${encodeURIComponent(collection)}` +
      `&order=created_at.desc&limit=50`
  );
  if (listRes.ok) {
    const all = (await listRes.json()) as { id: string }[];
    const idx = all.findIndex((r) => r.id === id);
    if (idx >= 0 && idx < all.length - 1) {
      const prevReceipt = await getReceipt(env, all[idx + 1].id);
      diff = diffIds(receiptIds(prevReceipt), receiptIds(receipt));
    }
  }

  return json({ run, receipt, footprints, diff }, 200, env, origin);
}

export default {
  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(
      runScheduledMaintenance(env).catch((err) => {
        console.error("scheduled maintenance failed", err);
      })
    );
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = request.headers.get("Origin");

    if (request.method === "OPTIONS") {
      if (!corsAllowed(env, origin)) {
        return new Response(null, { status: 403, headers: corsHeaders(env, origin) });
      }
      return new Response(null, { status: 204, headers: corsHeaders(env, origin) });
    }

    if (origin && !corsAllowed(env, origin)) {
      return json({ error: "Origin not allowed" }, 403, env, origin);
    }

    try {
      const url = new URL(request.url);
      const path = url.pathname.replace(/\/$/, "") || "/";

      if (request.method === "GET" && (path === "/" || path === "/health")) {
        return json(await buildPublicStatus(env), 200, env, origin);
      }

      if (request.method === "POST" && path === "/search") {
        return await handleSearch(request, env, origin);
      }
      if (request.method === "POST" && path === "/runs") {
        return await handleCreateRun(request, env, origin);
      }
      if (request.method === "GET" && path === "/runs") {
        return await handleListRuns(env, origin);
      }
      const m = path.match(
        /^\/runs\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i
      );
      if (request.method === "GET" && m) {
        return await handleGetRun(env, m[1], origin);
      }

      if (request.method === "POST" && path === "/admin/login") {
        return await handleAdminLogin(request, env, origin);
      }
      if (request.method === "GET" && path === "/admin/status") {
        const denied = await requireAdmin(request, env, origin);
        if (denied) return denied;
        return await handleAdminStatusGet(env, origin);
      }
      if (request.method === "POST" && path === "/admin/status") {
        const denied = await requireAdmin(request, env, origin);
        if (denied) return denied;
        return await handleAdminStatusSet(request, env, origin);
      }
      if (request.method === "POST" && path === "/admin/keepalive") {
        const denied = await requireAdmin(request, env, origin);
        if (denied) return denied;
        return await handleAdminKeepalive(env, origin);
      }
      if (request.method === "GET" && path === "/admin/runs") {
        const denied = await requireAdmin(request, env, origin);
        if (denied) return denied;
        return await handleAdminListRuns(env, origin);
      }
      const adminDel = path.match(
        /^\/admin\/runs\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i
      );
      if (request.method === "DELETE" && adminDel) {
        const denied = await requireAdmin(request, env, origin);
        if (denied) return denied;
        return await handleAdminDeleteRun(env, adminDel[1], origin);
      }

      return json({ error: "not found" }, 404, env, origin);
    } catch (err) {
      const { status, message } = clientError(err);
      return json({ error: message }, status, env, origin);
    }
  },
};
