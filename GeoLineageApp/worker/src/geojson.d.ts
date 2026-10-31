declare namespace GeoJSON {
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
