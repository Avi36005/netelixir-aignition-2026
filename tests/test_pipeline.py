"""Smoke + contract tests for the scored core.

Runs the full pipeline on the committed sample data via ``run.sh`` and asserts a
schema-valid, non-empty, coherent output. Also exercises the mapping layer's
"never crash on unfamiliar input" guarantee.

Run: ``python -m pytest tests/ -q``  (or ``python tests/test_pipeline.py``)
"""
import os
import subprocess
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from forecasting import mapping, schema  # noqa: E402


def _bash() -> str:
    """A REAL bash. On Windows, System32's bash.exe is a WSL stub that may not
    work — prefer Git Bash when present. On Linux/macOS this is just "bash"."""
    for cand in (r"C:\Program Files\Git\bin\bash.exe",
                 r"C:\Program Files\Git\usr\bin\bash.exe"):
        if os.name == "nt" and os.path.exists(cand):
            return cand
    return "bash"


def test_run_sh_end_to_end(tmp_path):
    out = tmp_path / "predictions.csv"
    result = subprocess.run(
        [
            _bash(),
            os.path.join(ROOT, "run.sh"),
            os.path.join(ROOT, "data"),
            os.path.join(ROOT, "pickle", "model.pkl"),
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"run.sh failed:\n{result.stderr}"
    assert out.exists(), "predictions.csv was not produced"

    df = pd.read_csv(out, keep_default_na=False)
    # Re-parse with NaN handling for the numeric validation.
    df_num = pd.read_csv(out)
    schema.validate_output(df_num)  # raises on any contract violation

    assert len(df_num) > 0
    assert (df_num["level"] == "blended").any(), "must include blended rows"
    assert set(df_num["window_days"].unique()) <= set(schema.WINDOWS)
    assert list(df_num.columns) == schema.OUTPUT_COLUMNS


def test_hierarchy_coherence(tmp_path):
    """Channel revenues must sum to the blended total (P50) per window."""
    out = tmp_path / "pred.csv"
    subprocess.run(
        [_bash(), os.path.join(ROOT, "run.sh"), os.path.join(ROOT, "data"),
         os.path.join(ROOT, "pickle", "model.pkl"), str(out)],
        check=True, capture_output=True, text=True,
    )
    df = pd.read_csv(out)
    for w in df["window_days"].unique():
        d = df[df["window_days"] == w]
        blended = d[d["level"] == "blended"]["revenue_p50"].sum()
        channel = d[d["level"] == "channel"]["revenue_p50"].sum()
        assert abs(blended - channel) <= 1e-3 * max(blended, 1.0), (
            f"window {w}: channel sum {channel} != blended {blended}"
        )


def test_roas_is_dimensionless_and_ordered(tmp_path):
    out = tmp_path / "pred.csv"
    subprocess.run(
        [_bash(), os.path.join(ROOT, "run.sh"), os.path.join(ROOT, "data"),
         os.path.join(ROOT, "pickle", "model.pkl"), str(out)],
        check=True, capture_output=True, text=True,
    )
    df = pd.read_csv(out)
    assert (df["roas_p10"] <= df["roas_p50"] + 1e-9).all()
    assert (df["roas_p50"] <= df["roas_p90"] + 1e-9).all()
    assert (df["revenue_p10"] <= df["revenue_p50"] + 1e-9).all()
    assert (df["revenue_p50"] <= df["revenue_p90"] + 1e-9).all()


def test_mapping_never_crashes_on_garbage():
    """Unknown channels/types must fall into safe buckets, not raise."""
    junk = pd.DataFrame(
        {
            "date": ["2025-01-01", "not-a-date", "2025-01-03"],
            "campaign_name": ["Mystery XYZ", "??", "Brand Search"],
            "weird_col": [1, 2, 3],
            "spend": [10, -5, "oops"],
            "conversion_value": [40, None, 100],
        }
    )
    long = mapping.to_long(junk)
    assert set(long["channel"]) <= set(mapping.CHANNELS)
    assert set(long["campaign_type"]) <= set(mapping.CAMPAIGN_TYPES)
    assert (long["spend"] >= 0).all()  # negative/garbage coerced to >= 0


def test_official_google_columns():
    raw = pd.DataFrame({
        "campaign_id": [1], "segments_date": ["2025-02-21"],
        "metrics_clicks": [10], "metrics_conversions": [2.0],
        "metrics_cost_micros": [5_000_000], "metrics_impressions": [100],
        "metrics_video_views": [0], "metrics_conversions_value": [42.5],
        "campaign_advertising_channel_type": ["SEARCH"],
        "campaign_budget_amount": [50.0], "campaign_name": ["Search_Campaign_01"],
    })
    long = mapping.to_long(raw, channel_hint="google")
    r = long.iloc[0]
    assert r["channel"] == "google"
    assert r["spend"] == 5.0, "cost_micros must be divided by 1,000,000"
    assert r["revenue"] == 42.5
    assert r["clicks"] == 10 and r["conversions"] == 2.0
    assert r["campaign_type"] == "Search"


def test_official_bing_columns():
    raw = pd.DataFrame({
        "CampaignId": [1], "TimePeriod": ["2024-05-25"], "Revenue": [99.0],
        "Spend": [4.7], "Clicks": [22], "Impressions": [140],
        "Conversions": [3.0], "CampaignType": ["Search"],
        "DailyBudget": [10.0], "CampaignName": ["Search_TM_Campaign_02"],
    })
    long = mapping.to_long(raw, channel_hint="microsoft")
    r = long.iloc[0]
    assert r["channel"] == "microsoft"
    assert r["revenue"] == 99.0 and r["spend"] == 4.7
    assert r["conversions"] == 3.0 and r["campaign_type"] == "Search"


def test_official_meta_columns_conversion_is_revenue_not_count():
    raw = pd.DataFrame({
        "campaign_id": [1], "date_start": ["2024-05-23"], "cpc": [12.1],
        "cpm": [55.7], "ctr": [1.6], "reach": [100.0], "spend": [85.0],
        "clicks": [37.0], "impressions": [5188.0], "conversion": [123.4],
        "daily_budget": [None], "campaign_name": ["Generic_Campaign_02"],
    })
    long = mapping.to_long(raw, channel_hint="meta")
    r = long.iloc[0]
    assert r["channel"] == "meta"
    assert r["revenue"] == 123.4, "meta 'conversion' is value-like -> revenue"
    assert r["conversions"] == 0.0, "meta has no true count -> must not poison counts"


def test_filename_channel_inference():
    assert mapping.infer_channel_from_filename("data/google_ads_campaign_stats.csv") == "google"
    assert mapping.infer_channel_from_filename("data/bing_campaign_stats.csv") == "microsoft"
    assert mapping.infer_channel_from_filename(r"C:\x\meta_ads_campaign_stats.csv") == "meta"
    assert mapping.infer_channel_from_filename("data/mystery.csv") is None


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        test_run_sh_end_to_end(Path(d))
        test_hierarchy_coherence(Path(d))
        test_roas_is_dimensionless_and_ordered(Path(d))
    test_mapping_never_crashes_on_garbage()
    print("All tests passed.")
