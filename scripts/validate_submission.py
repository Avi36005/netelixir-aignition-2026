#!/usr/bin/env python
"""Standalone validator for predictions.csv — the grader's-eye view.

Usage:  python scripts/validate_submission.py [path/to/predictions.csv] [--data-dir ./data]

Exits non-zero with a clear message on ANY contract violation. Uses only
pandas/numpy (already pinned in requirements.txt). Independent of src/ so it
also catches bugs in the pipeline's own validation.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = [
    "level", "channel", "campaign_type", "campaign", "window_days",
    "revenue_p10", "revenue_p50", "revenue_p90",
    "roas_p10", "roas_p50", "roas_p90",
]
NUMERIC = REQUIRED_COLUMNS[4:]
WINDOWS = {30, 60, 90}
LEVELS = {"blended", "channel", "campaign_type", "campaign"}
EPS = 1e-9

_failures: list[str] = []


def check(ok: bool, msg: str) -> None:
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {msg}")
    if not ok:
        _failures.append(msg)


def official_channels_present(data_dir: str) -> set[str]:
    """Channels the output MUST contain, inferred from data/ filenames."""
    want = set()
    for path in glob.glob(os.path.join(data_dir, "**", "*.csv"), recursive=True):
        name = os.path.basename(path).lower()
        if "google" in name:
            want.add("google")
        if "bing" in name or "microsoft" in name:
            want.add("microsoft")
        if "meta" in name or "facebook" in name:
            want.add("meta")
    return want


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default="./output/predictions.csv")
    ap.add_argument("--data-dir", default="./data")
    args = ap.parse_args()

    print(f"validating {args.csv}")
    if not os.path.exists(args.csv):
        print("  [FAIL] output file does not exist")
        return 1
    check(os.path.getsize(args.csv) > 0, "file is not empty")

    df = pd.read_csv(args.csv, keep_default_na=False)
    num = df.copy()
    for c in NUMERIC:
        if c in num.columns:
            num[c] = pd.to_numeric(num[c], errors="coerce")

    check(list(df.columns) == REQUIRED_COLUMNS,
          f"columns exactly match required schema ({list(df.columns)!r})"
          if list(df.columns) != REQUIRED_COLUMNS else "columns exactly match required schema")
    check(len(df) > 1, f"more than 1 data row ({len(df)} rows)")
    check(not df.eq("").all(axis=1).any(), "no completely empty rows")

    vals = num[NUMERIC]
    check(not vals.isna().any().any(), "no NaN in numeric columns")
    check(np.isfinite(vals.to_numpy(dtype=float)).all(), "no infinite values")
    check((vals >= 0).all().all(), "revenue/ROAS/window all non-negative")

    check(set(num["window_days"].astype(int)) == WINDOWS,
          f"forecast windows are exactly 30/60/90 ({sorted(set(num['window_days'].astype(int)))})")
    check(set(df["level"]) == LEVELS,
          f"all four levels present ({sorted(set(df['level']))})")

    check(bool((num["revenue_p10"] <= num["revenue_p50"] + EPS).all()
               and (num["revenue_p50"] <= num["revenue_p90"] + EPS).all()),
          "revenue P10 <= P50 <= P90")
    check(bool((num["roas_p10"] <= num["roas_p50"] + EPS).all()
               and (num["roas_p50"] <= num["roas_p90"] + EPS).all()),
          "ROAS P10 <= P50 <= P90")

    want = official_channels_present(args.data_dir)
    got = set(df.loc[df["level"] == "channel", "channel"])
    check(want <= got,
          f"official channels present at channel level (want {sorted(want)}, got {sorted(got)})")

    dupes = df.duplicated(
        subset=["level", "window_days", "channel", "campaign_type", "campaign"]).sum()
    check(dupes == 0, f"no duplicate level/window/entity rows ({dupes} dupes)")

    # ROAS consistency: within each window, blended ROAS_p50 should equal
    # blended revenue_p50 / implied spend, and channel ROAS ordering should
    # mirror revenue ordering given the fixed spend denominator.
    coherent = True
    for w in sorted(WINDOWS):
        d = num[num["window_days"] == w]
        b = d[d["level"] == "blended"]
        ch = d[d["level"] == "channel"]
        if b.empty or ch.empty:
            coherent = False
            continue
        # channel revenues must sum to blended (bottom-up reconciliation)
        if abs(ch["revenue_p50"].sum() - float(b["revenue_p50"].iloc[0])) > \
                1e-3 * max(float(b["revenue_p50"].iloc[0]), 1.0):
            coherent = False
        # implied spend = revenue/roas must be consistent across quantiles
        r = b.iloc[0]
        spends = [r[f"revenue_p{q}"] / r[f"roas_p{q}"]
                  for q in (10, 50, 90) if r[f"roas_p{q}"] > 0]
        if spends and (max(spends) - min(spends)) > 0.01 * max(spends):
            coherent = False
    check(coherent, "hierarchy coherent + ROAS == revenue/spend with one spend denominator")

    if _failures:
        print(f"\nVALIDATION FAILED — {len(_failures)} problem(s):")
        for m in _failures:
            print(f"  - {m}")
        return 1
    print("\nVALIDATION PASSED — predictions.csv satisfies the scoring contract.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
