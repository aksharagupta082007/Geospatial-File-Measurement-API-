from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile


class FileStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.uploads_dir = data_dir / "uploads"
        self.database_path = data_dir / "files.json"

    def initialize(self) -> None:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        if not self.database_path.exists():
            self._write_database({})

    def create_record(self, filename: str) -> dict[str, Any]:
        file_id = uuid4().hex
        record = {
            "id": file_id,
            "filename": filename,
            "feature_count": 0,
            "crs": None,
            "status": "PROCESSING",
            "uploaded_at": datetime.now(UTC).isoformat(),
            "error": None,
            "features": [],
            "measurements": [],
        }
        database = self._read_database()
        database[file_id] = record
        self._write_database(database)
        return record

    def save_upload(self, file_id: str, upload: UploadFile, max_bytes: int) -> Path:
        upload_dir = self.upload_dir(file_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(upload.filename or "").suffix.lower()
        source_path = upload_dir / f"source{suffix}"

        total = 0
        with source_path.open("wb") as destination:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    destination.close()
                    source_path.unlink(missing_ok=True)
                    raise ValueError("Uploaded file exceeds the configured size limit.")
                destination.write(chunk)
        return source_path

    def upload_dir(self, file_id: str) -> Path:
        return self.uploads_dir / file_id

    def complete_record(self, file_id: str, crs: str | None, features: list[dict[str, Any]], measurements: list[dict[str, Any]]) -> dict[str, Any]:
        database = self._read_database()
        record = database[file_id]
        record.update(
            {
                "feature_count": len(features),
                "crs": crs,
                "status": "COMPLETED",
                "error": None,
                "features": features,
                "measurements": measurements,
            }
        )
        self._write_database(database)
        return record

    def fail_record(self, file_id: str, error: str) -> dict[str, Any]:
        database = self._read_database()
        record = database[file_id]
        record.update({"status": "FAILED", "error": error})
        self._write_database(database)
        return record

    def get_record(self, file_id: str) -> dict[str, Any] | None:
        return self._read_database().get(file_id)

    def public_record(self, file_id: str) -> dict[str, Any] | None:
        record = self.get_record(file_id)
        if record is None:
            return None
        return {key: record[key] for key in ("id", "filename", "feature_count", "crs", "status", "uploaded_at", "error")}

    def _read_database(self) -> dict[str, Any]:
        if not self.database_path.exists():
            return {}
        with self.database_path.open("r", encoding="utf-8") as source:
            return json.load(source)

    def _write_database(self, database: dict[str, Any]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self.database_path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as destination:
            json.dump(database, destination, indent=2)
        shutil.move(str(temp_path), self.database_path)
