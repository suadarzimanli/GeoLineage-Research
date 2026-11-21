"""
The STAC lineage study (after study/collect.py).

    python -m study.analyze           -> study/results.json, study/results.md

E1 Repeatability   the same query asked again now: same items, same order? (live, sorted vs catalog default)
E2 Window churn    a weekly "latest 10 scenes" pipeline through 2025, rebuilt from the item lists and
                   spot-checked live: what its diffs report, and whether "removed" items are gone
E3 Mutability      how often items change after publication (Earth Search created/updated), and how
                   often an id-only identity would wrongly reuse a stale output
E4 Identity        the same scenes in Earth Search and Planetary Computer: ids, product URIs, times
E5 Reuse           share of weekly re-runs that can reuse their output, per query design
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from lineage.identity import DEFAULT_SORTBY  # noqa: E402
from study.collect import CATALOGS, CITIES, DATA, bbox_of  # noqa: E402

OUT = Path(__file__).resolve().parent
UA = {"User-Agent": "stac-lineage-study/1.0"}
N = 10  # items per "latest N" query
WEEKS = [datetime(2025, 1, 6, tzinfo=timezone.utc) + timedelta(weeks=k) for k in range(52)]  # Mondays 00:00 UTC
FIXED = ("2025-03-01T00:00:00Z", "2025-03-31T23:59:59Z")  # a fixed past period queried weekly from April
random.seed(1)


def ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load(name: str) -> list[dict]:
    with open(DATA / f"items_{name}.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def by_city(rows):
    d = defaultdict(list)
    for r in rows:
        d[r["city"]].append(r)
    return d


def pct(x, n):
    return 0.0 if not n else 100.0 * x / n


# ------------------------------------------------------------------ E1 repeatability (live)

def post_search(cat: str, body: dict) -> list[str] | None:
    url, coll = CATALOGS[cat]
    try:
        r = requests.post(url + "/search", json={"collections": [coll], **body}, headers=UA, timeout=60)
        r.raise_for_status()
        return [f["id"] for f in r.json()["features"]]
    except requests.RequestException:
        return None


def e1_repeatability(repeats: int = 3) -> dict:
    out = {}
    for cat in CATALOGS:
        res = {"sorted": [0, 0, 0], "default": [0, 0, 0]}  # [queries, same order, same set]
        default_equals_sorted = default_set_equals_sorted = 0
        for city in CITIES:
            body = {"bbox": bbox_of(city), "datetime": "2025-01-01T00:00:00Z/2025-12-31T23:59:59Z", "limit": N}
            lists = {}
            for mode in ("sorted", "default"):
                b = dict(body, sortby=DEFAULT_SORTBY) if mode == "sorted" else body
                got = [post_search(cat, b) for _ in range(repeats)]
                got = [g for g in got if g is not None]
                lists[mode] = got
                res[mode][0] += 1
                res[mode][1] += all(g == got[0] for g in got)
                res[mode][2] += all(set(g) == set(got[0]) for g in got)
            if lists["sorted"] and lists["default"]:
                default_equals_sorted += lists["default"][0] == lists["sorted"][0]
                default_set_equals_sorted += set(lists["default"][0]) == set(lists["sorted"][0])
        out[cat] = {"cities": res["sorted"][0], "repeats": repeats,
                    "sorted_same_order": res["sorted"][1], "default_same_order": res["default"][1],
                    "default_same_set": res["default"][2], "default_equals_sorted": default_equals_sorted,
                    "default_set_equals_sorted": default_set_equals_sorted}
    return out


# ------------------------------------------------------------------ E2 window churn (rebuilt)

def latest_n(items: list[dict], as_of: datetime, n: int = N) -> list[str]:
    eligible = [r for r in items if ts(r["datetime"]) <= as_of]
    eligible.sort(key=lambda r: (-ts(r["datetime"]).timestamp(), r["id"]))
    return [r["id"] for r in eligible[:n]]


def e2_window_churn(es: dict[str, list[dict]]) -> dict:
    diffs = []
    removed_ids = []
    for city, items in es.items():
        prev = None
        for d in WEEKS:
            cur = latest_n(items, d)
            if prev is not None:
                a, r = set(cur) - set(prev), set(prev) - set(cur)
                diffs.append({"city": city, "added": len(a), "removed": len(r), "identical": not a and not r})
                removed_ids += [(city, i) for i in r]
            prev = cur
    n = len(diffs)
    # every removed id is in the 2025 list we collected, i.e. still in the catalog: confirm a sample live
    sample = random.sample(removed_ids, min(60, len(removed_ids)))
    url, coll = CATALOGS["earthsearch"]
    exists = Counter()
    for _, i in sample:
        try:
            code = requests.get(f"{url}/collections/{coll}/items/{i}", headers=UA, timeout=30).status_code
        except requests.RequestException:
            code = None
        exists["present" if code == 200 else "absent" if code == 404 else "error"] += 1
    # check the rebuild against the live catalog for a few (city, week) pairs
    checks = []
    for city, d in random.sample([(c, w) for c in es for w in WEEKS[4:]], 12):
        live = post_search("earthsearch", {"bbox": bbox_of(city), "datetime": f"../{d.strftime('%Y-%m-%dT%H:%M:%SZ')}",
                                           "limit": N, "sortby": DEFAULT_SORTBY})
        checks.append(live == latest_n(es[city], d) if live is not None else None)
    return {
        "weekly_diffs": n,
        "mean_added": st.mean(x["added"] for x in diffs),
        "mean_removed": st.mean(x["removed"] for x in diffs),
        "share_with_removed": pct(sum(x["removed"] > 0 for x in diffs), n),
        "share_identical": pct(sum(x["identical"] for x in diffs), n),
        "removed_total": len(removed_ids),
        "removed_sample": len(sample),
        "removed_sample_still_in_catalog": exists["present"],
        "removed_sample_absent": exists["absent"],
        "removed_sample_errors": exists["error"],
        "rebuild_checks": len(checks),
        "rebuild_matches_live": sum(c is True for c in checks),
    }


# ------------------------------------------------------------------ E3 mutability

def e3_mutability(es_rows: list[dict], es: dict[str, list[dict]]) -> dict:
    lags = []
    for r in es_rows:
        c, u = ts(r["created"]), ts(r["updated"])
        if c and u:
            lags.append((u - c).total_seconds())
    n = len(lags)
    thresholds = {"1h": 3600, "1d": 86400, "30d": 30 * 86400}
    shares = {k: pct(sum(lag > v for lag in lags), n) for k, v in thresholds.items()}
    later = sorted(lag / 86400 for lag in lags if lag > 86400)
    # weekly re-runs of a fixed past period (March 2025), from 7 April: would an id-only identity have
    # reused an output whose inputs were updated since the previous run?
    reruns = stale = 0
    first = datetime(2025, 4, 7, tzinfo=timezone.utc)
    schedule = [first + timedelta(weeks=k) for k in range(39)]  # through the end of 2025
    lo, hi = ts(FIXED[0]), ts(FIXED[1])
    affected_cities = set()
    for city, items in es.items():
        march = [r for r in items if lo <= ts(r["datetime"]) <= hi]
        for a, b in zip(schedule, schedule[1:]):
            reruns += 1
            if any(ts(r["updated"]) and a < ts(r["updated"]) <= b for r in march):
                stale += 1
                affected_cities.add(city)
    return {
        "items_with_timestamps": n,
        "updated_after_creation_share": shares,
        "median_days_when_later_than_1d": st.median(later) if later else None,
        "fixed_period_reruns": reruns,
        "fixed_period_reruns_with_updated_inputs": stale,
        "fixed_period_cities_affected": len(affected_cities),
        "updated_months": dict(sorted(Counter(r["updated"][:7] for r in es_rows if r.get("updated")).items())),
    }


# ------------------------------------------------------------------ E4 identity across catalogs

def sensing_key(scene_key: str) -> str:
    """Product URI without processing baseline and generation time: mission, sensing time, orbit, tile."""
    p = scene_key.split("_")
    if len(p) >= 7 and p[3].startswith("N"):
        return "_".join(p[:3] + p[4:6])
    return scene_key


def e4_identity(es_rows: list[dict], pc_rows: list[dict]) -> dict:
    es_keys = {r["scene_key"]: r for r in es_rows}
    pc_keys = {r["scene_key"]: r for r in pc_rows}
    both = set(es_keys) & set(pc_keys)
    id_equal = sum(es_keys[k]["id"] == pc_keys[k]["id"] for k in both)
    dt_diff = [abs((ts(es_keys[k]["datetime"]) - ts(pc_keys[k]["datetime"])).total_seconds()) for k in both]
    es_s = Counter(sensing_key(r["scene_key"]) for r in es_rows)
    pc_s = Counter(sensing_key(r["scene_key"]) for r in pc_rows)
    sens_both = set(es_s) & set(pc_s)
    baselines = {"earthsearch": Counter(r["baseline"] for r in es_rows), "planetary": Counter(r["baseline"] for r in pc_rows)}
    same_sensing_diff_uri = len({sensing_key(k) for k in es_keys} & {sensing_key(k) for k in pc_keys}) - len({sensing_key(k) for k in both})
    # one acquisition delivered more than once (same baseline, different generation time) within a catalog
    def regenerated(rows):
        g = defaultdict(set)
        for r in rows:
            g[sensing_key(r["scene_key"])].add(r["scene_key"])
        return sum(len(v) > 1 for v in g.values()), sum(len(v) - 1 for v in g.values())
    return {
        "earthsearch_items": len(es_rows), "planetary_items": len(pc_rows),
        "earthsearch_unique_scene_keys": len(es_keys), "planetary_unique_scene_keys": len(pc_keys),
        "matched_by_product_uri": len(both),
        "share_of_earthsearch_matched": pct(len(both), len(es_keys)),
        "matched_with_equal_ids": id_equal,
        "datetime_diff_seconds_median": st.median(dt_diff) if dt_diff else None,
        "datetime_diff_seconds_max": max(dt_diff) if dt_diff else None,
        "matched_by_sensing_key": len(sens_both),
        "share_of_earthsearch_matched_by_sensing": pct(len(sens_both), len(es_s)),
        "sensing_matches_with_different_uri": same_sensing_diff_uri,
        "duplicate_sensings": {"earthsearch": sum(v > 1 for v in es_s.values()), "planetary": sum(v > 1 for v in pc_s.values())},
        "regenerated": {"earthsearch": regenerated(es_rows), "planetary": regenerated(pc_rows)},
        "baselines": {k: dict(v.most_common(6)) for k, v in baselines.items()},
    }


# ------------------------------------------------------------------ E5 reuse by query design

def e5_reuse(es: dict[str, list[dict]]) -> dict:
    def rate(query):
        same = total = 0
        for items in es.values():
            prev = None
            for d in WEEKS[14:]:  # from April, when the fixed period is over
                cur = query(items, d)
                if prev is not None:
                    total += 1
                    same += set(cur) == set(prev)
                prev = cur
        return pct(same, total), total

    lo, hi = ts(FIXED[0]), ts(FIXED[1])
    designs = {
        "latest_10": lambda items, d: latest_n(items, d),
        "rolling_30_days": lambda items, d: sorted(r["id"] for r in items if d - timedelta(days=30) < ts(r["datetime"]) <= d),
        "fixed_period_march": lambda items, d: sorted(r["id"] for r in items if lo <= ts(r["datetime"]) <= hi and ts(r["datetime"]) <= d),
    }
    return {k: {"reuse_share_by_ids": rate(f)[0], "reruns": rate(f)[1]} for k, f in designs.items()}


def main():
    es_rows, pc_rows = load("earthsearch"), load("planetary")
    es = by_city(es_rows)
    res = {"cities": list(CITIES), "period": "2025", "n": N,
           "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    print("E4 identity ..."); res["e4_identity"] = e4_identity(es_rows, pc_rows)
    print("E3 mutability ..."); res["e3_mutability"] = e3_mutability(es_rows, es)
    print("E5 reuse ..."); res["e5_reuse"] = e5_reuse(es)
    print("E2 window churn (with live checks) ..."); res["e2_window"] = e2_window_churn(es)
    print("E1 repeatability (live) ..."); res["e1_repeatability"] = e1_repeatability()
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    write_md(res)
    print((OUT / "results.md").read_text(encoding="utf-8"))


def write_md(r: dict):
    e1, e2, e3, e4, e5 = r["e1_repeatability"], r["e2_window"], r["e3_mutability"], r["e4_identity"], r["e5_reuse"]
    L = [f"# STAC lineage study — results\n\n{len(r['cities'])} cities, Sentinel-2 L2A, {r['period']}; generated {r['generated']}.\n",
         "## E1 Repeatability (same query, asked again)\n", "| Catalog | cities | sorted: same order | default: same order | default: same set | default order = sorted | default set = sorted |", "|---|---:|---:|---:|---:|---:|---:|"]
    for k, v in e1.items():
        L.append(f"| {k} | {v['cities']} | {v['sorted_same_order']} | {v['default_same_order']} | {v['default_same_set']} | {v['default_equals_sorted']} | {v['default_set_equals_sorted']} |")
    L += ["\n## E2 Weekly 'latest 10' pipeline (Earth Search)\n",
          f"{e2['weekly_diffs']} weekly diffs: mean {e2['mean_added']:.2f} added and {e2['mean_removed']:.2f} removed; "
          f"{e2['share_with_removed']:.0f}% of diffs report removals; {e2['share_identical']:.0f}% identical. "
          f"Of {e2['removed_sample']} sampled 'removed' items, {e2['removed_sample_still_in_catalog']} are still in the catalog "
          f"({e2['removed_sample_absent']} absent, {e2['removed_sample_errors']} errors). Rebuild matches the live catalog in "
          f"{e2['rebuild_matches_live']} of {e2['rebuild_checks']} checks.\n",
          "## E3 Mutability (Earth Search created/updated)\n",
          f"{e3['items_with_timestamps']} items; updated after creation by more than 1 h: {e3['updated_after_creation_share']['1h']:.1f}%, "
          f"1 day: {e3['updated_after_creation_share']['1d']:.1f}%, 30 days: {e3['updated_after_creation_share']['30d']:.1f}%; "
          f"median lag when > 1 day: {e3['median_days_when_later_than_1d']:.1f} days.\n",
          f"Weekly re-runs of a fixed past period (March 2025): {e3['fixed_period_reruns_with_updated_inputs']} of {e3['fixed_period_reruns']} "
          f"re-runs had inputs updated since the previous run ({e3['fixed_period_cities_affected']} cities); each such case would be one where an id-only identity reuses a stale output.\n",
          f"Months of 'updated': {e3['updated_months']}\n",
          "## E4 Identity across catalogs\n",
          f"Earth Search {e4['earthsearch_items']} items ({e4['earthsearch_unique_scene_keys']} product URIs), Planetary Computer {e4['planetary_items']} "
          f"({e4['planetary_unique_scene_keys']}). Matched by product URI: {e4['matched_by_product_uri']} ({e4['share_of_earthsearch_matched']:.1f}% of Earth Search); "
          f"equal ids among them: {e4['matched_with_equal_ids']}; datetime difference median {e4['datetime_diff_seconds_median']} s, max {e4['datetime_diff_seconds_max']} s. "
          f"By sensing key (without baseline and generation time): {e4['matched_by_sensing_key']} ({e4['share_of_earthsearch_matched_by_sensing']:.1f}%). Acquisitions delivered more than once (same sensing, different generation time): {e4['regenerated']} (acquisitions, extra items). Baselines: {e4['baselines']}\n",
          "## E5 Reuse by query design (weekly re-runs from April)\n", "| Design | re-runs | reusable (same ids) |", "|---|---:|---:|"]
    for k, v in e5.items():
        L.append(f"| {k} | {v['reruns']} | {v['reuse_share_by_ids']:.1f}% |")
    (OUT / "results.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
