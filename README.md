# GeoLineage

**Provenance for STAC-driven geospatial pipelines** — a lineage receipt for every run, a diff against the previous run of the *same query* with reasons for every change, and reuse of unchanged outputs.

**Status:** working paper + open hosted demo + open code.

| Link | URL |
|------|-----|
| **Live demo** | https://geolineage-research.pages.dev/ |
| **API** | https://geolineage-api.suad-arzimanli.workers.dev/ |
| **Paper** | [`Paper/GeoLineage_Research_Paper.pdf`](Paper/GeoLineage_Research_Paper.pdf) |

---

## The problem

Pipelines built on STAC catalogs are re-run against catalogs that keep changing. Two questions recur: *what produced this output?* and *what changed since the last run?* GeoLineage records a compact JSON receipt per run and answers both, provided the identity rules are right:

- **Query key** — a hash of catalog, collection, area, time interval, result limit and sort order. A run is compared with, and may reuse, only the previous run of the same query.
- **Content hash** per input — the same id with a new hash means the item changed in place.
- **Scene key** — a catalog-independent name (Sentinel-2 product URI): item ids differ between catalogs.
- **Reasoned diff** — added / removed / changed / unchanged; removed items are *outside the window* (still in the catalog) or *gone*.
- **Minimum recompute** — decided before any transform runs.

## Key findings (2025, 20 cities, Earth Search + Planetary Computer, 8,320 Sentinel-2 items)

- A weekly "newest 10 scenes" pipeline reports removals in **92%** of its diffs, yet **60 of 60** sampled "removed" scenes were still in the catalog: they only fell out of the window.
- Reuse is possible in **0.4%** of such re-runs, against **100%** for the same query over a fixed past period.
- The same scene has a **different id in every one** of 4,140 cross-catalog matches and an acquisition time up to 34 minutes apart; the product URI matches **99.4%**.
- Catalog default orders differ (11 of 20 cities in Planetary Computer), so the sort order belongs in the query key. In-place item updates were rare (0.4% more than an hour after publication).

Details: [`reference-pipeline/study/results.md`](reference-pipeline/study/results.md).

---

## Two implementations, one contract

| Path | Footprint product | Role |
|------|-------------------|------|
| [`GeoLineageApp/`](GeoLineageApp/) | GeoJSON | Hosted demo: React on Cloudflare Pages + Cloudflare Worker + Supabase. Earth Search, nine allowed collections. |
| [`reference-pipeline/`](reference-pipeline/) | GeoParquet | Python reference CLI, validation scripts and the catalog study. |

The identity rules are `reference-pipeline/lineage/identity.py` and `GeoLineageApp/worker/src/lineage.ts`; shared test vectors assert that both compute the same query key and content hash.

## Quick start

**Live demo:** open https://geolineage-research.pages.dev/, pick a place and an optional date range, run, then run again — the second run reuses the output and shows what changed.

**Reference CLI:**

```bash
cd reference-pipeline
python -m venv .venv && .venv\Scripts\activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.run_pipeline --bbox 8.48 47.34 8.58 47.40 --datetime 2025-06-01/2025-06-30 --max-items 5
python -m unittest discover -s tests -t .            # 12 offline tests
python -m scripts.validation_suite --bbox 8.48 47.34 8.58 47.40
```

**Worker tests:** `cd GeoLineageApp/worker && npm ci && node --test test/` (7 unit tests); `test/e2e-local.mjs` runs 17 end-to-end checks against a local database stand-in (`test/mock-supabase.mjs`).

**Study:** `python -m study.collect`, `python -m study.analyze`, `python -m study.make_figures` in `reference-pipeline/`.

Hosting the demo yourself: [`GeoLineageApp/README.md`](GeoLineageApp/README.md) and [`GeoLineageApp/HOSTING.md`](GeoLineageApp/HOSTING.md).

## Scope

- Single-transform footprint products and dataset-level lineage — not a W3C PROV store, ISO 19115 package or OpenLineage backend.
- Catalog versions are not pinned: receipts record what the catalog returned, and diffs explain how that changed.
- The hosted demo is free-tier (soft caps); it is for inspection, not production use.

## Licence and citation

Code: **MIT** ([LICENSE](LICENSE)). Paper, figures and study data: **CC BY 4.0**. Cite with [CITATION.cff](CITATION.cff).
