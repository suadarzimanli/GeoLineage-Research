# GeoLineage

**Provenance-first GeoETL for STAC-driven footprint products** — lineage receipt every run, input-set diff, minimum recompute.

**Status:** working paper + open hosted demo + open code. **Not peer-reviewed. Not a published venue paper.**

| Link | URL |
|------|-----|
| **Live demo** | https://geolineage-research.pages.dev/ |
| **API** | https://geolineage-api.suad-arzimanli.workers.dev/ |
| **This repo** | https://github.com/suadarzimanli/GeoLineage-Research |

---

## Problem (short)

STAC / EO pipelines often cannot answer: *what produced this output?* and *what changed since last run?* GeoLineage records a compact JSON receipt per run and reuses checksummed footprint products when the input set is unchanged.

## Research questions (working paper)

- **RQ1** — Can a compact receipt answer “what produced this?” without an external lineage service?
- **RQ2** — Can an input-set diff (added / removed / unchanged) reflect parameter change?
- **RQ3** — Can minimum recompute skip rewriting identical products while still writing a new receipt?

See [`Paper/GeoLineage_Research_Paper.pdf`](Paper/GeoLineage_Research_Paper.pdf) and [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).

---

## Two implementations (same lineage contract)

| Path | Footprint product | Role |
|------|-------------------|------|
| [`GeoLineageApp/`](GeoLineageApp/) | **GeoJSON** | Thin **hosted portfolio demo** (Cloudflare Pages + Worker + Supabase). One allowlisted catalog (Earth Search). |
| [`reference-pipeline/`](reference-pipeline/) | **GeoParquet** | Python **reference CLI** + validation / stress scripts. Dual-catalog experiments (Earth Search + Copernicus) live here. |

Do **not** treat the SPA as the evaluation platform. Evaluation claims in the paper (PASS suite, stress test, timing) refer to `reference-pipeline/`.

```
Browser demo  →  GeoJSON + receipt + diff/reuse  →  Cloudflare / Supabase
CLI reference →  GeoParquet + receipt + validation scripts  →  local folders
```

---

## Repository layout

```
.
  README.md                 # this file
  REPRODUCIBILITY.md        # demo vs reference + how eval maps
  CloudflarePublishedLink.txt
  GeoLineageApp/            # hosted demo (web + worker + supabase SQL)
  reference-pipeline/       # GeoParquet CLI + scripts/*.py validation suite
  Paper/                    # working paper (LaTeX + PDF + figures)
  ImagesFromApp/            # UI screenshots
```

---

## Quick start — live demo (no install)

1. Open https://geolineage-research.pages.dev/
2. Pick a place (e.g. Zurich) → Run → open History / receipt / diff.

Local demo stack: see [`GeoLineageApp/README.md`](GeoLineageApp/README.md) and [`GeoLineageApp/HOSTING.md`](GeoLineageApp/HOSTING.md).

## Quick start — reference CLI + validation

```bash
cd reference-pipeline
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m scripts.run_pipeline --bbox -122.5 37.5 -122.2 37.8 --max-items 5
python -m scripts.validation_suite --bbox -122.5 37.5 -122.2 37.8
```

Full script list: [`reference-pipeline/README.md`](reference-pipeline/README.md).

---

## Scope / honesty

- Single-step footprint extract (not a full multi-step GeoETL platform).
- Retrospective JSON receipt — **not** a full W3C PROV store, ISO 19115 package, or OpenLineage backend.
- Catalog version pinning is out of scope; we record what the catalog returned at query time.
- Hosted demo is free-tier (soft caps / possible Supabase pause); suitable for inspection, not production tenancy.

## Citation / contact

Working manuscript title: *GeoLineage: A Provenance-First GeoETL Pipeline for Reproducible Geospatial Data Supply Chains* (Suad Arzimanli).  
Contact: suad.arzimanli@gmail.com
