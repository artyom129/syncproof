from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RuleName = Literal["exact", "text", "email", "numeric", "numeric_tolerance", "date"]


class FieldMapping(BaseModel):
    source: str
    target: str
    rule: RuleName = "exact"
    tolerance: float = 0.0


class AcceptancePolicy(BaseModel):
    max_changed: int = Field(default=0, ge=0)
    max_source_only: int = Field(default=0, ge=0)
    max_target_only: int = Field(default=0, ge=0)
    max_ambiguous: int = Field(default=0, ge=0)
    min_quality_score: float = Field(default=100.0, ge=0, le=100)


class ReconciliationConfig(BaseModel):
    source_key: str
    target_key: str
    mappings: list[FieldMapping]
    fuzzy_fields: list[FieldMapping] = Field(default_factory=list)
    fuzzy_threshold: float = Field(default=90.0, ge=0, le=100)
    ambiguity_delta: float = Field(default=2.0, ge=0, le=25)
    acceptance: AcceptancePolicy = Field(default_factory=AcceptancePolicy)


class RunRequest(BaseModel):
    name: str
    source_dataset_id: int
    target_dataset_id: int
    config: ReconciliationConfig


class DatasetProfile(BaseModel):
    rows: int
    columns: int
    fields: dict[str, dict[str, Any]]
