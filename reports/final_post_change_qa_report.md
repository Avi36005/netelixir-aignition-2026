# ROAScast Final Post-Change QA Report

Date: 2026-07-10 · Changes under test: OOD scale-mismatch guardrail + judge-friendly frontend graphs.

## 1. Summary verdict

**READY**

## 2. Official dataset scoring pipeline

- run.sh official data: **pass** (`./run.sh ./data ./pickle/model.pkl ./output/predictions.csv`)
- validate_submission: **pass** (all 14 checks)
- predictions.csv valid: **pass** (372 rows, byte-identical to pre-change output)
- no NaN/infinite: **pass**
- P10/P50/P90 valid (revenue + ROAS): **pass**
- windows 30/60/90: **pass**
- levels blended/channel/campaign_type/campaign: **pass**
- channels google/meta/microsoft: **pass**
- no LLM/network/backend imports in the scored path: **pass** (grep-verified)

## 3. Official dataset accuracy

- backtest runs: **pass**
- overall WAPE: 72.3% (P50)
- overall MAPE: 428.6% (P50, small-denominator campaigns inflate this; WAPE is the volume-weighted headline)
- interval coverage: 91.7% (target ~80%)
- pinball loss P10/P50/P90: 1,664.1 / 7,097.3 / 9,435.8
- accuracy regression vs prior (reports/backtest_report.md): **no — identical**
- OOD fallback on official data: not triggered (High confidence, weights 1.0/0.0)
- final status: **pass**

## 4. External large dataset OOD test

- external dataset found: yes (the three external CSVs provided at the repo parent; tested via a temporary `external_test_data/` folder, deleted after QA)
- run.sh external data: **pass** (666 rows, validate_submission PASS)
- historical ROAS: 3.74x blended
- forecast ROAS before fallback (model only, P50): 3.32x / 3.49x / 3.78x (30/60/90d)
- forecast ROAS after fallback (shipped, P50): 2.56x / 2.67x / 2.91x — no collapse, nothing near 0.03x
- OOD score: 0.339 (predict path) / 0.448 (full-history validate path)
- confidence: **Medium**
- fallback used: **yes**
- model weight: 0.60 · baseline weight: 0.40 · interval widening: 1.34x
- warning shown: yes — run.sh stdout, output scale_report.json, /validate issues, frontend scale section
- Low-confidence 25/75 path (the 0.03x collapse scenario): unit-tested in tests/test_scale_guard.py
- final status: **pass**

## 5. Frontend graph QA

- npm install: **pass** · npm run build: **pass**
- Upload page: **pass** (live-tested via API; real CSVs parse to session)
- Validation page: **pass** (scale/OOD section renders backend data)
- Forecast graphs (30/60/90 tabs, P10/P50/P90 cards + range bars): **pass**
- Channel contribution chart (revenue P50 + ROAS P50 by channel): **pass**
- Budget simulator comparison chart (current vs simulated spend/revenue/ROAS): **pass**
- Risk/confidence visual (badges by channel + OOD banner): **pass**
- AI Insights: **pass** (template fallback verified live)
- white background/black text/light gray borders, no dark mode/gradients: **pass**
- no overlapping layout: pass at code level (cards grid + overflow-x-auto tables); pixel-level screenshot sweep intentionally skipped per instruction — recommend one manual click-through
- no console errors: **pass** (fresh tracked load, zero errors)

## 6. Backend/session/AI QA

- backend starts: **pass** (uvicorn, model + training profile loaded)
- no-key mode works: **pass** (all five endpoints with every LLM key empty and Ollama unreachable)
- unknown session handled: **pass** (404, clear message)
- expired session handled: **pass** (frontend auto-returns to Upload)
- AI fallback works: **pass** (provider: "template", guardrail: "fallback", no invented numbers)
- run.sh unaffected by AI/backend/frontend: **pass**

## 7. Files changed

Modified: `src/predict.py`, `src/train.py`, `src/backtest.py`, `README.md`,
`product/backend/app/core.py`, `product/backend/app/main.py`,
`product/frontend/src/App.jsx`, `pages/{Dashboard,Breakdown,Simulator,Validation,Insights}.jsx`.
Added: `src/forecasting/scale_guard.py`, `pickle/training_profile.json` (sidecar, not gitignored),
`tests/test_scale_guard.py`, `product/frontend/src/lib/charts.jsx`, five QA reports in `reports/`.
Untouched: `run.sh`, `pickle/model.pkl`, `requirements.txt`, output schema.

Repo structure matches the submission guide: `run.sh`, `requirements.txt`,
`data/` (official sample), `pickle/model.pkl`, `src/`, `README.md` at root;
everything else is permitted extras. All temporary QA artifacts
(external_test_data/, output_external/, scratchpad files, test servers) were
deleted/stopped.

## 8. Remaining risks

- Pixel-level layout at unusual viewports was not screenshot-verified
  (browser automation skipped per instruction) — one manual click-through of
  the six pages is recommended before the demo.
- Otherwise: no critical scoring or demo risks found.

## 9. Final judge command

```
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

Verified again after cleanup as the last step of this QA (plus 5x stability
run in full_submission_test.sh) — VALIDATION PASSED every time, and the full
pytest suite (19 tests) passes.
