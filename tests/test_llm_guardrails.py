"""No-hallucination guardrail tests for the AI Media Planner layer.

These test the PRODUCT layer only (product/backend/app/llm.py) — the scored
pipeline never imports it (test_pipeline.py::test_run_sh_end_to_end proves
run.sh works with no LLM at all).

Run: python -m pytest tests/test_llm_guardrails.py -q
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "product", "backend"))

from app import llm  # noqa: E402


def _ctx():
    rows = []
    for ch, rev, roas in (("google", 100000.0, 4.5), ("meta", 20000.0, 5.6),
                          ("microsoft", 3000.0, 4.9)):
        rows.append({"level": "channel", "channel": ch, "campaign_type": "",
                     "campaign": "", "window_days": 30,
                     "revenue_p10": rev * 0.4, "revenue_p50": rev,
                     "revenue_p90": rev * 2.5, "roas_p10": roas * 0.4,
                     "roas_p50": roas, "roas_p90": roas * 2.5})
    rows.append({"level": "blended", "channel": "", "campaign_type": "",
                 "campaign": "", "window_days": 30,
                 "revenue_p10": 49200.0, "revenue_p50": 123000.0,
                 "revenue_p90": 307500.0, "roas_p10": 1.85,
                 "roas_p50": 4.63, "roas_p90": 11.57})
    rows.append({"level": "campaign", "channel": "google",
                 "campaign_type": "Search", "campaign": "Search_Brand_01",
                 "window_days": 30, "revenue_p10": 8000.0,
                 "revenue_p50": 20000.0, "revenue_p90": 50000.0,
                 "roas_p10": 2.0, "roas_p50": 5.0, "roas_p90": 12.5})
    return llm.build_context(rows, [{"feature": "tr28_revenue", "importance": 0.3}], 30)


def _valid_item(claim="Google is forecast to contribute $100,000 expected revenue (P50)."):
    return {"forecast_summary": [
        {"claim": claim, "evidence": ["channels[google].revenue_p50"],
         "confidence": "high"}]}


def test_1_no_providers_uses_deterministic_fallback(monkeypatch):
    for name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm, "_try_ollama", lambda ctx: None)  # ignore local Ollama
    res = llm.explain(_ctx())
    assert res["provider"] == "template"
    assert res["guardrail"] == "fallback"
    assert res["insights"]["forecast_summary"], "fallback must still produce insights"
    assert res["insights"]["suggested_budget_shift"] is not None


def test_2_invented_number_rejected():
    bad = _valid_item(claim="Revenue will reach exactly $9,999,123 next month.")
    log = []
    assert llm.validate_insights(bad, _ctx(), log) is None
    assert any("number" in m for m in log)


def test_3_unsupported_campaign_rejected():
    ins = _valid_item()
    ins["campaigns_to_watch"] = [
        {"campaign_or_group": "TotallyFakeCampaign_99",
         "reason": "It appears strong.", "evidence": ["top_campaigns"]}]
    out = llm.validate_insights(ins, _ctx())
    assert out is not None
    assert out["campaigns_to_watch"] == [], "fake campaign must be stripped"


def test_4_unsupported_causality_rejected():
    ins = _valid_item()
    ins["risks"] = [
        {"risk": "Revenue dropped because of competitor activity.",
         "evidence": ["channels"], "severity": "high",
         "recommended_action": "Increase budget."}]
    out = llm.validate_insights(ins, _ctx())
    assert out is not None and out["risks"] == []
    ins2 = _valid_item(claim="Sales will definitely increase to $100,000.")
    assert llm.validate_insights(ins2, _ctx()) is None


def test_5_valid_grounded_response_passes():
    ins = _valid_item()
    ins["suggested_budget_shift"] = {
        "summary": "Shifting budget from Google toward Meta may improve efficiency.",
        "source_channel": "google", "target_channel": "meta",
        "evidence": ["channels[meta].roas_p50"], "confidence": "medium"}
    log = []
    out = llm.validate_insights(ins, _ctx(), log)
    assert out is not None
    assert out["forecast_summary"][0]["claim"].startswith("Google")
    assert out["suggested_budget_shift"]["target_channel"] == "meta"


def test_6_provider_chain_falls_through_to_template(monkeypatch):
    def boom(ctx):
        raise RuntimeError("provider down")
    for prov in ("_try_ollama", "_try_openai", "_try_gemini", "_try_groq"):
        monkeypatch.setattr(llm, prov, boom)
    res = llm.explain(_ctx())
    assert res["provider"] == "template"
    assert res["guardrail"] == "fallback"
    assert len(res["guardrail_log"]) == 4  # every provider logged its failure
    assert res["narrative"]  # deterministic narrative still rendered


def test_missing_evidence_rejected():
    ins = {"forecast_summary": [
        {"claim": "Google is forecast to contribute $100,000 (P50).",
         "confidence": "high"}]}  # no evidence key
    assert llm.validate_insights(ins, _ctx()) is None
