import type { BBox } from "./api";
import { isValidBbox } from "./bbox";

export interface PlaceHit {
  id: string;
  label: string;
  bbox: BBox;
  center: [number, number];
}

interface PhotonFeature {
  geometry?: { coordinates?: number[] };
  properties?: {
    osm_id?: number | string;
    osm_type?: string;
    name?: string;
    city?: string;
    state?: string;
    country?: string;
    extent?: number[];
  };
}

function paddedPointBbox(lon: number, lat: number, pad = 0.04): BBox {
  return [lon - pad, lat - pad, lon + pad, lat + pad];
}

function bboxFromPhotonExtent(ext: number[]): BBox | null {
  if (!ext || ext.length !== 4 || ext.some((n) => !Number.isFinite(n))) return null;
  // Photon extent: [west, north, east, south]
  const west = Math.min(ext[0], ext[2]);
  const east = Math.max(ext[0], ext[2]);
  const south = Math.min(ext[1], ext[3]);
  const north = Math.max(ext[1], ext[3]);
  const bbox: BBox = [west, south, east, north];
  return isValidBbox(bbox) ? bbox : null;
}

/** Free place search via Photon (Komoot / OSM). No API key. */
export async function searchPlaces(query: string, signal?: AbortSignal): Promise<PlaceHit[]> {
  const q = query.trim();
  if (q.length < 2) return [];

  const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(q)}&limit=6`;
  const res = await fetch(url, {
    signal: signal ?? AbortSignal.timeout(12_000),
  });
  if (!res.ok) throw new Error(`Place search failed (${res.status})`);
  const data = (await res.json()) as { features?: PhotonFeature[] };

  return (data.features || [])
    .map((f, i) => {
      const lon = f.geometry?.coordinates?.[0];
      const lat = f.geometry?.coordinates?.[1];
      if (typeof lon !== "number" || typeof lat !== "number") return null;
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) return null;

      const props = f.properties || {};
      const parts = [props.name, props.city, props.state, props.country].filter(Boolean);
      const label = [...new Set(parts)].join(", ") || `${lat.toFixed(3)}, ${lon.toFixed(3)}`;

      const fromExtent = props.extent ? bboxFromPhotonExtent(props.extent) : null;
      const bbox = fromExtent ?? paddedPointBbox(lon, lat);
      if (!isValidBbox(bbox)) return null;

      return {
        id: `${props.osm_type || "p"}-${props.osm_id ?? i}`,
        label,
        bbox,
        center: [lat, lon] as [number, number],
      };
    })
    .filter((x): x is PlaceHit => x != null);
}
