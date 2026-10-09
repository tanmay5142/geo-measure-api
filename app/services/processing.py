import json
import logging

import shapely
from sqlalchemy.orm import Session

from app.models import Feature, FileStatus, UploadedFile
from app.services.file_reader import InvalidFileError, ParsedFeature, read_geo_file
from app.services.measurement import Measurement, measure

logger = logging.getLogger(__name__)


def _to_geojson(geom) -> dict | None:
    if geom is None:
        return None
    return json.loads(shapely.to_geojson(geom))


def _build_feature(parsed: ParsedFeature, crs: str) -> Feature:
    try:
        result = measure(parsed.geometry, crs)
    except Exception:
        # measure() should never raise, but one surprise must not fail the file
        logger.exception("Unexpected error measuring feature %s", parsed.index)
        result = Measurement(error="Unexpected error while measuring this feature")

    return Feature(
        feature_index=parsed.index,
        geometry_type=parsed.geometry_type,
        geometry=_to_geojson(parsed.geometry),
        crs=crs,
        properties=parsed.properties,
        measurement_type=result.type,
        measurement_value=result.value,
        unit=result.unit,
        crs_used=result.crs_used,
        error=result.error,
    )


def process_upload(db: Session, path: str, filename: str) -> UploadedFile:
    """Read the file, measure every feature and save everything.

    If the file can't be read, it is saved with status FAILED and the
    reason is in `error_message`. Nothing is raised in that case.
    """
    record = UploadedFile(filename=filename, status=FileStatus.PROCESSING.value)
    db.add(record)
    db.commit()   # the file has an id now, even if processing fails later

    try:
        parsed = read_geo_file(path, filename)
    except InvalidFileError as exc:
        record.status = FileStatus.FAILED.value
        record.error_message = str(exc)
        db.commit()
        return record

    try:
        record.crs = parsed.crs
        record.feature_count = len(parsed.features)
        record.features = [_build_feature(f, parsed.crs) for f in parsed.features]
        record.status = FileStatus.COMPLETED.value
        db.commit()
    except Exception:
        logger.exception("Unexpected error processing file %s", record.id)
        db.rollback()
        record.status = FileStatus.FAILED.value
        record.error_message = "Unexpected error while processing the file."
        db.commit()
        raise

    return record