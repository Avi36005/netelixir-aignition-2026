#!/usr/bin/env python
"""OFFLINE training — writes ``pickle/model.pkl``.

NOT referenced by ``run.sh``: the grader never retrains, it only loads this
pickle and predicts. Every source of randomness is seeded for reproducibility.

When the real AIgnition dataset is available, point ``--data-dir`` at a small
committed slice of it and confirm the real column names match ``mapping.py``.
"""
from __future__ import annotations

import argparse
import os
import random
import sys

import joblib
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from forecasting import curves, features, ingest, scale_guard  # noqa: E402
from forecasting import model as model_mod  # noqa: E402


def set_seeds(seed: int) -> None:
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Train ForecastModel -> pickle/model.pkl")
    ap.add_argument("--data-dir", default="./data")
    ap.add_argument("--out", default="./pickle/model.pkl")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    set_seeds(args.seed)
    long_df = ingest.load_long(args.data_dir, strict=True)
    print("[train] parsed:\n" + ingest.summarize(long_df))

    seasonal = features.compute_seasonal_index(long_df)
    channel_curves = curves.fit_channel_curves(long_df)
    raw, raw_ex, targets = features.build_training_table(long_df, seed=args.seed)
    if len(raw) == 0:
        raise ValueError("No training samples produced — check the data span/history.")

    model = model_mod.ForecastModel().train(
        raw, targets, seasonal, channel_curves, raw_calib=raw_ex, seed=args.seed
    )

    # Training-distribution profile for the OOD scale guard: stored both on
    # the model AND as a JSON sidecar next to the pickle (survives a pickle
    # from an older class version).
    profile = scale_guard.build_training_profile(long_df)
    model.training_profile_ = profile

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir or ".", exist_ok=True)
    joblib.dump(model, args.out)
    profile_path = scale_guard.save_profile(profile, args.out)
    print(f"[train] training profile -> {profile_path}")

    print(
        f"[train] {len(raw)} samples ({raw['campaign'].nunique()} campaigns); "
        f"features={len(model.feature_columns_)}; "
        f"seasonal_months={len(seasonal)}; curves={sorted(channel_curves)}; "
        f"calib_factor={model.calib_factor_:.3f}; "
        f"blend_weight={model.blend_weight_:.2f}; -> {args.out}"
    )


if __name__ == "__main__":
    main()
