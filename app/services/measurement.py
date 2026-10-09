from dataclasses import dataclass
from functools import lru_cache

from pyproj import Transformer
from pyproj.exceptions import ProjError
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from app.services.crs import to_wgs84, utm_epsg_for

AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "MultiLineString"}
NO_MEASUREMENT_TYPES = {"Point", "MultiPoint"}


@dataclass
class Measurement:
    type: str | None = None       # "area", "length" or None
    value: float | None = None
    unit: str | None = None       # "m2" or "m"
    crs_used: str | None = None   # the projected CRS used, e.g. "EPSG:32643"
    error: str | None = None


@lru_cache(maxsize=64)
def _transformer_to_utm(epsg: int) -> Transformer:
    # Building a transformer is slow, so we reuse it for the same zone.
    return Transformer.from_crs(4326, epsg, always_xy=True)


def measure(geom: BaseGeometry | None, source_crs="EPSG:4326") -> Measurement:
    if geom is None or geom.is_empty:
        return Measurement(error="Empty or missing geometry")

    kind = geom.geom_type

    if kind in NO_MEASUREMENT_TYPES:
        return Measurement()

    if kind not in AREA_TYPES and kind not in LENGTH_TYPES:
        return Measurement(error=f"Unsupported geometry type: {kind}")

    if not geom.is_valid:
        return Measurement(error="Invalid geometry (for example, it crosses itself)")

    try:
        geom_wgs84 = to_wgs84(geom, source_crs)
        epsg = utm_epsg_for(geom_wgs84)
        projected = transform(_transformer_to_utm(epsg).transform, geom_wgs84)
    except (ValueError, ProjError) as exc:
        return Measurement(error=f"Could not project geometry: {exc}")

    if kind in AREA_TYPES:
        return Measurement("area", projected.area, "m2", f"EPSG:{epsg}")
    return Measurement("length", projected.length, "m", f"EPSG:{epsg}")