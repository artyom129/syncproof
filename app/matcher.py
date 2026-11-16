from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from rapidfuzz import fuzz

from .models import FieldMapping, ReconciliationConfig


@dataclass
class ReconciliationResult:
    summary: dict[str, Any]
    records: list[dict[str, Any]]


def _text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _display_key(value: Any) -> str | None:
    """Key as it is stored in the dataset, so a patch plan can address the real row."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


_NUMBER_NOISE = re.compile(r"[\s '$€£¥₽]")
_THOUSANDS_COMMA = re.compile(r"^-?\d{1,3}(,\d{3})+$")


def _number(value: Any) -> float | None:
    """Parse 1234.5, 1,234.50, 1.234,50, 1 234,50 and $1,200 as numbers."""
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _NUMBER_NOISE.sub("", str(value))
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", "") if _THOUSANDS_COMMA.match(text) else text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _date(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    candidates = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d.%m.%Y")
    for fmt in candidates:
        try:
            return datetime.strptime(text[:10], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def values_equal(left: Any, right: Any, mapping: FieldMapping) -> bool:
    if left in (None, "") and right in (None, ""):
        return True
    rule = mapping.rule
    if rule == "exact":
        return str(left) == str(right)
    if rule in {"text", "email"}:
        return _text(left) == _text(right)
    if rule == "numeric":
        return _number(left) == _number(right)
    if rule == "numeric_tolerance":
        a, b = _number(left), _number(right)
        return a is not None and b is not None and abs(a - b) <= mapping.tolerance
    if rule == "date":
        a, b = _date(left), _date(right)
        return a is not None and b is not None and abs((a - b).days) <= int(mapping.tolerance)
    return str(left) == str(right)


def compare_rows(source: dict[str, Any], target: dict[str, Any], mappings: list[FieldMapping]) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for mapping in mappings:
        left = source.get(mapping.source)
        right = target.get(mapping.target)
        if not values_equal(left, right, mapping):
            diffs.append(
                {
                    "source_field": mapping.source,
                    "target_field": mapping.target,
                    "source_value": left,
                    "target_value": right,
                    "rule": mapping.rule,
                    "tolerance": mapping.tolerance,
                }
            )
    return diffs


def fuzzy_score(source: dict[str, Any], target: dict[str, Any], fields: list[FieldMapping]) -> float:
    if not fields:
        return 0.0
    scores: list[float] = []
    for mapping in fields:
        left = _text(source.get(mapping.source))
        right = _text(target.get(mapping.target))
        if not left and not right:
            continue
        scores.append(float(fuzz.WRatio(left, right)))
    return sum(scores) / len(scores) if scores else 0.0


def reconcile(
    source_records: list[dict[str, Any]],
    target_records: list[dict[str, Any]],
    config: ReconciliationConfig,
) -> ReconciliationResult:
    # Index targets by normalized key. Rows without a key are never matched by key.
    target_index: dict[str, int] = {}
    duplicate_target_keys: set[str] = set()
    for index, row in enumerate(target_records):
        key = _text(row.get(config.target_key))
        if not key:
            continue
        if key in target_index:
            duplicate_target_keys.add(key)
        else:
            target_index[key] = index

    used_targets: set[int] = set()
    # source index -> (target index, score, status)
    assigned: dict[int, tuple[int, float, str]] = {}
    ambiguous: dict[int, float] = {}
    seen_source_keys: set[str] = set()
    duplicate_source_keys: set[str] = set()

    # Pass 1: exact key matches. They run before any fuzzy matching, so a fuzzy
    # guess can never take a row that another source row owns by key.
    for index, source in enumerate(source_records):
        key = _text(source.get(config.source_key))
        if not key:
            continue
        if key in seen_source_keys:
            duplicate_source_keys.add(key)
        seen_source_keys.add(key)
        target_index_for_key = target_index.get(key)
        if target_index_for_key is None or target_index_for_key in used_targets:
            continue
        used_targets.add(target_index_for_key)
        assigned[index] = (target_index_for_key, 100.0, "matched")

    # Pass 2: fuzzy matches for the rest, against targets nobody owns yet.
    if config.fuzzy_fields:
        for index, source in enumerate(source_records):
            if index in assigned:
                continue
            candidates = sorted(
                (
                    (fuzzy_score(source, candidate, config.fuzzy_fields), target_idx)
                    for target_idx, candidate in enumerate(target_records)
                    if target_idx not in used_targets
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            if not candidates or candidates[0][0] < config.fuzzy_threshold:
                continue
            best_score, best_index = candidates[0]
            second_score = candidates[1][0] if len(candidates) > 1 else -1
            if second_score >= config.fuzzy_threshold and abs(best_score - second_score) <= config.ambiguity_delta:
                ambiguous[index] = best_score
                continue
            used_targets.add(best_index)
            assigned[index] = (best_index, best_score, "fuzzy_matched")

    output: list[dict[str, Any]] = []
    for index, source in enumerate(source_records):
        source_key = _display_key(source.get(config.source_key))
        if index in ambiguous:
            output.append({
                "source_key": source_key,
                "target_key": None,
                "status": "ambiguous",
                "match_score": round(ambiguous[index], 2),
                "diffs": [],
                "source": source,
                "target": None,
            })
            continue
        if index not in assigned:
            output.append({
                "source_key": source_key,
                "target_key": None,
                "status": "source_only",
                "match_score": 0.0,
                "diffs": [],
                "source": source,
                "target": None,
            })
            continue
        target_idx, score, status = assigned[index]
        target = target_records[target_idx]
        diffs = compare_rows(source, target, config.mappings)
        output.append({
            "source_key": source_key,
            "target_key": _display_key(target.get(config.target_key)),
            "status": "changed" if diffs else status,
            "match_score": round(score, 2),
            "diffs": diffs,
            "source": source,
            "target": target,
        })

    for target_idx, target in enumerate(target_records):
        if target_idx not in used_targets:
            output.append({
                "source_key": None,
                "target_key": _display_key(target.get(config.target_key)),
                "status": "target_only",
                "match_score": 0.0,
                "diffs": [],
                "source": None,
                "target": target,
            })

    counts: dict[str, int] = {}
    changed_fields = 0
    for row in output:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        changed_fields += len(row["diffs"])

    total = max(len(output), 1)
    clean = counts.get("matched", 0) + counts.get("fuzzy_matched", 0)
    quality_score = round(clean / total * 100, 1)
    policy = config.acceptance
    reasons: list[str] = []
    checks = [
        (counts.get("changed", 0), policy.max_changed, "changed records"),
        (counts.get("source_only", 0), policy.max_source_only, "source-only records"),
        (counts.get("target_only", 0), policy.max_target_only, "target-only records"),
        (counts.get("ambiguous", 0), policy.max_ambiguous, "ambiguous matches"),
    ]
    for actual, maximum, label in checks:
        if actual > maximum:
            reasons.append(f"{actual} {label} exceeds allowed maximum {maximum}")
    if quality_score < policy.min_quality_score:
        reasons.append(f"quality score {quality_score} is below required {policy.min_quality_score}")

    summary = {
        "source_rows": len(source_records),
        "target_rows": len(target_records),
        "results": len(output),
        "counts": counts,
        "changed_fields": changed_fields,
        "duplicate_target_keys": sorted(duplicate_target_keys),
        "duplicate_source_keys": sorted(duplicate_source_keys),
        "quality_score": quality_score,
        "acceptance": {"passed": not reasons, "reasons": reasons},
    }
    return ReconciliationResult(summary=summary, records=output)
