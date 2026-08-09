# Example acceptance report

A reconciliation run produces an auditable record for every source/target relationship:

- `matched` — key and mapped fields agree
- `fuzzy_matched` — identity was recovered using configured fuzzy fields and all mapped fields agree
- `changed` — identity matches but one or more mapped fields differ
- `source_only` — source record was not found in the target
- `target_only` — target record has no source counterpart
- `ambiguous` — multiple fuzzy candidates are too close to choose safely

The generated patch plan converts findings into reviewable `insert`, `update`, `review_delete`, and `manual_review` operations. SyncProof never executes destructive changes itself.
