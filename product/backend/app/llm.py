"""ROAScast AI Analyst — grounded LLM narrative layer. PRODUCT SIDE ONLY.

NEVER imported by run.sh / the scored pipeline. The forecasting engine produces
every number; the LLM only EXPLAINS a compact structured JSON context.

Provider order (first available wins):
    1. Ollama   (local server)      — qwen3:8b preferred; private, free, offline
    2. OpenAI   (OPENAI_API_KEY)    — strong chat model, temperature 0
    3. Gemini   (GEMINI_API_KEY)    — structured forecast explanation
    4. Groq     (GROQ_API_KEY)      — fast Llama fallback
    5. Deterministic template       — no key, no network, always works

The local LLM is NOT trained on the campaign dataset — the forecasting model
is. The LLM is grounded at runtime with structured forecast outputs plus the
guardrails below; it never generates forecast numbers.

Anti-hallucination controls:
  * The LLM gets ONLY a compact JSON context (never raw files).
  * temperature 0; a strict system prompt; JSON-only response contract.
  * Post-validation: every numeric token in a claim must exist in the context
    (rounding-tolerant); campaign/channel names must exist in the context;
    every item must carry evidence references. Violations drop the item; if
    parsing or evidence fails wholesale we fall back to the template.

All providers are called over plain REST (urllib) so the product backend needs
no extra SDK dependencies.
"""
from __future__ import annotations

import json
import os
import re
import textwrap
import urllib.request

# ---------------------------------------------------------------------------
# .env loading (tiny, dependency-free; product/backend/.env is gitignored)
# ---------------------------------------------------------------------------
def _load_env():
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.path.join(here, ".."), os.path.join(here, "..", "..")):
        path = os.path.abspath(os.path.join(d, ".env"))
        if not os.path.exists(path):
            continue
        try:
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except OSError:
            pass


_load_env()

SYSTEM_PROMPT = textwrap.dedent("""
    You are ROAScast AI Media Planner. You explain ecommerce revenue and ROAS
    forecasts using only the structured JSON context provided. You must not
    invent revenue, ROAS, spend, budgets, campaign names, dates, confidence
    scores, or causes. Every numeric claim must be copied from or directly
    supported by the JSON context. If the data is insufficient, say: 'Not
    enough evidence in the provided data.' Do not claim causality unless the
    evidence is explicitly present. Use cautious language such as 'may',
    'likely', 'appears', and 'based on the forecast output'. Never mention
    external market events, competitor activity, inflation, platform algorithm
    changes, or customer behavior unless present in the JSON context. Your
    output must be valid JSON only.

    All money is USD. ROAS is a dimensionless multiple (write "4.2x", never
    dollars). Forecasts are P10/P50/P90 ranges over an aggregate window, never
    daily. Respond with ONLY a JSON object matching exactly this schema:
    {
      "forecast_summary":[{"claim":"...","evidence":["field_or_row_reference"],"confidence":"high|medium|low"}],
      "risks":[{"risk":"...","evidence":["..."],"severity":"high|medium|low","recommended_action":"..."}],
      "budget_recommendations":[{"recommendation":"...","evidence":["..."],"expected_direction":"increase_revenue|protect_roas|reduce_risk|not_enough_evidence"}],
      "campaigns_to_watch":[{"campaign_or_group":"...","reason":"...","evidence":["..."]}],
      "suggested_budget_shift":{"summary":"...","source_channel":"...|null","target_channel":"...|null","evidence":["..."],"confidence":"high|medium|low"},
      "limitations":["..."]
    }
""").strip()

_INSIGHT_KEYS = ("forecast_summary", "risks", "budget_recommendations",
                 "campaigns_to_watch", "suggested_budget_shift", "limitations")

# Deterministic / unsupported-causality language is rejected outright.
_BANNED_PHRASES = (
    "will definitely", "guaranteed", "certainly", "without a doubt",
    "because of competitor", "competitor activity", "because of inflation",
    "inflation", "algorithm update", "algorithm change",
    "customers are changing behavior", "market crash",
)


# ---------------------------------------------------------------------------
# Context builder — the ONLY thing the LLM ever sees
# ---------------------------------------------------------------------------
def build_context(forecast_rows: list[dict], drivers: list[dict],
                  window_days: int, simulate: dict | None = None,
                  history: dict | None = None,
                  warnings: list | None = None) -> dict:
    def _lvl(name):
        return [r for r in forecast_rows
                if r["level"] == name and int(r["window_days"]) == window_days]

    blended = next(iter(_lvl("blended")), None)
    channels = _lvl("channel")
    campaigns = sorted(_lvl("campaign"),
                       key=lambda r: -float(r.get("revenue_p50", 0)))[:8]
    return {
        "forecast_window_days": window_days,
        "blended": blended,
        "channels": channels,
        "campaign_types": _lvl("campaign_type"),
        "top_campaigns": campaigns,
        "top_drivers": (drivers or [])[:6],
        "historical_summary": history,
        "validation_warnings": warnings or [],
        "budget_simulation": simulate,
        # Explicit allow-lists — the validator rejects anything outside these.
        "allowed_channels": sorted({str(r.get("channel", "")) for r in channels if r.get("channel")}),
        "allowed_campaigns": sorted({str(r.get("campaign", "")) for r in campaigns if r.get("campaign")}),
        "allowed_metrics": ["revenue_p10", "revenue_p50", "revenue_p90",
                            "roas_p10", "roas_p50", "roas_p90", "spend", "budget"],
    }


# ---------------------------------------------------------------------------
# Grounding validation
# ---------------------------------------------------------------------------
_NUM_RE = re.compile(r"-?\$?\d[\d,]*\.?\d*")


def _context_numbers(obj, acc=None):
    acc = acc if acc is not None else set()
    if isinstance(obj, dict):
        for v in obj.values():
            _context_numbers(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _context_numbers(v, acc)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        acc.add(float(obj))
    return acc


def _context_names(ctx):
    names = set()
    for key in ("channels", "campaign_types", "top_campaigns"):
        for r in ctx.get(key) or []:
            for f in ("channel", "campaign_type", "campaign"):
                if r.get(f):
                    names.add(str(r[f]).strip().lower())
    names.update({"google", "meta", "microsoft", "bing", "microsoft/bing", "blended"})
    return names


def _num_supported(value, allowed):
    """A number in prose counts as grounded if it matches a context value to
    ~1% (rounding for display) — or is a trivial small integer (window days,
    quantile labels, ordinal counts)."""
    if value in (10.0, 50.0, 90.0, 30.0, 60.0, 80.0) or abs(value) <= 12:
        return True
    for a in allowed:
        if a == 0:
            continue
        if abs(value - a) <= max(0.015 * abs(a), 0.51):
            return True
    return False


def _text_grounded(text, allowed):
    for tok in _NUM_RE.findall(str(text)):
        clean = tok.replace(",", "").replace("$", "")
        try:
            v = float(clean)
        except ValueError:
            continue
        if not _num_supported(v, allowed):
            return False
    return True


def _clean_language(*texts) -> bool:
    joined = " ".join(str(t).lower() for t in texts)
    return not any(p in joined for p in _BANNED_PHRASES)


def validate_insights(ins: dict, ctx: dict, log: list | None = None) -> dict | None:
    """Drop ungrounded items; return None if the response is unusable.

    ``log`` (optional list) collects human-readable rejection reasons so the
    backend can report WHY a guardrail fired.
    """
    log = log if log is not None else []
    if not isinstance(ins, dict):
        log.append("response is not a JSON object")
        return None
    allowed = _context_numbers(ctx)
    names = _context_names(ctx)
    out = {k: [] for k in _INSIGHT_KEYS}
    out["suggested_budget_shift"] = None

    def _ok_item(item, text_fields):
        if not isinstance(item, dict):
            log.append("dropped non-object item")
            return False
        if not item.get("evidence") or not isinstance(item["evidence"], list):
            log.append("dropped item without evidence references")
            return False
        if not _clean_language(*(item.get(f, "") for f in text_fields)):
            log.append("dropped item with deterministic/unsupported-causality language")
            return False
        if not all(_text_grounded(item.get(f, ""), allowed) for f in text_fields):
            log.append("dropped item citing a number not present in the context")
            return False
        return True

    for it in ins.get("forecast_summary") or []:
        if _ok_item(it, ("claim",)):
            out["forecast_summary"].append(it)
    for it in ins.get("risks") or []:
        if _ok_item(it, ("risk", "recommended_action")):
            out["risks"].append(it)
    for it in ins.get("budget_recommendations") or []:
        if _ok_item(it, ("recommendation",)):
            out["budget_recommendations"].append(it)
    for it in ins.get("campaigns_to_watch") or []:
        if not _ok_item(it, ("reason",)):
            continue
        ref = str(it.get("campaign_or_group", "")).strip().lower()
        if ref and (ref in names or any(ref in n or n in ref for n in names)):
            out["campaigns_to_watch"].append(it)
    shift = ins.get("suggested_budget_shift")
    if isinstance(shift, dict) and _ok_item(shift, ("summary",)):
        ok_chan = True
        for f in ("source_channel", "target_channel"):
            v = shift.get(f)
            if v and str(v).strip().lower() not in names:
                log.append("dropped budget shift: unknown channel " + repr(v))
                ok_chan = False
        if ok_chan:
            out["suggested_budget_shift"] = shift

    out["limitations"] = [str(x) for x in (ins.get("limitations") or [])
                          if _text_grounded(x, allowed) and _clean_language(x)]

    # Unusable if the core sections are empty — fall back to the template.
    if not out["forecast_summary"]:
        log.append("no grounded forecast_summary claims survived validation")
        return None
    return out


# ---------------------------------------------------------------------------
# Deterministic fallback — same structured schema, zero network, zero keys
# ---------------------------------------------------------------------------
def _money(x):
    try:
        return f"${float(x):,.0f}"
    except (TypeError, ValueError):
        return "$0"


def _template_insights(ctx: dict) -> dict:
    b = ctx.get("blended") or {}
    w = ctx["forecast_window_days"]
    chans = ctx.get("channels") or []
    summary, risks, recs, watch = [], [], [], []

    if b:
        summary.append({
            "claim": (f"Over the next {w} days, blended revenue is forecast at "
                      f"{_money(b.get('revenue_p50'))} expected (P50), with a range of "
                      f"{_money(b.get('revenue_p10'))} (P10) to {_money(b.get('revenue_p90'))} "
                      f"(P90) and an expected ROAS of {float(b.get('roas_p50', 0)):.2f}x (P50)."),
            "evidence": ["blended.revenue_p10", "blended.revenue_p50",
                         "blended.revenue_p90", "blended.roas_p50"],
            "confidence": "high",
        })
    if chans:
        top = max(chans, key=lambda c: float(c.get("revenue_p50", 0)))
        summary.append({
            "claim": (f"{top['channel'].title()} contributes the largest share of forecast "
                      f"revenue at {_money(top.get('revenue_p50'))} (P50), so changes in "
                      f"{top['channel'].title()} spend may have the largest blended impact."),
            "evidence": [f"channels[{top['channel']}].revenue_p50"],
            "confidence": "high",
        })
        best = max(chans, key=lambda c: float(c.get("roas_p50", 0)))
        recs.append({
            "recommendation": (f"{best['channel'].title()} shows the highest expected ROAS "
                               f"({float(best.get('roas_p50', 0)):.2f}x P50) among detected "
                               "channels; incremental budget appears most efficient there, "
                               "subject to diminishing returns."),
            "evidence": [f"channels[{best['channel']}].roas_p50"],
            "expected_direction": "increase_revenue",
        })
        for c in chans:
            spread = float(c.get("revenue_p90", 0)) - float(c.get("revenue_p10", 0))
            p50 = float(c.get("revenue_p50", 0))
            if p50 > 0 and spread > 4 * p50:
                risks.append({
                    "risk": (f"{c['channel'].title()} has a wide P10-P90 revenue range "
                             f"({_money(c.get('revenue_p10'))} to {_money(c.get('revenue_p90'))}), "
                             "so forecast confidence for this channel may be lower."),
                    "evidence": [f"channels[{c['channel']}].revenue_p10",
                                 f"channels[{c['channel']}].revenue_p90"],
                    "severity": "medium",
                    "recommended_action": "Review pacing weekly and re-forecast as new data arrives.",
                })
    for r in (ctx.get("top_campaigns") or [])[:3]:
        watch.append({
            "campaign_or_group": r.get("campaign", ""),
            "reason": (f"Top forecast contributor at {_money(r.get('revenue_p50'))} "
                       f"expected revenue (P50) over {w} days."),
            "evidence": [f"top_campaigns[{r.get('campaign', '')}].revenue_p50"],
        })
    if not risks:
        risks.append({
            "risk": "No channel-level anomaly flags in the current forecast output.",
            "evidence": ["channels"],
            "severity": "low",
            "recommended_action": "Maintain current allocation; re-evaluate as data arrives.",
        })
    shift = None
    if len(chans) >= 2:
        by_roas = sorted(chans, key=lambda c: float(c.get("roas_p50", 0)))
        lo_c, hi_c = by_roas[0], by_roas[-1]
        if lo_c["channel"] != hi_c["channel"]:
            shift = {
                "summary": ("Based on the forecast output, shifting incremental budget "
                            "from " + lo_c["channel"].title() + " "
                            "(" + format(float(lo_c.get("roas_p50", 0)), ".2f") + "x expected ROAS) toward "
                            + hi_c["channel"].title() + " "
                            "(" + format(float(hi_c.get("roas_p50", 0)), ".2f") + "x expected ROAS) may "
                            "improve blended efficiency, subject to diminishing returns."),
                "source_channel": lo_c["channel"],
                "target_channel": hi_c["channel"],
                "evidence": ["channels[" + lo_c["channel"] + "].roas_p50",
                             "channels[" + hi_c["channel"] + "].roas_p50"],
                "confidence": "medium",
            }
    return {
        "forecast_summary": summary,
        "risks": risks,
        "budget_recommendations": recs,
        "campaigns_to_watch": watch,
        "suggested_budget_shift": shift or {
            "summary": "Not enough evidence in the provided data.",
            "source_channel": None, "target_channel": None,
            "evidence": ["channels"], "confidence": "low",
        },
        "limitations": [
            "Forecast assumes budgets and attribution remain as observed in the input data.",
            "P10-P90 intervals are calibrated on historical backtests (~80% target coverage).",
            "Not enough evidence in the provided data to attribute changes to external market events.",
        ],
    }


def _render_narrative(ins: dict) -> str:
    """Markdown narrative from the validated structured insights."""
    parts = ["**Forecast Summary**"]
    parts += [f"- {i['claim']}" for i in ins["forecast_summary"]]
    parts.append("\n**Anomalies & Risks**")
    parts += [f"- {i['risk']} _Action: {i.get('recommended_action', 'n/a')}_"
              for i in ins["risks"]] or ["- None flagged."]
    parts.append("\n**Budget Recommendation**")
    parts += [f"- {i['recommendation']}" for i in ins["budget_recommendations"]] \
        or ["- Maintain current allocation."]
    if ins.get("campaigns_to_watch"):
        parts.append("\n**Campaigns to Watch**")
        parts += [f"- {i['campaign_or_group']}: {i['reason']}"
                  for i in ins["campaigns_to_watch"]]
    if ins.get("suggested_budget_shift"):
        parts.append("\n**Suggested Budget Shift**")
        parts.append("- " + str(ins["suggested_budget_shift"].get("summary", "")))
    if ins.get("limitations"):
        parts.append("\n**Limitations**")
        parts += [f"- {x}" for x in ins["limitations"]]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Providers (plain REST; short timeouts; any failure -> next provider)
# ---------------------------------------------------------------------------
_TIMEOUT = 45


def _post_json(url, payload, headers):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_json_text(text):
    text = re.sub(r"^```(?:json)?|```$", "", str(text).strip(), flags=re.M).strip()
    # tolerate <think>...</think> blocks from reasoning models (qwen3 etc.)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _user_msg(ctx):
    return ("Forecast context JSON (the ONLY source of truth):\n"
            + json.dumps(ctx, default=str)
            + "\n\nRespond with the JSON object only.")


def _try_openai(ctx):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    body = _post_json(
        "https://api.openai.com/v1/chat/completions",
        {"model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
         "temperature": 0,
         "response_format": {"type": "json_object"},
         "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": _user_msg(ctx)}]},
        {"Authorization": f"Bearer {key}"})
    return _parse_json_text(body["choices"][0]["message"]["content"])


def _try_gemini(ctx):
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return None
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    body = _post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        {"system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
         "contents": [{"role": "user", "parts": [{"text": _user_msg(ctx)}]}],
         "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}},
        {"x-goog-api-key": key})
    return _parse_json_text(body["candidates"][0]["content"]["parts"][0]["text"])


def _try_groq(ctx):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    body = _post_json(
        "https://api.groq.com/openai/v1/chat/completions",
        {"model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
         "temperature": 0,
         "response_format": {"type": "json_object"},
         "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": _user_msg(ctx)}]},
        {"Authorization": f"Bearer {key}"})
    return _parse_json_text(body["choices"][0]["message"]["content"])


# NOTE: qwen3:14b deliberately excluded — too heavy for the JSON-contract
# fallback role on this hardware; 8b answers faster and reliably.
_OLLAMA_PREFERENCE = ("qwen3:8b", "mistral-small3.2:24b",
                      "mistral:7b", "llama3.2:3b")


def _try_ollama(ctx):
    base = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    try:
        with urllib.request.urlopen(base + "/api/tags", timeout=3) as resp:
            tags = {m["name"] for m in json.loads(resp.read()).get("models", [])}
    except Exception:
        return None
    model = os.environ.get("OLLAMA_MODEL") or next(
        (m for m in _OLLAMA_PREFERENCE if m in tags), None)
    if not model:
        return None
    body = _post_json(
        base + "/api/chat",
        {"model": model, "stream": False, "format": "json",
         "options": {"temperature": 0},
         "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": _user_msg(ctx)}]},
        {})
    return _parse_json_text(body["message"]["content"])


# Provider order by NAME (not function reference) so the chain is resolved at
# call time — keeps the functions monkeypatchable in tests and lets a swapped
# implementation take effect without rebuilding this tuple.
_PROVIDERS = ("ollama", "openai", "gemini", "groq")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def explain(ctx: dict) -> dict:
    """{"narrative", "insights", "provider"} — always succeeds (template floor).

    Every provider response is grounded-validated against the context; a
    response that fails parsing or grounding is discarded and the chain moves
    on, ending at the deterministic template.
    """
    guardrail_log = []
    for name in _PROVIDERS:
        fn = globals()["_try_" + name]  # resolved now, so tests can patch it
        try:
            raw = fn(ctx)
        except Exception as exc:
            guardrail_log.append(name + ": provider error (" + type(exc).__name__ + ")")
            raw = None
        if raw is None:
            continue
        log = []
        ins = validate_insights(raw, ctx, log)
        if ins is not None:
            return {"narrative": _render_narrative(ins), "insights": ins,
                    "provider": name, "guardrail": "passed",
                    "guardrail_log": log}
        guardrail_log.append(name + ": rejected - " + "; ".join(log[:3]))
    ins = _template_insights(ctx)
    return {"narrative": _render_narrative(ins), "insights": ins,
            "provider": "template", "guardrail": "fallback",
            "guardrail_log": guardrail_log}
