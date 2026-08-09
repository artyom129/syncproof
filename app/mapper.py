from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz


ALIASES = {
    "id": {"id", "identifier", "key", "code", "customerid", "userid", "vendorid"},
    "name": {"name", "fullname", "displayname", "title", "customername", "vendorname"},
    "email": {"email", "emailaddress", "mail"},
    "phone": {"phone", "phonenumber", "mobile", "telephone"},
    "amount": {"amount", "total", "value", "revenue", "monthlyrevenue", "mrr", "price", "cost"},
    "date": {"date", "createdat", "updatedat", "startdate", "activatedat", "timestamp"},
    "country": {"country", "countrycode", "nation"},
    "status": {"status", "state"},
    "plan": {"plan", "tier", "package", "subscription"},
}


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def semantic_bucket(name: str) -> str | None:
    normalized = normalize_name(name)
    for bucket, values in ALIASES.items():
        if normalized in values:
            return bucket
    return None


def field_similarity(source: str, target: str) -> float:
    a, b = normalize_name(source), normalize_name(target)
    if a == b:
        return 100.0
    bucket_a, bucket_b = semantic_bucket(source), semantic_bucket(target)
    alias_bonus = 96.0 if bucket_a and bucket_a == bucket_b else 0.0
    lexical = float(fuzz.WRatio(a, b))
    return max(alias_bonus, lexical)


def suggested_rule(source_name: str, target_name: str, source_profile: dict[str, Any], target_profile: dict[str, Any]) -> str:
    bucket = semantic_bucket(source_name) or semantic_bucket(target_name)
    if bucket == "email":
        return "email"
    if bucket in {"id", "status", "plan", "country"}:
        return "exact"
    a = source_profile.get("kind")
    b = target_profile.get("kind")
    if a == "numeric" and b == "numeric":
        return "numeric_tolerance"
    if a == "date" and b == "date":
        return "date"
    return "text"


def suggest_mapping(source_profile: dict[str, Any], target_profile: dict[str, Any], threshold: float = 55.0) -> dict[str, Any]:
    source_fields = source_profile.get("fields", {})
    target_fields = target_profile.get("fields", {})
    available = set(target_fields)
    suggestions = []

    for source_name, source_meta in source_fields.items():
        ranked = sorted(
            ((field_similarity(source_name, target_name), target_name) for target_name in available),
            reverse=True,
        )
        if not ranked or ranked[0][0] < threshold:
            continue
        score, target_name = ranked[0]
        available.remove(target_name)
        rule = suggested_rule(source_name, target_name, source_meta, target_fields[target_name])
        suggestions.append({
            "source": source_name,
            "target": target_name,
            "score": round(score, 1),
            "rule": rule,
            "tolerance": 0.01 if rule == "numeric_tolerance" else 0,
        })

    key_candidates = sorted(
        suggestions,
        key=lambda item: (
            1 if semantic_bucket(item["source"]) == "id" else 0,
            source_fields[item["source"]].get("unique_rate", 0),
            item["score"],
        ),
        reverse=True,
    )
    key = key_candidates[0] if key_candidates else None
    return {
        "source_key": key["source"] if key else None,
        "target_key": key["target"] if key else None,
        "mappings": suggestions,
    }
