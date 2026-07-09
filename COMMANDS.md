# ROAScast — Commands Runbook (for the team)

Everything you need to run, test, and demo ROAScast. Copy-paste the blocks.

- **Scoring core** (what the judge runs) is fully offline: no keys, no internet, no LLM.
- **Product layer** (frontend / backend / AI) is optional and only for the demo.

> Windows note: commands below are written for **bash** (Git Bash / Linux / macOS).
> On Windows use Git Bash. Where a Python venv is activated, the Windows path is
> `.venv/Scripts/activate` (shown); on macOS/Linux it's `.venv/bin/activate`.

---

## 0. Prerequisites

| tool | version | needed for |
|---|---|---|
| Python | 3.13 (works 3.10–3.13) | scoring core + backend |
| Node.js + npm | Node 18+ (tested v24) | frontend only |
| Ollama | optional | local AI demo only |

---

## 1. Scoring core — the judge command (MOST IMPORTANT)

```bash
# from the repo root
cd roascast

# one-time: create venv + install the PINNED scoring deps
python -m venv .venv
source .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# THE JUDGE COMMAND — generates features + predictions in one shot
bash run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

Also valid:

```bash
bash run.sh                          # uses defaults: ./data ./pickle/model.pkl ./output/predictions.csv
bash run.sh ./data ./pickle/model.pkl ./tmp/custom.csv   # custom output path
```

Output → `output/predictions.csv` (372 rows: blended / channel / campaign_type / campaign × windows 30/60/90).

---

## 2. Validate the output (must PASS before submitting)

```bash
python scripts/validate_submission.py ./output/predictions.csv
# 14 checks: schema, no NaN/inf/negatives, windows 30/60/90, all 4 levels,
# P10<=P50<=P90, official channels present, hierarchy coherent. Exit 0 = PASS.
```

---

## 3. Full submission self-test (do this before final submission)

```bash
bash scripts/full_submission_test.sh
# Runs: model load, explicit/default/custom/dynamic-dir/no-key runs,
# 5x stability, freshness(no-append), validating after every run.
# Prints "FINAL SUBMISSION TEST PASS" at the end.
```

---

## 4. Inspect data parsing (sanity check the official CSVs)

```bash
python scripts/inspect_data_parsing.py --data-dir ./data
# Per-file raw vs parsed rows, date range, spend/revenue, channel=other %,
# invalid dates, zero-value warnings, Google cost_micros /1e6 sanity check.
```

Expected: Google 19,272 · Bing 2,873 · Meta 3,417 rows · channel=other 0%.

---

## 5. Accuracy / backtest (numbers for the report/slides)

```bash
python src/backtest.py --data-dir ./data
# Time-based forward holdout. Reports WAPE, MAPE, pinball P10/P50/P90,
# P10-P90 interval coverage, by window (30/60/90) and by channel.
```

Latest: WAPE(P50) 72.3% · interval coverage 91.7% · best window 30d · best channel meta.
Full write-up: `reports/backtest_report.md`.

---

## 6. Run the unit + guardrail tests

```bash
python -m pip install pytest        # if not already installed
python -m pytest tests/ -q
# 15 tests: pipeline end-to-end + AI guardrails (no-hallucination). All pass.
```

---

## 7. OPTIONAL — Product backend (FastAPI, demo only)

```bash
cd product/backend
python -m venv .venv                 # separate venv is fine
source .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
python -m pip install fastapi "uvicorn[standard]" pydantic python-multipart
# (or:  pip install -r ../../requirements-product.txt  from repo root)

uvicorn app.main:app --reload --port 8000
# Endpoints: GET /health, POST /upload /validate /forecast /simulate /explain
# Works with NO API keys — /explain falls back to a deterministic narrative.
```

Quick smoke test (in another terminal):

```bash
curl http://localhost:8000/health
```

---

## 8. OPTIONAL — Product frontend (React + Vite, demo only)

```bash
cd product/frontend
npm install
npm run dev          # dev server (proxies /api -> :8000; falls back to mock data if backend is down)
# or
npm run build        # production build into dist/
npm run preview      # serve the built app
```

White background / black text, no dark mode. Pages: Upload, Validation,
Forecast Dashboard (30/60/90), Channel Breakdown, Budget Simulator, AI Insights.
If the backend isn't running, the UI automatically uses mock data.

---

## 9. OPTIONAL — AI provider setup (for the /explain narrative)

The AI layer is **product-only** and never touches `run.sh`. Provider order:
**Ollama → OpenAI → Gemini → Groq → deterministic template**.

Copy the example env and add any keys you have (all optional):

```bash
cd product/backend
cp .env.example .env
# edit .env and uncomment/fill any of:
#   OPENAI_API_KEY=...      GEMINI_API_KEY=...      GROQ_API_KEY=...
#   OLLAMA_HOST=http://localhost:11434   OLLAMA_MODEL=qwen3:8b
```

**Local Ollama (offline, private):**

```bash
ollama serve                         # start the server (usually auto-runs)
ollama pull qwen3:8b                 # or a faster one: ollama pull llama3.2:3b
```

> Hardware note: on a CPU-only / low-RAM machine the large local models
> (qwen3:8b, mistral-small3.2:24b) may take longer than the 45s request
> timeout to generate the full JSON, so the app gracefully falls back to a
> cloud provider or the deterministic template. For a snappy **offline** demo,
> set `OLLAMA_MODEL=llama3.2:3b` and warm it once. On a GPU machine qwen3:8b
> is fine. Either way the demo never breaks — the fallback chain guarantees a
> grounded answer.

---

## 10. Clean-clone check (reproduce the grader's fresh environment)

```bash
# from a fresh copy containing only: run.sh requirements.txt README.md src/ data/ pickle/ scripts/
python -m venv .venv_test
source .venv_test/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
bash run.sh ./data ./pickle/model.pkl ./output/predictions.csv
python scripts/validate_submission.py ./output/predictions.csv
```

---

## Reports (already generated in `reports/`)

- `final_submission_qa_report.md` — overall QA verdict
- `backtest_report.md` — accuracy numbers
- `prediction_output_summary.md` — output shape/ranges
- `frontend_test_report.md`, `backend_test_report.md`, `ai_guardrail_test_report.md`

**Do not commit:** `.venv/`, `node_modules/`, `output/`, `__pycache__/`, `.env`
(all already in `.gitignore`).
