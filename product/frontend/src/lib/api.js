// Thin API client with a DEMO fallback: every call tries the real backend
// first (Vite dev proxy /api -> :8000); when the backend is unreachable the
// Upload page offers a clearly-labeled local demo dataset so the UI still
// walks end to end. The frontend never invents live numbers — demo mode is
// flagged in the header and all demo values live in mock.js.
import { MOCK } from './mock.js'

const BASE = import.meta.env.VITE_API_BASE || '/api'
const DEMO_ID = 'demo'

async function jpost(path, body) {
  const r = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText)
  return r.json()
}

export const api = {
  health: () => fetch(BASE + '/health').then((r) => r.json()),

  demoSession: () => ({ session_id: DEMO_ID, summary: MOCK.summary, mock: true }),

  upload: async (files) => {
    const fd = new FormData()
    if (files.google) fd.append('google', files.google)
    if (files.meta) fd.append('meta', files.meta)
    ;(files.other || []).forEach((f) => fd.append('files', f))
    const r = await fetch(BASE + '/upload', { method: 'POST', body: fd })
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText)
    return r.json()
  },

  validate: (sid) =>
    sid === DEMO_ID ? Promise.resolve(MOCK.validate) : jpost('/validate', { session_id: sid }),

  forecast: (sid, windows, budget_overrides) =>
    sid === DEMO_ID
      ? Promise.resolve(MOCK.forecast)
      : jpost('/forecast', { session_id: sid, windows, budget_overrides }),

  simulate: (sid, scenario) =>
    sid === DEMO_ID
      ? Promise.resolve(MOCK.simulate(scenario))
      : jpost('/simulate', { session_id: sid, scenario }),

  explain: (sid, window_days, budget_overrides) =>
    sid === DEMO_ID
      ? Promise.resolve(MOCK.explain)
      : jpost('/explain', { session_id: sid, window_days, budget_overrides }),
}

export const fmtUSD = (x) =>
  x == null ? '—' : '$' + Number(x).toLocaleString('en-US', { maximumFractionDigits: 0 })
export const fmtUSDc = (x) => {
  if (x == null) return '—'
  const v = Number(x)
  if (Math.abs(v) >= 1e6) return '$' + (v / 1e6).toFixed(1) + 'M'
  if (Math.abs(v) >= 1e4) return '$' + (v / 1e3).toFixed(0) + 'k'
  return fmtUSD(v)
}
export const fmtROAS = (x) => (x == null ? '—' : Number(x).toFixed(2) + 'x')
export const fmtPct = (x) => (x == null ? '—' : (Number(x) * 100).toFixed(1) + '%')
