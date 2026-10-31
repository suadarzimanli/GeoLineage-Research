import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { PRESETS, createRun, type AppStatus, type BBox } from "../api";
import { bboxError, clampMaxItems, isValidBbox } from "../bbox";
import { DEFAULT_COLLECTION, EARTH_SEARCH_COLLECTIONS } from "../collections";
import { BboxMap } from "../components/BboxMap";
import { searchPlaces, type PlaceHit } from "../geocode";

function sameBbox(a: BBox, b: BBox, eps = 1e-5) {
  return a.every((v, i) => Math.abs(v - b[i]) < eps);
}

function presetIndexFor(bbox: BBox): number {
  const i = PRESETS.findIndex((p) => sameBbox(p.bbox, bbox));
  return i >= 0 ? i : -1;
}

export function Run() {
  const navigate = useNavigate();
  const outlet = useOutletContext<{ appStatus: AppStatus | null } | null>();
  const appStatus = outlet?.appStatus ?? null;
  const closed = Boolean(appStatus?.closed);
  const [bbox, setBbox] = useState<BBox>(PRESETS[0].bbox);
  const [bboxText, setBboxText] = useState(PRESETS[0].bbox.map(String));
  const [preset, setPreset] = useState(0);
  const [maxItems, setMaxItems] = useState(10);
  const [maxItemsText, setMaxItemsText] = useState("10");
  const [collection, setCollection] = useState(DEFAULT_COLLECTION);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drawMode, setDrawMode] = useState(false);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<PlaceHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [openHits, setOpenHits] = useState(false);
  const [fitKey, setFitKey] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const searchWrapRef = useRef<HTMLLabelElement>(null);
  /** Skip one search cycle after committing a suggestion (avoids reopening the list). */
  const skipSearchRef = useRef(false);

  function applyBbox(next: BBox, fly = true) {
    if (!isValidBbox(next)) return;
    setBbox(next);
    setBboxText(next.map(String));
    setPreset(presetIndexFor(next));
    setDrawMode(false);
    setOpenHits(false);
    if (fly) setFitKey((k) => k + 1);
  }

  function pickPlace(hit: PlaceHit) {
    skipSearchRef.current = true;
    abortRef.current?.abort();
    setHits([]);
    setOpenHits(false);
    setSearching(false);
    setSearchError(null);
    applyBbox(hit.bbox);
    setQuery(hit.label);
  }

  function onPreset(i: number) {
    if (i < 0) return;
    setPreset(i);
    setBbox(PRESETS[i].bbox);
    setBboxText(PRESETS[i].bbox.map(String));
    setDrawMode(false);
    setFitKey((k) => k + 1);
  }

  useEffect(() => {
    if (skipSearchRef.current) {
      skipSearchRef.current = false;
      setHits([]);
      setOpenHits(false);
      setSearching(false);
      setSearchError(null);
      return;
    }

    const q = query.trim();
    if (q.length < 2) {
      setHits([]);
      setOpenHits(false);
      setSearching(false);
      setSearchError(null);
      return;
    }

    const timer = window.setTimeout(async () => {
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      setSearching(true);
      setSearchError(null);
      try {
        const results = await searchPlaces(q, ac.signal);
        if (!ac.signal.aborted) {
          setHits(results);
          setOpenHits(true);
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        setHits([]);
        setOpenHits(false);
        setSearchError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!ac.signal.aborted) setSearching(false);
      }
    }, 350);

    return () => {
      window.clearTimeout(timer);
      abortRef.current?.abort();
    };
  }, [query]);

  useEffect(() => {
    function onPointerDown(e: PointerEvent) {
      if (!searchWrapRef.current?.contains(e.target as Node)) setOpenHits(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpenHits(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (closed) {
      setError(appStatus?.reason || "App is closed near free-tier limits.");
      return;
    }
    const err = bboxError(bbox);
    if (err) {
      setError(err);
      return;
    }
    const items = clampMaxItems(maxItemsText, 10);
    setMaxItems(items);
    setMaxItemsText(String(items));
    setBusy(true);
    setError(null);
    try {
      const result = await createRun({
        bbox,
        max_items: items,
        collection,
      });
      navigate(`/runs/${result.run.id}`, { state: result });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="page-head">
        <h1>Run a search</h1>
        <p>
          Pick an area and a collection, then run the search. Matching scenes and a receipt are stored
          for the run.
        </p>
      </div>

      <form className="panel stack" onSubmit={onSubmit}>
        <div className="place-tools">
          <label className="place-search" ref={searchWrapRef}>
            Search place
            <input
              type="search"
              placeholder="e.g. Zurich, Nairobi…"
              value={query}
              autoComplete="off"
              aria-expanded={openHits}
              aria-controls="place-hits"
              onChange={(e) => {
                skipSearchRef.current = false;
                setQuery(e.target.value);
              }}
              onFocus={() => {
                if (hits.length > 0) setOpenHits(true);
              }}
            />
            {searching && <span className="place-hint muted">Searching…</span>}
            {searchError && <span className="place-hint error">{searchError}</span>}
            {openHits && (
              <ul className="place-hits" id="place-hits" role="listbox">
                {hits.length === 0 && !searching ? (
                  <li className="place-hits-empty muted">No places found.</li>
                ) : (
                  hits.map((hit) => (
                    <li key={hit.id}>
                      <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => pickPlace(hit)}>
                        {hit.label}
                      </button>
                    </li>
                  ))
                )}
              </ul>
            )}
          </label>

          <label>
            Place preset
            <select value={preset} onChange={(e) => onPreset(Number(e.target.value))}>
              <option value={-1} disabled={preset !== -1}>
                Custom area
              </option>
              {PRESETS.map((p, i) => (
                <option key={p.label} value={i}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="map-toolbar">
          <button
            type="button"
            className={`btn btn-ghost${drawMode ? " is-active" : ""}`}
            aria-pressed={drawMode}
            onClick={() => setDrawMode((v) => !v)}
          >
            {drawMode ? "Drag on the map…" : "Draw area on map"}
          </button>
          <span className="muted map-hint">
            {drawMode
              ? "Let go to lock the box."
              : "You can also type west / south / east / north below."}
          </span>
        </div>

        <BboxMap
          bbox={bbox}
          onChange={(next) => applyBbox(next, true)}
          drawMode={drawMode}
          fitKey={fitKey}
        />

        <div className="form-grid">
          {(["west", "south", "east", "north"] as const).map((name, i) => (
            <label key={name}>
              BBox {name}
              <input
                type="number"
                step="any"
                value={bboxText[i]}
                onChange={(e) => {
                  const text = e.target.value;
                  setBboxText((prev) => {
                    const next = [...prev];
                    next[i] = text;
                    return next;
                  });
                  if (text.trim() === "") return;
                  const n = Number(text);
                  if (!Number.isFinite(n)) return;
                  const next = [...bbox] as BBox;
                  next[i] = n;
                  if (isValidBbox(next)) {
                    setBbox(next);
                    setPreset(presetIndexFor(next));
                  } else {
                    setBbox(next);
                    setPreset(-1);
                  }
                }}
                onBlur={() => {
                  if (isValidBbox(bbox)) setBboxText(bbox.map(String));
                }}
              />
            </label>
          ))}
          <label>
            Max items
            <input
              type="number"
              min={1}
              max={50}
              value={maxItemsText}
              onChange={(e) => setMaxItemsText(e.target.value)}
              onBlur={() => {
                const n = clampMaxItems(maxItemsText, maxItems || 10);
                setMaxItems(n);
                setMaxItemsText(String(n));
              }}
            />
          </label>
          <label>
            Collection
            <select value={collection} onChange={(e) => setCollection(e.target.value)}>
              {EARTH_SEARCH_COLLECTIONS.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {error && <p className="error">{error}</p>}

        <div className="cta-row">
          <button className="btn btn-primary" type="submit" disabled={busy || closed}>
            {busy ? "Working…" : closed ? "Closed" : "Run search"}
          </button>
        </div>
        <p className="muted" style={{ margin: 0 }}>
          Catalog is Earth Search. The Worker saves the run in Supabase.
        </p>
      </form>
    </div>
  );
}
