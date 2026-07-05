#!/usr/bin/env python
"""Offline HTML forecast report — P10-P90 range bars with a P50 marker.

Pure stdlib + pandas (no plotting libraries, no network, NOT part of run.sh).
Reads a finished predictions.csv and writes a self-contained HTML file with
inline SVG, so judges/analysts can eyeball the forecast without the product UI.

Run: ``python src/report.py --predictions ./output/predictions.csv \
        --out ./output/report.html``
"""
from __future__ import annotations

import argparse
import html
import os

import pandas as pd

CSS = """
body{font-family:Segoe UI,system-ui,sans-serif;margin:24px auto;max-width:980px;
     color:#1a2233;background:#fafbfc}
h1{font-size:22px} h2{font-size:16px;margin:28px 0 8px}
.small{color:#5a6b85;font-size:12px}
table{border-collapse:collapse;width:100%;font-size:13px}
td,th{padding:6px 8px;border-bottom:1px solid #e3e8ef;text-align:left}
.bar{background:#eef2f7;border-radius:4px}
"""


def _fmt_money(x):
    return f"${x:,.0f}"


def _svg_range(p10, p50, p90, vmax, width=420, h=22):
    """One horizontal P10-P90 range bar with a P50 tick."""
    if vmax <= 0:
        vmax = 1.0
    x10, x50, x90 = (v / vmax * (width - 8) + 4 for v in (p10, p50, p90))
    return (
        f'<svg width="{width}" height="{h}" class="bar">'
        f'<rect x="{x10:.1f}" y="6" width="{max(x90 - x10, 2):.1f}" height="10" '
        f'rx="5" fill="#7aa5d8"/>'
        f'<rect x="{x50 - 1.5:.1f}" y="2" width="3" height="18" fill="#1f4e8c"/>'
        f"</svg>"
    )


def _section(df, level, key_cols, vmax, title):
    rows_html = [f"<h2>{title}</h2>",
                 "<table><tr><th>entity</th><th>window</th>"
                 "<th>P10 – P90 revenue (P50 marker)</th>"
                 "<th>low / expected / high</th><th>ROAS range</th></tr>"]
    sub = df[df["level"] == level]
    for _, r in sub.iterrows():
        name = " / ".join(str(r[c]) for c in key_cols if str(r.get(c, "")) not in ("", "nan")) or "All channels"
        rng = _svg_range(r["revenue_p10"], r["revenue_p50"], r["revenue_p90"], vmax)
        rows_html.append(
            f"<tr><td>{html.escape(name)}</td><td>{int(r['window_days'])}d</td>"
            f"<td>{rng}</td>"
            f"<td class='small'>{_fmt_money(r['revenue_p10'])} / "
            f"<b>{_fmt_money(r['revenue_p50'])}</b> / {_fmt_money(r['revenue_p90'])}</td>"
            f"<td>{r['roas_p10']:.1f}x – <b>{r['roas_p50']:.1f}x</b> – {r['roas_p90']:.1f}x</td></tr>"
        )
    rows_html.append("</table>")
    return "\n".join(rows_html)


def build_report(pred_csv: str, out_html: str, top_campaigns: int = 15) -> None:
    df = pd.read_csv(pred_csv, keep_default_na=False)
    for c in ("revenue_p10", "revenue_p50", "revenue_p90",
              "roas_p10", "roas_p50", "roas_p90", "window_days"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    parts = [f"<style>{CSS}</style>",
             "<h1>ROAScast — probabilistic revenue &amp; ROAS forecast</h1>",
             "<p class='small'>Aggregate 30/60/90-day forecast ranges. "
             "Bars span P10 (low estimate) to P90 (high estimate); the dark tick "
             "is P50 (expected). Revenue in USD; ROAS is a multiple, never $.</p>"]

    vmax_blend = float(df[df["level"].isin(["blended", "channel"])]["revenue_p90"].max())
    parts.append(_section(df, "blended", [], vmax_blend, "Blended (all channels)"))
    parts.append(_section(df, "channel", ["channel"], vmax_blend, "By channel"))
    vmax_ct = float(df[df["level"] == "campaign_type"]["revenue_p90"].max() or 1.0)
    parts.append(_section(df, "campaign_type", ["channel", "campaign_type"],
                          vmax_ct, "By campaign type"))

    camp = df[df["level"] == "campaign"].sort_values("revenue_p50", ascending=False)
    keep = camp["campaign"].drop_duplicates().head(top_campaigns)
    camp = camp[camp["campaign"].isin(set(keep))]
    vmax_c = float(camp["revenue_p90"].max() or 1.0)
    dfc = df[df["level"].eq("campaign") & df["campaign"].isin(set(keep))]
    parts.append(_section(dfc, "campaign", ["channel", "campaign"], vmax_c,
                          f"Top {len(keep)} campaigns by expected revenue"))

    os.makedirs(os.path.dirname(os.path.abspath(out_html)) or ".", exist_ok=True)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"[report] wrote {out_html}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="HTML range-bar report from predictions.csv")
    ap.add_argument("--predictions", default="./output/predictions.csv")
    ap.add_argument("--out", default="./output/report.html")
    args = ap.parse_args(argv)
    build_report(args.predictions, args.out)


if __name__ == "__main__":
    main()
