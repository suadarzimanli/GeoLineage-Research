"""Transform: list of STAC items → one GeoParquet (footprints + id, datetime)."""

import hashlib
from pathlib import Path
from dataclasses import dataclass

import geopandas as gpd
from shapely.geometry import shape
from pystac import Item

CRS_WGS84 = "EPSG:4326"


@dataclass
class TransformResult:
    """Output path and checksum for lineage."""
    output_path: str
    checksum: str
    crs: str = CRS_WGS84


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def items_to_geoparquet(
    items: list[Item],
    output_dir: Path | str,
    filename: str = "footprints.parquet",
    crs: str = CRS_WGS84,
) -> TransformResult:
    """
    Build a GeoDataFrame from item geometries (footprints), write GeoParquet.
    Returns output path (str), checksum, and crs for lineage.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename

    rows = []
    for item in items:
        geom = item.geometry
        if geom is None:
            continue
        shp = shape(geom)
        dt = item.datetime.isoformat() if item.datetime else None
        rows.append({"id": item.id, "datetime": dt, "geometry": shp})

    if not rows:
        # Empty GeoDataFrame with same schema
        gdf = gpd.GeoDataFrame(columns=["id", "datetime", "geometry"], geometry="geometry", crs=crs)
    else:
        gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=crs)

    gdf.to_parquet(output_path, index=False)

    checksum = _file_sha256(output_path)
    return TransformResult(
        output_path=str(output_path),
        checksum=checksum,
        crs=crs,
    )
