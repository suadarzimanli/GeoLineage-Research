import { useEffect, useRef } from "react";
import L from "leaflet";
import type { BBox } from "../api";
import { isValidBbox } from "../bbox";

interface Props {
  bbox: BBox;
  onChange: (bbox: BBox) => void;
  drawMode: boolean;
  /** Bump to fly the map to the current bbox (search / preset / draw). */
  fitKey?: number;
}

function boundsFromBbox(bbox: BBox): L.LatLngBounds {
  const [w, s, e, n] = bbox;
  return L.latLngBounds([
    [s, w],
    [n, e],
  ]);
}

function bboxFromBounds(b: L.LatLngBounds): BBox {
  return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
}

function latLngFromClient(map: L.Map, clientX: number, clientY: number): L.LatLng {
  const rect = map.getContainer().getBoundingClientRect();
  return map.containerPointToLatLng(L.point(clientX - rect.left, clientY - rect.top));
}

export function BboxMap({ bbox, onChange, drawMode, fitKey = 0 }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const rectRef = useRef<L.Rectangle | null>(null);
  const draftRef = useRef<L.Rectangle | null>(null);
  const startRef = useRef<L.LatLng | null>(null);
  const drawingRef = useRef(false);
  const onChangeRef = useRef(onChange);
  const drawModeRef = useRef(drawMode);
  const skipFitRef = useRef(true);

  onChangeRef.current = onChange;
  drawModeRef.current = drawMode;

  useEffect(() => {
    if (!ref.current || mapRef.current) return;

    const map = L.map(ref.current, {
      zoomControl: true,
      attributionControl: true,
      doubleClickZoom: false,
    });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap",
    }).addTo(map);

    const initial = isValidBbox(bbox) ? bbox : ([-0.15, 51.48, 0.0, 51.55] as BBox);
    const rect = L.rectangle(boundsFromBbox(initial), {
      color: "#0b3d2e",
      weight: 2,
      fillOpacity: 0.12,
    }).addTo(map);
    rectRef.current = rect;
    map.fitBounds(rect.getBounds().pad(0.2));
    mapRef.current = map;

    const clearDraft = () => {
      if (draftRef.current) {
        map.removeLayer(draftRef.current);
        draftRef.current = null;
      }
    };

    const endDraw = (clientX: number, clientY: number) => {
      const start = startRef.current;
      drawingRef.current = false;
      startRef.current = null;
      map.dragging.enable();
      if (!start || !drawModeRef.current) {
        clearDraft();
        return;
      }
      const end = latLngFromClient(map, clientX, clientY);
      const bounds = L.latLngBounds(start, end);
      clearDraft();
      if (
        Math.abs(bounds.getWest() - bounds.getEast()) < 1e-6 ||
        Math.abs(bounds.getSouth() - bounds.getNorth()) < 1e-6
      ) {
        return;
      }
      const next = bboxFromBounds(bounds);
      if (isValidBbox(next)) onChangeRef.current(next);
    };

    const onPointerDown = (e: PointerEvent) => {
      if (!drawModeRef.current) return;
      if (e.button !== 0 && e.pointerType === "mouse") return;
      e.preventDefault();
      drawingRef.current = true;
      startRef.current = latLngFromClient(map, e.clientX, e.clientY);
      map.dragging.disable();
      clearDraft();
    };

    const onPointerMove = (e: PointerEvent) => {
      if (!drawingRef.current || !startRef.current || !drawModeRef.current) return;
      const bounds = L.latLngBounds(startRef.current, latLngFromClient(map, e.clientX, e.clientY));
      if (draftRef.current) {
        draftRef.current.setBounds(bounds);
      } else {
        draftRef.current = L.rectangle(bounds, {
          color: "#1f6f54",
          weight: 2,
          dashArray: "6 4",
          fillOpacity: 0.08,
        }).addTo(map);
      }
    };

    const onPointerUp = (e: PointerEvent) => {
      if (!drawingRef.current) return;
      endDraw(e.clientX, e.clientY);
    };

    const onPointerCancel = () => {
      if (!drawingRef.current) return;
      drawingRef.current = false;
      startRef.current = null;
      clearDraft();
      map.dragging.enable();
    };

    const container = map.getContainer();
    container.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerCancel);

    requestAnimationFrame(() => map.invalidateSize());

    return () => {
      container.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerCancel);
      map.remove();
      mapRef.current = null;
      rectRef.current = null;
      draftRef.current = null;
    };
    // Mount once; bbox sync handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const rect = rectRef.current;
    if (!rect || !isValidBbox(bbox)) return;
    rect.setBounds(boundsFromBbox(bbox));
  }, [bbox]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isValidBbox(bbox)) return;
    if (skipFitRef.current) {
      skipFitRef.current = false;
      return;
    }
    map.fitBounds(boundsFromBbox(bbox).pad(0.2));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const el = map.getContainer();
    el.classList.toggle("map-draw", drawMode);
    if (!drawMode) {
      drawingRef.current = false;
      startRef.current = null;
      if (draftRef.current) {
        map.removeLayer(draftRef.current);
        draftRef.current = null;
      }
      map.dragging.enable();
    }
  }, [drawMode]);

  return <div className="map bbox-map" ref={ref} />;
}
