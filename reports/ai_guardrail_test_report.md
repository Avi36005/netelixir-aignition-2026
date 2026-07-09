# ROAScast AI / LLM Guardrail Test Report

The AI layer lives **only** in `product/backend/app/llm.py`. It is never
imported by `run.sh` or `src/`. The forecasting model produces every number;
the LLM only *explains* a compact structured JSON context under strict
guardrails, and any unsafe/ungrounded response is replaced by a deterministic
template.

## Provider order (first available wins)

1. **Ollama** (local server) — private, free, offline
2. **OpenAI** (`OPENAI_API_KEY`)
3. **Gemini** (`GEMINI_API_KEY` / `GOOGLE_API_KEY`)
4. **Groq** (`GROQ_API_KEY`)
5. **Deterministic template** — no key, no network, always succeeds

Every provider is called over plain `urllib` REST (no SDK dependency). Each
response is grounding-validated; a failed parse or failed grounding discards the
response and the chain moves on, ending at the template floor.

## Local Ollama models supported

Preference order in `_OLLAMA_PREFERENCE`: `qwen3:8b` (default) →
`mistral-small3.2:24b` → `mistral:7b` → `llama3.2:3b`. `OLLAMA_MODEL` overrides.
The client only uses a model that is **already pulled** (`/api/tags`); it never
auto-downloads. `nomic-embed-text` is embeddings-only and is not used for chat.

## Bug found and fixed

**`_PROVIDERS` captured function references at import time**, so the provider
chain could not be re-dispatched and `monkeypatch` in tests had no effect —
`test_6_provider_chain_falls_through_to_template` failed (it returned `openai`
instead of `template`, silently making a live API call using a key from
`.env`). Fixed by storing provider **names** and resolving `_try_<name>` from
module globals at call time (`llm.py`). All guardrail tests now pass and the
chain is correctly mockable/testable.

## Guardrail test results (`tests/test_llm_guardrails.py`) — 7/7 PASS

| # | scenario | covered by | result |
|---|---|---|---|
| 1 | No key / no Ollama → deterministic fallback | test_1 | PASS |
| 2 | LLM invents an unsupported number → reject | test_2 | PASS |
| 3 | LLM invents an unsupported campaign → strip | test_3 | PASS |
| 4 | LLM claims unsupported causality (competitor) → reject | test_4 | PASS |
| 4b | Banned deterministic phrase ("will definitely") → reject | test_4 | PASS |
| 5 | Valid grounded output → pass guardrail | test_5 | PASS |
| 6 | All providers fail → template fallback | test_6 | PASS (fixed) |
| 7 | Item missing evidence references → reject | test_missing_evidence | PASS |

### Additional guardrails enforced in code (`validate_insights`)

- **Unsupported channel** in a budget shift → dropped (`source_channel` /
  `target_channel` must be in the allow-list built from the context).
- **Invalid JSON / non-object** response → parsed defensively; unusable → None →
  template fallback (`_parse_json_text`, tolerant of ```` ```json ```` fences and
  `<think>…</think>` blocks).
- **Numeric grounding**: every number in prose must match a context value within
  ~1.5% (rounding tolerant) or be a trivial small integer (window/quantile
  labels).
- **Causality allow-list**: banned phrases include competitor activity,
  inflation, algorithm changes, market crash, and absolute-certainty language.
- **Empty core section**: if no grounded `forecast_summary` claim survives, the
  whole response is rejected and the template is used.

## No-key / no-network behaviour

With `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`
unset and Ollama unreachable, `/explain` returns `provider=template`,
`guardrail=fallback`, and a fully-populated, grounded insight set. No crash.

## AI Insights payload (for the UI)

`explain()` returns `provider`, `guardrail` status, `guardrail_log`,
`narrative`, and structured `insights` (forecast_summary, risks,
budget_recommendations, campaigns_to_watch, suggested_budget_shift,
limitations) — everything the AI Insights page shows.

## Scoring isolation confirmed

`grep -rniE "openai|gemini|groq|anthropic|ollama"` over `run.sh` and `src/`
returns nothing. The scored pipeline has no AI dependency, no network, no keys.
Secrets (`product/backend/.env`, `KEYSS U.txt`) are gitignored and untracked.
