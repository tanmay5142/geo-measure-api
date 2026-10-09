from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

WGS84 = CRS.from_epsg(4326)

def to_wgs84(geom: BaseGeometry, source_crs) -> BaseGeometry:
  """Convert a shape to plain latitude/longitude (EPSG:4326)."""
  source = CRS.from_user_input(source_crs)
  if source == WGS84:
    return geom
  transformer = Transformer.from_crs(source, WGS84, always_xy=True)
  return transform(transformer.transform, geom)

def utm_epsg_for(geom_wgs84: BaseGeometry) -> int:
  """Pick the UTM zone (as an EPSG code) for a shape in lat/lon."""
  if geom_wgs84.is_empty:
    raise ValueError("Cannot pick a CRS for an empty geometry")

  center = geom_wgs84.centroid
  lon, lat = center.x, center.y

  if not (-180 <= lon <= 180 and -90 <= lat <= 90):
    raise ValueError("Coordinates out of range: lon={lon}, lat={lat}")

  zone = min(int((lon + 180) // 6) + 1, 60)
  return (32600 if lat >= 0 else 32700) + zone