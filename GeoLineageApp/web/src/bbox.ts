import type { BBox } from "./api";

export function isValidBbox(bbox: unknown): bbox is BBox {
  if (!Array.isArray(bbox) || bbox.length !== 4) return false;
  const nums = bbox.map(Number);
  if (nums.some((n) => !Number.isFinite(n))) return false;
  const [west, south, east, north] = nums;
  if (west >= east || south >= north) return false;
  if (west < -180 || east > 180 || south < -90 || north > 90) return false;
  return true;
}

export function bboxError(bbox: unknown): string | null {
  if (!Array.isArray(bbox) || bbox.length !== 4) {
    return "Bounding box needs west, south, east, north.";
  }
  const nums = bbox.map(Number);
  if (nums.some((n) => !Number.isFinite(n))) {
    return "Bounding box values must be finite numbers.";
  }
  const [west, south, east, north] = nums;
  if (west >= east || south >= north) {
    return "Need west < east and south < north.";
  }
  if (west < -180 || east > 180 || south < -90 || north > 90) {
    return "Coordinates out of range (lon ±180, lat ±90).";
  }
  return null;
}

export function clampMaxItems(value: unknown, fallback = 10): number {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(50, Math.max(1, Math.floor(n)));
}
