from app.matcher import reconcile
from app.models import ReconciliationConfig


def config():
    return ReconciliationConfig.model_validate({
        "source_key": "id", "target_key": "customer_id",
        "mappings": [
            {"source": "name", "target": "full_name", "rule": "text"},
            {"source": "amount", "target": "mrr", "rule": "numeric_tolerance", "tolerance": 0.01},
        ],
        "fuzzy_fields": [{"source": "name", "target": "full_name", "rule": "text"}],
        "fuzzy_threshold": 85,
    })


def test_reconcile_detects_clean_changed_and_missing():
    source = [
        {"id": "1", "name": "Alice", "amount": "10.00"},
        {"id": "2", "name": "Bob", "amount": "20.00"},
        {"id": "3", "name": "Carla", "amount": "30.00"},
    ]
    target = [
        {"customer_id": "1", "full_name": "alice", "mrr": 10},
        {"customer_id": "2", "full_name": "Bob", "mrr": 22},
        {"customer_id": "4", "full_name": "Derek", "mrr": 40},
    ]
    result = reconcile(source, target, config())
    assert result.summary["counts"]["matched"] == 1
    assert result.summary["counts"]["changed"] == 1
    assert result.summary["counts"]["source_only"] == 1
    assert result.summary["counts"]["target_only"] == 1
    changed = [r for r in result.records if r["status"] == "changed"][0]
    assert changed["diffs"][0]["target_field"] == "mrr"


def test_fuzzy_match_can_recover_changed_key():
    cfg = ReconciliationConfig.model_validate({
        "source_key": "id", "target_key": "customer_id",
        "mappings": [{"source": "amount", "target": "mrr", "rule": "numeric_tolerance", "tolerance": 0.01}],
        "fuzzy_fields": [{"source": "name", "target": "full_name", "rule": "text"}],
        "fuzzy_threshold": 85,
    })
    source = [{"id": "old-1", "name": "Northstar Components", "amount": 10}]
    target = [{"customer_id": "new-99", "full_name": "Northstar Component", "mrr": 10}]
    result = reconcile(source, target, cfg)
    assert result.records[0]["status"] == "fuzzy_matched"
    assert result.records[0]["target_key"] == "new-99"
    assert result.records[0]["match_score"] >= 85


def test_acceptance_gate_fails_on_changed_record():
    source = [{"id": "1", "name": "Alice", "amount": 10}]
    target = [{"customer_id": "1", "full_name": "Alice", "mrr": 20}]
    result = reconcile(source, target, config())
    assert result.summary["acceptance"]["passed"] is False
    assert any("changed records" in reason for reason in result.summary["acceptance"]["reasons"])
