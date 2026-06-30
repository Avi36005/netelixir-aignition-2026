#!/usr/bin/env python
"""CLI: read DATA_DIR dynamically -> unified long frame -> prediction features.

Reads ALL CSVs in the folder by pattern (never hardcodes filenames the test set
may not use), detects each platform by its column signature, and tolerates a
different row count and unseen campaigns. Writes an intermediate parquet that
``predict.py`` consumes.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import pandas as pd

# Make ``forecasting`` importable regardless of the caller's CWD.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from forecasting import features, mapping  # noqa: E402


def load_long(data_dir: str) -> pd.DataFrame:
    paths = sorted(glob.glob(os.path.join(data_dir, "**", "*.csv"), recursive=True))
    if not paths:  # also accept compressed exports
        paths = sorted(glob.glob(os.path.join(data_dir, "**", "*.csv*"), recursive=True))
    if not paths:
        raise FileNotFoundError(f"No CSV files found under {data_dir!r}")

    longs = []
    for path in paths:
        try:
            raw = pd.read_csv(path)
        except Exception as exc:  # a junk file must not abort the run
            print(f"[generate_features] WARN: skipping {path}: {exc}", file=sys.stderr)
            continue
        if raw is None or raw.empty:
            continue
        longs.append(mapping.to_long(raw))

    longs = [df for df in longs if len(df)]
    if not longs:
        raise ValueError(f"No usable rows parsed from any CSV under {data_dir!r}")
    return pd.concat(longs, ignore_index=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build prediction features from data/")
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    long_df = load_long(args.data_dir)
    table = features.build_prediction_table(long_df)

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir or ".", exist_ok=True)
    table.to_parquet(args.out, index=False)

    print(
        f"[generate_features] {len(long_df)} long rows -> {len(table)} feature rows "
        f"({table['campaign'].nunique()} campaigns x {table['window_days'].nunique()} "
        f"windows) -> {args.out}"
    )


if __name__ == "__main__":
    main()
