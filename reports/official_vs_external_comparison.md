# Official vs External Dataset — OOD Guard Behavior Comparison

Date: 2026-07-10. Same model pickle (`pickle/model.pkl`, roascast-1.0.0), same
`run.sh`, no retraining. All values from real runs.

| | Official (`./data`) | External (`./external_test_data`) |
|---|---|---|
| rows / campaigns | 25,562 / 109 | 124,063 / 205 |
| date range | 2024-01-01 → 2026-06-05 | 2023-01-01 → 2025-06-30 |
| monthly scale vs training | 1x (it IS the training data) | revenue 6.6x, spend 11.3x the training median |
| **confidence** | **High** | **Medium** |
| **OOD score** | 0.00 | 0.339 |
| **fallback used** | no | **yes** |
| model / baseline weight | 1.00 / 0.00 | 0.60 / 0.40 |
| interval widening | none | 1.34x |
| historical (trailing) ROAS | ~4.0x (campaign median) | 3.74x (blended) |
| shipped blended ROAS P50 (30/60/90d) | 4.47x / 4.34x / 4.47x | 2.56x / 2.67x / 2.91x |
| warning shown | no (nothing to warn about) | yes — reasons in run.sh output, scale_report.json, /validate, frontend |
| validate_submission.py | PASS (all checks) | PASS (all checks) |
| backtest WAPE / coverage | 72.3% / 91.7% (identical to pre-change) | n/a (no retraining/backtest on external data by design) |
| output vs pre-change code | **byte-identical** | n/a (new capability) |

## Expected-behavior checklist

- ✅ Official dataset remains scoring-safe and calibrated — the guard is a
  strict no-op at High confidence (verified byte-identical output).
- ✅ External dataset triggers OOD confidence handling (Medium, score 0.339,
  two scale reasons).
- ✅ External dataset uses baseline blending (60/40) because the scale mismatch
  is large; a full collapse scenario blends 25/75 at Low confidence (covered by
  unit test).
- ✅ External dataset shows warnings everywhere instead of silently producing a
  bad forecast; shipped ROAS stays in a plausible band (2.5–2.9x vs 3.74x
  historical) instead of an absurd value like 0.03x.
