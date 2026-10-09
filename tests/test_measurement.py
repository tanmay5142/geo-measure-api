import pytest
from pyproj import Geod, Transformer
from shapely.geometry import (
    GeometryCollection, LineString, MultiPolygon, Point, Polygon,
)
from shapely.ops import transform

from app.services.measurement import measure

GEOD = Geod(ellps="WGS84")

# A square of about 0.01 x 0.01 degrees near Bengaluru
SQUARE = Polygon([
    (77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98),
])


def test_polygon_area_is_close_to_geodesic_area():
    result = measure(SQUARE)
    expected, _ = GEOD.geometry_area_perimeter(SQUARE)

    assert result.type == "area"
    assert result.unit == "m2"
    assert result.crs_used == "EPSG:32643"
    assert result.error is None
    assert result.value == pytest.approx(abs(expected), rel=0.005)  # within 0.5%


def test_polygon_area_is_in_a_sensible_range():
    # About 1085 m x 1106 m is roughly 1.2 million square meters
    assert 1.15e6 < measure(SQUARE).value < 1.25e6


def test_area_in_degrees_would_be_wrong():
    # This is the mistake the task wants us to avoid
    assert SQUARE.area < 0.001
    assert measure(SQUARE).value > 1_000_000


def test_linestring_length_is_close_to_geodesic_length():
    line = LineString([(77.59, 12.97), (77.59, 12.98)])
    result = measure(line)
    expected = GEOD.geometry_length(line)

    assert result.type == "length"
    assert result.unit == "m"
    assert result.value == pytest.approx(expected, rel=0.005)


def test_multipolygon_adds_up_the_areas():
    other = Polygon([
        (77.61, 12.97), (77.62, 12.97), (77.62, 12.98), (77.61, 12.98),
    ])
    result = measure(MultiPolygon([SQUARE, other]))
    single = measure(SQUARE).value

    assert result.value == pytest.approx(2 * single, rel=0.01)


def test_point_has_no_measurement_and_no_error():
    result = measure(Point(77.59, 12.97))

    assert result.type is None
    assert result.value is None
    assert result.error is None


def test_unsupported_geometry_returns_error_instead_of_crashing():
    result = measure(GeometryCollection([Point(77.59, 12.97)]))

    assert result.value is None
    assert "Unsupported geometry type" in result.error


def test_empty_geometry_returns_error():
    assert "Empty" in measure(Polygon()).error


def test_missing_geometry_returns_error():
    assert "Empty or missing" in measure(None).error


def test_self_crossing_polygon_returns_error():
    bowtie = Polygon([
        (77.59, 12.97), (77.60, 12.98), (77.60, 12.97), (77.59, 12.98),
    ])
    assert "Invalid" in measure(bowtie).error


def test_input_in_utm_gives_same_area_as_input_in_wgs84():
    to_utm = Transformer.from_crs(4326, 32643, always_xy=True)
    square_utm = transform(to_utm.transform, SQUARE)

    from_utm = measure(square_utm, source_crs="EPSG:32643")
    from_wgs84 = measure(SQUARE)

    assert from_utm.value == pytest.approx(from_wgs84.value, rel=0.001)