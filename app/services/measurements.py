from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pyproj import CRS, Transformer
from shapely.geometry import mapping
from shapely.ops import transform

from app.domain import SourceFeature


@dataclass(frozen=True)
class MeasurementResult:
    feature_id: str
    feature_index: int
    geometry_type: str
    geometry: dict[str, Any]
    crs: str | None
    properties: dict[str, Any]
    area_sq_m: float | None
    length_m: float | None
    projected_crs: str | None
    status: str
    message: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_index": self.feature_index,
            "geometry_type": self.geometry_type,
            "geometry": self.geometry,
            "crs": self.crs,
            "properties": self.properties,
            "area_sq_m": self.area_sq_m,
            "length_m": self.length_m,
            "projected_crs": self.projected_crs,
            "status": self.status,
            "message": self.message,
        }


def measure_features(features: list[SourceFeature]) -> list[MeasurementResult]:
    return [measure_feature(feature) for feature in features]


def measure_feature(feature: SourceFeature) -> MeasurementResult:
    geometry = feature.geometry
    geometry_type = geometry.geom_type
    base = {
        "feature_id": feature.feature_id,
        "feature_index": feature.index,
        "geometry_type": geometry_type,
        "geometry": mapping(geometry),
        "crs": feature.crs,
        "properties": feature.properties,
    }

    if geometry.is_empty:
        return MeasurementResult(**base, area_sq_m=None, length_m=None, projected_crs=None, status="UNSUPPORTED", message="Geometry is empty.")

    if geometry_type in {"Point", "MultiPoint"}:
        return MeasurementResult(
            **base,
            area_sq_m=None,
            length_m=None,
            projected_crs=None,
            status="NOT_APPLICABLE",
            message="Point geometries do not require measurement.",
        )

    if geometry_type not in {"LineString", "MultiLineString", "Polygon", "MultiPolygon"}:
        return MeasurementResult(
            **base,
            area_sq_m=None,
            length_m=None,
            projected_crs=None,
            status="UNSUPPORTED",
            message=f"Measurement is not implemented for {geometry_type}.",
        )

    if not feature.crs:
        return MeasurementResult(
            **base,
            area_sq_m=None,
            length_m=None,
            projected_crs=None,
            status="UNSUPPORTED",
            message="Input CRS is missing; measurement skipped to avoid unsafe units.",
        )

    try:
        source_crs = CRS.from_user_input(feature.crs)
    except Exception:
        return MeasurementResult(
            **base,
            area_sq_m=None,
            length_m=None,
            projected_crs=None,
            status="UNSUPPORTED",
            message=f"Input CRS '{feature.crs}' could not be parsed.",
        )

    try:
        projected_geometry, projected_crs, unit_factor = _project_for_measurement(geometry, source_crs)
    except ValueError as exc:
        return MeasurementResult(
            **base,
            area_sq_m=None,
            length_m=None,
            projected_crs=None,
            status="UNSUPPORTED",
            message=str(exc),
        )

    if geometry_type in {"Polygon", "MultiPolygon"}:
        return MeasurementResult(
            **base,
            area_sq_m=round(abs(projected_geometry.area) * (unit_factor**2), 3),
            length_m=None,
            projected_crs=projected_crs.to_string(),
            status="MEASURED",
            message=None,
        )

    return MeasurementResult(
        **base,
        area_sq_m=None,
        length_m=round(projected_geometry.length * unit_factor, 3),
        projected_crs=projected_crs.to_string(),
        status="MEASURED",
        message=None,
    )


def _project_for_measurement(geometry, source_crs: CRS):
    if source_crs.is_projected:
        return geometry, source_crs, _linear_unit_to_meters(source_crs)

    if not source_crs.is_geographic:
        raise ValueError("Input CRS is neither geographic nor projected; measurement skipped.")

    target_crs = _local_metric_crs_for_geometry(geometry)
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    projected_geometry = transform(transformer.transform, geometry)
    return projected_geometry, target_crs, 1.0


def _local_metric_crs_for_geometry(geometry) -> CRS:
    centroid = geometry.centroid
    lon = float(centroid.x)
    lat = float(centroid.y)

    if lat >= 84:
        return CRS.from_epsg(3413)
    if lat <= -80:
        return CRS.from_epsg(3031)

    zone = int((lon + 180) // 6) + 1
    zone = max(1, min(zone, 60))
    epsg = (32600 if lat >= 0 else 32700) + zone
    return CRS.from_epsg(epsg)


def _linear_unit_to_meters(crs: CRS) -> float:
    for axis in crs.axis_info:
        factor = getattr(axis, "unit_conversion_factor", None)
        if factor:
            return float(factor)
    return 1.0
