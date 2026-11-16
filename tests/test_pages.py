import json
import os
from pathlib import Path

os.environ.setdefault("SYNCPROOF_DB_PATH", str(Path("data/test-syncproof.db")))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, service  # noqa: E402
from app.models import ReconciliationConfig  # noqa: E402

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_pages_render_with_a_real_run():
    source = service.ingest_local_file(EXAMPLES / "source_customers.csv", "Legacy CRM")
    target = service.ingest_local_file(EXAMPLES / "target_customers.csv", "New CRM")
    config = ReconciliationConfig.model_validate(json.loads((EXAMPLES / "customer_mapping.json").read_text(encoding="utf-8")))
    run_id = service.run("Page render check", source, target, config)

    client = TestClient(app)
    for path in ["/", "/new", f"/runs/{run_id}", f"/runs/{run_id}?status=changed"]:
        response = client.get(path)
        assert response.status_code == 200, path

    run_page = client.get(f"/runs/{run_id}").text
    assert "Rejected" in run_page
    assert "C-1003" in run_page  # original key case is shown
    assert "Starter" in run_page  # the changed target value is in the ledger
