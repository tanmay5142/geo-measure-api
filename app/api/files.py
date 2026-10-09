import logging
import os
import tempfile
from contextlib import contextmanager, suppress

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import MAX_UPLOAD_BYTES
from app.database import get_db
from app.models import Feature, FileStatus, UploadedFile
from app.schemas import (
    FeatureOut, FileInfo, MeasurementOut, MeasurementsResponse, MeasurementSummary,
)
from app.services.processing import process_upload

router = APIRouter(prefix="/api/files", tags=["files"])

ALLOWED_SUFFIXES = {".zip", ".kml"}
CHUNK_SIZE = 1024 * 1024  # read uploads 1 MB at a time


def _clean_filename(name: str | None) -> str:
    """Keep only the file name itself, never a path."""
    if not name:
        raise HTTPException(status_code=400, detail="A file with a name is required.")
    return os.path.basename(name.replace("\\", "/"))[:255]


@contextmanager
def _saved_upload(upload: UploadFile, suffix: str):
    """Save the upload to a temporary file, and always delete it afterwards."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        total = 0
        with os.fdopen(fd, "wb") as out:
            while chunk := upload.file.read(CHUNK_SIZE):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File is too large. The limit is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                    )
                out.write(chunk)
        yield path
    finally:
        with suppress(FileNotFoundError):
            os.remove(path)


def _get_file_or_404(db: Session, file_id: str) -> UploadedFile:
    record = db.get(UploadedFile, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="File not found.")
    return record


def _feature_out(f: Feature) -> FeatureOut:
    measurement = None
    if f.measurement_type is not None:
        measurement = MeasurementOut(
            type=f.measurement_type,
            value=f.measurement_value,
            unit=f.unit,
            crs_used=f.crs_used,
        )
    return FeatureOut(
        index=f.feature_index,
        geometry_type=f.geometry_type,
        geometry=f.geometry,
        crs=f.crs,
        properties=f.properties,
        measurement=measurement,
        error=f.error,
    )


@router.post("/", response_model=FileInfo, status_code=201)
def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a .kml or a zipped Shapefile. It is processed right away."""
    filename = _clean_filename(file.filename)
    suffix = os.path.splitext(filename)[1].lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload a .zip (Shapefile) or a .kml file.",
        )

    with _saved_upload(file, suffix) as path:
        record = process_upload(db, path, filename)

    if record.status == FileStatus.FAILED:
        return JSONResponse(
            status_code=422,
            content={"detail": record.error_message, "id": record.id, "status": record.status},
        )
    return record


@router.get("/{file_id}/", response_model=FileInfo)
def get_file(file_id: str, db: Session = Depends(get_db)):
    """Basic information about an uploaded file."""
    return _get_file_or_404(db, file_id)


@router.get("/{file_id}/measurements/", response_model=MeasurementsResponse)
def get_measurements(
    file_id: str,
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Measurements for the features of a file (paged)."""
    record = _get_file_or_404(db, file_id)
    if record.status != FileStatus.COMPLETED:
        detail = f"File is not ready (status: {record.status})."
        if record.error_message:
            detail += f" {record.error_message}"
        raise HTTPException(status_code=409, detail=detail)

    count = select(func.count()).select_from(Feature).where(Feature.file_id == file_id)
    measured = db.scalar(count.where(Feature.measurement_value.is_not(None)))
    errors = db.scalar(count.where(Feature.error.is_not(None)))

    rows = db.scalars(
        select(Feature)
        .where(Feature.file_id == file_id)
        .order_by(Feature.feature_index)
        .offset(offset)
        .limit(limit)
    ).all()

    return MeasurementsResponse(
        file_id=record.id,
        crs=record.crs,
        feature_count=record.feature_count,
        limit=limit,
        offset=offset,
        summary=MeasurementSummary(
            measured=measured,
            no_measurement=record.feature_count - measured - errors,
            errors=errors,
        ),
        features=[_feature_out(f) for f in rows],
    )