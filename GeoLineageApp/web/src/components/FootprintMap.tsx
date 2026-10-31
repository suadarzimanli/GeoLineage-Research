import { useEffect, useRef } from "react";
import L from "leaflet";

interface Props {
  footprints: GeoJSON.FeatureCollection | null;
  bbox?: number[] | null;
}

export function FootprintMap({ footprints, bbox }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    const map = L.map(ref.current, { zoomControl: true, attributionControl: true });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap",
    }).addTo(map);
    map.setView([51.5, -0.08], 10);
    mapRef.current = map;
    requestAnimationFrame(() => map.invalidateSize());
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    map.eachLayer((layer) => {
      if (layer instanceof L.GeoJSON || layer instanceof L.Rectangle) {
        map.removeLayer(layer);
      }
    });

    const layers: L.Layer[] = [];
    if (bbox && bbox.length === 4) {
      const [w, s, e, n] = bbox;
      const rect = L.rectangle(
        [
          [s, w],
          [n, e],
        ],
        { color: "#0b3d2e", weight: 2, fillOpacity: 0.05 }
      );
      rect.addTo(map);
      layers.push(rect);
    }

    if (footprints?.features?.length) {
      const gj = L.geoJSON(footprints as GeoJSON.GeoJsonObject, {
        style: { color: "#1f6f54", weight: 2, fillColor: "#1f6f54", fillOpacity: 0.25 },
      });
      gj.addTo(map);
      layers.push(gj);
    }

    if (layers.length) {
      const group = L.featureGroup(layers as L.Layer[]);
      map.fitBounds(group.getBounds().pad(0.15));
    }
  }, [footprints, bbox]);

  return <div className="map" ref={ref} />;
}
