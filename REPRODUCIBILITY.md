# Reproducibility — what lives where

| Path | Product | Role |
|------|---------|------|
| `GeoLineageApp/` | GeoJSON footprints | Hosted Cloudflare + Supabase demo |
| `reference-pipeline/` | GeoParquet footprints | Python CLI, validation scripts and the catalog study used in the paper |

## Paper claims and how to reproduce them

| Claim (paper section) | Command |
|---|---|
| Identity rules and diff logic (3) | `python -m unittest discover -s tests -t .` in `reference-pipeline/` |
| Same keys in Python and the Worker (4) | the same tests, plus `node --test test/` in `GeoLineageApp/worker/` |
| Validation suite, stress test (4) | `python -m scripts.validation_suite`, `python -m scripts.experiment_d_stress --n 20` in `reference-pipeline/` |
| Hosted service behaviour (4) | in `GeoLineageApp/worker/`: `node test/mock-supabase.mjs`, then `npx wrangler dev --var SUPABASE_URL:http://127.0.0.1:54321 --var SUPABASE_SERVICE_ROLE_KEY:test`, then `node test/e2e-local.mjs` |
| Study E1–E5 (5) | `python -m study.collect`, `python -m study.analyze`, `python -m study.make_figures` in `reference-pipeline/` |

`reference-pipeline/study/data/` holds the collected item lists (2025, 20 cities), so `study.analyze` reproduces E2–E5 offline. E1 and the spot checks query the live catalogs and reflect their state on the day they are run.
