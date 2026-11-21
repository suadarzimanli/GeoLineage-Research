# STAC lineage study — results

20 cities, Sentinel-2 L2A, 2025; generated 2026-11-21T18:44:43Z.

## E1 Repeatability (same query, asked again)

| Catalog | cities | sorted: same order | default: same order | default: same set | default order = sorted | default set = sorted |
|---|---:|---:|---:|---:|---:|---:|
| earthsearch | 20 | 20 | 20 | 20 | 20 | 20 |
| planetary | 20 | 20 | 20 | 20 | 9 | 19 |

## E2 Weekly 'latest 10' pipeline (Earth Search)

1020 weekly diffs: mean 3.73 added and 3.58 removed; 92% of diffs report removals; 0% identical. Of 60 sampled 'removed' items, 60 are still in the catalog (0 absent, 0 errors). Rebuild matches the live catalog in 12 of 12 checks.

## E3 Mutability (Earth Search created/updated)

4163 items; updated after creation by more than 1 h: 0.4%, 1 day: 0.3%, 30 days: 0.0%; median lag when > 1 day: 1.3 days.

Weekly re-runs of a fixed past period (March 2025): 0 of 760 re-runs had inputs updated since the previous run (0 cities); each such case would be one where an id-only identity reuses a stale output.

Months of 'updated': {'2025-01': 219, '2025-02': 222, '2025-03': 392, '2025-04': 368, '2025-05': 382, '2025-06': 359, '2025-07': 382, '2025-08': 370, '2025-09': 363, '2025-10': 383, '2025-11': 362, '2025-12': 360, '2026-02': 1}

## E4 Identity across catalogs

Earth Search 4163 items (4163 product URIs), Planetary Computer 4157 (4157). Matched by product URI: 4140 (99.4% of Earth Search); equal ids among them: 0; datetime difference median 407.9115 s, max 2033.255 s. By sensing key (without baseline and generation time): 4107 (99.4%). Acquisitions delivered more than once (same sensing, different generation time): {'earthsearch': [33, 33], 'planetary': [50, 50]} (acquisitions, extra items). Baselines: {'earthsearch': {'05.11': 4163}, 'planetary': {'05.11': 4157}}

## E5 Reuse by query design (weekly re-runs from April)

| Design | re-runs | reusable (same ids) |
|---|---:|---:|
| latest_10 | 740 | 0.4% |
| rolling_30_days | 740 | 0.0% |
| fixed_period_march | 740 | 100.0% |
