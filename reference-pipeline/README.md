# GeoLineage — reference pipeline (GeoParquet CLI)

**Provenance-first GeoETL** — ingest from STAC → produce GeoParquet → record lineage and support "diff since last run" and minimum recompute.

This folder is the **evaluation / CLI reference** inside [GeoLineage-Research](https://github.com/suadarzimanli/GeoLineage-Research). The thin hosted **GeoJSON** demo lives in `../GeoLineageApp/`. See `../README.md` and `../REPRODUCIBILITY.md`.

**Status:** working paper companion code — not a peer-reviewed publication by itself.

---

## What it is

GeoLineage is a minimal reference pipeline that makes geospatial data supply chains **reproducible and auditable**: every output can be traced to its inputs and parameters, and you can see what changed between runs. It:

1. **Ingests** spatiotemporal assets from a STAC catalog (bbox, collection, max_items).
2. **Transforms** them into analysis-ready GeoParquet (e.g. item footprints with id, datetime, geometry).
3. **Records lineage** — a machine-readable JSON "receipt" for every run (run_id, timestamp, catalog, search params, input assets, transform steps, output path and checksum).
4. **Reports "diff since last run"** — added, removed, and unchanged inputs compared to the previous run.
5. **Reuses output when inputs are unchanged** (minimum recompute): no duplicate files, with a full audit trail.

No external lineage database is required; lineage lives as JSON files next to the run outputs.

**Want to try it without the command line?** After installing (see below), double‑click **`run_demo.bat`** (Windows) or run **`streamlit run demo/app.py`** — the demo opens in your browser. Pick a location, click **Run pipeline**, and explore. No coding required.

---

## Features

| Feature | Description |
|--------|--------------|
| **Lineage every run** | Each run produces a lineage JSON with run_id, timestamp, catalog_url, search_params, input_assets, transform_steps, output_assets. |
| **Query-scoped diff** | Each run is compared with the previous run of the *same query* (catalog, collection, bbox, datetime, max_items, sort order → `query_key`) and reports Added / Removed / Changed / Unchanged. Removed items are labelled *outside the window* (still in the catalog) or *gone*. |
| **Content identity** | Every input has a `content_hash` of its geometry, properties and asset hrefs, and a catalog-independent `scene_key` (Sentinel-2 product URI). Same id + new hash = changed in place. |
| **Minimum recompute** | If the inputs (ids and content hashes) equal those of the previous run of the same query, the output is reused **before** any transform runs; a new lineage record with `reused_from_run_id` is still written. |
| **Deterministic queries** | Searches are sorted newest first, ties by id; dates are normalised to RFC 3339; the catalog's match count is recorded. |
| **Catalog-agnostic** | Works with any STAC 1.x–compliant API. Tested with Earth Search (Element84) and Copernicus Data Space Ecosystem. |
| **Lineage DAG** | Each run’s lineage includes a small DAG (input_set → transform → output_asset) for queryable provenance. |
| **“What produced this?”** | Query by output path or run ID: `python -m scripts.query_lineage --run-id <id>` or `--output <path>`. |
| **Incremental recompute** | Per-region reuse when re-running multiple bboxes; only changed regions recomputed. See run_pipeline_multi_bbox, experiment_incremental_recompute. |
| **CLI + Streamlit demo** | Run from the command line or via a web UI to set parameters and inspect lineage and diff. |

---

## Quick start

### Prerequisites

- **Python 3.10+**
- Clone or download the repo and `cd` into the `reference-pipeline` folder.

### 1. Install

**Option A — venv (recommended):**

```bash
cd reference-pipeline
python -m venv .venv
# Windows (if script execution is allowed):
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate
pip install -r requirements.txt
```

**Option B — editable package:**

```bash
cd reference-pipeline
pip install -e .
```

**Windows without activation:** If PowerShell blocks script execution, skip `activate` and use the venv executables directly (see commands below with `.venv\Scripts\python.exe` and `.venv\Scripts\streamlit.exe`).

### 2. Run the pipeline (CLI)

From the `reference-pipeline` folder:

```bash
# With venv activated:
python -m scripts.run_pipeline --bbox -122.5 37.5 -122.2 37.8 --max-items 5

# Windows without activation:
.venv\Scripts\python.exe -m scripts.run_pipeline --bbox -122.5 37.5 -122.2 37.8 --max-items 5
```

- **Input:** STAC search (default: Element84 Earth Search, collection `sentinel-2-c1-l2a`) for the given bbox.
- **Output:** `outputs/<run_id>/footprints.parquet` and `lineage_runs/runs/<run_id>.json`.
- **Diff:** After the first run, the CLI prints how many inputs were added/removed/unchanged vs the previous run. Run the same command again to see minimum recompute ("Output unchanged (reused from run ...)").

You can also double‑click **`run_pipeline.bat`** (Windows) to run with a default bbox.

### 3. Run the demo (Streamlit)

**How to start the demo:** From the project folder, run the command below (or double-click **`run_demo.bat`** on Windows). The browser opens at http://localhost:8501. Use the sidebar to pick a location and click **Run pipeline**.

**Important:** Start the demo with `streamlit run demo/app.py`, not `python demo/app.py`.

```bash
# With venv activated:
streamlit run demo/app.py

# Windows without activation:
.venv\Scripts\streamlit.exe run demo/app.py
```

Or double‑click **`run_demo.bat`** (Windows). The browser opens at http://localhost:8501. **No coding required** for the demo: use the sidebar to pick a location and click Run pipeline.

- **Sidebar:** Pick a **Location** (e.g. San Francisco Bay, London, Paris, Berlin, New York, Tokyo, Sydney) or use custom coordinates; choose a catalog preset; set max items; then click **Run pipeline**. A small map shows the area. Use **Need help?** in the sidebar for quick start and docs links.
- **Main area:** Plain-language intro, then select a run to view output path, lineage receipt, DAG, “What produced this?”, and **diff since previous run** (Added / Removed / Unchanged). Styled for easier reading by non-coders.

---

## Data sources

The pipeline is catalog-agnostic. Two presets are included in the demo:

| Preset | Catalog | Collection (example) |
|--------|---------|------------------------|
| **Earth Search** | [Element84 Earth Search](https://earth-search.aws.element84.com/v1) | `sentinel-2-c1-l2a` |
| **Copernicus Data Space** | [Copernicus Data Space Ecosystem STAC](https://stac.dataspace.copernicus.eu/v1) | `SENTINEL-2` |

You can override catalog URL and collection in the CLI (`--catalog`, `--collection`) or in the demo sidebar.

---

## Pipeline design

1. **Ingest** — STAC search by bbox, collection, datetime (optional, normalised to RFC 3339), max_items, sorted newest first with ties by id. For each item we record id, href, the catalog's checksum if any, a `content_hash`, a `scene_key` and the `updated` time.
2. **Minimum recompute** — Find the previous run with the same `query_key`. If its inputs equal the current ones (ids and content hashes), reuse its output, set `reused_from_run_id`, and skip the transform.
3. **Transform** — If not reusing: extract footprint geometry, id, datetime from each Item; build a GeoDataFrame; write GeoParquet; compute SHA-256 of the file.
4. **Lineage** — Write a JSON record for this run: run_id, timestamp (microseconds), catalog_url, search_params (with `query_key`, `sortby`, `matched`), input_assets, transform_steps, output_assets (path, checksum, crs).
5. **Diff** — Compare with the previous run of the same query: Added, Removed (with reason), Changed, Unchanged. Different queries are never compared automatically; `lineage.diff.diff_runs(a, b)` compares any two runs on purpose.

The identity rules live in `lineage/identity.py` (standard library only). The hosted demo's Worker implements the same rules in `GeoLineageApp/worker/src/lineage.ts`; shared test vectors check that both compute identical keys.

Output layout:

- **Outputs:** `outputs/<run_id>/footprints.parquet` (one file per run unless reused; reused runs point at the prior run’s path).
- **Lineage:** `lineage_runs/runs/<run_id>.json` (one JSON per run).

---

## Lineage schema (minimal)

Each lineage JSON includes:

| Field | Description |
|-------|-------------|
| `run_id` | UUID for this run. |
| `timestamp` | ISO 8601 UTC. |
| `catalog_url` | STAC catalog URL. |
| `search_params` | bbox, collection, datetime, max_items. |
| `input_assets` | List of `{ id, href, checksum }` (one per STAC item). |
| `transform_steps` | List of `{ name, parameters }`; for reuse, parameters may include `reused_from_run_id`. |
| `output_assets` | List of `{ path, checksum, crs }` (path to GeoParquet, SHA-256, CRS). |

This is enough to answer "what produced this output?" for the implemented pipeline without an external lineage service. The paper discusses optional extensions (e.g. run signatures, pipeline_version) for stronger reproducibility claims.

### Lineage DAG (queryable provenance)

Each run’s lineage can be represented as a small **directed acyclic graph (DAG)** stored in the same JSON under `lineage_dag`:

- **Nodes:** One `input_set` node (catalog_url, search_params, input_assets) and one `output_asset` node per output (path, checksum, crs).
- **Edges:** One edge per output: `input_set --[transform_name]--> output_asset`, with parameters (e.g. crs, optional reused_from_run_id).

The pipeline emits this DAG on every run. Old runs without `lineage_dag` get a DAG built on load so they remain queryable. **“What produced this output?”** is answered by walking the DAG backward from an output node to the transform and input set(s). Use `python -m scripts.query_lineage --run-id <id>` or `--output <path>` to query by run or by output file path.

---

## CLI reference

| Option | Description | Default |
|--------|-------------|---------|
| `--bbox minx miny maxx maxy` | Bounding box (WGS84). | Required. |
| `--catalog URL` | STAC catalog URL. | Earth Search. |
| `--collection NAME` | STAC collection id. | `sentinel-2-c1-l2a` |
| `--max-items N` | Max STAC items to fetch. | 10 |
| `--out-dir PATH` | Output directory for GeoParquet. | `outputs` |
| `--lineage-dir PATH` | Lineage directory (runs stored under `runs/`). | `lineage_runs` |

Example with custom catalog, output dir, and lineage dir:

```bash
python -m scripts.run_pipeline --bbox -122.5 37.5 -122.2 37.8 --catalog https://stac.dataspace.copernicus.eu/v1 --collection SENTINEL-2 --max-items 5 --out-dir ./my_outputs --lineage-dir ./my_lineage
```

---

## Validation and testing

### Offline unit tests

```bash
python -m unittest discover -s tests -t .     # 12 tests, no network
```

### STAC lineage study (paper, Section 5)

```bash
python -m study.collect        # 2025 Sentinel-2 L2A item lists, 20 cities, Earth Search + Planetary Computer -> study/data/
python -m study.analyze        # E1–E5 (with a few live checks) -> study/results.json, study/results.md
python -m study.make_figures   # -> ../Paper/figures/fig_*.pdf
```

### Automated validation suite

Runs four checks in dedicated dirs (`validation_outputs/`, `validation_lineage_runs/`) so your main runs are untouched:

1. First run produces at least one output file and one lineage file.
2. Second run with same parameters reuses the first run’s output.
3. A run with higher max_items is a new query (no automatic diff); an explicit comparison with the 5-item run keeps all 5 items.
4. Latest lineage has all required fields and non-empty output checksum.

```bash
# Default bbox (-122.5, 37.5, -122.2, 37.8)
.venv\Scripts\python.exe -m scripts.validation_suite

# Custom bbox
.venv\Scripts\python.exe -m scripts.validation_suite --bbox -122.5 37.5 -122.2 37.8
```

Expected: "All 4 tests PASSED".

### Reproducibility check

Runs Experiment A (same params twice → reuse) and Experiment B (max_items 5 → 10 → new output and diff), then prints a short PASS summary.

```bash
.venv\Scripts\python.exe -m scripts.reproducibility_check
.venv\Scripts\python.exe -m scripts.reproducibility_check --bbox -122.5 37.5 -122.2 37.8
```

### Experiment D (stress test)

Runs the pipeline N times with identical parameters and reports reuse rate, input-set stability, and spurious diff rate (for M5 reproducibility rate).

```bash
.venv\Scripts\python.exe -m scripts.experiment_d_stress --bbox -122.5 37.5 -122.2 37.8
.venv\Scripts\python.exe -m scripts.experiment_d_stress --bbox -122.5 37.5 -122.2 37.8 --n 20
```

Uses `experiment_d_outputs/` and `experiment_d_lineage_runs/` so main and validation dirs are unchanged.

### Incremental recompute experiment

Runs the pipeline for N regions twice (full rebuild, then incremental). Reports time saved when unchanged regions reuse.

```bash
.venv\Scripts\python.exe -m scripts.experiment_incremental_recompute --n 5
```

Uses `incremental_experiment_outputs/` and `incremental_experiment_lineage_runs/`.

### Evaluation (lineage completeness + summary)

Checks that for every output in the lineage store you can answer “what produced this output?” (lineage completeness). Also prints how to run the other evaluation scripts.

```bash
.venv\Scripts\python.exe -m scripts.run_evaluation
.venv\Scripts\python.exe -m scripts.run_evaluation --lineage-dir lineage_runs
```

Target: 100% lineage completeness. For full evaluation (reproducibility, stress, incremental), run `validation_suite`, `reproducibility_check`, `experiment_d_stress`, and `experiment_incremental_recompute` as above.

### Manual 3-step test

See **`docs/START_HERE.md`** for a minimal hand-run test: (1) run once, (2) run same again (reuse), (3) run with more items (diff). **`docs/TESTING_AND_VALIDATION.md`** has the full step-by-step testing guide with exact commands and pass criteria.

---

## Repository structure

| Path | Purpose |
|-----|---------|
| `ingest/stac_ingest.py` | STAC search by bbox/collection; returns items for transform and lineage. |
| `transform/footprints_to_geoparquet.py` | STAC items → one GeoParquet (footprints + id, datetime). |
| `lineage/schema.py` | Lineage data structures (LineageRun, InputAsset, OutputAsset, TransformStep). |
| `lineage/store.py` | Save/load lineage runs as JSON under `lineage_runs/runs/`. |
| `lineage/diff.py` | Compare current run’s inputs to previous run (added/removed/unchanged). |
| `scripts/run_pipeline.py` | End-to-end: ingest → minimum recompute / transform → lineage (with DAG) → diff. |
| `scripts/query_lineage.py` | Query “what produced this output?” by `--run-id` or `--output` path. |
| `scripts/run_pipeline_multi_bbox.py` | Run pipeline for multiple bboxes; incremental recompute per region. |
| `scripts/experiment_incremental_recompute.py` | Two-pass experiment: full vs incremental; reports time saved %. |
| `scripts/run_evaluation.py` | Lineage completeness (what produced this? for every output); evaluation summary. |
| `scripts/validation_suite.py` | Automated 4-check validation (PASS/FAIL). |
| `scripts/reproducibility_check.py` | Experiment A + B: reuse and diff checks. |
| `scripts/experiment_d_stress.py` | Experiment D: N identical runs, reuse rate, spurious diff rate. |
| `demo/app.py` | Streamlit UI: run pipeline, select run, view lineage and diff. |
| `docs/` | All project documentation: user manual, START_HERE, testing, paper (md + tex), technical report, roadmap. |

---

## Documentation

| Document | Description |
|----------|-------------|
| **docs/USER_MANUAL.md** | Full user manual: install, CLI, demo, outputs, lineage, validation. |
| **docs/START_HERE.md** | Plain-language intro and 3-step test to prove the pipeline works. |
| **docs/TESTING_AND_VALIDATION.md** | Detailed testing guide (all tests, commands, pass criteria). |
| **docs/PROJECT_SUMMARY.md** | What was built, why, and how it works (one-page summary). |
| **docs/EXPLAIN_LIKE_A_KID.md** | Plain-language explanation and app field meanings. |
| **docs/WHAT_THIS_IS_AND_HOW_TO_TEST.md** | Short “what this is” and how to test. |
| **docs/IMPLEMENTATION_PLAN.md** | Implementation plan and structure. |
| **docs/GeoLineage_Paper.md** | Research paper (Markdown). |
| **docs/GeoLineage_paper_latex.tex** | Research paper (LaTeX; for Overleaf or pdflatex). |
| **docs/TECHNICAL_REPORT.md** | Technical report with RQs, design, evaluation, limitations. |
| **docs/PAPER_CODE_ALIGNMENT.md** | Paper–code alignment and Experiment D implementation. |
| **docs/DEEPEN_GEOLINEAGE_ROADMAP.md** | Phased roadmap (multi-source, DAG, incremental, evaluation). |

### Building the paper (PDF)

- **Overleaf:** Upload `docs/GeoLineage_paper_latex.tex` (and `streamlit_demo.png` if you use the figure), then compile. Replace `[repository URL]` in the "Code availability" line with your repo link.
- **Local TeX:** From `docs/` run `pdflatex GeoLineage_paper_latex.tex` twice (for references and table of contents).

---

## Code and data availability

Source code, validation scripts (`validation_suite.py`, `reproducibility_check.py`, `experiment_d_stress.py`), and documentation are available in this repository. All experiments (validation suite, reproducibility check, Experiment D) are reproducible with the provided scripts and produce run artifacts (lineage JSON and output GeoParquet) in the documented directories. See `docs/START_HERE.md` and `docs/GeoLineage_Paper.md` (Appendix B) for run instructions.

---

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for the full text.

---

## References

- [STAC Specification](https://stacspec.org/)
- [GeoParquet](https://geoparquet.org/)
- [Earth Search (Element84) STAC API](https://earth-search.aws.element84.com/v1)
- [Copernicus Data Space Ecosystem STAC](https://stac.dataspace.copernicus.eu/v1)

---

## Roadmap and future work

A phased plan to deepen GeoLineage (multi-source, lineage DAG, queryable “what produced this?”, incremental recompute, evaluation, write-up) is in **`docs/DEEPEN_GEOLINEAGE_ROADMAP.md`**. Phases 1–3 are implemented (multi-source, lineage DAG + query, incremental recompute).

Further work: additional data sources (e.g. Overture GeoParquet), multi-step DAGs with incremental recompute, lineage schema alignment with STAC/PROV, optional DB backend for querying lineage.
