# Reproducibility — what lives where

This repository has **two** implementations of the same lineage contract:

| Path | Product | Role |
|------|---------|------|
| `GeoLineageApp/` | GeoJSON footprints | Hosted Cloudflare + Supabase **portfolio demo** |
| `reference-pipeline/` | GeoParquet footprints | Python CLI + validation / stress scripts used in the **working paper** evaluation |

## Evaluation claims in `Paper/`

Experiments, 4/4 PASS suite, Experiment D stress test, and incremental timing (M7) refer to `reference-pipeline/` scripts:

- `python -m scripts.validation_suite`
- `python -m scripts.reproducibility_check`
- `python -m scripts.experiment_d_stress`
- `python -m scripts.run_evaluation`
- `python -m scripts.experiment_incremental_recompute`

See `reference-pipeline/README.md` and `Paper/geolineage_research_paper.tex` Appendix (How to Run Validation).

## Status

Working paper + open demo + open code. **Not peer-reviewed. Not a published venue paper.**
