"""Out-of-distribution (OOD) scale guardrail.

The trained model is calibrated on the official NetElixir dataset scale. An
external dataset that is ~100x larger per month is out of distribution: the
GBM's raw revenue predictions can no longer be trusted on their own, producing
absurd ROAS (e.g. 0.03x when trailing ROAS is 1.4x).

This module — pure numpy/pandas, no network, no LLM — provides:

  * ``build_training_profile``  — distribution metadata of the TRAINING data,
    saved as a JSON sidecar next to the pickle (never inside run.sh's model
    load path, so old pickles keep working).
  * ``assess``                  — compares uploaded data against the profile
    and returns ``{ood_score, confidence, reasons, comparison}``.
  * ``apply_guardrail``         — when confidence drops, blends the model's
    revenue quantiles with a trailing-ROAS baseline and widens the P10-P90
    interval to reflect the extra uncertainty. On in-distribution data the
    predictions pass through UNCHANGED, so official-scale behaviour is intact.

ROAS is never predicted here: it is always derived downstream by reconcile.py
as revenue / planned spend, so displayed ROAS stays consistent with revenue.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

PROFILE_VERSION = 1
PROFILE_FILENAME = "training_profile.json"

# Blend weights per confidence bucket: (model_weight, baseline_weight).
# High = in-distribution -> pure model, so official-scale output is unchanged.
BLEND_WEIGHTS = {
    "High": (1.0, 0.0),
    "Medium": (0.6, 0.4),
    "Low": (0.25, 0.75),
}

# A scale signal fires when the uploaded median exceeds 5x the training P90.
SCALE_TRIGGER = 5.0

OOD_WARNING = (
    "This dataset is outside the training scale used for calibration. "
    "Forecast confidence is low. ROAS estimates are blended with a historical "
    "ROAS baseline to avoid over-trusting the trained model."
)

_ROAS_CAP = 100.0
_EPS = 1e-9


def _quantiles(values) -> dict:
    v = np.asarray([x for x in np.asarray(values, dtype=float) if np.isfinite(x)])
    if v.size == 0:
        return {"p10": 0.0, "p50": 0.0, "p90": 0.0}
    return {
        "p10": float(np.quantile(v, 0.10)),
        "p50": float(np.quantile(v, 0.50)),
        "p90": float(np.quantile(v, 0.90)),
    }


# ---------------------------------------------------------------------------
# Profile builders — the same shape from either a long frame or feature table
# ---------------------------------------------------------------------------
def build_training_profile(long_df: pd.DataFrame) -> dict:
    """Distribution metadata of a unified long frame (train time or upload)."""
    d = long_df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["month"] = d["date"].dt.to_period("M").astype(str)

    monthly = d.groupby("month")[["spend", "revenue"]].sum()
    camp_month = d.groupby(["campaign", "month"])[["spend", "revenue"]].sum()
    camp_month = camp_month[camp_month["spend"] > 0]

    camp_tot = d.groupby("campaign")[["spend", "revenue"]].sum()
    camp_tot = camp_tot[camp_tot["spend"] > 0]
    roas = np.clip(camp_tot["revenue"] / camp_tot["spend"], 0.0, _ROAS_CAP)

    by_channel = {}
    for ch, cf in d.groupby("channel"):
        ch_month = cf.groupby("month")[["spend", "revenue"]].sum()
        spend, rev = float(cf["spend"].sum()), float(cf["revenue"].sum())
        by_channel[str(ch)] = {
            "monthly_spend": _quantiles(ch_month["spend"]),
            "monthly_revenue": _quantiles(ch_month["revenue"]),
            "roas": float(np.clip(rev / spend, 0.0, _ROAS_CAP)) if spend > 0 else 0.0,
        }

    return {
        "profile_version": PROFILE_VERSION,
        "date_min": str(d["date"].min().date()),
        "date_max": str(d["date"].max().date()),
        "channels": sorted(str(c) for c in d["channel"].unique()),
        "campaign_types": sorted(str(t) for t in d["campaign_type"].unique()),
        "n_campaigns": int(d["campaign"].nunique()),
        "monthly_spend": _quantiles(monthly["spend"]),
        "monthly_revenue": _quantiles(monthly["revenue"]),
        "campaign_monthly_spend": _quantiles(camp_month["spend"]),
        "campaign_monthly_revenue": _quantiles(camp_month["revenue"]),
        "roas": _quantiles(roas),
        "other_channel_share": float((d["channel"] == "other").mean()),
        "by_channel": by_channel,
    }


def profile_from_table(table: pd.DataFrame) -> dict:
    """Approximate the same profile from the prediction feature table (the
    only artifact predict.py has). Trailing 28-day sums are scaled to a
    30-day month; one row per campaign (window_days == smallest window)."""
    w = int(table["window_days"].min())
    t = table[table["window_days"] == w]
    k = 30.0 / 28.0  # tr28 -> monthly

    camp_spend = t["tr28_spend"].to_numpy(dtype=float) * k
    camp_rev = t["tr28_revenue"].to_numpy(dtype=float) * k
    active = camp_spend > 0
    roas = np.clip(
        np.divide(camp_rev, camp_spend, out=np.zeros_like(camp_rev),
                  where=camp_spend > 0),
        0.0, _ROAS_CAP,
    )

    return {
        "profile_version": PROFILE_VERSION,
        "channels": sorted(str(c) for c in t["channel"].unique()),
        "campaign_types": sorted(str(x) for x in t["campaign_type"].unique()),
        "n_campaigns": int(len(t)),
        "monthly_spend": {"p50": float(camp_spend.sum())},
        "monthly_revenue": {"p50": float(camp_rev.sum())},
        "campaign_monthly_spend": _quantiles(camp_spend[active]),
        "campaign_monthly_revenue": _quantiles(camp_rev[active]),
        "roas": _quantiles(roas[active]),
        "other_channel_share": float((t["channel"].astype(str) == "other").mean()),
    }


# ---------------------------------------------------------------------------
# Sidecar persistence
# ---------------------------------------------------------------------------
def profile_path_for_model(model_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(model_path)),
                        PROFILE_FILENAME)


def save_profile(profile: dict, model_path: str) -> str:
    path = profile_path_for_model(model_path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    return path


def load_profile(model_path: str, model=None) -> dict | None:
    """Sidecar JSON first, then an attribute pickled on the model. Missing
    profile -> None (guard disabled; caller logs it — never a crash)."""
    path = profile_path_for_model(model_path)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    prof = getattr(model, "training_profile_", None)
    return prof if isinstance(prof, dict) else None


# ---------------------------------------------------------------------------
# OOD assessment
# ---------------------------------------------------------------------------
def _ratio(up, train):
    up, train = float(up or 0.0), float(train or 0.0)
    if train <= 0:
        return float("inf") if up > 0 else 1.0
    return up / train


def _scale_signal(name, up_p50, train, weight, reasons, comparison):
    """Graded scale signal. Fires when the uploaded median is either

      * > 5x the training P90 (hard out-of-range), or
      * > 5x the training median AND above the training P90 (the whole upload
        sits beyond anything seen in training, even if the training P90 is
        inflated by seasonal peak months).

    Severity grows with the ratio — 100x is much worse than 6x.
    """
    r_p90 = _ratio(up_p50, train.get("p90"))
    r_p50 = _ratio(up_p50, train.get("p50"))
    comparison[name] = {
        "uploaded_p50": float(up_p50 or 0.0),
        "training_p50": float(train.get("p50", 0.0)),
        "training_p90": float(train.get("p90", 0.0)),
        "ratio_vs_training_median": round(r_p50, 2) if np.isfinite(r_p50) else None,
    }
    if r_p90 > SCALE_TRIGGER or (r_p50 > SCALE_TRIGGER and r_p90 > 1.0):
        severity = min(1.0, 0.5 + max(r_p90 / 25.0, r_p50 / 50.0))
        reasons.append(
            f"Uploaded {name.replace('_', ' ')} is {r_p50:,.1f}x higher than "
            "the training median"
        )
        return weight * severity
    return 0.0


def assess(upload_profile: dict, training_profile: dict,
           divergence: float | None = None) -> dict:
    """Compare an upload profile to the training profile.

    ``divergence`` (optional): total model-predicted P50 revenue divided by
    the trailing-ROAS baseline P50 — the direct symptom of scale failure. A
    healthy model tracks its own trailing baseline within ~3x either way.

    Returns ``{"confidence": High|Medium|Low, "ood_score": 0..1,
    "reasons": [...], "comparison": {...}}``.
    """
    reasons: list[str] = []
    comparison: dict = {}
    score = 0.0

    score += _scale_signal("monthly_revenue",
                           upload_profile.get("monthly_revenue", {}).get("p50"),
                           training_profile.get("monthly_revenue", {}),
                           0.25, reasons, comparison)
    score += _scale_signal("monthly_spend",
                           upload_profile.get("monthly_spend", {}).get("p50"),
                           training_profile.get("monthly_spend", {}),
                           0.25, reasons, comparison)
    score += _scale_signal("campaign_monthly_revenue",
                           upload_profile.get("campaign_monthly_revenue", {}).get("p50"),
                           training_profile.get("campaign_monthly_revenue", {}),
                           0.15, reasons, comparison)
    score += _scale_signal("campaign_monthly_spend",
                           upload_profile.get("campaign_monthly_spend", {}).get("p50"),
                           training_profile.get("campaign_monthly_spend", {}),
                           0.15, reasons, comparison)

    # ROAS far outside the training range (either direction).
    up_roas = float(upload_profile.get("roas", {}).get("p50", 0.0))
    tr_roas = training_profile.get("roas", {})
    lo = float(tr_roas.get("p10", 0.0)) / 3.0
    hi = float(tr_roas.get("p90", 0.0)) * 3.0
    comparison["roas_p50"] = {"uploaded": round(up_roas, 3),
                              "training_range_p10_p90": [tr_roas.get("p10"),
                                                         tr_roas.get("p90")]}
    if hi > 0 and up_roas > 0 and not (lo <= up_roas <= hi):
        score += 0.15
        reasons.append(
            f"Uploaded median campaign ROAS ({up_roas:.2f}x) is far outside "
            f"the training range ({tr_roas.get('p10', 0):.2f}x-"
            f"{tr_roas.get('p90', 0):.2f}x)"
        )

    # Too many unseen campaign types.
    trained_types = set(training_profile.get("campaign_types", []))
    up_types = set(upload_profile.get("campaign_types", []))
    unseen = sorted(up_types - trained_types)
    if trained_types and up_types:
        unseen_share = len(unseen) / len(up_types)
        comparison["unseen_campaign_types"] = unseen
        if unseen_share > 0.3:
            score += 0.10
            reasons.append(
                f"{len(unseen)}/{len(up_types)} campaign types were never "
                "seen in training"
            )

    # Too many rows falling into channel="other".
    other = float(upload_profile.get("other_channel_share", 0.0))
    comparison["other_channel_share"] = round(other, 3)
    if other > 0.20:
        score += 0.10
        reasons.append(
            f"{other:.0%} of rows could not be mapped to a known channel"
        )

    # Model-vs-baseline divergence: the trained model's total P50 revenue vs
    # the trailing-ROAS baseline. On in-distribution data these agree within
    # ~3x; a model predicting far BELOW its own trailing baseline is the
    # classic tree-extrapolation failure on out-of-scale inputs.
    if divergence is not None and np.isfinite(divergence) and divergence > 0:
        comparison["model_vs_baseline_p50"] = round(float(divergence), 4)
        if divergence < 1 / 3 or divergence > 3.0:
            gap = (1 / 3) / divergence if divergence < 1 else divergence / 3.0
            score += 0.40 * min(1.0, gap / 5.0)
            reasons.append(
                "Model P50 revenue diverges from the trailing-ROAS baseline "
                f"by {1 / divergence if divergence < 1 else divergence:,.1f}x "
                "— symptomatic of out-of-scale inputs"
            )

    score = float(min(1.0, score))
    confidence = "High" if score < 0.30 else ("Medium" if score < 0.60 else "Low")
    return {"confidence": confidence, "ood_score": round(score, 3),
            "reasons": reasons, "comparison": comparison}


# ---------------------------------------------------------------------------
# Scale-safe baseline + blending
# ---------------------------------------------------------------------------
def baseline_forecast(table: pd.DataFrame, seasonal_index: dict | None,
                      fallback_roas: float = 1.0) -> np.ndarray:
    """Trailing-ROAS baseline revenue quantiles, shape (n, 3).

    baseline_p50 = planned_spend x trailing ROAS x seasonal index. The trailing
    ROAS comes from the campaign's own 28-day history (14-day, then the
    channel aggregate, then ``fallback_roas`` as fallbacks). The P10/P90
    spread is a fixed +-45%/+65% band — deliberately wide; ``apply_guardrail``
    widens it further with the OOD score.
    """
    roas28 = table["tr28_roas"].to_numpy(dtype=float)
    roas14 = table["tr14_roas"].to_numpy(dtype=float)
    roas = np.where(roas28 > 0, roas28, roas14)

    # Channel-aggregate trailing ROAS for campaigns with no usable history.
    ch_rev = table.groupby("channel")["tr28_revenue"].transform("sum").to_numpy(dtype=float)
    ch_spd = table.groupby("channel")["tr28_spend"].transform("sum").to_numpy(dtype=float)
    ch_roas = np.divide(ch_rev, ch_spd, out=np.zeros_like(ch_rev), where=ch_spd > 0)
    roas = np.where(roas > 0, roas, ch_roas)
    roas = np.where(roas > 0, roas, float(fallback_roas))
    roas = np.clip(roas, 0.0, _ROAS_CAP)

    if seasonal_index:
        from . import features as F
        seas = F._window_seasonal(table, seasonal_index)
    else:
        seas = np.ones(len(table), dtype=float)

    budget = np.clip(table["budget_input"].to_numpy(dtype=float), 0.0, None)
    p50 = np.clip(roas * budget * seas, 0.0, None)
    return np.column_stack([p50 * 0.55, p50, p50 * 1.65])


def run_guardrail(model_pred: pd.DataFrame, table: pd.DataFrame,
                  seasonal_index: dict | None, training_profile: dict,
                  fallback_roas: float = 1.0) -> tuple[pd.DataFrame, dict]:
    """Full guardrail pass: baseline -> divergence -> assess -> blend.

    The single entry point used by both the scored pipeline (predict.py) and
    the product backend, so the two can never disagree.
    """
    base_q = baseline_forecast(table, seasonal_index, fallback_roas)
    model_total = float(model_pred["revenue_p50"].sum())
    base_total = float(base_q[:, 1].sum())
    divergence = model_total / base_total if base_total > 0 else None

    assessment = assess(profile_from_table(table), training_profile,
                        divergence=divergence)
    return apply_guardrail(model_pred, base_q, assessment)


def apply_guardrail(model_pred: pd.DataFrame, base_q: np.ndarray,
                    assessment: dict) -> tuple[pd.DataFrame, dict]:
    """Blend model quantiles with precomputed baseline quantiles according to
    confidence.

    High confidence returns ``model_pred`` untouched (bit-identical official
    output). Otherwise: blend each quantile, widen the interval by the OOD
    score, and enforce finite / non-negative / ordered quantiles. ROAS is NOT
    touched here — reconcile derives it as revenue / spend afterwards.
    """
    confidence = assessment.get("confidence", "High")
    w_model, w_base = BLEND_WEIGHTS.get(confidence, (1.0, 0.0))
    info = {
        "confidence": confidence,
        "ood_score": assessment.get("ood_score", 0.0),
        "reasons": assessment.get("reasons", []),
        "comparison": assessment.get("comparison", {}),
        "fallback_used": w_base > 0.0,
        "model_weight": w_model,
        "baseline_weight": w_base,
        "interval_widening": 1.0,
        "warning": OOD_WARNING if confidence == "Low" else None,
    }
    if w_base <= 0.0:
        return model_pred, info

    cols = ["revenue_p10", "revenue_p50", "revenue_p90"]
    model_q = model_pred[cols].to_numpy(dtype=float)
    blended = w_model * model_q + w_base * base_q

    # Widen P10-P90 around the blended P50 to reflect OOD uncertainty.
    widen = 1.0 + float(assessment.get("ood_score", 0.0))
    info["interval_widening"] = round(widen, 3)
    lo, mid, hi = blended[:, 0], blended[:, 1], blended[:, 2]
    lo = mid - widen * (mid - lo)
    hi = mid + widen * (hi - mid)
    blended = np.column_stack([lo, mid, hi])

    blended = np.nan_to_num(blended, nan=0.0, posinf=0.0, neginf=0.0)
    blended = np.sort(np.clip(blended, 0.0, None), axis=1)

    out = model_pred.copy()
    out[cols[0]], out[cols[1]], out[cols[2]] = (
        blended[:, 0], blended[:, 1], blended[:, 2])
    return out, info


def format_report(info: dict) -> str:
    """Human-readable summary block (printed by predict.py — never hidden)."""
    lines = [
        f"scale guard      : confidence={info['confidence']} "
        f"ood_score={info['ood_score']:.2f}",
        f"fallback used    : {'yes' if info['fallback_used'] else 'no'} "
        f"(model weight {info['model_weight']:.2f}, "
        f"baseline weight {info['baseline_weight']:.2f})",
    ]
    for r in info.get("reasons", []):
        lines.append(f"  reason: {r}")
    if info.get("warning"):
        lines.append(f"  WARNING: {info['warning']}")
    return "\n".join(lines)
