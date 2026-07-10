# Backend + AI Guardrail Sanity Report (post-change)

Date: 2026-07-10 · Mode under test: **no API keys, Ollama unavailable**
(`OPENAI_API_KEY= GEMINI_API_KEY= GOOGLE_API_KEY= GROQ_API_KEY= ANTHROPIC_API_KEY=`
set empty so `.env` cannot repopulate them; `OLLAMA_HOST=http://localhost:9`
points at a dead port). Backend: `uvicorn app.main:app --port 8010`.

## Results — official dataset session

| check | result |
|---|---|
| backend starts without keys | PASS (startup complete, `/health` → model roascast-1.0.0) |
| `/upload` (3 official CSVs) | PASS — 25,562 rows, 109 campaigns, session created |
| `/validate` | PASS — ok:true, scale: **High**, ood 0.0, fallback:false, weights 1.0/0.0 |
| `/forecast` | PASS — 372 schema-valid rows + `scale_guard` (High, no fallback) |
| `/simulate` | PASS — blended revenue/ROAS returned (curve-based) |
| `/explain` with no LLM available | PASS — **provider: "template"**, guardrail: "fallback", grounded structured insights returned; no crash, no invented numbers (deterministic template reads only forecast output) |
| unknown session_id | PASS — HTTP 404 with clear message `Unknown session_id 'nope'. Upload first.` |

## Results — external (large) dataset session

| check | result |
|---|---|
| `/upload` external CSVs (124k rows) | PASS |
| `/validate` scale section | Medium confidence, ood 0.448, fallback true, weights 0.6/0.4, reasons: monthly revenue 14.6x / spend 25.2x above training median; same reasons injected as `scale_mismatch` warning issues |
| `/forecast` | PASS — `scale_guard` Medium / 0.339 / fallback true; blended 30d ROAS P50 2.56x (no collapse) |

Note: `/validate` computes the OOD score from the full daily history (exact
monthly sums) while `/forecast` uses the prediction feature table plus the
model-divergence signal, so the scores differ slightly (0.448 vs 0.339); both
land in the same Medium bucket and report the same weights.

## Guardrail properties confirmed

- LLM never generates forecast numbers; with zero providers reachable the
  deterministic template still produces the full insight schema.
- AI insights are only produced from a live forecast context (the `/explain`
  endpoint computes the forecast first; no session → 404, never fabricated).
- `run.sh` is completely independent of all of this — the scored path imports
  no LLM/network/backend module (verified by grep in the official report).

**Final status: PASS.**
