from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry

from app.domain import ProcessedDataset, SourceFeature
from app.services.errors import UserInputError


GEOMETRY_TAGS = {"Point", "LineString", "Polygon", "MultiGeometry"}


def read_kml(path: Path) -> ProcessedDataset:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise UserInputError("The KML file is not valid XML.") from exc

    features: list[SourceFeature] = []
    for index, placemark in enumerate(_iter_local(root, "Placemark")):
        geometry_element = _first_geometry_element(placemark)
        if geometry_element is None:
            continue

        geometry = _parse_geometry(geometry_element)
        if geometry.is_empty:
            continue

        feature_id = placemark.attrib.get("id") or str(index)
        features.append(
            SourceFeature(
                feature_id=feature_id,
                index=len(features),
                geometry=geometry,
                geometry_type=geometry.geom_type,
                properties=_properties_for_placemark(placemark),
                crs="EPSG:4326",
            )
        )

    if not features:
        raise UserInputError("No placemark geometries were found in the KML file.")

    return ProcessedDataset(features=features, crs="EPSG:4326")


def _parse_geometry(element: ET.Element) -> BaseGeometry:
    tag = _local_name(element.tag)
    if tag == "Point":
        coordinates = _coordinates_from_text(_first_text(element, "coordinates"))
        if not coordinates:
            raise UserInputError("A KML Point is missing coordinates.")
        return Point(coordinates[0])

    if tag == "LineString":
        coordinates = _coordinates_from_text(_first_text(element, "coordinates"))
        if len(coordinates) < 2:
            raise UserInputError("A KML LineString must contain at least two coordinates.")
        return LineString(coordinates)

    if tag == "Polygon":
        outer = _first_child(element, "outerBoundaryIs")
        if outer is None:
            raise UserInputError("A KML Polygon is missing an outer boundary.")

        shell = _coordinates_from_text(_first_text(outer, "coordinates"))
        holes = [
            _coordinates_from_text(_first_text(inner, "coordinates"))
            for inner in _direct_children(element, "innerBoundaryIs")
        ]
        holes = [hole for hole in holes if hole]
        if len(shell) < 4:
            raise UserInputError("A KML Polygon outer boundary must contain at least four coordinates.")
        return Polygon(shell=shell, holes=holes)

    if tag == "MultiGeometry":
        geometries = [_parse_geometry(child) for child in element if _local_name(child.tag) in GEOMETRY_TAGS]
        if not geometries:
            raise UserInputError("A KML MultiGeometry does not contain supported geometry members.")
        return _combine_geometries(geometries)

    raise UserInputError(f"KML geometry type '{tag}' is not supported.")


def _combine_geometries(geometries: list[BaseGeometry]) -> BaseGeometry:
    types = {geometry.geom_type for geometry in geometries}
    if types == {"Point"}:
        return MultiPoint(geometries)
    if types == {"LineString"}:
        return MultiLineString(geometries)
    if types == {"Polygon"}:
        return MultiPolygon(geometries)
    return GeometryCollection(geometries)


def _coordinates_from_text(text: str | None) -> list[tuple[float, float]]:
    if not text:
        return []

    coordinates: list[tuple[float, float]] = []
    for raw_tuple in text.replace("\n", " ").replace("\t", " ").split():
        parts = raw_tuple.split(",")
        if len(parts) < 2:
            continue
        try:
            lon = float(parts[0])
            lat = float(parts[1])
        except ValueError as exc:
            raise UserInputError(f"Invalid KML coordinate tuple: '{raw_tuple}'.") from exc
        coordinates.append((lon, lat))
    return coordinates


def _properties_for_placemark(placemark: ET.Element) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for key in ("name", "description"):
        value = _first_text(placemark, key, direct_only=True)
        if value:
            properties[key] = value

    for data in _iter_local(placemark, "Data"):
        name = data.attrib.get("name")
        value = _first_text(data, "value", direct_only=True)
        if name and value is not None:
            properties[name] = value

    for simple_data in _iter_local(placemark, "SimpleData"):
        name = simple_data.attrib.get("name")
        if name and simple_data.text is not None:
            properties[name] = simple_data.text.strip()

    return properties


def _first_geometry_element(placemark: ET.Element) -> ET.Element | None:
    for element in placemark.iter():
        if element is placemark:
            continue
        if _local_name(element.tag) in GEOMETRY_TAGS:
            return element
    return None


def _first_text(element: ET.Element, local_name: str, direct_only: bool = False) -> str | None:
    candidates = _direct_children(element, local_name) if direct_only else _iter_local(element, local_name)
    for candidate in candidates:
        if candidate.text is not None:
            return candidate.text.strip()
    return None


def _first_child(element: ET.Element, local_name: str) -> ET.Element | None:
    for child in element.iter():
        if _local_name(child.tag) == local_name:
            return child
    return None


def _direct_children(element: ET.Element, local_name: str) -> Iterable[ET.Element]:
    for child in element:
        if _local_name(child.tag) == local_name:
            yield child


def _iter_local(element: ET.Element, local_name: str) -> Iterable[ET.Element]:
    for child in element.iter():
        if _local_name(child.tag) == local_name:
            yield child


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
