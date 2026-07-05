"""Channel + campaign-type normalization for Google and Meta ad exports.

Turns heterogeneous platform CSVs into one tidy long frame the feature layer
understands.

HARD RULE: never raise on unfamiliar input. The held-out test set will contain
naming, casing, and possibly columns we have not seen. Every unknown falls into
a safe default bucket ("other" / "Other") instead of crashing the run.

Microsoft Ads is recognized defensively (the brief mentions MS Ads) even though
our committed sample data is Google + Meta only — if a Microsoft-shaped file
appears at test time it maps cleanly instead of erroring.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

# Canonical vocabularies — FIXED so the model's one-hot columns are stable across
# training and an unseen test set. Adding a value here is the only place to grow
# the category space.
CHANNELS = ("google", "meta", "microsoft", "other")

CAMPAIGN_TYPES = (
    # Google-native (carried explicitly in the export)
    "Search",
    "Shopping",
    "PerformanceMax",
    "Display",
    "Video",
    "DemandGen",
    # Meta-derived (parsed from the campaign name)
    "Prospecting",
    "Retargeting",
    "Brand",
    "DPA",
    # catch-all
    "Other",
)

# Unified long-format columns produced by ``to_long``.
LONG_COLUMNS = [
    "date",
    "channel",
    "campaign",
    "campaign_type",
    "is_brand",
    "impressions",
    "clicks",
    "spend",
    "conversions",
    "revenue",
    "daily_budget",
]

# ---------------------------------------------------------------------------
# Column alias resolution — case / space / underscore insensitive, first wins.
# Lets minor schema drift in the test set resolve without code changes.
# ---------------------------------------------------------------------------
_ALIASES = {
    "date": [
        "date",
        "day",
        # official AIgnition exports: Google API / Bing API / Meta API naming
        "segments_date",       # google_ads_campaign_stats.csv
        "timeperiod",          # bing_campaign_stats.csv (TimePeriod)
        "time_period",
        "date_start",          # meta_ads_campaign_stats.csv
        "reporting_starts",
        "reporting_date",
    ],
    "campaign": ["campaign_name", "campaign", "campaignname"],
    "campaign_type": [
        "campaign_type",
        "campaigntype",                        # Bing: CampaignType
        "campaign_advertising_channel_type",   # Google API export
        "advertising_channel_type",
        "campaign_subtype",
        "objective",
    ],
    "adset": ["adset_name", "ad_set_name", "adgroup_name", "ad_group_name"],
    "impressions": ["impressions", "metrics_impressions", "impr"],
    "clicks": ["clicks", "metrics_clicks", "link_clicks", "all_clicks", "clicks_all"],
    # NOTE: *_micros sources are auto-divided by 1e6 in ``to_long`` (see _MICROS).
    "spend": [
        "spend",
        "metrics_cost_micros",  # Google API export — micro-currency units
        "cost",
        "cost_micros",
        "amount_spent",
        "amount_spent_usd",
        "cost_usd",
    ],
    "conversions": [
        "conversions",
        "metrics_conversions",  # Google API export
        "purchases",
        "results",
        "website_purchases",
        "total_conversions",
        "all_conversions",
        "conv",
        # DELIBERATELY EXCLUDED: meta's singular "conversion" column is
        # value-like (revenue), NOT a count — see the revenue aliases.
    ],
    "revenue": [
        # Google UI exports say "Conv. value"; Meta says "Purchases conversion value".
        "metrics_conversions_value",  # Google API export
        "conversion_value",
        "conv_value",
        "conv_val",
        "all_conv_value",
        "purchase_conversion_value",
        "purchases_conversion_value",
        "conversions_value",
        "purchase_value",
        "revenue",
        "total_conversion_value",
        "website_purchases_conversion_value",
        # LAST on purpose: meta's "conversion" column carries conversion VALUE
        # (revenue-like), so it maps to revenue only when nothing better exists.
        "conversion",
    ],
    "budget": [
        "campaign_budget_amount",  # Google
        "dailybudget",             # Bing: DailyBudget
        "daily_budget",            # Meta
        "budget",
    ],
    "channel": ["channel", "platform", "source", "publisher_platform"],
}

# Spend sources carrying micro-currency units (Google Ads API cost_micros).
_MICROS_TOKEN = "micros"

_BRAND_TOKENS = ("brand", "branded", "trademark")
_DPA_TOKENS = ("dpa", "catalog", "advantage_catalog", "product_set", "asc")
_RETARGET_TOKENS = (
    "retarget",
    "remarket",
    "rmkt",
    "rtg",
    "mof",
    "bof",
    "warm",
    "abandon",
    "cart",
    "purchasers",
    "site_visitors",
    "engaged",
    "lookback",
)
_PROSPECT_TOKENS = (
    "prospect",
    "tof",
    "cold",
    "acquisition",
    "broad",
    "interest",
    "lookalike",
    "lal",
    "new_user",
)

# Google's advertising_channel_type / campaign_type strings -> canonical bucket.
_GOOGLE_TYPE_MAP = {
    "search": "Search",
    "shopping": "Shopping",
    "performance_max": "PerformanceMax",
    "performancemax": "PerformanceMax",
    "pmax": "PerformanceMax",
    "display": "Display",
    "video": "Video",
    "youtube": "Video",
    "demand_gen": "DemandGen",
    "demandgen": "DemandGen",
    "discovery": "DemandGen",
    # Microsoft/Bing-specific labels
    "audience": "Display",
    "hotel": "Other",
    "smart": "Search",
    "dynamicsearchads": "Search",
    "dynamic_search": "Search",
}


def _norm(s) -> str:
    """Lower-case, collapse non-alphanumerics to single underscores."""
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def _resolve(columns, field):
    """Return the actual column name in ``columns`` matching ``field``, or None."""
    norm_map = {_norm(c): c for c in columns}
    for alias in _ALIASES[field]:
        if _norm(alias) in norm_map:
            return norm_map[_norm(alias)]
    return None


def normalize_channel(raw) -> str:
    s = _norm(raw)
    if not s:
        return "other"
    if "google" in s or s in ("g", "gads", "googleads", "adwords"):
        return "google"
    if "meta" in s or "facebook" in s or "fb" in s or "instagram" in s or s == "ig":
        return "meta"
    if "microsoft" in s or "bing" in s or "msft" in s:
        return "microsoft"
    return "other"


def infer_channel_from_filename(path) -> str | None:
    """Channel from the FILE NAME — the strongest signal for the official set.

    google_ads_campaign_stats.csv -> google
    bing_campaign_stats.csv       -> microsoft
    meta_ads_campaign_stats.csv   -> meta
    """
    name = _norm(str(path).replace("\\", "/").rsplit("/", 1)[-1])
    if "google" in name or "adwords" in name:
        return "google"
    if "bing" in name or "microsoft" in name or "msads" in name:
        return "microsoft"
    if "meta" in name or "facebook" in name or "instagram" in name:
        return "meta"
    return None


def detect_channel(columns, explicit_value=None) -> str:
    """Best-effort channel from an explicit value or the column signature."""
    if explicit_value is not None:
        return normalize_channel(explicit_value)
    cols = {_norm(c) for c in columns}
    # Official API-export signatures first (exact, unambiguous).
    if any(c.startswith("metrics_") or c == "segments_date" for c in cols):
        return "google"
    if "timeperiod" in cols or "time_period" in cols:
        return "microsoft"
    if "date_start" in cols and ("cpm" in cols or "reach" in cols or "daily_budget" in cols):
        return "meta"
    if any("purchase" in c for c in cols) or "adset_name" in cols or "ad_set_name" in cols:
        return "meta"
    if any("microsoft" in c or c == "bing" for c in cols):
        return "microsoft"
    if "cost" in cols or "conversion_value" in cols or "advertising_channel_type" in cols:
        return "google"
    return "other"


def normalize_campaign_type(channel, raw_type=None, campaign_name="", adset_name="") -> str:
    """Canonical campaign_type.

    Google carries the type explicitly -> trust the column (fall back to the name
    only if the column is blank/unknown). Meta (and microsoft/other) have no type
    column -> parse it from the campaign + adset name string.
    """
    nb = _norm(f"{campaign_name} {adset_name}")
    # Google and Microsoft both carry an explicit campaign-type column -> trust it.
    if channel in ("google", "microsoft"):
        t = _norm(raw_type)
        for key, val in _GOOGLE_TYPE_MAP.items():
            if key in t:
                return val
        for key, val in _GOOGLE_TYPE_MAP.items():  # name fallback
            if key in nb:
                return val
        return "Other"
    # Meta / other: derive from the name. Order matters (DPA before Retargeting
    # because catalog campaigns are often also retargeting).
    if any(tok in nb for tok in _DPA_TOKENS):
        return "DPA"
    if any(tok in nb for tok in _BRAND_TOKENS):
        return "Brand"
    if any(tok in nb for tok in _RETARGET_TOKENS):
        return "Retargeting"
    if any(tok in nb for tok in _PROSPECT_TOKENS):
        return "Prospecting"
    return "Other"


def is_brand_campaign(campaign_name="", adset_name="") -> int:
    nb = _norm(f"{campaign_name} {adset_name}")
    return int(any(tok in nb for tok in _BRAND_TOKENS))


def has_revenue_column(columns) -> bool:
    """True if this raw export carries any recognized revenue-like column."""
    return _resolve(list(columns), "revenue") is not None


def to_long(df_raw: pd.DataFrame, channel_hint=None) -> pd.DataFrame:
    """Map one raw platform export into the unified long schema.

    Tolerant of missing columns and unknown channels; fills safe defaults; never
    raises. Rows without a parseable date are dropped (they cannot be placed on
    the time axis).

    ``channel_hint`` (e.g. from the file name) beats column-signature detection
    but loses to an explicit per-row channel column.
    """
    if df_raw is None or len(df_raw) == 0:
        return pd.DataFrame(columns=LONG_COLUMNS)

    cols = list(df_raw.columns)
    n = len(df_raw)

    # Channel may be a per-row column, or inferred once for the whole file.
    ch_col = _resolve(cols, "channel")
    if ch_col is not None:
        channel_series = df_raw[ch_col].map(normalize_channel)
    else:
        channel_series = pd.Series([detect_channel(cols, channel_hint)] * n)

    date_col = _resolve(cols, "date")
    camp_col = _resolve(cols, "campaign")
    type_col = _resolve(cols, "campaign_type")
    adset_col = _resolve(cols, "adset")

    out = pd.DataFrame(index=df_raw.index)
    out["date"] = (
        pd.to_datetime(df_raw[date_col], errors="coerce") if date_col else pd.NaT
    )
    out["channel"] = channel_series.values
    out["campaign"] = (
        df_raw[camp_col].astype(str) if camp_col else "unknown_campaign"
    )

    adset = (
        df_raw[adset_col].astype(str)
        if adset_col is not None
        else pd.Series([""] * n, index=df_raw.index)
    )
    raw_type = (
        df_raw[type_col].astype(str)
        if type_col is not None
        else pd.Series([""] * n, index=df_raw.index)
    )

    for field in ("impressions", "clicks", "spend", "conversions", "revenue"):
        src = _resolve(cols, field)
        vals = pd.to_numeric(df_raw[src], errors="coerce") if src else 0.0
        series = np.clip(pd.Series(vals, index=df_raw.index).fillna(0.0), 0.0, None)
        # Google Ads API reports cost in micro-currency units -> real currency.
        if field == "spend" and src is not None and _MICROS_TOKEN in _norm(src):
            series = series / 1_000_000.0
        out[field] = series

    # Optional daily-budget attribute (carried for the product layer; the model
    # derives its own budget_input from trailing spend).
    bud_col = _resolve(cols, "budget")
    if bud_col is not None:
        out["daily_budget"] = np.clip(
            pd.to_numeric(df_raw[bud_col], errors="coerce").fillna(0.0), 0.0, None
        )
    else:
        out["daily_budget"] = 0.0

    out["campaign_type"] = [
        normalize_campaign_type(ch, rt, cn, an)
        for ch, rt, cn, an in zip(out["channel"], raw_type, out["campaign"], adset)
    ]
    out["is_brand"] = [
        1 if bt == "Brand" else is_brand_campaign(cn, an)
        for bt, cn, an in zip(out["campaign_type"], out["campaign"], adset)
    ]

    out = out.dropna(subset=["date"]).reset_index(drop=True)
    return out[LONG_COLUMNS]
