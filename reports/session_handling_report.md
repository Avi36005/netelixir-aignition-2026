# Session Handling Report (post-change)

Date: 2026-07-10 · Backend under test: no-key uvicorn instance (port 8010).

## Normal flow

- `POST /upload` with the three official CSVs → **session created**
  (`session_id: 49b598aeca62`, 25,562 rows summarized) — verified live.
- The frontend stores that one session object in app state and passes it to
  every page (Validation, Forecast, Breakdown, Simulator, Insights) — all
  requests observed carry the same `session_id`; there is no per-page session.
- The external dataset upload produced a second, independent session
  (`3cf639189749`) whose validation correctly reported the OOD scale mismatch.

## Missing session

- The app has no client-side session persistence (nothing in localStorage), so
  "missing session" = fresh load: the sidebar disables every page except
  Upload and only Upload renders. No crash, no blank screen — by construction.

## Expired / unknown session (backend restart equivalent)

- Backend behavior: `POST /forecast {"session_id":"nope"}` → **HTTP 404**
  `"Unknown session_id 'nope'. Upload first."` — clear, safe, no stack trace,
  verified live. Since the session store is in-memory, a backend restart makes
  every old id take exactly this path; no stale/fake forecast can be served.
- Frontend behavior: every data page (Validation, Dashboard, Breakdown,
  Simulator, Insights) catches fetch errors, detects the "Unknown session"
  message (`isSessionExpired` in `lib/charts.jsx`), and calls `onExpired`,
  which clears the session and returns the user to the Upload page. Any other
  error renders an inline error card instead.

## Verdict

**PASS** — one session id flows through all pages; unknown/expired sessions
produce a clear 404 on the backend and an automatic return to Upload on the
frontend; no fake forecasts, no crashes.
