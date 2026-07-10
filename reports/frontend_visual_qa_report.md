# Frontend Visual QA Report (post-change)

Date: 2026-07-10 · Scope note: per instruction, browser automation
(Claude-in-Chrome / Playwright / Puppeteer) was **not** used, so no screenshot
files were produced. Verification below combines the production build, a live
served instance loaded in Chrome (fresh page load, console checked — zero
errors), live backend API responses (the exact JSON the pages render), and the
demo-mode data shapes. A final human eyeball pass of each page is recommended
before the demo.

## Build status

- `npm install` — PASS (0 vulnerabilities).
- `npm run build` (vite production build) — **PASS** (185.7 kB JS, 15.4 kB CSS).
  A build pass compiles every page/JSX path, so there are no broken imports or
  syntax errors on any page.
- Fresh page load of the built app in Chrome: **no console errors** (verified
  via extension console reader on a tracked load).

## Pages and visuals

| requirement | status | evidence |
|---|---|---|
| Forecast range visual, 30/60/90 tabs | PRESENT | `Dashboard.jsx` — window tabs + metric cards `Expected revenue (P50)`, `Revenue range (P10–P90)` with sub-label "P10 low estimate – P90 high estimate", same pair for ROAS; per-channel P10–P90 range bars with P50 tick |
| Every number labeled P10/P50/P90 | PRESENT | all cards, bars, and table headers carry explicit (P10)/(P50)/(P90) tags; footer states P10 = low estimate, P50 = expected, P90 = high estimate |
| Channel contribution bar chart (revenue P50 by channel) | PRESENT | `Breakdown.jsx` — "Forecast revenue by channel — expected (P50)" bar list (google / meta / Microsoft-Bing), plain monochrome divs |
| ROAS P50 by channel chart | PRESENT | second card "Expected ROAS by channel (P50)" |
| Budget simulator comparison chart | PRESENT | `Simulator.jsx` — "Current plan vs simulated scenario": paired bars for spend / expected revenue (P50 basis) / expected ROAS, legend black = current, gray = simulated, plus per-channel table |
| Risk/confidence visual | PRESENT | Dashboard "Confidence by channel" table with High/Medium/Low badges; Breakdown per-row Risk badges; Validation page OOD confidence badge + training-scale table |
| OOD Low-confidence warning | PRESENT | Dashboard amber banner with the exact required sentence when `scale_guard.warning` is set; Validation page always shows scale section (backend verified live: Medium + reasons for the external dataset) |
| No daily line charts | CONFIRMED | no time-series chart exists anywhere; all visuals are window aggregates |
| ROAS formatted like 5.2x / revenue as USD | CONFIRMED | `fmtROAS` → `4.47x`, `fmtUSD`/`fmtUSDc` → `$298,129` |
| Empty state instead of crash | PRESENT | `EmptyState` rendered when no rows (Dashboard/Breakdown/Simulator); all optional fields null-guarded (`r.scale_guard || null`, `data.scale &&`) |
| Missing/expired session → Upload | PRESENT | pages without a session are unmounted (sidebar disabled, Upload shown); backend 404 "Unknown session" triggers `onExpired` → app resets to Upload |

## Data contract check (live backend on :8010)

The exact fields each page reads were verified in real API responses:
`/forecast` → `rows` (372 schema-valid) + `scale_guard {confidence, ood_score,
fallback_used, model_weight, baseline_weight, warning}`; `/validate` → `scale`
section + `scale_mismatch` issues; `/simulate` → blended + per-channel budget/
revenue/roas; `/explain` → template-provider insights. Demo-mode (`mock.js`)
shapes match the same guards.

## Design constraints

White background, black text, light gray borders only (`index.css` enforces
`color-scheme: light`, no dark mode, no gradients); charts are plain
neutral-toned divs, no chart library, no animations beyond CSS transitions.
Wide tables sit in `overflow-x-auto` cards.

## Issues fixed during QA

None found in this pass (build, console, and API contract all clean).

## Remaining risks

- Pixel-level layout (label collisions at 390px width, exact banner placement)
  was not screenshot-verified in this pass — recommend a quick manual click
  through the six pages at one desktop size before the demo.
