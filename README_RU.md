# SyncProof

SyncProof — локальная платформа для проверки миграций и синхронизаций данных.

Проект сравнивает исходный и целевой наборы данных не только по количеству строк: строит профиль схемы, применяет явный mapping полей, сопоставляет записи по ключам и fuzzy matching, показывает различия на уровне конкретных полей и формирует безопасный JSON patch-plan.

## Что показывает проект

- FastAPI backend и REST API
- CSV / JSON / Excel
- schema profiling
- exact + fuzzy record matching
- configurable comparison rules
- SQLite audit history
- field-level diff evidence
- migration quality score
- CSV export
- JSON corrective patch plan
- web dashboard
- Docker
- pytest + GitHub Actions

Быстрый запуск:

```bash
pip install -r requirements.txt
python scripts/seed_demo.py
uvicorn app.main:app --reload
```

После запуска открой `http://127.0.0.1:8000`.
