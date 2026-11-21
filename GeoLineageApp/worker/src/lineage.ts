/**
 * Lineage identity rules — the same contract as reference-pipeline/lineage/identity.py.
 *
 *   queryKey        catalog + collection + bbox + datetime + max_items + sort order. Only runs with
 *                   the same key are compared ("previous run" = previous run of the same query) and
 *                   only they may reuse each other's output. Identical in Python and here (tested).
 *   itemContentHash an item's geometry, bbox, properties and asset hrefs (links excluded). Same id +
 *                   different hash = the item changed in place.
 *   sceneKey        catalog-independent scene name (Sentinel-2 product URI, else id).
 *
 * Pure: no Worker or network APIs except crypto.subtle, so it runs under node --test.
 */

export type BBox = [number, number, number, number];
export type SortBy = { field: string; direction: "asc" | "desc" }[];

export const DEFAULT_SORTBY: SortBy = [
  { field: "properties.datetime", direction: "desc" },
  { field: "id", direction: "asc" },
];

/** Collections the hosted demo offers (Earth Search). Anything else is rejected. */
export const ALLOWED_COLLECTIONS = [
  "sentinel-2-c1-l2a",
  "sentinel-2-l2a",
  "sentinel-2-l1c",
  "sentinel-2-pre-c1-l2a",
  "sentinel-1-grd",
  "landsat-c2-l2",
  "naip",
  "cop-dem-glo-30",
  "cop-dem-glo-90",
];

/** JSON with object keys sorted at every level and no whitespace (matches Python json.dumps(sort_keys=True)). */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value ?? null);
  if (Array.isArray(value)) return `[${value.map((v) => canonicalJson(v === undefined ? null : v)).join(",")}]`;
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).filter((k) => obj[k] !== undefined).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(obj[k])}`).join(",")}}`;
}

export async function sha256Hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const DATE_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/;

/**
 * Normalise a STAC datetime or interval to RFC 3339 (catalogs reject plain dates):
 * '2025-06-01/2025-06-30' -> '2025-06-01T00:00:00Z/2025-06-30T23:59:59Z'. '..' keeps an end open.
 * Returns null for empty input; throws for malformed input.
 */
export function normalizeDatetime(raw: unknown): string | null {
  if (raw == null || String(raw).trim() === "") return null;
  const parts = String(raw).trim().split("/");
  if (parts.length > 2) throw new Error("datetime must be a single instant or 'start/end'");
  const out = parts.map((p, i) => {
    const s = p.trim();
    if (s === "" || s === "..") return "..";
    if (DATE_ONLY.test(s)) return s + (i === 0 ? "T00:00:00Z" : "T23:59:59Z");
    if (DATE_TIME.test(s)) return s;
    throw new Error(`not an RFC 3339 date or time: ${s}`);
  });
  if (out.length === 2 && out[0] === ".." && out[1] === "..") throw new Error("an interval needs at least one end");
  return out.join("/");
}

export async function queryKey(q: {
  catalog_url: string;
  collection: string;
  bbox: number[];
  datetime: string | null;
  max_items: number;
  sortby?: SortBy;
}): Promise<string> {
  return sha256Hex(
    canonicalJson({
      catalog_url: q.catalog_url.replace(/\/+$/, ""),
      collection: q.collection,
      bbox: q.bbox.map((v) => Number(v).toFixed(6)),
      datetime: normalizeDatetime(q.datetime),
      max_items: Math.trunc(q.max_items),
      sortby: q.sortby ?? DEFAULT_SORTBY,
    })
  );
}

export async function itemContentHash(item: Record<string, unknown>): Promise<string> {
  const assets = (item.assets && typeof item.assets === "object" ? item.assets : {}) as Record<string, { href?: unknown }>;
  const hrefs: Record<string, unknown> = {};
  for (const k of Object.keys(assets).sort()) hrefs[k] = assets[k]?.href ?? null;
  return sha256Hex(
    canonicalJson({
      id: item.id ?? null,
      geometry: item.geometry ?? null,
      bbox: item.bbox ?? null,
      properties: item.properties ?? {},
      assets: hrefs,
    })
  );
}

export function sceneKey(item: { id?: unknown; properties?: Record<string, unknown> | null }): string {
  const uri = item.properties?.["s2:product_uri"];
  if (typeof uri === "string" && uri) return uri.endsWith(".SAFE") ? uri.slice(0, -5) : uri;
  return String(item.id);
}

export type RemovedReason = "outside_window" | "gone" | "unknown";

export interface InputDiff {
  added: string[];
  removed: string[];
  changed: string[];
  unchanged: string[];
  removed_reason: Record<string, RemovedReason>;
}

/** previous/current: item id -> content hash (null when unknown, e.g. older receipts). */
export function diffInputs(previous: Map<string, string | null>, current: Map<string, string | null>): InputDiff {
  const d: InputDiff = { added: [], removed: [], changed: [], unchanged: [], removed_reason: {} };
  for (const id of [...current.keys()].sort()) {
    if (!previous.has(id)) d.added.push(id);
    else {
      const a = previous.get(id);
      const b = current.get(id);
      if (a && b && a !== b) d.changed.push(id);
      else d.unchanged.push(id);
    }
  }
  d.removed = [...previous.keys()].filter((id) => !current.has(id)).sort();
  return d;
}

export function isIdentical(d: InputDiff): boolean {
  return !d.added.length && !d.removed.length && !d.changed.length;
}

/** id -> identity (content hash) from a stored receipt's input_assets. */
export function receiptInputs(receipt: Record<string, unknown> | null | undefined): Map<string, string | null> {
  const m = new Map<string, string | null>();
  const assets = (receipt?.input_assets as { id?: unknown; content_hash?: unknown }[] | undefined) ?? [];
  for (const a of assets) if (typeof a?.id === "string") m.set(a.id, typeof a.content_hash === "string" ? a.content_hash : null);
  return m;
}

/** Query key of a stored run: the recorded one, or recomputed from its search parameters (older runs). */
export async function runQueryKey(run: {
  catalog_url?: unknown;
  collection?: unknown;
  bbox?: unknown;
  max_items?: unknown;
  search_params?: Record<string, unknown> | null;
}): Promise<string | null> {
  const sp = run.search_params ?? {};
  if (typeof sp.query_key === "string") return sp.query_key;
  try {
    return await queryKey({
      catalog_url: String(run.catalog_url ?? ""),
      collection: String(sp.collection ?? run.collection ?? ""),
      bbox: ((sp.bbox ?? run.bbox) as number[]) ?? [0, 0, 0, 0],
      datetime: (sp.datetime as string | null) ?? null,
      max_items: Number(sp.max_items ?? run.max_items ?? 0),
      sortby: (sp.sortby as SortBy) ?? [], // older runs used the catalog's default order: a different query
    });
  } catch {
    return null;
  }
}
