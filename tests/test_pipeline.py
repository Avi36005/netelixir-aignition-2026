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


def test_run_sh_end_to_end(tmp_path):
    out = tmp_path / "predictions.csv"
    result = subprocess.run(
        [
            "bash",
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
        ["bash", os.path.join(ROOT, "run.sh"), os.path.join(ROOT, "data"),
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
        ["bash", os.path.join(ROOT, "run.sh"), os.path.join(ROOT, "data"),
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


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        test_run_sh_end_to_end(Path(d))
        test_hierarchy_coherence(Path(d))
        test_roas_is_dimensionless_and_ordered(Path(d))
    test_mapping_never_crashes_on_garbage()
    print("All tests passed.")
