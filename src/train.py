#!/usr/bin/env python
"""OFFLINE training — writes ``pickle/model.pkl``.

NOT referenced by ``run.sh``: the grader never retrains, it only loads this
pickle and predicts. Every source of randomness is seeded for reproducibility.

When the real AIgnition dataset is available, point ``--data-dir`` at a small
committed slice of it and confirm the real column names match ``mapping.py``.
"""
from __future__ import annotations

import argparse
import glob
import os
import random
import sys

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from forecasting import curves, features, mapping  # noqa: E402
from forecasting import model as model_mod  # noqa: E402


def set_seeds(seed: int) -> None:
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)


def load_long(data_dir: str) -> pd.DataFrame:
    paths = sorted(glob.glob(os.path.join(data_dir, "**", "*.csv"), recursive=True))
    longs = [mapping.to_long(pd.read_csv(p)) for p in paths if os.path.getsize(p) > 0]
    longs = [df for df in longs if len(df)]
    if not longs:
        raise ValueError(f"No usable training data under {data_dir!r}")
    return pd.concat(longs, ignore_index=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Train ForecastModel -> pickle/model.pkl")
    ap.add_argument("--data-dir", default="./data")
    ap.add_argument("--out", default="./pickle/model.pkl")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    set_seeds(args.seed)
    long_df = load_long(args.data_dir)

    seasonal = features.compute_seasonal_index(long_df)
    channel_curves = curves.fit_channel_curves(long_df)
    raw, raw_ex, targets = features.build_training_table(long_df, seed=args.seed)
    if len(raw) == 0:
        raise ValueError("No training samples produced — check the data span/history.")

    model = model_mod.ForecastModel().train(
        raw, targets, seasonal, channel_curves, raw_calib=raw_ex, seed=args.seed
    )

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir or ".", exist_ok=True)
    joblib.dump(model, args.out)

    print(
        f"[train] {len(raw)} samples ({raw['campaign'].nunique()} campaigns); "
        f"features={len(model.feature_columns_)}; "
        f"seasonal_months={len(seasonal)}; curves={sorted(channel_curves)}; "
        f"calib_factor={model.calib_factor_:.3f}; -> {args.out}"
    )


if __name__ == "__main__":
    main()
