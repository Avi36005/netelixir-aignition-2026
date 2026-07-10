# Official Dataset — Post-Change QA Report

Date: 2026-07-10 · Change under test: OOD scale-mismatch guardrail + frontend graphs.
All numbers below are real command outputs (nothing estimated).

## 1. Parsing summary (`./data`)

| file | rows | spend | revenue |
|---|---|---|---|
| google_ads_campaign_stats.csv | 19,272 | $1,946,126 | $9,266,678 |
| meta_ads_campaign_stats.csv | 3,417 | $196,387 | $1,656,751 |
| bing_campaign_stats.csv | 2,873 | $39,430 | $172,028 |

Total: 25,562 long rows · 109 campaigns · 2024-01-01 → 2026-06-05.

## 2. Predictions output summary

Command: `bash run.sh ./data ./pickle/model.pkl ./output/predictions.csv`

- 372 rows written; `scripts/validate_submission.py` → **VALIDATION PASSED** (all
  14 checks: schema, no NaN, no infinities, non-negative, P10 ≤ P50 ≤ P90 for
  revenue and ROAS, windows 30/60/90, all four levels, google/meta/microsoft
  present, no duplicates, coherent hierarchy).
- Blended ROAS P50: 4.47x (30d) / 4.34x (60d) / 4.47x (90d).
- Output is **byte-identical** to the pre-change predictions.csv (verified with
  `cmp` against a snapshot taken before the guardrail was added).
- Scored path imports: no LLM / network / backend modules (verified by grep on
  `predict.py`, `generate_features.py`, `scale_guard.py`).

## 3. OOD guard on official data

```
[predict] scale guard   : confidence=High ood_score=0.00
[predict] fallback used : no (model weight 1.00, baseline weight 0.00)
```

The fallback did **not** trigger on official-scale data — as designed, High
confidence passes the model prediction object through untouched.

## 4. Backtest metrics (time-based, 90d holdout, origin 2026-03-07)

| metric | previous (reports/backtest_report.md) | current | regressed? |
|---|---|---|---|
| Interval coverage (P10–P90) | 91.7% | 91.7% | no (identical) |
| WAPE on P50 | 72.3% | 72.3% | no (identical) |
| MAPE on P50 | 428.6% | 428.6% | no (identical) |
| Pinball P10/P50/P90 | 1,664.1 / 7,097.3 / 9,435.8 | same | no |

By window: 30d coverage 94.4% / WAPE 58.9% · 60d 91.7% / 71.4% · 90d 88.9% / 77.3%.
By channel: google 92.0% / 72.3% · meta 100% / 71.2% · microsoft 83.3% / 73.1%.

Accuracy is identical because the guard is a no-op at official scale — the
backtest exercises the exact model path used for scoring.

New guard-comparison section (same holdout rows, honest numbers):

| forecast | coverage | WAPE | MAPE |
|---|---|---|---|
| model only (what scoring uses) | 91.7% | 72.3% | 428.6% |
| baseline only | 15.7% | 78.7% | 432.8% |
| blended (Low-confidence 25/75) | 47.2% | 76.2% | 428.1% |

The model beats the baseline in-distribution — which is exactly why High
confidence keeps the model at 100% weight and the blend only activates
out-of-distribution.

## 5. Final status

**PASS** — pipeline valid, output byte-identical, accuracy unchanged, OOD
fallback correctly dormant on official data.
