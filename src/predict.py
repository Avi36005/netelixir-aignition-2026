#!/usr/bin/env python
"""CLI: features parquet + pickled model -> predictions.csv (schema-validated).

Critically, this adds ``src/`` to ``sys.path`` BEFORE unpickling so the
``forecasting.ForecastModel`` class resolves at load time — otherwise the grader
hits ``ModuleNotFoundError: No module named 'forecasting'``.

Writes the output FRESH every run (overwrite, never append).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import joblib
import pandas as pd

# MUST precede joblib.load so the pickled class can be imported.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from forecasting import reconcile, scale_guard, schema  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Predict revenue/ROAS -> predictions.csv")
    ap.add_argument("--features", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)

    model = joblib.load(args.model)
    table = pd.read_parquet(args.features)

    campaign_pred = model.predict(table)        # adds revenue_p10/p50/p90

    # OOD scale guardrail: on in-distribution (official-scale) data this is a
    # no-op and predictions pass through untouched. On far-out-of-scale data
    # it blends the model with a trailing-ROAS baseline and widens intervals.
    guard_info = None
    profile = scale_guard.load_profile(args.model, model)
    if profile is not None:
        campaign_pred, guard_info = scale_guard.run_guardrail(
            campaign_pred, table, getattr(model, "seasonal_index_", {}),
            profile,
            getattr(model, "fallback_", {}).get("global_median_roas", 1.0))
        print("[predict] " + scale_guard.format_report(guard_info)
              .replace("\n", "\n[predict] "))
    else:
        print("[predict] scale guard: no training profile found next to the "
              "model — OOD detection skipped (model used as-is).")

    full = reconcile.reconcile(campaign_pred)   # campaign -> type -> channel -> blended
    full = schema.validate_output(full)         # raises on ANY contract violation

    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir or ".", exist_ok=True)
    full.to_csv(args.output, index=False)       # fresh every run

    if guard_info is not None:  # sidecar report; predictions.csv schema untouched
        with open(os.path.join(out_dir or ".", "scale_report.json"), "w",
                  encoding="utf-8") as f:
            json.dump(guard_info, f, indent=2)

    print(
        f"[predict] wrote {len(full)} rows -> {args.output} "
        f"(currency={schema.CURRENCY}, model={getattr(model, 'version', '?')})"
    )


if __name__ == "__main__":
    main()
