import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Feature, FileStatus, UploadedFile


def make_feature(index, **overrides):
    values = dict(
        feature_index=index,
        geometry_type="Polygon",
        crs="EPSG:4326",
        properties={},
    )
    values.update(overrides)
    return Feature(**values)


def test_new_file_gets_default_values(db_session):
    uploaded = UploadedFile(filename="survey.kml")
    db_session.add(uploaded)
    db_session.commit()

    assert len(uploaded.id) == 36          # a UUID as text
    assert uploaded.status == FileStatus.PROCESSING
    assert uploaded.feature_count == 0
    assert uploaded.created_at is not None
    assert uploaded.crs is None
    assert uploaded.error_message is None


def test_file_and_features_can_be_saved_and_read_back(db_session):
    uploaded = UploadedFile(
        filename="plots.zip", crs="EPSG:4326",
        feature_count=2, status=FileStatus.COMPLETED,
    )
    uploaded.features = [
        make_feature(
            0,
            geometry={"type": "Point", "coordinates": [77.59, 12.97]},
            properties={"name": "Plot A", "area_ha": 1.5},
            measurement_type="area", measurement_value=1196283.4,
            unit="m2", crs_used="EPSG:32643",
        ),
        make_feature(
            1,
            geometry_type="GeometryCollection", geometry=None,
            error="Unsupported geometry type: GeometryCollection",
        ),
    ]
    db_session.add(uploaded)
    db_session.commit()
    db_session.expire_all()              # forget everything, so we read from the database

    saved = db_session.get(UploadedFile, uploaded.id)
    first, second = saved.features

    assert saved.status == FileStatus.COMPLETED
    assert first.properties == {"name": "Plot A", "area_ha": 1.5}
    assert first.geometry["coordinates"] == [77.59, 12.97]
    assert first.measurement_value == pytest.approx(1196283.4)
    assert first.error is None
    assert second.geometry is None
    assert "Unsupported" in second.error      # one bad feature, stored with its error


def test_features_come_back_in_file_order(db_session):
    uploaded = UploadedFile(filename="plots.zip")
    uploaded.features = [make_feature(2), make_feature(0), make_feature(1)]
    db_session.add(uploaded)
    db_session.commit()
    db_session.expire_all()

    saved = db_session.get(UploadedFile, uploaded.id)
    assert [f.feature_index for f in saved.features] == [0, 1, 2]


def test_deleting_a_file_deletes_its_features(db_session):
    uploaded = UploadedFile(filename="plots.zip")
    uploaded.features = [make_feature(0), make_feature(1)]
    db_session.add(uploaded)
    db_session.commit()

    db_session.delete(uploaded)
    db_session.commit()

    assert db_session.scalars(select(Feature)).all() == []


def test_two_features_with_the_same_index_are_rejected(db_session):
    uploaded = UploadedFile(filename="plots.zip")
    uploaded.features = [make_feature(0), make_feature(0)]
    db_session.add(uploaded)

    with pytest.raises(IntegrityError):
        db_session.commit()