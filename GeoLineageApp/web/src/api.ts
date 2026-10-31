const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") || "";

const REQUEST_TIMEOUT_MS = 30_000;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE) {
    throw new Error("Set VITE_API_BASE to your Worker URL (see .env.example).");
  }
  const method = (init?.method || "GET").toUpperCase();
  const headers = new Headers(init?.headers);
  if (method !== "GET" && method !== "HEAD" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    signal: init?.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });

  const contentType = res.headers.get("Content-Type") || "";
  let data: unknown = {};
  if (contentType.includes("application/json")) {
    data = await res.json().catch(() => ({}));
  } else {
    const text = await res.text().catch(() => "");
    data = text ? { error: text } : {};
  }

  if (!res.ok) {
    throw new Error((data as { error?: string }).error || res.statusText || "Request failed");
  }
  return data as T;
}

export type BBox = [number, number, number, number];

export interface RunSummary {
  id: string;
  created_at?: string;
  catalog_url: string;
  collection: string;
  bbox: number[];
  max_items: number;
  input_count: number;
  output_path?: string | null;
  output_checksum?: string | null;
  reused_from_run_id?: string | null;
  status: string;
}

export interface Diff {
  added: string[];
  removed: string[];
  unchanged: string[];
}

export interface CreateRunResult {
  run: RunSummary;
  receipt: Record<string, unknown>;
  footprints: GeoJSON.FeatureCollection;
  diff: Diff | null;
}

export interface RunDetail {
  run: RunSummary;
  receipt: Record<string, unknown> | null;
  footprints: GeoJSON.FeatureCollection | null;
  diff: Diff | null;
}

export interface AppStatus {
  ok: boolean;
  service?: string;
  supabase_configured: boolean;
  closed?: boolean;
  reason?: string | null;
  status?: "open" | "closed";
  runs_count?: number | null;
  max_runs?: number;
  requests_today?: number;
  max_requests_per_day?: number;
  last_activity_at?: string | null;
  keepalive_max_age_hours?: number;
}

export function health() {
  return request<AppStatus>("/health");
}

export function createRun(body: {
  bbox: BBox;
  collection?: string;
  catalog_url?: string;
  max_items?: number;
  datetime?: string;
}) {
  return request<CreateRunResult>("/runs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listRuns() {
  return request<{ runs: RunSummary[] }>("/runs");
}

export function getRun(id: string) {
  return request<RunDetail>(`/runs/${encodeURIComponent(id)}`);
}

const ADMIN_TOKEN_KEY = "geolineage_admin_token";

export function getAdminToken(): string | null {
  try {
    return sessionStorage.getItem(ADMIN_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAdminToken(token: string) {
  sessionStorage.setItem(ADMIN_TOKEN_KEY, token);
}

export function clearAdminToken() {
  sessionStorage.removeItem(ADMIN_TOKEN_KEY);
}

export async function adminLogin(username: string, password: string) {
  const data = await request<{ token: string; expires_at: number }>("/admin/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  setAdminToken(data.token);
  return data;
}

function adminHeaders(): HeadersInit {
  const token = getAdminToken();
  if (!token) throw new Error("Not signed in");
  return { Authorization: `Bearer ${token}` };
}

export function adminListRuns() {
  return request<{ runs: RunSummary[] }>("/admin/runs", {
    headers: adminHeaders(),
  });
}

export function adminDeleteRun(id: string) {
  return request<{ ok: boolean; id: string }>(`/admin/runs/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: adminHeaders(),
  });
}

export function adminGetStatus() {
  return request<AppStatus>("/admin/status", {
    headers: adminHeaders(),
  });
}

export function adminSetStatus(status: "open" | "closed", reason?: string) {
  return request<AppStatus & { ok?: boolean }>("/admin/status", {
    method: "POST",
    headers: adminHeaders(),
    body: JSON.stringify({ status, reason }),
  });
}

export function adminKeepalive() {
  return request<{ ok: boolean; marker: number; created_at: string }>("/admin/keepalive", {
    method: "POST",
    headers: adminHeaders(),
  });
}

/** Optional quick-start places (west, south, east, north). Prefer search or map draw for any AOI. */
export const PRESETS: { label: string; bbox: BBox }[] = [
  { label: "London / Greenwich", bbox: [-0.15, 51.48, 0.0, 51.55] },
  { label: "Zurich", bbox: [8.48, 47.34, 8.58, 47.4] },
  { label: "San Francisco Bay", bbox: [-122.52, 37.7, -122.35, 37.85] },
];
