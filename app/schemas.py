from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


FileStatus = Literal["PROCESSING", "COMPLETED", "FAILED"]
MeasurementStatus = Literal["MEASURED", "NOT_APPLICABLE", "UNSUPPORTED"]


class FileInfo(BaseModel):
    id: str
    filename: str
    feature_count: int
    crs: str | None
    status: FileStatus
    uploaded_at: datetime
    error: str | None = None


class FeatureMeasurement(BaseModel):
    feature_id: str
    feature_index: int
    geometry_type: str
    geometry: dict[str, Any]
    crs: str | None
    properties: dict[str, Any] = Field(default_factory=dict)
    area_sq_m: float | None = None
    length_m: float | None = None
    projected_crs: str | None = None
    status: MeasurementStatus
    message: str | None = None


class MeasurementsResponse(BaseModel):
    file_id: str
    measurements: list[FeatureMeasurement]


class ErrorResponse(BaseModel):
    detail: str
