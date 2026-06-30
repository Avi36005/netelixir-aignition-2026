"""ForecastModel — the fitted forecasting core.

Holds ONLY fitted state (LightGBM model strings, fitted curve params, learned
seasonal indices, the exact feature-column order, fallback stats, a version
stamp). All logic stays as code in this package, which travels with the clone,
so the pickle is small and the class is importable at unpickle time.

Serialization detail that matters for the cold grader: we store LightGBM *model
strings* (``model_to_string``), not live ``Booster`` objects. Text model dumps
are far more portable across library patch versions — pickle version mismatch is
the single most common reason hackathon submissions fail to load. The predict
path rebuilds boosters from those strings and never imports scikit-learn.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import lightgbm as lgb

from . import curves as C
from . import features as F

MODEL_VERSION = "roascast-1.0.0"
QUANTILES = (0.1, 0.5, 0.9)
_REV_COLS = ["revenue_p10", "revenue_p50", "revenue_p90"]


class ForecastModel:
    """Train three quantile regressors (P10/P50/P90) for revenue; derive ROAS."""

    def __init__(self):
        self.feature_columns_ = None
        self.seasonal_index_ = {}
        self.curves_ = {}
        self.booster_strings_ = {}  # {alpha: model_to_string()}
        self.fallback_ = {}
        self.calib_factor_ = 1.0  # interval-width multiplier around P50 (1.0 = none)
        self.target_coverage_ = 0.8
        self.version = MODEL_VERSION
        self._booster_cache = {}

    # ------------------------------------------------------------------ train
    def train(self, raw_df, targets, seasonal_index, channel_curves,
              raw_calib=None, seed=42, params=None, target_coverage=0.8):
        """Fit P10/P50/P90 quantile LightGBM models on the design matrix.

        Note on monotonicity: LightGBM rejects ``monotone_constraints`` under the
        quantile objective, so the "revenue rises with budget" guarantee is
        enforced structurally by the saturating curves and the isotonic budget
        sweep (see ``predict_budget_sweep`` / ``curves.py``), not by a GBM
        constraint. ``budget_input`` remains a strong (index-0) feature here.

        Interval calibration: if ``raw_calib`` (the extrapolated-budget twin of
        ``raw_df``) is supplied, we run a time-based split + normalized split-
        conformal step to learn a single width adjustment so out-of-sample
        coverage approaches ``target_coverage``. The point forecast (P50) is
        never altered — only the interval width.
        """
        self.seasonal_index_ = dict(seasonal_index)
        self.curves_ = dict(channel_curves)
        self.target_coverage_ = float(target_coverage)

        x, cols = F.build_design_matrix(raw_df, self.seasonal_index_)
        self.feature_columns_ = cols
        y = np.asarray(targets, dtype=float)

        base = dict(
            n_estimators=400,
            num_leaves=31,
            learning_rate=0.05,
            min_child_samples=20,
            subsample=0.9,
            subsample_freq=1,
            colsample_bytree=0.9,
            reg_lambda=1.0,
            min_split_gain=0.0,
            random_state=seed,
            deterministic=True,
            force_row_wise=True,
            n_jobs=1,
            verbose=-1,
        )
        if params:
            base.update(params)

        self.calib_factor_ = self._calibrate(
            x, y, raw_calib, base, target_coverage
        )

        # Final models: fit on ALL the data (use every sample we have).
        self.booster_strings_ = {}
        for alpha in QUANTILES:
            reg = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **base)
            reg.fit(x, y)
            self.booster_strings_[alpha] = reg.booster_.model_to_string()

        budget = np.clip(raw_df["budget_input"].to_numpy(dtype=float), 1e-9, None)
        self.fallback_ = {
            "global_median_roas": float(np.median(np.clip(y / budget, 0.0, 100.0))),
        }
        self._booster_cache = {}
        return self

    def _calibrate(self, x, y, raw_calib, base, target_coverage):
        """Width multiplier ``f`` (around P50) that hits ~target coverage.

        We split the training rows by time (earliest 80% fit / latest 20%
        calibrate — the recent slice is the best proxy for the forecast horizon),
        fit on the realized-budget design matrix, then evaluate on the
        extrapolated-budget calibration rows and binary-search the single factor
        ``f`` so that ~target_coverage of actuals fall inside the scaled interval.

        ``f`` scales each side's distance from the median (``f=1`` leaves the
        interval untouched). Coverage is monotone in ``f``, so the search is
        stable — unlike a normalized-conformal score whose near-zero denominator
        can explode. Returns ``1.0`` (no change) when data is too thin.
        """
        if raw_calib is None or len(y) < 40:
            return 1.0
        ws = pd.to_datetime(raw_calib["window_start"]).astype("int64").to_numpy()
        cutoff = np.quantile(ws, 0.8)
        fit_mask = ws <= cutoff
        cal_mask = ~fit_mask
        if cal_mask.sum() < 10 or fit_mask.sum() < 20:
            return 1.0

        regs = {
            a: lgb.LGBMRegressor(objective="quantile", alpha=a, **base).fit(
                x[fit_mask], y[fit_mask]
            )
            for a in QUANTILES
        }
        xc, _ = F.build_design_matrix(raw_calib, self.seasonal_index_, self.feature_columns_)
        xc, yc = xc[cal_mask], y[cal_mask]
        preds = np.sort(
            np.clip(np.column_stack([regs[a].predict(xc) for a in QUANTILES]), 0.0, None),
            axis=1,
        )
        lo, mid, hi = preds[:, 0], preds[:, 1], preds[:, 2]

        def coverage(f):
            low = mid - f * (mid - lo)
            high = mid + f * (hi - mid)
            return float(np.mean((yc >= low) & (yc <= high)))

        f_hi = 8.0
        if coverage(f_hi) < target_coverage:
            return f_hi
        f_lo = 1.0
        for _ in range(40):
            mid_f = 0.5 * (f_lo + f_hi)
            if coverage(mid_f) >= target_coverage:
                f_hi = mid_f
            else:
                f_lo = mid_f
        return float(f_hi)

    # ------------------------------------------------------------- inference
    def _booster(self, alpha):
        if alpha not in self._booster_cache:
            self._booster_cache[alpha] = lgb.Booster(
                model_str=self.booster_strings_[alpha]
            )
        return self._booster_cache[alpha]

    def predict(self, raw_df):
        """Return ``raw_df`` (copy) with ``revenue_p10/p50/p90`` added.

        Guarantees: one row out per row in, ``P10 <= P50 <= P90`` (crossing
        fixed), revenue ``>= 0``, and a documented fallback for any non-finite
        prediction (we never silently drop an entity the grader expects).
        """
        x, _ = F.build_design_matrix(raw_df, self.seasonal_index_, self.feature_columns_)
        preds = np.column_stack([self._booster(a).predict(x) for a in QUANTILES])
        preds = np.clip(preds, 0.0, None)
        preds = np.sort(preds, axis=1)  # fix quantile crossing row-wise

        # Interval calibration — scale each side's distance from P50 by the
        # learned multiplier (scale-free across the campaign-to-blended magnitude
        # range). The point forecast P50 is left untouched.
        f = getattr(self, "calib_factor_", 1.0)
        if f and f != 1.0:
            lo, mid, hi = preds[:, 0], preds[:, 1], preds[:, 2]
            lo = mid - f * (mid - lo)
            hi = mid + f * (hi - mid)
            preds = np.sort(np.clip(np.column_stack([lo, mid, hi]), 0.0, None), axis=1)

        out = raw_df.copy()
        bad = ~np.isfinite(preds).all(axis=1)
        if bad.any():
            roas = self.fallback_.get("global_median_roas", 1.0)
            fb = np.clip(raw_df["budget_input"].to_numpy(dtype=float) * roas, 0.0, None)
            for j, scale in enumerate((0.6, 1.0, 1.5)):
                preds[bad, j] = fb[bad] * scale
            preds = np.sort(np.clip(preds, 0.0, None), axis=1)

        out[_REV_COLS[0]] = preds[:, 0]
        out[_REV_COLS[1]] = preds[:, 1]
        out[_REV_COLS[2]] = preds[:, 2]
        return out

    # --------------------------------------------- budget simulator (product)
    def simulate_budget(self, channel, budgets):
        """Curve-only revenue at given budgets — fast, monotone by construction.
        Powers the budget what-if slider in the product layer."""
        return C.simulate(self.curves_, channel, budgets)

    def predict_budget_sweep(self, raw_row, budgets):
        """Sweep ``budget_input`` for one entity through the full GBM and enforce
        monotone non-decreasing revenue (isotonic cumulative-max). This is the
        operational guarantee that "more budget never predicts less revenue"
        despite the GBM lacking a hard monotone constraint under quantile loss."""
        budgets = np.sort(np.asarray(budgets, dtype=float))
        rows = pd.concat([raw_row.to_frame().T] * len(budgets), ignore_index=True)
        rows["budget_input"] = budgets
        preds = self.predict(rows)[_REV_COLS].to_numpy()
        preds = np.maximum.accumulate(preds, axis=0)
        return budgets, preds

    # --------------------------------------------------- portable (un)pickling
    def __getstate__(self):
        state = self.__dict__.copy()
        state["_booster_cache"] = {}  # never pickle live boosters
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._booster_cache = {}
