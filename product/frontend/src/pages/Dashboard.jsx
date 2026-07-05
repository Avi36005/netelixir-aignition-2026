import { useEffect, useMemo, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  ErrorBar, CartesianGrid,
} from 'recharts'
import { api, fmtUSD, fmtROAS } from '../lib/api.js'

const WINDOWS = [30, 60, 90]

export default function Dashboard({ session }) {
  const [win, setWin] = useState(30)
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    setRows(null)
    api
      .forecast(session.session_id, null)
      .then((r) => setRows(r.rows))
      .catch((e) => setErr(e.message))
  }, [session.session_id])

  const view = useMemo(() => {
    if (!rows) return null
    const r = rows.filter((x) => Number(x.window_days) === win)
    const blended = r.find((x) => x.level === 'blended')
    const channels = r.filter((x) => x.level === 'channel')
    const types = r.filter((x) => x.level === 'campaign_type')
    return { blended, channels, types }
  }, [rows, win])

  if (err) return <div className="card text-red-600">{err}</div>
  if (!view) return <div className="card text-neutral-400">Forecasting…</div>

  const { blended, channels, types } = view
  const topChannel = [...channels].sort((a, b) => b.revenue_p50 - a.revenue_p50)[0]
  const totalSpend = channels.reduce(
    (s, c) => s + c.revenue_p50 / (c.roas_p50 || 1), 0)

  const chartData = channels.map((c) => ({
    name: c.channel,
    p50: c.revenue_p50,
    // ErrorBar wants [downErr, upErr] relative to p50
    err: [c.revenue_p50 - c.revenue_p10, c.revenue_p90 - c.revenue_p50],
  }))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Forecast dashboard</h1>
        <div className="flex gap-1 bg-neutral-100 p-1 rounded-md">
          {WINDOWS.map((w) => (
            <button
              key={w}
              className={`tab ${win === w ? 'tab-active' : 'tab-idle'}`}
              onClick={() => setWin(w)}
            >
              {w}d
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card label={`Blended revenue (${win}d)`}
          value={fmtUSD(blended?.revenue_p50)}
          sub={`${fmtUSD(blended?.revenue_p10)} – ${fmtUSD(blended?.revenue_p90)}`} />
        <Card label="Blended ROAS"
          value={fmtROAS(blended?.roas_p50)}
          sub={`${fmtROAS(blended?.roas_p10)} – ${fmtROAS(blended?.roas_p90)}`} />
        <Card label="Planned spend" value={fmtUSD(totalSpend)} sub="across channels" />
        <Card label="Top channel"
          value={topChannel ? topChannel.channel : '—'}
          sub={topChannel ? fmtUSD(topChannel.revenue_p50) + ' P50' : ''} />
      </div>

      <div className="card">
        <div className="label mb-3">Revenue range by channel (P10 → P90, tick = P50)</div>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(v) => '$' + (v / 1000).toFixed(0) + 'k'}
              tick={{ fontSize: 12 }} width={60} />
            <Tooltip formatter={(v) => fmtUSD(v)} />
            <Bar dataKey="p50" fill="#171717" radius={[3, 3, 0, 0]} maxBarSize={70}>
              <ErrorBar dataKey="err" width={6} strokeWidth={2} stroke="#a3a3a3" />
              {chartData.map((_, i) => <Cell key={i} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="text-xs text-neutral-400 mt-2">
          Range bars (not a daily line) — each bar is the aggregate revenue forecast
          for the whole {win}-day window. Whiskers show the P10–P90 interval.
        </p>
      </div>

      <div className="card">
        <div className="label mb-3">Campaign-type contribution (P50 revenue)</div>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={types.map((t) => ({
            name: `${t.channel}/${t.campaign_type}`, value: t.revenue_p50,
          }))} layout="vertical" margin={{ left: 120 }}>
            <XAxis type="number" tickFormatter={(v) => '$' + (v / 1000).toFixed(0) + 'k'}
              tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={120} />
            <Tooltip formatter={(v) => fmtUSD(v)} />
            <Bar dataKey="value" fill="#404040" radius={[0, 3, 3, 0]} maxBarSize={18} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function Card({ label, value, sub }) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className="metric mt-1">{value}</div>
      {sub && <div className="text-xs text-neutral-500 mt-1">{sub}</div>}
    </div>
  )
}
