r"""
Streamlit demo: run pipeline for a bbox, view lineage and diff since last run.

You MUST start it with:   streamlit run demo/app.py
Not with:                python demo/app.py

From the reference-pipeline folder (no venv activation):
  .venv\Scripts\streamlit.exe run demo/app.py
Or double-click: run_demo.bat
"""

from pathlib import Path
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

# If you ran "python demo/app.py" instead of "streamlit run demo/app.py", exit with a clear message.
def _running_under_streamlit_run():
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        try:
            return st.runtime.exists()
        except Exception:
            return True  # assume OK if we can't tell
if not _running_under_streamlit_run():
    print()
    print("  This is a Streamlit app. Do not run it with 'python demo/app.py'.")
    print()
    print("  Run it with:")
    print("    .venv\\Scripts\\streamlit.exe run demo/app.py")
    print()
    print("  Or double-click:  run_demo.bat")
    print()
    sys.exit(1)
from scripts.run_pipeline import run_pipeline
from lineage.store import list_runs, load_run, DEFAULT_LINEAGE_DIR
from lineage.diff import diff_since_last_run
from lineage.query import get_lineage

LINEAGE_DIR = ROOT / "lineage_runs"
OUTPUTS_DIR = ROOT / "outputs"

# Location presets: (minx, miny, maxx, maxy) in WGS84
LOCATION_PRESETS = {
    "San Francisco Bay": (-122.5, 37.5, -122.2, 37.8),
    "London": (-0.15, 51.48, 0.0, 51.55),
    "Paris": (2.28, 48.82, 2.42, 48.92),
    "Berlin": (13.35, 52.48, 13.45, 52.55),
    "New York (Manhattan area)": (-74.02, 40.70, -73.95, 40.78),
    "Tokyo": (139.70, 35.65, 139.80, 35.72),
    "Sydney": (150.98, -33.92, 151.05, -33.85),
    "Custom (edit numbers below)": None,
}

st.set_page_config(page_title="GeoLineage Demo", layout="wide", initial_sidebar_state="expanded")

# ---- Custom CSS ----
st.markdown("""
<style>
  .geo-intro {
    background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
    color: #fff;
    padding: 1.2rem 1.5rem;
    border-radius: 10px;
    margin-bottom: 1.5rem;
    font-size: 0.95rem;
    line-height: 1.5;
  }
  .geo-intro h3 { margin: 0 0 0.5rem 0; font-size: 1.1rem; }
  .geo-intro ul { margin: 0.5rem 0 0 1rem; padding: 0; }
  .geo-step {
    background: #f8fafc;
    border-left: 4px solid #2d5a87;
    padding: 0.8rem 1rem;
    margin: 0.5rem 0;
    border-radius: 0 8px 8px 0;
  }
  .geo-step strong { color: #1e3a5f; }
  .geo-card {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }
  .geo-card h4 { margin: 0 0 0.5rem 0; color: #1e3a5f; font-size: 1rem; }
  .stMap { border-radius: 8px; margin: 0.5rem 0; }
</style>
""", unsafe_allow_html=True)

# ---- Intro (plain language for non-coders) ----
st.markdown("""
<div class="geo-intro">
  <h3>What does this app do?</h3>
  <p>It fetches <strong>satellite scene footprints</strong> for a place you choose, saves a map file, and keeps a <strong>receipt</strong> (lineage) of what was used and what changed since the last run. A run usually takes <strong>a few seconds to a minute</strong> depending on the catalog.</p>
  <p><strong>How to start this app:</strong> Double-click <strong>run_demo.bat</strong> (Windows) or run <strong>streamlit run demo/app.py</strong> from the project folder. Then open the link shown (e.g. http://localhost:8501).</p>
  <p><strong>How to use it:</strong></p>
  <ul>
    <li><strong>1. Choose a location</strong> (or keep the default). Click <strong>Run pipeline</strong> in the sidebar.</li>
    <li><strong>2. Wait</strong> until you see &ldquo;Run completed&rdquo;.</li>
    <li><strong>3. Select a run</strong> below to see the output path, lineage receipt, and what changed vs the previous run.</li>
  </ul>
</div>
""", unsafe_allow_html=True)

st.title("GeoLineage — Provenance-first GeoETL")
st.caption("Fetch satellite data for an area and see exactly what was used and what changed.")
with st.expander("First time here? — 3 steps"):
    st.markdown("""
    1. **Pick a location** in the sidebar (e.g. San Francisco Bay, London) and leave the rest as is.
    2. Click **Run pipeline** and wait until you see "Run completed."
    3. **Select a run** in the dropdown below (the top one is your latest). Scroll down to see the output path, receipt, and what changed.
    """)
with st.expander("Technical description"):
    st.caption("STAC → GeoParquet pipeline; lineage and diff since last run.")

# Catalog presets (second source = Copernicus)
CATALOG_PRESETS = {
    "Earth Search (Sentinel-2)": ("https://earth-search.aws.element84.com/v1", "sentinel-2-c1-l2a"),
    "Copernicus Data Space (Sentinel-2)": ("https://stac.dataspace.copernicus.eu/v1", "SENTINEL-2"),
}

# Sidebar: run pipeline
with st.sidebar:
    st.header("Run pipeline")
    st.caption("Most users: pick a **Location** below and click **Run pipeline**. You can leave Catalog as is.")
    # Location preset (friendly for non-coders)
    location_choice = st.selectbox(
        "Location (area to fetch)",
        list(LOCATION_PRESETS.keys()),
        help="Pick a preset region; the numbers below update. Or choose Custom to type coordinates.",
    )
    preset_bbox = LOCATION_PRESETS.get(location_choice)
    if preset_bbox is not None:
        def_minx, def_miny, def_maxx, def_maxy = preset_bbox
    else:
        def_minx, def_miny, def_maxx, def_maxy = -122.5, 37.5, -122.2, 37.8

    preset = st.selectbox("Catalog preset", list(CATALOG_PRESETS.keys()), help="Choose a catalog; you can still edit URL and collection below.")
    _url, _coll = CATALOG_PRESETS[preset]
    catalog = st.text_input("STAC catalog URL", value=_url, help="Address of the STAC catalog.")
    collection = st.text_input("Collection", value=_coll, help="Collection id (e.g. sentinel-2-c1-l2a or SENTINEL-2).")
    minx = st.number_input("minx (west longitude)", value=def_minx, format="%.4f")
    miny = st.number_input("miny (south latitude)", value=def_miny, format="%.4f")
    maxx = st.number_input("maxx (east longitude)", value=def_maxx, format="%.4f")
    maxy = st.number_input("maxy (north latitude)", value=def_maxy, format="%.4f")
    max_items = st.slider("Max items", 1, 50, 10, help="How many satellite scenes to fetch (1–50).")

    if st.button("Run pipeline"):
        bbox = (minx, miny, maxx, maxy)
        try:
            with st.spinner("Running pipeline… (this may take a few seconds)"):
                run, run_id, reused_from = run_pipeline(
                    bbox=bbox,
                    catalog_url=catalog,
                    collection=collection,
                    max_items=max_items,
                    output_dir=OUTPUTS_DIR,
                    lineage_dir=LINEAGE_DIR,
                )
            if reused_from:
                st.success(f"Run completed. Output unchanged (reused from a previous run). Run ID: `{run_id[:8]}...`")
            else:
                st.success(f"Run completed. Scroll down to **Select run to inspect** and choose your run to see the result.")
            st.session_state["last_run_id"] = run_id
        except Exception as e:
            st.error("Something went wrong. Check your internet connection and try again, or pick a different location.")
            with st.expander("Error details (for troubleshooting)"):
                st.code(str(e))

# Sidebar: help
with st.sidebar:
    with st.expander("Need help?"):
        st.markdown("""
        **How to start:** Double‑click **run_demo.bat** (Windows) or run **streamlit run demo/app.py** from the project folder.

        **More help:** Open **docs/START_HERE.md** or **docs/USER_MANUAL.md** in the project folder for a step‑by‑step guide.
        """)

# Small map: where is this area? (center point)
with st.sidebar:
    st.caption("Map preview (center of area)")
    center_lat = (miny + maxy) / 2
    center_lon = (minx + maxx) / 2
    map_df = pd.DataFrame({"lat": [center_lat], "lon": [center_lon]})
    st.map(map_df, use_container_width=True)

# Main: list runs, show lineage, show diff
run_ids = list_runs(LINEAGE_DIR)
if not run_ids:
    st.markdown("""
    <div class="geo-step">
      <strong>No runs yet.</strong> Use the sidebar: pick a <strong>Location</strong>, then click <strong>Run pipeline</strong>. 
      When it finishes, this page will show your run and you can see the output path, lineage receipt, and what changed.
    </div>
    """, unsafe_allow_html=True)
    st.info("Use the sidebar to run the pipeline.")
else:
    # Sort by timestamp (newest first) and build friendly labels
    def _run_label(rid: str) -> str:
        r = load_run(rid, LINEAGE_DIR)
        if not r or not r.timestamp:
            return rid[:8] + "..."
        try:
            dt = datetime.fromisoformat(r.timestamp.replace("Z", "+00:00"))
            return dt.strftime("%d %b %Y, %H:%M") + " — " + rid[:8] + "..."
        except Exception:
            return rid[:8] + "..."
    runs_with_ts = [(rid, load_run(rid, LINEAGE_DIR)) for rid in run_ids]
    runs_with_ts = [(rid, r) for rid, r in runs_with_ts if r]
    runs_with_ts.sort(key=lambda x: x[1].timestamp or "", reverse=True)
    run_ids_sorted = [rid for rid, _ in runs_with_ts]
    labels = []
    for i, (rid, r) in enumerate(runs_with_ts):
        try:
            dt = datetime.fromisoformat((r.timestamp or "").replace("Z", "+00:00"))
            when = dt.strftime("%d %b %Y, %H:%M")
        except Exception:
            when = rid[:8]
        label = f"{when} — {rid[:8]}..." + (" (most recent)" if i == 0 else "")
        labels.append(label)
    run_options = dict(zip(labels, run_ids_sorted))
    default_idx = 0
    if st.session_state.get("last_run_id") in run_ids_sorted:
        default_idx = run_ids_sorted.index(st.session_state["last_run_id"])
    chosen_label = st.selectbox(
        "Select run to inspect",
        options=list(run_options.keys()),
        index=default_idx,
        help="Pick a run to see its output file path, receipt (lineage), and what changed vs the previous run.",
    )
    selected = run_options[chosen_label]
    run = load_run(selected, LINEAGE_DIR)
    if not run:
        st.warning("This run could not be loaded (the file may have been moved or deleted). Please choose another run from the list above.")
    elif run:
        st.markdown("""
        <div class="geo-step">
          <strong>You are here:</strong> You ran the pipeline. Below you see this run&rsquo;s <strong>output file</strong>, <strong>receipt (lineage)</strong>, and <strong>what changed</strong> compared to the previous run. Scroll down to see everything.
        </div>
        """, unsafe_allow_html=True)
        st.subheader(f"Run {selected[:8]}...")

        # Output & lineage paths (card-style)
        col_a, col_b = st.columns(2)
        with col_a:
            if run.output_assets:
                out_path = run.output_assets[0].path
                st.markdown("""
                <div class="geo-card">
                  <h4>Output file (copy path)</h4>
                  <p style="margin:0; color:#64748b; font-size:0.9rem;">Path to your map file. Copy this path to open the file in File Explorer (Windows) or Finder (Mac).</p>
                </div>
                """, unsafe_allow_html=True)
                st.code(out_path, language=None)
        with col_b:
            lineage_path = LINEAGE_DIR / "runs" / f"{run.run_id}.json"
            st.markdown("""
            <div class="geo-card">
              <h4>Lineage file (receipt)</h4>
              <p style="margin:0; color:#64748b; font-size:0.9rem;">Path to the receipt (lineage) for this run. You can open it in a text editor to see the full record.</p>
            </div>
            """, unsafe_allow_html=True)
            st.code(str(lineage_path), language=None)

        # Lineage DAG (nodes + edges)
        if run.lineage_dag:
            with st.expander("Lineage DAG (nodes → edges → outputs) — for experts"):
                st.caption("Technical view of how this output was produced (nodes and edges). Most users can skip this.")
                st.caption("Nodes")
                for n in run.lineage_dag.nodes:
                    st.code(f"{n.node_id} ({n.type}): {list(n.data.keys())}", language=None)
                st.caption("Edges")
                for e in run.lineage_dag.edges:
                    st.code(f"{e.from_node_id} --[{e.transform_name}]--> {e.to_node_id}", language=None)

        st.markdown("""
        <div class="geo-card">
          <h4>Full lineage (JSON)</h4>
          <p style="margin:0; color:#64748b; font-size:0.9rem;">Complete receipt in machine-readable form. You can copy this or open the lineage file path above in a text editor.</p>
        </div>
        """, unsafe_allow_html=True)
        st.json(run.to_dict())

        # What produced this output?
        if run.output_assets:
            produced = get_lineage(run_id=run.run_id, output_index=0, lineage_dir=LINEAGE_DIR)
            if produced:
                st.markdown("""
                <div class="geo-card">
                  <h4>What produced this output?</h4>
                  <p style="margin:0; color:#64748b; font-size:0.9rem;">Transform, parameters, and input set summary.</p>
                </div>
                """, unsafe_allow_html=True)
                st.write("**Transform:**", produced.produced_by.transform_name)
                st.json(produced.produced_by.parameters)
                st.write("**Inputs:**", len(produced.produced_by.inputs), "input set(s)")
                for i, inp in enumerate(produced.produced_by.inputs):
                    st.write("Catalog:", inp.get("catalog_url", ""))
                    st.json(inp.get("search_params", {}))
                    st.write("Input asset count:", inp.get("input_asset_count", 0))

        # Diff since previous run
        diff = diff_since_last_run(run, LINEAGE_DIR)
        st.markdown("""
        <div class="geo-card">
          <h4>Diff since previous run</h4>
          <p style="margin:0; color:#64748b; font-size:0.9rem;">What inputs were added, removed, or unchanged compared to the last run.</p>
        </div>
        """, unsafe_allow_html=True)
        if diff.previous_run_id:
            st.write("**Previous run:**", diff.previous_run_id)
            col1, col2, col3 = st.columns(3)
            col1.metric("Added inputs", len(diff.added))
            col2.metric("Removed inputs", len(diff.removed))
            col3.metric("Unchanged inputs", len(diff.unchanged))
            if diff.added:
                with st.expander("Added"):
                    for a in diff.added:
                        st.code(f"{a.id} {a.href[:80]}...")
            if diff.removed:
                with st.expander("Removed"):
                    for a in diff.removed:
                        st.code(f"{a.id} {a.href[:80]}...")
        else:
            st.write("No previous run to compare.")

        # Where is data stored? (for non-coders)
        st.markdown("---")
        st.markdown("""
        <div class="geo-step">
          <strong>Where is my data stored?</strong> Your output map file is in the project folder under <code>outputs/&lt;run_id&gt;/footprints.parquet</code>. 
          The receipt (lineage) is in <code>lineage_runs/runs/&lt;run_id&gt;.json</code>. You can open these folders in File Explorer (Windows) or Finder (Mac).
        </div>
        """, unsafe_allow_html=True)
