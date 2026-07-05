import { useEffect, useMemo, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  ReferenceDot, Legend,
} from 'recharts'
import { api, fmtUSD, fmtROAS } from '../lib/api.js'

const COLORS = ['#171717', '#737373', '#a3a3a3', '#d4d4d4']

export default function Simulator({ session }) {
  const [baseline, setBaseline] = useState(null)
  const [scenario, setScenario] = useState({})
  const [sim, setSim] = useState(null)
  const [err, setErr] = useState(null)

  // Seed sliders from the channels present in the upload.
  useEffect(() => {
    api
      .simulate(session.session_id, {})
      .catch(() => null) // empty scenario may 200 with empty; fall through
    api
      .forecast(session.session_id, [30])
      .then((r) => {
        const chans = r.rows.filter((x) => x.level === 'channel')
        const init = {}
        chans.forEach((c) => {
          init[c.channel] = Math.round(c.revenue_p50 / (c.roas_p50 || 1))
        })
        setBaseline(init)
        setScenario(init)
      })
      .catch((e) => setErr(e.message))
  }, [session.session_id])

  useEffect(() => {
    if (!scenario || Object.keys(scenario).length === 0) return
    const t = setTimeout(() => {
      api.simulate(session.session_id, scenario).then(setSim).catch((e) => setErr(e.message))
    }, 150)
    return () => clearTimeout(t)
  }, [scenario, session.session_id])

  const curveData = useMemo(() => {
    if (!sim?.curves) return []
    // merge per-channel curve points onto a shared spend axis
    const channels = Object.keys(sim.curves)
    const len = sim.curves[channels[0]]?.length || 0
    const out = []
    for (let i = 0; i < len; i++) {
      const row = { spend: sim.curves[channels[0]][i].spend }
      channels.forEach((ch) => { row[ch] = sim.curves[ch][i]?.revenue })
      out.push(row)
    }
    return out
  }, [sim])

  if (err) return <div className="card text-red-600">{err}</div>
  if (!baseline) return <div className="card text-neutral-400">Loading…</div>

  const channels = Object.keys(baseline)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Budget simulator</h1>
        <p className="text-neutral-500 mt-1">
          Slide per-channel spend and watch revenue respond along the saturating
          curve — diminishing returns are explicit.
        </p>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="card space-y-5">
          {channels.map((ch, i) => {
            const max = Math.max(baseline[ch] * 3, 1000)
            return (
              <div key={ch}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="font-medium capitalize" style={{ color: COLORS[i] }}>
                    {ch}
                  </span>
                  <span>{fmtUSD(scenario[ch])}</span>
                </div>
                <input
                  type="range" min={0} max={max} step={Math.max(Math.round(max / 100), 1)}
                  value={scenario[ch] ?? 0}
                  onChange={(e) =>
                    setScenario((s) => ({ ...s, [ch]: Number(e.target.value) }))}
                  className="w-full accent-neutral-900"
                />
              </div>
            )
          })}
          <button className="btn-ghost border border-neutral-200"
            onClick={() => setScenario({ ...baseline })}>
            Reset to current
          </button>
        </div>

        <div className="card">
          <div className="label mb-3">Response curves (spend → revenue)</div>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={curveData} margin={{ top: 5, right: 15, bottom: 0, left: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="spend" tickFormatter={(v) => '$' + (v / 1000).toFixed(0) + 'k'}
                tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={(v) => '$' + (v / 1000).toFixed(0) + 'k'}
                tick={{ fontSize: 11 }} width={55} />
              <Tooltip formatter={(v) => fmtUSD(v)}
                labelFormatter={(l) => 'Spend ' + fmtUSD(l)} />
              <Legend />
              {channels.map((ch, i) => (
                <Line key={ch} type="monotone" dataKey={ch} stroke={COLORS[i]}
                  dot={false} strokeWidth={2} />
              ))}
              {sim?.channels?.map((c, i) => (
                <ReferenceDot key={c.channel} x={c.budget} y={c.revenue} r={5}
                  fill={COLORS[channels.indexOf(c.channel)]} stroke="#fff" />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {sim && (
        <div className="card overflow-x-auto">
          <div className="label mb-3">Current vs simulated</div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-neutral-500 border-b border-neutral-200">
                <th className="py-2">Channel</th><th>Budget</th>
                <th>Revenue</th><th>ROAS</th><th>Marginal ROAS</th><th>Δ vs current</th>
              </tr>
            </thead>
            <tbody>
              {sim.channels.map((c) => {
                const baseBudget = baseline[c.channel] || 0
                const delta = c.budget - baseBudget
                return (
                  <tr key={c.channel} className="border-b border-neutral-100">
                    <td className="py-2 capitalize font-medium">{c.channel}</td>
                    <td>{fmtUSD(c.budget)}</td>
                    <td>{fmtUSD(c.revenue)}</td>
                    <td>{fmtROAS(c.roas)}</td>
                    <td className="text-neutral-500">{fmtROAS(c.marginal_roas)}</td>
                    <td className={delta >= 0 ? 'text-neutral-900' : 'text-red-600'}>
                      {delta >= 0 ? '+' : ''}{fmtUSD(delta)}
                    </td>
                  </tr>
                )
              })}
              <tr className="font-semibold">
                <td className="py-2">Blended</td>
                <td>{fmtUSD(sim.blended.budget)}</td>
                <td>{fmtUSD(sim.blended.revenue)}</td>
                <td>{fmtROAS(sim.blended.roas)}</td>
                <td></td><td></td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
