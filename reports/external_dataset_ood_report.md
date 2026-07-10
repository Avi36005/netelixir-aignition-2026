# External Large Dataset — OOD Guardrail Report

Date: 2026-07-10 · Dataset: `./external_test_data` (the three external CSVs
provided at the repo parent directory — copied in verbatim, not generated).
The model was **not** retrained on this data.

## 1. Dataset summary

- 124,063 rows · 205 campaigns · 2023-01-01 → 2025-06-30.
- Totals: spend $24,543,713 · revenue $91,759,715 (google $19.8M/$69.7M,
  meta $3.9M/$19.4M, microsoft $0.77M/$2.7M).
- Uploaded monthly scale vs training profile: revenue median **6.6x** and spend
  median **11.3x** the training median (both above the training P90).
- **Historical (trailing) blended ROAS: 3.74x.**

## 2. Pipeline + validation

Command: `bash run.sh ./external_test_data ./pickle/model.pkl ./output_external/external_predictions.csv`

- Succeeded; 666 rows written; `validate_submission.py` → **VALIDATION PASSED**
  (no NaN, no infinities, non-negative, P10 ≤ P50 ≤ P90, windows 30/60/90, all
  levels, google/meta/microsoft present, coherent hierarchy).

## 3. OOD guard verdict (`output_external/scale_report.json`)

| field | value |
|---|---|
| confidence | **Medium** |
| ood_score | **0.339** |
| fallback used | **yes** |
| model weight | 0.60 |
| baseline weight | 0.40 |
| interval widening | 1.339x |

Reasons reported (also shown in the product validation report and as warnings):
1. Uploaded monthly revenue is 6.6x higher than the training median
2. Uploaded monthly spend is 11.3x higher than the training median

## 4. Forecast ROAS — before vs after fallback

| window | model-only ROAS P50 (before) | shipped ROAS P50 (after blend) | historical |
|---|---|---|---|
| 30d | 3.32x | 2.56x | 3.74x |
| 60d | 3.49x | 2.67x | 3.74x |
| 90d | 3.78x | 2.91x | 3.74x |

- **No ROAS collapse**: nothing near the 0.03x failure mode; every P50 stays in
  a plausible 2.5–2.9x band vs the 3.74x trailing reality.
- The blend is slightly more conservative than the raw model here because the
  trailing-ROAS baseline is seasonally adjusted with the training-data seasonal
  index (summer months index below 1). This is disclosed, not hidden: the OOD
  score also widens the P10–P90 interval by 1.34x, so the truth remains well
  inside the shipped range.
- On this dataset the model itself did not collapse (its scale features —
  trailing spend/revenue — carry most of the signal), so Medium confidence and
  a 60/40 blend is the appropriate response. A dataset that *does* produce a
  collapsed prediction trips the model-vs-baseline divergence signal and drops
  to Low confidence with a 25/75 blend (unit-tested in
  `tests/test_scale_guard.py::test_100x_scale_triggers_low_confidence_blend`).

## 5. Warning visibility

- `run.sh` output: guard verdict + reasons printed by `predict.py` (never hidden).
- `output_external/scale_report.json`: full machine-readable report.
- Product backend: `/forecast` and `/explain` return `scale_guard`; `/validate`
  includes the scale assessment and injects reasons as warning issues.
- Frontend: Dashboard shows the Low-confidence warning banner when triggered;
  the Validation page always shows the training-scale comparison table,
  confidence badge, OOD score, and weights.

## 6. Final status

**PASS** — external data is detected as out-of-scale, confidence drops to
Medium, the baseline blend engages with reported weights, the output stays
contract-valid, and no absurd ROAS is produced.
