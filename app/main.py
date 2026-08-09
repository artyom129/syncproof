from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import settings
from .db import Database
from .models import ReconciliationConfig, RunRequest
from .mapper import suggest_mapping
from .repository import Repository
from .services import SyncProofService


app = FastAPI(
    title="SyncProof",
    version="1.0.0",
    description="Data migration reconciliation, schema profiling and patch-plan generation.",
)
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

db = Database(settings.db_path)
repository = Repository(db)
service = SyncProofService(repository)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "syncproof"}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"runs": repository.list_runs(12), "datasets": repository.list_datasets()[:8], "stats": repository.stats()},
    )




@app.get("/new", response_class=HTMLResponse)
def new_run(request: Request):
    return templates.TemplateResponse(request=request, name="new.html", context={"datasets": repository.list_datasets()})


@app.get("/api/mappings/suggest")
def mapping_suggestion(source_dataset_id: int, target_dataset_id: int):
    source = repository.get_dataset(source_dataset_id)
    target = repository.get_dataset(target_dataset_id)
    if not source or not target:
        raise HTTPException(404, "Dataset not found")
    return suggest_mapping(source["profile"], target["profile"])


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_view(request: Request, run_id: int, status: str | None = None):
    run = repository.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    results = repository.get_results(run_id, status=status)
    return templates.TemplateResponse(
        request=request,
        name="run.html",
        context={"run": run, "results": results, "status_filter": status},
    )


@app.post("/api/datasets")
async def upload_dataset(file: UploadFile = File(...), name: str | None = Form(default=None)):
    try:
        dataset_id = await service.ingest_upload(file, name=name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    dataset = repository.get_dataset(dataset_id)
    return JSONResponse(dataset)


@app.get("/api/datasets")
def list_datasets():
    return repository.list_datasets()


@app.get("/api/datasets/{dataset_id}")
def get_dataset(dataset_id: int):
    dataset = repository.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    return dataset


@app.post("/api/runs")
def create_run(payload: RunRequest):
    try:
        run_id = service.run(payload.name, payload.source_dataset_id, payload.target_dataset_id, payload.config)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return repository.get_run(run_id)


@app.post("/api/runs/from-json")
def create_run_from_form(
    name: str = Form(...),
    source_dataset_id: int = Form(...),
    target_dataset_id: int = Form(...),
    config_json: str = Form(...),
):
    try:
        config = ReconciliationConfig.model_validate(json.loads(config_json))
        run_id = service.run(name, source_dataset_id, target_dataset_id, config)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"run_id": run_id, "url": f"/runs/{run_id}"}


@app.get("/api/runs")
def list_runs():
    return repository.list_runs(100)


@app.get("/api/runs/{run_id}")
def get_run(run_id: int):
    run = repository.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    run["records"] = repository.get_results(run_id)
    return run


@app.get("/api/runs/{run_id}/export.csv", response_class=PlainTextResponse)
def export_run(run_id: int):
    if not repository.get_run(run_id):
        raise HTTPException(404, "Run not found")
    return PlainTextResponse(
        service.export_csv(run_id),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="syncproof-run-{run_id}.csv"'},
    )


@app.get("/api/runs/{run_id}/patch-plan.json")
def patch_plan(run_id: int):
    try:
        return service.patch_plan(run_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
