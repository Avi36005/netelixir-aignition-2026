# ROAScast Prediction Output Summary

Generated from `output/predictions.csv` produced by
`bash run.sh ./data ./pickle/model.pkl ./output/predictions.csv`.
All figures are read directly from the emitted file — nothing is hand-written.

## Output shape

| item | value |
|---|---|
| Total rows | 372 |
| Columns | `level, channel, campaign_type, campaign, window_days, revenue_p10, revenue_p50, revenue_p90, roas_p10, roas_p50, roas_p90` (11) |
| Forecast windows present | 30, 60, 90 |
| Currency | USD |
| Model version | roascast-1.0.0 |

## Rows by level

| level | rows | note |
|---|---|---|
| blended | 3 | one per window (30/60/90) |
| channel | 9 | 3 channels × 3 windows |
| campaign_type | 33 | 11 channel×type groups × 3 windows |
| campaign | 327 | 109 campaigns × 3 windows |

Channels present at channel level: **google, meta, microsoft** (all three
official channels).

## Value ranges

| metric | min | max |
|---|---|---|
| revenue_p50 | $0.00 | $894,302.26 |
| roas_p50 | 0.00x | 8.07x |

- No negative revenue or ROAS anywhere in the file.
- `revenue_p10 <= revenue_p50 <= revenue_p90` holds for every row.
- `roas_p10 <= roas_p50 <= roas_p90` holds for every row.
- Structural blanks in `channel` / `campaign_type` / `campaign` for the
  higher aggregation levels are intentional (a blended row has no single
  channel); the validator treats these as empty strings, not NaN.

## Warnings / notes

- Some small/inactive campaigns forecast to `revenue_p50 = 0` — expected for
  campaigns whose recent history is near-zero; the P90 still carries upside.
- The hierarchy reconciles bottom-up: channel revenues sum to blended within
  tolerance (checked by `scripts/validate_submission.py`).

## Validation

`python scripts/validate_submission.py ./output/predictions.csv` → **PASS**
(all 14 contract checks green).
