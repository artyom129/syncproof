# Architecture

SyncProof separates dataset ingestion, profiling, comparison logic and persistence so the reconciliation engine can be reused outside the web UI.

```mermaid
flowchart LR
    A[CSV / JSON / XLSX] --> B[Dataset Loader]
    B --> C[Schema Profiler]
    B --> D[Reconciliation Engine]
    E[Mapping Contract] --> D
    D --> F[Exact Key Match]
    F --> G[Fuzzy Recovery]
    G --> H[Field Rules]
    H --> I[Record Evidence]
    I --> J[(SQLite Audit Store)]
    I --> K[CSV Report]
    I --> L[JSON Patch Plan]
    J --> M[FastAPI Dashboard]
```

The engine is deterministic: the same source snapshot, target snapshot and mapping contract produce the same reconciliation result.
