from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True)
class SourceFeature:
    feature_id: str
    index: int
    geometry: BaseGeometry
    geometry_type: str
    properties: dict[str, Any]
    crs: str | None


@dataclass(frozen=True)
class ProcessedDataset:
    features: list[SourceFeature]
    crs: str | None
