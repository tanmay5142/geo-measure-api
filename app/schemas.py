from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    feature_count: int
    crs: str | None
    status: str
    error_message: str | None = None
    created_at: datetime


class MeasurementOut(BaseModel):
    type: str            # "area" or "length"
    value: float
    unit: str            # "m2" or "m"
    crs_used: str        # the projected CRS used, e.g. "EPSG:32643"


class FeatureOut(BaseModel):
    index: int
    geometry_type: str
    geometry: dict | None
    crs: str
    properties: dict
    measurement: MeasurementOut | None   # null for points and for failed features
    error: str | None


class MeasurementSummary(BaseModel):
    measured: int          # features with an area or length
    no_measurement: int    # features that don't need one (points)
    errors: int            # features that failed


class MeasurementsResponse(BaseModel):
    file_id: str
    crs: str | None
    feature_count: int
    limit: int
    offset: int
    summary: MeasurementSummary
    features: list[FeatureOut]