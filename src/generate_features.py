#!/usr/bin/env python
"""CLI: read DATA_DIR dynamically -> unified long frame -> prediction features.

Reads ALL CSVs in the folder by pattern (never hardcodes filenames the test set
may not use), detects each platform by its column signature, and tolerates a
different row count and unseen campaigns. Writes an intermediate parquet that
``predict.py`` consumes.
"""
from __future__ import annotations

import argparse
import os
import sys

# Make ``forecasting`` importable regardless of the caller's CWD.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from forecasting import features, ingest  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build prediction features from data/")
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    long_df = ingest.load_long(args.data_dir, strict=True)
    print("[generate_features] parsed:\n" + ingest.summarize(long_df))
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
