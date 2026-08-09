from __future__ import annotations

import csv
import json
import shutil
import uuid
from io import StringIO
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from .config import settings
from .matcher import reconcile
from .models import ReconciliationConfig
from .profiler import file_sha256, load_records, profile_records
from .repository import Repository


ALLOWED_SUFFIXES = {".csv", ".json", ".xlsx", ".xlsm"}


class SyncProofService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def ingest_local_file(self, path: Path, name: str | None = None) -> int:
        suffix = path.suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise ValueError("Supported formats: CSV, JSON, XLSX, XLSM")
        records = load_records(path)
        profile = profile_records(records)
        return self.repository.create_dataset({
            "name": name or path.stem,
            "original_name": path.name,
            "file_path": str(path),
            "format": suffix.lstrip("."),
            "sha256": file_sha256(path),
            "row_count": profile["rows"],
            "column_count": profile["columns"],
            "profile": profile,
        })

    async def ingest_upload(self, upload: UploadFile, name: str | None = None) -> int:
        original_name = upload.filename or "dataset.csv"
        suffix = Path(original_name).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise ValueError("Supported formats: CSV, JSON, XLSX, XLSM")
        target = settings.upload_dir / f"{uuid.uuid4().hex}{suffix}"
        with target.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        dataset_id = self.ingest_local_file(target, name=name or Path(original_name).stem)
        return dataset_id

    def run(self, name: str, source_dataset_id: int, target_dataset_id: int, config: ReconciliationConfig) -> int:
        source = self.repository.get_dataset(source_dataset_id)
        target = self.repository.get_dataset(target_dataset_id)
        if source is None or target is None:
            raise ValueError("Dataset not found")
        run_id = self.repository.create_run(name, source_dataset_id, target_dataset_id, config.model_dump())
        try:
            source_records = load_records(Path(source["file_path"]))
            target_records = load_records(Path(target["file_path"]))
            result = reconcile(source_records, target_records, config)
            self.repository.finish_run(run_id, result.summary, result.records)
            return run_id
        except Exception as exc:
            self.repository.fail_run(run_id, str(exc))
            raise

    def export_csv(self, run_id: int) -> str:
        results = self.repository.get_results(run_id)
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=["status", "source_key", "target_key", "match_score", "changed_fields"])
        writer.writeheader()
        for row in results:
            writer.writerow({
                "status": row["status"],
                "source_key": row["source_key"],
                "target_key": row["target_key"],
                "match_score": row["match_score"],
                "changed_fields": ", ".join(diff["target_field"] for diff in row["diffs"]),
            })
        return output.getvalue()

    def patch_plan(self, run_id: int) -> dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError("Run not found")
        results = self.repository.get_results(run_id)
        operations = []
        for row in results:
            if row["status"] == "source_only":
                operations.append({"operation": "insert", "key": row["source_key"], "payload": row["source"]})
            elif row["status"] == "changed":
                changes = {diff["target_field"]: diff["source_value"] for diff in row["diffs"]}
                operations.append({"operation": "update", "key": row["target_key"], "changes": changes})
            elif row["status"] == "target_only":
                operations.append({"operation": "review_delete", "key": row["target_key"], "payload": row["target"]})
            elif row["status"] == "ambiguous":
                operations.append({"operation": "manual_review", "key": row["source_key"]})
        return {"run_id": run_id, "run_name": run["name"], "operations": operations}
