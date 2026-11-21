// End-to-end check of the Worker against test/mock-supabase.mjs (see header there).
const API = process.env.API || "http://127.0.0.1:8789";
const DB = "http://127.0.0.1:54321/rest/v1";
const LONDON = [-0.15, 51.48, 0.0, 51.55], ZURICH = [8.48, 47.34, 8.58, 47.4];
const ok = (name, cond, extra = "") => console.log(cond ? "PASS" : "FAIL", name, extra);
async function run(body) {
  const r = await fetch(API + "/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return { status: r.status, data: await r.json() };
}
const L = { bbox: LONDON, max_items: 3, datetime: "2025-06-01/2025-06-30" };

const a = await run(L);
ok("first London run: complete, no diff", a.status === 201 && a.data.run.status === "complete" && a.data.diff === null, a.data.run?.id);
ok("datetime normalised in receipt", a.data.receipt.search_params.datetime === "2025-06-01T00:00:00Z/2025-06-30T23:59:59Z");
ok("receipt has query key, sortby, matched, content hashes", !!a.data.receipt.search_params.query_key && Array.isArray(a.data.receipt.search_params.sortby) && a.data.receipt.search_params.matched > 0 && a.data.receipt.input_assets.every((x) => /^[0-9a-f]{64}$/.test(x.content_hash)));
const b = await run(L);
ok("second London run: reused, diff all unchanged", b.data.run.status === "reused" && b.data.run.reused_from_run_id === a.data.run.id && b.data.diff.unchanged.length === 3 && !b.data.diff.added.length, JSON.stringify({ u: b.data.diff.unchanged.length }));
ok("reused run still returns footprints", b.data.footprints?.features?.length === 3);
const z = await run({ ...L, bbox: ZURICH });
ok("Zurich: a different query -> first run, no diff", z.data.run.status === "complete" && z.data.diff === null);
const c = await run(L);
ok("third London run compares with London, not Zurich", c.data.diff?.compared_with_run_id === b.data.run.id && c.data.run.reused_from_run_id === a.data.run.id);
const d = await run({ ...L, max_items: 2 });
ok("different max_items -> new query, no diff", d.data.diff === null && d.data.run.status === "complete");
const bad = await run({ ...L, collection: "sentinel-2-c1-l" });
ok("misspelled collection rejected", bad.status === 400, bad.data.error?.slice(0, 50));
const empty = await run({ ...L, datetime: "1990-01-01/1990-01-02" });
ok("empty search rejected, nothing stored", empty.status === 422 && empty.data.empty === true);
const badDate = await run({ ...L, datetime: "June 2025" });
ok("malformed datetime rejected", badDate.status === 400, badDate.data.error);

// change detection: edit the latest London receipt (c) to hold a scene outside the window, a scene that
// does not exist, and a different content hash for one current scene; then run the query again
const rec = (await (await fetch(`${DB}/lineage_receipts?run_id=eq.${c.data.run.id}`)).json())[0].receipt;
const older = await (await fetch(API + "/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...L, max_items: 6 }) })).json();
const outsideId = older.features[5].id; // exists in the catalog, but not in the first 3
rec.input_assets = [...rec.input_assets.slice(0, 2), { id: outsideId, href: "x", content_hash: "0".repeat(64) }, { id: "S2X_FAKE_SCENE_L2A", href: "x", content_hash: "1".repeat(64) }];
rec.input_assets[0] = { ...rec.input_assets[0], content_hash: "f".repeat(64) };
await fetch(`${DB}/lineage_receipts?run_id=eq.${c.data.run.id}`, { method: "PATCH", body: JSON.stringify({ receipt: rec }) });
const e = await run(L);
const df = e.data.diff;
ok("changed scene detected (same id, new content)", df.changed.length === 1, JSON.stringify(df.changed));
ok("re-appearing scene counted as added", df.added.length === 1);
ok("removed reasons: outside_window and gone", df.removed_reason[outsideId] === "outside_window" && df.removed_reason["S2X_FAKE_SCENE_L2A"] === "gone", JSON.stringify(df.removed_reason));
ok("changed inputs prevent reuse", e.data.run.status === "complete");
const g = await (await fetch(API + "/runs/" + e.data.run.id)).json();
ok("GET run returns the stored diff with its reasons", g.diff?.compared_with_run_id === c.data.run.id && g.diff.removed_reason[outsideId] === "outside_window");

// legacy run (no query key, unsorted) with London parameters must not be treated as the same query
await fetch(`${DB}/runs`, { method: "POST", body: JSON.stringify({ catalog_url: a.data.run.catalog_url, collection: "sentinel-2-c1-l2a", bbox: LONDON, max_items: 3, input_count: 3, status: "complete", output_path: null, search_params: { bbox: LONDON, collection: "sentinel-2-c1-l2a", max_items: 3, datetime: "2025-06-01T00:00:00Z/2025-06-30T23:59:59Z" } }) });
const f = await run(L);
ok("legacy unsorted run is not the previous run", f.data.diff?.compared_with_run_id === e.data.run.id);
