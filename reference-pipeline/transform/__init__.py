"""Transforms: STAC items → analysis-ready outputs (GeoParquet)."""

from .footprints_to_geoparquet import items_to_geoparquet, TransformResult

__all__ = ["items_to_geoparquet", "TransformResult"]
