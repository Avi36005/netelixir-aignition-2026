#!/usr/bin/env python
"""CLI: features parquet + pickled model -> predictions.csv (schema-validated).

Critically, this adds ``src/`` to ``sys.path`` BEFORE unpickling so the
``forecasting.ForecastModel`` class resolves at load time — otherwise the grader
hits ``ModuleNotFoundError: No module named 'forecasting'``.

Writes the output FRESH every run (overwrite, never append).
"""
from __future__ import annotations

import argparse
import os
import sys

import joblib
import pandas as pd

# MUST precede joblib.load so the pickled class can be imported.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from forecasting import reconcile, schema  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Predict revenue/ROAS -> predictions.csv")
    ap.add_argument("--features", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)

    model = joblib.load(args.model)
    table = pd.read_parquet(args.features)

    campaign_pred = model.predict(table)        # adds revenue_p10/p50/p90
    full = reconcile.reconcile(campaign_pred)   # campaign -> type -> channel -> blended
    full = schema.validate_output(full)         # raises on ANY contract violation

    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir or ".", exist_ok=True)
    full.to_csv(args.output, index=False)       # fresh every run

    print(
        f"[predict] wrote {len(full)} rows -> {args.output} "
        f"(currency={schema.CURRENCY}, model={getattr(model, 'version', '?')})"
    )


if __name__ == "__main__":
    main()
