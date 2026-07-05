"""ROAScast PRODUCT API — FastAPI, the online half of the system.

Six endpoints, all calling the SHARED forecasting core via ``core.ForecastService``
so the demo and the scored output never disagree on the math. The LLM lives only
in ``/explain``. Nothing here is installed or run by ``run.sh``.

Run (from product/backend):
    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .core import ForecastService
from .llm import build_context, explain
from .models import ExplainRequest, ForecastRequest, SimulateRequest
from .sessions import STORE

app = FastAPI(title="ROAScast API", version="1.0.0",
              description="Probabilistic revenue & ROAS forecasting — product layer.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev; tighten for deploy
    allow_methods=["*"],
    allow_headers=["*"],
)

SERVICE = ForecastService()


def _get_long(session_id: str):
    try:
        return STORE.get(session_id)
    except KeyError:
        raise HTTPException(404, f"Unknown session_id '{session_id}'. Upload first.")


@app.get("/health")
def health():
    """Model version + pipeline status."""
    return {"status": "ok", "model_version": SERVICE.version,
            "currency": "USD", "windows": [30, 60, 90]}


@app.post("/upload")
async def upload(google: UploadFile | None = File(None),
                 meta: UploadFile | None = File(None),
                 files: list[UploadFile] | None = File(None)):
    """Multipart Google + Meta CSVs -> normalize, summary, session_id."""
    frames = []
    if google is not None:
        frames.append(SERVICE.read_csv(await google.read(), channel_hint="google"))
    if meta is not None:
        frames.append(SERVICE.read_csv(await meta.read(), channel_hint="meta"))
    for f in (files or []):
        frames.append(SERVICE.read_csv(await f.read()))
    if not frames:
        raise HTTPException(400, "Provide at least one CSV (google, meta, or files).")

    long_df = SERVICE.combine(frames)
    if long_df.empty:
        raise HTTPException(422, "No parseable rows found in the uploaded files.")
    summary = SERVICE.summarize(long_df)
    sid = STORE.create(long_df, summary)
    return {"session_id": sid, "summary": summary}


@app.post("/validate")
def validate(req: ForecastRequest):
    """Campaign consistency check -> issues list + per-campaign mapping."""
    long_df = _get_long(req.session_id)
    return SERVICE.validate(long_df)


@app.post("/forecast")
def forecast(req: ForecastRequest):
    """Windows + optional budget override -> full reconciled hierarchy."""
    long_df = _get_long(req.session_id)
    df = SERVICE.forecast(long_df, budget_overrides=req.budget_overrides)
    if req.windows:
        df = df[df["window_days"].astype(int).isin(req.windows)]
    return {"currency": "USD", "model_version": SERVICE.version,
            "rows": df.to_dict(orient="records")}


@app.post("/simulate")
def simulate(req: SimulateRequest):
    """Budget scenario -> response-curve revenue/ROAS per channel (curve-only)."""
    long_df = _get_long(req.session_id)
    result = SERVICE.simulate(long_df, req.scenario)
    result["curves"] = SERVICE.curve_points(long_df)
    return result


@app.post("/explain")
def explain_endpoint(req: ExplainRequest):
    """Forecast + drivers -> grounded LLM causal narrative (3 sections)."""
    long_df = _get_long(req.session_id)
    df = SERVICE.forecast(long_df, budget_overrides=req.budget_overrides)
    rows = df.to_dict(orient="records")
    drivers = SERVICE.drivers()
    ctx = build_context(rows, drivers, req.window_days)
    result = explain(ctx)
    result["drivers"] = drivers
    return result
