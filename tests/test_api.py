from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import geopandas as gpd
from fastapi import HTTPException, UploadFile
from fastapi.routing import APIRoute
from shapely.geometry import Polygon

from app.config import Settings
from app.main import create_app


TEST_TMP = Path(__file__).resolve().parents[1] / ".test-tmp"


KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark id="point-1">
      <name>Control point</name>
      <Point><coordinates>-73.9857,40.7484,0</coordinates></Point>
    </Placemark>
    <Placemark id="line-1">
      <name>Survey line</name>
      <LineString><coordinates>-73.9857,40.7484,0 -73.9851,40.7489,0</coordinates></LineString>
    </Placemark>
    <Placemark id="polygon-1">
      <name>Parcel</name>
      <ExtendedData><Data name="owner"><value>Ada</value></Data></ExtendedData>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              -73.9860,40.7480,0 -73.9850,40.7480,0 -73.9850,40.7490,0 -73.9860,40.7490,0 -73.9860,40.7480,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>
"""


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        TEST_TMP.mkdir(exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=TEST_TMP)
        self.app = create_app(Settings(data_dir=Path(self.temp_dir.name)))
        self.upload_file = _endpoint(self.app, "/api/files/", "POST")
        self.get_file = _endpoint(self.app, "/api/files/{file_id}/", "GET")
        self.get_measurements = _endpoint(self.app, "/api/files/{file_id}/measurements/", "GET")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_kml_upload_file_info_and_measurements(self) -> None:
        upload = UploadFile(filename="survey.kml", file=io.BytesIO(KML.encode("utf-8")))
        file_info = self.upload_file(file=upload)

        self.assertEqual(file_info["filename"], "survey.kml")
        self.assertEqual(file_info["feature_count"], 3)
        self.assertEqual(file_info["crs"], "EPSG:4326")
        self.assertEqual(file_info["status"], "COMPLETED")

        info_response = self.get_file(file_id=file_info["id"])
        self.assertEqual(info_response["feature_count"], 3)

        measurements = self.get_measurements(file_id=file_info["id"])["measurements"]

        statuses = {item["feature_id"]: item["status"] for item in measurements}
        self.assertEqual(statuses["point-1"], "NOT_APPLICABLE")
        self.assertEqual(statuses["line-1"], "MEASURED")
        self.assertEqual(statuses["polygon-1"], "MEASURED")
        self.assertGreater(_by_id(measurements, "line-1")["length_m"], 0)
        self.assertGreater(_by_id(measurements, "polygon-1")["area_sq_m"], 0)
        self.assertEqual(_by_id(measurements, "polygon-1")["properties"]["owner"], "Ada")

    def test_rejects_unsupported_file_type(self) -> None:
        upload = UploadFile(filename="notes.txt", file=io.BytesIO(b"hello"))

        with self.assertRaises(HTTPException) as raised:
            self.upload_file(file=upload)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn(".kml", raised.exception.detail)

    def test_zipped_shapefile_upload(self) -> None:
        archive = _sample_shapefile_zip()
        upload = UploadFile(filename="parcel.zip", file=archive)
        file_info = self.upload_file(file=upload)

        self.assertEqual(file_info["feature_count"], 1)
        self.assertEqual(file_info["crs"], "EPSG:4326")

        measurements = self.get_measurements(file_id=file_info["id"])["measurements"]
        self.assertEqual(measurements[0]["status"], "MEASURED")
        self.assertGreater(measurements[0]["area_sq_m"], 0)


def _endpoint(app, path: str, method: str):
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route.endpoint
    raise AssertionError(f"Endpoint {method} {path} not found")


def _by_id(measurements: list[dict], feature_id: str) -> dict:
    return next(item for item in measurements if item["feature_id"] == feature_id)


def _sample_shapefile_zip() -> io.BytesIO:
    TEST_TMP.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TEST_TMP) as directory:
        directory_path = Path(directory)
        shapefile_path = directory_path / "parcel.shp"
        geodata = gpd.GeoDataFrame(
            {"name": ["Test parcel"]},
            geometry=[Polygon([(-73.986, 40.748), (-73.985, 40.748), (-73.985, 40.749), (-73.986, 40.749), (-73.986, 40.748)])],
            crs="EPSG:4326",
        )
        geodata.to_file(shapefile_path)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for file_path in directory_path.iterdir():
                archive.write(file_path, file_path.name)
        buffer.seek(0)
        return buffer


if __name__ == "__main__":
    unittest.main()
