# ROAScast Frontend Test Report

## Location & stack

| item | value |
|---|---|
| Frontend folder | `product/frontend/` |
| Framework | React 18 + Vite 6 + Tailwind CSS 3 (JavaScript/JSX, no TypeScript) |
| Charts | Recharts 2 |
| Node / npm | v24.16.0 / 11.13.0 |

## Install & build

| step | command | result |
|---|---|---|
| Dependencies | `npm install` | already present in `node_modules/`; resolves cleanly |
| Production build | `npm run build` (`vite build`) | **PASS** — 35 modules transformed, built in ~2.9s |

Build output:
```
dist/index.html                 0.44 kB
dist/assets/index-*.css        14.22 kB │ gzip 3.12 kB
dist/assets/index-*.js        177.08 kB │ gzip 55.00 kB
```
No TypeScript errors (project is JSX). No missing imports. No build warnings.

## Pages present & rendering

| page | file | status |
|---|---|---|
| Upload CSV | `src/pages/Upload.jsx` | present, builds |
| Validation Report | `src/pages/Validation.jsx` | present, builds |
| Forecast Dashboard (30/60/90 tabs) | `src/pages/Dashboard.jsx` | present, builds |
| Channel Breakdown | `src/pages/Breakdown.jsx` | present, builds |
| Budget Simulator | `src/pages/Simulator.jsx` | present, builds |
| AI Insights | `src/pages/Insights.jsx` | present, builds |

Sidebar navigation is wired in `src/App.jsx`.

## Design compliance (white/black requirement)

Verified in `src/index.css`:
- `:root { color-scheme: light; }` — light only, **no dark mode**.
- Body background `#ffffff`, text `#0a0a0a` (white background, black text).
- Comment in source: *"White + black, minimal. Light gray borders only. No
  gradients, no dark mode."*

## Backend-independent demo (mock fallback)

`src/lib/api.js` tries the real backend first (Vite proxy `/api` → :8000) and
falls back to `src/lib/mock.js` when the backend is unreachable. A demo session
id routes every call (validate/forecast/simulate/explain) to deterministic
mock data, so the UI demos fully **without a running backend**.

## Scoring isolation

The frontend is **not** imported by `run.sh` or `src/`. It has no effect on the
scored pipeline.

## Remaining risks

- None blocking. The frontend is a demo layer; if the backend is down the
  header flags mock mode and the demo continues on canned data.
