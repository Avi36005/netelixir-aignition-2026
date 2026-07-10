"""OOD scale-guard tests: in-distribution data passes through untouched,
out-of-scale data triggers the baseline blend, and outputs stay contract-valid.

Run: ``python -m pytest tests/test_scale_guard.py -q``
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from forecasting import scale_guard  # noqa: E402


def _profile(scale=1.0):
    return {
        "profile_version": 1,
        "channels": ["google", "meta", "microsoft"],
        "campaign_types": ["Search", "Shopping", "PerformanceMax"],
        "monthly_spend": {"p10": 27e3 * scale, "p50": 38e3 * scale, "p90": 216e3 * scale},
        "monthly_revenue": {"p10": 125e3 * scale, "p50": 247e3 * scale, "p90": 717e3 * scale},
        "campaign_monthly_spend": {"p10": 56 * scale, "p50": 692 * scale, "p90": 5252 * scale},
        "campaign_monthly_revenue": {"p10": 0.0, "p50": 3720 * scale, "p90": 29529 * scale},
        "roas": {"p10": 0.5, "p50": 4.0, "p90": 7.4},
        "other_channel_share": 0.0,
    }


def _table(n=6, spend_per_campaign=700.0, roas=4.0):
    rows = []
    for i in range(n):
        for w in (30, 60, 90):
            monthly = spend_per_campaign
            rows.append({
                "campaign": f"c{i}", "channel": "google",
                "campaign_type": "Search", "is_brand": 0,
                "window_days": w,
                "window_start": pd.Timestamp("2026-06-06"),
                "budget_input": monthly / 30.0 * w,
                "tr28_spend": monthly * 28 / 30, "tr14_spend": monthly * 14 / 30,
                "tr28_revenue": monthly * 28 / 30 * roas,
                "tr14_revenue": monthly * 14 / 30 * roas,
                "tr28_roas": roas, "tr14_roas": roas,
            })
    return pd.DataFrame(rows)


def _model_pred(table, roas=4.0):
    out = table.copy()
    p50 = table["budget_input"].to_numpy() * roas
    out["revenue_p10"] = p50 * 0.6
    out["revenue_p50"] = p50
    out["revenue_p90"] = p50 * 1.5
    return out


def test_in_distribution_is_untouched():
    table = _table()
    pred = _model_pred(table)
    out, info = scale_guard.run_guardrail(pred, table, {}, _profile())
    assert info["confidence"] == "High"
    assert not info["fallback_used"]
    assert out is pred  # bit-identical passthrough


def test_100x_scale_triggers_low_confidence_blend():
    table = _table(spend_per_campaign=700.0 * 100)
    # The classic failure: the model predicts near training-scale revenue for
    # 100x-scale spend -> absurdly low ROAS.
    pred = _model_pred(table, roas=0.03)
    out, info = scale_guard.run_guardrail(pred, table, {}, _profile())
    assert info["confidence"] == "Low"
    assert info["fallback_used"]
    assert info["model_weight"] == 0.25 and info["baseline_weight"] == 0.75
    assert info["warning"] == scale_guard.OOD_WARNING
    assert len(info["reasons"]) >= 2

    q = out[["revenue_p10", "revenue_p50", "revenue_p90"]].to_numpy()
    assert np.isfinite(q).all() and (q >= 0).all()
    assert (q[:, 0] <= q[:, 1]).all() and (q[:, 1] <= q[:, 2]).all()
    # Blended implied ROAS is pulled toward the trailing 4.0x, away from 0.03x.
    roas_p50 = q[:, 1] / out["budget_input"].to_numpy()
    assert (roas_p50 > 1.0).all()
    # Wider intervals than the model's own on OOD data.
    assert info["interval_widening"] > 1.0
    assert info["ood_score"] > 0.6


def test_zero_spend_is_safe():
    table = _table(spend_per_campaign=0.0)
    table["tr28_roas"] = 0.0
    table["tr14_roas"] = 0.0
    pred = _model_pred(table)
    base = scale_guard.baseline_forecast(table, {}, fallback_roas=1.0)
    assert np.isfinite(base).all() and (base >= 0).all()


def test_assessment_shape_and_report_roundtrip(tmp_path):
    a = scale_guard.assess(scale_guard.profile_from_table(
        _table(spend_per_campaign=70000.0)), _profile())
    assert set(a) == {"confidence", "ood_score", "reasons", "comparison"}
    assert 0.0 <= a["ood_score"] <= 1.0
    assert a["confidence"] in ("High", "Medium", "Low")
    json.dumps(a)  # must be JSON-serializable for the sidecar report
