# ROAScast — Product Layer (Track 2)

The **online half** of ROAScast: a FastAPI backend + React dashboard with a
grounded LLM narrative. It lives on the far side of the **network wall** from the
scored core and **imports the exact same forecasting math** (`src/forecasting/`)
that powers `run.sh` — so the demo and the scored `predictions.csv` can never
disagree.

> The scored Track-1 core (offline, no network, `run.sh` → `predictions.csv`)
> is the parent directory. `run.sh` never installs or runs anything here.

```
Google/Meta CSV ─► SHARED CORE (src/forecasting) ─┬─► Track 1: run.sh (offline)
                                                  └─► Track 2: this product layer
                                                        FastAPI + React + LLM
```

## Backend (FastAPI)

Six endpoints, all calling the shared core via `app/core.ForecastService`:

| Endpoint | Purpose |
|---|---|
| `GET /health` | model version + pipeline status |
| `POST /upload` | Google + Meta CSVs → normalize, summary, `session_id` |
| `POST /validate` | campaign consistency (mapping coverage, gaps, drift) |
| `POST /forecast` | windows + optional budget override → full reconciled hierarchy |
| `POST /simulate` | budget scenario → response-curve revenue/ROAS (fast, curve-only) |
| `POST /explain` | grounded Gemini/Groq narrative (3 sections) + drivers |

**Run:**

```bash
cd product/backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**LLM is optional.** With no API key, `/explain` returns a deterministic,
**grounded** narrative built from the real forecast numbers — so the demo works
fully offline. Set `GEMINI_API_KEY` (and/or `GROQ_API_KEY`) in `.env` to use a
live model (see `.env.example`). The LLM only narrates; it never touches the math.

## Frontend (React + Vite + Tailwind + Recharts)

Six pages, black-and-white agency aesthetic:

1. **Upload** — drop both CSVs, inline data summary, "Run Forecast".
2. **Forecast** — 30/60/90 tabs, four metric cards, interval **range bars**
   (P10→P90 per channel, P50 tick — *no date axis*), campaign-type contribution.
3. **Budget Simulator** — per-channel sliders → live `/simulate`, saturating
   response curves (diminishing returns visible), current-vs-simulated deltas.
4. **Channel Breakdown** — expandable Channel → Type → Campaign table, P10/P50/P90.
5. **AI Insights** — grounded narrative (3 sections), top model drivers, regenerate.
6. **Validation Report** — campaign → type → channel mapping + consistency issues.

**Run:**

```bash
cd product/frontend
npm install
npm run dev          # http://localhost:5173, proxies /api -> http://localhost:8000
```

For a deployed backend, set `VITE_API_BASE` to the API URL.

## Visualization rule

Aggregate forecasts are shown as **range bars and metric cards, never daily line
charts** — each bar is the total for the whole 30/60/90-day window. The only line
chart is the budget **response curve** (spend → revenue), which is not a time axis.
