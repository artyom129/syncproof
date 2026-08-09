from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, (int, float, bool, str)) or value is None:
        return value
    return str(value)


def load_records(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path, dtype=object)
    elif suffix in {".xlsx", ".xlsm"}:
        frame = pd.read_excel(path, dtype=object)
    elif suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("records", raw.get("data", raw))
        if not isinstance(raw, list):
            raise ValueError("JSON dataset must contain an array of records")
        frame = pd.DataFrame(raw)
    else:
        raise ValueError(f"Unsupported dataset format: {suffix}")
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        records.append({str(k): _clean_value(v) for k, v in row.items()})
    return records


def infer_kind(values: list[Any]) -> str:
    present = [v for v in values if v not in (None, "")]
    if not present:
        return "empty"
    numeric = 0
    dates = 0
    for value in present:
        try:
            float(str(value).replace(",", ""))
            numeric += 1
        except Exception:
            pass
        try:
            parsed = pd.to_datetime(value, errors="coerce")
            if not pd.isna(parsed):
                dates += 1
        except Exception:
            pass
    if numeric / len(present) >= 0.9:
        return "numeric"
    if dates / len(present) >= 0.9:
        return "date"
    return "text"


def profile_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    columns: list[str] = []
    seen = set()
    for row in records:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    fields: dict[str, dict[str, Any]] = {}
    for column in columns:
        values = [row.get(column) for row in records]
        non_null = [v for v in values if v not in (None, "")]
        unique = {json.dumps(v, sort_keys=True, default=str) for v in non_null}
        fields[column] = {
            "kind": infer_kind(values),
            "nulls": len(values) - len(non_null),
            "null_rate": round((len(values) - len(non_null)) / max(len(values), 1), 4),
            "unique": len(unique),
            "unique_rate": round(len(unique) / max(len(non_null), 1), 4),
            "sample": non_null[:3],
        }
    return {"rows": len(records), "columns": len(columns), "fields": fields}
