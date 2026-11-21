"""Offline tests for identity, diff and run scoping:  python -m unittest discover -s tests -t ."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lineage.diff import diff_since_last_run, input_assets_equal  # noqa: E402
from lineage.identity import (  # noqa: E402
    DEFAULT_SORTBY, classify_removed, diff_inputs, item_content_hash, normalize_datetime, query_key, scene_key)
from lineage.schema import InputAsset, LineageRun, OutputAsset, TransformStep  # noqa: E402
from lineage.store import get_previous_run_for_query, record_run, run_query_key  # noqa: E402

ITEM = {
    "id": "S2A_T32TMT_20250629T103535_L2A",
    "bbox": [8.0, 47.0, 9.0, 48.0],
    "geometry": {"type": "Polygon", "coordinates": [[[8, 47], [9, 47], [9, 48], [8, 48], [8, 47]]]},
    "properties": {"datetime": "2025-06-29T10:38:02Z", "updated": "2025-06-29T16:21:55Z",
                   "s2:product_uri": "S2A_MSIL2A_20250629T102701_N0511_R108_T32TMT_20250629T143707.SAFE"},
    "assets": {"red": {"href": "s3://bucket/red.tif"}},
    "links": [{"rel": "self", "href": "https://catalog-a/items/x"}],
}


class Keys(unittest.TestCase):
    def test_datetime_normalisation(self):
        self.assertEqual(normalize_datetime("2025-06-01/2025-06-30"), "2025-06-01T00:00:00Z/2025-06-30T23:59:59Z")
        self.assertEqual(normalize_datetime("../2025-06-30"), "../2025-06-30T23:59:59Z")
        self.assertEqual(normalize_datetime("2025-06-01T10:00:00Z"), "2025-06-01T10:00:00Z")
        self.assertIsNone(normalize_datetime(""))
        for bad in ("yesterday", "2025-13", "../..", "a/b/c"):
            with self.assertRaises(ValueError):
                normalize_datetime(bad)

    def test_query_key_is_stable_and_specific(self):
        a = query_key("https://c/v1/", "s2", [8.48, 47.34, 8.58, 47.40], "2025-06-01/2025-06-30", 10)
        b = query_key("https://c/v1", "s2", (8.4800000001, 47.34, 8.58, 47.4), "2025-06-01T00:00:00Z/2025-06-30T23:59:59Z", 10, DEFAULT_SORTBY)
        self.assertEqual(a, b)  # trailing slash, float noise and date spelling do not matter
        self.assertNotEqual(a, query_key("https://c/v1", "s2", [8.48, 47.34, 8.58, 47.40], "2025-06-01/2025-06-30", 11))
        self.assertNotEqual(a, query_key("https://c/v1", "s2", [8.48, 47.34, 8.58, 47.41], "2025-06-01/2025-06-30", 10))

    def test_content_hash_ignores_links_but_sees_metadata(self):
        h = item_content_hash(ITEM)
        moved = json.loads(json.dumps(ITEM)); moved["links"][0]["href"] = "https://catalog-b/items/x"
        self.assertEqual(h, item_content_hash(moved))
        edited = json.loads(json.dumps(ITEM)); edited["properties"]["updated"] = "2025-07-01T00:00:00Z"
        self.assertNotEqual(h, item_content_hash(edited))
        rehref = json.loads(json.dumps(ITEM)); rehref["assets"]["red"]["href"] = "s3://bucket/red_v2.tif"
        self.assertNotEqual(h, item_content_hash(rehref))

    def test_scene_key_uses_product_uri(self):
        self.assertEqual(scene_key(ITEM), "S2A_MSIL2A_20250629T102701_N0511_R108_T32TMT_20250629T143707")
        self.assertEqual(scene_key({"id": "x", "properties": {}}), "x")


class Diffs(unittest.TestCase):
    def test_added_removed_changed_unchanged(self):
        d = diff_inputs({"a": "1", "b": "2", "c": "3"}, {"b": "2", "c": "9", "d": "4"})
        self.assertEqual((d.added, d.removed, d.changed, d.unchanged), (["d"], ["a"], ["c"], ["b"]))
        self.assertFalse(d.identical)
        self.assertTrue(diff_inputs({"a": "1"}, {"a": "1"}).identical)

    def test_unknown_hash_compares_by_id(self):
        self.assertTrue(diff_inputs({"a": None}, {"a": "1"}).identical)

    def test_removed_reasons(self):
        d = classify_removed(diff_inputs({"a": "1", "b": "2", "c": "3"}, {}), {"a": True, "b": False, "c": None}.get)
        self.assertEqual(d.removed_reason, {"a": "outside_window", "b": "gone", "c": "unknown"})

    def test_input_equality_needs_same_content(self):
        a = [InputAsset("x", "h", content_hash="1")]
        self.assertTrue(input_assets_equal(a, [InputAsset("x", "h2", content_hash="1")]))
        self.assertFalse(input_assets_equal(a, [InputAsset("x", "h", content_hash="2")]))


def make_run(run_id, ts, bbox, ids, catalog="https://c/v1"):
    sp = {"bbox": bbox, "collection": "s2", "datetime": None, "max_items": 10, "sortby": DEFAULT_SORTBY}
    sp["query_key"] = query_key(catalog, "s2", bbox, None, 10, DEFAULT_SORTBY)
    return LineageRun(run_id, ts, catalog, sp, [InputAsset(i, "h", content_hash=i + "h") for i in ids],
                      [TransformStep("t", {"crs": "EPSG:4326"})], [OutputAsset("p", "c", "EPSG:4326")])


class Scoping(unittest.TestCase):
    def test_previous_run_is_the_same_query_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            zurich, london = [8.48, 47.34, 8.58, 47.40], [-0.15, 51.48, 0.0, 51.55]
            r1 = make_run("r1", "2025-01-01T00:00:00.000001Z", london, ["a", "b"])
            r2 = make_run("r2", "2025-01-01T00:00:00.000002Z", zurich, ["z1"])
            r3 = make_run("r3", "2025-01-01T00:00:00.000003Z", london, ["b", "c"])
            for r in (r1, r2, r3):
                record_run(r, d)
            self.assertIsNone(get_previous_run_for_query("r2", run_query_key(r2), d))  # first Zurich run
            self.assertEqual(get_previous_run_for_query("r3", run_query_key(r3), d), "r1")  # skips Zurich
            diff = diff_since_last_run(r3, d)
            self.assertEqual(diff.previous_run_id, "r1")
            self.assertEqual(([a.id for a in diff.added], [a.id for a in diff.removed]), (["c"], ["a"]))
            self.assertIsNone(diff_since_last_run(r2, d).previous_run_id)

    def test_old_receipts_without_query_key_still_match(self):
        r = make_run("old", "2024-01-01T00:00:00Z", [1, 2, 3, 4], ["a"])
        stored_key = r.search_params.pop("query_key")
        self.assertEqual(run_query_key(r), stored_key)

    def test_unsorted_legacy_runs_are_a_different_query(self):
        r = make_run("old", "2024-01-01T00:00:00Z", [1, 2, 3, 4], ["a"])
        sorted_key = r.search_params.pop("query_key")
        r.search_params.pop("sortby")
        self.assertNotEqual(run_query_key(r), sorted_key)

    def test_query_key_matches_the_worker(self):
        # same vector is asserted in GeoLineageApp/worker/test/lineage.test.ts
        self.assertEqual(query_key("https://earth-search.aws.element84.com/v1", "sentinel-2-c1-l2a",
                                   [8.48, 47.34, 8.58, 47.4], "2025-06-01/2025-06-30", 10),
                         "928ac3a41981c560ddb4d4ded090e222a3f23f2319e3ee0ee81e0bfe27d991d3")


if __name__ == "__main__":
    unittest.main()
