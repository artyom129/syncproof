from __future__ import annotations

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


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
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
    target_by_key: dict[str, dict[str, Any]] = {}
    duplicate_target_keys: set[str] = set()
    for row in target_records:
        key = _text(row.get(config.target_key))
        if key in target_by_key:
            duplicate_target_keys.add(key)
        else:
            target_by_key[key] = row

    matched_target_ids: set[int] = set()
    output: list[dict[str, Any]] = []

    for source in source_records:
        source_key = _text(source.get(config.source_key))
        target = target_by_key.get(source_key)
        score = 100.0 if target is not None else 0.0
        status = "matched"

        if target is None and config.fuzzy_fields:
            candidates = []
            for candidate in target_records:
                candidate_id = id(candidate)
                if candidate_id in matched_target_ids:
                    continue
                candidates.append((fuzzy_score(source, candidate, config.fuzzy_fields), candidate))
            candidates.sort(key=lambda item: item[0], reverse=True)
            if candidates and candidates[0][0] >= config.fuzzy_threshold:
                best_score, best = candidates[0]
                second_score = candidates[1][0] if len(candidates) > 1 else -1
                if second_score >= config.fuzzy_threshold and abs(best_score - second_score) <= config.ambiguity_delta:
                    output.append({
                        "source_key": source_key,
                        "target_key": None,
                        "status": "ambiguous",
                        "match_score": round(best_score, 2),
                        "diffs": [],
                        "source": source,
                        "target": None,
                    })
                    continue
                target = best
                score = best_score
                status = "fuzzy_matched"

        if target is None:
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

        matched_target_ids.add(id(target))
        target_key = _text(target.get(config.target_key))
        diffs = compare_rows(source, target, config.mappings)
        final_status = "changed" if diffs else status
        output.append({
            "source_key": source_key,
            "target_key": target_key,
            "status": final_status,
            "match_score": round(score, 2),
            "diffs": diffs,
            "source": source,
            "target": target,
        })

    for target in target_records:
        if id(target) not in matched_target_ids:
            output.append({
                "source_key": None,
                "target_key": _text(target.get(config.target_key)),
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
        "quality_score": quality_score,
        "acceptance": {"passed": not reasons, "reasons": reasons},
    }
    return ReconciliationResult(summary=summary, records=output)
