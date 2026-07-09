# ROAScast Final Submission QA Report

## 1. Judge command

```bash
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

## 2. Environment

- Python version: 3.13.2 (pinned wheels also resolve on CPython 3.10–3.13)
- OS: Windows 11 (development) — `run.sh` is plain POSIX bash, verified under Git Bash; grader Linux is the simpler case
- Fresh virtualenv tested: **yes** (clean `git clone` → `python -m venv` → `pip install --upgrade pip` → `pip install -r requirements.txt` → run → validate)
- requirements pinned: **yes** (7 packages, all `==`)

## 3. Repository structure

- run.sh (root, git mode 100755, `set -euo pipefail`): **pass**
- requirements.txt: **pass**
- data/ (official Google/Bing/Meta campaign stats): **pass**
- pickle/model.pkl (3.4 MB, plain git, no LFS): **pass**
- src/: **pass**
- README.md (Python version, schema, methodology, troubleshooting): **pass**

## 4. Run tests

- Explicit argument run: **pass**
- Default argument run (`bash run.sh`): **pass**
- Custom output path run (`./tmp_test_output/custom_predictions.csv`, `./output` untouched): **pass**
- Repeated 5× run: **pass** (see `scripts/full_submission_test.sh` output)
- Output freshness / no append (line count stable across reruns): **pass**
- No API key run (`env -u OPENAI_API_KEY -u GEMINI_API_KEY -u GROQ_API_KEY -u ANTHROPIC_API_KEY -u OLLAMA_HOST`): **pass**
- Dynamic DATA_DIR run (CSVs copied to a temp folder): **pass**
- Clean clone simulation (fresh venv): **pass**
- Edge cases (fewer rows, unknown columns, shuffled column order, invalid
  dates, missing CampaignType, zero-spend rows, missing channel): **pass**;
  an official-named file with unrecognizable columns **fails loudly** with no
  output file (correct behavior)

## 5. Data parsing (official dataset)

- Google rows: **19,272**
- Microsoft/Bing rows: **2,873**
- Meta rows: **3,417**
- channel=other percentage: **0%** (hard runtime limit: 5%)
- Date range: 2024-01-01 → 2026-06-05 · campaigns: **109**
- Google spend/revenue: **$1,946,126 / $9,266,678** (cost_micros ÷ 1e6 verified by unit test)
- Microsoft spend/revenue: **$39,430 / $172,028**
- Meta spend/revenue: **$196,387 / $1,656,751** (meta `conversion` mapped to revenue, never to conversion counts)

## 6. Output validation (`scripts/validate_submission.py`, 14 checks)

- predictions.csv exists & non-empty: **pass**
- no NaN / infinite values: **pass**
- windows 30/60/90 present: **pass**
- levels blended/channel/campaign_type/campaign present: **pass**
- P10 ≤ P50 ≤ P90 (revenue and ROAS): **pass**
- no negative revenue/ROAS: **pass**
- no duplicate level/window/entity rows: **pass**
- hierarchy sums coherent + ROAS ≡ revenue ÷ one spend denominator: **pass**
- custom OUTPUT_PATH honored: **pass**

## 7. Model

- model.pkl exists: **pass**
- model loads with joblib (fresh venv, pinned versions): **pass**
- no retraining required during run.sh: **pass**
- no internet required during run.sh: **pass** (code scan: no
  openai/gemini/groq/anthropic/ollama/requests/urllib/curl/wget in `src/` or
  `run.sh`; no absolute paths; no `input()`)
- no LLM required during run.sh: **pass**

## 8. Accuracy and backtest (`python src/backtest.py --data-dir ./data`)

- Backtest runs: **pass** (time-based forward holdout, fully seeded/reproducible)
- Overall WAPE (P50): **72.3%**
- Overall MAPE: 428.6% (dominated by near-zero-revenue campaigns — WAPE is the honest aggregate)
- P10 pinball loss: **1,664.1**
- P50 pinball loss: **7,097.3**
- P90 pinball loss: **9,435.8**
- P10–P90 interval coverage: **91.7%** (target ~80%, calibrated conservative)
- Best channel: **meta** (100% coverage, 62.6% MAPE)
- Weakest channel: **google on MAPE** (many small campaigns; WAPE 72.3%)
- Best forecast window: **30d** (94.4% coverage, 58.9% WAPE)
- Weakest forecast window: **90d** (88.9% coverage, 77.3% WAPE — horizon effect)

Full details: [`reports/backtest_report.md`](backtest_report.md).

## 9. Frontend (product layer, never in run.sh)

- Frontend present: **yes** (`product/frontend/`, React 18 + Vite 6 + Tailwind 3, JSX)
- `npm run build`: **pass** (35 modules, ~2.9s, no TS/import errors)
- Upload / Validation / Dashboard (30/60/90) / Channel Breakdown / Budget
  Simulator / AI Insights pages: **all present & build**
- White background / black text, no dark mode (`color-scheme: light`): **pass**
- Mock fallback works when backend unavailable: **pass**
- Not imported by run.sh / scoring: **pass**

Details: [`reports/frontend_test_report.md`](frontend_test_report.md).

## 10. Backend (product layer, never in run.sh)

- Backend present: **yes** (`product/backend/`, FastAPI, imports shared `src/forecasting`)
- Endpoints tested in-process (TestClient, no API keys):
  `/health`, `/upload`, `/validate`, `/forecast`, `/simulate`, `/explain` — **all pass**
- Error paths: unknown session → **404**, empty upload → **400**
- No-key fallback (deterministic `/explain`): **pass** (`provider=template`)
- Does not affect run.sh: **pass**

Details: [`reports/backend_test_report.md`](backend_test_report.md).

## 11. AI guardrails (product layer, never in run.sh)

`tests/test_llm_guardrails.py` — **7/7 passing** (full suite 15/15):
keyless deterministic fallback; invented-number rejection; fake-campaign
rejection; unsupported-causality rejection ("competitor activity",
"will definitely"); unsupported-channel rejection; grounded response
acceptance; full provider-chain failure falls back safely with logged reasons.

**Bug fixed during QA:** `_PROVIDERS` in `llm.py` captured function references
at import time, so the provider chain wasn't re-dispatchable and
`test_6_provider_chain_falls_through_to_template` failed (returned `openai`
and made a live API call instead of falling back to `template`). Changed to
resolve `_try_<name>` by name at call time. All tests green.

Details: [`reports/ai_guardrail_test_report.md`](ai_guardrail_test_report.md).

## 12. Remaining risks

No critical scoring risks found. Non-critical notes:
1. The grader's held-out data will shift totals; strict runtime validators
   turn any silent mis-parse into a loud, diagnosable failure instead of a
   wrong score.
2. Campaign-level WAPE ~72% reflects genuinely volatile 30–90-day campaign
   revenue; interval coverage (the probabilistic-forecast headline) is 91.7%.

## 13. Final verdict

**READY FOR SUBMISSION**

Gating checks confirmed this QA pass: clean-clone simulation (fresh venv from
`requirements.txt`) passes; `scripts/full_submission_test.sh` passes end-to-end
(explicit/default/custom/dynamic-dir/no-key runs, 5× stability, freshness);
model loads via joblib; `predictions.csv` validates (14/14); scoring runs with
no API keys, no internet, no LLM.

```bash
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```
