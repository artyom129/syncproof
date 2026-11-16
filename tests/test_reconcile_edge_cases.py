import dataclasses
import io
import os
from pathlib import Path

import pytest

os.environ.setdefault("SYNCPROOF_DB_PATH", str(Path("data/test-syncproof.db")))

from app.matcher import _number, reconcile  # noqa: E402
from app.models import ReconciliationConfig  # noqa: E402


def make_config(**extra):
    data = {
        "source_key": "id",
        "target_key": "customer_id",
        "mappings": [{"source": "amount", "target": "mrr", "rule": "numeric_tolerance", "tolerance": 0.01}],
    }
    data.update(extra)
    return ReconciliationConfig.model_validate(data)


def test_keys_keep_their_original_case_for_the_patch_plan():
    source = [{"id": "C-1001", "amount": "10"}]
    target = [{"customer_id": "c-1001 ", "mrr": "12"}]
    record = reconcile(source, target, make_config()).records[0]
    assert record["status"] == "changed"
    assert record["source_key"] == "C-1001"
    assert record["target_key"] == "c-1001"


def test_exact_key_wins_over_an_earlier_fuzzy_guess():
    cfg = make_config(
        fuzzy_fields=[{"source": "name", "target": "full_name", "rule": "text"}],
        fuzzy_threshold=80,
    )
    source = [
        {"id": "old-7", "name": "Northstar Components", "amount": 10},
        {"id": "N-1", "name": "Northstar Components", "amount": 10},
    ]
    target = [{"customer_id": "N-1", "full_name": "Northstar Components", "mrr": 10}]
    result = reconcile(source, target, cfg)
    statuses = [row["status"] for row in result.records]
    assert statuses == ["source_only", "matched"]
    assert result.summary["counts"].get("target_only", 0) == 0


def test_rows_without_a_key_are_not_matched_to_each_other():
    source = [{"id": "", "amount": 1}, {"id": None, "amount": 2}]
    target = [{"customer_id": "", "mrr": 1}]
    counts = reconcile(source, target, make_config()).summary["counts"]
    assert counts == {"source_only": 2, "target_only": 1}


def test_duplicate_source_key_matches_the_target_only_once():
    source = [{"id": "1", "amount": 5}, {"id": "1", "amount": 5}]
    target = [{"customer_id": "1", "mrr": 5}]
    result = reconcile(source, target, make_config())
    assert [row["status"] for row in result.records] == ["matched", "source_only"]
    assert result.summary["duplicate_source_keys"] == ["1"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234.5", 1234.5),
        ("1,234.50", 1234.5),
        ("1.234,50", 1234.5),
        ("1 234,50", 1234.5),
        ("$1,200", 1200.0),
        ("12,5", 12.5),
        (7, 7.0),
        ("n/a", None),
        ("", None),
    ],
)
def test_number_formats(raw, expected):
    assert _number(raw) == expected


@pytest.fixture()
def service(tmp_path, monkeypatch):
    from app import services
    from app.db import Database
    from app.repository import Repository

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(services, "settings", dataclasses.replace(services.settings, upload_dir=upload_dir))
    return services.SyncProofService(Repository(Database(tmp_path / "test.db"))), upload_dir


class FakeUpload:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self.file = io.BytesIO(content)


async def _ingest(svc, filename, content):
    return await svc.ingest_upload(FakeUpload(filename, content))


def test_broken_upload_is_rejected_and_removed(service):
    import asyncio

    svc, upload_dir = service
    with pytest.raises(ValueError):
        asyncio.run(_ingest(svc, "broken.xlsx", b"not a spreadsheet"))
    assert list(upload_dir.iterdir()) == []


def test_run_with_unknown_column_is_rejected(service):
    import asyncio

    svc, _ = service
    source_id = asyncio.run(_ingest(svc, "s.csv", b"id,amount\n1,10\n"))
    target_id = asyncio.run(_ingest(svc, "t.csv", b"customer_id,mrr\n1,10\n"))
    bad = make_config(mappings=[{"source": "amount", "target": "revenue", "rule": "numeric"}])
    with pytest.raises(ValueError, match="revenue"):
        svc.run("bad", source_id, target_id, bad)
    assert svc.repository.list_runs() == []


def test_export_escapes_formula_like_keys(service):
    import asyncio

    svc, _ = service
    source_id = asyncio.run(_ingest(svc, "s.csv", b"id,amount\n=HYPERLINK(1),10\n"))
    target_id = asyncio.run(_ingest(svc, "t.csv", b"customer_id,mrr\nX,10\n"))
    run_id = svc.run("export", source_id, target_id, make_config())
    exported = svc.export_csv(run_id)
    assert "'=HYPERLINK(1)" in exported
    plan = svc.patch_plan(run_id)
    assert {"operation": "insert", "key": "=HYPERLINK(1)", "payload": {"id": "=HYPERLINK(1)", "amount": "10"}} in plan["operations"]
