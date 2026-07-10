"""Product-side wrapper around the SHARED forecasting core.

This module is the single bridge between the FastAPI product layer and
``src/forecasting`` — the exact same math that powers the scored ``run.sh``.
The product never re-implements the model; it imports it. That is the whole
point of the "two halves, one core" architecture: the demo and the scored
output can never disagree.

Nothing here makes a network call. The LLM lives in ``llm.py`` only.
"""
from __future__ import annotations

import io
import os
import sys

import joblib
import numpy as np
import pandas as pd

# --- make the shared core importable (repo_root/src) ------------------------
_THIS = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS, "..", "..", ".."))
_SRC = os.path.join(_REPO_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from forecasting import curves, features, mapping, reconcile, scale_guard, schema  # noqa: E402

DEFAULT_MODEL_PATH = os.path.join(_REPO_ROOT, "pickle", "model.pkl")


class ForecastService:
    """Loads the pickled model once and serves forecasts / simulations."""

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path or os.environ.get(
            "ROASCAST_MODEL_PATH", DEFAULT_MODEL_PATH
        )
        self.model = joblib.load(self.model_path)
        self.version = getattr(self.model, "version", "unknown")
        # Training-distribution profile for the OOD scale guard (sidecar JSON
        # next to the pickle; None disables the guard rather than crashing).
        self.training_profile = scale_guard.load_profile(self.model_path, self.model)

    # -- ingestion ----------------------------------------------------------
    @staticmethod
    def read_csv(raw_bytes: bytes, channel_hint: str | None = None) -> pd.DataFrame:
        """Bytes of one platform export -> unified long frame (never raises)."""
        df = pd.read_csv(io.BytesIO(raw_bytes))
        return mapping.to_long(df, channel_hint=channel_hint)

    @staticmethod
    def combine(long_frames: list[pd.DataFrame]) -> pd.DataFrame:
        frames = [f for f in long_frames if f is not None and len(f)]
        if not frames:
            return mapping.to_long(pd.DataFrame())
        return pd.concat(frames, ignore_index=True)

    # -- data summary (for the upload page) ---------------------------------
    @staticmethod
    def summarize(long_df: pd.DataFrame) -> dict:
        if long_df is None or long_df.empty:
            return {"rows": 0, "channels": [], "campaigns": 0,
                    "date_min": None, "date_max": None,
                    "total_spend": 0.0, "total_revenue": 0.0}
        d = long_df
        by_channel = (
            d.groupby("channel")
            .agg(spend=("spend", "sum"), revenue=("revenue", "sum"),
                 campaigns=("campaign", "nunique"))
            .reset_index()
        )
        return {
            "rows": int(len(d)),
            "campaigns": int(d["campaign"].nunique()),
            "channels": d["channel"].unique().tolist(),
            "date_min": str(d["date"].min().date()),
            "date_max": str(d["date"].max().date()),
            "total_spend": float(d["spend"].sum()),
            "total_revenue": float(d["revenue"].sum()),
            "currency": schema.CURRENCY,
            "by_channel": by_channel.to_dict(orient="records"),
        }

    # -- validation (campaign consistency) ----------------------------------
    def validate(self, long_df: pd.DataFrame) -> dict:
        """Campaign consistency report: mapping coverage, gaps, name drift,
        plus the OOD scale assessment vs the training distribution."""
        issues: list[dict] = []
        if long_df is None or long_df.empty:
            return {"ok": False, "issues": [
                {"severity": "error", "code": "no_data",
                 "message": "No parseable rows found in the uploaded files."}],
                "campaigns": []}

        d = long_df
        # 1) unmapped channels / types -> "Other" coverage
        other_ch = int((d["channel"] == "other").sum())
        if other_ch:
            issues.append({"severity": "warning", "code": "unmapped_channel",
                           "message": f"{other_ch} rows could not be mapped to a "
                                      "known channel (fell back to 'other')."})
        other_type = int((d["campaign_type"] == "Other").sum())
        if other_type:
            issues.append({"severity": "info", "code": "other_type",
                           "message": f"{other_type} rows mapped to campaign_type "
                                      "'Other' (name did not match a known pattern)."})

        # 2) per-campaign coverage / gaps
        rows = []
        for camp, cf in d.groupby("campaign"):
            ch = cf["channel"].mode().iloc[0]
            ctype = cf["campaign_type"].mode().iloc[0]
            span_days = (cf["date"].max() - cf["date"].min()).days + 1
            active = cf["date"].dt.normalize().nunique()
            coverage = active / span_days if span_days else 0.0
            if cf["channel"].nunique() > 1:
                issues.append({"severity": "warning", "code": "channel_drift",
                               "message": f"Campaign '{camp}' appears under multiple "
                                          "channels."})
            if coverage < 0.5 and span_days > 14:
                issues.append({"severity": "info", "code": "sparse_history",
                               "message": f"Campaign '{camp}' has sparse history "
                                          f"({active}/{span_days} active days)."})
            rows.append({
                "campaign": camp, "channel": ch, "campaign_type": ctype,
                "is_brand": int(cf["is_brand"].max()),
                "active_days": int(active), "span_days": int(span_days),
                "coverage": round(float(coverage), 3),
                "spend": float(cf["spend"].sum()),
                "revenue": float(cf["revenue"].sum()),
            })
        # 3) OOD scale assessment vs the training distribution
        scale = None
        if self.training_profile is not None:
            up_profile = scale_guard.build_training_profile(d)
            scale = scale_guard.assess(up_profile, self.training_profile)
            w_model, w_base = scale_guard.BLEND_WEIGHTS.get(
                scale["confidence"], (1.0, 0.0))
            scale["fallback_used"] = w_base > 0.0
            scale["model_weight"] = w_model
            scale["baseline_weight"] = w_base
            if scale["confidence"] == "Low":
                scale["warning"] = scale_guard.OOD_WARNING
            for reason in scale["reasons"]:
                issues.append({"severity": "warning", "code": "scale_mismatch",
                               "message": reason})

        has_error = any(i["severity"] == "error" for i in issues)
        return {"ok": not has_error, "issues": issues,
                "campaigns": sorted(rows, key=lambda r: -r["spend"]),
                "scale": scale}

    # -- forecast -----------------------------------------------------------
    def forecast(self, long_df: pd.DataFrame,
                 budget_overrides: dict | None = None) -> pd.DataFrame:
        """Full reconciled hierarchy for all windows -> schema-valid frame.

        ``budget_overrides`` (optional): ``{channel: total_budget_for_window}``
        scales each channel's per-window budget_input proportionally so the user
        can ask "what if I spend $X on Meta".
        """
        df, _ = self.forecast_with_guard(long_df, budget_overrides)
        return df

    def forecast_with_guard(self, long_df: pd.DataFrame,
                            budget_overrides: dict | None = None
                            ) -> tuple[pd.DataFrame, dict | None]:
        """Forecast plus the OOD scale-guard report (None if no profile).

        Same guardrail as the scored pipeline: on in-distribution data the
        model output passes through untouched; on out-of-scale data the
        revenue quantiles are blended with a trailing-ROAS baseline and the
        interval is widened. ROAS always = revenue / planned spend.
        """
        table = features.build_prediction_table(long_df)
        if budget_overrides:
            table = self._apply_budget_overrides(table, budget_overrides)
        campaign_pred = self.model.predict(table)
        guard_info = None
        if self.training_profile is not None:
            campaign_pred, guard_info = scale_guard.run_guardrail(
                campaign_pred, table,
                getattr(self.model, "seasonal_index_", {}),
                self.training_profile,
                getattr(self.model, "fallback_", {}).get("global_median_roas", 1.0))
        full = reconcile.reconcile(campaign_pred)
        return schema.validate_output(full), guard_info

    @staticmethod
    def _apply_budget_overrides(table: pd.DataFrame, overrides: dict) -> pd.DataFrame:
        t = table.copy()
        for window, wf in t.groupby("window_days"):
            for channel, target in overrides.items():
                mask = (t["window_days"] == window) & (t["channel"] == channel)
                cur = float(t.loc[mask, "budget_input"].sum())
                if cur > 0 and target is not None:
                    scale = float(target) / cur
                    t.loc[mask, "budget_input"] *= scale
        return t

    # -- budget simulation (curve-only, fast) -------------------------------
    def simulate(self, long_df: pd.DataFrame, scenario: dict) -> dict:
        """Per-channel response-curve revenue/ROAS for a budget scenario.

        Refits per-channel saturating Hill curves on the uploaded history and
        evaluates them at the requested budgets — diminishing returns visible.
        """
        channel_curves = curves.fit_channel_curves(long_df)
        out = []
        total_rev = total_spend = 0.0
        for channel, budget in scenario.items():
            budget = float(budget)
            rev = float(curves.simulate(channel_curves, channel, budget))
            roas = rev / budget if budget > 0 else 0.0
            # marginal ROAS: revenue gain per extra $1k, shows saturation
            rev_more = float(curves.simulate(channel_curves, channel, budget + 1000.0))
            marginal_roas = (rev_more - rev) / 1000.0 if budget > 0 else 0.0
            out.append({"channel": channel, "budget": budget,
                        "revenue": rev, "roas": roas,
                        "marginal_roas": marginal_roas})
            total_rev += rev
            total_spend += budget
        return {
            "currency": schema.CURRENCY,
            "channels": out,
            "blended": {"budget": total_spend, "revenue": total_rev,
                        "roas": (total_rev / total_spend) if total_spend else 0.0},
        }

    def curve_points(self, long_df: pd.DataFrame, n: int = 30) -> dict:
        """Sampled (spend, revenue) points per channel for plotting the curve."""
        channel_curves = curves.fit_channel_curves(long_df)
        result = {}
        for channel in long_df["channel"].unique():
            cf = long_df[long_df["channel"] == channel]
            daily = cf.groupby(cf["date"].dt.normalize())["spend"].sum()
            typ_window = float(daily.mean() * 30) if len(daily) else 1000.0
            hi = max(typ_window * 2.5, 1000.0)
            xs = np.linspace(0, hi, n)
            ys = [float(curves.simulate(channel_curves, channel, x)) for x in xs]
            result[channel] = [{"spend": float(x), "revenue": y}
                               for x, y in zip(xs, ys)]
        return result

    # -- feature drivers (for grounded LLM context) -------------------------
    def drivers(self, top: int = 8) -> list[dict]:
        """Top LightGBM feature importances from the P50 booster."""
        try:
            booster = self.model._booster(0.5)
            names = self.model.feature_columns_
            gains = booster.feature_importance(importance_type="gain")
            order = np.argsort(gains)[::-1][:top]
            tot = float(gains.sum()) or 1.0
            return [{"feature": names[i], "importance": round(float(gains[i]) / tot, 4)}
                    for i in order]
        except Exception:
            return []
