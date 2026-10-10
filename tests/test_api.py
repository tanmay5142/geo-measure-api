import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select

from app.api import files as files_api
from app.models import UploadedFile
from app.services import processing


def upload(client, path, filename=None):
    """Upload a file from disk the way a real client would."""
    path = Path(path)
    with open(path, "rb") as f:
        return client.post("/api/files/", files={"file": (filename or path.name, f)})


def measurements(client, file_id, **params):
    return client.get(f"/api/files/{file_id}/measurements/", params=params)


def features_by_type(body):
    return {f["geometry_type"]: f for f in body["features"]}


# ---------- Creating a job ----------

def test_upload_kml_creates_a_completed_job(client, mixed_kml, db_session):
    response = upload(client, mixed_kml)

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "mixed.kml"
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 3
    assert body["crs"] == "EPSG:4326"
    assert body["error_message"] is None

    saved = db_session.get(UploadedFile, body["id"])
    assert saved is not None
    assert len(saved.features) == 3


def test_upload_zipped_shapefile(client, shapefile_zip):
    response = upload(client, shapefile_zip)

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "plots.zip"
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 2


# ---------- Job status ----------

def test_file_info_endpoint(client, sample_kml):
    file_id = upload(client, sample_kml).json()["id"]

    response = client.get(f"/api/files/{file_id}/")

    assert response.status_code == 200
    body = response.json()
    assert {"id", "filename", "feature_count", "crs", "status"} <= set(body)
    assert body["id"] == file_id
    assert body["filename"] == "square.kml"
    assert body["feature_count"] == 1
    assert body["crs"] == "EPSG:4326"
    assert body["status"] == "COMPLETED"


# ---------- Retrieving results ----------

def test_measurements_for_polygon_line_and_point(client, mixed_kml):
    file_id = upload(client, mixed_kml).json()["id"]

    response = measurements(client, file_id)

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {"measured": 2, "no_measurement": 1, "errors": 0}

    by_type = features_by_type(body)

    polygon = by_type["Polygon"]["measurement"]
    assert polygon["type"] == "area"
    assert polygon["unit"] == "m2"
    assert polygon["crs_used"] == "EPSG:32643"
    assert 1.15e6 < polygon["value"] < 1.25e6      # about 1.2 million square meters

    line = by_type["LineString"]["measurement"]
    assert line["type"] == "length"
    assert line["unit"] == "m"
    assert 1000 < line["value"] < 1200             # about 1.1 kilometers

    point = by_type["Point"]
    assert point["measurement"] is None            # points need no measurement
    assert point["error"] is None

    for feature in body["features"]:               # every feature shows the basics
        assert feature["geometry"] is not None
        assert feature["crs"] == "EPSG:4326"


def test_shapefile_features_keep_their_properties(client, shapefile_zip):
    file_id = upload(client, shapefile_zip).json()["id"]

    body = measurements(client, file_id).json()

    first, second = body["features"]
    assert [first["index"], second["index"]] == [0, 1]
    assert first["properties"]["name"] == "Plot A"
    assert first["properties"]["area_ha"] == 1.5
    assert second["properties"]["area_ha"] is None
    assert first["measurement"]["type"] == "area"
    assert body["summary"]["measured"] == 2


def test_measurements_can_be_paged(client, shapefile_zip):
    file_id = upload(client, shapefile_zip).json()["id"]

    first_page = measurements(client, file_id, limit=1).json()
    second_page = measurements(client, file_id, limit=1, offset=1).json()
    past_the_end = measurements(client, file_id, offset=5).json()

    assert [f["index"] for f in first_page["features"]] == [0]
    assert [f["index"] for f in second_page["features"]] == [1]
    assert first_page["feature_count"] == 2
    assert first_page["summary"]["measured"] == 2    # the summary covers the whole file
    assert past_the_end["features"] == []


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 5001}, {"offset": -1}])
def test_invalid_paging_values_are_rejected(client, sample_kml, params):
    file_id = upload(client, sample_kml).json()["id"]

    assert measurements(client, file_id, **params).status_code == 422


def test_unknown_file_id_returns_404(client):
    assert client.get("/api/files/does-not-exist/").status_code == 404
    assert client.get("/api/files/does-not-exist/measurements/").status_code == 404


# ---------- Input validation ----------

def test_wrong_file_extension_is_rejected(client, tmp_path, db_session):
    notes = tmp_path / "notes.txt"
    notes.write_text("hello")

    response = upload(client, notes)

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]
    assert db_session.scalars(select(UploadedFile)).all() == []   # nothing was saved


def test_request_without_a_file_is_rejected(client):
    assert client.post("/api/files/").status_code == 422


def test_unreadable_file_is_saved_as_failed(client, tmp_path):
    fake = tmp_path / "fake.zip"
    fake.write_text("this is not a zip")

    response = upload(client, fake)

    assert response.status_code == 422
    body = response.json()
    assert "not a valid zip" in body["detail"]
    assert body["status"] == "FAILED"

    info = client.get(f"/api/files/{body['id']}/").json()
    assert info["status"] == "FAILED"
    assert "not a valid zip" in info["error_message"]

    not_ready = measurements(client, body["id"])
    assert not_ready.status_code == 409
    assert "not a valid zip" in not_ready.json()["detail"]


def test_shapefile_without_crs_is_rejected(client, shapefile_zip_no_prj):
    response = upload(client, shapefile_zip_no_prj)

    assert response.status_code == 422
    assert "no CRS" in response.json()["detail"]


def test_file_that_is_too_large_is_rejected(client, shapefile_zip, monkeypatch, db_session):
    monkeypatch.setattr(files_api, "MAX_UPLOAD_BYTES", 10)

    response = upload(client, shapefile_zip)

    assert response.status_code == 413
    assert "too large" in response.json()["detail"]
    assert db_session.scalars(select(UploadedFile)).all() == []


def test_path_in_filename_is_removed(client, sample_kml):
    response = upload(client, sample_kml, filename="../../evil.kml")

    assert response.status_code == 201
    assert response.json()["filename"] == "evil.kml"


# ---------- One failure must not stop the rest ----------

def test_invalid_polygon_does_not_stop_other_features(client, invalid_polygon_kml):
    response = upload(client, invalid_polygon_kml)

    assert response.status_code == 201
    assert response.json()["status"] == "COMPLETED"

    body = measurements(client, response.json()["id"]).json()
    good = [f for f in body["features"] if f["error"] is None]
    bad = [f for f in body["features"] if f["error"]]

    assert len(good) == 1
    assert good[0]["measurement"]["type"] == "area"
    assert len(bad) == 1
    assert "Invalid geometry" in bad[0]["error"]
    assert bad[0]["measurement"] is None
    assert body["summary"] == {"measured": 1, "no_measurement": 0, "errors": 1}


def test_crash_while_measuring_one_feature_does_not_fail_the_file(
    client, mixed_kml, monkeypatch
):
    real_measure = processing.measure

    def flaky_measure(geom, crs):
        if geom.geom_type == "LineString":
            raise RuntimeError("something unexpected")
        return real_measure(geom, crs)

    monkeypatch.setattr(processing, "measure", flaky_measure)

    response = upload(client, mixed_kml)

    assert response.status_code == 201
    assert response.json()["status"] == "COMPLETED"

    body = measurements(client, response.json()["id"]).json()
    by_type = features_by_type(body)
    assert "Unexpected error" in by_type["LineString"]["error"]
    assert by_type["Polygon"]["measurement"]["type"] == "area"
    assert body["summary"] == {"measured": 1, "no_measurement": 1, "errors": 1}


# ---------- Cleanup ----------

def test_temp_files_are_deleted(
    client, mixed_kml, tmp_path, tmp_path_factory, monkeypatch
):
    upload_dir = tmp_path_factory.mktemp("uploads")
    monkeypatch.setattr(tempfile, "tempdir", str(upload_dir))

    fake = tmp_path / "fake.zip"
    fake.write_text("not a zip")

    assert upload(client, mixed_kml).status_code == 201   # a successful upload
    assert upload(client, fake).status_code == 422        # a failed upload

    assert list(upload_dir.iterdir()) == []               # nothing left behind