"""STAC-based ingest for GeoLineage."""

from .stac_ingest import search_stac, StacIngestResult

__all__ = ["search_stac", "StacIngestResult"]
