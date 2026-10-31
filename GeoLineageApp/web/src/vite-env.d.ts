/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare namespace GeoJSON {
  type GeoJsonObject = FeatureCollection | Feature | Geometry;
  type Geometry =
    | { type: "Point"; coordinates: number[] }
    | { type: "LineString"; coordinates: number[][] }
    | { type: "Polygon"; coordinates: number[][][] }
    | { type: "MultiPolygon"; coordinates: number[][][][] }
    | { type: string; coordinates: unknown };

  interface Feature {
    type: "Feature";
    id?: string | number;
    geometry: Geometry;
    properties: Record<string, unknown> | null;
  }

  interface FeatureCollection {
    type: "FeatureCollection";
    features: Feature[];
  }
}
