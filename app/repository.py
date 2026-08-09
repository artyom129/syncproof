from __future__ import annotations

import json
from typing import Any

from .db import Database, utcnow


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def audit(self, action: str, entity_type: str, entity_id: str | None, details: dict[str, Any]) -> None:
        with self.db.conn() as conn:
            conn.execute(
                "INSERT INTO audit_logs(action, entity_type, entity_id, details_json, created_at) VALUES(?,?,?,?,?)",
                (action, entity_type, entity_id, json.dumps(details, default=str), utcnow()),
            )

    def create_dataset(self, payload: dict[str, Any]) -> int:
        with self.db.conn() as conn:
            cursor = conn.execute(
                """INSERT INTO datasets(name, original_name, file_path, format, sha256, row_count, column_count, profile_json, created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    payload["name"], payload["original_name"], payload["file_path"], payload["format"],
                    payload["sha256"], payload["row_count"], payload["column_count"],
                    json.dumps(payload["profile"], default=str), utcnow(),
                ),
            )
            dataset_id = int(cursor.lastrowid)
        self.audit("dataset.created", "dataset", str(dataset_id), {"name": payload["name"]})
        return dataset_id

    def get_dataset(self, dataset_id: int) -> dict[str, Any] | None:
        with self.db.conn() as conn:
            row = conn.execute("SELECT * FROM datasets WHERE id=?", (dataset_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["profile"] = json.loads(result.pop("profile_json"))
        return result

    def list_datasets(self) -> list[dict[str, Any]]:
        with self.db.conn() as conn:
            rows = conn.execute("SELECT * FROM datasets ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]

    def create_run(self, name: str, source_id: int, target_id: int, config: dict[str, Any]) -> int:
        with self.db.conn() as conn:
            cursor = conn.execute(
                "INSERT INTO runs(name, source_dataset_id, target_dataset_id, config_json, status, summary_json, created_at) VALUES(?,?,?,?,?,?,?)",
                (name, source_id, target_id, json.dumps(config), "running", "{}", utcnow()),
            )
            run_id = int(cursor.lastrowid)
        self.audit("run.created", "run", str(run_id), {"name": name})
        return run_id

    def finish_run(self, run_id: int, summary: dict[str, Any], records: list[dict[str, Any]]) -> None:
        with self.db.conn() as conn:
            for record in records:
                conn.execute(
                    """INSERT INTO record_results(run_id, source_key, target_key, status, match_score, diffs_json, source_json, target_json)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        run_id, record.get("source_key"), record.get("target_key"), record["status"],
                        record.get("match_score", 0), json.dumps(record.get("diffs", []), default=str),
                        json.dumps(record.get("source"), default=str) if record.get("source") is not None else None,
                        json.dumps(record.get("target"), default=str) if record.get("target") is not None else None,
                    ),
                )
            conn.execute(
                "UPDATE runs SET status='succeeded', summary_json=?, finished_at=? WHERE id=?",
                (json.dumps(summary, default=str), utcnow(), run_id),
            )
        self.audit("run.completed", "run", str(run_id), summary)

    def fail_run(self, run_id: int, error: str) -> None:
        with self.db.conn() as conn:
            conn.execute(
                "UPDATE runs SET status='failed', summary_json=?, finished_at=? WHERE id=?",
                (json.dumps({"error": error}), utcnow(), run_id),
            )
        self.audit("run.failed", "run", str(run_id), {"error": error})

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        with self.db.conn() as conn:
            row = conn.execute(
                """SELECT r.*, s.name AS source_name, t.name AS target_name
                   FROM runs r JOIN datasets s ON s.id=r.source_dataset_id JOIN datasets t ON t.id=r.target_dataset_id
                   WHERE r.id=?""", (run_id,)
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["config"] = json.loads(result.pop("config_json"))
        result["summary"] = json.loads(result.pop("summary_json"))
        return result

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.db.conn() as conn:
            rows = conn.execute(
                """SELECT r.*, s.name AS source_name, t.name AS target_name
                   FROM runs r JOIN datasets s ON s.id=r.source_dataset_id JOIN datasets t ON t.id=r.target_dataset_id
                   ORDER BY r.id DESC LIMIT ?""", (limit,)
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["summary"] = json.loads(item.pop("summary_json"))
            item.pop("config_json", None)
            output.append(item)
        return output

    def get_results(self, run_id: int, status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM record_results WHERE run_id=?"
        args: list[Any] = [run_id]
        if status:
            query += " AND status=?"
            args.append(status)
        query += " ORDER BY id"
        with self.db.conn() as conn:
            rows = conn.execute(query, tuple(args)).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["diffs"] = json.loads(item.pop("diffs_json"))
            item["source"] = json.loads(item.pop("source_json")) if item.get("source_json") else None
            item["target"] = json.loads(item.pop("target_json")) if item.get("target_json") else None
            output.append(item)
        return output

    def stats(self) -> dict[str, int]:
        with self.db.conn() as conn:
            datasets = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
            runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            issues = conn.execute("SELECT COUNT(*) FROM record_results WHERE status IN ('changed','source_only','target_only','ambiguous')").fetchone()[0]
        return {"datasets": datasets, "runs": runs, "issues": issues}
