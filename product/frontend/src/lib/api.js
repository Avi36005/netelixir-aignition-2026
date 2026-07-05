// Thin API client. Uses the Vite dev proxy (/api -> :8000) by default; override
// with VITE_API_BASE for a deployed backend.
const BASE = import.meta.env.VITE_API_BASE || '/api'

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
  upload: async (files) => {
    const fd = new FormData()
    if (files.google) fd.append('google', files.google)
    if (files.meta) fd.append('meta', files.meta)
    ;(files.other || []).forEach((f) => fd.append('files', f))
    const r = await fetch(BASE + '/upload', { method: 'POST', body: fd })
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText)
    return r.json()
  },
  validate: (session_id) => jpost('/validate', { session_id }),
  forecast: (session_id, windows, budget_overrides) =>
    jpost('/forecast', { session_id, windows, budget_overrides }),
  simulate: (session_id, scenario) => jpost('/simulate', { session_id, scenario }),
  explain: (session_id, window_days, budget_overrides) =>
    jpost('/explain', { session_id, window_days, budget_overrides }),
}

export const fmtUSD = (x) =>
  x == null ? '—' : '$' + Number(x).toLocaleString('en-US', { maximumFractionDigits: 0 })
export const fmtROAS = (x) => (x == null ? '—' : Number(x).toFixed(2) + 'x')
