#!/usr/bin/env python
"""Parser inspection for the official AIgnition exports (Google / Bing / Meta).

Usage:  python scripts/inspect_data_parsing.py --data-dir ./data

Reports, per file and per channel: raw vs parsed row counts, date range, spend,
revenue, campaign count, channel=other share, invalid dates, zero-value
warnings, and a Google cost_micros sanity check. Exits non-zero if any hard
parsing rule is violated (mirrors the strict checks in forecasting/ingest.py so
this can be run standalone as a pre-submission gate).

Uses only the shared mapping layer + pandas/numpy (already pinned).
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import pandas as pd

# Make the shared forecasting core importable regardless of CWD.
_THIS = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_THIS, "..", "src"))
sys.path.insert(0, _SRC)
from forecasting import mapping  # noqa: E402

MAX_OTHER_SHARE = 0.05
_failures: list[str] = []


def fail(msg: str) -> None:
    _failures.append(msg)
    print(f"  [FAIL] {msg}")


def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def _money(x) -> str:
    return f"${float(x):,.0f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="./data")
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.data_dir, "**", "*.csv"), recursive=True))
    if not paths:
        print(f"No CSV files found under {args.data_dir!r}")
        return 1

    print("=" * 70)
    print(f"  ROAScast data parsing inspection  ({args.data_dir})")
    print("=" * 70)
    print(f"  files found: {len(paths)}")
    for p in paths:
        print(f"    - {os.path.basename(p)}")

    all_long = []
    for path in paths:
        name = os.path.basename(path)
        print("\n" + "-" * 70)
        print(f"  {name}")
        try:
            raw = pd.read_csv(path)
        except Exception as exc:
            fail(f"{name}: could not read CSV ({exc})")
            continue

        raw_rows = len(raw)
        hint = mapping.infer_channel_from_filename(path)
        has_rev_col = mapping.has_revenue_column(raw.columns)

        # Count invalid dates BEFORE to_long drops them.
        cols = list(raw.columns)
        date_col = mapping._resolve(cols, "date")
        if date_col is not None:
            parsed_dates = pd.to_datetime(raw[date_col], errors="coerce")
            invalid_dates = int(parsed_dates.isna().sum())
        else:
            invalid_dates = raw_rows  # no date column at all

        long_df = mapping.to_long(raw, channel_hint=hint)
        parsed_rows = len(long_df)

        print(f"    channel (from filename) : {hint or 'auto-detect'}")
        print(f"    raw rows                : {raw_rows:,}")
        print(f"    parsed rows             : {parsed_rows:,}")
        print(f"    invalid/undated rows    : {invalid_dates:,} (dropped)")

        # Hard rule: an official-named file must parse to > 0 rows.
        if hint is not None and parsed_rows == 0:
            fail(f"{name}: official {hint} file parsed to 0 rows")
            continue

        if parsed_rows:
            spend = float(long_df["spend"].sum())
            revenue = float(long_df["revenue"].sum())
            zero_rev = int((long_df["revenue"] <= 0).sum())
            zero_spend = int((long_df["spend"] <= 0).sum())
            print(f"    date range              : "
                  f"{long_df['date'].min().date()} -> {long_df['date'].max().date()}")
            print(f"    campaigns               : {long_df['campaign'].nunique()}")
            print(f"    spend                   : {_money(spend)}")
            print(f"    revenue                 : {_money(revenue)}")
            print(f"    campaign types          : "
                  f"{sorted(long_df['campaign_type'].unique())}")
            print(f"    zero-revenue rows       : {zero_rev:,} "
                  f"({zero_rev / parsed_rows:.1%})")
            print(f"    zero-spend rows         : {zero_spend:,} "
                  f"({zero_spend / parsed_rows:.1%})")

            if has_rev_col and revenue <= 0:
                fail(f"{name}: revenue column present but total revenue is 0")
            if (long_df[["impressions", "clicks", "spend", "conversions",
                         "revenue"]] < 0).any().any():
                fail(f"{name}: negative numeric values after parsing")

            # Google cost_micros sanity: raw micros / 1e6 must equal parsed spend.
            if hint == "google":
                spend_col = mapping._resolve(cols, "spend")
                if spend_col and "micros" in mapping._norm(spend_col):
                    raw_micros = pd.to_numeric(raw[spend_col], errors="coerce").fillna(0).sum()
                    implied = float(raw_micros) / 1_000_000.0
                    if abs(implied - spend) <= max(1.0, 0.001 * implied):
                        ok(f"Google cost_micros /1e6 verified "
                           f"(raw {raw_micros:,.0f} micros -> {_money(spend)})")
                    else:
                        fail(f"Google cost_micros division mismatch: "
                             f"implied {_money(implied)} vs parsed {_money(spend)}")
                else:
                    fail("Google file has no *_micros spend column (unexpected)")

            all_long.append(long_df)

    # -------- combined checks --------
    print("\n" + "=" * 70)
    print("  COMBINED")
    print("=" * 70)
    if not all_long:
        fail("no usable rows parsed from any file")
    else:
        combined = pd.concat(all_long, ignore_index=True)
        other_share = float((combined["channel"] == "other").mean())
        print(f"  total parsed rows : {len(combined):,}")
        print(f"  channels          : {sorted(combined['channel'].unique())}")
        print(f"  channel=other     : {other_share:.2%}")
        print(f"  date range        : "
              f"{combined['date'].min().date()} -> {combined['date'].max().date()}")
        per = combined.groupby("channel")[["spend", "revenue"]].sum()
        for ch, row in per.iterrows():
            print(f"    {ch:<10} spend={_money(row['spend']):>14}  "
                  f"revenue={_money(row['revenue']):>14}")
        if other_share > MAX_OTHER_SHARE:
            fail(f"channel=other {other_share:.1%} exceeds "
                 f"{MAX_OTHER_SHARE:.0%} limit")
        else:
            ok(f"channel=other within limit ({other_share:.2%} <= "
               f"{MAX_OTHER_SHARE:.0%})")

    print("\n" + "=" * 70)
    if _failures:
        print(f"  DATA PARSING INSPECTION: FAIL ({len(_failures)} problem(s))")
        for m in _failures:
            print(f"   - {m}")
        return 1
    print("  DATA PARSING INSPECTION: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
