from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path
    upload_dir: Path
    host: str
    port: int


def load_settings() -> Settings:
    db_path = Path(os.getenv("SYNCPROOF_DB_PATH", "data/syncproof.db"))
    upload_dir = Path(os.getenv("SYNCPROOF_UPLOAD_DIR", "data/uploads"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        db_path=db_path,
        upload_dir=upload_dir,
        host=os.getenv("SYNCPROOF_HOST", "0.0.0.0"),
        port=int(os.getenv("SYNCPROOF_PORT", "8000")),
    )


settings = load_settings()
