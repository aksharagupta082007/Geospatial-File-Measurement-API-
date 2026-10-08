from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, status

from app.config import Settings, get_settings
from app.domain import SourceFeature
from app.schemas import ErrorResponse, FileInfo, MeasurementsResponse
from app.services.errors import UserInputError
from app.services.measurements import measure_features
from app.services.processing import process_upload
from app.services.storage import FileStore


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    store = FileStore(app_settings.data_dir)
    store.initialize()

    app = FastAPI(
        title="Geospatial File Measurement API",
        version="1.0.0",
        description="Upload KML files or zipped Shapefiles and get per-feature area/length measurements.",
    )
    app.state.store = store
    app.state.settings = app_settings

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/api/files/",
        response_model=FileInfo,
        status_code=status.HTTP_201_CREATED,
        responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}},
    )
    def upload_file(file: UploadFile = File(...)) -> dict:
        filename = Path(file.filename or "").name
        if not filename:
            raise HTTPException(status_code=400, detail="A filename is required.")

        suffix = Path(filename).suffix.lower()
        if suffix not in {".zip", ".kml"}:
            raise HTTPException(status_code=400, detail="Upload a .kml file or a .zip containing a Shapefile.")

        record = store.create_record(filename)
        file_id = record["id"]
        try:
            source_path = store.save_upload(file_id, file, app_settings.max_upload_bytes)
            dataset = process_upload(source_path, store.upload_dir(file_id) / "extracted")
            measurements = measure_features(dataset.features)
            completed = store.complete_record(
                file_id=file_id,
                crs=dataset.crs,
                features=[_feature_to_dict(feature) for feature in dataset.features],
                measurements=[measurement.to_dict() for measurement in measurements],
            )
            return _public_record(completed)
        except ValueError as exc:
            store.fail_record(file_id, str(exc))
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except UserInputError as exc:
            store.fail_record(file_id, str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/files/{file_id}/", response_model=FileInfo, responses={404: {"model": ErrorResponse}})
    def get_file(file_id: str) -> dict:
        record = store.public_record(file_id)
        if record is None:
            raise HTTPException(status_code=404, detail="File not found.")
        return _public_record(record)

    @app.get(
        "/api/files/{file_id}/measurements/",
        response_model=MeasurementsResponse,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def get_measurements(file_id: str) -> dict:
        record = store.get_record(file_id)
        if record is None:
            raise HTTPException(status_code=404, detail="File not found.")
        if record["status"] != "COMPLETED":
            raise HTTPException(status_code=409, detail=f"File status is {record['status']}.")
        return {"file_id": file_id, "measurements": record["measurements"]}

    return app


def _feature_to_dict(feature: SourceFeature) -> dict:
    from shapely.geometry import mapping

    return {
        "feature_id": feature.feature_id,
        "feature_index": feature.index,
        "geometry_type": feature.geometry_type,
        "geometry": mapping(feature.geometry),
        "crs": feature.crs,
        "properties": feature.properties,
    }


def _public_record(record: dict) -> dict:
    public = {key: record[key] for key in ("id", "filename", "feature_count", "crs", "status", "uploaded_at", "error")}
    if isinstance(public["uploaded_at"], str):
        public["uploaded_at"] = datetime.fromisoformat(public["uploaded_at"])
    return public


app = create_app()
