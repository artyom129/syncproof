from app.mapper import suggest_mapping


def test_mapping_suggestion_understands_common_aliases():
    source = {"fields": {
        "customer_id": {"kind": "text", "unique_rate": 1.0},
        "full_name": {"kind": "text", "unique_rate": 0.9},
        "mrr": {"kind": "numeric", "unique_rate": 0.3},
    }}
    target = {"fields": {
        "id": {"kind": "text", "unique_rate": 1.0},
        "name": {"kind": "text", "unique_rate": 0.9},
        "monthly_revenue": {"kind": "numeric", "unique_rate": 0.3},
    }}
    result = suggest_mapping(source, target)
    assert result["source_key"] == "customer_id"
    assert result["target_key"] == "id"
    pairs = {(m["source"], m["target"]) for m in result["mappings"]}
    assert ("full_name", "name") in pairs
