import { useEffect, useMemo, useState } from 'react'
import { api, fmtUSD, fmtROAS, fmtPct } from '../lib/api.js'
import { BarRow, EmptyState, isSessionExpired } from '../lib/charts.jsx'

const WINDOWS = [30, 60, 90]

// Risk flag from forecast output only: very wide interval or expected ROAS < 1.
function riskOf(r) {
  if ((r.roas_p50 ?? 0) < 1) return 'Watch'
  if (r.revenue_p50 > 0 && (r.revenue_p90 - r.revenue_p10) > 5 * r.revenue_p50) return 'Watch'
  return 'OK'
}

export default function Breakdown({ session, onExpired }) {
  const [win, setWin] = useState(30)
  const [q, setQ] = useState('')
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    api.forecast(session.session_id, null)
      .then((r) => setRows(r.rows || []))
      .catch((e) => (isSessionExpired(e) ? onExpired?.() : setErr(e.message)))
  }, [session.session_id])

  const view = useMemo(() => {
    if (!rows) return null
    const r = rows.filter((x) => Number(x.window_days) === win)
    const blended = r.find((x) => x.level === 'blended')
    const totalP50 = blended?.revenue_p50 || 1
    const flat = r
      .filter((x) => x.level !== 'blended')
      .map((x) => ({
        ...x,
        spend: x.roas_p50 > 0 ? x.revenue_p50 / x.roas_p50 : 0,
        contribution: x.revenue_p50 / totalP50,
        risk: riskOf(x),
      }))
      .sort((a, b) =>
        a.level.localeCompare(b.level) || b.revenue_p50 - a.revenue_p50)
    const needle = q.trim().toLowerCase()
    return needle
      ? flat.filter((x) =>
          [x.channel, x.campaign_type, x.campaign, x.level]
            .join(' ').toLowerCase().includes(needle))
      : flat
  }, [rows, win, q])

  if (err) return <div className="card">Error: {err}</div>
  if (!view) return <div className="card text-neutral-400">Loading…</div>

  const channelRows = rows
    .filter((x) => x.level === 'channel' && Number(x.window_days) === win)
    .sort((a, b) => b.revenue_p50 - a.revenue_p50)
  const maxRev = Math.max(...channelRows.map((c) => c.revenue_p50), 1e-9)
  const maxRoas = Math.max(...channelRows.map((c) => c.roas_p50), 1e-9)
  const chName = (c) => (c === 'microsoft' ? 'Microsoft/Bing' : c)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Channel breakdown</h1>
        <div className="flex gap-3 items-center">
          <input
            className="border border-neutral-300 rounded-md px-3 py-2 text-sm w-56"
            placeholder="Search channel / type / campaign"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <div className="flex gap-1 border border-neutral-200 p-1 rounded-md">
            {WINDOWS.map((w) => (
              <button key={w} className={`tab ${win === w ? 'tab-active' : 'tab-idle'}`}
                onClick={() => setWin(w)}>{w}d</button>
            ))}
          </div>
        </div>
      </div>

      {channelRows.length === 0 ? (
        <EmptyState message={`No channel-level forecast for the ${win}-day window.`} />
      ) : (
        <div className="grid md:grid-cols-2 gap-6">
          <div className="card">
            <div className="label mb-3">Forecast revenue by channel — expected (P50)</div>
            <div className="space-y-3">
              {channelRows.map((c) => (
                <BarRow key={c.channel} label={chName(c.channel)}
                  value={c.revenue_p50} max={maxRev}
                  display={fmtUSD(c.revenue_p50)} tag="P50" />
              ))}
            </div>
            <p className="text-xs text-neutral-500 mt-3">
              {win}-day window totals in USD.
            </p>
          </div>
          <div className="card">
            <div className="label mb-3">Expected ROAS by channel (P50)</div>
            <div className="space-y-3">
              {channelRows.map((c) => (
                <BarRow key={c.channel} label={chName(c.channel)}
                  value={c.roas_p50} max={maxRoas}
                  display={fmtROAS(c.roas_p50)} tag="P50" />
              ))}
            </div>
            <p className="text-xs text-neutral-500 mt-3">
              ROAS = forecast revenue ÷ planned spend (dimensionless multiple).
            </p>
          </div>
        </div>
      )}

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-neutral-500 border-b border-neutral-200 text-xs uppercase">
              <th className="text-left py-2">Level</th>
              <th className="text-left">Channel</th>
              <th className="text-left">Type</th>
              <th className="text-left">Campaign</th>
              <th className="text-right">Spend</th>
              <th className="text-right">Rev P10</th>
              <th className="text-right">Rev P50</th>
              <th className="text-right">Rev P90</th>
              <th className="text-right">ROAS P10</th>
              <th className="text-right">ROAS P50</th>
              <th className="text-right">ROAS P90</th>
              <th className="text-right">Contribution</th>
              <th className="text-center">Risk</th>
            </tr>
          </thead>
          <tbody>
            {view.map((r, i) => (
              <tr key={i}
                className={`border-b border-neutral-100 ${r.level === 'channel' ? 'font-semibold' : ''}`}>
                <td className="py-2 text-neutral-500">{r.level.replace('_', ' ')}</td>
                <td className="capitalize">{r.channel}</td>
                <td>{r.campaign_type || '—'}</td>
                <td className="max-w-[180px] truncate">{r.campaign || '—'}</td>
                <td className="text-right tabular-nums">{fmtUSD(r.spend)}</td>
                <td className="text-right tabular-nums">{fmtUSD(r.revenue_p10)}</td>
                <td className="text-right tabular-nums font-medium">{fmtUSD(r.revenue_p50)}</td>
                <td className="text-right tabular-nums">{fmtUSD(r.revenue_p90)}</td>
                <td className="text-right tabular-nums">{fmtROAS(r.roas_p10)}</td>
                <td className="text-right tabular-nums font-medium">{fmtROAS(r.roas_p50)}</td>
                <td className="text-right tabular-nums">{fmtROAS(r.roas_p90)}</td>
                <td className="text-right tabular-nums">{fmtPct(r.contribution)}</td>
                <td className="text-center">
                  <span className={r.risk === 'OK' ? 'badge badge-pass' : 'badge badge-warn'}>
                    {r.risk}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-neutral-500">
        Contribution = share of the blended P50 revenue for the selected window.
        Numbers are coherent across levels: campaigns sum to types, types to
        channels, channels to the blended total.
      </p>
    </div>
  )
}
