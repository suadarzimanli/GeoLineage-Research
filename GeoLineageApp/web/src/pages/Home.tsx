import { Link } from "react-router-dom";

export function Home() {
  return (
    <section className="hero">
      <p className="brand" style={{ fontSize: "1rem", margin: 0, opacity: 0.85 }}>
        GeoLineage
      </p>
      <h1>Save the search, not just the map screenshot.</h1>
      <p>
        Pick an area, pull matching satellite scenes from a public catalog, and keep the outlines
        plus a receipt of what went into the result. Runs live in the cloud, so nothing depends on a
        laptop-only folder.
      </p>
      <div className="cta-row">
        <Link className="btn btn-primary" to="/run">
          Start a run
        </Link>
        <Link className="btn btn-ghost" to="/history">
          View history
        </Link>
        <Link className="btn btn-ghost" to="/about">
          How it works
        </Link>
      </div>
    </section>
  );
}
