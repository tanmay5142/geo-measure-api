import pytest
from pyproj import Transformer
from shapely.geometry import Point, Polygon
from shapely.ops import transform

from app.services.crs import to_wgs84, utm_epsg_for

def test_bengaluru_is_utm_zone_43_north():
  assert utm_epsg_for(Point(77.595, 12.975)) == 32643

def test_sydney_is_southern_hemisphere():
  assert utm_epsg_for(Point(151.2, -33.9)) == 32756

def test_longitude_180_stays_in_zone_60():
  assert utm_epsg_for(Point(180, 10)) == 32660

def test_empty_geometry_raises():
  with pytest.raises(ValueError):
    utm_epsg_for(Polygon())

def test_out_of_range_coordinates_raise():
  with pytest.raises(ValueError):
    utm_epsg_for(Point(200, 10))

def test_to_wgs84_returns_same_shape_when_already_wgs84():
  p = Point(77.595, 12.975)
  assert to_wgs84(p, "EPSG:4326").equals(p)

def test_to_wgs84_round_trip_from_utm():
  original = Point(77.595, 12.975)
  to_utm = Transformer.from_crs(4326, 32643, always_xy=True)
  in_utm = transform(to_utm.transform, original)

  back = to_wgs84(in_utm, "EPSG:32643")

  assert back.x == pytest.approx(original.x, abs=1e-6)
  assert back.y == pytest.approx(original.y, abs=1e-6)