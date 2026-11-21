import { useEffect, useRef } from "react";
import L from "leaflet";

interface Props {
  footprints: GeoJSON.FeatureCollection | null;
  bbox?: number[] | null;
}

function featureId(feature: GeoJSON.Feature): string {
  const fromProps = feature.properties?.id;
  if (typeof fromProps === "string" && fromProps) return fromProps;
  if (typeof feature.id === "string" || typeof feature.id === "number") return String(feature.id);
  return "scene";
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

    // Search window: dashed outline, almost no fill — distinct from scene footprints.
    if (bbox && bbox.length === 4) {
      const [w, s, e, n] = bbox;
      const rect = L.rectangle(
        [
          [s, w],
          [n, e],
        ],
        {
          color: "#b45309",
          weight: 2.5,
          dashArray: "6 4",
          fillColor: "#b45309",
          fillOpacity: 0.04,
        }
      );
      rect.bindTooltip("Search box (query bbox)", { sticky: true });
      rect.addTo(map);
      layers.push(rect);
    }

    // Scene footprints: light fill + clear borders; click/hover shows scene id.
    if (footprints?.features?.length) {
      const gj = L.geoJSON(footprints as GeoJSON.GeoJsonObject, {
        style: {
          color: "#1f6f54",
          weight: 2,
          fillColor: "#1f6f54",
          fillOpacity: 0.06,
        },
        onEachFeature(feature, layer) {
          const id = featureId(feature as GeoJSON.Feature);
          layer.bindTooltip(id, { sticky: true, direction: "top" });
          layer.bindPopup(
            `<div style="font:12px/1.4 system-ui,sans-serif"><strong>Scene</strong><br/><code style="word-break:break-all">${id}</code></div>`
          );
          layer.on({
            mouseover(e) {
              const target = e.target as L.Path;
              target.setStyle({ weight: 3, fillOpacity: 0.14 });
              target.bringToFront();
            },
            mouseout(e) {
              const target = e.target as L.Path;
              gj.resetStyle(target);
            },
          });
        },
      });
      gj.addTo(map);
      layers.push(gj);
    }

    if (layers.length) {
      const group = L.featureGroup(layers as L.Layer[]);
      map.fitBounds(group.getBounds().pad(0.15));
    }
  }, [footprints, bbox]);

  const sceneCount = footprints?.features?.length ?? 0;

  return (
    <div>
      <div className="map" ref={ref} />
      <p className="map-legend muted">
        <span className="map-legend-item map-legend-bbox">Search box</span>
        <span className="map-legend-item map-legend-scene">
          Scene footprints{sceneCount ? ` (${sceneCount})` : ""} — click for id
        </span>
      </p>
    </div>
  );
}
