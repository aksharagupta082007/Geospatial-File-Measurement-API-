from __future__ import annotations

import math
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd

from app.domain import ProcessedDataset, SourceFeature
from app.services.errors import UserInputError
from app.services.kml import read_kml


def process_upload(source_path: Path, extract_dir: Path) -> ProcessedDataset:
    suffix = source_path.suffix.lower()
    if suffix == ".kml":
        return read_kml(source_path)
    if suffix == ".zip":
        return _read_shapefile_zip(source_path, extract_dir)
    raise UserInputError("Unsupported file type. Upload a .kml file or a .zip containing a Shapefile.")


def _read_shapefile_zip(zip_path: Path, extract_dir: Path) -> ProcessedDataset:
    extract_dir.mkdir(parents=True, exist_ok=True)
    _safe_extract_zip(zip_path, extract_dir)

    shapefiles = sorted(extract_dir.rglob("*.shp"))
    if not shapefiles:
        raise UserInputError("The ZIP archive does not contain a .shp file.")
    if len(shapefiles) > 1:
        raise UserInputError("The ZIP archive contains multiple .shp files; upload one Shapefile per archive.")

    try:
        geodata = gpd.read_file(shapefiles[0])
    except Exception as exc:
        raise UserInputError("The Shapefile could not be read.") from exc

    if geodata.empty:
        raise UserInputError("The Shapefile does not contain any features.")

    crs = geodata.crs.to_string() if geodata.crs is not None else None
    features: list[SourceFeature] = []
    for source_index, row in geodata.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty:
            continue

        properties = {
            key: _jsonable(value)
            for key, value in row.drop(labels=["geometry"]).to_dict().items()
        }
        features.append(
            SourceFeature(
                feature_id=str(source_index),
                index=len(features),
                geometry=geometry,
                geometry_type=geometry.geom_type,
                properties=properties,
                crs=crs,
            )
        )

    if not features:
        raise UserInputError("No non-empty geometries were found in the Shapefile.")

    return ProcessedDataset(features=features, crs=crs)


def _safe_extract_zip(zip_path: Path, extract_dir: Path) -> None:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                target = (extract_dir / member.filename).resolve()
                if not str(target).startswith(str(extract_dir.resolve())):
                    raise UserInputError("The ZIP archive contains an unsafe file path.")
            archive.extractall(extract_dir)
    except zipfile.BadZipFile as exc:
        raise UserInputError("The uploaded file is not a valid ZIP archive.") from exc


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        return _jsonable(value.item())
    return str(value)
