"""Per-channel saturating budget -> revenue response curves (Hill).

Deliberately INDEPENDENT per channel: this is NOT a media-mix model. There is no
joint cross-channel adstock or decomposition — each channel gets its own curve.
That keeps us safely inside the brief's scope ("per-channel response curves are
fine; a full MMM is out of scope").

Each curve makes diminishing returns explicit and powers the budget what-if
simulator. It is monotone increasing in spend BY CONSTRUCTION, which is how we
guarantee "revenue cannot fall as budget rises" for budget sweeps — LightGBM
forbids monotone_constraints under the quantile objective, so the structural
monotonicity guarantee lives here in the curves.

Fitted with pure NumPy (grid-search on the saturation point, closed-form scale)
so we add no scipy.optimize dependency to the scored core.
"""
from __future__ import annotations

import numpy as np

_EPS = 1e-9


class HillCurve:
    """``revenue = vmax * spend / (k + spend)`` — monotone increasing, saturating.

    ``vmax`` is the revenue ceiling; ``k`` is the spend at which half of vmax is
    reached (the saturation half-point).
    """

    def __init__(self, vmax: float, k: float):
        self.vmax = float(vmax)
        self.k = float(max(k, _EPS))

    def predict(self, spend):
        s = np.clip(np.asarray(spend, dtype=float), 0.0, None)
        return self.vmax * s / (self.k + s + _EPS)

    def as_tuple(self):
        return (self.vmax, self.k)


def fit_hill(spend, revenue) -> HillCurve:
    """Fit Hill parameters with NumPy only.

    For a fixed ``k`` the model is linear in ``vmax`` (no intercept), so vmax has
    a closed form; we grid-search ``k`` over the observed spend range and keep the
    least-squares best. Degenerate/tiny data falls back to a near-linear curve
    using the realized blended ROAS.
    """
    s = np.asarray(spend, dtype=float)
    r = np.asarray(revenue, dtype=float)
    mask = np.isfinite(s) & np.isfinite(r) & (s >= 0) & (r >= 0)
    s, r = s[mask], r[mask]

    def _linear_fallback():
        roas = (r.sum() / s.sum()) if s.sum() > 0 else 1.0
        k = max(s.max() * 10.0, 1.0) if s.size and s.max() > 0 else 1.0
        return HillCurve(vmax=roas * k, k=k)  # large k => near-linear in range

    if s.size < 5 or s.max() <= 0 or r.max() <= 0:
        return _linear_fallback()

    smax = float(s.max())
    ks = np.linspace(smax * 0.05, smax * 5.0, 60)
    best = None
    for k in ks:
        x = s / (k + s + _EPS)            # transformed feature in [0, 1)
        denom = float((x * x).sum())
        if denom <= 0:
            continue
        vmax = float((x * r).sum() / denom)
        if vmax <= 0:
            continue
        sse = float(((vmax * x - r) ** 2).sum())
        if best is None or sse < best[0]:
            best = (sse, vmax, k)

    if best is None:
        return _linear_fallback()
    return HillCurve(vmax=best[1], k=best[2])


def fit_channel_curves(long_df) -> dict:
    """Fit one Hill curve per channel on daily ``(spend, revenue)`` aggregates.

    Returns ``{channel: (vmax, k)}`` (plain tuples so it pickles trivially).
    """
    curves = {}
    daily = (
        long_df.groupby(["channel", "date"], as_index=False)[["spend", "revenue"]].sum()
    )
    for ch, g in daily.groupby("channel"):
        curves[str(ch)] = fit_hill(g["spend"].to_numpy(), g["revenue"].to_numpy()).as_tuple()
    return curves


def simulate(curves: dict, channel, budget):
    """Evaluate revenue at ``budget`` for ``channel`` using the fitted curve.

    Unknown channel -> average of the known curves (defensive), so a never-seen
    channel still produces a sensible, monotone response instead of crashing.
    """
    params = curves.get(channel) if curves else None
    if params is None:
        if curves:
            vmax = float(np.mean([v for v, _ in curves.values()]))
            k = float(np.mean([k for _, k in curves.values()]))
        else:
            vmax, k = 1.0, 1.0
    else:
        vmax, k = params
    return HillCurve(vmax, k).predict(budget)
