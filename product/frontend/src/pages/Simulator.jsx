import { useEffect, useRef, useState } from 'react'
import { api, fmtUSD, fmtROAS } from '../lib/api.js'

export default function Simulator({ session }) {
  const [baseline, setBaseline] = useState(null)   // { channel: currentBudget }
  const [baseSim, setBaseSim] = useState(null)     // simulate(baseline) result
  const [scenario, setScenario] = useState(null)
  const [sim, setSim] = useState(null)
  const [err, setErr] = useState(null)
  const timer = useRef(null)

  useEffect(() => {
    api.forecast(session.session_id, [30])
      .then(async (r) => {
        const chans = r.rows.filter((x) => x.level === 'channel')
        const init = {}
        chans.forEach((c) => {
          init[c.channel] = Math.round(c.revenue_p50 / (c.roas_p50 || 1))
        })
        setBaseline(init)
        setScenario(init)
        const bs = await api.simulate(session.session_id, init)
        setBaseSim(bs)
        setSim(bs)
      })
      .catch((e) => setErr(e.message))
  }, [session.session_id])

  useEffect(() => {
    if (!scenario) return
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      api.simulate(session.session_id, scenario).then(setSim).catch((e) => setErr(e.message))
    }, 150)
    return () => clearTimeout(timer.current)
  }, [scenario, session.session_id])

  if (err) return <div className="card">Error: {err}</div>
  if (!baseline || !sim) return <div className="card text-neutral-400">Loading…</div>

  const channels = Object.keys(baseline)
  const dRev = baseSim ? sim.blended.revenue - baseSim.blended.revenue : 0
  const dRoas = baseSim ? sim.blended.roas - baseSim.blended.roas : 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Budget simulator</h1>
        <p className="text-neutral-500 mt-1">
          Adjust per-channel 30-day budgets and compare against the current plan.
        </p>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="card space-y-5">
          <div className="label">Budget scenario (30-day spend)</div>
          {channels.map((ch) => {
            const max = Math.max(baseline[ch] * 3, 1000)
            return (
              <div key={ch}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="font-medium capitalize">{ch}</span>
                  <span className="flex items-center gap-2">
                    <input
                      type="number" min={0}
                      className="border border-neutral-300 rounded px-2 py-1 w-28 text-right text-sm"
                      value={scenario[ch] ?? 0}
                      onChange={(e) =>
                        setScenario((s) => ({ ...s, [ch]: Number(e.target.value) }))}
                    />
                  </span>
                </div>
                <input
                  type="range" min={0} max={max}
                  step={Math.max(Math.round(max / 100), 1)}
                  value={scenario[ch] ?? 0}
                  onChange={(e) =>
                    setScenario((s) => ({ ...s, [ch]: Number(e.target.value) }))}
                  className="w-full accent-black"
                />
                <div className="text-xs text-neutral-500">
                  current: {fmtUSD(baseline[ch])}
                </div>
              </div>
            )
          })}
          <button className="btn-outline" onClick={() => setScenario({ ...baseline })}>
            Reset to current
          </button>
        </div>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Stat label="Current spend" value={fmtUSD(baseSim?.blended.budget)} />
            <Stat label="Simulated spend" value={fmtUSD(sim.blended.budget)} />
            <Stat label="Expected revenue" value={fmtUSD(sim.blended.revenue)}
              sub="P50 basis, simulated" />
            <Stat label="Expected ROAS" value={fmtROAS(sim.blended.roas)}
              sub="revenue ÷ spend" />
            <Stat label="Change in revenue"
              value={(dRev >= 0 ? '+' : '') + fmtUSD(dRev)} sub="vs current plan" />
            <Stat label="Change in ROAS"
              value={(dRoas >= 0 ? '+' : '') + dRoas.toFixed(2) + 'x'} sub="vs current plan" />
          </div>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <div className="label mb-3">Per-channel: current vs simulated</div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-neutral-500 border-b border-neutral-200 text-xs uppercase">
              <th className="py-2">Channel</th>
              <th className="text-right">Current spend</th>
              <th className="text-right">Simulated spend</th>
              <th className="text-right">Expected revenue</th>
              <th className="text-right">Expected ROAS</th>
              <th className="text-right">Δ spend</th>
            </tr>
          </thead>
          <tbody>
            {sim.channels.map((c) => {
              const delta = c.budget - (baseline[c.channel] || 0)
              return (
                <tr key={c.channel} className="border-b border-neutral-100">
                  <td className="py-2 capitalize font-medium">{c.channel}</td>
                  <td className="text-right">{fmtUSD(baseline[c.channel])}</td>
                  <td className="text-right">{fmtUSD(c.budget)}</td>
                  <td className="text-right">{fmtUSD(c.revenue)}</td>
                  <td className="text-right">{fmtROAS(c.roas)}</td>
                  <td className="text-right">{(delta >= 0 ? '+' : '') + fmtUSD(delta)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-neutral-500">
        Budget simulation is directional and based on historical ROAS and
        diminishing returns.
      </p>
    </div>
  )
}

function Stat({ label, value, sub }) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className="text-xl font-semibold mt-1">{value}</div>
      {sub && <div className="text-xs text-neutral-500 mt-1">{sub}</div>}
    </div>
  )
}
