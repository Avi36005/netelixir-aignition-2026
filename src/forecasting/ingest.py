"""Shared CSV ingestion + HARD validation for every entry point.

Used by generate_features.py, train.py, and backtest.py so the three can never
drift. Reads every CSV under a data dir, passes a filename-based channel hint
into the mapper, and then FAILS LOUDLY (strict mode, the default) when the
parse looks wrong — a silent mis-parse scores worse than a crash we can fix.

Checks enforced in strict mode:
  * an official-named file (google/bing/meta *_campaign_stats.csv) that parses
    to 0 rows aborts the run;
  * more than 5% of rows landing in channel="other" aborts the run;
  * zero total parsed revenue while a source revenue column exists aborts;
  * spend from a *_micros source must have been divided by 1e6 (sanity bound).
"""
from __future__ import annotations

import glob
import os
import sys

import pandas as pd

from . import mapping

# Fraction of rows allowed to fall into the "other" channel bucket.
MAX_OTHER_SHARE = 0.05


def _read_csv(path):
    try:
        return pd.read_csv(path)
    except Exception as exc:  # a junk file must not abort the run
        print(f"[ingest] WARN: skipping {path}: {exc}", file=sys.stderr)
        return None


def load_long(data_dir: str, strict: bool = True) -> pd.DataFrame:
    """All CSVs under ``data_dir`` -> one validated long frame."""
    paths = sorted(glob.glob(os.path.join(data_dir, "**", "*.csv"), recursive=True))
    if not paths:
        paths = sorted(glob.glob(os.path.join(data_dir, "**", "*.csv*"), recursive=True))
    if not paths:
        raise FileNotFoundError(f"No CSV files found under {data_dir!r}")

    longs, any_revenue_col = [], False
    for path in paths:
        raw = _read_csv(path)
        if raw is None or raw.empty:
            continue
        hint = mapping.infer_channel_from_filename(path)
        any_revenue_col = any_revenue_col or mapping.has_revenue_column(raw.columns)
        long_df = mapping.to_long(raw, channel_hint=hint)

        name = os.path.basename(path)
        if strict and hint is not None and len(long_df) == 0:
            raise ValueError(
                f"Official file {name!r} (channel={hint}) parsed to 0 rows — "
                "column mapping is broken; refusing to continue."
            )
        print(
            f"[ingest] {name}: {len(long_df)} rows, channel="
            f"{hint or 'auto'}, spend={long_df['spend'].sum():,.0f}, "
            f"revenue={long_df['revenue'].sum():,.0f}"
        )
        if len(long_df):
            longs.append(long_df)

    if not longs:
        raise ValueError(f"No usable rows parsed from any CSV under {data_dir!r}")
    out = pd.concat(longs, ignore_index=True)

    if strict:
        other_share = float((out["channel"] == "other").mean())
        if other_share > MAX_OTHER_SHARE:
            raise ValueError(
                f"{other_share:.1%} of rows parsed as channel='other' "
                f"(limit {MAX_OTHER_SHARE:.0%}) — channel detection is broken."
            )
        if any_revenue_col and float(out["revenue"].sum()) <= 0:
            raise ValueError(
                "Source files carry revenue columns but total parsed revenue "
                "is 0 — revenue mapping is broken."
            )
        # micros sanity: no single campaign-day should cost > $10M after the
        # 1e6 division; if it does, cost_micros was almost surely not divided.
        if float(out["spend"].max()) > 10_000_000:
            raise ValueError(
                "Implausible per-row spend detected (> $10M/day) — "
                "cost_micros may not have been divided by 1,000,000."
            )
    return out


def summarize(long_df: pd.DataFrame) -> str:
    """Human-readable parse summary (used by backtest and feature CLIs)."""
    lines = [
        f"rows={len(long_df)}  campaigns={long_df['campaign'].nunique()}  "
        f"dates {long_df['date'].min().date()} -> {long_df['date'].max().date()}"
    ]
    per = long_df.groupby("channel")[["spend", "revenue"]].sum()
    for ch, row in per.iterrows():
        lines.append(f"  {ch:<10} spend=${row['spend']:>12,.0f}  revenue=${row['revenue']:>12,.0f}")
    return "\n".join(lines)
