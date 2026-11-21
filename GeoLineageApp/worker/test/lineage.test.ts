// node --test test/  (Node 22.6+ strips the TypeScript types)
import { test } from "node:test";
import assert from "node:assert/strict";
import { ALLOWED_COLLECTIONS, canonicalJson, diffInputs, isIdentical, itemContentHash, normalizeDatetime, queryKey, receiptInputs, runQueryKey, sceneKey } from "../src/lineage.ts";

test("query key matches the Python reference pipeline", async () => {
  const k = await queryKey({ catalog_url: "https://earth-search.aws.element84.com/v1/", collection: "sentinel-2-c1-l2a", bbox: [8.48, 47.34, 8.58, 47.4], datetime: "2025-06-01/2025-06-30", max_items: 10 });
  assert.equal(k, "928ac3a41981c560ddb4d4ded090e222a3f23f2319e3ee0ee81e0bfe27d991d3");
});

test("content hash matches the Python reference pipeline and ignores links", async () => {
  const item = { id: "a", geometry: null, bbox: [1.5, 2.25, 3.5, 4.75], properties: { datetime: "2025-01-01T00:00:00Z", n: 3 }, assets: { b: { href: "x" }, a: { href: "y" } }, links: [{ rel: "self", href: "https://x" }] };
  assert.equal(await itemContentHash(item), "9de1c629e99f44d85c62c3c00566677969ac1bd5b35e777f69b270de564e2e21");
  assert.notEqual(await itemContentHash({ ...item, properties: { ...item.properties, n: 4 } }), await itemContentHash(item));
});

test("query key separates different questions and ignores spelling", async () => {
  const base = { catalog_url: "https://c/v1", collection: "s2", bbox: [8.48, 47.34, 8.58, 47.4], datetime: "2025-06-01/2025-06-30", max_items: 10 };
  const k = await queryKey(base);
  assert.equal(k, await queryKey({ ...base, datetime: "2025-06-01T00:00:00Z/2025-06-30T23:59:59Z", bbox: [8.4800000001, 47.34, 8.58, 47.4] }));
  assert.notEqual(k, await queryKey({ ...base, bbox: [-0.15, 51.48, 0, 51.55] }));
  assert.notEqual(k, await queryKey({ ...base, max_items: 5 }));
});

test("datetime normalisation", () => {
  assert.equal(normalizeDatetime("2025-06-01/2025-06-30"), "2025-06-01T00:00:00Z/2025-06-30T23:59:59Z");
  assert.equal(normalizeDatetime("../2025-06-30"), "../2025-06-30T23:59:59Z");
  assert.equal(normalizeDatetime(""), null);
  for (const bad of ["yesterday", "../..", "a/b/c", "2025-6-1"]) assert.throws(() => normalizeDatetime(bad));
});

test("diff: added, removed, changed, unchanged", () => {
  const d = diffInputs(new Map([["a", "1"], ["b", "2"], ["c", "3"]]), new Map([["b", "2"], ["c", "9"], ["d", "4"]]));
  assert.deepEqual([d.added, d.removed, d.changed, d.unchanged], [["d"], ["a"], ["c"], ["b"]]);
  assert.equal(isIdentical(d), false);
  assert.equal(isIdentical(diffInputs(new Map([["a", null]]), new Map([["a", "1"]]))), true); // old receipts: by id
});

test("legacy runs without a stored key: same parameters, unsorted -> their own query", async () => {
  const legacy = { catalog_url: "https://c/v1", collection: "s2", bbox: [1, 2, 3, 4], max_items: 10, search_params: { bbox: [1, 2, 3, 4], collection: "s2", max_items: 10, datetime: null } };
  const sorted = await queryKey({ catalog_url: "https://c/v1", collection: "s2", bbox: [1, 2, 3, 4], datetime: null, max_items: 10 });
  assert.notEqual(await runQueryKey(legacy), sorted);
  assert.equal(await runQueryKey({ ...legacy, search_params: { query_key: "abc" } }), "abc");
});

test("helpers", () => {
  assert.equal(sceneKey({ id: "x", properties: { "s2:product_uri": "S2A_MSIL2A_X.SAFE" } }), "S2A_MSIL2A_X");
  assert.equal(canonicalJson({ b: 1, a: [2, { d: null, c: "x" }] }), '{"a":[2,{"c":"x","d":null}],"b":1}');
  assert.deepEqual([...receiptInputs({ input_assets: [{ id: "a", content_hash: "h" }, { id: "b" }] })], [["a", "h"], ["b", null]]);
  assert.ok(ALLOWED_COLLECTIONS.includes("sentinel-2-c1-l2a") && !ALLOWED_COLLECTIONS.includes("sentinel-2-c1-l"));
});
