from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("GEOSPATIAL_DATA_DIR", "data"))
    max_upload_bytes: int = int(os.getenv("GEOSPATIAL_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))


def get_settings() -> Settings:
    return Settings()
