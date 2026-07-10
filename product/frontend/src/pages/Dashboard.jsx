import { useEffect, useMemo, useState } from 'react'
import { api, fmtUSD, fmtUSDc, fmtROAS } from '../lib/api.js'
import { confidenceOf, ConfidenceBadge, EmptyState, isSessionExpired } from '../lib/charts.jsx'

const WINDOWS = [30, 60, 90]

// Confidence from the calibrated interval: narrower P10–P90 (relative to the
// expected value) means the model is more certain. Derived from forecast
// output only — the frontend never invents numbers.
function confidence(b) {
  if (!b || !b.revenue_p50) return { label: '—', note: '' }
  const spread = (b.revenue_p90 - b.revenue_p10) / b.revenue_p50
  if (spread < 1.5) return { label: 'High', note: 'narrow P10–P90 interval' }
  if (spread < 3.5) return { label: 'Medium', note: 'moderate P10–P90 interval' }
  return { label: 'Low', note: 'wide P10–P90 interval' }
}

function RangeBar({ p10, p50, p90, max }) {
  if (!max) return null
  const x = (v) => Math.min((v / max) * 100, 100)
  return (
    <div className="relative h-3 bg-neutral-100 rounded">
      <div
        className="absolute h-3 bg-neutral-300 rounded"
        style={{ left: x(p10) + '%', width: Math.max(x(p90) - x(p10), 1) + '%' }}
      />
      <div
        className="absolute w-1 h-3 bg-black rounded"
        style={{ left: x(p50) + '%' }}
        title={'P50 ' + fmtUSD(p50)}
      />
    </div>
  )
}

export default function Dashboard({ session, onExpired }) {
  const [win, setWin] = useState(30)
  const [rows, setRows] = useState(null)
  const [guard, setGuard] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    setRows(null)
    api.forecast(session.session_id, null)
      .then((r) => { setRows(r.rows || []); setGuard(r.scale_guard || null) })
      .catch((e) => (isSessionExpired(e) ? onExpired?.() : setErr(e.message)))
  }, [session.session_id])

  const view = useMemo(() => {
    if (!rows) return null
    const r = rows.filter((x) => Number(x.window_days) === win)
    return {
      blended: r.find((x) => x.level === 'blended'),
      channels: r.filter((x) => x.level === 'channel')
        .sort((a, b) => b.revenue_p50 - a.revenue_p50),
    }
  }, [rows, win])

  if (err) return <div className="card">Error: {err}</div>
  if (!view) return <div className="card text-neutral-400">Forecasting…</div>

  const { blended, channels } = view
  if (!blended && channels.length === 0) {
    return (
      <EmptyState message="No forecast rows returned. Upload data with enough history and try again." />
    )
  }
  // The backend's OOD scale guard overrides the interval-width heuristic:
  // it knows whether the data sits inside the training distribution.
  const conf = guard && guard.fallback_used
    ? { label: guard.confidence,
        note: `out-of-distribution scale (OOD score ${Number(guard.ood_score).toFixed(2)})` }
    : confidence(blended)
  const maxRev = Math.max(...channels.map((c) => c.revenue_p90), 1)

  return (
    <div className="space-y-6">
      {guard?.warning && (
        <div className="card border-amber-300 bg-amber-50 text-amber-900 text-sm">
          <span className="font-medium">Scale mismatch — low confidence. </span>
          {guard.warning}
          <span className="text-amber-700">
            {' '}(model weight {Math.round(guard.model_weight * 100)}%, baseline
            weight {Math.round(guard.baseline_weight * 100)}%)
          </span>
        </div>
      )}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Forecast dashboard</h1>
        <div className="flex gap-1 border border-neutral-200 p-1 rounded-md">
          {WINDOWS.map((w) => (
            <button key={w} className={`tab ${win === w ? 'tab-active' : 'tab-idle'}`}
              onClick={() => setWin(w)}>
              {w} days
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card label="Expected revenue (P50)" value={fmtUSDc(blended?.revenue_p50)}
          sub={`${win}-day window total`} />
        <Card label="Revenue range (P10–P90)"
          value={`${fmtUSDc(blended?.revenue_p10)} – ${fmtUSDc(blended?.revenue_p90)}`}
          sub="P10 low estimate – P90 high estimate" small />
        <Card label="Expected ROAS (P50)" value={fmtROAS(blended?.roas_p50)}
          sub="revenue ÷ planned spend" />
        <Card label="ROAS range (P10–P90)"
          value={`${fmtROAS(blended?.roas_p10)} – ${fmtROAS(blended?.roas_p90)}`}
          sub="P10 low estimate – P90 high estimate" small />
        <Card label="Forecast confidence" value={conf.label} sub={conf.note} />
      </div>

      <div className="card">
        <div className="label mb-4">
          Revenue range by channel — bar spans P10 (low) to P90 (high), black tick = P50 (expected)
        </div>
        <div className="space-y-4">
          {channels.map((c) => (
            <div key={c.channel}>
              <div className="flex justify-between text-sm mb-1">
                <span className="font-medium capitalize">{c.channel}</span>
                <span className="text-neutral-600">
                  {fmtUSDc(c.revenue_p10)} (P10) · <b className="text-black">{fmtUSDc(c.revenue_p50)} (P50)</b> · {fmtUSDc(c.revenue_p90)} (P90)
                </span>
              </div>
              <RangeBar p10={c.revenue_p10} p50={c.revenue_p50} p90={c.revenue_p90} max={maxRev} />
              <div className="text-xs text-neutral-500 mt-1">
                ROAS {fmtROAS(c.roas_p10)} (P10) – {fmtROAS(c.roas_p50)} (P50) – {fmtROAS(c.roas_p90)} (P90)
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-neutral-500 mt-4">
          Aggregate {win}-day window totals — never daily forecasts.
        </p>
      </div>

      <div className="card">
        <div className="label mb-3">Confidence by channel</div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-neutral-500 border-b border-neutral-200 text-xs uppercase">
              <th className="py-2">Channel</th>
              <th>Confidence</th>
              <th className="text-right">Expected revenue (P50)</th>
              <th className="text-right">Expected ROAS (P50)</th>
              <th>Basis</th>
            </tr>
          </thead>
          <tbody>
            {channels.map((c) => {
              const level = guard?.fallback_used && guard.confidence === 'Low'
                ? 'Low' : confidenceOf(c)
              return (
                <tr key={c.channel} className="border-b border-neutral-100">
                  <td className="py-2 capitalize font-medium">{c.channel}</td>
                  <td><ConfidenceBadge level={level} /></td>
                  <td className="text-right tabular-nums">{fmtUSD(c.revenue_p50)}</td>
                  <td className="text-right tabular-nums">{fmtROAS(c.roas_p50)}</td>
                  <td className="text-neutral-500 text-xs">
                    {guard?.fallback_used && guard.confidence === 'Low'
                      ? 'OOD scale mismatch — baseline-blended forecast'
                      : 'relative width of the P10–P90 interval'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Card({ label, value, sub, small }) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className={small ? 'text-lg font-semibold mt-1' : 'metric mt-1'}>{value}</div>
      {sub && <div className="text-xs text-neutral-500 mt-1">{sub}</div>}
    </div>
  )
}
