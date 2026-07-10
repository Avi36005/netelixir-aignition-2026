# ROAScast — Probabilistic Revenue & ROAS Forecasting

![Python](https://img.shields.io/badge/python-3.10–3.13-black)
![Offline scoring](https://img.shields.io/badge/scoring-100%25%20offline-black)
![No LLM in run.sh](https://img.shields.io/badge/run.sh-no%20LLM%2C%20no%20network-black)
![Deps](https://img.shields.io/badge/dependencies-pinned-black)
![Model](https://img.shields.io/badge/model-LightGBM%20quantile%20%2B%20calibration-black)
![Coverage](https://img.shields.io/badge/P10–P90%20coverage-~92%25-black)

**NetElixir AIgnition 3.0 · Team Kryptonite**

> **Judge command** (exactly as in the submission guide):
> ```bash
> ./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
> ```
> Also works with no arguments (`./run.sh`) and via `bash run.sh …`. Verify the
> whole grading contract in one shot with `bash scripts/full_submission_test.sh`.

**The one-line story:** *forecast accuracy comes from the trained forecasting
model; the LLM only explains the forecast — with guardrails.*

A reproducible, offline forecasting core that predicts **probabilistic e-commerce
revenue and ROAS** from Google Ads, Microsoft/Bing Ads and Meta Ads exports, at the
**blended / channel / campaign-type / campaign** levels over **30 / 60 / 90-day**
windows. This repository is the **scored Track-1 core**: it runs end-to-end with
**no network access**, loads a **committed, pre-trained model**, and writes a
single `predictions.csv`.

> The online product layer (FastAPI + React dashboard + LLM narratives) lives
> behind a strict network wall under [`product/`](product/README.md) and imports
> this same forecasting core, so the demo and the scored output never disagree on
> the math. `run.sh` never installs or runs it. The LLM is product-only by design,
> because the scorer runs with the internet disabled.

---

## Quick start

```bash
# Python 3.13 (verified). Wheels also resolve on 3.10–3.13.
pip install -r requirements.txt
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

That single command generates features from whatever CSVs are in `./data`, loads
`./pickle/model.pkl`, and writes `./output/predictions.csv`. It also works with
no arguments (same defaults) and via `bash run.sh ...`.

**Exact command for the grader:**

```bash
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

- **Python version:** 3.13 (developed & tested). The pinned dependencies publish
  wheels for CPython 3.10–3.13.
- **No internet at runtime.** Everything (model, lookups, logic) is in the repo.
- **No retraining at test time.** `run.sh` only generates features and predicts.

---

## Output schema (`predictions.csv`)

One file covers all three windows. Columns, in order:

| column | meaning |
|---|---|
| `level` | `blended` \| `channel` \| `campaign_type` \| `campaign` (coarser levels leave finer columns blank) |
| `channel` | `google` \| `meta` \| `microsoft` \| `other` |
| `campaign_type` | `Search`, `Shopping`, `PerformanceMax`, `Display`, `Video`, `DemandGen`, `Prospecting`, `Retargeting`, `Brand`, `DPA`, `Other` |
| `campaign` | campaign name (campaign-level rows only) |
| `window_days` | `30` \| `60` \| `90` (aggregate total for the window — **never daily**) |
| `revenue_p10/p50/p90` | revenue quantiles, **USD** |
| `roas_p10/p50/p90` | ROAS quantiles — a **dimensionless multiple** (never `$`) |

`P10 ≤ P50 ≤ P90` is guaranteed for both revenue and ROAS, and the hierarchy is
**coherent**: campaign sums to campaign-type sums to channel sums to blended.

> ⚠️ **The exact scored schema is a Q&A item** (column names / required
> granularities / one file vs one-per-window). It is defined in **one place** —
> `src/forecasting/schema.py` — so matching the announced format is a one-line
> edit. See [Open items](#open-items-to-confirm-via-qa).

---


## Official dataset support (ingestion)

`data/` is parsed dynamically: every CSV is mapped by **filename channel
inference** first, then column aliases, then column-signature detection. The
three official AIgnition files are fully supported:

| file | channel | date | spend | revenue | conversions |
|---|---|---|---|---|---|
| `google_ads_campaign_stats.csv` | `google` | `segments_date` | `metrics_cost_micros` **÷ 1,000,000** | `metrics_conversions_value` | `metrics_conversions` |
| `bing_campaign_stats.csv` | `microsoft` | `TimePeriod` | `Spend` | `Revenue` | `Conversions` |
| `meta_ads_campaign_stats.csv` | `meta` | `date_start` | `spend` | `conversion` (value-like → **revenue**) | none → **0** (never poisons count features) |

Hard validation (`src/forecasting/ingest.py`) **fails loudly** when: an official
file parses to 0 rows; > 5% of rows land in channel `other`; total revenue is 0
while revenue columns exist; or a per-row spend suggests `cost_micros` was not
divided. Unknown columns never crash the run; rows with invalid dates are
dropped; all metrics are coerced to non-negative numerics.

---

## Architecture

One repository, two halves, separated by the **network wall**. Both halves share
a single forecasting core (`src/forecasting/`), so the demo and the scored output
can never disagree on the math.

```
            Google Ads CSV        Meta Ads CSV
                   \                 /
              ┌─────────────────────────────────┐
              │   SHARED FORECASTING CORE        │
              │   mapping · features · quantile  │
              │   model · curves · reconcile     │
              └───────────────┬─────────────────┘
                              │
      ┌───────────────────────┴────────────────────────┐
      │ TRACK 1 (THIS REPO)         ││ TRACK 2 (separate) │
      │ run.sh — OFFLINE, no net    ││ FastAPI+React+LLM  │
      │ → predictions.csv (scored)  ││ demo / finale      │
      └─────────────────────────────┘└────────────────────┘
                                 ↑ network wall — LLM lives ONLY on the right
```

### Repository layout

```
roascast/
├── run.sh                      # entry point (exact name, root, executable)
├── requirements.txt            # MINIMAL + pinned (scored core only)
├── requirements-product.txt    # product layer deps — run.sh NEVER installs this
├── data/                       # committed sample data; overwritten at test time
├── pickle/model.pkl            # committed trained model; loads offline
├── src/
│   ├── generate_features.py    # data/ -> features.parquet  (CLI)
│   ├── predict.py              # features + model -> predictions.csv  (CLI)
│   ├── train.py                # OFFLINE; writes model.pkl  (NOT in run path)
│   ├── backtest.py             # time-based validation report
│   ├── make_sample_data.py     # synthetic sample-data generator
│   └── forecasting/            # the shared core (imported by predict AND the API)
│       ├── schema.py           # output columns + currency — single source of truth
│       ├── mapping.py          # Google/Meta/MS channel + campaign-type normalization
│       ├── features.py         # feature engineering (no campaign identity)
│       ├── model.py            # ForecastModel: train / load / predict
│       ├── curves.py           # per-channel budget→revenue response curves
│       └── reconcile.py        # bottom-up hierarchy aggregation
└── tests/test_pipeline.py      # smoke + contract + coherence tests
```

---

## Methodology

### Model
A **single global gradient-boosting model** (LightGBM) rather than per-series
ARIMA/Prophet: the data is short, multi-series and sparse, so pooling across all
campaigns and letting **budget enter as a feature** generalizes far better — and
it scores **brand-new campaigns** from their attributes + behaviour.

- **Probabilistic ranges:** three quantile regressors at `alpha = 0.1 / 0.5 / 0.9`
  → P10 / P50 / P90 directly.
- **Quantile-crossing fix:** the three predictions are sorted row-wise so
  `P10 ≤ P50 ≤ P90` always.
- **Skew-robust target:** quantile models are fitted on `log1p(revenue)` and
  inverted with `expm1` — quantiles are invariant under monotone transforms, so
  the P10/P50/P90 remain valid while heavy revenue skew stops dominating the fit.
- **Ensemble P50:** Model A (LightGBM quantiles) is blended with Model B, a
  **seasonal ROAS baseline** (trailing 28-day ROAS × planned spend × seasonal
  index). The blend weight is selected by WAPE on a forward time-based
  calibration split, defaulting LightGBM-heavy when the blend does not help.
- **Calibrated intervals (a headline differentiator):** the same time-based split
  learns a single interval-width multiplier so out-of-sample coverage targets
  ~80% — the point forecast (P50) is never altered.
- **Spend is a known input.** We forecast **revenue given a budget** and derive
  ROAS = revenue ÷ spend. ROAS is never modelled directly.

### Features (per `campaign × window`)
- **Never campaign identity.** No campaign-name/ID encoding — the held-out set has
  unseen campaigns; identity features would assign garbage. We use **attributes +
  behaviour** only.
- **Attributes:** channel, campaign_type, is_brand.
- **Trailing behaviour:** 14/28-day revenue, spend, ROAS, conversions, clicks,
  impressions, CTR, CVR, CPC; WoW/MoM growth; daily spend rate; active days.
- **Calendar / seasonality:** month, week-of-month, trend index, a learned monthly
  seasonal index, and an explicit **US retail calendar** (Black Friday, Cyber
  Monday, the Nov–Dec peak) — a 30/60/90-day window crossing BFCM moves revenue
  enormously, so the model must know.
- **Budget (`budget_input`):** the planned spend for the window. Its derivation is
  isolated in `features.derive_budget_input()` (see [Assumptions](#assumptions)).
- **Defensive computation:** every feature falls back (group mean → channel mean →
  global mean → 0). No NaN ever reaches the model.

### Budget response curves
A **per-channel saturating Hill curve** is fitted on historical `(spend, revenue)`
pairs (pure NumPy, no scipy). It makes diminishing returns explicit, powers the
budget what-if simulator, and is **monotone increasing by construction** — which is
how we guarantee "revenue cannot fall as budget rises" (see the note below).
Curves are **independent per channel** — deliberately **not** a media-mix model.

> **Monotonicity note.** LightGBM rejects `monotone_constraints` under the
> `quantile` objective. We therefore guarantee budget→revenue monotonicity
> *structurally*: (a) the saturating response curves used for every budget what-if
> are monotone by construction, and (b) any budget sweep through the GBM is passed
> through an isotonic (cumulative-max) step (`model.predict_budget_sweep`). The
> scored output uses one budget per entity, where row-wise monotonicity does not
> apply.

### Reconciliation
We predict at the **campaign** level and aggregate **upward** to
campaign-type → channel → blended. Summing medians is exact; summing the P10/P90
bounds is a stated interval approximation. ROAS at each level is revenue ÷ total
planned spend at that level.

---

## Validation

A **time-based backtest** (`python src/backtest.py --data-dir ./data`) mimics the
scorer: train on an earlier period, hold out the forward 30/60/90-day window,
predict, and score against realized actuals. On the official AIgnition dataset
(Google + Bing + Meta, 25,562 rows, 109 campaigns, 2024-01-01 → 2026-06-05):

| metric | result | notes |
|---|---|---|
| **Interval coverage** | **~92%** | fraction of actuals inside P10–P90 (target ~80%; conservative side) |
| **WAPE on P50** | **~72%** | volume-weighted campaign-level revenue error over 30/60/90d holdout |
| **Pinball P10/P50/P90** | 1,664 / 7,097 / 9,436 | the standard probabilistic scoring metric |

The backtest also reports per-window and per-channel coverage/WAPE/MAPE, parsed
per-channel spend/revenue totals, campaign counts and the date range. MAPE is
reported but dominated by near-zero-revenue campaigns; WAPE is the honest
aggregate number.

---

## Assumptions

- **Spend is a known input**, not a forecast target. We forecast revenue given a
  budget and derive ROAS. `budget_input` is set in **one** documented place
  (`features.derive_budget_input`): at **training** it is the realized spend over
  the target window; at **prediction** it is the trailing 28-day spend
  extrapolated across the window (or an explicit future-spend column if the test
  set provides one — a one-line switch).
- **Existing platform attribution is the source of truth**, used as-is. No custom
  attribution engine.
- **Blended total = simple sum** across Google + Microsoft + Meta. Cross-platform attribution
  overlap (a conversion can be claimed by both) is **acknowledged, not
  deduplicated** — deduplication would require an attribution model, which is out
  of scope.
- All monetary values are **USD**, native to the exports (no FX conversion).

## Limitations

- **Limited history → limited seasonality.** With ~14 months of sample data the
  model sees one BFCM peak; the seasonal index is correspondingly coarse. More
  history sharpens it.
- **Interval-summing approximation.** Aggregated P10/P90 bounds are summed across
  the hierarchy (an additive approximation), so a parent interval is wider than a
  strict joint-distribution interval would be. Medians are exact.
- **Per-channel curves, not an MMM.** Cross-channel interactions (halo, cannibal-
  ization) are intentionally not modelled.
- **Meta conversion counts are unavailable** in the official export (its
  `conversion` column is value-like and mapped to revenue), so meta CVR features
  fall back to safe defaults.

---

## Reproducibility

- **Pinned dependencies** (`requirements.txt`) — installed & tested versions only.
- **All randomness seeded** (NumPy, LightGBM; `deterministic=True`).
- **No absolute paths** — relative paths / passed arguments only.
- **The model is committed** under `pickle/` (3 MB, no Git LFS) and stores
  LightGBM **model strings**, not Booster objects, for portability across patch
  versions. Verified to unpickle in a clean virtualenv with the pinned versions.
- `data/` is read **dynamically** (glob + column-signature detection); the code
  assumes the **schema**, not the row count, and tolerates unseen campaigns.

### Regenerate everything (offline dev)

```bash
python src/train.py --data-dir ./data --out ./pickle/model.pkl   # retrain
python src/backtest.py --data-dir ./data                         # validation report
python src/report.py --predictions ./output/predictions.csv        --out ./output/report.html                                # visual range-bar report
python -m pytest tests/ -q                                       # smoke + contract tests
```

The committed `pickle/model.pkl` is trained on the official Google + Bing + Meta
campaign stats in `data/`.

---

## AI Media Planner (product layer only — never in `run.sh`)

> *“ROAScast separates prediction from reasoning. The trained forecasting model
> generates calibrated P10/P50/P90 revenue and ROAS ranges. The AI Media
> Planner, which can run locally through Ollama or through API providers, only
> explains those outputs using strict guardrails. Every AI recommendation is
> grounded in structured forecast evidence, and unsafe or unsupported responses
> are automatically replaced by a deterministic fallback.”*

**Core principle: the ML model predicts · the LLM explains · guardrails verify.**

- The **forecasting model is trained on the campaign dataset**. The local LLM is
  **not** — it is grounded at runtime with structured forecast outputs and
  guardrails. The LLM never generates forecast numbers.
- Provider order (first available wins):
  **1. Ollama (local)** → 2. OpenAI → 3. Gemini → 4. Groq → **5. deterministic
  rule-based fallback** (no key, no network — insights always render).
- Guardrails: the LLM receives only a compact JSON context with explicit
  `allowed_channels` / `allowed_campaigns` / `allowed_metrics`; temperature 0;
  JSON-only responses; and a post-validator that rejects invented numbers,
  unknown campaign/channel names, missing evidence references, deterministic
  language (“will definitely”, “guaranteed”) and unsupported causality
  (“because of competitors / inflation / algorithm changes”). Rejected
  responses fall back to the rule-based generator, and the UI shows
  **Guardrail: Passed / Fallback used**.
- Tested in `tests/test_llm_guardrails.py` (invented numbers, fake campaigns,
  unsupported causality, provider-chain failure, keyless fallback).

**Optional local AI setup** (never required for scoring or the frontend):

```bash
ollama pull qwen3:8b               # default local analyst
ollama pull llama3.2:3b            # lightweight fallback
ollama pull mistral-small3.2:24b   # stronger instruction-following (optional)
# then run the product backend (product/README.md)
```

No model is ever downloaded at runtime; if Ollama is absent the chain simply
moves on to API keys, then to the deterministic fallback.

---

## Troubleshooting

| symptom | cause / fix |
|---|---|
| `run.sh: python not found` | Install Python 3.10–3.13 and ensure `python3` or `python` is on PATH. On Windows, disable the Microsoft Store python alias (run.sh skips it automatically if a real interpreter exists). |
| `ModuleNotFoundError: lightgbm` (or pandas/pyarrow) | Run `pip install -r requirements.txt` in the active environment first. |
| `Official file ... parsed to 0 rows` | Deliberate loud failure: an official-named CSV had unrecognizable columns. Check the file's header row matches the launch schema. |
| `No CSV files found under ./data` | `data/` is empty — drop the campaign-stats CSVs in and rerun. |
| Output file missing after a run | run.sh fails loudly *before* writing on any validation error — read the last error line; it names the exact contract violation. |
| Permission denied on `./run.sh` | Use `bash run.sh ...` (equivalent) or `chmod +x run.sh`. |

Verify the whole submission contract in one shot with
`bash scripts/full_submission_test.sh` (runs the grader command twice and
deep-validates the output).

---

## Open items to confirm (via Q&A)

These are isolated and trivially changeable; they do not block the pipeline:

1. **Exact `predictions.csv` schema** — column names/order, required granularities,
   one file for all windows vs one run per window. (Edit `schema.py`.)
2. **Scoring metric** — pinball loss / MAPE on P50 / coverage / a combination.
3. **Future spend in the held-out set** — present (use it directly as
   `budget_input`) or inferred (current trailing-extrapolation default).
4. ~~Real dataset column names~~ — **confirmed**: the official Google/Bing/Meta
   exports are parsed natively (see *Official dataset support*).

---

## Team

**Project Name:** ROAScast
**Team Name:** Kryptonite
**College:** Vivekanand Education Society's Institute Of Technology (VESIT)

**Team Members:**

- Avinash Gehi
- Hardik Hinduja
- Sahil Deshmukh ([@sahil200511](https://github.com/sahil200511))

Built for NetElixir AIgnition 3.0.
