# Geospatial File Measurement API

A production-quality REST API built with **FastAPI** that accepts geospatial files (KML or zipped Shapefiles), parses their features, reprojects geometries to an appropriate metric CRS, and returns per-feature area and length measurements.

---

## Table of Contents

- [Features](#features)
- [Setup](#setup)
- [Running Locally](#running-locally)
- [Running Tests](#running-tests)
- [API Reference](#api-reference)
- [Architecture](#architecture)
- [CRS Handling](#crs-handling)
- [Design Decisions](#design-decisions)
- [Learnings](#learnings)
- [Future Scope](#future-scope)

---

## Features

- Upload a `.kml` file or a `.zip` containing a Shapefile
- Extracts and normalises all features (Point, LineString, Polygon, Multi\* variants)
- Reprojects geographic coordinates (e.g. EPSG:4326) to a local metric CRS before measuring
- Returns area (m²) for Polygons and length (m) for LineStrings
- Gracefully handles unsupported geometry types without crashing
- Stores file metadata and measurements persistently on disk
- Auto-generated interactive API docs via Swagger UI

---

## Setup

### Prerequisites

- Python 3.11+
- `pip`

### Install

```bash
git clone https://github.com/aksharagupta082007/Geospatial-File-Measurement-API-.git
cd Geospatial-File-Measurement-API-

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Environment Variables (optional)

| Variable | Default | Description |
|---|---|---|
| `GEOSPATIAL_DATA_DIR` | `data` | Directory where uploads and metadata are stored |
| `GEOSPATIAL_MAX_UPLOAD_BYTES` | `104857600` (100 MB) | Maximum allowed upload size in bytes |

---

## Running Locally

```bash
uvicorn app.main:app --reload
```

The server starts at **http://127.0.0.1:8000**

| URL | Purpose |
|---|---|
| http://127.0.0.1:8000/docs | Swagger UI — interactive API explorer |
| http://127.0.0.1:8000/redoc | ReDoc — alternative API reference |
| http://127.0.0.1:8000/healthz | Health check |

---

## Running Tests

```bash
python -m unittest discover -s tests -v
```

Expected output:

```
test_kml_upload_file_info_and_measurements ... ok
test_rejects_unsupported_file_type ... ok
test_zipped_shapefile_upload ... ok

----------------------------------------------------------------------
Ran 3 tests in ~0.5s

OK
```

Tests use isolated temporary directories — they do not touch the live `data/` folder.

---

## API Reference

### `POST /api/files/`

Upload and process a geospatial file.

**Accepted formats:**

| Format | Description |
|---|---|
| `.kml` | KML file |
| `.zip` | ZIP archive containing exactly one Shapefile (`.shp`, `.dbf`, `.prj`, etc.) |

**Request (multipart/form-data):**

```bash
# KML
curl -X POST http://127.0.0.1:8000/api/files/ \
  -F "file=@survey.kml"

# Zipped Shapefile
curl -X POST http://127.0.0.1:8000/api/files/ \
  -F "file=@parcels.zip"
```

**Response `201 Created`:**

```json
{
  "id": "a3f9c1d2e4b54c8fbd2e1234abcd5678",
  "filename": "survey.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "uploaded_at": "2026-10-08T09:30:00.000Z",
  "error": null
}
```

**Error responses:**

| Status | Reason |
|---|---|
| `400` | Unsupported file type, invalid file content, or no features found |
| `413` | File exceeds the configured size limit |

---

### `GET /api/files/{id}/`

Retrieve metadata for a previously uploaded file.

```bash
curl http://127.0.0.1:8000/api/files/a3f9c1d2e4b54c8fbd2e1234abcd5678/
```

**Response `200 OK`:**

```json
{
  "id": "a3f9c1d2e4b54c8fbd2e1234abcd5678",
  "filename": "survey.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "uploaded_at": "2026-10-08T09:30:00.000Z",
  "error": null
}
```

**Error responses:**

| Status | Reason |
|---|---|
| `404` | File ID not found |

---

### `GET /api/files/{id}/measurements/`

Retrieve per-feature measurements for a processed file.

```bash
curl http://127.0.0.1:8000/api/files/a3f9c1d2e4b54c8fbd2e1234abcd5678/measurements/
```

**Response `200 OK`:**

```json
{
  "file_id": "a3f9c1d2e4b54c8fbd2e1234abcd5678",
  "measurements": [
    {
      "feature_id": "point-1",
      "feature_index": 0,
      "geometry_type": "Point",
      "geometry": { "type": "Point", "coordinates": [-73.9857, 40.7484] },
      "crs": "EPSG:4326",
      "properties": { "name": "Control point" },
      "area_sq_m": null,
      "length_m": null,
      "projected_crs": null,
      "status": "NOT_APPLICABLE",
      "message": "Point geometries do not require measurement."
    },
    {
      "feature_id": "line-1",
      "feature_index": 1,
      "geometry_type": "LineString",
      "geometry": {
        "type": "LineString",
        "coordinates": [[-73.9857, 40.7484], [-73.9851, 40.7489]]
      },
      "crs": "EPSG:4326",
      "properties": { "name": "Survey line" },
      "area_sq_m": null,
      "length_m": 75.42,
      "projected_crs": "EPSG:32618",
      "status": "MEASURED",
      "message": null
    },
    {
      "feature_id": "polygon-1",
      "feature_index": 2,
      "geometry_type": "Polygon",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[-73.986, 40.748], [-73.985, 40.748], [-73.985, 40.749], [-73.986, 40.749], [-73.986, 40.748]]]
      },
      "crs": "EPSG:4326",
      "properties": { "name": "Parcel", "owner": "Ada" },
      "area_sq_m": 8645.231,
      "length_m": null,
      "projected_crs": "EPSG:32618",
      "status": "MEASURED",
      "message": null
    }
  ]
}
```

**Measurement `status` values:**

| Status | Meaning |
|---|---|
| `MEASURED` | Area or length was calculated successfully |
| `NOT_APPLICABLE` | Geometry type does not require measurement (e.g. Point) |
| `UNSUPPORTED` | Geometry type not yet supported, or CRS could not be resolved |

**Error responses:**

| Status | Reason |
|---|---|
| `404` | File ID not found |
| `409` | File is not yet in `COMPLETED` status |

---

### `GET /healthz`

Simple health check.

```bash
curl http://127.0.0.1:8000/healthz
# {"status":"ok"}
```

---

## Architecture

### Project Structure

```
geospatial-fastapi-api/
├── app/
│   ├── main.py              # FastAPI app factory and route handlers
│   ├── domain.py            # Pure Python domain models (SourceFeature, ProcessedDataset)
│   ├── schemas.py           # Pydantic response schemas (FileInfo, MeasurementsResponse)
│   ├── config.py            # Settings loaded from environment variables
│   └── services/
│       ├── storage.py       # FileStore: disk uploads + atomic JSON metadata store
│       ├── processing.py    # File-type dispatch, safe ZIP extraction, Shapefile reading
│       ├── kml.py           # Lightweight KML parser (no GDAL dependency)
│       ├── measurements.py  # CRS-aware area / length calculation
│       └── errors.py        # UserInputError for client-facing 400 messages
├── tests/
│   └── test_api.py          # Automated API-level tests (isolated tmp dirs)
├── data/                    # Runtime data directory (gitignored)
│   ├── files.json           # Persistent metadata store
│   └── uploads/             # Uploaded files, one folder per file_id
├── requirements.txt
└── README.md
```

### File-Processing Flow

```
POST /api/files/
       │
       ├─ Validate extension (.kml or .zip)                 → 400 on failure
       ├─ Create record in files.json  (status: PROCESSING)
       ├─ Stream upload to data/uploads/{file_id}/source.*  → 413 if too large
       │
       ├─ .kml ──► kml.py
       │            └─ xml.etree.ElementTree parser
       │            └─ Strips XML namespaces
       │            └─ Parses Point / LineString / Polygon / MultiGeometry
       │            └─ CRS hardcoded to EPSG:4326 (KML spec)
       │
       └─ .zip ──► processing.py
                    └─ Safe ZIP extraction (path-traversal check)
                    └─ GeoPandas reads .shp
                    └─ CRS detected from .prj sidecar
       │
       ▼
  list[SourceFeature]
  (feature_id, index, geometry, geometry_type, properties, crs)
       │
       ▼
  measurements.py  measure_feature() per feature
       │
       ▼
  list[MeasurementResult]  (area_sq_m / length_m / status / projected_crs)
       │
       ▼
  storage.py complete_record()
  → files.json updated  (status: COMPLETED)
       │
       ▼
  201 Created  →  FileInfo JSON
```

### Measurement Decision Tree

```
Feature received
       │
       ├─ geometry is empty           → UNSUPPORTED
       ├─ Point / MultiPoint          → NOT_APPLICABLE
       ├─ unknown geometry type       → UNSUPPORTED
       ├─ CRS missing / unparsable    → UNSUPPORTED
       │
       ├─ source CRS is projected     → measure in native units, convert to metres
       │
       └─ source CRS is geographic    → reproject to local UTM  → measure in metres
              │
              └─ lat >= 84  → EPSG:3413  (Arctic)
              └─ lat <= -80 → EPSG:3031  (Antarctic)
              └─ otherwise  → EPSG:326xx / 327xx  (UTM North / South)
```

---

## CRS Handling

Coordinates in a geographic CRS (e.g. EPSG:4326) are expressed in **decimal degrees**, not metres. Calculating `.area` or `.length` in degree-units produces meaningless results (square-degrees).

**Strategy: per-feature local UTM reprojection**

For each feature with a geographic source CRS:

1. Compute the geometry centroid in (longitude, latitude)
2. Derive the UTM zone: `zone = int((lon + 180) / 6) + 1`
3. Select `EPSG:326xx` (Northern Hemisphere) or `EPSG:327xx` (Southern Hemisphere)
4. Polar fallbacks: `EPSG:3413` (Arctic, lat ≥ 84°) and `EPSG:3031` (Antarctic, lat ≤ −80°)
5. Reproject with `pyproj.Transformer` (`always_xy=True`) via `shapely.ops.transform`
6. Measure on the projected geometry — results are in **metres** / **square metres**

For features already in a projected CRS, measurements use native coordinates and the CRS axis unit conversion factor is applied to convert to metres.

| File type | CRS source |
|---|---|
| KML | Always `EPSG:4326` (mandated by the KML 2.2 spec) |
| Shapefile ZIP | Read from the `.prj` sidecar file via GeoPandas / pyproj |

---

## Design Decisions

**FastAPI over Django REST Framework**
FastAPI provides automatic OpenAPI documentation, native `async` support, and Pydantic-based validation with minimal boilerplate. For a pure API service with no admin interface or ORM, it is the lighter and faster choice.

**Custom KML parser over GDAL/Fiona**
The GDAL KML driver is an optional build flag and its Windows binaries can be difficult to install. A direct `xml.etree.ElementTree` parser covers all geometry types required by the spec (Point, LineString, Polygon, MultiGeometry), handles XML namespaces robustly, and adds zero binary dependencies.

**File-based JSON store over a database**
Local setup requires zero infrastructure. The store uses **atomic writes** (write to `.tmp`, then `os.rename`) to prevent corruption on crash. The explicit `status` field (`PROCESSING → COMPLETED / FAILED`) makes the migration to a real database and background workers straightforward in the future.

**Per-feature UTM zone selection**
Choosing a UTM zone per geometry centroid (rather than per dataset) correctly handles files that span multiple zones. The trade-off is slightly higher distortion for geometries far from their zone's central meridian; a production service could detect multi-zone datasets and use a global equal-area projection instead.

**Synchronous processing**
Uploads are processed inline during the `POST` request, keeping the flow deterministic and easy to test. The `PROCESSING / COMPLETED / FAILED` state machine already supports async workers — moving the heavy lifting to Celery or ARQ would require only minimal changes to the route handler.

**Safe ZIP extraction**
Every archive member path is resolved and checked against the extraction directory before `extractall` is called, preventing path-traversal attacks.

---

## Learnings

The core insight from this project is that **geospatial measurement is fundamentally a CRS problem**. Longitude and latitude are angular measurements, not distances — calculating area or length in EPSG:4326 units produces results in square-degrees, a unit with no physical meaning. Correctly handling this requires detecting the source CRS, reprojecting to a metric system, and only then calling `.area` or `.length`.

A secondary lesson is that **KML's XML namespace handling** is a common source of bugs. `xml.etree.ElementTree` includes the full namespace URI in every tag (e.g. `{http://www.opengis.net/kml/2.2}Placemark`). Stripping namespaces before tag comparisons is essential for a parser that works with both namespaced and non-namespaced KML files.

---

## Future Scope

- **Async / background processing** — offload parsing to a task queue (Celery, ARQ, or FastAPI BackgroundTasks) so large uploads return `202 Accepted` immediately with a status the client can poll
- **Database storage** — replace the JSON flat-file with PostgreSQL + PostGIS for concurrent writes, spatial indexing, and efficient feature queries
- **Authentication & rate limiting** — API keys or OAuth 2.0, per-key upload quotas and throttling
- **Additional formats** — GeoJSON, GeoPackage, FlatGeobuf, GML
- **Feature listing endpoint** — `GET /api/files/{id}/features/` with pagination and property-based filtering
- **File scanning** — virus scan uploaded archives before processing
- **Multi-zone projection** — detect datasets spanning multiple UTM zones and apply a global equal-area projection (e.g. Mollweide, EPSG:54009) or split by zone
- **Docker image** — single-command local setup with `docker compose up`
- **CI pipeline** — GitHub Actions to run the test suite and linter on every push

