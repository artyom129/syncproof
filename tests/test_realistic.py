"""Hold SyncProof to a known truth: the generated migration has an exact number of each defect."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from app.matcher import reconcile  # noqa: E402
from app.models import ReconciliationConfig  # noqa: E402
from app.profiler import load_records  # noqa: E402
from generate_realistic import build  # noqa: E402

MAPPING = ROOT / "examples" / "realistic" / "mapping.json"


def _run(rows: int, seed: int):
    source, target, expected = build(rows, seed)
    config = ReconciliationConfig.model_validate(json.loads(MAPPING.read_text(encoding="utf-8")))
    return reconcile(source, target, config), expected


def test_every_defect_is_found_exactly():
    result, expected = _run(600, 7)
    counts = result.summary["counts"]
    for outcome in ("matched", "fuzzy_matched", "changed", "source_only", "target_only"):
        assert counts.get(outcome, 0) == expected[outcome], outcome
    assert counts.get("ambiguous", 0) == 0
    assert len(result.summary["duplicate_source_keys"]) == expected["duplicate_source_keys"]


def test_formatting_noise_is_not_a_difference():
    # Upper-case emails, padded names, 1.290,00 prices and DD.MM.YYYY dates are all noise.
    result, expected = _run(600, 7)
    flagged = {d["source_field"] for row in result.records for d in row["diffs"]}
    assert flagged <= {"plan", "mrr", "start_date"}
    assert result.summary["changed_fields"] == expected["changed"]


def test_a_dirty_migration_is_rejected():
    result, _ = _run(600, 7)
    assert result.summary["acceptance"]["passed"] is False


def test_committed_files_match_the_generator():
    expected = json.loads((ROOT / "examples" / "realistic" / "expected.json").read_text(encoding="utf-8"))
    source = load_records(ROOT / "examples" / "realistic" / "legacy_customers.csv")
    target = load_records(ROOT / "examples" / "realistic" / "migrated_customers.csv")
    assert len(source) == expected["source_rows"]
    assert len(target) == expected["target_rows"]
