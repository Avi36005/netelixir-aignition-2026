"""Single source of truth for the scored output contract.

Every other module imports the column list, the level/window enums, and the
currency from here. The grader scores ``predictions.csv`` against an EXACT
column format announced at the hackathon Q&A. That format is NOT YET CONFIRMED,
so changing it must be a one-line edit in this file.

# CONFIRM EXACT SCHEMA AT Q&A:
#   - exact column names + order
#   - which granularities are required (blended only? + channel/type/campaign?)
#   - one file for all three windows (current assumption) or one run per window
"""
from __future__ import annotations

import pandas as pd

# Native to the Google/Meta exports — no FX conversion anywhere in the pipeline.
CURRENCY = "USD"

# Forecast horizons in days. AGGREGATE totals for the whole window — never daily.
WINDOWS = (30, 60, 90)

# Hierarchy levels, coarse -> fine. Higher levels leave the finer columns blank.
LEVELS = ("blended", "channel", "campaign_type", "campaign")

# Exact output columns, in order. ROAS is a dimensionless multiple — never "$".
OUTPUT_COLUMNS = [
    "level",
    "channel",
    "campaign_type",
    "campaign",
    "window_days",
    "revenue_p10",
    "revenue_p50",
    "revenue_p90",
    "roas_p10",
    "roas_p50",
    "roas_p90",
]

REVENUE_QUANTILES = ["revenue_p10", "revenue_p50", "revenue_p90"]
ROAS_QUANTILES = ["roas_p10", "roas_p50", "roas_p90"]

# Columns that should be blank ("") for a level coarser than that column.
BLANK_BY_LEVEL = {
    "blended": ["channel", "campaign_type", "campaign"],
    "channel": ["campaign_type", "campaign"],
    "campaign_type": ["campaign"],
    "campaign": [],
}

_EPS = 1e-9


def empty_output() -> pd.DataFrame:
    """An empty frame with the exact output columns (useful for guards/tests)."""
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


def validate_output(df: pd.DataFrame) -> pd.DataFrame:
    """Validate a predictions DataFrame against the contract.

    Returns the frame re-ordered to ``OUTPUT_COLUMNS`` or raises ``ValueError``.
    Call this immediately before writing the CSV — producing the right numbers
    in the wrong format scores zero.
    """
    if list(df.columns) != OUTPUT_COLUMNS:
        raise ValueError(
            f"Output columns {list(df.columns)} != required {OUTPUT_COLUMNS}"
        )
    if len(df) == 0:
        raise ValueError("Output is empty — grader expects at least blended rows.")

    bad_levels = set(df["level"]) - set(LEVELS)
    if bad_levels:
        raise ValueError(f"Unknown level values: {sorted(bad_levels)}")

    win = pd.to_numeric(df["window_days"], errors="coerce")
    if win.isna().any():
        raise ValueError("Non-numeric window_days present.")
    bad_windows = set(win.astype(int)) - set(WINDOWS)
    if bad_windows:
        raise ValueError(f"Unknown window_days: {sorted(bad_windows)}")

    # All quantile columns must be numeric, finite and non-negative.
    for col in REVENUE_QUANTILES + ROAS_QUANTILES:
        v = pd.to_numeric(df[col], errors="coerce")
        if v.isna().any():
            raise ValueError(f"Non-numeric/NaN value in {col}")
        if (v < 0).any():
            raise ValueError(f"Negative value in {col} (revenue/ROAS must be >= 0)")

    # P10 <= P50 <= P90 for both revenue and ROAS (no quantile crossing).
    for trio in (REVENUE_QUANTILES, ROAS_QUANTILES):
        a, b, c = (pd.to_numeric(df[x]) for x in trio)
        if not (bool((a <= b + _EPS).all()) and bool((b <= c + _EPS).all())):
            raise ValueError(f"Quantile crossing detected in {trio}")

    return df[OUTPUT_COLUMNS]
