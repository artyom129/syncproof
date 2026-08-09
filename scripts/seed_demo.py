from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.db import Database
from app.models import ReconciliationConfig
from app.repository import Repository
from app.services import SyncProofService


def main() -> None:
    db = Database(settings.db_path)
    repo = Repository(db)
    service = SyncProofService(repo)
    source_path = ROOT / "examples" / "source_customers.csv"
    target_path = ROOT / "examples" / "target_customers.csv"
    config_path = ROOT / "examples" / "customer_mapping.json"

    source_id = service.ingest_local_file(source_path, "Legacy CRM customers")
    target_id = service.ingest_local_file(target_path, "New CRM customers")
    config = ReconciliationConfig.model_validate(json.loads(config_path.read_text(encoding="utf-8")))
    run_id = service.run("CRM migration acceptance check", source_id, target_id, config)
    run = repo.get_run(run_id)
    print(f"Seeded SyncProof demo: run #{run_id}")
    print(json.dumps(run["summary"], indent=2))


if __name__ == "__main__":
    main()
