# ROAScast Backend Test Report

## Location & stack

| item | value |
|---|---|
| Backend folder | `product/backend/` |
| Framework | FastAPI + Uvicorn (Pydantic models, python-multipart uploads) |
| Shared core | imports `src/forecasting` — the SAME math as scored `run.sh` |
| Deps | product-only (`fastapi`, `uvicorn`, `pydantic`, `python-multipart`); NOT in scored `requirements.txt` |

## How it was tested

Endpoints exercised in-process with FastAPI's `TestClient`, with **all API keys
unset** and Ollama forced unreachable, so the AI path takes the deterministic
fallback. The official Google/Bing/Meta CSVs were uploaded through `/upload`.

## Endpoint results

| endpoint | method | test | result |
|---|---|---|---|
| `/health` | GET | model version + windows | **PASS** (`model_version=roascast-1.0.0`, windows `[30,60,90]`) |
| `/upload` | POST | google+meta+bing multipart | **PASS** (25,562 rows, channels google/meta/microsoft) |
| `/validate` | POST | campaign consistency | **PASS** (`ok=true`, 31 informational issues) |
| `/forecast` | POST | windows 30/60/90 | **PASS** (372 reconciled rows) |
| `/simulate` | POST | budget scenario | **PASS** (per-channel curve + blended ROAS) |
| `/explain` | POST | grounded AI narrative | **PASS** (`provider=template`, `guardrail=fallback`) |

## Failure-path behaviour

| case | expected | result |
|---|---|---|
| Unknown `session_id` | 404 | **404** |
| Upload with no files | 400 | **400** |
| No API keys / no Ollama | still returns insights via deterministic fallback | **PASS** (no crash) |

## Model / core reuse

`core.ForecastService` loads `pickle/model.pkl` once and calls the shared
`forecasting` package (`features`, `reconcile`, `schema`, `curves`,
`mapping`). It re-implements none of the model math, so the demo and the scored
output cannot diverge. No endpoint makes a network call except `/explain`, and
that path degrades safely to the template.

## Scoring isolation

`run.sh` never imports the backend and never installs its dependencies.
Confirmed: scored `requirements.txt` contains no FastAPI/LLM packages, and the
full submission test passes with the scored venv only.

## Remaining risks

- None blocking. Sessions are in-memory (`sessions.STORE`) — fine for a single
  demo instance; a restart clears uploads (expected for the demo).
