import { Link } from "react-router-dom";

export function About() {
  return (
    <div className="stack">
      <div className="page-head">
        <h1>About GeoLineage</h1>
        <p>
          Short version: you search for satellite scenes over a place, and the app keeps enough
          detail that you can tell later what that search actually used and what file it wrote.
        </p>
      </div>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>Why bother</h2>
        <p style={{ margin: 0 }}>
          Satellite workflows are easy to do once and hard to explain a month later. Which catalog?
          Which collection? Which scene ids? GeoLineage writes that down on every run and stores the
          scene outlines (footprints) so you are not reconstructing the story from memory.
        </p>
        <p style={{ margin: 0 }}>
          If you already speak STAC: this is a small cloud lineage path from catalog search to a
          GeoJSON footprint product—params, input ids, one transform step, output checksum.
        </p>
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>What you get out of it</h2>
        <ul className="about-list">
          <li>
            History of past runs. Open one and you still see the scenes it used, not only a pretty
            map from that day.
          </li>
          <li>
            Footprint GeoJSON in storage. That is the outline of each scene, not a full image
            download.
          </li>
          <li>
            Reuse when nothing changed. Run exactly the same search again (same area, collection,
            dates and number of scenes) and, if the scenes and their content are unchanged, the
            earlier output is reused before anything is rebuilt.
          </li>
          <li>
            A comparison with the previous run of the same search: scenes added, removed or changed
            in place, and for each removed scene whether it is still in the catalog (it only fell
            out of the first results) or gone.
          </li>
        </ul>
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>How a run goes</h2>
        <ol className="about-list">
          <li>Choose a place—type a name, draw a box, or grab a preset—pick a collection and, if you
            like, a fixed date range (fixed past dates give repeatable results).</li>
          <li>Hit run. The app queries Earth Search (public Element84 STAC catalog).</li>
          <li>The result page shows footprints, a JSON receipt, and what changed since the last run of
            the same search (or says it is the first one).</li>
          <li>History keeps the list so you can open an old run again.</li>
        </ol>
        <p className="muted" style={{ margin: 0 }}>
          “Receipt” here just means the JSON bag of catalog URL, search params, input scenes,
          transform, and checksum. “Footprint” is the polygon of a scene on the ground.
        </p>
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>Stack</h2>
        <p style={{ margin: 0 }}>
          React UI on Cloudflare Pages, a small Worker for the API and STAC calls, Supabase for the
          database and files. This is a free-tier portfolio build. There is no real multi-user login;
          treat it like a demo you can host, not a production tenancy product.
        </p>
      </section>

      <div className="cta-row">
        <Link className="btn btn-primary" to="/run">
          Start a run
        </Link>
        <Link className="btn btn-ghost" to="/history">
          View history
        </Link>
      </div>
    </div>
  );
}
