import json
import zipfile

import pytest

from app.services import file_reader
from app.services.file_reader import InvalidFileError, read_geo_file


def test_reads_kml_with_mixed_geometry_types(mixed_kml):
    parsed = read_geo_file(str(mixed_kml), "mixed.kml")

    assert parsed.crs == "EPSG:4326"
    assert [f.index for f in parsed.features] == [0, 1, 2]
    assert {f.geometry_type for f in parsed.features} == {"Polygon", "LineString", "Point"}


def test_reads_the_sample_kml_file(sample_kml):
    parsed = read_geo_file(str(sample_kml), "square.kml")

    assert len(parsed.features) == 1
    assert parsed.features[0].geometry_type == "Polygon"


def test_reads_zipped_shapefile(shapefile_zip):
    parsed = read_geo_file(str(shapefile_zip), "plots.zip")

    assert parsed.crs == "EPSG:4326"
    assert len(parsed.features) == 2
    assert all(f.geometry_type == "Polygon" for f in parsed.features)
    assert parsed.features[0].properties["name"] == "Plot A"


def test_properties_are_json_safe(shapefile_zip):
    parsed = read_geo_file(str(shapefile_zip), "plots.zip")

    second = parsed.features[1].properties
    assert second["area_ha"] is None      # the missing number became null, not NaN
    for feature in parsed.features:
        json.dumps(feature.properties, allow_nan=False)   # must not raise


def test_shapefile_without_crs_is_rejected(shapefile_zip_no_prj):
    with pytest.raises(InvalidFileError, match="no CRS"):
        read_geo_file(str(shapefile_zip_no_prj), "plots.zip")


def test_shapefile_missing_dbf_is_rejected(shapefile_zip_no_dbf):
    with pytest.raises(InvalidFileError, match=r"\.dbf"):
        read_geo_file(str(shapefile_zip_no_dbf), "plots.zip")


def test_zip_without_shapefile_is_rejected(tmp_path):
    zip_path = tmp_path / "notes.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("notes.txt", "hello")

    with pytest.raises(InvalidFileError, match="No .shp"):
        read_geo_file(str(zip_path), "notes.zip")


def test_fake_zip_is_rejected(tmp_path):
    fake = tmp_path / "fake.zip"
    fake.write_text("this is not a zip")

    with pytest.raises(InvalidFileError, match="not a valid zip"):
        read_geo_file(str(fake), "fake.zip")


def test_unsupported_extension_is_rejected(tmp_path):
    txt = tmp_path / "data.txt"
    txt.write_text("hello")

    with pytest.raises(InvalidFileError, match="Unsupported file type"):
        read_geo_file(str(txt), "data.txt")


def test_broken_kml_is_rejected(tmp_path):
    bad = tmp_path / "bad.kml"
    bad.write_text("this is not kml")

    with pytest.raises(InvalidFileError):
        read_geo_file(str(bad), "bad.kml")


def test_zip_that_is_too_big_when_unpacked_is_rejected(shapefile_zip, monkeypatch):
    monkeypatch.setattr(file_reader, "MAX_UNZIPPED_BYTES", 10)

    with pytest.raises(InvalidFileError, match="too large"):
        read_geo_file(str(shapefile_zip), "plots.zip")