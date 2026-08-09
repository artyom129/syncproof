from app.profiler import profile_records


def test_profile_reports_nulls_and_uniqueness():
    profile = profile_records([
        {"id": "1", "email": "a@example.com", "amount": 10},
        {"id": "2", "email": None, "amount": 20},
        {"id": "3", "email": "a@example.com", "amount": 30},
    ])
    assert profile["rows"] == 3
    assert profile["columns"] == 3
    assert profile["fields"]["email"]["nulls"] == 1
    assert profile["fields"]["email"]["unique"] == 1
    assert profile["fields"]["amount"]["kind"] == "numeric"
